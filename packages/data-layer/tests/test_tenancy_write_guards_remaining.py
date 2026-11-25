"""Tool-boundary ownership assertions for the remaining HTTP-only families.

MULTI_TENANCY_PLAN §4 listed the write families that were guarded only at
the HTTP layer: visual identities, conversation turns, session-recorder
entries, resolutions, GM notes, parties, and tone libraries. One test class
per family proves the contract for each:

- A foreign owner bound in context makes the tool refuse with
  ``OwnerViolationError`` and write nothing.
- The matching owner passes the gate (the ownership registry is consulted
  with the expected arguments — the real ``world_get_for_owner`` callee).
- No owner in context (local mode, scripts, workers, tests) means no
  assertion — the tool behaves exactly as before and the ownership
  registry is never consulted.

Where a family exposes a natural happy path, the matching-owner test
completes a real write under the gate.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from _tenancy_fakes import FakeMongo, FakeNeo4j, FakePostgres, install_fakes

from monitor_data.schemas.conversations import (
    AppendConversationTurn,
    ConversationMode,
    ConversationSessionCreate,
)
from monitor_data.schemas.gm_notes import GmNoteUpsert
from monitor_data.schemas.party_inventory import AddCharacterItemRequest, PartyInventoryCreate
from monitor_data.schemas.parties import AddPartyMember, PartyCreate
from monitor_data.schemas.resolutions import (
    ActionType,
    Mechanics,
    ResolutionCreate,
    ResolutionType,
    ResolutionUpdate,
    SuccessLevel,
)
from monitor_data.schemas.tone_libraries import ToneLibraryCreate, ToneLibraryUpdate
from monitor_data.schemas.visual_identity import VisualIdentityCreate, VisualIdentityUpdate
from monitor_data.tenancy import OwnerViolationError, set_owner_id
from monitor_data.tools.mongodb_tools.conversations import (
    mongodb_append_conversation_turn,
    mongodb_create_conversation,
)
from monitor_data.tools.mongodb_tools.gm_notes import mongodb_upsert_gm_note
from monitor_data.tools.mongodb_tools.party import (
    mongodb_add_character_item,
    mongodb_create_party_inventory,
)
from monitor_data.tools.mongodb_tools.resolutions import (
    mongodb_create_resolution,
    mongodb_delete_resolution,
    mongodb_update_resolution,
)
from monitor_data.tools.mongodb_tools.session_entries import (
    mongodb_delete_session_entry,
    mongodb_update_session_entry,
)
from monitor_data.tools.mongodb_tools.tone_libraries import (
    mongodb_create_tone_library,
    mongodb_delete_tone_library,
    mongodb_update_tone_library,
)
from monitor_data.tools.mongodb_tools.visual_identities import (
    mongodb_update_visual_identity_status,
    mongodb_upsert_visual_identity,
)
from monitor_data.tools.neo4j_tools.parties import neo4j_add_party_member, neo4j_create_party


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
# Visual identities
# ---------------------------------------------------------------------------


class TestVisualIdentityGuards:
    def test_foreign_owner_refused_create_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        params = VisualIdentityCreate(entity_id=uuid4(), universe_id=UUID(universe))
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_upsert_visual_identity(params)
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_matching_owner_create_passes_and_registry_consulted(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        pg.owned_universes.add(universe)
        params = VisualIdentityCreate(entity_id=uuid4(), universe_id=UUID(universe))
        set_owner_id(owner)
        created = mongodb_upsert_visual_identity(params)
        assert created.version == 1
        assert mongo.get_collection("visual_identities").insert_calls
        assert (universe, owner) in pg.world_get_for_owner_calls

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        params = VisualIdentityCreate(entity_id=uuid4(), universe_id=UUID(universe))
        set_owner_id(None)
        created = mongodb_upsert_visual_identity(params)
        assert created.version == 1
        assert mongo.get_collection("visual_identities").insert_calls
        assert pg.world_get_for_owner_calls == []

    def test_foreign_owner_refused_update_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        identity_id = uuid4()
        mongo.get_collection("visual_identities").find_one_result = {
            "identity_id": str(identity_id),
            "entity_id": str(uuid4()),
            "universe_id": str(universe),
            "version": 1,
            "status": "draft",
            "description": "",
        }
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_upsert_visual_identity(
                VisualIdentityUpdate(identity_id=identity_id, expected_version=1, description="x")
            )
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_foreign_owner_refused_status_transition(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        identity_id = uuid4()
        mongo.get_collection("visual_identities").find_one_result = {
            "identity_id": str(identity_id),
            "entity_id": str(uuid4()),
            "universe_id": str(universe),
            "version": 1,
            "status": "draft",
            "description": "",
        }
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_update_visual_identity_status(identity_id, status="approved")
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]


# ---------------------------------------------------------------------------
# Conversations (turns)
# ---------------------------------------------------------------------------


def _conversation_doc(universe: str, conversation_id: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "conversation_id": conversation_id,
        "universe_id": universe,
        "mode": ConversationMode.DIRECT.value,
        "status": "active",
        "npc_ids": [],
        "scene_id": None,
        "story_id": None,
        "player_entity_id": None,
        "turns": [],
        "metadata": {},
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }


class TestConversationGuards:
    def test_foreign_owner_refused_create_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        params = ConversationSessionCreate(
            universe_id=UUID(universe),
            mode=ConversationMode.DIRECT,
            npc_ids=[uuid4()],
        )
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_create_conversation(params)
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_matching_owner_create_passes(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        pg.owned_universes.add(universe)
        params = ConversationSessionCreate(
            universe_id=UUID(universe),
            mode=ConversationMode.DIRECT,
            npc_ids=[uuid4()],
        )
        set_owner_id(owner)
        created = mongodb_create_conversation(params)
        assert str(created.universe_id) == universe
        assert mongo.get_collection("conversations").insert_calls
        assert (universe, owner) in pg.world_get_for_owner_calls

    def test_foreign_owner_refused_append_turn_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        conversation_id = str(uuid4())
        mongo.get_collection("conversations").find_one_result = _conversation_doc(universe, conversation_id)
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_append_conversation_turn(
                UUID(conversation_id),
                AppendConversationTurn(speaker_role="player", text="hello"),
            )
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_matching_owner_appends_turn(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        pg.owned_universes.add(universe)
        conversation_id = str(uuid4())
        mongo.get_collection("conversations").find_one_result = _conversation_doc(universe, conversation_id)
        set_owner_id(owner)
        updated = mongodb_append_conversation_turn(
            UUID(conversation_id),
            AppendConversationTurn(speaker_role="player", text="hello"),
        )
        assert str(updated.conversation_id) == conversation_id
        assert mongo.get_collection("conversations").update_calls == 1
        assert (universe, owner) in pg.world_get_for_owner_calls

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        conversation_id = str(uuid4())
        mongo.get_collection("conversations").find_one_result = _conversation_doc(universe, conversation_id)
        set_owner_id(None)
        updated = mongodb_append_conversation_turn(
            UUID(conversation_id),
            AppendConversationTurn(speaker_role="player", text="hello"),
        )
        assert str(updated.conversation_id) == conversation_id
        assert mongo.get_collection("conversations").update_calls == 1
        assert pg.world_get_for_owner_calls == []


# ---------------------------------------------------------------------------
# Session-recorder entries (chat messages)
# ---------------------------------------------------------------------------


class TestSessionEntryGuards:
    def _seed(self, mongo: FakeMongo, entry_id: str, session_id: str, owner: str | None) -> None:
        mongo.get_collection("chat_messages").find_one_result = {
            "id": entry_id,
            "session_id": session_id,
            "content": "old text",
            "struck": False,
        }
        mongo.get_collection("chat_sessions").find_one_result = {
            "id": session_id,
            "owner_id": owner,
        }

    def test_foreign_owner_refused_update_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        other: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        self._seed(mongo, "entry-1", "sess-1", owner)
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_update_session_entry("entry-1", "corrected text")
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == []

    def test_matching_session_owner_updates(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        self._seed(mongo, "entry-1", "sess-1", owner)
        set_owner_id(owner)
        updated = mongodb_update_session_entry("entry-1", "corrected text")
        assert updated["id"] == "entry-1"
        assert mongo.get_collection("chat_messages").update_calls == 1
        assert pg.world_get_for_owner_calls == []

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        # A foreign session doc with no owner bound: the legacy path.
        self._seed(mongo, "entry-1", "sess-1", owner)
        set_owner_id(None)
        updated = mongodb_update_session_entry("entry-1", "corrected text")
        assert updated["id"] == "entry-1"
        assert mongo.get_collection("chat_messages").update_calls == 1
        assert pg.world_get_for_owner_calls == []

    def test_foreign_owner_refused_strike_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        other: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        self._seed(mongo, "entry-1", "sess-1", owner)
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_delete_session_entry("entry-1")
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == []


# ---------------------------------------------------------------------------
# Resolutions
# ---------------------------------------------------------------------------


class TestResolutionGuards:
    def _params(self) -> ResolutionCreate:
        return ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Slash the goblin",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.DICE,
            mechanics=Mechanics(formula="d20+5"),
            success_level=SuccessLevel.SUCCESS,
        )

    def test_foreign_owner_refused_create_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        mongo.get_collection("scenes").find_one_result = {"universe_id": universe}
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_create_resolution(self._params())
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_matching_owner_create_passes(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        pg.owned_universes.add(universe)
        params = self._params()
        mongo.get_collection("scenes").find_one_result = {
            "universe_id": universe,
            "turns": [{"turn_id": str(params.turn_id)}],
        }
        set_owner_id(owner)
        created = mongodb_create_resolution(params)
        assert created.action == "Slash the goblin"
        assert mongo.get_collection("resolutions").insert_calls
        assert (universe, owner) in pg.world_get_for_owner_calls

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        params = self._params()
        mongo.get_collection("scenes").find_one_result = {
            "universe_id": universe,
            "turns": [{"turn_id": str(params.turn_id)}],
        }
        set_owner_id(None)
        created = mongodb_create_resolution(params)
        assert created.action == "Slash the goblin"
        assert mongo.get_collection("resolutions").insert_calls
        assert pg.world_get_for_owner_calls == []

    def test_foreign_owner_refused_update_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        resolution_id = uuid4()
        mongo.get_collection("resolutions").find_one_result = {
            "resolution_id": str(resolution_id),
            "scene_id": str(uuid4()),
        }
        mongo.get_collection("scenes").find_one_result = {"universe_id": universe}
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_update_resolution(resolution_id, ResolutionUpdate(description="changed"))
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_foreign_owner_refused_delete_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        resolution_id = uuid4()
        mongo.get_collection("resolutions").find_one_result = {
            "resolution_id": str(resolution_id),
            "scene_id": str(uuid4()),
        }
        mongo.get_collection("scenes").find_one_result = {"universe_id": universe}
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_delete_resolution(resolution_id)
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]


# ---------------------------------------------------------------------------
# GM notes
# ---------------------------------------------------------------------------


class TestGmNoteGuards:
    def test_foreign_owner_refused_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_upsert_gm_note(UUID(universe), GmNoteUpsert(content="secret plan"))
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_matching_owner_upserts(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        pg.owned_universes.add(universe)
        set_owner_id(owner)
        note = mongodb_upsert_gm_note(UUID(universe), GmNoteUpsert(content="my plan"))
        assert note.content == "my plan"
        assert mongo.get_collection("gm_notes").update_calls == 1
        assert (universe, owner) in pg.world_get_for_owner_calls

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        set_owner_id(None)
        note = mongodb_upsert_gm_note(UUID(universe), GmNoteUpsert(content="local plan"))
        assert note.content == "local plan"
        assert mongo.get_collection("gm_notes").update_calls == 1
        assert pg.world_get_for_owner_calls == []


# ---------------------------------------------------------------------------
# Parties (Neo4j nodes + Mongo inventories)
# ---------------------------------------------------------------------------


class TestPartyGuards:
    def _seed_party(self, neo4j: FakeNeo4j, universe: str, party_id: str) -> str:
        story_id = str(uuid4())
        neo4j.party_story_by_id[party_id] = story_id
        neo4j.universe_by_id[story_id] = universe
        return story_id

    def test_foreign_owner_refused_inventory_create_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, neo4j, pg = fx
        party_id = uuid4()
        self._seed_party(neo4j, universe, str(party_id))
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_create_party_inventory(PartyInventoryCreate(party_id=party_id, initial_gold=10))
        assert mongo.total_write_calls == 0
        assert neo4j.write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_matching_owner_inventory_create_passes(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        universe: str,
    ) -> None:
        mongo, neo4j, pg = fx
        pg.owned_universes.add(universe)
        party_id = uuid4()
        self._seed_party(neo4j, universe, str(party_id))
        set_owner_id(owner)
        created = mongodb_create_party_inventory(PartyInventoryCreate(party_id=party_id, initial_gold=10))
        assert created.gold == 10
        assert mongo.get_collection("party_inventories").insert_calls
        assert (universe, owner) in pg.world_get_for_owner_calls

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        universe: str,
    ) -> None:
        mongo, neo4j, pg = fx
        party_id = uuid4()
        self._seed_party(neo4j, universe, str(party_id))
        set_owner_id(None)
        created = mongodb_create_party_inventory(PartyInventoryCreate(party_id=party_id, initial_gold=10))
        assert created.gold == 10
        assert mongo.get_collection("party_inventories").insert_calls
        assert pg.world_get_for_owner_calls == []

    def test_foreign_owner_refused_neo4j_member_add_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, neo4j, pg = fx
        party_id = uuid4()
        self._seed_party(neo4j, universe, str(party_id))
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            neo4j_add_party_member(AddPartyMember(party_id=party_id, entity_id=uuid4()))
        assert neo4j.write_calls == 0
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_matching_owner_neo4j_party_create_gate_opens(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        universe: str,
    ) -> None:
        mongo, neo4j, pg = fx
        pg.owned_universes.add(universe)
        story_id = uuid4()
        neo4j.universe_by_id[str(story_id)] = universe
        set_owner_id(owner)
        _gate_open(lambda: neo4j_create_party(PartyCreate(story_id=story_id, name="The Company")))
        assert (universe, owner) in pg.world_get_for_owner_calls
        assert mongo.total_write_calls == 0

    def test_foreign_owner_refused_character_inventory_add(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, neo4j, pg = fx
        entity_id = uuid4()
        neo4j.universe_by_id[str(entity_id)] = universe
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_add_character_item(AddCharacterItemRequest(entity_id=entity_id, item_name="Rope", quantity=1))
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]


# ---------------------------------------------------------------------------
# Tone libraries
# ---------------------------------------------------------------------------


def _tone_doc(library_id: str, universe: str | None) -> dict[str, Any]:
    return {
        "library_id": library_id,
        "name": "Noir",
        "description": "",
        "tone_profile_ids": [],
        "pack_id": None,
        "universe_id": universe,
        "priority": 100,
        "is_default": False,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


class TestToneLibraryGuards:
    def test_foreign_owner_refused_create_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        params = ToneLibraryCreate(name="Noir", universe_id=UUID(universe))
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_create_tone_library(params)
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_matching_owner_create_passes(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        owner: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        pg.owned_universes.add(universe)
        params = ToneLibraryCreate(name="Noir", universe_id=UUID(universe))
        set_owner_id(owner)
        created = mongodb_create_tone_library(params)
        assert created.name == "Noir"
        assert mongo.get_collection("tone_libraries").insert_calls
        assert (universe, owner) in pg.world_get_for_owner_calls

    def test_no_owner_in_context_unchanged(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        params = ToneLibraryCreate(name="Noir", universe_id=UUID(universe))
        set_owner_id(None)
        created = mongodb_create_tone_library(params)
        assert created.name == "Noir"
        assert mongo.get_collection("tone_libraries").insert_calls
        assert pg.world_get_for_owner_calls == []

    def test_foreign_owner_refused_update_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        library_id = uuid4()
        mongo.get_collection("tone_libraries").find_one_result = _tone_doc(str(library_id), universe)
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_update_tone_library(library_id, ToneLibraryUpdate(name="Renamed"))
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]

    def test_foreign_owner_refused_delete_and_writes_nothing(
        self,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
        other: str,
        universe: str,
    ) -> None:
        mongo, _neo4j, pg = fx
        library_id = uuid4()
        mongo.get_collection("tone_libraries").find_one_result = _tone_doc(str(library_id), universe)
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            mongodb_delete_tone_library(library_id)
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == [(universe, other)]
