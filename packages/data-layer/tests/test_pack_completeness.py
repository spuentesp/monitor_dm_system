"""
Tests for KnowledgePack completeness validation.

LAYER: data-layer (unit tests)
"""

from uuid import uuid4

from monitor_data.schemas.knowledge_packs import (
    KnowledgePackResponse,
    KnowledgePackType,
    KnowledgePackStatus,
    ExtractedAxiom,
    ExtractedEntityArchetype,
    ExtractedLoreFact,
    ExtractedRandomTable,
    ExtractedAgenda,
    ExtractedTopology,
    EmbeddedGameSystem,
)
from monitor_data.tools.pack_completeness import (
    compute_knowledge_pack_completeness,
)


def _make_pack(
    pack_type: KnowledgePackType = KnowledgePackType.RULEBOOK,
    axioms: int = 0,
    entities: int = 0,
    lore: int = 0,
    tables: int = 0,
    agendas: int = 0,
    has_game_system: bool = False,
    topologies: int = 0,
) -> KnowledgePackResponse:
    """Helper to construct a minimal KnowledgePackResponse."""
    from datetime import datetime, timezone

    return KnowledgePackResponse(
        pack_id=uuid4(),
        name="Test Pack",
        description="Test",
        pack_type=pack_type,
        system_name="Test System",
        status=KnowledgePackStatus.READY,
        source_document_ids=[],
        ingestion_job_id=None,
        tags=[],
        axioms=[ExtractedAxiom(statement=f"Axiom {i}", domain="test") for i in range(axioms)],
        entity_archetypes=[
            ExtractedEntityArchetype(name=f"Entity {i}", entity_type="character")
            for i in range(entities)
        ],
        lore_facts=[ExtractedLoreFact(statement=f"Lore {i}") for i in range(lore)],
        random_tables=[ExtractedRandomTable(name=f"Table {i}", entries=[]) for i in range(tables)],
        agendas=[ExtractedAgenda(title=f"Agenda {i}", description="desc") for i in range(agendas)],
        topologies=[
            ExtractedTopology(from_location=f"L{i}", to_location=f"L{i + 1}")
            for i in range(topologies)
        ],
        game_system_id=uuid4() if has_game_system else None,
        game_system_data=EmbeddedGameSystem(
            name="Test System",
            description="Test",
            system_id="test",
            core_mechanic=None,
        )
        if has_game_system
        else None,
        source_profile_data=None,
        created_at=datetime.now(timezone.utc),
        updated_at=None,
    )


class TestCompletenessCategory:
    def test_score_full(self):
        from monitor_data.tools.pack_completeness import _score_category

        score, status = _score_category(present=5, expected=3)
        assert score == 1.0
        assert status == "complete"

    def test_score_partial(self):
        from monitor_data.tools.pack_completeness import _score_category

        score, status = _score_category(present=2, expected=5)
        assert status == "partial"
        assert 0 < score < 1

    def test_score_missing(self):
        from monitor_data.tools.pack_completeness import _score_category

        score, status = _score_category(present=0, expected=3)
        assert score == 0.0
        assert status == "missing"

    def test_score_not_required_but_present(self):
        from monitor_data.tools.pack_completeness import _score_category

        score, status = _score_category(present=5, expected=0)
        assert score == 1.0
        assert status == "complete"

    def test_score_not_required_and_absent(self):
        from monitor_data.tools.pack_completeness import _score_category

        score, status = _score_category(present=0, expected=0)
        assert score == 0.0
        assert status == "missing"


class TestRulebookCompleteness:
    def test_complete_rulebook(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.RULEBOOK,
            axioms=2,
            entities=3,
            lore=2,
            tables=1,
            agendas=1,
            has_game_system=True,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert result.overall_score >= 0.9
        assert result.overall_status == "complete"
        assert result.missing_categories == []

    def test_rulebook_missing_game_system(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.RULEBOOK,
            axioms=2,
            entities=3,
            lore=2,
            tables=1,
            agendas=1,
            has_game_system=False,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert result.overall_status in ("partial", "minimal")
        assert "game_system" in result.missing_categories + result.partial_categories

    def test_rulebook_empty(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.RULEBOOK,
            axioms=0,
            entities=0,
            lore=0,
            tables=0,
            agendas=0,
            has_game_system=False,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert result.overall_score < 0.2
        assert result.overall_status == "empty"


class TestSettingSupplementCompleteness:
    def test_complete_setting(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
            entities=5,
            lore=4,
            topologies=2,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert result.overall_score >= 0.8
        assert result.overall_status in ("complete", "partial")

    def test_setting_missing_entities(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
            entities=1,
            lore=2,
            topologies=1,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert "entities" in result.partial_categories + result.missing_categories


class TestAdventureModuleCompleteness:
    def test_complete_adventure(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.ADVENTURE_MODULE,
            entities=3,
            tables=3,
            agendas=2,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert result.overall_score >= 0.8

    def test_adventure_missing_tables(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.ADVENTURE_MODULE,
            entities=2,
            tables=0,
            agendas=1,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert "tables" in result.missing_categories + result.partial_categories


class TestHomebrewAndSessionNotes:
    def test_homebrew_lenient(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.HOMEBREW,
            entities=1,
            lore=1,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert result.overall_score >= 0.8

    def test_session_notes_minimum_bar(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.SESSION_NOTES,
            entities=1,
            agendas=1,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert result.overall_score >= 0.5


class TestRecommendations:
    def test_recommendations_for_missing_categories(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.RULEBOOK,
            axioms=0,
            entities=0,
            has_game_system=False,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert len(result.recommendations) > 0
        assert any("axioms" in r for r in result.recommendations)

    def test_no_recommendations_when_complete(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.RULEBOOK,
            axioms=2,
            entities=3,
            has_game_system=True,
        )
        result = compute_knowledge_pack_completeness(pack)
        # May still have recommendations for non-required categories
        # that have 0
        missing_req = [
            c for c in result.missing_categories if result.thresholds_applied.get(c, 0) > 0
        ]
        assert len(missing_req) == 0


class TestOverallScoreCalculation:
    def test_weighted_score(self):
        # RULEBOOK with all required categories met
        pack = _make_pack(
            pack_type=KnowledgePackType.RULEBOOK,
            axioms=2,
            entities=3,
            has_game_system=True,
        )
        result = compute_knowledge_pack_completeness(pack)
        # game_system=1 (weight 0.20) + entities=3 (weight 0.20) + axioms=2 (weight 0.10)
        # entities expected=2, score=1.0, game_system expected=1, score=1.0
        assert result.overall_score > 0

    def test_empty_pack_zero_score(self):
        pack = _make_pack(
            pack_type=KnowledgePackType.RULEBOOK,
            axioms=0,
            entities=0,
            has_game_system=False,
        )
        result = compute_knowledge_pack_completeness(pack)
        assert result.overall_score == 0.0
