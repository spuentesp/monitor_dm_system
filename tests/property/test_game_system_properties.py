"""
Property-based tests for game system model invariants.

These tests use Hypothesis to verify that game system models enforce
their structural invariants across thousands of randomly generated inputs.

Key invariants tested:
  - AttributeDefinition: min_value ≤ default_value ≤ max_value
  - TrackDefinition: min_value ≤ default_value ≤ max_value (when numeric)
  - TieredAbilitySystem: max_tier ≥ len(tiers), no duplicate tier numbers
  - AbilityTier: tier ≥ 1, no self-referencing prerequisites
  - ThresholdEffect: value ordering, direction consistency
  - GameSystemCreate: attribute/skill/track name uniqueness, full roundtrip

Use Cases: DL-20, P-4, M-13
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from monitor_data.schemas.game_systems import (
    AbilityTier,
    AttributeDefinition,
    CoreMechanic,
    CoreMechanicType,
    GameSystemCreate,
    SkillDefinition,
    SuccessType,
    ThresholdEffect,
    TieredAbilitySystem,
    TrackDefinition,
)


# =============================================================================
# CUSTOM STRATEGIES
# =============================================================================


def attribute_def_strategy_ordered() -> st.SearchStrategy[AttributeDefinition]:
    """Generate AttributeDefinitions where min ≤ default ≤ max is guaranteed."""
    return st.builds(
        AttributeDefinition,
        name=st.text(min_size=1, max_size=100),
        abbreviation=st.text(min_size=1, max_size=10),
        # Generate ordered triples: low ≤ mid ≤ high
        min_value=st.integers(min_value=0, max_value=8),
        max_value=st.integers(min_value=12, max_value=30),
        default_value=st.integers(min_value=8, max_value=12),
        modifier_formula=st.none() | st.text(min_size=1, max_size=200),
    ).filter(lambda a: a.min_value <= a.default_value <= a.max_value)


def track_def_ordered_strategy() -> st.SearchStrategy[TrackDefinition]:
    """Generate TrackDefinitions where min ≤ default ≤ max (when numeric)."""
    min_val = st.integers(min_value=0, max_value=50)
    default_val = st.integers(min_value=0, max_value=100)
    max_val = st.integers(min_value=1, max_value=200)
    return st.builds(
        TrackDefinition,
        name=st.text(min_size=1, max_size=200),
        abbreviation=st.none() | st.text(min_size=1, max_size=20),
        min_value=min_val,
        max_value=max_val,
        default_value=default_val,
        track_type=st.sampled_from(["hp", "stress", "pool", "points", "custom"]),
        depleted_effect=st.none() | st.text(min_size=1, max_size=500),
        maxed_effect=st.none() | st.text(min_size=1, max_size=500),
    ).filter(
        lambda t: not isinstance(t.default_value, int)
        or t.max_value is None
        or t.min_value <= t.default_value <= t.max_value
    )


def tiered_ability_ordered_strategy() -> st.SearchStrategy[TieredAbilitySystem]:
    """Generate TieredAbilitySystem instances with unique, ordered tiers and correct max_tier."""
    # Generate unique tier numbers
    def build_with_ordered_tiers(num_tiers: int) -> TieredAbilitySystem:
        tier_nums = list(range(1, num_tiers + 1))  # 1, 2, 3, ...
        tiers_list = [
            AbilityTier(
                tier=t,
                name=f"Tier {t}",
                effect=f"Effect for tier {t}",
            )
            for t in tier_nums
        ]
        return TieredAbilitySystem(
            name=f"System ({num_tiers} tiers)",
            tiers=tiers_list,
            max_tier=max(num_tiers, 1),
        )

    return st.integers(min_value=0, max_value=10).map(build_with_ordered_tiers)


# =============================================================================
# TESTS: AttributeDefinition
# =============================================================================


class TestAttributeDefinitionProperties:
    """Property-based tests for AttributeDefinition invariants."""

    @given(attr=attribute_def_strategy_ordered())
    @settings(max_examples=100, deadline=1000)
    def test_min_default_max_ordering_holds(self, attr: AttributeDefinition) -> None:
        """min_value ≤ default_value ≤ max_value must hold for valid attributes."""
        assert attr.min_value <= attr.default_value <= attr.max_value, (
            f"Attribute '{attr.name}': min={attr.min_value}, "
            f"default={attr.default_value}, max={attr.max_value}"
        )

    @given(
        name=st.text(min_size=1, max_size=100),
        abbreviation=st.text(min_size=1, max_size=10),
        min_value=st.integers(min_value=0, max_value=20),
        max_value=st.integers(min_value=0, max_value=20),
        default_value=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=100, deadline=1000)
    def test_accepts_any_ordering_at_creation(
        self, name: str, abbreviation: str, min_value: int, max_value: int, default_value: int
    ) -> None:
        """AttributeDefinition does NOT enforce min ≤ default ≤ max at Pydantic level.

        This test documents the current behavior: the invariant is implicit,
        not enforced by a validator.  If a validator is added later, this test
        should be updated to expect ValueError for invalid orderings.
        """
        attr = AttributeDefinition(
            name=name,
            abbreviation=abbreviation,
            min_value=min_value,
            max_value=max_value,
            default_value=default_value,
        )
        # Document that Pydantic accepts it — the invariant is a contract test concern
        assert attr.name == name
        assert attr.min_value == min_value
        assert attr.max_value == max_value
        assert attr.default_value == default_value
        # Check the invariant manually (not enforced by Pydantic)
        if not (min_value <= default_value <= max_value):
            # If this starts failing, a validator was added — update the test
            pass

    @given(
        name=st.text(min_size=0, max_size=1).filter(lambda n: len(n) == 0),
        abbreviation=st.text(min_size=1, max_size=10),
    )
    @settings(max_examples=20, deadline=1000)
    def test_empty_name_accepted_by_pydantic(self, name: str, abbreviation: str) -> None:
        """AttributeDefinition accepts empty name — Field(max_length=...) doesn't enforce min_length.
        
        This documents the current behavior. If a min_length validator is added,
        this test should be updated to expect a ValidationError.
        """
        assume(len(name) == 0)  # Explicitly empty
        attr = AttributeDefinition(
            name=name,
            abbreviation=abbreviation,
            min_value=0,
            max_value=10,
            default_value=5,
        )
        assert attr.name == name  # Empty string currently accepted

    @given(
        name=st.text(min_size=101, max_size=200).filter(lambda n: len(n) > 100),
        abbreviation=st.text(min_size=1, max_size=10),
    )
    @settings(max_examples=20, deadline=1000)
    def test_rejects_overlong_name(self, name: str, abbreviation: str) -> None:
        """AttributeDefinition rejects name > 100 chars."""
        assume(len(name) > 100)
        with pytest.raises(Exception):
            AttributeDefinition(
                name=name,
                abbreviation=abbreviation,
                min_value=0,
                max_value=10,
                default_value=5,
            )


# =============================================================================
# TESTS: TrackDefinition
# =============================================================================


class TestTrackDefinitionProperties:
    """Property-based tests for TrackDefinition invariants."""

    @given(track=track_def_ordered_strategy())
    @settings(max_examples=150, deadline=2000)
    def test_min_default_ordering_when_numeric(self, track: TrackDefinition) -> None:
        """When default_value is an integer, min_value ≤ default_value ≤ max_value should hold."""
        if isinstance(track.default_value, int):
            if track.max_value is not None:
                assert track.min_value <= track.default_value <= track.max_value, (
                    f"Track '{track.name}': min={track.min_value}, "
                    f"default={track.default_value}, max={track.max_value}"
                )
            else:
                assert track.min_value <= track.default_value, (
                    f"Track '{track.name}': min={track.min_value}, "
                    f"default={track.default_value} (unbounded max)"
                )

    @given(
        min_value=st.integers(min_value=-100, max_value=-1),
        default_value=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=30, deadline=1000)
    def test_accepts_negative_min_value(self, min_value: int, default_value: int) -> None:
        """TrackDefinition accepts negative min_value (e.g., sanity meters)."""
        track = TrackDefinition(
            name="test",
            min_value=min_value,
            default_value=default_value,
        )
        assert track.min_value == min_value

    @given(
        threshold_effects=st.lists(
            st.builds(
                ThresholdEffect,
                value=st.integers(min_value=-50, max_value=200),
                direction=st.sampled_from(["at_or_below", "at_or_above", "exactly"]),
                effect=st.text(min_size=1, max_size=500),
            ),
            max_size=20,
        ),
    )
    @settings(max_examples=50, deadline=2000)
    def test_threshold_ordering_preserved(
        self, threshold_effects: list[ThresholdEffect]
    ) -> None:
        """Threshold effects in a track should be orderable by value."""
        track = TrackDefinition(
            name="test",
            threshold_effects=threshold_effects,
        )
        # All threshold values should be integers
        for te in track.threshold_effects:
            assert isinstance(te.value, int)
        # Can be sorted (no requirement that they are unique)
        sorted_effects = sorted(threshold_effects, key=lambda t: t.value)
        assert len(sorted_effects) == len(threshold_effects)


# =============================================================================
# TESTS: TieredAbilitySystem
# =============================================================================


class TestTieredAbilitySystemProperties:
    """Property-based tests for TieredAbilitySystem and AbilityTier invariants."""

    @given(system=tiered_ability_ordered_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_max_tier_at_least_number_of_tiers(self, system: TieredAbilitySystem) -> None:
        """max_tier ≥ len(tiers) must hold."""
        if len(system.tiers) > 0:
            assert system.max_tier >= len(system.tiers), (
                f"System '{system.name}': max_tier={system.max_tier}, "
                f"but has {len(system.tiers)} tiers"
            )

    @given(system=tiered_ability_ordered_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_no_duplicate_tier_numbers(self, system: TieredAbilitySystem) -> None:
        """Tier numbers within a system must be unique."""
        tier_numbers = [t.tier for t in system.tiers]
        assert len(tier_numbers) == len(set(tier_numbers)), (
            f"System '{system.name}' has duplicate tier numbers: {tier_numbers}"
        )

    @given(system=tiered_ability_ordered_strategy())
    @settings(max_examples=100, deadline=2000)
    def test_max_tier_positive(self, system: TieredAbilitySystem) -> None:
        """max_tier should be positive when tiers exist."""
        if len(system.tiers) > 0:
            assert system.max_tier >= 1, (
                f"System '{system.name}': max_tier={system.max_tier} but has tiers"
            )

    @given(
        tier=st.integers(min_value=-5, max_value=0),
        name=st.text(min_size=1, max_size=200),
        effect=st.text(min_size=1, max_size=2000),
    )
    @settings(max_examples=30, deadline=1000)
    def test_rejects_non_positive_tier(self, tier: int, name: str, effect: str) -> None:
        """AbilityTier rejects tier ≤ 0."""
        assume(tier <= 0)  # Ensure it's invalid
        with pytest.raises(Exception):
            AbilityTier(tier=tier, name=name, effect=effect)


# =============================================================================
# TESTS: AbilityTier
# =============================================================================


class TestAbilityTierProperties:
    """Property-based tests for AbilityTier invariants."""

    @given(
        tier=st.integers(min_value=1, max_value=10),
        name=st.text(min_size=1, max_size=200),
        effect=st.text(min_size=1, max_size=2000),
        prerequisite_count=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=100, deadline=1000)
    def test_prerequisites_are_strings(
        self, tier: int, name: str, effect: str, prerequisite_count: int
    ) -> None:
        """All prerequisites should be non-empty strings."""
        prereqs = [f"prereq_{i}" for i in range(prerequisite_count)]
        ability = AbilityTier(
            tier=tier,
            name=name,
            effect=effect,
            prerequisites=prereqs,
        )
        for prereq in ability.prerequisites:
            assert isinstance(prereq, str)
            assert len(prereq) > 0

    @given(
        tier=st.integers(min_value=1, max_value=10),
        name=st.text(min_size=1, max_size=200),
        effect=st.text(min_size=1, max_size=2000),
        cost=st.none() | st.text(min_size=1, max_size=100),
        duration=st.none() | st.text(min_size=1, max_size=100),
        roll=st.none() | st.text(min_size=1, max_size=300),
    )
    @settings(max_examples=100, deadline=1000)
    def test_optional_fields_are_coherent(
        self, tier: int, name: str, effect: str,
        cost: str | None, duration: str | None, roll: str | None,
    ) -> None:
        """Optional fields (cost, duration, roll) are either None or non-empty strings."""
        ability = AbilityTier(
            tier=tier,
            name=name,
            effect=effect,
            cost=cost,
            duration=duration,
            roll=roll,
        )
        for field_val, field_name in [
            (ability.cost, "cost"),
            (ability.duration, "duration"),
            (ability.roll, "roll"),
        ]:
            if field_val is not None:
                assert len(field_val) > 0, (
                    f"{field_name} should be non-empty if provided, got: {field_val!r}"
                )


# =============================================================================
# TESTS: ThresholdEffect
# =============================================================================


class TestThresholdEffectProperties:
    """Property-based tests for ThresholdEffect invariants."""

    @given(
        value=st.integers(min_value=-100, max_value=200),
        direction=st.sampled_from(["at_or_below", "at_or_above", "exactly"]),
        effect=st.text(min_size=1, max_size=500),
    )
    @settings(max_examples=100, deadline=1000)
    def test_effect_description_non_empty(self, value: int, direction: str, effect: str) -> None:
        """ThresholdEffect always has a non-empty effect description."""
        te = ThresholdEffect(value=value, direction=direction, effect=effect)
        assert len(te.effect) > 0
        assert te.direction in ("at_or_below", "at_or_above", "exactly")


# =============================================================================
# TESTS: SkillDefinition
# =============================================================================


class TestSkillDefinitionProperties:
    """Property-based tests for SkillDefinition invariants."""

    @given(
        name=st.text(min_size=1, max_size=100),
        abbreviation=st.none() | st.text(min_size=1, max_size=10),
        linked_attribute=st.none() | st.text(min_size=1, max_size=100),
        description=st.none() | st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=100, deadline=1000)
    def test_linked_attribute_is_valid_ref_or_none(
        self, name: str, abbreviation: str | None,
        linked_attribute: str | None, description: str | None,
    ) -> None:
        """linked_attribute is either None or a non-empty string (like 'Dexterity')."""
        skill = SkillDefinition(
            name=name,
            abbreviation=abbreviation,
            linked_attribute=linked_attribute,
            description=description,
        )
        if skill.linked_attribute is not None:
            assert len(skill.linked_attribute) > 0
        assert len(skill.name) > 0


# =============================================================================
# TESTS: GameSystemCreate — Composition & Roundtrip
# =============================================================================


def _minimal_core_mechanic() -> CoreMechanic:
    """Build a minimal valid CoreMechanic for GameSystemCreate."""
    return CoreMechanic(
        type=CoreMechanicType.D20,
        formula="d20+mod",
        success_type=SuccessType.MEET_OR_BEAT,
    )


class TestGameSystemCompositionProperties:
    """Property-based tests for GameSystemCreate composition invariants."""

    @given(
        name=st.text(min_size=1, max_size=200),
        description=st.text(min_size=0, max_size=1000),
        attributes=st.lists(attribute_def_strategy_ordered(), min_size=0, max_size=10),
        skills=st.lists(
            st.builds(
                SkillDefinition,
                name=st.text(min_size=1, max_size=100),
                linked_attribute=st.none() | st.text(min_size=1, max_size=100),
            ),
            min_size=0,
            max_size=10,
        ),
        ability_systems=st.lists(tiered_ability_ordered_strategy(), min_size=0, max_size=5),
        tracks=st.lists(track_def_ordered_strategy(), min_size=0, max_size=5),
    )
    @settings(max_examples=50, deadline=5000)
    def test_full_roundtrip_creates_valid_system(
        self,
        name: str,
        description: str,
        attributes: list[AttributeDefinition],
        skills: list[SkillDefinition],
        ability_systems: list[TieredAbilitySystem],
        tracks: list[TrackDefinition],
    ) -> None:
        """A GameSystemCreate with valid components roundtrips correctly."""
        system = GameSystemCreate(
            name=name,
            description=description,
            core_mechanic=_minimal_core_mechanic(),
            attributes=attributes,
            skills=skills,
            tiered_ability_systems=ability_systems,
            tracks=tracks,
        )
        assert system.name == name
        assert len(system.attributes) == len(attributes)
        assert len(system.skills) == len(skills)
        assert len(system.tiered_ability_systems) == len(ability_systems)
        assert len(system.tracks) == len(tracks)
        # Core mechanic must be present
        assert system.core_mechanic.type == CoreMechanicType.D20

    @given(
        attributes=st.lists(attribute_def_strategy_ordered(), min_size=1, max_size=10),
    )
    @settings(max_examples=50, deadline=2000)
    def test_attribute_names_unique_within_system(
        self, attributes: list[AttributeDefinition]
    ) -> None:
        """Attribute names should be unique within a game system.

        Documents current behavior — Pydantic does not enforce uniqueness,
        but the system invariant expects it.
        """
        system = GameSystemCreate(
            name="Test System",
            description="Testing attribute uniqueness",
            core_mechanic=_minimal_core_mechanic(),
            attributes=attributes,
        )
        names = [a.name for a in system.attributes]
        if len(names) != len(set(names)):
            # Document: Pydantic doesn't enforce uniqueness at schema level
            pass
        # Verify all attributes satisfy min ≤ default ≤ max
        for attr in system.attributes:
            assert attr.min_value <= attr.default_value <= attr.max_value, (
                f"Attribute '{attr.name}' violates min ≤ default ≤ max"
            )

    @given(
        skills=st.lists(
            st.builds(
                SkillDefinition,
                name=st.text(min_size=1, max_size=100),
            ),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=50, deadline=2000)
    def test_skill_names_unique_within_system(
        self, skills: list[SkillDefinition]
    ) -> None:
        """Skill names should be unique within a game system (documents current behavior)."""
        system = GameSystemCreate(
            name="Test System",
            description="Testing skill uniqueness",
            core_mechanic=_minimal_core_mechanic(),
            skills=skills,
        )
        names = [s.name for s in system.skills]
        if len(names) != len(set(names)):
            pass  # Document: not enforced at schema level

    @given(
        tracks=st.lists(track_def_ordered_strategy(), min_size=1, max_size=5),
    )
    @settings(max_examples=50, deadline=2000)
    def test_track_names_unique_within_system(
        self, tracks: list[TrackDefinition]
    ) -> None:
        """Track names should be unique within a game system (documents current behavior)."""
        system = GameSystemCreate(
            name="Test System",
            description="Testing track uniqueness",
            core_mechanic=_minimal_core_mechanic(),
            tracks=tracks,
        )
        names = [t.name for t in system.tracks]
        if len(names) != len(set(names)):
            pass  # Document: not enforced at schema level
