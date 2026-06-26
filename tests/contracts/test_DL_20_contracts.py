"""
DL-20: Game Systems — Contract Tests

Tests the input/output contracts for game system schemas.
These tests validate schema constraints, not database interactions.

Use Cases: DL-20 (Game Systems)
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from monitor_data.schemas.game_systems import (
    CoreMechanicType,
    SuccessType,
    GameRuleType,
    AbilityScoreMethod,
    CreationStepType,
    NPCTier,
    RuleOverrideScope,
    GameSystemCreate,
    GameSystemUpdate,
    GameSystemResponse,
    GameSystemListResponse,
    CoreMechanic,
    GameRule,
)


# =============================================================================
# Enum contract tests
# =============================================================================


@pytest.mark.unit
class TestGameSystemEnumsContract:
    """Contract tests for game system enums."""

    def test_core_mechanic_type_values(self):
        """CoreMechanicType has expected values."""
        assert CoreMechanicType.D20 == "d20"
        assert CoreMechanicType.DICE_POOL == "dice_pool"
        assert CoreMechanicType.PERCENTILE == "percentile"
        assert CoreMechanicType.CARD == "card"
        assert CoreMechanicType.NARRATIVE == "narrative"
        assert len(CoreMechanicType) == 5

    def test_success_type_values(self):
        """SuccessType has expected values."""
        assert SuccessType.MEET_OR_BEAT == "meet_or_beat"
        assert SuccessType.COUNT_SUCCESSES == "count_successes"
        assert SuccessType.HIGHEST_WINS == "highest_wins"
        assert SuccessType.DEGREES_OF_SUCCESS == "degrees_of_success"
        assert len(SuccessType) == 4

    def test_game_rule_type_values(self):
        """GameRuleType has expected values."""
        assert GameRuleType.CORE == "core"
        assert GameRuleType.COMBAT == "combat"
        assert GameRuleType.SOCIAL == "social"
        assert GameRuleType.POWER == "power"
        assert GameRuleType.LORE == "lore"
        assert GameRuleType.MECHANIC == "mechanic"  # used by builtin seed
        assert GameRuleType.CUSTOM == "custom"
        assert GameRuleType.CONDITION == "condition"  # added in Phase 8B
        assert len(GameRuleType) == 8

    def test_ability_score_method_values(self):
        """AbilityScoreMethod has expected values."""
        assert AbilityScoreMethod.RANDOM_ROLL == "random_roll"
        assert AbilityScoreMethod.POINT_BUY == "point_buy"
        assert AbilityScoreMethod.STANDARD_ARRAY == "standard_array"
        assert AbilityScoreMethod.FIXED == "fixed"
        assert AbilityScoreMethod.FREE_ASSIGN == "free_assign"
        assert len(AbilityScoreMethod) == 5

    def test_creation_step_type_values(self):
        """CreationStepType has expected values."""
        assert CreationStepType.CHOOSE_ARCHETYPE == "choose_archetype"
        assert CreationStepType.GENERATE_STATS == "generate_stats"
        assert CreationStepType.ASSIGN_STATS == "assign_stats"
        assert CreationStepType.CHOOSE_BACKGROUND == "choose_background"
        assert CreationStepType.CHOOSE_POWERS == "choose_powers"
        assert CreationStepType.CHOOSE_EQUIPMENT == "choose_equipment"
        assert CreationStepType.CALCULATE_DERIVED == "calculate_derived"
        assert CreationStepType.WRITE_BACKSTORY == "write_backstory"
        assert CreationStepType.CUSTOM == "custom"
        # Builtin-seed steps added in T-028 (seed/enum drift fix)
        assert CreationStepType.CHOOSE_SPECIES == "choose_species"
        assert CreationStepType.CHOOSE_CLASS == "choose_class"
        assert CreationStepType.GENERATE_ATTRIBUTES == "generate_attributes"
        assert CreationStepType.CHOOSE_SKILLS == "choose_skills"
        assert len(CreationStepType) == 17

    def test_npc_tier_values(self):
        """NPCTier has expected values."""
        assert NPCTier.MINION == "minion"
        assert NPCTier.STANDARD == "standard"
        assert NPCTier.ELITE == "elite"
        assert NPCTier.BOSS == "boss"
        assert NPCTier.BRUTE == "brute"
        assert NPCTier.VILLAIN == "villain"
        assert len(NPCTier) == 6

    def test_rule_override_scope_values(self):
        """RuleOverrideScope has expected values."""
        assert RuleOverrideScope.STORY == "story"
        assert RuleOverrideScope.SCENE == "scene"
        assert len(RuleOverrideScope) == 2


# =============================================================================
# GameSystemCreate contract tests
# =============================================================================


@pytest.mark.unit
class TestGameSystemCreateContract:
    """Contract tests for GameSystemCreate schema."""

    def test_create_minimal(self):
        """GameSystemCreate with only required fields is valid."""
        params = GameSystemCreate(
            name="D&D 5e",
            description="A fantasy RPG system.",
            core_mechanic=CoreMechanic(
                type=CoreMechanicType.D20,
                formula="1d20+modifier",
                success_type=SuccessType.MEET_OR_BEAT,
            ),
        )
        assert params.name == "D&D 5e"
        assert params.core_mechanic.type == CoreMechanicType.D20
        assert params.description == "A fantasy RPG system."
        assert params.version is None
        assert params.is_builtin is False

    def test_create_with_description(self):
        """GameSystemCreate can include description."""
        params = GameSystemCreate(
            name="Pathfinder 2e",
            description="A fantasy RPG system.",
            core_mechanic=CoreMechanic(
                type=CoreMechanicType.D20,
                formula="1d20+modifier",
                success_type=SuccessType.DEGREES_OF_SUCCESS,
            ),
            version="2.0",
        )
        assert params.description == "A fantasy RPG system."
        assert params.version == "2.0"

    def test_create_empty_name_fails(self):
        """GameSystemCreate with empty name raises ValidationError."""
        with pytest.raises(Exception):
            GameSystemCreate(
                name="",
                core_mechanic=CoreMechanic(
                    type=CoreMechanicType.D20,
                    formula="1d20",
                    success_type=SuccessType.MEET_OR_BEAT,
                ),
            )

    def test_create_all_core_mechanic_types(self):
        """All CoreMechanicType values are valid."""
        for cm in CoreMechanicType:
            params = GameSystemCreate(
                name=f"Test {cm.value}",
                description=f"Test system for {cm.value}",
                core_mechanic=CoreMechanic(
                    type=cm,
                    formula="1d20",
                    success_type=SuccessType.MEET_OR_BEAT,
                ),
            )
            assert params.core_mechanic.type == cm


# =============================================================================
# GameSystemUpdate contract tests
# =============================================================================


@pytest.mark.unit
class TestGameSystemUpdateContract:
    """Contract tests for GameSystemUpdate schema."""

    def test_update_all_none(self):
        """GameSystemUpdate with all fields None is valid (no-op update)."""
        update = GameSystemUpdate()
        assert update.name is None
        assert update.description is None
        assert update.version is None
        assert update.core_mechanic is None

    def test_update_name_only(self):
        """GameSystemUpdate can update just the name."""
        update = GameSystemUpdate(name="Updated System")
        assert update.name == "Updated System"

    def test_update_name_valid(self):
        """GameSystemUpdate can update name to a valid string."""
        update = GameSystemUpdate(name="Updated System")
        assert update.name == "Updated System"


# =============================================================================
# CoreMechanic contract tests
# =============================================================================


@pytest.mark.unit
class TestCoreMechanicContract:
    """Contract tests for CoreMechanic schema."""

    def test_core_mechanic_minimal(self):
        """CoreMechanic with required fields is valid."""
        cm = CoreMechanic(
            type=CoreMechanicType.D20,
            formula="1d20+modifier",
            success_type=SuccessType.MEET_OR_BEAT,
        )
        assert cm.type == CoreMechanicType.D20
        assert cm.formula == "1d20+modifier"
        assert cm.success_type == SuccessType.MEET_OR_BEAT
        assert cm.success_threshold is None

    def test_core_mechanic_with_threshold(self):
        """CoreMechanic can specify success threshold."""
        cm = CoreMechanic(
            type=CoreMechanicType.D20,
            formula="1d20+modifier",
            success_type=SuccessType.MEET_OR_BEAT,
            success_threshold=15,
        )
        assert cm.success_threshold == 15


# =============================================================================
# GameRule contract tests
# =============================================================================


@pytest.mark.unit
class TestGameRuleContract:
    """Contract tests for GameRule schema."""

    def test_game_rule_minimal(self):
        """GameRule with required fields is valid."""
        rule = GameRule(
            name="Critical Hit",
            rule_type=GameRuleType.COMBAT,
            description="Roll a natural 20 to score a critical hit.",
        )
        assert rule.name == "Critical Hit"
        assert rule.rule_type == GameRuleType.COMBAT
        assert rule.formula is None
        assert rule.tags == []

    def test_game_rule_with_formula(self):
        """GameRule can include a formula."""
        rule = GameRule(
            name="Advantage",
            rule_type=GameRuleType.CORE,
            description="Roll twice, take the higher result.",
            formula="max(2d20)",
            tags=["advantage", "core"],
        )
        assert rule.formula == "max(2d20)"
        assert "advantage" in rule.tags


# =============================================================================
# GameSystemResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestGameSystemResponseContract:
    """Contract tests for GameSystemResponse schema."""

    def test_response_minimal(self):
        """GameSystemResponse with required fields is valid."""
        now = datetime.now(timezone.utc)
        resp = GameSystemResponse(
            id=uuid4(),
            name="D&D 5e",
            description="",
            version="1.0",
            core_mechanic=CoreMechanic(
                type=CoreMechanicType.D20,
                formula="1d20+modifier",
                success_type=SuccessType.MEET_OR_BEAT,
            ),
            attributes=[],
            skills=[],
            resources=[],
            custom_dice={},
            is_builtin=False,
            created_at=now,
            updated_at=now,
        )
        assert resp.name == "D&D 5e"
        assert resp.is_builtin is False


# =============================================================================
# GameSystemListResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestGameSystemListResponseContract:
    """Contract tests for GameSystemListResponse schema."""

    def test_list_response_empty(self):
        """GameSystemListResponse with empty list is valid."""
        resp = GameSystemListResponse(
            systems=[],
            total=0,
            limit=50,
            offset=0,
        )
        assert resp.systems == []
        assert resp.total == 0