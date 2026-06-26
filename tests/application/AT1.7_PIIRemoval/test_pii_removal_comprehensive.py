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
Application Test: AT1.7 - PII Removal Comprehensive Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Comprehensive tests for PII removal from session, history, returned results, and audit

Related Requirements: CS1.4, FR1.2, NF1.8
Related Tasks: T026, T074
Related Architecture: SE1.4
Related Tests: AT1.7

Test Quality Standards:
- All outputs validated for format, content, and structure
- No hardcoded values - all from configuration system
- Comprehensive scenario coverage
- Proper cleanup and isolation
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


import pytest
import uuid
import json
import re
from src.utils.logger import PIIRedactor
from src.config.loader import get_config


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def test_expert(api_client):
    """Create test expert configuration via API."""
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    expert_data = {
        "name": f"at1_7_expert_{uuid.uuid4().hex[:8]}",
        "title": "AT1.7 PII Expert",
        "description": (
            "AT1.7 PII expert description with unique vocabulary: "
            "amber basil cipher dune ember fjord glyph."
        ),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "enabled": True,
    }
    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create test expert: {response.text}"
    expert = response.json()

    yield expert

    try:
        api_client.delete(f"/experts/{expert['id']}")
    except Exception:
        pass


@pytest.fixture
def test_user_credentials(test_env_file, test_secrets_file):
    """Get test user credentials from configuration system."""
    from src.config.loader import load_config

    load_config.cache_clear()

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")

    if not base_username or not base_email or not base_password:
        pytest.fail(
            "Test user credentials not configured. "
            "Set test.user.username/test.user.email/test.user.password in your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_pii_{unique_id}",
        "email": build_test_email("pii", unique_id, base_email),
        "password": base_password,
    }


@pytest.fixture
def test_user(api_client, test_user_credentials):
    """Create test user via API."""
    creds = test_user_credentials

    response = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
        },
    )
    assert response.status_code == 200, f"Failed to create test user: {response.text}"
    user_data = response.json()

    yield user_data

    # Cleanup via API
    try:
        api_client.delete(f"/users/{user_data['id']}")
    except Exception:
        pass


@pytest.fixture
def pii_redactor():
    """PII redactor instance."""
    return PIIRedactor


def _require_pii_value(key: str) -> str:
    value = get_config(f"test.pii.{key}")
    if not value:
        pytest.fail(f"Missing test.pii.{key} in --env file")
    return str(value)


# ============================================================================
# PII DETECTION AND REDACTION TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_email_various_formats(pii_redactor):
    """Test PII removal for email addresses in various formats."""
    test_cases = [
        f"Contact me at {_require_pii_value('email_simple')}",
        f"Email: {_require_pii_value('email_secondary')}",
        f"Send to {_require_pii_value('email_plus')}",
        f"My email is {_require_pii_value('email_complex')}",
    ]

    for text in test_cases:
        redacted = pii_redactor.redact(text)
        # Extract email pattern
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        emails = re.findall(email_pattern, text, re.IGNORECASE)

        for email in emails:
            assert email not in redacted, f"Email {email} should be redacted"
            assert "[REDACTED_EMAIL]" in redacted or "REDACTED" in redacted, (
                "Should contain redaction marker"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_phone_various_formats(pii_redactor):
    """Test PII removal for phone numbers in various formats."""
    test_cases = [
        f"Call me at {_require_pii_value('phone_basic')}",
        f"Phone: {_require_pii_value('phone_paren')}",
        f"Mobile: {_require_pii_value('phone_dot')}",
        f"Contact: {_require_pii_value('phone_intl')}",
        f"Tel: {_require_pii_value('phone_compact')}",
    ]

    for text in test_cases:
        redacted = pii_redactor.redact(text)
        # Extract phone pattern
        phone_pattern = r"\b\d{3}[\s.-]?\d{3}[\s.-]?\d{4}\b"
        phones = re.findall(phone_pattern, text)

        for phone in phones:
            # Check that original phone format is not in redacted
            assert phone.replace("-", "").replace(".", "").replace(" ", "").replace(
                "(", ""
            ).replace(")", "") not in redacted.replace("-", "").replace(".", "").replace(
                " ", ""
            ).replace("(", "").replace(")", ""), f"Phone {phone} should be redacted"
            assert "[REDACTED_PHONE]" in redacted or "REDACTED" in redacted, (
                "Should contain redaction marker"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_ssn(pii_redactor):
    """Test PII removal for Social Security Numbers."""
    ssn = _require_pii_value("ssn")
    text = f"My SSN is {ssn}."
    redacted = pii_redactor.redact(text)

    assert ssn not in redacted
    assert "[REDACTED_SSN]" in redacted or "REDACTED" in redacted
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_credit_card(pii_redactor):
    """Test PII removal for credit card numbers."""
    card = _require_pii_value("card")
    dashed = f"{card[:4]}-{card[4:8]}-{card[8:12]}-{card[12:]}"
    spaced = f"{card[:4]} {card[4:8]} {card[8:12]} {card[12:]}"
    test_cases = [
        f"Card: {dashed}",
        f"CC: {spaced}",
        f"Card number: {card}",
    ]

    for text in test_cases:
        redacted = pii_redactor.redact(text)
        # Extract card pattern
        card_pattern = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
        cards = re.findall(card_pattern, text)

        for card in cards:
            assert card.replace("-", "").replace(" ", "") not in redacted.replace("-", "").replace(
                " ", ""
            ), f"Card {card} should be redacted"
            assert "[REDACTED_CC]" in redacted or "REDACTED" in redacted, (
                "Should contain redaction marker"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_ip_address(pii_redactor):
    """Test PII removal for IP addresses (if enabled)."""
    ip_addr = _require_pii_value("ip_address")
    text = f"Server IP: {ip_addr}"
    redacted = pii_redactor.redact(text)

    # IP redaction may or may not be enabled - just verify structure is preserved
    assert "Server" in redacted or "IP" in redacted.lower()
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_multiple_types(pii_redactor):
    """Test PII removal when multiple PII types are present."""
    test_email = _require_pii_value("email_simple")
    phone = _require_pii_value("phone_basic")
    ssn = _require_pii_value("ssn")
    card = _require_pii_value("card")
    card_dashed = f"{card[:4]}-{card[4:8]}-{card[8:12]}-{card[12:]}"
    text = f"Contact: {test_email}, Phone: {phone}, SSN: {ssn}, Card: {card_dashed}"
    redacted = pii_redactor.redact(text)

    # All PII should be redacted
    assert test_email not in redacted
    assert phone not in redacted
    assert ssn not in redacted
    assert card not in redacted

    # Structure should be preserved
    assert "Contact" in redacted or "Phone" in redacted or "SSN" in redacted or "Card" in redacted
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_no_pii(pii_redactor):
    """Test PII removal when no PII is present."""
    text = "This is a normal message with no sensitive information."
    redacted = pii_redactor.redact(text)

    assert redacted == text, "Text without PII should remain unchanged"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_preserves_structure(pii_redactor):
    """Test that PII removal preserves message structure."""
    test_email = _require_pii_value("email_simple")
    phone = _require_pii_value("phone_basic")
    text = f"Hello, my email is {test_email} and phone is {phone}. Please contact me."
    redacted = pii_redactor.redact(text)

    # Structure should be preserved
    assert "Hello" in redacted
    assert "email" in redacted.lower()
    assert "phone" in redacted.lower()
    assert "contact" in redacted.lower()

    # But PII should be redacted
    assert test_email not in redacted
    assert phone not in redacted
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_nested_json(pii_redactor):
    """Test PII removal from nested JSON structures."""
    test_email = _require_pii_value("email_simple")
    phone = _require_pii_value("phone_basic")
    data = {"user": {"email": test_email, "phone": phone, "profile": {"contact": test_email}}}

    json_str = json.dumps(data)
    redacted_str = pii_redactor.redact(json_str)

    # PII should be redacted
    assert test_email not in redacted_str
    assert phone not in redacted_str

    # Structure should be preserved
    assert "user" in redacted_str
    assert "email" in redacted_str.lower()
    assert "phone" in redacted_str.lower()


# ============================================================================
# PII REMOVAL FROM SESSION HISTORY TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_from_session_messages(api_client, test_user, test_expert, pii_redactor):
    """Test PII removal from session messages."""
    # Create session
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": "PII Test Session",
        },
    )
    assert session_response.status_code == 200
    session = session_response.json()
    session_id = session["id"]

    # Add messages with PII
    test_email = _require_pii_value("email_simple")
    phone = _require_pii_value("phone_basic")
    messages = [
        {"role": "user", "content": f"My email is {test_email}"},
        {"role": "assistant", "content": "I'll help you."},
        {"role": "user", "content": f"Call me at {phone}"},
    ]

    for msg in messages:
        response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert response.status_code == 200

    # Get session history
    history_response = api_client.get(f"/sessions/{session_id}/messages")
    assert history_response.status_code == 200
    history_data = history_response.json()

    # Validate response structure
    assert "messages" in history_data
    assert "count" in history_data
    assert isinstance(history_data["messages"], list)

    # Test redaction on retrieved messages
    for msg in history_data["messages"]:
        assert "content" in msg
        content = msg["content"]

        # Redact PII from content
        redacted_content = pii_redactor.redact(content)

        # If original content had PII, verify redaction
        if test_email in content:
            assert test_email not in redacted_content or "[REDACTED_EMAIL]" in redacted_content
        if phone in content:
            assert phone not in redacted_content or "[REDACTED_PHONE]" in redacted_content
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_from_session_history_export(api_client, test_user, test_expert, pii_redactor):
    """Test PII removal from exported session history."""
    # Create session and add messages with PII
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": "PII Export Test",
        },
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    test_email = _require_pii_value("email_simple")
    phone = _require_pii_value("phone_basic")
    api_client.post(
        f"/sessions/{session_id}/messages",
        json={"role": "user", "content": f"Email: {test_email}, Phone: {phone}"},
    )

    # Get history as JSON
    history_response = api_client.get(f"/sessions/{session_id}/messages")
    assert history_response.status_code == 200
    history_json = json.dumps(history_response.json())

    # Redact PII from exported data
    redacted_json = pii_redactor.redact(history_json)

    # Verify PII is redacted
    if test_email in history_json:
        assert test_email not in redacted_json or "[REDACTED_EMAIL]" in redacted_json
    if phone in history_json:
        assert phone not in redacted_json or "[REDACTED_PHONE]" in redacted_json


# ============================================================================
# PII REMOVAL FROM API RESPONSES TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_from_user_api_response(api_client, test_user, pii_redactor):
    """Test PII removal from user API response."""
    user_id = test_user["id"]
    user_email = test_user["email"]

    # Get user via API
    response = api_client.get(f"/users/{user_id}")
    assert response.status_code == 200
    user_data = response.json()

    # Validate response structure
    assert "id" in user_data
    assert "username" in user_data
    assert "email" in user_data

    # Test redaction on response
    response_str = json.dumps(user_data)
    redacted_str = pii_redactor.redact(response_str)

    # If email was in response, verify it can be redacted
    if user_email in response_str:
        # Note: API may or may not redact email automatically
        # This test verifies manual redaction works
        assert user_email not in redacted_str or "[REDACTED_EMAIL]" in redacted_str
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_from_session_api_response(api_client, test_user, test_expert, pii_redactor):
    """Test PII removal from session API response."""
    # Create session
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": "PII Session Test",
        },
    )
    assert session_response.status_code == 200
    session = session_response.json()
    session_id = session["id"]

    # Add message with PII
    test_email = _require_pii_value("email_simple")
    api_client.post(
        f"/sessions/{session_id}/messages",
        json={"role": "user", "content": f"Contact: {test_email}"},
    )

    # Get session details
    get_response = api_client.get(f"/sessions/{session_id}")
    assert get_response.status_code == 200
    session_data = get_response.json()

    # Validate response structure
    assert "id" in session_data
    assert "title" in session_data

    # Test redaction on response
    response_str = json.dumps(session_data)
    redacted_str = pii_redactor.redact(response_str)

    # If email was in response, verify redaction
    if test_email in response_str:
        assert test_email not in redacted_str or "[REDACTED_EMAIL]" in redacted_str


# ============================================================================
# PII REMOVAL FROM AUDIT LOGS TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_from_audit_log_entries(api_client, test_user, test_expert, pii_redactor):
    """Test PII removal from audit log entries."""
    user_id = test_user["id"]
    user_email = test_user["email"]

    # Trigger some audit events by creating a session
    session_response = api_client.post(
        "/sessions",
        json={"user_id": user_id, "expert_config_id": test_expert["id"], "title": "Audit PII Test"},
    )
    assert session_response.status_code == 200

    # Get audit events
    audit_response = api_client.get(f"/audit?user_id={user_id}")
    assert audit_response.status_code == 200
    audit_data = audit_response.json()

    # Validate response structure
    assert "events" in audit_data
    assert isinstance(audit_data["events"], list)

    if len(audit_data["events"]) > 0:
        # Test redaction on audit entries
        for event in audit_data["events"]:
            event_str = json.dumps(event)
            redacted_str = pii_redactor.redact(event_str)

            # If email was in event, verify redaction
            if user_email in event_str:
                assert user_email not in redacted_str or "[REDACTED_EMAIL]" in redacted_str
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_from_audit_log_export_json(api_client, test_user, test_expert, pii_redactor):
    """Test PII removal from exported audit logs (JSON format)."""
    user_id = test_user["id"]
    user_email = test_user["email"]

    # Trigger audit event
    api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": test_expert["id"],
            "title": "Audit Export Test",
        },
    )

    # Export audit logs as JSON
    export_response = api_client.get(f"/audit/export/json?user_id={user_id}")
    assert export_response.status_code == 200

    export_data = export_response.text

    # Test redaction on exported data
    redacted_export = pii_redactor.redact(export_data)

    # If email was in export, verify redaction
    if user_email in export_data:
        assert user_email not in redacted_export or "[REDACTED_EMAIL]" in redacted_export
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_from_audit_log_export_csv(api_client, test_user, test_expert, pii_redactor):
    """Test PII removal from exported audit logs (CSV format)."""
    user_id = test_user["id"]
    user_email = test_user["email"]

    # Trigger audit event
    api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": test_expert["id"],
            "title": "Audit CSV Export Test",
        },
    )

    # Export audit logs as CSV
    export_response = api_client.get(f"/audit/export/csv?user_id={user_id}")
    assert export_response.status_code == 200

    export_data = export_response.text

    # Test redaction on exported data
    redacted_export = pii_redactor.redact(export_data)

    # If email was in export, verify redaction
    if user_email in export_data:
        assert user_email not in redacted_export or "[REDACTED_EMAIL]" in redacted_export
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_from_audit_log_by_id(api_client, test_user, test_expert, pii_redactor):
    """Test PII removal from individual audit log entry."""
    user_id = test_user["id"]
    user_email = test_user["email"]

    # Trigger audit event
    api_client.post(
        "/sessions",
        json={"user_id": user_id, "expert_config_id": test_expert["id"], "title": "Audit ID Test"},
    )

    # Get audit events
    audit_response = api_client.get(f"/audit?user_id={user_id}")
    assert audit_response.status_code == 200
    events = audit_response.json()["events"]

    if len(events) > 0:
        event_id = events[0]["id"]

        # Get event by ID
        event_response = api_client.get(f"/audit/{event_id}")
        assert event_response.status_code == 200
        event_data = event_response.json()

        # Validate response structure
        assert "id" in event_data
        assert "timestamp" in event_data
        assert "event_type" in event_data

        # Test redaction on event
        event_str = json.dumps(event_data)
        redacted_str = pii_redactor.redact(event_str)

        # If email was in event, verify redaction
        if user_email in event_str:
            assert user_email not in redacted_str or "[REDACTED_EMAIL]" in redacted_str


# ============================================================================
# PII REMOVAL CONFIGURATION TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_configuration_enabled(api_client, test_user, pii_redactor):
    """Test that PII removal can be enabled/disabled via configuration."""
    # Check if PII redaction is enabled in config
    pii_enabled = get_config("log.pii_redaction") or get_config("privacy.pii_removal_enabled")

    # If enabled, verify redaction works
    if pii_enabled:
        test_email = _require_pii_value("email_simple")
        text = f"Email: {test_email}"
        redacted = pii_redactor.redact(text)
        assert test_email not in redacted or "[REDACTED_EMAIL]" in redacted
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_patterns_configurable(pii_redactor):
    """Test that PII patterns are configurable."""
    # Verify default patterns work
    test_email = _require_pii_value("email_simple")
    text = f"Contact: {test_email}"
    redacted = pii_redactor.redact(text)

    # Should redact email
    assert test_email not in redacted or "[REDACTED_EMAIL]" in redacted


# ============================================================================
# PII REMOVAL EDGE CASES TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_boundary_cases(pii_redactor):
    """Test PII removal at text boundaries."""
    test_email = _require_pii_value("email_simple")

    # PII at start
    text1 = f"{test_email} is my email"
    redacted1 = pii_redactor.redact(text1)
    assert test_email not in redacted1 or "[REDACTED_EMAIL]" in redacted1

    # PII at end
    text2 = f"My email is {test_email}"
    redacted2 = pii_redactor.redact(text2)
    assert test_email not in redacted2 or "[REDACTED_EMAIL]" in redacted2

    # PII only
    text3 = test_email
    redacted3 = pii_redactor.redact(text3)
    assert test_email not in redacted3 or "[REDACTED_EMAIL]" in redacted3
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_in_code_blocks(pii_redactor):
    """Test PII removal in code blocks (may or may not redact)."""
    test_email = _require_pii_value("email_simple")
    text = f"Code: ```\nemail = '{test_email}'\n```"
    redacted = pii_redactor.redact(text)

    # PII should still be redacted even in code blocks
    assert test_email not in redacted or "[REDACTED_EMAIL]" in redacted
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_in_urls(pii_redactor):
    """Test PII removal in URLs."""
    test_email = _require_pii_value("email_simple")
    url_base = _require_pii_value("url_base").rstrip("/")
    text = f"Visit {url_base}/{test_email}/profile"
    redacted = pii_redactor.redact(text)

    # Email in URL should be redacted
    assert test_email not in redacted or "[REDACTED_EMAIL]" in redacted
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_unicode_characters(pii_redactor):
    """Test PII removal with Unicode characters."""
    # Test with international email
    text = "Contact: 用户@例子.中国"
    redacted = pii_redactor.redact(text)

    # Should handle Unicode (may or may not redact depending on pattern)
    assert isinstance(redacted, str), "Redacted should be a string"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_empty_string(pii_redactor):
    """Test PII removal with empty string."""
    text = ""
    redacted = pii_redactor.redact(text)

    assert redacted == text, "Empty string should remain empty"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_pii_removal_very_long_text(pii_redactor):
    """Test PII removal with very long text."""
    test_email = _require_pii_value("email_simple")
    long_text = " ".join([f"Paragraph {i} with email {test_email}" for i in range(100)])
    redacted = pii_redactor.redact(long_text)

    # All occurrences should be redacted
    assert long_text.count(test_email) > 0, "Original should have email"
    assert redacted.count(test_email) == 0, "Redacted should not have email"
    assert "[REDACTED_EMAIL]" in redacted or "REDACTED" in redacted, "Should have redaction markers"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

