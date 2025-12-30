"""
OpenSearch MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose OpenSearch operations via the MCP server.
OpenSearch provides full-text search for narratives, facts, and documents.
"""

from typing import Optional, Dict, Any, List

from monitor_data.db.opensearch import get_opensearch_client


# =============================================================================
# OPENSEARCH OPERATIONS
# =============================================================================


def opensearch_index_document(
    index: str,
    doc_id: str,
    body: Dict[str, Any],
    refresh: bool = False,
) -> Dict[str, Any]:
    """
    Index a document in OpenSearch (create or update/upsert).

    Authority: * (all agents)
    Use Case: DL-11

    Args:
        index: Index name (e.g., 'snippets', 'facts', 'scenes', 'sources')
        doc_id: Document ID (unique identifier)
        body: Document content with metadata
            Expected structure:
            {
                "id": str,
                "type": str,  # e.g., 'snippet', 'fact', 'scene'
                "universe_id": str,  # UUID of universe
                "text": str,  # Main searchable text
                "metadata": dict,  # Additional metadata
                "created_at": str,  # ISO timestamp
                "updated_at": str,  # ISO timestamp
            }
        refresh: Whether to refresh index immediately (default: False)

    Returns:
        Indexing result with:
        {
            "_index": str,
            "_id": str,
            "_version": int,
            "result": str,  # 'created' or 'updated'
        }

    Notes:
        - Creates index if it doesn't exist
        - Uses upsert semantics (create or update)
        - Refresh=True makes document immediately searchable (use for testing)
    """
    client = get_opensearch_client()
    result = client.index_document(
        index=index,
        doc_id=doc_id,
        body=body,
        refresh=refresh,
    )
    return result


def opensearch_get_document(index: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a document by ID from OpenSearch.

    Authority: * (all agents)
    Use Case: DL-11

    Args:
        index: Index name
        doc_id: Document ID

    Returns:
        Document if found with structure:
        {
            "_index": str,
            "_id": str,
            "_source": dict,  # The actual document body
            "found": bool,
        }
        None if document not found
    """
    client = get_opensearch_client()
    result = client.get_document(index=index, doc_id=doc_id)
    return result


def opensearch_search(
    index: str,
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    highlight: bool = True,
    from_: int = 0,
    size: int = 10,
) -> Dict[str, Any]:
    """
    Search documents in OpenSearch with keyword/phrase queries.

    Authority: * (all agents)
    Use Case: DL-11

    Args:
        index: Index name to search
        query: Search query string (keyword or phrase)
        filters: Optional filters to apply:
            {
                "universe_id": str,  # Filter by universe
                "type": str,  # Filter by document type
                # Additional field filters as needed
            }
        highlight: Whether to return highlighted snippets (default: True)
        from_: Starting offset for pagination (default: 0)
        size: Number of results to return (default: 10)

    Returns:
        Search results with structure:
        {
            "hits": {
                "total": {"value": int},
                "hits": [
                    {
                        "_index": str,
                        "_id": str,
                        "_score": float,
                        "_source": dict,
                        "highlight": {  # If highlight=True
                            "text": [str],  # Highlighted snippets
                        }
                    }
                ]
            }
        }

    Notes:
        - Supports both keyword matching and phrase queries
        - Filters are applied as must clauses (AND logic)
        - Results are ranked by relevance score
        - Highlighting shows matched text with <em> tags
    """
    client = get_opensearch_client()

    # Build query DSL
    must_clauses: List[Dict[str, Any]] = []

    # Add text search query
    if query:
        must_clauses.append({
            "multi_match": {
                "query": query,
                "fields": ["text", "metadata.*"],
                "type": "best_fields",
            }
        })

    # Add filters
    if filters:
        for field, value in filters.items():
            must_clauses.append({
                "term": {field: value}
            })

    # Construct bool query
    if must_clauses:
        query_dsl = {
            "bool": {
                "must": must_clauses
            }
        }
    else:
        # If no query or filters, match all
        query_dsl = {"match_all": {}}

    # Configure highlighting
    highlight_config = None
    if highlight:
        highlight_config = {
            "fields": {
                "text": {
                    "fragment_size": 150,
                    "number_of_fragments": 3,
                }
            },
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        }

    result = client.search(
        index=index,
        query=query_dsl,
        from_=from_,
        size=size,
        highlight=highlight_config,
    )

    return result


def opensearch_delete_document(index: str, doc_id: str) -> Dict[str, Any]:
    """
    Delete a document by ID from OpenSearch.

    Authority: * (all agents)
    Use Case: DL-11

    Args:
        index: Index name
        doc_id: Document ID to delete

    Returns:
        Deletion result with:
        {
            "_index": str,
            "_id": str,
            "result": str,  # 'deleted'
        }

    Raises:
        NotFoundError: If document doesn't exist
    """
    client = get_opensearch_client()
    result = client.delete_document(index=index, doc_id=doc_id)
    return result


def opensearch_delete_by_query(
    index: str,
    filters: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Delete documents matching a filter query.

    Authority: * (all agents)
    Use Case: DL-11

    Args:
        index: Index name
        filters: Filter criteria for documents to delete:
            {
                "universe_id": str,  # Delete all docs for universe
                "type": str,  # Delete all docs of type
                # Additional field filters as needed
            }

    Returns:
        Deletion result with:
        {
            "deleted": int,  # Number of documents deleted
            "took": int,  # Time in milliseconds
        }

    Notes:
        - Deletes all documents matching the filter criteria
        - Use with caution as this is a bulk operation
        - Empty filters will delete ALL documents (not recommended)
    """
    client = get_opensearch_client()

    # Build query from filters
    must_clauses: List[Dict[str, Any]] = []
    for field, value in filters.items():
        must_clauses.append({
            "term": {field: value}
        })

    if not must_clauses:
        # Safety: don't allow deleting everything without explicit match_all
        raise ValueError("Delete by query requires at least one filter")

    query = {
        "bool": {
            "must": must_clauses
        }
    }

    result = client.delete_by_query(index=index, query=query)
    return result
