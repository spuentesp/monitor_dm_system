"""
OpenSearch MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose OpenSearch operations via the MCP server.
All OpenSearch operations are accessible by all agents (authority: *).
"""

from typing import Any, Dict, List, Optional

from opensearchpy.exceptions import NotFoundError

from monitor_data.db.opensearch import get_opensearch_client
from monitor_data.schemas.opensearch import (
    DocumentIndexRequest,
    DocumentIndexResponse,
    DocumentGetRequest,
    DocumentGetResponse,
    DocumentDeleteRequest,
    DocumentDeleteResponse,
    SearchRequest,
    SearchResponse,
    SearchHit,
    DeleteByQueryRequest,
    DeleteByQueryResponse,
)


# =============================================================================
# DOCUMENT OPERATIONS
# =============================================================================


def opensearch_index_document(params: DocumentIndexRequest) -> DocumentIndexResponse:
    """
    Index a document in OpenSearch (upsert operation).

    Authority: * (all agents)
    Use Case: DL-11

    This operation:
    - Creates the index if it doesn't exist
    - Inserts document if new
    - Updates document if it already exists

    Args:
        params: Document indexing parameters

    Returns:
        DocumentIndexResponse with indexing result

    Raises:
        RuntimeError: If client not connected or operation fails
    """
    client = get_opensearch_client()

    response = client.index_document(
        index=params.index,
        doc_id=params.id,
        body=params.body,
        refresh=params.refresh,
    )

    return DocumentIndexResponse(
        id=response["_id"],
        index=response["_index"],
        result=response["result"],  # "created" or "updated"
        version=response["_version"],
    )


def opensearch_get_document(params: DocumentGetRequest) -> DocumentGetResponse:
    """
    Get a document by ID from OpenSearch.

    Authority: * (all agents)
    Use Case: DL-11

    Args:
        params: Document get parameters

    Returns:
        DocumentGetResponse with document data or not found status

    Raises:
        RuntimeError: If client not connected
    """
    client = get_opensearch_client()

    response = client.get_document(index=params.index, doc_id=params.id)

    if response is None:
        return DocumentGetResponse(
            id=params.id,
            index=params.index,
            found=False,
            source=None,
            version=None,
        )

    return DocumentGetResponse(
        id=response["_id"],
        index=response["_index"],
        found=response["found"],
        source=response.get("_source"),
        version=response.get("_version"),
    )


def opensearch_delete_document(
    params: DocumentDeleteRequest,
) -> DocumentDeleteResponse:
    """
    Delete a document by ID from OpenSearch.

    Authority: * (all agents)
    Use Case: DL-11

    Args:
        params: Document delete parameters

    Returns:
        DocumentDeleteResponse with deletion result

    Raises:
        RuntimeError: If client not connected
        NotFoundError: If document doesn't exist
    """
    client = get_opensearch_client()

    try:
        response = client.delete_document(index=params.index, doc_id=params.id)

        return DocumentDeleteResponse(
            id=response["_id"],
            index=response["_index"],
            result=response["result"],  # "deleted"
            version=response.get("_version"),
        )
    except NotFoundError:
        return DocumentDeleteResponse(
            id=params.id,
            index=params.index,
            result="not_found",
            version=None,
        )


# =============================================================================
# SEARCH OPERATIONS
# =============================================================================


def opensearch_search(params: SearchRequest) -> SearchResponse:
    """
    Search documents in OpenSearch.

    Authority: * (all agents)
    Use Case: DL-11

    Supports:
    - Keyword search (match)
    - Phrase search (match_phrase)
    - Multi-field search
    - Filtering by fields (universe_id, type, etc.)
    - Result highlighting
    - Pagination

    Args:
        params: Search parameters

    Returns:
        SearchResponse with matching documents and highlights

    Raises:
        RuntimeError: If client not connected or query malformed
    """
    client = get_opensearch_client()

    # Build query based on type
    fields = params.fields or ["text"]

    if params.query_type == "match":
        if len(fields) == 1:
            query = {"match": {fields[0]: params.query}}
        else:
            query = {"multi_match": {"query": params.query, "fields": fields}}
    elif params.query_type == "match_phrase":
        if len(fields) == 1:
            query = {"match_phrase": {fields[0]: params.query}}
        else:
            query = {
                "multi_match": {
                    "query": params.query,
                    "fields": fields,
                    "type": "phrase",
                }
            }
    elif params.query_type == "multi_match":
        query = {"multi_match": {"query": params.query, "fields": fields}}
    else:
        raise ValueError(f"Unsupported query_type: {params.query_type}")

    # Build highlight config
    highlight_config = None
    if params.highlight:
        highlight_fields = params.highlight_fields or ["text"]
        highlight_config = {
            "fields": {field: {} for field in highlight_fields},
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        }

    # Execute search
    response = client.search(
        index=params.index,
        query=query,
        filters=params.filters,
        highlight=highlight_config,
        from_=params.from_,
        size=params.size,
    )

    # Parse response
    hits_data = response["hits"]
    hits = []

    for hit in hits_data["hits"]:
        hits.append(
            SearchHit(
                id=hit["_id"],
                index=hit["_index"],
                score=hit["_score"],
                source=hit["_source"],
                highlight=hit.get("highlight"),
            )
        )

    return SearchResponse(
        total=hits_data["total"]["value"],
        max_score=hits_data.get("max_score"),
        hits=hits,
        took=response["took"],
    )


# =============================================================================
# BULK OPERATIONS
# =============================================================================


def opensearch_delete_by_query(
    params: DeleteByQueryRequest,
) -> DeleteByQueryResponse:
    """
    Delete documents matching a query.

    Authority: * (all agents)
    Use Case: DL-11

    Useful for:
    - Deleting all documents in a universe
    - Removing documents of a specific type
    - Bulk cleanup operations

    Args:
        params: Delete by query parameters

    Returns:
        DeleteByQueryResponse with count of deleted documents

    Raises:
        RuntimeError: If client not connected or query malformed
    """
    client = get_opensearch_client()

    # Build query based on type
    if params.query_type == "match":
        query = {"match": {"text": params.query}}
    elif params.query_type == "match_phrase":
        query = {"match_phrase": {"text": params.query}}
    elif params.query_type == "term":
        # Term query for exact keyword matching
        # Useful for filtering by type, universe_id, etc.
        query = {"term": {"text.keyword": params.query}}
    else:
        raise ValueError(f"Unsupported query_type: {params.query_type}")

    # Apply filters if provided
    if params.filters:
        query = {
            "bool": {
                "must": [query],
                "filter": [{"term": {k: v}} for k, v in params.filters.items()],
            }
        }

    # Execute delete by query
    response = client.delete_by_query(index=params.index, query=query)

    return DeleteByQueryResponse(
        deleted=response["deleted"],
        total=response["total"],
        took=response["took"],
    )
