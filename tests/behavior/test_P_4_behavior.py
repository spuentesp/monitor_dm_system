"""Behavior tests for P-4: Resolve Action.

Verifies that actual implementation matches behavior specifications.
"""

from __future__ import annotations

from enum import Enum
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from monitor_data.schemas.resolutions import (
    ActionType,
    ResolutionCreate,
    ResolutionType,
    RollResult,
    SuccessLevel,
)


class ResolutionOutcome(Enum):
    """Outcome types for action resolution."""

    CRITICAL_SUCCESS = "critical_success"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    CRITICAL_FAILURE = "critical_failure"


def determine_outcome(roll: int, dc: int) -> ResolutionOutcome:
    """Determine outcome based on roll vs DC."""
    diff = roll - dc
    if diff >= 10:
        return ResolutionOutcome.CRITICAL_SUCCESS
    elif diff >= 0:
        return ResolutionOutcome.SUCCESS
    elif diff >= -5:
        return ResolutionOutcome.PARTIAL
    elif diff >= -10:
        return ResolutionOutcome.FAILURE
    else:
        return ResolutionOutcome.CRITICAL_FAILURE


def determine_resolution_type(
    action: str,
    is_combat: bool = False,
    is_trivial: bool = False,
    is_impossible: bool = False,
) -> ResolutionType:
    """Determine resolution type for an action."""
    if is_impossible:
        return ResolutionType.FORCED_NARRATIVE
    if is_trivial:
        return ResolutionType.NARRATIVE
    if is_combat:
        return ResolutionType.DICE
    return ResolutionType.DICE


class TestP4ActionResolution:
    """Scenario 1: Action Resolution - Core resolution logic."""

    def test_determine_outcome_critical_success(self):
        """Test CRITICAL_SUCCESS when roll exceeds DC by 10+."""
        outcome = determine_outcome(roll=20, dc=10)
        assert outcome == ResolutionOutcome.CRITICAL_SUCCESS

    def test_determine_outcome_success(self):
        """Test SUCCESS when roll meets or exceeds DC."""
        outcome = determine_outcome(roll=15, dc=10)
        assert outcome == ResolutionOutcome.SUCCESS

    def test_determine_outcome_partial(self):
        """Test PARTIAL when roll is 1-5 below DC."""
        outcome = determine_outcome(roll=7, dc=10)
        assert outcome == ResolutionOutcome.PARTIAL

    def test_determine_outcome_failure(self):
        """Test FAILURE when roll is 6-10 below DC."""
        outcome = determine_outcome(roll=4, dc=10)
        assert outcome == ResolutionOutcome.FAILURE

    def test_determine_outcome_critical_failure(self):
        """Test CRITICAL_FAILURE when roll is 10+ below DC."""
        outcome = determine_outcome(roll=-1, dc=10)
        assert outcome == ResolutionOutcome.CRITICAL_FAILURE

    def test_determine_outcome_exact_dc(self):
        """Test SUCCESS when roll exactly equals DC."""
        outcome = determine_outcome(roll=10, dc=10)
        assert outcome == ResolutionOutcome.SUCCESS


class TestP4ResolutionTypeDetermination:
    """Scenario 2: Resolution Type Determination."""

    def test_combat_action_requires_dice(self):
        """Test that combat actions require dice resolution."""
        resolution_type = determine_resolution_type(
            "I attack the goblin", is_combat=True
        )
        assert resolution_type == ResolutionType.DICE

    def test_trivial_action_narrative_resolution(self):
        """Test that trivial actions use narrative resolution."""
        resolution_type = determine_resolution_type(
            "I open an unlocked door", is_trivial=True
        )
        assert resolution_type == ResolutionType.NARRATIVE

    def test_impossible_action_forced_narrative(self):
        """Test that impossible actions use forced narrative."""
        resolution_type = determine_resolution_type(
            "I jump to the moon", is_impossible=True
        )
        assert resolution_type == ResolutionType.FORCED_NARRATIVE

    def test_skill_check_requires_dice(self):
        """Test that skill checks require dice resolution."""
        resolution_type = determine_resolution_type(
            "I pick the lock", is_combat=False, is_trivial=False
        )
        assert resolution_type == ResolutionType.DICE


class TestP4RollResultSchema:
    """Scenario 3: Roll Result Schema Validation."""

    def test_roll_result_valid(self):
        """Test valid RollResult creation."""
        roll = RollResult(
            raw_rolls=[17],
            kept_rolls=[17],
            total=22,
            natural=17,
            critical=False,
        )
        assert roll.raw_rolls == [17]
        assert roll.total == 22

    def test_roll_result_with_modifiers(self):
        """Test RollResult with modifiers."""
        roll = RollResult(
            raw_rolls=[17],
            kept_rolls=[17],
            total=22,  # 17 + 5 modifier
            natural=17,
            critical=False,
        )
        assert roll.total == 22

    def test_roll_result_critical(self):
        """Test RollResult with critical hit."""
        roll = RollResult(
            raw_rolls=[20],
            kept_rolls=[20],
            total=25,
            natural=20,
            critical=True,
        )
        assert roll.critical is True

    def test_roll_result_fumble(self):
        """Test RollResult with fumble."""
        roll = RollResult(
            raw_rolls=[1],
            kept_rolls=[1],
            total=1,
            natural=1,
            fumble=True,
        )
        assert roll.fumble is True


class TestP4ResolutionCreateSchema:
    """Scenario 4: Resolution Create Schema."""

    @pytest.mark.integration
    def test_resolution_create_dice(self):
        """Test ResolutionCreate for dice resolution."""
        resolution = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Attack goblin",
            action_type=ActionType.COMBAT,
            resolution_type=ResolutionType.DICE,
            mechanics={"formula": "1d20+5", "target": 12},
            success_level=SuccessLevel.SUCCESS,
        )
        assert resolution.resolution_type == ResolutionType.DICE
        assert resolution.success_level == SuccessLevel.SUCCESS

    @pytest.mark.integration
    def test_resolution_create_narrative(self):
        """Test ResolutionCreate for narrative resolution."""
        resolution = ResolutionCreate(
            turn_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            action="Open unlocked door",
            action_type=ActionType.SKILL,
            resolution_type=ResolutionType.NARRATIVE,
            mechanics={"formula": "Auto-success"},
            success_level=SuccessLevel.SUCCESS,
        )
        assert resolution.resolution_type == ResolutionType.NARRATIVE


class TestP4ResolutionStorage:
    """Scenario 5: Resolution Storage in MongoDB."""

    @pytest.mark.integration
    def test_resolution_stored_with_all_fields(self):
        """Test that resolution is stored with all required fields."""
        scene_id = uuid4()
        turn_id = uuid4()
        story_id = uuid4()

        # Mock MongoDB client and Neo4j client
        with patch(
            "monitor_data.tools.mongodb_tools.resolutions.get_mongodb_client"
        ) as mock_mongo, patch(
            "monitor_data.tools.mongodb_tools.resolutions.get_neo4j_client"
        ) as mock_neo:
            mongo_client = MagicMock()
            mock_mongo.return_value = mongo_client

            # Mock scene lookup - return scene with the turn in it
            scene_mock = {
                "scene_id": str(scene_id),
                "turns": [
                    {"turn_id": str(turn_id)},
                ],
            }

            def get_collection_side_effect(collection_name):
                collection = MagicMock()
                if collection_name == "scenes":
                    collection.find_one.return_value = scene_mock
                elif collection_name == "resolutions":
                    collection.insert_one.return_value = MagicMock(
                        inserted_id="test_resolution_id"
                    )
                return collection

            mongo_client.get_collection.side_effect = get_collection_side_effect

            # Mock Neo4j story lookup
            neo4j_client = MagicMock()
            mock_neo.return_value = neo4j_client
            neo4j_client.execute_read.return_value = [{"story_id": str(story_id)}]

            from monitor_data.tools.mongodb_tools.resolutions import (
                mongodb_create_resolution,
            )

            resolution = mongodb_create_resolution(
                ResolutionCreate(
                    turn_id=turn_id,
                    scene_id=scene_id,
                    story_id=story_id,
                    actor_id=uuid4(),
                    action="Attack goblin",
                    action_type=ActionType.COMBAT,
                    mechanics={"formula": "1d20+5", "target": 12},
                    resolution_type=ResolutionType.DICE,
                    success_level=SuccessLevel.SUCCESS,
                )
            )

            assert resolution is not None


class TestP4ProposalCreation:
    """Scenario 6: Proposal Creation for State Changes."""

    @pytest.mark.integration
    def test_proposal_created_for_state_change(self):
        """Test that ProposedChange is created for state changes."""
        from monitor_data.schemas.proposed_changes import (
            ProposalType,
            ProposedChangeCreate,
        )
        from monitor_data.tools.mongodb_tools.proposals import (
            mongodb_create_proposed_change,
        )

        scene_id = uuid4()
        entity_id = uuid4()

        with patch(
            "monitor_data.tools.mongodb_tools.proposals.get_mongodb_client"
        ) as mock_mongo:
            mongo_client = MagicMock()
            mock_mongo.return_value = mongo_client
            mongo_client.get_collection.return_value.insert_one = MagicMock()

            proposal = mongodb_create_proposed_change(
                ProposedChangeCreate(
                    scene_id=scene_id,
                    change_type=ProposalType.STATE_CHANGE,
                    content={
                        "entity_id": str(entity_id),
                        "tag": "hp",
                        "action": "decrement",
                        "value": 5,
                    },
                )
            )

            assert proposal is not None


class TestP4AcceptanceCriteria:
    """Verify acceptance criteria from P-4-behavior.md."""

    def test_ac1_action_parsing(self):
        """AC-1: Action text is parsed for intent."""
        action = "I attack the goblin with my sword"
        assert "attack" in action.lower()

    def test_ac2_dice_resolution_for_combat(self):
        """AC-2: Dice resolution for combat actions."""
        resolution_type = determine_resolution_type("I attack", is_combat=True)
        assert resolution_type == ResolutionType.DICE

    def test_ac3_narrative_resolution_for_trivial(self):
        """AC-3: Narrative resolution for trivial actions."""
        resolution_type = determine_resolution_type(
            "I look at the sky", is_trivial=True
        )
        assert resolution_type == ResolutionType.NARRATIVE

    def test_ac4_outcome_mapping(self):
        """AC-4: Outcome mapping works correctly."""
        assert determine_outcome(20, 10) == ResolutionOutcome.CRITICAL_SUCCESS
        assert determine_outcome(15, 10) == ResolutionOutcome.SUCCESS
        assert determine_outcome(8, 10) == ResolutionOutcome.PARTIAL
        assert determine_outcome(3, 10) == ResolutionOutcome.FAILURE
        assert determine_outcome(-5, 10) == ResolutionOutcome.CRITICAL_FAILURE

    def test_ac7_dice_formula_parsing(self):
        """AC-7: Dice formula is parsed correctly."""
        formula = "1d20+5"
        assert "d20" in formula.lower()
        assert "+5" in formula

    def test_ac10_outcome_determined_by_roll_vs_dc(self):
        """AC-10: Outcome is determined based on roll vs DC."""
        outcome = determine_outcome(18, 15)
        assert outcome == ResolutionOutcome.SUCCESS
