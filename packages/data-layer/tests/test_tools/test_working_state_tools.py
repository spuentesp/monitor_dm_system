"""
Tests for Character Working State MongoDB tools (DL-26).
"""

from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4


from monitor_data.schemas.working_state import (
    WorkingStateCreate,
    WorkingStateUpdate,
    AddStatModification,
    WorkingStateFilter,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_working_state,
    mongodb_get_working_state,
    mongodb_update_working_state,
    mongodb_add_modification,
    mongodb_list_working_states,
)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_working_state_success(mock_get_mongodb: Mock):
    """Test creating a working state record."""
    entity_id = uuid4()
    scene_id = uuid4()
    story_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    # Mock no existing
    mock_state.find_one.return_value = None

    params = WorkingStateCreate(
        entity_id=entity_id,
        scene_id=scene_id,
        story_id=story_id,
        base_stats={"STR": 10, "DEX": 12},
        resources={"hp": {"current": 20, "max": 20}},
    )

    # Mock uuid4
    new_id = uuid4()

    with patch("monitor_data.tools.mongodb_tools.uuid4", return_value=new_id):
        result = mongodb_create_working_state(params)

    assert result.state.entity_id == entity_id
    assert result.state.scene_id == scene_id
    assert result.state.current_stats["STR"] == 10
    assert result.state.resources["hp"]["current"] == 20
    mock_state.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_working_state_success(mock_get_mongodb: Mock):
    """Test getting working state."""
    entity_id = uuid4()
    scene_id = uuid4()
    state_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.find_one.return_value = {
        "state_id": str(state_id),
        "entity_id": str(entity_id),
        "scene_id": str(scene_id),
        "story_id": str(uuid4()),
        "base_stats": {},
        "current_stats": {},
        "resources": {},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    result = mongodb_get_working_state(entity_id, scene_id)
    assert result is not None
    assert result.state.state_id == state_id
    assert result.state.entity_id == entity_id


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_working_state_success(mock_get_mongodb: Mock):
    """Test updating working state."""
    state_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.find_one_and_update.return_value = {
        "state_id": str(state_id),
        "entity_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "story_id": str(uuid4()),
        "base_stats": {},
        "current_stats": {"STR": 14},  # Updated
        "resources": {},
    }

    params = WorkingStateUpdate(current_stats={"STR": 14})
    result = mongodb_update_working_state(state_id, params)

    assert result.state.current_stats["STR"] == 14
    mock_state.find_one_and_update.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_add_modification_success(mock_get_mongodb: Mock):
    """Test adding a modification."""
    state_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.find_one_and_update.return_value = {
        "state_id": str(state_id),
        "entity_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "story_id": str(uuid4()),
        "base_stats": {},
        "current_stats": {},
        "resources": {},
        "modifications": [
            {
                "mod_id": str(uuid4()),
                "stat_or_resource": "hp",
                "change": -5,
                "source": "Trap",
                "source_id": None,
                "timestamp": datetime.now(timezone.utc),
            }
        ],
    }

    params = AddStatModification(
        state_id=state_id, stat_or_resource="hp", change=-5, source="Trap"
    )

    result = mongodb_add_modification(params)
    assert len(result.state.modifications) == 1
    assert result.state.modifications[0].change == -5


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_working_states(mock_get_mongodb: Mock):
    """Test listing."""
    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.count_documents.return_value = 1

    mock_cursor = MagicMock()
    mock_state.find.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "state_id": str(uuid4()),
            "entity_id": str(uuid4()),
            "scene_id": str(uuid4()),
            "story_id": str(uuid4()),
            "base_stats": {},
            "current_stats": {},
            "resources": {},
        }
    ]

    params = WorkingStateFilter()
    result = mongodb_list_working_states(params)

    assert result.total == 1
    assert len(result.states) == 1
