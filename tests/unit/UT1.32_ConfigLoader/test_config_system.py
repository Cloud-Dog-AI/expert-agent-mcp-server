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
Configuration System Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for configuration management system

Related Requirements: NF1.5
Related Tasks: T110
Related Architecture: CM1.1
Related Tests: UT1.32

Recent Changes:
- Initial implementation
"""

import os
from src.config.loader import ConfigLoader, get_config
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_loader_loads_defaults():
    """Test that config loader loads defaults.yaml and test config."""
    from src.config.loader import load_config

    load_config.cache_clear()

    loader = ConfigLoader()
    loader._config = None  # Force reload
    config = loader.load()

    assert config is not None
    assert "llm" in config
    assert config["llm"]["provider"] == "ollama"
    # In test mode, should use env-test settings (or default if not set)
    base_url = config["llm"].get("base_url", "")
    # Just verify it's a string, not hardcoded to specific value
    assert isinstance(base_url, str), f"Expected string, got '{type(base_url)}'"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_loader_get_path():
    """Test getting config value by path."""
    from src.config.loader import load_config

    load_config.cache_clear()

    loader = ConfigLoader()
    loader._config = None  # Force reload
    base_url = loader.get("llm.base_url")

    # In test mode, should use env-test settings (or default if not set)
    # Just verify it's a string, not hardcoded to specific value
    assert isinstance(base_url, str), f"Expected string, got '{type(base_url)}'"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_config_loader_env_override():
    """Test that environment variables override defaults."""
    os.environ["CLOUD_DOG__EXPERT__LLM__BASE_URL"] = "http://test:11434"

    loader = ConfigLoader()
    loader.reload()  # Clear cache
    base_url = loader.get("llm.base_url")

    assert base_url == "http://test:11434"

    # Cleanup
    del os.environ["CLOUD_DOG__EXPERT__LLM__BASE_URL"]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-037")


def test_get_config_function():
    """Test get_config convenience function."""
    from src.config.loader import load_config

    # Clear cache to force reload
    load_config.cache_clear()

    # Test that get_config works with test config
    config = get_config()
    assert config is not None
    assert "llm" in config

    # In test mode, should use env-test settings (or default if not set)
    base_url = get_config("llm.base_url")
    # Just verify it's a string, not hardcoded to specific value
    assert isinstance(base_url, str), f"Expected string, got '{type(base_url)}'"

    # Note: OS env override is tested in test_config_loader_env_override
    # This test focuses on get_config convenience function working with test config

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.llm, pytest.mark.fast]

