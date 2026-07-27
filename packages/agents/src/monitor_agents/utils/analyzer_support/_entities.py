"""Entity merging, alias building, and relationship normalization functions."""

from __future__ import annotations

import re
from typing import Any

from monitor_data.schemas.knowledge_packs import (
    ExtractedEntityArchetype,
    ExtractedRelationship,
)

from monitor_agents.utils.analyzer_support._constants import CONTAINER_TYPE_HINTS

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _best_description(desc_a: str | None, desc_b: str | None) -> str:
    """Return the richer of two descriptions rather than concatenating them."""
    if not desc_a and not desc_b:
        return ""
    if not desc_a:
        return (desc_b or "").strip()
    if not desc_b:
        return desc_a.strip()

    def _clean(d: str) -> str:
        if " | " in d:
            return max(d.split(" | "), key=len).strip()
        return d.strip()

    a = _clean(desc_a)
    b = _clean(desc_b)
    return a if len(a) >= len(b) else b


# ---------------------------------------------------------------------------
# Entity merging
# ---------------------------------------------------------------------------


def merge_entity_archetypes(
    entities: list[ExtractedEntityArchetype],
) -> list[ExtractedEntityArchetype]:
    """Merge duplicate entity names while preserving the richest combined record."""
    merged: dict[str, ExtractedEntityArchetype] = {}
    alias_index: dict[str, str] = {}

    def _register_aliases(entity: ExtractedEntityArchetype, canon_key: str) -> None:
        alias_index[canon_key] = canon_key
        for alias in getattr(entity, "aliases", []):
            alias_index[alias.lower().strip()] = canon_key

    def _merge_into(base: ExtractedEntityArchetype, incoming: ExtractedEntityArchetype) -> ExtractedEntityArchetype:
        combined_props = {**incoming.properties, **base.properties}
        combined_tags = list(base.tags)
        for tag in incoming.tags:
            if tag not in combined_tags:
                combined_tags.append(tag)
        return base.model_copy(
            update={
                "properties": combined_props,
                "description": _best_description(base.description, incoming.description),
                "tags": combined_tags,
                "confidence": max(base.confidence, incoming.confidence),
                "source_ref": base.source_ref or incoming.source_ref,
                "parent_entity_name": base.parent_entity_name or incoming.parent_entity_name,
                "sub_type": base.sub_type or incoming.sub_type,
            }
        )

    for entity in entities:
        key = entity.name.lower().strip()

        existing_canon = alias_index.get(key)
        if existing_canon is not None and existing_canon in merged:
            merged[existing_canon] = _merge_into(merged[existing_canon], entity)
            for alias in getattr(entity, "aliases", []):
                alias_key = alias.lower().strip()
                if alias_key not in alias_index:
                    alias_index[alias_key] = existing_canon
            continue

        absorbed = False
        for alias in getattr(entity, "aliases", []):
            alias_key = alias.lower().strip()
            existing_canon = alias_index.get(alias_key)
            if existing_canon is not None and existing_canon in merged:
                merged[existing_canon] = _merge_into(merged[existing_canon], entity)
                if key not in alias_index:
                    alias_index[key] = existing_canon
                absorbed = True
                break

        if absorbed:
            continue

        merged[key] = entity
        _register_aliases(entity, key)

    return list(merged.values())


def build_alias_map(
    entities: list[ExtractedEntityArchetype],
) -> dict[str, str]:
    """Return a lowercased alias→canonical-name lookup for relationship normalization."""
    alias_map: dict[str, str] = {}
    for entity in entities:
        canon = entity.name
        alias_map[canon.lower().strip()] = canon
        for alias in getattr(entity, "aliases", []):
            alias_key = alias.lower().strip()
            if alias_key not in alias_map:
                alias_map[alias_key] = canon
    return alias_map


def normalize_relationship_refs(
    relationships: list[ExtractedRelationship],
    alias_map: dict[str, str],
) -> list[ExtractedRelationship]:
    """Rewrite from_entity/to_entity through the alias map."""
    normalized: list[ExtractedRelationship] = []
    for rel in relationships:
        from_canon = alias_map.get(rel.from_entity.lower().strip(), rel.from_entity)
        to_canon = alias_map.get(rel.to_entity.lower().strip(), rel.to_entity)
        if from_canon == rel.from_entity and to_canon == rel.to_entity:
            normalized.append(rel)
        else:
            normalized.append(
                rel.model_copy(
                    update={
                        "from_entity": from_canon,
                        "to_entity": to_canon,
                    }
                )
            )
    return normalized


def infer_container_entity_type(
    parent_name: str,
    child_entities: list[ExtractedEntityArchetype],
) -> str:
    """Infer a stable entity_type for a synthesized container/category entity."""
    lowered = parent_name.lower().strip()
    for token, entity_type in CONTAINER_TYPE_HINTS:
        if token in lowered:
            return entity_type

    counts: dict[str, int] = {}
    for child in child_entities:
        counts[child.entity_type] = counts.get(child.entity_type, 0) + 1
    if counts:
        return max(counts.items(), key=lambda item: item[1])[0]
    return "concept"


def split_semantic_values(raw: Any) -> list[str]:
    """Split a compact property value into distinct named references."""
    if raw is None:
        return []

    if isinstance(raw, list):
        candidates = [str(item) for item in raw]
    else:
        text = str(raw).strip()
        if not text:
            return []
        text = re.sub(r"\([^)]*\)", "", text)
        candidates = re.split(r"\s*[,/;+]\s*", text)

    _SENTENCE_STARTERS = frozenset(
        [
            "not",
            "as",
            "but",
            "and",
            "or",
            "in",
            "of",
            "when",
            "while",
            "if",
            "the",
            "a",
            "an",
            "they",
            "who",
            "which",
            "because",
            "often",
            "always",
            "however",
            "although",
            "despite",
            "unlike",
            "known",
        ]
    )
    # English sentence-internal glue words — morphology, not a gameplay decision.
    # See ``docs/architecture/DE_HEURISTIC_PRINCIPLE.md`` — stop-lists are a
    # different tool from gameplay heuristics and stay.
    _INTERIOR_VERBS = frozenset(
        [
            "are",
            "is",
            "was",
            "were",
            "has",
            "have",
            "had",
            "often",
            "always",
            "does",
            "did",
            "can",
            "could",
            "should",
            "would",
            "belongs",
            "considers",
            "maintains",
            "calls",
            "refers",
            "serves",
            "acts",
            "includes",
            "provides",
            "requires",
            "allows",
            "uses",
        ]
    )

    values: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = candidate.strip(" -\t").replace("\u00ad", "")
        lowered = cleaned.lower()
        if not cleaned or lowered in {"none", "n/a", "na", "unknown", "varies", "various"}:
            continue
        if len(cleaned) > 60:
            continue
        words = lowered.split()
        first_word = words[0] if words else ""
        if first_word in _SENTENCE_STARTERS:
            continue
        if len(words) > 2 and any(w in _INTERIOR_VERBS for w in words[1:]):
            continue
        if any(ch in cleaned for ch in (".", "!", "?", ":")):
            continue
        if lowered not in seen:
            seen.add(lowered)
            values.append(cleaned)
    return values
