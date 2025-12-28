"""
Unit tests for Neo4j plot thread operations (DL-6).

Tests cover:
- neo4j_create_plot_thread
- neo4j_list_plot_threads
- neo4j_update_plot_thread
- neo4j_advance_plot_thread
- neo4j_link_plot_to_fact
"""

from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.plot_threads import (
    ThreadType,
    ThreadStatus,
    PlotThreadCreate,
    PlotThreadUpdate,
    PlotThreadFilter,
    PlotThreadAdvancement,
    PlotThreadFactLink,
)
from monitor_data.schemas.base import CanonLevel, Authority
from monitor_data.tools.neo4j_tools import (
    neo4j_create_plot_thread,
    neo4j_list_plot_threads,
    neo4j_update_plot_thread,
    neo4j_advance_plot_thread,
    neo4j_link_plot_to_fact,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def story_id() -> UUID:
    """Provide a test story ID."""
    return uuid4()


@pytest.fixture
def thread_data(story_id: UUID) -> Dict[str, Any]:
    """Provide sample plot thread data."""
    return {
        "id": str(uuid4()),
        "story_id": str(story_id),
        "title": "Main Quest",
        "thread_type": ThreadType.MAIN.value,
        "description": "The hero's main journey",
        "status": ThreadStatus.ACTIVE.value,
        "canon_level": CanonLevel.CANON.value,
        "confidence": 1.0,
        "authority": Authority.GM.value,
        "created_at": "2024-01-01T00:00:00",
    }


# =============================================================================
# TESTS: neo4j_create_plot_thread
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_plot_thread_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_id: UUID,
):
    """Test successful plot thread creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock story exists check
    mock_neo4j_client.execute_read.return_value = [{"id": str(story_id)}]

    # Mock thread creation
    mock_neo4j_client.execute_write.return_value = []

    params = PlotThreadCreate(
        story_id=story_id,
        title="Main Quest",
        thread_type=ThreadType.MAIN,
        description="The hero's main journey",
    )

    result = neo4j_create_plot_thread(params)

    assert result.story_id == story_id
    assert result.title == "Main Quest"
    assert result.thread_type == ThreadType.MAIN
    assert result.status == ThreadStatus.ACTIVE
    assert result.canon_level == CanonLevel.CANON
    assert mock_neo4j_client.execute_read.call_count == 1
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_plot_thread_invalid_story(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test plot thread creation with invalid story_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock story doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = PlotThreadCreate(
        story_id=uuid4(),
        title="Main Quest",
        thread_type=ThreadType.MAIN,
    )

    with pytest.raises(ValueError, match="Story .* not found"):
        neo4j_create_plot_thread(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_plot_thread_all_types(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_id: UUID,
):
    """Test creating plot threads of different types."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = [{"id": str(story_id)}]
    mock_neo4j_client.execute_write.return_value = []

    thread_types = [
        ThreadType.MAIN,
        ThreadType.SUBPLOT,
        ThreadType.CHARACTER_ARC,
        ThreadType.MYSTERY,
        ThreadType.CONFLICT,
    ]

    for thread_type in thread_types:
        params = PlotThreadCreate(
            story_id=story_id,
            title=f"{thread_type.value.title()} Thread",
            thread_type=thread_type,
        )

        result = neo4j_create_plot_thread(params)
        assert result.thread_type == thread_type


# =============================================================================
# TESTS: neo4j_list_plot_threads
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_plot_threads_all(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    thread_data: Dict[str, Any],
):
    """Test listing all plot threads."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock count query
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],  # count query
        [{"t": thread_data}],  # list query
    ]

    filters = PlotThreadFilter()
    result = neo4j_list_plot_threads(filters)

    assert result.total == 1
    assert len(result.threads) == 1
    assert result.threads[0].title == "Main Quest"
    assert result.limit == 50
    assert result.offset == 0


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_threads_by_story(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_id: UUID,
    thread_data: Dict[str, Any],
):
    """Test listing plot threads filtered by story_id."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [{"t": thread_data}],
    ]

    filters = PlotThreadFilter(story_id=story_id)
    result = neo4j_list_plot_threads(filters)

    assert result.total == 1
    assert len(result.threads) == 1
    # Verify the query was called with story_id filter
    call_args = mock_neo4j_client.execute_read.call_args_list
    assert str(story_id) in str(call_args)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_threads_by_status(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    thread_data: Dict[str, Any],
):
    """Test listing plot threads filtered by status."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [{"t": thread_data}],
    ]

    filters = PlotThreadFilter(status=ThreadStatus.ACTIVE)
    result = neo4j_list_plot_threads(filters)

    assert result.total == 1
    assert result.threads[0].status == ThreadStatus.ACTIVE


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_threads_by_type(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    thread_data: Dict[str, Any],
):
    """Test listing plot threads filtered by thread_type."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],
        [{"t": thread_data}],
    ]

    filters = PlotThreadFilter(thread_type=ThreadType.MAIN)
    result = neo4j_list_plot_threads(filters)

    assert result.total == 1
    assert result.threads[0].thread_type == ThreadType.MAIN


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_threads_empty(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test listing plot threads when none exist."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 0}],
        [],
    ]

    filters = PlotThreadFilter()
    result = neo4j_list_plot_threads(filters)

    assert result.total == 0
    assert len(result.threads) == 0


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_threads_pagination(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    thread_data: Dict[str, Any],
):
    """Test listing plot threads with pagination."""
    mock_get_client.return_value = mock_neo4j_client

    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 100}],
        [{"t": thread_data}],
    ]

    filters = PlotThreadFilter(limit=10, offset=20)
    result = neo4j_list_plot_threads(filters)

    assert result.total == 100
    assert result.limit == 10
    assert result.offset == 20


# =============================================================================
# TESTS: neo4j_update_plot_thread
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_plot_thread_status(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    thread_data: Dict[str, Any],
):
    """Test updating plot thread status."""
    mock_get_client.return_value = mock_neo4j_client

    thread_id = UUID(thread_data["id"])
    updated_data = {**thread_data, "status": ThreadStatus.RESOLVED.value}

    # Mock verification and update
    mock_neo4j_client.execute_read.return_value = [{"id": str(thread_id)}]
    mock_neo4j_client.execute_write.return_value = [{"t": updated_data}]

    params = PlotThreadUpdate(status=ThreadStatus.RESOLVED)
    result = neo4j_update_plot_thread(thread_id, params)

    assert result.id == thread_id
    assert result.status == ThreadStatus.RESOLVED
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_plot_thread_description(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    thread_data: Dict[str, Any],
):
    """Test updating plot thread description."""
    mock_get_client.return_value = mock_neo4j_client

    thread_id = UUID(thread_data["id"])
    updated_data = {**thread_data, "description": "Updated description"}

    mock_neo4j_client.execute_read.return_value = [{"id": str(thread_id)}]
    mock_neo4j_client.execute_write.return_value = [{"t": updated_data}]

    params = PlotThreadUpdate(description="Updated description")
    result = neo4j_update_plot_thread(thread_id, params)

    assert result.description == "Updated description"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_plot_thread_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test updating a non-existent plot thread."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    params = PlotThreadUpdate(status=ThreadStatus.RESOLVED)

    with pytest.raises(ValueError, match="PlotThread .* not found"):
        neo4j_update_plot_thread(uuid4(), params)


# =============================================================================
# TESTS: neo4j_advance_plot_thread
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_advance_plot_thread_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test advancing a plot thread with a scene."""
    mock_get_client.return_value = mock_neo4j_client

    thread_id = uuid4()
    scene_id = uuid4()

    # Mock thread exists check
    mock_neo4j_client.execute_read.return_value = [{"id": str(thread_id)}]
    mock_neo4j_client.execute_write.return_value = [{"r": {}}]

    params = PlotThreadAdvancement(
        scene_id=scene_id,
        advancement_note="Hero defeats the dragon",
    )

    result = neo4j_advance_plot_thread(thread_id, params)

    assert result["thread_id"] == str(thread_id)
    assert result["scene_id"] == str(scene_id)
    assert result["advancement_note"] == "Hero defeats the dragon"
    assert "created_at" in result
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_advance_plot_thread_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test advancing a non-existent plot thread."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    params = PlotThreadAdvancement(scene_id=uuid4())

    with pytest.raises(ValueError, match="PlotThread .* not found"):
        neo4j_advance_plot_thread(uuid4(), params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_advance_plot_thread_no_note(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test advancing a plot thread without a note."""
    mock_get_client.return_value = mock_neo4j_client

    thread_id = uuid4()
    scene_id = uuid4()

    mock_neo4j_client.execute_read.return_value = [{"id": str(thread_id)}]
    mock_neo4j_client.execute_write.return_value = [{"r": {}}]

    params = PlotThreadAdvancement(scene_id=scene_id)

    result = neo4j_advance_plot_thread(thread_id, params)

    assert result["advancement_note"] == ""


# =============================================================================
# TESTS: neo4j_link_plot_to_fact
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_link_plot_to_fact_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test linking a plot thread to a fact."""
    mock_get_client.return_value = mock_neo4j_client

    thread_id = uuid4()
    fact_id = uuid4()

    # Mock thread exists, then fact exists
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": str(thread_id)}],  # thread exists
        [{"id": str(fact_id)}],     # fact exists
    ]
    mock_neo4j_client.execute_write.return_value = [{"r": {}}]

    params = PlotThreadFactLink(
        fact_id=fact_id,
        link_type="resolves",
    )

    result = neo4j_link_plot_to_fact(thread_id, params)

    assert result["thread_id"] == str(thread_id)
    assert result["fact_id"] == str(fact_id)
    assert result["link_type"] == "resolves"
    assert "created_at" in result
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_link_plot_to_fact_thread_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test linking when thread doesn't exist."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    params = PlotThreadFactLink(fact_id=uuid4())

    with pytest.raises(ValueError, match="PlotThread .* not found"):
        neo4j_link_plot_to_fact(uuid4(), params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_link_plot_to_fact_fact_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test linking when fact doesn't exist."""
    mock_get_client.return_value = mock_neo4j_client

    thread_id = uuid4()
    
    # Thread exists, but fact doesn't
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": str(thread_id)}],  # thread exists
        [],                         # fact doesn't exist
    ]

    params = PlotThreadFactLink(fact_id=uuid4())

    with pytest.raises(ValueError, match="Fact/Event .* not found"):
        neo4j_link_plot_to_fact(thread_id, params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_link_plot_to_fact_default_link_type(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test linking with default link_type."""
    mock_get_client.return_value = mock_neo4j_client

    thread_id = uuid4()
    fact_id = uuid4()

    mock_neo4j_client.execute_read.side_effect = [
        [{"id": str(thread_id)}],
        [{"id": str(fact_id)}],
    ]
    mock_neo4j_client.execute_write.return_value = [{"r": {}}]

    params = PlotThreadFactLink(fact_id=fact_id)

    result = neo4j_link_plot_to_fact(thread_id, params)

    assert result["link_type"] == "relates_to"
