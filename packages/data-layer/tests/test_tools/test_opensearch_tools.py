"""
Unit tests for OpenSearch tools.

Tests cover:
- opensearch_index_document
- opensearch_get_document
- opensearch_search
- opensearch_delete_document
- opensearch_delete_by_query
"""

from typing import Dict, Any
from unittest.mock import Mock, patch

import pytest
from opensearchpy.exceptions import NotFoundError

from monitor_data.schemas.opensearch import (
    DocumentIndexRequest,
    DocumentGetRequest,
    DocumentDeleteRequest,
    SearchRequest,
    DeleteByQueryRequest,
)
from monitor_data.tools.opensearch_tools import (
    opensearch_index_document,
    opensearch_get_document,
    opensearch_search,
    opensearch_delete_document,
    opensearch_delete_by_query,
)


# =============================================================================
# TESTS: opensearch_index_document
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_index_document_success(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test successful document indexing."""
    mock_get_client.return_value = mock_opensearch_client

    # Configure mock response
    mock_opensearch_client.index_document.return_value = {
        "_id": "snippet_123",
        "_index": "snippets",
        "result": "created",
        "_version": 1,
    }

    params = DocumentIndexRequest(
        index="snippets",
        id="snippet_123",
        body={
            "id": "snippet_123",
            "type": "snippet",
            "text": "This is a test snippet",
            "universe_id": "universe_456",
        },
        refresh=True,
    )

    result = opensearch_index_document(params)

    assert result.id == "snippet_123"
    assert result.index == "snippets"
    assert result.result == "created"
    assert result.version == 1

    mock_opensearch_client.index_document.assert_called_once_with(
        index="snippets",
        doc_id="snippet_123",
        body=params.body,
        refresh=True,
    )


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_index_document_update(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test document update (upsert)."""
    mock_get_client.return_value = mock_opensearch_client

    # Configure mock response for update
    mock_opensearch_client.index_document.return_value = {
        "_id": "fact_789",
        "_index": "facts",
        "result": "updated",
        "_version": 2,
    }

    params = DocumentIndexRequest(
        index="facts",
        id="fact_789",
        body={
            "id": "fact_789",
            "type": "fact",
            "text": "Updated fact content",
        },
        refresh=False,
    )

    result = opensearch_index_document(params)

    assert result.result == "updated"
    assert result.version == 2


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_index_creates_index_if_not_exists(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test that indexing creates index if it doesn't exist."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.index_document.return_value = {
        "_id": "doc_1",
        "_index": "new_index",
        "result": "created",
        "_version": 1,
    }

    params = DocumentIndexRequest(
        index="new_index",
        id="doc_1",
        body={"text": "content"},
    )

    result = opensearch_index_document(params)

    assert result.id == "doc_1"
    # The index_document method in client handles auto-creation


# =============================================================================
# TESTS: opensearch_get_document
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_get_document_found(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test retrieving an existing document."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.get_document.return_value = {
        "_id": "snippet_123",
        "_index": "snippets",
        "found": True,
        "_source": {
            "id": "snippet_123",
            "type": "snippet",
            "text": "Test content",
        },
        "_version": 1,
    }

    params = DocumentGetRequest(index="snippets", id="snippet_123")

    result = opensearch_get_document(params)

    assert result.id == "snippet_123"
    assert result.found is True
    assert result.source is not None
    assert result.source["text"] == "Test content"
    assert result.version == 1


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_get_document_not_found(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test retrieving a non-existent document."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.get_document.return_value = None

    params = DocumentGetRequest(index="snippets", id="nonexistent")

    result = opensearch_get_document(params)

    assert result.found is False
    assert result.source is None
    assert result.version is None


# =============================================================================
# TESTS: opensearch_search
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_keyword(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test keyword search."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.search.return_value = {
        "took": 5,
        "hits": {
            "total": {"value": 2},
            "max_score": 1.5,
            "hits": [
                {
                    "_id": "doc_1",
                    "_index": "snippets",
                    "_score": 1.5,
                    "_source": {"text": "dragon keyword appears here"},
                    "highlight": {"text": ["<em>dragon</em> keyword appears here"]},
                },
                {
                    "_id": "doc_2",
                    "_index": "snippets",
                    "_score": 1.2,
                    "_source": {"text": "another dragon reference"},
                    "highlight": {"text": ["another <em>dragon</em> reference"]},
                },
            ],
        },
    }

    params = SearchRequest(
        index="snippets",
        query="dragon",
        query_type="match",
        highlight=True,
    )

    result = opensearch_search(params)

    assert result.total == 2
    assert result.max_score == 1.5
    assert len(result.hits) == 2
    assert result.hits[0].id == "doc_1"
    assert result.hits[0].highlight is not None
    assert "<em>dragon</em>" in result.hits[0].highlight["text"][0]


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_phrase(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test phrase search for exact matches."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.search.return_value = {
        "took": 3,
        "hits": {
            "total": {"value": 1},
            "max_score": 2.0,
            "hits": [
                {
                    "_id": "doc_1",
                    "_index": "facts",
                    "_score": 2.0,
                    "_source": {"text": "the ancient dragon awakens"},
                }
            ],
        },
    }

    params = SearchRequest(
        index="facts",
        query="ancient dragon",
        query_type="match_phrase",
        highlight=False,
    )

    result = opensearch_search(params)

    assert result.total == 1
    assert result.hits[0].source["text"] == "the ancient dragon awakens"


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_with_filters(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test search with field filters (universe_id, type)."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.search.return_value = {
        "took": 4,
        "hits": {
            "total": {"value": 1},
            "max_score": 1.0,
            "hits": [
                {
                    "_id": "snippet_1",
                    "_index": "snippets",
                    "_score": 1.0,
                    "_source": {
                        "text": "filtered content",
                        "universe_id": "universe_123",
                        "type": "snippet",
                    },
                }
            ],
        },
    }

    params = SearchRequest(
        index="snippets",
        query="content",
        filters={"universe_id": "universe_123", "type": "snippet"},
    )

    result = opensearch_search(params)

    assert result.total == 1
    assert result.hits[0].source["universe_id"] == "universe_123"

    # Verify filters were passed correctly
    mock_opensearch_client.search.assert_called_once()
    call_args = mock_opensearch_client.search.call_args
    assert call_args[1]["filters"] == {"universe_id": "universe_123", "type": "snippet"}


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_with_highlight(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test search returns highlighted snippets."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.search.return_value = {
        "took": 2,
        "hits": {
            "total": {"value": 1},
            "max_score": 1.0,
            "hits": [
                {
                    "_id": "doc_1",
                    "_index": "snippets",
                    "_score": 1.0,
                    "_source": {"text": "highlighted term appears here"},
                    "highlight": {
                        "text": ["<em>highlighted</em> term appears here"]
                    },
                }
            ],
        },
    }

    params = SearchRequest(
        index="snippets",
        query="highlighted",
        highlight=True,
        highlight_fields=["text"],
    )

    result = opensearch_search(params)

    assert result.hits[0].highlight is not None
    assert "text" in result.hits[0].highlight
    assert "<em>highlighted</em>" in result.hits[0].highlight["text"][0]


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_with_pagination(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test search pagination with from/size parameters."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.search.return_value = {
        "took": 3,
        "hits": {
            "total": {"value": 50},
            "max_score": 1.0,
            "hits": [
                {
                    "_id": f"doc_{i}",
                    "_index": "snippets",
                    "_score": 1.0,
                    "_source": {"text": f"content {i}"},
                }
                for i in range(20, 25)  # Simulating page 2 with size 5
            ],
        },
    }

    params = SearchRequest(
        index="snippets",
        query="content",
        from_=20,
        size=5,
    )

    result = opensearch_search(params)

    assert result.total == 50
    assert len(result.hits) == 5

    # Verify pagination parameters were passed
    call_args = mock_opensearch_client.search.call_args
    assert call_args[1]["from_"] == 20
    assert call_args[1]["size"] == 5


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_multi_field(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test multi-field search."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.search.return_value = {
        "took": 2,
        "hits": {
            "total": {"value": 1},
            "max_score": 1.0,
            "hits": [
                {
                    "_id": "doc_1",
                    "_index": "facts",
                    "_score": 1.0,
                    "_source": {"text": "content", "title": "matching title"},
                }
            ],
        },
    }

    params = SearchRequest(
        index="facts",
        query="matching",
        query_type="multi_match",
        fields=["text", "title"],
    )

    result = opensearch_search(params)

    assert result.total == 1


# =============================================================================
# TESTS: opensearch_delete_document
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_document_success(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test successful document deletion."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.delete_document.return_value = {
        "_id": "snippet_123",
        "_index": "snippets",
        "result": "deleted",
        "_version": 2,
    }

    params = DocumentDeleteRequest(index="snippets", id="snippet_123")

    result = opensearch_delete_document(params)

    assert result.id == "snippet_123"
    assert result.result == "deleted"
    assert result.version == 2


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_document_not_found(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test deleting a non-existent document."""
    mock_get_client.return_value = mock_opensearch_client

    # Simulate NotFoundError from OpenSearch
    mock_opensearch_client.delete_document.side_effect = NotFoundError(
        404, "document not found"
    )

    params = DocumentDeleteRequest(index="snippets", id="nonexistent")

    result = opensearch_delete_document(params)

    assert result.result == "not_found"
    assert result.version is None


# =============================================================================
# TESTS: opensearch_delete_by_query
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_by_query_success(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test deleting documents by query."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.delete_by_query.return_value = {
        "deleted": 5,
        "total": 5,
        "took": 10,
    }

    params = DeleteByQueryRequest(
        index="snippets",
        query="test",
        query_type="match",
    )

    result = opensearch_delete_by_query(params)

    assert result.deleted == 5
    assert result.total == 5
    assert result.took == 10


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_by_query_with_filters(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test deleting documents with filters."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.delete_by_query.return_value = {
        "deleted": 3,
        "total": 3,
        "took": 8,
    }

    params = DeleteByQueryRequest(
        index="snippets",
        query="outdated",
        filters={"universe_id": "universe_123"},
    )

    result = opensearch_delete_by_query(params)

    assert result.deleted == 3

    # Verify filters were applied
    call_args = mock_opensearch_client.delete_by_query.call_args
    query = call_args[1]["query"]
    # Should have bool query with filters
    assert "bool" in query


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_by_query_no_matches(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test delete by query when no documents match."""
    mock_get_client.return_value = mock_opensearch_client

    mock_opensearch_client.delete_by_query.return_value = {
        "deleted": 0,
        "total": 0,
        "took": 2,
    }

    params = DeleteByQueryRequest(
        index="snippets",
        query="nonexistent_term",
    )

    result = opensearch_delete_by_query(params)

    assert result.deleted == 0
    assert result.total == 0


# =============================================================================
# TESTS: Error Handling
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_invalid_query_type(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test that invalid query type raises ValueError."""
    mock_get_client.return_value = mock_opensearch_client

    params = SearchRequest(
        index="snippets",
        query="test",
        query_type="invalid_type",
    )

    with pytest.raises(ValueError, match="Unsupported query_type"):
        opensearch_search(params)


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_by_query_invalid_query_type(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
):
    """Test that invalid query type raises ValueError."""
    mock_get_client.return_value = mock_opensearch_client

    params = DeleteByQueryRequest(
        index="snippets",
        query="test",
        query_type="invalid_type",
    )

    with pytest.raises(ValueError, match="Unsupported query_type"):
        opensearch_delete_by_query(params)
