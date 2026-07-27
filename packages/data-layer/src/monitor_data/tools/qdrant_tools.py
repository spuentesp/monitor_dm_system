"""
Qdrant MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose Qdrant vector operations via the MCP server.
Qdrant stores embeddings for semantic search across narrative content.
"""

import inspect
import logging
from typing import Any
from uuid import UUID

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchText,
    MatchValue,
    PointStruct,
)

from monitor_data.db._utils import run_sync
from monitor_data.db.qdrant import get_qdrant_client
from monitor_data.schemas.memories import (
    MemoryEmbedRequest,
    MemoryEmbedResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
)
from monitor_data.schemas.vectors import (
    CollectionInfo,
    CollectionInfoRequest,
    CollectionInfoResponse,
    ScoredVector,
    VectorBatchUpsertRequest,
    VectorDeleteByFilterRequest,
    VectorDeleteRequest,
    VectorDeleteResponse,
    VectorFilter,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorUpsertRequest,
    VectorUpsertResponse,
)
from monitor_data.tools._shared import call_sync as _call_sync

logger = logging.getLogger(__name__)


def _embed_query_via_service(text: str) -> list[Any]:
    """Embed a query through the RetrievalService — the single embed owner.

    Routes retrieval embeddings through ``RetrievalService.embed_query`` so the
    pinned model is used consistently (index-time and query-time). Kept sync
    here because these MCP tool entry points are sync; the actual embed is
    awaited via ``_call_sync``.
    """
    from monitor_data.retrieval import default_retrieval_service

    return list(_call_sync(default_retrieval_service().embed_query(text)))


def _upsert_points(client: Any, collection: str, points: list[Any]) -> None:
    """Upsert points with a one-shot self-healing retry (T-098/R9).

    In the sync ingestion path, ``get_client`` cannot see the (closed) event
    loop a cached async client is bound to, so a stale client only surfaces as
    'RuntimeError: Event loop is closed' at await time. A fresh client recovers
    every time, so on that specific error we reset the cached client, rebuild,
    and retry exactly once.
    """
    qdrant = client.get_client()
    try:
        _call_sync(qdrant.upsert(collection_name=collection, points=points))
        return
    except RuntimeError as exc:
        if "Event loop is closed" not in str(exc):
            raise
        logger.warning(
            "qdrant upsert hit a closed event loop; rebuilding client and retrying once (collection=%s, points=%d)",
            collection,
            len(points),
        )
    client.reset_client()
    qdrant = client.get_client()
    _call_sync(qdrant.upsert(collection_name=collection, points=points))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


async def _qdrant_search_points(
    qdrant: Any,
    *,
    collection_name: str,
    query_vector: list[float],
    limit: int,
    query_filter: Filter | None,
    score_threshold: float | None,
) -> list[Any]:
    """Compatibility wrapper for mixed Qdrant client versions."""
    if hasattr(qdrant, "search"):
        response = qdrant.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )
        response = await response if inspect.isawaitable(response) else response
        return list(response or [])

    if hasattr(qdrant, "query_points"):
        response = qdrant.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,
        )
        response = await response if inspect.isawaitable(response) else response
        return list(getattr(response, "points", []) or getattr(response, "result", []) or [])

    search_api = getattr(getattr(qdrant, "http", None), "search_api", None)
    if search_api is not None and hasattr(search_api, "search_points"):
        response = search_api.search_points(
            collection_name=collection_name,
            search_request={
                "vector": query_vector,
                "limit": limit,
                "with_payload": True,
                "with_vector": False,
                "filter": query_filter,
                "score_threshold": score_threshold,
            },
        )
        response = await response if inspect.isawaitable(response) else response
        return list(getattr(response, "result", []) or [])

    raise AttributeError("No supported Qdrant search method found")


def _build_qdrant_filter(filter_params: VectorFilter) -> Filter | None:
    """Build a Qdrant Filter from the structured VectorFilter model."""
    if not filter_params:
        return None

    if filter_params.custom:
        try:
            custom_filter = Filter(**filter_params.custom)
            if not custom_filter.must and not custom_filter.should and not custom_filter.must_not:
                return None
            return custom_filter
        except Exception as exc:
            raise ValueError(f"Invalid custom filter parameters: {filter_params.custom}") from exc

    must_conditions = []
    scalar_filters = {
        "story_id": filter_params.story_id,
        "scene_id": filter_params.scene_id,
        "entity_id": filter_params.entity_id,
        "universe_id": filter_params.universe_id,
        "play_session_id": filter_params.play_session_id,
        "doc_id": filter_params.doc_id,
        "ingestion_job_id": filter_params.ingestion_job_id,
        "type": filter_params.type,
        "temporal_mode": filter_params.temporal_mode,
        "entity_type": filter_params.entity_type,
        "detail_level": filter_params.detail_level,
        "node_type": filter_params.node_type,
        "domain": filter_params.domain,
        "canon_level": filter_params.canon_level,
    }

    for key, value in scalar_filters.items():
        if value is not None:
            must_conditions.append(
                FieldCondition(
                    key=key,
                    match=MatchValue(value=str(value) if isinstance(value, UUID) else value),
                )
            )

    if filter_params.is_archetype is not None:
        must_conditions.append(
            FieldCondition(
                key="is_archetype",
                match=MatchValue(value=filter_params.is_archetype),
            )
        )

    if not must_conditions:
        return None

    return Filter(must=must_conditions)


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
    _call_sync(client.ensure_collection(params.collection))

    # Create point
    point = PointStruct(
        id=str(params.id),
        vector=params.vector,
        payload=params.payload,
    )

    # Upsert point (self-healing on a closed event loop — T-098/R9)
    _upsert_points(client, params.collection, [point])

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
    _call_sync(client.ensure_collection(params.collection))

    # Convert to PointStruct list
    qdrant_points = [
        PointStruct(
            id=str(point.id),
            vector=point.vector,
            payload=point.payload,
        )
        for point in params.points
    ]

    # Batch upsert (self-healing on a closed event loop — T-098/R9)
    _upsert_points(client, params.collection, qdrant_points)

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
    """Search for semantically similar vectors with optional filtering."""
    query_vector = list(params.query_vector or [])
    if not query_vector:
        query_text = (params.query_text or "").strip()
        if not query_text:
            raise ValueError("Query vector cannot be empty")
        query_vector = _embed_query_via_service(query_text)

    client = get_qdrant_client()

    # Ensure collection exists
    _call_sync(client.ensure_collection(params.collection))

    # Get the underlying Qdrant client
    qdrant = client.get_client()

    qdrant_filter = _build_qdrant_filter(params.filter) if params.filter else None

    if params.keyword_filter and params.keyword_filter.strip():
        keyword_condition = FieldCondition(
            key="text",
            match=MatchText(text=params.keyword_filter.strip()),
        )
        if qdrant_filter is None:
            qdrant_filter = Filter(must=[keyword_condition])
        else:
            existing_must = list(qdrant_filter.must or [])
            existing_must.append(keyword_condition)
            qdrant_filter = Filter(
                must=existing_must,
                should=qdrant_filter.should,
                must_not=qdrant_filter.must_not,
            )

    search_results = run_sync(
        _qdrant_search_points(
            qdrant,
            collection_name=params.collection,
            query_vector=query_vector,
            limit=params.top_k,
            query_filter=qdrant_filter,
            score_threshold=params.score_threshold,
        )
    )

    results = []
    for result in search_results:
        try:
            vector_id = UUID(str(result.id))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid UUID '{result.id}' returned from Qdrant for collection '{params.collection}'."
            ) from exc
        results.append(
            ScoredVector(
                id=vector_id,
                score=float(getattr(result, "score", 0.0)),
                payload=getattr(result, "payload", None) or {},
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
    _call_sync(client.ensure_collection(params.collection))

    # Get the underlying Qdrant client
    qdrant = client.get_client()

    # Delete point by ID
    _call_sync(
        qdrant.delete(
            collection_name=params.collection,
            points_selector=[str(params.id)],
        )
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
    _call_sync(client.ensure_collection(params.collection))

    # Get the underlying Qdrant client
    qdrant = client.get_client()

    # Build filter
    qdrant_filter = _build_qdrant_filter(params.filter)

    if not qdrant_filter:
        raise ValueError("Filter parameters resulted in empty filter")

    # Count before delete for reporting
    count_before = _call_sync(
        qdrant.count(
            collection_name=params.collection,
            count_filter=qdrant_filter,
        )
    ).count

    # Delete points matching filter (always attempt; rely on filter match at delete time)
    _call_sync(
        qdrant.delete(
            collection_name=params.collection,
            points_selector=qdrant_filter,
        )
    )

    # Count after delete to calculate actual deleted count
    # This handles race conditions: if points were added between operations,
    # they won't be deleted, and the count difference will be accurate
    count_after = _call_sync(
        qdrant.count(
            collection_name=params.collection,
            count_filter=qdrant_filter,
        )
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
    _call_sync(client.ensure_collection(params.collection))

    # Get the underlying Qdrant client
    qdrant = client.get_client()

    # Get collection info
    collection_info = _call_sync(qdrant.get_collection(params.collection))

    # Extract vector configuration
    vectors_config = collection_info.config.params.vectors

    # Handle VectorParams (not dict)
    if not hasattr(vectors_config, "size"):
        raise ValueError(f"Invalid vector configuration for collection {params.collection}")

    vector_size = vectors_config.size
    distance_name = vectors_config.distance.name
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
    _call_sync(client.ensure_collection("memories"))

    # Generate embedding vector
    embedding = _embed_query_via_service(params.text)

    # Build payload with memory metadata
    payload = {
        "memory_id": str(params.memory_id),
        "universe_id": str(params.universe_id),
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

    # Upsert point (self-healing on a closed event loop — T-098/R9)
    _upsert_points(client, "memories", [point])

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

    Note:
        The `text` field in search results is None because full memory text
        is not stored in Qdrant (storage optimization). Use the `memory_id`
        from search results to fetch full memory text from MongoDB if needed.

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
        ...     # result.text is None, use memory_id to fetch from MongoDB
        ...     print(f"Memory ID: {result.memory_id} (score: {result.score})")
    """
    client = get_qdrant_client()

    # Ensure collection exists
    _call_sync(client.ensure_collection("memories"))

    # Generate query embedding
    query_vector = _embed_query_via_service(params.query_text)

    # Build filter conditions
    must_conditions = []

    # Filter by universe if specified
    if params.universe_id:
        must_conditions.append(
            FieldCondition(
                key="universe_id",
                match=MatchValue(value=str(params.universe_id)),
            )
        )

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
        search_filter = Filter(must=must_conditions)

    # Get underlying Qdrant client
    qdrant = client.get_client()

    # Search for similar memories
    search_results = run_sync(
        _qdrant_search_points(
            qdrant,
            collection_name="memories",
            query_vector=query_vector,
            limit=params.top_k,
            query_filter=search_filter,
            score_threshold=None,
        )
    )

    # Convert results to MemorySearchResult objects
    results = []
    for scored_point in search_results:
        payload = scored_point.payload

        # Filter by importance if specified
        importance = payload.get("importance", 0.0)
        if params.min_importance is not None and importance < params.min_importance:
            continue

        # Extract metadata from payload
        # Note: Full memory text is NOT stored in Qdrant (storage optimization)
        # Caller must use memory_id to fetch full memory from MongoDB if needed
        results.append(
            MemorySearchResult(
                memory_id=UUID(payload["memory_id"]),
                entity_id=UUID(payload["entity_id"]),
                text=None,  # Not stored in Qdrant, fetch from MongoDB using memory_id
                scene_id=(UUID(payload["scene_id"]) if payload.get("scene_id") else None),
                importance=importance,
                score=scored_point.score,
                metadata={
                    k: v
                    for k, v in payload.items()
                    if k not in ["memory_id", "entity_id", "scene_id", "importance", "type"]
                },
            )
        )

    return MemorySearchResponse(
        results=results,
        query=params.query_text,
        top_k=params.top_k,
    )
