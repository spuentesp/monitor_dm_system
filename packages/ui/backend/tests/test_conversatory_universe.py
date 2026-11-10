"""Per-user Conversatory universe tests (multi-tenancy Phase 6).

``ensure_conversatory_universe`` must find the caller's hidden host universe
through the Postgres ownership registry (``worlds.kind = 'conversatory'``),
never by name and never through a process-global cache. Cross-component
calls (CanonKeeper creation, registry writes, the owner hand-off from
``ensure_character_backed``) are asserted on the real callees' arguments.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import monitor_ui.routers.character_conversation as cc
from monitor_ui.auth import LOCAL_USER_ID
from fake_postgres import FakePostgres


class SpyPostgres(FakePostgres):
    """FakePostgres that records registry calls for argument assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, tuple, dict]] = []

    async def world_get_conversatory(self, owner_id):  # type: ignore[no-untyped-def]
        self.calls.append(("world_get_conversatory", (owner_id,), {}))
        return await super().world_get_conversatory(owner_id)

    async def world_upsert(self, world):  # type: ignore[no-untyped-def]
        self.calls.append(("world_upsert", (), dict(world)))
        await super().world_upsert(world)

    async def multiverse_upsert(self, multiverse):  # type: ignore[no-untyped-def]
        self.calls.append(("multiverse_upsert", (), dict(multiverse)))
        await super().multiverse_upsert(multiverse)


@pytest.fixture
def spy_db(monkeypatch: pytest.MonkeyPatch) -> SpyPostgres:
    db = SpyPostgres()
    monkeypatch.setattr("monitor_data.db.postgres.get_postgres_client", lambda: db)
    return db


def _fake_keeper(monkeypatch: pytest.MonkeyPatch, universe_id: str) -> MagicMock:
    keeper = MagicMock()
    keeper.create_multiverse = AsyncMock(return_value={"id": str(uuid4())})
    keeper.create_universe = AsyncMock(return_value={"id": universe_id})
    monkeypatch.setattr("monitor_agents.canonkeeper.agent.CanonKeeper", MagicMock(return_value=keeper))
    return keeper


class TestFindThroughRegistry:
    @pytest.mark.asyncio
    async def test_returns_the_owners_registered_universe(self, spy_db: SpyPostgres) -> None:
        owner = uuid4()
        spy_db.worlds["uni-1"] = {
            "id": "uni-1",
            "owner_id": owner,
            "label": "Conversatory",
            "active": True,
            "kind": "conversatory",
        }
        result = await cc.ensure_conversatory_universe(owner)
        assert result == "uni-1"
        assert ("world_get_conversatory", (owner,), {}) in spy_db.calls

    @pytest.mark.asyncio
    async def test_lookup_is_not_by_name(self, spy_db: SpyPostgres, monkeypatch: pytest.MonkeyPatch) -> None:
        def fail(*a, **k):  # type: ignore[no-untyped-def]
            raise AssertionError("must not list universes by name")

        monkeypatch.setattr("monitor_data.tools.neo4j_tools.core.neo4j_list_universes", fail)
        spy_db.worlds["uni-1"] = {
            "id": "uni-1",
            "owner_id": uuid4(),
            "label": "Conversatory",
            "active": True,
            "kind": "conversatory",
        }
        assert await cc.ensure_conversatory_universe(spy_db.worlds["uni-1"]["owner_id"]) == "uni-1"

    @pytest.mark.asyncio
    async def test_no_process_global_cache(self, spy_db: SpyPostgres) -> None:
        a, b = uuid4(), uuid4()
        spy_db.worlds["uni-a"] = {
            "id": "uni-a",
            "owner_id": a,
            "label": "Conversatory",
            "active": True,
            "kind": "conversatory",
        }
        spy_db.worlds["uni-b"] = {
            "id": "uni-b",
            "owner_id": b,
            "label": "Conversatory",
            "active": True,
            "kind": "conversatory",
        }
        assert await cc.ensure_conversatory_universe(a) == "uni-a"
        assert await cc.ensure_conversatory_universe(b) == "uni-b"
        assert not hasattr(cc, "_conversatory_universe_id")

    @pytest.mark.asyncio
    async def test_none_owner_is_the_local_account(self, spy_db: SpyPostgres) -> None:
        spy_db.worlds["uni-local"] = {
            "id": "uni-local",
            "owner_id": LOCAL_USER_ID,
            "label": "Conversatory",
            "active": True,
            "kind": "conversatory",
        }
        assert await cc.ensure_conversatory_universe(None) == "uni-local"
        assert ("world_get_conversatory", (LOCAL_USER_ID,), {}) in spy_db.calls


class TestCreateAndRegister:
    @pytest.mark.asyncio
    async def test_creates_via_canonkeeper_and_registers(self, spy_db: SpyPostgres, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        owner = uuid4()
        universe_id = str(uuid4())
        keeper = _fake_keeper(monkeypatch, universe_id)

        result = await cc.ensure_conversatory_universe(owner)

        assert result == universe_id
        # the real callee (CanonKeeper) got the creation payload
        mv_args = keeper.create_multiverse.await_args.args[0]
        assert mv_args["name"] == "__MONITOR_CONVERSATORY__"
        u_args = keeper.create_universe.await_args.args[0]
        assert u_args["name"] == "Conversatory"
        # and the ownership registry got the per-user conversatory marker
        world_calls = [c for c in spy_db.calls if c[0] == "world_upsert"]
        assert len(world_calls) == 1
        payload = world_calls[0][2]
        assert payload["id"] == universe_id
        assert payload["owner_id"] == owner
        assert payload["kind"] == "conversatory"
        mv_reg = [c for c in spy_db.calls if c[0] == "multiverse_upsert"]
        assert len(mv_reg) == 1 and mv_reg[0][2]["owner_id"] == owner

    @pytest.mark.asyncio
    async def test_second_call_reuses_the_registry_row(self, spy_db: SpyPostgres, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        owner = uuid4()
        universe_id = str(uuid4())
        keeper = _fake_keeper(monkeypatch, universe_id)

        first = await cc.ensure_conversatory_universe(owner)
        second = await cc.ensure_conversatory_universe(owner)

        assert first == second == universe_id
        keeper.create_universe.assert_awaited_once()


class TestEnsureCharacterBackedHandsOverTheOwner:
    @pytest.mark.asyncio
    async def test_passes_the_card_owner_to_the_lookup(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        owner = uuid4()
        card = {
            "id": "char-1",
            "owner_id": str(owner),
            "name": "Ranger",
            "description": "d",
            "personality": "p",
            "gm_notes": "",
            "versions": [],
        }
        mock_conv = AsyncMock(return_value="uni-conv")
        fake_gen = MagicMock()
        fake_gen.forward.return_value = {"triggers": []}
        with (
            monkeypatch.context() as m,
        ):
            m.setattr(cc, "get_character", lambda cid: card)
            m.setattr(cc, "ensure_conversatory_universe", mock_conv)
            m.setattr(cc, "_provision_entity_and_profile", MagicMock(return_value="ent-1"))
            m.setattr(cc, "add_version", MagicMock(return_value={"version_id": "v1"}))
            m.setattr(
                "monitor_agents.character_creator.npc_profile_gen.NPCProfileGenerator",
                MagicMock(return_value=fake_gen),
            )
            out = await asyncio.wait_for(cc.ensure_character_backed("char-1"), timeout=10)

        assert out["universe_id"] == "uni-conv"
        mock_conv.assert_awaited_once_with(str(owner))
