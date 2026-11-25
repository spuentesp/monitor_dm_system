"""Tool-boundary ownership for the last write tools that were HTTP-only.

Covers documents, book records, foreshadowing, generated assets, merge
candidates/proposals, GM profiles, world snapshots and transcripts. For each
tool the same contract as the other guard suites:

- a foreign owner bound in context is refused with ``OwnerViolationError``
  and nothing is written;
- the matching owner passes the gate, and the Postgres ownership registry is
  consulted for the target universe;
- with no owner bound (workers, scripts, local mode) the registry is never
  consulted — behavior is unchanged.

Tone profiles and tag definitions are deliberately not guarded at the tool
boundary (global registries, admin-only over HTTP, also written by
CanonKeeper while applying a pack); ``TestGlobalRegistriesStayShared``
pins that decision.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from _tenancy_fakes import FakeMongo, FakeNeo4j, FakePostgres, install_fakes

from monitor_data.schemas.documents import DocumentCreate, DocumentUpdate
from monitor_data.schemas.foreshadowing import ForeshadowingCreate
from monitor_data.schemas.generated_assets import GeneratedAssetCreate, GeneratedAssetUpdate, ReferenceStatus
from monitor_data.schemas.gm_profiles import GMProfileCreate, GMProfileUpdate
from monitor_data.schemas.merge_candidates import EntityMergeCandidate, MergeProposalStatus
from monitor_data.schemas.transcripts import TranscriptCreate, TranscriptUpdate
from monitor_data.schemas.world_snapshots import WorldSnapshotCreate
from monitor_data.tenancy import OwnerViolationError, set_owner_id
from monitor_data.tools.mongodb_tools import (
    book_decomposition,
    documents,
    foreshadowing,
    generated_assets,
    merge_candidates,
    profiles,
    snapshots,
    transcripts,
)


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
    # Prepare stored state (existing docs) for a target universe.
    setup: Callable[[FakeMongo, str], None]
    # Invoke the tool against that universe.
    invoke: Callable[[str], Any]


def _existing(collection: str) -> Callable[[FakeMongo, str], None]:
    def setup(mongo: FakeMongo, universe: str) -> None:
        mongo.get_collection(collection).find_one_result = {"universe_id": universe}

    return setup


def _nothing(_mongo: FakeMongo, _universe: str) -> None:
    return None


def _scene_in(mongo: FakeMongo, universe: str) -> None:
    mongo.get_collection("scenes").find_one_result = {"universe_id": universe}


CASES = [
    Case(
        "create_document",
        _nothing,
        lambda u: documents.mongodb_create_document(
            DocumentCreate.model_construct(source_id=uuid4(), universe_id=UUID(u), owner_id=None, title="t")
        ),
    ),
    Case(
        "update_document",
        _existing("documents"),
        lambda u: documents.mongodb_update_document(uuid4(), DocumentUpdate.model_construct()),
    ),
    Case(
        "upsert_book_records",
        _existing("documents"),
        lambda u: book_decomposition.mongodb_upsert_book_records(
            str(uuid4()),
            "section",
            [],  # type: ignore[arg-type]
        ),
    ),
    Case(
        "delete_book_records",
        _existing("documents"),
        lambda u: book_decomposition.mongodb_delete_book_records(str(uuid4())),
    ),
    Case(
        "create_foreshadowing",
        _scene_in,
        lambda u: foreshadowing.mongodb_create_foreshadowing(
            ForeshadowingCreate.model_construct(scene_id=uuid4(), story_id=uuid4(), summary="s")
        ),
    ),
    Case(
        "create_generated_asset",
        _nothing,
        lambda u: generated_assets.mongodb_create_generated_asset(
            GeneratedAssetCreate.model_construct(universe_id=UUID(u), character_id=None, entity_id=None)
        ),
    ),
    Case(
        "update_generated_asset",
        _existing("generated_assets"),
        lambda u: generated_assets.mongodb_update_generated_asset(uuid4(), GeneratedAssetUpdate.model_construct()),
    ),
    Case(
        "approve_generated_asset",
        _existing("generated_assets"),
        lambda u: generated_assets.mongodb_approve_generated_asset(
            uuid4(), approved_by="gm", reference_status=next(iter(ReferenceStatus))
        ),
    ),
    Case(
        "reject_generated_asset",
        _existing("generated_assets"),
        lambda u: generated_assets.mongodb_reject_generated_asset(uuid4(), rejected_by="gm"),
    ),
    Case(
        "save_merge_candidate",
        _nothing,
        lambda u: merge_candidates.mongodb_save_merge_candidate(
            EntityMergeCandidate.model_construct(candidate_id=uuid4(), universe_id=UUID(u), entity_ids=[])
        ),
    ),
    Case(
        "delete_merge_candidate",
        _existing("entity_merge_candidates"),
        lambda u: merge_candidates.mongodb_delete_merge_candidate(uuid4()),
    ),
    Case(
        "create_merge_proposal",
        _nothing,
        lambda u: merge_candidates.mongodb_create_merge_proposal(
            merged_name="m",
            merged_entity_type="character",
            merged_description="d",
            merged_properties={},
            merged_tags=[],
            source_entity_ids=[],
            source_pack_ids=[],
            resolution_notes={},
            universe_id=UUID(u),
        ),
    ),
    Case(
        "update_merge_proposal_status",
        _existing("merge_proposals"),
        lambda u: merge_candidates.mongodb_update_merge_proposal_status(uuid4(), next(iter(MergeProposalStatus))),
    ),
    Case(
        "create_gm_profile",
        _nothing,
        lambda u: profiles.mongodb_create_gm_profile(GMProfileCreate.model_construct(name="p", universe_id=UUID(u))),
    ),
    Case(
        "update_gm_profile",
        _existing("gm_profiles"),
        lambda u: profiles.mongodb_update_gm_profile(uuid4(), GMProfileUpdate.model_construct(universe_id=None)),
    ),
    Case("delete_gm_profile", _existing("gm_profiles"), lambda u: profiles.mongodb_delete_gm_profile(uuid4())),
    Case(
        "create_world_snapshot",
        _nothing,
        lambda u: snapshots.mongodb_create_world_snapshot(WorldSnapshotCreate.model_construct(universe_id=UUID(u))),
    ),
    Case(
        "delete_world_snapshot",
        _existing("world_snapshots"),
        lambda u: snapshots.mongodb_delete_world_snapshot(uuid4()),
    ),
    Case(
        "create_transcript",
        _nothing,
        lambda u: transcripts.mongodb_create_transcript(
            TranscriptCreate.model_construct(universe_id=UUID(u), owner_id=str(uuid4()), text="t", segments=[])
        ),
    ),
    Case(
        "update_transcript",
        _existing("transcripts"),
        lambda u: transcripts.mongodb_update_transcript(uuid4(), TranscriptUpdate.model_construct()),
    ),
    Case("delete_transcript", _existing("transcripts"), lambda u: transcripts.mongodb_delete_transcript(uuid4())),
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
    mongo, _neo4j, pg = fx
    universe, other = str(uuid4()), str(uuid4())
    case.setup(mongo, universe)
    set_owner_id(other)
    with pytest.raises(OwnerViolationError):
        case.invoke(universe)
    assert mongo.total_write_calls == 0
    assert (universe, other) in pg.world_get_for_owner_calls


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_matching_owner_passes_the_gate(case: Case, fx: Any) -> None:
    mongo, _neo4j, pg = fx
    universe, owner = str(uuid4()), str(uuid4())
    pg.owned_universes.add(universe)
    case.setup(mongo, universe)
    set_owner_id(owner)
    _run_ignoring_tool_preconditions(lambda: case.invoke(universe))
    assert (universe, owner) in pg.world_get_for_owner_calls


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_no_owner_in_context_never_consults_the_registry(case: Case, fx: Any) -> None:
    mongo, _neo4j, pg = fx
    universe = str(uuid4())
    case.setup(mongo, universe)
    _run_ignoring_tool_preconditions(lambda: case.invoke(universe))
    assert pg.world_get_for_owner_calls == []


class TestDirectOwnerAndEdgeCases:
    def test_document_uploader_passes_even_before_universe_registration(self, fx: Any) -> None:
        """A document stamped with the acting owner passes on owner_id alone."""
        mongo, _neo4j, pg = fx
        owner = str(uuid4())
        set_owner_id(owner)
        _run_ignoring_tool_preconditions(
            lambda: documents.mongodb_create_document(
                DocumentCreate.model_construct(source_id=uuid4(), universe_id=uuid4(), owner_id=owner, title="t")
            )
        )

    def test_global_gm_profile_write_refused_with_a_user_bound(self, fx: Any) -> None:
        mongo, _neo4j, _pg = fx
        set_owner_id(str(uuid4()))
        with pytest.raises(OwnerViolationError):
            profiles.mongodb_create_gm_profile(GMProfileCreate.model_construct(name="p", universe_id=None))
        assert mongo.total_write_calls == 0

    def test_generated_asset_without_any_target_refused_with_a_user_bound(self, fx: Any) -> None:
        mongo, _neo4j, _pg = fx
        set_owner_id(str(uuid4()))
        with pytest.raises(OwnerViolationError):
            generated_assets.mongodb_create_generated_asset(
                GeneratedAssetCreate.model_construct(universe_id=None, character_id=None, entity_id=None)
            )
        assert mongo.total_write_calls == 0


class TestGlobalRegistriesStayShared:
    """Tone profiles / tag definitions: global, admin-gated at HTTP, written by
    CanonKeeper during pack apply in user context — no tool-level owner gate."""

    def test_tone_profile_create_does_not_consult_the_registry(self, fx: Any) -> None:
        from monitor_data.schemas.tone_profiles import ToneProfileCreate
        from monitor_data.tools.mongodb_tools.tone_profiles import mongodb_create_tone_profile

        _mongo, _neo4j, pg = fx
        set_owner_id(str(uuid4()))
        _run_ignoring_tool_preconditions(
            lambda: mongodb_create_tone_profile(ToneProfileCreate.model_construct(name="n", instruction="i"))
        )
        assert pg.world_get_for_owner_calls == []
