"""
Unit tests for Neo4j story operations (DL-4).

Tests cover:
- neo4j_create_story
- neo4j_get_story
- neo4j_update_story
- neo4j_list_stories
"""

from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4
from datetime import datetime

import pytest

from monitor_data.schemas.stories import (
    StoryCreate,
    StoryUpdate,
    StoryFilter,
)
from monitor_data.schemas.base import StoryType, StoryStatus
from monitor_data.tools.neo4j_tools import (
    neo4j_create_story,
    neo4j_get_story,
    neo4j_update_story,
    neo4j_list_stories,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def story_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample story data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "title": "The Quest for the Ancient Artifact",
        "story_type": StoryType.CAMPAIGN.value,
        "theme": "Heroes vs Ancient Evil",
        "premise": "A group of adventurers seeks a powerful artifact",
        "status": StoryStatus.PLANNED.value,
        "start_time_ref": None,
        "end_time_ref": None,
        "created_at": datetime.fromisoformat("2024-01-01T00:00:00"),
        "completed_at": None,
    }


@pytest.fixture
def pc_entity_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample player character entity data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": "Aragorn",
        "entity_type": "character",
        "is_archetype": False,
    }


# =============================================================================
# TESTS: neo4j_create_story
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_story_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    story_data: Dict[str, Any],
):
    """Test successful story creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists check
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock story creation
    mock_neo4j_client.execute_write.return_value = [{"s": story_data}]

    params = StoryCreate(
        universe_id=UUID(universe_data["id"]),
        title="The Quest for the Ancient Artifact",
        story_type=StoryType.CAMPAIGN,
        theme="Heroes vs Ancient Evil",
        premise="A group of adventurers seeks a powerful artifact",
        status=StoryStatus.PLANNED,
    )

    result = neo4j_create_story(params)

    assert result.title == "The Quest for the Ancient Artifact"
    assert result.universe_id == UUID(universe_data["id"])
    assert result.story_type == StoryType.CAMPAIGN
    assert result.status == StoryStatus.PLANNED
    assert result.scene_count == 0
    assert mock_neo4j_client.execute_read.call_count >= 1
    assert mock_neo4j_client.execute_write.call_count >= 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_story_with_pcs(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    story_data: Dict[str, Any],
    pc_entity_data: Dict[str, Any],
):
    """Test story creation with player characters."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe and entity checks
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],  # universe check
        [{"id": pc_entity_data["id"]}],  # pc check
    ]

    # Mock story creation and PC edge creation
    mock_neo4j_client.execute_write.return_value = [{"s": story_data}]

    pc_id = UUID(pc_entity_data["id"])
    params = StoryCreate(
        universe_id=UUID(universe_data["id"]),
        title="The Quest for the Ancient Artifact",
        story_type=StoryType.CAMPAIGN,
        theme="Heroes vs Ancient Evil",
        premise="A group of adventurers seeks a powerful artifact",
        pc_ids=[pc_id],
    )

    result = neo4j_create_story(params)

    assert result.title == "The Quest for the Ancient Artifact"
    assert pc_id in result.pc_ids
    # 1 universe check + 1 pc check
    assert mock_neo4j_client.execute_read.call_count == 2
    # 1 story creation + 1 PC edge
    assert mock_neo4j_client.execute_write.call_count == 2


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_story_invalid_universe(
    mock_get_client: Mock, mock_neo4j_client: Mock
):
    """Test story creation with invalid universe_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = StoryCreate(
        universe_id=uuid4(),
        title="Test Story",
        story_type=StoryType.CAMPAIGN,
    )

    with pytest.raises(ValueError, match="Universe .* not found"):
        neo4j_create_story(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_story_invalid_pc(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test story creation with invalid player character entity."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists, but PC doesn't
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],  # universe check
        [],  # pc check fails
    ]

    params = StoryCreate(
        universe_id=UUID(universe_data["id"]),
        title="Test Story",
        pc_ids=[uuid4()],
    )

    with pytest.raises(ValueError, match="Player character entity .* not found"):
        neo4j_create_story(params)


# =============================================================================
# TESTS: neo4j_get_story
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_story_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test successful story retrieval."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock story query result
    mock_neo4j_client.execute_read.return_value = [
        {"s": story_data, "scene_count": 3, "pc_ids": [str(uuid4()), str(uuid4())]}
    ]

    result = neo4j_get_story(UUID(story_data["id"]))

    assert result is not None
    assert result.id == UUID(story_data["id"])
    assert result.title == "The Quest for the Ancient Artifact"
    assert result.scene_count == 3
    assert len(result.pc_ids) == 2


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_story_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test story retrieval when story doesn't exist."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock empty result
    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_story(uuid4())

    assert result is None


# =============================================================================
# TESTS: neo4j_update_story
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_story_title(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test updating story title."""
    mock_get_client.return_value = mock_neo4j_client

    updated_data = story_data.copy()
    updated_data["title"] = "New Story Title"

    # Mock story exists check, update, and get
    mock_neo4j_client.execute_read.side_effect = [
        [{"s": story_data}],  # verify exists
        [{"s": updated_data, "scene_count": 0, "pc_ids": []}],  # get after update
    ]
    mock_neo4j_client.execute_write.return_value = [{"s": updated_data}]

    params = StoryUpdate(title="New Story Title")
    result = neo4j_update_story(UUID(story_data["id"]), params)

    assert result.title == "New Story Title"
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_story_status(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test updating story status to completed."""
    mock_get_client.return_value = mock_neo4j_client

    updated_data = story_data.copy()
    updated_data["status"] = StoryStatus.COMPLETED.value
    updated_data["completed_at"] = datetime.now()

    # Mock story exists check, update, and get
    mock_neo4j_client.execute_read.side_effect = [
        [{"s": story_data}],  # verify exists
        [{"s": updated_data, "scene_count": 0, "pc_ids": []}],  # get after update
    ]
    mock_neo4j_client.execute_write.return_value = [{"s": updated_data}]

    params = StoryUpdate(status=StoryStatus.COMPLETED)
    result = neo4j_update_story(UUID(story_data["id"]), params)

    assert result.status == StoryStatus.COMPLETED
    assert result.completed_at is not None


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_story_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test updating non-existent story."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock story doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = StoryUpdate(title="New Title")

    with pytest.raises(ValueError, match="Story .* not found"):
        neo4j_update_story(uuid4(), params)


# =============================================================================
# TESTS: neo4j_list_stories
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_stories_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    story_data: Dict[str, Any],
):
    """Test listing stories with no filters."""
    mock_get_client.return_value = mock_neo4j_client

    story_data_2 = story_data.copy()
    story_data_2["id"] = str(uuid4())
    story_data_2["title"] = "Another Story"

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 2}],  # count
        [
            {"s": story_data, "scene_count": 3, "pc_ids": []},
            {"s": story_data_2, "scene_count": 1, "pc_ids": []},
        ],  # list
    ]

    params = StoryFilter()
    result = neo4j_list_stories(params)

    assert result.total == 2
    assert len(result.stories) == 2
    assert result.stories[0].title == "The Quest for the Ancient Artifact"
    assert result.stories[1].title == "Another Story"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_stories_filtered_by_universe(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    story_data: Dict[str, Any],
):
    """Test listing stories filtered by universe_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],  # count
        [{"s": story_data, "scene_count": 3, "pc_ids": []}],  # list
    ]

    params = StoryFilter(universe_id=UUID(universe_data["id"]))
    result = neo4j_list_stories(params)

    assert result.total == 1
    assert len(result.stories) == 1
    assert result.stories[0].universe_id == UUID(universe_data["id"])


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_stories_filtered_by_status(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test listing stories filtered by status."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],  # count
        [{"s": story_data, "scene_count": 0, "pc_ids": []}],  # list
    ]

    params = StoryFilter(status=StoryStatus.PLANNED)
    result = neo4j_list_stories(params)

    assert result.total == 1
    assert len(result.stories) == 1
    assert result.stories[0].status == StoryStatus.PLANNED


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_stories_pagination(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test listing stories with pagination."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 10}],  # count
        [{"s": story_data, "scene_count": 0, "pc_ids": []}],  # list (1 result)
    ]

    params = StoryFilter(limit=1, offset=5)
    result = neo4j_list_stories(params)

    assert result.total == 10
    assert result.limit == 1
    assert result.offset == 5
    assert len(result.stories) == 1


# =============================================================================
# TESTS: Story status transitions
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_story_status_valid_transition_planned_to_active(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test valid status transition: planned → active."""
    mock_get_client.return_value = mock_neo4j_client

    story_data["status"] = StoryStatus.PLANNED.value
    updated_data = story_data.copy()
    updated_data["status"] = StoryStatus.ACTIVE.value

    # Mock story exists check, update, and get
    mock_neo4j_client.execute_read.side_effect = [
        [{"s": story_data}],  # verify exists
        [{"s": updated_data, "scene_count": 0, "pc_ids": []}],  # get after update
    ]
    mock_neo4j_client.execute_write.return_value = [{"s": updated_data}]

    params = StoryUpdate(status=StoryStatus.ACTIVE)
    result = neo4j_update_story(UUID(story_data["id"]), params)

    assert result.status == StoryStatus.ACTIVE


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_story_status_valid_transition_active_to_completed(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test valid status transition: active → completed."""
    mock_get_client.return_value = mock_neo4j_client

    story_data["status"] = StoryStatus.ACTIVE.value
    updated_data = story_data.copy()
    updated_data["status"] = StoryStatus.COMPLETED.value

    # Mock story exists check, update, and get
    mock_neo4j_client.execute_read.side_effect = [
        [{"s": story_data}],  # verify exists
        [{"s": updated_data, "scene_count": 0, "pc_ids": []}],  # get after update
    ]
    mock_neo4j_client.execute_write.return_value = [{"s": updated_data}]

    params = StoryUpdate(status=StoryStatus.COMPLETED)
    result = neo4j_update_story(UUID(story_data["id"]), params)

    assert result.status == StoryStatus.COMPLETED


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_story_status_invalid_transition_completed_to_active(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test invalid status transition: completed → active."""
    mock_get_client.return_value = mock_neo4j_client

    # Story is already completed
    story_data["status"] = StoryStatus.COMPLETED.value

    # Mock story exists check
    mock_neo4j_client.execute_read.return_value = [{"s": story_data}]

    params = StoryUpdate(status=StoryStatus.ACTIVE)

    with pytest.raises(ValueError, match="Invalid status transition"):
        neo4j_update_story(UUID(story_data["id"]), params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_story_status_invalid_transition_planned_to_completed(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test invalid status transition: planned → completed (must go through active)."""
    mock_get_client.return_value = mock_neo4j_client

    # Story is planned
    story_data["status"] = StoryStatus.PLANNED.value

    # Mock story exists check
    mock_neo4j_client.execute_read.return_value = [{"s": story_data}]

    params = StoryUpdate(status=StoryStatus.COMPLETED)

    with pytest.raises(ValueError, match="Invalid status transition"):
        neo4j_update_story(UUID(story_data["id"]), params)
