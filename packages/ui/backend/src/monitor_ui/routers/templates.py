"""
Entity Templates router — CRUD operations for entity templates.

Exposes the full lifecycle of entity templates (NPC generation blueprints)
to the UI. Templates enable the GM to create NPCs on the fly with
consistent mechanics. Backed by MongoDB.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: data-layer only
"""

from __future__ import annotations

import random
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

# reason: monitor_data.schemas.entity_templates module is a recent addition that hasn't published py.typed metadata; suppress the unresolved-attribute errors at import time
from monitor_data.schemas.entity_templates import (  # type: ignore
    EntityTemplateCreate,
    EntityTemplateFilter,
    EntityTemplateListResponse,
    EntityTemplateResponse,
    EntityTemplateUpdate,
    EntityType,
    GenerationType,
    InstantiateEntityRequest,
    InstantiateEntityResponse,
    NamingPattern,
    NamingType,
    VariableProperty,
)
from monitor_data.tools.mongodb_tools.random_tables import mongodb_roll_on_table
from monitor_data.tools.mongodb_tools.templates import (
    mongodb_create_entity_template,
    mongodb_delete_entity_template,
    mongodb_get_entity_template,
    mongodb_increment_template_usage,
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


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


def _inherited_base_properties(
    template: EntityTemplateResponse,
    _visited: set[UUID] | None = None,
) -> dict[str, Any]:
    """Merge base_properties down the parent chain (oldest ancestor first).

    Child values win over parent values. Cycles are broken by the visited set.
    """
    visited = _visited if _visited is not None else set()
    visited.add(template.template_id)
    merged: dict[str, Any] = {}
    if template.parent_template_id and template.parent_template_id not in visited:
        parent = mongodb_get_entity_template(template.parent_template_id)
        if parent:
            merged = _inherited_base_properties(parent, visited)
    merged.update(template.base_properties)
    return merged


def _resolve_variable_property(
    vp: VariableProperty,
    naming: NamingPattern,
    instance_number: int,
) -> Any:
    """Resolve one variable property per its generation_type.

    Returns None when the value cannot be resolved server-side (LLM type, or
    a misconfigured property) — callers surface those separately.
    """
    if vp.generation_type == GenerationType.FIXED:
        return vp.options[0] if vp.options else None
    if vp.generation_type == GenerationType.CHOICE:
        return random.choice(vp.options) if vp.options else None
    if vp.generation_type == GenerationType.RANGE:
        if vp.range_min is None or vp.range_max is None:
            return None
        return random.randint(vp.range_min, vp.range_max)
    if vp.generation_type == GenerationType.PATTERN:
        if not vp.pattern:
            return None
        return _substitute_pattern(vp.pattern, naming, instance_number)
    if vp.generation_type == GenerationType.TABLE:
        if not vp.table_id:
            return None
        try:
            return mongodb_roll_on_table(vp.table_id).get("value")
        except (ValueError, KeyError):
            return None
    # LLM — resolved by the caller, not here.
    return None


def _substitute_pattern(pattern: str, naming: NamingPattern, instance_number: int) -> str:
    """Substitute {adjective} / {noun} / {number} tokens in a pattern string."""
    adjective = random.choice(naming.adjectives) if naming.adjectives else "Mysterious"
    noun = random.choice(naming.nouns) if naming.nouns else "Stranger"
    return pattern.replace("{adjective}", adjective).replace("{noun}", noun).replace("{number}", str(instance_number))


def _resolve_name(
    template: EntityTemplateResponse,
    override_name: str | None,
    instance_number: int,
) -> str:
    """Resolve the instance name from the template's naming_pattern."""
    if override_name and override_name.strip():
        return override_name.strip()
    naming = template.naming_pattern
    if naming.type == NamingType.PATTERN and naming.pattern:
        return _substitute_pattern(naming.pattern, naming, instance_number)
    if naming.type == NamingType.NUMBERED:
        return f"{template.name} {instance_number}"
    if naming.type == NamingType.LIST and naming.name_list:
        return random.choice(naming.name_list)
    # LLM / USER / unresolvable — caller (or LLM chain) may rename later.
    return f"{template.name} (Instance)"


def _set_dot_path(properties: dict[str, Any], path: str, value: Any) -> None:
    """Set ``value`` at a dot-path inside ``properties``, creating dicts.

    A leading ``properties.`` segment is stripped so schema examples like
    ``properties.faction`` and ``stats.STR`` both land in the same place.
    """
    parts = path.split(".")
    if parts and parts[0] == "properties":
        parts = parts[1:]
    if not parts:
        return
    cursor = properties
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base`` (override wins)."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


@router.post(
    "/templates/{template_id}/instantiate",
    response_model=InstantiateEntityResponse,
)
async def instantiate_template(
    template_id: UUID,
    body: InstantiateEntityRequest,
) -> InstantiateEntityResponse:
    """Resolve a template into a populated entity create-payload.

    Exercises ``variable_properties`` (per their generation rules) and
    ``naming_pattern``, merges inherited base_properties, applies overrides,
    and bumps ``usage_count``. LLM-typed variables are returned unresolved in
    ``llm_hints`` — the caller chains into an LLM generation endpoint if it
    wants those elaborated. Does NOT write to Neo4j (CanonKeeper authority).
    """
    if body.template_id is not None and body.template_id != template_id:
        raise HTTPException(
            status_code=400,
            detail="Body template_id does not match path template_id",
        )
    template = mongodb_get_entity_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

    instance_number = template.usage_count + 1

    properties = _inherited_base_properties(template)
    resolved: dict[str, Any] = {}
    llm_hints: dict[str, str] = {}
    for vp in template.variable_properties:
        if vp.generation_type == GenerationType.LLM:
            if vp.llm_hint:
                llm_hints[vp.property_path] = vp.llm_hint
            continue
        value = _resolve_variable_property(vp, template.naming_pattern, instance_number)
        if value is None:
            continue
        resolved[vp.property_path] = value
        _set_dot_path(properties, vp.property_path, value)

    if body.override_properties:
        _deep_merge(properties, body.override_properties)

    mongodb_increment_template_usage(template_id)

    return InstantiateEntityResponse(
        template_id=template.template_id,
        universe_id=template.universe_id,
        name=_resolve_name(template, body.override_name, instance_number),
        entity_type=template.entity_type,
        description=template.description,
        properties=properties,
        resolved_variables=resolved,
        llm_hints=llm_hints,
        state_tags=list(template.default_state_tags),
        detail_level=template.default_detail_level,
        default_personality=template.default_personality,
        usage_count=instance_number,
        scene_id=body.scene_id,
        story_id=body.story_id,
    )


@router.post(
    "/templates/{template_id}/increment-usage",
    response_model=EntityTemplateResponse,
)
async def increment_template_usage(template_id: UUID) -> EntityTemplateResponse:
    """Manually bump a template's usage_count (e.g. out-of-band instantiation)."""
    template = mongodb_get_entity_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    mongodb_increment_template_usage(template_id)
    updated = mongodb_get_entity_template(template_id)
    assert updated
    return updated
