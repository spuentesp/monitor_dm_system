"""
Tests for ingestion delta detection (P2-6).
"""

from datetime import UTC, datetime
from uuid import uuid4

from monitor_data.schemas.ingestion_delta import (
    DeltaCategory,
    DeltaItem,
    IngestionDeltaApplyRequest,
)
from monitor_data.schemas.knowledge_packs import (
    ExtractedAxiom,
    ExtractedEntityArchetype,
    ExtractedRandomTable,
    ExtractedRelationship,
    KnowledgePackResponse,
    KnowledgePackStatus,
    KnowledgePackType,
)
from monitor_data.tools.ingest_tools.delta_detection import (
    compute_ingestion_delta,
    filter_delta_for_apply,
)


def _make_pack(**overrides) -> KnowledgePackResponse:
    """Minimal KnowledgePackResponse for testing."""
    now = datetime.now(UTC)
    defaults = {
        "pack_id": uuid4(),
        "name": "Test Pack",
        "description": "",
        "pack_type": KnowledgePackType.RULEBOOK,
        "system_name": "D&D 5e",
        "status": KnowledgePackStatus.READY,
        "source_document_ids": [],
        "ingestion_job_id": None,
        "tags": [],
        "parent_pack_ids": [],
        "axioms": [],
        "entity_archetypes": [],
        "lore_facts": [],
        "entity_relationships": [],
        "random_tables": [],
        "agendas": [],
        "topologies": [],
        "game_system_id": None,
        "game_system_data": None,
        "source_profile_data": None,
        "chunk_summaries": [],
        "section_summaries": [],
        "source_mindscape": None,
        "applied_to": [],
        "axiom_count": 0,
        "entity_count": 0,
        "lore_fact_count": 0,
        "created_at": now,
        "updated_at": None,
    }
    defaults.update(overrides)
    return KnowledgePackResponse(**defaults)


class TestComputeIngestionDeltaEmpty:
    def test_identical_empty_packs(self):
        current = _make_pack(axioms=[], entity_archetypes=[])
        new = _make_pack(axioms=[], entity_archetypes=[])
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.net_new_items == 0
        assert delta.modified_items == 0
        assert delta.removed_items == 0
        assert delta.unchanged_items == 0
        assert delta.change_significance == "minimal"
        assert delta.apply_decision == "skip"
        assert not delta.has_changes


class TestComputeIngestionDeltaAxioms:
    def test_new_axiom_added(self):
        current = _make_pack(axioms=[])
        new = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="Magic exists in this world.",
                    domain="magic",
                    confidence=0.9,
                )
            ]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.net_new_items == 1
        assert delta.removed_items == 0
        assert delta.axioms_delta[0].delta_category == DeltaCategory.ADDED
        assert delta.axioms_delta[0].summary == "Added: magic exists in this world."

    def test_new_entity_added(self):
        current = _make_pack(entity_archetypes=[])
        new = _make_pack(
            entity_archetypes=[
                ExtractedEntityArchetype(
                    name="Goblin",
                    entity_type="character",
                    entity_roles=["enemy"],
                    confidence=0.8,
                )
            ]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.net_new_items == 1
        assert delta.entities_delta[0].delta_category == DeltaCategory.ADDED

    def test_item_removed(self):
        current = _make_pack(
            entity_archetypes=[
                ExtractedEntityArchetype(
                    name="Orc",
                    entity_type="character",
                    confidence=0.85,
                )
            ]
        )
        new = _make_pack(entity_archetypes=[])
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.removed_items == 1
        assert delta.entities_delta[0].delta_category == DeltaCategory.REMOVED
        assert "orc" in delta.entities_delta[0].summary.lower()

    def test_item_modified(self):
        current = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="The world is round.",
                    domain="cosmology",
                    confidence=0.9,
                )
            ]
        )
        new = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="The world is round.",
                    domain="cosmology",
                    confidence=0.95,  # Changed
                )
            ]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        # confidence change alone should NOT be flagged as modified
        assert delta.modified_items == 0
        assert delta.unchanged_items == 1

    def test_item_modified_substantive(self):
        current = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="The world is round.",
                    domain="cosmology",
                    confidence=0.9,
                )
            ]
        )
        new = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="The world is flat.",  # Changed!
                    domain="cosmology",
                    confidence=0.9,
                )
            ]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.modified_items == 1
        assert delta.axioms_delta[0].delta_category == DeltaCategory.MODIFIED
        assert "statement" in delta.axioms_delta[0].changed_fields


class TestComputeIngestionDeltaRelationships:
    def test_relationship_added(self):
        current = _make_pack(entity_relationships=[])
        new = _make_pack(
            entity_relationships=[
                ExtractedRelationship(
                    from_entity="Gandalf",
                    rel_type="ally_of",
                    to_entity="Frodo",
                    confidence=0.9,
                )
            ]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.relationships_delta[0].delta_category == DeltaCategory.ADDED

    def test_relationship_removed(self):
        current = _make_pack(
            entity_relationships=[
                ExtractedRelationship(
                    from_entity="Gandalf",
                    rel_type="enemy_of",
                    to_entity="Sauron",
                    confidence=0.9,
                )
            ]
        )
        new = _make_pack(entity_relationships=[])
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.removed_items == 1
        assert delta.relationships_delta[0].delta_category == DeltaCategory.REMOVED


class TestComputeIngestionDeltaRandomTables:
    def test_table_unchanged(self):
        current = _make_pack(
            random_tables=[
                ExtractedRandomTable(
                    name="Encounter Table",
                    dice_formula="1d20",
                    confidence=0.8,
                    entries=[],
                )
            ]
        )
        new = _make_pack(
            random_tables=[
                ExtractedRandomTable(
                    name="Encounter Table",
                    dice_formula="1d20",
                    confidence=0.8,
                    entries=[],
                )
            ]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.unchanged_items == 1
        assert delta.random_tables_delta[0].delta_category == DeltaCategory.UNCHANGED


class TestComputeIngestionDeltaSignificance:
    def test_minimal_when_no_changes(self):
        current = _make_pack(axioms=[], entity_archetypes=[])
        new = _make_pack(axioms=[], entity_archetypes=[])
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.change_significance == "minimal"
        assert delta.apply_decision == "skip"

    def test_minor_single_addition(self):
        current = _make_pack(axioms=[])
        new = _make_pack(axioms=[ExtractedAxiom(statement="One axiom.", domain="test", confidence=0.9)])
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.change_significance in ("minor", "moderate")

    def test_recommendations_include_review(self):
        current = _make_pack(axioms=[])
        new = _make_pack(
            axioms=[ExtractedAxiom(statement=f"Axiom {i}", domain="test", confidence=0.9) for i in range(10)]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.apply_decision == "approve_review"
        assert any("review" in r.lower() for r in delta.recommendations)


class TestFilterDeltaForApply:
    def test_removes_unchanged_items(self):
        current = _make_pack(
            entity_archetypes=[ExtractedEntityArchetype(name="Goblin", entity_type="character", confidence=0.8)]
        )
        new = _make_pack(
            entity_archetypes=[ExtractedEntityArchetype(name="Goblin", entity_type="character", confidence=0.8)]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        request = IngestionDeltaApplyRequest(
            source_id=uuid4(),
            delta=delta,
            multiverse_id=uuid4(),
        )
        filtered = filter_delta_for_apply(delta, request)
        assert filtered.unchanged_items == 0
        assert all(
            d.delta_category not in (DeltaCategory.UNCHANGED, DeltaCategory.REMOVED)
            for d in [
                *filtered.entities_delta,
                *filtered.axioms_delta,
            ]
        )

    def test_keeps_added_items(self):
        current = _make_pack(entity_archetypes=[])
        new = _make_pack(
            entity_archetypes=[ExtractedEntityArchetype(name="Orc", entity_type="character", confidence=0.8)]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        request = IngestionDeltaApplyRequest(
            source_id=uuid4(),
            delta=delta,
            multiverse_id=uuid4(),
        )
        filtered = filter_delta_for_apply(delta, request)
        assert len(filtered.entities_delta) == 1
        assert filtered.entities_delta[0].delta_category == DeltaCategory.ADDED

    def test_include_modified_false_removes_modified(self):
        current = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="The world is round.",
                    domain="cosmology",
                    confidence=0.9,
                )
            ]
        )
        new = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="The world is flat.",
                    domain="cosmology",
                    confidence=0.9,
                )
            ]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.modified_items == 1

        request = IngestionDeltaApplyRequest(
            source_id=uuid4(),
            delta=delta,
            multiverse_id=uuid4(),
            include_modified=False,
        )
        filtered = filter_delta_for_apply(delta, request)
        assert all(d.delta_category != DeltaCategory.MODIFIED for d in filtered.axioms_delta)


class TestIngestionDeltaProperties:
    def test_has_changes_true_when_added(self):
        current = _make_pack(axioms=[])
        new = _make_pack(axioms=[ExtractedAxiom(statement="New fact.", domain="test", confidence=0.9)])
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.has_changes is True

    def test_has_changes_false_when_identical(self):
        current = _make_pack(axioms=[ExtractedAxiom(statement="Fact.", domain="test", confidence=0.9)])
        new = _make_pack(axioms=[ExtractedAxiom(statement="Fact.", domain="test", confidence=0.9)])
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.has_changes is False

    def test_apply_decision_skip(self):
        current = _make_pack(axioms=[])
        new = _make_pack(axioms=[])
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.apply_decision == "skip"

    def test_apply_decision_auto_apply(self):
        current = _make_pack(axioms=[])
        new = _make_pack(axioms=[ExtractedAxiom(statement="New.", domain="test", confidence=0.9)])
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.apply_decision == "auto_apply"


class TestDeltaItem:
    def test_delta_item_all_fields(self):
        item = DeltaItem(
            item_index=0,
            delta_category=DeltaCategory.MODIFIED,
            field_name="axioms",
            summary="Statement changed",
            changed_fields=["statement"],
            item_snapshot={"statement": "New."},
            confidence_delta=0.05,
            source_ref="p.42",
        )
        assert item.delta_category == DeltaCategory.MODIFIED
        assert item.confidence_delta == 0.05
        assert "statement" in item.changed_fields
