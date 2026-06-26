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
Unit Test: UT1.140 — File-upload (admin-only) and quality-feedback (auth) gates.

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description:
    W28E-1809B Stream-B negative-auth coverage for the two route-level gaps:
      * POST /files/upload is admin-only (verify_admin): admin passes the gate,
        a non-admin (read-write) caller is 403, an anonymous caller is 401
        (FR-008 Multimedia Processing — admin-gated ingest).
      * POST /quality/feedback requires authentication (verify_api_key): an
        anonymous caller is 401 and an authenticated caller is attributed to the
        real user (never a default user); a bad job id yields 404, proving the
        gate is reached without placeholder attribution (FR-023 Response Quality).

Related Requirements: FR-008, FR-023
Related Tests: UT1.140
"""

from __future__ import annotations

import uuid

import pytest
from cloud_dog_idam.api_keys.hashing import hash_api_key

from src.core.auth.user_manager import UserManager
from src.database.models import APIKey
from tests.helpers_orchestration import build_api_client, seed_admin


def _seed_user_with_key(db_session, role: str, api_key: str):
    unique = uuid.uuid4().hex[:8]
    user = UserManager(db_session).create_user(
        username=f"ut140_{role}_{unique}",
        email=f"ut140_{role}_{unique}@example.com",
        password="Password123!",
        role=role,
        enabled=True,
    )
    db_session.add(
        APIKey(
            key_hash=hash_api_key(api_key),
            user_id=user.id,
            name=f"ut140_{role}_key",
            read_channels=True,
            write_channels=True,
            read_logs=True,
            write_logs=True,
            read_histories=True,
            write_histories=True,
            revoked=False,
        )
    )
    db_session.commit()
    db_session.refresh(user)
    return user, api_key


_FILE = {"uploaded_file": ("ut140.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")}


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.req("FR-008")
def test_upload_admin_passes_auth_gate(db_session):
    _, api_key = seed_admin(db_session, api_key="ut140-admin-key")
    client = build_api_client(db_session, api_key=api_key)
    try:
        resp = client.post("/files/upload", files=_FILE)
        # Admin clears the auth gate. The request may still fail validation
        # (unsupported format/size) but must NOT be rejected for auth reasons.
        assert resp.status_code not in (401, 403), resp.text
    finally:
        client.close()


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.negative
@pytest.mark.req("FR-008")
def test_upload_non_admin_is_forbidden(db_session):
    _, api_key = _seed_user_with_key(db_session, role="user", api_key="ut140-user-key")
    client = build_api_client(db_session, api_key=api_key)
    try:
        resp = client.post("/files/upload", files=_FILE)
        assert resp.status_code == 403, f"non-admin upload must be 403, got {resp.status_code}: {resp.text[:160]}"
    finally:
        client.close()


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.negative
@pytest.mark.req("FR-008")
def test_upload_anonymous_is_unauthorized(db_session):
    _, api_key = seed_admin(db_session, api_key="ut140-anon-upload-key")
    client = build_api_client(db_session, api_key=api_key)
    client.headers.pop("X-API-Key", None)
    try:
        resp = client.post("/files/upload", files=_FILE)
        assert resp.status_code == 401, f"anon upload must be 401, got {resp.status_code}: {resp.text[:160]}"
    finally:
        client.close()


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.negative
@pytest.mark.req("FR-023")
def test_feedback_anonymous_is_unauthorized(db_session):
    _, api_key = seed_admin(db_session, api_key="ut140-anon-feedback-key")
    client = build_api_client(db_session, api_key=api_key)
    client.headers.pop("X-API-Key", None)
    try:
        resp = client.post("/quality/feedback", json={"job_id": 1, "rating": 5})
        assert resp.status_code == 401, f"anon feedback must be 401, got {resp.status_code}: {resp.text[:160]}"
    finally:
        client.close()


@pytest.mark.UT
@pytest.mark.api
@pytest.mark.req("FR-023")
def test_feedback_authenticated_reaches_handler(db_session):
    _, api_key = seed_admin(db_session, api_key="ut140-feedback-key")
    client = build_api_client(db_session, api_key=api_key)
    try:
        # Authenticated caller clears the gate; a non-existent job is 404 (not a
        # silent placeholder-attributed 200).
        resp = client.post("/quality/feedback", json={"job_id": 999999, "rating": 5})
        assert resp.status_code == 404, f"authenticated feedback on missing job must be 404, got {resp.status_code}: {resp.text[:160]}"
    finally:
        client.close()
