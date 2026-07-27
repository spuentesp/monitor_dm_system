from datetime import datetime
from uuid import uuid4

import pytest

from monitor_data.schemas.contradiction import (
    ContradictionResult,
    ContradictionSeverity,
    ContradictionType,
)
from monitor_data.schemas.knowledge_packs import (
    ExtractedAxiom,
    ExtractedLoreFact,
    KnowledgePackResponse,
    KnowledgePackStatus,
    KnowledgePackType,
)
from monitor_data.tools.ingest_tools.contradiction_detection import (
    _check_axioms,
    _check_lore_facts,
    _classify_severity,
    _compare_statements,
    _has_negation_conflict,
    _has_opposite_terms,
    _levenshtein_ratio,
    _safe_uuid,
    _shares_subject,
    detect_contradictions,
)

# =============================================================================
# FIXTURES
# =============================================================================


def _pack(
    axioms: list[ExtractedAxiom] | None = None,
    lore_facts: list[ExtractedLoreFact] | None = None,
) -> KnowledgePackResponse:
    """Build a valid KnowledgePackResponse with required fields."""
    return KnowledgePackResponse(
        id=uuid4(),
        name="test-pack",
        description="Test pack for contradiction detection",
        pack_type=KnowledgePackType.LORE,
        system_name=None,
        status=KnowledgePackStatus.PENDING,
        source_document_ids=[],
        ingestion_job_id=None,
        tags=[],
        axioms=axioms or [],
        lore_facts=lore_facts or [],
        entity_archetypes=[],
        created_at=datetime.now(),
        game_system_id=None,
        game_system_data=None,
    )


@pytest.fixture
def sample_axiom():
    return ExtractedAxiom(
        statement="Elves are immortal",
        source_ref="lore-book-1",
        confidence=0.95,
    )


@pytest.fixture
def sample_lore_fact():
    return ExtractedLoreFact(
        statement="The Sundering happened 1000 years ago",
        source_ref="lore-book-1",
        confidence=0.9,
    )


@pytest.fixture
def canon_axioms():
    return [
        {
            "id": "a1",
            "statement": "Elves are immortal",
            "canon_level": "canon",
            "source_ref": "core",
        },
        {
            "id": "a2",
            "statement": "Dwarves are mortal",
            "canon_level": "canon",
            "source_ref": "core",
        },
    ]


@pytest.fixture
def canon_facts():
    return [
        {
            "id": "f1",
            "statement": "The Sundering happened 1000 years ago",
            "canon_level": "canon",
            "source_ref": "core",
        },
        {
            "id": "f2",
            "statement": "Dragons are extinct",
            "canon_level": "canon",
            "source_ref": "core",
        },
    ]


# =============================================================================
# PUBLIC API: detect_contradictions
# =============================================================================


def test_detect_contradictions_no_contradictions(sample_axiom, canon_axioms):
    pack = _pack(axioms=[sample_axiom])
    result = detect_contradictions(pack, canon_axioms, [])
    assert isinstance(result, ContradictionResult)
    assert result.total_contradictions == 0


def test_detect_contradictions_with_negation():
    pack = _pack(axioms=[ExtractedAxiom(statement="Elves are not immortal", source_ref="new-book", confidence=0.9)])
    canon = [
        {
            "id": "a1",
            "statement": "Elves are immortal",
            "canon_level": "canon",
            "source_ref": "core",
        }
    ]
    result = detect_contradictions(pack, canon, [])
    assert result.total_contradictions >= 1
    assert result.high_severity_count >= 1
    match = result.axiom_contradictions[0]
    assert match.contradiction_type == ContradictionType.SEMANTIC_OPPOSITE


def test_detect_contradictions_ignores_identical():
    """Identical statements should not be flagged as contradictions (dedup handles them)."""
    pack = _pack(axioms=[ExtractedAxiom(statement="Elves are immortal", source_ref="new-book", confidence=0.9)])
    canon = [
        {
            "id": "a1",
            "statement": "Elves are immortal",
            "canon_level": "canon",
            "source_ref": "core",
        }
    ]
    result = detect_contradictions(pack, canon, [])
    assert result.total_contradictions == 0


# =============================================================================
# _check_axioms
# =============================================================================


def test_check_axioms_empty_canon(sample_axiom):
    result = _check_axioms([sample_axiom], [])
    assert result == []


def test_check_axioms_opposite_terms():
    axioms = [ExtractedAxiom(statement="Goblins are evil", source_ref="book", confidence=0.8)]
    canon = [{"statement": "Goblins are good", "canon_level": "canon", "source_ref": "core"}]
    result = _check_axioms(axioms, canon)
    assert len(result) == 1
    assert result[0].contradiction_type == ContradictionType.SEMANTIC_OPPOSITE
    # Axiom contradictions are always at least HIGH severity
    assert result[0].severity == ContradictionSeverity.HIGH


# =============================================================================
# _check_lore_facts
# =============================================================================


def test_check_lore_facts_skips_rumors():
    from monitor_data.schemas.base import KnowledgeScope

    fact = ExtractedLoreFact(
        statement="Dragons are alive",
        source_ref="book",
        confidence=0.8,
        knowledge_scope=KnowledgeScope.CHARACTER,
    )
    canon = [{"statement": "Dragons are extinct", "canon_level": "canon", "source_ref": "core"}]
    result = _check_lore_facts([fact], canon)
    # Character knowledge contradicting canon is intentionally skipped
    assert len(result) == 0


def test_check_lore_facts_world_scope_detects():
    fact = ExtractedLoreFact(
        statement="Dragons are not extinct",
        source_ref="book",
        confidence=0.9,
    )
    canon = [{"statement": "Dragons are extinct", "canon_level": "canon", "source_ref": "core"}]
    result = _check_lore_facts([fact], canon)
    assert len(result) == 1
    assert result[0].severity == ContradictionSeverity.HIGH


# =============================================================================
# _compare_statements
# =============================================================================


def test_compare_statements_identical_returns_none():
    result = _compare_statements("Same text", "Same text")
    assert result is None


def test_compare_statements_near_identical_returns_none():
    result = _compare_statements("Elves are immortal beings", "Elves are immortal being")
    assert result is None  # >0.92 similarity


def test_compare_statements_negation():
    result = _compare_statements(
        "The door is not locked",
        "The door is locked",
    )
    assert result is not None
    assert result.contradiction_type == ContradictionType.SEMANTIC_OPPOSITE
    assert result.severity == ContradictionSeverity.HIGH


def test_compare_statements_opposite_terms():
    result = _compare_statements(
        "The villain is mortal",
        "The villain is immortal",
    )
    assert result is not None
    assert result.contradiction_type == ContradictionType.SEMANTIC_OPPOSITE


def test_compare_statements_partial_overlap_shared_subject():
    result = _compare_statements(
        "the dragon attacked the village yesterday",
        "the dragon attacked the castle yesterday",
    )
    # 'dragon' is a shared proper noun, similarity ~0.85, should flag as partial overlap
    assert result is not None
    assert result.contradiction_type == ContradictionType.PARTIAL_OVERLAP
    assert result.severity == ContradictionSeverity.LOW


def test_compare_statements_partial_overlap_no_shared_subject():
    """Without shared subject, partial overlap should not flag."""
    result = _compare_statements(
        "the cat sat on the mat",
        "the dog ran on the mat",
    )
    # 'mat' is shared token but not proper noun; only one shared long token
    assert result is None


# =============================================================================
# HEURISTIC HELPERS
# =============================================================================


def test_has_negation_conflict_true():
    assert _has_negation_conflict("The door is not locked", "The door is locked") is True
    assert _has_negation_conflict("Elves are not mortal", "Elves are mortal") is True


def test_has_negation_conflict_bidirectional():
    # Either direction should detect
    assert _has_negation_conflict("X is locked", "X is not locked") is True


def test_has_negation_conflict_false():
    assert _has_negation_conflict("The door is blue", "The door is red") is False
    assert _has_negation_conflict("Dragons fly", "Dragons breathe fire") is False


def test_has_opposite_terms_found():
    assert _has_opposite_terms("The hero is mortal", "The villain is immortal") == "mortal/immortal"
    assert _has_opposite_terms("The door is open", "The door is closed") == "open/closed"


def test_has_opposite_terms_not_found():
    assert _has_opposite_terms("Elves are tall", "Dwarves are short") is None


def test_shares_subject_proper_nouns():
    assert _shares_subject("Aragorn fought at Helm's Deep", "Aragorn is the King") is True
    assert _shares_subject("Gandalf arrived", "Gandalf departed") is True


def test_shares_subject_fallback_tokens():
    # No proper nouns, but shared long tokens (fortress, kingdom are both >=5)
    assert _shares_subject("the fortress stands in a kingdom", "the fortress fell in a kingdom") is True


def test_shares_subject_false():
    assert _shares_subject("the cat sat", "the dog ran") is False


# =============================================================================
# SEVERITY & UTILS
# =============================================================================


def test_classify_severity_canon_high_similarity():
    assert _classify_severity(0.85, "canon") == ContradictionSeverity.HIGH


def test_classify_severity_canon_medium_similarity():
    assert _classify_severity(0.70, "canon") == ContradictionSeverity.MEDIUM


def test_classify_severity_proposed():
    assert _classify_severity(0.90, "proposed") == ContradictionSeverity.LOW
    assert _classify_severity(0.90, "rumor") == ContradictionSeverity.LOW


def test_safe_uuid_valid():
    u = uuid4()
    assert _safe_uuid(str(u)) == u


def test_safe_uuid_none():
    assert _safe_uuid(None) is None


def test_safe_uuid_invalid():
    assert _safe_uuid("not-a-uuid") is None


def test_levenshtein_ratio_identical():
    assert _levenshtein_ratio("hello", "hello") == 1.0


def test_levenshtein_ratio_empty():
    assert _levenshtein_ratio("", "hello") == 0.0
    assert _levenshtein_ratio("hello", "") == 0.0


def test_levenshtein_ratio_very_different_strings():
    # Very different strings score near zero (rapidfuzz exact ratio, no
    # quick-reject shortcut — the old pure-Python impl returned a hard 0.0)
    assert _levenshtein_ratio("hi", "this is a very long string that is nothing alike") < 0.1


def test_levenshtein_ratio_partial():
    ratio = _levenshtein_ratio("hello world", "hello there")
    assert 0.0 < ratio < 1.0


# =============================================================================
# INTEGRATION: full contradiction pipeline
# =============================================================================


def test_full_pipeline_no_false_positives_on_different_subjects():
    """Two unrelated statements about different subjects should not contradict."""
    pack = _pack(
        axioms=[
            ExtractedAxiom(statement="Elves live in forests", source_ref="book1", confidence=0.9),
        ],
        lore_facts=[
            ExtractedLoreFact(statement="Dragons breathe fire", source_ref="book1", confidence=0.9),
        ],
    )
    canon_axioms = [{"statement": "Dwarves live underground", "canon_level": "canon"}]
    canon_facts = [{"statement": "Orcs are warlike", "canon_level": "canon"}]
    result = detect_contradictions(pack, canon_axioms, canon_facts)
    assert result.total_contradictions == 0


def test_full_pipeline_multiple_contradictions():
    pack = _pack(
        axioms=[
            ExtractedAxiom(statement="Elves are not immortal", source_ref="new", confidence=0.9),
            ExtractedAxiom(statement="Dwarves are not mortal", source_ref="new", confidence=0.9),
        ],
        lore_facts=[
            ExtractedLoreFact(statement="Dragons are not extinct", source_ref="new", confidence=0.9),
        ],
    )
    canon_axioms = [
        {"statement": "Elves are immortal", "canon_level": "canon"},
        {"statement": "Dwarves are mortal", "canon_level": "canon"},
    ]
    canon_facts = [
        {"statement": "Dragons are extinct", "canon_level": "canon"},
    ]
    result = detect_contradictions(pack, canon_axioms, canon_facts)
    assert result.total_contradictions == 3
    assert result.high_severity_count == 3


def test_contradiction_result_compute_totals():
    result = ContradictionResult(
        axiom_contradictions=[],
        lore_contradictions=[],
        entity_contradictions=[],
    )
    result.compute_totals()
    assert result.total_contradictions == 0
    assert result.high_severity_count == 0
    assert result.critical_severity_count == 0


def test_detect_contradictions_unrelated_statements():
    """Identical statements and different-subject statements should not contradict."""
    pack = _pack(axioms=[ExtractedAxiom(statement="The sky is blue today", source_ref="book1", confidence=0.9)])
    canon = [{"statement": "The ocean is deep and cold", "canon_level": "canon", "source_ref": "core"}]
    result = detect_contradictions(pack, canon, [])
    assert result.total_contradictions == 0


def test_detect_contradictions_opposite_pair_across_subjects():
    """Opposite terms in statements about different subjects should not flag if no shared subject."""
    pack = _pack(axioms=[ExtractedAxiom(statement="Dragons are alive", source_ref="book1", confidence=0.9)])
    canon = [{"statement": "Orcs are dead", "canon_level": "canon", "source_ref": "core"}]
    result = detect_contradictions(pack, canon, [])
    # No shared proper nouns, only "are" is shared long token, so _shares_subject is False
    assert result.total_contradictions == 0
