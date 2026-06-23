"""Helpers for source-scope routing during runtime retrieval.

These functions build a lightweight scope object from the active source profile
and player action, then use that scope to enrich queries and rerank snippets.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from monitor_agents.utils.runtime_profile_support import normalize_source_profile


_CATEGORY_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "combat_rules": ("attack", "combat", "fight", "strike", "damage", "weapon"),
    "social_moral": ("ask", "persuade", "convince", "threaten", "negotiate", "promise"),
    "power_system": ("spell", "magic", "discipline", "power", "ritual", "cast"),
    "items_equipment": ("item", "gear", "weapon", "armor", "tool", "inventory"),
    "factions": ("faction", "clan", "guild", "order", "house", "crew"),
    "lore_history": ("history", "origin", "legend", "past", "ancient"),
    "creatures_npc": ("npc", "creature", "monster", "beast", "character"),
    "game_mechanics": ("rule", "roll", "difficulty", "dc", "modifier", "check"),
}


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else [value]
    items: List[str] = []
    seen: set[str] = set()
    for entry in raw:
        text = str(entry).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append(text)
    return items


def _dedupe(values: Iterable[str], *, limit: int) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def derive_source_scope(
    player_action: str,
    source_profile: Any,
    *,
    max_terms: int = 12,
    max_categories: int = 4,
) -> Dict[str, Any]:
    """Build a lightweight source scope from action + profile metadata."""
    normalized = normalize_source_profile(source_profile)
    action = (player_action or "").strip().lower()

    categories: List[str] = []
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in action for keyword in keywords):
            categories.append(category)

    if not categories:
        categories = ["general"]
    categories = _dedupe(categories, limit=max_categories)

    term_candidates: List[str] = []
    for field in (
        "canon_signal_terms",
        "taxonomy_containers",
        "important_named_sets",
        "lore_domains",
    ):
        term_candidates.extend(_as_list(normalized.get(field)))

    terms = _dedupe(term_candidates, limit=max_terms)

    return {
        "system_name": normalized.get("system_name") if isinstance(normalized, Mapping) else None,
        "preferred_semantic_categories": categories,
        "preferred_terms": terms,
    }


def append_scope_terms_to_query(query: str, scope: Mapping[str, Any], *, limit: int = 6) -> str:
    """Append high-value scope terms to a query string for retrieval routing."""
    base = (query or "").strip()
    terms = _as_list(scope.get("preferred_terms"))[:limit]
    if not terms:
        return base
    if not base:
        return " ".join(terms)
    return f"{base} {' '.join(terms)}".strip()


def rank_snippets_with_source_scope(
    snippets: List[Dict[str, Any]],
    *,
    scope: Mapping[str, Any],
    player_action: str,
) -> List[Dict[str, Any]]:
    """Rerank snippets using source-scope category and vocabulary signals."""
    if not snippets:
        return snippets

    preferred_categories = {
        value.lower() for value in _as_list(scope.get("preferred_semantic_categories")) if value
    }
    preferred_terms = [value.lower() for value in _as_list(scope.get("preferred_terms"))]
    expected_system = str(scope.get("system_name") or "").strip().lower()
    if not preferred_categories and not preferred_terms and not expected_system:
        return snippets
    action = (player_action or "").strip().lower()

    rescored: List[tuple[float, int, Dict[str, Any]]] = []
    for index, snippet in enumerate(snippets):
        score = float(snippet.get("score", 0.0) or 0.0)

        category = str(snippet.get("semantic_category") or "").strip().lower()
        if category and category in preferred_categories:
            score += 0.75

        snippet_system = str(snippet.get("source_system_name") or "").strip().lower()
        if expected_system and snippet_system and snippet_system == expected_system:
            score += 0.45

        text_blob = " ".join(
            str(snippet.get(field, ""))
            for field in (
                "text",
                "document",
                "content",
                "summary",
                "source_name",
                "section_summary",
            )
        ).lower()

        term_hits = sum(1 for term in preferred_terms if term and term in text_blob)
        if term_hits:
            score += min(0.2 * term_hits, 0.8)
        if action and action in text_blob:
            score += 0.2

        rescored.append((score, -index, snippet))

    rescored.sort(reverse=True)
    return [snippet for _, _, snippet in rescored]
