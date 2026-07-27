"""
Contextual relationship tools for hierarchical queries.

LAYER: 1 (data-layer)
DEPENDENCIES: monitor_data.db, monitor_data.schemas

This module provides tools for querying relationships by category and tags,
enabling context-aware queries like "all social relationships" or "all
relationships tagged 'familial'".

These tools are part of Phase 4 of the Neo4j performance optimization plan.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.relationships import (
    Direction,
    RelationshipCategory,
    RelationshipResponse,
    RelationshipSubcategory,
    RelationshipType,
)


def neo4j_get_relationships_by_category(
    entity_id: UUID,
    category: RelationshipCategory,
    direction: Direction = Direction.BOTH,
    limit: int = 50,
    offset: int = 0,
) -> list[RelationshipResponse]:
    """
    Get all relationships of a specific category for an entity.

    Authority: All agents
    Use Case: DL-14 (extended)

    Args:
        entity_id: Entity UUID
        category: Relationship category to filter by
        direction: Relationship direction (default: BOTH)
        limit: Maximum results to return
        offset: Results offset for pagination

    Returns:
        List of RelationshipResponse objects

    Example:
        Get all social relationships for an NPC:
        >>> from monitor_data.schemas.relationships import RelationshipCategory
        >>> social_rels = neo4j_get_relationships_by_category(
        ...     entity_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        ...     category=RelationshipCategory.SOCIAL
        ... )
    """
    client = get_neo4j_client()

    # Build direction clause
    if direction == Direction.OUTGOING:
        match_clause = "MATCH (e:Entity {id: $entity_id})-[r]->(other)"
    elif direction == Direction.INCOMING:
        match_clause = "MATCH (other)-[r]->(e:Entity {id: $entity_id})"
    else:  # BOTH
        match_clause = "MATCH (e:Entity {id: $entity_id})-[r]-(other)"

    query = f"""
    {match_clause}
    WHERE r.category = $category OR r.category IS NULL
    RETURN id(r) as rel_id, e.id as from_id, other.id as to_id,
           type(r) as rel_type, r.category as category, r.subcategory as subcategory,
           r.tags as tags, properties(r) as props
    ORDER BY id(r)
    SKIP $offset
    LIMIT $limit
    """

    result = client.execute_read(
        query,
        {
            "entity_id": str(entity_id),
            "category": category.value,
            "offset": offset,
            "limit": limit,
        },
    )

    relationships = []
    for rel in result:
        props = rel["props"] or {}

        # Extract category and subcategory
        category_str = rel.get("category") or props.get("category")
        subcategory_str = rel.get("subcategory") or props.get("subcategory")
        tags = rel.get("tags") or props.get("tags", [])

        # Parse category and subcategory
        rel_category = RelationshipCategory(category_str) if category_str else category
        rel_subcategory = RelationshipSubcategory(subcategory_str) if subcategory_str else None

        # Handle direction for from/to IDs
        if direction == Direction.INCOMING:
            from_id = UUID(rel["to_id"])
            to_id = UUID(rel["from_id"])
        else:
            from_id = UUID(rel["from_id"])
            to_id = UUID(rel["to_id"])

        relationships.append(
            RelationshipResponse(
                relationship_id=str(rel["rel_id"]),
                from_entity_id=from_id,
                to_entity_id=to_id,
                rel_type=RelationshipType(rel["rel_type"]),
                category=rel_category,
                subcategory=rel_subcategory,
                tags=tags,
                properties=props,
                created_at=(datetime.fromisoformat(str(props.get("created_at"))) if props.get("created_at") else None),
            )
        )

    return relationships


def neo4j_get_relationships_by_tags(
    entity_id: UUID,
    tags: list[str],
    require_all: bool = True,
    direction: Direction = Direction.BOTH,
    limit: int = 50,
    offset: int = 0,
) -> list[RelationshipResponse]:
    """
    Get relationships for an entity filtered by tags.

    Authority: All agents
    Use Case: DL-14 (extended)

    Args:
        entity_id: Entity UUID
        tags: Tags to filter by
        require_all: If True, require all tags; if False, require any tag
        direction: Relationship direction (default: BOTH)
        limit: Maximum results to return
        offset: Results offset for pagination

    Returns:
        List of RelationshipResponse objects

    Example:
        Get all familial relationships:
        >>> familial_rels = neo4j_get_relationships_by_tags(
        ...     entity_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        ...     tags=["familial"],
        ...     require_all=True
        ... )
    """
    client = get_neo4j_client()

    # Build direction clause
    if direction == Direction.OUTGOING:
        match_clause = "MATCH (e:Entity {id: $entity_id})-[r]->(other)"
    elif direction == Direction.INCOMING:
        match_clause = "MATCH (other)-[r]->(e:Entity {id: $entity_id})"
    else:  # BOTH
        match_clause = "MATCH (e:Entity {id: $entity_id})-[r]-(other)"

    # Build tag filter clause
    if require_all:
        tag_filter = "ALL(tag IN $tags WHERE tag IN coalesce(r.tags, []))"
    else:
        tag_filter = "ANY(tag IN $tags WHERE tag IN coalesce(r.tags, []))"

    query = f"""
    {match_clause}
    WHERE {tag_filter}
    RETURN id(r) as rel_id, e.id as from_id, other.id as to_id,
           type(r) as rel_type, r.category as category, r.subcategory as subcategory,
           r.tags as tags, properties(r) as props
    ORDER BY id(r)
    SKIP $offset
    LIMIT $limit
    """

    result = client.execute_read(
        query,
        {
            "entity_id": str(entity_id),
            "tags": tags,
            "offset": offset,
            "limit": limit,
        },
    )

    relationships = []
    for rel in result:
        props = rel["props"] or {}

        # Extract category and subcategory
        category_str = rel.get("category") or props.get("category")
        subcategory_str = rel.get("subcategory") or props.get("subcategory")
        tags_list = rel.get("tags") or props.get("tags", [])

        # Parse category and subcategory
        rel_category = RelationshipCategory(category_str) if category_str else RelationshipCategory.GENERIC
        rel_subcategory = RelationshipSubcategory(subcategory_str) if subcategory_str else None

        # Handle direction for from/to IDs
        if direction == Direction.INCOMING:
            from_id = UUID(rel["to_id"])
            to_id = UUID(rel["from_id"])
        else:
            from_id = UUID(rel["from_id"])
            to_id = UUID(rel["to_id"])

        relationships.append(
            RelationshipResponse(
                relationship_id=str(rel["rel_id"]),
                from_entity_id=from_id,
                to_entity_id=to_id,
                rel_type=RelationshipType(rel["rel_type"]),
                category=rel_category,
                subcategory=rel_subcategory,
                tags=tags_list,
                properties=props,
                created_at=(datetime.fromisoformat(str(props.get("created_at"))) if props.get("created_at") else None),
            )
        )

    return relationships


def neo4j_get_entity_relationship_context(
    entity_id: UUID,
    include_categories: list[RelationshipCategory] | None = None,
    max_distance: int = 2,
    limit_per_entity: int = 10,
) -> dict[str, Any]:
    """
    Get comprehensive relationship context for an entity.

    Returns all relationships within a given hop distance, optionally
    filtered by category. This is useful for context assembly and
    understanding an entity's social, organizational, or power network.

    Authority: All agents
    Use Case: DL-14 (extended)

    Args:
        entity_id: Entity UUID
        include_categories: Optional list of categories to include (None = all)
        max_distance: Maximum hop distance (default: 2)
        limit_per_entity: Max relationships per related entity

    Returns:
        Dict with:
        - entity_id: The queried entity
        - categories: Mapping of category -> list of relationships
        - by_entity: Mapping of related entity ID -> list of relationships
        - stats: Summary statistics

    Example:
        Get social and power relationships for context:
        >>> context = neo4j_get_entity_relationship_context(
        ...     entity_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        ...     include_categories=[RelationshipCategory.SOCIAL, RelationshipCategory.POWER]
        ... )
    """
    client = get_neo4j_client()

    # Build category filter
    category_filter = ""
    if include_categories:
        category_filter = "AND r.category IN $categories"

    # Build query to get relationships within distance
    query = f"""
    MATCH path = (e:Entity {{id: $entity_id}})-[*1..{max_distance}]-(other:Entity)
    UNWIND relationships(path) as r
    MATCH (from)-[r]->(to)
    WHERE r.category IS NOT NULL {category_filter}
    RETURN id(r) as rel_id, from.id as from_id, to.id as to_id,
           type(r) as rel_type, r.category as category, r.subcategory as subcategory,
           r.tags as tags, properties(r) as props,
           length([p IN [(e)-[*1..{max_distance}]-(other) WHERE (e)-[*1..{max_distance}]-(other) | p]
                  WHERE (e)-[*]->(other) IN path]) as distance
    ORDER BY distance, id(r)
    LIMIT $limit
    """

    # Calculate approximate limit based on max_distance
    total_limit = limit_per_entity * max_distance * 10  # Heuristic

    params = {
        "entity_id": str(entity_id),
        "limit": total_limit,
    }

    if include_categories:
        params["categories"] = [cat.value for cat in include_categories]

    result = client.execute_read(query, params)

    # Organize results
    categories: dict[str, list[RelationshipResponse]] = {}
    by_entity: dict[str, list[RelationshipResponse]] = {}
    by_category_stats: dict[str, int] = {}
    unique_entities_set: set[str] = set()
    stats: dict[str, Any] = {
        "total_relationships": len(result),
        "by_category": by_category_stats,
        "unique_entities": unique_entities_set,
    }

    for rel in result:
        props = rel["props"] or {}

        # Extract category and subcategory
        category_str = rel.get("category") or props.get("category")
        subcategory_str = rel.get("subcategory") or props.get("subcategory")
        tags = rel.get("tags") or props.get("tags", [])

        # Parse category and subcategory
        rel_category = RelationshipCategory(category_str) if category_str else RelationshipCategory.GENERIC
        rel_subcategory = RelationshipSubcategory(subcategory_str) if subcategory_str else None

        relationship = RelationshipResponse(
            relationship_id=str(rel["rel_id"]),
            from_entity_id=UUID(rel["from_id"]),
            to_entity_id=UUID(rel["to_id"]),
            rel_type=RelationshipType(rel["rel_type"]),
            category=rel_category,
            subcategory=rel_subcategory,
            tags=tags,
            properties=props,
            created_at=(datetime.fromisoformat(str(props.get("created_at"))) if props.get("created_at") else None),
        )

        # Organize by category
        cat_key = rel_category.value
        if cat_key not in categories:
            categories[cat_key] = []
        categories[cat_key].append(relationship)
        by_category_stats[cat_key] = by_category_stats.get(cat_key, 0) + 1

        # Organize by entity (both from and to)
        for entity_key in [str(rel["from_id"]), str(rel["to_id"])]:
            if entity_key != str(entity_id):
                if entity_key not in by_entity:
                    by_entity[entity_key] = []
                by_entity[entity_key].append(relationship)
                unique_entities_set.add(entity_key)

    stats["unique_entities"] = list(unique_entities_set)
    stats["total_unique_entities"] = len(unique_entities_set)

    return {
        "entity_id": str(entity_id),
        "categories": categories,
        "by_entity": by_entity,
        "stats": stats,
    }
