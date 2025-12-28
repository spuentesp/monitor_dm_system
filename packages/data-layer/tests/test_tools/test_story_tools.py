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
        "title": "The Fellowship of the Ring",
        "story_type": StoryType.CAMPAIGN.value,
        "theme": "Good vs Evil",
        "premise": "A hobbit must destroy the One Ring",
        "status": StoryStatus.PLANNED.value,
        "start_time_ref": None,
        "end_time_ref": None,
        "created_at": "2024-01-01T00:00:00",
        "completed_at": None,
    }


@pytest.fixture
def pc_entity_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample PC entity data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": "Frodo Baggins",
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
):
    """Test successful story creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists check
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock story creation
    mock_neo4j_client.execute_write.return_value = []

    params = StoryCreate(
        universe_id=UUID(universe_data["id"]),
        title="The Fellowship of the Ring",
        story_type=StoryType.CAMPAIGN,
        theme="Good vs Evil",
        premise="A hobbit must destroy the One Ring",
    )

    result = neo4j_create_story(params)

    assert result.title == "The Fellowship of the Ring"
    assert result.universe_id == UUID(universe_data["id"])
    assert result.story_type == StoryType.CAMPAIGN
    assert result.status == StoryStatus.PLANNED
    assert result.scene_count == 0
    assert mock_neo4j_client.execute_read.call_count == 1
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_story_with_pcs(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    pc_entity_data: Dict[str, Any],
):
    """Test story creation with PC participants."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe and PCs exist
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],  # Universe check
        [{"found_ids": [pc_entity_data["id"]]}],  # PC check
    ]

    # Mock story creation and PARTICIPATES edges
    mock_neo4j_client.execute_write.return_value = []

    pc_id = UUID(pc_entity_data["id"])
    params = StoryCreate(
        universe_id=UUID(universe_data["id"]),
        title="The Fellowship of the Ring",
        pc_ids=[pc_id],
    )

    result = neo4j_create_story(params)

    assert len(result.participant_ids) == 1
    assert result.participant_ids[0] == pc_id
    assert mock_neo4j_client.execute_write.call_count == 2  # Story + PARTICIPATES


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
        title="The Fellowship of the Ring",
    )

    with pytest.raises(ValueError, match="Universe .* not found"):
        neo4j_create_story(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_story_invalid_pc(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test story creation with invalid PC entity_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists, but PC doesn't
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],  # Universe check
        [{"found_ids": []}],  # PC check - empty
    ]

    params = StoryCreate(
        universe_id=UUID(universe_data["id"]),
        title="The Fellowship of the Ring",
        pc_ids=[uuid4()],
    )

    with pytest.raises(ValueError, match="PC entities not found"):
        neo4j_create_story(params)


# =============================================================================
# TESTS: neo4j_get_story
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_story_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
    pc_entity_data: Dict[str, Any],
):
    """Test successful story retrieval."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.return_value = [
        {
            "s": story_data,
            "scene_count": 3,
            "participant_ids": [pc_entity_data["id"]],
        }
    ]

    result = neo4j_get_story(UUID(story_data["id"]))

    assert result is not None
    assert result.id == UUID(story_data["id"])
    assert result.title == story_data["title"]
    assert result.scene_count == 3
    assert len(result.participant_ids) == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_story_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test story retrieval when story doesn't exist."""
    mock_get_client.return_value = mock_neo4j_client
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

    # Mock story exists
    mock_neo4j_client.execute_read.return_value = [{"id": story_data["id"]}]

    # Mock update
    updated_story = story_data.copy()
    updated_story["title"] = "The Two Towers"
    mock_neo4j_client.execute_write.return_value = [
        {
            "s": updated_story,
            "scene_count": 0,
            "participant_ids": [],
        }
    ]

    params = StoryUpdate(title="The Two Towers")
    result = neo4j_update_story(UUID(story_data["id"]), params)

    assert result.title == "The Two Towers"
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_story_status_to_completed(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test updating story status to completed."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock story exists
    mock_neo4j_client.execute_read.return_value = [{"id": story_data["id"]}]

    # Mock update
    updated_story = story_data.copy()
    updated_story["status"] = StoryStatus.COMPLETED.value
    updated_story["completed_at"] = "2024-12-01T00:00:00"
    mock_neo4j_client.execute_write.return_value = [
        {
            "s": updated_story,
            "scene_count": 5,
            "participant_ids": [],
        }
    ]

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


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_story_no_changes(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test updating story with no changes."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock story exists check, then the get_story call
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": story_data["id"]}],  # Story exists check
        [
            {
                "s": story_data,
                "scene_count": 0,
                "participant_ids": [],
            }
        ],  # get_story call
    ]

    params = StoryUpdate()  # No changes
    result = neo4j_update_story(UUID(story_data["id"]), params)

    assert result.id == UUID(story_data["id"])
    assert mock_neo4j_client.execute_write.call_count == 0  # No write executed


# =============================================================================
# TESTS: neo4j_list_stories
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_stories_all(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test listing all stories."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],  # Count
        [
            {
                "s": story_data,
                "scene_count": 0,
                "participant_ids": [],
            }
        ],  # List
    ]

    filters = StoryFilter()
    result = neo4j_list_stories(filters)

    assert result.total == 1
    assert len(result.stories) == 1
    assert result.stories[0].id == UUID(story_data["id"])


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_stories_by_universe(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    story_data: Dict[str, Any],
):
    """Test listing stories filtered by universe."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],  # Count
        [
            {
                "s": story_data,
                "scene_count": 2,
                "participant_ids": [],
            }
        ],  # List
    ]

    filters = StoryFilter(universe_id=UUID(universe_data["id"]))
    result = neo4j_list_stories(filters)

    assert result.total == 1
    assert len(result.stories) == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_stories_by_status(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test listing stories filtered by status."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],  # Count
        [
            {
                "s": story_data,
                "scene_count": 0,
                "participant_ids": [],
            }
        ],  # List
    ]

    filters = StoryFilter(status=StoryStatus.PLANNED)
    result = neo4j_list_stories(filters)

    assert result.total == 1
    assert result.stories[0].status == StoryStatus.PLANNED


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_stories_pagination(
    mock_get_client: Mock, mock_neo4j_client: Mock
):
    """Test listing stories with pagination."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and empty list (offset beyond results)
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 50}],  # Count
        [],  # Empty list at offset
    ]

    filters = StoryFilter(limit=10, offset=100)
    result = neo4j_list_stories(filters)

    assert result.total == 50
    assert len(result.stories) == 0
    assert result.limit == 10
    assert result.offset == 100


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_story_theme_and_premise(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test updating story theme and premise."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock story exists
    mock_neo4j_client.execute_read.return_value = [{"id": story_data["id"]}]

    # Mock update
    updated_story = story_data.copy()
    updated_story["theme"] = "Hope and Courage"
    updated_story["premise"] = "Updated premise"
    mock_neo4j_client.execute_write.return_value = [
        {
            "s": updated_story,
            "scene_count": 0,
            "participant_ids": [],
        }
    ]

    params = StoryUpdate(theme="Hope and Courage", premise="Updated premise")
    result = neo4j_update_story(UUID(story_data["id"]), params)

    assert result.theme == "Hope and Courage"
    assert result.premise == "Updated premise"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_stories_by_story_type(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test listing stories filtered by story_type."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count and list
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],  # Count
        [
            {
                "s": story_data,
                "scene_count": 0,
                "participant_ids": [],
            }
        ],  # List
    ]

    filters = StoryFilter(story_type=StoryType.CAMPAIGN)
    result = neo4j_list_stories(filters)

    assert result.total == 1
    assert result.stories[0].story_type == StoryType.CAMPAIGN
