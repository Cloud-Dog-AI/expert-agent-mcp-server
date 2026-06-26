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
Unit Test: UT1.1 - Configuration Manager Parsing and Validation

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for configuration manager parsing and validation

Related Requirements: NF1.5
Related Tasks: T003
Related Architecture: CM1.1
Related Tests: UT1.1

Recent Changes:
- Initial implementation
"""

import os
from src.config.loader import ConfigLoader, load_config, get_config
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_loader_initialization():
    """Test that ConfigLoader can be initialized."""
    loader = ConfigLoader()
    assert loader is not None
    assert isinstance(loader, ConfigLoader)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_loader_loads_defaults():
    """Test that config loader loads defaults.yaml."""
    load_config.cache_clear()
    loader = ConfigLoader()
    loader._config = None  # Force reload
    config = loader.load()

    assert config is not None
    assert isinstance(config, dict)
    # Should have at least some basic structure
    assert "llm" in config or "app" in config or "db" in config
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_loader_get_path():
    """Test getting config value by dot notation path."""
    load_config.cache_clear()
    loader = ConfigLoader()
    loader._config = None  # Force reload

    # Test getting a value that should exist
    value = loader.get("llm.provider", "default")
    assert value is not None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_loader_get_nonexistent():
    """Test getting non-existent config value returns default."""
    load_config.cache_clear()
    loader = ConfigLoader()
    loader._config = None  # Force reload

    value = loader.get("nonexistent.key.path", "default_value")
    assert value == "default_value"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_loader_reload():
    """Test that reload clears cache and reloads config."""
    load_config.cache_clear()
    loader = ConfigLoader()
    loader.load()

    # Modify environment and reload
    original_value = os.environ.get("CLOUD_DOG__EXPERT__TEST__KEY")
    os.environ["CLOUD_DOG__EXPERT__TEST__KEY"] = "test_value"

    try:
        config2 = loader.reload()
        assert config2 is not None
        # Should have the new value
        assert loader.get("test.key") == "test_value"
    finally:
        if original_value:
            os.environ["CLOUD_DOG__EXPERT__TEST__KEY"] = original_value
        elif "CLOUD_DOG__EXPERT__TEST__KEY" in os.environ:
            del os.environ["CLOUD_DOG__EXPERT__TEST__KEY"]
        load_config.cache_clear()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_parsing_from_yaml():
    """Test parsing configuration from YAML files."""
    load_config.cache_clear()
    config = load_config()

    assert config is not None
    assert isinstance(config, dict)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_parsing_from_env_file():
    """Test parsing configuration from environment file."""
    load_config.cache_clear()

    # Set TESTING mode to use env-test
    original_testing = os.environ.get("TESTING", "")
    os.environ["TESTING"] = "true"

    try:
        load_config.cache_clear()
        config = load_config()
        assert config is not None
    finally:
        if original_testing:
            os.environ["TESTING"] = original_testing
        elif "TESTING" in os.environ:
            del os.environ["TESTING"]
        load_config.cache_clear()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_validation_hierarchy():
    """Test that configuration hierarchy is respected (env > .env > config.yaml > defaults.yaml)."""
    from src.config.loader import ConfigLoader

    # Use a test key that's unlikely to be in env-test
    test_key = "CLOUD_DOG__EXPERT__TEST__HIERARCHY__KEY"
    original_value = os.environ.get(test_key)
    os.environ[test_key] = "Env Override"

    try:
        # Clear cache and create new loader instance
        load_config.cache_clear()
        loader = ConfigLoader()
        loader._config = None  # Force reload
        loader.reload()

        test_value = loader.get("test.hierarchy.key", "")
        # Environment variable should override defaults
        assert test_value == "Env Override", f"Expected 'Env Override', got '{test_value}'"
    finally:
        if original_value:
            os.environ[test_key] = original_value
        elif test_key in os.environ:
            del os.environ[test_key]
        load_config.cache_clear()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_validation_types():
    """Test that configuration values are parsed with correct types."""
    load_config.cache_clear()

    # Test string value
    os.environ["CLOUD_DOG__EXPERT__TEST__STRING"] = "test_string"
    # Test boolean value
    os.environ["CLOUD_DOG__EXPERT__TEST__BOOL"] = "true"
    # Test integer value
    os.environ["CLOUD_DOG__EXPERT__TEST__INT"] = "42"

    try:
        load_config.cache_clear()
        loader = ConfigLoader()
        loader._config = None  # Force reload

        string_val = loader.get("test.string", "")
        bool_val = loader.get("test.bool", False)
        int_val = loader.get("test.int", 0)

        assert string_val == "test_string"
        assert bool_val is True  # cloud_dog_config coerces "true" → True
        assert int_val == 42  # cloud_dog_config coerces "42" → 42
    finally:
        for key in [
            "CLOUD_DOG__EXPERT__TEST__STRING",
            "CLOUD_DOG__EXPERT__TEST__BOOL",
            "CLOUD_DOG__EXPERT__TEST__INT",
        ]:
            if key in os.environ:
                del os.environ[key]
        load_config.cache_clear()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_get_config_function():
    """Test get_config convenience function."""
    load_config.cache_clear()

    # Test getting full config
    config = get_config()
    assert config is not None
    assert isinstance(config, dict)

    # Test getting specific path
    value = get_config("llm.provider")
    assert value is not None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_nested_access():
    """Test accessing nested configuration values."""
    load_config.cache_clear()
    loader = ConfigLoader()
    loader._config = None  # Force reload

    # Test nested access
    value = loader.get("llm.base_url", None)
    # Value might be None if not set, but should not raise exception
    assert value is None or isinstance(value, str)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.pure, pytest.mark.fast]

