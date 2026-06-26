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
Unit Test: UT1.13 - Entropy Checking for Prompt Titles/Descriptions

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for entropy checking

Related Requirements: FR1.1
Related Tasks: T012
Related Architecture: CC3.1.4
Related Tests: UT1.13

Recent Changes:
- Initial implementation
"""

from src.core.prompts.engineering import PromptEngineer
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_entropy_checking_basic():
    """Test basic entropy checking functionality."""
    engineer = PromptEngineer()

    title = "Test Title"
    description = "Test Description"

    result = engineer.check_prompt_entropy(title, description)

    assert "valid" in result
    assert "title_entropy" in result
    assert "description_entropy" in result
    assert "min_entropy" in result
    assert "recommendations" in result
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_entropy_checking_high_entropy():
    """Test entropy checking with high entropy text."""
    engineer = PromptEngineer()

    title = "Comprehensive Expert Configuration for Advanced Technical Support"
    description = "This expert configuration provides detailed technical support including debugging, code review, architecture guidance, and best practices."

    result = engineer.check_prompt_entropy(title, description, min_entropy=2.0)

    assert result["title_entropy"] > 2.0
    assert result["description_entropy"] > 2.0
    assert result["valid"] is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_entropy_checking_low_entropy():
    """Test entropy checking with low entropy text."""
    engineer = PromptEngineer()

    title = "aa"
    description = "bb"

    result = engineer.check_prompt_entropy(title, description, min_entropy=2.0)

    assert result["title_entropy"] < 2.0
    assert result["description_entropy"] < 2.0
    assert result["valid"] is False
    assert len(result["recommendations"]) >= 2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_entropy_checking_mixed():
    """Test entropy checking with mixed entropy."""
    engineer = PromptEngineer()

    title = "aa"  # Low entropy
    description = "Comprehensive expert configuration with many details"  # High entropy

    result = engineer.check_prompt_entropy(title, description, min_entropy=2.0)

    assert result["title_entropy"] < 2.0
    assert result["description_entropy"] >= 2.0
    assert result["valid"] is False
    assert len(result["recommendations"]) >= 1
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_entropy_checking_custom_threshold():
    """Test entropy checking with custom threshold."""
    engineer = PromptEngineer()

    title = "Test Title"
    description = "Test Description"

    # With low threshold, should pass
    result_low = engineer.check_prompt_entropy(title, description, min_entropy=1.0)

    # With high threshold, might fail
    result_high = engineer.check_prompt_entropy(title, description, min_entropy=5.0)

    assert result_low["min_entropy"] == 1.0
    assert result_high["min_entropy"] == 5.0
    # Low threshold should be easier to pass
    assert result_low["valid"] >= result_high["valid"]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_entropy_recommendations_format():
    """Test that recommendations are properly formatted."""
    engineer = PromptEngineer()

    title = "aa"
    description = "bb"

    result = engineer.check_prompt_entropy(title, description, min_entropy=2.0)

    assert isinstance(result["recommendations"], list)
    assert all(isinstance(rec, str) for rec in result["recommendations"])
    assert all(len(rec) > 0 for rec in result["recommendations"])
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_entropy_checking_special_characters():
    """Test entropy checking with special characters."""
    engineer = PromptEngineer()

    title = "Test!@#$%^&*()"
    description = "Description with special chars: !@#$%"

    result = engineer.check_prompt_entropy(title, description)

    # Should handle special characters
    assert "title_entropy" in result
    assert "description_entropy" in result
    assert result["title_entropy"] > 0
    assert result["description_entropy"] > 0

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.pure, pytest.mark.fast]

