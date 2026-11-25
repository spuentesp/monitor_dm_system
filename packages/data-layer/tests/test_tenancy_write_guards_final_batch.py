"""Tool-boundary ownership for the final FU-guards batch.

Covers character templates, GM prep bundles, world profiles, prompt
collections, random tables, scene rewind, world-snapshot restore, commit
webhooks, working state, world clock/deadlines, universe fork, and the
Neo4j entity/agenda/mechanics write tools. For each tool the same contract
as the other guard suites:

- a foreign owner bound in context is refused with ``OwnerViolationError``
  and nothing is written;
- the matching owner passes the gate, and the Postgres ownership registry is
  consulted for the target universe;
- with no owner bound (workers, scripts, local mode) the registry is never
  consulted — behavior is unchanged.

Character templates carry ``owner_id`` directly (no universe chain), so they
are pinned in ``TestCharacterTemplateDirectOwner`` with the direct-owner
contract: a foreign owner is refused without touching the registry, the
matching owner passes on the stored owner alone, and no owner is unchanged.

Global rows stay shared exactly like tone libraries: prompt collections and
random tables without a ``universe_id`` (and character templates without an
owner stamp) are admin-gated over HTTP, not at the tool boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from _tenancy_fakes import FakeMongo, FakeNeo4j, FakePostgres, install_fakes

from monitor_data.schemas.character_templates import CharacterTemplateCreate, CharacterTemplateUpdate
from monitor_data.schemas.entities import StateTagsUpdate
from monitor_data.schemas.gm_prep import GmPrepBundleUpsert
from monitor_data.schemas.knowledge_packs import EmbeddedWorldProfile
from monitor_data.schemas.prompt_collections import (
    PromptCollectionCreate,
    PromptCollectionPublish,
    PromptCollectionUpdate,
)
from monitor_data.schemas.random_tables import RandomTableCreate, RandomTableUpdate
from monitor_data.schemas.relationships import StateTag, StateTagUpdate
from monitor_data.schemas.webhooks import CommitWebhookCreate, CommitWebhookUpdate
from monitor_data.schemas.working_state import AddStatModification, WorkingStateCreate, WorkingStateUpdate
from monitor_data.schemas.world_clock import WorldClockAdvance, WorldClockDeadlineUpsert
from monitor_data.tenancy import OwnerViolationError, set_owner_id
from monitor_data.tools.mongodb_tools import (
    character_templates,
    gm_prep,
    profiles,
    prompt_collections,
    random_tables,
    scene_rewind,
    snapshots,
    webhook_tools,
    working_state,
    world_clock,
    world_fork,
)
from monitor_data.tools.neo4j_tools import agendas, entities, mechanics, relationships as neo4j_tools_relationships

# Fixed ids shared by setup and invoke so Neo4j universe resolution can be
# pre-registered for each case.
_ENTITY_ID = uuid4()
_FROM_ID = uuid4()
_TO_ID = uuid4()
_ARCHETYPE_ID = uuid4()
_AGENDA_ID = uuid4()


@pytest.fixture(autouse=True)
def _clean_owner_ctx() -> Iterator[None]:
    set_owner_id(None)
    yield
    set_owner_id(None)


@pytest.fixture
def fx(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeMongo, FakeNeo4j, FakePostgres]:
    return install_fakes(monkeypatch)


@dataclass
class Case:
    name: str
    # Prepare stored state (existing docs, Neo4j universe links) for a universe.
    setup: Callable[[FakeMongo, FakeNeo4j, str], None]
    # Invoke the tool against that universe.
    invoke: Callable[[str], Any]


def _nothing(_mongo: FakeMongo, _neo4j: FakeNeo4j, _universe: str) -> None:
    return None


def _doc_in(collection: str, **fields: Any) -> Callable[[FakeMongo, FakeNeo4j, str], None]:
    def setup(mongo: FakeMongo, _neo4j: FakeNeo4j, universe: str) -> None:
        mongo.get_collection(collection).find_one_result = {
            "universe_id": universe,
            "created_at": datetime.now(UTC),
            **fields,
        }

    return setup


def _restore_version_setup(mongo: FakeMongo, _neo4j: FakeNeo4j, universe: str) -> None:
    mongo.get_collection("prompt_collection_versions").find_one_result = {
        "version_id": str(uuid4()),
        "collection_id": str(uuid4()),
        "version": "v1",
        "name": "n",
        "entries": [],
        "published_at": datetime.now(UTC),
    }
    mongo.get_collection("prompt_collections").find_one_result = {
        "collection_id": str(uuid4()),
        "universe_id": universe,
        "name": "n",
        "created_at": datetime.now(UTC),
    }


def _webhook_in(mongo: FakeMongo, _neo4j: FakeNeo4j, universe: str) -> None:
    mongo.get_collection("commit_webhooks").find_one_result = {
        "webhook_id": str(uuid4()),
        "multiverse_id": universe,
        "universe_id": universe,
        "callback_url": "http://example.invalid/hook",
        "description": "",
        "enabled": True,
        "created_at": datetime.now(UTC),
    }


def _entity_in_universe(_mongo: FakeMongo, neo4j: FakeNeo4j, universe: str) -> None:
    neo4j.universe_by_id[str(_ENTITY_ID)] = universe


def _both_characters_in_universe(_mongo: FakeMongo, neo4j: FakeNeo4j, universe: str) -> None:
    neo4j.universe_by_id[str(_FROM_ID)] = universe
    neo4j.universe_by_id[str(_TO_ID)] = universe


def _agenda_in_universe(_mongo: FakeMongo, neo4j: FakeNeo4j, universe: str) -> None:
    neo4j.universe_by_id[str(_AGENDA_ID)] = universe


def _working_state(mongo: FakeMongo, neo4j: FakeNeo4j, universe: str) -> None:
    mongo.get_collection("character_working_state").find_one_result = {
        "state_id": str(uuid4()),
        "entity_id": str(_ENTITY_ID),
    }
    neo4j.universe_by_id[str(_ENTITY_ID)] = universe


CASES = [
    Case(
        "upsert_gm_prep_bundle",
        _nothing,
        lambda u: gm_prep.mongodb_upsert_gm_prep_bundle(GmPrepBundleUpsert.model_construct(universe_id=UUID(u))),
    ),
    Case(
        "upsert_world_profile",
        _nothing,
        lambda u: profiles.mongodb_upsert_world_profile(UUID(u), EmbeddedWorldProfile.model_construct()),
    ),
    Case(
        "create_prompt_collection",
        _nothing,
        lambda u: prompt_collections.mongodb_create_prompt_collection(
            PromptCollectionCreate.model_construct(name="c", universe_id=UUID(u))
        ),
    ),
    Case(
        "update_prompt_collection",
        _doc_in("prompt_collections", collection_id=str(uuid4()), name="n"),
        lambda u: prompt_collections.mongodb_update_prompt_collection(
            uuid4(), PromptCollectionUpdate.model_construct(name="x")
        ),
    ),
    Case(
        "delete_prompt_collection",
        _doc_in("prompt_collections", collection_id=str(uuid4()), name="n"),
        lambda u: prompt_collections.mongodb_delete_prompt_collection(uuid4()),
    ),
    Case(
        "publish_prompt_collection",
        _doc_in("prompt_collections", collection_id=str(uuid4()), name="n"),
        lambda u: prompt_collections.mongodb_publish_prompt_collection(
            uuid4(), PromptCollectionPublish.model_construct(version=None, note=None)
        ),
    ),
    Case(
        "restore_prompt_collection_version",
        _restore_version_setup,
        lambda u: prompt_collections.mongodb_restore_prompt_collection_version(uuid4()),
    ),
    Case(
        "create_random_table",
        _nothing,
        lambda u: random_tables.mongodb_create_random_table(
            RandomTableCreate.model_construct(universe_id=UUID(u), name="t", dice_formula="1d6", entries=[])
        ),
    ),
    Case(
        "update_random_table",
        _doc_in("random_tables", table_id=str(uuid4()), name="t"),
        lambda u: random_tables.mongodb_update_random_table(uuid4(), RandomTableUpdate.model_construct()),
    ),
    Case(
        "delete_random_table",
        _doc_in("random_tables", table_id=str(uuid4()), name="t"),
        lambda u: random_tables.mongodb_delete_random_table(uuid4()),
    ),
    Case(
        "rewind_scene",
        # The scene resolves its universe through the Mongo scene doc.
        _doc_in("scenes", scene_id=str(uuid4())),
        lambda u: scene_rewind.mongodb_rewind_scene(uuid4(), datetime.now(UTC)),
    ),
    Case(
        "restore_world_snapshot",
        _doc_in("world_snapshots", snapshot_id=str(uuid4()), entities=[], facts=[], relationships=[]),
        lambda u: snapshots.mongodb_restore_world_snapshot(uuid4()),
    ),
    Case(
        "create_commit_webhook",
        _nothing,
        # The webhook's multiverse id doubles as the universe id here so the
        # shared registry assertions cover both registry tables.
        lambda u: webhook_tools.mongodb_create_commit_webhook(
            CommitWebhookCreate.model_construct(
                multiverse_id=UUID(u),
                universe_id=UUID(u),
                callback_url="http://example.invalid/hook",
            )
        ),
    ),
    Case(
        "update_commit_webhook",
        _webhook_in,
        lambda u: webhook_tools.mongodb_update_commit_webhook(
            uuid4(), CommitWebhookUpdate.model_construct(enabled=False)
        ),
    ),
    Case(
        "delete_commit_webhook",
        _webhook_in,
        lambda u: webhook_tools.mongodb_delete_commit_webhook(uuid4()),
    ),
    Case(
        "create_working_state",
        _entity_in_universe,
        lambda u: working_state.mongodb_create_working_state(
            WorkingStateCreate.model_construct(
                entity_id=_ENTITY_ID,
                scene_id=uuid4(),
                story_id=uuid4(),
                base_stats={},
                current_stats=None,
                resources={},
            )
        ),
    ),
    Case(
        "update_working_state",
        _working_state,
        lambda u: working_state.mongodb_update_working_state(uuid4(), WorkingStateUpdate.model_construct()),
    ),
    Case(
        "add_modification",
        _working_state,
        lambda u: working_state.mongodb_add_modification(
            AddStatModification.model_construct(state_id=uuid4(), stat_or_resource="hp", change=-1, source="test")
        ),
    ),
    Case(
        "advance_world_clock",
        _nothing,
        lambda u: world_clock.mongodb_advance_world_clock(
            WorldClockAdvance.model_construct(universe_id=UUID(u), story_id=uuid4(), delta="+1 day", target_time=None)
        ),
    ),
    Case(
        "upsert_world_deadline",
        _doc_in(
            "world_clocks",
            story_id=str(uuid4()),
            current_at=datetime.now(UTC),
            deadlines=[],
            advances=[],
            display="",
        ),
        lambda u: world_clock.mongodb_upsert_world_deadline(
            WorldClockDeadlineUpsert.model_construct(
                universe_id=UUID(u), story_id=uuid4(), title="due", due_at=datetime.now(UTC)
            )
        ),
    ),
    Case(
        "fork_universe_data",
        _nothing,
        # Source and destination are the same universe so the shared matching
        # owner owns both ends of the copy.
        lambda u: world_fork.mongodb_fork_universe_data(UUID(u), UUID(u), "w_"),
    ),
    Case(
        "set_state_tags",
        _entity_in_universe,
        lambda u: entities.neo4j_set_state_tags(
            _ENTITY_ID, StateTagsUpdate.model_construct(add_tags=["wounded"], remove_tags=[])
        ),
    ),
    Case(
        "update_state_tags",
        _entity_in_universe,
        lambda u: neo4j_tools_relationships.neo4j_update_state_tags(
            StateTagUpdate.model_construct(entity_id=_ENTITY_ID, add_tags=[StateTag.ALIVE], remove_tags=[])
        ),
    ),
    Case(
        "link_to_archetype",
        _entity_in_universe,
        lambda u: entities.neo4j_link_to_archetype(_ENTITY_ID, _ARCHETYPE_ID),
    ),
    Case(
        "create_character_relationship",
        _both_characters_in_universe,
        lambda u: entities.neo4j_create_character_relationship(_FROM_ID, _TO_ID, "ALLY_OF"),
    ),
    Case(
        "link_entity_to_ability",
        _entity_in_universe,
        lambda u: mechanics.neo4j_link_entity_to_ability(entity_id=str(_ENTITY_ID), ability_system_name="dnd5e"),
    ),
    Case(
        "tick_agendas",
        _nothing,
        lambda u: entities.neo4j_tick_agendas(u),
    ),
    Case(
        "create_agenda",
        _nothing,
        lambda u: agendas.neo4j_create_agenda({"universe_id": u, "title": "t"}),
    ),
    Case(
        "update_agenda_clock",
        _agenda_in_universe,
        lambda u: agendas.neo4j_update_agenda_clock(_AGENDA_ID, 1),
    ),
]
IDS = [c.name for c in CASES]


def _run_ignoring_tool_preconditions(invoke: Callable[[], Any]) -> None:
    """Run past the gate; the tool's own downstream behavior is not under test."""
    try:
        invoke()
    except OwnerViolationError:
        raise
    except Exception:  # noqa: BLE001, S110  # reason: post-gate tool preconditions are outside this contract
        pass


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_foreign_owner_is_refused_and_nothing_is_written(case: Case, fx: Any) -> None:
    mongo, neo4j, pg = fx
    universe, other = str(uuid4()), str(uuid4())
    case.setup(mongo, neo4j, universe)
    set_owner_id(other)
    with pytest.raises(OwnerViolationError):
        case.invoke(universe)
    assert mongo.total_write_calls == 0
    assert neo4j.write_calls == 0
    assert (universe, other) in pg.world_get_for_owner_calls


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_matching_owner_passes_the_gate(case: Case, fx: Any) -> None:
    mongo, neo4j, pg = fx
    universe, owner = str(uuid4()), str(uuid4())
    pg.owned_universes.add(universe)
    # Commit-webhook cases use the universe id as their multiverse id.
    pg.owned_multiverses.add(universe)
    case.setup(mongo, neo4j, universe)
    set_owner_id(owner)
    _run_ignoring_tool_preconditions(lambda: case.invoke(universe))
    assert (universe, owner) in pg.world_get_for_owner_calls


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_no_owner_in_context_never_consults_the_registry(case: Case, fx: Any) -> None:
    mongo, neo4j, pg = fx
    universe = str(uuid4())
    case.setup(mongo, neo4j, universe)
    _run_ignoring_tool_preconditions(lambda: case.invoke(universe))
    assert pg.world_get_for_owner_calls == []
    assert pg.multiverse_get_for_owner_calls == []


class TestCharacterTemplateDirectOwner:
    """Character templates are rootless docs stamped with ``owner_id``:
    direct-owner match, no registry round-trip."""

    def test_foreign_owner_refused_on_create_and_writes_nothing(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        owner, other = str(uuid4()), str(uuid4())
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            character_templates.mongodb_create_character_template(
                CharacterTemplateCreate.model_construct(name="t"), owner_id=owner
            )
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == []

    def test_matching_owner_create_passes_without_the_registry(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        owner = str(uuid4())
        set_owner_id(owner)
        _run_ignoring_tool_preconditions(
            lambda: character_templates.mongodb_create_character_template(
                CharacterTemplateCreate.model_construct(name="t"), owner_id=owner
            )
        )
        assert mongo.total_write_calls == 1
        assert pg.world_get_for_owner_calls == []

    def test_no_owner_create_is_unchanged(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        set_owner_id(None)
        _run_ignoring_tool_preconditions(
            lambda: character_templates.mongodb_create_character_template(
                CharacterTemplateCreate.model_construct(name="t"), owner_id=str(uuid4())
            )
        )
        assert mongo.total_write_calls == 1
        assert pg.world_get_for_owner_calls == []

    def test_foreign_owner_refused_on_update_and_writes_nothing(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        owner, other = str(uuid4()), str(uuid4())
        mongo.get_collection("characters").find_one_result = {"id": str(uuid4()), "owner_id": owner}
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            character_templates.mongodb_update_character_template(
                uuid4(), CharacterTemplateUpdate.model_construct(name="x")
            )
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == []

    def test_matching_owner_update_passes(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        owner = str(uuid4())
        mongo.get_collection("characters").find_one_result = {"id": str(uuid4()), "owner_id": owner, "name": "t"}
        set_owner_id(owner)
        _run_ignoring_tool_preconditions(
            lambda: character_templates.mongodb_update_character_template(
                uuid4(), CharacterTemplateUpdate.model_construct(name="x")
            )
        )
        assert pg.world_get_for_owner_calls == []

    def test_foreign_owner_refused_on_delete_and_writes_nothing(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        owner, other = str(uuid4()), str(uuid4())
        mongo.get_collection("characters").find_one_result = {"id": str(uuid4()), "owner_id": owner}
        set_owner_id(other)
        with pytest.raises(OwnerViolationError):
            character_templates.mongodb_delete_character_template(uuid4())
        assert mongo.total_write_calls == 0
        assert pg.world_get_for_owner_calls == []

    def test_no_owner_delete_is_unchanged(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        set_owner_id(None)
        _run_ignoring_tool_preconditions(lambda: character_templates.mongodb_delete_character_template(uuid4()))
        assert mongo.total_write_calls == 1
        assert pg.world_get_for_owner_calls == []


class TestMultiverseScopedWebhook:
    """Commit webhooks always name a multiverse (Postgres registry root);
    the optional ``universe_id`` narrows the scope and is asserted too."""

    def test_foreign_multiverse_refused_without_universe_scope(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        mv = str(uuid4())
        mongo.get_collection("commit_webhooks").find_one_result = {
            "webhook_id": str(uuid4()),
            "multiverse_id": mv,
            "universe_id": None,
        }
        set_owner_id(str(uuid4()))
        with pytest.raises(OwnerViolationError):
            webhook_tools.mongodb_delete_commit_webhook(uuid4())
        assert mongo.total_write_calls == 0
        assert pg.multiverse_get_for_owner_calls != []

    def test_matching_multiverse_passes_and_multiverse_registry_consulted(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        mv, owner = str(uuid4()), str(uuid4())
        pg.owned_multiverses.add(mv)
        mongo.get_collection("commit_webhooks").find_one_result = {
            "webhook_id": str(uuid4()),
            "multiverse_id": mv,
            "universe_id": None,
        }
        set_owner_id(owner)
        _run_ignoring_tool_preconditions(lambda: webhook_tools.mongodb_delete_commit_webhook(uuid4()))
        assert (mv, owner) in pg.multiverse_get_for_owner_calls
        assert pg.world_get_for_owner_calls == []


class TestGlobalRowsStayShared:
    """Prompt collections / random tables without a universe (and global
    rows on update/delete) are admin-gated over HTTP — no tool-level gate."""

    def test_global_prompt_collection_create_does_not_consult_the_registry(self, fx: Any) -> None:
        _mongo, _neo4j, pg = fx
        set_owner_id(str(uuid4()))
        _run_ignoring_tool_preconditions(
            lambda: prompt_collections.mongodb_create_prompt_collection(
                PromptCollectionCreate.model_construct(name="global", universe_id=None)
            )
        )
        assert pg.world_get_for_owner_calls == []

    def test_global_prompt_collection_delete_allowed_with_a_user_bound(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        mongo.get_collection("prompt_collections").find_one_result = {
            "collection_id": str(uuid4()),
            "universe_id": None,
        }
        set_owner_id(str(uuid4()))
        _run_ignoring_tool_preconditions(lambda: prompt_collections.mongodb_delete_prompt_collection(uuid4()))
        assert mongo.total_write_calls == 1
        assert pg.world_get_for_owner_calls == []

    def test_global_random_table_create_does_not_consult_the_registry(self, fx: Any) -> None:
        _mongo, _neo4j, pg = fx
        set_owner_id(str(uuid4()))
        _run_ignoring_tool_preconditions(
            lambda: random_tables.mongodb_create_random_table(
                RandomTableCreate.model_construct(universe_id=None, name="g", dice_formula="1d6", entries=[])
            )
        )
        assert pg.world_get_for_owner_calls == []


class TestFailClosedEdges:
    def test_agenda_clock_refused_when_agenda_resolves_to_no_universe(self, fx: Any) -> None:
        _mongo, neo4j, pg = fx
        set_owner_id(str(uuid4()))
        with pytest.raises(OwnerViolationError):
            agendas.neo4j_update_agenda_clock(uuid4(), 1)
        assert neo4j.write_calls == 0
        assert pg.world_get_for_owner_calls == []

    def test_world_profile_refused_when_no_universe_names(self, fx: Any) -> None:
        mongo, _neo4j, pg = fx
        set_owner_id(str(uuid4()))
        with pytest.raises(OwnerViolationError):
            profiles.mongodb_upsert_world_profile(None, EmbeddedWorldProfile.model_construct())  # type: ignore[arg-type]
        assert mongo.total_write_calls == 0
