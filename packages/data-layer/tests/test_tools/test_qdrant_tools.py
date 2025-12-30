"""
Unit tests for Qdrant vector operations.

Tests cover:
- qdrant_upsert
- qdrant_upsert_batch
- qdrant_search
- qdrant_delete
- qdrant_delete_by_filter
- qdrant_get_collection_info
"""

from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

import pytest

from monitor_data.schemas.vectors import (
    VectorUpsert,
    VectorUpsertBatch,
    VectorSearch,
    VectorDelete,
    VectorDeleteByFilter,
    CollectionInfoRequest,
)
from monitor_data.tools.qdrant_tools import (
    qdrant_upsert,
    qdrant_upsert_batch,
    qdrant_search,
    qdrant_delete,
    qdrant_delete_by_filter,
    qdrant_get_collection_info,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_qdrant_client():
    """Provide a mock Qdrant client."""
    mock_client = Mock()
    mock_qdrant_sdk = Mock()
    mock_client.get_client.return_value = mock_qdrant_sdk
    mock_client.ensure_collection = Mock()
    return mock_client


@pytest.fixture
def sample_vector() -> List[float]:
    """Provide a sample vector."""
    return [0.1] * 1536


@pytest.fixture
def sample_payload() -> Dict[str, Any]:
    """Provide a sample payload."""
    return {
        "id": str(uuid4()),
        "type": "scene",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "created_at": "2024-01-01T00:00:00Z",
    }


# =============================================================================
# TESTS: qdrant_upsert
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_success(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
    sample_payload: Dict[str, Any],
):
    """Test successful vector upsert."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_sdk = mock_qdrant_client.get_client.return_value

    params = VectorUpsert(
        collection="scenes",
        id="test-id-1",
        vector=sample_vector,
        payload=sample_payload,
    )

    result = qdrant_upsert(params)

    assert result.success is True
    assert result.collection == "scenes"
    assert result.id == "test-id-1"
    mock_qdrant_client.ensure_collection.assert_called_once_with("scenes", 1536)
    mock_qdrant_sdk.upsert.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_creates_collection_if_not_exists(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
    sample_payload: Dict[str, Any],
):
    """Test that upsert creates collection if it doesn't exist."""
    mock_get_client.return_value = mock_qdrant_client

    params = VectorUpsert(
        collection="new_collection",
        id="test-id",
        vector=sample_vector,
        payload=sample_payload,
    )

    result = qdrant_upsert(params)

    assert result.success is True
    mock_qdrant_client.ensure_collection.assert_called_once()


# =============================================================================
# TESTS: qdrant_upsert_batch
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_batch_success(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
    sample_payload: Dict[str, Any],
):
    """Test successful batch upsert."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_sdk = mock_qdrant_client.get_client.return_value

    points = [
        {
            "id": f"test-id-{i}",
            "vector": sample_vector,
            "payload": sample_payload,
        }
        for i in range(3)
    ]

    params = VectorUpsertBatch(collection="scenes", points=points)

    result = qdrant_upsert_batch(params)

    assert result.success is True
    assert result.collection == "scenes"
    assert result.count == 3
    mock_qdrant_sdk.upsert.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_batch_empty_points(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test that batch upsert raises error with empty points."""
    mock_get_client.return_value = mock_qdrant_client

    params = VectorUpsertBatch(collection="scenes", points=[])

    with pytest.raises(ValueError, match="Points list cannot be empty"):
        qdrant_upsert_batch(params)


# =============================================================================
# TESTS: qdrant_search
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_basic(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
):
    """Test basic vector search."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_sdk = mock_qdrant_client.get_client.return_value

    # Mock search results
    mock_hit1 = Mock()
    mock_hit1.id = "result-1"
    mock_hit1.score = 0.95
    mock_hit1.payload = {"type": "scene"}

    mock_hit2 = Mock()
    mock_hit2.id = "result-2"
    mock_hit2.score = 0.85
    mock_hit2.payload = {"type": "scene"}

    mock_qdrant_sdk.search.return_value = [mock_hit1, mock_hit2]

    params = VectorSearch(
        collection="scenes",
        query_vector=sample_vector,
        top_k=5,
    )

    result = qdrant_search(params)

    assert result.collection == "scenes"
    assert result.top_k == 5
    assert len(result.results) == 2
    assert result.results[0].id == "result-1"
    assert result.results[0].score == 0.95
    assert result.results[1].id == "result-2"
    assert result.results[1].score == 0.85


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_with_filter(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
):
    """Test search with payload filter."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_sdk = mock_qdrant_client.get_client.return_value

    mock_hit = Mock()
    mock_hit.id = "result-1"
    mock_hit.score = 0.95
    mock_hit.payload = {"type": "scene", "story_id": "story-123"}

    mock_qdrant_sdk.search.return_value = [mock_hit]

    params = VectorSearch(
        collection="scenes",
        query_vector=sample_vector,
        top_k=5,
        filter={"story_id": "story-123"},
    )

    result = qdrant_search(params)

    assert len(result.results) == 1
    assert result.results[0].payload["story_id"] == "story-123"
    # Verify filter was passed to search
    mock_qdrant_sdk.search.assert_called_once()
    call_args = mock_qdrant_sdk.search.call_args
    assert call_args.kwargs["query_filter"] is not None


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_with_score_threshold(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
):
    """Test search with score threshold."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_sdk = mock_qdrant_client.get_client.return_value

    mock_hit = Mock()
    mock_hit.id = "result-1"
    mock_hit.score = 0.95
    mock_hit.payload = {"type": "scene"}

    mock_qdrant_sdk.search.return_value = [mock_hit]

    params = VectorSearch(
        collection="scenes",
        query_vector=sample_vector,
        top_k=10,
        score_threshold=0.7,
    )

    result = qdrant_search(params)

    assert len(result.results) == 1
    # Verify score_threshold was passed to search
    call_args = mock_qdrant_sdk.search.call_args
    assert call_args.kwargs["score_threshold"] == 0.7


# =============================================================================
# TESTS: qdrant_delete
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_success(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test successful vector deletion."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_sdk = mock_qdrant_client.get_client.return_value

    params = VectorDelete(collection="scenes", id="test-id-1")

    result = qdrant_delete(params)

    assert result.success is True
    assert result.collection == "scenes"
    assert result.id == "test-id-1"
    mock_qdrant_sdk.delete.assert_called_once()


# =============================================================================
# TESTS: qdrant_delete_by_filter
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_by_filter_success(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test successful deletion by filter."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_sdk = mock_qdrant_client.get_client.return_value

    # Mock count result
    mock_count_result = Mock()
    mock_count_result.count = 5
    mock_qdrant_sdk.count.return_value = mock_count_result

    params = VectorDeleteByFilter(
        collection="scenes",
        filter={"story_id": "story-123"},
    )

    result = qdrant_delete_by_filter(params)

    assert result.success is True
    assert result.collection == "scenes"
    assert result.count == 5
    mock_qdrant_sdk.count.assert_called_once()
    mock_qdrant_sdk.delete.assert_called_once()


# =============================================================================
# TESTS: qdrant_get_collection_info
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_get_collection_info_success(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test getting collection information."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_sdk = mock_qdrant_client.get_client.return_value

    # Mock collection info
    mock_collection = Mock()
    mock_collection.points_count = 100
    mock_collection.config.params.vectors.size = 1536
    mock_collection.config.params.vectors.distance.name = "COSINE"
    mock_qdrant_sdk.get_collection.return_value = mock_collection

    params = CollectionInfoRequest(collection="scenes")

    result = qdrant_get_collection_info(params)

    assert result.collection == "scenes"
    assert result.vector_count == 100
    assert result.vector_size == 1536
    assert result.distance == "COSINE"


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_get_collection_info_not_found(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test getting info for non-existent collection."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_sdk = mock_qdrant_client.get_client.return_value

    mock_qdrant_sdk.get_collection.side_effect = Exception("Collection not found")

    params = CollectionInfoRequest(collection="nonexistent")

    with pytest.raises(ValueError, match="Collection nonexistent not found"):
        qdrant_get_collection_info(params)
