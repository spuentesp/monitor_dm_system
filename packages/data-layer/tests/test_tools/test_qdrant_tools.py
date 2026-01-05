"""
Tests for Qdrant vector operations (DL-10).

Tests all 6 Qdrant operations with proper mocking:
- qdrant_upsert: Store single vector
- qdrant_upsert_batch: Store multiple vectors
- qdrant_search: Semantic search with filtering
- qdrant_delete: Delete by ID
- qdrant_delete_by_filter: Batch delete
- qdrant_get_collection_info: Collection metadata
"""

import pytest
from unittest.mock import Mock, patch
from uuid import uuid4

from monitor_data.tools.qdrant_tools import (
    qdrant_upsert,
    qdrant_upsert_batch,
    qdrant_search,
    qdrant_delete,
    qdrant_delete_by_filter,
    qdrant_get_collection_info,
)
from monitor_data.schemas.vectors import (
    VectorUpsertRequest,
    VectorBatchUpsertRequest,
    VectorPoint,
    VectorSearchRequest,
    VectorFilter,
    VectorDeleteRequest,
    VectorDeleteByFilterRequest,
    CollectionInfoRequest,
)


# =============================================================================
# UPSERT TESTS
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_success(mock_get_client: Mock):
    """Test successful single vector upsert."""
    # Setup
    vector_id = uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    params = VectorUpsertRequest(
        collection="scenes",
        id=vector_id,
        vector=[0.1] * 1536,
        payload={"type": "scene", "story_id": str(uuid4())},
    )

    # Execute
    result = qdrant_upsert(params)

    # Verify
    assert result.success is True
    assert result.collection == "scenes"
    assert result.upserted_count == 1
    assert result.ids == [vector_id]
    mock_client.ensure_collection.assert_called_once_with("scenes")
    mock_qdrant.upsert.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_empty_vector(mock_get_client: Mock):
    """Test upsert fails with empty vector."""
    params = VectorUpsertRequest(
        collection="scenes",
        id=uuid4(),
        vector=[],  # Empty vector
        payload={},
    )

    with pytest.raises(ValueError, match="Vector cannot be empty"):
        qdrant_upsert(params)


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_batch_success(mock_get_client: Mock):
    """Test successful batch vector upsert."""
    # Setup
    id1, id2, id3 = uuid4(), uuid4(), uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    params = VectorBatchUpsertRequest(
        collection="memories",
        points=[
            VectorPoint(id=id1, vector=[0.1] * 1536, payload={"type": "memory"}),
            VectorPoint(id=id2, vector=[0.2] * 1536, payload={"type": "memory"}),
            VectorPoint(id=id3, vector=[0.3] * 1536, payload={"type": "memory"}),
        ],
    )

    # Execute
    result = qdrant_upsert_batch(params)

    # Verify
    assert result.success is True
    assert result.collection == "memories"
    assert result.upserted_count == 3
    assert result.ids == [id1, id2, id3]
    mock_client.ensure_collection.assert_called_once_with("memories")
    mock_qdrant.upsert.assert_called_once()


def test_upsert_batch_empty_points():
    """Test batch upsert fails with empty points list."""
    # Pydantic validation will catch this before reaching the function
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        VectorBatchUpsertRequest(
            collection="memories",
            points=[],  # Empty list - Pydantic min_length=1
        )


# =============================================================================
# SEARCH TESTS
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_basic(mock_get_client: Mock):
    """Test basic vector search without filters."""
    # Setup
    id1, id2 = uuid4(), uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock search results
    mock_result1 = Mock()
    mock_result1.id = str(id1)
    mock_result1.score = 0.95
    mock_result1.payload = {"type": "scene"}

    mock_result2 = Mock()
    mock_result2.id = str(id2)
    mock_result2.score = 0.87
    mock_result2.payload = {"type": "scene"}

    mock_qdrant.search.return_value = [mock_result1, mock_result2]

    params = VectorSearchRequest(
        collection="scenes",
        query_vector=[0.1] * 1536,
        top_k=5,
    )

    # Execute
    result = qdrant_search(params)

    # Verify
    assert result.collection == "scenes"
    assert result.count == 2
    assert len(result.results) == 2
    assert result.results[0].id == id1
    assert result.results[0].score == 0.95
    assert result.results[1].id == id2
    assert result.results[1].score == 0.87
    mock_client.ensure_collection.assert_called_once_with("scenes")
    mock_qdrant.search.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_with_filter(mock_get_client: Mock):
    """Test vector search with story_id filter."""
    # Setup
    story_id = uuid4()
    id1 = uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    mock_result1 = Mock()
    mock_result1.id = str(id1)
    mock_result1.score = 0.92
    mock_result1.payload = {"type": "scene", "story_id": str(story_id)}

    mock_qdrant.search.return_value = [mock_result1]

    params = VectorSearchRequest(
        collection="scenes",
        query_vector=[0.1] * 1536,
        top_k=10,
        filter=VectorFilter(story_id=story_id),
    )

    # Execute
    result = qdrant_search(params)

    # Verify
    assert result.count == 1
    assert result.results[0].id == id1
    assert result.results[0].payload["story_id"] == str(story_id)

    # Verify filter was passed to search
    call_args = mock_qdrant.search.call_args
    assert call_args[1]["query_filter"] is not None


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_with_threshold(mock_get_client: Mock):
    """Test vector search with score threshold."""
    # Setup
    id1 = uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    mock_result1 = Mock()
    mock_result1.id = str(id1)
    mock_result1.score = 0.85
    mock_result1.payload = {"type": "memory"}

    mock_qdrant.search.return_value = [mock_result1]

    params = VectorSearchRequest(
        collection="memories",
        query_vector=[0.2] * 1536,
        top_k=5,
        score_threshold=0.8,
    )

    # Execute
    result = qdrant_search(params)

    # Verify
    assert result.count == 1
    assert result.results[0].score >= 0.8

    # Verify threshold was passed to search
    call_args = mock_qdrant.search.call_args
    assert call_args[1]["score_threshold"] == 0.8


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_empty_vector(mock_get_client: Mock):
    """Test search fails with empty query vector."""
    params = VectorSearchRequest(
        collection="scenes",
        query_vector=[],  # Empty vector
        top_k=5,
    )

    with pytest.raises(ValueError, match="Query vector cannot be empty"):
        qdrant_search(params)


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_multiple_filters(mock_get_client: Mock):
    """Test vector search with multiple filter conditions."""
    # Setup
    story_id = uuid4()
    entity_id = uuid4()
    id1 = uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    mock_result1 = Mock()
    mock_result1.id = str(id1)
    mock_result1.score = 0.90
    mock_result1.payload = {
        "type": "scene",
        "story_id": str(story_id),
        "entity_id": str(entity_id),
    }

    mock_qdrant.search.return_value = [mock_result1]

    params = VectorSearchRequest(
        collection="scenes",
        query_vector=[0.1] * 1536,
        top_k=5,
        filter=VectorFilter(
            story_id=story_id,
            entity_id=entity_id,
            type="scene",
        ),
    )

    # Execute
    result = qdrant_search(params)

    # Verify
    assert result.count == 1
    assert result.results[0].payload["story_id"] == str(story_id)
    assert result.results[0].payload["entity_id"] == str(entity_id)
    assert result.results[0].payload["type"] == "scene"


# =============================================================================
# DELETE TESTS
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_success(mock_get_client: Mock):
    """Test successful vector deletion by ID."""
    # Setup
    vector_id = uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    params = VectorDeleteRequest(
        collection="scenes",
        id=vector_id,
    )

    # Execute
    result = qdrant_delete(params)

    # Verify
    assert result.success is True
    assert result.collection == "scenes"
    assert result.deleted_count == 1
    mock_client.ensure_collection.assert_called_once_with("scenes")
    mock_qdrant.delete.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_by_filter_success(mock_get_client: Mock):
    """Test successful batch deletion by filter."""
    # Setup
    story_id = uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock count result
    mock_count_result = Mock()
    mock_count_result.count = 5
    mock_qdrant.count.return_value = mock_count_result

    params = VectorDeleteByFilterRequest(
        collection="scenes",
        filter=VectorFilter(story_id=story_id),
    )

    # Execute
    result = qdrant_delete_by_filter(params)

    # Verify
    assert result.success is True
    assert result.collection == "scenes"
    assert result.deleted_count == 5
    mock_client.ensure_collection.assert_called_once_with("scenes")
    mock_qdrant.count.assert_called_once()
    mock_qdrant.delete.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_by_filter_no_matches(mock_get_client: Mock):
    """Test batch deletion when no points match filter."""
    # Setup
    story_id = uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock count result - no matches
    mock_count_result = Mock()
    mock_count_result.count = 0
    mock_qdrant.count.return_value = mock_count_result

    params = VectorDeleteByFilterRequest(
        collection="scenes",
        filter=VectorFilter(story_id=story_id),
    )

    # Execute
    result = qdrant_delete_by_filter(params)

    # Verify
    assert result.success is True
    assert result.deleted_count == 0
    mock_qdrant.count.assert_called_once()
    # Delete should not be called when count is 0
    mock_qdrant.delete.assert_not_called()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_by_filter_empty_filter(mock_get_client: Mock):
    """Test delete by filter fails with empty filter."""
    mock_client = Mock()
    mock_get_client.return_value = mock_client

    params = VectorDeleteByFilterRequest(
        collection="scenes",
        filter=VectorFilter(),  # Empty filter
    )

    with pytest.raises(ValueError, match="Filter parameters resulted in empty filter"):
        qdrant_delete_by_filter(params)


# =============================================================================
# COLLECTION INFO TESTS
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_get_collection_info_success(mock_get_client: Mock):
    """Test successful collection info retrieval."""
    # Setup
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock collection info
    mock_collection_info = Mock()
    mock_collection_info.points_count = 1500
    mock_collection_info.indexed_vectors_count = 1500
    mock_collection_info.status.name = "green"

    # Mock config structure
    mock_vectors_config = Mock()
    mock_vectors_config.size = 1536
    mock_vectors_config.distance.name = "COSINE"

    mock_params = Mock()
    mock_params.vectors = mock_vectors_config

    mock_config = Mock()
    mock_config.params = mock_params

    mock_collection_info.config = mock_config

    mock_qdrant.get_collection.return_value = mock_collection_info

    params = CollectionInfoRequest(collection="scenes")

    # Execute
    result = qdrant_get_collection_info(params)

    # Verify
    assert result.collection.name == "scenes"
    assert result.collection.vector_size == 1536
    assert result.collection.points_count == 1500
    assert result.collection.indexed_vectors_count == 1500
    assert result.collection.distance == "COSINE"
    assert result.collection.status == "green"
    mock_client.ensure_collection.assert_called_once_with("scenes")
    mock_qdrant.get_collection.assert_called_once_with("scenes")


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_get_collection_info_empty_collection(mock_get_client: Mock):
    """Test collection info for empty collection."""
    # Setup
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock empty collection info
    mock_collection_info = Mock()
    mock_collection_info.points_count = 0
    mock_collection_info.indexed_vectors_count = 0
    mock_collection_info.status.name = "green"

    mock_vectors_config = Mock()
    mock_vectors_config.size = 1536
    mock_vectors_config.distance.name = "COSINE"

    mock_params = Mock()
    mock_params.vectors = mock_vectors_config

    mock_config = Mock()
    mock_config.params = mock_params

    mock_collection_info.config = mock_config

    mock_qdrant.get_collection.return_value = mock_collection_info

    params = CollectionInfoRequest(collection="memories")

    # Execute
    result = qdrant_get_collection_info(params)

    # Verify
    assert result.collection.points_count == 0
    assert result.collection.indexed_vectors_count == 0
