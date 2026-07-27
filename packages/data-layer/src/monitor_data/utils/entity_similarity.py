"""
Entity similarity detection for merge candidate identification (I-13).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (rapidfuzz, re)
CALLED BY: mongodb_tools/entities.py, agents/merger_agent.py

Provides string similarity metrics and entity comparison functions
for detecting potential duplicate entities across sources.
"""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz.distance import JaroWinkler, Levenshtein

# =============================================================================
# STRING SIMILARITY METRICS
# =============================================================================


def _normalize(s: str) -> str:
    """Normalize string for comparison: lowercase, strip, collapse spaces."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.lower().strip())


def jaro_winkler_similarity(s1: str, s2: str) -> float:
    """
    Compute Jaro-Winkler similarity between two strings.

    Returns a float in [0.0, 1.0] where 1.0 means identical.
    Gives more weight to matching prefixes (first 4 chars).

    Uses rapidfuzz (C++ backend) for ~50x speedup over pure Python.
    """
    if not s1 or not s2:
        return 0.0

    s1_norm, s2_norm = _normalize(s1), _normalize(s2)

    if s1_norm == s2_norm:
        return 1.0

    return JaroWinkler.normalized_similarity(s1_norm, s2_norm)


def levenshtein_ratio(s1: str, s2: str) -> float:
    """
    Compute normalized Levenshtein similarity ratio.

    Returns a float in [0.0, 1.0] where 1.0 means identical.

    Uses rapidfuzz (C++ backend) for ~50x speedup over difflib.
    """
    if not s1 or not s2:
        return 0.0

    s1_norm, s2_norm = _normalize(s1), _normalize(s2)

    if s1_norm == s2_norm:
        return 1.0

    return Levenshtein.normalized_similarity(s1_norm, s2_norm)


def name_similarity(name1: str, name2: str) -> float:
    """
    Compute comprehensive name similarity score.

    Uses multiple metrics and returns the maximum to catch:
    - Exact matches (fuzzy: "Gandalf" ≈ "Gandalf")
    - Nicknames ("Gandalf" ≈ "Mithrandir")
    - Partial matches ("Gandalf the Grey" ≈ "Gandalf")
    - Typos ("Gandalf" ≈ "Gandolf")

    Returns the max of Jaro-Winkler and Levenshtein for robustness.
    """
    jw = jaro_winkler_similarity(name1, name2)
    lv = levenshtein_ratio(name1, name2)

    # Boost if one name is a substring of the other
    n1, n2 = _normalize(name1), _normalize(name2)
    if n1 in n2 or n2 in n1:
        substring_boost = 0.1
        return min(1.0, max(jw, lv) + substring_boost)

    return max(jw, lv)


# =============================================================================
# ENTITY COMPARISON
# =============================================================================


def compare_entity_fields(
    entity1: dict[str, Any],
    entity2: dict[str, Any],
) -> tuple[list[str], list[str], dict[str, float]]:
    """
    Compare two entity dictionaries and find conflicting vs agreed fields.

    Args:
        entity1: First entity as dict (typically from KnowledgePack.entity_archetypes)
        entity2: Second entity as dict

    Returns:
        (conflicting_fields, agreed_fields, similarity_scores)
        - conflicting_fields: list of field names with different values
        - agreed_fields: list of field names with identical values
        - similarity_scores: dict of per-field similarity scores
    """
    conflicting: list[str] = []
    agreed: list[str] = []
    scores: dict[str, float] = {}

    # Fields to compare (excluding metadata like confidence, source_ref)
    comparable_fields = ["name", "entity_type", "sub_type", "description", "properties"]

    for field in comparable_fields:
        v1 = entity1.get(field)
        v2 = entity2.get(field)

        # Handle None/missing
        if v1 is None and v2 is None:
            continue
        if v1 is None or v2 is None:
            conflicting.append(field)
            scores[field] = 0.0
            continue

        # Compare values
        if isinstance(v1, dict) and isinstance(v2, dict):
            # For properties, compute overlap ratio
            overlap = len(set(v1.keys()) & set(v2.keys()))
            total = len(set(v1.keys()) | set(v2.keys()))
            score = overlap / total if total > 0 else 0.0

            # Check if common keys have same values
            common_keys = set(v1.keys()) & set(v2.keys())
            same_value_keys = {k for k in common_keys if v1[k] == v2[k]}
            if same_value_keys == common_keys and len(common_keys) > 0:
                agreed.append(field)
            else:
                conflicting.append(field)

            scores[field] = score

        elif isinstance(v1, str) and isinstance(v2, str):
            score = levenshtein_ratio(v1, v2)
            scores[field] = score

            if v1 == v2:
                agreed.append(field)
            elif score > 0.85:
                # High similarity but not exact
                agreed.append(field)
            else:
                conflicting.append(field)
        else:
            # Other types - direct equality
            if v1 == v2:
                agreed.append(field)
            else:
                conflicting.append(field)
            scores[field] = 1.0 if v1 == v2 else 0.0

    return conflicting, agreed, scores


def compute_entity_similarity(
    entity1: dict[str, Any],
    entity2: dict[str, Any],
    name_weight: float = 0.5,
    type_weight: float = 0.2,
    prop_weight: float = 0.2,
    desc_weight: float = 0.1,
) -> dict[str, float]:
    """
    Compute overall similarity score between two entities.

    Uses weighted combination of multiple metrics:
    - name_similarity: How similar are the names
    - type_match: Do entity types match (1.0 or 0.0)
    - prop_overlap: How much property overlap exists
    - desc_similarity: How similar are descriptions

    Returns dict with 'overall' and per-component scores.
    """
    name1 = entity1.get("name", "")
    name2 = entity2.get("name", "")
    name_sim = name_similarity(name1, name2)

    type1 = entity1.get("entity_type", "")
    type2 = entity2.get("entity_type", "")
    type_match = 1.0 if type1 and type2 and type1.lower() == type2.lower() else 0.0

    _, _, field_scores = compare_entity_fields(entity1, entity2)
    prop_overlap = field_scores.get("properties", 0.0)
    desc_sim = field_scores.get("description", 0.0)

    overall = name_weight * name_sim + type_weight * type_match + prop_weight * prop_overlap + desc_weight * desc_sim

    return {
        "overall": overall,
        "name_similarity": name_sim,
        "type_match": type_match,
        "prop_overlap": prop_overlap,
        "desc_similarity": desc_sim,
    }


# =============================================================================
# MERGE CANDIDATE DETECTION
# =============================================================================


def find_merge_candidates(
    entities: list[dict[str, Any]],
    min_confidence: float = 0.7,
) -> list[dict[str, Any]]:
    """
    Find potential merge candidates from a list of entities.

    This is a O(n^2) comparison - suitable for small to medium lists.
    For large-scale detection, use vector similarity or database-level grouping.

    Args:
        entities: List of entity dicts with 'id', 'name', 'entity_type', etc.
        min_confidence: Minimum overall similarity to suggest as candidate

    Returns:
        List of candidate groups, each with 'entity_ids' and 'merge_confidence'
    """
    n = len(entities)
    if n < 2:
        return []

    candidates: list[dict[str, Any]] = []
    used_indices: set[int] = set()

    for i in range(n):
        if i in used_indices:
            continue

        entity_i = entities[i]
        best_match_idx: int | None = None
        best_score = 0.0

        for j in range(i + 1, n):
            if j in used_indices:
                continue

            entity_j = entities[j]
            score_data = compute_entity_similarity(entity_i, entity_j)

            if score_data["overall"] > best_score:
                best_score = score_data["overall"]
                best_match_idx = j

        if best_match_idx is not None and best_score >= min_confidence:
            entity_j = entities[best_match_idx]

            candidates.append(
                {
                    "entity_ids": [entity_i["id"], entity_j["id"]],
                    "merge_confidence": best_score,
                    "similarity_metrics": score_data,
                }
            )

            used_indices.add(i)
            used_indices.add(best_match_idx)

    return candidates
