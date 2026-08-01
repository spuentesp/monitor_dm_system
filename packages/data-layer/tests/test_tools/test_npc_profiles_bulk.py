"""Bulk NPC profile fetch."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

import monitor_data.tools.mongodb_tools.npc_profiles as npc_mod


class _FakeProfilesCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def find(self, query: dict, projection: dict | None = None) -> list[dict]:
        # Support entity_id: {"$in": [...]}
        if "entity_id" in query and isinstance(query["entity_id"], dict):
            ids = query["entity_id"].get("$in") or []
            return [self.docs[i] for i in ids if i in self.docs]
        if "entity_id" in query:
            return [self.docs[query["entity_id"]]] if query["entity_id"] in self.docs else []
        return list(self.docs.values())


class _FakeMongoClient:
    def __init__(self) -> None:
        self.profiles = _FakeProfilesCollection()

    def __getitem__(self, name: str) -> _FakeProfilesCollection:
        return self.profiles


def _seed_doc(entity_id: UUID, **overrides) -> dict:
    base = {
        "profile_id": str(uuid4()),
        "entity_id": str(entity_id),
        "universe_id": None,
        "traits": {},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": "neutral",
        "relationship_states": {},
        "relationship_states_by_universe": {},
        "current_emotional_state_by_universe": {},
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    base.update(overrides)
    return base


def test_returns_only_requested_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    eid1, eid2, eid3 = uuid4(), uuid4(), uuid4()
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles.docs[str(eid1)] = _seed_doc(eid1, values=["honor"])
    fake_mongo.profiles.docs[str(eid2)] = _seed_doc(eid2, values=["greed"])
    fake_mongo.profiles.docs[str(eid3)] = _seed_doc(eid3, values=["piety"])

    monkeypatch.setattr(
        npc_mod, "get_mongodb_client", lambda: fake_mongo,
    )
    from monitor_data.tools.mongodb_tools.npc_profiles import (
        mongodb_get_npc_profiles_by_entities,
    )

    out = mongodb_get_npc_profiles_by_entities([eid1, eid2])
    assert len(out) == 2
    assert {r.entity_id for r in out} == {eid1, eid2}


def test_returns_empty_when_no_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mongo = _FakeMongoClient()
    monkeypatch.setattr(npc_mod, "get_mongodb_client", lambda: fake_mongo)
    from monitor_data.tools.mongodb_tools.npc_profiles import (
        mongodb_get_npc_profiles_by_entities,
    )

    out = mongodb_get_npc_profiles_by_entities([uuid4()])
    assert out == []


def test_empty_input_returns_empty() -> None:
    from monitor_data.tools.mongodb_tools.npc_profiles import (
        mongodb_get_npc_profiles_by_entities,
    )
    assert mongodb_get_npc_profiles_by_entities([]) == []


def test_response_includes_current_emotional_state_by_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    eid = uuid4()
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles.docs[str(eid)] = _seed_doc(
        eid, current_emotional_state_by_universe={"u1": "wary"}
    )
    monkeypatch.setattr(npc_mod, "get_mongodb_client", lambda: fake_mongo)
    from monitor_data.tools.mongodb_tools.npc_profiles import (
        mongodb_get_npc_profiles_by_entities,
    )

    out = mongodb_get_npc_profiles_by_entities([eid])
    assert len(out) == 1
    assert out[0].current_emotional_state_by_universe == {"u1": "wary"}