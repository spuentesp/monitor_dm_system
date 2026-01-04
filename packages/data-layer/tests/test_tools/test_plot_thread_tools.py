"""
Unit tests for Neo4j plot thread operations (DL-6).

Tests cover:
- neo4j_create_plot_thread
- neo4j_get_plot_thread
- neo4j_update_plot_thread
- neo4j_list_plot_threads
"""

from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4
from datetime import datetime

import pytest

from monitor_data.schemas.story_outlines import (
    PlotThreadCreate,
    PlotThreadUpdate,
    PlotThreadFilter,
    ThreadDeadline,
)
from monitor_data.schemas.base import (
    PlotThreadType,
    PlotThreadStatus,
    ThreadPriority,
    ThreadUrgency,
    PayoffStatus,
)
from monitor_data.tools.neo4j_tools import (
    neo4j_create_plot_thread,
    neo4j_get_plot_thread,
    neo4j_update_plot_thread,
    neo4j_list_plot_threads,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def plot_thread_data(story_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample plot thread data."""
    return {
        "id": str(uuid4()),
        "story_id": story_data["id"],
        "title": "The Missing Artifact",
        "thread_type": PlotThreadType.MAIN.value,
        "status": PlotThreadStatus.OPEN.value,
        "priority": ThreadPriority.MAIN.value,
        "urgency": ThreadUrgency.MEDIUM.value,
        "deadline": None,
        "payoff_status": PayoffStatus.SETUP_ONLY.value,
        "player_interest_level": 0.7,
        "gm_importance": 0.9,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "resolved_at": None,
    }


@pytest.fixture
def entity_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample entity data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": "Lord Blackwood",
        "entity_type": "character",
    }


@pytest.fixture
def scene_node_data(story_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample scene node data."""
    return {
        "id": str(uuid4()),
        "story_id": story_data["id"],
        "title": "The Investigation Begins",
    }


@pytest.fixture
def event_node_data() -> Dict[str, Any]:
    """Provide sample event node data."""
    return {
        "id": str(uuid4()),
        "description": "The artifact was stolen",
    }


# =============================================================================
# TESTS: neo4j_create_plot_thread
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_plot_thread_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
    plot_thread_data: Dict[str, Any],
):
    """Test successful plot thread creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock story exists check
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": story_data["id"]}],  # Story exists verification
        [
            {  # Return created thread with relationships
                "t": plot_thread_data,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    # Mock write operations
    mock_neo4j_client.execute_write.return_value = Mock()

    params = PlotThreadCreate(
        story_id=UUID(story_data["id"]),
        title="The Missing Artifact",
        thread_type=PlotThreadType.MAIN,
        priority=ThreadPriority.MAIN,
        urgency=ThreadUrgency.MEDIUM,
        player_interest_level=0.7,
        gm_importance=0.9,
    )

    result = neo4j_create_plot_thread(params)

    assert result.story_id == UUID(story_data["id"])
    assert result.title == "The Missing Artifact"
    assert result.thread_type == PlotThreadType.MAIN
    assert result.priority == ThreadPriority.MAIN
    assert result.urgency == ThreadUrgency.MEDIUM
    assert result.status == PlotThreadStatus.OPEN
    assert result.player_interest_level == 0.7
    assert result.gm_importance == 0.9

    # Verify story exists check was called
    assert mock_neo4j_client.execute_read.call_count >= 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_plot_thread_with_relationships(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
    plot_thread_data: Dict[str, Any],
    entity_data: Dict[str, Any],
    scene_node_data: Dict[str, Any],
    event_node_data: Dict[str, Any],
):
    """Test creating plot thread with relationships."""
    mock_get_client.return_value = mock_neo4j_client

    scene_id = UUID(scene_node_data["id"])
    entity_id = UUID(entity_data["id"])
    event_id = UUID(event_node_data["id"])

    # Mock responses
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": story_data["id"]}],  # Story exists
        [
            {  # Return with relationships
                "t": plot_thread_data,
                "scene_ids": [str(scene_id)],
                "entity_ids": [str(entity_id)],
                "foreshadowing_event_ids": [str(event_id)],
                "revelation_event_ids": [],
            }
        ],
    ]

    mock_neo4j_client.execute_write.return_value = Mock()

    params = PlotThreadCreate(
        story_id=UUID(story_data["id"]),
        title="The Missing Artifact",
        thread_type=PlotThreadType.MAIN,
        priority=ThreadPriority.MAIN,
        scene_ids=[scene_id],
        entity_ids=[entity_id],
        foreshadowing_events=[event_id],
    )

    result = neo4j_create_plot_thread(params)

    assert len(result.scene_ids) == 1
    assert result.scene_ids[0] == scene_id
    assert len(result.entity_ids) == 1
    assert result.entity_ids[0] == entity_id
    assert len(result.foreshadowing_events) == 1
    assert result.foreshadowing_events[0] == event_id

    # Verify relationship creation calls
    assert mock_neo4j_client.execute_write.call_count >= 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_plot_thread_with_deadline(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
    plot_thread_data: Dict[str, Any],
):
    """Test creating plot thread with deadline."""
    mock_get_client.return_value = mock_neo4j_client

    deadline_time = datetime.utcnow()
    thread_with_deadline = plot_thread_data.copy()
    thread_with_deadline["deadline"] = {
        "world_time": deadline_time.isoformat(),
        "description": "Before the kingdom falls",
    }

    mock_neo4j_client.execute_read.side_effect = [
        [{"id": story_data["id"]}],
        [
            {
                "t": thread_with_deadline,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    mock_neo4j_client.execute_write.return_value = Mock()

    deadline = ThreadDeadline(
        world_time=deadline_time,
        description="Before the kingdom falls",
    )

    params = PlotThreadCreate(
        story_id=UUID(story_data["id"]),
        title="Save the Kingdom",
        thread_type=PlotThreadType.MAIN,
        priority=ThreadPriority.MAIN,
        urgency=ThreadUrgency.CRITICAL,
        deadline=deadline,
    )

    result = neo4j_create_plot_thread(params)

    assert result.deadline is not None
    assert result.deadline.description == "Before the kingdom falls"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_plot_thread_story_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test plot thread creation fails when story doesn't exist."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []  # Story not found

    params = PlotThreadCreate(
        story_id=uuid4(),
        title="Test Thread",
        thread_type=PlotThreadType.MAIN,
        priority=ThreadPriority.MAIN,
    )

    with pytest.raises(ValueError, match="not found"):
        neo4j_create_plot_thread(params)


# =============================================================================
# TESTS: neo4j_get_plot_thread
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_plot_thread_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test successful plot thread retrieval."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.return_value = [
        {
            "t": plot_thread_data,
            "scene_ids": [],
            "entity_ids": [],
            "foreshadowing_event_ids": [],
            "revelation_event_ids": [],
        }
    ]

    thread_id = UUID(plot_thread_data["id"])
    result = neo4j_get_plot_thread(thread_id)

    assert result is not None
    assert result.id == thread_id
    assert result.title == "The Missing Artifact"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_plot_thread_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test plot thread retrieval when thread doesn't exist."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_plot_thread(uuid4())

    assert result is None


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_plot_thread_with_relationships(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test getting plot thread with all relationships populated."""
    mock_get_client.return_value = mock_neo4j_client

    scene_id = str(uuid4())
    entity_id = str(uuid4())
    foreshadow_id = str(uuid4())
    reveal_id = str(uuid4())

    mock_neo4j_client.execute_read.return_value = [
        {
            "t": plot_thread_data,
            "scene_ids": [scene_id],
            "entity_ids": [entity_id],
            "foreshadowing_event_ids": [foreshadow_id],
            "revelation_event_ids": [reveal_id],
        }
    ]

    result = neo4j_get_plot_thread(UUID(plot_thread_data["id"]))

    assert result is not None
    assert len(result.scene_ids) == 1
    assert str(result.scene_ids[0]) == scene_id
    assert len(result.entity_ids) == 1
    assert str(result.entity_ids[0]) == entity_id
    assert len(result.foreshadowing_events) == 1
    assert str(result.foreshadowing_events[0]) == foreshadow_id
    assert len(result.revelation_events) == 1
    assert str(result.revelation_events[0]) == reveal_id


# =============================================================================
# TESTS: neo4j_update_plot_thread
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_plot_thread_title(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test updating plot thread title."""
    mock_get_client.return_value = mock_neo4j_client

    # First read: get existing, second read: get updated
    existing_thread = plot_thread_data.copy()
    updated_thread = plot_thread_data.copy()
    updated_thread["title"] = "Updated Thread Title"

    mock_neo4j_client.execute_read.side_effect = [
        [
            {
                "t": existing_thread,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
        [
            {
                "t": updated_thread,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    mock_neo4j_client.execute_write.return_value = Mock()

    params = PlotThreadUpdate(
        title="Updated Thread Title",
    )

    result = neo4j_update_plot_thread(UUID(plot_thread_data["id"]), params)

    assert result.title == "Updated Thread Title"

    # Verify update was called
    mock_neo4j_client.execute_write.assert_called_once()


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_plot_thread_status_valid_transition(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test valid status transition."""
    mock_get_client.return_value = mock_neo4j_client

    existing_thread = plot_thread_data.copy()
    existing_thread["status"] = PlotThreadStatus.OPEN.value

    updated_thread = plot_thread_data.copy()
    updated_thread["status"] = PlotThreadStatus.ADVANCED.value

    mock_neo4j_client.execute_read.side_effect = [
        [
            {
                "t": existing_thread,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
        [
            {
                "t": updated_thread,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    mock_neo4j_client.execute_write.return_value = Mock()

    params = PlotThreadUpdate(
        status=PlotThreadStatus.ADVANCED,
    )

    result = neo4j_update_plot_thread(UUID(plot_thread_data["id"]), params)

    assert result.status == PlotThreadStatus.ADVANCED


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_plot_thread_status_invalid_transition(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test invalid status transition is rejected."""
    mock_get_client.return_value = mock_neo4j_client

    existing_thread = plot_thread_data.copy()
    existing_thread["status"] = PlotThreadStatus.RESOLVED.value

    mock_neo4j_client.execute_read.return_value = [
        {
            "t": existing_thread,
            "scene_ids": [],
            "entity_ids": [],
            "foreshadowing_event_ids": [],
            "revelation_event_ids": [],
        }
    ]

    params = PlotThreadUpdate(
        status=PlotThreadStatus.OPEN,  # Can't go back from resolved
    )

    with pytest.raises(ValueError, match="Invalid status transition"):
        neo4j_update_plot_thread(UUID(plot_thread_data["id"]), params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_plot_thread_resolve_sets_timestamp(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test that resolving a thread sets resolved_at timestamp."""
    mock_get_client.return_value = mock_neo4j_client

    existing_thread = plot_thread_data.copy()
    existing_thread["status"] = PlotThreadStatus.ADVANCED.value

    updated_thread = plot_thread_data.copy()
    updated_thread["status"] = PlotThreadStatus.RESOLVED.value
    updated_thread["resolved_at"] = datetime.utcnow()

    mock_neo4j_client.execute_read.side_effect = [
        [
            {
                "t": existing_thread,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
        [
            {
                "t": updated_thread,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    mock_neo4j_client.execute_write.return_value = Mock()

    params = PlotThreadUpdate(
        status=PlotThreadStatus.RESOLVED,
    )

    result = neo4j_update_plot_thread(UUID(plot_thread_data["id"]), params)

    assert result.status == PlotThreadStatus.RESOLVED
    assert result.resolved_at is not None


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_plot_thread_add_scenes(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test adding scene relationships to plot thread."""
    mock_get_client.return_value = mock_neo4j_client

    existing_thread = plot_thread_data.copy()
    new_scene_id = uuid4()

    updated_thread = plot_thread_data.copy()

    mock_neo4j_client.execute_read.side_effect = [
        [
            {
                "t": existing_thread,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
        [
            {
                "t": updated_thread,
                "scene_ids": [str(new_scene_id)],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    mock_neo4j_client.execute_write.return_value = Mock()

    params = PlotThreadUpdate(
        add_scene_ids=[new_scene_id],
    )

    result = neo4j_update_plot_thread(UUID(plot_thread_data["id"]), params)

    assert len(result.scene_ids) == 1
    assert result.scene_ids[0] == new_scene_id


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_plot_thread_add_entities(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test adding entity relationships to plot thread."""
    mock_get_client.return_value = mock_neo4j_client

    existing_thread = plot_thread_data.copy()
    new_entity_id = uuid4()

    updated_thread = plot_thread_data.copy()

    mock_neo4j_client.execute_read.side_effect = [
        [
            {
                "t": existing_thread,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
        [
            {
                "t": updated_thread,
                "scene_ids": [],
                "entity_ids": [str(new_entity_id)],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    mock_neo4j_client.execute_write.return_value = Mock()

    params = PlotThreadUpdate(
        add_entity_ids=[new_entity_id],
    )

    result = neo4j_update_plot_thread(UUID(plot_thread_data["id"]), params)

    assert len(result.entity_ids) == 1
    assert result.entity_ids[0] == new_entity_id


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_plot_thread_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test updating non-existent plot thread."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    params = PlotThreadUpdate(title="New Title")

    with pytest.raises(ValueError, match="not found"):
        neo4j_update_plot_thread(uuid4(), params)


# =============================================================================
# TESTS: neo4j_list_plot_threads
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_plot_threads_all(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test listing all plot threads."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],  # Count
        [
            {  # List results
                "t": plot_thread_data,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    params = PlotThreadFilter()

    result = neo4j_list_plot_threads(params)

    assert result.total == 1
    assert len(result.threads) == 1
    assert result.threads[0].title == "The Missing Artifact"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_plot_threads_filter_by_story(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
    story_data: Dict[str, Any],
):
    """Test filtering plot threads by story."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [
            {
                "t": plot_thread_data,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    params = PlotThreadFilter(
        story_id=UUID(story_data["id"]),
    )

    result = neo4j_list_plot_threads(params)

    assert result.total == 1
    assert result.threads[0].story_id == UUID(story_data["id"])


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_plot_threads_filter_by_type(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test filtering plot threads by type."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [
            {
                "t": plot_thread_data,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    params = PlotThreadFilter(
        thread_type=PlotThreadType.MAIN,
    )

    result = neo4j_list_plot_threads(params)

    assert result.total == 1
    assert result.threads[0].thread_type == PlotThreadType.MAIN


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_plot_threads_filter_by_status(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test filtering plot threads by status."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [
            {
                "t": plot_thread_data,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    params = PlotThreadFilter(
        status=PlotThreadStatus.OPEN,
    )

    result = neo4j_list_plot_threads(params)

    assert result.total == 1
    assert result.threads[0].status == PlotThreadStatus.OPEN


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_plot_threads_filter_by_entity(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
    entity_data: Dict[str, Any],
):
    """Test filtering plot threads by involved entity."""
    mock_get_client.return_value = mock_neo4j_client

    entity_id = UUID(entity_data["id"])

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [
            {
                "t": plot_thread_data,
                "scene_ids": [],
                "entity_ids": [str(entity_id)],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    params = PlotThreadFilter(
        entity_id=entity_id,
    )

    result = neo4j_list_plot_threads(params)

    assert result.total == 1
    assert entity_id in result.threads[0].entity_ids


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_plot_threads_pagination(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test plot thread pagination."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 10}],  # Total count
        [
            {  # Single result (second page)
                "t": plot_thread_data,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    params = PlotThreadFilter(
        limit=1,
        offset=1,
    )

    result = neo4j_list_plot_threads(params)

    assert result.total == 10
    assert result.limit == 1
    assert result.offset == 1
    assert len(result.threads) == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_plot_threads_sorting(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    plot_thread_data: Dict[str, Any],
):
    """Test plot thread sorting."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [
            {
                "t": plot_thread_data,
                "scene_ids": [],
                "entity_ids": [],
                "foreshadowing_event_ids": [],
                "revelation_event_ids": [],
            }
        ],
    ]

    params = PlotThreadFilter(
        sort_by="urgency",
        sort_order="desc",
    )

    result = neo4j_list_plot_threads(params)

    assert result.total == 1
    # Verify query was built correctly by checking it executed
    assert mock_neo4j_client.execute_read.call_count == 2
