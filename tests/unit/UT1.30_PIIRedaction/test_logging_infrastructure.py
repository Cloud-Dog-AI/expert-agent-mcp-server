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
Logging Infrastructure Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for logging system

Related Requirements: FR1.9, CS1.4
Related Tasks: T111
Related Architecture: MO1.1
Related Tests: ST1.17

Recent Changes:
- Initial implementation
"""

import json
import pytest
from src.utils.logger import setup_logging, get_logger, PIIRedactor
from src.core.auth.audit import log_authentication_event
from src.config.loader import get_config


def _require_pii_config():
    email = get_config("test.user.email")
    phone = get_config("test.pii.phone")
    ssn = get_config("test.pii.ssn")
    if not email or not phone or not ssn:
        pytest.fail("Missing test.user.email/test.pii.phone/test.pii.ssn in config")
    if "@" not in email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    return email, phone, ssn
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_pii_redactor_email():
    """Test PII redaction for email addresses."""
    email, _, _ = _require_pii_config()
    text = f"Contact {email} for details"
    redacted = PIIRedactor.redact(text)
    assert "[REDACTED_EMAIL]" in redacted
    assert email not in redacted
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_pii_redactor_phone():
    """Test PII redaction for phone numbers."""
    _, phone, _ = _require_pii_config()
    text = f"Call {phone} for support"
    redacted = PIIRedactor.redact(text)
    assert "[REDACTED_PHONE]" in redacted
    assert phone not in redacted
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_pii_redactor_ssn():
    """Test PII redaction for SSN."""
    _, _, ssn = _require_pii_config()
    text = f"SSN: {ssn}"
    redacted = PIIRedactor.redact(text)
    assert "[REDACTED_SSN]" in redacted
    assert ssn not in redacted
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_setup_logging():
    """Test logging setup."""
    logger = setup_logging(level="DEBUG", format_type="text", pii_redaction=False)
    assert logger is not None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_get_logger():
    """Test getting a logger instance."""
    logger = get_logger("test_module", pii_redaction=True)
    assert logger is not None
    assert logger.name == "test_module"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_setup_logging_includes_server_id_and_audit_file(monkeypatch, tmp_path):
    """Logging setup writes server_id into app logs and keeps a separate audit log file."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("src.utils.logger._SERVER_ID", "expert-agent-test-node")

    app_log = tmp_path / "app.log.jsonl"
    logger = setup_logging(level="INFO", format_type="json", pii_redaction=True, log_file=app_log)
    logger.info("server_id_check")
    for handler in __import__("logging").getLogger().handlers:
        handler.flush()

    app_payload = json.loads(app_log.read_text().splitlines()[-1])
    assert app_payload["extra"]["server_id"] == "expert-agent-test-node"

    log_authentication_event("audit_user", "success", reason="unit_test")
    audit_log = tmp_path / "logs" / "audit.log.jsonl"
    assert audit_log.exists()
    audit_payload = json.loads(audit_log.read_text().splitlines()[-1])
    assert audit_payload["service_instance"] == "expert-agent-test-node"
    assert audit_payload["details"]["server_id"] == "expert-agent-test-node"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.smtp, pytest.mark.fast]
