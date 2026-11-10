"""Tests for GM prep bundle MongoDB tool behavior (CF-7 prep-to-table)."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from monitor_data.schemas.gm_prep import (
    GmPrepBundleUpsert,
    GmPrepLocation,
    GmPrepNpc,
    GmPrepThread,
)
from monitor_data.tools.mongodb_tools.gm_prep import (
    mongodb_get_gm_prep_bundle,
    mongodb_upsert_gm_prep_bundle,
)


class _FakeGmPrepCollection:
    """In-memory stand-in for the ``gm_prep_bundles`` collection.

    Mirrors the production surface the two tools actually use:
    ``find_one`` and ``update_one(..., upsert=True)``.
    """

    def __init__(self) -> None:
        self.docs: dict[tuple[str, str], dict] = {}

    def find_one(self, query: dict) -> dict | None:
        return self.docs.get((query["universe_id"], query["story_id"]))

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        key = (query["universe_id"], query["story_id"])
        existing = self.docs.get(key)
        if existing is None:
            if not upsert:
                return  # mirror pymongo's no-op on no-match
            existing = {}
            self.docs[key] = existing
        for field, value in update.get("$set", {}).items():
            existing[field] = value


def _patch_collection(fake: _FakeGmPrepCollection):
    """Patch ``get_mongodb_client`` so the tools see ``fake`` as the collection."""
    fake_client = type("C", (), {"get_collection": staticmethod(lambda _name: fake)})()
    return patch(
        "monitor_data.tools.mongodb_tools.gm_prep.get_mongodb_client",
        return_value=fake_client,
    )


def _bundle(universe_id, story_id):
    return GmPrepBundleUpsert(
        universe_id=universe_id,
        story_id=story_id,
        npcs=[GmPrepNpc(name="Mira", description="A thief", want="the key back")],
        locations=[GmPrepLocation(name="The Sunken Chapel")],
        threads=[GmPrepThread(title="The sealed door", description="Something waits below")],
    )


def test_get_miss_returns_none() -> None:
    """No prior upsert → ``mongodb_get_gm_prep_bundle`` returns ``None``."""
    fake = _FakeGmPrepCollection()
    with _patch_collection(fake):
        assert mongodb_get_gm_prep_bundle(uuid4(), uuid4()) is None


def test_upsert_then_get_roundtrip() -> None:
    """Upsert on an empty collection creates a row; immediate get returns it."""
    fake = _FakeGmPrepCollection()
    universe_id = uuid4()
    story_id = uuid4()
    with _patch_collection(fake):
        written = mongodb_upsert_gm_prep_bundle(_bundle(universe_id, story_id))
        read = mongodb_get_gm_prep_bundle(universe_id, story_id)

    assert written.updated_at is not None
    assert read is not None
    assert read.universe_id == universe_id
    assert read.story_id == story_id
    assert read.npcs[0].name == "Mira"
    assert read.npcs[0].want == "the key back"
    assert read.locations[0].name == "The Sunken Chapel"
    assert read.threads[0].title == "The sealed door"


def test_upsert_overwrites_prior_bundle() -> None:
    """A second upsert replaces the bundle — one doc per (universe, story)."""
    fake = _FakeGmPrepCollection()
    universe_id = uuid4()
    story_id = uuid4()
    with _patch_collection(fake):
        mongodb_upsert_gm_prep_bundle(_bundle(universe_id, story_id))
        second = _bundle(universe_id, story_id)
        second.npcs = [GmPrepNpc(name="The guild master")]
        second.threads = []
        mongodb_upsert_gm_prep_bundle(second)
        read = mongodb_get_gm_prep_bundle(universe_id, story_id)

    assert read is not None
    assert [npc.name for npc in read.npcs] == ["The guild master"]
    assert read.threads == []


def test_universe_and_story_isolation() -> None:
    """Bundles are keyed per (universe, story) — one never overwrites another."""
    fake = _FakeGmPrepCollection()
    universe_a, universe_b = uuid4(), uuid4()
    story_id = uuid4()
    with _patch_collection(fake):
        mongodb_upsert_gm_prep_bundle(_bundle(universe_a, story_id))
        mongodb_upsert_gm_prep_bundle(_bundle(universe_b, story_id))
        assert mongodb_get_gm_prep_bundle(universe_a, story_id) is not None
        assert mongodb_get_gm_prep_bundle(universe_b, story_id) is not None
        # same universe, different story → separate bundle
        assert mongodb_get_gm_prep_bundle(universe_a, uuid4()) is None


def test_storyless_bundle_key() -> None:
    """A bundle without a story is keyed on the empty story key."""
    fake = _FakeGmPrepCollection()
    universe_id = uuid4()
    with _patch_collection(fake):
        mongodb_upsert_gm_prep_bundle(_bundle(universe_id, None))
        read = mongodb_get_gm_prep_bundle(universe_id, None)

    assert read is not None
    assert read.story_id is None
