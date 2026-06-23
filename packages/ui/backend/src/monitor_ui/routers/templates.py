"""
Entity Templates router — CRUD operations for entity templates.

Exposes the full lifecycle of entity templates (NPC generation blueprints)
to the UI. Templates enable the GM to create NPCs on the fly with
consistent mechanics. Backed by MongoDB.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: data-layer only
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from monitor_data.schemas.entity_templates import (
    EntityType,
    EntityTemplateCreate,
    EntityTemplateFilter,
    EntityTemplateListResponse,
    EntityTemplateResponse,
    EntityTemplateUpdate,
)
from monitor_data.tools.mongodb_tools.templates import (
    mongodb_create_entity_template,
    mongodb_delete_entity_template,
    mongodb_get_entity_template,
    mongodb_list_entity_templates,
    mongodb_update_entity_template,
)


router = APIRouter()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/templates", response_model=EntityTemplateResponse, status_code=201)
async def create_template(body: EntityTemplateCreate) -> EntityTemplateResponse:
    """Create a new entity template."""
    result = mongodb_create_entity_template(body)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create template")
    return result


@router.get("/templates/{template_id}", response_model=EntityTemplateResponse)
async def get_template(template_id: UUID) -> EntityTemplateResponse:
    """Get a specific entity template by ID."""
    result = mongodb_get_entity_template(template_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    return result


@router.get("/templates", response_model=EntityTemplateListResponse)
async def list_templates(
    universe_id: UUID | None = None,
    entity_type: EntityType | None = None,
    parent_template_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EntityTemplateListResponse:
    """List entity templates with optional filtering."""
    filters = EntityTemplateFilter(
        universe_id=universe_id,
        entity_type=entity_type,
        parent_template_id=parent_template_id,
        limit=limit,
        offset=offset,
    )
    return mongodb_list_entity_templates(filters)


@router.patch("/templates/{template_id}", response_model=EntityTemplateResponse)
async def update_template(
    template_id: UUID,
    body: EntityTemplateUpdate,
) -> EntityTemplateResponse:
    """Update an existing entity template."""
    try:
        return mongodb_update_entity_template(template_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: UUID) -> None:
    """Delete an entity template."""
    deleted = mongodb_delete_entity_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
