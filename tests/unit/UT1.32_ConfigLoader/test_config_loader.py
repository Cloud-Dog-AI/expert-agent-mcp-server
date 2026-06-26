import pytest
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
Unit Test: UT1.32 - Config Loader Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for configuration loading

Related Requirements: NF1.1
Related Tasks: T001
Related Architecture: CM1.1
Related Tests: UT1.32

Recent Changes:
- Initial implementation
"""

import os
from src.config.loader import load_config, get_config
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-034")


def test_config_loader_basic():
    """Test basic configuration loading."""
    load_config.cache_clear()
    config = load_config()

    assert config is not None
    assert isinstance(config, dict)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-034")


def test_get_config_basic():
    """Test getting configuration values."""
    load_config.cache_clear()

    # Missing key should return None
    value = get_config("nonexistent.key")
    assert value is None

    # Test existing key
    app_name = get_config("app.name")
    assert isinstance(app_name, str)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-034")


def test_config_hierarchy():
    """Test configuration hierarchy (env > .env > config.yaml > defaults.yaml)."""
    from src.config.loader import ConfigLoader

    # Use a test key that's unlikely to be in env-test
    test_key = "CLOUD_DOG__EXPERT__TEST__HIERARCHY__KEY"
    original_value = os.environ.get(test_key)
    os.environ[test_key] = "Test App"

    try:
        # Clear cache and create new loader instance
        load_config.cache_clear()
        loader = ConfigLoader()
        loader._config = None  # Force reload
        loader.reload()

        test_value = loader.get("test.hierarchy.key")
        # Environment variable should override defaults
        assert test_value == "Test App", f"Expected 'Test App', got '{test_value}'"
    finally:
        # Clean up
        if original_value:
            os.environ[test_key] = original_value
        elif test_key in os.environ:
            del os.environ[test_key]
        load_config.cache_clear()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-034")


def test_config_with_env_test():
    """Test configuration loads from env-test when TESTING=true."""
    load_config.cache_clear()

    # Set TESTING environment variable
    original_testing = os.environ.get("TESTING", "")
    os.environ["TESTING"] = "true"

    try:
        load_config.cache_clear()
        config = load_config()

        # Should load from env-test if it exists
        assert config is not None

    finally:
        # Restore
        if original_testing:
            os.environ["TESTING"] = original_testing
        elif "TESTING" in os.environ:
            del os.environ["TESTING"]
        load_config.cache_clear()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-034")


def test_config_llm_settings():
    """Test LLM configuration loading."""
    load_config.cache_clear()

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")

    assert isinstance(llm_provider, str)
    assert isinstance(llm_model, str)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-034")


def test_config_database_settings():
    """Test database configuration loading."""
    load_config.cache_clear()

    db_uri = get_config("db.uri")

    assert isinstance(db_uri, str)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-034")


def test_config_env_overrides_default_api_port():
    """Test that CLOUD_DOG__EXPERT__API_SERVER__PORT overrides file/default config."""
    test_key = "CLOUD_DOG__EXPERT__API_SERVER__PORT"
    original_value = os.environ.get(test_key)
    os.environ[test_key] = "19999"
    try:
        load_config.cache_clear()
        port = get_config("api_server.port")
        assert int(port) == 19999
    finally:
        if original_value is None:
            os.environ.pop(test_key, None)
        else:
            os.environ[test_key] = original_value
        load_config.cache_clear()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-034")


def test_expert_test_overrides_merge_into_top_level_test():
    """Test expert.test env overrides are surfaced through top-level test config."""
    env_updates = {
        "TESTING": "true",
        "CLOUD_DOG_ENV_FILES": "tests/env-UT",
        "CLOUD_DOG__TEST__HTTP_TIMEOUT_SECONDS": "60",
        "CLOUD_DOG__EXPERT__TEST__HTTP_TIMEOUT_SECONDS": "300",
        "CLOUD_DOG__TEST__LLM_HTTP_TIMEOUT_SECONDS": "120",
        "CLOUD_DOG__EXPERT__TEST__LLM_HTTP_TIMEOUT_SECONDS": "480",
    }
    original_values = {key: os.environ.get(key) for key in env_updates}

    try:
        for key, value in env_updates.items():
            os.environ[key] = value

        load_config.cache_clear()
        config = load_config()

        assert config["expert"]["test"]["http_timeout_seconds"] == 300
        assert config["expert"]["test"]["llm_http_timeout_seconds"] == 480
        assert config["test"]["http_timeout_seconds"] == 300
        assert config["test"]["llm_http_timeout_seconds"] == 480
    finally:
        for key, original_value in original_values.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
        load_config.cache_clear()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-034")


def test_expert_agent_prefix_base_path_overrides_runtime_sections():
    """Test EXPERT_AGENT-prefixed env overrides flow into runtime server config."""
    env_updates = {
        "CLOUD_DOG__EXPERT_AGENT__API_SERVER__BASE_PATH": "/api/v2",
    }
    original_values = {key: os.environ.get(key) for key in env_updates}

    try:
        for key, value in env_updates.items():
            os.environ[key] = value

        load_config.cache_clear()
        config = load_config()

        assert config["expert"]["api_server"]["base_path"] == "/api/v2"
        assert config["api_server"]["base_path"] == "/api/v2"
        assert config["web_server"]["api_base_url"].endswith("/api/v2")
    finally:
        for key, original_value in original_values.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
        load_config.cache_clear()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.fast]
