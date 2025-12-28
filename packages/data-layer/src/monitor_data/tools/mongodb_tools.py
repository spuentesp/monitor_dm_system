"""
MongoDB MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose MongoDB operations via the MCP server.
MongoDB stores narrative documents: scenes, turns, proposals, memories, etc.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.memories import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
    MemoryFilter,
    MemoryListResponse,
)


# =============================================================================
# MEMORY OPERATIONS (DL-7)
# =============================================================================


def mongodb_create_memory(params: MemoryCreate) -> MemoryResponse:
    """
    Create a new CharacterMemory document in MongoDB.

    Authority: Any agent (*)
    Use Case: DL-7

    Args:
        params: Memory creation parameters

    Returns:
        MemoryResponse with created memory data

    Raises:
        ValueError: If entity_id doesn't exist in Neo4j
    """
    # Validate entity exists
    neo4j_client = get_neo4j_client()
    verify_query = """
    MATCH (e:EntityInstance {id: $entity_id})
    RETURN e.id as id
    """
    result = neo4j_client.execute_read(
        verify_query, {"entity_id": str(params.entity_id)}
    )
    if not result:
        raise ValueError(f"Entity {params.entity_id} not found")

    # Create memory document
    mongodb_client = get_mongodb_client()
    collection = mongodb_client.get_collection("character_memories")

    memory_id = uuid4()
    created_at = datetime.now(timezone.utc)

    memory_doc = {
        "memory_id": str(memory_id),
        "entity_id": str(params.entity_id),
        "text": params.text,
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "fact_id": str(params.fact_id) if params.fact_id else None,
        "importance": params.importance,
        "emotional_valence": params.emotional_valence,
        "certainty": params.certainty,
        "metadata": params.metadata,
        "created_at": created_at,
        "last_accessed": created_at,
        "access_count": 0,
    }

    collection.insert_one(memory_doc)

    return MemoryResponse(
        memory_id=memory_id,
        entity_id=params.entity_id,
        text=params.text,
        scene_id=params.scene_id,
        fact_id=params.fact_id,
        importance=params.importance,
        emotional_valence=params.emotional_valence,
        certainty=params.certainty,
        metadata=params.metadata,
        created_at=created_at,
        last_accessed=created_at,
        access_count=0,
    )


def mongodb_get_memory(memory_id: UUID) -> Optional[MemoryResponse]:
    """
    Get a CharacterMemory by ID.

    Authority: Any agent (*)
    Use Case: DL-7

    Args:
        memory_id: UUID of the memory

    Returns:
        MemoryResponse if found, None otherwise
    """
    from pymongo import ReturnDocument

    mongodb_client = get_mongodb_client()
    collection = mongodb_client.get_collection("character_memories")

    # Atomically update and retrieve the document
    memory_doc = collection.find_one_and_update(
        {"memory_id": str(memory_id)},
        {
            "$set": {"last_accessed": datetime.now(timezone.utc)},
            "$inc": {"access_count": 1},
        },
        return_document=ReturnDocument.AFTER,
    )

    if not memory_doc:
        return None

    return MemoryResponse(
        memory_id=UUID(memory_doc["memory_id"]),
        entity_id=UUID(memory_doc["entity_id"]),
        text=memory_doc["text"],
        scene_id=UUID(memory_doc["scene_id"]) if memory_doc.get("scene_id") else None,
        fact_id=UUID(memory_doc["fact_id"]) if memory_doc.get("fact_id") else None,
        importance=memory_doc["importance"],
        emotional_valence=memory_doc["emotional_valence"],
        certainty=memory_doc["certainty"],
        metadata=memory_doc.get("metadata", {}),
        created_at=memory_doc["created_at"],
        last_accessed=memory_doc["last_accessed"],
        access_count=memory_doc["access_count"],
    )


def mongodb_list_memories(params: MemoryFilter) -> MemoryListResponse:
    """
    List CharacterMemories with filtering and pagination.

    Authority: Any agent (*)
    Use Case: DL-7

    Args:
        params: Filter parameters

    Returns:
        MemoryListResponse with memories and pagination info
    """
    mongodb_client = get_mongodb_client()
    collection = mongodb_client.get_collection("character_memories")

    # Build query filter
    query: Dict = {}
    if params.entity_id:
        query["entity_id"] = str(params.entity_id)
    if params.scene_id:
        query["scene_id"] = str(params.scene_id)
    if params.min_importance is not None:
        query["importance"] = {"$gte": params.min_importance}

    # Build sort
    sort_order = -1 if params.sort_order == "desc" else 1
    sort = [(params.sort_by, sort_order)]

    # Execute query with pagination
    cursor = collection.find(query).sort(sort).skip(params.offset).limit(params.limit)
    total = collection.count_documents(query)

    memories = []
    for doc in cursor:
        memories.append(
            MemoryResponse(
                memory_id=UUID(doc["memory_id"]),
                entity_id=UUID(doc["entity_id"]),
                text=doc["text"],
                scene_id=UUID(doc["scene_id"]) if doc.get("scene_id") else None,
                fact_id=UUID(doc["fact_id"]) if doc.get("fact_id") else None,
                importance=doc["importance"],
                emotional_valence=doc["emotional_valence"],
                certainty=doc["certainty"],
                metadata=doc.get("metadata", {}),
                created_at=doc["created_at"],
                last_accessed=doc["last_accessed"],
                access_count=doc["access_count"],
            )
        )

    return MemoryListResponse(
        memories=memories,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def mongodb_update_memory(
    memory_id: UUID, params: MemoryUpdate
) -> Optional[MemoryResponse]:
    """
    Update a CharacterMemory's mutable fields.

    Authority: Any agent (*)
    Use Case: DL-7

    Args:
        memory_id: UUID of the memory to update
        params: Update parameters

    Returns:
        Updated MemoryResponse if found, None otherwise
    """
    mongodb_client = get_mongodb_client()
    collection = mongodb_client.get_collection("character_memories")

    # Build update document
    update_doc: Dict = {}
    if params.importance is not None:
        update_doc["importance"] = params.importance
    if params.emotional_valence is not None:
        update_doc["emotional_valence"] = params.emotional_valence
    if params.certainty is not None:
        update_doc["certainty"] = params.certainty
    if params.metadata is not None:
        update_doc["metadata"] = params.metadata

    if not update_doc:
        # No updates provided, just return current memory
        return mongodb_get_memory(memory_id)

    # Update the document
    result = collection.update_one(
        {"memory_id": str(memory_id)},
        {"$set": update_doc},
    )

    if result.matched_count == 0:
        return None

    # Return updated memory
    return mongodb_get_memory(memory_id)


def mongodb_delete_memory(memory_id: UUID) -> bool:
    """
    Delete a CharacterMemory document.

    Authority: Any agent (*)
    Use Case: DL-7

    Args:
        memory_id: UUID of the memory to delete

    Returns:
        True if deleted, False if not found
    """
    mongodb_client = get_mongodb_client()
    collection = mongodb_client.get_collection("character_memories")

    result = collection.delete_one({"memory_id": str(memory_id)})

    return result.deleted_count > 0
