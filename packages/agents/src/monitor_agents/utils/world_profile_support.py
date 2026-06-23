"""Deterministic helpers for World Architect profile framing and gap analysis.

These helpers keep `world_architect.py` focused on orchestration while a
small, auditable profile layer infers tone, domains, institutions, and open
questions from the current world state plus the latest conversation turn.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from monitor_data.schemas.knowledge_packs import EmbeddedWorldProfile, ProfileEvidenceRef


_WORLD_KIND_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gothic horror", ("vampire", "gothic", "blood", "nocturnal", "eldritch")),
    ("fantasy", ("kingdom", "dragon", "sorcery", "magic", "castle", "sword")),
    ("sci-fi", ("starship", "mech", "cyber", "orbit", "ai", "android", "colony")),
    ("post-apocalypse", ("wasteland", "ruin", "apocalypse", "scarcity", "salvage")),
    ("mythic", ("god", "divine", "oracle", "myth", "prophecy")),
)

_TONE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("courtly intrigue", ("court", "noble", "intrigue", "house", "succession", "alliance")),
    ("grim", ("grim", "ruin", "bleak", "ash", "hardship")),
    ("mystery", ("mystery", "secret", "hidden", "investigate", "clue")),
    ("heroic", ("heroic", "champion", "quest", "valor", "oath")),
    ("survival", ("survive", "scarcity", "ration", "danger", "salvage")),
    ("horror", ("horror", "terror", "dread", "nightmare", "haunt")),
)

_FRAME_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("political", ("court", "council", "throne", "house", "empire", "govern")),
    ("investigative", ("investigate", "mystery", "clue", "conspiracy", "solve")),
    ("military", ("war", "legion", "army", "front", "garrison")),
    ("survival", ("survive", "wasteland", "scarcity", "storm", "siege")),
    ("religious", ("temple", "church", "cult", "faith", "saint")),
)

_DOMAIN_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("history", ("ancient", "fell", "war", "era", "dynasty", "founded")),
    ("religion", ("god", "faith", "temple", "church", "cult", "rite")),
    ("geography", ("city", "sea", "mountain", "desert", "island", "region")),
    ("factions", ("guild", "house", "clan", "court", "order", "legion")),
    ("metaphysics", ("magic", "soul", "void", "blood", "spirit", "curse")),
    ("technology", ("machine", "engine", "cyber", "mech", "reactor")),
)

_INSTITUTION_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("noble houses", ("house", "duke", "baron", "court", "prince")),
    ("guilds", ("guild", "union", "syndicate")),
    ("religious orders", ("church", "temple", "faith", "order", "abbey")),
    ("military commands", ("legion", "garrison", "admiral", "captain", "fleet")),
    ("clans", ("clan", "lineage", "bloodline", "tribe")),
)

_RELATIONSHIP_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rules", ("rules", "governs", "holds sway", "dominates")),
    ("member_of", ("belongs", "sworn", "serves", "member")),
    ("opposes", ("feud", "oppose", "rival", "enemy", "war")),
    ("allied_with", ("alliance", "ally", "pact", "treaty")),
    ("located_in", ("in the", "within", "beneath", "across")),
)


def _dedupe(items: Iterable[str], *, limit: int | None = None) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
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


def _match_labels(
    text: str, mapping: Sequence[tuple[str, tuple[str, ...]]], *, limit: int = 6
) -> List[str]:
    lowered = (text or "").lower()
    labels = [
        label for label, keywords in mapping if any(keyword in lowered for keyword in keywords)
    ]
    return _dedupe(labels, limit=limit)


def _iter_entity_names(summary: Mapping[str, Any]) -> List[str]:
    entities = summary.get("entities") or []
    if not isinstance(entities, list):
        return []
    return _dedupe(
        [item.get("name", "") for item in entities if isinstance(item, Mapping)], limit=8
    )

    entities_terms = [
        " ".join(str(item.get(k, "")) for k in ("name", "type", "description"))
        for item in summary.get("entities") or []
        if isinstance(item, Mapping)
    ]
    axioms_terms = [
        " ".join(str(item.get(k, "")) for k in ("statement", "domain"))
        for item in summary.get("axioms") or []
        if isinstance(item, Mapping)
    ]
    facts_terms = [
        " ".join(str(item.get(k, "")) for k in ("statement", "type"))
        for item in summary.get("facts") or []
        if isinstance(item, Mapping)
    ]
    return " ".join(entities_terms + axioms_terms + facts_terms)


def _build_term_lexicon(names: Sequence[str]) -> Dict[str, List[str]]:
    lexicon: Dict[str, List[str]] = {}
    for name in names:
        words = [word for word in re.findall(r"[A-Za-z][A-Za-z'-]+", name) if len(word) > 2]
        if len(words) < 2:
            continue
        aliases = [words[-1]]
        if (
            words[0].lower() in {"house", "clan", "order", "guild", "court", "city"}
            and len(words) >= 2
        ):
            aliases.append(" ".join(words[1:]))
        lexicon[name] = _dedupe(aliases, limit=3)
    return {key: value for key, value in lexicon.items() if value}


def summarize_world_coverage(
    summary: Mapping[str, Any], *, profile: EmbeddedWorldProfile | None = None
) -> str:
    entity_count = int(summary.get("entity_count", 0) or 0)
    axiom_count = int(summary.get("axiom_count", 0) or 0)
    fact_count = int(summary.get("fact_count", 0) or 0)
    anchors = _iter_entity_names(summary)

    parts = [
        f"Current world coverage includes {entity_count} entities, {axiom_count} axioms, and {fact_count} lore facts."
    ]
    if anchors:
        parts.append(f"Named anchors: {', '.join(anchors[:5])}.")
    if profile and profile.genre_tone:
        parts.append(f"Tone cues: {', '.join(profile.genre_tone[:3])}.")
    if profile and profile.institution_model:
        parts.append(f"Power structures: {', '.join(profile.institution_model[:3])}.")
    return " ".join(parts).strip()


def derive_known_open_questions(
    summary: Mapping[str, Any], profile: EmbeddedWorldProfile
) -> List[str]:
    entities = summary.get("entities") or []
    entity_types = {
        str(item.get("type", "")).lower() for item in entities if isinstance(item, Mapping)
    }

    questions: List[str] = []
    if not _iter_entity_names(summary):
        questions.append("What is the world, realm, or central city called?")
    if not profile.world_kind:
        questions.append("What genre blend or foundational mood defines this setting?")
    if not ({"location", "place", "region", "city"} & entity_types):
        questions.append("Which regions, cities, or landmarks matter most right now?")
    if not ({"faction", "organization"} & entity_types):
        questions.append("Which factions, houses, cults, or governments hold power?")
    if int(summary.get("axiom_count", 0) or 0) == 0:
        questions.append("What fundamental rule shapes magic, technology, faith, or society?")
    if int(summary.get("fact_count", 0) or 0) < 2:
        questions.append("What active conflict, threat, or pressure point is driving play?")
    if not any("character" in etype for etype in entity_types):
        questions.append("Who are the key figures players are likely to meet or fear?")
    return _dedupe(questions, limit=6)


def build_priority_gaps(
    summary: Mapping[str, Any], profile: EmbeddedWorldProfile
) -> List[Dict[str, Any]]:
    """Generate deterministic, prioritized world-building gaps."""
    prompts = [
        (
            "Core identity",
            1,
            "Name the world and lock in its genre and emotional tone.",
            "This world is called ____, and its tone is ____.",
        ),
        (
            "Power structures",
            2,
            "Define the factions, courts, houses, or institutions that hold power.",
            "The dominant factions are ____ because ____.",
        ),
        (
            "Geography",
            3,
            "Establish a few regions, cities, or landmarks players can orient around.",
            "The most important places are ____.",
        ),
        (
            "World rules",
            4,
            "Clarify the core axiom that governs magic, technology, faith, or survival.",
            "In this world, it is always true that ____.",
        ),
        (
            "Current conflict",
            5,
            "Surface the present crisis or tension that gives the setting momentum.",
            "Right now, the greatest tension is ____.",
        ),
    ]

    open_questions = set(derive_known_open_questions(summary, profile))
    gaps: List[Dict[str, Any]] = []
    for area, priority, suggestion, example in prompts:
        if any(token in " ".join(open_questions).lower() for token in area.lower().split()):
            gaps.append(
                {
                    "area": area,
                    "priority": priority,
                    "suggestion": suggestion,
                    "example_prompt": example,
                }
            )

    if not gaps:
        gaps = [
            {
                "area": area,
                "priority": priority,
                "suggestion": suggestion,
                "example_prompt": example,
            }
            for area, priority, suggestion, example in prompts[:3]
        ]
    return gaps[:5]


def merge_world_profiles(
    current: EmbeddedWorldProfile,
    prior: EmbeddedWorldProfile | None,
) -> EmbeddedWorldProfile:
    """Merge a freshly derived profile with a previously persisted one.

    The current profile takes precedence for scalar fields; list fields are
    unioned so accumulated knowledge is never discarded across turns or sessions.
    Confidence values are averaged to reflect the combined evidence base.
    """
    if prior is None:
        return current

    def _union(a: List[str], b: List[str]) -> List[str]:
        return _dedupe([*a, *b])

    def _union_dict(a: Dict[str, List[str]], b: Dict[str, List[str]]) -> Dict[str, List[str]]:
        combined: Dict[str, List[str]] = {}
        for key in {*a, *b}:
            combined[key] = _dedupe([*(a.get(key) or []), *(b.get(key) or [])])
        return combined

    def _avg_confidence(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
        merged: Dict[str, float] = {}
        for key in {*a, *b}:
            va = a.get(key, 0.0)
            vb = b.get(key, 0.0)
            merged[key] = round((va + vb) / 2, 4) if (key in a and key in b) else max(va, vb)
        return merged

    merged = EmbeddedWorldProfile(
        world_kind=current.world_kind or prior.world_kind,
        system_name=current.system_name or prior.system_name,
        edition=current.edition or prior.edition,
        family=current.family or prior.family,
        genre_tone=_union(current.genre_tone, prior.genre_tone),
        narrative_frame=_union(current.narrative_frame, prior.narrative_frame),
        lore_domains=_union(current.lore_domains, prior.lore_domains),
        taxonomy_containers=_union(current.taxonomy_containers, prior.taxonomy_containers),
        institution_model=_union(current.institution_model, prior.institution_model),
        relationship_patterns=_union(current.relationship_patterns, prior.relationship_patterns),
        term_lexicon=_union_dict(current.term_lexicon, prior.term_lexicon),
        aliases=_union_dict(current.aliases, prior.aliases),
        canon_signal_terms=_union(current.canon_signal_terms, prior.canon_signal_terms),
        important_named_sets=_union(current.important_named_sets, prior.important_named_sets),
        known_open_questions=_union(current.known_open_questions, prior.known_open_questions),
        confidence_by_field=_avg_confidence(current.confidence_by_field, prior.confidence_by_field),
        evidence_refs=_dedupe([ref.ref for ref in [*current.evidence_refs, *prior.evidence_refs]])
        and [
            *current.evidence_refs,
            *prior.evidence_refs[: max(0, 6 - len(current.evidence_refs))],
        ],
        profile_version=current.profile_version,
        prompt_version=current.prompt_version,
        model_used=current.model_used,
        world_name=current.world_name or prior.world_name,
        multiverse_name=current.multiverse_name or prior.multiverse_name,
    )
    merged.coverage_summary = current.coverage_summary or prior.coverage_summary
    merged.known_open_questions = _dedupe(
        [*current.known_open_questions, *prior.known_open_questions],
        limit=8,
    )
    return merged


def build_world_profile(
    summary: Mapping[str, Any],
    *,
    user_message: str = "",
    conversation_history: Sequence[Mapping[str, Any]] | None = None,
    prior_profile: EmbeddedWorldProfile | None = None,
) -> EmbeddedWorldProfile:
    """Infer a world profile from world state and recent messages, merging with prior.

    When ``prior_profile`` is supplied (loaded from MongoDB persistence), the
    newly derived profile is merged with it so accumulated vocabulary, tone cues,
    and named anchors are carried forward across turns and sessions.
    """
    summary = summary if isinstance(summary, Mapping) else {}
    history_text = " ".join(
        str(msg.get("content", ""))
        for msg in (conversation_history or [])
        if isinstance(msg, Mapping)
    )
    source_text = " ".join(
        [
            user_message,
            history_text,
            " ".join(
                " ".join(str(item.get(k, "")) for k in ("name", "type", "description"))
                for item in summary.get("entities") or []
                if isinstance(item, Mapping)
            )
            + " ".join(
                " ".join(str(item.get(k, "")) for k in ("statement", "domain"))
                for item in summary.get("axioms") or []
                if isinstance(item, Mapping)
            )
            + " ".join(
                " ".join(str(item.get(k, "")) for k in ("statement", "type"))
                for item in summary.get("facts") or []
                if isinstance(item, Mapping)
            ),
        ]
    ).strip()

    world_kind_matches = _match_labels(source_text, _WORLD_KIND_HINTS, limit=2)
    world_kind = world_kind_matches[0] if world_kind_matches else None
    genre_tone = _match_labels(source_text, _TONE_HINTS)
    narrative_frame = _match_labels(source_text, _FRAME_HINTS)
    lore_domains = _dedupe(
        [
            *[
                str(item.get("domain", "")).strip()
                for item in (summary.get("axioms") or [])
                if isinstance(item, Mapping)
            ],
            *_match_labels(source_text, _DOMAIN_HINTS),
        ],
        limit=8,
    )
    institution_model = _match_labels(source_text, _INSTITUTION_HINTS)
    relationship_patterns = _match_labels(source_text, _RELATIONSHIP_HINTS)

    entity_types = _dedupe(
        [
            str(item.get("type", "")).strip().title()
            for item in (summary.get("entities") or [])
            if isinstance(item, Mapping)
        ],
        limit=8,
    )
    important_named_sets = _iter_entity_names(summary)
    term_lexicon = _build_term_lexicon(important_named_sets)
    aliases = {key: values for key, values in term_lexicon.items() if values}

    capitalized_terms = _dedupe(re.findall(r"\b[A-Z][a-zA-Z'-]{2,}\b", source_text), limit=10)
    canon_signal_terms = _dedupe(
        [
            *capitalized_terms,
            *[label.split()[0].title() for label in institution_model],
        ],
        limit=10,
    )

    evidence_refs = []
    if user_message.strip():
        evidence_refs.append(
            ProfileEvidenceRef(
                ref=f"Latest user turn: {user_message[:120]}",
                section_path=None,
                page_hint=None,
                note="World Architect input",
            )
        )
    if important_named_sets:
        evidence_refs.append(
            ProfileEvidenceRef(
                ref=f"World anchors: {', '.join(important_named_sets[:4])}",
                section_path=None,
                page_hint=None,
                note="Existing world state",
            )
        )

    confidence_by_field: Dict[str, float] = {}
    if world_kind:
        confidence_by_field["world_kind"] = 0.82
    if genre_tone:
        confidence_by_field["genre_tone"] = 0.78
    if narrative_frame:
        confidence_by_field["narrative_frame"] = 0.76
    if lore_domains:
        confidence_by_field["lore_domains"] = 0.84
    if institution_model:
        confidence_by_field["institution_model"] = 0.8
    if canon_signal_terms:
        confidence_by_field["canon_signal_terms"] = 0.72
    if term_lexicon:
        confidence_by_field["term_lexicon"] = 0.7

    profile = EmbeddedWorldProfile(
        profile_type="world",
        world_kind=world_kind,
        system_name=None,
        edition=None,
        family=None,
        genre_tone=genre_tone,
        narrative_frame=narrative_frame,
        lore_domains=lore_domains,
        taxonomy_containers=entity_types,
        institution_model=institution_model,
        relationship_patterns=relationship_patterns,
        term_lexicon=term_lexicon,
        aliases=aliases,
        canon_signal_terms=canon_signal_terms,
        important_named_sets=important_named_sets,
        confidence_by_field=confidence_by_field,
        evidence_refs=evidence_refs,
        prompt_version="world-profile-v1",
        model_used=None,
        world_name=None,
        multiverse_name=None,
    )
    profile.coverage_summary = summarize_world_coverage(summary, profile=profile)
    profile.known_open_questions = derive_known_open_questions(summary, profile)
    if prior_profile is not None:
        profile = merge_world_profiles(profile, prior_profile)
    return profile


def render_world_profile_context(profile: EmbeddedWorldProfile) -> str:
    """Render concise, high-value profile context for world-building prompts."""
    lines: List[str] = []
    if profile.world_kind:
        lines.append(f"World kind: {profile.world_kind}")
    if profile.genre_tone:
        lines.append(f"Genre/tone: {', '.join(profile.genre_tone[:5])}")
    if profile.narrative_frame:
        lines.append(f"Narrative frame: {', '.join(profile.narrative_frame[:5])}")
    if profile.lore_domains:
        lines.append(f"Lore domains: {', '.join(profile.lore_domains[:6])}")
    if profile.institution_model:
        lines.append(f"Institutions: {', '.join(profile.institution_model[:6])}")
    if profile.important_named_sets:
        lines.append(f"Named anchors: {', '.join(profile.important_named_sets[:6])}")
    if profile.relationship_patterns:
        lines.append(
            f"Likely relationship patterns: {', '.join(profile.relationship_patterns[:6])}"
        )
    if profile.known_open_questions:
        lines.append(f"Open questions: {'; '.join(profile.known_open_questions[:4])}")
    return "\n".join(lines)
