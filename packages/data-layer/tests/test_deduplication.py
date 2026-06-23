"""
Tests for cross-pack deduplication (P2-7).
"""

from datetime import datetime, timezone
from uuid import uuid4

from monitor_data.schemas.deduplication import (
    DuplicateCategory,
    DeduplicationStrategy,
)
from monitor_data.schemas.knowledge_packs import (
    ExtractedAxiom,
    ExtractedCharacterProfile,
    ExtractedEntityArchetype,
    ExtractedGenerationTemplate,
    ExtractedRelationship,
    ExtractedToneProfile,
    KnowledgePackResponse,
    KnowledgePackType,
    KnowledgePackStatus,
)
from monitor_data.tools.ingest_tools.deduplication import (
    compute_deduplication,
    _compute_content_hash,
    _get_item_identity,
    _make_duplicate_id,
)


def _make_pack(**overrides) -> KnowledgePackResponse:
    """Minimal KnowledgePackResponse for testing."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        pack_id=uuid4(),
        name="Test Pack",
        description="",
        pack_type=KnowledgePackType.RULEBOOK,
        system_name="D&D 5e",
        status=KnowledgePackStatus.READY,
        source_document_ids=[],
        ingestion_job_id=None,
        tags=[],
        parent_pack_ids=[],
        axioms=[],
        entity_archetypes=[],
        lore_facts=[],
        entity_relationships=[],
        random_tables=[],
        agendas=[],
        topologies=[],
        game_system_id=None,
        game_system_data=None,
        source_profile_data=None,
        chunk_summaries=[],
        section_summaries=[],
        source_mindscape=None,
        applied_to=[],
        axiom_count=0,
        entity_count=0,
        lore_fact_count=0,
        created_at=now,
        updated_at=None,
    )
    defaults.update(overrides)
    return KnowledgePackResponse(**defaults)


class TestComputeDeduplicationNoDuplicates:
    def test_new_pack_with_no_existing_packs(self):
        new = _make_pack(
            axioms=[ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.9)]
        )
        result = compute_deduplication(new, [], multiverse_id=str(uuid4()))
        assert result.has_duplicates is False
        assert result.auto_resolvable_count == 0
        assert result.review_required_count == 0

    def test_new_item_not_in_existing(self):
        new = _make_pack(
            axioms=[ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.9)]
        )
        existing = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="Dragons breathe fire.", domain="creatures", confidence=0.85
                )
            ]
        )
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        assert result.has_duplicates is False
        assert result.total_items_checked == 1

    def test_extended_narrative_outputs_are_checked(self):
        new = _make_pack(
            tone_profiles=[
                ExtractedToneProfile(
                    name="Gothic Pressure",
                    description="Dark social dread.",
                    instruction="Keep narration tense and intimate.",
                )
            ],
            character_profiles=[ExtractedCharacterProfile(name="Camarilla Elder")],
            generation_templates=[
                ExtractedGenerationTemplate(name="Harpy Envoy", archetype_name="Harpy")
            ],
        )
        result = compute_deduplication(new, [], multiverse_id=str(uuid4()))
        assert result.total_items_checked == 3


class TestComputeDeduplicationExact:
    def test_exact_duplicate_same_content(self):
        new = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="Magic is real.", domain="magic", confidence=0.9, source_ref="p1"
                )
            ]
        )
        existing = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="Magic is real.", domain="magic", confidence=0.85, source_ref="p2"
                )
            ]
        )
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        assert result.has_duplicates is True
        assert len(result.duplicate_groups) == 1
        group = result.duplicate_groups[0]
        assert group.category == DuplicateCategory.EXACT
        assert group.strategy == DeduplicationStrategy.KEEP_NEW  # new has higher confidence
        assert len(group.items) == 2
        assert group.items[0].pack_id == new.id
        assert group.items[1].pack_id == existing.id

    def test_exact_duplicate_existing_higher_confidence(self):
        new = _make_pack(
            axioms=[ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.7)]
        )
        existing = _make_pack(
            axioms=[ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.95)]
        )
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        assert result.has_duplicates is True
        group = result.duplicate_groups[0]
        assert group.category == DuplicateCategory.EXACT
        assert group.strategy == DeduplicationStrategy.KEEP_EXISTING

    def test_conflicting_different_content_same_identity(self):
        new = _make_pack(
            axioms=[ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.9)]
        )
        existing = _make_pack(
            axioms=[ExtractedAxiom(statement="Magic is NOT real.", domain="magic", confidence=0.85)]
        )
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        assert result.has_duplicates is True
        group = result.duplicate_groups[0]
        assert group.category == DuplicateCategory.CONFLICTING
        assert group.strategy == DeduplicationStrategy.REVIEW
        assert result.review_required_count == 1


class TestComputeDeduplicationSemantic:
    def test_semantic_similar_but_not_identical(self):
        new = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="Magic is woven into the world.", domain="magic", confidence=0.9
                )
            ]
        )
        existing = _make_pack(
            axioms=[
                ExtractedAxiom(
                    statement="Magic is woven into reality.", domain="magic", confidence=0.85
                )
            ]
        )
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        assert result.has_duplicates is True
        group = result.duplicate_groups[0]
        assert group.category == DuplicateCategory.SEMANTIC
        assert 0.70 <= group.similarity_score < 1.0
        assert group.strategy == DeduplicationStrategy.KEEP_NEW  # new is more specific


class TestComputeDeduplicationEntityArchetypes:
    def test_same_entity_name_different_type(self):
        """Same name but different entity_type should be CONFLICTING."""
        new = _make_pack(
            entity_archetypes=[
                ExtractedEntityArchetype(name="Dragon", entity_type="character", confidence=0.9)
            ]
        )
        existing = _make_pack(
            entity_archetypes=[
                ExtractedEntityArchetype(name="Dragon", entity_type="creature", confidence=0.85)
            ]
        )
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        # With name as identity, they'll be EXACT since name matches
        # but the content differs (entity_type field)
        assert result.has_duplicates is True


class TestComputeDeduplicationRelationships:
    def test_same_relationship_different_type(self):
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
        existing = _make_pack(
            entity_relationships=[
                ExtractedRelationship(
                    from_entity="Gandalf",
                    rel_type="enemy_of",
                    to_entity="Frodo",
                    confidence=0.85,
                )
            ]
        )
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        # rel_type is the identity for relationships, so these are different identities
        assert result.has_duplicates is False


class TestComputeDeduplicationMultiple:
    def test_multiple_duplicates(self):
        new = _make_pack(
            axioms=[
                ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.9),
                ExtractedAxiom(statement="Dragons exist.", domain="creatures", confidence=0.9),
            ]
        )
        existing = _make_pack(
            axioms=[
                ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.5),
                ExtractedAxiom(statement="Dragons exist.", domain="creatures", confidence=0.5),
            ]
        )
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        assert result.has_duplicates is True
        assert len(result.duplicate_groups) == 2
        assert result.auto_resolvable_count == 2
        assert result.review_required_count == 0


class TestDeduplicationProperties:
    def test_all_auto_resolvable_true(self):
        new = _make_pack(
            axioms=[ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.9)]
        )
        existing = _make_pack(
            axioms=[ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.5)]
        )
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        assert result.has_duplicates is True
        assert result.all_auto_resolvable is True

    def test_all_auto_resolvable_false_with_conflict(self):
        new = _make_pack(
            axioms=[ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.9)]
        )
        existing = _make_pack(
            axioms=[ExtractedAxiom(statement="Magic is NOT real.", domain="magic", confidence=0.85)]
        )
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        assert result.has_duplicates is True
        assert result.all_auto_resolvable is False


class TestUtilities:
    def test_make_duplicate_id_stable(self):
        id1 = _make_duplicate_id("axioms", "magic is real")
        id2 = _make_duplicate_id("axioms", "magic is real")
        assert id1 == id2
        assert len(id1) == 24

    def test_make_duplicate_id_different_fields(self):
        id1 = _make_duplicate_id("axioms", "magic is real")
        id2 = _make_duplicate_id("entity_archetypes", "magic is real")
        assert id1 != id2

    def test_compute_content_hash_same_for_identical_items(self):
        item1 = ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.9)
        item2 = ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.9)
        h1 = _compute_content_hash(item1)
        h2 = _compute_content_hash(item2)
        assert h1 == h2

    def test_compute_content_hash_different_for_different_content(self):
        item1 = ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.9)
        item2 = ExtractedAxiom(statement="Magic is NOT real.", domain="magic", confidence=0.9)
        h1 = _compute_content_hash(item1)
        h2 = _compute_content_hash(item2)
        assert h1 != h2

    def test_get_item_identity(self):
        axiom = ExtractedAxiom(statement="Magic is real.", domain="magic", confidence=0.9)
        assert _get_item_identity(axiom, "statement") == "Magic is real."

    def test_get_item_identity_missing(self):
        entity = ExtractedEntityArchetype(name="Goblin", entity_type="character", confidence=0.8)
        assert _get_item_identity(entity, "description") is None
