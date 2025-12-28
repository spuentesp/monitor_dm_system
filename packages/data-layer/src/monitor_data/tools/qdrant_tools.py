"""
Qdrant MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose Qdrant vector operations via the MCP server.
Qdrant stores embeddings for semantic search of scenes, memories, and snippets.
"""

from typing import Dict, List, Optional
from uuid import UUID

from qdrant_client.models import (
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
    PointIdsList,
)

from monitor_data.db.qdrant import get_qdrant_client
from monitor_data.schemas.memories import (
    MemorySearchQuery,
    MemorySearchResponse,
    MemorySearchResult,
)


# =============================================================================
# MEMORY EMBEDDING OPERATIONS (DL-7)
# =============================================================================

# Collection name for memory embeddings
MEMORIES_COLLECTION = "memory_chunks"

# Vector size (using default OpenAI embedding size)
# In production, this should be configurable or detected from the embedding model
VECTOR_SIZE = 1536


def qdrant_embed_memory(
    memory_id: UUID,
    text: str,
    entity_id: UUID,
    importance: float,
    scene_id: Optional[UUID] = None,
    metadata: Optional[Dict] = None,
) -> Dict:
    """
    Generate and store embedding for a memory in Qdrant.

    Authority: Any agent (*)
    Use Case: DL-7

    Args:
        memory_id: UUID of the memory
        text: Memory text to embed
        entity_id: UUID of the entity who owns the memory
        importance: Importance score (0.0-1.0)
        scene_id: Optional scene reference
        metadata: Optional additional metadata

    Returns:
        Dict with operation result and point_id

    Note:
        This is a placeholder implementation. In production, you would:
        1. Call an embedding service (OpenAI, local model, etc.)
        2. Generate actual vector embeddings from the text
        3. Store the vector in Qdrant with the payload

        For now, we store a placeholder vector of zeros.
    """
    qdrant_client = get_qdrant_client()

    # Ensure collection exists
    qdrant_client.ensure_collection(
        collection_name=MEMORIES_COLLECTION,
        vector_size=VECTOR_SIZE,
    )

    # In production, generate actual embedding vector from text
    # For now, use a placeholder zero vector
    # TODO: Integrate with actual embedding service (OpenAI, etc.)
    vector = [0.0] * VECTOR_SIZE

    # Build payload
    payload = {
        "memory_id": str(memory_id),
        "entity_id": str(entity_id),
        "text": text,
        "importance": importance,
        "type": "memory",
    }

    if scene_id:
        payload["scene_id"] = str(scene_id)

    if metadata:
        payload["metadata"] = metadata

    # Create point
    point = PointStruct(
        id=str(memory_id),
        vector=vector,
        payload=payload,
    )

    # Upsert to Qdrant
    client = qdrant_client.get_client()
    client.upsert(
        collection_name=MEMORIES_COLLECTION,
        points=[point],
    )

    return {
        "success": True,
        "point_id": str(memory_id),
        "collection": MEMORIES_COLLECTION,
    }


def qdrant_search_memories(params: MemorySearchQuery) -> MemorySearchResponse:
    """
    Perform semantic search on memory embeddings.

    Authority: Any agent (*)
    Use Case: DL-7

    Args:
        params: Search query parameters

    Returns:
        MemorySearchResponse with ranked results

    Note:
        This is a placeholder implementation. In production, you would:
        1. Generate embedding for query_text
        2. Perform actual vector similarity search
        3. Return ranked results

        For now, we return empty results as we're using placeholder vectors.
    """
    qdrant_client = get_qdrant_client()

    # In production, generate actual embedding vector from query_text
    # For now, use a placeholder zero vector
    # TODO: Integrate with actual embedding service
    query_vector = [0.0] * VECTOR_SIZE

    # Build filter
    filter_conditions = []

    if params.entity_id:
        filter_conditions.append(
            FieldCondition(
                key="entity_id",
                match=MatchValue(value=str(params.entity_id)),
            )
        )

    if params.min_importance is not None:
        filter_conditions.append(
            FieldCondition(
                key="importance",
                range=Range(gte=params.min_importance),
            )
        )

    search_filter = Filter(must=filter_conditions) if filter_conditions else None

    # Perform search
    try:
        client = qdrant_client.get_client()
        search_results = client.search(
            collection_name=MEMORIES_COLLECTION,
            query_vector=query_vector,
            query_filter=search_filter,
            limit=params.top_k,
        )
    except Exception as e:
        # Collection might not exist yet or other Qdrant errors
        # Log for debugging in production
        search_results = []

    # Convert results
    results = []
    for hit in search_results:
        results.append(
            MemorySearchResult(
                memory_id=UUID(hit.payload["memory_id"]),
                entity_id=UUID(hit.payload["entity_id"]),
                text=hit.payload["text"],
                importance=hit.payload["importance"],
                score=hit.score,
                scene_id=(
                    UUID(hit.payload["scene_id"])
                    if hit.payload.get("scene_id")
                    else None
                ),
                metadata=hit.payload.get("metadata", {}),
            )
        )

    return MemorySearchResponse(
        results=results,
        query_text=params.query_text,
        total_results=len(results),
    )


def qdrant_delete_memory(memory_id: UUID) -> bool:
    """
    Delete a memory embedding from Qdrant.

    Authority: Any agent (*)
    Use Case: DL-7

    Args:
        memory_id: UUID of the memory to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    qdrant_client = get_qdrant_client()

    try:
        client = qdrant_client.get_client()
        client.delete(
            collection_name=MEMORIES_COLLECTION,
            points_selector=PointIdsList(points=[str(memory_id)]),
        )
        return True
    except Exception as e:
        # Log error in production for debugging
        # Could be collection not found, connection error, etc.
        return False
