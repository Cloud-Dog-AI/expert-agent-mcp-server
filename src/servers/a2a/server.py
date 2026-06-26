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
A2A Server Implementation

License: Apache 2.0
Ownership: Cloud Dog
Description: Agent-to-Agent WebSocket server for real-time events

Related Requirements: FR1.7, CFG-06
Related Tasks: T044
Related Architecture: CC1.1.4
Related Tests: ST1.3, IT2.5, IT2.42

Recent Changes:
- Initial implementation
- W28A-1002-CONV-EXPERT-AGENT (v0.12.0 adoption):
  Adopt cloud_dog_api_kit.a2a.events.EventBroadcaster Protocol via a
  service-backed broadcaster wrapping the existing ConnectionManager
  cross-process HTTP-bridge architecture. The bespoke WebSocket topic
  fan-out + ``/a2a/broadcast/{topic}`` + ``/a2a/topics`` + ``/a2a/ws/{topic}``
  surfaces are PRESERVED byte-for-byte — the WS frame shape
  (``{"topic": <topic>, "data": <body>}`` / ``{"topic": <topic>,
  "echo": <body>}`` / ``{"topic": <topic>, "type": "command_response",
  "result": ...}``) carries schema-foreign fields (``topic`` envelope
  wrapping + arbitrary non-config-change payloads on non-config-change
  topics) that cannot be expressed via ``RESTPollAdapter.field_mapping``
  1:1 rename-only. The canonical PS-72 §A2A-change-events SSE surface
  is mounted ADDITIVELY at ``/a2a/events/sse`` via
  ``create_a2a_events_router`` so platform-conforming consumers can
  subscribe without disturbing legacy WebSocket clients. When
  ``/a2a/broadcast/{topic}`` receives a payload for one of the four
  config-change resource topics (``experts``/``users``/``groups``/
  ``api_keys``), the broadcaster ALSO synthesises a canonical
  ConfigChangeEvent alongside the legacy WS fan-out; non-config-change
  topics (``conversations``/``sessions``/``jobs``/``system``) are
  fanned out on the WS surface only.
"""

import asyncio
import json
from asyncio import Queue as EventFanoutQueue, QueueFull as EventFanoutQueueFull
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, Set

from cloud_dog_api_kit import create_app
from cloud_dog_api_kit.a2a.card import create_a2a_card_router, A2ASkill
from cloud_dog_api_kit.middleware.timeout import TimeoutMiddleware
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

try:
    from cloud_dog_api_kit.a2a.events import (
        ConfigChangeEvent,
        EventBroadcaster,
        create_a2a_events_router,
    )
except ImportError:
    @dataclass(frozen=True)
    class ConfigChangeEvent:
        service: str
        resource: str
        action: str
        identifier: str
        actor: Optional[str]
        correlation_id: Optional[str]
        before: Optional[Dict[str, Any]]
        after: Optional[Dict[str, Any]]
        outcome: str
        timestamp: datetime
        event_id: int = 0

        def with_event_id(self, event_id: int) -> "ConfigChangeEvent":
            return ConfigChangeEvent(
                service=self.service,
                resource=self.resource,
                action=self.action,
                identifier=self.identifier,
                actor=self.actor,
                correlation_id=self.correlation_id,
                before=self.before,
                after=self.after,
                outcome=self.outcome,
                timestamp=self.timestamp,
                event_id=event_id,
            )

    class EventBroadcaster(Protocol):
        async def publish(self, event: ConfigChangeEvent) -> ConfigChangeEvent:
            ...

        async def subscribe(self) -> AsyncIterator[ConfigChangeEvent]:
            ...

        def history(self, after_id: int = 0, limit: int = 100) -> List[ConfigChangeEvent]:
            ...

    def create_a2a_events_router(
        broadcaster: EventBroadcaster,
        *,
        base_path: str = "/a2a/events/sse",
    ) -> APIRouter:
        # Older cloud_dog_api_kit builds do not ship the optional SSE events router.
        return APIRouter()

from src.common.base_paths import join_route, normalise_base_path
from src.servers.base import BaseServer
from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# W28A-1002-CONV-EXPERT-AGENT — ServiceBackedBroadcaster wrapping the
# cross-process HTTP-bridge CRUD-event path.
# ---------------------------------------------------------------------------

# Resource topics that carry canonical ConfigChangeEvent semantics — these
# are fanned out on BOTH the legacy WS surface AND the canonical SSE surface.
# Non-config-change topics (conversations/sessions/jobs/system) carry arbitrary
# payloads on the WS surface only; they do NOT synthesise canonical events.
_CONFIG_CHANGE_TOPICS = {"experts", "users", "groups", "api_keys"}

# Map a config-change topic to the canonical ConfigChangeEvent.resource value.
# The legacy helper publishes the pluralised topic (users/groups/api_keys/
# experts); the canonical representation uses the singular resource name.
_TOPIC_TO_RESOURCE = {
    "experts": "expert",
    "users": "user",
    "groups": "group",
    "api_keys": "api_key",
}


def _legacy_broadcast_to_canonical_event(
    topic: str, body: Dict[str, Any], event_id: int
) -> Optional[ConfigChangeEvent]:
    """Translate a legacy ``/a2a/broadcast/{topic}`` body into a canonical event.

    Legacy body shape (produced by ``src.common.a2a_client.publish_config_change_event``)::

        {
            "action": "create" | "update" | "delete" | ...,
            "resource_type": "expert" | "user" | "group" | "api_key",
            "resource_id": <int>,
            "timestamp": "<ISO-8601 UTC>",
            "actor": "<username>" | "system"
        }

    Only the four config-change topics above synthesise canonical events;
    return ``None`` for any other topic so non-config-change broadcasts
    (conversations/sessions/jobs/system with arbitrary payloads) are not
    misrepresented as ConfigChangeEvents.
    """
    if topic not in _CONFIG_CHANGE_TOPICS:
        return None
    if not isinstance(body, dict):
        return None
    action = str(body.get("action") or "")
    resource_type = str(body.get("resource_type") or "")
    # Fall back to the topic-derived resource if body omits resource_type.
    if not resource_type:
        resource_type = _TOPIC_TO_RESOURCE.get(topic, topic)
    resource_id = body.get("resource_id")
    identifier = "" if resource_id is None else str(resource_id)
    if not action or not identifier:
        # Malformed legacy body — skip canonical synthesis but preserve the
        # legacy WS fan-out (legacy contract unchanged by this conversion).
        return None
    actor = body.get("actor")
    if actor is not None:
        actor = str(actor)
    ts_raw = body.get("timestamp")
    ts: datetime
    if isinstance(ts_raw, str) and ts_raw:
        try:
            ts_str = ts_raw.replace("Z", "+00:00") if ts_raw.endswith("Z") else ts_raw
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            ts = datetime.now(timezone.utc)
    else:
        ts = datetime.now(timezone.utc)
    # Legacy body carries no before/after payload; leave those unset.
    return ConfigChangeEvent(
        service="expert-agent-mcp-server",
        resource=resource_type,
        action=action,
        identifier=identifier,
        actor=actor,
        correlation_id=None,
        before=None,
        after=None,
        outcome="success",
        timestamp=ts,
        event_id=event_id,
    )


class _ExpertAgentServiceBackedBroadcaster:
    """Adapter bridging the bespoke WebSocket topic fan-out + cross-process
    HTTP-bridge CRUD events to the platform ``EventBroadcaster`` Protocol
    (cloud_dog_api_kit 0.12.0).

    The A2AServer process receives CRUD events via HTTP POST at
    ``/a2a/broadcast/{topic}`` from the separate APIServer process. For the
    four config-change topics (experts/users/groups/api_keys), the
    ``broadcast_message`` handler invokes
    ``broadcaster.publish_from_http_broadcast(topic, body)`` which
    synthesises a canonical ConfigChangeEvent (in-process) AND preserves
    the legacy WS fan-out via ``ConnectionManager.broadcast``. For the
    other four topics (conversations/sessions/jobs/system) only the legacy
    WS fan-out fires — those carry arbitrary non-config-change payloads.

    Protocol surface (runtime_checkable EventBroadcaster):
        * ``async publish(event)`` — stamp an in-process event id + fan out
          to canonical subscribers. Used by direct callers (tests /
          in-process publishers) that already construct a
          ConfigChangeEvent. Does NOT touch the legacy WS surface.
        * ``subscribe()`` — async iterator of live canonical events.
        * ``history(after_id, limit)`` — bounded replay of canonical events
          seen by this process since startup.

    Why not ``HTTPIngestAdapter`` directly? The legacy body shape lacks the
    canonical ``identifier`` field name (uses ``resource_id``) and the
    legacy topic-to-resource pluralisation mapping (``api_keys`` →
    ``api_key``) is not expressible via the adapter's accept_legacy_fields
    surface. Wrapping preserves the 21 emit call-sites byte-for-byte via
    the existing ``src.common.a2a_client`` helper.

    Why not ``WebSocketAdapter``? The legacy WS endpoint handles
    bidirectional RPC (echo frames on any received message, and NLP
    command-response frames for ``type: "command"``) that the pure
    subscriber WebSocketAdapter does not support. Keeping the inline
    endpoint preserves those contracts.
    """

    def __init__(
        self,
        connection_manager: "ConnectionManager",
        *,
        history_size: int = 1000,
        subscriber_queue_size: int = 256,
    ) -> None:
        self._manager = connection_manager
        self._history_size = int(history_size)
        self._queue_size = int(subscriber_queue_size)
        self._history: List[ConfigChangeEvent] = []
        self._subscribers: "set[EventFanoutQueue[ConfigChangeEvent]]" = set()
        self._lock = asyncio.Lock()
        self._next_id = 1

    # ------------------------------------------------------------------ props
    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def history_size(self) -> int:
        return self._history_size

    # ------------------------------------------------------------------ EventBroadcaster Protocol
    async def publish(self, event: ConfigChangeEvent) -> ConfigChangeEvent:
        """Stamp an in-process event id and fan out to canonical subscribers only.

        Does NOT fan out on the legacy WS surface — direct publish() callers
        already operate at the canonical level. For the mixed legacy+canonical
        path (HTTP broadcast ingress), use ``publish_from_http_broadcast``.
        """
        async with self._lock:
            stamped = event.with_event_id(self._next_id)
            self._next_id += 1
            self._history.append(stamped)
            if len(self._history) > self._history_size:
                self._history = self._history[-self._history_size :]
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(stamped)
            except EventFanoutQueueFull:
                continue
        return stamped

    async def subscribe(self) -> AsyncIterator[ConfigChangeEvent]:
        queue: EventFanoutQueue[ConfigChangeEvent] = EventFanoutQueue(maxsize=self._queue_size)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    def history(self, after_id: int = 0, limit: int = 100) -> List[ConfigChangeEvent]:
        if limit <= 0:
            return []
        if limit > self._history_size:
            limit = self._history_size
        out = [evt for evt in self._history if evt.event_id > int(after_id or 0)]
        if len(out) > limit:
            out = out[-limit:]
        return out

    # ------------------------------------------------------------------ HTTP ingress path
    async def publish_from_http_broadcast(
        self, topic: str, body: Dict[str, Any]
    ) -> None:
        """Handle a legacy ``/a2a/broadcast/{topic}`` POST body.

        Behaviour:
          1. ALWAYS fan out on the legacy WS surface via
             ``ConnectionManager.broadcast(topic, body)`` — preserves the
             byte-for-byte ``{"topic": <topic>, "data": <body>}`` frame shape
             regardless of whether body is a config-change envelope.
          2. If ``topic`` is one of the four config-change topics AND the
             body parses as a canonical config-change envelope, ALSO
             publish a canonical ConfigChangeEvent to the SSE subscribers.
        """
        # 1. Legacy WS fan-out — unchanged behaviour for all 8 topics.
        await self._manager.broadcast(topic, body)
        # 2. Optional canonical synthesis — only for the 4 config-change topics.
        async with self._lock:
            event_id = self._next_id
        event = _legacy_broadcast_to_canonical_event(topic, body, event_id)
        if event is None:
            return
        async with self._lock:
            self._next_id = event_id + 1
            self._history.append(event)
            if len(self._history) > self._history_size:
                self._history = self._history[-self._history_size :]
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except EventFanoutQueueFull:
                continue


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}  # topic -> connections
        self.event_topics = {
            "conversations": "Real-time conversation events",
            "sessions": "Session state change events",
            "experts": "Expert configuration events",
            "users": "User configuration events",
            "groups": "Group configuration events",
            "api_keys": "API key configuration events",
            "jobs": "Job status events",
            "system": "System status events",
        }

    async def connect(self, websocket: WebSocket, topic: str = "default"):
        """Connect a WebSocket client."""
        await websocket.accept()
        if topic not in self.active_connections:
            self.active_connections[topic] = set()
        self.active_connections[topic].add(websocket)
        logger.info(f"WebSocket connected to topic: {topic}")

    def disconnect(self, websocket: WebSocket, topic: str = "default"):
        """Disconnect a WebSocket client."""
        if topic in self.active_connections:
            self.active_connections[topic].discard(websocket)
        logger.info(f"WebSocket disconnected from topic: {topic}")

    async def broadcast(self, topic: str, data: Dict[str, Any]):
        """Broadcast message to all connections on a topic."""
        if topic not in self.active_connections:
            return

        message = json.dumps({"topic": topic, "data": data})
        disconnected = set()

        for connection in self.active_connections[topic].copy():
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send to connection: {e}")
                disconnected.add(connection)

        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn, topic)


class A2AServer(BaseServer):
    """Agent-to-Agent WebSocket server."""

    def __init__(self):
        super().__init__("A2A Server", "a2a_server")
        self._a2a_base_path = normalise_base_path(get_config("a2a_server.base_path"), default="/a2a")
        self.app = self._create_platform_app()
        self._remove_platform_health_routes()
        self._configure_platform_timeout()
        self.manager = ConnectionManager()
        # W28A-1002-CONV-EXPERT-AGENT: ServiceBackedBroadcaster wrapping the
        # ConnectionManager + cross-process HTTP-bridge ingress. Implements
        # the EventBroadcaster Protocol so create_a2a_events_router can
        # consume it directly for canonical SSE fan-out.
        self.broadcaster: EventBroadcaster = _ExpertAgentServiceBackedBroadcaster(
            self.manager
        )
        # Expose broadcaster on app.state for external tests / introspection.
        self.app.state.a2a_events_broadcaster = self.broadcaster
        self._server_task: asyncio.Task | None = None
        self._stopping = False
        self._register_routes()
        self._mount_canonical_events_router()

        # --- A2A skill handlers (real service logic) ---

        async def _a2a_list_experts(text: str) -> str:
            from src.database.connection import get_db
            from src.core.expert.manager import ExpertManager
            db = next(get_db())
            try:
                manager = ExpertManager(db)
                experts = manager.list_experts()
                names = [f"{e.id}: {e.title}" for e in experts[:20]]
                return f"Found {len(experts)} experts:\n" + "\n".join(names)
            finally:
                db.close()

        async def _a2a_execute_expert(text: str) -> str:
            from src.database.connection import get_db
            from src.core.expert.manager import ExpertManager
            from src.core.llm.manager import LLMManager
            db = next(get_db())
            try:
                manager = ExpertManager(db)
                experts = manager.list_experts()
                if not experts:
                    return "No experts configured"
                expert = experts[0]
                llm = LLMManager()
                response = await llm.generate([
                    {"role": "system", "content": expert.description or "You are a helpful assistant."},
                    {"role": "user", "content": text},
                ])
                return response.get("content", str(response))
            finally:
                db.close()

        async def _a2a_chat(text: str) -> str:
            from src.core.llm.manager import LLMManager
            llm = LLMManager()
            response = await llm.generate([{"role": "user", "content": text}])
            return response.get("content", str(response))

        # W28M-1605: additive agentic document-process action skill. Parses a
        # single natural-language instruction, IDAM-gates the chat actor, invokes
        # the W28M-1604 document-generation capability via the proven execute
        # path (Drive read/write + notification delivery), and returns the
        # in-chat confirmation. Additive only — the conversational skills above
        # and chat_tool/execute_tool are unchanged.
        async def _a2a_run_document_process(text: str) -> str:
            from src.core.agentic.document_process import run_document_process
            try:
                return await run_document_process(text)
            except Exception as exc:  # never leak a stack trace into chat
                logger.error(f"run_document_process failed: {exc}", exc_info=True)
                return ("The document process could not be started due to an internal error. "
                        "No document was generated and no delivery was claimed.")

        # W28M-1606: additive chat entry to the layered scheduled-demo capability —
        # the SAME run_research_document capability the scheduler invokes, so the
        # chat-client path and the scheduled path produce equivalent quality (chat
        # parity). Additive only; nothing above is changed.
        async def _a2a_run_research_document(text: str) -> str:
            import re as _re
            from src.core.agentic.research_document import run_research_document, DOC_TOPICS
            low = (text or "").lower()
            topic = None
            if "nato" in low:
                topic = "nato-doctrine"
            elif ("report" in low or "document" in low) and ("transparent" in low or "border" in low):
                topic = "transparent-borders-report"
            elif "transparent" in low or "border" in low:
                topic = "transparent-borders"
            elif "ukraine" in low:
                topic = "ukraine"
            topic = topic or next((t for t in DOC_TOPICS if t.replace("-", " ") in low), None)
            if not topic:
                return ("Which scheduled demo report would you like? Options: ukraine, "
                        "transparent-borders, transparent-borders-report, nato-doctrine.")
            m = _re.search(r"\bfor\s+([A-Za-z][A-Za-z -]{2,})", text or "")
            target = m.group(1).strip().lower().replace(" ", "-") if m else None
            deliver = any(w in low for w in ("send", "deliver", "email", "recipients", "notify"))
            try:
                res = await run_research_document(topic=topic, target=target,
                                                  deliver=deliver, async_mode=True)
                return (f"Started the layered full-depth {topic} research document "
                        f"(run id {res.get('run_id')}, target {res.get('target')}). It is web-grounded and "
                        f"generated to the W28M-1604 quality bar (>=0.9x depth, comparator tables, cited sources, "
                        f"plain-english + humanise correction)"
                        + (" and will be delivered to the configured recipients on completion." if deliver
                           else "; delivery was not requested.")
                        + " Poll status with get_research_document_status using the run id.")
            except Exception as exc:
                logger.error(f"run_research_document failed: {exc}", exc_info=True)
                return ("The research document could not be started due to an internal error. "
                        "No document was generated and no delivery was claimed.")

        # A2A agent card and task submission router
        _a2a_skills = [
            A2ASkill(id="chat", name="Chat", description="Converse with the expert agent", handler=_a2a_chat),
            A2ASkill(id="list_experts", name="List Experts", description="List available expert configurations", handler=_a2a_list_experts),
            A2ASkill(id="execute_expert", name="Execute Expert", description="Execute a named expert pipeline", handler=_a2a_execute_expert),
            A2ASkill(id="run_document_process", name="Run Document Process",
                     description="Run a document-generation process (e.g. 'Run the Document Researcher process for "
                                 "France, and send to all recipients, return here confirmation of delivery'): "
                                 "intent-parse, IDAM-gate, generate+correct+deliver, and confirm in chat.",
                     handler=_a2a_run_document_process),
            A2ASkill(id="run_research_document", name="Run Research Document",
                     description="Chat entry to the W28M-1606 layered scheduled demo: web-grounded research + "
                                 "full-depth W28M-1604 report for a topic (e.g. 'generate the transparent-borders "
                                 "report for poland and send it'). Same capability the scheduler runs (chat parity).",
                     handler=_a2a_run_research_document),
        ]
        _a2a_card_router = create_a2a_card_router(
            name="expert-agent",
            description="Expert agent A2A server for real-time events and expert pipeline execution",
            skills=_a2a_skills,
        )
        self.app.include_router(_a2a_card_router, prefix=self._a2a_base_path or "")

        # W28A-970e3 / PS-92: also mount the A2A card router at root so the
        # discovery endpoint answers on /.well-known/agent.json (platform
        # convention per W28A-970i db-mcp-server reference). The prefixed
        # mount above still serves /a2a/.well-known/agent.json for
        # prefix-strip Traefik routes. Using a fresh router instance avoids
        # mutating the prefixed router's internal state.
        _a2a_root_card_router = create_a2a_card_router(
            name="expert-agent",
            description="Expert agent A2A server for real-time events and expert pipeline execution",
            skills=_a2a_skills,
        )
        self.app.include_router(_a2a_root_card_router)

    def _create_platform_app(self):
        """Create A2A app via cloud_dog_api_kit across package versions."""
        kwargs = {
            "title": "Expert Agent A2A Server",
            "version": "0.1.0",
            "description": "Agent-to-Agent realtime event server for Expert Agent",
            "cors_origins": ["*"],
        }
        try:
            return create_app(**kwargs, register_signal_handlers_on_startup=False)
        except TypeError as exc:
            if "register_signal_handlers_on_startup" not in str(exc):
                raise
            return create_app(**kwargs)

    def _remove_platform_health_routes(self) -> None:
        """Keep existing /health and /a2a/health contracts stable."""
        health_paths = {"/health", "/ready", "/live", "/status"}
        self.app.router.routes = [
            route
            for route in self.app.router.routes
            if getattr(route, "path", None) not in health_paths
        ]

    def _configure_platform_timeout(self) -> None:
        """Align API kit timeout middleware with project timeout settings."""
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

    def _mount_canonical_events_router(self) -> None:
        """Mount the canonical PS-72 SSE surface at ``<base>/events/sse``.

        Additive — does NOT disturb the legacy WebSocket or /a2a/broadcast
        routes. Canonical consumers can subscribe to PS-72-compliant frames
        via SSE without interfering with legacy WS clients.

        Mount path deliberately nests under ``/events/sse`` (not
        ``/events``) so there is no collision with the legacy
        ``broadcast/{topic}`` POST or ``ws/{topic}`` WebSocket routes.
        """
        base_path = f"{self._a2a_base_path or ''}/events/sse"
        # Ensure base_path starts with / per create_a2a_events_router contract.
        if not base_path.startswith("/"):
            base_path = "/" + base_path
        events_router = create_a2a_events_router(
            self.broadcaster,
            base_path=base_path,
        )
        self.app.include_router(events_router)

    def _register_routes(self):
        """Register A2A routes."""
        websocket_path = join_route(self._a2a_base_path, "/ws/{topic}")
        topics_path = join_route(self._a2a_base_path, "/topics")
        broadcast_path = join_route(self._a2a_base_path, "/broadcast/{topic}")
        health_path = join_route(self._a2a_base_path, "/health")

        async def websocket_endpoint(websocket: WebSocket, topic: str):
            """WebSocket endpoint for a topic."""
            await self.manager.connect(websocket, topic)
            try:
                while True:
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    logger.debug(f"Received message on topic {topic}: {message}")

                    # Process natural language commands
                    if message.get("type") == "command":
                        result = await self._process_command(topic, message.get("command"))
                        await websocket.send_text(
                            json.dumps(
                                {"topic": topic, "type": "command_response", "result": result}
                            )
                        )
                    else:
                        # Echo back
                        await websocket.send_text(json.dumps({"topic": topic, "echo": message}))
            except WebSocketDisconnect:
                self.manager.disconnect(websocket, topic)
        self.app.add_api_websocket_route(websocket_path, websocket_endpoint)

        async def list_topics():
            """List available event topics."""
            return {
                "topics": self.manager.event_topics,
                "active_connections": {
                    topic: len(conns) for topic, conns in self.manager.active_connections.items()
                },
            }
        self.app.add_api_route(topics_path, list_topics, methods=["GET"])

        async def broadcast_message(topic: str, data: Dict[str, Any]):
            """Broadcast message to all connections on a topic.

            W28A-1002-CONV-EXPERT-AGENT: Delegates to the ServiceBacked
            broadcaster so BOTH the legacy WS surface AND (for config-change
            topics) the canonical SSE surface receive the event. Response
            envelope unchanged from pre-convergence (``{"status":
            "broadcast", "topic": <topic>}``).
            """
            # publish_from_http_broadcast always fans out on the legacy WS
            # surface; for the 4 config-change topics it ALSO synthesises a
            # canonical ConfigChangeEvent into the SSE subscribers.
            if isinstance(self.broadcaster, _ExpertAgentServiceBackedBroadcaster):
                await self.broadcaster.publish_from_http_broadcast(topic, data)
            else:
                # Fall back to the pure legacy WS fan-out if a different
                # broadcaster has been substituted (tests / custom wiring).
                await self.manager.broadcast(topic, data)
            return {"status": "broadcast", "topic": topic}
        self.app.add_api_route(broadcast_path, broadcast_message, methods=["POST"])

        async def a2a_health():
            """A2A health check."""
            total_connections = sum(
                len(conns) for conns in self.manager.active_connections.values()
            )
            return {
                "status": "healthy",
                "service": "a2a",
                "application": "expert-agent-mcp-server",
                "version": "0.1.0",
                "connections": total_connections,
                "topics": list(self.manager.active_connections.keys()),
                "env": {
                    "config_env_file": get_config("expert.env_file"),
                    "secrets_env_files": get_config("expert.env_secrets_files"),
                    "testing": get_config("test.enabled"),
                },
            }
        self.app.add_api_route(health_path, a2a_health, methods=["GET"])

        @self.app.get("/health")
        async def health():
            """Compatibility health check (server root)."""
            return await a2a_health()

    async def start(self):
        """Start the A2A server."""
        import uvicorn

        logger.info(f"Starting A2A WebSocket server on {self.host}:{self.port}")
        config = uvicorn.Config(app=self.app, host=self.host, port=int(self.port), log_level="info")
        self._server = uvicorn.Server(config)
        self._stopping = False
        self._server_task = asyncio.create_task(self._server.serve())
        self._server_task.add_done_callback(self._on_server_task_done)
        await asyncio.sleep(0.5)
        if self._server_task.done():
            exc = self._server_task.exception()
            raise RuntimeError(f"A2A server failed during startup: {exc}")

    def _on_server_task_done(self, task: asyncio.Task) -> None:
        """Detect unexpected uvicorn task termination."""
        if self._stopping:
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            exc = None
        if exc:
            logger.error(f"A2A server task exited unexpectedly: {exc}", exc_info=True)
        else:
            logger.error("A2A server task exited unexpectedly without error")
        self._shutdown_event.set()

    async def stop(self):
        """Stop the A2A server."""
        self._stopping = True
        if hasattr(self, "_server") and self._server:
            self._server.should_exit = True
        if self._server_task and not self._server_task.done():
            try:
                await asyncio.wait_for(self._server_task, timeout=15)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for A2A server task shutdown; cancelling task")
                self._server_task.cancel()

        # Close all connections
        for topic_connections in self.manager.active_connections.values():
            for connection in topic_connections.copy():
                try:
                    await connection.close()
                except Exception:
                    pass

        self.manager.active_connections.clear()
        logger.info("Stopped A2A server")

    async def health_check(self) -> bool:
        """Check if server is healthy."""
        return self.is_running()

    async def broadcast(self, topic: str, data: Dict[str, Any]):
        """Broadcast message to all connected clients."""
        if isinstance(self.broadcaster, _ExpertAgentServiceBackedBroadcaster):
            await self.broadcaster.publish_from_http_broadcast(topic, data)
        else:
            await self.manager.broadcast(topic, data)

    async def _process_command(self, topic: str, command: str) -> Dict[str, Any]:
        """
        Process natural language command.

        Args:
            topic: Event topic
            command: Natural language command

        Returns:
            Command result
        """
        # Simple command processing (can be enhanced with LLM)
        command_lower = command.lower()

        if "status" in command_lower or "health" in command_lower:
            return {"type": "status", "status": "healthy", "topic": topic}
        elif "list" in command_lower:
            return {"type": "list", "items": []}
        else:
            return {"type": "unknown", "command": command, "message": "Command not recognized"}

    async def publish_event(self, topic: str, event_type: str, data: Dict[str, Any]):
        """
        Publish event to topic.

        Args:
            topic: Event topic (conversations, sessions, experts, jobs, system)
            event_type: Type of event
            data: Event data
        """
        event = {"type": event_type, "timestamp": datetime.utcnow().isoformat(), "data": data}
        if isinstance(self.broadcaster, _ExpertAgentServiceBackedBroadcaster):
            await self.broadcaster.publish_from_http_broadcast(topic, event)
        else:
            await self.manager.broadcast(topic, event)
# W28A-565 cache bust 1775026109
