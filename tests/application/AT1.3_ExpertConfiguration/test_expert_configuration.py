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
Application Test: AT1.3 - Expert Configuration Management

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for expert configuration CRUD, validation, and activation via API

Related Requirements: FR1.1, FR1.12
Related Tasks: T007, T008, T009
Related Architecture: CC3.1.1
Related Tests: AT1.3

Recent Changes:
- Refactored to use API endpoints only (no direct ExpertConfig model calls)
- Added expert cleanup fixtures (remove at start/end)
- Removed all hard-coded values (all from config system)
- Added support for all LLM parameters (temperature, max_tokens, top_p, etc.)
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import create_api_client_fixture, validate_config_loaded


import pytest
import uuid
from src.config.loader import get_config


def _build_description(unique_id: str, purpose: str) -> str:
    return (
        f"AT1.3 {purpose} expert description {unique_id} "
        "with robust unique tokens for validation and compliance."
    )


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def test_expert_data(test_config):
    """Get test expert configuration data from config system (no hard-coding)."""
    test_config.get("llm", {})

    # Get all LLM parameters from config system
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_temperature = get_config("llm.temperature")
    llm_max_tokens = get_config("llm.max_tokens")
    llm_timeout = get_config("llm.timeout")

    # Get additional LLM parameters if available
    llm_params = {}
    if llm_temperature is not None:
        llm_params["temperature"] = float(llm_temperature)
    if llm_max_tokens is not None:
        llm_params["max_tokens"] = int(llm_max_tokens)
    if llm_timeout is not None:
        llm_params["timeout"] = int(llm_timeout)

    # Get optional LLM parameters (top_p, frequency_penalty, presence_penalty, etc.)
    top_p = get_config("llm.top_p")
    frequency_penalty = get_config("llm.frequency_penalty")
    presence_penalty = get_config("llm.presence_penalty")
    top_k = get_config("llm.top_k")
    repeat_penalty = get_config("llm.repeat_penalty")

    if top_p is not None:
        llm_params["top_p"] = float(top_p)
    if frequency_penalty is not None:
        llm_params["frequency_penalty"] = float(frequency_penalty)
    if presence_penalty is not None:
        llm_params["presence_penalty"] = float(presence_penalty)
    if top_k is not None:
        llm_params["top_k"] = int(top_k)
    if repeat_penalty is not None:
        llm_params["repeat_penalty"] = float(repeat_penalty)

    if not llm_provider or not llm_model:
        pytest.fail("LLM configuration not available. Set llm.provider and llm.model in --env file")

    unique_id = str(uuid.uuid4())[:8]
    return {
        "name": f"expert_at1_3_{unique_id}",
        "title": f"Test Expert {unique_id}",
        "description": _build_description(unique_id, "primary"),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_params": llm_params if llm_params else None,
        "prompt_template": "You are a helpful assistant.",
        "enabled": True,
    }


@pytest.fixture
def unique_expert_name():
    """Generate unique expert name for each test."""
    return f"expert_at1_3_{str(uuid.uuid4())[:8]}"


@pytest.fixture(autouse=True)
def cleanup_expert(api_client, test_expert_data):
    """Cleanup: Remove test expert at start (if exists) and end of test."""
    expert_name = test_expert_data["name"]

    # Cleanup before test via API
    list_response = api_client.get("/experts")
    if list_response.status_code != 200:
        pytest.fail(
            f"Failed to list experts for cleanup: {list_response.status_code} {list_response.text}"
        )
    experts = list_response.json().get("experts", [])
    for expert in experts:
        if expert.get("name") == expert_name:
            delete_response = api_client.delete(f"/experts/{expert['id']}")
            if delete_response.status_code not in (200, 204):
                pytest.fail(
                    f"Failed to delete expert via API: {delete_response.status_code} {delete_response.text}"
                )

    yield

    # Cleanup after test via API
    list_response = api_client.get("/experts")
    if list_response.status_code != 200:
        pytest.fail(
            f"Failed to list experts for cleanup: {list_response.status_code} {list_response.text}"
        )
    experts = list_response.json().get("experts", [])
    for expert in experts:
        if expert.get("name") == expert_name:
            delete_response = api_client.delete(f"/experts/{expert['id']}")
            if delete_response.status_code not in (200, 204):
                pytest.fail(
                    f"Failed to delete expert via API: {delete_response.status_code} {delete_response.text}"
                )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_create_expert_configuration(api_client, test_expert_data):
    """Test creating an expert configuration via API."""
    creds = test_expert_data

    # Show settings being used
    print(f"\n[SETTINGS] Expert name: {creds['name']}")
    print(f"[SETTINGS] LLM provider: {creds['llm_provider']}")
    print(f"[SETTINGS] LLM model: {creds['llm_model']}")
    if creds.get("llm_params"):
        print(f"[SETTINGS] LLM params: {creds['llm_params']}")

    # Create expert via API
    response = api_client.post(
        "/experts",
        json={
            "name": creds["name"],
            "title": creds["title"],
            "description": creds["description"],
            "llm_provider": creds["llm_provider"],
            "llm_model": creds["llm_model"],
            "llm_params": creds["llm_params"],
            "prompt_template": creds["prompt_template"],
            "enabled": creds["enabled"],
        },
    )

    assert response.status_code == 200, f"Creation failed: {response.text}"
    data = response.json()

    assert "id" in data
    assert data["name"] == creds["name"]
    assert data["title"] == creds["title"]
    assert data["llm_provider"] == creds["llm_provider"]
    assert data["llm_model"] == creds["llm_model"]
    assert data["enabled"] == creds["enabled"]

    # Verify expert exists via API
    get_response = api_client.get(f"/experts/{data['id']}")
    assert get_response.status_code == 200
    expert_data = get_response.json()
    assert expert_data["name"] == creds["name"]
    assert expert_data["description"] == creds["description"]
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_read_expert_configuration(api_client, test_expert_data):
    """Test reading an expert configuration via API."""
    creds = test_expert_data

    # Create expert via API
    create_response = api_client.post(
        "/experts",
        json={
            "name": creds["name"],
            "title": creds["title"],
            "description": creds["description"],
            "llm_provider": creds["llm_provider"],
            "llm_model": creds["llm_model"],
            "enabled": creds["enabled"],
        },
    )
    assert create_response.status_code == 200
    expert_id = create_response.json()["id"]

    # Retrieve expert via API
    get_response = api_client.get(f"/experts/{expert_id}")
    assert get_response.status_code == 200
    data = get_response.json()

    assert data["id"] == expert_id
    assert data["name"] == creds["name"]
    assert data["title"] == creds["title"]
    assert data["llm_provider"] == creds["llm_provider"]
    assert data["llm_model"] == creds["llm_model"]
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_expert_configuration_validation(api_client, test_expert_data):
    """Test expert configuration validation via API."""
    creds = test_expert_data

    # Missing description should fail
    response_missing = api_client.post(
        "/experts",
        json={
            "name": creds["name"],
            "title": creds["title"],
            "llm_provider": creds["llm_provider"],
            "llm_model": creds["llm_model"],
        },
    )
    assert response_missing.status_code == 422

    # Required fields with description should pass
    response = api_client.post(
        "/experts",
        json={
            "name": creds["name"],
            "title": creds["title"],
            "description": creds["description"],
            "llm_provider": creds["llm_provider"],
            "llm_model": creds["llm_model"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None

    # Test duplicate name (should fail)
    response2 = api_client.post(
        "/experts",
        json={
            "name": creds["name"],  # Same name
            "title": "Different Title",
            "description": _build_description("duplicate", "validation"),
            "llm_provider": creds["llm_provider"],
            "llm_model": creds["llm_model"],
        },
    )

    # Should fail with 400 (duplicate name)
    assert response2.status_code == 400
    assert (
        "already exists" in response2.json()["detail"].lower()
        or "duplicate" in response2.json()["detail"].lower()
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_expert_configuration_enable_disable(api_client, test_expert_data):
    """Test enabling and disabling expert configuration via API."""
    creds = test_expert_data

    # Create enabled expert via API
    create_response = api_client.post(
        "/experts",
        json={
            "name": creds["name"],
            "title": creds["title"],
            "description": creds["description"],
            "llm_provider": creds["llm_provider"],
            "llm_model": creds["llm_model"],
            "enabled": True,
        },
    )
    assert create_response.status_code == 200, f"Creation failed: {create_response.text}"
    expert_id = create_response.json()["id"]

    # Verify enabled via API
    get_response = api_client.get(f"/experts/{expert_id}")
    assert get_response.status_code == 200
    assert get_response.json()["enabled"] is True

    # Update to disabled via PUT endpoint
    put_response = api_client.put(f"/experts/{expert_id}", json={"enabled": False})

    assert put_response.status_code == 200, f"Update failed: {put_response.text}"

    # Verify disabled via API
    get_response2 = api_client.get(f"/experts/{expert_id}")
    assert get_response2.status_code == 200
    assert get_response2.json()["enabled"] is False

    # Update back to enabled via PUT endpoint
    put_response2 = api_client.put(f"/experts/{expert_id}", json={"enabled": True})

    assert put_response2.status_code == 200

    # Verify enabled again via API
    get_response3 = api_client.get(f"/experts/{expert_id}")
    assert get_response3.status_code == 200
    assert get_response3.json()["enabled"] is True
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_expert_configuration_list_all(api_client, test_expert_data):
    """Test listing all expert configurations via API."""
    creds = test_expert_data

    # Create multiple experts via API
    expert_ids = []
    for i in range(3):
        unique_id = str(uuid.uuid4())[:8]
        create_response = api_client.post(
            "/experts",
            json={
                "name": f"{creds['name']}_list_{i}_{unique_id}",
                "title": f"Expert {i} {unique_id}",
                "description": _build_description(f"{unique_id}_{i}", "list_all"),
                "llm_provider": creds["llm_provider"],
                "llm_model": creds["llm_model"],
                "enabled": True,
            },
        )
        assert create_response.status_code == 200
        expert_ids.append(create_response.json()["id"])

    # List all experts via API
    list_response = api_client.get("/experts")
    assert list_response.status_code == 200
    data = list_response.json()

    assert "experts" in data
    assert "count" in data
    assert len(data["experts"]) >= 3
    assert data["count"] >= 3
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_expert_configuration_list_enabled_only(api_client, test_expert_data):
    """Test listing only enabled expert configurations via API."""
    creds = test_expert_data

    # Create enabled and disabled experts via API
    unique_id1 = str(uuid.uuid4())[:8]
    create_response1 = api_client.post(
        "/experts",
        json={
            "name": f"{creds['name']}_enabled_{unique_id1}",
            "title": f"Enabled Expert {unique_id1}",
            "description": _build_description(unique_id1, "enabled_only"),
            "llm_provider": creds["llm_provider"],
            "llm_model": creds["llm_model"],
            "enabled": True,
        },
    )
    assert create_response1.status_code == 200

    unique_id2 = str(uuid.uuid4())[:8]
    create_response2 = api_client.post(
        "/experts",
        json={
            "name": f"{creds['name']}_disabled_{unique_id2}",
            "title": f"Disabled Expert {unique_id2}",
            "description": _build_description(unique_id2, "enabled_only"),
            "llm_provider": creds["llm_provider"],
            "llm_model": creds["llm_model"],
            "enabled": False,
        },
    )
    assert create_response2.status_code == 200

    # List only enabled experts via API
    list_response = api_client.get("/experts?enabled_only=true")
    assert list_response.status_code == 200
    data = list_response.json()

    assert "experts" in data
    assert "count" in data
    assert len(data["experts"]) >= 1
    assert all(expert["enabled"] for expert in data["experts"])
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_expert_configuration_system_prompt(api_client, test_expert_data):
    """Test expert configuration with system prompt via API."""
    creds = test_expert_data

    prompt_template = "You are a medical expert. Always be professional and accurate."

    create_response = api_client.post(
        "/experts",
        json={
            "name": creds["name"],
            "title": creds["title"],
            "description": creds["description"],
            "llm_provider": creds["llm_provider"],
            "llm_model": creds["llm_model"],
            "prompt_template": prompt_template,
            "enabled": True,
        },
    )

    assert create_response.status_code == 200
    expert_id = create_response.json()["id"]

    # Verify prompt template via API
    get_response = api_client.get(f"/experts/{expert_id}")
    assert get_response.status_code == 200
    data = get_response.json()

    # Verify prompt_template is in API response
    assert "prompt_template" in data
    assert data["prompt_template"] is not None
    assert "medical expert" in data["prompt_template"].lower()
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_expert_configuration_llm_providers(api_client, test_config):
    """Test expert configuration with different LLM providers via API."""
    # Get available providers from config or use defaults
    default_provider = get_config("llm.provider")
    default_model = get_config("llm.model")

    if not default_provider or not default_model:
        pytest.fail("LLM configuration not available")

    # Test with the configured provider
    providers_to_test = [default_provider]

    # Optionally test with other providers if configured
    openai_provider = get_config("llm.providers.openai.enabled")
    openrouter_provider = get_config("llm.providers.openrouter.enabled")

    secondary_provider = None
    tertiary_provider = None
    secondary_model = None
    tertiary_model = None
    if openai_provider:
        secondary_provider = get_config("test.llm.provider_secondary")
        secondary_model = get_config("test.llm.model_secondary")
        if not secondary_provider or not secondary_model:
            pytest.fail(
                "Missing test.llm.provider_secondary/test.llm.model_secondary for OpenAI provider tests"
            )
        providers_to_test.append(secondary_provider)
    if openrouter_provider:
        tertiary_provider = get_config("test.llm.provider_tertiary")
        tertiary_model = get_config("test.llm.model_tertiary")
        if not tertiary_provider or not tertiary_model:
            pytest.fail(
                "Missing test.llm.provider_tertiary/test.llm.model_tertiary for OpenRouter provider tests"
            )
        providers_to_test.append(tertiary_provider)

    created_experts = []
    for provider in providers_to_test:
        unique_id = str(uuid.uuid4())[:8]
        model = default_model
        if secondary_provider and provider == secondary_provider:
            model = secondary_model
        if tertiary_provider and provider == tertiary_provider:
            model = tertiary_model

        create_response = api_client.post(
            "/experts",
            json={
                "name": f"expert_{provider}_{unique_id}",
                "title": f"Expert {provider} {unique_id}",
                "description": _build_description(unique_id, f"provider_{provider}"),
                "llm_provider": provider,
                "llm_model": model,
                "enabled": True,
            },
        )

        if create_response.status_code == 200:
            created_experts.append(create_response.json()["id"])
        else:
            # Provider may not be configured, skip
            pytest.fail(f"Provider {provider} not configured: {create_response.text}")

    # Verify all created via API
    list_response = api_client.get("/experts")
    assert list_response.status_code == 200
    experts_data = list_response.json()["experts"]

    created_names = [f"expert_{p}_" for p in providers_to_test]
    found_experts = [e for e in experts_data if any(name in e["name"] for name in created_names)]
    assert len(found_experts) >= len(created_experts)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_expert_configuration_llm_parameters(api_client, test_expert_data):
    """Test expert configuration with all LLM parameters via API."""
    creds = test_expert_data

    # Get all LLM parameters from config
    llm_params = creds.get("llm_params", {})

    if not llm_params:
        pytest.fail("No LLM parameters configured")

    unique_id = str(uuid.uuid4())[:8]
    create_response = api_client.post(
        "/experts",
        json={
            "name": f"{creds['name']}_params_{unique_id}",
            "title": f"Expert with LLM Params {unique_id}",
            "description": _build_description(unique_id, "llm_params"),
            "llm_provider": creds["llm_provider"],
            "llm_model": creds["llm_model"],
            "llm_params": llm_params,
            "enabled": True,
        },
    )

    assert create_response.status_code == 200
    expert_id = create_response.json()["id"]

    # Verify LLM parameters via API
    get_response = api_client.get(f"/experts/{expert_id}")
    assert get_response.status_code == 200
    data = get_response.json()

    # Verify llm_params is in API response
    assert "llm_params" in data
    stored_params = data["llm_params"]

    if stored_params and llm_params:
        # Verify key parameters are present
        if "temperature" in llm_params:
            assert "temperature" in stored_params
            assert stored_params.get("temperature") == llm_params["temperature"]
        if "max_tokens" in llm_params:
            assert "max_tokens" in stored_params
            assert stored_params.get("max_tokens") == llm_params["max_tokens"]
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_expert_not_found(api_client):
    """Test expert not found error via API."""
    # Try to get non-existent expert
    response = api_client.get("/experts/99999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.heavy]

