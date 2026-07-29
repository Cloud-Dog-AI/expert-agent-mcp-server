# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
MCP Server Implementation

License: Apache 2.0
Ownership: Cloud Dog
Description: Model Context Protocol server for agent-to-agent interactions

Related Requirements: FR1.7, FR1.25
Related Tasks: T039, T063
Related Architecture: CC1.1.3
Related Tests: ST1.2, AT1.23

Recent Changes:
- Initial implementation
- W28M-1634: fail async jobs closed when a tool returns an MCP error envelope
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from typing import Optional, Dict, Any, List
from cloud_dog_api_kit import create_app
from cloud_dog_api_kit.mcp import InMemoryAsyncJobStore, LegacySSEConfig, register_mcp_routes
from cloud_dog_api_kit.mcp import transport as mcp_transport
from cloud_dog_api_kit.middleware.timeout import TimeoutMiddleware
from fastapi import Request
from fastapi.responses import StreamingResponse

from src.servers.base import BaseServer
from src.config.loader import get_config
from src.core.session.manager import SessionManager
from src.core.job.manager import JobManager
from src.core.job.timeout_contract import (
    positive_timeout_seconds,
    resolve_execution_timeout_seconds,
)
from src.core.llm.manager import LLMManager
from src.database.connection import get_db
from src.database.models import Job
from src.servers.mcp.tools import MCPTools
from src.utils.logger import get_logger

logger = get_logger(__name__)

_ASYNC_RUNTIME_INSTANCE_ENV = "MCP_ASYNC_RUNTIME_INSTANCE"
_ASYNC_RUNTIME_INSTANCE_PATH = Path("/tmp/expert-agent-mcp-async-runtime-instance")


def _async_runtime_instance() -> str:
    """Return the identity shared by workers in exactly one container runtime.

    A wait=false report runner is in-process.  Its durable Job can therefore
    survive a container replacement even though the asyncio task cannot.  The
    service hostname is deliberately stable across replacements, so the runtime
    writes one random token into container-ephemeral ``/tmp``.  Uvicorn workers
    in that container share it; a replacement receives a fresh filesystem and
    therefore a different token.
    """
    configured = str(os.environ.get(_ASYNC_RUNTIME_INSTANCE_ENV) or "").strip()
    if configured:
        return configured
    try:
        descriptor = os.open(
            str(_ASYNC_RUNTIME_INSTANCE_PATH),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        # A sibling Uvicorn worker may have won O_EXCL but not written the token
        # yet.  Wait briefly rather than accepting an unmarked async job.
        for _ in range(20):
            try:
                token = _ASYNC_RUNTIME_INSTANCE_PATH.read_text(encoding="utf-8").strip()
            except OSError:
                token = ""
            if token:
                return token
            time.sleep(0.01)
        return ""
    except OSError:
        return ""
    try:
        token = uuid.uuid4().hex
        os.write(descriptor, token.encode("ascii"))
        return token
    finally:
        os.close(descriptor)


def _async_result_failure(result: Any) -> Optional[str]:
    """Return a useful failure message for a failed async tool result.

    MCP tools can report failure either by raising or by returning an MCP
    ``isError`` envelope.  Async job status must reflect both forms; otherwise
    callers and quality gates see a completed job whose result is an error.
    """

    if not isinstance(result, dict):
        return None

    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        nested_failure = _async_result_failure(nested_result)
        if nested_failure:
            return nested_failure

    structured_content = result.get("structuredContent")
    if isinstance(structured_content, dict):
        structured_failure = _async_result_failure(structured_content)
        if structured_failure:
            return structured_failure

    explicit_error = result.get("error")
    if explicit_error:
        if isinstance(explicit_error, dict):
            explicit_error = (
                explicit_error.get("message")
                or explicit_error.get("detail")
                or explicit_error
            )
        return str(explicit_error)[:1000]

    if result.get("isError") is not True:
        return None

    for key in ("message", "detail"):
        value = result.get(key)
        if value:
            return str(value)[:1000]

    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                return str(item["text"])[:1000]
    return "MCP tool returned an error result"


def _find_first_nested_value(value: Any, target_key: str, max_depth: int = 8) -> Any:
    """Return the first value matching ``target_key`` in a JSON-like result tree."""
    seen: set[int] = set()

    def walk(node: Any, depth: int) -> Any:
        if depth > max_depth:
            return None
        if isinstance(node, (dict, list)):
            node_id = id(node)
            if node_id in seen:
                return None
            seen.add(node_id)
        if isinstance(node, dict):
            if target_key in node and node[target_key] not in (None, ""):
                return node[target_key]
            for nested_key in ("result", "structuredContent", "data", "notification"):
                if nested_key in node:
                    found = walk(node[nested_key], depth + 1)
                    if found not in (None, ""):
                        return found
            for nested in node.values():
                found = walk(nested, depth + 1)
                if found not in (None, ""):
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item, depth + 1)
                if found not in (None, ""):
                    return found
        elif isinstance(node, str):
            text = node.strip()
            if text and text[:1] in "{[" and len(text) <= 20000:
                try:
                    return walk(json.loads(text), depth + 1)
                except (TypeError, ValueError):
                    return None
        return None

    return walk(value, 0)


def _compact_invocation_result(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    compact: Dict[str, Any] = {}
    for key in (
        "service_name",
        "service_id",
        "tool_name",
        "status",
        "message_id",
        "id",
        "delivered",
        "written",
        "figures",
        "result_count",
        "chunk_ids",
        "source_ids",
    ):
        if key in value and value[key] not in (None, ""):
            compact[key] = value[key]
    notification = value.get("notification")
    if isinstance(notification, dict):
        slim_notification = {
            key: notification[key]
            for key in ("message_id", "id", "status", "state")
            if notification.get(key) not in (None, "")
        }
        if slim_notification:
            compact["notification"] = slim_notification
    return compact or {
        "status": value.get("status") or "ok",
    }


def _compact_wait_false_result(tool_name: str, result: Any) -> Any:
    """Keep async execute_tool poll results small while preserving delivery IDs.

    Long document runs return the full generated output, traces and service
    payloads. Persisting that whole object as the MCP wait=false job result can
    leave the durable job stuck after the actual notification was sent. Keep
    every values-safe invocation summary so pollers retain an auditable path to
    terminal action tools, while excluding report prose and raw tool payloads.
    """
    if tool_name != "execute_tool" or not isinstance(result, dict):
        return result
    large_result_keys = {
        "output_text",
        "services_invoked",
        "post_service_results",
        "agent_trace",
        "delegations",
    }
    if not any(key in result for key in large_result_keys):
        return result

    compact: Dict[str, Any] = {
        "compact_async_result": True,
    }
    for key in (
        "expert_id",
        "llm_model",
        "mode",
        "agent_strategy",
        "session_id",
        "execution_time_ms",
        "token_usage",
    ):
        if result.get(key) not in (None, ""):
            compact[key] = result[key]

    output_text = result.get("output_text")
    if isinstance(output_text, str):
        compact["output_chars"] = len(output_text)
        compact["output_sha256"] = hashlib.sha256(output_text.encode("utf-8")).hexdigest()

    message_id = _find_first_nested_value(result, "message_id")
    if message_id not in (None, ""):
        compact["message_id"] = message_id

    for key in ("services_invoked", "post_service_results"):
        items = result.get(key)
        if isinstance(items, list):
            compact[key] = [_compact_invocation_result(item) for item in items]
            compact[f"{key}_count"] = len(items)
            compact[f"{key}_trace_complete"] = True

    return compact


class SourceBackedAsyncJobStore(InMemoryAsyncJobStore):
    """Keep MCP async jobs visible in the application's durable Jobs surface.

    The shared MCP console links every ``wait=false`` acknowledgement to the
    Jobs page.  The API-kit in-memory store alone cannot satisfy that contract:
    its UUID exists only inside the MCP process and is absent from ``/api/jobs``.
    This store retains the API-kit status contract while creating and updating
    a corresponding database Job whose metadata contains the platform job id.
    """

    _HEARTBEAT_INTERVAL_SECONDS = 15.0
    _CANCELLATION_POLL_SECONDS = 1.0
    _REPLAY_SECRET_ARGUMENT_KEYS = {
        "api_key",
        "apikey",
        "authorization",
        "bearer",
        "cookie",
        "credential",
        "credentials",
        "password",
        "secret",
        "token",
        "x_api_key",
    }

    def __init__(self, resume_runner_factory: Any = None) -> None:
        super().__init__()
        self._heartbeat_interval_seconds = self._positive_float_config(
            "mcp_server.async_job_heartbeat_seconds",
            self._HEARTBEAT_INTERVAL_SECONDS,
        )
        self._stale_after_seconds = max(
            self._heartbeat_interval_seconds * 2,
            self._required_positive_float_config(
                "mcp_server.async_job_stale_after_seconds",
            ),
        )
        self._execution_timeout_seconds = self._required_positive_float_config(
            "mcp_server.async_job_execution_timeout_seconds",
        )
        # A wait=false acknowledgement must remain executable after the HTTP
        # worker/container that accepted it is replaced.  The server supplies a
        # small factory rather than serialising a closure: only JSON-safe tool
        # arguments are persisted on the Job, never request credentials.
        self._resume_runner_factory = resume_runner_factory

    @staticmethod
    def _positive_float_config(key: str, default: float) -> float:
        try:
            value = float(get_config(key))
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    @staticmethod
    def _required_positive_float_config(key: str) -> float:
        """Resolve a required timeout from the compiled configuration."""
        return positive_timeout_seconds(get_config(key), field_name=key)

    def _resolve_execution_timeout_seconds(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> float:
        """Preserve an execute_tool wall budget through the async wrapper."""
        parameters = (
            arguments.get("parameters")
            if tool_name == "execute_tool" and isinstance(arguments, dict)
            else None
        )
        return resolve_execution_timeout_seconds(
            parameters if isinstance(parameters, dict) else None,
            configured_timeout_seconds=self._execution_timeout_seconds,
        )

    @classmethod
    def _replayable_arguments(cls, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Return JSON-safe resume arguments without accepting credentials.

        Durable jobs are database-visible.  Persisting an API key, bearer token
        or password there would turn a resilience feature into a credential
        disclosure path.  Fail closed before acknowledging wait=false when a
        caller tries to include one; normal MCP authentication remains in the
        request headers and the accepted job carries only its safe invocation.
        """
        def _walk(value: Any, path: str = "arguments") -> Any:
            if isinstance(value, dict):
                copied: Dict[str, Any] = {}
                for key, item in value.items():
                    key_text = str(key)
                    if key_text.strip().lower() in cls._REPLAY_SECRET_ARGUMENT_KEYS:
                        raise ValueError(
                            "MCP_ASYNC_REPLAY_REJECTED: credential-bearing "
                            f"argument at {path}.{key_text} cannot be persisted"
                        )
                    copied[key_text] = _walk(item, f"{path}.{key_text}")
                return copied
            if isinstance(value, list):
                return [_walk(item, f"{path}[]") for item in value]
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            raise ValueError(
                "MCP_ASYNC_REPLAY_REJECTED: non-JSON argument at "
                f"{path} cannot be persisted"
            )

        replayable = _walk(dict(arguments or {}))
        # Force JSON encoding now, rather than discovering an invalid payload
        # only after the caller has received an acknowledgement.
        return json.loads(json.dumps(replayable, ensure_ascii=False))

    def _start_heartbeat_worker(
        self,
        app_job_id: int,
    ) -> tuple[threading.Event, threading.Thread]:
        """Create a heartbeat worker backed by the shared durable Job record."""
        stop = threading.Event()
        return stop, threading.Thread(
            target=self._heartbeat_source_job,
            args=(app_job_id, stop),
            daemon=True,
            name=f"mcp-async-heartbeat-{app_job_id}",
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _is_stale_source_job(self, job: Job, metadata: Dict[str, Any]) -> bool:
        """Return whether an in-process async execution can no longer be alive.

        MCP async execution is intentionally in-process.  A container replacement
        therefore destroys the task, while the database Job remains.  The runner
        refreshes this heartbeat while it is alive; after the lease expires, the
        job must become terminal instead of reporting a false permanent running
        status to Scheduler or an operator.
        """
        heartbeat = self._parse_timestamp(metadata.get("mcp_async_heartbeat_at"))
        if heartbeat is None:
            heartbeat = self._parse_timestamp(
                metadata.get("mcp_async_started_at")
                or getattr(job, "updated_at", None)
                or getattr(job, "created_at", None)
            )
        if heartbeat is None:
            return True
        stale_after_seconds = self._stale_after_seconds
        persisted_timeout = metadata.get("mcp_async_execution_timeout_seconds")
        if persisted_timeout not in (None, ""):
            try:
                stale_after_seconds = max(
                    stale_after_seconds,
                    positive_timeout_seconds(
                        persisted_timeout,
                        field_name="mcp_async_execution_timeout_seconds",
                    ),
                )
            except ValueError:
                # Invalid historical metadata cannot make the configured
                # staleness contract less safe.
                pass
        return (datetime.now(timezone.utc) - heartbeat).total_seconds() > stale_after_seconds

    @staticmethod
    def _is_replaced_runtime_instance(metadata: Dict[str, Any]) -> bool:
        """Return whether a running durable job belongs to a replaced container."""
        recorded = str(metadata.get("mcp_async_runtime_instance") or "").strip()
        current = _async_runtime_instance()
        return bool(recorded and current and recorded != current)

    def submit(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        runner = context.get("runner")
        if not callable(runner):
            raise TypeError("async job context requires a callable 'runner'")

        result_formatter = context.get("result_formatter")
        if result_formatter is not None and not callable(result_formatter):
            raise TypeError(
                "async job context 'result_formatter' must be callable when provided"
            )

        platform_job_id = f"job-{uuid.uuid4().hex}"
        heartbeat_lease_token = uuid.uuid4().hex
        delivery_idempotency_key = f"mcp-async-delivery-{platform_job_id}"
        # The normal document publisher accepts this data parameter and forwards
        # it to Notification-Agent.  A resumed model run therefore cannot emit a
        # duplicate message if the original runtime was replaced at the delivery
        # boundary.  Other tools simply ignore the parameter.
        execution_arguments = dict(arguments or {})
        if tool_name == "execute_tool":
            execution_parameters = dict(execution_arguments.get("parameters") or {})
            execution_parameters.setdefault(
                "delivery_idempotency_key", delivery_idempotency_key
            )
            execution_arguments["parameters"] = execution_parameters
        arguments.clear()
        arguments.update(execution_arguments)
        replay_arguments = self._replayable_arguments(execution_arguments)
        execution_timeout_seconds = self._resolve_execution_timeout_seconds(
            tool_name,
            execution_arguments,
        )
        app_job_id = self._create_source_job(
            platform_job_id,
            tool_name,
            context.get("request"),
            replay_arguments,
            delivery_idempotency_key,
            heartbeat_lease_token,
            execution_timeout_seconds=execution_timeout_seconds,
        )
        with self._lock:
            self._jobs[platform_job_id] = {
                "status": "pending",
                "tool_name": tool_name,
                "arguments": dict(arguments),
                "app_job_id": app_job_id,
                "execution_timeout_seconds": execution_timeout_seconds,
            }

        task = asyncio.create_task(
            self._run_source_job(
                platform_job_id,
                app_job_id,
                runner,
                result_formatter,
                heartbeat_lease_token,
                execution_timeout_seconds=execution_timeout_seconds,
            )
        )
        with self._lock:
            self._tasks[platform_job_id] = task
        return platform_job_id

    def get_status(self, platform_job_id: str) -> Dict[str, Any]:
        """Return live status, falling back to the durable source Job.

        The MCP endpoint can be served by a different Uvicorn worker than the
        worker that accepted a ``wait=false`` request.  The shared in-memory
        store is therefore only a fast path; the application Job is the common
        status record across workers and remains available after replacement.
        """
        live = super().get_status(platform_job_id)
        if live.get("status") != "not_found":
            return live

        durable = self._get_durable_status(platform_job_id)
        return durable if durable is not None else live

    def _get_durable_status(self, platform_job_id: str) -> Optional[Dict[str, Any]]:
        """Rehydrate the MCP polling payload from its persisted application Job."""
        db_gen = get_db()
        db = next(db_gen)
        try:
            job = (
                db.query(Job)
                .filter(Job.job_type == "mcp_execute_tool")
                .filter(Job.metadata_json.like(f'%"mcp_platform_job_id": "{platform_job_id}"%'))
                .order_by(Job.id.desc())
                .first()
            )
            if job is None:
                return None

            try:
                metadata = json.loads(job.metadata_json) if job.metadata_json else {}
            except (TypeError, ValueError):
                metadata = {}
            try:
                result = json.loads(job.response_received) if job.response_received else None
            except (TypeError, ValueError):
                result = job.response_received
            try:
                error_info = json.loads(job.error_info_json) if job.error_info_json else {}
            except (TypeError, ValueError):
                error_info = {"message": job.error_info_json}

            source_status = str(job.status or "pending").strip().lower()
            running_statuses = {"running", "processing", "in_progress"}
            resumable_statuses = running_statuses | {"pending"}
            if source_status in resumable_statuses and self._is_replaced_runtime_instance(metadata):
                # The old runtime is decisively gone.  Claim the persisted job
                # once, rebuild its runner from the safe stored arguments, and
                # leave duplicate pollers observing the same running job.
                recovery_outcome = self._resume_replaced_source_job(
                    platform_job_id,
                    job,
                    metadata,
                )
                # The atomic claim writes the source Job before this response;
                # report it as running even though the newly scheduled task may
                # not receive its first event-loop slice until after this poll.
                if recovery_outcome is not False:
                    source_status = "running"
                else:
                    source_status = "failed"
                    error_info = {
                        "message": (
                            "MCP_ASYNC_RECOVERY_UNAVAILABLE: unable to resume the "
                            "persisted job; submit a new normal scheduler run"
                        )
                    }
            elif source_status in running_statuses:
                stale_source_job = self._is_stale_source_job(job, metadata)
                if stale_source_job:
                    error = (
                        "MCP async execution was interrupted before completion: "
                        "the worker heartbeat expired. Retry the normal scheduler run."
                    )
                    self._update_source_job(
                        int(job.id),
                        status="failed",
                        error_info={"message": error, "reason": "async_worker_heartbeat_expired"},
                        metadata={
                            "mcp_async_state": "interrupted",
                            "mcp_async_interrupted_at": self._timestamp(),
                        },
                    )
                    source_status = "failed"
                    error_info = {"message": error}
            if source_status in {"completed", "succeeded", "success"}:
                status = "completed"
            elif source_status in {"failed", "cancelled", "canceled", "error"}:
                status = "failed"
            elif source_status in {"running", "processing", "in_progress"}:
                status = "running"
            else:
                status = "pending"

            payload: Dict[str, Any] = {
                "status": status,
                "tool_name": metadata.get("mcp_tool_name"),
                "app_job_id": int(job.id),
            }
            replay_arguments = metadata.get("mcp_async_replay_arguments")
            if isinstance(replay_arguments, dict):
                payload["arguments"] = dict(replay_arguments)
            persisted_timeout = metadata.get(
                "mcp_async_execution_timeout_seconds"
            )
            if persisted_timeout not in (None, ""):
                try:
                    payload["execution_timeout_seconds"] = (
                        positive_timeout_seconds(
                            persisted_timeout,
                            field_name=(
                                "mcp_async_execution_timeout_seconds"
                            ),
                        )
                    )
                except ValueError as exc:
                    # Never replace corrupt durable metadata with the process
                    # default: expose an explicit contract error so callers
                    # and evidence validators fail closed.
                    payload["timeout_contract_error"] = str(exc)
            if result is not None:
                payload["result"] = result
            if status == "failed":
                payload["error"] = str(
                    error_info.get("message") or error_info.get("detail") or error_info or "Job failed"
                )
            return payload
        except Exception as exc:
            logger.warning("Unable to rehydrate MCP job %s: %s", platform_job_id, exc)
            return None
        finally:
            db_gen.close()

    def _claim_source_job_recovery(
        self,
        app_job_id: int,
        expected_lease_token: str,
        replacement_lease_token: str,
        metadata: Dict[str, Any],
    ) -> Optional[bool]:
        """Atomically hand a replaced durable job to one new runtime worker."""
        if not expected_lease_token:
            return False
        updated_metadata = dict(metadata)
        now = self._timestamp()
        try:
            resume_count = int(updated_metadata.get("mcp_async_resume_count") or 0)
        except (TypeError, ValueError):
            resume_count = 0
        updated_metadata.update(
            {
                "mcp_async_state": "recovering",
                "mcp_async_runtime_instance": _async_runtime_instance(),
                "mcp_async_lease_token": replacement_lease_token,
                "mcp_async_heartbeat_at": now,
                "mcp_async_recovered_at": now,
                "mcp_async_resume_count": resume_count + 1,
            }
        )
        db_gen = get_db()
        db = next(db_gen)
        try:
            # The unique lease token is an optimistic concurrency guard.  Two
            # Uvicorn workers can both observe a replacement, but only one can
            # replace the old token in this single SQL update.
            rows = (
                db.query(Job)
                .filter(Job.id == int(app_job_id))
                .filter(Job.status.in_({"pending", "running", "processing", "in_progress"}))
                .filter(
                    Job.metadata_json.like(
                        f'%"mcp_async_lease_token": "{expected_lease_token}"%'
                    )
                )
                .update(
                    {
                        Job.status: "running",
                        Job.metadata_json: json.dumps(updated_metadata),
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            return rows == 1
        except Exception as exc:
            db.rollback()
            logger.warning("Unable to claim MCP async recovery for job %s: %s", app_job_id, exc)
            return False
        finally:
            db_gen.close()

    def _resume_replaced_source_job(
        self,
        platform_job_id: str,
        job: Job,
        metadata: Dict[str, Any],
    ) -> bool:
        """Schedule one safe replay after a decisive runtime replacement."""
        app_job_id = int(job.id)
        tool_name = str(metadata.get("mcp_tool_name") or "").strip()
        replay_arguments = metadata.get("mcp_async_replay_arguments")
        previous_lease_token = str(metadata.get("mcp_async_lease_token") or "").strip()
        if not tool_name or not isinstance(replay_arguments, dict) or not previous_lease_token:
            error = (
                "MCP_ASYNC_RECOVERY_UNAVAILABLE: persisted replay metadata is missing; "
                "submit a new normal scheduler run"
            )
            self._update_source_job(
                app_job_id,
                status="failed",
                error_info={"message": error, "reason": "async_replay_metadata_missing"},
                metadata={
                    "mcp_async_state": "failed",
                    "mcp_async_finished_at": self._timestamp(),
                },
            )
            return False
        if not callable(self._resume_runner_factory):
            error = "MCP_ASYNC_RECOVERY_UNAVAILABLE: runner factory is not configured"
            self._update_source_job(
                app_job_id,
                status="failed",
                error_info={"message": error, "reason": "async_replay_factory_missing"},
                metadata={
                    "mcp_async_state": "failed",
                    "mcp_async_finished_at": self._timestamp(),
                },
            )
            return False

        replacement_lease_token = uuid.uuid4().hex
        if not self._claim_source_job_recovery(
            app_job_id,
            previous_lease_token,
            replacement_lease_token,
            metadata,
        ):
            # Another current-runtime worker may have already replaced this
            # lease.  Do not tell Scheduler the job failed merely because this
            # poller lost the optimistic claim; the winning worker owns it.
            return None
        try:
            runner, result_formatter = self._resume_runner_factory(
                tool_name,
                dict(replay_arguments),
            )
            execution_timeout_seconds = self._resolve_execution_timeout_seconds(
                tool_name,
                replay_arguments,
            )
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._run_source_job(
                    platform_job_id,
                    app_job_id,
                    runner,
                    result_formatter,
                    replacement_lease_token,
                    execution_timeout_seconds=execution_timeout_seconds,
                )
            )
        except Exception as exc:
            error = f"MCP_ASYNC_RECOVERY_UNAVAILABLE: unable to resume durable job: {exc}"
            self._update_source_job(
                app_job_id,
                status="failed",
                error_info={"message": error, "reason": "async_replay_start_failed"},
                metadata={
                    "mcp_async_state": "failed",
                    "mcp_async_finished_at": self._timestamp(),
                },
            )
            return False
        with self._lock:
            self._jobs[platform_job_id] = {
                "status": "running",
                "tool_name": tool_name,
                "arguments": dict(replay_arguments),
                "app_job_id": app_job_id,
                "execution_timeout_seconds": execution_timeout_seconds,
            }
            self._tasks[platform_job_id] = task
        return True

    async def _run_source_job(
        self,
        platform_job_id: str,
        app_job_id: int,
        runner: Any,
        result_formatter: Any,
        heartbeat_lease_token: Optional[str] = None,
        execution_timeout_seconds: Optional[float] = None,
    ) -> None:
        timeout_seconds = (
            positive_timeout_seconds(
                execution_timeout_seconds,
                field_name="per-job execution timeout",
            )
            if execution_timeout_seconds is not None
            else self._execution_timeout_seconds
        )
        with self._lock:
            job = dict(self._jobs.get(platform_job_id) or {})
            job["status"] = "running"
            job["execution_timeout_seconds"] = timeout_seconds
            self._jobs[platform_job_id] = job
        started_at = self._timestamp()
        heartbeat_lease_token = heartbeat_lease_token or uuid.uuid4().hex
        self._update_source_job(
            app_job_id,
            status="running",
            metadata={
                "mcp_async_state": "running",
                "mcp_async_started_at": started_at,
                "mcp_async_heartbeat_at": started_at,
                "mcp_async_runtime_instance": _async_runtime_instance(),
                "mcp_async_lease_token": heartbeat_lease_token,
                "mcp_async_execution_timeout_seconds": timeout_seconds,
            },
        )
        heartbeat_stop, heartbeat_worker = self._start_heartbeat_worker(app_job_id)
        heartbeat_worker.start()

        try:
            async def _run_runner() -> Any:
                outcome = runner()
                if inspect.isawaitable(outcome):
                    return await outcome
                return outcome

            # The Jobs API records a cancellation durably, whereas a wait=false
            # MCP execution is an in-process asyncio task.  Without this small
            # cancellation bridge, cancelling the durable Job only changes the
            # row while a slow model/report task keeps running and can still
            # publish.  Poll the durable source row while the runner is alive
            # and cancel the exact task before it reaches any later publication
            # boundary.  This does not alter report content or delivery logic.
            runner_task = asyncio.create_task(_run_runner())

            async def _await_runner_with_cancellation() -> Any:
                try:
                    while not runner_task.done():
                        await asyncio.wait(
                            {runner_task}, timeout=self._CANCELLATION_POLL_SECONDS
                        )
                        if runner_task.done():
                            break
                        if self._source_job_is_cancelled(app_job_id):
                            runner_task.cancel()
                            try:
                                await runner_task
                            except asyncio.CancelledError:
                                pass
                            raise asyncio.CancelledError
                    return runner_task.result()
                except asyncio.CancelledError:
                    if not runner_task.done():
                        runner_task.cancel()
                        try:
                            await runner_task
                        except asyncio.CancelledError:
                            pass
                    raise

            try:
                result = await asyncio.wait_for(
                    _await_runner_with_cancellation(),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    "MCP_ASYNC_EXECUTION_TIMEOUT: execution exceeded "
                    f"{timeout_seconds:g} seconds"
                ) from exc
            if result_formatter is not None:
                result = result_formatter(result)
            result_failure = _async_result_failure(result)
            with self._lock:
                job = dict(self._jobs.get(platform_job_id) or {})
                job["status"] = "failed" if result_failure else "completed"
                job["result"] = result
                if result_failure:
                    job["error"] = result_failure
                else:
                    job.pop("error", None)
                self._jobs[platform_job_id] = job
            if result_failure:
                self._update_source_job(
                    app_job_id,
                    status="failed",
                    error_info={"message": result_failure},
                    metadata={
                        "mcp_async_state": "failed",
                        "mcp_async_finished_at": self._timestamp(),
                    },
                )
            else:
                # Persist the result on the durable Job too (mirrors the REST async runner) so a
                # wait=false acknowledgement is fully trackable - status AND response - via /api/jobs.
                try:
                    response_received = result if isinstance(result, str) else json.dumps(result, default=str)
                except (TypeError, ValueError):
                    response_received = None
                if response_received is not None:
                    self._update_source_job(
                        app_job_id,
                        status="completed",
                        response_received=response_received,
                        metadata={
                            "mcp_async_state": "completed",
                            "mcp_async_finished_at": self._timestamp(),
                        },
                    )
                else:
                    self._update_source_job(
                        app_job_id,
                        status="completed",
                        metadata={
                            "mcp_async_state": "completed",
                            "mcp_async_finished_at": self._timestamp(),
                        },
                    )
        except asyncio.CancelledError:
            # Graceful ASGI shutdown cancels in-process tasks just before a
            # container replacement.  Preserve the durable job for the next
            # runtime unless the Jobs API itself recorded a user cancellation.
            if not self._source_job_is_cancelled(app_job_id):
                self._update_source_job(
                    app_job_id,
                    status="running",
                    metadata={
                        "mcp_async_state": "recovery_pending",
                        "mcp_async_interrupted_at": self._timestamp(),
                    },
                )
                raise
            cancellation = "MCP async execution was cancelled before completion"
            with self._lock:
                job = dict(self._jobs.get(platform_job_id) or {})
                job["status"] = "failed"
                job["error"] = cancellation
                self._jobs[platform_job_id] = job
            self._update_source_job(
                app_job_id,
                status="failed",
                error_info={"message": cancellation, "reason": "async_worker_cancelled"},
                metadata={
                    "mcp_async_state": "cancelled",
                    "mcp_async_finished_at": self._timestamp(),
                },
            )
            raise
        except Exception as exc:
            with self._lock:
                job = dict(self._jobs.get(platform_job_id) or {})
                job["status"] = "failed"
                job["error"] = str(exc)
                self._jobs[platform_job_id] = job
            self._update_source_job(
                app_job_id,
                status="failed",
                error_info={"message": str(exc)},
                metadata={
                    "mcp_async_state": "failed",
                    "mcp_async_finished_at": self._timestamp(),
                },
            )
        finally:
            heartbeat_stop.set()
            await asyncio.to_thread(heartbeat_worker.join, 5)
            if heartbeat_worker.is_alive():
                logger.warning("MCP async heartbeat worker did not stop for job %s", app_job_id)
            with self._lock:
                self._tasks.pop(platform_job_id, None)

    def _heartbeat_source_job(
        self,
        app_job_id: int,
        stop: threading.Event,
    ) -> None:
        """Refresh the durable Job heartbeat independently of model progress."""
        while not stop.wait(self._heartbeat_interval_seconds):
            try:
                heartbeat_at = self._timestamp()
                self._update_source_job(
                    app_job_id,
                    metadata={"mcp_async_heartbeat_at": heartbeat_at},
                )
            except Exception as exc:  # pragma: no cover - defensive persistence boundary
                logger.warning("Unable to refresh MCP async heartbeat for job %s: %s", app_job_id, exc)

    @staticmethod
    def _request_user_id(request: Any) -> Optional[int]:
        if request is None:
            return None
        authorization = str(request.headers.get("authorization") or "")
        api_key = request.headers.get("x-api-key")
        bearer = (
            authorization.split(" ", 1)[1].strip()
            if authorization.lower().startswith("bearer ")
            else ""
        )
        if not api_key and not bearer:
            return None

        from src.servers.api.auth import _validate_api_key_user, _validate_bearer_user

        db_gen = get_db()
        db = next(db_gen)
        try:
            user = (
                _validate_api_key_user(str(api_key), db)
                if api_key
                else _validate_bearer_user(bearer, db)
            )
            return int(user.id) if user is not None else None
        finally:
            db_gen.close()

    @classmethod
    def _create_source_job(
        cls,
        platform_job_id: str,
        tool_name: str,
        request: Any,
        replay_arguments: Dict[str, Any],
        delivery_idempotency_key: str,
        heartbeat_lease_token: str,
        execution_timeout_seconds: float,
    ) -> int:
        user_id = cls._request_user_id(request)
        auth_method = (
            "bearer"
            if request and request.headers.get("authorization")
            else "api_key"
        )
        db_gen = get_db()
        db = next(db_gen)
        try:
            job = JobManager(db).create_job(
                job_type="mcp_execute_tool",
                user_id=user_id,
                prompt_sent=tool_name,
                metadata={
                    "mcp_platform_job_id": platform_job_id,
                    "mcp_tool_name": tool_name,
                    "request_source": "mcp_console",
                    "auth_method": auth_method,
                    "mcp_async_runtime_instance": _async_runtime_instance(),
                    "mcp_async_lease_token": heartbeat_lease_token,
                    "mcp_async_replay_arguments": replay_arguments,
                    "mcp_async_delivery_idempotency_key": delivery_idempotency_key,
                    "mcp_async_execution_timeout_seconds": execution_timeout_seconds,
                    "mcp_async_state": "accepted",
                    "mcp_async_accepted_at": cls._timestamp(),
                },
            )
            return int(job.id)
        finally:
            db_gen.close()

    @staticmethod
    def _update_source_job(app_job_id: int, **updates: Any) -> None:
        db_gen = get_db()
        db = next(db_gen)
        try:
            JobManager(db).update_job(app_job_id, **updates)
        finally:
            db_gen.close()

    @staticmethod
    def _source_job_is_cancelled(app_job_id: int) -> bool:
        """Return whether the durable Jobs API has cancelled this MCP task.

        The check is deliberately best-effort: a transient database read fault
        must not turn a healthy report run into a cancellation.  A confirmed
        cancellation is terminal and is acted on by ``_run_source_job``.
        """
        db_gen = get_db()
        db = next(db_gen)
        try:
            job = JobManager(db).get_job(app_job_id)
            return bool(job and str(job.status or "").strip().lower() in {"cancelled", "canceled"})
        except Exception as exc:  # pragma: no cover - defensive cancellation probe
            logger.warning("Unable to read cancellation state for MCP job %s: %s", app_job_id, exc)
            return False
        finally:
            db_gen.close()


class MCPToolAuthMiddleware:
    """EA1 (W28C-1704 / 1601-C): authentication gate for MCP tool dispatch.

    Before W28C-1704 the MCP server had NO auth middleware: an anonymous caller
    reached ``_run_tool_call`` and ``_resolve_auth_role`` defaulted the missing
    principal to role ``user`` (which holds expert:tool:read+execute), so every
    non-admin tool was reachable anonymously (the 340-session anon leak).

    This pure-ASGI middleware authenticates every MCP request
    (the JSON-RPC ``/mcp`` endpoint and the bespoke ``/mcp/<tool>``
    REST routes) via ``X-API-Key`` — a valid user key (DB) OR the configured
    expert-agent service/admin key — or a valid user JWT in ``Authorization:
    Bearer``. The bearer path is used by the cookie-authenticated Web BFF; the
    browser never receives or supplies a service/admin key. Anonymous callers
    receive ``401`` BEFORE any tool runs. Health stays open; MCP transport POSTs
    require authentication before discovery or tool dispatch.
    """

    _OPEN_PATHS = {"/health", "/mcp/health"}
    _ADMIN_TOOL_PREFIXES = ("admin_",)
    _EXECUTION_ROLES = {"admin", "user", "operator"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        path = (scope.get("path") or "/").rstrip("/") or "/"
        if path in self._OPEN_PATHS:
            return await self.app(scope, receive, send)

        is_jsonrpc = path in {"/mcp", "/messages", "/message"} or path.endswith("/mcp")
        is_bespoke_tool = path.startswith("/mcp/")
        is_legacy_transport = path == "/sse"
        if not (is_jsonrpc or is_bespoke_tool or is_legacy_transport):
            return await self.app(scope, receive, send)

        method = scope.get("method", "GET")
        principal = self._authenticate(scope)
        if principal is None:
            return await self._send_401(send)
        role, actor = principal
        if role not in self._EXECUTION_ROLES:
            return await self._send_json(
                send,
                403,
                {"detail": "Insufficient role"},
            )

        body = b""
        if method in ("POST", "PUT", "PATCH"):
            more = True
            while more:
                message = await receive()
                body += message.get("body", b"")
                more = message.get("more_body", False)

        if is_jsonrpc and body:
            body = self._bind_authenticated_context(body, role=role, actor=actor)
        compat_response = self._jsonrpc_compat_response(body, role=role) if is_jsonrpc else None
        if compat_response is not None:
            status, payload = compat_response
            return await self._send_json(send, status, payload)

        if method in ("POST", "PUT", "PATCH"):
            replayed = {"sent": False}

            async def _replay():
                if not replayed["sent"]:
                    replayed["sent"] = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.request", "body": b"", "more_body": False}

            return await self.app(scope, _replay, send)
        return await self.app(scope, receive, send)

    @classmethod
    def _jsonrpc_compat_response(
        cls,
        body: bytes,
        *,
        role: str,
    ) -> tuple[int, dict[str, Any]] | None:
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            return None
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            return None
        request_id = payload.get("id")
        method = payload.get("method")
        if method == "resources/list":
            return 200, {"jsonrpc": "2.0", "id": request_id, "result": {"resources": []}}
        if method == "tools/call":
            params = payload.get("params") or {}
            if not isinstance(params, dict):
                return None
            name = str(params.get("name") or "")
            if name.startswith(cls._ADMIN_TOOL_PREFIXES) and role != "admin":
                return 403, {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32003,
                        "message": "Forbidden: role is not authorised for admin MCP tool",
                    },
                }
        return None

    @staticmethod
    def _bind_authenticated_context(body: bytes, *, role: str, actor: str) -> bytes:
        """Replace caller-supplied auth context with the validated principal."""
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return body
        if not isinstance(payload, dict) or payload.get("method") != "tools/call":
            return body
        params = payload.get("params")
        if not isinstance(params, dict):
            return body
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
            params["arguments"] = arguments
        arguments["auth_context"] = {"role": role, "user_id": actor}
        return json.dumps(payload).encode("utf-8")

    @staticmethod
    def _authenticate(scope) -> tuple[str, str] | None:
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        api_key = headers.get("x-api-key")
        authorization = headers.get("authorization", "")
        bearer = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else ""
        if not api_key and not bearer:
            return None
        # Resolve database-backed principals first so configured keys that have
        # been bootstrapped retain their real numeric actor identity.
        try:
            from src.database.connection import get_db
            from src.servers.api.auth import _validate_api_key_user, _validate_bearer_user

            db_gen = get_db()
            db = next(db_gen)
            try:
                user = (
                    _validate_api_key_user(str(api_key), db)
                    if api_key
                    else _validate_bearer_user(bearer, db)
                )
            finally:
                db.close()
            if user and getattr(user, "enabled", False):
                role = str(getattr(user, "role", None) or "user").strip().lower()
                actor = str(getattr(user, "id", None) or getattr(user, "username", None) or "user")
                return (role, actor)
        except Exception as exc:  # pragma: no cover - auth resolution must fail closed
            logger.warning("MCP auth resolution error (failing closed): %s", exc)

        # A configured service key remains a valid machine principal if it has
        # not been persisted in the user database. Existing admin handlers
        # require an integer actor identifier, so use the reserved system id.
        if api_key:
            for cfg_key in ("api_key", "api_server.api_key", "mcp_server.api_key", "client_api.admin_api_key"):
                try:
                    configured = get_config(cfg_key)
                except Exception:
                    configured = None
                if configured and str(configured) == api_key:
                    return ("admin", "0")
        return None

    @staticmethod
    async def _send_json(send, status: int, payload_obj: dict[str, Any]) -> None:
        payload = json.dumps(payload_obj).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})

    @staticmethod
    async def _send_401(send) -> None:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32001,
                    "message": "Unauthorized: authentication required for MCP tool calls",
                },
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})


# --- PS-50 MCP compliance: per-tool RBAC permission map ---
_TOOL_PERMISSION_MAP: Dict[str, str] = {
    # Read/query tools — all authenticated roles
    "chat": "expert:tool:execute",
    "start_session": "expert:tool:execute",
    "resume_session": "expert:tool:execute",
    "end_session": "expert:tool:execute",
    "list_sessions": "expert:tool:read",
    "session_status": "expert:tool:read",
    "get_history": "expert:tool:read",
    "list_experts": "expert:tool:read",
    "get_expert": "expert:tool:read",
    "vector_search": "expert:tool:read",
    "vector_add": "expert:tool:execute",
    "get_session_by_key": "expert:tool:read",
    "get_history_by_key": "expert:tool:read",
    "share_session": "expert:tool:execute",
    "unshare_session": "expert:tool:execute",
    "summarize_session": "expert:tool:execute",
    "get_summaries": "expert:tool:read",
    "execute_tool": "expert:tool:execute",
    "list_services": "expert:tool:read",
    "invoke_service_tool": "expert:tool:execute",
    "run_research_cycle": "expert:tool:execute",
    "code_execute": "expert:tool:execute",
    # Admin tools — admin role only
    "admin_list_experts": "expert:admin:*",
    "admin_create_expert": "expert:admin:*",
    "admin_update_expert": "expert:admin:*",
    "admin_delete_expert": "expert:admin:*",
    "admin_list_users": "expert:admin:*",
    "admin_create_api_key": "expert:admin:*",
    "admin_revoke_api_key": "expert:admin:*",
}


class MCPServer(BaseServer):
    """Model Context Protocol server."""

    def __init__(self):
        super().__init__("MCP Server", "mcp_server")
        self.transport = get_config("mcp_server.transport")  # sse or stdio
        if not self.transport:
            raise RuntimeError("mcp_server.transport not configured")
        self.protocol_version = str(get_config("mcp_server.protocol_version") or "2024-11-05")
        self.app = self._create_platform_app()
        # EA1 (W28C-1704 / 1601-C): gate anonymous MCP tool dispatch before any
        # tool runs. Must wrap the app before the transport routes are registered.
        self.app.add_middleware(MCPToolAuthMiddleware)
        self._remove_platform_health_routes()
        self._configure_platform_timeout()
        self.session_manager = SessionManager()
        self.llm_manager = LLMManager()
        self.tools = MCPTools()
        self._server_task: Optional[asyncio.Task] = None
        self._stopping = False
        self._async_job_store = SourceBackedAsyncJobStore(self._build_async_runner)
        # Keep stdio JSON-RPC state local to the stdio transport helper.
        self._rpc_sessions: Dict[str, Dict[str, Any]] = {}
        self._async_jobs: Dict[str, Dict[str, Any]] = {}
        # Strong references to in-flight async-job tasks. asyncio only keeps WEAK
        # references to tasks created with create_task; without holding a strong
        # reference here a long-running job (e.g. a multi-section document that
        # takes many minutes) can be garbage-collected mid-execution and silently
        # never complete/deliver. Hold until done, then discard.
        self._async_job_tasks: set = set()
        self._register_routes()
        self._register_platform_transport()
        self._register_mcp_contract()

    def _create_platform_app(self):
        """Create MCP app via cloud_dog_api_kit across package versions."""
        kwargs = {
            "title": "Expert Agent MCP Server",
            "version": "0.1.0",
            "description": "Model Context Protocol server for Expert Agent",
            "cors_origins": ["*"],
        }
        try:
            return create_app(**kwargs, register_signal_handlers_on_startup=False)
        except TypeError as exc:
            if "register_signal_handlers_on_startup" not in str(exc):
                raise
            return create_app(**kwargs)

    def _remove_platform_health_routes(self) -> None:
        """Keep existing /health and /mcp/health contracts stable."""
        health_paths = {"/health", "/ready", "/live", "/status"}
        self.app.router.routes = [
            route
            for route in self.app.router.routes
            if getattr(route, "path", None) not in health_paths
        ]

    def _configure_platform_timeout(self) -> None:
        """Align API kit timeout middleware with project timeout settings."""
        raw_timeout = get_config("expert.test.http_timeout_seconds")
        if raw_timeout is None:
            raw_timeout = get_config("test.http_timeout_seconds")
        try:
            timeout_seconds = float(raw_timeout)
        except (TypeError, ValueError):
            timeout_seconds = 300.0
        if timeout_seconds <= 0:
            timeout_seconds = 300.0

        for middleware in self.app.user_middleware:
            if middleware.cls is TimeoutMiddleware:
                middleware.kwargs["timeout_seconds"] = timeout_seconds
                return

    def _tool_catalog(self) -> List[Dict[str, Any]]:
        return [
            {"name": "chat", "description": "Chat tool for conversation initiation"},
            {"name": "start_session", "description": "Start a new session"},
            {"name": "resume_session", "description": "Resume an existing session"},
            {"name": "end_session", "description": "End a session"},
            {"name": "list_sessions", "description": "List sessions"},
            {"name": "session_status", "description": "Get session status"},
            {"name": "get_history", "description": "Get session history"},
            {"name": "list_experts", "description": "List expert configurations"},
            {"name": "get_expert", "description": "Get expert configuration"},
            {"name": "admin_list_experts", "description": "Admin list expert configurations"},
            {"name": "admin_create_expert", "description": "Admin create expert configuration"},
            {"name": "admin_update_expert", "description": "Admin update expert configuration"},
            {"name": "admin_delete_expert", "description": "Admin delete expert configuration"},
            {"name": "admin_list_users", "description": "Admin list users"},
            {"name": "admin_create_api_key", "description": "Admin create API key"},
            {"name": "admin_revoke_api_key", "description": "Admin revoke API key"},
            {"name": "vector_search", "description": "Search vector store"},
            {"name": "vector_add", "description": "Add documents to vector store"},
            {"name": "get_session_by_key", "description": "Get session by session key (AT1.11)"},
            {"name": "get_history_by_key", "description": "Get history by history key (AT1.11)"},
            {"name": "share_session", "description": "Share session with users/groups (AT1.11)"},
            {
                "name": "unshare_session",
                "description": "Unshare session with users/groups (AT1.11)",
            },
            {"name": "summarize_session", "description": "Trigger session summarization (AT1.11)"},
            {"name": "get_summaries", "description": "Get all summaries for a session (AT1.11)"},
            {"name": "execute_tool",
             "description": "Transactional expert execution. Optional DATA parameter "
                            "parameters.agent_strategy (PS-96 §3): simple (default) | react | rlm | "
                            "reflexion. Non-simple strategies run the cloud_dog_agent loop, driven by "
                            "the expert's prompt and its bound tools / sub-experts."},
            {"name": "list_services", "description": "List bound services for an expert"},
            {
                "name": "invoke_service_tool",
                "description": "Invoke a tool on a bound external service",
            },
            {
                "name": "run_research_cycle",
                "description": (
                    "Consume search-mcp research_stream SSE, relay progress events, "
                    "and enrich image URL/file-mcp refs with caption/chart extraction."
                ),
            },
            {
                "name": "code_execute",
                "description": "Run code on the code-runner service over A2A (analyst reasoning tool)",
            },
        ]

    def _register_mcp_contract(self) -> None:
        """Register tools via cloud_dog_api_kit.mcp for PS-50 compliance."""
        try:
            from cloud_dog_api_kit.mcp.contract import register_mcp_contract
            tool_registry = {
                tool["name"]: {"description": tool["description"], "handler": lambda **kw: kw}
                for tool in self._tool_catalog()
            }
            transport = str(self.transport).strip().lower()
            contract_modes = ["stdio"] if transport == "stdio" else self._transport_modes()
            register_mcp_contract(self.app, tool_registry, transport_modes=contract_modes)
            logger.info(f"MCP contract registered via cloud_dog_api_kit ({len(tool_registry)} tools)")
        except Exception as exc:
            logger.warning("cloud_dog_api_kit MCP contract registration skipped: %s", exc)

    def _transport_modes(self) -> List[str]:
        """Return the service's supported MCP transport modes."""
        return ["streamable_http", "http_jsonrpc", "legacy_sse"]

    def _build_tool_registry(self) -> Dict[str, Dict[str, Any]]:
        """Expose the MCP tool dispatch through the shared transport helper."""

        def _make_handler(tool_name: str):
            async def _handler(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
                if not isinstance(payload, dict):
                    payload = {}
                return await self._run_tool_call(tool_name, payload)

            return _handler

        registry: Dict[str, Dict[str, Any]] = {}
        for tool in self._tool_catalog():
            registry[tool["name"]] = {
                "description": tool["description"],
                "handler": _make_handler(tool["name"]),
                "input_schema": {"type": "object", "properties": {}},
            }
        return registry

    def _register_platform_transport(self) -> None:
        """Adopt the shared API-kit MCP transport routes for HTTP/SSE modes."""
        self._patch_platform_tool_payload_contract()
        register_mcp_routes(
            self.app,
            self._build_tool_registry(),
            transport_modes=self._transport_modes(),
            async_job_store=self._async_job_store,
            async_job_status_path="/mcp/jobs/{job_id}",
            legacy_sse=LegacySSEConfig(
                sse_path="/sse",
                message_path="/message",
                session_header="Mcp-Session-Id",
            ),
            session_termination_mode="200_json",
            error_response_mode="jsonrpc_200",
            capabilities_override={"tools": {}},
        )

    @staticmethod
    def _patch_platform_tool_payload_contract() -> None:
        """Backfill structuredContent on older API-kit MCP transport builds."""
        formatter = getattr(mcp_transport, "_mcp_tool_call_payload", None)
        if formatter is None or getattr(formatter, "_expert_agent_patched", False):
            return

        def _patched_tool_payload(result: Any) -> Dict[str, Any]:
            payload = formatter(result)
            if not isinstance(payload, dict) or "structuredContent" in payload:
                return payload

            data: Any = result
            if isinstance(result, dict):
                if result.get("data") is not None:
                    data = result.get("data")
                elif result.get("result") is not None:
                    data = result.get("result")
                elif result.get("error") is not None:
                    data = result.get("error")

            if isinstance(data, (dict, list)):
                payload = dict(payload)
                payload["structuredContent"] = data
            return payload

        setattr(_patched_tool_payload, "_expert_agent_patched", True)
        mcp_transport._mcp_tool_call_payload = _patched_tool_payload

    @staticmethod
    def _jsonrpc_error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": int(code), "message": str(message)},
        }

    @staticmethod
    def _jsonrpc_result(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _resolve_auth_role(self, arguments: Dict[str, Any]) -> tuple[str, str]:
        """Resolve MCP auth context to a principal and effective role."""
        auth_context = (arguments or {}).get("auth_context") or {}
        requested_role = str(auth_context.get("role") or "user").strip().lower() or "user"
        api_key = auth_context.get("x_api_key") or auth_context.get("api_key")
        if api_key:
            try:
                from src.database.connection import get_db
                from src.servers.api.auth import _validate_api_key_user

                db_gen = get_db()
                db = next(db_gen)
                try:
                    user = _validate_api_key_user(str(api_key), db)
                finally:
                    db.close()
                if user and getattr(user, "enabled", False):
                    principal = str(getattr(user, "id", None) or getattr(user, "username", "") or api_key)
                    role = str(getattr(user, "role", None) or requested_role).strip().lower() or "user"
                    return principal, role
            except Exception as exc:
                logger.warning("Failed to resolve MCP auth role from API key: %s", exc)

        principal = str(
            auth_context.get("user_id")
            or auth_context.get("x_api_key")
            or auth_context.get("api_key")
            or f"role:{requested_role}"
        )
        return principal, requested_role

    def _enforce_tool_rbac(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """PS-50: Per-tool RBAC enforcement via cloud_dog_idam.rbac.RBACEngine."""
        required_permission = _TOOL_PERMISSION_MAP.get(tool_name)
        if not required_permission:
            return None  # Unknown tool — will be caught later
        from cloud_dog_idam.rbac import RBACEngine
        engine = RBACEngine(role_permissions={
            "admin": {"expert:admin:*", "expert:tool:read", "expert:tool:execute"},
            "owner": {"expert:tool:read", "expert:tool:execute", "expert:config:write"},
            "user": {"expert:tool:read", "expert:tool:execute"},
            "viewer": {"expert:tool:read"},
        })
        principal, role = self._resolve_auth_role(arguments)
        engine.assign_role_to_user(principal, role)
        if not engine.has_permission(principal, required_permission):
            logger.warning("RBAC denied: tool=%s permission=%s role=%s", tool_name, required_permission, role)
            return {"error": f"Permission denied: {required_permission}", "code": -32603}
        return None

    def _audit_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any], duration_ms: float) -> None:
        """PS-50: Audit log every MCP tool call."""
        try:
            from cloud_dog_logging import get_audit_logger
            audit = get_audit_logger("mcp_tool_audit")
            auth_context = (arguments or {}).get("auth_context") or {}
            audit.info(
                "mcp_tool_call",
                extra={
                    "service": "expert-agent",
                    "tool_name": tool_name,
                    "actor": str(auth_context.get("user_id") or auth_context.get("x_api_key") or "anonymous"),
                    "outcome": "error" if "error" in result else "success",
                    "duration_ms": round(duration_ms, 1),
                },
            )
        except Exception:
            pass  # Audit failure must not break tool execution

    async def _run_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch with RBAC + audit wrapping (PS-50)."""
        # PS-50: Per-tool RBAC enforcement
        rbac_denial = self._enforce_tool_rbac(tool_name, arguments)
        if rbac_denial is not None:
            self._audit_tool_call(tool_name, arguments, rbac_denial, 0)
            return rbac_denial
        _t0 = time.monotonic()
        result = await self._dispatch_tool(tool_name, arguments)
        self._audit_tool_call(tool_name, arguments, result, (time.monotonic() - _t0) * 1000)
        return result

    def _build_async_runner(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> tuple[Any, Any]:
        """Recreate the normal MCP runner from durable JSON-safe arguments."""
        def _runner(_name=tool_name, _arguments=arguments):
            return self._run_tool_call(_name, _arguments)

        def _formatter(result: Any) -> Any:
            if isinstance(result, dict) and result.get("isError") is True:
                return result
            compact = _compact_wait_false_result(tool_name, result)
            return {
                "content": [{"type": "text", "text": json.dumps(compact, default=str)}],
                "structuredContent": compact,
            }

        return _runner, _formatter

    async def _dispatch_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        args = arguments or {}
        if tool_name == "chat":
            return await self.tools.chat_tool(
                session_id=args.get("session_id"),
                message=args.get("message"),
                temperature=args.get("temperature"),
                top_k=args.get("top_k"),
                top_p=args.get("top_p"),
                max_tokens=args.get("max_tokens"),
                response_format=args.get("response_format"),
                language=args.get("language"),
                system_prompt=args.get("system_prompt"),
            )
        if tool_name == "start_session":
            return self.tools.start_session_tool(
                user_id=args.get("user_id"),
                expert_config_id=args.get("expert_config_id"),
                title=args.get("title"),
                channel_id=args.get("channel_id"),
            )
        if tool_name == "resume_session":
            return self.tools.resume_session_tool(args.get("session_id"))
        if tool_name == "end_session":
            return self.tools.end_session_tool(args.get("session_id"))
        if tool_name == "list_sessions":
            return self.tools.list_sessions_tool(
                user_id=args.get("user_id"), status=args.get("status")
            )
        if tool_name == "session_status":
            return self.tools.session_status_tool(args.get("session_id"))
        if tool_name == "get_history":
            return self.tools.get_history_tool(args.get("session_id"), limit=args.get("limit"))
        if tool_name == "list_experts":
            return self.tools.list_experts_tool()
        if tool_name == "get_expert":
            return self.tools.get_expert_tool(args.get("expert_id"))
        if tool_name == "admin_list_experts":
            return self.tools.admin_list_experts_tool(
                auth_context=args.get("auth_context"),
                enabled_only=bool(args.get("enabled_only", False)),
                skip=int(args.get("skip", 0) or 0),
                limit=int(args.get("limit", 100) or 100),
            )
        if tool_name == "admin_create_expert":
            return self.tools.admin_create_expert_tool(
                name=args.get("name"),
                title=args.get("title"),
                description=args.get("description"),
                auth_context=args.get("auth_context"),
                llm_provider=args.get("llm_provider"),
                llm_model=args.get("llm_model"),
                llm_base_url=args.get("llm_base_url"),
                llm_params=args.get("llm_params"),
                prompt_template=args.get("prompt_template"),
                tools=args.get("tools"),
                enabled=bool(args.get("enabled", True)),
                access_control=args.get("access_control"),
            )
        if tool_name == "admin_update_expert":
            update_args = dict(args)
            update_args.pop("auth_context", None)
            update_args.pop("expert_id", None)
            return self.tools.admin_update_expert_tool(
                args.get("expert_id"),
                auth_context=args.get("auth_context"),
                **update_args,
            )
        if tool_name == "admin_delete_expert":
            return self.tools.admin_delete_expert_tool(
                args.get("expert_id"), auth_context=args.get("auth_context")
            )
        if tool_name == "admin_list_users":
            return self.tools.admin_list_users_tool(
                auth_context=args.get("auth_context"),
                enabled_only=bool(args.get("enabled_only", False)),
                role=args.get("role"),
            )
        if tool_name == "admin_create_api_key":
            return self.tools.admin_create_api_key_tool(
                auth_context=args.get("auth_context"),
                user_id=args.get("user_id"),
                name=args.get("name"),
                expires_days=args.get("expires_days"),
                read_logs=bool(args.get("read_logs", True)),
                read_histories=bool(args.get("read_histories", True)),
                read_channels=bool(args.get("read_channels", True)),
            )
        if tool_name == "admin_revoke_api_key":
            return self.tools.admin_revoke_api_key_tool(
                args.get("key_id"), auth_context=args.get("auth_context")
            )
        if tool_name == "vector_search":
            return await self.tools.search_vector_tool(
                query=args.get("query"),
                collection=args.get("collection"),
                n_results=args.get("n_results", 5),
                vector_store_name=args.get("vector_store_name") or args.get("store_name") or args.get("store_id") or "_DEFAULT_",
            )
        if tool_name == "vector_add":
            return await self.tools.add_to_vector_tool(
                documents=args.get("documents"),
                collection=args.get("collection"),
                vector_store_name=args.get("vector_store_name") or args.get("store_name") or args.get("store_id") or "_DEFAULT_",
                metadatas=args.get("metadatas"),
            )
        if tool_name == "get_session_by_key":
            return self.tools.get_session_by_key_tool(args.get("session_key"))
        if tool_name == "get_history_by_key":
            return self.tools.get_history_by_key_tool(args.get("history_key"))
        if tool_name == "share_session":
            return self.tools.share_session_tool(
                session_id=args.get("session_id"),
                user_ids=args.get("user_ids"),
                group_ids=args.get("group_ids"),
            )
        if tool_name == "unshare_session":
            return self.tools.unshare_session_tool(
                session_id=args.get("session_id"),
                user_ids=args.get("user_ids"),
                group_ids=args.get("group_ids"),
            )
        if tool_name == "summarize_session":
            return await self.tools.summarize_session_tool(
                session_id=args.get("session_id"),
                preserve_recent=args.get("preserve_recent", 5),
                max_tokens=args.get("max_tokens"),
            )
        if tool_name == "get_summaries":
            return self.tools.get_summaries_tool(args.get("session_id"))
        if tool_name == "execute_tool":
            return await self.tools.execute_tool(
                expert_id=args.get("expert_id"),
                input_text=args.get("input_text"),
                parameters=args.get("parameters"),
                context=args.get("context"),
                auth_context=args.get("auth_context"),
            )
        if tool_name == "list_services":
            return await self.tools.list_services_tool(args.get("expert_id"))
        if tool_name == "invoke_service_tool":
            return await self.tools.invoke_service_tool(
                service_id=args.get("service_id"),
                tool_name=args.get("tool_name"),
                arguments=args.get("arguments"),
                auth_context=args.get("auth_context"),
                session_id=args.get("session_id"),
                timeout_seconds=args.get("timeout_seconds"),
            )
        if tool_name == "run_research_cycle":
            return await self.tools.run_research_cycle_tool(
                query=args.get("query"),
                depth=args.get("depth"),
                tenant_id=args.get("tenant_id"),
                correlation_id=args.get("correlation_id"),
                budget=args.get("budget"),
                image_refs=args.get("image_refs") or args.get("images") or [],
                auth_context=args.get("auth_context"),
            )
        if tool_name == "code_execute":
            return await self.tools.code_execute_tool(
                code=args.get("code"),
                language=args.get("language"),
                task_id=args.get("task_id"),
                auth_context=args.get("auth_context"),
            )

        return {"error": f"Unknown tool: {tool_name}"}

    async def _execute_jsonrpc(
        self, payload: Dict[str, Any], session_id: Optional[str]
    ) -> Dict[str, Any]:
        request_id = payload.get("id")
        if payload.get("jsonrpc") != "2.0":
            return self._jsonrpc_error(request_id, -32600, "Invalid Request: jsonrpc must be '2.0'")
        method = payload.get("method")
        params = payload.get("params") or {}
        if not method:
            return self._jsonrpc_error(request_id, -32600, "Invalid Request: method is required")

        # Notification path
        if method == "notifications/initialized":
            if session_id and session_id in self._rpc_sessions:
                self._rpc_sessions[session_id]["initialized"] = True
            return {}

        if method == "initialize":
            negotiated = str(params.get("protocolVersion") or self.protocol_version)
            return self._jsonrpc_result(
                request_id,
                {
                    "protocolVersion": negotiated,
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "expert-agent-mcp-server", "version": "0.1.0"},
                },
            )

        if session_id and session_id not in self._rpc_sessions:
            return self._jsonrpc_error(request_id, -32001, "Invalid or expired MCP session")

        if method == "tools/list":
            tools = []
            for item in self._tool_catalog():
                tools.append(
                    {
                        "name": item["name"],
                        "description": item["description"],
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                )
            return self._jsonrpc_result(request_id, {"tools": tools})

        if method == "resources/list":
            return self._jsonrpc_result(request_id, {"resources": []})

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not name:
                return self._jsonrpc_error(request_id, -32602, "Missing required param: name")

            # Async job mode: wait=false returns a reference resolved via /mcp/jobs/{job_id}.
            # Route through the durable Source-backed async job store (the intended, wired path)
            # so the acknowledgement is a REAL database Job created exactly like the proven REST
            # async runner (_process_expert_execute_job) - visible on the Jobs surface and reliably
            # tracked - rather than an in-process-only UUID. The prior inline branch bypassed that
            # store: it recorded status only in `self._async_jobs`, creating no durable job, so
            # callers saw "Session not found" and long document runs went untracked. That is why
            # the configured scheduler `execute_tool` (wait=false) target produced phantom,
            # non-delivering jobs while the REST async path did not (W28M-1635 R2 / raw ledger R50).
            if arguments.get("wait") is False:
                guid = uuid.uuid4().hex[:8]
                _runner, _formatter = self._build_async_runner(name, arguments)

                platform_job_id = self._async_job_store.submit(
                    name, arguments, {"runner": _runner, "result_formatter": _formatter}
                )
                return self._jsonrpc_result(
                    request_id, {"job_id": platform_job_id, "guid": guid}
                )

            tool_result = await self._run_tool_call(name, arguments)
            if isinstance(tool_result, dict) and tool_result.get("error"):
                return self._jsonrpc_error(request_id, -32602, str(tool_result.get("error")))

            return self._jsonrpc_result(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(tool_result)}],
                    "structuredContent": tool_result,
                },
            )

        return self._jsonrpc_error(request_id, -32601, f"Method not found: {method}")

    def _register_routes(self):
        """Register MCP routes."""

        @self.app.post("/mcp/chat")
        async def mcp_chat(request: Request):
            """MCP chat tool endpoint."""
            data = await request.json()
            session_id = data.get("session_id")
            message = data.get("message")

            if not session_id or not message:
                return {"error": "session_id and message required"}

            # Extract LLM parameters
            temperature = data.get("temperature")
            top_k = data.get("top_k")
            top_p = data.get("top_p")
            max_tokens = data.get("max_tokens")
            response_format = data.get("response_format")
            language = data.get("language")
            system_prompt = data.get("system_prompt")

            return await self.tools.chat_tool(
                session_id=session_id,
                message=message,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                max_tokens=max_tokens,
                response_format=response_format,
                language=language,
                system_prompt=system_prompt,
            )

        @self.app.post("/mcp/start_session")
        async def mcp_start_session(request: Request):
            """MCP start session tool."""
            data = await request.json()
            return self.tools.start_session_tool(
                user_id=data.get("user_id"),
                expert_config_id=data.get("expert_config_id"),
                title=data.get("title"),
                channel_id=data.get("channel_id"),
            )

        @self.app.post("/mcp/resume_session")
        async def mcp_resume_session(request: Request):
            """MCP resume session tool."""
            data = await request.json()
            return self.tools.resume_session_tool(data.get("session_id"))

        @self.app.post("/mcp/end_session")
        async def mcp_end_session(request: Request):
            """MCP end session tool."""
            data = await request.json()
            return self.tools.end_session_tool(data.get("session_id"))

        @self.app.get("/mcp/sessions")
        async def mcp_list_sessions(user_id: int = None, status: str = None):
            """MCP list sessions tool."""
            return self.tools.list_sessions_tool(user_id=user_id, status=status)

        @self.app.get("/mcp/session/{session_id}/status")
        async def mcp_session_status(session_id: int):
            """MCP session status tool."""
            return self.tools.session_status_tool(session_id)

        @self.app.get("/mcp/session/{session_id}/history")
        async def mcp_get_history(session_id: int, limit: int = None):
            """MCP get history tool."""
            return self.tools.get_history_tool(session_id, limit=limit)

        @self.app.get("/mcp/experts")
        async def mcp_list_experts():
            """MCP list experts tool."""
            return self.tools.list_experts_tool()

        @self.app.get("/mcp/expert/{expert_id}")
        async def mcp_get_expert(expert_id: int):
            """MCP get expert tool."""
            return self.tools.get_expert_tool(expert_id)

        @self.app.post("/mcp/vector/search")
        async def mcp_vector_search(request: Request):
            """MCP vector search tool."""
            data = await request.json()
            return await self.tools.search_vector_tool(
                query=data.get("query"),
                collection=data.get("collection"),
                n_results=data.get("n_results", 5),
                vector_store_name=data.get("vector_store_name") or data.get("store_name") or data.get("store_id") or "_DEFAULT_",
            )

        @self.app.post("/mcp/vector/add")
        async def mcp_vector_add(request: Request):
            """MCP vector add tool."""
            data = await request.json()
            return await self.tools.add_to_vector_tool(
                documents=data.get("documents"),
                collection=data.get("collection"),
                vector_store_name=data.get("vector_store_name") or data.get("store_name") or data.get("store_id") or "_DEFAULT_",
                metadatas=data.get("metadatas"),
            )

        @self.app.get("/mcp/research/stream")
        async def mcp_research_stream(request: Request):
            """Relay search-mcp research_stream SSE to MCP/chat clients."""
            from src.core.agentic.research_cycle import ResearchCycleManager, sse_frame

            query = request.query_params.get("query")
            depth = request.query_params.get("depth")
            tenant_id = request.query_params.get("tenant_id") or "default"
            correlation_id = request.query_params.get("correlation_id") or str(uuid.uuid4())
            max_results_raw = request.query_params.get("max_results")
            max_results = None
            if max_results_raw:
                try:
                    max_results = int(max_results_raw)
                except ValueError:
                    max_results = None
            last_raw = (
                request.headers.get("Last-Event-ID")
                or request.query_params.get("last_event_id")
                or request.query_params.get("after_id")
            )
            last_event_id = None
            if last_raw:
                try:
                    last_event_id = int(last_raw)
                except ValueError:
                    last_event_id = None

            def _values(name: str) -> List[str]:
                values = request.query_params.getlist(name)
                if not values:
                    return []
                expanded: List[str] = []
                for value in values:
                    expanded.extend(
                        [part.strip() for part in str(value).split(",") if part.strip()]
                    )
                return expanded

            async def _event_stream():
                with self.tools._db_scope() as db:
                    manager = ResearchCycleManager(db)
                    try:
                        async for event in manager.stream_research(
                            query or "",
                            depth=depth,
                            tenant_id=tenant_id,
                            correlation_id=correlation_id,
                            max_results=max_results,
                            query_languages=_values("query_languages") or _values("languages"),
                            target_languages=_values("target_languages"),
                            synthesise_in=(
                                request.query_params.get("synthesise_in")
                                or request.query_params.get("synthesize_in")
                            ),
                            auth_context={
                                "correlation_id": correlation_id,
                                "x_api_key": request.headers.get("x-api-key"),
                            },
                            last_event_id=last_event_id,
                        ):
                            yield sse_frame(event).encode("utf-8")
                    except Exception as exc:
                        error_event = {
                            "id": last_event_id or 0,
                            "type": "error",
                            "correlation_id": correlation_id,
                            "tenant_id": tenant_id,
                            "error": str(exc),
                        }
                        yield sse_frame(error_event).encode("utf-8")

            return StreamingResponse(
                _event_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Correlation-ID": correlation_id},
            )

        @self.app.get("/mcp/health")
        async def mcp_health():
            """MCP health check."""
            return {
                "status": "healthy",
                "service": "mcp",
                "application": "expert-agent-mcp-server",
                "version": "0.1.0",
                "transport": self.transport,
                "protocol_version": self.protocol_version,
                "env": {
                    "config_env_file": get_config("expert.env_file"),
                    "secrets_env_files": get_config("expert.env_secrets_files"),
                    "testing": get_config("test.enabled"),
                },
            }

        @self.app.get("/health")
        async def health():
            """Compatibility health check (server root)."""
            return await mcp_health()

        # AT1.11: Session key and history key endpoints

        @self.app.get("/mcp/session/key/{session_key}")
        async def mcp_get_session_by_key(session_key: str):
            """MCP get session by key tool."""
            return self.tools.get_session_by_key_tool(session_key)

        @self.app.get("/mcp/history/key/{history_key}")
        async def mcp_get_history_by_key(history_key: str):
            """MCP get history by key tool."""
            return self.tools.get_history_by_key_tool(history_key)

        @self.app.post("/mcp/session/{session_id}/share")
        async def mcp_share_session(session_id: int, request: Request):
            """MCP share session tool."""
            data = await request.json()
            return self.tools.share_session_tool(
                session_id=session_id,
                user_ids=data.get("user_ids"),
                group_ids=data.get("group_ids"),
            )

        @self.app.post("/mcp/session/{session_id}/unshare")
        async def mcp_unshare_session(session_id: int, request: Request):
            """MCP unshare session tool."""
            data = await request.json()
            return self.tools.unshare_session_tool(
                session_id=session_id,
                user_ids=data.get("user_ids"),
                group_ids=data.get("group_ids"),
            )

        @self.app.post("/mcp/session/{session_id}/summarize")
        async def mcp_summarize_session(session_id: int, request: Request):
            """MCP summarize session tool."""
            data = await request.json()
            return await self.tools.summarize_session_tool(
                session_id=session_id,
                preserve_recent=data.get("preserve_recent", 5),
                max_tokens=data.get("max_tokens"),
            )

        @self.app.get("/mcp/session/{session_id}/summaries")
        async def mcp_get_summaries(session_id: int):
            """MCP get summaries tool."""
            return self.tools.get_summaries_tool(session_id)

        @self.app.get("/mcp/tools")
        async def mcp_list_tools():
            """List available MCP tools."""
            return {"tools": self._tool_catalog()}

    async def _run_stdio_loop(self) -> None:
        """
        Minimal stdio JSON-RPC loop for MCP clients.
        Reads one JSON-RPC payload per line from stdin and writes one JSON response line to stdout.
        """
        session_id = "stdio-session"
        self._rpc_sessions.setdefault(session_id, {"initialized": False})
        while not self._shutdown_event.is_set():
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                await asyncio.sleep(0.05)
                continue
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                response = self._jsonrpc_error(None, -32700, "Parse error")
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue

            response = await self._execute_jsonrpc(payload, session_id)
            if response:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

    async def start(self):
        """Start the MCP server."""
        import uvicorn

        logger.info(
            f"Starting MCP server with {self.transport} transport on {self.host}:{self.port}"
        )
        self._stopping = False
        if str(self.transport).lower() == "stdio":
            self._stdio_task = asyncio.create_task(self._run_stdio_loop())
            return
        config = uvicorn.Config(app=self.app, host=self.host, port=int(self.port), log_level="info")
        self._server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self._server.serve())
        self._server_task.add_done_callback(self._on_server_task_done)
        await asyncio.sleep(0.5)
        if self._server_task.done():
            exc = self._server_task.exception()
            raise RuntimeError(f"MCP server failed during startup: {exc}")

    def _on_server_task_done(self, task: asyncio.Task) -> None:
        """Detect unexpected uvicorn task termination."""
        if self._stopping:
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            exc = None
        if exc:
            logger.error(f"MCP server task exited unexpectedly: {exc}", exc_info=True)
        else:
            logger.error("MCP server task exited unexpectedly without error")
        self._shutdown_event.set()

    async def stop(self):
        """Stop the MCP server."""
        self._stopping = True
        if hasattr(self, "_stdio_task") and self._stdio_task:
            self._stdio_task.cancel()
        if hasattr(self, "_server") and self._server:
            self._server.should_exit = True
        if self._server_task and not self._server_task.done():
            try:
                await asyncio.wait_for(self._server_task, timeout=15)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for MCP server task shutdown; cancelling task")
                self._server_task.cancel()
        logger.info("Stopping MCP server")

    async def health_check(self) -> bool:
        """Check if server is healthy."""
        return self.is_running()
