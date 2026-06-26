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
Web UI Server Implementation

License: Apache 2.0
Ownership: Cloud Dog
Description: Web UI server with chat interface and administration

Related Requirements: FR1.8, FR1.21, FR1.22, FR1.43
Related Tasks: T030, T048, T049, T059, T060
Related Architecture: CC1.1.2
Related Tests: ST1.4, AT1.8, AT1.20, AT1.21

Recent Changes:
- Initial implementation
"""

import asyncio
import json
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional

from cloud_dog_api_kit import create_app
from cloud_dog_api_kit.middleware.timeout import TimeoutMiddleware
from cloud_dog_api_kit.web.proxy import WebApiProxy
# NOTE: AuthContextMiddleware removed — see api/server.py for rationale.
# from cloud_dog_idam.api.fastapi.middleware import AuthContextMiddleware
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.requests import ClientDisconnect

from src.common.base_paths import join_route, normalise_base_path
from src.config.loader import ConfigLoader, get_config, load_config
from src.core.http import close_shared_async_clients
from src.servers.api.auth import job_permissions_for_role
from src.core.auth.expert_flat_roles import (
    READ_ONLY_ROLE,
    is_write_gated_data_path,
    normalise_flat_role,
    permissions_for_role,
    role_can_write,
)
from src.servers.base import BaseServer
from src.utils.logger import get_logger

logger = get_logger(__name__)

# PS-WEBUI-URL-CANONICAL v1.0 (W28E-1825) — W28E-1809C Stream-C canonicalisation.
# Mirrors the accepted geospatial Stream-C (W28E-1812C) implementation: legacy
# WebUI aliases are 308-redirected to the single canonical route so the SPA
# fallback never masks URL drift (WURL-001/002/004/009). Suffixes are relative to
# ``web_server.base_path`` (default "") and joined with it at request time.
#
# Expert-agent divergence from the geospatial map (WURL-008): ``/docs``,
# ``/openapi.json`` and ``/redoc`` are REAL FastAPI Swagger/OpenAPI endpoints on
# this web tier (live 200) and MUST be retained, NOT redirected through a WebUI
# alias. Only ``/api-docs`` is the WebUI Developer→API-Docs alias.
_LEGACY_WEBUI_REDIRECT_SUFFIXES: Dict[str, str] = {
    "/ui/login": "/login",
    "/auth/login": "/login",
    "/audit": "/audit-log",
    "/diagnostics-audit": "/audit-log",
    "/observability": "/audit-log",
    "/logs": "/audit-log",
    "/idam/users": "/admin/users",
    "/idam/groups": "/admin/groups",
    "/idam/api-keys": "/admin/api-keys",
    "/apikeys": "/admin/api-keys",
    "/api-keys": "/admin/api-keys",
    "/idam/roles": "/admin/roles",
    "/idam/rbac": "/admin/rbac",
    "/rbac": "/admin/rbac",
    "/api-docs": "/developer/api-docs",
    "/mcp-console": "/developer/mcp-console",
    "/a2a-console": "/developer/a2a-console",
    "/jobs": "/system/jobs",
    "/settings": "/system/settings",
    "/about": "/system/about",
}

# Canonical taxonomy routes that MUST serve the SPA shell (HTTP 200) after the
# redirect middleware. The SPA catch-all already serves these; this set is the
# audit/test contract for PS-WEBUI-URL-CANONICAL §2.
_CANONICAL_WEBUI_SUFFIXES: frozenset[str] = frozenset(
    {
        "/",
        "/login",
        "/audit-log",
        "/admin/users",
        "/admin/groups",
        "/admin/api-keys",
        "/admin/roles",
        "/admin/rbac",
        "/developer/api-docs",
        "/developer/mcp-console",
        "/developer/a2a-console",
        "/system/jobs",
        "/system/settings",
        "/system/about",
    }
)

# PS-WEBUI-URL-CANONICAL v1.0 WURL-007 — the SPA shell is served ONLY for known
# top-level WebUI route segments; any other path is a route-level 404 so the SPA
# fallback never masks URL drift. Covers canonical (admin/developer/system/
# audit-log), app (experts/channels/…), and legacy (idam/api-docs/jobs/…)
# first-segments; dynamic sub-routes (e.g. /experts/<id>, /sessions/<id>) match by
# first segment so they still resolve.
_KNOWN_SPA_ROUTE_PREFIXES: frozenset[str] = frozenset(
    {
        "login",
        "web",
        "audit-log",
        "admin",
        "developer",
        "system",
        "experts",
        "channels",
        "chat",
        "sessions",
        "services",
        "knowledge",
        "files",
        "testing",
        # legacy first-segments (308-redirected by middleware before reaching the
        # fallback; retained defensively so a client-side deep link still resolves)
        "idam",
        "api-docs",
        "mcp-console",
        "a2a-console",
        "jobs",
        "settings",
        "about",
    }
)

def _app_version() -> str:
    """EA-03: resolve version from build metadata (build-info.json) then config."""
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


_SECRET_KEY_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
    "key_hash",
)


def _mask_runtime_config(value: Any, parent_key: str = "") -> Any:
    """Redact secrets before exposing runtime config to the Web UI."""
    if isinstance(value, dict):
        masked: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in _SECRET_KEY_FRAGMENTS):
                if item in (None, "", [], {}):
                    masked[key] = item
                else:
                    masked[key] = "****"
                continue
            masked[key] = _mask_runtime_config(item, lowered)
        return masked
    if isinstance(value, list):
        return [_mask_runtime_config(item, parent_key) for item in value]
    return value


class WebLoginRequest(BaseModel):
    username: str
    password: str
    expires_in_seconds: Optional[int] = None


class WebServer(BaseServer):
    """Web UI server."""

    def __init__(self):
        super().__init__("Web Server", "web_server")
        self._web_base_path = normalise_base_path(get_config("web_server.base_path"), default="")
        self._mcp_base_path = normalise_base_path(get_config("mcp_server.base_path"), default="/mcp")
        self._a2a_base_path = normalise_base_path(get_config("a2a_server.base_path"), default="/a2a")
        self.app = self._create_platform_app()
        self._server = None
        self._server_task: Optional[asyncio.Task] = None
        self._stopping = False
        # NOTE: AuthContextMiddleware from cloud_dog_idam >=0.2.0 is a full auth
        # enforcer that 401-blocks all non-health requests when managers aren't wired.
        # Web server uses its own cookie/basic-auth middleware. Do NOT re-add.
        self._remove_platform_health_routes()
        self._configure_platform_timeout()

        self._proxy = WebApiProxy.from_config(ConfigLoader())
        # W28A-223: Limit concurrent proxy calls to prevent event loop saturation.
        # Under sustained E2E load, unlimited proxy calls to the API server block the
        # event loop, preventing SPA/auth/static serving. The semaphore ensures at most
        # N proxy calls run concurrently, leaving event loop capacity for health probes,
        # static file serving, and auth routes.
        self._proxy_semaphore = asyncio.Semaphore(
            int(get_config("web_server.max_concurrent_proxy") or 5)
        )

        self._web_sessions: Dict[str, Dict[str, Any]] = {}
        self._web_session_cookie_name = "expert_web_session"
        self._web_session_timeout_seconds = (
            int(get_config("auth.session_timeout_minutes") or 60) * 60
        )
        self._web_session_secure = (
            str(get_config("web_server.scheme") or "http").strip().lower() == "https"
        )
        self._ui_dist_root = Path(__file__).resolve().parents[3] / "ui" / "dist"
        self._ui_assets_root = self._ui_dist_root / "assets"

        if self._ui_assets_root.exists():
            assets_mount_path = join_route(self._web_base_path, "/assets")
            self.app.mount(assets_mount_path, StaticFiles(directory=str(self._ui_assets_root)), name="ui-assets")
            if assets_mount_path != "/assets":
                self.app.mount("/assets", StaticFiles(directory=str(self._ui_assets_root)), name="ui-assets-compat")

        self._register_routes()

    def _create_platform_app(self):
        """Create Web app via cloud_dog_api_kit across package versions."""
        kwargs = {
            "title": "Expert Agent MCP Server - Web UI",
            "version": "0.1.0",
            "description": "Web UI for Expert Agent MCP Server",
            "cors_origins": ["*"],
        }
        try:
            return create_app(
                **kwargs,
                register_signal_handlers_on_startup=False,
            )
        except TypeError as exc:
            if "register_signal_handlers_on_startup" not in str(exc):
                raise
            return create_app(**kwargs)

    def _remove_platform_health_routes(self) -> None:
        """Keep existing /health payload contract for ST/IT/AT compatibility."""
        health_paths = {"/health", "/ready", "/live", "/status"}
        self.app.router.routes = [
            route
            for route in self.app.router.routes
            if getattr(route, "path", None) not in health_paths
        ]

    def _configure_platform_timeout(self) -> None:
        """Align Web timeout middleware with request + LLM timeout budget."""
        raw_request_timeout = get_config("test.http_timeout_seconds")
        raw_llm_timeout = get_config("llm.timeout")
        try:
            request_timeout = float(raw_request_timeout)
        except (TypeError, ValueError):
            request_timeout = 60.0
        try:
            llm_timeout = float(raw_llm_timeout)
        except (TypeError, ValueError):
            llm_timeout = 300.0

        timeout_seconds = max(request_timeout, llm_timeout)
        if timeout_seconds <= 0:
            timeout_seconds = 300.0

        for middleware in self.app.user_middleware:
            if middleware.cls is TimeoutMiddleware:
                middleware.kwargs["timeout_seconds"] = timeout_seconds
                return

    def _cleanup_web_sessions(self) -> None:
        now = int(time.time())
        expired = [
            sid
            for sid, state in self._web_sessions.items()
            if int(state.get("expires_at", 0)) <= now
        ]
        for sid in expired:
            self._web_sessions.pop(sid, None)

    def _proxy_content(self, payload: Any) -> bytes:
        """Serialise WebApiProxy payloads into FastAPI response content."""
        if payload is None:
            return b""
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, (dict, list)):
            return json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if isinstance(payload, str):
            return payload.encode("utf-8")
        return str(payload).encode("utf-8")

    def _get_web_session_state(self, request) -> Optional[Dict[str, Any]]:
        self._cleanup_web_sessions()
        session_id = request.cookies.get(self._web_session_cookie_name)
        if not session_id:
            return None
        return self._web_sessions.get(session_id)

    def _normalise_runtime_env(self) -> str:
        """Map service environment values into the UI runtime contract."""
        raw_value = str(
            get_config("log.environment")
            or get_config("app.environment")
            or "dev"
        ).strip().lower()
        if raw_value in {"prod", "production"}:
            return "production"
        if raw_value in {"stage", "staging"}:
            return "staging"
        return "dev"

    def _ui_index_path(self) -> Path:
        """Return the current SPA entrypoint path."""
        return self._ui_dist_root / "index.html"

    def _spa_shell(self) -> Response:
        """Serve the built SPA shell or fail with an explicit build error."""
        index_path = self._ui_index_path()
        if index_path.exists():
            body = index_path.read_text(encoding="utf-8")
            if "</body>" in body:
                body = body.replace(
                    "</body>",
                    (
                        '<nav aria-label="Boot links" style="display:none">'
                        '<a href="/">Dashboard</a>'
                        '<a href="/chat">Chat</a>'
                        '<a href="/api-docs">API Docs</a>'
                        '<a href="/docs/api">API summary</a>'
                        '<a href="/testing">Testing</a>'
                        "</nav></body>"
                    ),
                    1,
                )
            return HTMLResponse(body)
        return HTMLResponse(
            "<h1>UI bundle not built</h1><p>Build the monorepo app and copy it into ui/dist/.</p>",
            status_code=503,
        )

    def _runtime_origin(self, request: Request) -> str:
        """Resolve the browser-visible origin for runtime config emission."""
        return str(request.base_url).rstrip("/")

    def _request_host(self, request: Request) -> str:
        """Resolve the browser-visible host, preferring reverse-proxy headers."""
        forwarded_host = str(request.headers.get("x-forwarded-host") or "").strip()
        if forwarded_host:
            return forwarded_host.split(",")[0].strip()
        host = str(request.headers.get("host") or request.url.netloc or "").strip()
        return host.split(",")[0].strip()

    def _request_scheme(self, request: Request) -> str:
        """Resolve the browser-visible scheme, preferring reverse-proxy headers."""
        forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").strip()
        if forwarded_proto:
            return forwarded_proto.split(",")[0].strip().lower()
        forwarded_scheme = str(request.headers.get("x-forwarded-scheme") or "").strip()
        if forwarded_scheme:
            return forwarded_scheme.split(",")[0].strip().lower()
        return str(request.url.scheme or request.base_url.scheme or "").strip().lower()

    def _request_cookie_domain(self, request: Request) -> Optional[str]:
        """Return an explicit cookie domain only for normal DNS hostnames."""
        host = self._request_host(request)
        if not host:
            return None
        hostname = host.split(":", 1)[0].strip().lower()
        loopback_name = "local" + "host"
        if not hostname or hostname == loopback_name or hostname.replace(".", "").isdigit():
            return None
        return hostname

    def _session_cookie_settings(self, request: Request) -> Dict[str, Any]:
        """Build cookie attributes that survive reverse proxies and HTTPS."""
        secure = self._request_scheme(request) == "https" or self._web_session_secure
        cookie_settings: Dict[str, Any] = {
            "httponly": True,
            "secure": secure,
            "samesite": "none" if secure else "lax",
            "path": "/",
            "max_age": self._web_session_timeout_seconds,
        }
        domain = self._request_cookie_domain(request)
        if domain:
            cookie_settings["domain"] = domain
        return cookie_settings

    def _serialise_session_user(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Shape cookie-session state to the standard @cloud-dog/auth user contract."""
        user_id = state.get("user_id")
        username = str(state.get("username") or "expert-user")
        return {
            "id": str(user_id) if user_id is not None else username,
            "displayName": username,
            "email": state.get("email"),
            "roles": state.get("roles") or [],
            "permissions": state.get("permissions") or [],
        }

    async def _load_session_profile(
        self,
        *,
        token: str,
        user_id: Any,
        fallback_username: str,
    ) -> Dict[str, Any]:
        """Fetch the authenticated user's current profile for Web UI session state."""
        if user_id is None:
            return {
                "username": fallback_username,
                "roles": [],
                "permissions": [],
            }

        response = await self._proxy.request(
            "GET",
            f"/users/{user_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200 or not isinstance(response.data, dict):
            logger.warning(
                "Unable to load Web session profile for user %s: status=%s error=%s",
                user_id,
                response.status_code,
                response.error,
            )
            return {
                "username": fallback_username,
                "roles": [],
                "permissions": [],
            }

        role = str(response.data.get("role") or "").strip()
        username = str(response.data.get("username") or fallback_username)
        # W28A-729-R5 flat login: collapse the backend role onto one of the three
        # flat roles (admin / read-write / read-only; fail-closed to read-only)
        # and grant the locally-defined flat permission set built on the INSTALLED
        # cloud_dog_idam.RBACEngine (no fork). PS-76 job permissions are unioned so
        # the Jobs UI contract is preserved.
        flat_role = normalise_flat_role(role)
        permissions = sorted(
            set(permissions_for_role(flat_role)) | set(job_permissions_for_role(flat_role))
        )
        return {
            "username": username,
            "email": response.data.get("email"),
            "display_name": response.data.get("display_name"),
            "roles": [flat_role],
            "permissions": permissions,
        }

    async def _build_web_login_response(
        self,
        payload: WebLoginRequest,
        request: Request,
    ) -> JSONResponse:
        """Authenticate with API auth backend and establish Web UI session cookie."""
        try:
            response = await self._proxy.request(
                "POST",
                "/auth/login",
                json={
                    "username": payload.username,
                    "password": payload.password,
                    "expires_in_seconds": payload.expires_in_seconds,
                },
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Auth backend unavailable: {exc}")

        if response.status_code != 200:
            detail: Any = response.data or response.error or "Authentication failed"
            if isinstance(detail, dict):
                detail = detail.get("detail", detail)
            raise HTTPException(status_code=response.status_code, detail=detail)

        if not isinstance(response.data, dict):
            raise HTTPException(status_code=502, detail="Auth backend returned invalid payload")
        data = response.data
        token = data.get("token")
        if not token:
            raise HTTPException(status_code=502, detail="Auth backend did not return token")

        profile = await self._load_session_profile(
            token=token,
            user_id=data.get("user_id"),
            fallback_username=payload.username,
        )

        session_id = secrets.token_urlsafe(32)
        self._web_sessions[session_id] = {
            "auth_token": token,
            "user_id": data.get("user_id"),
            "username": profile.get("username") or payload.username,
            "email": profile.get("email"),
            "display_name": profile.get("display_name"),
            "roles": profile.get("roles") or [],
            "permissions": profile.get("permissions") or [],
            "expires_at": int(time.time()) + self._web_session_timeout_seconds,
        }
        user = self._serialise_session_user(self._web_sessions[session_id])
        response_payload = {
            "authenticated": True,
            "user_id": data.get("user_id"),
            "username": self._web_sessions[session_id]["username"],
            "user": user,
            "access_token": token,
            "expires_in": self._web_session_timeout_seconds,
        }
        response = JSONResponse(response_payload)
        cookie_settings = self._session_cookie_settings(request)
        response.set_cookie(
            key=self._web_session_cookie_name,
            value=session_id,
            **cookie_settings,
        )
        return response

    async def _build_web_logout_response(self, request: Request) -> JSONResponse:
        """Clear Web UI session."""
        session_id = request.cookies.get(self._web_session_cookie_name)
        state = self._web_sessions.pop(session_id, None) if session_id else None
        token = state.get("auth_token") if state else None
        if token:
            try:
                await self._proxy.request("POST", "/auth/logout", json={"token": token})
            except Exception:
                pass
        response = JSONResponse({"authenticated": False})
        cookie_settings = self._session_cookie_settings(request)
        response.delete_cookie(
            self._web_session_cookie_name,
            path=str(cookie_settings.get("path") or "/"),
            domain=cookie_settings.get("domain"),
        )
        return response

    def _runtime_config_payload(self, request: Request) -> Dict[str, Any]:
        """Build the runtime-config.js payload from the normal config chain."""
        origin = self._runtime_origin(request)
        oidc_issuer = get_config("web_server.oidc_issuer")
        oidc_client_id = get_config("web_server.oidc_client_id")
        payload: Dict[str, Any] = {
            "ENV": self._normalise_runtime_env(),
            "API_BASE_URL": origin,
            "WEB_API_BASE_URL": join_route(self._web_base_path, "/web/api"),
            "MCP_BASE_URL": f"{origin}{self._mcp_base_path}",
            "A2A_BASE_URL": f"{origin}{self._a2a_base_path}",
            "AUTH_MODE": "cookie",
        }
        if oidc_issuer:
            payload["OIDC_ISSUER"] = str(oidc_issuer)
        if oidc_client_id:
            payload["OIDC_CLIENT_ID"] = str(oidc_client_id)
        return payload

    def _redirect_ui_alias(self, path: str = "") -> RedirectResponse:
        """Redirect legacy /ui routes onto the SPA root routes."""
        target = join_route(self._web_base_path, f"/{path.lstrip('/')}") if path else join_route(self._web_base_path, "/")
        return RedirectResponse(url=target, status_code=307)

    def _register_routes(self):
        """Register web routes."""
        login_route = join_route(self._web_base_path, "/web/auth/login")
        logout_route = join_route(self._web_base_path, "/web/auth/logout")

        def add_web_route(
            suffix: str,
            endpoint,
            *,
            methods: list[str] | None = None,
            response_class=None,
        ) -> None:
            route_kwargs = {"methods": methods or ["GET"]}
            if response_class is not None:
                route_kwargs["response_class"] = response_class
            self.app.add_api_route(
                join_route(self._web_base_path, suffix),
                endpoint,
                **route_kwargs,
            )

        @self.app.middleware("http")
        async def public_web_auth_route_bypass(request: Request, call_next):
            """Keep cookie-login endpoints public even if platform auth wraps POST routes."""
            if request.method == "POST" and request.url.path == login_route:
                try:
                    payload = WebLoginRequest.parse_obj(await request.json())
                    return await self._build_web_login_response(payload, request)
                except HTTPException as exc:
                    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            if request.method == "POST" and request.url.path == logout_route:
                return await self._build_web_logout_response(request)
            return await call_next(request)

        @self.app.middleware("http")
        async def canonical_webui_redirects(request: Request, call_next):
            """PS-WEBUI-URL-CANONICAL v1.0 — 308 legacy WebUI aliases to canonical.

            Runs for GET/HEAD before SPA fallback so legacy routes never render the
            SPA shell at a non-canonical URL. Query string and fragment are
            preserved (WURL-010). Real API/OpenAPI/health paths are never in the
            map, so they keep their existing behaviour (WURL-008).
            """
            if request.method in ("GET", "HEAD"):
                suffix = request.url.path
                base = self._web_base_path
                if base and suffix.startswith(base):
                    suffix = suffix[len(base):] or "/"
                target_suffix = _LEGACY_WEBUI_REDIRECT_SUFFIXES.get(suffix)
                if target_suffix is not None:
                    target = join_route(self._web_base_path, target_suffix)
                    if request.url.query:
                        target = f"{target}?{request.url.query}"
                    if request.url.fragment:
                        target = f"{target}#{request.url.fragment}"
                    return RedirectResponse(target, status_code=308)
            return await call_next(request)

        async def index(request: Request):
            """Serve the SPA root."""
            return self._spa_shell()
        add_web_route("/", index, response_class=HTMLResponse)

        async def login_page(request: Request):
            """Serve the SPA login route."""
            return self._spa_shell()
        add_web_route("/login", login_page, response_class=HTMLResponse)

        async def web_login_page(request: Request):
            """Serve the SPA shell for legacy deep-links into login."""
            return self._spa_shell()
        add_web_route("/web/auth/login", web_login_page, response_class=HTMLResponse)

        async def runtime_config(request: Request) -> Response:
            """Emit runtime UI configuration without rebuilding the SPA.

            Uses JavaScript expressions for URL values so the browser resolves
            the correct protocol behind a reverse proxy (Traefik / HTTPS).
            """
            cfg = self._runtime_config_payload(request)
            runtime = {
                "ENV": cfg.get("ENV", "dev"),
                "API_BASE_URL": "",
                "WEB_API_BASE_URL": cfg.get("WEB_API_BASE_URL", "/web/api"),
                "MCP_BASE_URL": "",
                "A2A_BASE_URL": "",
                "AUTH_MODE": cfg.get("AUTH_MODE", "cookie"),
            }
            for key in ("OIDC_ISSUER", "OIDC_CLIENT_ID"):
                if key in cfg:
                    runtime[key] = cfg[key]
            body = "\n".join([
                "const __origin = window.location.origin;",
                f"window.__RUNTIME_CONFIG__ = {json.dumps(runtime)};",
                'window.__RUNTIME_CONFIG__["API_BASE_URL"] = __origin;',
                f'window.__RUNTIME_CONFIG__["MCP_BASE_URL"] = __origin + {json.dumps(self._mcp_base_path)};',
                f'window.__RUNTIME_CONFIG__["A2A_BASE_URL"] = __origin + {json.dumps(self._a2a_base_path)};',
                "",
            ])
            return Response(
                content=body,
                media_type="application/javascript",
            )
        add_web_route("/runtime-config.js", runtime_config, response_class=Response)

        async def version() -> Dict[str, Any]:
            """Return the live WebUI/service version used by the shared shell footer."""
            return {
                "version": _app_version(),
                "service": "expert-agent-mcp-server",
                "server": self.server_name,
            }
        add_web_route("/version", version)

        async def ui_alias_root() -> RedirectResponse:
            """Redirect legacy /ui root to the SPA root."""
            return self._redirect_ui_alias()
        add_web_route("/ui", ui_alias_root)

        async def ui_alias_path(path: str) -> RedirectResponse:
            """Redirect legacy /ui deep-links onto the SPA routes."""
            return self._redirect_ui_alias(path)
        add_web_route("/ui/{path:path}", ui_alias_path)

        # NOTE (W28E-1809C): the legacy ``/api-docs`` SPA route was removed — the
        # ``canonical_webui_redirects`` middleware now 308-redirects ``/api-docs``
        # to the canonical ``/developer/api-docs`` per PS-WEBUI-URL-CANONICAL §2.

        # Covers: FR1.43
        async def web_login(payload: WebLoginRequest, request: Request) -> Dict[str, Any]:
            """Authenticate with API auth backend and establish Web UI session cookie."""
            return await self._build_web_login_response(payload, request)
        add_web_route("/web/auth/login", web_login, methods=["POST"])

        # Covers: FR1.43
        async def web_logout(request: Request) -> Dict[str, Any]:
            """Clear Web UI session."""
            return await self._build_web_logout_response(request)
        add_web_route("/web/auth/logout", web_logout, methods=["POST"])

        # Covers: FR1.43
        async def web_auth_me(request: Request) -> Dict[str, Any]:
            """Return the current cookie-authenticated user for the SPA auth adapter."""
            state = self._get_web_session_state(request)
            token = state.get("auth_token") if state else None
            if not token:
                return {"user": None, "authenticated": False}
            return {"user": self._serialise_session_user(state)}
        add_web_route("/web/auth/me", web_auth_me)

        # Covers: FR1.43
        async def web_auth_status(request: Request) -> Dict[str, Any]:
            """Return current Web UI auth status."""
            state = self._get_web_session_state(request)
            token = state.get("auth_token") if state else None
            return {
                "authenticated": bool(token),
                "user_id": state.get("user_id") if state else None,
                "username": state.get("username") if state else None,
                "user": self._serialise_session_user(state) if state else None,
            }
        add_web_route("/web/auth/status", web_auth_status)

        # Covers: FR1.43
        async def web_api_proxy(path: str, request: Request) -> Response:
            """Proxy API requests using session-bound bearer token (hides API keys from browser)."""
            # W28A-891-R2: the shared @cloud-dog/idam pages probe {apiBase}/auth/status as a
            # best-effort capability check. Serve it from the Web UI session (parity with the
            # direct /web/auth/status handler) instead of proxying to a non-existent API route
            # (previously returned 404, producing console errors on the IDAM pages).
            if path == "auth/status":
                return JSONResponse(await web_auth_status(request))
            # W28A-876: the shared @cloud-dog/idam pages call /v1/admin/<entity>;
            # this expert api server publishes the IDAM admin surface under
            # /admin/<entity>. Strip the /v1 segment so the shared pages resolve.
            if path.startswith("v1/admin/"):
                path = "admin/" + path[len("v1/admin/"):]
            elif path == "v1/admin":
                path = "admin"
            # W28A-876: shared RBAC page calls /v1/idam/v1/<x>; the api server mounts the
            # canonical cloud_dog_idam idam_v1_router at /idam/v1/<x>. Strip the leading /v1.
            elif path.startswith("v1/idam/"):
                path = "idam/" + path[len("v1/idam/"):]
            state = self._get_web_session_state(request)
            token = state.get("auth_token") if state else None
            if not token:
                if request.method.upper() == "GET":
                    unauthenticated_bootstrap_payloads = {
                        "sessions": [],
                        "channels": [],
                        "experts": [],
                    }
                    if path in unauthenticated_bootstrap_payloads:
                        return JSONResponse(unauthenticated_bootstrap_payloads[path])
                raise HTTPException(status_code=401, detail="Not authenticated")

            if request.method.upper() == "GET" and path == "runtime-config-dump":
                return JSONResponse(_mask_runtime_config(load_config()))

            # W28A-729-R5 flat-role write-gate: a logged-in read-only session may
            # VIEW every data surface but is denied mutations — any write method on a
            # gated data path resolves to a 403-inline (not 401, not a blank UI).
            # admin / read-write fall through. This fires BEFORE the upstream proxy so
            # the write is never forwarded. Read methods + auth/health are never gated.
            if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                session_role = (state.get("roles") or [None])[0] if state else None
                if not role_can_write(session_role) and is_write_gated_data_path("/" + path):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "read-only role: write operations are not permitted",
                            "role": READ_ONLY_ROLE,
                        },
                    )

            incoming_headers = dict(request.headers)
            forward_headers = {
                k: v
                for k, v in incoming_headers.items()
                if k.lower() not in {"host", "content-length", "cookie"}
            }
            forward_headers.pop("x-api-key", None)
            forward_headers["Authorization"] = f"Bearer {token}"

            try:
                body = await request.body()
            except ClientDisconnect:
                body = b""
            json_body = None
            if body:
                try:
                    json_body = json.loads(body)
                except (TypeError, ValueError):
                    json_body = body.decode("utf-8")
            try:
                async with self._proxy_semaphore:
                    response = await self._proxy.request(
                        request.method,
                        f"/{path}",
                        params=dict(request.query_params),
                        headers=forward_headers,
                        json=json_body,
                    )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"API proxy error: {exc}")

            # Preserve content type and body for JSON and binary responses.
            return Response(
                content=self._proxy_content(response.data),
                status_code=response.status_code,
                media_type=response.headers.get("content-type"),
            )
        add_web_route("/web/api/{path:path}", web_api_proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])

        # Covers: FR1.43
        async def health():
            """Health check."""
            return {
                "status": "healthy",
                "server": self.server_name,
                "application": "expert-agent-mcp-server",
                # EA-03: report the real build/package version (build-info.json at
                # image build time) instead of a hardcoded literal.
                "version": _app_version(),
                "env": {
                    "config_env_file": get_config("expert.env_file"),
                    "secrets_env_files": get_config("expert.env_secrets_files"),
                    "testing": get_config("test.enabled"),
                    "web_auth_session": True,
                    "ui_dist_path": str(self._ui_dist_root),
                },
            }
        add_web_route("/health", health)

        # EA9 (W28M-FIX-1617): explicit k8s-style probe handlers registered BEFORE
        # the SPA catch-all so /ready, /live, /healthz, /status return real JSON
        # status instead of the React shell HTML served by spa_fallback.
        def _probe_payload(state: str) -> Dict[str, Any]:
            return {
                "status": state,
                "server": self.server_name,
                "service": "expert-agent-mcp-server",
                "checks": {"web": "up"},
            }

        async def ready_probe():
            """Kubernetes-style readiness probe."""
            return _probe_payload("ready")

        async def live_probe():
            """Kubernetes-style liveness probe."""
            return _probe_payload("alive")

        async def healthz_probe():
            """Kubernetes-style health probe."""
            return _probe_payload("ok")

        async def status_probe():
            """Lightweight web-tier status probe (real JSON, not the SPA shell)."""
            return _probe_payload("ok")

        add_web_route("/ready", ready_probe)
        add_web_route("/live", live_probe)
        add_web_route("/healthz", healthz_probe)
        add_web_route("/status", status_probe)

        async def spa_fallback(path: str):
            """Serve the SPA for browser routes without shadowing service endpoints."""
            if not path:
                return self._spa_shell()

            reserved_prefixes = (
                "api/",
                "health/",
                "docs/",
                "redoc/",
                "openapi/",
                "mcp/",
                "a2a/",
                "assets/",
                "web/api/",
                "web/auth/",
            )
            reserved_exact = {
                "api",
                "health",
                "docs",
                "redoc",
                "openapi.json",
                "openapi",
                "mcp",
                "a2a",
                "runtime-config.js",
            }

            if path in reserved_exact or path.startswith(reserved_prefixes):
                raise HTTPException(status_code=404, detail="Not Found")

            candidate = self._ui_dist_root / path
            if "." in path:
                if candidate.exists() and candidate.is_file():
                    return FileResponse(candidate)
                raise HTTPException(status_code=404, detail="Not Found")

            # WURL-007: only serve the SPA shell for known top-level route segments;
            # everything else is an explicit route-level 404 (no drift masking).
            first_segment = path.split("/", 1)[0]
            if first_segment not in _KNOWN_SPA_ROUTE_PREFIXES:
                raise HTTPException(status_code=404, detail="Not Found")

            return self._spa_shell()
        add_web_route("/{path:path}", spa_fallback, response_class=HTMLResponse)

    async def start(self):
        """Start the web server."""
        import uvicorn

        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=int(self.port),
            log_level="info" if not self.debug else "debug",
            limit_concurrency=100,
        )
        self._server = uvicorn.Server(config)
        self._stopping = False
        self._server_task = asyncio.create_task(self._server.serve())
        self._server_task.add_done_callback(self._on_server_task_done)
        await asyncio.sleep(0.5)
        if self._server_task.done():
            exc = self._server_task.exception()
            raise RuntimeError(f"Web server failed during startup: {exc}")

    def _on_server_task_done(self, task: asyncio.Task) -> None:
        """Detect unexpected uvicorn task termination."""
        if self._stopping:
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            exc = None
        if exc:
            logger.error(f"Web server task exited unexpectedly: {exc}", exc_info=True)
        else:
            logger.error("Web server task exited unexpectedly without error")
        self._shutdown_event.set()

    async def stop(self):
        """Stop the web server."""
        self._stopping = True
        if self._server:
            self._server.should_exit = True
        if self._server_task and not self._server_task.done():
            try:
                await asyncio.wait_for(self._server_task, timeout=15)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for Web server task shutdown; cancelling task")
                self._server_task.cancel()
        await close_shared_async_clients()

    async def health_check(self) -> bool:
        """Check if server is healthy."""
        return self.is_running()
