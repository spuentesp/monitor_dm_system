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

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.vectors import (
    CollectionInfoRequest,
    VectorBatchUpsertRequest,
    VectorDeleteByFilterRequest,
    VectorDeleteRequest,
    VectorFilter,
    VectorPoint,
    VectorSearchRequest,
    VectorUpsertRequest,
)
from monitor_data.tools.qdrant_tools import (
    _upsert_points,
    qdrant_delete,
    qdrant_delete_by_filter,
    qdrant_get_collection_info,
    qdrant_search,
    qdrant_upsert,
    qdrant_upsert_batch,
)

# =============================================================================
# SELF-HEALING UPSERT RETRY (T-098/R9)
# =============================================================================


def test_upsert_points_self_heals_on_closed_loop():
    """A stale client (closed event loop) triggers a rebuild + one retry."""
    bad = Mock()
    bad.upsert.side_effect = RuntimeError("Event loop is closed")
    good = Mock()  # default Mock return is non-awaitable -> call_sync passes through
    client = Mock()
    client.get_client.side_effect = [bad, good]

    _upsert_points(client, "memories", [object()])

    client.reset_client.assert_called_once()
    assert client.get_client.call_count == 2
    good.upsert.assert_called_once()


def test_upsert_points_does_not_retry_other_runtime_errors():
    """Unrelated RuntimeErrors propagate without a rebuild/retry."""
    bad = Mock()
    bad.upsert.side_effect = RuntimeError("collection not found")
    client = Mock()
    client.get_client.return_value = bad

    with pytest.raises(RuntimeError, match="collection not found"):
        _upsert_points(client, "memories", [object()])

    client.reset_client.assert_not_called()


def test_upsert_points_succeeds_without_retry_on_happy_path():
    qdrant = Mock()
    client = Mock()
    client.get_client.return_value = qdrant

    _upsert_points(client, "scenes", [object(), object()])

    qdrant.upsert.assert_called_once()
    client.reset_client.assert_not_called()


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


@patch("monitor_data.tools.qdrant_tools._embed_query_via_service")
@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_accepts_query_text_and_query_points(mock_get_client: Mock, mock_embed_query: Mock):
    """Text-based search should embed the query and work with query_points-only clients."""
    result_id = uuid4()
    # The embed-branch routes through the RetrievalService now (single embed
    # owner); patch that sync bridge rather than the raw embed_text.
    mock_embed_query.return_value = [0.25] * 1536

    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    mock_point = Mock()
    mock_point.id = str(result_id)
    mock_point.score = 0.88
    mock_point.payload = {"type": "snippet", "doc_id": str(uuid4())}

    mock_response = Mock()
    mock_response.points = [mock_point]
    del mock_qdrant.search
    mock_qdrant.query_points = AsyncMock(return_value=mock_response)

    params = VectorSearchRequest(
        collection="snippets",
        query_text="ancient ruins",
        limit=3,
    )

    result = qdrant_search(params)

    assert result.count == 1
    assert result.results[0].id == result_id
    mock_qdrant.query_points.assert_awaited_once()


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

    # Mock count results - before: 5, after: 0 (all deleted)
    mock_count_before = Mock()
    mock_count_before.count = 5
    mock_count_after = Mock()
    mock_count_after.count = 0
    mock_qdrant.count.side_effect = [mock_count_before, mock_count_after]

    params = VectorDeleteByFilterRequest(
        collection="scenes",
        filter=VectorFilter(story_id=story_id),
    )

    # Execute
    result = qdrant_delete_by_filter(params)

    # Verify
    assert result.success is True
    assert result.collection == "scenes"
    assert result.deleted_count == 5  # 5 - 0 = 5 deleted
    mock_client.ensure_collection.assert_called_once_with("scenes")
    assert mock_qdrant.count.call_count == 2  # Called before and after
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

    # Mock count results - before: 0, after: 0 (nothing to delete)
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
    assert result.deleted_count == 0  # 0 - 0 = 0 deleted
    assert mock_qdrant.count.call_count == 2  # Called before and after
    # Delete is always called regardless of count
    mock_qdrant.delete.assert_called_once()


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


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_batch_large(mock_get_client: Mock):
    """Test successful batch upsert with 100 points."""
    # Setup
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Create 100 points
    points = [
        VectorPoint(
            id=uuid4(),
            vector=[(i / 100.0)] * 1536,
            payload={"type": "embedding", "index": i},
        )
        for i in range(100)
    ]

    params = VectorBatchUpsertRequest(
        collection="embeddings",
        points=points,
    )

    # Execute
    result = qdrant_upsert_batch(params)

    # Verify
    assert result.success is True
    assert result.collection == "embeddings"
    assert result.upserted_count == 100
    assert len(result.ids) == 100
    mock_client.ensure_collection.assert_called_once_with("embeddings")
    mock_qdrant.upsert.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_returns_correct_order(mock_get_client: Mock):
    """Test vector search returns results in correct score order."""
    # Setup
    id1, id2, id3 = uuid4(), uuid4(), uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock results in decreasing score order
    mock_result1 = Mock()
    mock_result1.id = str(id1)
    mock_result1.score = 0.95
    mock_result1.payload = {"type": "scene"}

    mock_result2 = Mock()
    mock_result2.id = str(id2)
    mock_result2.score = 0.87
    mock_result2.payload = {"type": "scene"}

    mock_result3 = Mock()
    mock_result3.id = str(id3)
    mock_result3.score = 0.72
    mock_result3.payload = {"type": "scene"}

    mock_qdrant.search.return_value = [mock_result1, mock_result2, mock_result3]

    params = VectorSearchRequest(
        collection="scenes",
        query_vector=[0.1] * 1536,
        top_k=5,
    )

    # Execute
    result = qdrant_search(params)

    # Verify results are in descending score order
    assert result.count == 3
    assert result.results[0].score == 0.95
    assert result.results[1].score == 0.87
    assert result.results[2].score == 0.72
    # Verify order is correct
    assert result.results[0].score >= result.results[1].score >= result.results[2].score


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_no_results(mock_get_client: Mock):
    """Test vector search returns empty results."""
    # Setup
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    mock_qdrant.search.return_value = []  # No results

    params = VectorSearchRequest(
        collection="scenes",
        query_vector=[0.1] * 1536,
        top_k=5,
    )

    # Execute
    result = qdrant_search(params)

    # Verify
    assert result.collection == "scenes"
    assert result.count == 0
    assert len(result.results) == 0
    mock_client.ensure_collection.assert_called_once_with("scenes")
    mock_qdrant.search.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_by_filter_partial_deletion(mock_get_client: Mock):
    """Test batch deletion when only some points match filter."""
    # Setup
    story_id = uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock count results - before: 10, after: 4 (6 deleted)
    mock_count_before = Mock()
    mock_count_before.count = 10
    mock_count_after = Mock()
    mock_count_after.count = 4
    mock_qdrant.count.side_effect = [mock_count_before, mock_count_after]

    params = VectorDeleteByFilterRequest(
        collection="scenes",
        filter=VectorFilter(story_id=story_id),
    )

    # Execute
    result = qdrant_delete_by_filter(params)

    # Verify
    assert result.success is True
    assert result.collection == "scenes"
    assert result.deleted_count == 6  # 10 - 4 = 6 deleted
    mock_client.ensure_collection.assert_called_once_with("scenes")
    assert mock_qdrant.count.call_count == 2  # Called before and after
    mock_qdrant.delete.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_get_collection_info_different_distance(mock_get_client: Mock):
    """Test collection info with Euclidean distance metric."""
    # Setup
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock collection info with Euclidean distance
    mock_collection_info = Mock()
    mock_collection_info.points_count = 2500
    mock_collection_info.indexed_vectors_count = 2500
    mock_collection_info.status.name = "green"

    mock_vectors_config = Mock()
    mock_vectors_config.size = 768
    mock_vectors_config.distance.name = "EUCLID"

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
    assert result.collection.vector_size == 768
    assert result.collection.points_count == 2500
    assert result.collection.distance == "EUCLID"
    assert result.collection.status == "green"


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_nonexistent_id(mock_get_client: Mock):
    """Test deletion of non-existent vector ID still returns success."""
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

    # Verify - delete operation still returns success even if ID doesn't exist
    assert result.success is True
    assert result.collection == "scenes"
    assert result.deleted_count == 1
    mock_client.ensure_collection.assert_called_once_with("scenes")
    mock_qdrant.delete.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_by_filter_multiple_conditions(mock_get_client: Mock):
    """Test batch deletion with multiple filter conditions."""
    # Setup
    story_id = uuid4()
    entity_id = uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock count results - before: 8, after: 2 (6 deleted)
    mock_count_before = Mock()
    mock_count_before.count = 8
    mock_count_after = Mock()
    mock_count_after.count = 2
    mock_qdrant.count.side_effect = [mock_count_before, mock_count_after]

    params = VectorDeleteByFilterRequest(
        collection="scenes",
        filter=VectorFilter(
            story_id=story_id,
            entity_id=entity_id,
            type="scene",
        ),
    )

    # Execute
    result = qdrant_delete_by_filter(params)

    # Verify
    assert result.success is True
    assert result.collection == "scenes"
    assert result.deleted_count == 6  # 8 - 2 = 6 deleted
    mock_client.ensure_collection.assert_called_once_with("scenes")
    assert mock_qdrant.count.call_count == 2
    mock_qdrant.delete.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_get_collection_info_yellow_status(mock_get_client: Mock):
    """Test collection info with yellow (warning) status."""
    # Setup
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock collection info with yellow status
    mock_collection_info = Mock()
    mock_collection_info.points_count = 5000
    mock_collection_info.indexed_vectors_count = 4500
    mock_collection_info.status.name = "yellow"

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
    assert result.collection.status == "yellow"
    assert result.collection.points_count == 5000
    assert result.collection.indexed_vectors_count == 4500
    assert result.collection.vector_size == 1536


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_with_limit(mock_get_client: Mock):
    """Test vector search respects limit parameter."""
    # Setup
    id1, id2 = uuid4(), uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Mock results
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
        limit=3,
    )

    # Execute
    result = qdrant_search(params)

    # Verify limit was passed to search
    assert result.count == 2
    call_args = mock_qdrant.search.call_args
    assert call_args[1]["limit"] == 3


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_with_large_payload(mock_get_client: Mock):
    """Test upsert with large payload (edge case)."""
    # Setup
    vector_id = uuid4()
    mock_client = Mock()
    mock_qdrant = Mock()
    mock_get_client.return_value = mock_client
    mock_client.get_client.return_value = mock_qdrant

    # Create large payload with nested structure
    large_payload = {
        "type": "scene",
        "story_id": str(uuid4()),
        "nested": {"level1": {"level2": {"level3": ["item1", "item2", "item3"] * 100}}},
        "tags": ["tag_" + str(i) for i in range(50)],
    }

    params = VectorUpsertRequest(
        collection="scenes",
        id=vector_id,
        vector=[0.1] * 1536,
        payload=large_payload,
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
