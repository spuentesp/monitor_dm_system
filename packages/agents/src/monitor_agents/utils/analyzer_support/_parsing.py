"""Parsing utilities for source profile JSON and section classification output."""

from __future__ import annotations

import json
import re
from typing import Any

from monitor_data.schemas.knowledge_packs import EmbeddedSourceProfile

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_str_list(value: Any) -> list[str]:
    """Normalize list-ish JSON values into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = re.split(r",|;|\n", value)
    else:
        raw_items = [value]
    items = [str(item).strip() for item in raw_items if str(item).strip()]
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _parse_alias_dict(value: Any) -> dict[str, list[str]]:
    """Normalize JSON alias maps into Dict[str, List[str]]."""
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for key, raw_values in value.items():
        clean_key = str(key).strip()
        if not clean_key:
            continue
        parsed_values = _parse_str_list(raw_values)
        if parsed_values:
            normalized[clean_key] = parsed_values
    return normalized


# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------


def parse_source_profile(profile_text: str) -> EmbeddedSourceProfile | None:
    """Parse a structured source-profile JSON payload from DSPy output."""
    if not profile_text or not profile_text.strip():
        return None

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", profile_text, re.DOTALL)
    candidate = fenced.group(1) if fenced else profile_text.strip()
    if not fenced and "{" in candidate and "}" in candidate:
        candidate = candidate[candidate.find("{") : candidate.rfind("}") + 1]

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    normalized = dict(payload)
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
        normalized[field] = _parse_str_list(payload.get(field))

    normalized["term_lexicon"] = _parse_alias_dict(payload.get("term_lexicon"))
    normalized["aliases"] = _parse_alias_dict(payload.get("aliases"))

    raw_refs = payload.get("evidence_refs") or []
    normalized["evidence_refs"] = [
        {"ref": ref} if isinstance(ref, str) else ref
        for ref in raw_refs
        if isinstance(ref, str) or (isinstance(ref, dict) and ref.get("ref"))
    ]

    normalized.setdefault("profile_type", "source")
    normalized.setdefault("source_kind", "mixed")

    try:
        return EmbeddedSourceProfile(**normalized)
    except Exception:
        return None


def parse_section_classifications(reasoning: str) -> dict[int, str]:
    """Parse SECTION | <num> | <classification> | <reason> lines."""
    valid = {"game_content", "metadata", "index", "front_matter"}
    result: dict[int, str] = {}
    for line in reasoning.splitlines():
        line = line.strip()
        if not line.upper().startswith("SECTION"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        try:
            num = int(parts[1])
            classification = parts[2].lower().strip()
            if classification in valid:
                result[num] = classification
        except (ValueError, IndexError):
            continue
    return result
