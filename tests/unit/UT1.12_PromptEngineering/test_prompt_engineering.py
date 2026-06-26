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
Unit Test: UT1.12 - Prompt Engineering Utilities

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for prompt engineering utilities

Related Requirements: FR1.1
Related Tasks: T012
Related Architecture: CC3.1.4
Related Tests: UT1.12

Recent Changes:
- Initial implementation
"""

from src.core.prompts.engineering import PromptEngineer
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_prompt_engineer_initialization():
    """Test prompt engineer can be initialized."""
    engineer = PromptEngineer()
    assert engineer is not None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_calculate_entropy():
    """Test entropy calculation."""
    engineer = PromptEngineer()

    # High entropy (diverse characters)
    high_entropy = engineer.calculate_entropy("abcdefghijklmnopqrstuvwxyz")
    assert high_entropy > 0

    # Low entropy (repeated characters)
    low_entropy = engineer.calculate_entropy("aaaaaa")
    assert low_entropy < high_entropy

    # Empty string
    assert engineer.calculate_entropy("") == 0.0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_check_prompt_entropy_valid():
    """Test checking prompt with sufficient entropy."""
    engineer = PromptEngineer()

    title = "Comprehensive Expert Configuration for Technical Support"
    description = "This expert configuration provides detailed technical support for software development, including debugging, code review, and architecture guidance."

    result = engineer.check_prompt_entropy(title, description, min_entropy=2.0)

    assert result["valid"] is True
    assert result["title_entropy"] >= 2.0
    assert result["description_entropy"] >= 2.0
    assert len(result["recommendations"]) == 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_check_prompt_entropy_low_title():
    """Test checking prompt with low title entropy."""
    engineer = PromptEngineer()

    title = "aa"  # Very low entropy
    description = "This is a comprehensive description with many different words and concepts."

    result = engineer.check_prompt_entropy(title, description, min_entropy=2.0)

    assert result["valid"] is False
    assert result["title_entropy"] < 2.0
    assert len(result["recommendations"]) > 0
    assert any("title" in rec.lower() for rec in result["recommendations"])
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_check_prompt_entropy_low_description():
    """Test checking prompt with low description entropy."""
    engineer = PromptEngineer()

    title = "Comprehensive Expert Configuration"
    description = "aa"  # Very low entropy

    result = engineer.check_prompt_entropy(title, description, min_entropy=2.0)

    assert result["valid"] is False
    assert result["description_entropy"] < 2.0
    assert len(result["recommendations"]) > 0
    assert any("description" in rec.lower() for rec in result["recommendations"])
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_optimize_prompt():
    """Test prompt optimization."""
    engineer = PromptEngineer()

    prompt = "This is a test prompt that needs optimization."
    result = engineer.optimize_prompt(prompt)

    assert "optimized" in result
    assert "suggestions" in result
    assert isinstance(result["suggestions"], list)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_optimize_prompt_with_target_length():
    """Test prompt optimization with target length."""
    engineer = PromptEngineer()

    long_prompt = "A" * 500  # Very long prompt
    result = engineer.optimize_prompt(long_prompt, target_length=100)

    assert "suggestions" in result
    # Should suggest shortening if over target
    if len(long_prompt) > 100:
        assert any("shorten" in s.lower() for s in result["suggestions"])
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_optimize_prompt_structure():
    """Test prompt optimization for structure."""
    engineer = PromptEngineer()

    unstructured_prompt = "This is a prompt without structure."
    result = engineer.optimize_prompt(unstructured_prompt)

    # Should suggest structure if missing
    assert any("structure" in s.lower() for s in result["suggestions"])
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_entropy_consistency():
    """Test that entropy calculation is consistent."""
    engineer = PromptEngineer()

    text = "Test text for entropy calculation"
    entropy1 = engineer.calculate_entropy(text)
    entropy2 = engineer.calculate_entropy(text)

    # Should be consistent
    assert entropy1 == entropy2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_check_prompt_entropy_empty():
    """Test checking prompt with empty strings."""
    engineer = PromptEngineer()

    result = engineer.check_prompt_entropy("", "", min_entropy=2.0)

    assert result["valid"] is False
    assert result["title_entropy"] == 0.0
    assert result["description_entropy"] == 0.0

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.pure, pytest.mark.fast]

