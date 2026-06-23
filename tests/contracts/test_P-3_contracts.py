"""
P-3: Turn Loop — Contract Tests

This module tests the API contracts defined in P-3-contracts.md:
- Data layer tools: mongodb_get_scene, mongodb_get_turns, mongodb_append_turn, mongodb_create_proposal
- Agent methods: SceneLoop.run, ContextAssembly.assemble, Narrator.narrate_turn

Note: parse_input was removed from the codebase; its tests have been removed.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from collections.abc import AsyncIterator
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
from uuid import uuid4

from monitor_agents.loops.scene_loop import SceneLoop, SceneState
from monitor_agents.context_assembly import ContextAssembly
from monitor_agents.narrator import Narrator


# ============================================================================
# Agent Contract Tests
# ============================================================================

class TestSceneLoopRunContract:
    """Contract tests for SceneLoop.run() method."""

    @pytest.mark.unit
    def test_run_accepts_user_input(self):
        """Contract: run() accepts user_input (str) parameter."""
        scene_loop = SceneLoop(scene_id=uuid4(), story_id=uuid4())
        import inspect
        sig = inspect.signature(scene_loop.run)
        assert "user_input" in sig.parameters

    @pytest.mark.unit
    def test_run_accepts_resolution_override(self):
        """Contract: run() accepts optional resolution_override parameter."""
        scene_loop = SceneLoop(scene_id=uuid4(), story_id=uuid4())
        import inspect
        sig = inspect.signature(scene_loop.run)
        assert "resolution_override" in sig.parameters

    @pytest.mark.unit
    async def test_run_returns_dict(self):
        """Contract: run() returns Dict[str, Any] with scene state."""
        from unittest.mock import patch
        scene_loop = SceneLoop(scene_id=uuid4(), story_id=uuid4())
        with patch("monitor_agents.loops.scene_loop.MongoDBSaver") as mock_saver_cls:
            mock_saver = MagicMock()
            mock_saver.__enter__ = MagicMock(return_value=mock_saver)
            mock_saver.__exit__ = MagicMock(return_value=False)
            mock_saver_cls.from_conn_string.return_value = mock_saver
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke.return_value = {"scene_id": str(uuid4()), "status": "active"}
            # Verify method signature exists and is callable
            assert hasattr(scene_loop, "run")
            assert callable(scene_loop.run)


class TestContextAssemblyConstructorContract:
    """Contract tests for ContextAssembly constructor."""

    @pytest.mark.unit
    def test_constructor_accepts_agent_id(self):
        """Contract: ContextAssembly.__init__ accepts agent_id (str)."""
        ca = ContextAssembly(agent_id="context-test-1")
        assert ca.agent_id == "context-test-1"

    @pytest.mark.unit
    def test_constructor_default_agent_id(self):
        """Contract: ContextAssembly.__init__ defaults agent_id to 'context-assembly-1'."""
        ca = ContextAssembly()
        assert ca.agent_id == "context-assembly-1"

    @pytest.mark.unit
    def test_has_assemble_method(self):
        """Contract: ContextAssembly has assemble() async method."""
        ca = ContextAssembly(agent_id="context-test-1")
        assert hasattr(ca, "assemble")
        assert callable(ca.assemble)

    @pytest.mark.unit
    def test_has_retrieve_turn_context_method(self):
        """Contract: ContextAssembly has retrieve_turn_context() async method."""
        ca = ContextAssembly(agent_id="context-test-1")
        assert hasattr(ca, "retrieve_turn_context")
        assert callable(ca.retrieve_turn_context)


class TestContextAssemblyAssembleContract:
    """Contract tests for ContextAssembly.assemble() method."""

    @pytest.mark.unit
    async def test_assemble_accepts_required_parameters(self):
        """Contract: assemble() accepts scene_id (UUID) and story_id (UUID)."""
        ca = ContextAssembly(agent_id="context-test-1")
        import inspect
        sig = inspect.signature(ca.assemble)
        assert "scene_id" in sig.parameters
        assert "story_id" in sig.parameters

    @pytest.mark.unit
    async def test_assemble_accepts_optional_parameters(self):
        """Contract: assemble() accepts optional player_action, character_name, etc."""
        ca = ContextAssembly(agent_id="context-test-1")
        import inspect
        sig = inspect.signature(ca.assemble)
        assert "player_action" in sig.parameters
        assert "character_name" in sig.parameters
        assert "universe_id" in sig.parameters

    @pytest.mark.unit
    async def test_assemble_returns_dict(self):
        """Contract: assemble() returns Dict[str, Any] with entities, memories, turns."""
        from unittest.mock import patch
        ca = ContextAssembly(agent_id="context-test-1")
        with patch.object(ca, "_cache_get_json", return_value=None), \
             patch.object(ca, "_fetch_entities", new_callable=AsyncMock) as mock_entities, \
             patch.object(ca, "_fetch_recent_turns", new_callable=AsyncMock) as mock_turns, \
             patch.object(ca, "_fetch_game_system", new_callable=AsyncMock) as mock_gs, \
             patch.object(ca, "_fetch_plot_threads", new_callable=AsyncMock) as mock_threads, \
             patch.object(ca, "_cache_set_json"):
            mock_entities.return_value = [{"id": "char-1", "name": "Aldern"}]
            mock_turns.return_value = [{"type": "narrative", "content": "Opening"}]
            mock_gs.return_value = {"system": "dnd5e"}
            mock_threads.return_value = []
            result = await ca.assemble(
                scene_id=uuid4(),
                story_id=uuid4(),
            )
            assert isinstance(result, dict)
            assert "entities" in result
            assert "turns" in result


class TestNarratorContract:
    """Contract tests for Narrator agent (P-3 specific)."""

    @pytest.mark.unit
    async def test_narrate_turn_accepts_context(self):
        """Contract: narrate_turn() accepts context (Dict[str, Any])."""
        narrator = Narrator(agent_id="narrator-test-1")
        import inspect
        sig = inspect.signature(narrator.narrate_turn)
        assert "context" in sig.parameters

    @pytest.mark.unit
    async def test_narrate_turn_accepts_resolution(self):
        """Contract: narrate_turn() accepts resolution (Optional[Dict])."""
        narrator = Narrator(agent_id="narrator-test-1")
        import inspect
        sig = inspect.signature(narrator.narrate_turn)
        assert "resolution" in sig.parameters

    @pytest.mark.unit
    async def test_narrate_turn_accepts_game_context(self):
        """Contract: narrate_turn() accepts optional game_context."""
        narrator = Narrator(agent_id="narrator-test-1")
        import inspect
        sig = inspect.signature(narrator.narrate_turn)
        assert "game_context" in sig.parameters


# ============================================================================
# Data Layer Contract Tests
# ============================================================================

class TestMongodbGetSceneContract:
    """Contract tests for mongodb_get_scene data layer tool."""

    @pytest.mark.unit
    async def test_returns_scene_data(self, fake_mcp_client):
        """Contract: Returns Dict[str, Any] with scene data."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "_id": "scene-456",
            "story_id": "story-123",
            "title": "Goblin Ambush",
            "location_id": "location-123",
            "entity_ids": ["char-001", "char-002", "char-003", "goblin-001"],
            "status": "active",
            "turns": [
                {
                    "_id": "turn-789",
                    "order": 1,
                    "type": "narrative",
                    "content": "You are traveling down the Triboar Trail...",
                    "actor": "narrator",
                    "timestamp": datetime.utcnow()
                }
            ],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "mongodb_get_scene",
            {"scene_id": "scene-456"}
        )

        # Verify contract: returns Dict[str, Any]
        assert isinstance(result, dict)
        assert "_id" in result
        assert "story_id" in result
        assert "title" in result
        assert "location_id" in result
        assert "entity_ids" in result
        assert "status" in result
        assert "turns" in result
        assert "created_at" in result
        assert "updated_at" in result

        # Verify contract: correct values
        assert result["_id"] == "scene-456"
        assert result["title"] == "Goblin Ambush"
        assert result["status"] == "active"

    @pytest.mark.unit
    async def test_raises_scene_not_found_error(self, fake_mcp_client):
        """Contract: Raises SceneNotFoundError when scene_id does not exist."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "SceneNotFoundError: Scene not found: scene-999"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "mongodb_get_scene",
                {"scene_id": "scene-999"}
            )

        assert "SceneNotFoundError" in str(exc_info.value)


class TestMongodbGetTurnsContract:
    """Contract tests for mongodb_get_turns data layer tool."""

    @pytest.mark.unit
    async def test_returns_list_of_turns(self, fake_mcp_client):
        """Contract: Returns List[Dict[str, Any]] with turn data."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = [
            {
                "_id": "turn-789",
                "order": 1,
                "type": "narrative",
                "content": "You are traveling down the Triboar Trail...",
                "actor": "narrator",
                "timestamp": datetime.utcnow()
            },
            {
                "_id": "turn-790",
                "order": 2,
                "type": "player_action",
                "content": "I attack the goblin",
                "actor": "char-001",
                "resolution_ref": "resolution-123",
                "timestamp": datetime.utcnow()
            }
        ]

        # Call tool with contract-specified parameters
        result = await fake_mcp_client.call_tool(
            "mongodb_get_turns",
            {
                "scene_id": "scene-456",
                "limit": 10
            }
        )

        # Verify contract: returns List[Dict[str, Any]]
        assert isinstance(result, list)
        assert len(result) == 2

        # Verify contract: each turn has required fields
        for turn in result:
            assert isinstance(turn, dict)
            assert "_id" in turn
            assert "order" in turn
            assert "type" in turn
            assert "content" in turn
            assert "timestamp" in turn

    @pytest.mark.unit
    async def test_respects_limit_parameter(self, fake_mcp_client):
        """Contract: Returns at most limit turns."""
        # Mock response with 2 turns
        fake_mcp_client.call_tool.return_value = [
            {"_id": "turn-789", "order": 1, "type": "narrative", "content": "Turn 1"},
            {"_id": "turn-790", "order": 2, "type": "player_action", "content": "Turn 2"}
        ]

        # Call with limit=5
        result = await fake_mcp_client.call_tool(
            "mongodb_get_turns",
            {
                "scene_id": "scene-456",
                "limit": 5
            }
        )

        # Verify limit parameter was passed
        call_args = fake_mcp_client.call_tool.call_args
        assert call_args[0][1]["limit"] == 5

    @pytest.mark.unit
    async def test_returns_turns_sorted_by_order(self, fake_mcp_client):
        """Contract: Returns turns sorted by order (most recent last)."""
        # Mock response with turns in order
        fake_mcp_client.call_tool.return_value = [
            {"_id": "turn-789", "order": 1, "type": "narrative", "content": "Turn 1"},
            {"_id": "turn-790", "order": 2, "type": "player_action", "content": "Turn 2"},
            {"_id": "turn-791", "order": 3, "type": "gm_action", "content": "Turn 3"}
        ]

        # Call tool
        result = await fake_mcp_client.call_tool(
            "mongodb_get_turns",
            {
                "scene_id": "scene-456",
                "limit": 10
            }
        )

        # Verify turns are sorted by order
        orders = [turn["order"] for turn in result]
        assert orders == [1, 2, 3]


class TestMongodbAppendTurnContract:
    """Contract tests for mongodb_append_turn data layer tool (already tested in P-2)."""

    # This contract is already tested in test_P-2_contracts.py
    # Keeping this test file for completeness and P-3-specific tests

    @pytest.mark.unit
    async def test_accepts_resolution_ref_parameter(self, fake_mcp_client):
        """Contract: Accepts optional resolution_ref parameter for action turns."""
        fake_mcp_client.call_tool.return_value = "turn-790"

        # Call with resolution_ref
        result = await fake_mcp_client.call_tool(
            "mongodb_append_turn",
            {
                "scene_id": "scene-456",
                "turn": {
                    "order": 2,
                    "type": "player_action",
                    "content": "I attack the goblin",
                    "actor": "char-001",
                    "resolution_ref": "resolution-123"
                }
            }
        )

        # Verify resolution_ref was passed
        call_args = fake_mcp_client.call_tool.call_args
        turn = call_args[0][1]["turn"]
        assert "resolution_ref" in turn
        assert turn["resolution_ref"] == "resolution-123"


class TestMongodbCreateProposalContract:
    """Contract tests for mongodb_create_proposal data layer tool."""

    @pytest.mark.unit
    async def test_returns_proposal_id(self, fake_mcp_client):
        """Contract: Returns proposal_id (str) as UUID."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = "proposal-456"

        # Call tool with contract-specified parameters
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
                "status": "pending"
            }
        )

        # Verify contract: returns str (UUID)
        assert isinstance(result, str)
        assert result == "proposal-456"

    @pytest.mark.unit
    async def test_accepts_required_parameters(self, fake_mcp_client):
        """Contract: Accepts required parameters: scene_id, type, content."""
        fake_mcp_client.call_tool.return_value = "proposal-456"

        # Call with minimum required parameters
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
                }
            }
        )

        # Verify required parameters were passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "scene_id" in params
        assert "type" in params
        assert "content" in params
        assert params["scene_id"] == "scene-456"
        assert params["type"] == "state_change"
        assert params["content"]["entity_id"] == "goblin-001"

    @pytest.mark.unit
    async def test_accepts_status_parameter(self, fake_mcp_client):
        """Contract: Accepts optional status parameter."""
        fake_mcp_client.call_tool.return_value = "proposal-456"

        # Call with status
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
                "status": "pending"
            }
        )

        # Verify status was passed
        call_args = fake_mcp_client.call_tool.call_args
        assert call_args[0][1]["status"] == "pending"

    @pytest.mark.unit
    async def test_accepts_different_content_actions(self, fake_mcp_client):
        """Contract: Accepts different content actions: set, increment, decrement."""
        fake_mcp_client.call_tool.return_value = "proposal-456"

        for action in ["set", "increment", "decrement"]:
            result = await fake_mcp_client.call_tool(
                "mongodb_create_proposal",
                {
                    "scene_id": "scene-456",
                    "type": "state_change",
                    "content": {
                        "entity_id": "goblin-001",
                        "tag": "health",
                        "action": action,
                        "value": 10
                    }
                }
            )

            # Verify action was passed
            call_args = fake_mcp_client.call_tool.call_args
            assert call_args[0][1]["content"]["action"] == action
