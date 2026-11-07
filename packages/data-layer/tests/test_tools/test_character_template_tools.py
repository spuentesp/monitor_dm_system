"""Tests for the portable character-template tools (G-6 / P&F §6).

The templates share the ``characters`` collection with standalone characters,
so these tests pin the two things that make that safe: a template is always
marked (``is_template``), and every query is marker-scoped — a plain character
document is never listed, updated, deleted or counted as a template.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

from monitor_data.schemas.character_templates import (
    CharacterTemplateCreate,
    CharacterTemplateFilter,
    CharacterTemplateUpdate,
)
from monitor_data.tools.mongodb_tools.character_templates import (
    mongodb_create_character_template,
    mongodb_delete_character_template,
    mongodb_get_character_template,
    mongodb_increment_character_template_usage,
    mongodb_list_character_templates,
    mongodb_update_character_template,
)


class _FakeCursor:
    """Minimal cursor supporting the chain the tools use."""

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def sort(self, key: str, direction: int = 1) -> _FakeCursor:
        self._docs.sort(key=lambda d: str(d.get(key) or ""), reverse=direction < 0)
        return self

    def skip(self, count: int) -> _FakeCursor:
        self._docs = self._docs[count:]
        return self

    def limit(self, count: int) -> _FakeCursor:
        self._docs = self._docs[:count]
        return self

    def __iter__(self):
        return iter(self._docs)


class _FakeCharactersCollection:
    """In-memory stand-in for the ``characters`` collection."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, condition in query.items():
            value = doc.get(key)
            if isinstance(condition, dict):
                if "$ne" in condition and value == condition["$ne"]:
                    return False
                if "$regex" in condition:
                    if value is None or not re.search(condition["$regex"], str(value), re.IGNORECASE):
                        return False
            elif value != condition:
                return False
        return True

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for doc in self.docs.values():
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query: dict[str, Any]) -> _FakeCursor:
        return _FakeCursor([dict(d) for d in self.docs.values() if self._matches(d, query)])

    def count_documents(self, query: dict[str, Any]) -> int:
        return sum(1 for d in self.docs.values() if self._matches(d, query))

    def insert_one(self, doc: dict[str, Any]) -> None:
        self.docs[str(doc["id"])] = dict(doc)

    def update_one(self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False) -> None:
        doc = self.find_one(query)
        if doc is None:
            return
        for key, value in update.get("$set", {}).items():
            doc[key] = value
        for key, value in update.get("$inc", {}).items():
            doc[key] = doc.get(key, 0) + value
        self.docs[str(doc["id"])] = doc

    def delete_one(self, query: dict[str, Any]) -> Any:
        doc = self.find_one(query)
        if doc is None:
            return type("R", (), {"deleted_count": 0})()
        del self.docs[str(doc["id"])]
        return type("R", (), {"deleted_count": 1})()


def _patch_collection(fake: _FakeCharactersCollection):
    fake_client = type("C", (), {"get_collection": staticmethod(lambda _name: fake)})()
    return patch(
        "monitor_data.tools.mongodb_tools.character_templates.get_mongodb_client",
        return_value=fake_client,
    )


def _a_character_doc(character_id: str = "char-1") -> dict[str, Any]:
    """A plain (non-template) character document in the same collection."""
    return {
        "id": character_id,
        "name": "Mira",
        "personality": "wry",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }


def test_create_returns_the_template_and_marks_the_document() -> None:
    fake = _FakeCharactersCollection()
    with _patch_collection(fake):
        template = mongodb_create_character_template(
            CharacterTemplateCreate(
                name="Varys",
                concept="A spymaster who is never where you expect",
                personality="Charming, patient, always three steps ahead",
                backstory_beats=["Lost a city to a bargain", "Never pays his debts"],
                voice="Warm, indirect, always speaks in parables",
                portrait_url="https://example.invalid/varys.png",
                gm_notes="Never lie outright.",
            )
        )

    assert template.name == "Varys"
    assert template.concept.startswith("A spymaster")
    assert template.backstory_beats == ["Lost a city to a bargain", "Never pays his debts"]
    assert template.usage_count == 0
    # The stored document carries the marker and the character-compatible portrait.
    stored = fake.docs[template.template_id]
    assert stored["is_template"] is True
    assert stored["avatar_url"] == "https://example.invalid/varys.png"


def test_get_round_trips_the_stored_template() -> None:
    fake = _FakeCharactersCollection()
    with _patch_collection(fake):
        created = mongodb_create_character_template(CharacterTemplateCreate(name="Varys", concept="spymaster"))
        fetched = mongodb_get_character_template(created.template_id)

    assert fetched is not None
    assert fetched.template_id == created.template_id
    assert fetched.concept == "spymaster"


def test_get_does_not_return_a_plain_character() -> None:
    fake = _FakeCharactersCollection()
    fake.docs["char-1"] = _a_character_doc()
    with _patch_collection(fake):
        assert mongodb_get_character_template("char-1") is None


def test_list_returns_only_templates() -> None:
    fake = _FakeCharactersCollection()
    fake.docs["char-1"] = _a_character_doc()
    with _patch_collection(fake):
        created = mongodb_create_character_template(CharacterTemplateCreate(name="Varys", concept="spymaster"))
        listed = mongodb_list_character_templates(CharacterTemplateFilter())

    assert listed.total == 1
    assert [t.template_id for t in listed.templates] == [created.template_id]
    assert all(t.name != "Mira" for t in listed.templates)


def test_list_filters_by_name() -> None:
    fake = _FakeCharactersCollection()
    with _patch_collection(fake):
        mongodb_create_character_template(CharacterTemplateCreate(name="Varys"))
        mongodb_create_character_template(CharacterTemplateCreate(name="Tycho"))
        listed = mongodb_list_character_templates(CharacterTemplateFilter(name_contains="vary"))

    assert listed.total == 1
    assert listed.templates[0].name == "Varys"


def test_update_changes_only_the_given_fields() -> None:
    fake = _FakeCharactersCollection()
    with _patch_collection(fake):
        created = mongodb_create_character_template(
            CharacterTemplateCreate(name="Varys", concept="spymaster", voice="parables")
        )
        updated = mongodb_update_character_template(
            created.template_id,
            CharacterTemplateUpdate(voice="clipped", portrait_url="https://example.invalid/v.png"),
        )

    assert updated is not None
    assert updated.voice == "clipped"
    assert updated.concept == "spymaster"  # untouched
    assert updated.name == "Varys"
    assert fake.docs[created.template_id]["avatar_url"] == "https://example.invalid/v.png"


def test_update_never_touches_a_plain_character() -> None:
    fake = _FakeCharactersCollection()
    fake.docs["char-1"] = _a_character_doc()
    with _patch_collection(fake):
        result = mongodb_update_character_template("char-1", CharacterTemplateUpdate(voice="clipped"))

    assert result is None
    assert fake.docs["char-1"]["personality"] == "wry"


def test_delete_only_removes_templates() -> None:
    fake = _FakeCharactersCollection()
    fake.docs["char-1"] = _a_character_doc()
    with _patch_collection(fake):
        created = mongodb_create_character_template(CharacterTemplateCreate(name="Varys"))
        assert mongodb_delete_character_template(created.template_id) is True
        assert mongodb_delete_character_template("char-1") is False

    assert created.template_id not in fake.docs
    assert "char-1" in fake.docs


def test_usage_count_increments() -> None:
    fake = _FakeCharactersCollection()
    with _patch_collection(fake):
        created = mongodb_create_character_template(CharacterTemplateCreate(name="Varys"))
        after_one = mongodb_increment_character_template_usage(created.template_id)
        after_two = mongodb_increment_character_template_usage(created.template_id)

    assert after_one is not None and after_one.usage_count == 1
    assert after_two is not None and after_two.usage_count == 2


def test_templates_carry_no_mechanics() -> None:
    """P&F §6 invariant: a template is portable — no stats, no world binding."""
    for model in (CharacterTemplateCreate, CharacterTemplateUpdate):
        fields = set(model.model_fields)
        assert not fields & {
            "stats",
            "attributes",
            "skills",
            "resources",
            "universe_id",
            "game_system_id",
            "system_id",
        }
