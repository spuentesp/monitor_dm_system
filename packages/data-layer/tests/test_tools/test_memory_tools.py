"""
Tests for character memory CRUD and vector operations.

Tests MongoDB storage, Qdrant embeddings, and semantic search for memories.
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from monitor_data.tools.mongodb_tools import (
    mongodb_create_memory,
    mongodb_get_memory,
    mongodb_list_memories,
    mongodb_update_memory,
    mongodb_delete_memory,
)
from monitor_data.tools.qdrant_tools import (
    qdrant_embed_memory,
    qdrant_search_memories,
)
from monitor_data.schemas.memories import (
    MemoryCreate,
    MemoryUpdate,
    MemoryFilter,
    MemoryEmbedRequest,
    MemorySearchRequest,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def entity_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample entity data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": "Test Character",
        "entity_type": "character",
    }


@pytest.fixture
def scene_data(
    story_data: Dict[str, Any], universe_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Provide sample scene data."""
    return {
        "scene_id": str(uuid4()),
        "story_id": story_data["id"],
        "universe_id": universe_data["id"],
        "title": "Test Scene",
    }


@pytest.fixture
def memory_data(entity_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample memory data."""
    return {
        "memory_id": str(uuid4()),
        "entity_id": entity_data["id"],
        "text": "I remember you saved my life",
        "scene_id": None,
        "linked_fact_id": None,
        "emotional_valence": 0.8,
        "importance": 0.9,
        "certainty": 1.0,
        "metadata": {},
        "created_at": datetime.now(timezone.utc),
        "last_accessed": datetime.now(timezone.utc),
        "access_count": 0,
    }


# =============================================================================
# MONGODB MEMORY CRUD TESTS
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_memory_success(
    mock_mongo_client: Mock,
    mock_neo4j_client: Mock,
    entity_data: Dict[str, Any],
):
    """Test creating a memory with valid parameters."""
    # Mock Neo4j entity check
    mock_neo4j_client.return_value.execute_read.return_value = [
        {"id": entity_data["id"]}
    ]

    # Mock MongoDB insert
    mock_collection = Mock()
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    params = MemoryCreate(
        entity_id=UUID(entity_data["id"]),
        text="I remember you saved my life in the dragon's lair",
        importance=0.9,
        emotional_valence=0.8,
        certainty=1.0,
        metadata={"tags": ["heroic", "grateful"]},
    )

    memory = mongodb_create_memory(params)

    assert memory.entity_id == UUID(entity_data["id"])
    assert memory.text == params.text
    assert memory.importance == 0.9
    assert memory.emotional_valence == 0.8
    assert memory.certainty == 1.0
    assert memory.metadata == {"tags": ["heroic", "grateful"]}
    assert memory.access_count == 0
    assert isinstance(memory.created_at, datetime)
    mock_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_memory_with_scene(
    mock_mongo_client: Mock,
    mock_neo4j_client: Mock,
    entity_data: Dict[str, Any],
    scene_data: Dict[str, Any],
):
    """Test creating a memory linked to a scene."""
    # Mock Neo4j entity check
    mock_neo4j_client.return_value.execute_read.return_value = [
        {"id": entity_data["id"]}
    ]

    # Mock MongoDB scene check
    mock_scenes_collection = Mock()
    mock_scenes_collection.find_one.return_value = scene_data
    mock_memories_collection = Mock()

    def get_collection_side_effect(name):
        if name == "scenes":
            return mock_scenes_collection
        elif name == "character_memories":
            return mock_memories_collection
        return Mock()

    mock_mongo_client.return_value.get_collection.side_effect = (
        get_collection_side_effect
    )

    params = MemoryCreate(
        entity_id=UUID(entity_data["id"]),
        text="The dragon breathed fire and I barely escaped",
        scene_id=UUID(scene_data["scene_id"]),
        importance=0.8,
    )

    memory = mongodb_create_memory(params)

    assert memory.scene_id == UUID(scene_data["scene_id"])
    assert memory.text == params.text


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
def test_create_memory_invalid_entity(mock_neo4j_client: Mock, mock_mongo_client: Mock):
    """Test creating a memory with non-existent entity fails."""
    # Mock Neo4j entity check returning empty
    mock_neo4j_client.return_value.execute_read.return_value = []

    fake_entity_id = uuid4()
    params = MemoryCreate(
        entity_id=fake_entity_id,
        text="This should fail",
        importance=0.5,
    )

    with pytest.raises(ValueError, match="Entity .* not found"):
        mongodb_create_memory(params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_memory(mock_mongo_client: Mock, memory_data: Dict[str, Any]):
    """Test retrieving a memory by ID."""
    # Mock MongoDB find_one_and_update
    updated_memory_data = memory_data.copy()
    updated_memory_data["access_count"] = 1

    mock_collection = Mock()
    mock_collection.find_one_and_update.return_value = updated_memory_data
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    memory = mongodb_get_memory(UUID(memory_data["memory_id"]))

    assert memory.memory_id == UUID(memory_data["memory_id"])
    assert memory.text == memory_data["text"]
    assert memory.access_count == 1
    mock_collection.find_one_and_update.assert_called_once()


def test_get_memory_not_found():
    """Test getting a non-existent memory raises error."""
    with patch("monitor_data.tools.mongodb_tools.get_mongodb_client") as mock_mongo:
        mock_collection = Mock()
        mock_collection.find_one_and_update.return_value = None
        mock_mongo.return_value.get_collection.return_value = mock_collection

        fake_id = uuid4()
        with pytest.raises(ValueError, match="Memory .* not found"):
            mongodb_get_memory(fake_id)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_memories(mock_mongo_client: Mock, entity_data: Dict[str, Any]):
    """Test listing memories with filters."""
    # Create mock memories
    mock_memories = []
    for i in range(5):
        mock_memories.append(
            {
                "memory_id": str(uuid4()),
                "entity_id": entity_data["id"],
                "text": f"Memory {i}",
                "scene_id": None,
                "linked_fact_id": None,
                "importance": 0.1 * (i + 1),
                "emotional_valence": 0.0,
                "certainty": 1.0,
                "metadata": {},
                "created_at": datetime.now(timezone.utc),
                "last_accessed": datetime.now(timezone.utc),
                "access_count": 0,
            }
        )

    mock_collection = Mock()
    mock_collection.count_documents.return_value = 5
    mock_cursor = MagicMock()  # Use MagicMock for iterators
    mock_cursor.__iter__.return_value = iter(mock_memories)
    mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
        mock_cursor
    )
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    filter_params = MemoryFilter(entity_id=UUID(entity_data["id"]), limit=100, offset=0)
    result = mongodb_list_memories(filter_params)

    assert result.total == 5
    assert len(result.memories) == 5


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_memory(mock_mongo_client: Mock, memory_data: Dict[str, Any]):
    """Test updating memory fields."""
    # Mock update_one and get_memory
    mock_collection = Mock()
    mock_collection.update_one.return_value.matched_count = 1

    # Mock find_one_and_update for get_memory call
    updated_data = memory_data.copy()
    updated_data["importance"] = 0.9
    updated_data["certainty"] = 0.6
    updated_data["access_count"] = 1
    mock_collection.find_one_and_update.return_value = updated_data

    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    update_params = MemoryUpdate(importance=0.9, certainty=0.6)
    updated = mongodb_update_memory(UUID(memory_data["memory_id"]), update_params)

    assert updated.importance == 0.9
    assert updated.certainty == 0.6


def test_update_memory_not_found():
    """Test updating non-existent memory raises error."""
    with patch("monitor_data.tools.mongodb_tools.get_mongodb_client") as mock_mongo:
        mock_collection = Mock()
        mock_collection.update_one.return_value.matched_count = 0
        mock_mongo.return_value.get_collection.return_value = mock_collection

        fake_id = uuid4()
        update_params = MemoryUpdate(importance=0.9)

        with pytest.raises(ValueError, match="Memory .* not found"):
            mongodb_update_memory(fake_id, update_params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_delete_memory(mock_mongo_client: Mock, memory_data: Dict[str, Any]):
    """Test deleting a memory."""
    mock_collection = Mock()
    mock_collection.delete_one.return_value.deleted_count = 1
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    result = mongodb_delete_memory(UUID(memory_data["memory_id"]))
    assert result is True


def test_delete_memory_not_found():
    """Test deleting non-existent memory returns False."""
    with patch("monitor_data.tools.mongodb_tools.get_mongodb_client") as mock_mongo:
        mock_collection = Mock()
        mock_collection.delete_one.return_value.deleted_count = 0
        mock_mongo.return_value.get_collection.return_value = mock_collection

        fake_id = uuid4()
        result = mongodb_delete_memory(fake_id)
        assert result is False


# =============================================================================
# QDRANT VECTOR OPERATIONS TESTS
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_embed_memory(mock_qdrant_client: Mock, memory_data: Dict[str, Any]):
    """Test embedding a memory in Qdrant."""
    mock_client = Mock()
    mock_client.ensure_collection.return_value = None
    mock_client.embed_text.return_value = [0.1] * 1536  # Mock embedding
    mock_qdrant = Mock()
    mock_client.get_client.return_value = mock_qdrant
    mock_qdrant_client.return_value = mock_client

    embed_params = MemoryEmbedRequest(
        memory_id=UUID(memory_data["memory_id"]),
        text=memory_data["text"],
        entity_id=UUID(memory_data["entity_id"]),
        importance=memory_data["importance"],
    )
    result = qdrant_embed_memory(embed_params)

    assert result.success is True
    assert result.memory_id == UUID(memory_data["memory_id"])
    assert result.collection == "memories"
    mock_qdrant.upsert.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_memories(mock_qdrant_client: Mock, entity_data: Dict[str, Any]):
    """Test semantic search across memories."""
    mock_client = Mock()
    mock_client.ensure_collection.return_value = None
    mock_client.embed_text.return_value = [0.1] * 1536

    # Mock search results
    mock_qdrant = Mock()
    mock_scored_point = Mock()
    mock_scored_point.score = 0.95
    mock_scored_point.payload = {
        "memory_id": str(uuid4()),
        "entity_id": entity_data["id"],
        "scene_id": None,
        "importance": 0.8,
        "type": "memory",
    }
    mock_qdrant.search.return_value = [mock_scored_point]
    mock_client.get_client.return_value = mock_qdrant
    mock_qdrant_client.return_value = mock_client

    search_params = MemorySearchRequest(
        query_text="fire breathing dragon",
        entity_id=UUID(entity_data["id"]),
        top_k=3,
    )
    result = qdrant_search_memories(search_params)

    assert len(result.results) == 1
    assert result.query == "fire breathing dragon"
    assert result.results[0].entity_id == UUID(entity_data["id"])
    assert result.results[0].score == 0.95


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_memories_importance_filter(
    mock_qdrant_client: Mock, entity_data: Dict[str, Any]
):
    """Test searching memories with importance threshold."""
    mock_client = Mock()
    mock_client.ensure_collection.return_value = None
    mock_client.embed_text.return_value = [0.1] * 1536

    # Mock search results with different importance levels
    mock_qdrant = Mock()
    mock_scored_points = []
    for importance in [0.3, 0.6, 0.9]:
        mock_point = Mock()
        mock_point.score = 0.9
        mock_point.payload = {
            "memory_id": str(uuid4()),
            "entity_id": entity_data["id"],
            "scene_id": None,
            "importance": importance,
            "type": "memory",
        }
        mock_scored_points.append(mock_point)

    mock_qdrant.search.return_value = mock_scored_points
    mock_client.get_client.return_value = mock_qdrant
    mock_qdrant_client.return_value = mock_client

    search_params = MemorySearchRequest(
        query_text="memory",
        entity_id=UUID(entity_data["id"]),
        min_importance=0.5,
        top_k=10,
    )
    result = qdrant_search_memories(search_params)

    # Should filter out importance < 0.5
    assert all(r.importance >= 0.5 for r in result.results)
    assert len(result.results) == 2  # 0.6 and 0.9
