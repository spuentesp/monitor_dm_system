"""Tool-boundary ownership assertions for the UX-1 write-tool gap families.

One test per family (lorebook, knowledge packs, play sessions, combat,
game systems) proving:

- A foreign owner bound in context makes the tool refuse with
  ``OwnerViolationError`` and write nothing.
- No owner in context (local mode, scripts, ingestion workers, tests)
  means no assertion — the tool behaves exactly as before and the
  ownership registry is never consulted.

Where a family exposes a natural happy path (play-session create stamps the
acting owner; game-system create stamps ``owner_id``), a matching-owner test
proves the gate opens for the right owner.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from _tenancy_fakes import FakeMongo, FakeNeo4j, FakePostgres, install_fakes

from monitor_data.schemas.combat import CombatCreate, CombatStart, CombatantCreate
from monitor_data.schemas.game_systems import (
    CoreMechanic,
    CoreMechanicType,
    GameSystemCreate,
    GameSystemUpdate,
    RuleOverrideCreate,
    SuccessType,
)
from monitor_data.schemas.knowledge_packs import KnowledgePackCreate, KnowledgePackUpdate
from monitor_data.schemas.lorebook import LorebookEntryCreate
from monitor_data.schemas.play_sessions import PlaySessionCreate
from monitor_data.tenancy import OwnerViolationError, set_owner_id
from monitor_data.tools.mongodb_tools.combat import (
    mongodb_combat_start,
    mongodb_create_combat,
)
from monitor_data.tools.mongodb_tools.game_systems import (
    mongodb_create_game_system,
    mongodb_create_rule_override,
    mongodb_update_game_system,
)
from monitor_data.tools.mongodb_tools.knowledge_packs import (
    mongodb_create_knowledge_pack,
    mongodb_update_knowledge_pack,
)
from monitor_data.tools.mongodb_tools.lorebook_tools import mongodb_create_lorebook_entry
from monitor_data.tools.mongodb_tools.play_sessions import mongodb_create_play_session


@pytest.fixture(autouse=True)
def _clean_owner_ctx() -> Iterator[None]:
    """Every test starts and ends with no acting owner bound."""
    set_owner_id(None)
    yield
    set_owner_id(None)


@pytest.fixture
def fx(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeMongo, FakeNeo4j, FakePostgres]:
    return install_fakes(monkeypatch)


@pytest.fixture
def owner() -> str:
    return str(uuid4())


@pytest.fixture
def other() -> str:
    return str(uuid4())


@pytest.fixture
def universe() -> str:
    return str(uuid4())


def _gate_open(invoke: Callable[[], Any]) -> None:
    """Run the tool: the ownership gate must open (never OwnerViolationError)."""
    try:
        invoke()
    except OwnerViolationError:  # pragma: no cover - failure path
        pytest.fail("ownership gate refused a matching/no-owner write")
    except Exception:  # noqa: BLE001, S110  # reason: the tool's own preconditions are outside this contract
        pass


# ---------------------------------------------------------------------------
# Lorebook
# ---------------------------------------------------------------------------


class TestLorebookGuards:
    def test_foreign_owner_refused_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        other: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        character_id = str(uuid4())
        # The entry targets a standalone card owned by `owner`.
        mongo.get_collection("characters").find_one_result = {"id": character_id, "owner_id": owner}
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_create_lorebook_entry(character_id, LorebookEntryCreate(content="secret lore"))
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == []

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
    ) -> None:
        mongo, _neo4j, pg = fx
        set_owner_id(None)
        entry = mongodb_create_lorebook_entry(str(uuid4()), LorebookEntryCreate(content="local lore"))
        assert entry.content == "local lore"
        assert mongo.get_collection("lorebook_entries").insert_calls
        assert pg.world_get_for_owner_calls == []

    def test_matching_card_owner_passes(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
    ) -> None:
        mongo, _neo4j, _pg = fx
        character_id = str(uuid4())
        mongo.get_collection("characters").find_one_result = {"id": character_id, "owner_id": owner}
        set_owner_id(owner)
        entry = mongodb_create_lorebook_entry(character_id, LorebookEntryCreate(content="owned lore"))
        assert entry.content == "owned lore"
        assert mongo.get_collection("lorebook_entries").insert_calls


# ---------------------------------------------------------------------------
# Knowledge packs
# ---------------------------------------------------------------------------


def _pack_doc(pack_id: UUID, owner_id: str | None) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "_id": str(uuid4()),
        "pack_id": str(pack_id),
        "owner_id": owner_id,
        "name": "Pack",
        "description": "",
        "pack_type": "general",
        "system_name": None,
        "status": "ready",
        "source_document_ids": [],
        "ingestion_job_id": None,
        "tags": [],
        "created_at": now,
        "updated_at": now,
    }


class TestKnowledgePackGuards:
    def test_foreign_owner_refused_update_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        other: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        pack_id = uuid4()
        mongo.get_collection("knowledge_packs").find_one_result = _pack_doc(pack_id, owner)
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_update_knowledge_pack(pack_id, KnowledgePackUpdate(name="Renamed"))
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == []

    def test_foreign_owner_refused_create_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        other: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_create_knowledge_pack(KnowledgePackCreate(name="Foreign", owner_id=owner))
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == []

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
    ) -> None:
        mongo, _neo4j, pg = fx
        pack_id = uuid4()
        mongo.get_collection("knowledge_packs").find_one_result = _pack_doc(pack_id, None)
        set_owner_id(None)
        _gate_open(lambda: mongodb_update_knowledge_pack(pack_id, KnowledgePackUpdate(name="Renamed")))
        assert pg.world_get_for_owner_calls == []

    def test_matching_owner_update_passes(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        pack_id = uuid4()
        mongo.get_collection("knowledge_packs").find_one_result = _pack_doc(pack_id, owner)
        set_owner_id(owner)
        updated = mongodb_update_knowledge_pack(pack_id, KnowledgePackUpdate(name="Renamed"))
        assert updated.name == "Renamed"
        assert pg.world_get_for_owner_calls == []


# ---------------------------------------------------------------------------
# Play sessions
# ---------------------------------------------------------------------------


class TestPlaySessionGuards:
    def test_foreign_owner_refused_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        params = PlaySessionCreate(story_id=uuid4(), universe_id=UUID(universe), session_number=1)
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_create_play_session(params)
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        params = PlaySessionCreate(story_id=uuid4(), universe_id=UUID(universe), session_number=1)
        set_owner_id(None)
        created = mongodb_create_play_session(params)
        assert created.session_number == 1
        assert mongo.get_collection("play_sessions").insert_calls
        assert pg.world_get_for_owner_calls == []

    def test_matching_owner_passes_and_registry_consulted(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        pg.owned_universes.add(universe)
        params = PlaySessionCreate(story_id=uuid4(), universe_id=UUID(universe), session_number=1)
        set_owner_id(owner)
        created = mongodb_create_play_session(params)
        assert created.session_number == 1
        assert (universe, owner) in pg.world_get_for_owner_calls
        assert mongo.get_collection("play_sessions").insert_calls


# ---------------------------------------------------------------------------
# Combat (encounter tools + session tracker)
# ---------------------------------------------------------------------------


class TestCombatGuards:
    def test_foreign_owner_refused_create_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        mongo.get_collection("scenes").find_one_result = {"universe_id": universe}
        params = CombatCreate(scene_id=uuid4(), story_id=uuid4())
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_create_combat(params)
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        mongo.get_collection("scenes").find_one_result = {"universe_id": universe}
        params = CombatCreate(scene_id=uuid4(), story_id=uuid4())
        set_owner_id(None)
        created = mongodb_create_combat(params)
        assert created.status.value == "initializing"
        assert mongo.get_collection("combat_encounters").insert_calls
        assert pg.world_get_for_owner_calls == []

    def test_session_combat_start_foreign_refused(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        params = CombatStart(
            universe_id=UUID(universe),
            session_id="sess-1",
            combatants=[CombatantCreate(name="Goblin", hp=7, max_hp=7)],
        )
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_combat_start(params)
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_session_combat_start_no_owner_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        params = CombatStart(
            universe_id=UUID(universe),
            session_id="sess-1",
            combatants=[CombatantCreate(name="Goblin", hp=7, max_hp=7)],
        )
        set_owner_id(None)
        state = mongodb_combat_start(params)
        assert state.session_id == "sess-1"
        assert mongo.get_collection("session_combats").write_calls
        assert pg.world_get_for_owner_calls == []


# ---------------------------------------------------------------------------
# Game systems (and rule overrides)
# ---------------------------------------------------------------------------


def _system_params() -> GameSystemCreate:
    return GameSystemCreate(
        name="Test System",
        description="A test system",
        core_mechanic=CoreMechanic(
            type=CoreMechanicType.D20,
            formula="1d20",
            success_type=SuccessType.MEET_OR_BEAT,
        ),
        hand_authored=True,
    )


class TestGameSystemGuards:
    def test_foreign_owner_refused_update_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        other: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        system_id = uuid4()
        mongo.get_collection("game_systems").find_one_result = {
            "system_id": str(system_id),
            "is_builtin": False,
            "owner_id": owner,
        }
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_update_game_system(system_id, GameSystemUpdate(name="Renamed"))
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == []

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
    ) -> None:
        mongo, _neo4j, pg = fx
        system_id = uuid4()
        mongo.get_collection("game_systems").find_one_result = {
            "system_id": str(system_id),
            "is_builtin": False,
            "owner_id": None,
        }
        set_owner_id(None)
        _gate_open(lambda: mongodb_update_game_system(system_id, GameSystemUpdate(name="Renamed")))
        assert pg.world_get_for_owner_calls == []

    def test_create_stamps_acting_owner(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
    ) -> None:
        mongo, _neo4j, _pg = fx
        set_owner_id(owner)
        created = mongodb_create_game_system(_system_params())
        assert created.name == "Test System"
        inserts = mongo.get_collection("game_systems").insert_calls
        assert inserts and inserts[0]["owner_id"] == owner

    def test_create_without_owner_leaves_system_shared(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
    ) -> None:
        mongo, _neo4j, _pg = fx
        set_owner_id(None)
        created = mongodb_create_game_system(_system_params())
        assert created.name == "Test System"
        inserts = mongo.get_collection("game_systems").insert_calls
        assert inserts and inserts[0]["owner_id"] is None

    def test_rule_override_create_foreign_refused(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, neo4j, pg = fx
        story_id = str(uuid4())
        neo4j.universe_by_id[story_id] = universe
        params = RuleOverrideCreate(
            scope_id=UUID(story_id),
            target="target",
            original="original",
            override="overridden",
        )
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_create_rule_override(params)
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_rule_override_create_no_owner_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        universe: str,
    ) -> None:
        mongo, neo4j, pg = fx
        story_id = str(uuid4())
        neo4j.universe_by_id[story_id] = universe
        params = RuleOverrideCreate(
            scope_id=UUID(story_id),
            target="target",
            original="original",
            override="overridden",
        )
        set_owner_id(None)
        created = mongodb_create_rule_override(params)
        assert created.target == "target"
        assert mongo.get_collection("rule_overrides").insert_calls
        assert pg.world_get_for_owner_calls == []
