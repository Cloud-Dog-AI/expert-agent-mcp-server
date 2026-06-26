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
Unit Test: UT1.30 - PII Redaction in Logs and Stored Data

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for PII redaction in logs and stored data

Related Requirements: CS1.4
Related Tasks: T111
Related Architecture: MO1.1
Related Tests: UT1.30

Recent Changes:
- Initial implementation
"""

import logging
import pytest
from src.utils.logger import PIIRedactor, get_logger
from src.config.loader import get_config


def _require_pii_config():
    email = get_config("test.user.email")
    phone = get_config("test.pii.phone")
    ssn = get_config("test.pii.ssn")
    credit_card = get_config("test.pii.credit_card")
    if not email or not phone or not ssn or not credit_card:
        pytest.fail(
            "Missing test.user.email/test.pii.phone/test.pii.ssn/test.pii.credit_card in config"
        )
    if "@" not in email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    return email, phone, ssn, credit_card
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-003")


def test_pii_redactor_email():
    """Test PII redaction for email addresses."""
    email, _, _, _ = _require_pii_config()
    text = f"Contact me at {email} for more information"
    redacted = PIIRedactor.redact(text)

    assert "[REDACTED_EMAIL]" in redacted
    assert email not in redacted
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-003")


def test_pii_redactor_phone():
    """Test PII redaction for phone numbers."""
    _, phone, _, _ = _require_pii_config()
    if "-" not in phone:
        pytest.fail("test.pii.phone must include '-' to build alternate format")
    phone_alt = phone.replace("-", ".")
    text = f"Call me at {phone} or {phone_alt}"
    redacted = PIIRedactor.redact(text)

    assert "[REDACTED_PHONE]" in redacted
    assert phone not in redacted
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-003")


def test_pii_redactor_ssn():
    """Test PII redaction for SSN."""
    _, _, ssn, _ = _require_pii_config()
    text = f"My SSN is {ssn}"
    redacted = PIIRedactor.redact(text)

    assert "[REDACTED_SSN]" in redacted
    assert ssn not in redacted
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-003")


def test_pii_redactor_credit_card():
    """Test PII redaction for credit card numbers."""
    _, _, _, credit_card = _require_pii_config()
    text = f"Card number: {credit_card}"
    redacted = PIIRedactor.redact(text)

    assert "[REDACTED_CC]" in redacted
    assert credit_card not in redacted
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-003")


def test_pii_redactor_multiple_pii():
    """Test PII redaction with multiple PII types."""
    email, phone, ssn, _ = _require_pii_config()
    text = f"Contact {email} or call {phone}. SSN: {ssn}"
    redacted = PIIRedactor.redact(text)

    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_SSN]" in redacted
    assert email not in redacted
    assert phone not in redacted
    assert ssn not in redacted
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-003")


def test_pii_redactor_no_pii():
    """Test PII redaction with no PII present."""
    text = "This is a normal text without any PII"
    redacted = PIIRedactor.redact(text)

    assert redacted == text  # Should remain unchanged
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-003")


def test_pii_redactor_empty_string():
    """Test PII redaction with empty string."""
    text = ""
    redacted = PIIRedactor.redact(text)

    assert redacted == ""
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-003")


def test_pii_redactor_none():
    """Test PII redaction with None."""
    text = None
    redacted = PIIRedactor.redact(text)

    # PIIRedactor.redact returns None for None input (as per implementation)
    assert redacted is None or redacted == ""
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-003")


def test_logger_pii_redaction():
    """Test that logger redacts PII from log messages."""
    logger = get_logger("test_pii_logger", pii_redaction=True)

    # Capture log output
    import io

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Log message with PII
    email, _, _, _ = _require_pii_config()
    logger.info("User email is %s", email)

    log_output = log_capture.getvalue()

    # Check that PII is redacted in log output
    assert "[REDACTED_EMAIL]" in log_output or email not in log_output
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-003")


def test_pii_redactor_case_insensitive():
    """Test that PII redaction is case insensitive."""
    email, _, _, _ = _require_pii_config()
    text = f"Email: {email.upper()}"
    redacted = PIIRedactor.redact(text)

    assert "[REDACTED_EMAIL]" in redacted
    assert "JOHN.DOE@EXAMPLE.COM" not in redacted

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.smtp, pytest.mark.fast]

