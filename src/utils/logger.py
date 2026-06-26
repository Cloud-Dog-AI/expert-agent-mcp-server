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
Logging Infrastructure

License: Apache 2.0
Ownership: Cloud Dog
Description: Structured logging with PII redaction support

Related Requirements: FR1.9, CS1.4
Related Tasks: T111
Related Architecture: MO1.1
Related Tests: ST1.17

Recent Changes:
- Initial implementation
"""

import re
import socket
from typing import Any, Optional

from cloud_dog_logging import (
    get_logger as platform_get_logger,
    setup_logging as platform_setup_logging,
)
from cloud_dog_logging.correlation import set_environment

from src.config.loader import load_config


# Covers: NF1.4
class PIIRedactor:
    """PII redaction patterns."""

    # Common PII patterns
    PATTERNS = [
        # Email addresses
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED_EMAIL]"),
        # Phone numbers
        (r"\b\d{3}[\s.-]?\d{3}[\s.-]?\d{4}\b", "[REDACTED_PHONE]"),
        # Social Security Numbers
        (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
        # Credit card numbers
        (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[REDACTED_CC]"),
        # IP addresses (optional - may want to keep for debugging)
        # (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[REDACTED_IP]'),
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        """Redact PII from text."""
        if not text:
            return text

        result = str(text)
        for pattern, replacement in cls.PATTERNS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result


_SERVER_ID = ""
_SERVER_LOG_KEYS = {
    "api": "api_server_log",
    "api_server": "api_server_log",
    "web": "web_server_log",
    "web_server": "web_server_log",
    "mcp": "mcp_server_log",
    "mcp_server": "mcp_server_log",
    "a2a": "a2a_server_log",
    "a2a_server": "a2a_server_log",
}


class LoggerAdapter:
    """Compatibility wrapper around ``cloud_dog_logging`` application loggers."""

    def __init__(self, name: str, *, pii_redaction: bool = True) -> None:
        self._platform_logger = platform_get_logger(name, pii_redaction=False)
        self._underlying_logger = self._platform_logger.underlying_logger
        self._pii_redaction = pii_redaction

    def _redact_message(self, message: Any) -> Any:
        if not self._pii_redaction:
            return message
        return PIIRedactor.redact(str(message))

    def _redact_args(self, args: tuple[Any, ...]) -> tuple[Any, ...]:
        if not self._pii_redaction:
            return args
        return tuple(PIIRedactor.redact(str(arg)) for arg in args)

    def _redact_extra(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        updated = dict(kwargs)
        extra: dict[str, Any] = {}
        raw_extra = kwargs.get("extra")
        if isinstance(raw_extra, dict):
            extra.update(raw_extra)
        extra.setdefault("server_id", get_server_id())

        if self._pii_redaction:
            extra = {key: PIIRedactor.redact(str(value)) for key, value in extra.items()}

        updated["extra"] = extra
        return updated

    def debug(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._underlying_logger.debug(
            self._redact_message(msg),
            *self._redact_args(args),
            **self._redact_extra(kwargs),
        )

    def info(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._underlying_logger.info(
            self._redact_message(msg),
            *self._redact_args(args),
            **self._redact_extra(kwargs),
        )

    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._underlying_logger.warning(
            self._redact_message(msg),
            *self._redact_args(args),
            **self._redact_extra(kwargs),
        )

    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._underlying_logger.error(
            self._redact_message(msg),
            *self._redact_args(args),
            **self._redact_extra(kwargs),
        )

    def critical(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._underlying_logger.critical(
            self._redact_message(msg),
            *self._redact_args(args),
            **self._redact_extra(kwargs),
        )

    def exception(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("exc_info", True)
        self.error(msg, *args, **kwargs)

    @property
    def level(self) -> int:
        """Return the effective log level."""
        return self._underlying_logger.getEffectiveLevel()

    @property
    def name(self) -> str:
        """Return the logger name."""
        return self._underlying_logger.name

    @property
    def underlying_logger(self) -> Any:
        """Expose the underlying stdlib logger for code that needs it."""
        return self._underlying_logger

    def addHandler(self, handler: Any) -> None:
        """Delegate addHandler to the underlying stdlib logger."""
        self._underlying_logger.addHandler(handler)

    def setLevel(self, level: Any) -> None:
        """Delegate setLevel to the underlying stdlib logger."""
        self._underlying_logger.setLevel(level)


def get_server_id() -> str:
    """Return the configured server identifier."""
    global _SERVER_ID
    if not _SERVER_ID:
        _SERVER_ID = socket.gethostname() or "expert-agent-local"
    return _SERVER_ID


def _resolve_surface_log(config: dict[str, Any], server_name: Optional[str]) -> Optional[str]:
    """Resolve the PS-40 application log path for a specific server surface."""
    log_config = config.get("log")
    if not isinstance(log_config, dict):
        return None

    surface_key = _SERVER_LOG_KEYS.get(str(server_name or "").strip().lower())
    if surface_key:
        surface_log = log_config.get(surface_key)
        if surface_log:
            return str(surface_log)

    app_log = log_config.get("app_log")
    if app_log:
        return str(app_log)
    return None


def _build_platform_config(
    *,
    config: dict[str, Any],
    level: str,
    format_type: str,
    pii_redaction: bool,
    log_file: Optional[str],
) -> dict[str, Any]:
    """Build the effective ``cloud_dog_logging`` config for this process."""
    log_config = config.get("log")
    if not isinstance(log_config, dict):
        log_config = {}

    app_config = config.get("app")
    if not isinstance(app_config, dict):
        app_config = {}

    effective_log = dict(log_config)
    effective_log["level"] = str(level or effective_log.get("level") or "INFO").upper()
    effective_log["format"] = "json" if str(format_type or effective_log.get("format") or "json").lower() == "json" else "text"
    effective_log["pii_redaction"] = bool(pii_redaction)
    effective_log["service_instance"] = str(get_server_id() or log_config.get("service_instance") or "expert-agent-local")
    effective_log["environment"] = str(
        log_config.get("environment") or config.get("environment") or app_config.get("environment") or "dev"
    )
    effective_log["audit_log"] = str(log_config.get("audit_log") or "logs/audit.log.jsonl")
    if log_file:
        effective_log["app_log"] = str(log_file)
    else:
        effective_log.pop("app_log", None)

    return {
        "service_name": str(config.get("service_name") or app_config.get("name") or "expert-agent-mcp-server"),
        "service_instance": effective_log["service_instance"],
        "environment": effective_log["environment"],
        "log": effective_log,
    }


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    pii_redaction: bool = True,
    log_file: Optional[str] = None,
    server_name: Optional[str] = None,
) -> LoggerAdapter:
    """
    Set up structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Format type ('json' or 'text')
        pii_redaction: Enable PII redaction
        log_file: Optional log file path

    Returns:
        Configured logger
    """
    config = load_config()
    resolved_log_file = str(log_file) if log_file else _resolve_surface_log(config, server_name)
    platform_config = _build_platform_config(
        config=config,
        level=level,
        format_type=format_type,
        pii_redaction=pii_redaction,
        log_file=resolved_log_file,
    )

    platform_setup_logging(platform_config)
    set_environment(str(platform_config.get("environment") or "dev"))
    return get_logger("expert_agent", pii_redaction=pii_redaction)


def get_logger(name: str, pii_redaction: bool = True) -> LoggerAdapter:
    """
    Get a logger instance.

    Args:
        name: Logger name
        pii_redaction: Enable PII redaction for this logger

    Returns:
        Logger instance
    """
    return LoggerAdapter(name, pii_redaction=pii_redaction)
