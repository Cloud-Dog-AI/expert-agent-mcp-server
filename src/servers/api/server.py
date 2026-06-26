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
API Server

License: Apache 2.0
Ownership: Cloud Dog
Description: FastAPI-based REST API server

Related Requirements: FR1.7, FR1.24
Related Tasks: T030
Related Architecture: CC1.1.1
Related Tests: ST1.1, IT2.7

Recent Changes:
- Initial implementation
"""

import asyncio
import uuid
from typing import Optional

from cloud_dog_api_kit import create_app, create_health_router
from cloud_dog_cache import create_cache_router, init_cache_from_config
from cloud_dog_api_kit.correlation.context import set_correlation_id as set_api_kit_correlation_id
from cloud_dog_api_kit.middleware.timeout import TimeoutMiddleware
from cloud_dog_logging import (
    clear_correlation_id as clear_logging_correlation_id,
    set_correlation_id as set_logging_correlation_id,
)
# NOTE: AuthContextMiddleware removed — see comment in __init__ for rationale.
# from cloud_dog_idam.api.fastapi.middleware import AuthContextMiddleware
import uvicorn
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.common.base_paths import join_route, normalise_base_path
from src.config.loader import get_config
from src.core.http import close_shared_async_clients
from src.servers.base import BaseServer
from src.utils.logger import get_logger

try:
    from src.core.observability.metrics import setup_metrics

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    setup_metrics = None


def _app_version() -> str:
    """EA-03: resolve the API/health version from build metadata (build-info.json
    baked at image build) so the platform health router and OpenAPI report the
    real build, not a hardcoded literal. Falls back to config then the package."""
    try:
        import json as _json
        from pathlib import Path as _Path
        bi = _Path("/app/build-info.json")
        if bi.exists():
            v = _json.loads(bi.read_text(encoding="utf-8")).get("version")
            if v:
                return str(v)
    except Exception:
        pass
    return get_config("app.version") or "0.1.1RC1"


logger = get_logger(__name__)


class _CorrelationBridgeMiddleware(BaseHTTPMiddleware):
    """Ensure a correlation ID exists even when callers omit X-Correlation-Id."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", "").strip() or uuid.uuid4().hex
        correlation_id = request.headers.get("x-correlation-id", "").strip() or request_id

        updated_headers = [
            (key, value)
            for key, value in request.scope.get("headers", [])
            if key not in {b"x-request-id", b"x-correlation-id"}
        ]
        updated_headers.append((b"x-request-id", request_id.encode("utf-8")))
        updated_headers.append((b"x-correlation-id", correlation_id.encode("utf-8")))
        request.scope["headers"] = updated_headers

        set_api_kit_correlation_id(correlation_id)
        set_logging_correlation_id(correlation_id)
        try:
            return await call_next(request)
        finally:
            clear_logging_correlation_id()


class APIServer(BaseServer):
    """RESTful API server."""

    def __init__(self):
        super().__init__("API Server", "api_server")
        self._api_base_path = normalise_base_path(get_config("api_server.base_path"), default="/v1")
        self.app = self._create_platform_app()
        self._server: Optional[uvicorn.Server] = None
        self._server_task: Optional[asyncio.Task] = None
        self._stopping = False

        # NOTE: AuthContextMiddleware from cloud_dog_idam >=0.2.0 is a full auth
        # enforcer that blocks all non-skip requests when api_key_manager /
        # token_service are not wired.  Route-level Depends(verify_api_key) in
        # src/servers/api/auth.py already handles all authentication; the
        # CorrelationMiddleware from cloud_dog_api_kit already sets
        # request.state.correlation_id.  Do NOT re-add AuthContextMiddleware
        # without wiring the IDAM managers — it will 401-block every
        # non-health request.
        self._install_platform_health_router()
        self._configure_platform_timeout()

        # Initialize database
        from src.database.connection import apply_migrations, init_db, get_engine
        from src.database import models_channel_extensions  # noqa: F401
        from src.database.models import Base

        # Apply Alembic migrations before initialising engines so long-lived
        # local DB files cannot remain on an older schema revision.
        apply_migrations()

        # Initialise database using the current config in this process.
        # This avoids stale engine/session factories from earlier imports.
        init_db(force_reinit=True)
        # Create all tables if they don't exist (idempotent - safe to call multiple times)
        engine = get_engine()
        Base.metadata.create_all(bind=engine)

        # Ensure a bootstrap API key exists for the configured test/admin user.
        # This enables RULES.md-compliant API-key authentication without manual DB edits.
        self._ensure_bootstrap_api_key()
        self._ensure_bootstrap_flat_role_users()
        self._init_cache_layer()

        self._ensure_bootstrap_vector_stores()

        # Setup metrics
        if METRICS_AVAILABLE and setup_metrics:
            setup_metrics()

        # Setup real-time synchronization with A2A server
        self._setup_synchronization()

        # Register routes
        self._register_routes()

    def _create_platform_app(self):
        """Create API app via cloud_dog_api_kit across package versions."""
        kwargs = {
            "title": "Expert Agent MCP Server API",
            "version": _app_version(),
            "description": "RESTful API for Expert Agent MCP Server",
            "cors_origins": ["*"],
            "auth_verify_fn": self._verify_api_key_for_health_status,
        }
        try:
            app = create_app(
                **kwargs,
                register_signal_handlers_on_startup=False,
            )
        except TypeError as exc:
            if "register_signal_handlers_on_startup" not in str(exc):
                raise
            app = create_app(**kwargs)

        from src.servers.api.auth import AuthStateMiddleware, ReadOnlyApiWriteGateMiddleware

        # Order matters: add_middleware stacks outermost-last. AuthStateMiddleware
        # (added last) runs FIRST and populates request.state.user; the read-only
        # write-gate (added before it) then runs and reads that resolved user.
        app.add_middleware(_CorrelationBridgeMiddleware)
        app.add_middleware(ReadOnlyApiWriteGateMiddleware)
        app.add_middleware(AuthStateMiddleware)
        return app

    def _install_platform_health_router(self) -> None:
        """Replace default health routes with platform create_health_router()."""
        # Remove the API-kit defaults first, then re-add only the public
        # platform health routes. The project supplies its own /status route
        # later with expert-agent-specific metrics.
        health_paths = {"/health", "/ready", "/live", "/status"}
        self.app.router.routes = [
            route
            for route in self.app.router.routes
            if getattr(route, "path", None) not in health_paths
        ]
        from src.config.loader import get_config
        env_file = get_config("expert.env_file") or ""
        router = create_health_router(
            application_name="expert-agent-mcp-server",
            version=_app_version(),
            env_file=str(env_file),
            auth_dependency=None,
        )
        router.routes = [
            route
            for route in router.routes
            if getattr(route, "path", None) not in {"/health", "/status"}
        ]
        self.app.include_router(router)
        if self._api_base_path:
            self.app.include_router(router, prefix=self._api_base_path, include_in_schema=False)

    def _configure_platform_timeout(self) -> None:
        """Align API kit timeout middleware with project test/runtime timeout config."""
        from src.config.loader import get_config

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

    def _init_cache_layer(self) -> None:
        """Initialise the platform cache manager from the active project config."""
        if init_cache_from_config is None:
            return
        from src.config.loader import get_config

        init_cache_from_config(get_config)

    @staticmethod
    async def _verify_api_key_for_health_status(api_key: str):
        """Adapter for api_kit /status auth checks."""
        if not api_key:
            return None
        from src.database.connection import get_db
        from src.core.auth.api_key_manager import APIKeyManager

        db_gen = get_db()
        db = next(db_gen)
        try:
            manager = APIKeyManager(db)
            key = manager.validate_key(api_key)
            if not key:
                return None
            return {"user_id": str(key.user_id or ""), "roles": [], "tenant_id": None}
        finally:
            db.close()

    def _ensure_bootstrap_api_key(self) -> None:
        """Ensure the configured test user exists as admin, and optionally seed a test API key."""
        try:
            from cloud_dog_idam.api_keys.hashing import hash_api_key
            from src.config.loader import get_config
            from src.database.connection import get_db
            from src.database.models import User, APIKey
            from src.core.auth.password import hash_password

            test_api_key = get_config("test.api_key")
            test_username = get_config("test.user.username")
            test_email = get_config("test.user.email")
            test_password = get_config("test.user.password")
            if not test_username or not test_email:
                return

            db_gen = get_db()
            db = next(db_gen)
            try:
                user = db.query(User).filter(User.username == str(test_username)).first()
                if not user:
                    user = User(
                        username=str(test_username),
                        email=str(test_email),
                        display_name=str(test_username),
                        pwd_hash=hash_password(str(test_password)) if test_password else None,
                        role="admin",
                        enabled=True,
                        user_type="local" if test_password else "external",
                    )
                    db.add(user)
                    db.commit()
                    db.refresh(user)
                else:
                    # Ensure admin and enabled
                    if user.role != "admin":
                        user.role = "admin"
                    if not user.enabled:
                        user.enabled = True
                    if test_password:
                        user.pwd_hash = hash_password(str(test_password))
                        user.user_type = "local"
                    db.commit()

                if test_api_key:
                    key_hash = hash_api_key(str(test_api_key))
                    existing = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()
                    if not existing:
                        api_key = APIKey(
                            key_hash=key_hash,
                            user_id=user.id,
                            name="bootstrap_test_key",
                            read_channels=True,
                            write_channels=True,
                            read_logs=True,
                            write_logs=True,
                            read_histories=True,
                            write_histories=True,
                            revoked=False,
                        )
                        db.add(api_key)
                        db.commit()
            finally:
                db.close()
        except Exception as e:
            # Never prevent server startup due to bootstrap key; log and continue.
            logger.warning(f"Failed to ensure bootstrap API key: {e}")

    def _ensure_bootstrap_flat_role_users(self) -> None:
        """Seed the read-write and read-only flat-role users (W28A-729-R5).

        The three-role flat WebUI login (admin / read-write / read-only)
        authenticates against THIS API backend (no local cred-seeding fork).
        ``admin`` is the existing bootstrap admin
        (CLOUD_DOG__EXPERT__WEB_SERVER__USERNAME/PASSWORD). This seeds the other
        two as REAL users via the user-management path (``UserManager`` —
        NO direct DB mutation): read-write -> backend role ``user`` (normalises
        to the read-write flat role); read-only -> backend role ``viewer``
        (normalises to the read-only flat role). Idempotent; never blocks startup.
        """
        try:
            from src.config.loader import get_config
            from src.core.auth.user_manager import UserManager
            from src.database.connection import get_db

            seeds = (
                (
                    str(get_config("web_server.read_write_username") or "read-write").strip(),
                    # Demo password meets the complexity policy (upper+lower+digit+special);
                    # overridable via web_server.read_write_password / the env key.
                    str(get_config("web_server.read_write_password") or "BlueRiverChair1!"),
                    "read-write@expert.local",
                    "user",
                ),
                (
                    str(get_config("web_server.read_only_username") or "read-only").strip(),
                    str(get_config("web_server.read_only_password") or "GreenRiverDesk2!"),
                    "read-only@expert.local",
                    "viewer",
                ),
            )

            db_gen = get_db()
            db = next(db_gen)
            try:
                manager = UserManager(db)
                for username, password, email, role in seeds:
                    if not username:
                        continue
                    existing = manager.get_user(username=username)
                    if existing is None:
                        manager.create_user(
                            username=username,
                            email=email,
                            password=password,
                            display_name=username,
                            role=role,
                            enabled=True,
                            user_type="local",
                        )
                    elif existing.role != role or not existing.enabled:
                        # Keep the seeded demo role correct without re-creating.
                        manager.update_user(existing.id, role=role, enabled=True)
            finally:
                db.close()
        except Exception as e:
            # Never prevent server startup due to flat-role seeding; log and continue.
            logger.warning(f"Failed to ensure flat-role users: {e}")

    def _ensure_bootstrap_vector_stores(self) -> None:
        try:
            from src.config.loader import get_config
            from src.database.connection import get_db
            from src.database.models import VectorStore
            from src.core.vector.manager import VectorStoreManager

            cfg = get_config("vector_stores_config")
            if not isinstance(cfg, dict) or not cfg:
                return

            db_gen = get_db()
            db = next(db_gen)
            manager = VectorStoreManager(db)
            try:
                for store_type, profiles in cfg.items():
                    if not isinstance(profiles, dict):
                        continue
                    profile_cfg = profiles.get("_DEFAULT_")
                    if not isinstance(profile_cfg, dict):
                        continue
                    if profile_cfg.get("enabled") is False:
                        continue

                    name = f"bootstrap_{str(store_type).lower()}_default"
                    existing = db.query(VectorStore).filter(VectorStore.name == name).first()
                    if existing:
                        continue

                    access_control = (
                        profile_cfg.get("access_control")
                        if isinstance(profile_cfg.get("access_control"), dict)
                        else None
                    )
                    config = {
                        k: v
                        for k, v in profile_cfg.items()
                        if k not in ("enabled", "access_control")
                    }
                    if not config:
                        continue

                    manager.create_vector_store(
                        name=name,
                        store_type=str(store_type).lower(),
                        config=config,
                        enabled=True,
                        access_control=access_control,
                    )
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to ensure bootstrap vector stores: {e}")

    def _register_routes(self):
        """Register API routes."""
        from src.servers.api.routes import (
            health,
            sessions,
            users,
            experts,
            channels,
            api_docs,
            groups,
            knowledge,
            jobs,
            files,
            prompts,
            validation,
            quality,
            testing,
            audit,
            operations,
            vector_stores,
            rbac,
            admin_roles,
            admin_permissions,
            auth,
            api_keys,
            services,
        )
        from src.servers.mcp.tools import MCPTools
        from fastapi import Request

        def include_api_router(router) -> None:
            self.app.include_router(router)
            if self._api_base_path:
                self.app.include_router(router, prefix=self._api_base_path, include_in_schema=False)

        def add_api_route_with_compat(
            suffix: str,
            endpoint,
            *,
            methods: list[str],
            include_in_schema: bool = True,
            response_model=None,
        ) -> None:
            primary_path = join_route(self._api_base_path, suffix)
            self.app.add_api_route(
                primary_path,
                endpoint,
                methods=methods,
                include_in_schema=include_in_schema,
                response_model=response_model,
            )
            if primary_path != suffix:
                self.app.add_api_route(
                    suffix,
                    endpoint,
                    methods=methods,
                    include_in_schema=False,
                    response_model=response_model,
                )

        # Include routers
        include_api_router(health.router)
        include_api_router(auth.router)
        include_api_router(api_keys.router)
        include_api_router(sessions.router)
        include_api_router(users.router)
        include_api_router(groups.router)
        include_api_router(experts.router)
        include_api_router(channels.router)
        include_api_router(knowledge.router)
        include_api_router(jobs.router)
        include_api_router(files.router)
        include_api_router(prompts.router)
        include_api_router(validation.router)
        include_api_router(quality.router)
        include_api_router(testing.router)
        include_api_router(audit.router)
        include_api_router(audit.logs_router)
        include_api_router(operations.router)
        include_api_router(vector_stores.router)
        include_api_router(services.router)
        include_api_router(api_docs.router)
        include_api_router(rbac.router)
        include_api_router(admin_roles.router)
        # W28A-891-R2: publish the assignable-permission catalogue at /admin/permissions so the
        # shared @cloud-dog/idam Roles/RBAC pages resolve /v1/admin/permissions (was 404).
        include_api_router(admin_permissions.router)
        # W28A-876: canonical PS-71 IDAM admin aliases. The shared @cloud-dog/idam WebUI
        # fetches /v1/admin/{users,groups,api-keys}; expert manages these at /users,/groups,
        # /api-keys. Mount the SAME routers under /admin/* (parity with admin_roles + the
        # file/db/git services) so the Users/Groups/API-Keys pages render.
        self.app.include_router(users.router, prefix="/admin")
        self.app.include_router(groups.router, prefix="/admin")
        self.app.include_router(api_keys.router, prefix="/admin")
        if self._api_base_path:
            self.app.include_router(users.router, prefix=self._api_base_path + "/admin", include_in_schema=False)
            self.app.include_router(groups.router, prefix=self._api_base_path + "/admin", include_in_schema=False)
            self.app.include_router(api_keys.router, prefix=self._api_base_path + "/admin", include_in_schema=False)
        # W28A-876: mount the canonical SHARED cloud_dog_idam idam_v1_router (resource-registry +
        # rbac-bindings) so the RBAC page resolves /idam/v1/* (parity with admin_roles).
        try:
            from cloud_dog_idam.api.fastapi.router import (
                idam_v1_router as _idam_v1_router,
                set_idam_v1_engine as _set_idam_v1_engine,
            )

            try:
                from src.database.connection import get_engine as _get_idam_engine
                _set_idam_v1_engine(_get_idam_engine())
            except Exception:
                pass
            include_api_router(_idam_v1_router)
        except Exception:
            pass
        if create_cache_router is not None:
            include_api_router(create_cache_router())

        # Register MCP routes (integrated into API server)
        mcp_tools = MCPTools()

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

            return await mcp_tools.chat_tool(
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
        add_api_route_with_compat("/mcp/chat", mcp_chat, methods=["POST"])

        async def mcp_health():
            """MCP health check endpoint."""
            return {"status": "healthy", "service": "mcp"}
        add_api_route_with_compat("/mcp/health", mcp_health, methods=["GET"])

        # Register A2A routes (integrated into API server)
        async def a2a_health():
            """A2A health check endpoint."""
            return {"status": "healthy", "service": "a2a", "active_connections": 0}
        add_api_route_with_compat("/a2a/health", a2a_health, methods=["GET"])

        async def root():
            """Root endpoint."""
            return {
                "service": "Expert Agent MCP Server API",
                "version": _app_version(),
                "docs": join_route(self._api_base_path, "/docs/routes"),
                "health": join_route(self._api_base_path, "/health"),
            }
        add_api_route_with_compat("/", root, methods=["GET"])

        async def docs_alias() -> RedirectResponse:
            """Handle docs probes after ingress path rewriting."""
            return RedirectResponse(url=join_route(self._api_base_path, "/docs/routes"), status_code=307)
        add_api_route_with_compat("/api-docs", docs_alias, methods=["GET"], include_in_schema=False)
        add_api_route_with_compat("/-docs", docs_alias, methods=["GET"], include_in_schema=False)

        async def metrics():
            """Prometheus metrics endpoint."""
            if not METRICS_AVAILABLE:
                return {"error": "Metrics not available - prometheus_client not installed"}
            try:
                from src.core.observability.metrics import get_metrics_output
                from fastapi.responses import Response

                output = get_metrics_output()
                return Response(
                    content=output if isinstance(output, bytes) else output.encode(),
                    media_type="text/plain",
                )
            except Exception as e:
                logger.warning(f"Metrics not available: {e}")
                return {"status": "metrics not available"}
        add_api_route_with_compat("/metrics", metrics, methods=["GET"])

    async def start(self):
        """Start the API server."""
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=int(self.port),
            log_level="info" if not self.debug else "debug",
            access_log=True,
            limit_concurrency=100,
        )
        self._server = uvicorn.Server(config)
        self._stopping = False
        self._server_task = asyncio.create_task(self._server.serve())
        self._server_task.add_done_callback(self._on_server_task_done)
        # Give server time to start
        await asyncio.sleep(0.5)
        if self._server_task.done():
            exc = self._server_task.exception()
            raise RuntimeError(f"API server failed during startup: {exc}")

    def _on_server_task_done(self, task: asyncio.Task) -> None:
        """Detect unexpected uvicorn task termination."""
        if self._stopping:
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            exc = None
        if exc:
            logger.error(f"API server task exited unexpectedly: {exc}", exc_info=True)
        else:
            logger.error("API server task exited unexpectedly without error")
        self._shutdown_event.set()

    async def stop(self):
        """Stop the API server."""
        self._stopping = True
        if self._server:
            self._server.should_exit = True
        if self._server_task and not self._server_task.done():
            try:
                await asyncio.wait_for(self._server_task, timeout=15)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for API server task shutdown; cancelling task")
                self._server_task.cancel()
        await close_shared_async_clients()

    async def health_check(self) -> bool:
        """Check if server is healthy."""
        return self.is_running()

    def _setup_synchronization(self):
        """Setup real-time synchronization with A2A server."""
        try:
            from src.config.loader import get_config

            # Try to get A2A server instance (if running)
            # This is a simplified approach - in production, use a service registry
            try:
                # Check if A2A server is configured and running
                a2a_config = get_config("a2a_server")
                if not isinstance(a2a_config, dict):
                    raise RuntimeError("a2a_server config not loaded")
                enabled = a2a_config.get("enabled")
                if enabled is True:
                    # In a real implementation, we'd connect to the A2A server
                    # For now, we'll set up the synchronizer to work when A2A is available
                    logger.info("Real-time synchronization configured (A2A server enabled)")
            except Exception as e:
                logger.debug(f"A2A server not available for synchronization: {e}")
        except Exception as e:
            logger.warning(f"Failed to setup synchronization: {e}")
