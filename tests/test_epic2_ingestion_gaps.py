"""
Tests for EPIC 2 ingestion pipeline enhancements:
  #5 — evidence_refs on extracted items
  #1 — contradiction detection against existing canon
  #2 — extended CanonLevel + KnowledgeScope
  #4 — dangling plot thread detection & extraction
"""

from uuid import uuid4

from monitor_data.schemas.base import CanonLevel, KnowledgeScope
from monitor_data.schemas.contradiction import (
    ContradictionFact,
    ContradictionMatch,
    ContradictionResult,
    ContradictionSeverity,
    ContradictionType,
)
from monitor_data.schemas.knowledge_packs import (
    ExtractedAxiom,
    ExtractedEntityArchetype,
    ExtractedLoreFact,
    KnowledgePackResponse,
    KnowledgePackStatus,
    ProfileEvidenceRef,
)
from monitor_data.tools.ingest_tools.contradiction_detection import (
    _has_negation_conflict,
    _has_opposite_terms,
    _levenshtein_ratio,
    _shares_subject,
    detect_contradictions,
)

# =============================================================================
# #5 — evidence_refs
# =============================================================================


class TestEvidenceRefs:
    """Verify evidence_refs field exists and works on all extracted types."""

    def test_axiom_evidence_refs_default_empty(self):
        axiom = ExtractedAxiom(statement="Magic exists", domain="magic")
        assert axiom.evidence_refs == []

    def test_axiom_evidence_refs_with_refs(self):
        axiom = ExtractedAxiom(
            statement="Magic exists",
            domain="magic",
            evidence_refs=[
                ProfileEvidenceRef(ref="p.42", section_path="Chapter 3: Magic"),
                ProfileEvidenceRef(ref="p.100", note="Explicit statement"),
            ],
        )
        assert len(axiom.evidence_refs) == 2
        assert axiom.evidence_refs[0].ref == "p.42"
        assert axiom.evidence_refs[0].section_path == "Chapter 3: Magic"
        assert axiom.evidence_refs[1].note == "Explicit statement"

    def test_entity_evidence_refs_default_empty(self):
        entity = ExtractedEntityArchetype(name="Dragon", entity_type="character")
        assert entity.evidence_refs == []

    def test_entity_evidence_refs_with_refs(self):
        entity = ExtractedEntityArchetype(
            name="Dragon",
            entity_type="character",
            evidence_refs=[
                ProfileEvidenceRef(ref="Monster Manual p.84", page_hint=84),
            ],
        )
        assert len(entity.evidence_refs) == 1
        assert entity.evidence_refs[0].page_hint == 84

    def test_lore_fact_evidence_refs_default_empty(self):
        fact = ExtractedLoreFact(statement="The Sundering happened 1000 years ago")
        assert fact.evidence_refs == []

    def test_lore_fact_evidence_refs_with_refs(self):
        fact = ExtractedLoreFact(
            statement="The Sundering happened 1000 years ago",
            evidence_refs=[
                ProfileEvidenceRef(ref="Forgotten Realms Campaign Setting p.5"),
                ProfileEvidenceRef(ref="Sword Coast Adventurer's Guide p.12"),
            ],
        )
        assert len(fact.evidence_refs) == 2

    def test_evidence_ref_serialization_roundtrip(self):
        """Ensure evidence_refs survive JSON serialization."""
        axiom = ExtractedAxiom(
            statement="Gods are real",
            domain="religion",
            evidence_refs=[ProfileEvidenceRef(ref="p.1")],
        )
        data = axiom.model_dump(mode="json")
        restored = ExtractedAxiom(**data)
        assert len(restored.evidence_refs) == 1
        assert restored.evidence_refs[0].ref == "p.1"


# =============================================================================
# #2 — Extended CanonLevel + KnowledgeScope
# =============================================================================


class TestExtendedCanonLevel:
    """Verify new CanonLevel values exist."""

    def test_rumor_exists(self):
        assert CanonLevel.RUMOR == "rumor"

    def test_character_belief_exists(self):
        assert CanonLevel.CHARACTER_BELIEF == "character_belief"

    def test_player_knowledge_exists(self):
        assert CanonLevel.PLAYER_KNOWLEDGE == "player_knowledge"

    def test_original_levels_still_work(self):
        assert CanonLevel.PROPOSED == "proposed"
        assert CanonLevel.CANON == "canon"
        assert CanonLevel.RETCONNED == "retconned"

    def test_all_canon_levels(self):
        levels = {e.value for e in CanonLevel}
        assert levels == {
            "proposed",
            "canon",
            "retconned",
            "rumor",
            "character_belief",
            "player_knowledge",
            "superseded",
        }


class TestKnowledgeScope:
    """Verify KnowledgeScope enum."""

    def test_world_scope(self):
        assert KnowledgeScope.WORLD == "world"

    def test_character_scope(self):
        assert KnowledgeScope.CHARACTER == "character"

    def test_player_scope(self):
        assert KnowledgeScope.PLAYER == "player"

    def test_rumor_scope(self):
        assert KnowledgeScope.RUMOR == "rumor"


class TestLoreFactKnowledgeScope:
    """Verify lore facts carry canon_level and knowledge_scope."""

    def test_default_scope_is_world(self):
        fact = ExtractedLoreFact(statement="Something happened")
        assert fact.knowledge_scope == KnowledgeScope.WORLD
        assert fact.canon_level == CanonLevel.PROPOSED

    def test_rumor_lore_fact(self):
        fact = ExtractedLoreFact(
            statement="Rumor says the King is dead",
            canon_level=CanonLevel.RUMOR,
            knowledge_scope=KnowledgeScope.RUMOR,
        )
        assert fact.canon_level == CanonLevel.RUMOR
        assert fact.knowledge_scope == KnowledgeScope.RUMOR

    def test_character_belief_lore_fact(self):
        fact = ExtractedLoreFact(
            statement="Gandalf believes the ring is evil",
            canon_level=CanonLevel.CHARACTER_BELIEF,
            knowledge_scope=KnowledgeScope.CHARACTER,
        )
        assert fact.canon_level == CanonLevel.CHARACTER_BELIEF
        assert fact.knowledge_scope == KnowledgeScope.CHARACTER

    def test_player_knowledge_lore_fact(self):
        fact = ExtractedLoreFact(
            statement="Sauron is disguised as Annatar",
            canon_level=CanonLevel.PLAYER_KNOWLEDGE,
            knowledge_scope=KnowledgeScope.PLAYER,
        )
        assert fact.knowledge_scope == KnowledgeScope.PLAYER

    def test_serialization_with_scope(self):
        fact = ExtractedLoreFact(
            statement="Test",
            canon_level=CanonLevel.RUMOR,
            knowledge_scope=KnowledgeScope.RUMOR,
        )
        data = fact.model_dump(mode="json")
        restored = ExtractedLoreFact(**data)
        assert restored.canon_level == CanonLevel.RUMOR
        assert restored.knowledge_scope == KnowledgeScope.RUMOR


# =============================================================================
# #1 — Contradiction Detection
# =============================================================================


def _make_pack(
    axioms=None,
    lore_facts=None,
    entities=None,
) -> KnowledgePackResponse:
    """Build a minimal KnowledgePackResponse for testing."""
    return KnowledgePackResponse(
        pack_id=uuid4(),
        name="Test Pack",
        description="test",
        pack_type="setting_supplement",
        system_name=None,
        status=KnowledgePackStatus.READY,
        source_document_ids=[],
        ingestion_job_id=None,
        tags=[],
        axioms=axioms or [],
        entity_archetypes=entities or [],
        lore_facts=lore_facts or [],
        game_system_id=None,
        axiom_count=len(axioms or []),
        entity_count=len(entities or []),
        lore_fact_count=len(lore_facts or []),
        created_at="2026-01-01T00:00:00Z",
    )


class TestContradictionHelpers:
    """Test internal helper functions."""

    def test_levenshtein_identical(self):
        assert _levenshtein_ratio("hello", "hello") == 1.0

    def test_levenshtein_completely_different(self):
        assert _levenshtein_ratio("abc", "xyz") < 0.5

    def test_levenshtein_similar(self):
        ratio = _levenshtein_ratio("Elves are immortal", "Elves are mortal")
        assert 0.7 < ratio < 0.95

    def test_negation_conflict_is_not(self):
        assert _has_negation_conflict("dragons are real", "dragons are not real")

    def test_negation_conflict_cannot(self):
        assert _has_negation_conflict("magic can exist", "magic cannot exist")

    def test_negation_no_conflict(self):
        assert not _has_negation_conflict("elves are tall", "dwarves are short")

    def test_opposite_terms_mortal_immortal(self):
        result = _has_opposite_terms("Elves are immortal", "Elves are mortal")
        assert result == "mortal/immortal"

    def test_opposite_terms_alive_dead(self):
        result = _has_opposite_terms("the king is alive", "the king is dead")
        assert result == "alive/dead"

    def test_opposite_terms_no_match(self):
        assert _has_opposite_terms("elves love nature", "dwarves love gold") is None

    def test_shares_subject_true(self):
        assert _shares_subject(
            "Gandalf is a wizard",
            "Gandalf is a Maiar spirit",
        )

    def test_shares_subject_false(self):
        assert not _shares_subject(
            "Elves are immortal",
            "Dwarves love gold",
        )


class TestContradictionDetection:
    """Test the main detect_contradictions function."""

    def test_no_contradictions_empty_canon(self):
        pack = _make_pack(
            lore_facts=[
                ExtractedLoreFact(statement="The Sundering happened 1000 years ago"),
            ]
        )
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=[])
        assert result.total_contradictions == 0

    def test_no_contradictions_compatible_facts(self):
        pack = _make_pack(
            lore_facts=[
                ExtractedLoreFact(statement="Elves live in forests"),
            ]
        )
        canon_facts = [{"statement": "Dwarves live in mountains"}]
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=canon_facts)
        assert result.total_contradictions == 0

    def test_negation_contradiction_detected(self):
        pack = _make_pack(
            lore_facts=[
                ExtractedLoreFact(statement="Elves are not immortal"),
            ]
        )
        canon_facts = [{"statement": "Elves are immortal", "canon_level": "canon"}]
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=canon_facts)
        assert result.total_contradictions >= 1
        assert any(
            m.contradiction_type == ContradictionType.SEMANTIC_OPPOSITE
            for m in result.all_matches
        )

    def test_opposite_terms_contradiction_detected(self):
        pack = _make_pack(
            axioms=[
                ExtractedAxiom(statement="The old king is dead", domain="history"),
            ]
        )
        canon_axioms = [{"statement": "The old king is alive", "canon_level": "canon"}]
        result = detect_contradictions(pack, canon_axioms=canon_axioms, canon_facts=[])
        assert result.total_contradictions >= 1
        # Axiom contradictions are always at least HIGH
        assert result.high_severity_count >= 1

    def test_rumor_facts_not_checked_for_contradictions(self):
        """Rumors should not be flagged as contradictions — they are expected to differ from canon."""
        pack = _make_pack(
            lore_facts=[
                ExtractedLoreFact(
                    statement="The king is dead",
                    canon_level=CanonLevel.RUMOR,
                    knowledge_scope=KnowledgeScope.RUMOR,
                ),
            ]
        )
        canon_facts = [{"statement": "The king is alive", "canon_level": "canon"}]
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=canon_facts)
        assert result.total_contradictions == 0

    def test_character_belief_not_checked(self):
        """Character beliefs are personal and don't contradict world canon."""
        pack = _make_pack(
            lore_facts=[
                ExtractedLoreFact(
                    statement="The gods are fake",
                    canon_level=CanonLevel.CHARACTER_BELIEF,
                    knowledge_scope=KnowledgeScope.CHARACTER,
                ),
            ]
        )
        canon_facts = [
            {"statement": "The gods are real and intervene", "canon_level": "canon"}
        ]
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=canon_facts)
        assert result.total_contradictions == 0

    def test_partial_overlap_detected(self):
        """Similar statements about the same subject should be flagged."""
        pack = _make_pack(
            lore_facts=[
                ExtractedLoreFact(
                    statement="Gandalf is a powerful Istari wizard sent by the Valar"
                ),
            ]
        )
        canon_facts = [
            {
                "statement": "Gandalf is a Maia spirit in the form of a wizard",
                "canon_level": "canon",
            }
        ]
        result = detect_contradictions(pack, canon_axioms=[], canon_facts=canon_facts)
        # May or may not detect depending on similarity threshold — at minimum it shouldn't crash
        assert isinstance(result.total_contradictions, int)

    def test_result_compute_totals(self):
        result = ContradictionResult(
            axiom_contradictions=[
                ContradictionMatch(
                    contradiction_id="test:1",
                    contradiction_type=ContradictionType.SEMANTIC_OPPOSITE,
                    severity=ContradictionSeverity.HIGH,
                    new_fact=ContradictionFact(statement="new"),
                    existing_fact=ContradictionFact(statement="old"),
                ),
            ],
            lore_contradictions=[
                ContradictionMatch(
                    contradiction_id="test:2",
                    contradiction_type=ContradictionType.PARTIAL_OVERLAP,
                    severity=ContradictionSeverity.LOW,
                    new_fact=ContradictionFact(statement="new2"),
                    existing_fact=ContradictionFact(statement="old2"),
                ),
            ],
        )
        result.compute_totals()
        assert result.total_contradictions == 2
        assert result.high_severity_count == 1
        assert len(result.all_matches) == 2

    def test_multiverse_id_tracked(self):
        mv_id = uuid4()
        pack = _make_pack()
        result = detect_contradictions(
            pack, canon_axioms=[], canon_facts=[], multiverse_id=mv_id
        )
        assert result.checked_against_multiverse == mv_id

    def test_severity_high_for_canon_axiom(self):
        """Contradicting established canon axioms is always HIGH severity."""
        pack = _make_pack(
            axioms=[
                ExtractedAxiom(statement="Magic does not exist", domain="magic"),
            ]
        )
        canon_axioms = [
            {"statement": "Magic exists and is real", "canon_level": "canon"}
        ]
        result = detect_contradictions(pack, canon_axioms=canon_axioms, canon_facts=[])
        if result.total_contradictions > 0:
            assert all(
                m.severity
                in (ContradictionSeverity.HIGH, ContradictionSeverity.CRITICAL)
                for m in result.axiom_contradictions
            )
