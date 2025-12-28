"""
Unit tests for Qdrant vector operations (DL-10).

Tests cover:
- qdrant_upsert (single vector)
- qdrant_upsert_batch (multiple vectors)
- qdrant_search (with filters and threshold)
- qdrant_delete (single point)
- qdrant_delete_by_filter (batch deletion)
- qdrant_get_collection_info
- qdrant_create_collection
"""

from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

import pytest

from monitor_data.schemas.vectors import (
    VectorPayload,
    VectorUpsert,
    VectorPoint,
    VectorUpsertBatch,
    VectorSearchFilter,
    VectorSearch,
    VectorDelete,
    VectorDeleteByFilter,
    CollectionCreate,
)
from monitor_data.tools.qdrant_tools import (
    qdrant_upsert,
    qdrant_upsert_batch,
    qdrant_search,
    qdrant_delete,
    qdrant_delete_by_filter,
    qdrant_get_collection_info,
    qdrant_create_collection,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_qdrant_client() -> Mock:
    """Provide a mock Qdrant client for testing."""
    mock_client = Mock()
    mock_client.collection_exists = Mock(return_value=True)
    mock_client.create_collection = Mock()
    mock_client.get_collection_info = Mock()
    mock_client.upsert = Mock()
    mock_client.upsert_batch = Mock()
    mock_client.search = Mock(return_value=[])
    mock_client.delete = Mock()
    mock_client.delete_by_filter = Mock(return_value=0)
    return mock_client


@pytest.fixture
def sample_vector() -> List[float]:
    """Provide a sample 384-dimensional vector."""
    return [0.1] * 384


@pytest.fixture
def sample_payload() -> Dict[str, Any]:
    """Provide a sample payload."""
    return {
        "id": str(uuid4()),
        "type": "scene",
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "text": "A sample scene description",
        "metadata": {}
    }


# =============================================================================
# TESTS: qdrant_get_collection_info
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_get_collection_info_exists(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test getting info for an existing collection."""
    mock_get_client.return_value = mock_qdrant_client
    
    mock_qdrant_client.get_collection_info.return_value = {
        "name": "test_collection",
        "exists": True,
        "vector_size": 384,
        "points_count": 100,
        "config": {"distance": "Cosine"}
    }
    
    result = qdrant_get_collection_info("test_collection")
    
    assert result.name == "test_collection"
    assert result.exists is True
    assert result.vector_size == 384
    assert result.points_count == 100
    assert result.config["distance"] == "Cosine"
    mock_qdrant_client.get_collection_info.assert_called_once_with("test_collection")


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_get_collection_info_not_exists(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test getting info for a non-existent collection."""
    mock_get_client.return_value = mock_qdrant_client
    
    mock_qdrant_client.get_collection_info.return_value = {
        "name": "missing_collection",
        "exists": False,
        "vector_size": 0,
        "points_count": 0,
    }
    
    result = qdrant_get_collection_info("missing_collection")
    
    assert result.name == "missing_collection"
    assert result.exists is False
    assert result.vector_size == 0
    assert result.points_count == 0


# =============================================================================
# TESTS: qdrant_create_collection
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_create_collection_success(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test successful collection creation."""
    mock_get_client.return_value = mock_qdrant_client
    
    mock_qdrant_client.collection_exists.return_value = False
    mock_qdrant_client.get_collection_info.return_value = {
        "name": "new_collection",
        "exists": True,
        "vector_size": 384,
        "points_count": 0,
        "config": {"distance": "Cosine"}
    }
    
    params = CollectionCreate(
        name="new_collection",
        vector_size=384,
        distance="Cosine"
    )
    
    result = qdrant_create_collection(params)
    
    assert result.name == "new_collection"
    assert result.vector_size == 384
    mock_qdrant_client.create_collection.assert_called_once_with(
        collection_name="new_collection",
        vector_size=384,
        distance="Cosine"
    )


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_create_collection_already_exists(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test creating a collection that already exists."""
    mock_get_client.return_value = mock_qdrant_client
    
    mock_qdrant_client.collection_exists.return_value = True
    
    params = CollectionCreate(
        name="existing_collection",
        vector_size=384
    )
    
    with pytest.raises(ValueError, match="already exists"):
        qdrant_create_collection(params)


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
    """Test successful single vector upsert."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_client.collection_exists.return_value = True
    
    payload = VectorPayload(**sample_payload)
    params = VectorUpsert(
        collection="scenes",
        id=sample_payload["id"],
        vector=sample_vector,
        payload=payload
    )
    
    result = qdrant_upsert(params)
    
    assert result["success"] is True
    assert result["collection"] == "scenes"
    assert result["id"] == sample_payload["id"]
    assert result["vector_size"] == 384
    mock_qdrant_client.upsert.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_creates_collection(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
    sample_payload: Dict[str, Any],
):
    """Test upsert creates collection if it doesn't exist."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_client.collection_exists.return_value = False
    
    payload = VectorPayload(**sample_payload)
    params = VectorUpsert(
        collection="new_scenes",
        id=sample_payload["id"],
        vector=sample_vector,
        payload=payload
    )
    
    result = qdrant_upsert(params)
    
    assert result["success"] is True
    mock_qdrant_client.create_collection.assert_called_once_with(
        collection_name="new_scenes",
        vector_size=384,
        distance="Cosine"
    )
    mock_qdrant_client.upsert.assert_called_once()


# =============================================================================
# TESTS: qdrant_upsert_batch
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_batch_success(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
):
    """Test successful batch upsert."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_client.collection_exists.return_value = True
    
    points = [
        VectorPoint(
            id=str(uuid4()),
            vector=sample_vector,
            payload={"type": "scene", "story_id": str(uuid4())}
        )
        for _ in range(3)
    ]
    
    params = VectorUpsertBatch(
        collection="scenes",
        points=points
    )
    
    result = qdrant_upsert_batch(params)
    
    assert result["success"] is True
    assert result["collection"] == "scenes"
    assert result["count"] == 3
    assert result["vector_size"] == 384
    mock_qdrant_client.upsert_batch.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_batch_empty(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test batch upsert with empty points list."""
    mock_get_client.return_value = mock_qdrant_client
    
    params = VectorUpsertBatch(
        collection="scenes",
        points=[]
    )
    
    with pytest.raises(ValueError, match="cannot be empty"):
        qdrant_upsert_batch(params)


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_upsert_batch_inconsistent_dimensions(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
):
    """Test batch upsert with inconsistent vector dimensions."""
    mock_get_client.return_value = mock_qdrant_client
    
    points = [
        VectorPoint(
            id=str(uuid4()),
            vector=[0.1] * 384,
            payload={"type": "scene"}
        ),
        VectorPoint(
            id=str(uuid4()),
            vector=[0.1] * 512,  # Different dimension
            payload={"type": "scene"}
        ),
    ]
    
    params = VectorUpsertBatch(
        collection="scenes",
        points=points
    )
    
    with pytest.raises(ValueError, match="same dimension"):
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
    """Test basic vector search without filters."""
    mock_get_client.return_value = mock_qdrant_client
    
    mock_qdrant_client.search.return_value = [
        {"id": str(uuid4()), "score": 0.95, "payload": {"type": "scene"}},
        {"id": str(uuid4()), "score": 0.87, "payload": {"type": "scene"}},
    ]
    
    params = VectorSearch(
        collection="scenes",
        query_vector=sample_vector,
        top_k=10
    )
    
    result = qdrant_search(params)
    
    assert result.collection == "scenes"
    assert result.count == 2
    assert len(result.results) == 2
    assert result.results[0].score == 0.95
    mock_qdrant_client.search.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_with_filter(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
):
    """Test search with payload filter."""
    mock_get_client.return_value = mock_qdrant_client
    
    story_id = str(uuid4())
    mock_qdrant_client.search.return_value = [
        {"id": str(uuid4()), "score": 0.92, "payload": {"type": "scene", "story_id": story_id}},
    ]
    
    search_filter = VectorSearchFilter(
        story_id=story_id,
        type="scene"
    )
    
    params = VectorSearch(
        collection="scenes",
        query_vector=sample_vector,
        top_k=5,
        filter=search_filter
    )
    
    result = qdrant_search(params)
    
    assert result.count == 1
    assert result.results[0].payload["story_id"] == story_id
    
    # Verify filter was passed correctly
    call_args = mock_qdrant_client.search.call_args
    assert call_args[1]["query_filter"] == {"story_id": story_id, "type": "scene"}


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_with_threshold(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
):
    """Test search with score threshold."""
    mock_get_client.return_value = mock_qdrant_client
    
    mock_qdrant_client.search.return_value = [
        {"id": str(uuid4()), "score": 0.95, "payload": {"type": "scene"}},
    ]
    
    params = VectorSearch(
        collection="scenes",
        query_vector=sample_vector,
        top_k=10,
        score_threshold=0.9
    )
    
    result = qdrant_search(params)
    
    assert result.count == 1
    assert result.results[0].score >= 0.9
    
    # Verify threshold was passed
    call_args = mock_qdrant_client.search.call_args
    assert call_args[1]["score_threshold"] == 0.9


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_search_collection_not_exists(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
    sample_vector: List[float],
):
    """Test search on non-existent collection."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_client.collection_exists.return_value = False
    
    params = VectorSearch(
        collection="missing_collection",
        query_vector=sample_vector
    )
    
    with pytest.raises(ValueError, match="does not exist"):
        qdrant_search(params)


# =============================================================================
# TESTS: qdrant_delete
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_success(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test successful point deletion."""
    mock_get_client.return_value = mock_qdrant_client
    
    point_id = str(uuid4())
    params = VectorDelete(
        collection="scenes",
        id=point_id
    )
    
    result = qdrant_delete(params)
    
    assert result.deleted is True
    assert result.count == 1
    mock_qdrant_client.delete.assert_called_once_with(
        collection_name="scenes",
        point_id=point_id
    )


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_collection_not_exists(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
):
    """Test delete on non-existent collection."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_client.collection_exists.return_value = False
    
    params = VectorDelete(
        collection="missing_collection",
        id=str(uuid4())
    )
    
    with pytest.raises(ValueError, match="does not exist"):
        qdrant_delete(params)


# =============================================================================
# TESTS: qdrant_delete_by_filter
# =============================================================================


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_by_filter_success(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test successful batch deletion by filter."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_client.delete_by_filter.return_value = 5
    
    search_filter = VectorSearchFilter(
        story_id=str(uuid4()),
        type="scene"
    )
    
    params = VectorDeleteByFilter(
        collection="scenes",
        filter=search_filter
    )
    
    result = qdrant_delete_by_filter(params)
    
    assert result.deleted is True
    assert result.count == 5
    mock_qdrant_client.delete_by_filter.assert_called_once()


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_by_filter_empty(mock_get_client: Mock, mock_qdrant_client: Mock):
    """Test delete by filter with empty filter."""
    mock_get_client.return_value = mock_qdrant_client
    
    # All fields None means empty filter
    search_filter = VectorSearchFilter()
    
    params = VectorDeleteByFilter(
        collection="scenes",
        filter=search_filter
    )
    
    with pytest.raises(ValueError, match="At least one filter"):
        qdrant_delete_by_filter(params)


@patch("monitor_data.tools.qdrant_tools.get_qdrant_client")
def test_delete_by_filter_collection_not_exists(
    mock_get_client: Mock,
    mock_qdrant_client: Mock,
):
    """Test delete by filter on non-existent collection."""
    mock_get_client.return_value = mock_qdrant_client
    mock_qdrant_client.collection_exists.return_value = False
    
    search_filter = VectorSearchFilter(story_id=str(uuid4()))
    
    params = VectorDeleteByFilter(
        collection="missing_collection",
        filter=search_filter
    )
    
    with pytest.raises(ValueError, match="does not exist"):
        qdrant_delete_by_filter(params)
