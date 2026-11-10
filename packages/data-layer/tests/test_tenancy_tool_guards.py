"""Tool-boundary ownership assertions (multi-tenancy Phase 6 task 8).

Contract per guarded write tool (story, scene, character/entity, memory,
NPC profile, proposed change):

- A foreign owner bound in context makes the tool refuse with
  ``OwnerViolationError`` and write nothing.
- The matching owner passes the gate (the ownership registry is consulted
  with the expected arguments — the real ``world_get_for_owner`` callee).
- No owner in context (local mode, scripts, workers, tests) means no
  assertion and no registry traffic — existing behavior unchanged.

Where a tool's own preconditions are out of scope, "passes the gate" means
the call raised the tool's own error (or succeeded), never
``OwnerViolationError``. The memory and story-ledger creates additionally
complete a full happy-path write for the matching owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import UUID, uuid4

import pytest
from _tenancy_fakes import FakeMongo, FakeNeo4j, FakePostgres, install_fakes

from monitor_data.schemas.base import ProposalType, Speaker
from monitor_data.schemas.character_sheets import CharacterSheetCreate, CharacterSheetUpdate
from monitor_data.schemas.memories import MemoryCreate, MemoryUpdate
from monitor_data.schemas.npc_profiles import NPCProfileCreate, NPCProfileUpdate
from monitor_data.schemas.proposed_changes import DecisionMetadata, ProposedChangeCreate, ProposedChangeUpdate
from monitor_data.schemas.scenes import SceneCreate, SceneUpdate, TurnCreate
from monitor_data.schemas.stories import StoryLedgerEntryCreate
from monitor_data.schemas.story_outlines import StoryOutlineCreate, StoryOutlineUpdate
from monitor_data.tenancy import OwnerViolationError, set_owner_id
from monitor_data.tools.mongodb_tools.character_sheets import (
    mongodb_create_character_sheet,
    mongodb_update_character_sheet,
)
from monitor_data.tools.mongodb_tools.memories import (
    mongodb_create_memory,
    mongodb_delete_memory,
    mongodb_update_memory,
)
from monitor_data.tools.mongodb_tools.npc_profiles import (
    mongodb_create_npc_profile,
    mongodb_update_npc_profile,
)
from monitor_data.tools.mongodb_tools.proposals import (
    mongodb_create_proposed_change,
    mongodb_defer_proposed_change,
    mongodb_edit_proposed_change,
    mongodb_flag_proposal_review,
    mongodb_update_proposed_change,
)
from monitor_data.tools.mongodb_tools.scenes import (
    mongodb_append_turn,
    mongodb_create_scene,
    mongodb_update_scene,
    mongodb_update_turn_resolution,
)
from monitor_data.tools.mongodb_tools.stories import (
    mongodb_append_story_ledger_entry,
    mongodb_create_story_outline,
    mongodb_update_story_outline,
)


@dataclass
class Ids:
    owner: str
    other: str
    universe: str
    scene_id: str
    story_id: str
    entity_id: str
    memory_id: str
    sheet_id: str
    proposal_id: str


@pytest.fixture
def ids() -> Ids:
    return Ids(
        owner=str(uuid4()),
        other=str(uuid4()),
        universe=str(uuid4()),
        scene_id=str(uuid4()),
        story_id=str(uuid4()),
        entity_id=str(uuid4()),
        memory_id=str(uuid4()),
        sheet_id=str(uuid4()),
        proposal_id=str(uuid4()),
    )


@pytest.fixture
def fx(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeMongo, FakeNeo4j, FakePostgres]:
    return install_fakes(monkeypatch)


PROPOSAL_DOC = {
    "proposal_id": "00000000-0000-0000-0000-000000000000",  # overwritten per test
    "scene_id": None,
    "story_id": None,
    "turn_id": None,
    "change_type": "fact",
    "content": {},
    "evidence": [],
    "confidence": 1.0,
    "authority": "system",
    "proposer": "UI",
    "status": "pending",
    "source": None,
    "created_at": datetime.now(UTC),
    "updated_at": datetime.now(UTC),
}


def _proposal_doc(proposal_id: str, **overrides: Any) -> dict[str, Any]:
    doc = {**PROPOSAL_DOC, "proposal_id": proposal_id}
    doc.update(overrides)
    return doc


def _case_table(
    ids: Ids, fx: tuple[FakeMongo, FakeNeo4j, FakePostgres]
) -> list[tuple[str, Callable[[], Any], str, Callable[[], None]]]:
    """(name, invoke, expected_target_universe, setup) for every guarded tool."""
    mongo, neo4j, _pg = fx
    universe = ids.universe

    def scene_resolution() -> None:
        mongo.get_collection("scenes").find_one_result = {"universe_id": universe}

    def memory_resolution() -> None:
        mongo.get_collection("character_memories").find_one_result = {"universe_id": universe}

    def proposal_resolution(scene: bool = True) -> Callable[[], None]:
        def setup() -> None:
            mongo.get_collection("proposed_changes").find_one_result = _proposal_doc(
                ids.proposal_id,
                scene_id=ids.scene_id if scene else None,
                story_id=None if scene else ids.story_id,
                content={"universe_id": universe},
            )
            scene_resolution()

        return setup

    def story_resolution() -> None:
        neo4j.universe_by_id[ids.story_id] = universe

    def entity_resolution() -> None:
        neo4j.universe_by_id[ids.entity_id] = universe

    now = datetime.now(UTC)
    cases: list[tuple[str, Callable[[], Any], str, Callable[[], None]]] = [
        (
            "mongodb_create_scene",
            lambda: mongodb_create_scene(
                SceneCreate(story_id=UUID(ids.story_id), universe_id=UUID(universe), title="Test scene")
            ),
            universe,
            lambda: None,
        ),
        (
            "mongodb_update_scene",
            lambda: mongodb_update_scene(UUID(ids.scene_id), SceneUpdate(title="Updated")),
            universe,
            scene_resolution,
        ),
        (
            "mongodb_append_turn",
            lambda: mongodb_append_turn(UUID(ids.scene_id), TurnCreate(speaker=Speaker.USER, text="hello")),
            universe,
            scene_resolution,
        ),
        (
            "mongodb_update_turn_resolution",
            lambda: mongodb_update_turn_resolution(UUID(ids.scene_id), uuid4(), uuid4()),
            universe,
            scene_resolution,
        ),
        (
            "mongodb_create_story_outline",
            lambda: mongodb_create_story_outline(StoryOutlineCreate(story_id=UUID(ids.story_id))),
            universe,
            story_resolution,
        ),
        (
            "mongodb_update_story_outline",
            lambda: mongodb_update_story_outline(UUID(ids.story_id), StoryOutlineUpdate(theme="t")),
            universe,
            story_resolution,
        ),
        (
            "mongodb_append_story_ledger_entry",
            lambda: mongodb_append_story_ledger_entry(
                StoryLedgerEntryCreate(
                    story_id=UUID(ids.story_id),
                    universe_id=UUID(universe),
                    scene_id=UUID(ids.scene_id),
                    summary="The party crossed the drowned road.",
                    start_time=now,
                    end_time=now,
                )
            ),
            universe,
            lambda: None,
        ),
        (
            "mongodb_create_character_sheet",
            lambda: mongodb_create_character_sheet(CharacterSheetCreate(entity_id=UUID(ids.entity_id))),
            universe,
            entity_resolution,
        ),
        (
            "mongodb_update_character_sheet",
            lambda: mongodb_update_character_sheet(UUID(ids.sheet_id), CharacterSheetUpdate(notes="x")),
            universe,
            lambda: (
                entity_resolution(),
                mongo.get_collection("character_sheets").__setattr__(
                    "find_one_result", {"sheet_id": ids.sheet_id, "entity_id": ids.entity_id}
                ),
            ),
        ),
        (
            "mongodb_create_memory",
            lambda: mongodb_create_memory(
                MemoryCreate(universe_id=UUID(universe), entity_id=UUID(ids.entity_id), text="a memory")
            ),
            universe,
            lambda: None,
        ),
        (
            "mongodb_update_memory",
            lambda: mongodb_update_memory(UUID(ids.memory_id), MemoryUpdate(importance=0.7)),
            universe,
            memory_resolution,
        ),
        (
            "mongodb_delete_memory",
            lambda: mongodb_delete_memory(UUID(ids.memory_id)),
            universe,
            memory_resolution,
        ),
        (
            "mongodb_create_npc_profile",
            lambda: mongodb_create_npc_profile(NPCProfileCreate(entity_id=UUID(ids.entity_id))),
            universe,
            entity_resolution,
        ),
        (
            "mongodb_update_npc_profile",
            lambda: mongodb_update_npc_profile(UUID(ids.entity_id), NPCProfileUpdate(traits={"bravery": 0.5})),
            universe,
            entity_resolution,
        ),
        (
            "mongodb_create_proposed_change",
            lambda: mongodb_create_proposed_change(
                ProposedChangeCreate(
                    change_type=ProposalType.FACT,
                    content={"universe_id": universe, "statement": "x"},
                    proposer="UI",
                )
            ),
            universe,
            lambda: None,
        ),
        (
            "mongodb_create_proposed_change_scene",
            lambda: mongodb_create_proposed_change(
                ProposedChangeCreate(
                    scene_id=UUID(ids.scene_id),
                    change_type=ProposalType.FACT,
                    content={"statement": "x"},
                )
            ),
            universe,
            scene_resolution,
        ),
        (
            "mongodb_update_proposed_change",
            lambda: mongodb_update_proposed_change(
                UUID(ids.proposal_id),
                ProposedChangeUpdate(
                    status="accepted",
                    decision_metadata=DecisionMetadata(decided_by="CanonKeeper", decided_at=now, reason="ok"),
                ),
            ),
            universe,
            proposal_resolution(),
        ),
        (
            "mongodb_defer_proposed_change",
            lambda: mongodb_defer_proposed_change(UUID(ids.proposal_id), reason="later"),
            universe,
            proposal_resolution(),
        ),
        (
            "mongodb_edit_proposed_change",
            lambda: mongodb_edit_proposed_change(UUID(ids.proposal_id), content_patch={"k": "v"}),
            universe,
            proposal_resolution(),
        ),
        (
            "mongodb_flag_proposal_review",
            lambda: mongodb_flag_proposal_review(UUID(ids.proposal_id), reason="check"),
            universe,
            proposal_resolution(),
        ),
    ]
    return cases


def _run_gate_open(invoke: Callable[[], Any]) -> None:
    """Run the tool: the ownership gate must open (never OwnerViolationError)."""
    try:
        invoke()
    except OwnerViolationError:  # pragma: no cover - failure path
        pytest.fail("ownership gate refused a matching/no-owner write")
    except Exception:  # noqa: BLE001, S110  # reason: the tool's own preconditions are outside this contract's scope
        pass


class TestForeignOwnerRefuses:
    @pytest.mark.parametrize("case_index", range(20))
    def test_foreign_owner_refuses_and_writes_nothing(
        self,
        case_index: int,
        ids: Ids,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
    ) -> None:
        mongo, _neo4j, pg = fx
        cases = _case_table(ids, fx)
        name, invoke, target, setup = cases[case_index]
        setup()
        set_owner_id(ids.other)  # a foreign owner in context
        with pytest.raises(OwnerViolationError):
            invoke()
        assert mongo.total_write_calls == 0, f"{name} wrote despite the owner violation"
        # The registry was consulted for exactly the target universe.
        assert pg.world_get_for_owner_calls in ([(target, ids.other)], []), (
            f"{name}: unexpected registry calls {pg.world_get_for_owner_calls}"
        )


class TestMatchingOwnerPasses:
    @pytest.mark.parametrize("case_index", range(20))
    def test_matching_owner_passes_the_gate(
        self,
        case_index: int,
        ids: Ids,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
    ) -> None:
        mongo, _neo4j, pg = fx
        cases = _case_table(ids, fx)
        name, invoke, target, setup = cases[case_index]
        setup()
        pg.owned_universes.add(target)
        set_owner_id(ids.owner)
        _run_gate_open(invoke)
        assert (target, ids.owner) in pg.world_get_for_owner_calls, (
            f"{name}: registry not consulted with expected args ({target}, {ids.owner})"
        )


class TestNoOwnerPasses:
    @pytest.mark.parametrize("case_index", range(20))
    def test_no_owner_in_context_never_asserts(
        self,
        case_index: int,
        ids: Ids,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
    ) -> None:
        mongo, _neo4j, pg = fx
        cases = _case_table(ids, fx)
        name, invoke, _target, setup = cases[case_index]
        setup()
        set_owner_id(None)  # local mode / scripts / workers / tests
        _run_gate_open(invoke)
        assert pg.world_get_for_owner_calls == [], f"{name} asserted with no owner bound"


class TestFullHappyPathWrites:
    def test_matching_owner_completes_memory_write(
        self,
        ids: Ids,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
    ) -> None:
        mongo, _neo4j, pg = fx
        pg.owned_universes.add(ids.universe)
        set_owner_id(ids.owner)
        created = mongodb_create_memory(
            MemoryCreate(universe_id=UUID(ids.universe), entity_id=UUID(ids.entity_id), text="a memory")
        )
        assert created.text == "a memory"
        assert mongo.get_collection("character_memories").insert_calls, "memory doc not written"
        assert (ids.universe, ids.owner) in pg.world_get_for_owner_calls

    def test_matching_owner_completes_ledger_append(
        self,
        ids: Ids,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
    ) -> None:
        mongo, _neo4j, pg = fx
        pg.owned_universes.add(ids.universe)
        set_owner_id(ids.owner)
        now = datetime.now(UTC)
        entry = mongodb_append_story_ledger_entry(
            StoryLedgerEntryCreate(
                story_id=UUID(ids.story_id),
                universe_id=UUID(ids.universe),
                scene_id=UUID(ids.scene_id),
                summary="The party crossed the drowned road.",
                start_time=now,
                end_time=now,
            )
        )
        assert entry.summary.startswith("The party")
        assert mongo.get_collection("story_ledger").insert_calls, "ledger entry not written"
        assert (ids.universe, ids.owner) in pg.world_get_for_owner_calls

    def test_foreign_owner_leaves_memory_collection_empty(
        self,
        ids: Ids,
        fx: tuple[FakeMongo, FakeNeo4j, FakePostgres],
    ) -> None:
        mongo, _neo4j, _pg = fx
        set_owner_id(ids.other)
        with pytest.raises(OwnerViolationError):
            mongodb_create_memory(
                MemoryCreate(universe_id=UUID(ids.universe), entity_id=UUID(ids.entity_id), text="a memory")
            )
        assert mongo.get_collection("character_memories").insert_calls == []
