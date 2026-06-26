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
Unit Test: UT1.11 - Safety and Moderation Filters

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for safety and moderation filters

Related Requirements: FR1.1
Related Tasks: T011
Related Architecture: CC3.1.2
Related Tests: UT1.11

Recent Changes:
- Initial implementation
"""

from src.core.llm.safety import SafetyFilter
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_safety_filter_initialization():
    """Test safety filter can be initialized."""
    filter = SafetyFilter()
    assert filter is not None
    assert len(filter.compiled_patterns) > 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_check_content_safe():
    """Test checking safe content."""
    filter = SafetyFilter()

    safe_content = "This is a normal conversation about technology."
    result = filter.check_content(safe_content)

    assert result["safe"] is True
    assert len(result["violations"]) == 0
    assert result["filtered_content"] == safe_content
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_check_content_unsafe():
    """Test checking unsafe content."""
    filter = SafetyFilter()

    unsafe_content = "This message contains a weapon reference."
    result = filter.check_content(unsafe_content)

    # Should detect unsafe pattern
    assert result["safe"] is False
    assert len(result["violations"]) > 0
    assert "[REDACTED]" in result["filtered_content"]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_check_content_multiple_violations():
    """Test checking content with multiple violations."""
    filter = SafetyFilter()

    unsafe_content = "This contains both weapon and hack references."
    result = filter.check_content(unsafe_content)

    assert result["safe"] is False
    assert len(result["violations"]) >= 1
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_filter_messages():
    """Test filtering messages."""
    filter = SafetyFilter()

    messages = [
        {"role": "user", "content": "Normal message"},
        {"role": "user", "content": "This contains a weapon reference."},
        {"role": "assistant", "content": "Safe response"},
    ]

    filtered = filter.filter_messages(messages)

    assert len(filtered) == len(messages)
    # Unsafe message should be filtered
    for msg in filtered:
        if "weapon" in msg.get("content", "").lower():
            assert "[REDACTED]" in msg["content"]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_filter_messages_all_safe():
    """Test filtering messages when all are safe."""
    filter = SafetyFilter()

    messages = [
        {"role": "user", "content": "Normal message 1"},
        {"role": "assistant", "content": "Normal response"},
        {"role": "user", "content": "Normal message 2"},
    ]

    filtered = filter.filter_messages(messages)

    # All messages should remain unchanged
    assert len(filtered) == len(messages)
    assert all(msg["content"] == messages[i]["content"] for i, msg in enumerate(filtered))
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_check_content_case_insensitive():
    """Test that content checking is case insensitive."""
    filter = SafetyFilter()

    # Test with uppercase
    result1 = filter.check_content("This contains WEAPON reference.")
    # Test with lowercase
    result2 = filter.check_content("This contains weapon reference.")

    # Both should be detected
    assert result1["safe"] == result2["safe"]
    assert result1["safe"] is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_check_content_empty():
    """Test checking empty content."""
    filter = SafetyFilter()

    result = filter.check_content("")

    assert result["safe"] is True
    assert result["filtered_content"] == ""
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_filter_messages_empty_list():
    """Test filtering empty message list."""
    filter = SafetyFilter()

    filtered = filter.filter_messages([])

    assert filtered == []
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_violations_list():
    """Test that violations list contains detected terms."""
    filter = SafetyFilter()

    content = "This message mentions a weapon."
    result = filter.check_content(content)

    if not result["safe"]:
        assert len(result["violations"]) > 0
        # Violations should be the detected terms
        assert all(isinstance(v, str) for v in result["violations"])

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.pure, pytest.mark.fast]

