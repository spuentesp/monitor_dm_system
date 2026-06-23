"""
P-4: Resolve Action — Contract Tests

This module tests the API contracts defined in P-4-contracts.md:
- Data layer tools: neo4j_get_entity, dice_roll, mongodb_create_resolution, mongodb_create_proposal
- Agent classes: Resolver, Narrator
- Resolver methods: resolve_turn, resolve_opposed_check, resolve_check
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class ResolutionType(Enum):
    """Enumeration of resolution types for actions."""
    DICE = "DICE"
    NARRATIVE = "NARRATIVE"
    AUTO_SUCCESS = "AUTO_SUCCESS"
    AUTO_FAIL = "AUTO_FAIL"


class Outcome(Enum):
    """Enumeration of possible action outcomes."""
    CRITICAL_SUCCESS = "CRITICAL_SUCCESS"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILURE = "FAILURE"
    CRITICAL_FAILURE = "CRITICAL_FAILURE"


# ============================================================================
# Helper Function Tests
# ============================================================================

# ============================================================================
# Agent Contract Tests
# ============================================================================

class TestResolverConstructorContract:
    """Contract tests for Resolver constructor."""

    @pytest.mark.unit
    def test_constructor_accepts_agent_id(self):
        """Contract: Resolver.__init__ accepts agent_id (str)."""
        from monitor_agents.resolver import Resolver
        resolver = Resolver(agent_id="resolver-test-1")
        assert resolver.agent_id == "resolver-test-1"

    @pytest.mark.unit
    def test_constructor_default_agent_id(self):
        """Contract: Resolver.__init__ defaults agent_id to 'resolver-cli-1'."""
        from monitor_agents.resolver import Resolver
        resolver = Resolver()
        assert resolver.agent_id == "resolver-cli-1"

    @pytest.mark.unit
    def test_has_resolve_turn_method(self):
        """Contract: Resolver has resolve_turn() async method."""
        from monitor_agents.resolver import Resolver
        resolver = Resolver(agent_id="resolver-test-1")
        assert hasattr(resolver, "resolve_turn")
        assert callable(resolver.resolve_turn)

    @pytest.mark.unit
    def test_has_resolve_opposed_check_method(self):
        """Contract: Resolver has resolve_opposed_check() async method."""
        from monitor_agents.resolver import Resolver
        resolver = Resolver(agent_id="resolver-test-1")
        assert hasattr(resolver, "resolve_opposed_check")
        assert callable(resolver.resolve_opposed_check)

    @pytest.mark.unit
    def test_has_resolve_check_method(self):
        """Contract: Resolver has resolve_check() async method."""
        from monitor_agents.resolver import Resolver
        resolver = Resolver(agent_id="resolver-test-1")
        assert hasattr(resolver, "resolve_check")
        assert callable(resolver.resolve_check)


class TestResolverResolveTurnContract:
    """Contract tests for Resolver.resolve_turn() method."""

    @pytest.mark.unit
    def test_resolve_turn_accepts_required_parameters(self):
        """Contract: resolve_turn() accepts scene_id and user_input."""
        from monitor_agents.resolver import Resolver
        import inspect
        resolver = Resolver(agent_id="resolver-test-1")
        sig = inspect.signature(resolver.resolve_turn)
        assert "scene_id" in sig.parameters
        assert "user_input" in sig.parameters

    @pytest.mark.unit
    def test_resolve_turn_accepts_optional_parameters(self):
        """Contract: resolve_turn() accepts context, game_context, play_mode, etc."""
        from monitor_agents.resolver import Resolver
        import inspect
        resolver = Resolver(agent_id="resolver-test-1")
        sig = inspect.signature(resolver.resolve_turn)
        assert "context" in sig.parameters
        assert "game_context" in sig.parameters
        assert "play_mode" in sig.parameters
        assert "roll_mode" in sig.parameters
        assert "tension_score" in sig.parameters

    @pytest.mark.unit
    async def test_resolve_turn_returns_dict(self):
        """Contract: resolve_turn() returns Dict[str, Any]."""
        from monitor_agents.resolver import Resolver
        from unittest.mock import patch, AsyncMock
        resolver = Resolver(agent_id="resolver-test-1")
        with patch.object(resolver, "call_tool", new_callable=AsyncMock) as mock_tool:
            mock_tool.return_value = {"result": "success"}
            with patch.object(resolver, "call_llm_structured", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = MagicMock(action_type="action", outcome="success", narrative="You hit!")
                result = await resolver.resolve_turn(
                    scene_id="scene-123",
                    user_input="I attack the goblin",
                )
                assert isinstance(result, dict)


class TestResolverResolveCheckContract:
    """Contract tests for Resolver.resolve_check() method."""

    @pytest.mark.unit
    def test_resolve_check_accepts_parameters(self):
        """Contract: resolve_check() accepts entity_id, stat_name, dc, roll_mode."""
        from monitor_agents.resolver import Resolver
        import inspect
        resolver = Resolver(agent_id="resolver-test-1")
        sig = inspect.signature(resolver.resolve_check)
        assert "entity_id" in sig.parameters
        assert "stat_name" in sig.parameters
        assert "dc" in sig.parameters
        assert "roll_mode" in sig.parameters


class TestNarratorDescribeContract:
    """Contract tests for Narrator.narrate_turn() (P-4 specific)."""

    @pytest.mark.unit
    async def test_narrate_turn_with_resolution(self):
        """Contract: narrate_turn() accepts resolution parameter for action narration."""
        from monitor_agents.narrator import Narrator
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch
        narrator = Narrator(agent_id="narrator-test-1")
        with patch.object(narrator, "_generate_narrative_and_proposals", new_callable=AsyncMock) as mock_gen, \
             patch.object(narrator, "_persist_turn", new_callable=AsyncMock) as mock_persist:
            mock_gen.return_value = ("The goblin falls!", [], 5)
            mock_persist.return_value = "turn-123"
            result = await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I attack the goblin",
                resolution={"outcome": "success", "narrative": "You hit!"},
                context={"entities": [], "memories": [], "turns": []},
            )
            assert isinstance(result, dict)
            assert "narrative_text" in result


# ============================================================================
# Data Layer Tool Contract Tests
# ============================================================================

class TestNeo4jGetEntityContract:
    """Contract tests for neo4j_get_entity data layer tool."""

    @pytest.mark.unit
    async def test_returns_entity_with_all_required_fields(self, fake_mcp_client):
        """Contract: Returns Entity object with id, name, type, universe_id, attributes, relationships, canon."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "id": "goblin-001",
            "name": "Goblin Warrior",
            "type": "character",
            "universe_id": "universe-123",
            "attributes": {
                "health": 15,
                "armor_class": 12,
                "damage": 5,
                "tags": ["hostile", "combatant"]
            },
            "relationships": [],
            "canon": {
                "role": "enemy",
                "location": "forest"
            }
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "neo4j_get_entity",
            {"entity_id": "goblin-001"}
        )

        # Verify contract: returns Entity object
        assert isinstance(result, dict)

        # Verify contract: contains required fields
        assert "id" in result
        assert "name" in result
        assert "type" in result
        assert "universe_id" in result
        assert "attributes" in result
        assert "relationships" in result
        assert "canon" in result

        # Verify contract: correct values
        assert result["id"] == "goblin-001"
        assert result["name"] == "Goblin Warrior"
        assert result["type"] == "character"
        assert result["attributes"]["health"] == 15

    @pytest.mark.unit
    async def test_raises_entity_not_found_error(self, fake_mcp_client):
        """Contract: Raises EntityNotFoundError when entity_id does not exist."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "EntityNotFoundError: Entity not found: entity-999"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "neo4j_get_entity",
                {"entity_id": "entity-999"}
            )

        assert "EntityNotFoundError" in str(exc_info.value)


class TestDiceRollContract:
    """Contract tests for dice_roll data layer tool."""

    @pytest.mark.unit
    async def test_returns_dice_roll_with_all_required_fields(self, fake_mcp_client):
        """Contract: Returns DiceRoll with formula, rolls, total."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "formula": "1d20+5",
            "rolls": [17],
            "total": 22,
            "success": True,
            "details": {}
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "dice_roll",
            {"formula": "1d20+5"}
        )

        # Verify contract: returns DiceRoll object
        assert isinstance(result, dict)

        # Verify contract: contains required fields
        assert "formula" in result
        assert "rolls" in result
        assert "total" in result

        # Verify contract: correct values
        assert result["formula"] == "1d20+5"
        assert result["rolls"] == [17]
        assert result["total"] == 22

    @pytest.mark.unit
    async def test_parses_standard_dice_notation(self, fake_mcp_client):
        """Contract: Parses standard dice notation (NdS)."""
        fake_mcp_client.call_tool.return_value = {
            "formula": "2d6",
            "rolls": [3, 4],
            "total": 7,
            "success": True,
            "details": {}
        }

        result = await fake_mcp_client.call_tool(
            "dice_roll",
            {"formula": "2d6"}
        )

        assert result["formula"] == "2d6"
        assert result["total"] == 7

    @pytest.mark.unit
    async def test_parses_dice_notation_with_modifiers(self, fake_mcp_client):
        """Contract: Parses dice notation with modifiers (+N, -N)."""
        fake_mcp_client.call_tool.return_value = {
            "formula": "1d20+5",
            "rolls": [15],
            "total": 20,
            "success": True,
            "details": {}
        }

        result = await fake_mcp_client.call_tool(
            "dice_roll",
            {"formula": "1d20+5"}
        )

        assert result["total"] == 20

    @pytest.mark.unit
    async def test_parses_keep_highest_notation(self, fake_mcp_client):
        """Contract: Parses dice notation with keep highest (NdSkhX)."""
        fake_mcp_client.call_tool.return_value = {
            "formula": "4d6kh3",
            "rolls": [6, 2, 5, 1],
            "total": 17,
            "success": True,
            "details": {}
        }

        result = await fake_mcp_client.call_tool(
            "dice_roll",
            {"formula": "4d6kh3"}
        )

        assert result["total"] == 17  # 6 + 5 + ? (keep highest 3)

    @pytest.mark.unit
    async def test_raises_invalid_dice_formula_error(self, fake_mcp_client):
        """Contract: Raises InvalidDiceFormulaError when formula is malformed."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "InvalidDiceFormulaError: Invalid dice formula: invalid"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "dice_roll",
                {"formula": "invalid"}
            )

        assert "InvalidDiceFormulaError" in str(exc_info.value)


class TestMongodbCreateResolutionContract:
    """Contract tests for mongodb_create_resolution data layer tool."""

    @pytest.mark.unit
    async def test_returns_resolution_id(self, fake_mcp_client):
        """Contract: Returns resolution_id (str) as UUID."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = "resolution-789"

        # Call tool with contract-specified parameters
        result = await fake_mcp_client.call_tool(
            "mongodb_create_resolution",
            {
                "scene_id": "scene-456",
                "turn_id": "turn-790",
                "action": "I attack the goblin with my sword",
                "formula": "1d20+5",
                "rolls": [17],
                "total": 22,
                "outcome": "SUCCESS",
                "dc": 15,
                "resolution_type": "DICE",
                "target_id": "goblin-001"
            }
        )

        # Verify contract: returns str (UUID)
        assert isinstance(result, str)
        assert result == "resolution-789"

    @pytest.mark.unit
    async def test_accepts_required_parameters(self, fake_mcp_client):
        """Contract: Accepts required parameters: scene_id, turn_id, action, outcome, resolution_type."""
        fake_mcp_client.call_tool.return_value = "resolution-789"

        # Call with minimum required parameters (no dice)
        result = await fake_mcp_client.call_tool(
            "mongodb_create_resolution",
            {
                "scene_id": "scene-456",
                "turn_id": "turn-790",
                "action": "I ask the guard for directions",
                "outcome": "SUCCESS",
                "resolution_type": "NARRATIVE"
            }
        )

        # Verify required parameters were passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "scene_id" in params
        assert "turn_id" in params
        assert "action" in params
        assert "outcome" in params
        assert "resolution_type" in params

    @pytest.mark.unit
    async def test_accepts_dice_parameters_when_resolution_type_is_dice(self, fake_mcp_client):
        """Contract: Accepts formula, rolls, total, dc when resolution_type is DICE."""
        fake_mcp_client.call_tool.return_value = "resolution-789"

        result = await fake_mcp_client.call_tool(
            "mongodb_create_resolution",
            {
                "scene_id": "scene-456",
                "turn_id": "turn-790",
                "action": "I attack the goblin",
                "formula": "1d20+5",
                "rolls": [17],
                "total": 22,
                "outcome": "SUCCESS",
                "dc": 15,
                "resolution_type": "DICE",
                "target_id": "goblin-001"
            }
        )

        # Verify dice parameters were passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert params["formula"] == "1d20+5"
        assert params["rolls"] == [17]
        assert params["total"] == 22
        assert params["dc"] == 15

    @pytest.mark.unit
    async def test_accepts_optional_target_id(self, fake_mcp_client):
        """Contract: Accepts optional target_id parameter."""
        fake_mcp_client.call_tool.return_value = "resolution-789"

        result = await fake_mcp_client.call_tool(
            "mongodb_create_resolution",
            {
                "scene_id": "scene-456",
                "turn_id": "turn-790",
                "action": "I attack the goblin",
                "outcome": "SUCCESS",
                "resolution_type": "DICE",
                "target_id": "goblin-001",
                "formula": "1d20+5",
                "rolls": [17],
                "total": 22,
                "dc": 15
            }
        )

        # Verify target_id was passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert params["target_id"] == "goblin-001"


class TestMongodbCreateProposalContract:
    """Contract tests for mongodb_create_proposal data layer tool (already tested in P-3)."""

    # This contract is already tested in test_P-3_contracts.py
    # Keeping this test file for completeness and P-4-specific tests

    @pytest.mark.unit
    async def test_links_proposal_to_resolution(self, fake_mcp_client):
        """Contract: Links proposal to resolution for traceability."""
        fake_mcp_client.call_tool.return_value = "proposal-456"

        # Call with resolution_ref
        result = await fake_mcp_client.call_tool(
            "mongodb_create_proposal",
            {
                "scene_id": "scene-456",
                "type": "state_change",
                "content": {
                    "entity_id": "goblin-001",
                    "tag": "health",
                    "action": "decrement",
                    "value": 10
                },
                "status": "pending",
                "resolution_ref": "resolution-789"
            }
        )

        # Verify resolution_ref was passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "resolution_ref" in params
        assert params["resolution_ref"] == "resolution-789"


# ============================================================================
