"""
Unit tests for OpenSearch client (DL-11).

Tests cover:
- OpenSearchClient connection management
- Index management and creation
- Client operations
- Singleton pattern
"""

from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
import pytest

from opensearchpy import NotFoundError

from monitor_data.db.opensearch import (
    OpenSearchClient,
    get_opensearch_client,
    reset_opensearch_client,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_opensearch() -> Mock:
    """Provide a mock OpenSearch instance."""
    mock = Mock()
    mock.ping.return_value = True
    mock.indices.exists.return_value = False
    mock.indices.create.return_value = {"acknowledged": True}
    mock.index.return_value = {"result": "created"}
    mock.get.return_value = {"_id": "test", "_source": {}}
    mock.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
    mock.delete.return_value = {"result": "deleted"}
    mock.delete_by_query.return_value = {"deleted": 0}
    mock.close.return_value = None
    return mock


# =============================================================================
# TESTS: OpenSearchClient initialization
# =============================================================================


def test_client_initialization_default() -> None:
    """Test client initializes with default values."""
    client = OpenSearchClient()

    assert client._client is None
    assert client.hosts is not None
    assert isinstance(client.hosts, list)
    assert client.http_auth is not None
    assert isinstance(client.http_auth, tuple)


def test_client_initialization_custom() -> None:
    """Test client initializes with custom values."""
    hosts = ["localhost:9200", "localhost:9201"]
    http_auth = ("user", "pass")

    client = OpenSearchClient(
        hosts=hosts,
        http_auth=http_auth,
        use_ssl=True,
        verify_certs=True,
    )

    assert client.hosts == hosts
    assert client.http_auth == http_auth
    assert client.use_ssl is True
    assert client.verify_certs is True


# =============================================================================
# TESTS: Connection management
# =============================================================================


@patch("monitor_data.db.opensearch.OpenSearch")
def test_connect(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test connecting to OpenSearch."""
    mock_opensearch_class.return_value = mock_opensearch

    client = OpenSearchClient()
    client.connect()

    assert client._client is not None
    mock_opensearch_class.assert_called_once()


@patch("monitor_data.db.opensearch.OpenSearch")
def test_connect_idempotent(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test connecting multiple times is idempotent."""
    mock_opensearch_class.return_value = mock_opensearch

    client = OpenSearchClient()
    client.connect()
    client.connect()  # Second call should not create new client

    assert mock_opensearch_class.call_count == 1


@patch("monitor_data.db.opensearch.OpenSearch")
def test_close(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test closing OpenSearch connection."""
    mock_opensearch_class.return_value = mock_opensearch

    client = OpenSearchClient()
    client.connect()
    client.close()

    assert client._client is None
    assert client._indexes_created == {}
    mock_opensearch.close.assert_called_once()


@patch("monitor_data.db.opensearch.OpenSearch")
def test_verify_connectivity_success(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test verifying successful connection."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.ping.return_value = True

    client = OpenSearchClient()
    result = client.verify_connectivity()

    assert result is True
    mock_opensearch.ping.assert_called_once()


@patch("monitor_data.db.opensearch.OpenSearch")
def test_verify_connectivity_failure(mock_opensearch_class: Mock) -> None:
    """Test verifying failed connection."""
    mock_opensearch_instance = Mock()
    mock_opensearch_instance.ping.side_effect = Exception("Connection failed")
    mock_opensearch_class.return_value = mock_opensearch_instance

    client = OpenSearchClient()
    result = client.verify_connectivity()

    assert result is False


@patch("monitor_data.db.opensearch.OpenSearch")
def test_get_client_not_connected(mock_opensearch_class: Mock) -> None:
    """Test getting client raises error if not connected."""
    client = OpenSearchClient()

    with pytest.raises(RuntimeError, match="not connected"):
        client.get_client()


@patch("monitor_data.db.opensearch.OpenSearch")
def test_get_client_connected(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test getting client returns OpenSearch instance."""
    mock_opensearch_class.return_value = mock_opensearch

    client = OpenSearchClient()
    client.connect()
    result = client.get_client()

    assert result is mock_opensearch


# =============================================================================
# TESTS: Index management
# =============================================================================


@patch("monitor_data.db.opensearch.OpenSearch")
def test_ensure_index_creates_new(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test ensure_index creates index if it doesn't exist."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.indices.exists.return_value = False

    client = OpenSearchClient()
    client.connect()
    client.ensure_index("test-index")

    mock_opensearch.indices.exists.assert_called_once_with(index="test-index")
    mock_opensearch.indices.create.assert_called_once()


@patch("monitor_data.db.opensearch.OpenSearch")
def test_ensure_index_exists(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test ensure_index skips creation if index exists."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.indices.exists.return_value = True

    client = OpenSearchClient()
    client.connect()
    client.ensure_index("existing-index")

    mock_opensearch.indices.exists.assert_called_once()
    mock_opensearch.indices.create.assert_not_called()


@patch("monitor_data.db.opensearch.OpenSearch")
def test_ensure_index_cached(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test ensure_index uses cache for repeated calls."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.indices.exists.return_value = False

    client = OpenSearchClient()
    client.connect()

    # First call creates index
    client.ensure_index("test-index")
    assert mock_opensearch.indices.create.call_count == 1

    # Second call uses cache
    client.ensure_index("test-index")
    assert mock_opensearch.indices.create.call_count == 1  # No additional call


@patch("monitor_data.db.opensearch.OpenSearch")
def test_ensure_index_custom_mappings(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test ensure_index with custom mappings."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.indices.exists.return_value = False

    custom_mappings = {
        "settings": {"number_of_shards": 2},
        "mappings": {"properties": {"custom_field": {"type": "text"}}},
    }

    client = OpenSearchClient()
    client.connect()
    client.ensure_index("custom-index", mappings=custom_mappings)

    # Verify custom mappings were used
    call_args = mock_opensearch.indices.create.call_args
    assert call_args[1]["body"] == custom_mappings


@patch("monitor_data.db.opensearch.OpenSearch")
def test_get_default_mappings(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test default mappings structure."""
    client = OpenSearchClient()
    mappings = client._get_default_mappings()

    assert "settings" in mappings
    assert "mappings" in mappings
    assert "properties" in mappings["mappings"]

    # Check expected fields
    properties = mappings["mappings"]["properties"]
    assert "id" in properties
    assert "type" in properties
    assert "universe_id" in properties
    assert "text" in properties
    assert "metadata" in properties


# =============================================================================
# TESTS: Document operations
# =============================================================================


@patch("monitor_data.db.opensearch.OpenSearch")
def test_index_document(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test indexing a document."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.indices.exists.return_value = True
    mock_opensearch.index.return_value = {"result": "created", "_id": "doc1"}

    client = OpenSearchClient()
    client.connect()

    body = {"text": "test content"}
    result = client.index_document("test-index", "doc1", body, refresh=True)

    assert result["result"] == "created"
    mock_opensearch.index.assert_called_once_with(
        index="test-index",
        id="doc1",
        body=body,
        refresh="wait_for",
    )


@patch("monitor_data.db.opensearch.OpenSearch")
def test_index_document_no_refresh(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test indexing without refresh."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.indices.exists.return_value = True

    client = OpenSearchClient()
    client.connect()

    body = {"text": "test"}
    client.index_document("test-index", "doc1", body, refresh=False)

    call_args = mock_opensearch.index.call_args
    assert call_args[1]["refresh"] is False


@patch("monitor_data.db.opensearch.OpenSearch")
def test_get_document_found(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test getting an existing document."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.get.return_value = {"_id": "doc1", "_source": {"text": "content"}}

    client = OpenSearchClient()
    client.connect()

    result = client.get_document("test-index", "doc1")

    assert result is not None
    assert result["_id"] == "doc1"
    mock_opensearch.get.assert_called_once_with(index="test-index", id="doc1")


@patch("monitor_data.db.opensearch.OpenSearch")
def test_get_document_not_found(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test getting a non-existent document."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.get.side_effect = NotFoundError(404, "not found")

    client = OpenSearchClient()
    client.connect()

    result = client.get_document("test-index", "nonexistent")

    assert result is None


@patch("monitor_data.db.opensearch.OpenSearch")
def test_search(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test searching documents."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.search.return_value = {
        "hits": {"total": {"value": 1}, "hits": [{"_id": "doc1"}]}
    }

    client = OpenSearchClient()
    client.connect()

    query = {"match": {"text": "search term"}}
    result = client.search("test-index", query, from_=0, size=10)

    assert result["hits"]["total"]["value"] == 1
    mock_opensearch.search.assert_called_once()


@patch("monitor_data.db.opensearch.OpenSearch")
def test_search_with_highlight(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test searching with highlighting."""
    mock_opensearch_class.return_value = mock_opensearch

    client = OpenSearchClient()
    client.connect()

    query = {"match": {"text": "search"}}
    highlight = {"fields": {"text": {}}}

    client.search("test-index", query, highlight=highlight)

    call_args = mock_opensearch.search.call_args
    assert "highlight" in call_args[1]["body"]


@patch("monitor_data.db.opensearch.OpenSearch")
def test_delete_document(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test deleting a document."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.delete.return_value = {"result": "deleted"}

    client = OpenSearchClient()
    client.connect()

    result = client.delete_document("test-index", "doc1")

    assert result["result"] == "deleted"
    mock_opensearch.delete.assert_called_once_with(index="test-index", id="doc1")


@patch("monitor_data.db.opensearch.OpenSearch")
def test_delete_by_query(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test deleting documents by query."""
    mock_opensearch_class.return_value = mock_opensearch
    mock_opensearch.delete_by_query.return_value = {"deleted": 5}

    client = OpenSearchClient()
    client.connect()

    query = {"term": {"universe_id": "test-universe"}}
    result = client.delete_by_query("test-index", query)

    assert result["deleted"] == 5
    mock_opensearch.delete_by_query.assert_called_once()


# =============================================================================
# TESTS: Singleton pattern
# =============================================================================


@patch("monitor_data.db.opensearch.OpenSearch")
def test_get_opensearch_client_singleton(mock_opensearch_class: Mock, mock_opensearch: Mock) -> None:
    """Test get_opensearch_client returns singleton."""
    mock_opensearch_class.return_value = mock_opensearch

    # Reset to ensure clean state
    reset_opensearch_client()

    client1 = get_opensearch_client()
    client2 = get_opensearch_client()

    assert client1 is client2
    assert mock_opensearch_class.call_count == 1


@patch("monitor_data.db.opensearch.OpenSearch")
def test_reset_opensearch_client(mock_opensearch_class: Mock) -> None:
    """Test resetting the singleton client."""
    # Create a mock instance
    mock_opensearch1 = Mock()
    mock_opensearch1.ping.return_value = True
    mock_opensearch1.close.return_value = None
    
    mock_opensearch2 = Mock()
    mock_opensearch2.ping.return_value = True

    # First call returns mock1, second call returns mock2
    mock_opensearch_class.side_effect = [mock_opensearch1, mock_opensearch2]

    # Ensure clean state
    reset_opensearch_client()
    
    client1 = get_opensearch_client()
    reset_opensearch_client()
    client2 = get_opensearch_client()

    assert client1 is not client2
    # Verify close was called on the first client
    mock_opensearch1.close.assert_called_once()
