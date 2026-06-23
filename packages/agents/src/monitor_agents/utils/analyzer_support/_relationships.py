"""Relationship deduplication and graph snapshot building."""

from __future__ import annotations

from typing import Dict, List

from monitor_data.schemas.knowledge_packs import (
    ExtractedEntityArchetype,
    ExtractedRelationship,
)


def dedupe_relationships(
    relationships: List[ExtractedRelationship],
) -> List[ExtractedRelationship]:
    """Remove duplicate relationships while preserving first-seen order."""
    deduped: List[ExtractedRelationship] = []
    seen: set[str] = set()
    for relationship in relationships:
        key = (
            f"{relationship.from_entity.lower().strip()}|"
            f"{relationship.rel_type.lower().strip()}|"
            f"{relationship.to_entity.lower().strip()}"
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(relationship)
    return deduped


def build_graph_snapshot(
    entities: Dict[str, ExtractedEntityArchetype],
    relationships: List[ExtractedRelationship],
    *,
    max_nodes: int = 40,
    max_edges: int = 30,
) -> str:
    """Build a compact Cypher-style snapshot of the known extracted graph."""
    if not entities:
        return ""

    node_parts: List[str] = []
    for entity in list(entities.values())[:max_nodes]:
        details: List[str] = []
        if entity.parent_entity_name:
            details.append(f"parent={entity.parent_entity_name}")
        if getattr(entity, "entity_roles", None):
            details.append(f"roles={'+'.join(entity.entity_roles[:4])}")
        suffix = f"[{';'.join(details)}]" if details else ""
        node_parts.append(f"{entity.name}:{entity.entity_type}{suffix}")
    nodes_line = ", ".join(node_parts)

    edge_strs: list[str] = []
    seen_edges: set[str] = set()

    def _add_edge(frm: str, rel: str, to: str) -> None:
        key = f"{frm.lower()}|{rel}|{to.lower()}"
        if key not in seen_edges and len(edge_strs) < max_edges:
            seen_edges.add(key)
            edge_strs.append(f"({frm})-[:{rel}]->({to})")

    for entity in entities.values():
        if entity.parent_entity_name:
            _add_edge(entity.name, "subtype_of", entity.parent_entity_name)

    for relationship in relationships:
        _add_edge(relationship.from_entity, relationship.rel_type, relationship.to_entity)

    lines = [f"Entities: {nodes_line}"]
    if edge_strs:
        lines.append("Structure:\n" + "\n".join(edge_strs))
    return "\n".join(lines)
