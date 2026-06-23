"""Pure helpers for applying embedded source profiles during runtime retrieval.

These helpers keep `context_assembly.py` focused on orchestration while the
profile-aware query expansion and snippet ranking logic lives in one small,
reusable place.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


def _as_list(value: Any) -> List[str]:
    """Normalize list-ish values into a clean list of strings."""
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]

    items: List[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text)
    return items


def _dedupe_terms(values: Iterable[str], *, limit: int | None = None) -> List[str]:
    """Deduplicate terms case-insensitively while preserving the first casing."""
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def normalize_source_profile(profile: Any) -> Dict[str, Any]:
    """Convert a profile model or dict into a plain JSON-like dict."""
    if profile is None:
        return {}
    if hasattr(profile, "model_dump"):
        try:
            profile = profile.model_dump(mode="json")
        except Exception:  # noqa: BLE001
            return {}
    if not isinstance(profile, Mapping):
        return {}

    normalized = dict(profile)
    for field in (
        "genre_tone",
        "narrative_frame",
        "lore_domains",
        "taxonomy_containers",
        "institution_model",
        "relationship_patterns",
        "canon_signal_terms",
        "important_named_sets",
        "known_open_questions",
    ):
        normalized[field] = _as_list(normalized.get(field))

    for dict_field in ("term_lexicon", "aliases"):
        raw_mapping = normalized.get(dict_field)
        if not isinstance(raw_mapping, Mapping):
            normalized[dict_field] = {}
            continue
        normalized[dict_field] = {
            str(key).strip(): _as_list(values)
            for key, values in raw_mapping.items()
            if str(key).strip()
        }

    return normalized


def _collect_profile_terms(
    query: str, player_action: str, profile: Mapping[str, Any], *, limit: int = 12
) -> List[str]:
    """Collect the most relevant profile terms for the current action/query."""
    haystack = f"{query} {player_action}".lower()
    expansions: List[str] = []

    for dict_field in ("term_lexicon", "aliases"):
        mapping = profile.get(dict_field, {})
        if not isinstance(mapping, Mapping):
            continue
        for canon, values in mapping.items():
            canon_text = str(canon).strip()
            alias_values = _as_list(values)
            if not canon_text:
                continue
            candidates = [canon_text, *alias_values]
            if any(candidate.lower() in haystack for candidate in candidates):
                expansions.extend(candidates)

    for field in ("canon_signal_terms", "taxonomy_containers", "important_named_sets"):
        expansions.extend(term for term in _as_list(profile.get(field)) if term.lower() in haystack)

    if not expansions:
        expansions.extend(_as_list(profile.get("taxonomy_containers"))[:2])
        expansions.extend(_as_list(profile.get("canon_signal_terms"))[:2])

    return _dedupe_terms(expansions, limit=limit)


def expand_query_with_profile(
    query: str, player_action: str, profile: Any, *, limit: int = 12
) -> str:
    """Expand a retrieval query using high-value profile lexicon and aliases."""
    base_query = (query or "").strip()
    if not base_query:
        return ""

    normalized = normalize_source_profile(profile)
    if not normalized:
        return base_query

    extra_terms = _collect_profile_terms(base_query, player_action, normalized, limit=limit)
    if not extra_terms:
        return base_query
    return f"{base_query} {' '.join(extra_terms)}".strip()


def build_profile_context(profile: Any, *, min_confidence: float = 0.75) -> str:
    """Render only the high-confidence runtime profile hints needed for prompt injection."""
    normalized = normalize_source_profile(profile)
    if not normalized:
        return ""

    confidence = normalized.get("confidence_by_field") or {}

    def include(field: str, value: Any) -> bool:
        if value in (None, "", [], {}):
            return False
        if field not in confidence:
            return True
        try:
            return float(confidence.get(field, 0.0)) >= min_confidence
        except (TypeError, ValueError):
            return False

    lines: List[str] = []
    if include("system_name", normalized.get("system_name")):
        lines.append(f"System: {normalized['system_name']}")
    if include("world_kind", normalized.get("world_kind")):
        lines.append(f"World kind: {normalized['world_kind']}")
    if include("lore_domains", normalized.get("lore_domains")):
        lines.append(f"Lore domains: {', '.join(normalized['lore_domains'][:6])}")
    if include("taxonomy_containers", normalized.get("taxonomy_containers")):
        lines.append(f"Taxonomy containers: {', '.join(normalized['taxonomy_containers'][:8])}")
    if include("institution_model", normalized.get("institution_model")):
        lines.append(f"Institution model: {', '.join(normalized['institution_model'][:6])}")
    if include("relationship_patterns", normalized.get("relationship_patterns")):
        lines.append(f"Relationship patterns: {', '.join(normalized['relationship_patterns'][:8])}")
    if include("canon_signal_terms", normalized.get("canon_signal_terms")):
        lines.append(f"Canon signal terms: {', '.join(normalized['canon_signal_terms'][:10])}")
    if include("term_lexicon", normalized.get("term_lexicon")):
        pairs = [
            f"{term}=>{', '.join(values[:3])}"
            for term, values in list(normalized["term_lexicon"].items())[:6]
            if values
        ]
        if pairs:
            lines.append(f"Lexicon aliases: {'; '.join(pairs)}")
    return "\n".join(lines)


def build_narrative_profile_context(profile: Any, *, min_confidence: float = 0.65) -> str:
    """Render narrative-facing profile hints for the narrator prompt."""
    normalized = normalize_source_profile(profile)
    if not normalized:
        return ""

    confidence = normalized.get("confidence_by_field") or {}

    def include(field: str, value: Any) -> bool:
        if value in (None, "", [], {}):
            return False
        if field not in confidence:
            return True
        try:
            return float(confidence.get(field, 0.0)) >= min_confidence
        except (TypeError, ValueError):
            return False

    lines: List[str] = []
    if include("genre_tone", normalized.get("genre_tone")):
        lines.append(f"Genre tone: {', '.join(normalized['genre_tone'][:6])}")
    if include("narrative_frame", normalized.get("narrative_frame")):
        lines.append(f"Narrative frame: {', '.join(normalized['narrative_frame'][:6])}")
    if include("institution_model", normalized.get("institution_model")):
        lines.append(f"Institution model: {', '.join(normalized['institution_model'][:6])}")
    if include("canon_signal_terms", normalized.get("canon_signal_terms")):
        lines.append(
            f"Forms of address / signal terms: {', '.join(normalized['canon_signal_terms'][:10])}"
        )
    if include("term_lexicon", normalized.get("term_lexicon")):
        pairs = [
            f"{term}=>{', '.join(values[:3])}"
            for term, values in list(normalized["term_lexicon"].items())[:6]
            if values
        ]
        if pairs:
            lines.append(f"Use native vocabulary: {'; '.join(pairs)}")
    return "\n".join(lines)


def build_tone_hints_from_profile(profile: Any, *, min_confidence: float = 0.65) -> str:
    """Return a compact prose-style tone hint string derived from the source profile."""
    normalized = normalize_source_profile(profile)
    if not normalized:
        return ""

    confidence = normalized.get("confidence_by_field") or {}

    def include(field: str, value: Any) -> bool:
        if value in (None, "", [], {}):
            return False
        if field not in confidence:
            return True
        try:
            return float(confidence.get(field, 0.0)) >= min_confidence
        except (TypeError, ValueError):
            return False

    parts: List[str] = []
    if include("genre_tone", normalized.get("genre_tone")):
        parts.append(f"Lean into {', '.join(normalized['genre_tone'][:4])}.")
    if include("narrative_frame", normalized.get("narrative_frame")):
        parts.append(
            f"Frame scenes through {', '.join(normalized['narrative_frame'][:4])} pressures."
        )
    if include("institution_model", normalized.get("institution_model")):
        parts.append(f"Social power runs through {', '.join(normalized['institution_model'][:4])}.")
    return " ".join(parts)


def build_npc_profile_context(
    profile: Any,
    *,
    npc_name: str = "",
    npc_role: str = "",
    npc_facts: Iterable[str] | None = None,
    min_confidence: float = 0.65,
) -> str:
    """Render bounded cultural vocabulary and social cues for NPC dialogue prompts."""
    normalized = normalize_source_profile(profile)
    if not normalized:
        return ""

    confidence = normalized.get("confidence_by_field") or {}

    def include(field: str, value: Any) -> bool:
        if value in (None, "", [], {}):
            return False
        if field not in confidence:
            return True
        try:
            return float(confidence.get(field, 0.0)) >= min_confidence
        except (TypeError, ValueError):
            return False

    haystack = " ".join([npc_name, npc_role, *[str(f) for f in (npc_facts or [])]]).lower()
    lines: List[str] = []

    if include("genre_tone", normalized.get("genre_tone")):
        lines.append(f"Dialogue tone: {', '.join(normalized['genre_tone'][:4])}")
    if include("institution_model", normalized.get("institution_model")):
        lines.append(f"Social order: {', '.join(normalized['institution_model'][:6])}")
    if include("canon_signal_terms", normalized.get("canon_signal_terms")):
        lines.append(
            f"Forms of address / rank terms: {', '.join(normalized['canon_signal_terms'][:8])}"
        )

    named_sets = _as_list(normalized.get("important_named_sets"))
    if include("important_named_sets", named_sets):
        relevant_sets = [name for name in named_sets if name.lower() in haystack][:4] or named_sets[
            :4
        ]
        if relevant_sets:
            lines.append(f"Relevant factions or groups: {', '.join(relevant_sets)}")

    if include("term_lexicon", normalized.get("term_lexicon")):
        relevant_pairs: List[str] = []
        for term, values in list(normalized.get("term_lexicon", {}).items()):
            candidates = [term, *values]
            if haystack and any(candidate.lower() in haystack for candidate in candidates):
                relevant_pairs.append(f"{term}=>{', '.join(values[:3])}")
        if not relevant_pairs:
            relevant_pairs = [
                f"{term}=>{', '.join(values[:3])}"
                for term, values in list(normalized.get("term_lexicon", {}).items())[:4]
                if values
            ]
        if relevant_pairs:
            lines.append(f"Setting-native vocabulary: {'; '.join(relevant_pairs[:4])}")

    return "\n".join(lines)


def rank_snippets_with_profile(
    snippets: List[Dict[str, Any]],
    *,
    player_action: str,
    profile: Any,
) -> List[Dict[str, Any]]:
    """Boost snippets that use profile-relevant vocabulary for the current action."""
    normalized = normalize_source_profile(profile)
    if not snippets or not normalized:
        return snippets

    relevant_terms = [
        term.lower()
        for term in _collect_profile_terms(player_action, player_action, normalized, limit=16)
    ]
    if not relevant_terms:
        return snippets

    rescored: List[tuple[float, int, Dict[str, Any]]] = []
    for index, snippet in enumerate(snippets):
        base_score = float(snippet.get("score", 0.0) or 0.0)
        text_blob = " ".join(
            str(snippet.get(field, ""))
            for field in ("text", "document", "content", "snippet", "summary")
        ).lower()

        matched_terms = sum(1 for term in relevant_terms if term and term in text_blob)
        boost = min(matched_terms * 0.4, 1.0)
        rescored.append((base_score + boost, -index, snippet))

    rescored.sort(reverse=True)
    return [snippet for _, _, snippet in rescored]
