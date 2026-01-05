"""
Qdrant MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose Qdrant vector operations via the MCP server.
Qdrant stores embeddings for semantic search across narrative content.
"""

from typing import Optional
from uuid import UUID

from qdrant_client.models import (
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from monitor_data.db.qdrant import get_qdrant_client
from monitor_data.schemas.vectors import (
    VectorUpsertRequest,
    VectorBatchUpsertRequest,
    VectorUpsertResponse,
    VectorSearchRequest,
    VectorSearchResponse,
    ScoredVector,
    VectorDeleteRequest,
    VectorDeleteByFilterRequest,
    VectorDeleteResponse,
    CollectionInfoRequest,
    CollectionInfoResponse,
    CollectionInfo,
    VectorFilter,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _build_qdrant_filter(filter_params: VectorFilter) -> Optional[Filter]:
    """
    Build Qdrant Filter from VectorFilter parameters.

    Args:
        filter_params: VectorFilter with optional story_id, scene_id, entity_id, type

    Returns:
        Qdrant Filter object or None if no filters specified

    Examples:
        >>> filter = VectorFilter(story_id=uuid, type="scene")
        >>> qdrant_filter = _build_qdrant_filter(filter)
        >>> # Returns Filter with must conditions for story_id and type
    """
    if not filter_params:
        return None

    # Start with custom filter if provided
    if filter_params.custom:
        return Filter(**filter_params.custom)

    must_conditions = []

    # Add story_id filter
    if filter_params.story_id:
        must_conditions.append(
            FieldCondition(
                key="story_id",
                match=MatchValue(value=str(filter_params.story_id)),
            )
        )

    # Add scene_id filter
    if filter_params.scene_id:
        must_conditions.append(
            FieldCondition(
                key="scene_id",
                match=MatchValue(value=str(filter_params.scene_id)),
            )
        )

    # Add entity_id filter
    if filter_params.entity_id:
        must_conditions.append(
            FieldCondition(
                key="entity_id",
                match=MatchValue(value=str(filter_params.entity_id)),
            )
        )

    # Add type filter
    if filter_params.type:
        must_conditions.append(
            FieldCondition(
                key="type",
                match=MatchValue(value=filter_params.type),
            )
        )

    if not must_conditions:
        return None

    # Use cast to fix type variance issue
    return Filter(must=must_conditions)  # type: ignore[arg-type]


# =============================================================================
# VECTOR UPSERT OPERATIONS
# =============================================================================


def qdrant_upsert(params: VectorUpsertRequest) -> VectorUpsertResponse:
    """
    Store a single vector with payload metadata in Qdrant.

    Creates collection if it doesn't exist. Upserts point (inserts or updates).

    Args:
        params: VectorUpsertRequest with collection, id, vector, and payload

    Returns:
        VectorUpsertResponse with success status and upserted IDs

    Raises:
        ValueError: If collection name is invalid or vector is empty
        Exception: If Qdrant operation fails

    Examples:
        >>> params = VectorUpsertRequest(
        ...     collection="scenes",
        ...     id=scene_id,
        ...     vector=[0.1, 0.2, ...],  # 1536 dims
        ...     payload={"type": "scene", "story_id": str(story_id)}
        ... )
        >>> response = qdrant_upsert(params)
        >>> assert response.success is True
        >>> assert len(response.ids) == 1
    """
    if not params.vector:
        raise ValueError("Vector cannot be empty")

    client = get_qdrant_client()

    # Ensure collection exists with correct configuration
    client.ensure_collection(params.collection)

    # Get the underlying Qdrant client
    qdrant = client.get_client()

    # Create point
    point = PointStruct(
        id=str(params.id),
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
        upserted_count=1,
        ids=[params.id],
    )


def qdrant_upsert_batch(params: VectorBatchUpsertRequest) -> VectorUpsertResponse:
    """
    Store multiple vectors in batch for efficient bulk operations.

    Creates collection if it doesn't exist. Upserts all points atomically.

    Args:
        params: VectorBatchUpsertRequest with collection and list of points

    Returns:
        VectorUpsertResponse with success status and upserted IDs

    Raises:
        ValueError: If points list is empty or collection name is invalid
        Exception: If Qdrant operation fails

    Examples:
        >>> params = VectorBatchUpsertRequest(
        ...     collection="memories",
        ...     points=[
        ...         VectorPoint(id=id1, vector=[...], payload={...}),
        ...         VectorPoint(id=id2, vector=[...], payload={...}),
        ...     ]
        ... )
        >>> response = qdrant_upsert_batch(params)
        >>> assert response.upserted_count == 2
    """
    if not params.points:
        raise ValueError("Points list cannot be empty")

    client = get_qdrant_client()

    # Ensure collection exists
    client.ensure_collection(params.collection)

    # Get the underlying Qdrant client
    qdrant = client.get_client()

    # Convert to PointStruct list
    qdrant_points = [
        PointStruct(
            id=str(point.id),
            vector=point.vector,
            payload=point.payload,
        )
        for point in params.points
    ]

    # Batch upsert
    qdrant.upsert(
        collection_name=params.collection,
        points=qdrant_points,
    )

    return VectorUpsertResponse(
        success=True,
        collection=params.collection,
        upserted_count=len(params.points),
        ids=[point.id for point in params.points],
    )


# =============================================================================
# VECTOR SEARCH OPERATIONS
# =============================================================================


def qdrant_search(params: VectorSearchRequest) -> VectorSearchResponse:
    """
    Search for semantically similar vectors with optional filtering.

    Supports payload filtering (story_id, scene_id, entity_id, type) and
    score thresholding for high-quality results.

    Args:
        params: VectorSearchRequest with query vector, top_k, filters, threshold

    Returns:
        VectorSearchResponse with ranked results and scores

    Raises:
        ValueError: If collection doesn't exist or query vector is empty
        Exception: If Qdrant search fails

    Examples:
        >>> params = VectorSearchRequest(
        ...     collection="scenes",
        ...     query_vector=[0.1, 0.2, ...],
        ...     top_k=5,
        ...     score_threshold=0.7,
        ...     filter=VectorFilter(story_id=story_id)
        ... )
        >>> response = qdrant_search(params)
        >>> for result in response.results:
        ...     print(f"ID: {result.id}, Score: {result.score}")
    """
    if not params.query_vector:
        raise ValueError("Query vector cannot be empty")

    client = get_qdrant_client()

    # Ensure collection exists
    client.ensure_collection(params.collection)

    # Get the underlying Qdrant client
    qdrant = client.get_client()

    # Build filter if provided
    qdrant_filter = None
    if params.filter:
        qdrant_filter = _build_qdrant_filter(params.filter)

    # Search
    search_results = qdrant.search(  # type: ignore[attr-defined]
        collection_name=params.collection,
        query_vector=params.query_vector,
        limit=params.top_k,
        query_filter=qdrant_filter,
        score_threshold=params.score_threshold,
    )

    # Convert results to ScoredVector
    results = [
        ScoredVector(
            id=UUID(result.id),  # Convert string ID back to UUID
            score=result.score,
            payload=result.payload or {},
        )
        for result in search_results
    ]

    return VectorSearchResponse(
        collection=params.collection,
        results=results,
        count=len(results),
    )


# =============================================================================
# VECTOR DELETE OPERATIONS
# =============================================================================


def qdrant_delete(params: VectorDeleteRequest) -> VectorDeleteResponse:
    """
    Delete a single vector point by ID.

    Args:
        params: VectorDeleteRequest with collection and point ID

    Returns:
        VectorDeleteResponse with success status and deleted count

    Raises:
        ValueError: If collection doesn't exist
        Exception: If Qdrant operation fails

    Examples:
        >>> params = VectorDeleteRequest(
        ...     collection="scenes",
        ...     id=scene_id
        ... )
        >>> response = qdrant_delete(params)
        >>> assert response.deleted_count == 1
    """
    client = get_qdrant_client()

    # Ensure collection exists
    client.ensure_collection(params.collection)

    # Get the underlying Qdrant client
    qdrant = client.get_client()

    # Delete point by ID
    qdrant.delete(
        collection_name=params.collection,
        points_selector=[str(params.id)],
    )

    return VectorDeleteResponse(
        success=True,
        collection=params.collection,
        deleted_count=1,  # Single point deletion
    )


def qdrant_delete_by_filter(
    params: VectorDeleteByFilterRequest,
) -> VectorDeleteResponse:
    """
    Delete multiple vector points matching filter criteria.

    Useful for bulk deletions (e.g., all vectors for a story or scene).

    Args:
        params: VectorDeleteByFilterRequest with collection and filter

    Returns:
        VectorDeleteResponse with success status and deleted count

    Raises:
        ValueError: If collection doesn't exist or filter is empty
        Exception: If Qdrant operation fails

    Examples:
        >>> params = VectorDeleteByFilterRequest(
        ...     collection="scenes",
        ...     filter=VectorFilter(story_id=story_id)
        ... )
        >>> response = qdrant_delete_by_filter(params)
        >>> print(f"Deleted {response.deleted_count} vectors")
    """
    if not params.filter:
        raise ValueError("Filter must be provided for delete_by_filter operation")

    client = get_qdrant_client()

    # Ensure collection exists
    client.ensure_collection(params.collection)

    # Get the underlying Qdrant client
    qdrant = client.get_client()

    # Build filter
    qdrant_filter = _build_qdrant_filter(params.filter)

    if not qdrant_filter:
        raise ValueError("Filter parameters resulted in empty filter")

    # First, count how many points match the filter
    count_result = qdrant.count(
        collection_name=params.collection,
        count_filter=qdrant_filter,
    )

    deleted_count = count_result.count

    # Delete points matching filter
    if deleted_count > 0:
        qdrant.delete(
            collection_name=params.collection,
            points_selector=qdrant_filter,
        )

    return VectorDeleteResponse(
        success=True,
        collection=params.collection,
        deleted_count=deleted_count,
    )


# =============================================================================
# COLLECTION INFO OPERATIONS
# =============================================================================


def qdrant_get_collection_info(
    params: CollectionInfoRequest,
) -> CollectionInfoResponse:
    """
    Get metadata and statistics about a vector collection.

    Returns collection configuration (dimension, distance metric) and
    usage statistics (point count, index status).

    Args:
        params: CollectionInfoRequest with collection name

    Returns:
        CollectionInfoResponse with collection metadata and stats

    Raises:
        ValueError: If collection doesn't exist
        Exception: If Qdrant operation fails

    Examples:
        >>> params = CollectionInfoRequest(collection="scenes")
        >>> response = qdrant_get_collection_info(params)
        >>> print(f"Collection: {response.collection.name}")
        >>> print(f"Points: {response.collection.points_count}")
        >>> print(f"Dimension: {response.collection.vector_size}")
    """
    client = get_qdrant_client()

    # Ensure collection exists (creates if needed)
    client.ensure_collection(params.collection)

    # Get the underlying Qdrant client
    qdrant = client.get_client()

    # Get collection info
    collection_info = qdrant.get_collection(params.collection)

    # Extract vector configuration
    vectors_config = collection_info.config.params.vectors

    # Handle VectorParams (not dict)
    if not hasattr(vectors_config, "size"):
        raise ValueError(
            f"Invalid vector configuration for collection {params.collection}"
        )

    vector_size = vectors_config.size  # type: ignore[attr-defined,union-attr]
    distance_name = vectors_config.distance.name  # type: ignore[attr-defined,union-attr]
    points_count = collection_info.points_count or 0

    # Extract relevant information
    info = CollectionInfo(
        name=params.collection,
        vector_size=vector_size,
        points_count=points_count,
        indexed_vectors_count=collection_info.indexed_vectors_count,
        distance=distance_name,
        status=collection_info.status.name,
    )

    return CollectionInfoResponse(collection=info)
