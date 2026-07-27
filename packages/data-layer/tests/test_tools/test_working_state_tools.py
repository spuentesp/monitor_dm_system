"""
Tests for Character Working State MongoDB tools (DL-26).
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.working_state import (
    AddStatModification,
    WorkingStateCreate,
    WorkingStateFilter,
    WorkingStateUpdate,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_add_modification,
    mongodb_create_working_state,
    mongodb_get_working_state,
    mongodb_list_working_states,
    mongodb_update_working_state,
)


# mongodb_create_working_state tests
@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
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

    with patch("monitor_data.tools.mongodb_tools.working_state.uuid4", return_value=new_id):
        result = mongodb_create_working_state(params)

    assert result.state.entity_id == entity_id
    assert result.state.scene_id == scene_id
    assert result.state.current_stats["STR"] == 10
    assert result.state.resources["hp"]["current"] == 20
    mock_state.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_create_working_state_returns_existing_when_exists(mock_get_mongodb: Mock):
    """Test creating working state returns existing when already exists."""
    entity_id = uuid4()
    scene_id = uuid4()
    state_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    # Mock existing
    existing_doc = {
        "state_id": str(state_id),
        "entity_id": str(entity_id),
        "scene_id": str(scene_id),
        "story_id": str(uuid4()),
        "base_stats": {"STR": 10, "DEX": 12},
        "current_stats": {"STR": 10, "DEX": 12},
        "resources": {"hp": {"current": 20, "max": 20}},
        "modifications": [],
        "temporary_effects": [],
        "inventory_changes": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "canonized": False,
        "canonized_at": None,
    }
    mock_state.find_one.return_value = existing_doc

    params = WorkingStateCreate(
        entity_id=entity_id,
        scene_id=scene_id,
        story_id=uuid4(),
        base_stats={"STR": 10, "DEX": 12},
        resources={"hp": {"current": 20, "max": 20}},
    )

    result = mongodb_create_working_state(params)

    assert result.state.state_id == state_id
    mock_state.insert_one.assert_not_called()


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_create_working_state_with_current_stats_provided(mock_get_mongodb: Mock):
    """Test creating working state with current_stats provided."""
    entity_id = uuid4()
    scene_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    # Mock no existing
    mock_state.find_one.return_value = None

    params = WorkingStateCreate(
        entity_id=entity_id,
        scene_id=scene_id,
        story_id=uuid4(),
        base_stats={"STR": 10, "DEX": 12},
        current_stats={"STR": 12, "DEX": 14},
        resources={"hp": {"current": 20, "max": 20}},
    )

    # Mock uuid4
    new_id = uuid4()

    with patch("monitor_data.tools.mongodb_tools.working_state.uuid4", return_value=new_id):
        result = mongodb_create_working_state(params)

    assert result.state.current_stats["STR"] == 12
    assert result.state.current_stats["DEX"] == 14
    mock_state.insert_one.assert_called_once()


# mongodb_get_working_state tests
@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
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
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }

    result = mongodb_get_working_state(entity_id, scene_id)
    assert result is not None
    assert result.state.state_id == state_id
    assert result.state.entity_id == entity_id


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_get_working_state_not_found_returns_none(mock_get_mongodb: Mock):
    """Test getting working state returns None when not found."""
    entity_id = uuid4()
    scene_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.find_one.return_value = None

    result = mongodb_get_working_state(entity_id, scene_id)

    assert result is None


# mongodb_update_working_state tests
@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_update_working_state_not_found_raises_error(mock_get_mongodb: Mock):
    """Test updating working state raises ValueError when not found."""
    state_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.find_one_and_update.return_value = None

    params = WorkingStateUpdate(current_stats={"STR": 14})

    with pytest.raises(ValueError, match=f"Working state {state_id} not found"):
        mongodb_update_working_state(state_id, params)


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_update_working_state_resources(mock_get_mongodb: Mock):
    """Test updating working state resources."""
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
        "resources": {"hp": {"current": 15, "max": 20}},
    }

    params = WorkingStateUpdate(resources={"hp": {"current": 15, "max": 20}})
    result = mongodb_update_working_state(state_id, params)

    assert result.state.resources["hp"]["current"] == 15


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_update_working_state_both_current_stats_and_resources(mock_get_mongodb: Mock):
    """Test updating both current_stats and resources."""
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
        "current_stats": {"STR": 15},
        "resources": {"hp": {"current": 18, "max": 20}},
    }

    params = WorkingStateUpdate(
        current_stats={"STR": 15},
        resources={"hp": {"current": 18, "max": 20}},
    )
    result = mongodb_update_working_state(state_id, params)

    assert result.state.current_stats["STR"] == 15
    assert result.state.resources["hp"]["current"] == 18


# mongodb_add_modification tests
@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
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
                "timestamp": datetime.now(UTC),
            }
        ],
    }

    params = AddStatModification(state_id=state_id, stat_or_resource="hp", change=-5, source="Trap")

    result = mongodb_add_modification(params)
    assert len(result.state.modifications) == 1
    assert result.state.modifications[0].change == -5


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_add_modification_not_found_raises_error(mock_get_mongodb: Mock):
    """Test adding modification raises ValueError when state not found."""
    state_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.find_one_and_update.return_value = None

    params = AddStatModification(state_id=state_id, stat_or_resource="hp", change=-5, source="Trap")

    with pytest.raises(ValueError, match=f"Working state {state_id} not found"):
        mongodb_add_modification(params)


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_add_modification_multiple_modifications(mock_get_mongodb: Mock):
    """Test adding multiple modifications accumulates them."""
    state_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    # Return with 2 existing modifications
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
                "timestamp": datetime.now(UTC),
            },
            {
                "mod_id": str(uuid4()),
                "stat_or_resource": "hp",
                "change": 10,
                "source": "Heal",
                "source_id": None,
                "timestamp": datetime.now(UTC),
            },
        ],
    }

    params = AddStatModification(state_id=state_id, stat_or_resource="hp", change=-5, source="Trap")

    result = mongodb_add_modification(params)
    assert len(result.state.modifications) == 2
    assert result.state.modifications[0].change == -5
    assert result.state.modifications[1].change == 10


# mongodb_list_working_states tests
@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_list_working_states_with_scene_filter(mock_get_mongodb: Mock):
    """Test listing with scene_id filter."""
    scene_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.count_documents.return_value = 2

    mock_cursor = MagicMock()
    mock_state.find.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "state_id": str(uuid4()),
            "entity_id": str(uuid4()),
            "scene_id": str(scene_id),
            "story_id": str(uuid4()),
            "base_stats": {},
            "current_stats": {},
            "resources": {},
        },
        {
            "state_id": str(uuid4()),
            "entity_id": str(uuid4()),
            "scene_id": str(scene_id),
            "story_id": str(uuid4()),
            "base_stats": {},
            "current_stats": {},
            "resources": {},
        },
    ]

    params = WorkingStateFilter(scene_id=scene_id)
    result = mongodb_list_working_states(params)

    assert result.total == 2
    assert len(result.states) == 2


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_list_working_states_empty_results(mock_get_mongodb: Mock):
    """Test listing returns empty when no results."""
    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.count_documents.return_value = 0

    mock_cursor = MagicMock()
    mock_state.find.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = []

    params = WorkingStateFilter()
    result = mongodb_list_working_states(params)

    assert result.total == 0
    assert len(result.states) == 0


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_list_working_states_with_pagination(mock_get_mongodb: Mock):
    """Test listing with pagination parameters."""
    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.count_documents.return_value = 5

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

    params = WorkingStateFilter(offset=2, limit=1)
    result = mongodb_list_working_states(params)

    assert result.total == 5
    assert result.limit == 1
    assert result.offset == 2
    assert len(result.states) == 1
    mock_cursor.skip.assert_called_once_with(2)
    mock_cursor.limit.assert_called_once_with(1)


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_list_working_states_with_entity_filter(mock_get_mongodb: Mock):
    """Test listing with entity_id filter."""
    entity_id = uuid4()

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
            "entity_id": str(entity_id),
            "scene_id": str(uuid4()),
            "story_id": str(uuid4()),
            "base_stats": {},
            "current_stats": {},
            "resources": {},
        }
    ]

    params = WorkingStateFilter(entity_id=entity_id)
    result = mongodb_list_working_states(params)

    assert result.total == 1
    assert len(result.states) == 1
    assert result.states[0].entity_id == entity_id


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_list_working_states_with_story_id_filter(mock_get_mongodb: Mock):
    """Test listing with story_id filter."""
    story_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    mock_state.count_documents.return_value = 2

    mock_cursor = MagicMock()
    mock_state.find.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = [
        {
            "state_id": str(uuid4()),
            "entity_id": str(uuid4()),
            "scene_id": str(uuid4()),
            "story_id": str(story_id),
            "base_stats": {},
            "current_stats": {},
            "resources": {},
        },
        {
            "state_id": str(uuid4()),
            "entity_id": str(uuid4()),
            "scene_id": str(uuid4()),
            "story_id": str(story_id),
            "base_stats": {},
            "current_stats": {},
            "resources": {},
        },
    ]

    params = WorkingStateFilter(story_id=story_id)
    result = mongodb_list_working_states(params)

    assert result.total == 2
    assert len(result.states) == 2
    assert all(state.story_id == story_id for state in result.states)


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_list_working_states_with_canonized_filter(mock_get_mongodb: Mock):
    """Test listing with canonized filter."""
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
            "canonized": True,
        }
    ]

    params = WorkingStateFilter(canonized=True)
    result = mongodb_list_working_states(params)

    assert result.total == 1
    assert len(result.states) == 1
    assert result.states[0].canonized is True


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_update_working_state_does_not_modify_base_stats(mock_get_mongodb: Mock):
    """Test that updating working state does not modify base_stats."""
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
        "base_stats": {"STR": 10, "DEX": 12},  # Unchanged
        "current_stats": {"STR": 15},  # Updated
        "resources": {},
    }

    params = WorkingStateUpdate(current_stats={"STR": 15})
    result = mongodb_update_working_state(state_id, params)

    assert result.state.base_stats == {"STR": 10, "DEX": 12}
    assert result.state.current_stats == {"STR": 15}


@patch("monitor_data.tools.mongodb_tools.working_state.get_mongodb_client")
def test_update_working_state_with_empty_params_does_nothing(mock_get_mongodb: Mock):
    """Test that updating with empty params only updates the timestamp."""
    state_id = uuid4()

    mock_mongodb = MagicMock()
    mock_state = MagicMock()

    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_state

    original_updated_at = datetime.now(UTC)
    mock_state.find_one_and_update.return_value = {
        "state_id": str(state_id),
        "entity_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "story_id": str(uuid4()),
        "base_stats": {"STR": 10, "DEX": 12},
        "current_stats": {"STR": 10, "DEX": 12},
        "resources": {},
        "updated_at": original_updated_at,
    }

    params = WorkingStateUpdate()
    result = mongodb_update_working_state(state_id, params)

    # The updated_at should be the only thing that changed
    assert result.state.base_stats == {"STR": 10, "DEX": 12}
    assert result.state.current_stats == {"STR": 10, "DEX": 12}
