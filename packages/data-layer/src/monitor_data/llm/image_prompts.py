"""Pure canon-aware prompt assembly for image generation.

LAYER: 1 (data-layer)
IMPORTS FROM: standard library, pydantic, and monitor_data schemas only

This module performs NO persistence or network access.  It receives a
character-like input (a mapping or an attribute object such as the character
dicts the UI backend passes around) plus a duck-typed canonical visual
context, and returns the final provider prompt with durable provenance.

The context object is imported loosely: the real ``CanonicalVisualContext``
lives in Layer 2 (``monitor_agents.image_context``), which this layer must
not import.  Any object with the following attributes works:

    visual_identities  — iterable of ``VisualIdentity`` models or mappings;
                         only ``approved`` identities are used
    facts              — iterable of objects/mappings with ``fact_id`` (or
                         ``id``) and ``statement``
    reference_assets   — iterable of objects/mappings with ``asset_id`` (or
                         ``id``) and optional ``approval_status`` /
                         ``reference_status``

Visual-identity precedence (per field):

    canonical entity identity (entity_id anchor, no character_id)
    > approved incarnation identity (character_id + universe_id,
      optionally also carrying an entity_id)
    > card default identity (character_id only)
    > card description/personality fallback

When sources conflict, the higher-precedence value wins and a human-readable
entry is recorded in ``ImagePrompt.warnings``.  Rejected (or otherwise
non-approved) assets never appear in ``reference_asset_ids``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, Field

from monitor_data.schemas.visual_identity import VisualIdentityStatus

_SCENE_EXCERPT_LIMIT = 3_000
_NEGATIVE_PROMPT = "text, watermark, signature, logo"
_VISUAL_METADATA_VALUES = frozenset({"appearance", "physical_appearance", "visual"})
_PORTRAIT_STYLE = (
    "Style: head-and-shoulders character portrait, expressive, painterly, "
    "high detail, consistent anatomy, no text, no watermark."
)
_SCENE_STYLE = "Style: atmospheric, painterly, dramatic lighting, coherent spatial composition, no text, no watermark."

# Fixed field order for identity rendering; "personality" is card-fallback only.
_VISUAL_FIELDS = (
    "description",
    "species_or_type",
    "apparent_age",
    "build",
    "hair",
    "eyes",
    "skin_or_surface",
    "signature_attire",
    "distinguishing_features",
    "palette",
    "style_hint",
    "personality",
)
_FIELD_LABELS = {
    "description": "Description",
    "species_or_type": "Species/type",
    "apparent_age": "Apparent age",
    "build": "Build",
    "hair": "Hair",
    "eyes": "Eyes",
    "skin_or_surface": "Skin/surface",
    "signature_attire": "Signature attire",
    "distinguishing_features": "Distinguishing features",
    "palette": "Palette",
    "style_hint": "Style hint",
    "personality": "Personality",
}
# Precedence tier labels, highest first.
_TIER_LABELS = ("canonical identity", "incarnation identity", "card identity")
_CARD_LABEL = "card defaults"


class ImagePrompt(BaseModel):
    """Final provider prompt plus durable provenance for a GeneratedAsset."""

    positive: str
    negative: str = ""
    reference_asset_ids: list[str] = Field(default_factory=list)
    source_fact_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Duck-typed access helpers
# ---------------------------------------------------------------------------


def _get(value: Any, key: str) -> Any:
    """Read ``key`` from a mapping or an attribute object; None when absent."""
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _enum_str(value: Any) -> str:
    """Normalize StrEnum/enum/plain values to a lowercase string."""
    return str(getattr(value, "value", value) or "").lower()


def _normalise(value: Any) -> Any:
    """Strip strings and normalise list-like values to tuples of strings."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return value


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, frozenset, Mapping)):
        return bool(value)
    return True


def _render(value: Any) -> str:
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    return str(value)


# ---------------------------------------------------------------------------
# Identity precedence
# ---------------------------------------------------------------------------


def _identity_tier(identity: Any) -> int:
    """0 = canonical entity, 1 = incarnation, 2 = card default.

    The schema allows incarnation anchors to carry an optional ``entity_id``;
    such identities must stay tier 1 so they never usurp canonical
    precedence.  Canonical is entity_id WITHOUT a character_id.
    """
    has_entity = _nonempty(_get(identity, "entity_id"))
    has_character = _nonempty(_get(identity, "character_id"))
    has_universe = _nonempty(_get(identity, "universe_id"))
    if has_entity and not has_character:
        return 0
    if has_character and has_universe:
        return 1
    return 2


def _identity_version(identity: Any) -> int:
    version = _get(identity, "version")
    try:
        return int(version)
    except (TypeError, ValueError):
        return 0


def _is_approved(identity: Any) -> bool:
    status = _get(identity, "status")
    return _enum_str(status) == VisualIdentityStatus.APPROVED.value


def _best_per_tier(identities: Iterable[Any]) -> dict[int, Any]:
    """Pick the highest-version approved identity for each precedence tier."""
    best: dict[int, Any] = {}
    for identity in identities:
        if identity is None or not _is_approved(identity):
            continue
        tier = _identity_tier(identity)
        current = best.get(tier)
        if current is None or _identity_version(identity) > _identity_version(current):
            best[tier] = identity
    return best


def _identity_values(identity: Any) -> dict[str, Any]:
    return {
        field_name: _normalise(_get(identity, field_name))
        for field_name in _VISUAL_FIELDS
        if field_name != "personality" and _nonempty(_get(identity, field_name))
    }


def _card_values(character: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field_name in ("description", "personality"):
        value = _normalise(_get(character, field_name))
        if _nonempty(value):
            values[field_name] = value
    return values


def _resolve_visual_fields(
    identities: Iterable[Any],
    character: Any,
) -> tuple[dict[str, Any], list[str]]:
    """Resolve visual fields by precedence; record conflicts as warnings."""
    best = _best_per_tier(identities)
    sources: list[tuple[str, dict[str, Any]]] = [
        (_TIER_LABELS[tier], _identity_values(best[tier])) for tier in sorted(best)
    ]
    sources.append((_CARD_LABEL, _card_values(character)))

    resolved: dict[str, Any] = {}
    winners: dict[str, str] = {}
    warnings: list[str] = []
    for source_label, candidate in sources:
        for field_name in _VISUAL_FIELDS:
            value = candidate.get(field_name)
            if not _nonempty(value):
                continue
            if field_name not in resolved:
                resolved[field_name] = value
                winners[field_name] = source_label
            elif value != resolved[field_name]:
                warnings.append(
                    f"Ignored conflicting lower-priority {source_label} field "
                    f"'{field_name}'; {winners[field_name]} value has priority."
                )
    return resolved, warnings


def _identity_group_key(identity: Any) -> str:
    entity_id = _get(identity, "entity_id")
    if _nonempty(entity_id):
        return f"entity:{entity_id}"
    return f"character:{_get(identity, 'character_id')}"


# ---------------------------------------------------------------------------
# Facts and reference assets
# ---------------------------------------------------------------------------


def _fact_parts(fact: Any) -> tuple[str, str]:
    fact_id = _get(fact, "fact_id")
    if not _nonempty(fact_id):
        fact_id = _get(fact, "id")
    statement = _get(fact, "statement")
    return (
        str(fact_id) if _nonempty(fact_id) else "",
        str(statement).strip() if _nonempty(statement) else "",
    )


def _sorted_facts(context: Any) -> list[tuple[str, str]]:
    raw = getattr(context, "facts", ()) if context is not None else ()
    parts = [_fact_parts(fact) for fact in raw or ()]
    # Defense in depth: upstream ``image_context._as_visual_fact`` already
    # drops superseded / proposed / non-canon facts, but a context assembled
    # some other way (test doubles, a future read path) must never leak
    # unrelated world facts into the provider prompt. When a fact carries
    # an explicit status or canon_level, the prompt layer honours them here.
    filtered = [
        (fact_id, statement)
        for fact_id, statement, _fact in (
            (fid, stmt, fact)
            for (fid, stmt), fact in zip(parts, raw or ())
        )
        if _fact_is_eligible(_fact)
    ]
    return sorted(filtered, key=lambda pair: (pair[0], pair[1]))


def _fact_is_eligible(fact: Any) -> bool:
    """Apply the upstream visual/canon filter defensively.

    The ``CanonicalVisualContext`` already enforces this in
    ``monitor_agents.image_context._as_visual_fact``; we mirror it here so a
    duck-typed context that bypasses that filter still cannot leak unrelated
    world facts (relationships, plain attributes, proposed canon, superseded
    status) into the provider prompt. Tests that pass facts without these
    fields continue to work — the filter only acts when the relevant fields
    are explicitly set on the fact.
    """
    status = _get(fact, "status")
    if _nonempty(status) and _enum_str(status) != "active":
        return False
    canon_level = _get(fact, "canon_level")
    if _nonempty(canon_level) and _enum_str(canon_level) != "canon":
        return False
    fact_type = _get(fact, "fact_type")
    if _nonempty(fact_type):
        normalized = _enum_str(fact_type)
        if normalized == "state":
            return True
        if normalized == "attribute":
            # Attribute facts must carry visual metadata to reach the prompt.
            properties = _get(fact, "properties") or {}
            if isinstance(properties, Mapping) and _has_visual_metadata(properties):
                return True
            return False
        # relationship / occurrence / other types are dropped.
        return False
    return True


def _has_visual_metadata(properties: Any) -> bool:
    """Mirror of ``monitor_agents.image_context._has_visual_metadata``.

    Attribute facts are eligible only when they carry one of the canonical
    visual cues (the ``visual`` / ``is_visual`` flags, a category/domain/
    kind/type of appearance/physical_appearance/visual, or a ``visual`` tag).
    """
    if not isinstance(properties, Mapping):
        return False
    if properties.get("visual") is True or properties.get("is_visual") is True:
        return True
    for key in ("category", "domain", "kind", "type"):
        if _enum_str(properties.get(key)) in _VISUAL_METADATA_VALUES:
            return True
    tags = properties.get("tags")
    return isinstance(tags, (list, tuple, set, frozenset)) and any(
        _enum_str(tag) in _VISUAL_METADATA_VALUES for tag in tags
    )


def _source_fact_ids(facts: list[tuple[str, str]]) -> list[str]:
    return sorted({fact_id for fact_id, _ in facts if fact_id})


def _reference_asset_ids(context: Any) -> list[str]:
    """Approved primary/supporting references only; rejected never appear."""
    raw = getattr(context, "reference_assets", ()) if context is not None else ()
    best_role: dict[str, int] = {}
    for asset in raw or ():
        approval = _get(asset, "approval_status")
        # A missing approval status means the context already curated the
        # asset (Layer 2 only carries approved references); an explicit
        # non-approved status (rejected/pending) always excludes it.
        if _nonempty(approval) and _enum_str(approval) != "approved":
            continue
        reference = _enum_str(_get(asset, "reference_status"))
        if reference not in ("primary", "supporting"):
            continue
        asset_id = _get(asset, "asset_id")
        if not _nonempty(asset_id):
            asset_id = _get(asset, "id")
        if not _nonempty(asset_id):
            continue
        role = 0 if reference == "primary" else 1
        key = str(asset_id)
        if key not in best_role or role < best_role[key]:
            best_role[key] = role
    ordered = sorted(best_role.items(), key=lambda item: (item[1], item[0]))
    return [asset_id for asset_id, _ in ordered]


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _appearance_lines(resolved: dict[str, Any]) -> list[str]:
    return [
        f"{_FIELD_LABELS[field_name]}: {_render(resolved[field_name])}"
        for field_name in _VISUAL_FIELDS
        if field_name in resolved
    ]


def _facts_section(facts: list[tuple[str, str]]) -> str | None:
    if not facts:
        return None
    return "Current visual facts:\n" + "\n".join(f"- {statement}" for _, statement in facts)


def build_portrait_prompt(character: Any, context: Any = None) -> ImagePrompt:
    """Assemble a deterministic portrait prompt from a character and context.

    ``character`` is a mapping or attribute object with ``name``,
    ``description`` and ``personality`` fields (the shape the UI backend
    passes).  ``context`` is the duck-typed canonical visual context
    documented in the module docstring; ``None`` means card fallback only.
    """
    name = _get(character, "name")
    name = str(name).strip() if _nonempty(name) else "a fictional character"
    identities = getattr(context, "visual_identities", ()) if context is not None else ()

    resolved, warnings = _resolve_visual_fields(identities or (), character)
    facts = _sorted_facts(context)

    sections = [f"Character portrait of {name}."]
    appearance = _appearance_lines(resolved)
    if appearance:
        sections.append("Visual identity:\n" + "\n".join(appearance))
    facts_section = _facts_section(facts)
    if facts_section is not None:
        sections.append(facts_section)
    sections.append(_PORTRAIT_STYLE)

    return ImagePrompt(
        positive="\n\n".join(sections),
        negative=_NEGATIVE_PROMPT,
        reference_asset_ids=_reference_asset_ids(context),
        source_fact_ids=_source_fact_ids(facts),
        warnings=list(dict.fromkeys(warnings)),
    )


def _scene_excerpt(messages: Iterable[Mapping[str, Any]]) -> tuple[str, list[str]]:
    lines: list[str] = []
    for message in messages or ():
        text = message.get("text") or message.get("content") or ""
        text = str(text).strip()
        if not text:
            continue
        speaker = message.get("entity_name") or message.get("speaker_role") or message.get("role")
        lines.append(f"{speaker}: {text}" if speaker else text)
    excerpt = "\n".join(lines)
    warnings: list[str] = []
    if len(excerpt) > _SCENE_EXCERPT_LIMIT:
        cut = excerpt[-_SCENE_EXCERPT_LIMIT:]
        # A mid-line cut leaves a partial first line; trim to the first
        # newline so the excerpt starts on a complete message line.  When
        # the cut lands exactly on a line boundary, keep all 3,000 chars.
        if excerpt[-_SCENE_EXCERPT_LIMIT - 1] != "\n":
            first_newline = cut.find("\n")
            if first_newline != -1:
                cut = cut[first_newline + 1 :]
        excerpt = cut
        warnings.append("Scene excerpt exceeded 3,000 characters; only the most recent 3,000 were used.")
    return excerpt, warnings


def build_scene_prompt(messages: list[dict[str, Any]], context: Any = None) -> ImagePrompt:
    """Assemble a deterministic scene prompt from recent messages and context.

    The concatenated scene excerpt is capped at 3,000 characters (most recent
    kept).  Identity groups are rendered in a stable anchor order.
    """
    identities = list(getattr(context, "visual_identities", ()) or ()) if context is not None else []
    groups: dict[str, list[Any]] = {}
    for identity in identities:
        groups.setdefault(_identity_group_key(identity), []).append(identity)

    warnings: list[str] = []
    sections = ["Cinematic scene illustration, 16:9 composition."]
    for key in sorted(groups):
        resolved, group_warnings = _resolve_visual_fields(groups[key], None)
        warnings.extend(group_warnings)
        appearance = _appearance_lines(resolved)
        if appearance:
            sections.append("Subject visual identity:\n" + "\n".join(appearance))

    facts = _sorted_facts(context)
    facts_section = _facts_section(facts)
    if facts_section is not None:
        sections.append(facts_section)

    excerpt, excerpt_warnings = _scene_excerpt(messages)
    warnings.extend(excerpt_warnings)
    sections.append(f"Scene excerpt:\n{excerpt}")
    sections.append(_SCENE_STYLE)

    return ImagePrompt(
        positive="\n\n".join(sections),
        negative=_NEGATIVE_PROMPT,
        reference_asset_ids=_reference_asset_ids(context),
        source_fact_ids=_source_fact_ids(facts),
        warnings=list(dict.fromkeys(warnings)),
    )


__all__ = ["ImagePrompt", "build_portrait_prompt", "build_scene_prompt"]
