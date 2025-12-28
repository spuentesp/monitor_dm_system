"""
Unit tests for MongoDB scene and turn operations (DL-4).

Tests cover:
- mongodb_create_scene
- mongodb_get_scene
- mongodb_update_scene
- mongodb_list_scenes
- mongodb_append_turn
"""

from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
from uuid import UUID, uuid4
from datetime import datetime, timezone

import pytest

from monitor_data.schemas.scenes import (
    SceneCreate,
    SceneUpdate,
    SceneFilter,
    TurnCreate,
)
from monitor_data.schemas.base import SceneStatus, Speaker
from monitor_data.tools.mongodb_tools import (
    mongodb_create_scene,
    mongodb_get_scene,
    mongodb_update_scene,
    mongodb_list_scenes,
    mongodb_append_turn,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def scene_data(story_data: Dict[str, Any], universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample scene data."""
    return {
        "scene_id": str(uuid4()),
        "story_id": story_data["id"],
        "universe_id": universe_data["id"],
        "title": "The Prancing Pony",
        "purpose": "Meet Strider",
        "status": SceneStatus.ACTIVE.value,
        "order": 1,
        "location_id": None,
        "participant_ids": [],
        "turns": [],
        "proposed_changes": [],
        "canonical_outcomes": [],
        "summary": None,
        "metadata": {},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "completed_at": None,
    }


@pytest.fixture
def turn_data() -> Dict[str, Any]:
    """Provide sample turn data."""
    return {
        "turn_id": str(uuid4()),
        "speaker": Speaker.GM.value,
        "entity_id": None,
        "text": "You enter the Prancing Pony inn.",
        "metadata": {},
        "timestamp": datetime.now(timezone.utc),
    }


# =============================================================================
# TESTS: mongodb_create_scene
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
def test_create_scene_success(
    mock_get_neo4j: Mock,
    mock_get_mongo: Mock,
    story_data: Dict[str, Any],
    universe_data: Dict[str, Any],
):
    """Test successful scene creation."""
    # Mock Neo4j story verification
    mock_neo4j_client = Mock()
    mock_neo4j_client.execute_read.return_value = [
        {"id": story_data["id"], "universe_id": universe_data["id"]}
    ]
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock MongoDB
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    params = SceneCreate(
        story_id=UUID(story_data["id"]),
        title="The Prancing Pony",
        purpose="Meet Strider",
        order=1,
    )

    result = mongodb_create_scene(params)

    assert result.title == "The Prancing Pony"
    assert result.story_id == UUID(story_data["id"])
    assert result.status == SceneStatus.ACTIVE
    assert len(result.turns) == 0
    mock_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
def test_create_scene_with_participants(
    mock_get_neo4j: Mock,
    mock_get_mongo: Mock,
    story_data: Dict[str, Any],
    universe_data: Dict[str, Any],
    pc_entity_data: Dict[str, Any],
):
    """Test scene creation with participants."""
    # Mock Neo4j
    mock_neo4j_client = Mock()
    mock_neo4j_client.execute_read.return_value = [
        {"id": story_data["id"], "universe_id": universe_data["id"]}
    ]
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock MongoDB
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    pc_id = UUID(pc_entity_data["id"])
    params = SceneCreate(
        story_id=UUID(story_data["id"]),
        title="The Prancing Pony",
        participant_ids=[pc_id],
    )

    result = mongodb_create_scene(params)

    assert len(result.participant_ids) == 1
    assert result.participant_ids[0] == pc_id


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
def test_create_scene_invalid_story(
    mock_get_neo4j: Mock,
    mock_get_mongo: Mock,
):
    """Test scene creation with invalid story_id."""
    # Mock Neo4j - story not found
    mock_neo4j_client = Mock()
    mock_neo4j_client.execute_read.return_value = []
    mock_get_neo4j.return_value = mock_neo4j_client

    params = SceneCreate(
        story_id=uuid4(),
        title="The Prancing Pony",
    )

    with pytest.raises(ValueError, match="Story .* not found"):
        mongodb_create_scene(params)


# =============================================================================
# TESTS: mongodb_get_scene
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_scene_success(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
):
    """Test successful scene retrieval."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.find_one.return_value = scene_data
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    result = mongodb_get_scene(UUID(scene_data["scene_id"]))

    assert result is not None
    assert result.scene_id == UUID(scene_data["scene_id"])
    assert result.title == scene_data["title"]
    assert len(result.turns) == 0


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_scene_with_turns(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
    turn_data: Dict[str, Any],
):
    """Test scene retrieval with turns."""
    scene_with_turns = scene_data.copy()
    scene_with_turns["turns"] = [turn_data]

    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.find_one.return_value = scene_with_turns
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    result = mongodb_get_scene(UUID(scene_data["scene_id"]))

    assert result is not None
    assert len(result.turns) == 1
    assert result.turns[0].text == turn_data["text"]


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_scene_not_found(mock_get_mongo: Mock):
    """Test scene retrieval when scene doesn't exist."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.find_one.return_value = None
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    result = mongodb_get_scene(uuid4())

    assert result is None


# =============================================================================
# TESTS: mongodb_update_scene
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_scene_status(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
):
    """Test updating scene status."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    
    # Mock find_one for both the update check and the get_scene call
    scene_finalizing = scene_data.copy()
    scene_finalizing["status"] = SceneStatus.FINALIZING.value
    mock_collection.find_one.side_effect = [
        scene_data,  # First call in update
        scene_finalizing,  # Second call in get_scene
    ]
    
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    params = SceneUpdate(status=SceneStatus.FINALIZING)
    result = mongodb_update_scene(UUID(scene_data["scene_id"]), params)

    assert result.status == SceneStatus.FINALIZING
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_scene_invalid_status_transition(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
):
    """Test invalid status transition."""
    # Try to go from active to completed (skipping finalizing)
    scene_data_active = scene_data.copy()
    scene_data_active["status"] = SceneStatus.ACTIVE.value

    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.find_one.return_value = scene_data_active
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    params = SceneUpdate(status=SceneStatus.COMPLETED)

    with pytest.raises(ValueError, match="Invalid status transition"):
        mongodb_update_scene(UUID(scene_data["scene_id"]), params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_scene_summary(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
):
    """Test updating scene summary."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    
    scene_with_summary = scene_data.copy()
    scene_with_summary["summary"] = "The party met Strider at the inn."
    mock_collection.find_one.side_effect = [
        scene_data,
        scene_with_summary,
    ]
    
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    params = SceneUpdate(summary="The party met Strider at the inn.")
    result = mongodb_update_scene(UUID(scene_data["scene_id"]), params)

    assert result.summary == "The party met Strider at the inn."


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_scene_not_found(mock_get_mongo: Mock):
    """Test updating non-existent scene."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.find_one.return_value = None
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    params = SceneUpdate(summary="New summary")

    with pytest.raises(ValueError, match="Scene .* not found"):
        mongodb_update_scene(uuid4(), params)


# =============================================================================
# TESTS: mongodb_list_scenes
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_scenes_all(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
):
    """Test listing all scenes."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.count_documents.return_value = 1
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [scene_data]
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_collection.find.return_value = mock_cursor
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    filters = SceneFilter()
    result = mongodb_list_scenes(filters)

    assert result.total == 1
    assert len(result.scenes) == 1
    assert result.scenes[0].scene_id == UUID(scene_data["scene_id"])


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_scenes_by_story(
    mock_get_mongo: Mock,
    story_data: Dict[str, Any],
    scene_data: Dict[str, Any],
):
    """Test listing scenes filtered by story."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.count_documents.return_value = 1
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [scene_data]
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_collection.find.return_value = mock_cursor
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    filters = SceneFilter(story_id=UUID(story_data["id"]))
    result = mongodb_list_scenes(filters)

    assert result.total == 1
    # Verify find was called with story_id filter
    call_args = mock_collection.find.call_args[0][0]
    assert "story_id" in call_args
    assert call_args["story_id"] == story_data["id"]


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_scenes_by_status(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
):
    """Test listing scenes filtered by status."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.count_documents.return_value = 1
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [scene_data]
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_collection.find.return_value = mock_cursor
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    filters = SceneFilter(status=SceneStatus.ACTIVE)
    result = mongodb_list_scenes(filters)

    assert result.total == 1
    # Verify find was called with status filter
    call_args = mock_collection.find.call_args[0][0]
    assert "status" in call_args
    assert call_args["status"] == SceneStatus.ACTIVE.value


# =============================================================================
# TESTS: mongodb_append_turn
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_append_turn_success(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
):
    """Test successful turn append."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.find_one.return_value = scene_data
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    params = TurnCreate(
        speaker=Speaker.GM,
        text="You enter the Prancing Pony inn.",
    )

    result = mongodb_append_turn(UUID(scene_data["scene_id"]), params)

    assert result.speaker == Speaker.GM
    assert result.text == "You enter the Prancing Pony inn."
    mock_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_append_turn_with_entity(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
    pc_entity_data: Dict[str, Any],
):
    """Test appending turn with entity speaker."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.find_one.return_value = scene_data
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    entity_id = UUID(pc_entity_data["id"])
    params = TurnCreate(
        speaker=Speaker.ENTITY,
        entity_id=entity_id,
        text="I will take the ring to Mordor.",
    )

    result = mongodb_append_turn(UUID(scene_data["scene_id"]), params)

    assert result.speaker == Speaker.ENTITY
    assert result.entity_id == entity_id
    assert result.text == "I will take the ring to Mordor."


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_append_turn_scene_not_found(mock_get_mongo: Mock):
    """Test appending turn to non-existent scene."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.find_one.return_value = None
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    params = TurnCreate(
        speaker=Speaker.GM,
        text="Some text",
    )

    with pytest.raises(ValueError, match="Scene .* not found"):
        mongodb_append_turn(uuid4(), params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_append_turn_with_metadata(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
):
    """Test appending turn with metadata."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.find_one.return_value = scene_data
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    params = TurnCreate(
        speaker=Speaker.USER,
        text="I attack the orc!",
        metadata={"action": "attack", "target": "orc"},
    )

    result = mongodb_append_turn(UUID(scene_data["scene_id"]), params)

    assert result.metadata == {"action": "attack", "target": "orc"}


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_scene_metadata(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
):
    """Test updating scene metadata."""
    mock_mongo_client = Mock()
    mock_collection = Mock()
    
    scene_with_metadata = scene_data.copy()
    scene_with_metadata["metadata"] = {"important": True}
    mock_collection.find_one.side_effect = [
        scene_data,
        scene_with_metadata,
    ]
    
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    params = SceneUpdate(metadata={"important": True})
    result = mongodb_update_scene(UUID(scene_data["scene_id"]), params)

    assert result.metadata == {"important": True}


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_scene_to_completed(
    mock_get_mongo: Mock,
    scene_data: Dict[str, Any],
):
    """Test updating scene status to completed."""
    # Scene starts as finalizing
    scene_finalizing = scene_data.copy()
    scene_finalizing["status"] = SceneStatus.FINALIZING.value
    
    scene_completed = scene_finalizing.copy()
    scene_completed["status"] = SceneStatus.COMPLETED.value
    scene_completed["completed_at"] = datetime.now(timezone.utc)
    
    mock_mongo_client = Mock()
    mock_collection = Mock()
    mock_collection.find_one.side_effect = [
        scene_finalizing,
        scene_completed,
    ]
    
    mock_mongo_client.get_collection.return_value = mock_collection
    mock_get_mongo.return_value = mock_mongo_client

    params = SceneUpdate(status=SceneStatus.COMPLETED)
    result = mongodb_update_scene(UUID(scene_data["scene_id"]), params)

    assert result.status == SceneStatus.COMPLETED
    assert result.completed_at is not None
