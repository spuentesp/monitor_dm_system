"""
Contract tests for Contradiction schemas.

Covers:
- ContradictionType enum (4 types: semantic, temporal, scope, partial)
- ContradictionSeverity enum (4 levels)
- ContradictionResolution enum (4 resolutions)
- ContradictionFact: one side of a contradiction
- ContradictionMatch: detected contradiction
- ContradictionResult: full result with compute_totals()

Use Cases: DL-5 (Contradiction detection)
"""

from __future__ import annotations

from uuid import uuid4
from typing import List

import pytest

from monitor_data.schemas.contradiction import (
    ContradictionType,
    ContradictionSeverity,
    ContradictionResolution,
    ContradictionFact,
    ContradictionMatch,
    ContradictionResult,
)


# =============================================================================
# Enums
# =============================================================================


class TestContradictionTypeEnum:
    def test_all_values(self):
        assert ContradictionType.SEMANTIC_OPPOSITE.value == "semantic_opposite"
        assert ContradictionType.TEMPORAL_OVERRIDE.value == "temporal_override"
        assert ContradictionType.SCOPE_CONFLICT.value == "scope_conflict"
        assert ContradictionType.PARTIAL_OVERLAP.value == "partial_overlap"


class TestContradictionSeverityEnum:
    def test_all_values(self):
        assert ContradictionSeverity.LOW.value == "low"
        assert ContradictionSeverity.MEDIUM.value == "medium"
        assert ContradictionSeverity.HIGH.value == "high"
        assert ContradictionSeverity.CRITICAL.value == "critical"


class TestContradictionResolutionEnum:
    def test_all_values(self):
        assert ContradictionResolution.NEW_WINS.value == "new_wins"
        assert ContradictionResolution.OLD_WINS.value == "old_wins"
        assert ContradictionResolution.MERGE.value == "merge"
        assert ContradictionResolution.REVIEW.value == "review"


# =============================================================================
# ContradictionFact
# =============================================================================


class TestContradictionFact:
    def test_minimal(self):
        f = ContradictionFact(statement="The king is alive")
        assert f.statement == "The king is alive"
        assert f.canon_level == "proposed"  # default
        assert f.confidence == 0.8  # default
        assert f.fact_type == "fact"  # default
        assert f.source_name is None

    def test_with_source(self):
        f = ContradictionFact(
            statement="The king is alive",
            source_name="PHB",
            source_id=uuid4(),
            canon_level="canon",
            confidence=0.95,
            fact_type="axiom",
        )
        assert f.source_name == "PHB"
        assert f.canon_level == "canon"
        assert f.fact_type == "axiom"

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            ContradictionFact(statement="x", confidence=1.5)
        with pytest.raises(Exception):
            ContradictionFact(statement="x", confidence=-0.1)


# =============================================================================
# ContradictionMatch
# =============================================================================


class TestContradictionMatch:
    def _make_facts(self):
        return (
            ContradictionFact(statement="The king is alive"),
            ContradictionFact(statement="The king is dead"),
        )

    def test_minimal(self):
        new, existing = self._make_facts()
        m = ContradictionMatch(
            contradiction_id="contra:axioms:0:1",
            contradiction_type=ContradictionType.SEMANTIC_OPPOSITE,
            severity=ContradictionSeverity.HIGH,
            new_fact=new,
            existing_fact=existing,
        )
        assert m.contradiction_id.startswith("contra:")
        assert m.similarity_score == 0.0  # default
        assert m.recommended_resolution == ContradictionResolution.REVIEW  # default

    def test_with_similarity(self):
        new, existing = self._make_facts()
        m = ContradictionMatch(
            contradiction_id="contra:lore_facts:5:2",
            contradiction_type=ContradictionType.SEMANTIC_OPPOSITE,
            severity=ContradictionSeverity.CRITICAL,
            new_fact=new,
            existing_fact=existing,
            similarity_score=0.95,
            explanation="Direct semantic contradiction",
            recommended_resolution=ContradictionResolution.NEW_WINS,
        )
        assert m.similarity_score == 0.95
        assert m.recommended_resolution == ContradictionResolution.NEW_WINS

    def test_similarity_bounds(self):
        new, existing = self._make_facts()
        with pytest.raises(Exception):
            ContradictionMatch(
                contradiction_id="x",
                contradiction_type=ContradictionType.SEMANTIC_OPPOSITE,
                severity=ContradictionSeverity.LOW,
                new_fact=new,
                existing_fact=existing,
                similarity_score=1.5,
            )


# =============================================================================
# ContradictionResult
# =============================================================================


class TestContradictionResult:
    def test_empty(self):
        r = ContradictionResult()
        assert r.total_contradictions == 0
        assert r.high_severity_count == 0
        assert r.critical_severity_count == 0
        assert r.all_matches == []

    def test_with_matches(self):
        new = ContradictionFact(statement="Arthur is king")
        existing = ContradictionFact(statement="Mordred is king")
        m1 = ContradictionMatch(
            contradiction_id="x1",
            contradiction_type=ContradictionType.SEMANTIC_OPPOSITE,
            severity=ContradictionSeverity.HIGH,
            new_fact=new,
            existing_fact=existing,
        )
        m2 = ContradictionMatch(
            contradiction_id="x2",
            contradiction_type=ContradictionType.SCOPE_CONFLICT,
            severity=ContradictionSeverity.CRITICAL,
            new_fact=new,
            existing_fact=existing,
        )
        r = ContradictionResult(
            checked_against_universe=uuid4(),
            axiom_contradictions=[m1],
            lore_contradictions=[m2],
        )
        r.compute_totals()
        assert r.total_contradictions == 2
        assert r.high_severity_count == 2  # both HIGH and CRITICAL
        assert r.critical_severity_count == 1
        assert len(r.all_matches) == 2

    def test_compute_totals_resets(self):
        """compute_totals should re-derive from scratch."""
        new = ContradictionFact(statement="x")
        existing = ContradictionFact(statement="y")
        m = ContradictionMatch(
            contradiction_id="x",
            contradiction_type=ContradictionType.PARTIAL_OVERLAP,
            severity=ContradictionSeverity.MEDIUM,
            new_fact=new,
            existing_fact=existing,
        )
        r = ContradictionResult(
            axiom_contradictions=[m],
            total_contradictions=999,  # stale value
        )
        r.compute_totals()
        assert r.total_contradictions == 1  # recomputed
