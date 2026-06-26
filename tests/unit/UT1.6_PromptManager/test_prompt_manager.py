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
Unit Test: UT1.6 - Prompt Manager Template Rendering

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for prompt manager template rendering and variable substitution

Related Requirements: FR1.1
Related Tasks: T009
Related Architecture: CC3.1.2
Related Tests: UT1.6

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.prompt.manager import PromptManager


@pytest.fixture
def prompt_manager():
    """Create prompt manager instance."""
    return PromptManager()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_template_rendering_basic(prompt_manager):
    """Test basic template rendering with simple variables."""
    template = "Hello {{ name }}, welcome to {{ system }}!"
    context = {"name": "Alice", "system": "Expert Agent"}

    result = prompt_manager.render_template(template, context)

    assert result == "Hello Alice, welcome to Expert Agent!"
    assert "{{" not in result
    assert "}}" not in result
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_template_rendering_missing_variable(prompt_manager):
    """Test template rendering with missing variable."""
    template = "Hello {{ name }}, your role is {{ role }}."
    context = {"name": "Bob"}

    # Jinja2 will leave {{ role }} as-is if variable is missing
    result = prompt_manager.render_template(template, context)

    assert "Hello Bob" in result
    assert "your role is" in result
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_template_rendering_nested_variables(prompt_manager):
    """Test template rendering with nested variable access."""
    template = "User {{ user.name }} ({{ user.id }}) has role {{ user.role }}."
    context = {"user": {"name": "Charlie", "id": 123, "role": "admin"}}

    result = prompt_manager.render_template(template, context)

    assert "User Charlie" in result
    assert "123" in result
    assert "has role admin" in result
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_template_rendering_default_values(prompt_manager):
    """Test template rendering with default values."""
    template = "Temperature: {{ temperature | default(0.7) }}, Max tokens: {{ max_tokens | default(1024) }}"
    context = {"temperature": 0.9}

    result = prompt_manager.render_template(template, context)

    assert "Temperature: 0.9" in result or "0.9" in result
    assert "1024" in result
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_template_rendering_system_prompt(prompt_manager):
    """Test system prompt template rendering."""
    template = """You are {{ expert_name }}, a {{ expert_type }} expert.
Your expertise includes: {{ expertise }}.
Always be {{ tone }} and {{ style }}."""

    context = {
        "expert_name": "Dr. Smith",
        "expert_type": "medical",
        "expertise": "cardiology, general medicine",
        "tone": "professional",
        "style": "concise",
    }

    result = prompt_manager.render_template(template, context)

    assert "Dr. Smith" in result
    assert "medical" in result
    assert "cardiology" in result
    assert "professional" in result
    assert "concise" in result
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_template_rendering_special_characters(prompt_manager):
    """Test template rendering with special characters."""
    template = "Message: {{ message }}"
    context = {"message": "Hello! This has \"quotes\" and 'apostrophes'."}

    result = prompt_manager.render_template(template, context)

    assert "Hello!" in result
    assert "quotes" in result
    assert "apostrophes" in result
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_template_rendering_empty_template(prompt_manager):
    """Test rendering empty template."""
    result = prompt_manager.render_template("", {})
    assert result == ""
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_template_rendering_no_variables(prompt_manager):
    """Test rendering template with no variables."""
    template = "This is a static message with no variables."
    result = prompt_manager.render_template(template, {})

    assert result == template
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_template_rendering_multiple_occurrences(prompt_manager):
    """Test template with same variable appearing multiple times."""
    template = "{{ name }} said: '{{ message }}'. Then {{ name }} added: '{{ message }}'."
    context = {"name": "Alice", "message": "Hello"}

    result = prompt_manager.render_template(template, context)

    assert result.count("Alice") == 2
    assert result.count("Hello") == 2

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.pure, pytest.mark.fast]

