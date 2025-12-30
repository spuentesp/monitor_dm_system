"""
Qdrant MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose Qdrant vector operations via the MCP server.
Vector operations enable semantic search across narrative content.
"""

from typing import Dict, List, Any, Optional
from uuid import UUID

from qdrant_client.models import (
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
)

from monitor_data.db.qdrant import get_qdrant_client
from monitor_data.schemas.vectors import (
    VectorUpsert,
    VectorUpsertBatch,
    VectorSearch,
    VectorDelete,
    VectorDeleteByFilter,
    CollectionInfoRequest,
    VectorUpsertResponse,
    VectorUpsertBatchResponse,
    VectorSearchResponse,
    VectorSearchResult,
    VectorDeleteResponse,
    VectorDeleteByFilterResponse,
    CollectionInfo,
    DEFAULT_VECTOR_SIZE,
)


# =============================================================================
# QDRANT UPSERT OPERATIONS
# =============================================================================


def qdrant_upsert(params: VectorUpsert) -> VectorUpsertResponse:
    """
    Upsert a single vector with payload metadata.

    Authority: * (all agents)
    Use Case: DL-10 (vector index operations)

    Args:
        params: Vector upsert parameters (collection, id, vector, payload)

    Returns:
        VectorUpsertResponse with success status

    Raises:
        ValueError: If vector dimensions don't match collection
    """
    client = get_qdrant_client()
    qdrant = client.get_client()

    # Ensure collection exists
    vector_size = len(params.vector)
    client.ensure_collection(params.collection, vector_size)

    # Create point
    point = PointStruct(
        id=params.id,
        vector=params.vector,
        payload=params.payload,
    )

    # Upsert point
    qdrant.upsert(
        collection_name=params.collection,
        points=[point],
    )

    return VectorUpsertResponse(
        success=True,
        collection=params.collection,
        id=params.id,
    )


def qdrant_upsert_batch(params: VectorUpsertBatch) -> VectorUpsertBatchResponse:
    """
    Upsert multiple vectors in batch.

    Authority: * (all agents)
    Use Case: DL-10 (vector index operations)

    Args:
        params: Batch upsert parameters (collection, points)

    Returns:
        VectorUpsertBatchResponse with count of upserted points

    Raises:
        ValueError: If points are empty or vector dimensions inconsistent
    """
    if not params.points:
        raise ValueError("Points list cannot be empty")

    client = get_qdrant_client()
    qdrant = client.get_client()

    # Ensure collection exists (use first vector's size)
    first_vector = params.points[0].get("vector", [])
    vector_size = len(first_vector)
    client.ensure_collection(params.collection, vector_size)

    # Convert to PointStruct objects
    points = []
    for p in params.points:
        point = PointStruct(
            id=p["id"],
            vector=p["vector"],
            payload=p.get("payload", {}),
        )
        points.append(point)

    # Batch upsert
    qdrant.upsert(
        collection_name=params.collection,
        points=points,
    )

    return VectorUpsertBatchResponse(
        success=True,
        collection=params.collection,
        count=len(points),
    )


# =============================================================================
# QDRANT SEARCH OPERATIONS
# =============================================================================


def qdrant_search(params: VectorSearch) -> VectorSearchResponse:
    """
    Search for similar vectors with optional filtering.

    Authority: * (all agents)
    Use Case: DL-10 (vector index operations)

    Args:
        params: Search parameters (collection, query_vector, top_k, filter, score_threshold)

    Returns:
        VectorSearchResponse with matching results and scores

    Examples:
        # Basic search
        qdrant_search(VectorSearch(
            collection="scenes",
            query_vector=[0.1, 0.2, ...],
            top_k=5
        ))

        # Search with story filter
        qdrant_search(VectorSearch(
            collection="scenes",
            query_vector=[0.1, 0.2, ...],
            top_k=5,
            filter={"story_id": "uuid-123"}
        ))

        # Search with score threshold
        qdrant_search(VectorSearch(
            collection="scenes",
            query_vector=[0.1, 0.2, ...],
            top_k=10,
            score_threshold=0.7
        ))
    """
    client = get_qdrant_client()
    qdrant = client.get_client()

    # Build filter if provided
    qdrant_filter = None
    if params.filter:
        conditions = []
        for key, value in params.filter.items():
            conditions.append(
                FieldCondition(
                    key=key,
                    match=MatchValue(value=value),
                )
            )
        if conditions:
            qdrant_filter = Filter(must=conditions)

    # Execute search
    search_results = qdrant.search(
        collection_name=params.collection,
        query_vector=params.query_vector,
        limit=params.top_k,
        query_filter=qdrant_filter,
        score_threshold=params.score_threshold,
    )

    # Convert to response
    results = []
    for hit in search_results:
        result = VectorSearchResult(
            id=str(hit.id),
            score=hit.score,
            payload=hit.payload or {},
        )
        results.append(result)

    return VectorSearchResponse(
        results=results,
        collection=params.collection,
        top_k=params.top_k,
    )


# =============================================================================
# QDRANT DELETE OPERATIONS
# =============================================================================


def qdrant_delete(params: VectorDelete) -> VectorDeleteResponse:
    """
    Delete a vector by ID.

    Authority: * (all agents)
    Use Case: DL-10 (vector index operations)

    Args:
        params: Delete parameters (collection, id)

    Returns:
        VectorDeleteResponse with success status
    """
    client = get_qdrant_client()
    qdrant = client.get_client()

    # Delete point
    qdrant.delete(
        collection_name=params.collection,
        points_selector=[params.id],
    )

    return VectorDeleteResponse(
        success=True,
        collection=params.collection,
        id=params.id,
    )


def qdrant_delete_by_filter(params: VectorDeleteByFilter) -> VectorDeleteByFilterResponse:
    """
    Delete vectors matching a filter.

    Authority: * (all agents)
    Use Case: DL-10 (vector index operations)

    Args:
        params: Delete by filter parameters (collection, filter)

    Returns:
        VectorDeleteByFilterResponse with count of deleted points

    Examples:
        # Delete all vectors for a story
        qdrant_delete_by_filter(VectorDeleteByFilter(
            collection="scenes",
            filter={"story_id": "uuid-123"}
        ))

        # Delete all vectors for an entity
        qdrant_delete_by_filter(VectorDeleteByFilter(
            collection="memories",
            filter={"entity_id": "uuid-456"}
        ))
    """
    client = get_qdrant_client()
    qdrant = client.get_client()

    # Build filter
    conditions = []
    for key, value in params.filter.items():
        conditions.append(
            FieldCondition(
                key=key,
                match=MatchValue(value=value),
            )
        )
    qdrant_filter = Filter(must=conditions)

    # Count matching points before deletion
    count_result = qdrant.count(
        collection_name=params.collection,
        count_filter=qdrant_filter,
    )
    count = count_result.count

    # Delete points
    qdrant.delete(
        collection_name=params.collection,
        points_selector=qdrant_filter,
    )

    return VectorDeleteByFilterResponse(
        success=True,
        collection=params.collection,
        count=count,
    )


# =============================================================================
# QDRANT INFO OPERATIONS
# =============================================================================


def qdrant_get_collection_info(params: CollectionInfoRequest) -> CollectionInfo:
    """
    Get information about a collection.

    Authority: * (all agents)
    Use Case: DL-10 (vector index operations)

    Args:
        params: Collection info request (collection)

    Returns:
        CollectionInfo with collection statistics

    Raises:
        ValueError: If collection doesn't exist
    """
    client = get_qdrant_client()
    qdrant = client.get_client()

    # Get collection info
    try:
        collection = qdrant.get_collection(params.collection)
    except Exception as e:
        raise ValueError(f"Collection {params.collection} not found: {e}")

    return CollectionInfo(
        collection=params.collection,
        vector_count=collection.points_count or 0,
        vector_size=collection.config.params.vectors.size,
        distance=collection.config.params.vectors.distance.name,
    )
