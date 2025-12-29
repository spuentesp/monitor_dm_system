"""
Unit tests for MongoDB scene operations (DL-4).

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
def mock_mongodb_client() -> Mock:
    """Provide a mock MongoDB client."""
    client = Mock()
    collection = Mock()
    client.get_collection.return_value = collection
    return client


@pytest.fixture
def story_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample story data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "title": "Test Story",
    }


@pytest.fixture
def scene_data(story_data: Dict[str, Any], universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample scene data."""
    return {
        "scene_id": str(uuid4()),
        "story_id": story_data["id"],
        "universe_id": universe_data["id"],
        "title": "Opening Scene",
        "purpose": "Introduce the characters",
        "status": SceneStatus.ACTIVE.value,
        "order": 1,
        "location_ref": None,
        "participating_entities": [],
        "turns": [],
        "proposed_changes": [],
        "canonical_outcomes": [],
        "summary": "",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "completed_at": None,
    }


@pytest.fixture
def entity_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample entity data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": "Test Entity",
    }


# =============================================================================
# TESTS: mongodb_create_scene
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_scene_success(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
    universe_data: Dict[str, Any],
):
    """Test successful scene creation."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock Neo4j story/universe exists check
    mock_neo4j_client.execute_read.return_value = [
        {"story_id": story_data["id"], "universe_id": universe_data["id"]}
    ]

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.insert_one.return_value = Mock(inserted_id="mongo_obj_id")

    params = SceneCreate(
        story_id=UUID(story_data["id"]),
        universe_id=UUID(universe_data["id"]),
        title="Opening Scene",
        purpose="Introduce the characters",
        order=1,
    )

    result = mongodb_create_scene(params)

    assert result.title == "Opening Scene"
    assert result.story_id == UUID(story_data["id"])
    assert result.status == SceneStatus.ACTIVE
    assert len(result.turns) == 0
    collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_scene_with_participants(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
    universe_data: Dict[str, Any],
    entity_data: Dict[str, Any],
):
    """Test scene creation with participating entities."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock Neo4j story/universe check and entity check
    mock_neo4j_client.execute_read.side_effect = [
        [{"story_id": story_data["id"], "universe_id": universe_data["id"]}],
        [{"id": entity_data["id"]}],  # entity check
    ]

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.insert_one.return_value = Mock(inserted_id="mongo_obj_id")

    entity_id = UUID(entity_data["id"])
    params = SceneCreate(
        story_id=UUID(story_data["id"]),
        universe_id=UUID(universe_data["id"]),
        title="Opening Scene",
        participating_entities=[entity_id],
    )

    result = mongodb_create_scene(params)

    assert entity_id in result.participating_entities
    assert mock_neo4j_client.execute_read.call_count == 2


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_scene_invalid_story(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test scene creation with invalid story_id."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock story doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = SceneCreate(
        story_id=uuid4(),
        universe_id=uuid4(),
        title="Test Scene",
    )

    with pytest.raises(ValueError, match="Story .* or Universe .* not found"):
        mongodb_create_scene(params)


# =============================================================================
# TESTS: mongodb_get_scene
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_scene_success(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    scene_data: Dict[str, Any],
):
    """Test successful scene retrieval."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = scene_data

    result = mongodb_get_scene(UUID(scene_data["scene_id"]))

    assert result is not None
    assert result.scene_id == UUID(scene_data["scene_id"])
    assert result.title == "Opening Scene"
    assert len(result.turns) == 0
    collection.find_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_scene_with_turns(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    scene_data: Dict[str, Any],
):
    """Test scene retrieval with turns."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Add turns to scene data
    turn_1 = {
        "turn_id": str(uuid4()),
        "speaker": Speaker.USER.value,
        "entity_id": None,
        "text": "Hello, world!",
        "timestamp": datetime.now(timezone.utc),
        "resolution_ref": None,
    }
    turn_2 = {
        "turn_id": str(uuid4()),
        "speaker": Speaker.GM.value,
        "entity_id": None,
        "text": "Welcome, adventurer!",
        "timestamp": datetime.now(timezone.utc),
        "resolution_ref": None,
    }
    scene_data["turns"] = [turn_1, turn_2]

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = scene_data

    result = mongodb_get_scene(UUID(scene_data["scene_id"]))

    assert result is not None
    assert len(result.turns) == 2
    assert result.turns[0].text == "Hello, world!"
    assert result.turns[1].text == "Welcome, adventurer!"


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_scene_not_found(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
):
    """Test scene retrieval when scene doesn't exist."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = None

    result = mongodb_get_scene(uuid4())

    assert result is None


# =============================================================================
# TESTS: mongodb_update_scene
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_scene_title(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    scene_data: Dict[str, Any],
):
    """Test updating scene title."""
    mock_get_mongo.return_value = mock_mongodb_client

    updated_data = scene_data.copy()
    updated_data["title"] = "New Scene Title"

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.side_effect = [scene_data, updated_data]
    collection.update_one.return_value = Mock(modified_count=1)

    params = SceneUpdate(title="New Scene Title")
    result = mongodb_update_scene(UUID(scene_data["scene_id"]), params)

    assert result.title == "New Scene Title"
    collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_scene_status_valid_transition(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    scene_data: Dict[str, Any],
):
    """Test updating scene status with valid transition."""
    mock_get_mongo.return_value = mock_mongodb_client

    updated_data = scene_data.copy()
    updated_data["status"] = SceneStatus.FINALIZING.value

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.side_effect = [scene_data, updated_data]
    collection.update_one.return_value = Mock(modified_count=1)

    params = SceneUpdate(status=SceneStatus.FINALIZING)
    result = mongodb_update_scene(UUID(scene_data["scene_id"]), params)

    assert result.status == SceneStatus.FINALIZING


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_scene_status_invalid_transition(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    scene_data: Dict[str, Any],
):
    """Test updating scene status with invalid transition."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Scene is already completed
    scene_data["status"] = SceneStatus.COMPLETED.value

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = scene_data

    params = SceneUpdate(status=SceneStatus.ACTIVE)

    with pytest.raises(ValueError, match="Invalid status transition"):
        mongodb_update_scene(UUID(scene_data["scene_id"]), params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_scene_not_found(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
):
    """Test updating non-existent scene."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = None

    params = SceneUpdate(title="New Title")

    with pytest.raises(ValueError, match="Scene .* not found"):
        mongodb_update_scene(uuid4(), params)


# =============================================================================
# TESTS: mongodb_list_scenes
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_scenes_success(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    scene_data: Dict[str, Any],
):
    """Test listing scenes with no filters."""
    mock_get_mongo.return_value = mock_mongodb_client

    scene_data_2 = scene_data.copy()
    scene_data_2["scene_id"] = str(uuid4())
    scene_data_2["title"] = "Second Scene"

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.count_documents.return_value = 2

    # Mock cursor
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.__iter__.return_value = iter([scene_data, scene_data_2])
    collection.find.return_value = cursor

    params = SceneFilter()
    result = mongodb_list_scenes(params)

    assert result.total == 2
    assert len(result.scenes) == 2


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_scenes_filtered_by_story(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    story_data: Dict[str, Any],
    scene_data: Dict[str, Any],
):
    """Test listing scenes filtered by story_id."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.count_documents.return_value = 1

    # Mock cursor
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.__iter__.return_value = iter([scene_data])
    collection.find.return_value = cursor

    params = SceneFilter(story_id=UUID(story_data["id"]))
    result = mongodb_list_scenes(params)

    assert result.total == 1
    assert len(result.scenes) == 1
    assert result.scenes[0].story_id == UUID(story_data["id"])


# =============================================================================
# TESTS: mongodb_append_turn
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_append_turn_success(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
    scene_data: Dict[str, Any],
):
    """Test successful turn append."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = scene_data
    collection.update_one.return_value = Mock(modified_count=1)

    params = TurnCreate(
        speaker=Speaker.USER,
        text="I draw my sword!",
    )

    result = mongodb_append_turn(UUID(scene_data["scene_id"]), params)

    assert result.text == "I draw my sword!"
    assert result.speaker == Speaker.USER
    collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_append_turn_with_entity(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
    scene_data: Dict[str, Any],
    entity_data: Dict[str, Any],
):
    """Test appending turn with entity speaker."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = scene_data
    collection.update_one.return_value = Mock(modified_count=1)

    # Mock Neo4j entity check
    mock_neo4j_client.execute_read.return_value = [{"id": entity_data["id"]}]

    entity_id = UUID(entity_data["id"])
    params = TurnCreate(
        speaker=Speaker.ENTITY,
        entity_id=entity_id,
        text="I attack the orc!",
    )

    result = mongodb_append_turn(UUID(scene_data["scene_id"]), params)

    assert result.text == "I attack the orc!"
    assert result.speaker == Speaker.ENTITY
    assert result.entity_id == entity_id


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_append_turn_to_completed_scene(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    scene_data: Dict[str, Any],
):
    """Test appending turn to completed scene fails."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Scene is completed
    scene_data["status"] = SceneStatus.COMPLETED.value

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = scene_data

    params = TurnCreate(
        speaker=Speaker.USER,
        text="This should fail",
    )

    with pytest.raises(ValueError, match="Cannot append turn to completed scene"):
        mongodb_append_turn(UUID(scene_data["scene_id"]), params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_append_turn_scene_not_found(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
):
    """Test appending turn to non-existent scene."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = None

    params = TurnCreate(
        speaker=Speaker.USER,
        text="Test text",
    )

    with pytest.raises(ValueError, match="Scene .* not found"):
        mongodb_append_turn(uuid4(), params)


# =============================================================================
# TESTS: Scene status transitions
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_scene_status_transition_active_to_completed(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    scene_data: Dict[str, Any],
):
    """Test valid status transition: active → completed."""
    mock_get_mongo.return_value = mock_mongodb_client

    updated_data = scene_data.copy()
    updated_data["status"] = SceneStatus.COMPLETED.value
    updated_data["completed_at"] = datetime.now(timezone.utc)

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.side_effect = [scene_data, updated_data]
    collection.update_one.return_value = Mock(modified_count=1)

    params = SceneUpdate(status=SceneStatus.COMPLETED)
    result = mongodb_update_scene(UUID(scene_data["scene_id"]), params)

    assert result.status == SceneStatus.COMPLETED
    assert result.completed_at is not None


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_scene_status_transition_finalizing_to_active_invalid(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    scene_data: Dict[str, Any],
):
    """Test invalid status transition: finalizing → active."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Scene is finalizing
    scene_data["status"] = SceneStatus.FINALIZING.value

    # Mock MongoDB collection
    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = scene_data

    params = SceneUpdate(status=SceneStatus.ACTIVE)

    with pytest.raises(ValueError, match="Invalid status transition"):
        mongodb_update_scene(UUID(scene_data["scene_id"]), params)
