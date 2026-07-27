"""Tests for GM notebook MongoDB tool behavior (P2.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from monitor_data.schemas.gm_notes import GmNoteUpsert
from monitor_data.tools.mongodb_tools.gm_notes import (
    mongodb_get_gm_note,
    mongodb_upsert_gm_note,
)


class _FakeGmNotesCollection:
    """In-memory stand-in for the ``gm_notes`` collection.

    Mirrors the production surface the two tools actually use:
    ``find_one`` and ``update_one(..., upsert=True)``.
    """

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def find_one(self, query: dict) -> dict | None:
        return self.docs.get(query["universe_id"])

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        universe_id = query["universe_id"]
        existing = self.docs.get(universe_id)
        if existing is None:
            if not upsert:
                return  # mirror pymongo's no-op on no-match
            existing = {"universe_id": universe_id}
            self.docs[universe_id] = existing
        # $set semantics
        for key, value in update.get("$set", {}).items():
            existing[key] = value


def _patch_collection(fake: _FakeGmNotesCollection):
    """Patch ``get_mongodb_client`` so the tools see ``fake`` as the collection."""
    fake_client = type("C", (), {"get_collection": staticmethod(lambda _name: fake)})()
    return patch("monitor_data.tools.mongodb_tools.gm_notes.get_mongodb_client", return_value=fake_client)


def test_get_miss_returns_none() -> None:
    """No prior upsert → ``mongodb_get_gm_note`` returns ``None``."""
    fake = _FakeGmNotesCollection()
    universe_id = uuid4()
    with _patch_collection(fake):
        assert mongodb_get_gm_note(universe_id) is None


def test_upsert_then_get_roundtrip() -> None:
    """Upsert on an empty collection creates a row; immediate get returns it."""
    fake = _FakeGmNotesCollection()
    universe_id = uuid4()
    with _patch_collection(fake):
        upserted = mongodb_upsert_gm_note(universe_id, GmNoteUpsert(content="hello"))
        loaded = mongodb_get_gm_note(universe_id)

    assert loaded is not None
    assert loaded.universe_id == universe_id
    assert loaded.content == "hello"
    # Same payload echoed back
    assert upserted.content == "hello"
    assert isinstance(upserted.updated_at, datetime)
    assert upserted.updated_at.tzinfo is UTC


def test_second_upsert_overwrites() -> None:
    """Two upserts on the same universe → exactly one doc, latest content wins."""
    fake = _FakeGmNotesCollection()
    universe_id = uuid4()
    with _patch_collection(fake):
        mongodb_upsert_gm_note(universe_id, GmNoteUpsert(content="first"))
        mongodb_upsert_gm_note(universe_id, GmNoteUpsert(content="second"))
        loaded = mongodb_get_gm_note(universe_id)

    assert loaded is not None
    assert loaded.content == "second"
    assert len(fake.docs) == 1, "second upsert must not create a second row"


def test_upsert_isolates_per_universe() -> None:
    """Two different universes → two distinct docs (no cross-pollination)."""
    fake = _FakeGmNotesCollection()
    a, b = uuid4(), uuid4()
    with _patch_collection(fake):
        mongodb_upsert_gm_note(a, GmNoteUpsert(content="alpha"))
        mongodb_upsert_gm_note(b, GmNoteUpsert(content="beta"))
        a_loaded = mongodb_get_gm_note(a)
        b_loaded = mongodb_get_gm_note(b)

    assert a_loaded is not None and a_loaded.content == "alpha"
    assert b_loaded is not None and b_loaded.content == "beta"
    assert len(fake.docs) == 2
