"""
Unit tests for MongoDB story outline operations (DL-6).

Tests cover:
- mongodb_create_story_outline
- mongodb_get_story_outline
- mongodb_update_story_outline
"""

from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
from uuid import UUID, uuid4
from datetime import datetime, timezone

import pytest

from monitor_data.schemas.outlines import (
    OutlineBeat,
    StoryOutlineCreate,
    StoryOutlineUpdate,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_story_outline,
    mongodb_get_story_outline,
    mongodb_update_story_outline,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def story_id() -> UUID:
    """Provide a test story ID."""
    return uuid4()


@pytest.fixture
def outline_beats() -> list:
    """Provide sample outline beats."""
    return [
        OutlineBeat(title="Opening", description="Intro scene", order=0, status="pending"),
        OutlineBeat(title="Conflict", description="Main conflict", order=1, status="pending"),
        OutlineBeat(title="Resolution", description="Resolve conflict", order=2, status="pending"),
    ]


@pytest.fixture
def outline_doc(story_id: UUID, outline_beats: list) -> Dict[str, Any]:
    """Provide sample outline document as returned by MongoDB."""
    return {
        "_id": "mock_object_id",
        "story_id": str(story_id),
        "theme": "Adventure",
        "premise": "A hero's journey",
        "constraints": ["PG-13", "No time travel"],
        "beats": [beat.model_dump() for beat in outline_beats],
        "open_threads": ["Who is the villain?"],
        "pc_ids": [],
        "status": "draft",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


# =============================================================================
# TESTS: mongodb_create_story_outline
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
def test_create_outline_success(
    mock_get_neo4j: Mock,
    mock_get_mongo: Mock,
    story_id: UUID,
    outline_beats: list,
):
    """Test successful story outline creation."""
    # Mock Neo4j story exists check
    mock_neo4j_client = Mock()
    mock_neo4j_client.execute_read.return_value = [{"id": str(story_id)}]
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock MongoDB client
    mock_mongo_client = Mock()
    mock_db = MagicMock()
    mock_mongo_client.db = mock_db
    mock_get_mongo.return_value = mock_mongo_client

    params = StoryOutlineCreate(
        story_id=story_id,
        theme="Adventure",
        premise="A hero's journey",
        constraints=["PG-13", "No time travel"],
        beats=outline_beats,
        open_threads=["Who is the villain?"],
    )

    result = mongodb_create_story_outline(params)

    assert result.story_id == story_id
    assert result.theme == "Adventure"
    assert result.premise == "A hero's journey"
    assert len(result.beats) == 3
    assert result.beats[0].title == "Opening"
    assert result.status == "draft"
    assert mock_db.story_outlines.insert_one.call_count == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
def test_create_outline_invalid_story(
    mock_get_neo4j: Mock,
    mock_get_mongo: Mock,
):
    """Test outline creation with invalid story_id."""
    # Mock Neo4j story doesn't exist
    mock_neo4j_client = Mock()
    mock_neo4j_client.execute_read.return_value = []
    mock_get_neo4j.return_value = mock_neo4j_client

    params = StoryOutlineCreate(
        story_id=uuid4(),
        theme="Adventure",
    )

    with pytest.raises(ValueError, match="Story .* not found"):
        mongodb_create_story_outline(params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
def test_create_outline_minimal_params(
    mock_get_neo4j: Mock,
    mock_get_mongo: Mock,
    story_id: UUID,
):
    """Test outline creation with minimal parameters."""
    # Mock Neo4j story exists check
    mock_neo4j_client = Mock()
    mock_neo4j_client.execute_read.return_value = [{"id": str(story_id)}]
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock MongoDB client
    mock_mongo_client = Mock()
    mock_db = MagicMock()
    mock_mongo_client.db = mock_db
    mock_get_mongo.return_value = mock_mongo_client

    params = StoryOutlineCreate(story_id=story_id)

    result = mongodb_create_story_outline(params)

    assert result.story_id == story_id
    assert result.theme == ""
    assert result.premise == ""
    assert len(result.beats) == 0
    assert result.status == "draft"


# =============================================================================
# TESTS: mongodb_get_story_outline
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_outline_exists(
    mock_get_mongo: Mock,
    story_id: UUID,
    outline_doc: Dict[str, Any],
):
    """Test getting an existing outline."""
    mock_mongo_client = Mock()
    mock_db = MagicMock()
    mock_db.story_outlines.find_one.return_value = outline_doc
    mock_mongo_client.db = mock_db
    mock_get_mongo.return_value = mock_mongo_client

    result = mongodb_get_story_outline(story_id)

    assert result is not None
    assert result.story_id == story_id
    assert result.theme == "Adventure"
    assert len(result.beats) == 3
    assert result.beats[0].title == "Opening"
    assert result.status == "draft"


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_outline_not_found(mock_get_mongo: Mock):
    """Test getting a non-existent outline."""
    mock_mongo_client = Mock()
    mock_db = MagicMock()
    mock_db.story_outlines.find_one.return_value = None
    mock_mongo_client.db = mock_db
    mock_get_mongo.return_value = mock_mongo_client

    result = mongodb_get_story_outline(uuid4())

    assert result is None


# =============================================================================
# TESTS: mongodb_update_story_outline
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_outline_beats(
    mock_get_mongo: Mock,
    story_id: UUID,
    outline_doc: Dict[str, Any],
):
    """Test updating outline beats."""
    mock_mongo_client = Mock()
    mock_db = MagicMock()
    
    # Mock existing document check
    mock_db.story_outlines.find_one.side_effect = [
        outline_doc,  # First call: check existence
        {**outline_doc, "beats": [{"title": "New Beat", "description": "", "order": 0, "status": "pending"}]},  # Second call: return updated
    ]
    mock_mongo_client.db = mock_db
    mock_get_mongo.return_value = mock_mongo_client

    new_beats = [OutlineBeat(title="New Beat", description="", order=0, status="pending")]
    params = StoryOutlineUpdate(beats=new_beats)

    result = mongodb_update_story_outline(story_id, params)

    assert result.story_id == story_id
    assert len(result.beats) == 1
    assert result.beats[0].title == "New Beat"
    assert mock_db.story_outlines.update_one.call_count == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_outline_status(
    mock_get_mongo: Mock,
    story_id: UUID,
    outline_doc: Dict[str, Any],
):
    """Test updating outline status."""
    mock_mongo_client = Mock()
    mock_db = MagicMock()
    
    updated_doc = {**outline_doc, "status": "completed"}
    mock_db.story_outlines.find_one.side_effect = [
        outline_doc,  # First call: check existence
        updated_doc,  # Second call: return updated
    ]
    mock_mongo_client.db = mock_db
    mock_get_mongo.return_value = mock_mongo_client

    params = StoryOutlineUpdate(status="completed")

    result = mongodb_update_story_outline(story_id, params)

    assert result.status == "completed"
    assert mock_db.story_outlines.update_one.call_count == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_outline_not_found(mock_get_mongo: Mock):
    """Test updating a non-existent outline."""
    mock_mongo_client = Mock()
    mock_db = MagicMock()
    mock_db.story_outlines.find_one.return_value = None
    mock_mongo_client.db = mock_db
    mock_get_mongo.return_value = mock_mongo_client

    params = StoryOutlineUpdate(theme="New Theme")

    with pytest.raises(ValueError, match="Story outline .* not found"):
        mongodb_update_story_outline(uuid4(), params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_outline_multiple_fields(
    mock_get_mongo: Mock,
    story_id: UUID,
    outline_doc: Dict[str, Any],
):
    """Test updating multiple fields at once."""
    mock_mongo_client = Mock()
    mock_db = MagicMock()
    
    updated_doc = {
        **outline_doc,
        "theme": "Epic Fantasy",
        "premise": "New premise",
        "status": "active",
    }
    mock_db.story_outlines.find_one.side_effect = [
        outline_doc,  # First call: check existence
        updated_doc,  # Second call: return updated
    ]
    mock_mongo_client.db = mock_db
    mock_get_mongo.return_value = mock_mongo_client

    params = StoryOutlineUpdate(
        theme="Epic Fantasy",
        premise="New premise",
        status="active",
    )

    result = mongodb_update_story_outline(story_id, params)

    assert result.theme == "Epic Fantasy"
    assert result.premise == "New premise"
    assert result.status == "active"
    assert mock_db.story_outlines.update_one.call_count == 1
