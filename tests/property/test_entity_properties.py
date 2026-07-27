"""
Property-based tests for entity schema invariants.

Uses Hypothesis to verify entity validation across random inputs.
"""

from __future__ import annotations

from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st
from monitor_data.schemas.base import DetailLevel, EntityType
from monitor_data.schemas.entities import EntityCreate, EntityFilter, EntityUpdate


class TestEntityCreate:
    @given(
        name=st.text(min_size=1, max_size=100),
        entity_type=st.sampled_from(list(EntityType)),
        is_archetype=st.booleans(),
    )
    @settings(max_examples=100)
    def test_create_with_name_and_type(self, name, entity_type, is_archetype):
        """Any valid name, type produce a valid EntityCreate."""
        e = EntityCreate(
            universe_id=uuid4(),
            name=name,
            entity_type=entity_type,
            is_archetype=is_archetype,
        )
        assert e.name.strip() == name.strip()
        assert e.entity_type == entity_type

    @given(
        confidence=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=100)
    def test_confidence_in_range(self, confidence):
        """Confidence is always clamped to 0.0-1.0 range."""
        e = EntityCreate(
            universe_id=uuid4(),
            name="Test",
            entity_type=EntityType.CHARACTER,
            confidence=confidence,
        )
        assert 0.0 <= e.confidence <= 1.0

    @given(name=st.text(min_size=201, max_size=500))
    @settings(max_examples=30)
    def test_name_too_long_fails(self, name):
        """Names > 200 chars are rejected."""
        import pytest as pt
        from pydantic import ValidationError

        with pt.raises(ValidationError):
            EntityCreate(
                universe_id=uuid4(), name=name, entity_type=EntityType.CHARACTER
            )


class TestEntityUpdate:
    @given(new_name=st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_update_name_partial(self, new_name):
        """EntityUpdate with only name set is valid."""
        u = EntityUpdate(name=new_name)
        assert u.name == new_name
        assert u.description is None


class TestEntityFilter:
    @given(
        limit=st.integers(min_value=1, max_value=100),
        offset=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=50)
    def test_pagination_bounds(self, limit, offset):
        """EntityFilter accepts valid pagination params."""
        f = EntityFilter(limit=limit, offset=offset)
        assert f.limit == limit
        assert f.offset == offset


class TestDetailLevel:
    def test_all_levels(self):
        assert DetailLevel.STUB.value == "stub"
        assert DetailLevel.SKETCHED.value == "sketched"
        assert DetailLevel.DETAILED.value == "detailed"
        assert DetailLevel.ELABORATED.value == "elaborated"


class TestEntityType:
    def test_entity_types(self):
        assert EntityType.CHARACTER.value == "character"
        assert EntityType.FACTION.value == "faction"
        assert EntityType.LOCATION.value == "location"
        assert EntityType.OBJECT.value == "object"
        assert EntityType.CONCEPT.value == "concept"
        assert EntityType.ORGANIZATION.value == "organization"
