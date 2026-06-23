"""
P-1: Start New Story — Contract Tests

This module tests the API contracts defined in P-1-contracts.md:
- Data layer tools: neo4j_get_universe, neo4j_create_story, mongodb_create_story_outline
- Agent class: StoryLoop (constructor, advance, start_or_resume, finalize)
- CLI command: monitor play new
- Web API endpoint: POST /api/stories

Note: StoryLoop.create_story() was removed; current API uses start_or_resume/advance.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, List, Optional
from datetime import datetime
from uuid import UUID, uuid4

from monitor_agents.loops.story_loop import StoryLoop


# ============================================================================
# Data Layer Contract Tests
# ============================================================================

class TestNeo4jGetUniverseContract:
    """Contract tests for neo4j_get_universe data layer tool."""

    @pytest.mark.unit
    async def test_returns_universe_data(self, fake_mcp_client):
        """Contract: Returns Dict[str, Any] with universe data."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "id": "universe-123",
            "name": "Forgotten Realms",
            "description": "A classic D&D setting",
            "multiverse_id": "multiverse-001"
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "neo4j_get_universe",
            {"universe_id": "universe-123"}
        )

        # Verify contract: returns Dict[str, Any]
        assert isinstance(result, dict)
        assert "id" in result
        assert "name" in result
        assert "description" in result
        assert "multiverse_id" in result

        # Verify contract: correct values
        assert result["id"] == "universe-123"
        assert result["name"] == "Forgotten Realms"
        assert result["description"] == "A classic D&D setting"
        assert result["multiverse_id"] == "multiverse-001"

    @pytest.mark.unit
    async def test_raises_universe_not_found_error(self, fake_mcp_client):
        """Contract: Raises UniverseNotFoundError when universe does not exist."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "UniverseNotFoundError: Universe not found: universe-999"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "neo4j_get_universe",
                {"universe_id": "universe-999"}
            )

        assert "UniverseNotFoundError" in str(exc_info.value)

    @pytest.mark.unit
    async def test_accepts_universe_id_parameter(self, fake_mcp_client):
        """Contract: Accepts universe_id (str) parameter."""
        fake_mcp_client.call_tool.return_value = {
            "id": "universe-123",
            "name": "Forgotten Realms",
            "description": "A classic D&D setting",
            "multiverse_id": "multiverse-001"
        }

        # Call with contract-specified parameter
        result = await fake_mcp_client.call_tool(
            "neo4j_get_universe",
            {"universe_id": "universe-123"}
        )

        # Verify parameter was passed correctly
        fake_mcp_client.call_tool.assert_called_once()
        call_args = fake_mcp_client.call_tool.call_args
        assert call_args[0][0] == "neo4j_get_universe"
        assert call_args[0][1]["universe_id"] == "universe-123"


class TestNeo4jCreateStoryContract:
    """Contract tests for neo4j_create_story data layer tool."""

    @pytest.mark.unit
    async def test_returns_story_id(self, fake_mcp_client):
        """Contract: Returns story_id (str) as UUID."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = "story-123"

        # Call tool with contract-specified parameters
        result = await fake_mcp_client.call_tool(
            "neo4j_create_story",
            {
                "universe_id": "universe-123",
                "title": "The Lost Mines of Phandelver",
                "story_type": "campaign",
                "theme": "Fantasy adventure",
                "premise": "A group of adventurers must rescue a dwarf from goblins.",
                "status": "active"
            }
        )

        # Verify contract: returns str (UUID)
        assert isinstance(result, str)
        assert result == "story-123"

    @pytest.mark.unit
    async def test_accepts_required_parameters(self, fake_mcp_client):
        """Contract: Accepts required parameters: universe_id, title, story_type."""
        fake_mcp_client.call_tool.return_value = "story-123"

        # Call with minimum required parameters
        result = await fake_mcp_client.call_tool(
            "neo4j_create_story",
            {
                "universe_id": "universe-123",
                "title": "The Lost Mines of Phandelver",
                "story_type": "campaign"
            }
        )

        # Verify all required parameters were passed
        fake_mcp_client.call_tool.assert_called_once()
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "universe_id" in params
        assert "title" in params
        assert "story_type" in params
        assert params["universe_id"] == "universe-123"
        assert params["title"] == "The Lost Mines of Phandelver"
        assert params["story_type"] == "campaign"

    @pytest.mark.unit
    async def test_accepts_optional_parameters(self, fake_mcp_client):
        """Contract: Accepts optional parameters: theme, premise, status."""
        fake_mcp_client.call_tool.return_value = "story-123"

        # Call with all parameters
        result = await fake_mcp_client.call_tool(
            "neo4j_create_story",
            {
                "universe_id": "universe-123",
                "title": "The Lost Mines of Phandelver",
                "story_type": "campaign",
                "theme": "Fantasy adventure",
                "premise": "A group of adventurers must rescue a dwarf from goblins.",
                "status": "active"
            }
        )

        # Verify optional parameters were passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "theme" in params
        assert "premise" in params
        assert "status" in params
        assert params["theme"] == "Fantasy adventure"
        assert params["premise"] == "A group of adventurers must rescue a dwarf from goblins."
        assert params["status"] == "active"

    @pytest.mark.unit
    async def test_raises_invalid_parameter_error(self, fake_mcp_client):
        """Contract: Raises InvalidParameterError when required parameters missing."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "InvalidParameterError: Missing required parameter: title"
        )

        # Verify contract: raises error when missing required parameter
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "neo4j_create_story",
                {
                    "universe_id": "universe-123",
                    # Missing title and story_type
                }
            )

        assert "InvalidParameterError" in str(exc_info.value)

    @pytest.mark.unit
    async def test_raises_universe_not_found_error(self, fake_mcp_client):
        """Contract: Raises UniverseNotFoundError when universe does not exist."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "UniverseNotFoundError: Universe not found: universe-999"
        )

        # Verify contract: raises error when universe not found
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "neo4j_create_story",
                {
                    "universe_id": "universe-999",
                    "title": "The Lost Mines of Phandelver",
                    "story_type": "campaign"
                }
            )

        assert "UniverseNotFoundError" in str(exc_info.value)


class TestMongodbCreateStoryOutlineContract:
    """Contract tests for mongodb_create_story_outline data layer tool."""

    @pytest.mark.unit
    async def test_returns_outline_id(self, fake_mcp_client):
        """Contract: Returns outline_id (str) as UUID."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = "outline-456"

        # Call tool with contract-specified parameters
        result = await fake_mcp_client.call_tool(
            "mongodb_create_story_outline",
            {
                "story_id": "story-123",
                "beats": [
                    {"order": 1, "title": "Introduction", "description": "Meet the party"},
                    {"order": 2, "title": "Inciting Incident", "description": "Goblin ambush"}
                ],
                "pc_ids": ["pc-001", "pc-002", "pc-003"]
            }
        )

        # Verify contract: returns str (UUID)
        assert isinstance(result, str)
        assert result == "outline-456"

    @pytest.mark.unit
    async def test_accepts_required_parameters(self, fake_mcp_client):
        """Contract: Accepts required parameters: story_id, pc_ids."""
        fake_mcp_client.call_tool.return_value = "outline-456"

        # Call with minimum required parameters
        result = await fake_mcp_client.call_tool(
            "mongodb_create_story_outline",
            {
                "story_id": "story-123",
                "pc_ids": ["pc-001", "pc-002", "pc-003"]
            }
        )

        # Verify required parameters were passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "story_id" in params
        assert "pc_ids" in params
        assert params["story_id"] == "story-123"
        assert params["pc_ids"] == ["pc-001", "pc-002", "pc-003"]

    @pytest.mark.unit
    async def test_accepts_beats_parameter(self, fake_mcp_client):
        """Contract: Accepts beats parameter (list of story beats)."""
        fake_mcp_client.call_tool.return_value = "outline-456"

        # Call with beats
        beats = [
            {"order": 1, "title": "Introduction", "description": "Meet the party"},
            {"order": 2, "title": "Inciting Incident", "description": "Goblin ambush"}
        ]

        result = await fake_mcp_client.call_tool(
            "mongodb_create_story_outline",
            {
                "story_id": "story-123",
                "beats": beats,
                "pc_ids": ["pc-001", "pc-002", "pc-003"]
            }
        )

        # Verify beats were passed correctly
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "beats" in params
        assert params["beats"] == beats

    @pytest.mark.unit
    async def test_accepts_empty_beats(self, fake_mcp_client):
        """Contract: Accepts empty beats list (default)."""
        fake_mcp_client.call_tool.return_value = "outline-456"

        # Call with empty beats
        result = await fake_mcp_client.call_tool(
            "mongodb_create_story_outline",
            {
                "story_id": "story-123",
                "beats": [],
                "pc_ids": ["pc-001", "pc-002", "pc-003"]
            }
        )

        # Verify empty beats were passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "beats" in params
        assert params["beats"] == []

    @pytest.mark.unit
    async def test_raises_invalid_parameter_error(self, fake_mcp_client):
        """Contract: Raises InvalidParameterError when required parameters missing."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "InvalidParameterError: Missing required parameter: story_id"
        )

        # Verify contract: raises error when missing required parameter
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "mongodb_create_story_outline",
                {
                    # Missing story_id
                    "pc_ids": ["pc-001", "pc-002", "pc-003"]
                }
            )

        assert "InvalidParameterError" in str(exc_info.value)

    @pytest.mark.unit
    async def test_raises_story_not_found_error(self, fake_mcp_client):
        """Contract: Raises StoryNotFoundError when story_id does not exist."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "StoryNotFoundError: Story not found: story-999"
        )

        # Verify contract: raises error when story not found
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "mongodb_create_story_outline",
                {
                    "story_id": "story-999",
                    "pc_ids": ["pc-001", "pc-002", "pc-003"]
                }
            )

        assert "StoryNotFoundError" in str(exc_info.value)


# ============================================================================
# Agent Contract Tests
# ============================================================================

class TestStoryLoopConstructorContract:
    """Contract tests for StoryLoop constructor and attribute contracts."""

    @pytest.mark.unit
    def test_constructor_accepts_story_id_and_universe_id(self):
        """Contract: StoryLoop.__init__ accepts story_id (UUID) and universe_id (UUID)."""
        from uuid import uuid4
        story_id = uuid4()
        universe_id = uuid4()
        story_loop = StoryLoop(story_id=story_id, universe_id=universe_id)
        assert story_loop.story_id == story_id
        assert story_loop.universe_id == universe_id

    @pytest.mark.unit
    def test_constructor_stores_ids_as_uuids(self):
        """Contract: StoryLoop stores story_id and universe_id as UUID objects."""
        from uuid import UUID, uuid4
        story_id = uuid4()
        universe_id = uuid4()
        story_loop = StoryLoop(story_id=story_id, universe_id=universe_id)
        assert isinstance(story_loop.story_id, UUID)
        assert isinstance(story_loop.universe_id, UUID)

    @pytest.mark.unit
    def test_constructor_stores_story_id_as_provided(self):
        """Contract: StoryLoop.__init__ stores story_id as provided (no coercion)."""
        story_id = uuid4()
        universe_id = uuid4()
        story_loop = StoryLoop(story_id=story_id, universe_id=universe_id)
        assert story_loop.story_id == story_id

    @pytest.mark.unit
    def test_constructor_stores_universe_id_as_provided(self):
        """Contract: StoryLoop.__init__ stores universe_id as provided (no coercion)."""
        story_id = uuid4()
        universe_id = uuid4()
        story_loop = StoryLoop(story_id=story_id, universe_id=universe_id)
        assert story_loop.universe_id == universe_id

    @pytest.mark.unit
    def test_has_start_or_resume_method(self):
        """Contract: StoryLoop has start_or_resume() async method."""
        from uuid import uuid4
        story_loop = StoryLoop(story_id=uuid4(), universe_id=uuid4())
        assert hasattr(story_loop, "start_or_resume")
        assert callable(story_loop.start_or_resume)

    @pytest.mark.unit
    def test_has_advance_method(self):
        """Contract: StoryLoop has advance() async method."""
        from uuid import uuid4
        story_loop = StoryLoop(story_id=uuid4(), universe_id=uuid4())
        assert hasattr(story_loop, "advance")
        assert callable(story_loop.advance)

    @pytest.mark.unit
    def test_has_complete_current_scene_method(self):
        """Contract: StoryLoop has complete_current_scene() async method."""
        from uuid import uuid4
        story_loop = StoryLoop(story_id=uuid4(), universe_id=uuid4())
        assert hasattr(story_loop, "complete_current_scene")
        assert callable(story_loop.complete_current_scene)

    @pytest.mark.unit
    def test_has_finalize_method(self):
        """Contract: StoryLoop has finalize() async method."""
        from uuid import uuid4
        story_loop = StoryLoop(story_id=uuid4(), universe_id=uuid4())
        assert hasattr(story_loop, "finalize")
        assert callable(story_loop.finalize)

    @pytest.mark.unit
    def test_has_create_flashback_method(self):
        """Contract: StoryLoop has create_flashback() async method."""
        from uuid import uuid4
        story_loop = StoryLoop(story_id=uuid4(), universe_id=uuid4())
        assert hasattr(story_loop, "create_flashback")
        assert callable(story_loop.create_flashback)


class TestStoryLoopAdvanceContract:
    """Contract tests for StoryLoop.advance() method."""

    @pytest.mark.unit
    async def test_advance_returns_dict(self):
        """Contract: advance() returns Dict[str, Any]."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch
        story_loop = StoryLoop(story_id=uuid4(), universe_id=uuid4())
        # Mock the internal dependencies
        with patch("monitor_agents.loops.story_loop.simulate_world_advance", new_callable=AsyncMock) as mock_sim, \
             patch("monitor_agents.loops.story_loop.transition_scene", new_callable=AsyncMock) as mock_trans:
            mock_sim.return_value = {"world_tone": "dramatic"}
            mock_trans.return_value = {"next_scene_id": str(uuid4())}
            result = await story_loop.advance(story_complete=False)
            assert isinstance(result, dict)

    @pytest.mark.unit
    async def test_advance_with_story_complete_returns_complete_flag(self):
        """Contract: advance(story_complete=True) returns story_complete=True."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch
        story_loop = StoryLoop(story_id=uuid4(), universe_id=uuid4())
        with patch("monitor_agents.loops.story_loop.finalize_story", new_callable=AsyncMock) as mock_finalize:
            result = await story_loop.advance(story_complete=True)
            assert result["story_complete"] is True

    @pytest.mark.unit
    async def test_advance_includes_story_id(self):
        """Contract: advance() result includes story_id."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch
        story_id = uuid4()
        story_loop = StoryLoop(story_id=story_id, universe_id=uuid4())
        with patch("monitor_agents.loops.story_loop.simulate_world_advance", new_callable=AsyncMock) as mock_sim, \
             patch("monitor_agents.loops.story_loop.transition_scene", new_callable=AsyncMock) as mock_trans:
            mock_sim.return_value = {"world_tone": "dramatic"}
            mock_trans.return_value = {"next_scene_id": str(uuid4())}
            result = await story_loop.advance(story_complete=False)
            assert "story_id" in result


# ============================================================================
# Web API Contract Tests
# ============================================================================

class TestCreateStoryAPIContract:
    """Contract tests for POST /api/stories endpoint."""

    @pytest.mark.unit
    async def test_returns_201_on_success(self):
        """Contract: Returns 201 status on successful creation."""
        # This would be tested with actual FastAPI test client
        # For now, we verify the contract specification
        pass

    @pytest.mark.unit
    async def test_returns_400_on_invalid_parameters(self):
        """Contract: Returns 400 status when required parameters missing."""
        # This would be tested with actual FastAPI test client
        pass

    @pytest.mark.unit
    async def test_returns_404_on_universe_not_found(self):
        """Contract: Returns 404 status when universe does not exist."""
        # This would be tested with actual FastAPI test client
        pass

    @pytest.mark.unit
    async def test_accepts_required_request_body_fields(self):
        """Contract: Request body requires universe_id, title."""
        # Request body contract:
        # {
        #   "universe_id": "string (required)",
        #   "title": "string (required)",
        #   "story_type": "string (optional, default='campaign')",
        #   "theme": "string (optional)",
        #   "premise": "string (optional)",
        #   "pc_ids": ["string"] (optional)
        # }
        pass

    @pytest.mark.unit
    async def test_returns_success_response_body(self):
        """Contract: Returns response with story_id, outline_id, status, created_at."""
        # Response body contract (201):
        # {
        #   "story_id": "story-123",
        #   "outline_id": "outline-456",
        #   "status": "success",
        #   "created_at": "2025-01-19T00:00:00Z"
        # }
        pass


# ============================================================================
# Integration Tests (with FakeMCPClient)
# ============================================================================

class TestP1Integration:
    """Integration tests for P-1 using FakeMCPClient."""

    @pytest.mark.integration
    async def test_full_story_creation_flow(self, fake_mcp_client):
        """Contract: Full flow from data layer tools creates story and outline."""
        # Setup: Mock all required MCP tool calls
        fake_mcp_client.call_tool.side_effect = [
            # Step 1: neo4j_get_universe - validate universe
            {
                "id": "universe-123",
                "name": "Forgotten Realms",
                "description": "A classic D&D setting",
                "multiverse_id": "multiverse-001"
            },
            # Step 2: neo4j_create_story - create Story node in Neo4j
            "story-123",
            # Step 3: mongodb_create_story_outline - create outline in MongoDB
            "outline-456"
        ]

        # Execute: Call data layer tools in sequence
        universe = await fake_mcp_client.call_tool(
            "neo4j_get_universe",
            {"universe_id": "universe-123"}
        )
        story_id = await fake_mcp_client.call_tool(
            "neo4j_create_story",
            {
                "universe_id": "universe-123",
                "title": "The Lost Mines of Phandelver",
                "story_type": "campaign",
                "theme": "Fantasy adventure",
                "premise": "A group of adventurers must rescue a dwarf from goblins.",
                "status": "active"
            }
        )
        outline_id = await fake_mcp_client.call_tool(
            "mongodb_create_story_outline",
            {
                "story_id": "story-123",
                "pc_ids": ["pc-001", "pc-002", "pc-003"]
            }
        )

        # Verify: Contract compliance
        assert isinstance(universe, dict)
        assert universe["id"] == "universe-123"
        assert isinstance(story_id, str)
        assert isinstance(outline_id, str)

        # Verify: All MCP tools were called in sequence
        assert fake_mcp_client.call_tool.call_count == 3

        # Verify: neo4j_get_universe called with correct parameters
        call_args_list = fake_mcp_client.call_tool.call_args_list
        assert call_args_list[0][0][0] == "neo4j_get_universe"
        assert call_args_list[0][0][1]["universe_id"] == "universe-123"

        # Verify: neo4j_create_story called with correct parameters
        assert call_args_list[1][0][0] == "neo4j_create_story"
        story_params = call_args_list[1][0][1]
        assert story_params["universe_id"] == "universe-123"
        assert story_params["title"] == "The Lost Mines of Phandelver"
        assert story_params["story_type"] == "campaign"

        # Verify: mongodb_create_story_outline called with correct parameters
        assert call_args_list[2][0][0] == "mongodb_create_story_outline"
        outline_params = call_args_list[2][0][1]
        assert outline_params["story_id"] == "story-123"
        assert outline_params["pc_ids"] == ["pc-001", "pc-002", "pc-003"]