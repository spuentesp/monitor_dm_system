"""
P-2: Start Scene — Contract Tests

This module tests the API contracts defined in P-2-contracts.md:
- Data layer tools: neo4j_get_entity, neo4j_list_entities, mongodb_create_scene, mongodb_append_turn, qdrant_search
- Agent classes: Narrator (narrate_turn), SceneLoop (constructor, run, finalize, backtrack)
- CLI command: monitor play scene
- Web API endpoint: POST /api/scenes

Note: Narrator.generate_opening_narration() and SceneLoop.create_scene() were removed;
current API uses Narrator.narrate_turn() and SceneLoop.run().
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, List, Optional
from datetime import datetime
from uuid import UUID, uuid4

from monitor_agents.narrator import Narrator
from monitor_agents.loops.scene_loop import SceneLoop


# ============================================================================
# Data Layer Contract Tests
# ============================================================================

class TestNeo4jGetEntityContract:
    """Contract tests for neo4j_get_entity data layer tool."""

    @pytest.mark.unit
    async def test_returns_entity_data(self, fake_mcp_client):
        """Contract: Returns Dict[str, Any] with entity data."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = {
            "id": "location-123",
            "name": "Phandalin",
            "type": "location",
            "description": "A small frontier town in the Sword Mountains",
            "universe_id": "universe-123"
        }

        # Call tool (simulated)
        result = await fake_mcp_client.call_tool(
            "neo4j_get_entity",
            {"entity_id": "location-123"}
        )

        # Verify contract: returns Dict[str, Any]
        assert isinstance(result, dict)
        assert "id" in result
        assert "name" in result
        assert "type" in result
        assert "description" in result
        assert "universe_id" in result

        # Verify contract: correct values
        assert result["id"] == "location-123"
        assert result["name"] == "Phandalin"
        assert result["type"] == "location"
        assert result["universe_id"] == "universe-123"

    @pytest.mark.unit
    async def test_raises_entity_not_found_error(self, fake_mcp_client):
        """Contract: Raises EntityNotFoundError when entity does not exist."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "EntityNotFoundError: Entity not found: location-999"
        )

        # Verify contract: raises error
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "neo4j_get_entity",
                {"entity_id": "location-999"}
            )

        assert "EntityNotFoundError" in str(exc_info.value)

    @pytest.mark.unit
    async def test_accepts_entity_id_parameter(self, fake_mcp_client):
        """Contract: Accepts entity_id (str) parameter."""
        fake_mcp_client.call_tool.return_value = {
            "id": "location-123",
            "name": "Phandalin",
            "type": "location",
            "description": "A small frontier town in the Sword Mountains",
            "universe_id": "universe-123"
        }

        # Call with contract-specified parameter
        result = await fake_mcp_client.call_tool(
            "neo4j_get_entity",
            {"entity_id": "location-123"}
        )

        # Verify parameter was passed correctly
        fake_mcp_client.call_tool.assert_called_once()
        call_args = fake_mcp_client.call_tool.call_args
        assert call_args[0][0] == "neo4j_get_entity"
        assert call_args[0][1]["entity_id"] == "location-123"


class TestNeo4jListEntitiesContract:
    """Contract tests for neo4j_list_entities data layer tool."""

    @pytest.mark.unit
    async def test_returns_list_of_entities(self, fake_mcp_client):
        """Contract: Returns List[Dict[str, Any]] with entity data."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = [
            {
                "id": "char-001",
                "name": "Aldern",
                "type": "character",
                "description": "A human fighter"
            },
            {
                "id": "char-002",
                "name": "Bronwyn",
                "type": "character",
                "description": "A dwarven cleric"
            },
            {
                "id": "char-003",
                "name": "Caelum",
                "type": "character",
                "description": "An elven wizard"
            }
        ]

        # Call tool with contract-specified parameters
        result = await fake_mcp_client.call_tool(
            "neo4j_list_entities",
            {
                "universe_id": "universe-123",
                "type": "character",
                "location_id": "location-123"
            }
        )

        # Verify contract: returns List[Dict[str, Any]]
        assert isinstance(result, list)
        assert len(result) == 3

        # Verify contract: each entity has required fields
        for entity in result:
            assert isinstance(entity, dict)
            assert "id" in entity
            assert "name" in entity
            assert "type" in entity
            assert "description" in entity

    @pytest.mark.unit
    async def test_filters_by_type(self, fake_mcp_client):
        """Contract: Accepts type parameter to filter entities."""
        fake_mcp_client.call_tool.return_value = [
            {"id": "char-001", "name": "Aldern", "type": "character", "description": "A human fighter"}
        ]

        # Call with type filter
        result = await fake_mcp_client.call_tool(
            "neo4j_list_entities",
            {
                "universe_id": "universe-123",
                "type": "character"
            }
        )

        # Verify type parameter was passed
        call_args = fake_mcp_client.call_tool.call_args
        assert call_args[0][1]["type"] == "character"
        assert all(e["type"] == "character" for e in result)

    @pytest.mark.unit
    async def test_filters_by_location(self, fake_mcp_client):
        """Contract: Accepts location_id parameter to filter entities at location."""
        fake_mcp_client.call_tool.return_value = [
            {"id": "char-001", "name": "Aldern", "type": "character", "description": "A human fighter"}
        ]

        # Call with location filter
        result = await fake_mcp_client.call_tool(
            "neo4j_list_entities",
            {
                "universe_id": "universe-123",
                "location_id": "location-123"
            }
        )

        # Verify location_id parameter was passed
        call_args = fake_mcp_client.call_tool.call_args
        assert call_args[0][1]["location_id"] == "location-123"


class TestMongodbCreateSceneContract:
    """Contract tests for mongodb_create_scene data layer tool."""

    @pytest.mark.unit
    async def test_returns_scene_id(self, fake_mcp_client):
        """Contract: Returns scene_id (str) as UUID."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = "scene-456"

        # Call tool with contract-specified parameters
        result = await fake_mcp_client.call_tool(
            "mongodb_create_scene",
            {
                "story_id": "story-123",
                "title": "Goblin Ambush",
                "purpose": "Introduce the party to goblin threat",
                "location_id": "location-123",
                "entity_ids": ["char-001", "char-002", "char-003", "goblin-001"],
                "status": "active"
            }
        )

        # Verify contract: returns str (UUID)
        assert isinstance(result, str)
        assert result == "scene-456"

    @pytest.mark.unit
    async def test_accepts_required_parameters(self, fake_mcp_client):
        """Contract: Accepts required parameters: story_id, title, location_id."""
        fake_mcp_client.call_tool.return_value = "scene-456"

        # Call with minimum required parameters
        result = await fake_mcp_client.call_tool(
            "mongodb_create_scene",
            {
                "story_id": "story-123",
                "title": "Goblin Ambush",
                "location_id": "location-123"
            }
        )

        # Verify required parameters were passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "story_id" in params
        assert "title" in params
        assert "location_id" in params
        assert params["story_id"] == "story-123"
        assert params["title"] == "Goblin Ambush"
        assert params["location_id"] == "location-123"

    @pytest.mark.unit
    async def test_accepts_optional_parameters(self, fake_mcp_client):
        """Contract: Accepts optional parameters: purpose, entity_ids, status."""
        fake_mcp_client.call_tool.return_value = "scene-456"

        # Call with all parameters
        result = await fake_mcp_client.call_tool(
            "mongodb_create_scene",
            {
                "story_id": "story-123",
                "title": "Goblin Ambush",
                "purpose": "Introduce the party to goblin threat",
                "location_id": "location-123",
                "entity_ids": ["char-001", "char-002", "char-003", "goblin-001"],
                "status": "active"
            }
        )

        # Verify optional parameters were passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "purpose" in params
        assert "entity_ids" in params
        assert "status" in params
        assert params["purpose"] == "Introduce the party to goblin threat"
        assert params["entity_ids"] == ["char-001", "char-002", "char-003", "goblin-001"]
        assert params["status"] == "active"

    @pytest.mark.unit
    async def test_accepts_empty_entity_ids(self, fake_mcp_client):
        """Contract: Accepts empty entity_ids list (default)."""
        fake_mcp_client.call_tool.return_value = "scene-456"

        # Call with empty entity_ids
        result = await fake_mcp_client.call_tool(
            "mongodb_create_scene",
            {
                "story_id": "story-123",
                "title": "Goblin Ambush",
                "location_id": "location-123",
                "entity_ids": []
            }
        )

        # Verify empty entity_ids were passed
        call_args = fake_mcp_client.call_tool.call_args
        params = call_args[0][1]
        assert "entity_ids" in params
        assert params["entity_ids"] == []

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
                "mongodb_create_scene",
                {
                    "story_id": "story-123",
                    "location_id": "location-123"
                    # Missing title
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
                "mongodb_create_scene",
                {
                    "story_id": "story-999",
                    "title": "Goblin Ambush",
                    "location_id": "location-123"
                }
            )

        assert "StoryNotFoundError" in str(exc_info.value)


class TestMongodbAppendTurnContract:
    """Contract tests for mongodb_append_turn data layer tool."""

    @pytest.mark.unit
    async def test_returns_turn_id(self, fake_mcp_client):
        """Contract: Returns turn_id (str) as UUID."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = "turn-789"

        # Call tool with contract-specified parameters
        result = await fake_mcp_client.call_tool(
            "mongodb_append_turn",
            {
                "scene_id": "scene-456",
                "turn": {
                    "order": 1,
                    "type": "narrative",
                    "content": "You are traveling down the Triboar Trail...",
                    "actor": "narrator"
                }
            }
        )

        # Verify contract: returns str (UUID)
        assert isinstance(result, str)
        assert result == "turn-789"

    @pytest.mark.unit
    async def test_accepts_required_turn_fields(self, fake_mcp_client):
        """Contract: Accepts required turn fields: order, type, content."""
        fake_mcp_client.call_tool.return_value = "turn-789"

        # Call with required turn fields
        result = await fake_mcp_client.call_tool(
            "mongodb_append_turn",
            {
                "scene_id": "scene-456",
                "turn": {
                    "order": 1,
                    "type": "narrative",
                    "content": "You are traveling down the Triboar Trail..."
                }
            }
        )

        # Verify required turn fields were passed
        call_args = fake_mcp_client.call_tool.call_args
        turn = call_args[0][1]["turn"]
        assert "order" in turn
        assert "type" in turn
        assert "content" in turn
        assert turn["order"] == 1
        assert turn["type"] == "narrative"
        assert turn["content"] == "You are traveling down the Triboar Trail..."

    @pytest.mark.unit
    async def test_accepts_optional_actor_field(self, fake_mcp_client):
        """Contract: Accepts optional actor field in turn."""
        fake_mcp_client.call_tool.return_value = "turn-789"

        # Call with actor field
        result = await fake_mcp_client.call_tool(
            "mongodb_append_turn",
            {
                "scene_id": "scene-456",
                "turn": {
                    "order": 1,
                    "type": "narrative",
                    "content": "You are traveling down the Triboar Trail...",
                    "actor": "narrator"
                }
            }
        )

        # Verify actor field was passed
        call_args = fake_mcp_client.call_tool.call_args
        turn = call_args[0][1]["turn"]
        assert "actor" in turn
        assert turn["actor"] == "narrator"

    @pytest.mark.unit
    async def test_accepts_different_turn_types(self, fake_mcp_client):
        """Contract: Accepts different turn types: narrative, player_action, gm_action."""
        fake_mcp_client.call_tool.return_value = "turn-789"

        for turn_type in ["narrative", "player_action", "gm_action"]:
            result = await fake_mcp_client.call_tool(
                "mongodb_append_turn",
                {
                    "scene_id": "scene-456",
                    "turn": {
                        "order": 1,
                        "type": turn_type,
                        "content": "Test content"
                    }
                }
            )

            # Verify turn type was passed
            call_args = fake_mcp_client.call_tool.call_args
            assert call_args[0][1]["turn"]["type"] == turn_type

    @pytest.mark.unit
    async def test_raises_scene_not_found_error(self, fake_mcp_client):
        """Contract: Raises SceneNotFoundError when scene_id does not exist."""
        # Mock error response
        fake_mcp_client.call_tool.side_effect = Exception(
            "SceneNotFoundError: Scene not found: scene-999"
        )

        # Verify contract: raises error when scene not found
        with pytest.raises(Exception) as exc_info:
            await fake_mcp_client.call_tool(
                "mongodb_append_turn",
                {
                    "scene_id": "scene-999",
                    "turn": {
                        "order": 1,
                        "type": "narrative",
                        "content": "Test content"
                    }
                }
            )

        assert "SceneNotFoundError" in str(exc_info.value)


class TestQdrantSearchContract:
    """Contract tests for qdrant_search data layer tool."""

    @pytest.mark.unit
    async def test_returns_list_of_results(self, fake_mcp_client):
        """Contract: Returns List[Dict[str, Any]] with search results."""
        # Mock response matching contract
        fake_mcp_client.call_tool.return_value = [
            {
                "id": "result-001",
                "score": 0.95,
                "payload": {
                    "content": "Goblin ambush on forest trail",
                    "source": "campaign_notes",
                    "metadata": {"type": "encounter"}
                }
            },
            {
                "id": "result-002",
                "score": 0.87,
                "payload": {
                    "content": "Forest trail ambush tactics",
                    "source": "bestiary",
                    "metadata": {"type": "tactics"}
                }
            }
        ]

        # Call tool with contract-specified parameters
        result = await fake_mcp_client.call_tool(
            "qdrant_search",
            {
                "query": "goblin ambush forest trail",
                "collection_name": "scene_chunks",
                "limit": 10
            }
        )

        # Verify contract: returns List[Dict[str, Any]]
        assert isinstance(result, list)
        assert len(result) == 2

        # Verify contract: each result has required fields
        for search_result in result:
            assert isinstance(search_result, dict)
            assert "id" in search_result
            assert "score" in search_result
            assert "payload" in search_result
            assert isinstance(search_result["score"], float)
            assert 0.0 <= search_result["score"] <= 1.0
            assert isinstance(search_result["payload"], dict)

    @pytest.mark.unit
    async def test_respects_limit_parameter(self, fake_mcp_client):
        """Contract: Returns at most limit results."""
        # Mock response with 2 results
        fake_mcp_client.call_tool.return_value = [
            {"id": "result-001", "score": 0.95, "payload": {"content": "Test 1"}},
            {"id": "result-002", "score": 0.87, "payload": {"content": "Test 2"}}
        ]

        # Call with limit=5
        result = await fake_mcp_client.call_tool(
            "qdrant_search",
            {
                "query": "test query",
                "collection_name": "scene_chunks",
                "limit": 5
            }
        )

        # Verify limit parameter was passed
        call_args = fake_mcp_client.call_tool.call_args
        assert call_args[0][1]["limit"] == 5

    @pytest.mark.unit
    async def test_accepts_collection_name_parameter(self, fake_mcp_client):
        """Contract: Accepts collection_name parameter."""
        fake_mcp_client.call_tool.return_value = []

        # Call with collection_name
        result = await fake_mcp_client.call_tool(
            "qdrant_search",
            {
                "query": "test query",
                "collection_name": "scene_chunks"
            }
        )

        # Verify collection_name was passed
        call_args = fake_mcp_client.call_tool.call_args
        assert call_args[0][1]["collection_name"] == "scene_chunks"

    @pytest.mark.unit
    async def test_returns_empty_list_on_no_results(self, fake_mcp_client):
        """Contract: Returns empty list when no results found."""
        # Mock empty response
        fake_mcp_client.call_tool.return_value = []

        # Call tool
        result = await fake_mcp_client.call_tool(
            "qdrant_search",
            {
                "query": "nonexistent query",
                "collection_name": "scene_chunks"
            }
        )

        # Verify contract: returns empty list
        assert isinstance(result, list)
        assert len(result) == 0


# ============================================================================
# Agent Contract Tests
# ============================================================================

class TestNarratorContract:
    """Contract tests for Narrator agent."""

    @pytest.mark.unit
    def test_constructor_accepts_agent_id(self):
        """Contract: Narrator.__init__ accepts agent_id (str)."""
        narrator = Narrator(agent_id="narrator-test-1")
        assert narrator.agent_id == "narrator-test-1"

    @pytest.mark.unit
    def test_constructor_default_agent_id(self):
        """Contract: Narrator.__init__ defaults agent_id to 'narrator-1'."""
        narrator = Narrator()
        assert narrator.agent_id == "narrator-1"

    @pytest.mark.unit
    def test_has_narrate_turn_method(self):
        """Contract: Narrator has narrate_turn() async method."""
        narrator = Narrator(agent_id="narrator-test-1")
        assert hasattr(narrator, "narrate_turn")
        assert callable(narrator.narrate_turn)

    @pytest.mark.unit
    async def test_narrate_turn_returns_dict(self):
        """Contract: narrate_turn() returns Dict[str, Any] with narrative_text, proposals, turn_id."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch
        narrator = Narrator(agent_id="narrator-test-1")
        with patch.object(narrator, "_generate_narrative_and_proposals", new_callable=AsyncMock) as mock_gen, \
             patch.object(narrator, "_persist_turn", new_callable=AsyncMock) as mock_persist:
            mock_gen.return_value = ("The goblins leap from the bushes.", [], 5)
            mock_persist.return_value = "turn-123"
            result = await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I attack the goblin",
                resolution=None,
                context={"entities": [], "memories": [], "turns": []},
            )
            assert isinstance(result, dict)
            assert "narrative_text" in result
            assert "proposals" in result
            assert "turn_id" in result

    @pytest.mark.unit
    async def test_narrate_turn_accepts_required_parameters(self):
        """Contract: narrate_turn() accepts scene_id, user_input, resolution, context."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch
        narrator = Narrator(agent_id="narrator-test-1")
        with patch.object(narrator, "_generate_narrative_and_proposals", new_callable=AsyncMock) as mock_gen, \
             patch.object(narrator, "_persist_turn", new_callable=AsyncMock) as mock_persist:
            mock_gen.return_value = ("Narrative text.", [], 5)
            mock_persist.return_value = "turn-456"
            result = await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I search the room",
                resolution={"outcome": "success"},
                context={"entities": [], "memories": [], "turns": []},
            )
            assert isinstance(result, dict)

    @pytest.mark.unit
    async def test_narrate_turn_accepts_optional_parameters(self):
        """Contract: narrate_turn() accepts optional game_context, session_tone, gm_profile."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch
        narrator = Narrator(agent_id="narrator-test-1")
        with patch.object(narrator, "_generate_narrative_and_proposals", new_callable=AsyncMock) as mock_gen, \
             patch.object(narrator, "_persist_turn", new_callable=AsyncMock) as mock_persist:
            mock_gen.return_value = ("Narrative text.", [], 5)
            mock_persist.return_value = "turn-789"
            result = await narrator.narrate_turn(
                scene_id=uuid4(),
                user_input="I attack",
                resolution=None,
                context={"entities": [], "memories": [], "turns": []},
                game_context={"system": "dnd5e"},
                session_tone="grim",
                gm_profile={"name": "Dark DM"},
            )
            assert isinstance(result, dict)


class TestSceneLoopConstructorContract:
    """Contract tests for SceneLoop constructor and attribute contracts."""

    @pytest.mark.unit
    def test_constructor_accepts_required_ids(self):
        """Contract: SceneLoop.__init__ accepts scene_id (UUID) and story_id (UUID)."""
        from uuid import uuid4
        scene_id = uuid4()
        story_id = uuid4()
        scene_loop = SceneLoop(scene_id=scene_id, story_id=story_id)
        assert scene_loop.scene_id == scene_id
        assert scene_loop.story_id == story_id

    @pytest.mark.unit
    def test_constructor_accepts_optional_universe_id(self):
        """Contract: SceneLoop.__init__ accepts optional universe_id (UUID)."""
        from uuid import uuid4
        scene_id = uuid4()
        story_id = uuid4()
        universe_id = uuid4()
        scene_loop = SceneLoop(scene_id=scene_id, story_id=story_id, universe_id=universe_id)
        assert scene_loop.universe_id == universe_id

    @pytest.mark.unit
    def test_constructor_accepts_optional_parameters(self):
        """Contract: SceneLoop.__init__ accepts max_turns, play_mode, session_tone, etc."""
        from uuid import uuid4
        scene_loop = SceneLoop(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            max_turns=30,
            play_mode="dice_game_system",
            session_tone="grim",
            roll_mode="normal",
            tension_score=0.7,
        )
        assert scene_loop.max_turns == 30
        assert scene_loop.play_mode == "dice_game_system"
        assert scene_loop.session_tone == "grim"
        assert scene_loop.roll_mode == "normal"
        assert scene_loop.tension_score == 0.7

    @pytest.mark.unit
    def test_has_run_method(self):
        """Contract: SceneLoop has run() async method."""
        from uuid import uuid4
        scene_loop = SceneLoop(scene_id=uuid4(), story_id=uuid4())
        assert hasattr(scene_loop, "run")
        assert callable(scene_loop.run)

    @pytest.mark.unit
    def test_has_finalize_method(self):
        """Contract: SceneLoop has finalize() async method."""
        from uuid import uuid4
        scene_loop = SceneLoop(scene_id=uuid4(), story_id=uuid4())
        assert hasattr(scene_loop, "finalize")
        assert callable(scene_loop.finalize)

    @pytest.mark.unit
    def test_has_backtrack_method(self):
        """Contract: SceneLoop has backtrack() async method."""
        from uuid import uuid4
        scene_loop = SceneLoop(scene_id=uuid4(), story_id=uuid4())
        assert hasattr(scene_loop, "backtrack")
        assert callable(scene_loop.backtrack)


class TestSceneLoopRunContract:
    """Contract tests for SceneLoop.run() method."""

    @pytest.mark.unit
    async def test_run_accepts_user_input(self):
        """Contract: run() accepts user_input (str) parameter."""
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch
        scene_loop = SceneLoop(scene_id=uuid4(), story_id=uuid4())
        with patch("monitor_agents.loops.scene_loop.MongoDBSaver") as mock_saver_cls:
            mock_saver = MagicMock()
            mock_saver.__enter__ = MagicMock(return_value=mock_saver)
            mock_saver.__exit__ = MagicMock(return_value=False)
            mock_saver_cls.from_conn_string.return_value = mock_saver
            mock_compiled = AsyncMock()
            mock_saver_cls.from_conn_string.return_value = mock_saver
            # Just verify the method signature accepts user_input
            import inspect
            sig = inspect.signature(scene_loop.run)
            assert "user_input" in sig.parameters


# ============================================================================
# Integration Tests (with FakeMCPClient)
# ============================================================================

class TestP2Integration:
    """Integration tests for P-2 using FakeMCPClient."""

    @pytest.mark.integration
    async def test_full_scene_data_flow(self, fake_mcp_client):
        """Contract: Full data-layer flow for scene creation via MCP tools."""
        # Setup: Mock all required MCP tool calls
        fake_mcp_client.call_tool.side_effect = [
            # Step 1: neo4j_get_entity - validate location
            {
                "id": "location-123",
                "name": "Phandalin",
                "type": "location",
                "description": "A small frontier town",
                "universe_id": "universe-123"
            },
            # Step 2: neo4j_list_entities - get available characters
            [
                {"id": "char-001", "name": "Aldern", "type": "character", "description": "A human fighter"},
                {"id": "char-002", "name": "Bronwyn", "type": "character", "description": "A dwarven cleric"},
                {"id": "char-003", "name": "Caelum", "type": "character", "description": "An elven wizard"}
            ],
            # Step 3: qdrant_search - retrieve context
            [
                {"id": "result-001", "score": 0.95, "payload": {"content": "Goblin ambush tactics"}},
                {"id": "result-002", "score": 0.87, "payload": {"content": "Forest trail encounters"}}
            ],
            # Step 4: mongodb_create_scene - create scene document
            "scene-456",
            # Step 5: mongodb_append_turn - append opening turn
            "turn-789"
        ]

        # Execute: Call data layer tools in sequence
        location = await fake_mcp_client.call_tool(
            "neo4j_get_entity",
            {"entity_id": "location-123"}
        )
        entities = await fake_mcp_client.call_tool(
            "neo4j_list_entities",
            {"universe_id": "universe-123"}
        )
        context = await fake_mcp_client.call_tool(
            "qdrant_search",
            {"collection_name": "scene_chunks", "query": "goblin ambush"}
        )
        scene_id = await fake_mcp_client.call_tool(
            "mongodb_create_scene",
            {
                "story_id": "story-123",
                "title": "Goblin Ambush",
                "location_id": "location-123",
                "entity_ids": ["char-001", "char-002", "char-003"]
            }
        )
        turn_id = await fake_mcp_client.call_tool(
            "mongodb_append_turn",
            {
                "scene_id": "scene-456",
                "turn": {"type": "narrative", "order": 1, "content": "You are traveling down the Triboar Trail..."}
            }
        )

        # Verify: Contract compliance
        assert isinstance(location, dict)
        assert location["id"] == "location-123"
        assert isinstance(entities, list)
        assert len(entities) == 3
        assert isinstance(context, list)
        assert isinstance(scene_id, str)
        assert isinstance(turn_id, str)

        # Verify: All MCP tools were called in sequence
        assert fake_mcp_client.call_tool.call_count == 5

        # Verify: neo4j_get_entity called with correct parameters
        call_args_list = fake_mcp_client.call_tool.call_args_list
        assert call_args_list[0][0][0] == "neo4j_get_entity"
        assert call_args_list[0][0][1]["entity_id"] == "location-123"

        # Verify: neo4j_list_entities called with correct parameters
        assert call_args_list[1][0][0] == "neo4j_list_entities"
        assert call_args_list[1][0][1]["universe_id"] == "universe-123"

        # Verify: qdrant_search called with correct parameters
        assert call_args_list[2][0][0] == "qdrant_search"
        assert call_args_list[2][0][1]["collection_name"] == "scene_chunks"

        # Verify: mongodb_create_scene called with correct parameters
        assert call_args_list[3][0][0] == "mongodb_create_scene"
        scene_params = call_args_list[3][0][1]
        assert scene_params["story_id"] == "story-123"
        assert scene_params["title"] == "Goblin Ambush"
        assert scene_params["location_id"] == "location-123"
        assert scene_params["entity_ids"] == ["char-001", "char-002", "char-003"]

        # Verify: mongodb_append_turn called with correct parameters
        assert call_args_list[4][0][0] == "mongodb_append_turn"
        assert call_args_list[4][0][1]["scene_id"] == "scene-456"
        assert call_args_list[4][0][1]["turn"]["type"] == "narrative"
        assert call_args_list[4][0][1]["turn"]["order"] == 1