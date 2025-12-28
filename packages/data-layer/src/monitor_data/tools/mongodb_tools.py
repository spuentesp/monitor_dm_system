"""
MongoDB MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose MongoDB operations via the MCP server for narrative
documents like story outlines, scenes, turns, and proposals.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.outlines import (
    StoryOutlineCreate,
    StoryOutlineUpdate,
    StoryOutlineResponse,
    OutlineBeat,
)


# =============================================================================
# STORY OUTLINE OPERATIONS (DL-6)
# =============================================================================


def mongodb_create_story_outline(params: StoryOutlineCreate) -> StoryOutlineResponse:
    """
    Create a new story outline document in MongoDB.

    Authority: CanonKeeper, Narrator
    Use Case: DL-6

    Args:
        params: Story outline creation parameters

    Returns:
        StoryOutlineResponse with created outline data

    Raises:
        ValueError: If story_id doesn't exist in Neo4j
    """
    # Verify story exists in Neo4j
    neo4j_client = get_neo4j_client()
    verify_query = """
    MATCH (s:Story {id: $story_id})
    RETURN s.id as id
    """
    result = neo4j_client.execute_read(verify_query, {"story_id": str(params.story_id)})
    if not result:
        raise ValueError(f"Story {params.story_id} not found in Neo4j")

    # Create outline document in MongoDB
    mongo_client = get_mongodb_client()
    db = mongo_client.db

    created_at = datetime.now(timezone.utc)

    outline_doc = {
        "story_id": str(params.story_id),
        "theme": params.theme,
        "premise": params.premise,
        "constraints": params.constraints,
        "beats": [beat.model_dump() for beat in params.beats],
        "open_threads": params.open_threads,
        "pc_ids": [str(pc_id) for pc_id in params.pc_ids],
        "status": "draft",
        "created_at": created_at,
        "updated_at": created_at,
    }

    db.story_outlines.insert_one(outline_doc)

    return StoryOutlineResponse(
        story_id=params.story_id,
        theme=params.theme,
        premise=params.premise,
        constraints=params.constraints,
        beats=params.beats,
        open_threads=params.open_threads,
        pc_ids=params.pc_ids,
        status="draft",
        created_at=created_at,
        updated_at=created_at,
    )


def mongodb_get_story_outline(story_id: UUID) -> Optional[StoryOutlineResponse]:
    """
    Get a story outline by story_id.

    Authority: Any agent (read-only)
    Use Case: DL-6

    Args:
        story_id: UUID of the story

    Returns:
        StoryOutlineResponse if found, None otherwise
    """
    mongo_client = get_mongodb_client()
    db = mongo_client.db

    outline_doc = db.story_outlines.find_one({"story_id": str(story_id)})

    if not outline_doc:
        return None

    # Convert beats back to OutlineBeat objects
    beats = [OutlineBeat(**beat) for beat in outline_doc.get("beats", [])]

    return StoryOutlineResponse(
        story_id=UUID(outline_doc["story_id"]),
        theme=outline_doc.get("theme", ""),
        premise=outline_doc.get("premise", ""),
        constraints=outline_doc.get("constraints", []),
        beats=beats,
        open_threads=outline_doc.get("open_threads", []),
        pc_ids=[UUID(pc_id) for pc_id in outline_doc.get("pc_ids", [])],
        status=outline_doc.get("status", "draft"),
        created_at=outline_doc["created_at"],
        updated_at=outline_doc.get("updated_at"),
    )


def mongodb_update_story_outline(
    story_id: UUID, params: StoryOutlineUpdate
) -> StoryOutlineResponse:
    """
    Update a story outline's mutable fields.

    Authority: CanonKeeper, Narrator
    Use Case: DL-6

    Args:
        story_id: UUID of the story
        params: Update parameters

    Returns:
        StoryOutlineResponse with updated outline data

    Raises:
        ValueError: If outline doesn't exist
    """
    mongo_client = get_mongodb_client()
    db = mongo_client.db

    # Verify outline exists
    existing = db.story_outlines.find_one({"story_id": str(story_id)})
    if not existing:
        raise ValueError(f"Story outline for story {story_id} not found")

    # Build update document
    update_doc = {"updated_at": datetime.now(timezone.utc)}

    if params.theme is not None:
        update_doc["theme"] = params.theme

    if params.premise is not None:
        update_doc["premise"] = params.premise

    if params.constraints is not None:
        update_doc["constraints"] = params.constraints

    if params.beats is not None:
        update_doc["beats"] = [beat.model_dump() for beat in params.beats]

    if params.open_threads is not None:
        update_doc["open_threads"] = params.open_threads

    if params.status is not None:
        update_doc["status"] = params.status

    # Update document
    db.story_outlines.update_one(
        {"story_id": str(story_id)}, {"$set": update_doc}
    )

    # Fetch and return updated document
    updated_doc = db.story_outlines.find_one({"story_id": str(story_id)})

    beats = [OutlineBeat(**beat) for beat in updated_doc.get("beats", [])]

    return StoryOutlineResponse(
        story_id=UUID(updated_doc["story_id"]),
        theme=updated_doc.get("theme", ""),
        premise=updated_doc.get("premise", ""),
        constraints=updated_doc.get("constraints", []),
        beats=beats,
        open_threads=updated_doc.get("open_threads", []),
        pc_ids=[UUID(pc_id) for pc_id in updated_doc.get("pc_ids", [])],
        status=updated_doc.get("status", "draft"),
        created_at=updated_doc["created_at"],
        updated_at=updated_doc.get("updated_at"),
    )
