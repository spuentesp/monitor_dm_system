# ruff: noqa: E402
"""Section scoring, heuristic schema extraction, and mindscape summary builders."""

from __future__ import annotations

import re
from typing import Any, cast

from monitor_data.schemas.knowledge_packs import ChunkSummaryArtifact

from monitor_agents.utils.analyzer_support._constants import (
    _EXPLICIT_ATTRIBUTE_RE,
    _PLACEHOLDER_SCHEMA_NAMES,
    _RESOURCE_HINTS,
    _SECTION_TEXT_MAX_CHARS,
    REFERENCE_SECTION_KEYWORDS,
    REFERENCE_SECTION_RE,
    SYSTEM_SCHEMA_SECTION_LIMIT,
)
from monitor_agents.utils.analyzer_support._sections import SectionDigest

# ---------------------------------------------------------------------------
# Schema-name cleaning
# ---------------------------------------------------------------------------


def _clean_schema_name(raw: str) -> str:
    cleaned = re.sub(r"\s+", " ", raw).strip(" :-\t")
    return cleaned.title()


# ---------------------------------------------------------------------------
# Section scoring
# ---------------------------------------------------------------------------


def system_section_score(section: SectionDigest) -> int:
    """Heuristically rank sections that are likely to define the system schema.

    PRE-FILTER, not a gameplay decision — see
    ``docs/architecture/DE_HEURISTIC_PRINCIPLE.md``. This runs per chunk
    during ingestion to skip chunks the LLM extractor shouldn't even see.
    Replacing the keyword list with embeddings would cost 50× more per chunk
    and degrade recall (the keyword list targets section *headings*, which are
    short, structural, and known-vocabulary — exactly what keyword filters are
    good at).
    """
    heading = (section.section_path or "").lower()
    preview = f"{heading}\n{section.text[:1200]}".lower()
    score = 0

    for keyword in REFERENCE_SECTION_KEYWORDS:
        if keyword in heading:
            score += 4
        elif keyword in preview:
            score += 2

    if REFERENCE_SECTION_RE.search(preview):
        score += 3

    if any(
        token in preview
        for token in (
            "strength",
            "dexterity",
            "wits",
            "brawn",
            "panache",
            "resolve",
            "savvy",
            "body",
            "tech",
            "skill",
            "knack",
            "discipline",
            "power",
            "arcana",
            "school",
            "resource",
            "wound",
            "stress",
            "hero point",
            "advantage",
            "ship combat",
            "duel",
            "sorcery",
            "feat",
            "edge",
            "defense rating",
            "hit points",
            "morale",
            "fuel",
        )
    ):
        score += 5

    if re.search(r"there are\s+\w+\s+abilities|there are\s+\d+\s+abilities", preview):
        score += 8
    if _EXPLICIT_ATTRIBUTE_RE.search(section.text):
        score += 12
    if re.search(r"\b1d20\s*\+\s*(?:relevant\s+)?(?:ability|stat|modifier)", preview):
        score += 8

    return score


# ---------------------------------------------------------------------------
# Section prioritization
# ---------------------------------------------------------------------------


def prioritize_schema_sections(
    sections: list[SectionDigest],
    limit: int = SYSTEM_SCHEMA_SECTION_LIMIT,
) -> list[SectionDigest]:
    """Deduplicate noisy section candidates and keep the strongest schema-defining sections."""
    if not sections:
        return []

    best_by_path: dict[str, SectionDigest] = {}
    for section in sections:
        key = (
            re.sub(r"\s+", " ", (section.section_path or "")).strip().lower()
            or f"page:{section.min_page}:{section.min_chunk_index}"
        )
        current = best_by_path.get(key)
        if current is None:
            best_by_path[key] = section
            continue

        current_key = (system_section_score(current), len(current.text or ""))
        candidate_key = (system_section_score(section), len(section.text or ""))
        if candidate_key > current_key:
            best_by_path[key] = section

    ranked = sorted(
        best_by_path.values(),
        key=lambda section: (
            -system_section_score(section),
            -len(section.text or ""),
            section.min_page,
            section.min_chunk_index,
        ),
    )
    strong = [section for section in ranked if system_section_score(section) >= 4]
    return (strong or ranked)[: max(limit, 1)]


# ---------------------------------------------------------------------------
# Named-item deduplication
# ---------------------------------------------------------------------------


def dedupe_named_items(items: list[Any]) -> list[Any]:
    """Deduplicate simple dictionaries or Pydantic objects by their case-insensitive `name` field."""
    seen: set[str] = set()
    deduped: list[Any] = []
    for item in items:
        if hasattr(item, "get"):
            name = str(item.get("name", "")).strip()
        else:
            name = str(getattr(item, "name", "")).strip()

        if not name:
            continue
        key = name.lower()
        if key in _PLACEHOLDER_SCHEMA_NAMES or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


# ---------------------------------------------------------------------------
# Heuristic character-sheet extraction
# ---------------------------------------------------------------------------


def heuristic_extract_character_sheet_sections(
    sections: list[SectionDigest],
    system_name: str,
) -> dict[str, Any]:
    """Heuristically recover explicit schema fields from raw text before/alongside the LLM pass."""
    del system_name  # currently unused but kept for future system-specific tweaks

    focus_sections = prioritize_schema_sections(sections)
    attributes: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    core_mechanic: dict[str, Any] = {}

    for section in focus_sections:
        blob = f"{section.section_path}\n{section.text}"
        blob_lower = blob.lower()

        if any(token in blob_lower for token in ("abilit", "attribute", "trait", "stat")):
            for match in _EXPLICIT_ATTRIBUTE_RE.finditer(blob):
                name = _clean_schema_name(match.group("name"))
                if name.lower() in _PLACEHOLDER_SCHEMA_NAMES:
                    continue
                attributes.append(
                    {
                        "name": name,
                        "abbreviation": match.group("abbr").strip().upper(),
                        "min_value": -3 if "roll two d4" in blob_lower or "minus the second" in blob_lower else 1,
                        "max_value": 3 if "roll two d4" in blob_lower or "minus the second" in blob_lower else 20,
                        "default_value": 0 if "roll two d4" in blob_lower or "minus the second" in blob_lower else 10,
                        "modifier_formula": None,
                    }
                )

        for pattern, resource_name, abbreviation in _RESOURCE_HINTS:
            if pattern.search(blob_lower):
                resources.append(
                    {
                        "name": resource_name,
                        "abbreviation": abbreviation,
                        "min_value": 0,
                        "recovers_on": None,
                        "depleted_effect": None,
                        "calculation": None,
                    }
                )

        if re.search(r"\b1d20\s*\+\s*(?:relevant\s+)?(?:ability|stat|modifier)", blob_lower):
            core_mechanic = {
                "type": "d20",
                "formula": "1d20 + relevant ability vs difficulty",
                "success_type": "meet_or_beat",
            }
        elif not core_mechanic and re.search(r"\broll\s+two\s+d4\b|\b2d4\b", blob_lower):
            core_mechanic = {
                "type": "d20",
                "formula": "Checks use a relevant ability; character abilities are generated by rolling two d4 and subtracting one from the other",
                "success_type": "meet_or_beat",
            }

    return {
        "attributes": dedupe_named_items(attributes),
        "skills": [],
        "resources": dedupe_named_items(resources),
        "powers": [],
        "subsystems": [],
        "conditions": [],
        "scenery_rules": [],
        "core_mechanic": core_mechanic,
        "resolution_mechanics": [],
    }


# ---------------------------------------------------------------------------
# Mindscape synthesis helpers
# ---------------------------------------------------------------------------


# Module-level reference to the MongoDB update function — can be monkeypatched in tests.
from monitor_data.tools.mongodb_tools import (
    mongodb_update_knowledge_pack as _update_knowledge_pack_fn,
)


def build_section_summary_inputs(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format sections for batch summarization."""
    result = []
    for section in sections:
        heading_path = section.get("heading_path", [])
        text = section.get("text", "")
        result.append(
            {
                "heading_path": " > ".join(heading_path) if heading_path else "(untitled)",
                "section_text": text[:_SECTION_TEXT_MAX_CHARS],
                "chunk_ids": list(section.get("chunk_ids", []) or []),
                "semantic_category": section.get("semantic_category"),
            }
        )
    return result


def _normalize_summary_text(text: str, *, limit: int = 280) -> str:
    """Collapse whitespace and keep a compact first 1-2 sentence excerpt."""
    normalized = re.sub(r"\s+", " ", (text or "")).strip()
    if not normalized:
        return ""

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
    summary = " ".join(sentences[:2]) if sentences else normalized
    if len(summary) <= limit:
        return summary

    clipped = summary[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped}..." if clipped else summary[:limit]


def build_chunk_summary_artifacts(
    sections: list[SectionDigest],
    *,
    max_chunks_per_section: int = 8,
    max_total_chunks: int = 160,
) -> list[ChunkSummaryArtifact]:
    """Create compact per-chunk summary artifacts from section provenance records."""
    artifacts: list[ChunkSummaryArtifact] = []
    seen_chunk_ids: set[str] = set()

    for section in sections:
        heading_ref = section.section_path or "General"
        for record in section.chunk_records[:max_chunks_per_section]:
            chunk_id = str(record.get("chunk_id") or "").strip()
            if not chunk_id or chunk_id in seen_chunk_ids:
                continue

            summary = _normalize_summary_text(str(record.get("text") or ""))
            if not summary:
                continue

            page = record.get("page")
            source_ref = f"{heading_ref} (p. {page})" if page else heading_ref
            semantic_category = record.get("semantic_category") or section.semantic_category
            tags = [tag for tag in [semantic_category] if tag]

            artifacts.append(
                ChunkSummaryArtifact(
                    chunk_id=chunk_id,
                    chunk_index=int(record.get("idx") or record.get("chunk_index") or 0),
                    source_ref=source_ref,
                    summary=summary,
                    confidence=0.72,
                    tags=tags,
                )
            )
            seen_chunk_ids.add(chunk_id)

            if len(artifacts) >= max_total_chunks:
                return artifacts

    return artifacts


def format_mindscape_context(mindscape: Any) -> str:
    """Produce the source-profile context string injected into every extraction prompt."""
    parts = [f"Source: {mindscape.source_name}"]
    if getattr(mindscape, "system_name", None):
        parts.append(f"System: {mindscape.system_name}")
    parts.append(f"Summary: {mindscape.summary}")
    if getattr(mindscape, "themes", None):
        parts.append(f"Themes: {', '.join(mindscape.themes)}")
    if getattr(mindscape, "taxonomy_hints", None):
        parts.append(f"Key concepts: {', '.join(mindscape.taxonomy_hints)}")
    return "\n".join(parts)


def persist_mindscape_artifacts(
    *,
    pack_id: str,
    chunk_summaries: list[ChunkSummaryArtifact],
    section_summaries: list[Any],
    mindscape: Any,
    mongo_client: Any,
) -> None:
    """Write summary artifacts to the KnowledgePack in a single update call."""
    from monitor_data.schemas.knowledge_packs import KnowledgePackUpdate

    update = KnowledgePackUpdate(
        chunk_summaries=chunk_summaries,
        section_summaries=section_summaries,
        source_mindscape=mindscape,
    )
    cast(Any, _update_knowledge_pack_fn)(pack_id, update)
