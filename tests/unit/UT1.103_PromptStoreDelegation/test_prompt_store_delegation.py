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
Unit Test: UT1.103 - PromptManager optional shared-store delegation (W28B-319 / D5)

License: Apache 2.0
Ownership: Cloud Dog
Description: Proves the prompt-engineering (D5) opt-in adoption:
  - UT_PROMPT_DEFAULT_UNCHANGED: with no injected store, PromptManager keeps its
    existing DB-backed behaviour exactly (default path is untouched).
  - UT_PROMPT_DELEGATE_OPTIN: with an injected cloud_dog_agent.prompts
    InMemoryPromptStore, template CRUD delegates to the shared store and
    round-trips (create -> get -> list -> update -> delete) without touching the DB.

Related Requirements: FR1.1
Related Tasks: T009
Related Architecture: CC3.1.2
Related Tests: UT1.6, UT1.100
"""

import json

import pytest

from cloud_dog_agent.prompts import InMemoryPromptStore, PromptStore
from src.core.prompt.manager import PromptManager
from src.database.models import PromptTemplate as DbPromptTemplate


pytestmark = [pytest.mark.unit, pytest.mark.pure, pytest.mark.fast]


# --------------------------------------------------------------------------- #
# UT_PROMPT_DEFAULT_UNCHANGED — no store injected => existing behaviour exactly #
# --------------------------------------------------------------------------- #
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")

def test_prompt_default_unchanged_store_is_none_by_default():
    """Constructing PromptManager without a store leaves the store opt-out (None)."""
    manager = PromptManager()
    assert manager.store is None

    manager_with_db = PromptManager(db=None)
    assert manager_with_db.store is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_prompt_default_unchanged_render_template_behaviour():
    """The pure render path is unaffected by the new optional store parameter."""
    manager = PromptManager()
    rendered = manager.render_template(
        "Hello {{ name }}, role {{ role }}", {"name": "Alice", "role": "admin"}
    )
    assert rendered == "Hello Alice, role admin"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_prompt_default_unchanged_db_crud_uses_db_models(db_session):
    """Without a store, CRUD hits the DB and returns SQLAlchemy model rows."""
    manager = PromptManager(db_session)
    created = manager.create_prompt_template(
        name="default-path",
        content="Body {{ x }}",
        variables_schema={"type": "object"},
        created_by="tester",
    )
    # Default path returns the real DB-backed model (NOT the store view).
    assert isinstance(created, DbPromptTemplate)
    assert created.id is not None
    assert created.name == "default-path"
    assert created.version == 1

    fetched = manager.get_prompt_template(created.id)
    assert isinstance(fetched, DbPromptTemplate)
    assert fetched.id == created.id
    assert fetched.content == "Body {{ x }}"

    listed = manager.list_prompt_templates()
    assert any(t.id == created.id for t in listed)

    updated = manager.update_prompt_template(created.id, content="Body {{ y }}")
    assert updated.content == "Body {{ y }}"

    assert manager.delete_prompt_template(created.id) is True
    assert manager.get_prompt_template(created.id) is None


# --------------------------------------------------------------------------- #
# UT_PROMPT_DELEGATE_OPTIN — injected store => CRUD delegates and round-trips   #
# --------------------------------------------------------------------------- #

def _new_store_manager():
    store = InMemoryPromptStore()
    # The shared store satisfies the runtime-checkable PromptStore protocol.
    assert isinstance(store, PromptStore)
    return PromptManager(db=None, store=store), store
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_prompt_delegate_optin_store_is_wired():
    manager, store = _new_store_manager()
    assert manager.store is store
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_prompt_delegate_optin_create_does_not_touch_db():
    """With a store injected, create must not require a DB session at all."""
    # db=None and no real DB env: if it touched the DB this would raise.
    manager, store = _new_store_manager()
    view = manager.create_prompt_template(
        name="delegated", content="Hi {greeting}", created_by="alice"
    )
    # Returned object is the DB-shaped store view, NOT a SQLAlchemy row.
    assert not isinstance(view, DbPromptTemplate)
    assert view.name == "delegated"
    assert view.version == 1
    assert view.content == "Hi {greeting}"
    assert view.created_by == "alice"
    # The body really landed in the shared store.
    import asyncio

    tmpl = asyncio.run(store.get_template("delegated"))
    assert tmpl is not None
    assert tmpl.latest_version == 1
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_prompt_delegate_optin_full_round_trip():
    """create -> get -> list -> update(new version) -> delete via the store."""
    manager, store = _new_store_manager()

    created = manager.create_prompt_template(
        name="rt", content="v1 {a}", variables_schema={"variables": ["a"]}, created_by="bob"
    )
    assert created.version == 1
    schema = json.loads(created.variables_schema)
    assert schema.get("variables") == ["a"]

    fetched = manager.get_prompt_template(created.id)
    assert fetched is not None
    assert fetched.name == "rt"
    assert fetched.content == "v1 {a}"

    listed = manager.list_prompt_templates()
    assert [t.name for t in listed] == ["rt"]

    # Content edit -> store appends an immutable version; latest resolves to v2.
    updated = manager.update_prompt_template(created.id, content="v2 {a} {b}")
    assert updated is not None
    assert updated.content == "v2 {a} {b}"
    assert updated.version == 2

    import asyncio

    versions = asyncio.run(store.list_versions("rt"))
    assert [v.version for v in versions] == [1, 2]
    assert versions[0].body == "v1 {a}"
    assert versions[1].body == "v2 {a} {b}"

    # Delete removes it from the store.
    assert manager.delete_prompt_template(created.id) is True
    assert manager.get_prompt_template(created.id) is None
    assert manager.list_prompt_templates() == []
    assert asyncio.run(store.get_template("rt")) is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_prompt_delegate_optin_recreate_existing_name_appends_version():
    """Re-creating an existing name appends a new immutable version in the store."""
    manager, store = _new_store_manager()
    manager.create_prompt_template(name="dup", content="first")
    second = manager.create_prompt_template(name="dup", content="second")
    assert second.name == "dup"
    assert second.version == 2

    import asyncio

    versions = asyncio.run(store.list_versions("dup"))
    assert [v.body for v in versions] == ["first", "second"]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_prompt_delegate_optin_get_unknown_returns_none():
    manager, _store = _new_store_manager()
    assert manager.get_prompt_template(9999) is None
    assert manager.update_prompt_template(9999, content="x") is None
    assert manager.delete_prompt_template(9999) is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_prompt_delegate_optin_list_filter_by_name():
    manager, _store = _new_store_manager()
    manager.create_prompt_template(name="alpha", content="a")
    manager.create_prompt_template(name="beta", content="b")
    only = manager.list_prompt_templates(name="beta")
    assert [t.name for t in only] == ["beta"]
