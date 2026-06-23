"""Helpers for query-aware traversal masks and relationship ranking.

Phase 4 introduces a lightweight traversal layer in agents that steers graph
reads toward intent-relevant relationship families before final summarization.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any, Dict, Iterable, List, Mapping, Optional


INTENT_RELATION_BUNDLES: Dict[str, List[str]] = {
    "social": [
        "KNOWS",
        "ALLIED_WITH",
        "WORKS_FOR",
        "TRUSTS",
        "DISTRUSTS",
        "INDEBTED_TO",
        "HOSTILE_TO",
    ],
    "spatial": ["LOCATED_IN", "CONTAINS", "OWNS", "CONTROLLED_BY", "CONTROLS"],
    "causal": ["PARTICIPATES_IN", "RELATED_TO", "MEMBER_OF", "AFFILIATED_WITH"],
    "rules": ["INSTANCE_OF", "SUBTYPE_OF", "PARTICIPATES_IN", "RELATED_TO"],
    "general": ["RELATED_TO", "KNOWS", "LOCATED_IN", "PARTICIPATES_IN"],
}


def infer_intent_family(player_action: str) -> str:
    """Infer a coarse traversal intent family from the user action string."""
    action = (player_action or "").strip().lower()
    if not action:
        return "general"

    social_terms = ("ask", "tell", "convince", "persuade", "negotiate", "threaten", "ally")
    spatial_terms = ("where", "locate", "find", "inside", "travel", "move", "route")
    causal_terms = ("why", "because", "caused", "trigger", "consequence", "result")
    rules_terms = ("rule", "roll", "dc", "difficulty", "check", "mechanic")

    if any(term in action for term in social_terms):
        return "social"
    if any(term in action for term in spatial_terms):
        return "spatial"
    if any(term in action for term in causal_terms):
        return "causal"
    if any(term in action for term in rules_terms):
        return "rules"
    return "general"


def build_traversal_mask(
    *,
    player_action: str,
    source_scope: Optional[Mapping[str, Any]],
    seed_entity_ids: Iterable[str],
) -> Dict[str, Any]:
    """Create a lightweight traversal mask for graph candidate collection."""
    intent_family = infer_intent_family(player_action)
    preferred = INTENT_RELATION_BUNDLES.get(intent_family, INTENT_RELATION_BUNDLES["general"])
    categories = list((source_scope or {}).get("preferred_semantic_categories") or [])

    return {
        "intent_family": intent_family,
        "preferred_rel_types": preferred,
        "allowed_rel_types": preferred
        if intent_family != "general"
        else INTENT_RELATION_BUNDLES["general"],
        "seed_entity_ids": [
            str(entity_id) for entity_id in seed_entity_ids if str(entity_id).strip()
        ],
        "source_categories": categories,
        "hop_limit": 2,
    }


def score_candidate_relationship(
    relationship: Mapping[str, Any],
    *,
    preferred_rel_types: Iterable[str],
) -> float:
    """Score a relationship candidate based on type preference and metadata."""
    preferred = {item.upper() for item in preferred_rel_types}
    rel_type = str(relationship.get("rel_type") or "").upper()
    score = 0.0

    if rel_type in preferred:
        score += 1.0
    elif rel_type:
        score += 0.2

    props = relationship.get("properties") or {}
    with suppress(TypeError, ValueError):
        score += min(float(props.get("strength", 0.0) or 0.0) * 0.1, 0.6)

    return score


def get_counterpart_entity_id(
    relationship: Mapping[str, Any],
    *,
    anchor_entity_id: str,
) -> Optional[str]:
    """Return the opposite endpoint of a relationship relative to an anchor entity."""
    anchor = str(anchor_entity_id)
    from_id = str(relationship.get("from_entity_id") or "")
    to_id = str(relationship.get("to_entity_id") or "")
    if from_id == anchor and to_id:
        return to_id
    if to_id == anchor and from_id:
        return from_id
    return None


def collect_traversal_query_terms(
    candidates: Iterable[Mapping[str, Any]],
    *,
    limit: int = 10,
) -> List[str]:
    """Extract compact lexical terms from traversal candidates for query enrichment."""
    terms: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        for value in (
            candidate.get("counterpart_name"),
            candidate.get("rel_type"),
            candidate.get("anchor_name"),
        ):
            text = str(value or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(text)
            if len(terms) >= limit:
                return terms
    return terms
