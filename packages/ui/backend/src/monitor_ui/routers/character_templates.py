"""
HTTP surface for portable character templates (G-6 / P&F §6).

The contract lives in the data layer
(``monitor_data.schemas.character_templates`` and
``monitor_data.tools.mongodb_tools.character_templates``); this router is a
thin wrapper over it, following the ``canon_review.py`` data-layer-direct
precedent.

A template is a *portable* description of a player character — no stats, no
skills, no world binding. The GM's library holds the templates; instantiating
one into a world is a separate step (G-6 Phase 3).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from monitor_data.schemas.character_templates import (
    CharacterTemplateCreate,
    CharacterTemplateFilter,
    CharacterTemplateListResponse,
    CharacterTemplateResponse,
    CharacterTemplateUpdate,
)
from monitor_data.tools.mongodb_tools.character_templates import (
    mongodb_create_character_template,
    mongodb_delete_character_template,
    mongodb_get_character_template,
    mongodb_list_character_templates,
    mongodb_update_character_template,
)

router = APIRouter()


@router.get("/templates", response_model=CharacterTemplateListResponse)
async def list_character_templates(
    name_contains: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> CharacterTemplateListResponse:
    """List the character templates in the GM's library."""
    return mongodb_list_character_templates(
        CharacterTemplateFilter(name_contains=name_contains, limit=limit, offset=offset)
    )


@router.post("/templates", response_model=CharacterTemplateResponse, status_code=201)
async def create_character_template(body: CharacterTemplateCreate) -> CharacterTemplateResponse:
    """Create a character template."""
    return mongodb_create_character_template(body)


@router.get("/templates/{template_id}", response_model=CharacterTemplateResponse)
async def get_character_template(template_id: str) -> CharacterTemplateResponse:
    """Fetch one character template."""
    template = mongodb_get_character_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Character template not found")
    return template


@router.patch("/templates/{template_id}", response_model=CharacterTemplateResponse)
async def update_character_template(
    template_id: str,
    body: CharacterTemplateUpdate,
) -> CharacterTemplateResponse:
    """Update a character template."""
    template = mongodb_update_character_template(template_id, body)
    if template is None:
        raise HTTPException(status_code=404, detail="Character template not found")
    return template


@router.delete("/templates/{template_id}", status_code=204)
async def delete_character_template(template_id: str) -> None:
    """Delete a character template."""
    if not mongodb_delete_character_template(template_id):
        raise HTTPException(status_code=404, detail="Character template not found")
