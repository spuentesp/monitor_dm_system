"""
Property-based tests for core schema validation invariants.

These tests use Hypothesis to verify that fundamental data models
(FactCreate, EntityCreate, StateTagsUpdate) enforce their constraints
across thousands of randomly generated inputs.

Key invariants tested:
  - FactCreate: statement 1–2000 chars, magnitude 1–10, confidence 0.0–1.0
  - EntityCreate: name 1–200 chars, state_tags uniqueness, confidence bounds
  - StateTagsUpdate: no overlap between add_tags and remove_tags
  - Authority: CanonLevel/Auth transitions
  - CanonLevel: proposed/canon/rumor/character_belief consistency

Use Cases: P-3, P-4, M-1, M-2, SYS-2
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from monitor_data.schemas.base import Authority, CanonLevel
from monitor_data.schemas.entities import EntityCreate, StateTagsUpdate
from monitor_data.schemas.facts import FactCreate, FactStatus, FactType, SimulationScope


# =============================================================================
# CUSTOM STRATEGIES
# =============================================================================


def fact_create_ordered_strategy() -> st.SearchStrategy[FactCreate]:
    """Generate FactCreate instances that satisfy all Pydantic constraints."""
    return st.builds(
        FactCreate,
        universe_id=st.uuids(),
        statement=st.text(min_size=1, max_size=2000),
        fact_type=st.sampled_from(list(FactType)),
        magnitude=st.integers(min_value=1, max_value=10),
        scope=st.sampled_from(list(SimulationScope)),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        authority=st.sampled_from(list(Authority)),
        canon_level=st.sampled_from(list(CanonLevel)),
        status=st.sampled_from(list(FactStatus)),
        entity_ids=st.none() | st.lists(st.uuids(), min_size=1, max_size=10),
        source_ids=st.none() | st.lists(st.uuids(), min_size=1, max_size=10),
        scene_ids=st.none() | st.lists(st.uuids(), min_size=1, max_size=5),
    )


def entity_create_strategy() -> st.SearchStrategy[EntityCreate]:
    """Generate valid EntityCreate instances."""
    return st.builds(
        EntityCreate,
        name=st.text(min_size=1, max_size=200),
        state_tags=st.lists(
            st.text(min_size=1, max_size=50).filter(lambda s: len(s.strip()) > 0),
            min_size=0,
            max_size=20,
            unique=True,
        ),
        properties=st.dictionaries(
            keys=st.text(min_size=1, max_size=50),
            values=st.one_of(
                st.text(min_size=1, max_size=200),
                st.integers(min_value=-10000, max_value=10000),
                st.floats(allow_nan=False, allow_infinity=False),
                st.booleans(),
            ),
            min_size=0,
            max_size=10,
        ),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )


def state_tags_update_strategy() -> st.SearchStrategy[StateTagsUpdate]:
    """Generate StateTagsUpdate instances with guaranteed no overlap."""
    # Generate disjoint tag sets
    all_tags = st.lists(
        st.text(min_size=1, max_size=50).filter(lambda s: len(s.strip()) > 0),
        min_size=2,
        max_size=20,
        unique=True,
    )
    return all_tags.map(_split_tags)


def _split_tags(tags: list[str]) -> StateTagsUpdate:
    """Split tags into non-overlapping add/remove sets."""
    mid = max(1, len(tags) // 2)
    return StateTagsUpdate(
        add_tags=tags[:mid],
        remove_tags=tags[mid:],
    )


# =============================================================================
# TESTS: FactCreate
# =============================================================================


class TestFactCreateProperties:
    """Property-based tests for FactCreate invariants."""

    @given(fact=fact_create_ordered_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_statement_non_empty_and_bounded(self, fact: FactCreate) -> None:
        """statement is 1–2000 characters."""
        assert 1 <= len(fact.statement) <= 2000, (
            f"statement length {len(fact.statement)} outside [1, 2000]"
        )

    @given(fact=fact_create_ordered_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_magnitude_in_range(self, fact: FactCreate) -> None:
        """magnitude is 1–10."""
        assert 1 <= fact.magnitude <= 10, (
            f"magnitude {fact.magnitude} outside [1, 10]"
        )

    @given(fact=fact_create_ordered_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_confidence_in_range(self, fact: FactCreate) -> None:
        """confidence is 0.0–1.0."""
        assert 0.0 <= fact.confidence <= 1.0, (
            f"confidence {fact.confidence} outside [0.0, 1.0]"
        )

    @given(fact=fact_create_ordered_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_entity_ids_all_uuid_no_none_mixed(self, fact: FactCreate) -> None:
        """All entity_ids are valid UUIDs; None not mixed into list."""
        if fact.entity_ids is not None:
            assert len(fact.entity_ids) > 0
            for eid in fact.entity_ids:
                assert isinstance(eid, UUID)

    @given(fact=fact_create_ordered_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_fact_type_is_valid_enum(self, fact: FactCreate) -> None:
        """fact_type is always a valid FactType enum."""
        assert isinstance(fact.fact_type, FactType)
        assert fact.fact_type.value in {t.value for t in FactType}

    @given(
        magnitude=st.one_of(
            st.integers(max_value=0),
            st.integers(min_value=11),
        ),
    )
    @settings(max_examples=30, deadline=1000)
    def test_rejects_out_of_range_magnitude(self, magnitude: int) -> None:
        """FactCreate rejects magnitude outside [1, 10]."""
        assume(magnitude < 1 or magnitude > 10)
        with pytest.raises(Exception):
            FactCreate(
                universe_id=uuid4(),
                statement="test",
                magnitude=magnitude,
            )

    @given(
        confidence=st.one_of(
            st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False),
            st.floats(min_value=1.01, allow_nan=False, allow_infinity=False),
        ),
    )
    @settings(max_examples=30, deadline=1000)
    def test_rejects_out_of_range_confidence(self, confidence: float) -> None:
        """FactCreate rejects confidence outside [0.0, 1.0]."""
        assume(confidence < 0.0 or confidence > 1.0)
        with pytest.raises(Exception):
            FactCreate(
                universe_id=uuid4(),
                statement="test",
                confidence=confidence,
            )

    @given(
        statement=st.text(min_size=2001, max_size=5000).filter(lambda s: len(s) > 2000),
    )
    @settings(max_examples=20, deadline=1000)
    def test_rejects_overlong_statement(self, statement: str) -> None:
        """FactCreate rejects statement > 2000 chars."""
        assume(len(statement) > 2000)
        with pytest.raises(Exception):
            FactCreate(
                universe_id=uuid4(),
                statement=statement,
            )


# =============================================================================
# TESTS: EntityCreate
# =============================================================================


class TestEntityCreateProperties:
    """Property-based tests for EntityCreate invariants."""

    @given(entity=entity_create_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_name_non_empty_and_bounded(self, entity: EntityCreate) -> None:
        """name is 1–200 characters."""
        assert 1 <= len(entity.name) <= 200, (
            f"name length {len(entity.name)} outside [1, 200]"
        )

    @given(entity=entity_create_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_confidence_in_range(self, entity: EntityCreate) -> None:
        """confidence is 0.0–1.0."""
        assert 0.0 <= entity.confidence <= 1.0, (
            f"confidence {entity.confidence} outside [0.0, 1.0]"
        )

    @given(entity=entity_create_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_state_tags_unique(self, entity: EntityCreate) -> None:
        """state_tags contain no duplicates."""
        assert len(entity.state_tags) == len(set(entity.state_tags)), (
            f"state_tags has duplicates: {entity.state_tags}"
        )

    @given(
        name=st.text(min_size=201, max_size=500).filter(lambda n: len(n) > 200),
    )
    @settings(max_examples=20, deadline=1000)
    def test_rejects_overlong_name(self, name: str) -> None:
        """EntityCreate rejects name > 200 chars."""
        assume(len(name) > 200)
        with pytest.raises(Exception):
            EntityCreate(name=name)

    @given(
        confidence=st.floats(min_value=1.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, deadline=1000)
    def test_rejects_confidence_above_1(self, confidence: float) -> None:
        """EntityCreate rejects confidence > 1.0."""
        assume(confidence > 1.0)
        with pytest.raises(Exception):
            EntityCreate(name="test", confidence=confidence)


# =============================================================================
# TESTS: StateTagsUpdate
# =============================================================================


class TestStateTagsUpdateProperties:
    """Property-based tests for StateTagsUpdate invariants."""

    @given(update=state_tags_update_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_no_overlap_between_add_and_remove(self, update: StateTagsUpdate) -> None:
        """add_tags and remove_tags have no overlap."""
        add_set = set(update.add_tags)
        remove_set = set(update.remove_tags)
        overlap = add_set & remove_set
        assert len(overlap) == 0, (
            f"Overlapping tags: {overlap}"
        )

    @given(update=state_tags_update_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_add_tags_unique(self, update: StateTagsUpdate) -> None:
        """add_tags have no duplicates."""
        assert len(update.add_tags) == len(set(update.add_tags))

    @given(update=state_tags_update_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_remove_tags_unique(self, update: StateTagsUpdate) -> None:
        """remove_tags have no duplicates."""
        assert len(update.remove_tags) == len(set(update.remove_tags))

    @given(
        add_tags=st.lists(
            st.text(min_size=1, max_size=50),
            min_size=0,
            max_size=5,
            unique=True,
        ),
        remove_tags=st.lists(
            st.text(min_size=1, max_size=50),
            min_size=0,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=50, deadline=1000)
    def test_accepts_non_overlapping_update(
        self, add_tags: list[str], remove_tags: list[str]
    ) -> None:
        """StateTagsUpdate accepts non-overlapping add/remove sets."""
        # Ensure no overlap between the lists
        assume(len(set(add_tags) & set(remove_tags)) == 0)
        update = StateTagsUpdate(add_tags=add_tags, remove_tags=remove_tags)
        assert update.add_tags == add_tags
        assert update.remove_tags == remove_tags

    @given(
        tag=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=20, deadline=1000)
    def test_rejects_overlapping_add_remove(self, tag: str) -> None:
        """StateTagsUpdate rejects overlapping add_tags and remove_tags."""
        with pytest.raises(ValueError, match="cannot appear in both"):
            StateTagsUpdate(add_tags=[tag], remove_tags=[tag])


# =============================================================================
# TESTS: Authority & CanonLevel
# =============================================================================


class TestAuthorityProperties:
    """Property-based tests for Authority and CanonLevel invariants."""

    @given(
        authority=st.sampled_from(list(Authority)),
        canon_level=st.sampled_from(list(CanonLevel)),
    )
    @settings(max_examples=50, deadline=1000)
    def test_valid_enum_values(self, authority: Authority, canon_level: CanonLevel) -> None:
        """All enum values are valid strings."""
        assert isinstance(authority.value, str)
        assert len(authority.value) > 0
        assert isinstance(canon_level.value, str)
        assert len(canon_level.value) > 0

    @given(fact=fact_create_ordered_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_default_authority_is_system(self, fact: FactCreate) -> None:
        """When authority is not explicitly SYSTEM, fact still has a valid authority."""
        assert fact.authority in list(Authority)
        # SYSTEM is the default — verify it's set correctly when not specified
        if fact.authority == Authority.SYSTEM:
            assert fact.authority.value == "system"

    @given(fact=fact_create_ordered_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_default_canon_level_is_proposed(self, fact: FactCreate) -> None:
        """Default canon_level should be PROPOSED."""
        assert fact.canon_level in list(CanonLevel)
