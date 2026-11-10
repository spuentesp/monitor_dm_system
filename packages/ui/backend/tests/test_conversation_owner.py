"""Ownership tests for ``require_conversation_owner`` (multi-tenancy Phase 6).

A conversation id must only resolve for the user who owns the character the
transcript speaks with — this is what keeps the in-process conversation loop
cache unreachable with another user's conversation id. Covers the three
resolution legs (client_session, caller-owned card incarnation, NPC entity
universe chain) and the fail-closed cases.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

import monitor_ui.ownership as ownership_mod
from monitor_ui.auth import Principal
from fake_postgres import FakePostgres
from test_cross_tenant import FakeCollection

CONV = "11111111-2222-4333-8444-555555555555"
ENT = "22222222-3333-4444-8555-666666666666"


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch):
    db = FakePostgres()
    chars = FakeCollection()
    convos = FakeCollection()

    class FakeNeo4j:
        def __init__(self) -> None:
            self.entities: dict[str, str] = {}

        def execute_read(self, query, parameters=None):  # type: ignore[no-untyped-def]
            params = parameters or {}
            if "WHERE e.id IN $ids" in query:
                return [{"id": i, "uid": self.entities[i]} for i in params.get("ids", []) if i in self.entities]
            return []

        def execute_write(self, query, parameters=None):  # type: ignore[no-untyped-def]
            return []

    neo = FakeNeo4j()
    monkeypatch.setattr(ownership_mod, "_characters_collection", lambda: chars)
    monkeypatch.setattr(ownership_mod, "_conversations_collection", lambda: convos)
    monkeypatch.setattr("monitor_data.db.neo4j.get_neo4j_client", lambda: neo)
    return db, chars, convos, neo


def _principal(user_id=None, via: str = "session") -> Principal:
    return Principal(user_id=user_id or uuid4(), is_admin=False, via=via)


def _own_world(db: FakePostgres, owner_id) -> str:  # type: ignore[no-untyped-def]
    uid = str(uuid4())
    db.worlds[uid] = {"id": uid, "owner_id": owner_id, "label": "w", "active": True, "kind": "world"}
    return uid


class TestClientSessionLeg:
    @pytest.mark.asyncio
    async def test_owned_character_passes(self, fakes) -> None:  # type: ignore[no-untyped-def]
        db, chars, convos, neo = fakes
        me = uuid4()
        chars.docs.append({"id": "c1", "owner_id": str(me), "versions": []})
        convos.docs.append({"conversation_id": CONV, "client_session": {"character_id": "c1"}})
        await ownership_mod.require_conversation_owner(db, _principal(me), CONV)

    @pytest.mark.asyncio
    async def test_foreign_character_is_404(self, fakes) -> None:  # type: ignore[no-untyped-def]
        db, chars, convos, neo = fakes
        chars.docs.append({"id": "c1", "owner_id": str(uuid4()), "versions": []})
        convos.docs.append({"conversation_id": CONV, "client_session": {"character_id": "c1"}})
        with pytest.raises(HTTPException) as exc:
            await ownership_mod.require_conversation_owner(db, _principal(), CONV)
        assert exc.value.status_code == 404


class TestCardIncarnationLeg:
    @pytest.mark.asyncio
    async def test_caller_owned_card_incarnation_passes(self, fakes) -> None:  # type: ignore[no-untyped-def]
        db, chars, convos, neo = fakes
        me = uuid4()
        chars.docs.append({"id": "c1", "owner_id": str(me), "versions": [{"entity_id": "ent-1", "universe_id": "u"}]})
        convos.docs.append({"conversation_id": CONV, "npc_ids": ["ent-1"]})
        await ownership_mod.require_conversation_owner(db, _principal(me), CONV)

    @pytest.mark.asyncio
    async def test_someone_elses_card_is_404(self, fakes) -> None:  # type: ignore[no-untyped-def]
        db, chars, convos, neo = fakes
        chars.docs.append(
            {"id": "c1", "owner_id": str(uuid4()), "versions": [{"entity_id": "ent-1", "universe_id": "u"}]}
        )
        convos.docs.append({"conversation_id": CONV, "npc_ids": ["ent-1"]})
        with pytest.raises(HTTPException) as exc:
            await ownership_mod.require_conversation_owner(db, _principal(), CONV)
        assert exc.value.status_code == 404


class TestEntityUniverseLeg:
    @pytest.mark.asyncio
    async def test_npc_entity_in_owned_universe_passes(self, fakes) -> None:  # type: ignore[no-untyped-def]
        db, chars, convos, neo = fakes
        me = uuid4()
        uid = _own_world(db, me)
        neo.entities[ENT] = uid
        convos.docs.append({"conversation_id": CONV, "npc_ids": [ENT]})
        await ownership_mod.require_conversation_owner(db, _principal(me), CONV)

    @pytest.mark.asyncio
    async def test_npc_entity_in_foreign_universe_is_404(self, fakes) -> None:  # type: ignore[no-untyped-def]
        db, chars, convos, neo = fakes
        uid = _own_world(db, uuid4())
        neo.entities[ENT] = uid
        convos.docs.append({"conversation_id": CONV, "npc_ids": [ENT]})
        with pytest.raises(HTTPException) as exc:
            await ownership_mod.require_conversation_owner(db, _principal(), CONV)
        assert exc.value.status_code == 404


class TestFailClosed:
    @pytest.mark.asyncio
    async def test_missing_and_malformed_and_empty_are_404(self, fakes) -> None:  # type: ignore[no-untyped-def]
        db, chars, convos, neo = fakes
        me = uuid4()
        for cid in ("nope", str(uuid4())):
            with pytest.raises(HTTPException) as exc:
                await ownership_mod.require_conversation_owner(db, _principal(me), cid)
            assert exc.value.status_code == 404
        convos.docs.append({"conversation_id": CONV})
        with pytest.raises(HTTPException) as exc:
            await ownership_mod.require_conversation_owner(db, _principal(me), CONV)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_local_mode_bypasses(self, fakes) -> None:  # type: ignore[no-untyped-def]
        db, chars, convos, neo = fakes
        await ownership_mod.require_conversation_owner(db, _principal(via="local"), CONV)
