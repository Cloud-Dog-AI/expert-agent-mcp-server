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
UT1.135 — outbound cross-service credential resolution (EA6 / W28M-FIX-1616).

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description:
    Proves expert-agent resolves its OUTBOUND api-key for a bound external
    service from config/Vault (service_credentials.<name>.api_key) rather than a
    secret stored in the external_services table. The file-mcp key provisioned in
    Vault (dev.services.filemcpserver0.api_key) is wired to expert-agent via
    CLOUD_DOG__EXPERT__SERVICE_CREDENTIALS__FILEMCPSERVER0__API_KEY=${vault...}.

Related Tasks: W28M-FIX-1616 / W28C-1704 EA6
"""

import json

import pytest

from src.core.service.composition import ServiceCompositionManager
from src.database.models import ExternalService


def _svc(name, auth_config):
    return ExternalService(
        name=name,
        type="mcp",
        endpoint_url=f"https://{name}.cloud-dog.net/mcp",
        auth_config_json=json.dumps(auth_config),
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_literal_value_used_when_present():
    svc = _svc("filemcpserver0", {"type": "api_key", "value": "literal-key"})
    assert ServiceCompositionManager._resolve_credential(svc, {"type": "api_key", "value": "literal-key"}) == "literal-key"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_config_key_resolved_via_get_config(monkeypatch):
    resolved = {"some.explicit.key": "from-config-key"}
    monkeypatch.setattr(
        "src.core.service.composition.get_config", lambda k: resolved.get(k)
    )
    svc = _svc("filemcpserver0", {"type": "api_key", "config_key": "some.explicit.key"})
    assert ServiceCompositionManager._resolve_credential(
        svc, {"type": "api_key", "config_key": "some.explicit.key"}
    ) == "from-config-key"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_service_name_convention_resolves_filemcpserver0_key(monkeypatch):
    # Mirrors preprod: service_credentials.filemcpserver0.api_key <- ${vault.dev.services.filemcpserver0.api_key}
    resolved = {"service_credentials.filemcpserver0.api_key": "cdfm0_vault_resolved"}
    monkeypatch.setattr(
        "src.core.service.composition.get_config", lambda k: resolved.get(k)
    )
    svc = _svc("filemcpserver0", {"type": "api_key"})
    assert ServiceCompositionManager._resolve_credential(svc, {"type": "api_key"}) == "cdfm0_vault_resolved"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_auth_headers_injects_resolved_key(db_session, monkeypatch):
    resolved = {"service_credentials.filemcpserver0.api_key": "cdfm0_vault_resolved"}
    monkeypatch.setattr(
        "src.core.service.composition.get_config", lambda k: resolved.get(k)
    )
    mgr = ServiceCompositionManager(db_session)
    svc = _svc("filemcpserver0", {"type": "api_key"})
    headers = mgr._auth_headers(svc, auth_context={"correlation_id": "abc"})
    assert headers["X-API-Key"] == "cdfm0_vault_resolved"
    assert headers["X-Correlation-ID"] == "abc"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_no_credential_means_no_api_key_header(db_session, monkeypatch):
    monkeypatch.setattr("src.core.service.composition.get_config", lambda k: None)
    mgr = ServiceCompositionManager(db_session)
    svc = _svc("filemcpserver0", {"type": "api_key"})
    headers = mgr._auth_headers(svc)
    assert "X-API-Key" not in headers
