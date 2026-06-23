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
def scene_data(story_data: Dict[str, Any], universe_data: Dict[str, Any]) -> Dict[str, Any]:
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
        "universe_id": entity_data["universe_id"],
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


@patch("monitor_data.tools.mongodb_tools.memories.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_create_memory_success(
    mock_mongo_client: Mock,
    mock_neo4j_client: Mock,
    entity_data: Dict[str, Any],
):
    """Test creating a memory with valid parameters."""
    # Mock Neo4j entity check
    mock_neo4j_client.return_value.execute_read.return_value = [{"id": entity_data["id"]}]

    # Mock MongoDB insert
    mock_collection = Mock()
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    params = MemoryCreate(
        universe_id=UUID(entity_data["universe_id"]),
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


@patch("monitor_data.tools.mongodb_tools.memories.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_create_memory_with_scene(
    mock_mongo_client: Mock,
    mock_neo4j_client: Mock,
    entity_data: Dict[str, Any],
    scene_data: Dict[str, Any],
):
    """Test creating a memory linked to a scene."""
    # Mock Neo4j entity check
    mock_neo4j_client.return_value.execute_read.return_value = [{"id": entity_data["id"]}]

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

    mock_mongo_client.return_value.get_collection.side_effect = get_collection_side_effect

    params = MemoryCreate(
        universe_id=UUID(entity_data["universe_id"]),
        entity_id=UUID(entity_data["id"]),
        text="The dragon breathed fire and I barely escaped",
        scene_id=UUID(scene_data["scene_id"]),
        importance=0.8,
    )

    memory = mongodb_create_memory(params)

    assert memory.scene_id == UUID(scene_data["scene_id"])
    assert memory.text == params.text


@patch("monitor_data.tools.mongodb_tools.characters.mongodb_get_character")
@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
@patch("monitor_data.tools.mongodb_tools.memories.get_neo4j_client")
def test_create_memory_invalid_entity(
    mock_neo4j_client: Mock, mock_mongo_client: Mock, mock_get_char: Mock, entity_data: Dict[str, Any]
):
    """Test creating a memory with non-existent entity fails."""
    # Mock Neo4j entity check returning empty
    mock_neo4j_client.return_value.execute_read.return_value = []
    # Mock MongoDB character check returning empty
    mock_get_char.return_value = None

    fake_entity_id = uuid4()
    params = MemoryCreate(
        universe_id=UUID(entity_data["universe_id"]),
        entity_id=fake_entity_id,
        text="This should fail",
        importance=0.5,
    )

    with pytest.raises(ValueError, match="Entity .* not found"):
        mongodb_create_memory(params)


@patch("monitor_data.tools.mongodb_tools.memories.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_create_memory_with_linked_fact(
    mock_mongo_client: Mock,
    mock_neo4j_client: Mock,
    entity_data: Dict[str, Any],
):
    """Test creating a memory linked to a fact."""
    # Mock Neo4j entity check
    mock_neo4j_client.return_value.execute_read.return_value = [
        {"id": entity_data["id"]},
        {"id": str(uuid4())},  # Linked fact exists
    ]

    # Mock MongoDB insert
    mock_collection = Mock()
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    params = MemoryCreate(
        universe_id=UUID(entity_data["universe_id"]),
        entity_id=UUID(entity_data["id"]),
        text="The fact that you saved my life changed everything",
        linked_fact_id=uuid4(),
        importance=0.9,
        emotional_valence=0.9,
        certainty=1.0,
    )

    memory = mongodb_create_memory(params)

    assert memory.entity_id == UUID(entity_data["id"])
    assert memory.linked_fact_id is not None
    assert memory.text == params.text
    assert memory.importance == 0.9
    assert memory.emotional_valence == 0.9
    mock_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
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
    with patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client") as mock_mongo:
        mock_collection = Mock()
        mock_collection.find_one_and_update.return_value = None
        mock_mongo.return_value.get_collection.return_value = mock_collection

        fake_id = uuid4()
        with pytest.raises(ValueError, match="Memory .* not found"):
            mongodb_get_memory(fake_id)


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_list_memories(mock_mongo_client: Mock, entity_data: Dict[str, Any]):
    """Test listing memories with filters."""
    # Create mock memories
    mock_memories = [
        {
            "memory_id": str(uuid4()),
            "universe_id": entity_data["universe_id"],
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
        for i in range(5)
    ]

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


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_list_memories_empty_results(mock_mongo_client: Mock, entity_data: Dict[str, Any]):
    """Test listing memories with no matches."""
    mock_collection = Mock()
    mock_collection.count_documents.return_value = 0
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter([])
    mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
        mock_cursor
    )
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    filter_params = MemoryFilter(
        entity_id=UUID(entity_data["id"]),
        min_importance=0.9,  # High importance that won't match
        max_importance=1.0,
        limit=100,
        offset=0,
    )
    result = mongodb_list_memories(filter_params)

    assert result.total == 0
    assert len(result.memories) == 0


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_list_memories_with_importance_range(mock_mongo_client: Mock, entity_data: Dict[str, Any]):
    """Test listing memories filtered by importance range."""
    # Create mock memories with different importance levels
    mock_memories = [
        {
            "memory_id": str(uuid4()),
            "universe_id": entity_data["universe_id"],
            "entity_id": entity_data["id"],
            "text": f"Memory with importance {imp}",
            "scene_id": None,
            "linked_fact_id": None,
            "importance": imp,
            "emotional_valence": 0.0,
            "certainty": 1.0,
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "last_accessed": datetime.now(timezone.utc),
            "access_count": 0,
        }
        for imp in [0.2, 0.4, 0.6, 0.8, 1.0]
    ]

    mock_collection = Mock()
    mock_collection.count_documents.return_value = 3  # Only 0.6, 0.8, 1.0 match range 0.5-1.0
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(mock_memories[2:])  # Return only 0.6, 0.8, 1.0
    mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
        mock_cursor
    )
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    filter_params = MemoryFilter(
        entity_id=UUID(entity_data["id"]),
        min_importance=0.5,
        max_importance=1.0,
        limit=100,
        offset=0,
    )
    result = mongodb_list_memories(filter_params)

    assert result.total == 3
    assert len(result.memories) == 3
    assert all(m.importance >= 0.5 and m.importance <= 1.0 for m in result.memories)


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
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


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_update_memory_partial_fields(mock_mongo_client: Mock, memory_data: Dict[str, Any]):
    """Test updating only some memory fields (partial update)."""
    mock_collection = Mock()
    mock_collection.update_one.return_value.matched_count = 1

    updated_data = memory_data.copy()
    updated_data["emotional_valence"] = -0.3
    updated_data["access_count"] = 1
    mock_collection.find_one_and_update.return_value = updated_data

    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    update_params = MemoryUpdate(emotional_valence=-0.3)  # Only update emotional_valence
    updated = mongodb_update_memory(UUID(memory_data["memory_id"]), update_params)

    assert updated.emotional_valence == -0.3
    assert updated.importance == memory_data["importance"]  # Should remain unchanged


def test_update_memory_not_found():
    """Test updating non-existent memory raises error."""
    with patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client") as mock_mongo:
        mock_collection = Mock()
        mock_collection.update_one.return_value.matched_count = 0
        mock_mongo.return_value.get_collection.return_value = mock_collection

        fake_id = uuid4()
        update_params = MemoryUpdate(importance=0.9)

        with pytest.raises(ValueError, match="Memory .* not found"):
            mongodb_update_memory(fake_id, update_params)


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_delete_memory(mock_mongo_client: Mock, memory_data: Dict[str, Any]):
    """Test deleting a memory."""
    mock_collection = Mock()
    mock_collection.delete_one.return_value.deleted_count = 1
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    result = mongodb_delete_memory(UUID(memory_data["memory_id"]))
    assert result is True


def test_delete_memory_not_found():
    """Test deleting non-existent memory returns False."""
    with patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client") as mock_mongo:
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
            universe_id=UUID("00000000-0000-0000-0000-000000000000"),
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
def test_search_memories_importance_filter(mock_qdrant_client: Mock, entity_data: Dict[str, Any]):
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


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_memories_empty_results(mock_qdrant_client: Mock, entity_data: Dict[str, Any]):
    """Test semantic search with no matching memories."""
    mock_client = Mock()
    mock_client.ensure_collection.return_value = None
    mock_client.embed_text.return_value = [0.1] * 1536

    # Mock empty search results
    mock_qdrant = Mock()
    mock_qdrant.search.return_value = []
    mock_client.get_client.return_value = mock_qdrant
    mock_qdrant_client.return_value = mock_client

    search_params = MemorySearchRequest(
        query_text="nonexistent topic that has no memories",
        entity_id=UUID(entity_data["id"]),
        top_k=10,
    )
    result = qdrant_search_memories(search_params)

    assert len(result.results) == 0
    assert result.query == "nonexistent topic that has no memories"


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_memories_universe_scoped(mock_qdrant_client: Mock, entity_data: Dict[str, Any]):
    """Test that semantic memory search filters by universe_id (T-093 retrieval scoping)."""
    mock_client = Mock()
    mock_client.ensure_collection.return_value = None
    mock_client.embed_text.return_value = [0.1] * 1536

    mock_qdrant = Mock()
    mock_scored_point = Mock()
    mock_scored_point.score = 0.92
    mock_scored_point.payload = {
        "memory_id": str(uuid4()),
        "universe_id": entity_data["universe_id"],
        "entity_id": entity_data["id"],
        "scene_id": None,
        "importance": 0.8,
        "type": "memory",
    }
    mock_qdrant.search.return_value = [mock_scored_point]
    mock_client.get_client.return_value = mock_qdrant
    mock_qdrant_client.return_value = mock_client

    universe_uuid = UUID(entity_data["universe_id"])
    search_params = MemorySearchRequest(
        query_text="dragon attack",
        universe_id=universe_uuid,
        entity_id=UUID(entity_data["id"]),
        top_k=5,
    )
    result = qdrant_search_memories(search_params)

    assert len(result.results) == 1
    # Verify the Qdrant search was called with a filter containing universe_id
    _search_call = mock_qdrant.search.call_args
    assert _search_call is not None
    qdrant_filter = _search_call.kwargs.get("query_filter")
    assert qdrant_filter is not None
    filter_keys = [fc.key for fc in (qdrant_filter.must or [])]
    assert "universe_id" in filter_keys


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_list_memories_universe_scoped(mock_mongo_client: Mock, entity_data: Dict[str, Any]):
    """Test that listing memories filters by universe_id (T-093 retrieval scoping)."""
    mock_memories = [
        {
            "memory_id": str(uuid4()),
            "universe_id": entity_data["universe_id"],
            "entity_id": entity_data["id"],
            "text": f"Universe-scoped memory {i}",
            "scene_id": None,
            "linked_fact_id": None,
            "importance": 0.5,
            "emotional_valence": 0.0,
            "certainty": 1.0,
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "last_accessed": datetime.now(timezone.utc),
            "access_count": 0,
        }
        for i in range(3)
    ]

    mock_collection = Mock()
    mock_collection.count_documents.return_value = 3
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(mock_memories)
    mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
        mock_cursor
    )
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    universe_uuid = UUID(entity_data["universe_id"])
    filter_params = MemoryFilter(
        universe_id=universe_uuid,
        entity_id=UUID(entity_data["id"]),
        limit=100,
        offset=0,
    )
    result = mongodb_list_memories(filter_params)

    assert result.total == 3
    assert len(result.memories) == 3
    # Verify the MongoDB filter included universe_id
    find_call = mock_collection.find.call_args
    assert find_call is not None
    filter_dict = find_call.args[0]
    assert filter_dict.get("universe_id") == entity_data["universe_id"]


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_list_memories_with_scene_filter(mock_mongo_client: Mock, entity_data: Dict[str, Any]):
    """Test listing memories filtered by scene_id."""
    # Create mock memories with different scene_id values
    scene_id = str(uuid4())
    scene_uuid = UUID(scene_id)  # Convert to UUID for comparison
    mock_memories = [
        {
            "memory_id": str(uuid4()),
            "universe_id": entity_data["universe_id"],
            "entity_id": entity_data["id"],
            "text": f"Memory {i}",
            "scene_id": scene_id if i < 3 else None,  # First 3 memories have scene_id
            "linked_fact_id": None,
            "importance": 0.5,
            "emotional_valence": 0.0,
            "certainty": 1.0,
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "last_accessed": datetime.now(timezone.utc),
            "access_count": 0,
        }
        for i in range(5)
    ]

    mock_collection = Mock()
    mock_collection.count_documents.return_value = 3  # Only 3 memories have scene_id
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(mock_memories[:3])  # Return first 3
    mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
        mock_cursor
    )
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    filter_params = MemoryFilter(
        entity_id=UUID(entity_data["id"]),
        scene_id=scene_uuid,
        limit=100,
        offset=0,
    )
    result = mongodb_list_memories(filter_params)

    assert result.total == 3
    assert len(result.memories) == 3
    # Verify all returned memories have the expected scene_id (parsed as UUID)
    assert all(m.scene_id == scene_uuid for m in result.memories)


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_list_memories_with_min_importance_filter(
    mock_mongo_client: Mock, entity_data: Dict[str, Any]
):
    """Test listing memories filtered by min_importance only."""
    # Create mock memories with different importance levels
    mock_memories = [
        {
            "memory_id": str(uuid4()),
            "universe_id": entity_data["universe_id"],
            "entity_id": entity_data["id"],
            "text": f"Memory with importance {imp}",
            "scene_id": None,
            "linked_fact_id": None,
            "importance": imp,
            "emotional_valence": 0.0,
            "certainty": 1.0,
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "last_accessed": datetime.now(timezone.utc),
            "access_count": 0,
        }
        for imp in [0.2, 0.4, 0.6, 0.8, 1.0]
    ]

    mock_collection = Mock()
    mock_collection.count_documents.return_value = 4  # Only 0.4, 0.6, 0.8, 1.0 >= 0.3
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(mock_memories[1:])  # Return 0.4, 0.6, 0.8, 1.0
    mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
        mock_cursor
    )
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    filter_params = MemoryFilter(
        entity_id=UUID(entity_data["id"]),
        min_importance=0.3,  # No max_importance set
        limit=100,
        offset=0,
    )
    result = mongodb_list_memories(filter_params)

    assert result.total == 4
    assert len(result.memories) == 4
    assert all(m.importance >= 0.3 for m in result.memories)


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_list_memories_with_max_importance_filter(
    mock_mongo_client: Mock, entity_data: Dict[str, Any]
):
    """Test listing memories filtered by max_importance only."""
    # Create mock memories with different importance levels
    mock_memories = [
        {
            "memory_id": str(uuid4()),
            "universe_id": entity_data["universe_id"],
            "entity_id": entity_data["id"],
            "text": f"Memory with importance {imp}",
            "scene_id": None,
            "linked_fact_id": None,
            "importance": imp,
            "emotional_valence": 0.0,
            "certainty": 1.0,
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "last_accessed": datetime.now(timezone.utc),
            "access_count": 0,
        }
        for imp in [0.2, 0.4, 0.6, 0.8, 1.0]
    ]

    mock_collection = Mock()
    mock_collection.count_documents.return_value = 3  # Only 0.2, 0.4, 0.6 <= 0.6
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(mock_memories[:3])  # Return 0.2, 0.4, 0.6
    mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = (
        mock_cursor
    )
    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    filter_params = MemoryFilter(
        entity_id=UUID(entity_data["id"]),
        max_importance=0.6,  # No min_importance set
        limit=100,
        offset=0,
    )
    result = mongodb_list_memories(filter_params)

    assert result.total == 3
    assert len(result.memories) == 3
    assert all(m.importance <= 0.6 for m in result.memories)


@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_update_memory_metadata_only(mock_mongo_client: Mock, memory_data: Dict[str, Any]):
    """Test updating only the metadata field of a memory."""
    mock_collection = Mock()
    mock_collection.update_one.return_value = Mock(matched_count=1)

    # Mock find_one_and_update for the get_memory call inside mongodb_update_memory
    updated_data = memory_data.copy()
    updated_data["metadata"] = {"source": "narrative", "tags": ["important", "plot_point"]}
    updated_data["access_count"] = 1
    mock_collection.find_one_and_update.return_value = updated_data

    mock_mongo_client.return_value.get_collection.return_value = mock_collection

    # Original memory with metadata
    updated_metadata = {"source": "narrative", "tags": ["important", "plot_point"]}

    memory_update = MemoryUpdate(
        metadata=updated_metadata,  # Only update metadata
    )

    result = mongodb_update_memory(UUID(memory_data["memory_id"]), memory_update)

    assert result is not None
    assert result.metadata == updated_metadata

    # Verify update was called with only metadata field
    update_call = mock_collection.update_one.call_args
    assert update_call is not None
    filter_query, update_dict = update_call[0]
    assert "$set" in update_dict
    assert "metadata" in update_dict["$set"]
    # Other fields should not be in $set
    assert "text" not in update_dict["$set"]


@patch("monitor_data.tools.mongodb_tools.memories.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client")
def test_create_memory_with_metadata(
    mock_mongo_client: Mock,
    mock_neo4j_client: Mock,
    entity_data: Dict[str, Any],
    scene_data: Dict[str, Any],
):
    """Test creating a memory with metadata field."""
    # Mock Neo4j entity validation
    mock_neo4j_client.return_value.execute_read.return_value = [{"id": entity_data["id"]}]

    # Mock MongoDB scene check and memory insertion
    mock_scenes_collection = Mock()
    mock_scenes_collection.find_one.return_value = scene_data
    mock_memories_collection = Mock()
    mock_memories_collection.insert_one.return_value = None

    def get_collection_side_effect(name):
        if name == "scenes":
            return mock_scenes_collection
        elif name == "character_memories":
            return mock_memories_collection
        return Mock()

    mock_mongo_client.return_value.get_collection.side_effect = get_collection_side_effect

    memory_create = MemoryCreate(
        universe_id=UUID(entity_data["universe_id"]),
        entity_id=UUID(entity_data["id"]),
        text="Memory with metadata",
        scene_id=UUID(scene_data["scene_id"]),
        importance=0.7,
        metadata={"source": "narrative", "tags": ["plot_point"], "chapter": 5},
    )

    result = mongodb_create_memory(memory_create)

    assert result is not None
    assert result.text == "Memory with metadata"
    assert result.metadata == {"source": "narrative", "tags": ["plot_point"], "chapter": 5}
    assert result.importance == 0.7

    # Verify metadata was saved to database
    insert_call = mock_memories_collection.insert_one.call_args
    assert insert_call is not None
    inserted_doc = insert_call[0][0]
    assert inserted_doc["metadata"] == {"source": "narrative", "tags": ["plot_point"], "chapter": 5}
