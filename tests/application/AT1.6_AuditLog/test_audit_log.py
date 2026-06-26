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
Application Test: AT1.6 - Audit Log Generation and Retrieval

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for audit log generation, retrieval, and export via API

Related Requirements: FR1.10
Related Tasks: T041
Related Architecture: SE1.3
Related Tests: AT1.6

Recent Changes:
- Refactored to use API endpoints for retrieval/export
- Use API actions to trigger audit events (user creation, session creation)
- Removed all hard-coded values (all from config system)
- All outputs validated via API responses
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


import pytest
import uuid
from datetime import datetime, timedelta
from src.config.loader import get_config


def _create_session(api_client, user_id: int, expert_id: int, title_suffix: str) -> dict:
    response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Audit Session {title_suffix}",
        },
    )
    assert response.status_code == 200, f"Failed to create session: {response.text}"
    return response.json()


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


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
        "username": f"{base_username}_at1_6_{unique_id}",
        "email": build_test_email("at1_6", unique_id, base_email),
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
    assert response.status_code == 200
    user_data = response.json()

    yield user_data

    # Cleanup via API
    try:
        api_client.delete(f"/users/{user_data['id']}")
    except Exception:
        pass


def _require_test_user_password() -> str:
    password = get_config("test.user.password")
    if not password:
        pytest.fail("test.user.password not configured (set in --env file)")
    return str(password)


@pytest.fixture
def test_expert(api_client, test_config):
    """Create test expert via API."""
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_6_{unique_id}",
        "title": f"Test Expert {unique_id}",
        "description": (
            f"Audit log expert for comprehensive testing with unique words and context {unique_id}"
        ),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200
    expert = response.json()

    yield expert

    # Cleanup via API
    try:
        api_client.delete(f"/experts/{expert['id']}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_log_retrieval_via_api(api_client, test_user, test_expert):
    """Test retrieving audit log entries via API with comprehensive output validation."""
    user_id = test_user["id"]
    event_type = "session.created"

    print("\n[TEST START] test_audit_log_retrieval_via_api")
    print(f"[SETTINGS] User ID: {user_id}")
    print(f"[SETTINGS] Event type: {event_type}")

    # Create an audit event via API (session create)
    session_data = _create_session(api_client, user_id, test_expert["id"], "retrieval")

    # Retrieve audit events via API
    response = api_client.get(f"/audit?session_id={session_data['id']}")

    assert response.status_code == 200, f"Failed to retrieve audit events: {response.text}"
    data = response.json()

    # Validate outputs - Format, Content, Structure
    # Format validation
    assert isinstance(data, dict), "Response should be a dictionary"
    assert "events" in data, "Response must contain 'events' field"
    assert "count" in data, "Response must contain 'count' field"
    assert isinstance(data["events"], list), "events must be a list"
    assert isinstance(data["count"], int), "count must be an integer"

    # Content validation
    assert data["count"] >= 1, f"count must be >= 1, got {data['count']}"
    assert len(data["events"]) >= 1, (
        f"events list must have at least 1 event, got {len(data['events'])}"
    )
    assert data["count"] == len(data["events"]), (
        f"count must match events length: expected {len(data['events'])}, got {data['count']}"
    )

    # Structure validation - validate event structure
    event = data["events"][0]
    assert isinstance(event, dict), "Each event must be a dictionary"
    assert "id" in event, "Event must have 'id' field"
    assert "timestamp" in event, "Event must have 'timestamp' field"
    assert "event_type" in event, "Event must have 'event_type' field"
    assert "user_id" in event, "Event must have 'user_id' field"

    # Validate field types and content
    assert isinstance(event["id"], int), "id must be an integer"
    assert event["id"] > 0, "id must be positive"
    assert isinstance(event["timestamp"], str), "timestamp must be a string (ISO format)"
    assert isinstance(event["event_type"], str), "event_type must be a string"
    assert event["event_type"] == event_type, (
        f"event_type must match: expected '{event_type}', got '{event['event_type']}'"
    )
    assert event["session_id"] == session_data["id"], (
        f"session_id must match: expected {session_data['id']}, got {event['session_id']}"
    )

    # Validate ISO datetime format
    from datetime import datetime

    try:
        datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    except ValueError:
        pytest.fail(f"timestamp must be valid ISO format datetime, got: {event['timestamp']}")

    # Validate details if present
    if "details" in event:
        assert isinstance(event["details"], dict), "details must be a dictionary if present"

    print("[TEST END] test_audit_log_retrieval_via_api")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_log_filtering_by_type_via_api(api_client, test_user, test_expert):
    """Test filtering audit logs by event type via API with comprehensive output validation."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    print("\n[TEST START] test_audit_log_filtering_by_type_via_api")
    print(f"[SETTINGS] User ID: {user_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")

    # Create a session via API
    session_data = _create_session(api_client, user_id, expert_id, "filter-type")

    # Get all events for this session
    all_events_response = api_client.get(f"/audit?session_id={session_data['id']}")
    assert all_events_response.status_code == 200, (
        f"Failed to get all events: {all_events_response.text}"
    )
    all_events_data = all_events_response.json()
    all_events = all_events_data["events"]

    # Validate all events response format
    assert isinstance(all_events_data, dict), "Response should be a dictionary"
    assert "events" in all_events_data, "Response must contain 'events' field"
    assert "count" in all_events_data, "Response must contain 'count' field"
    assert isinstance(all_events, list), "events must be a list"
    assert len(all_events) >= 1, f"Should have at least 1 event, got {len(all_events)}"

    # Filter by event type via API
    filter_type = "session.created"
    session_events_response = api_client.get(
        f"/audit?session_id={session_data['id']}&event_type={filter_type}"
    )
    assert session_events_response.status_code == 200, (
        f"Failed to filter by type: {session_events_response.text}"
    )
    session_events_data = session_events_response.json()
    session_events = session_events_data["events"]

    # Validate outputs - Format, Content, Structure
    # Format validation
    assert isinstance(session_events_data, dict), "Filtered response should be a dictionary"
    assert "events" in session_events_data, "Response must contain 'events' field"
    assert "count" in session_events_data, "Response must contain 'count' field"
    assert isinstance(session_events, list), "events must be a list"

    # Content validation
    assert len(session_events) >= 1, (
        f"Should have at least 1 session.created event, got {len(session_events)}"
    )
    assert session_events_data["count"] == len(session_events), (
        f"count must match events length: expected {len(session_events)}, got {session_events_data['count']}"
    )
    assert all(e["event_type"] == filter_type for e in session_events), (
        f"All events must be of type '{filter_type}'"
    )

    # Structure validation - verify all filtered events have correct structure
    for event in session_events:
        assert isinstance(event, dict), "Each event must be a dictionary"
        assert "id" in event, "Event must have 'id' field"
        assert "event_type" in event, "Event must have 'event_type' field"
        assert event["event_type"] == filter_type, (
            f"Event type must match filter: expected '{filter_type}', got '{event['event_type']}'"
        )
        assert "user_id" in event, "Event must have 'user_id' field"
        assert event["session_id"] == session_data["id"], (
            f"session_id must match: expected {session_data['id']}, got {event['session_id']}"
        )

    print("[TEST END] test_audit_log_filtering_by_type_via_api")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_log_filtering_by_date_range_via_api(api_client, test_user, test_expert):
    """Test filtering audit logs by date range via API with comprehensive output validation."""
    user_id = test_user["id"]

    print("\n[TEST START] test_audit_log_filtering_by_date_range_via_api")
    print(f"[SETTINGS] User ID: {user_id}")

    # Create an audit event via API (session create)
    start_time = datetime.utcnow() - timedelta(hours=1)
    session_data = _create_session(api_client, user_id, test_expert["id"], "date-range")
    end_time = datetime.utcnow() + timedelta(minutes=1)

    response = api_client.get(
        f"/audit?session_id={session_data['id']}&start_date={start_time.isoformat()}&end_date={end_time.isoformat()}"
    )

    assert response.status_code == 200, f"Failed to filter by date range: {response.text}"
    data = response.json()

    # Validate outputs - Format, Content, Structure
    # Format validation
    assert isinstance(data, dict), "Response should be a dictionary"
    assert "events" in data, "Response must contain 'events' field"
    assert "count" in data, "Response must contain 'count' field"
    assert isinstance(data["events"], list), "events must be a list"

    # Content validation
    assert len(data["events"]) >= 1, (
        f"Should have at least 1 event in date range, got {len(data['events'])}"
    )
    assert data["count"] == len(data["events"]), (
        f"count must match events length: expected {len(data['events'])}, got {data['count']}"
    )

    # Structure validation - verify timestamps are in range
    for event in data["events"]:
        assert isinstance(event, dict), "Each event must be a dictionary"
        assert "timestamp" in event, "Event must have 'timestamp' field"
        assert isinstance(event["timestamp"], str), "timestamp must be a string"

        # Verify timestamp is in range
        try:
            event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            event_time_naive = event_time.replace(tzinfo=None)
            assert start_time <= event_time_naive <= end_time, (
                f"Event timestamp {event['timestamp']} must be in range [{start_time.isoformat()}, {end_time.isoformat()}]"
            )
        except ValueError:
            pytest.fail(f"timestamp must be valid ISO format datetime, got: {event['timestamp']}")

    print("[TEST END] test_audit_log_filtering_by_date_range_via_api")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_log_export_via_api(api_client, test_user, test_expert):
    """Test exporting audit logs via API with comprehensive format validation."""
    user_id = test_user["id"]

    print("\n[TEST START] test_audit_log_export_via_api")
    print(f"[SETTINGS] User ID: {user_id}")

    # Create audit events via API (session create)
    session_data = _create_session(api_client, user_id, test_expert["id"], "export")

    # Export as JSON
    json_response = api_client.get(f"/audit/export/json?session_id={session_data['id']}")
    assert json_response.status_code == 200, f"Failed to export JSON: {json_response.text}"

    # Validate JSON response headers
    assert "content-type" in json_response.headers, "Response must have content-type header"
    assert json_response.headers["content-type"] == "application/json", (
        f"Content-Type must be application/json, got {json_response.headers.get('content-type')}"
    )

    # Validate Content-Disposition header
    if "content-disposition" in json_response.headers:
        assert "attachment" in json_response.headers["content-disposition"].lower(), (
            "Content-Disposition should indicate attachment"
        )
        assert "audit_logs.json" in json_response.headers["content-disposition"], (
            "Filename should be audit_logs.json"
        )

    # Validate JSON export format and content
    import json

    try:
        export_data = json.loads(json_response.text)
    except json.JSONDecodeError:
        pytest.fail(f"JSON export must be valid JSON, got: {json_response.text[:100]}")

    assert isinstance(export_data, list), "JSON export must be a list"
    assert len(export_data) >= 1, f"JSON export must have at least 1 event, got {len(export_data)}"

    # Validate JSON export structure - each item should have event structure
    for item in export_data:
        assert isinstance(item, dict), "Each export item must be a dictionary"
        assert "id" in item, "Each item must have 'id' field"
        assert "timestamp" in item, "Each item must have 'timestamp' field"
        assert "event_type" in item, "Each item must have 'event_type' field"

    # Export as CSV
    csv_response = api_client.get(f"/audit/export/csv?session_id={session_data['id']}")
    assert csv_response.status_code == 200, f"Failed to export CSV: {csv_response.text}"

    # Validate CSV response headers
    assert "content-type" in csv_response.headers, "Response must have content-type header"
    assert "text/csv" in csv_response.headers["content-type"], (
        f"Content-Type must contain text/csv, got {csv_response.headers.get('content-type')}"
    )

    # Validate Content-Disposition header
    if "content-disposition" in csv_response.headers:
        assert "attachment" in csv_response.headers["content-disposition"].lower(), (
            "Content-Disposition should indicate attachment"
        )
        assert "audit_logs.csv" in csv_response.headers["content-disposition"], (
            "Filename should be audit_logs.csv"
        )

    # Validate CSV export format and content
    csv_text = csv_response.text
    assert isinstance(csv_text, str), "CSV export must be a string"
    csv_lines = csv_text.strip().split("\n")
    assert len(csv_lines) >= 2, (
        f"CSV must have header + at least one data row, got {len(csv_lines)} lines"
    )

    # Validate CSV header row
    header_line = csv_lines[0]
    assert "id" in header_line.lower(), f"CSV header must contain 'id', got: {header_line}"
    assert "timestamp" in header_line.lower() or "created_at" in header_line.lower(), (
        f"CSV header must contain timestamp field, got: {header_line}"
    )
    assert "event_type" in header_line.lower() or "kind" in header_line.lower(), (
        f"CSV header must contain event_type field, got: {header_line}"
    )

    # Validate CSV data rows
    for i, line in enumerate(csv_lines[1:], start=1):
        assert len(line) > 0, f"CSV data row {i} must not be empty"
        # CSV rows should have comma-separated values
        values = line.split(",")
        assert len(values) >= 3, f"CSV data row {i} must have at least 3 columns, got {len(values)}"

    print("[TEST END] test_audit_log_export_via_api")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_log_get_event_by_id_via_api(api_client, test_user, test_expert):
    """Test getting audit event by ID via API with comprehensive output validation."""
    user_id = test_user["id"]

    print("\n[TEST START] test_audit_log_get_event_by_id_via_api")
    print(f"[SETTINGS] User ID: {user_id}")

    # Create an audit event via API (session create)
    session_data = _create_session(api_client, user_id, test_expert["id"], "get-by-id")

    # Get all events
    all_events_response = api_client.get(f"/audit?session_id={session_data['id']}")
    assert all_events_response.status_code == 200, (
        f"Failed to get events: {all_events_response.text}"
    )
    events = all_events_response.json()["events"]

    if len(events) == 0:
        pytest.fail("No audit events found to test")

    event_id = events[0]["id"]

    # Get specific event by ID via API
    response = api_client.get(f"/audit/{event_id}")
    assert response.status_code == 200, f"Failed to get event by ID: {response.text}"
    event = response.json()

    # Validate all outputs - Format, Content, Structure
    # Format validation
    assert isinstance(event, dict), "Response should be a dictionary"
    assert "id" in event, "Event must have 'id' field"
    assert "timestamp" in event, "Event must have 'timestamp' field"
    assert "event_type" in event, "Event must have 'event_type' field"
    assert "user_id" in event, "Event must have 'user_id' field"
    assert "details" in event, "Event must have 'details' field"
    assert "signature" in event, "Event must have 'signature' field (cryptographic signature)"

    # Content validation
    assert event["id"] == event_id, f"id must match: expected {event_id}, got {event['id']}"
    assert isinstance(event["id"], int), "id must be an integer"
    assert isinstance(event["timestamp"], str), "timestamp must be a string (ISO format)"
    assert isinstance(event["event_type"], str), "event_type must be a string"
    assert isinstance(event["user_id"], (int, type(None))), "user_id must be an integer or null"
    assert isinstance(event["details"], dict), "details must be a dictionary"
    assert isinstance(event["signature"], str), "signature must be a string"

    # Structure validation - signature must not be empty
    assert event["signature"] is not None, "signature must not be None"
    assert len(event["signature"]) > 0, (
        f"signature must not be empty, got length {len(event['signature'])}"
    )

    # Validate ISO datetime format
    from datetime import datetime

    try:
        datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    except ValueError:
        pytest.fail(f"timestamp must be valid ISO format datetime, got: {event['timestamp']}")

    # Optional fields validation
    if "session_id" in event:
        assert isinstance(event["session_id"], (int, type(None))), (
            "session_id must be an integer or null"
        )
    if "channel_id" in event:
        assert isinstance(event["channel_id"], (int, type(None))), (
            "channel_id must be an integer or null"
        )
    if "expert_id" in event:
        assert isinstance(event["expert_id"], (int, type(None))), (
            "expert_id must be an integer or null"
        )
    if "ip_address" in event:
        assert isinstance(event["ip_address"], (str, type(None))), (
            "ip_address must be a string or null"
        )
    if "user_agent" in event:
        assert isinstance(event["user_agent"], (str, type(None))), (
            "user_agent must be a string or null"
        )

    print("[TEST END] test_audit_log_get_event_by_id_via_api")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_log_integrity_signature_via_api(api_client, test_user, test_expert):
    """Test that audit logs have cryptographic signatures via API."""
    user_id = test_user["id"]

    # Create an audit event via API (session create)
    session_data = _create_session(api_client, user_id, test_expert["id"], "signature")

    # Get events via API
    response = api_client.get(f"/audit?session_id={session_data['id']}")
    assert response.status_code == 200
    events = response.json()["events"]

    if len(events) == 0:
        pytest.fail("No audit events found to test")

    # Get first event by ID to get full details including signature
    event_id = events[0]["id"]
    event_response = api_client.get(f"/audit/{event_id}")
    assert event_response.status_code == 200
    event = event_response.json()

    # Verify signature exists
    assert "signature" in event
    assert event["signature"] is not None
    assert len(event["signature"]) > 0

    # Verify signature via API - signature is included in GET /audit/{event_id} response
    # The signature verification is an internal operation, but we can verify the signature exists
    # and is non-empty, which indicates it was generated correctly
    # Full cryptographic verification would require an API endpoint, which doesn't exist yet
    # For now, we verify the signature field exists and is non-empty
    assert "signature" in event
    assert event["signature"] is not None
    assert len(event["signature"]) > 0
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_log_session_events_via_api(api_client, test_user, test_expert):
    """Test audit logging for session events via API."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Create session via API
    session_data = _create_session(api_client, user_id, expert_id, "session-events")
    session_id = session_data["id"]

    # Session creation should generate audit events automatically

    # Get audit events for this session via API
    audit_response = api_client.get(f"/audit?session_id={session_id}")
    assert audit_response.status_code == 200
    events = audit_response.json()["events"]

    # Should have at least one session.created event
    assert len(events) >= 1

    # Find session.created event
    session_events = [e for e in events if e["event_type"] == "session.created"]
    assert len(session_events) >= 1

    # Validate event
    event = session_events[0]
    assert event["user_id"] == user_id
    assert event["session_id"] == session_id
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_log_pagination_via_api(api_client, test_user, test_expert):
    """Test audit log pagination via API with comprehensive output validation."""
    user_id = test_user["id"]
    num_events = 10
    page_size = 5

    print("\n[TEST START] test_audit_log_pagination_via_api")
    print(f"[SETTINGS] User ID: {user_id}")
    print(f"[SETTINGS] Creating {num_events} events, page size: {page_size}")

    # Create multiple audit events via API (session create)
    sessions = []
    for i in range(num_events):
        sessions.append(_create_session(api_client, user_id, test_expert["id"], f"page-{i + 1}"))

    # Get first page
    page1_response = api_client.get(f"/audit?event_type=session.created&limit={page_size}&offset=0")
    assert page1_response.status_code == 200, f"Failed to get first page: {page1_response.text}"
    page1 = page1_response.json()

    # Validate outputs - Format, Content, Structure
    # Format validation
    assert isinstance(page1, dict), "Response should be a dictionary"
    assert "events" in page1, "Response must contain 'events' field"
    assert "count" in page1, "Response must contain 'count' field"
    assert isinstance(page1["events"], list), "events must be a list"
    assert isinstance(page1["count"], int), "count must be an integer"

    # Content validation
    assert len(page1["events"]) <= page_size, (
        f"Page 1 should have <= {page_size} events, got {len(page1['events'])}"
    )
    # Note: count may be the count for this page or total count, depending on API implementation
    assert page1["count"] >= len(page1["events"]), (
        f"count should be >= page events: expected >= {len(page1['events'])}, got {page1['count']}"
    )

    # Structure validation - verify event structure
    for event in page1["events"]:
        assert isinstance(event, dict), "Each event must be a dictionary"
        assert "id" in event, "Event must have 'id' field"
        assert "timestamp" in event, "Event must have 'timestamp' field"
        assert "event_type" in event, "Event must have 'event_type' field"

    # Get second page (if we have enough events)
    if page1["count"] > page_size:
        page2_response = api_client.get(
            f"/audit?user_id={user_id}&limit={page_size}&offset={page_size}"
        )
        assert page2_response.status_code == 200, (
            f"Failed to get second page: {page2_response.text}"
        )
        page2 = page2_response.json()

        # Validate page 2 format
        assert isinstance(page2, dict), "Page 2 response should be a dictionary"
        assert "events" in page2, "Page 2 response must contain 'events' field"
        assert "count" in page2, "Page 2 response must contain 'count' field"
        assert isinstance(page2["events"], list), "Page 2 events must be a list"

        # Content validation - events should be different
        if len(page1["events"]) > 0 and len(page2["events"]) > 0:
            page1_ids = {e["id"] for e in page1["events"]}
            page2_ids = {e["id"] for e in page2["events"]}
            assert page1_ids != page2_ids, "Page 1 and Page 2 should have different events"
            assert len(page1_ids & page2_ids) == 0, (
                "Page 1 and Page 2 should not have overlapping events"
            )

            # Count should be consistent
            assert page2["count"] == page1["count"], (
                f"Total count should be consistent: page1={page1['count']}, page2={page2['count']}"
            )

    print("[TEST END] test_audit_log_pagination_via_api")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_log_not_found_via_api(api_client):
    """Test audit event not found error via API with comprehensive error validation."""
    non_existent_id = 99999

    print("\n[TEST START] test_audit_log_not_found_via_api")
    print(f"[SETTINGS] Non-existent event ID: {non_existent_id}")

    # Try to get non-existent event
    response = api_client.get(f"/audit/{non_existent_id}")

    # Validate error response - Format, Content, Structure
    assert response.status_code == 404, (
        f"Non-existent event should return 404, got {response.status_code}: {response.text}"
    )

    error_data = response.json()
    assert isinstance(error_data, dict), "Error response should be a dictionary"
    assert "detail" in error_data, "Error response must contain 'detail' field"
    assert isinstance(error_data["detail"], str), "detail must be a string"

    detail_lower = error_data["detail"].lower()
    assert "not found" in detail_lower, (
        f"Error message should indicate not found: {error_data['detail']}"
    )

    print("[TEST END] test_audit_log_not_found_via_api")

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

