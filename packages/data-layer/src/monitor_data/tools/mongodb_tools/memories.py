"""Auto-extracted MongoDB tools sub-module."""

from datetime import datetime, timezone
from typing import Dict, Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.memories import (
    MemoryCreate,
    MemoryFilter,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdate,
)
# =============================================================================
# CHARACTER MEMORY OPERATIONS
# =============================================================================


def mongodb_create_memory(params: MemoryCreate) -> MemoryResponse:
    """
    Create a new CharacterMemory document in MongoDB.

    Authority: All agents
    Use Case: DL-7

    Args:
        params: Memory creation parameters

    Returns:
        MemoryResponse with created memory data

    Raises:
        ValueError: If entity_id doesn't exist in Neo4j
    """
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()

    # Verify entity exists in Neo4j
    entity_check_query = """
    MATCH (e {id: $entity_id})
    WHERE e:EntityArchetype OR e:EntityInstance
    RETURN e.id as id
    """
    result = neo4j_client.execute_read(entity_check_query, {"entity_id": str(params.entity_id)})
    if not result:
        # Fallback: Check MongoDB for standalone characters (Task 4)
        from monitor_data.tools.mongodb_tools.characters import mongodb_get_character

        if not mongodb_get_character(params.entity_id):
            raise ValueError(f"Entity {params.entity_id} not found in Neo4j or MongoDB")

    # Verify scene exists if provided
    if params.scene_id:
        scenes_collection = mongo_client.get_collection("scenes")
        scene = scenes_collection.find_one({"scene_id": str(params.scene_id)})
        if not scene:
            raise ValueError(f"Scene {params.scene_id} not found")

    # Verify linked fact exists if provided
    if params.linked_fact_id:
        fact_check_query = """
        MATCH (f:Fact {id: $fact_id})
        RETURN f.id as id
        """
        result = neo4j_client.execute_read(
            fact_check_query, {"fact_id": str(params.linked_fact_id)}
        )
        if not result:
            raise ValueError(f"Fact {params.linked_fact_id} not found")

    # Create memory document
    now = datetime.now(timezone.utc)
    memory_id = uuid4()

    memory_doc = {
        "memory_id": str(memory_id),
        "universe_id": str(params.universe_id),
        "entity_id": str(params.entity_id),
        "text": params.text,
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "linked_fact_id": str(params.linked_fact_id) if params.linked_fact_id else None,
        "emotional_valence": params.emotional_valence,
        "importance": params.importance,
        "certainty": params.certainty,
        "metadata": params.metadata,
        "created_at": now,
        "last_accessed": now,
        "access_count": 0,
    }

    memories_collection = mongo_client.get_collection("character_memories")
    memories_collection.insert_one(memory_doc)

    # G1 FIX: After MongoDB write, fire-and-forget Qdrant embedding.
    # This is idempotent — safe to fail silently since the memory is already persisted.
    # Embedding is async by design (vectorization is the expensive step).
    try:
        from monitor_data.tools.qdrant_tools import qdrant_embed_memory
        from monitor_data.schemas.memories import MemoryEmbedRequest
        import threading

        embed_req = MemoryEmbedRequest(
            memory_id=memory_id,
            universe_id=params.universe_id,
            text=params.text,
            entity_id=params.entity_id,
            scene_id=params.scene_id,
            importance=params.importance,
            metadata={
                "story_id": params.metadata.get("story_id") if params.metadata else None,
            },
        )

        def _embed() -> None:
            try:
                qdrant_embed_memory(embed_req)
            except Exception:
                pass  # Don't let embedding failures affect the memory write

        thread = threading.Thread(target=_embed)
        thread.start()
    except Exception:
        pass  # Complete silence on embedding failures

    return MemoryResponse(
        memory_id=memory_id,
        universe_id=params.universe_id,
        entity_id=params.entity_id,
        text=params.text,
        scene_id=params.scene_id,
        linked_fact_id=params.linked_fact_id,
        emotional_valence=params.emotional_valence,
        importance=params.importance,
        certainty=params.certainty,
        metadata=params.metadata,
        created_at=now,
        last_accessed=now,
        access_count=0,
    )


def mongodb_get_memory(memory_id: UUID) -> MemoryResponse:
    """
    Get a memory by ID and update access tracking.

    Authority: All agents
    Use Case: DL-7

    Args:
        memory_id: Memory UUID

    Returns:
        MemoryResponse with memory data

    Raises:
        ValueError: If memory not found
    """
    mongo_client = get_mongodb_client()
    memories_collection = mongo_client.get_collection("character_memories")

    # Update access tracking
    now = datetime.now(timezone.utc)
    result = memories_collection.find_one_and_update(
        {"memory_id": str(memory_id)},
        {"$set": {"last_accessed": now}, "$inc": {"access_count": 1}},
        return_document=True,
    )

    if not result:
        raise ValueError(f"Memory {memory_id} not found")

    return MemoryResponse(
        memory_id=UUID(result["memory_id"]),
        universe_id=UUID(result["universe_id"]),
        entity_id=UUID(result["entity_id"]),
        text=result["text"],
        scene_id=UUID(result["scene_id"]) if result.get("scene_id") else None,
        linked_fact_id=(UUID(result["linked_fact_id"]) if result.get("linked_fact_id") else None),
        emotional_valence=result["emotional_valence"],
        importance=result["importance"],
        certainty=result["certainty"],
        metadata=result["metadata"],
        created_at=result["created_at"],
        last_accessed=result["last_accessed"],
        access_count=result["access_count"],
    )


def mongodb_list_memories(params: MemoryFilter) -> MemoryListResponse:
    """
    List memories with optional filters.

    Authority: All agents
    Use Case: DL-7

    Args:
        params: Filter parameters

    Returns:
        MemoryListResponse with filtered memories and pagination
    """
    mongo_client = get_mongodb_client()
    memories_collection = mongo_client.get_collection("character_memories")

    # Build filter
    filter_dict: Dict[str, Any] = {}
    if params.universe_id:
        filter_dict["universe_id"] = str(params.universe_id)
    if params.entity_id:
        filter_dict["entity_id"] = str(params.entity_id)
    if params.scene_id:
        filter_dict["scene_id"] = str(params.scene_id)
    if params.min_importance is not None or params.max_importance is not None:
        filter_dict["importance"] = {}
        if params.min_importance is not None:
            filter_dict["importance"]["$gte"] = params.min_importance
        if params.max_importance is not None:
            filter_dict["importance"]["$lte"] = params.max_importance
    if params.min_emotional_valence is not None or params.max_emotional_valence is not None:
        filter_dict["emotional_valence"] = {}
        if params.min_emotional_valence is not None:
            filter_dict["emotional_valence"]["$gte"] = params.min_emotional_valence
        if params.max_emotional_valence is not None:
            filter_dict["emotional_valence"]["$lte"] = params.max_emotional_valence

    # Get total count
    total = memories_collection.count_documents(filter_dict)

    # Get paginated results, ordered by importance descending
    cursor = (
        memories_collection.find(filter_dict)
        .sort("importance", -1)
        .skip(params.offset)
        .limit(params.limit)
    )

    memories = [
        MemoryResponse(
            memory_id=UUID(mem_doc["memory_id"]),
            universe_id=UUID(mem_doc["universe_id"]),
            entity_id=UUID(mem_doc["entity_id"]),
            text=mem_doc["text"],
            scene_id=UUID(mem_doc["scene_id"]) if mem_doc.get("scene_id") else None,
            linked_fact_id=(
                UUID(mem_doc["linked_fact_id"]) if mem_doc.get("linked_fact_id") else None
            ),
            emotional_valence=mem_doc["emotional_valence"],
            importance=mem_doc["importance"],
            certainty=mem_doc["certainty"],
            metadata=mem_doc["metadata"],
            created_at=mem_doc["created_at"],
            last_accessed=mem_doc["last_accessed"],
            access_count=mem_doc["access_count"],
        )
        for mem_doc in cursor
    ]

    return MemoryListResponse(
        memories=memories, total=total, limit=params.limit, offset=params.offset
    )


def mongodb_update_memory(memory_id: UUID, params: MemoryUpdate) -> MemoryResponse:
    """
    Update a memory document.

    Authority: All agents
    Use Case: DL-7

    Args:
        memory_id: Memory UUID
        params: Fields to update

    Returns:
        Updated MemoryResponse

    Raises:
        ValueError: If memory not found
    """
    mongo_client = get_mongodb_client()
    memories_collection = mongo_client.get_collection("character_memories")

    # Build update dict
    update_dict: Dict[str, Any] = {}
    if params.importance is not None:
        update_dict["importance"] = params.importance
    if params.certainty is not None:
        update_dict["certainty"] = params.certainty
    if params.emotional_valence is not None:
        update_dict["emotional_valence"] = params.emotional_valence
    if params.metadata is not None:
        update_dict["metadata"] = params.metadata

    if not update_dict:
        # No updates provided, just return current state
        return mongodb_get_memory(memory_id)

    result = memories_collection.update_one({"memory_id": str(memory_id)}, {"$set": update_dict})

    if result.matched_count == 0:
        raise ValueError(f"Memory {memory_id} not found")

    return mongodb_get_memory(memory_id)


def mongodb_delete_memory(memory_id: UUID) -> bool:
    """
    Delete a memory document.

    Note: Caller is responsible for deleting corresponding Qdrant vector.

    Authority: All agents
    Use Case: DL-7

    Args:
        memory_id: Memory UUID

    Returns:
        True if deleted, False if not found
    """
    mongo_client = get_mongodb_client()
    memories_collection = mongo_client.get_collection("character_memories")

    result = memories_collection.delete_one({"memory_id": str(memory_id)})

    return result.deleted_count > 0


def mongodb_verify_memory(
    memory_id: UUID,
    expected_text: str | None = None,
    expected_entity_id: UUID | None = None,
) -> dict:
    """
    Verify a memory was written correctly.

    Checks that the memory exists and optionally validates that its text
    and entity_id match expected values. Used by agents to confirm that
    memory extraction persisted correctly.

    Authority: ["*"] (read-only verification)
    Use Case: GAP-H/T

    Args:
        memory_id: UUID of the memory to verify.
        expected_text: Optional text to match against (substring check).
        expected_entity_id: Optional entity_id to match against.

    Returns:
        Dict with 'verified' (bool), 'memory_id', 'matches_text',
        'matches_entity_id', and 'actual_text' (truncated).

    Raises:
        ValueError: If memory not found.
    """
    memory = mongodb_get_memory(memory_id)

    matches_text = True
    if expected_text:
        matches_text = expected_text.lower() in memory.text.lower()

    matches_entity_id = True
    if expected_entity_id:
        matches_entity_id = str(memory.entity_id) == str(expected_entity_id)

    verified = matches_text and matches_entity_id

    return {
        "verified": verified,
        "memory_id": str(memory_id),
        "matches_text": matches_text,
        "matches_entity_id": matches_entity_id,
        "actual_text": memory.text[:200] if memory.text else "",
    }
