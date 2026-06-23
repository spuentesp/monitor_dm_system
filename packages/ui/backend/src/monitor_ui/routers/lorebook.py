"""
Lorebook router — CRUD + injection operations for character lorebook entries.

Exposes the full lifecycle of lorebook entries (keyword-triggered memory injection)
to the UI. Entries belong to characters or universes and are scanned against
player input to inject relevant lore into the narrative context.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: data-layer only
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from monitor_data.schemas.lorebook import (
    LorebookEntry,
    LorebookEntryCreate,
    LorebookEntryUpdate,
)
from monitor_data.tools.mongodb_tools.lorebook_tools import (
    mongodb_bulk_create_lorebook_entries,
    mongodb_create_lorebook_entry,
    mongodb_delete_lorebook_entry,
    mongodb_get_lorebook_entries,
    mongodb_get_lorebook_entries_by_tags,
    mongodb_get_lorebook_entry,
    mongodb_get_lorebook_stats,
    mongodb_get_top_lorebook_entries,
    mongodb_inject_lorebook_entries,
    mongodb_update_lorebook_entry,
)


router = APIRouter()


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------


@router.post("/lorebook/entries", response_model=LorebookEntry, status_code=201)
async def create_entry(body: LorebookEntryCreate, character_id: str) -> LorebookEntry:
    """Create a new lorebook entry for a character."""
    return mongodb_create_lorebook_entry(character_id=character_id, data=body)


@router.get("/lorebook/entries/by-tags", response_model=List[LorebookEntry])
async def list_entries_by_tags(
    character_id: str = Query(..., description="Character ID"),
    tags: str = Query(..., description="Comma-separated tags"),
) -> List[LorebookEntry]:
    """List entries matching any of the given tags."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    return mongodb_get_lorebook_entries_by_tags(
        character_id=character_id, tags=tag_list
    )


@router.get("/lorebook/entries", response_model=List[LorebookEntry])
async def list_entries(
    character_id: str = Query(..., description="Character ID to filter by"),
    sort_by: str = Query(
        default="priority",
        description="Sort field: priority, trigger_count, created_at",
    ),
    ascending: bool = Query(default=False),
) -> List[LorebookEntry]:
    """List all active lorebook entries for a character."""
    return mongodb_get_lorebook_entries(
        character_id=character_id, sort_by=sort_by, ascending=ascending
    )


@router.get("/lorebook/entries/{entry_id}", response_model=LorebookEntry)
async def get_entry(entry_id: str) -> LorebookEntry:
    """Get a specific lorebook entry by ID."""
    result = mongodb_get_lorebook_entry(entry_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")
    return result


@router.patch("/lorebook/entries/{entry_id}", response_model=LorebookEntry)
async def update_entry(entry_id: str, body: LorebookEntryUpdate) -> LorebookEntry:
    """Update a lorebook entry."""
    result = mongodb_update_lorebook_entry(entry_id, body)
    if not result:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")
    return result


@router.delete("/lorebook/entries/{entry_id}", status_code=204)
async def delete_entry(entry_id: str) -> None:
    """Delete a lorebook entry."""
    deleted = mongodb_delete_lorebook_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")


# ---------------------------------------------------------------------------
# Bulk Operations
# ---------------------------------------------------------------------------


@router.post("/lorebook/bulk", response_model=List[LorebookEntry], status_code=201)
async def bulk_create_entries(
    character_id: str,
    entries: List[LorebookEntryCreate],
) -> List[LorebookEntry]:
    """Create multiple lorebook entries at once."""
    return mongodb_bulk_create_lorebook_entries(
        character_id=character_id, entries=entries
    )


# ---------------------------------------------------------------------------
# Injection & Stats
# ---------------------------------------------------------------------------


@router.post("/lorebook/inject", response_model=List[str])
async def inject_entries(
    character_id: str = Query(..., description="Character ID"),
    text: str = Query(..., description="Player input text to scan"),
    scene_context: Optional[str] = Query(None, description="Optional scene tag filter"),
) -> List[str]:
    """Scan text against lorebook entries and return matched content."""
    return mongodb_inject_lorebook_entries(
        character_id=character_id,
        text=text,
        scene_context=scene_context,
        increment_triggers=True,
    )


@router.get("/lorebook/stats")
async def get_stats(character_id: str = Query(..., description="Character ID")) -> dict:
    """Get aggregate stats for a character's lorebook."""
    return mongodb_get_lorebook_stats(character_id)


@router.get("/lorebook/top", response_model=List[LorebookEntry])
async def get_top_entries(
    character_id: str = Query(..., description="Character ID"),
    limit: int = Query(default=10, ge=1, le=50),
) -> List[LorebookEntry]:
    """Get top lorebook entries by trigger count."""
    return mongodb_get_top_lorebook_entries(character_id=character_id, limit=limit)
