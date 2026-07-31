"""
Lorebook router — CRUD + injection operations for character lorebook entries.

Exposes the full lifecycle of lorebook entries (keyword-triggered memory injection)
to the UI. Entries belong to characters or universes and are scanned against
player input to inject relevant lore into the narrative context.

Also provides SillyTavern / character.ai lorebook import/export.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: data-layer only
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from monitor_data.interop.sillytavern_lorebook import (
    build_st_lorebook,
    parse_st_lorebook_raw,
)
from monitor_data.schemas.lorebook import (
    LorebookEntry,
    LorebookEntryCreate,
    LorebookEntryUpdate,
    LorebookScanConfig,
)
from monitor_data.tools.mongodb_tools.lorebook_tools import (
    mongodb_bulk_create_lorebook_entries,
    mongodb_create_lorebook_entry,
    mongodb_delete_lorebook_entry,
    mongodb_get_lorebook_entries,
    mongodb_get_lorebook_entries_by_tags,
    mongodb_get_lorebook_entry,
    mongodb_get_lorebook_stats,
    mongodb_get_scan_config,
    mongodb_get_top_lorebook_entries,
    mongodb_inject_lorebook_entries,
    mongodb_save_scan_config,
    mongodb_scan_lorebook,
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


@router.get("/lorebook/entries/by-tags", response_model=list[LorebookEntry])
async def list_entries_by_tags(
    character_id: str = Query(..., description="Character ID"),
    tags: str = Query(..., description="Comma-separated tags"),
) -> list[LorebookEntry]:
    """List entries matching any of the given tags."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    return mongodb_get_lorebook_entries_by_tags(character_id=character_id, tags=tag_list)


@router.get("/lorebook/entries", response_model=list[LorebookEntry])
async def list_entries(
    character_id: str = Query(..., description="Character ID to filter by"),
    sort_by: str = Query(
        default="priority",
        description="Sort field: priority, trigger_count, created_at",
    ),
    ascending: bool = Query(default=False),
) -> list[LorebookEntry]:
    """List all active lorebook entries for a character."""
    return mongodb_get_lorebook_entries(character_id=character_id, sort_by=sort_by, ascending=ascending)  # type: ignore


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


@router.post("/lorebook/bulk", response_model=list[LorebookEntry], status_code=201)
async def bulk_create_entries(
    character_id: str,
    entries: list[LorebookEntryCreate],
) -> list[LorebookEntry]:
    """Create multiple lorebook entries at once."""
    return mongodb_bulk_create_lorebook_entries(character_id=character_id, entries=entries)


# ---------------------------------------------------------------------------
# Injection & Stats
# ---------------------------------------------------------------------------


@router.post("/lorebook/inject", response_model=list[str])
async def inject_entries(
    character_id: str = Query(..., description="Character ID"),
    text: str = Query(..., description="Player input text to scan"),
    scene_context: str | None = Query(None, description="Optional scene tag filter"),
) -> list[str]:
    """Scan text against lorebook entries and return matched content."""
    return mongodb_inject_lorebook_entries(
        character_id=character_id,
        text=text,
        scene_context=scene_context,
        increment_triggers=True,
    )


@router.get("/lorebook/stats")
async def get_stats(character_id: str = Query(..., description="Character ID")) -> dict:  # type: ignore
    """Get aggregate stats for a character's lorebook."""
    return mongodb_get_lorebook_stats(character_id)


@router.get("/lorebook/top", response_model=list[LorebookEntry])
async def get_top_entries(
    character_id: str = Query(..., description="Character ID"),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[LorebookEntry]:
    """Get top lorebook entries by trigger count."""
    return mongodb_get_top_lorebook_entries(character_id=character_id, limit=limit)


# ---------------------------------------------------------------------------
# SillyTavern import/export
# ---------------------------------------------------------------------------


@router.post("/lorebook/import", status_code=201)
async def import_lorebook(
    character_id: str = Form(..., description="Character ID to own the imported entries"),
    file: UploadFile | None = File(None, description="SillyTavern World Info JSON file"),
    payload: str | None = Form(None, description="Raw SillyTavern World Info JSON string"),
) -> dict[str, Any]:
    """Import a SillyTavern World Info JSON file or string for a character."""
    raw: bytes | str | None = None
    if file:
        raw = await file.read()
    elif payload:
        raw = payload
    else:
        raise HTTPException(status_code=422, detail="Provide either 'file' or 'payload'.")

    try:
        parsed_entries, config = parse_st_lorebook_raw(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid lorebook JSON: {exc}") from exc

    created: list[LorebookEntry] = []
    errors: list[str] = []
    for raw_entry in parsed_entries:
        try:
            data = LorebookEntryCreate(**raw_entry)
            entry = mongodb_create_lorebook_entry(character_id=character_id, data=data)
            created.append(entry)
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(str(exc))

    mongodb_save_scan_config(character_id, config)

    return {
        "imported": len(created),
        "errors": errors,
        "entries": created,
        "scan_config": config.model_dump(),
    }


@router.get("/lorebook/export")
async def export_lorebook(
    character_id: str = Query(..., description="Character ID"),
    name: str = Query(default="MONITOR lorebook"),
    description: str = Query(default=""),
) -> JSONResponse:
    """Export a character's lorebook as a SillyTavern World Info JSON file."""
    entries = mongodb_get_lorebook_entries(character_id, sort_by="order", ascending=True)
    raw_config = mongodb_get_scan_config(character_id)
    config = raw_config if isinstance(raw_config, LorebookScanConfig) else LorebookScanConfig(**raw_config)
    book = build_st_lorebook(
        entries,
        name=name,
        description=description,
        config=config,
    )
    filename = f"{character_id}_lorebook.json"
    return JSONResponse(
        content=book,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Scan config
# ---------------------------------------------------------------------------


@router.get("/lorebook/scan-config", response_model=LorebookScanConfig)
async def get_scan_config(character_id: str = Query(..., description="Character ID")) -> LorebookScanConfig:
    """Get SillyTavern-style scan settings for a character's lorebook."""
    return mongodb_get_scan_config(character_id)


@router.put("/lorebook/scan-config", response_model=LorebookScanConfig)
async def update_scan_config(
    character_id: str = Query(..., description="Character ID"),
    config: LorebookScanConfig = ...,  # type: ignore[assignment]
) -> LorebookScanConfig:
    """Update SillyTavern-style scan settings for a character's lorebook."""
    return mongodb_save_scan_config(character_id, config)


# ---------------------------------------------------------------------------
# Full scan (diagnostic/debug)
# ---------------------------------------------------------------------------


@router.post("/lorebook/scan")
async def scan_lorebook(
    character_id: str = Query(..., description="Character ID"),
    text: str = Query(..., description="Player input text to scan"),
    history: list[str] | None = Query(None, description="Recent turn texts (oldest to newest)"),
    scene_context: str | None = Query(None, description="Optional scene tag filter"),
) -> dict[str, Any]:
    """Run a full SillyTavern-aware scan and return position-grouped contents."""
    raw_config = mongodb_get_scan_config(character_id)
    config = raw_config if isinstance(raw_config, LorebookScanConfig) else LorebookScanConfig(**raw_config)
    result = mongodb_scan_lorebook(
        character_ids=[character_id],
        text=text,
        history=history,
        config=config,
        scene_context=scene_context,
        turn_index=None,
        increment_triggers=False,
    )
    if isinstance(result, dict):
        return result
    return result.model_dump()
