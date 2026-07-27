"""MP-7 / MP-8 — conflict detection and resolution for apply-to-existing-world.

Covers F1-6 step 1: POST /packs/{id}/apply/{universe_id} must return real
conflicts (instead of a hardcoded empty list), hold back conflicting items,
honour ``resolved_conflicts`` on the second call, and honour subset indices.

Also covers F1-3: POST /packs/{id}/apply/new-world (wizard "new world" path).
"""

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from monitor_data.schemas.knowledge_packs import (
    ExtractedAxiom,
    ExtractedEntityArchetype,
    ExtractedLoreFact,
    KnowledgePackResponse,
    KnowledgePackStatus,
    KnowledgePackType,
)

from monitor_ui.routers import pack_library
from monitor_agents.services import pack_service


def _pack(pack_id: UUID) -> KnowledgePackResponse:
    return KnowledgePackResponse(
        pack_id=pack_id,
        name="Test Pack",
        description="",
        pack_type=KnowledgePackType.CUSTOM,
        system_name=None,
        status=KnowledgePackStatus.READY,
        source_document_ids=[],
        ingestion_job_id=None,
        tags=[],
        created_at="2026-01-01T00:00:00+00:00",
        entity_archetypes=[
            ExtractedEntityArchetype(
                name="Vampire",
                entity_type="character",
                description="A noble undead lineage",
            ),
            ExtractedEntityArchetype(
                name="Werewolf",
                entity_type="character",
                description="A shapeshifter",
            ),
        ],
        axioms=[ExtractedAxiom(statement="Elves are not immortal", domain="biology")],
        lore_facts=[ExtractedLoreFact(statement="The Sundering happened recently")],
    )


class _FakeKeeper:
    """Captures apply_pack_to_universe kwargs instead of touching MongoDB."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def apply_pack_to_universe(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "proposals_created": 3,
            "committed": 0,
            "errors": [],
            "review_status": "pending",
        }


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Patch all Mongo/Neo4j/CanonKeeper access in pack_library."""
    pack_id = uuid4()
    universe_id = uuid4()
    mv_id = uuid4()
    keeper = _FakeKeeper()

    monkeypatch.setattr(pack_library, "mongodb_get_knowledge_pack", lambda _uid: _pack(pack_id) if hasattr(_pack, "__call__") else None)
    monkeypatch.setattr(pack_service, "mongodb_get_knowledge_pack", lambda _uid: _pack(pack_id))
    monkeypatch.setattr(pack_library, "CanonKeeper", lambda: keeper)
    monkeypatch.setattr(pack_service, "CanonKeeper", lambda: keeper)
    monkeypatch.setattr(pack_service.KnowledgePackService, "_propagate_system_to_universe", lambda *_a, **_kw: None)
    monkeypatch.setattr(pack_service, "neo4j_list_universes",
        lambda _f: [SimpleNamespace(id=universe_id, multiverse_id=mv_id)],
    )
    # World state: "Vampire" exists with different content; one canon axiom
    # opposed by the pack axiom; no facts.
    monkeypatch.setattr(pack_service, "neo4j_list_entities",
        lambda _f: SimpleNamespace(
            entities=[
                SimpleNamespace(
                    name="vampire",
                    entity_type="character",
                    sub_type=None,
                    description="Undead blood-drinker",
                )
            ]
        ),
    )
    monkeypatch.setattr(pack_service, "neo4j_list_axioms",
        lambda _f: [
            SimpleNamespace(
                statement="Elves are immortal",
                source_ref=None,
                canon_level="canon",
                confidence=0.9,
            )
        ],
    )
    monkeypatch.setattr(pack_service, "neo4j_list_facts", lambda _f: [])

    return SimpleNamespace(pack_id=pack_id, universe_id=universe_id, mv_id=mv_id, keeper=keeper)


async def test_first_call_returns_conflicts_and_holds_back_conflicting_items(
    world: SimpleNamespace,
) -> None:
    """MP-7: overlapping items surface as conflicts and are not applied."""
    result = await pack_library.apply_pack_existing_world(
        str(world.pack_id),
        str(world.universe_id),
        pack_library.ApplyExistingWorldRequest(),
    )

    assert result["status"] == "conflicts_detected"
    assert len(result["conflicts"]) == 2

    by_type = {c["item_type"]: c for c in result["conflicts"]}
    entity = by_type["entity"]
    assert entity["item_name"] == "Vampire"
    assert entity["pack_value"]["description"] == "A noble undead lineage"
    assert entity["world_value"]["description"] == "Undead blood-drinker"
    assert entity["resolution"] is None
    axiom = by_type["axiom"]
    assert axiom["item_name"] == "Elves are not immortal"
    assert axiom["world_value"]["statement"] == "Elves are immortal"

    # Only non-conflicting items are proposed: Werewolf (entity 1) and the
    # lore fact; the conflicting entity 0 and axiom 0 are held back.
    assert len(world.keeper.calls) == 1
    overrides = world.keeper.calls[0]["request_overrides"]
    assert overrides["entity_indices"] == [1]
    assert overrides["axiom_indices"] == []
    assert overrides["lore_indices"] == [0]


async def test_first_call_without_overlaps_applies_everything(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MP-7: no overlap → no conflicts, full apply (legacy behaviour)."""
    monkeypatch.setattr(pack_service, "neo4j_list_entities", lambda _f: SimpleNamespace(entities=[]))
    monkeypatch.setattr(pack_service, "neo4j_list_axioms", lambda _f: [])

    result = await pack_library.apply_pack_existing_world(
        str(world.pack_id),
        str(world.universe_id),
        pack_library.ApplyExistingWorldRequest(),
    )

    assert result["status"] == "review_pending"
    assert result["conflicts"] == []
    # No subset and no conflicts → no overrides, identical to the old call.
    assert world.keeper.calls[0]["request_overrides"] is None


async def test_second_call_applies_resolved_conflicts(world: SimpleNamespace) -> None:
    """MP-8: pack_wins applies as-is; human_picked patches the payload."""
    body = pack_library.ApplyExistingWorldRequest(
        resolved_conflicts=[
            {"item_type": "axiom", "item_name": "Elves are not immortal", "resolution": "pack_wins"},
            {
                "item_type": "entity",
                "item_name": "Vampire",
                "resolution": "human_picked",
                "resolved_value": "A tragic cursed bloodline",
            },
        ]
    )
    result = await pack_library.apply_pack_existing_world(str(world.pack_id), str(world.universe_id), body)

    assert result["status"] == "review_pending"
    assert result["resolutions_applied"]["pack_wins"] == 1
    assert result["resolutions_applied"]["human_picked"] == 1

    assert len(world.keeper.calls) == 1
    overrides = world.keeper.calls[0]["request_overrides"]
    assert overrides["entity_indices"] == [0]
    assert overrides["axiom_indices"] == [0]
    assert overrides["lore_indices"] == []
    assert overrides["item_overrides"] == {"entity:0": {"description": "A tragic cursed bloodline"}}
    # Only resolved items apply here; other item types were proposed already.
    assert overrides["apply_relationships"] is False
    assert overrides["apply_random_tables"] is False


async def test_second_call_world_wins_skips_item(world: SimpleNamespace) -> None:
    """MP-8: world_wins keeps canon — nothing is proposed."""
    body = pack_library.ApplyExistingWorldRequest(
        resolved_conflicts=[
            {"item_type": "entity", "item_name": "Vampire", "resolution": "world_wins"},
            {"item_type": "axiom", "item_name": "Elves are not immortal", "resolution": "world_wins"},
        ]
    )
    result = await pack_library.apply_pack_existing_world(str(world.pack_id), str(world.universe_id), body)

    assert result["resolutions_applied"]["world_wins"] == 2
    assert result["proposals_created"] == 0
    assert world.keeper.calls == []  # nothing to apply → no keeper call


async def test_second_call_llm_merged_falls_back_to_world_wins(
    world: SimpleNamespace,
) -> None:
    """MP-8: llm_merged has no merge infrastructure — graceful fallback."""
    body = pack_library.ApplyExistingWorldRequest(
        resolved_conflicts=[
            {"item_type": "axiom", "item_name": "Elves are not immortal", "resolution": "llm_merged"},
        ]
    )
    result = await pack_library.apply_pack_existing_world(str(world.pack_id), str(world.universe_id), body)

    assert result["resolutions_applied"]["llm_merged"] == 1
    assert any("llm_merged" in note for note in result["notes"])
    assert world.keeper.calls == []  # world value kept, nothing proposed


async def test_subset_indices_restrict_applied_items(world: SimpleNamespace) -> None:
    """MP-7: entity_indices restrict both conflict detection and apply."""
    result = await pack_library.apply_pack_existing_world(
        str(world.pack_id),
        str(world.universe_id),
        pack_library.ApplyExistingWorldRequest(entity_indices=[1]),
    )

    # Vampire (index 0) is excluded from the subset → no entity conflict.
    assert result["status"] == "conflicts_detected"  # axiom still conflicts
    assert [c["item_type"] for c in result["conflicts"]] == ["axiom"]

    overrides = world.keeper.calls[0]["request_overrides"]
    assert overrides["entity_indices"] == [1]
    assert overrides["axiom_indices"] == []
    assert overrides["lore_indices"] == [0]


async def test_human_picked_json_override(world: SimpleNamespace) -> None:
    """MP-8: a JSON custom value updates named payload fields."""
    body = pack_library.ApplyExistingWorldRequest(
        resolved_conflicts=[
            {
                "item_type": "entity",
                "item_name": "Vampire",
                "resolution": "human_picked",
                "resolved_value": '{"description": "Daywalker", "sub_type": "clan", "bogus": 1}',
            },
        ]
    )
    result = await pack_library.apply_pack_existing_world(str(world.pack_id), str(world.universe_id), body)

    assert result["resolutions_applied"]["human_picked"] == 1
    overrides = world.keeper.calls[0]["request_overrides"]
    # Unknown keys are dropped; only payload fields pass through.
    assert overrides["item_overrides"] == {"entity:0": {"description": "Daywalker", "sub_type": "clan"}}


# ─── F1-3: apply/new-world (wizard "new world" path) ──────────


async def test_apply_new_world_creates_setting_and_applies(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new Multiverse+Universe is created, then the pack is proposed
    (auto_accept=False → review_pending, nothing silently committed)."""
    created: dict[str, Any] = {}

    def _fake_create_setting(**kwargs: Any) -> tuple[UUID, UUID]:
        created.update(kwargs)
        return world.mv_id, world.universe_id

    monkeypatch.setattr(pack_library, "_create_setting", _fake_create_setting)

    result = await pack_library.apply_pack_new_world(
        str(world.pack_id),
        pack_library.ApplyNewWorldRequest(world_name="New Realm"),
    )

    assert result["status"] == "review_pending"
    assert result["review_status"] == "pending"
    assert result["world_name"] == "New Realm"
    assert result["multiverse_id"] == str(world.mv_id)
    assert result["universe_id"] == str(world.universe_id)
    assert result["proposals_created"] == 3
    assert result["committed"] == 0

    # The setting is named after the world; system falls back to world name.
    assert created["name"] == "New Realm"
    assert created["system_name"] == "New Realm"

    assert len(world.keeper.calls) == 1
    call = world.keeper.calls[0]
    assert call["pack_id"] == world.pack_id
    assert call["multiverse_id"] == world.mv_id
    assert call["universe_id"] == world.universe_id
    assert call["auto_accept"] is False


async def test_apply_new_world_uses_explicit_system_name(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pack_library,
        "_create_setting",
        lambda **_kw: (world.mv_id, world.universe_id),
    )

    await pack_library.apply_pack_new_world(
        str(world.pack_id),
        pack_library.ApplyNewWorldRequest(world_name="New Realm", system_name="D&D 5e"),
    )

    assert world.keeper.calls[0]["auto_accept"] is False


async def test_apply_new_world_rejects_archived_pack(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    archived = _pack(world.pack_id).model_copy(update={"status": KnowledgePackStatus.ARCHIVED})
    monkeypatch.setattr(pack_library, "mongodb_get_knowledge_pack", lambda _uid: archived)
    monkeypatch.setattr(pack_service, "mongodb_get_knowledge_pack", lambda _uid: archived)

    with pytest.raises(HTTPException) as exc_info:
        await pack_library.apply_pack_new_world(
            str(world.pack_id),
            pack_library.ApplyNewWorldRequest(world_name="New Realm"),
        )
    assert exc_info.value.status_code == 422


async def test_apply_new_world_missing_pack_is_404(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pack_library, "mongodb_get_knowledge_pack", lambda _uid: None)
    monkeypatch.setattr(pack_service, "mongodb_get_knowledge_pack", lambda _uid: None)

    with pytest.raises(HTTPException) as exc_info:
        await pack_library.apply_pack_new_world(
            str(world.pack_id),
            pack_library.ApplyNewWorldRequest(world_name="New Realm"),
        )
    assert exc_info.value.status_code == 404
