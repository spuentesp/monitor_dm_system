"""
Property-based tests for fact schema invariants.

Tests fact validation across random inputs:
- statement length bounds (1-2000)
- magnitude bounds (1-10)
- confidence bounds (0.0-1.0)
- canon level values
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from uuid import uuid4

from monitor_data.schemas.base import Authority, CanonLevel
from monitor_data.schemas.facts import (
    FactCreate,
    FactType,
    SimulationScope,
    FactStatus,
    FactUpdate,
)


class TestFactCreate:
    @given(
        statement=st.text(min_size=1, max_size=100),
        fact_type=st.sampled_from(list(FactType)),
    )
    @settings(max_examples=100)
    def test_fact_create_with_statement(self, statement, fact_type):
        """Any valid statement and type produces a valid FactCreate."""
        f = FactCreate(
            universe_id=uuid4(),
            statement=statement,
            fact_type=fact_type,
        )
        assert f.statement.strip() == statement.strip()
        assert f.fact_type == fact_type
        assert f.magnitude == 1  # default
        assert f.confidence == 1.0  # default
        assert f.canon_level == CanonLevel.PROPOSED
        assert f.status == FactStatus.ACTIVE

    @given(magnitude=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50)
    def test_magnitude_in_range(self, magnitude):
        f = FactCreate(universe_id=uuid4(), statement="Test", fact_type=FactType.STATE, magnitude=magnitude)
        assert 1 <= f.magnitude <= 10

    @given(confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_confidence_in_range(self, confidence):
        f = FactCreate(universe_id=uuid4(), statement="Test", fact_type=FactType.STATE, confidence=confidence)
        assert 0.0 <= f.confidence <= 1.0

    @given(statement=st.text(min_size=2001, max_size=5000))
    @settings(max_examples=30)
    def test_statement_too_long_fails(self, statement):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            FactCreate(universe_id=uuid4(), statement=statement, fact_type=FactType.STATE)


class TestFactUpdate:
    @given(new_statement=st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_update_statement(self, new_statement):
        u = FactUpdate(statement=new_statement)
        assert u.statement == new_statement


class TestCanonLevelTransitions:
    def test_all_canon_levels(self):
        assert CanonLevel.PROPOSED.value == "proposed"
        assert CanonLevel.CANON.value == "canon"
        assert CanonLevel.RUMOR.value == "rumor"
        assert CanonLevel.CHARACTER_BELIEF.value == "character_belief"
        assert CanonLevel.PLAYER_KNOWLEDGE.value == "player_knowledge"
        assert CanonLevel.RETCONNED.value == "retconned"
        assert CanonLevel.SUPERSEDED.value == "superseded"


class TestAuthorityValues:
    def test_all_authorities(self):
        assert Authority.SOURCE.value == "source"
        assert Authority.GM.value == "gm"
        assert Authority.SYSTEM.value == "system"
        assert Authority.PLAYER.value == "player"


class TestFactTypeAndScope:
    def test_fact_types(self):
        assert FactType.STATE.value == "state"
        assert FactType.RELATIONSHIP.value == "relationship"
        assert FactType.ATTRIBUTE.value == "attribute"
        assert FactType.OCCURRENCE.value == "occurrence"

    def test_simulation_scopes(self):
        assert SimulationScope.LOCAL.value == "local"
        assert SimulationScope.REGIONAL.value == "regional"
        assert SimulationScope.GLOBAL.value == "global"

    def test_fact_statuses(self):
        assert FactStatus.ACTIVE.value == "active"
        assert FactStatus.SUPERSEDED.value == "superseded"
        assert FactStatus.TOMBSTONED.value == "tombstoned"
