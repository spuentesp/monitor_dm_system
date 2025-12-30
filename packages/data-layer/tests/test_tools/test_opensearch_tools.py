"""
Unit tests for OpenSearch operations (DL-11).

Tests cover:
- opensearch_index_document
- opensearch_get_document
- opensearch_search
- opensearch_delete_document
- opensearch_delete_by_query
"""

from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

import pytest
from opensearchpy import NotFoundError

from monitor_data.tools.opensearch_tools import (
    opensearch_index_document,
    opensearch_get_document,
    opensearch_search,
    opensearch_delete_document,
    opensearch_delete_by_query,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_opensearch_client() -> Mock:
    """Provide a mock OpenSearch client."""
    client = Mock()
    return client


@pytest.fixture
def sample_document() -> Dict[str, Any]:
    """Provide sample document data."""
    return {
        "id": str(uuid4()),
        "type": "snippet",
        "universe_id": str(uuid4()),
        "text": "The hero ventured into the dark forest seeking the ancient artifact.",
        "metadata": {
            "source": "chapter_1",
            "page": 42,
        },
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_search_result() -> Dict[str, Any]:
    """Provide sample search result from OpenSearch."""
    return {
        "took": 5,
        "timed_out": False,
        "hits": {
            "total": {"value": 2, "relation": "eq"},
            "max_score": 1.5,
            "hits": [
                {
                    "_index": "snippets",
                    "_id": "doc1",
                    "_score": 1.5,
                    "_source": {
                        "id": "doc1",
                        "type": "snippet",
                        "universe_id": "univ-123",
                        "text": "The ancient artifact was hidden in the forest.",
                    },
                    "highlight": {
                        "text": ["The <em>ancient</em> <em>artifact</em> was hidden in the forest."]
                    },
                },
                {
                    "_index": "snippets",
                    "_id": "doc2",
                    "_score": 1.2,
                    "_source": {
                        "id": "doc2",
                        "type": "snippet",
                        "universe_id": "univ-123",
                        "text": "Legends spoke of an artifact with great power.",
                    },
                    "highlight": {
                        "text": ["Legends spoke of an <em>artifact</em> with great power."]
                    },
                },
            ],
        },
    }


# =============================================================================
# TESTS: opensearch_index_document
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_index_document_creates_new(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
    sample_document: Dict[str, Any],
) -> None:
    """Test indexing a new document."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.index_document.return_value = {
        "_index": "snippets",
        "_id": sample_document["id"],
        "_version": 1,
        "result": "created",
    }

    result = opensearch_index_document(
        index="snippets",
        doc_id=sample_document["id"],
        body=sample_document,
        refresh=True,
    )

    mock_opensearch_client.index_document.assert_called_once_with(
        index="snippets",
        doc_id=sample_document["id"],
        body=sample_document,
        refresh=True,
    )
    assert result["result"] == "created"
    assert result["_id"] == sample_document["id"]


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_index_document_updates_existing(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
    sample_document: Dict[str, Any],
) -> None:
    """Test updating an existing document (upsert)."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.index_document.return_value = {
        "_index": "snippets",
        "_id": sample_document["id"],
        "_version": 2,
        "result": "updated",
    }

    result = opensearch_index_document(
        index="snippets",
        doc_id=sample_document["id"],
        body=sample_document,
    )

    assert result["result"] == "updated"
    assert result["_version"] == 2


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_index_document_with_metadata(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test indexing document with rich metadata."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.index_document.return_value = {
        "_index": "facts",
        "_id": "fact-123",
        "_version": 1,
        "result": "created",
    }

    doc_body = {
        "id": "fact-123",
        "type": "fact",
        "universe_id": str(uuid4()),
        "text": "The kingdom fell in the year 1453.",
        "metadata": {
            "canon_level": "canon",
            "confidence": 1.0,
            "tags": ["historical", "kingdom"],
        },
    }

    result = opensearch_index_document(
        index="facts",
        doc_id="fact-123",
        body=doc_body,
    )

    assert result["result"] == "created"
    mock_opensearch_client.index_document.assert_called_once()


# =============================================================================
# TESTS: opensearch_get_document
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_get_document_found(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
    sample_document: Dict[str, Any],
) -> None:
    """Test retrieving an existing document."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.get_document.return_value = {
        "_index": "snippets",
        "_id": sample_document["id"],
        "_source": sample_document,
        "found": True,
    }

    result = opensearch_get_document(
        index="snippets",
        doc_id=sample_document["id"],
    )

    assert result is not None
    assert result["found"] is True
    assert result["_source"]["text"] == sample_document["text"]
    mock_opensearch_client.get_document.assert_called_once_with(
        index="snippets",
        doc_id=sample_document["id"],
    )


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_get_document_not_found(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test retrieving a non-existent document."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.get_document.return_value = None

    result = opensearch_get_document(
        index="snippets",
        doc_id="non-existent-id",
    )

    assert result is None


# =============================================================================
# TESTS: opensearch_search
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_keyword(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
    sample_search_result: Dict[str, Any],
) -> None:
    """Test keyword search."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.search.return_value = sample_search_result

    result = opensearch_search(
        index="snippets",
        query="artifact",
    )

    assert result["hits"]["total"]["value"] == 2
    assert len(result["hits"]["hits"]) == 2
    assert "artifact" in result["hits"]["hits"][0]["_source"]["text"].lower()

    # Verify search was called with correct parameters
    mock_opensearch_client.search.assert_called_once()
    call_args = mock_opensearch_client.search.call_args
    assert call_args[1]["index"] == "snippets"
    assert "multi_match" in call_args[1]["query"]["bool"]["must"][0]


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_phrase(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test phrase search."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.search.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_index": "snippets",
                    "_id": "doc1",
                    "_score": 2.5,
                    "_source": {
                        "text": "The ancient artifact of power.",
                    },
                }
            ],
        }
    }

    result = opensearch_search(
        index="snippets",
        query="ancient artifact",
    )

    assert result["hits"]["total"]["value"] == 1
    mock_opensearch_client.search.assert_called_once()


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_with_filters(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test search with filters (universe_id, type)."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.search.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_index": "snippets",
                    "_id": "doc1",
                    "_score": 1.5,
                    "_source": {
                        "type": "snippet",
                        "universe_id": "univ-123",
                        "text": "Forest scene",
                    },
                }
            ],
        }
    }

    universe_id = "univ-123"
    result = opensearch_search(
        index="snippets",
        query="forest",
        filters={"universe_id": universe_id, "type": "snippet"},
    )

    assert result["hits"]["total"]["value"] == 1

    # Verify filters were applied
    call_args = mock_opensearch_client.search.call_args
    query_dsl = call_args[1]["query"]
    must_clauses = query_dsl["bool"]["must"]

    # Should have 3 must clauses: 1 multi_match + 2 term filters
    assert len(must_clauses) == 3

    # Check that term filters are present
    term_filters = [c for c in must_clauses if "term" in c]
    assert len(term_filters) == 2


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_with_highlighting(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
    sample_search_result: Dict[str, Any],
) -> None:
    """Test search returns highlighted snippets."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.search.return_value = sample_search_result

    result = opensearch_search(
        index="snippets",
        query="artifact",
        highlight=True,
    )

    # Check highlighting is present
    first_hit = result["hits"]["hits"][0]
    assert "highlight" in first_hit
    assert "text" in first_hit["highlight"]
    assert "<em>" in first_hit["highlight"]["text"][0]

    # Verify highlight config was passed
    call_args = mock_opensearch_client.search.call_args
    assert call_args[1]["highlight"] is not None
    assert "fields" in call_args[1]["highlight"]


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_without_highlighting(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test search without highlighting."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.search.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_index": "snippets",
                    "_id": "doc1",
                    "_score": 1.5,
                    "_source": {"text": "Some text"},
                }
            ],
        }
    }

    result = opensearch_search(
        index="snippets",
        query="text",
        highlight=False,
    )

    # Verify no highlight config was passed
    call_args = mock_opensearch_client.search.call_args
    assert call_args[1]["highlight"] is None


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_with_pagination(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test search with pagination parameters."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.search.return_value = {
        "hits": {
            "total": {"value": 100, "relation": "eq"},
            "hits": [],
        }
    }

    result = opensearch_search(
        index="snippets",
        query="forest",
        from_=20,
        size=10,
    )

    # Verify pagination parameters were passed
    call_args = mock_opensearch_client.search.call_args
    assert call_args[1]["from_"] == 20
    assert call_args[1]["size"] == 10


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_empty_query_matches_all(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test search with empty query returns all documents."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.search.return_value = {
        "hits": {
            "total": {"value": 10, "relation": "eq"},
            "hits": [],
        }
    }

    result = opensearch_search(
        index="snippets",
        query="",
    )

    # Verify match_all query was used
    call_args = mock_opensearch_client.search.call_args
    assert "match_all" in call_args[1]["query"]


# =============================================================================
# TESTS: opensearch_delete_document
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_document(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test deleting a document by ID."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.delete_document.return_value = {
        "_index": "snippets",
        "_id": "doc-123",
        "result": "deleted",
    }

    result = opensearch_delete_document(
        index="snippets",
        doc_id="doc-123",
    )

    assert result["result"] == "deleted"
    mock_opensearch_client.delete_document.assert_called_once_with(
        index="snippets",
        doc_id="doc-123",
    )


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_document_not_found(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test deleting a non-existent document raises error."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.delete_document.side_effect = NotFoundError(
        404, "document not found"
    )

    with pytest.raises(NotFoundError):
        opensearch_delete_document(
            index="snippets",
            doc_id="non-existent",
        )


# =============================================================================
# TESTS: opensearch_delete_by_query
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_by_query_with_filters(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test deleting documents matching filter criteria."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.delete_by_query.return_value = {
        "deleted": 5,
        "took": 100,
        "batches": 1,
    }

    result = opensearch_delete_by_query(
        index="snippets",
        filters={"universe_id": "univ-123"},
    )

    assert result["deleted"] == 5
    mock_opensearch_client.delete_by_query.assert_called_once()

    # Verify query was built correctly
    call_args = mock_opensearch_client.delete_by_query.call_args
    query = call_args[1]["query"]
    assert "bool" in query
    assert "must" in query["bool"]


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_by_query_multiple_filters(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test deleting with multiple filter criteria."""
    mock_get_client.return_value = mock_opensearch_client
    mock_opensearch_client.delete_by_query.return_value = {
        "deleted": 3,
        "took": 50,
    }

    result = opensearch_delete_by_query(
        index="snippets",
        filters={"universe_id": "univ-123", "type": "snippet"},
    )

    assert result["deleted"] == 3

    # Verify both filters were applied
    call_args = mock_opensearch_client.delete_by_query.call_args
    must_clauses = call_args[1]["query"]["bool"]["must"]
    assert len(must_clauses) == 2


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_delete_by_query_empty_filters_raises_error(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test that delete by query without filters raises error."""
    mock_get_client.return_value = mock_opensearch_client

    with pytest.raises(ValueError, match="requires at least one filter"):
        opensearch_delete_by_query(
            index="snippets",
            filters={},
        )


# =============================================================================
# INTEGRATION-STYLE TESTS
# =============================================================================


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_index_and_search_workflow(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
    sample_document: Dict[str, Any],
) -> None:
    """Test typical workflow: index document, then search for it."""
    mock_get_client.return_value = mock_opensearch_client

    # Index document
    mock_opensearch_client.index_document.return_value = {
        "_index": "snippets",
        "_id": sample_document["id"],
        "_version": 1,
        "result": "created",
    }

    index_result = opensearch_index_document(
        index="snippets",
        doc_id=sample_document["id"],
        body=sample_document,
        refresh=True,
    )

    assert index_result["result"] == "created"

    # Search for indexed document
    mock_opensearch_client.search.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_index": "snippets",
                    "_id": sample_document["id"],
                    "_score": 1.5,
                    "_source": sample_document,
                }
            ],
        }
    }

    search_result = opensearch_search(
        index="snippets",
        query="forest artifact",
    )

    assert search_result["hits"]["total"]["value"] == 1
    assert search_result["hits"]["hits"][0]["_id"] == sample_document["id"]


@patch("monitor_data.tools.opensearch_tools.get_opensearch_client")
def test_search_facts_by_universe(
    mock_get_client: Mock,
    mock_opensearch_client: Mock,
) -> None:
    """Test searching facts scoped to a specific universe."""
    mock_get_client.return_value = mock_opensearch_client
    universe_id = str(uuid4())

    mock_opensearch_client.search.return_value = {
        "hits": {
            "total": {"value": 3, "relation": "eq"},
            "hits": [
                {
                    "_index": "facts",
                    "_id": f"fact-{i}",
                    "_score": 1.0,
                    "_source": {
                        "type": "fact",
                        "universe_id": universe_id,
                        "text": f"Fact {i} about the kingdom.",
                    },
                }
                for i in range(3)
            ],
        }
    }

    result = opensearch_search(
        index="facts",
        query="kingdom",
        filters={"universe_id": universe_id, "type": "fact"},
    )

    assert result["hits"]["total"]["value"] == 3
    for hit in result["hits"]["hits"]:
        assert hit["_source"]["universe_id"] == universe_id
        assert hit["_source"]["type"] == "fact"
