"""
Unit tests for MongoDB and Qdrant memory operations (DL-7).

Tests cover:
- mongodb_create_memory
- mongodb_get_memory
- mongodb_list_memories
- mongodb_update_memory
- mongodb_delete_memory
- qdrant_embed_memory
- qdrant_search_memories
- qdrant_delete_memory
"""

from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.memories import (
    MemoryCreate,
    MemoryUpdate,
    MemoryFilter,
    MemorySearchQuery,
)
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
    qdrant_delete_memory,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def entity_id() -> UUID:
    """Provide a test entity ID."""
    return uuid4()


@pytest.fixture
def memory_id() -> UUID:
    """Provide a test memory ID."""
    return uuid4()


@pytest.fixture
def scene_id() -> UUID:
    """Provide a test scene ID."""
    return uuid4()


@pytest.fixture
def fact_id() -> UUID:
    """Provide a test fact ID."""
    return uuid4()


@pytest.fixture
def memory_doc(memory_id: UUID, entity_id: UUID) -> Dict[str, Any]:
    """Provide sample memory document."""
    return {
        "memory_id": str(memory_id),
        "entity_id": str(entity_id),
        "text": "I remember you saved my life in the ancient ruins",
        "scene_id": None,
        "fact_id": None,
        "importance": 0.8,
        "emotional_valence": 0.7,
        "certainty": 0.9,
        "metadata": {"context": "battle"},
        "created_at": datetime.now(timezone.utc),
        "last_accessed": datetime.now(timezone.utc),
        "access_count": 0,
    }


# =============================================================================
# TESTS: mongodb_create_memory
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_memory_success(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
    entity_id: UUID,
):
    """Test creating a memory with valid parameters."""
    # Mock Neo4j client to verify entity exists
    mock_neo4j = Mock()
    mock_neo4j.execute_read.return_value = [{"id": str(entity_id)}]
    mock_get_neo4j.return_value = mock_neo4j

    # Mock MongoDB client
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_collection.insert_one.return_value = Mock()
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    params = MemoryCreate(
        entity_id=entity_id,
        text="I remember the first time we met",
        importance=0.7,
    )

    result = mongodb_create_memory(params)

    assert result.entity_id == entity_id
    assert result.text == "I remember the first time we met"
    assert result.importance == 0.7
    assert result.access_count == 0
    assert mock_collection.insert_one.called


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_memory_with_references(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
    entity_id: UUID,
    scene_id: UUID,
    fact_id: UUID,
):
    """Test creating a memory with scene and fact references."""
    # Mock Neo4j client
    mock_neo4j = Mock()
    mock_neo4j.execute_read.return_value = [{"id": str(entity_id)}]
    mock_get_neo4j.return_value = mock_neo4j

    # Mock MongoDB client
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_collection.insert_one.return_value = Mock()
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    params = MemoryCreate(
        entity_id=entity_id,
        text="Important memory from scene",
        scene_id=scene_id,
        fact_id=fact_id,
        importance=0.9,
    )

    result = mongodb_create_memory(params)

    assert result.scene_id == scene_id
    assert result.fact_id == fact_id


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
def test_create_memory_entity_not_found(
    mock_get_neo4j: Mock,
    entity_id: UUID,
):
    """Test creating a memory with invalid entity_id raises error."""
    # Mock Neo4j client to return empty result (entity not found)
    mock_neo4j = Mock()
    mock_neo4j.execute_read.return_value = []
    mock_get_neo4j.return_value = mock_neo4j

    params = MemoryCreate(
        entity_id=entity_id,
        text="Memory for non-existent entity",
    )

    with pytest.raises(ValueError, match="Entity .* not found"):
        mongodb_create_memory(params)


def test_create_memory_importance_range():
    """Test that importance range validation works (0.0-1.0)."""
    entity_id = uuid4()

    # Test invalid low importance
    with pytest.raises(ValueError):
        MemoryCreate(
            entity_id=entity_id,
            text="Test memory",
            importance=-0.1,
        )

    # Test invalid high importance
    with pytest.raises(ValueError):
        MemoryCreate(
            entity_id=entity_id,
            text="Test memory",
            importance=1.1,
        )

    # Test valid boundary values
    valid_low = MemoryCreate(
        entity_id=entity_id,
        text="Test memory",
        importance=0.0,
    )
    assert valid_low.importance == 0.0

    valid_high = MemoryCreate(
        entity_id=entity_id,
        text="Test memory",
        importance=1.0,
    )
    assert valid_high.importance == 1.0


# =============================================================================
# TESTS: mongodb_get_memory
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_memory_success(
    mock_get_mongodb: Mock,
    memory_id: UUID,
    memory_doc: Dict[str, Any],
):
    """Test retrieving a memory by ID."""
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_collection.find_one_and_update.return_value = memory_doc
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    result = mongodb_get_memory(memory_id)

    assert result is not None
    assert result.memory_id == UUID(memory_doc["memory_id"])
    assert result.text == memory_doc["text"]
    assert result.importance == memory_doc["importance"]
    # Verify access tracking with find_one_and_update
    assert mock_collection.find_one_and_update.called


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_memory_not_found(
    mock_get_mongodb: Mock,
    memory_id: UUID,
):
    """Test retrieving a non-existent memory returns None."""
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_collection.find_one_and_update.return_value = None
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    result = mongodb_get_memory(memory_id)

    assert result is None


# =============================================================================
# TESTS: mongodb_list_memories
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_memories_by_entity(
    mock_get_mongodb: Mock,
    entity_id: UUID,
    memory_doc: Dict[str, Any],
):
    """Test listing memories filtered by entity_id."""
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_cursor = Mock()
    mock_cursor.__iter__ = Mock(return_value=iter([memory_doc]))
    mock_collection.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    params = MemoryFilter(entity_id=entity_id)

    result = mongodb_list_memories(params)

    assert len(result.memories) == 1
    assert result.total == 1
    # Verify filter was applied
    call_args = mock_collection.find.call_args
    assert call_args[0][0]["entity_id"] == str(entity_id)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_memories_by_importance(
    mock_get_mongodb: Mock,
    memory_doc: Dict[str, Any],
):
    """Test listing memories filtered by importance threshold."""
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_cursor = Mock()
    mock_cursor.__iter__ = Mock(return_value=iter([memory_doc]))
    mock_collection.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_collection.count_documents.return_value = 1
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    params = MemoryFilter(min_importance=0.7)

    result = mongodb_list_memories(params)

    # Verify filter was applied
    call_args = mock_collection.find.call_args
    assert "$gte" in call_args[0][0]["importance"]
    assert call_args[0][0]["importance"]["$gte"] == 0.7


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_memories_pagination(
    mock_get_mongodb: Mock,
):
    """Test memory listing with pagination."""
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_cursor = Mock()
    mock_cursor.__iter__ = Mock(return_value=iter([]))
    mock_collection.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_collection.count_documents.return_value = 100
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    params = MemoryFilter(limit=20, offset=40)

    result = mongodb_list_memories(params)

    assert result.limit == 20
    assert result.offset == 40
    assert result.total == 100
    mock_cursor.skip.assert_called_with(40)
    mock_cursor.limit.assert_called_with(20)


# =============================================================================
# TESTS: mongodb_update_memory
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
@patch("monitor_data.tools.mongodb_tools.mongodb_get_memory")
def test_update_memory_importance(
    mock_get_memory: Mock,
    mock_get_mongodb: Mock,
    memory_id: UUID,
    entity_id: UUID,
):
    """Test updating memory importance."""
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_result = Mock()
    mock_result.matched_count = 1
    mock_collection.update_one.return_value = mock_result
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    # Mock the get_memory call that happens after update
    mock_get_memory.return_value = Mock(
        memory_id=memory_id,
        entity_id=entity_id,
        importance=0.95,
    )

    params = MemoryUpdate(importance=0.95)

    result = mongodb_update_memory(memory_id, params)

    assert result is not None
    assert result.importance == 0.95
    assert mock_collection.update_one.called


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_memory_not_found(
    mock_get_mongodb: Mock,
    memory_id: UUID,
):
    """Test updating non-existent memory returns None."""
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_result = Mock()
    mock_result.matched_count = 0
    mock_collection.update_one.return_value = mock_result
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    params = MemoryUpdate(importance=0.95)

    result = mongodb_update_memory(memory_id, params)

    assert result is None


# =============================================================================
# TESTS: mongodb_delete_memory
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_delete_memory_success(
    mock_get_mongodb: Mock,
    memory_id: UUID,
):
    """Test deleting a memory."""
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_result = Mock()
    mock_result.deleted_count = 1
    mock_collection.delete_one.return_value = mock_result
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    result = mongodb_delete_memory(memory_id)

    assert result is True
    mock_collection.delete_one.assert_called_with({"memory_id": str(memory_id)})


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_delete_memory_not_found(
    mock_get_mongodb: Mock,
    memory_id: UUID,
):
    """Test deleting non-existent memory returns False."""
    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_result = Mock()
    mock_result.deleted_count = 0
    mock_collection.delete_one.return_value = mock_result
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    result = mongodb_delete_memory(memory_id)

    assert result is False


# =============================================================================
# TESTS: qdrant_embed_memory
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_embed_memory(
    mock_get_qdrant: Mock,
    memory_id: UUID,
    entity_id: UUID,
):
    """Test creating a Qdrant embedding for a memory."""
    mock_qdrant = Mock()
    mock_client = Mock()
    mock_client.upsert.return_value = Mock()
    mock_qdrant.get_client.return_value = mock_client
    mock_qdrant.ensure_collection.return_value = None
    mock_get_qdrant.return_value = mock_qdrant

    result = qdrant_embed_memory(
        memory_id=memory_id,
        text="Test memory text",
        entity_id=entity_id,
        importance=0.8,
    )

    assert result["success"] is True
    assert result["point_id"] == str(memory_id)
    assert mock_client.upsert.called
    assert mock_qdrant.ensure_collection.called


# =============================================================================
# TESTS: qdrant_search_memories
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_memories(
    mock_get_qdrant: Mock,
    memory_id: UUID,
    entity_id: UUID,
):
    """Test semantic search of memories."""
    mock_qdrant = Mock()
    mock_client = Mock()

    # Mock search result
    mock_hit = Mock()
    mock_hit.payload = {
        "memory_id": str(memory_id),
        "entity_id": str(entity_id),
        "text": "Test memory",
        "importance": 0.8,
    }
    mock_hit.score = 0.95

    mock_client.search.return_value = [mock_hit]
    mock_qdrant.get_client.return_value = mock_client
    mock_get_qdrant.return_value = mock_qdrant

    params = MemorySearchQuery(
        query_text="test query",
        entity_id=entity_id,
        top_k=5,
    )

    result = qdrant_search_memories(params)

    assert result.query_text == "test query"
    assert len(result.results) == 1
    assert result.results[0].memory_id == memory_id
    assert result.results[0].score == 0.95


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_memories_with_importance_filter(
    mock_get_qdrant: Mock,
):
    """Test semantic search with importance filter."""
    mock_qdrant = Mock()
    mock_client = Mock()
    mock_client.search.return_value = []
    mock_qdrant.get_client.return_value = mock_client
    mock_get_qdrant.return_value = mock_qdrant

    params = MemorySearchQuery(
        query_text="test query",
        min_importance=0.7,
        top_k=10,
    )

    result = qdrant_search_memories(params)

    # Verify filter was applied in search call
    call_args = mock_client.search.call_args
    assert call_args[1]["query_filter"] is not None


# =============================================================================
# TESTS: qdrant_delete_memory
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_memory_embedding(
    mock_get_qdrant: Mock,
    memory_id: UUID,
):
    """Test deleting a memory embedding from Qdrant."""
    mock_qdrant = Mock()
    mock_client = Mock()
    mock_client.delete.return_value = Mock()
    mock_qdrant.get_client.return_value = mock_client
    mock_get_qdrant.return_value = mock_qdrant

    result = qdrant_delete_memory(memory_id)

    assert result is True
    mock_client.delete.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_memory_embedding_failure(
    mock_get_qdrant: Mock,
    memory_id: UUID,
):
    """Test deleting memory embedding handles errors."""
    mock_qdrant = Mock()
    mock_client = Mock()
    mock_client.delete.side_effect = Exception("Qdrant error")
    mock_qdrant.get_client.return_value = mock_client
    mock_get_qdrant.return_value = mock_qdrant

    result = qdrant_delete_memory(memory_id)

    assert result is False


# =============================================================================
# INTEGRATION TEST: Memory lifecycle
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_memory_lifecycle(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
    mock_get_qdrant: Mock,
    entity_id: UUID,
):
    """Test complete memory lifecycle: create → embed → search → delete."""
    # Setup mocks
    mock_neo4j = Mock()
    mock_neo4j.execute_read.return_value = [{"id": str(entity_id)}]
    mock_get_neo4j.return_value = mock_neo4j

    mock_mongodb = Mock()
    mock_collection = Mock()
    mock_collection.insert_one.return_value = Mock()
    mock_mongodb.get_collection.return_value = mock_collection
    mock_get_mongodb.return_value = mock_mongodb

    mock_qdrant = Mock()
    mock_qdrant_client = Mock()
    mock_qdrant.get_client.return_value = mock_qdrant_client
    mock_qdrant.ensure_collection.return_value = None
    mock_get_qdrant.return_value = mock_qdrant

    # 1. Create memory
    params = MemoryCreate(
        entity_id=entity_id,
        text="Important event in the story",
        importance=0.9,
    )
    memory = mongodb_create_memory(params)

    # 2. Embed memory
    embed_result = qdrant_embed_memory(
        memory_id=memory.memory_id,
        text=memory.text,
        entity_id=memory.entity_id,
        importance=memory.importance,
    )
    assert embed_result["success"] is True

    # 3. Verify all operations called
    assert mock_collection.insert_one.called
    assert mock_qdrant_client.upsert.called
