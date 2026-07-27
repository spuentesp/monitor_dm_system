"""Social entity inference, role annotation, and container materialization."""

from __future__ import annotations

import re
from typing import Any

from monitor_data.schemas.knowledge_packs import (
    ExtractedEntityArchetype,
    ExtractedRelationship,
)

from monitor_agents.utils.analyzer_support._constants import (
    _FACTION_RELATION_KEYS,
    _FACTION_TOKENS,
    _GENERIC_MEMBER_KEYS,
    _ORG_RELATION_KEYS,
    _ORG_TOKENS,
    _PART_OF_SUB_TYPES,
    GENERIC_CATEGORY_NAMES,
    INSTITUTION_ROLE_HINTS,
    SOCIAL_RELATION_PROPERTY_KEYS,
)
from monitor_agents.utils.analyzer_support._entities import (
    infer_container_entity_type,
    split_semantic_values,
)

# ---------------------------------------------------------------------------
# Social entity identity inference
# ---------------------------------------------------------------------------


def infer_social_entity_identity(name: str, relation_key: str) -> tuple[str, str]:
    """Infer entity_type/sub_type for a synthesized social or institutional entity."""
    lowered = f"{relation_key} {name}".lower().strip()
    if relation_key in _FACTION_RELATION_KEYS or any(token in lowered for token in _FACTION_TOKENS):
        return "faction", relation_key if relation_key in _FACTION_RELATION_KEYS else "faction"
    if relation_key in _ORG_RELATION_KEYS or any(token in lowered for token in _ORG_TOKENS):
        if relation_key in _GENERIC_MEMBER_KEYS:
            return "organization", "institution"
        return "organization", relation_key
    return "organization", "institution"


# ---------------------------------------------------------------------------
# Role annotation
# ---------------------------------------------------------------------------


def annotate_entity_roles(entity: ExtractedEntityArchetype) -> ExtractedEntityArchetype:
    """Annotate each entity with explicit semantic roles and container metadata."""
    props = dict(entity.properties or {})
    raw_role_values: list[Any] = []
    for key in ("entity_roles", "roles"):
        value = props.get(key)
        if value:
            raw_role_values.append(value)

    roles: set[str] = {str(role).strip().lower() for role in getattr(entity, "entity_roles", []) if str(role).strip()}
    for existing_roles in raw_role_values:
        if isinstance(existing_roles, str):
            roles.update(part.strip().lower() for part in re.split(r"\s*[,/;+]\s*", existing_roles) if part.strip())
        elif isinstance(existing_roles, list):
            roles.update(str(role).strip().lower() for role in existing_roles if str(role).strip())

    base_role_map = {
        "character": "character",
        "faction": "faction",
        "organization": "organization",
        "location": "location",
        "object": "object",
        "concept": "concept",
    }
    if entity.entity_type in base_role_map:
        roles.add(base_role_map[entity.entity_type])

    role_blob = f"{entity.name} {entity.sub_type or ''} {entity.description or ''}".lower()
    if entity.parent_entity_name:
        roles.add("taxonomy_member")

    if entity.entity_type in {"organization", "faction"} or any(token in role_blob for token in INSTITUTION_ROLE_HINTS):
        roles.add("institution")
        if entity.entity_type in {"organization", "faction"}:
            roles.add(entity.entity_type)

    is_container = bool(
        getattr(entity, "is_container", False)
        or props.get("container") is True
        or props.get("is_container") is True
        or (entity.sub_type or "").lower().strip() == "container"
    )
    if is_container:
        roles.update({"container", "taxonomy_container"})

    if "taxonomy_member" in roles and any(role in roles for role in {"organization", "faction", "institution"}):
        roles.add("multi_role")

    props["entity_roles"] = sorted(roles)
    if is_container:
        props["is_container"] = True

    tags = list(dict.fromkeys([*(entity.tags or []), *sorted(roles)]))
    return entity.model_copy(
        update={
            "properties": props,
            "entity_roles": sorted(roles),
            "is_container": is_container,
            "tags": tags,
        }
    )


# ---------------------------------------------------------------------------
# Container entity materialization
# ---------------------------------------------------------------------------


def materialize_container_entities(
    entities: list[ExtractedEntityArchetype],
    source_name: str,
) -> tuple[list[ExtractedEntityArchetype], int]:
    """Create named parent/container entities from child hierarchy hints."""
    if not entities:
        return entities, 0

    normalized_entities: list[ExtractedEntityArchetype] = []
    for entity in entities:
        parent_name = entity.parent_entity_name
        if not parent_name and entity.sub_type:
            candidate = entity.sub_type.replace("_", " ").strip().title()
            if candidate and candidate.lower() != entity.name.lower():
                entity = entity.model_copy(update={"parent_entity_name": candidate})
        normalized_entities.append(annotate_entity_roles(entity))

    existing_by_name = {
        entity.name.lower().strip(): entity for entity in normalized_entities if entity.name and entity.name.strip()
    }

    children_by_parent: dict[str, list[ExtractedEntityArchetype]] = {}
    for entity in normalized_entities:
        if not entity.parent_entity_name:
            continue
        children_by_parent.setdefault(entity.parent_entity_name.strip(), []).append(entity)

    synthesized: list[ExtractedEntityArchetype] = []
    for parent_name, children in children_by_parent.items():
        key = parent_name.lower().strip()
        if not parent_name or key in existing_by_name:
            continue

        entity_type = infer_container_entity_type(parent_name, children)
        child_names = ", ".join(child.name for child in children[:6])
        synthesized_entity = ExtractedEntityArchetype(
            name=parent_name,
            entity_type=entity_type,
            sub_type="container",
            description=(
                f"Named container/category entity synthesized from {source_name}. "
                f"Groups examples such as: {child_names}."
            )[:1000],
            properties={
                "container": True,
                "child_count": len(children),
                "examples": [child.name for child in children[:12]],
            },
            entity_roles=["container", "taxonomy_container"],
            is_container=True,
            parent_entity_name=None,
            source_ref=children[0].source_ref,
            confidence=max(child.confidence for child in children),
            tags=["container", "schema_family", f"source:{source_name[:40]}"],
        )
        synthesized_entity = annotate_entity_roles(synthesized_entity)
        synthesized.append(synthesized_entity)
        existing_by_name[key] = synthesized_entity

    return normalized_entities + synthesized, len(synthesized)


# ---------------------------------------------------------------------------
# Hierarchy → relationship derivation
# ---------------------------------------------------------------------------


def derive_hierarchy_relationships(
    entities: list[ExtractedEntityArchetype],
) -> list[ExtractedRelationship]:
    """Convert every parent_entity_name link into an ExtractedRelationship deterministically."""
    by_name: dict[str, ExtractedEntityArchetype] = {e.name.lower().strip(): e for e in entities}

    broken: set[str] = set()
    for entity in entities:
        if not entity.parent_entity_name:
            continue
        key = entity.name.lower().strip()
        parent_key = entity.parent_entity_name.lower().strip()
        if key == parent_key:
            entity.parent_entity_name = None
            broken.add(key)
            continue
        parent = by_name.get(parent_key)
        if parent and parent.parent_entity_name:
            grandparent_key = parent.parent_entity_name.lower().strip()
            if grandparent_key == key:
                children_of_entity = sum(1 for e in entities if (e.parent_entity_name or "").lower().strip() == key)
                children_of_parent = sum(
                    1 for e in entities if (e.parent_entity_name or "").lower().strip() == parent_key
                )
                if children_of_entity >= children_of_parent:
                    entity.parent_entity_name = None
                    broken.add(key)
                else:
                    parent.parent_entity_name = None
                    broken.add(parent_key)

    def _has_cycle(start_key: str) -> bool:
        visited: set[str] = set()
        current = start_key
        while current:
            if current in visited:
                return True
            visited.add(current)
            ent = by_name.get(current)
            if not ent or not ent.parent_entity_name:
                return False
            current = ent.parent_entity_name.lower().strip()
        return False

    rels: list[ExtractedRelationship] = []
    for entity in entities:
        if not entity.parent_entity_name:
            continue
        key = entity.name.lower().strip()
        if _has_cycle(key):
            entity.parent_entity_name = None
            continue
        sub = (entity.sub_type or "").lower().strip()
        rel_type = "part_of" if sub in _PART_OF_SUB_TYPES else "subtype_of"
        rels.append(
            ExtractedRelationship(
                from_entity=entity.name,
                rel_type=rel_type,
                to_entity=entity.parent_entity_name,
                confidence=entity.confidence,
                source_ref=entity.source_ref,
            )
        )
    return rels


# ---------------------------------------------------------------------------
# Social entity materialization
# ---------------------------------------------------------------------------


def materialize_social_entities_and_relationships(
    entities: list[ExtractedEntityArchetype],
    source_name: str,
) -> tuple[list[ExtractedEntityArchetype], list[ExtractedRelationship], int]:
    """Create missing social entities and explicit membership links from traits."""
    if not entities:
        return entities, [], 0

    normalized_entities = [annotate_entity_roles(entity) for entity in entities]
    existing_by_name = {
        entity.name.lower().strip(): entity for entity in normalized_entities if entity.name and entity.name.strip()
    }

    synthesized: list[ExtractedEntityArchetype] = []
    inferred_relationships: list[ExtractedRelationship] = []
    seen_relationships: set[str] = set()

    for entity in normalized_entities:
        for key, raw_value in (entity.properties or {}).items():
            relation_key = str(key).strip().lower()
            rel_type = SOCIAL_RELATION_PROPERTY_KEYS.get(relation_key)
            if not rel_type:
                continue

            for target_name in split_semantic_values(raw_value):
                target_key = target_name.lower().strip()
                if not target_name or target_key == entity.name.lower().strip() or target_key in GENERIC_CATEGORY_NAMES:
                    continue

                target_entity = existing_by_name.get(target_key)
                if target_entity is None:
                    target_type, target_sub_type = infer_social_entity_identity(
                        target_name,
                        relation_key,
                    )
                    synthesized_entity = ExtractedEntityArchetype(
                        name=target_name,
                        entity_type=target_type,
                        sub_type=target_sub_type,
                        description=(
                            f"Named social or institutional entity synthesized from {source_name} "
                            f"based on the {relation_key} reference attached to {entity.name}."
                        )[:1000],
                        properties={"source_hint": relation_key},
                        entity_roles=[target_type, "institution"],
                        is_container=False,
                        parent_entity_name=None,
                        source_ref=entity.source_ref,
                        confidence=max(0.7, min(entity.confidence, 0.95)),
                        tags=["social_group", f"source:{source_name[:40]}"],
                    )
                    synthesized_entity = annotate_entity_roles(synthesized_entity)
                    synthesized.append(synthesized_entity)
                    existing_by_name[target_key] = synthesized_entity

                rel_key = f"{entity.name.lower().strip()}|{rel_type}|{target_key}"
                if rel_key in seen_relationships:
                    continue
                seen_relationships.add(rel_key)

                description = {
                    "member_of": f"{entity.name} belongs to or is aligned with {target_name}.",
                    "part_of": f"{entity.name} is part of {target_name}.",
                    "subgroup_of": f"{entity.name} is a subgroup or branch of {target_name}.",
                    "affiliated_with": f"{entity.name} is affiliated with {target_name}.",
                }.get(rel_type, f"{entity.name} is related to {target_name}.")
                inferred_relationships.append(
                    ExtractedRelationship(
                        from_entity=entity.name,
                        rel_type=rel_type,
                        to_entity=target_name,
                        description=description,
                        confidence=max(0.65, min(entity.confidence, 0.9)),
                        source_ref=entity.source_ref,
                    )
                )

    return normalized_entities + synthesized, inferred_relationships, len(synthesized)
