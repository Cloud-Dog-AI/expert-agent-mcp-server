#!/usr/bin/env python3
"""
Expert Agent MCP Server - A2A Server
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.servers.a2a.server import A2AServer
from src.utils.logger import setup_logging

# W28A-654: Patch cloud_dog_logging ContextVar defaults at module import time.
# ContextVars are task-scoped in asyncio — set_environment() in one task does NOT
# propagate to AuditMiddleware in another. Patching defaults ensures all tasks inherit.
try:
    import contextvars as _ctxvars, os as _patch_os
    from cloud_dog_logging import correlation as _cmod
    _cmod._environment_var = _ctxvars.ContextVar(
        "environment", default=_patch_os.environ.get("CLOUD_DOG_ENVIRONMENT", "dev"))
    _cmod._service_name_var = _ctxvars.ContextVar(
        "service_name", default="expert-agent-mcp-server")
    _cmod._service_instance_var = _ctxvars.ContextVar(
        "service_instance", default=_patch_os.environ.get("HOSTNAME", "expert-agent-local"))
    del _ctxvars, _patch_os, _cmod
except Exception:
    pass  # cloud_dog_logging not installed or incompatible version


if __name__ == "__main__":
    logger = setup_logging(level="INFO", format_type="json", pii_redaction=True, server_name="a2a")
    server = A2AServer()
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)
