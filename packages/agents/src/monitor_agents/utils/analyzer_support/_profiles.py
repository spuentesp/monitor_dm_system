"""Source profile building, merging, and ranking functions."""

from __future__ import annotations

import re
from typing import Any

from monitor_data.schemas.knowledge_packs import (  # type: ignore[attr-defined]
    EmbeddedSourceProfile,
    ProfileEvidenceRef,
)

from monitor_agents.utils.analyzer_support._constants import (
    _ALIAS_SIGNAL_RE,
    CONTAINER_TYPE_HINTS,
    GENERIC_CATEGORY_NAMES,
    PROFILE_DOMAIN_HINTS,
)
from monitor_agents.utils.analyzer_support._sections import SectionDigest

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dedupe_strings(values: list[str], *, limit: int | None = None) -> list[str]:
    """Return a case-insensitive deduped list while preserving the first casing."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if limit is not None and len(result) >= limit:
            break
    return result


def _singularize(term: str) -> str:
    """Reduce simple plural heading labels to a stable display form."""
    cleaned = term.strip().strip("#:- ")
    lowered = cleaned.lower()
    if lowered.endswith("ies") and len(cleaned) > 4:
        return cleaned[:-3] + "y"
    if lowered.endswith("s") and len(cleaned) > 3 and lowered[:-1] in GENERIC_CATEGORY_NAMES:
        return cleaned[:-1]
    return cleaned


# ---------------------------------------------------------------------------
# Taxonomy / glossary extraction
# ---------------------------------------------------------------------------


def extract_candidate_taxonomy_containers(
    sections: list[SectionDigest],
    *,
    limit: int = 12,
) -> list[str]:
    """Derive likely taxonomy container families from heading paths and reference sections."""
    candidates: list[str] = []
    for section in sections:
        for raw_part in re.split(r"[>/:|]", section.section_path or ""):
            part = _singularize(raw_part)
            lowered = part.lower()
            if not lowered:
                continue
            if lowered in GENERIC_CATEGORY_NAMES:
                candidates.append(part.title())
                continue
            for token, _entity_type in CONTAINER_TYPE_HINTS:
                if lowered == token or lowered.endswith(f" {token}"):
                    candidates.append(part.title())
                    break

        for raw_line in section.text.splitlines():
            line = _singularize(re.sub(r"\.{2,}\s*\d+$", "", raw_line).strip())
            lowered = line.lower()
            if not lowered or len(lowered.split()) > 4:
                continue
            if lowered in GENERIC_CATEGORY_NAMES:
                candidates.append(line.title())
                continue
            for token, _entity_type in CONTAINER_TYPE_HINTS:
                if lowered == token or lowered.endswith(f" {token}"):
                    candidates.append(line.title())
                    break
    return _dedupe_strings(candidates, limit=limit)


def extract_glossary_aliases(
    sections: list[SectionDigest],
    *,
    limit: int = 24,
) -> dict[str, list[str]]:
    """Build a compact alias lexicon from glossary-style reference text."""
    alias_map: dict[str, list[str]] = {}
    for section in sections:
        for raw_line in section.text.splitlines():
            line = raw_line.strip().strip("•-")
            if len(line) < 4:
                continue
            term = ""
            definition = ""
            if " — " in line:
                term, definition = line.split(" — ", 1)
            elif ":" in line and len(line.split(":", 1)[0].split()) <= 5:
                term, definition = line.split(":", 1)
            if not term or not definition:
                continue
            canon = _singularize(term)
            aliases: list[str] = []
            match = _ALIAS_SIGNAL_RE.search(definition)
            if match:
                aliases.extend(piece.strip(" .") for piece in re.split(r",|/|;", match.group(1)) if piece.strip())
            if aliases:
                alias_map[canon] = _dedupe_strings(aliases, limit=6)
            if len(alias_map) >= limit:
                break
        if len(alias_map) >= limit:
            break
    return alias_map


def infer_lore_domains(
    sections: list[SectionDigest],
    *,
    limit: int = 6,
) -> list[str]:
    """Infer the strongest lore domains from heading-path keywords."""
    counts: dict[str, int] = {}
    for section in sections:
        haystack = f"{section.section_path} {section.text[:240]}".lower()
        for domain, hints in PROFILE_DOMAIN_HINTS.items():
            if any(hint in haystack for hint in hints):
                counts[domain] = counts.get(domain, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [domain for domain, _count in ranked[:limit]]


def extract_canon_signal_terms(
    sections: list[SectionDigest],
    *,
    limit: int = 16,
) -> list[str]:
    """Harvest repeated canon-signaling vocabulary from headings and glossary entries."""
    terms: list[str] = []
    terms.extend(
        raw for section in sections for raw in re.findall(r"\b[A-Z][A-Za-z'-]{2,}\b", section.section_path or "")
    )
    terms.extend(
        raw.title()
        for section in sections
        for raw in re.findall(
            r"\b(?:tradition|elder|prince|rite|license|school|discipline|clan|sect|house|order)\b",
            section.text,
            re.IGNORECASE,
        )
    )
    return _dedupe_strings(terms, limit=limit)


# ---------------------------------------------------------------------------
# Source profile building / merging
# ---------------------------------------------------------------------------


def build_source_profile_seed(
    source_name: str,
    sections: list[SectionDigest],
    reference_sections: list[SectionDigest],
    *,
    source_kind: str,
    detected_system_name: str | None = None,
) -> EmbeddedSourceProfile:
    """Create a heuristic baseline profile from headings/reference signals alone."""
    support_sections = reference_sections or sections
    taxonomy_containers = extract_candidate_taxonomy_containers(support_sections)
    term_lexicon = extract_glossary_aliases(reference_sections)
    lore_domains = infer_lore_domains(sections + reference_sections)
    canon_signal_terms = extract_canon_signal_terms(support_sections)

    evidence_refs = [
        ProfileEvidenceRef(
            ref=section.section_path or f"{source_name} reference",
            section_path=section.section_path or None,
            page_hint=section.min_page if section.min_page and section.min_page > 0 else None,
            note="reference signal" if section in reference_sections else "body section",
        )
        for section in support_sections[:6]
    ]

    confidence_by_field: dict[str, float] = {}
    if taxonomy_containers:
        confidence_by_field["taxonomy_containers"] = 0.82
    if term_lexicon:
        confidence_by_field["term_lexicon"] = 0.74
    if lore_domains:
        confidence_by_field["lore_domains"] = 0.78
    if canon_signal_terms:
        confidence_by_field["canon_signal_terms"] = 0.72
    if detected_system_name:
        confidence_by_field["system_name"] = 0.92

    coverage_bits: list[str] = []
    if taxonomy_containers:
        coverage_bits.append(f"taxonomy families: {', '.join(taxonomy_containers[:4])}")
    if lore_domains:
        coverage_bits.append(f"domains: {', '.join(lore_domains[:4])}")

    return EmbeddedSourceProfile(
        title=source_name,
        source_type=source_kind or "mixed",
        system_name=detected_system_name,
        lore_domains=lore_domains,
        taxonomy_containers=taxonomy_containers,
        term_lexicon=term_lexicon,
        canon_signal_terms=canon_signal_terms,
        coverage_summary=("; ".join(coverage_bits) or f"Profile seed created from {source_name} headings.")[:2000],
        evidence_refs=evidence_refs,
        confidence_by_field=confidence_by_field,
        profile_version="1.0",
        prompt_version="source-profile-v1",
    )


def merge_source_profiles(
    seed: EmbeddedSourceProfile,
    synthesized: EmbeddedSourceProfile | None,
) -> EmbeddedSourceProfile:
    """Merge heuristic seed data with a synthesized LLM profile without losing evidence."""
    if synthesized is None:
        return seed

    merged_data = seed.model_dump(mode="python")
    synth_data = synthesized.model_dump(mode="python")

    list_fields = (
        "genre_tone",
        "narrative_frame",
        "lore_domains",
        "taxonomy_containers",
        "institution_model",
        "relationship_patterns",
        "canon_signal_terms",
        "important_named_sets",
        "known_open_questions",
    )
    for field in list_fields:
        merged_data[field] = _dedupe_strings(
            [
                *merged_data.get(field, []),
                *synth_data.get(field, []),
            ]
        )

    for field in (
        "world_kind",
        "system_name",
        "edition",
        "family",
        "coverage_summary",
        "prompt_version",
        "model_used",
    ):
        if synth_data.get(field):
            merged_data[field] = synth_data[field]

    for dict_field in ("term_lexicon", "aliases"):
        combined: dict[str, list[str]] = {}
        for source_dict in (merged_data.get(dict_field, {}), synth_data.get(dict_field, {})):
            for key, raw_values in (source_dict or {}).items():
                existing = combined.get(str(key), [])
                combined[str(key)] = _dedupe_strings([*existing, *(raw_values or [])])
        merged_data[dict_field] = combined

    merged_confidence = dict(seed.confidence_by_field)
    merged_confidence.update(synthesized.confidence_by_field)
    merged_data["confidence_by_field"] = merged_confidence

    merged_refs = [*seed.evidence_refs, *synthesized.evidence_refs]
    deduped_refs: list[ProfileEvidenceRef] = []
    seen_refs: set[tuple[str, str | None]] = set()
    for ref in merged_refs:
        key = (ref.ref, ref.section_path)
        if key in seen_refs:
            continue
        seen_refs.add(key)
        deduped_refs.append(ref)
    merged_data["evidence_refs"] = deduped_refs[:12]

    return EmbeddedSourceProfile(**merged_data)


def format_source_profile_context(
    profile: EmbeddedSourceProfile | None,
    *,
    min_confidence: float = 0.75,
) -> str:
    """Render only high-confidence profile fields for downstream prompt injection."""
    if profile is None:
        return ""

    confidence = profile.confidence_by_field or {}

    def include(field: str, value: Any) -> bool:
        if value in (None, "", [], {}):
            return False
        return confidence.get(field, 0.0) >= min_confidence

    lines: list[str] = []
    if include("system_name", profile.system_name):
        lines.append(f"System: {profile.system_name}")
    if include("world_kind", profile.world_kind):
        lines.append(f"World kind: {profile.world_kind}")
    if include("lore_domains", profile.lore_domains):
        lines.append(f"Lore domains: {', '.join(profile.lore_domains[:6])}")
    if include("taxonomy_containers", profile.taxonomy_containers):
        lines.append(f"Taxonomy containers: {', '.join(profile.taxonomy_containers[:8])}")
    if include("institution_model", profile.institution_model):
        lines.append(f"Institution model: {', '.join(profile.institution_model[:6])}")
    if include("relationship_patterns", profile.relationship_patterns):
        lines.append(f"Relationship patterns: {', '.join(profile.relationship_patterns[:8])}")
    if include("canon_signal_terms", profile.canon_signal_terms):
        lines.append(f"Canon signal terms: {', '.join(profile.canon_signal_terms[:10])}")
    if include("term_lexicon", profile.term_lexicon):
        compact_pairs = [
            f"{term}=>{', '.join(values[:3])}" for term, values in list(profile.term_lexicon.items())[:6] if values
        ]
        if compact_pairs:
            lines.append(f"Lexicon aliases: {'; '.join(compact_pairs)}")
    return "\n".join(lines)


def summarize_source_profile(profile: EmbeddedSourceProfile | None) -> str:
    """Build a short user-facing status line for job activity logs."""
    if profile is None:
        return "Source profile unavailable; using generic extraction mode"

    summary_bits: list[str] = []
    if profile.source_kind:
        summary_bits.append(profile.source_kind)
    if profile.system_name:
        summary_bits.append(profile.system_name)
    if profile.taxonomy_containers:
        summary_bits.append(f"containers={', '.join(profile.taxonomy_containers[:3])}")
    if profile.lore_domains:
        summary_bits.append(f"domains={', '.join(profile.lore_domains[:3])}")
    return "Source profile ready: " + " | ".join(summary_bits[:4])


def rank_sections_with_profile(
    sections: list[SectionDigest],
    profile: EmbeddedSourceProfile | None,
) -> list[SectionDigest]:
    """Re-rank content sections by profile relevance so the richest batches come first."""
    if not profile or not sections:
        return sections

    signal_terms: set[str] = set()
    for terms_list in (
        profile.taxonomy_containers,
        profile.lore_domains,
        profile.canon_signal_terms,
        profile.institution_model,
        profile.important_named_sets,
        profile.genre_tone,
        profile.narrative_frame,
    ):
        for term in terms_list or []:
            cleaned = str(term).strip().lower()
            if cleaned:
                signal_terms.add(cleaned)
    for term in profile.term_lexicon or {}:
        cleaned = str(term).strip().lower()
        if cleaned:
            signal_terms.add(cleaned)

    if not signal_terms:
        return sections

    scored: list[tuple[int, int, SectionDigest]] = []
    for idx, section in enumerate(sections):
        haystack = f"{section.section_path or ''} {section.text[:600]}".lower()
        score = sum(1 for term in signal_terms if term in haystack)
        scored.append((score, idx, section))

    scored.sort(key=lambda t: (-t[0], t[1]))
    return [section for _, _, section in scored]
