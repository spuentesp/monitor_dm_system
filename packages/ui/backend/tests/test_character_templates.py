"""Tests for the character-template HTTP surface (G-6 / P&F §6)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from monitor_data.schemas.character_templates import (
    CharacterTemplateListResponse,
    CharacterTemplateResponse,
)
from monitor_ui.main import app

pytestmark = pytest.mark.usefixtures("local_auth_mode")

client = TestClient(app)

BASE = "/api/characters/templates"


def _template(**overrides) -> CharacterTemplateResponse:
    payload = {
        "template_id": "t-1",
        "name": "Varys",
        "concept": "A spymaster who is never where you expect",
        "personality": "Charming, patient",
        "backstory_beats": ["Lost a city to a bargain"],
        "voice": "Speaks in parables",
        "portrait_url": None,
        "first_message": "",
        "gm_notes": "",
        "usage_count": 0,
    }
    payload.update(overrides)
    return CharacterTemplateResponse(**payload)


def test_list_returns_the_template_library() -> None:
    with patch("monitor_ui.routers.character_templates.mongodb_list_character_templates") as spy:
        spy.return_value = CharacterTemplateListResponse(templates=[_template()], total=1, limit=50, offset=0)
        resp = client.get(BASE)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["templates"][0]["name"] == "Varys"
    assert body["templates"][0]["backstory_beats"] == ["Lost a city to a bargain"]


def test_create_returns_201_and_the_template() -> None:
    with patch("monitor_ui.routers.character_templates.mongodb_create_character_template") as spy:
        spy.return_value = _template()
        resp = client.post(
            BASE,
            json={
                "name": "Varys",
                "concept": "A spymaster",
                "backstory_beats": ["Lost a city to a bargain"],
                "voice": "Speaks in parables",
            },
        )

    assert resp.status_code == 201
    assert resp.json()["template_id"] == "t-1"
    created = spy.call_args[0][0]
    assert created.name == "Varys"
    assert created.backstory_beats == ["Lost a city to a bargain"]


def test_get_missing_template_is_404() -> None:
    with patch("monitor_ui.routers.character_templates.mongodb_get_character_template") as spy:
        spy.return_value = None
        resp = client.get(f"{BASE}/nope")

    assert resp.status_code == 404


def test_update_returns_the_updated_template() -> None:
    with patch("monitor_ui.routers.character_templates.mongodb_update_character_template") as spy:
        spy.return_value = _template(voice="Clipped")
        resp = client.patch(f"{BASE}/t-1", json={"voice": "Clipped"})

    assert resp.status_code == 200
    assert resp.json()["voice"] == "Clipped"


def test_update_missing_template_is_404() -> None:
    with patch("monitor_ui.routers.character_templates.mongodb_update_character_template") as spy:
        spy.return_value = None
        resp = client.patch(f"{BASE}/nope", json={"voice": "Clipped"})

    assert resp.status_code == 404


def test_delete_removes_the_template() -> None:
    with patch("monitor_ui.routers.character_templates.mongodb_delete_character_template") as spy:
        spy.return_value = True
        resp = client.delete(f"{BASE}/t-1")

    assert resp.status_code == 204


def test_delete_missing_template_is_404() -> None:
    with patch("monitor_ui.routers.character_templates.mongodb_delete_character_template") as spy:
        spy.return_value = False
        resp = client.delete(f"{BASE}/nope")

    assert resp.status_code == 404


def test_template_payload_ignores_mechanics() -> None:
    """P&F §6 invariant, enforced at the API boundary too."""
    with patch("monitor_ui.routers.character_templates.mongodb_create_character_template") as spy:
        spy.return_value = _template()
        resp = client.post(
            BASE,
            json={"name": "Varys", "stats": {"Strength": 3}, "game_system_id": "x"},
        )

    assert resp.status_code == 201
    created = spy.call_args[0][0]
    # The extra fields are dropped by the schema — a template never carries
    # mechanics, whatever the caller sends.
    assert not hasattr(created, "stats")
    assert not hasattr(created, "game_system_id")


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, _key: str, _direction: int = 1) -> _FakeCursor:
        return self

    def skip(self, _count: int) -> _FakeCursor:
        return self

    def limit(self, _count: int) -> _FakeCursor:
        return self

    def __iter__(self):
        return iter(self._docs)


class _FakeCharactersCollection:
    """Enough of the characters collection to exercise the list filter."""

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs

    def _matches(self, doc: dict, query: dict) -> bool:
        for key, condition in query.items():
            value = doc.get(key)
            if isinstance(condition, dict) and "$ne" in condition:
                if value == condition["$ne"]:
                    return False
            elif value != condition:
                return False
        return True

    def count_documents(self, query: dict) -> int:
        return sum(1 for d in self.docs if self._matches(d, query))

    def find(self, query: dict) -> _FakeCursor:
        return _FakeCursor([d for d in self.docs if self._matches(d, query)])


def test_character_list_excludes_templates() -> None:
    """G-6: a template shares the characters collection but is not a character."""
    from monitor_ui.routers import character_storage

    docs = [
        {"id": "char-1", "name": "Mira", "updated_at": "2026-11-07T00:00:00Z"},
        {
            "id": "tpl-1",
            "name": "Varys",
            "is_template": True,
            "updated_at": "2026-11-07T00:00:00Z",
        },
    ]
    fake = _FakeCharactersCollection(docs)

    with patch.object(character_storage, "_coll", return_value=fake):
        listed, total = character_storage.list_characters()

    assert total == 1
    assert [d["id"] for d in listed] == ["char-1"]
