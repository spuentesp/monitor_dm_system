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
from monitor_data.schemas.memories import (
    MemoryEmbedRequest,
    MemoryEmbedResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
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
        try:
            custom_filter = Filter(**filter_params.custom)
            # Validate the filter is not empty
            if (
                not custom_filter.must
                and not custom_filter.should
                and not custom_filter.must_not
            ):
                return None
            return custom_filter
        except Exception as exc:
            raise ValueError(
                f"Invalid custom filter parameters: {filter_params.custom}"
            ) from exc

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
    # Note: Pydantic schema already enforces min_length=1 for points
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

    # Convert results to ScoredVector with error handling
    results = []
    for result in search_results:
        try:
            vector_id = UUID(str(result.id))  # Convert string ID back to UUID
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid UUID '{result.id}' returned from Qdrant "
                f"for collection '{params.collection}'."
            ) from exc
        results.append(
            ScoredVector(
                id=vector_id,
                score=result.score,
                payload=result.payload or {},
            )
        )

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

    # Count before delete for reporting
    count_before = qdrant.count(  # type: ignore[attr-defined]
        collection_name=params.collection,
        count_filter=qdrant_filter,
    ).count

    # Delete points matching filter (always attempt; rely on filter match at delete time)
    qdrant.delete(  # type: ignore[attr-defined]
        collection_name=params.collection,
        points_selector=qdrant_filter,
    )

    # Count after delete to calculate actual deleted count
    # This handles race conditions: if points were added between operations,
    # they won't be deleted, and the count difference will be accurate
    count_after = qdrant.count(  # type: ignore[attr-defined]
        collection_name=params.collection,
        count_filter=qdrant_filter,
    ).count

    deleted_count = count_before - count_after

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


# =============================================================================
# MEMORY VECTOR OPERATIONS
# =============================================================================


def qdrant_embed_memory(params: MemoryEmbedRequest) -> MemoryEmbedResponse:
    """
    Generate and store vector embedding for a character memory.

    Uses the Qdrant client's embedding model to vectorize memory text,
    then stores the vector with memory metadata in the 'memories' collection.

    Authority: All agents
    Use Case: DL-7

    Args:
        params: MemoryEmbedRequest with memory data

    Returns:
        MemoryEmbedResponse with embedding status

    Raises:
        ValueError: If memory text is empty or entity_id is invalid
        Exception: If embedding generation or Qdrant operation fails

    Examples:
        >>> params = MemoryEmbedRequest(
        ...     memory_id=memory_id,
        ...     text="I remember you saved my life in the dragon's lair",
        ...     entity_id=entity_id,
        ...     scene_id=scene_id,
        ...     importance=0.9,
        ...     metadata={}
        ... )
        >>> response = qdrant_embed_memory(params)
        >>> print(f"Memory {response.memory_id} embedded")
    """
    client = get_qdrant_client()

    # Ensure memories collection exists
    client.ensure_collection("memories")

    # Generate embedding vector
    embedding = client.embed_text(params.text)

    # Build payload with memory metadata
    payload = {
        "memory_id": str(params.memory_id),
        "entity_id": str(params.entity_id),
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "importance": params.importance,
        "type": "memory",  # For filtering
        **params.metadata,
    }

    # Create point with memory_id as ID (ensures idempotent upserts)
    point = PointStruct(
        id=str(params.memory_id),
        vector=embedding,
        payload=payload,
    )

    # Get underlying Qdrant client
    qdrant = client.get_client()

    # Upsert point
    qdrant.upsert(  # type: ignore[attr-defined]
        collection_name="memories",
        points=[point],
    )

    return MemoryEmbedResponse(
        memory_id=params.memory_id,
        point_id=str(params.memory_id),
        collection="memories",
        success=True,
    )


def qdrant_search_memories(params: MemorySearchRequest) -> MemorySearchResponse:
    """
    Search character memories using semantic similarity.

    Generates embedding for query text and searches the 'memories' collection
    for similar vectors. Supports filtering by entity, scene, and importance.

    Authority: All agents
    Use Case: DL-7

    Args:
        params: MemorySearchRequest with query and optional filters

    Returns:
        MemorySearchResponse with ranked search results

    Raises:
        ValueError: If query text is empty or top_k is invalid
        Exception: If embedding generation or search fails

    Examples:
        >>> params = MemorySearchRequest(
        ...     query_text="dragon battle",
        ...     entity_id=entity_id,
        ...     min_importance=0.5,
        ...     top_k=10
        ... )
        >>> response = qdrant_search_memories(params)
        >>> for result in response.results:
        ...     print(f"Memory: {result.text} (score: {result.score})")
    """
    client = get_qdrant_client()

    # Ensure collection exists
    client.ensure_collection("memories")

    # Generate query embedding
    query_vector = client.embed_text(params.query_text)

    # Build filter conditions
    must_conditions = []

    # Filter by entity if specified
    if params.entity_id:
        must_conditions.append(
            FieldCondition(
                key="entity_id",
                match=MatchValue(value=str(params.entity_id)),
            )
        )

    # Filter by scene if specified
    if params.scene_id:
        must_conditions.append(
            FieldCondition(
                key="scene_id",
                match=MatchValue(value=str(params.scene_id)),
            )
        )

    # Build filter object
    search_filter = None
    if must_conditions:
        search_filter = Filter(must=must_conditions)  # type: ignore[arg-type]

    # Get underlying Qdrant client
    qdrant = client.get_client()

    # Search for similar memories
    search_results = qdrant.search(  # type: ignore[attr-defined]
        collection_name="memories",
        query_vector=query_vector,
        query_filter=search_filter,
        limit=params.top_k,
    )

    # Convert results to MemorySearchResult objects
    results = []
    for scored_point in search_results:
        payload = scored_point.payload

        # Filter by importance if specified
        importance = payload.get("importance", 0.0)
        if params.min_importance is not None and importance < params.min_importance:
            continue

        # Extract text from payload (may not be stored, just metadata)
        # Note: We don't store full text in Qdrant, just metadata
        # Caller should use memory_id to fetch full text from MongoDB
        results.append(
            MemorySearchResult(
                memory_id=UUID(payload["memory_id"]),
                entity_id=UUID(payload["entity_id"]),
                text="",  # Not stored in Qdrant, fetch from MongoDB
                scene_id=(
                    UUID(payload["scene_id"]) if payload.get("scene_id") else None
                ),
                importance=importance,
                score=scored_point.score,
                metadata={
                    k: v
                    for k, v in payload.items()
                    if k
                    not in ["memory_id", "entity_id", "scene_id", "importance", "type"]
                },
            )
        )

    return MemorySearchResponse(
        results=results,
        query=params.query_text,
        top_k=params.top_k,
    )
