"""Tracks & conditions — track management, threshold evaluation, condition triggers.

All functions are pure: they receive a ``SystemData`` snapshot
(and any extra parameters) and return plain data structures.

TRIGGER MATCHING — SEMANTIC, NOT KEYWORD
----------------------------------------
The previous version matched event/trigger strings with substring containment
(``"damage taken" in "take nasty damage"``) and checked ``trigger_verbs``
against player input via ``any(verb in user_input)``. That can't tell
``take fire damage`` from ``take a fire break`` — same failure mode that
motivated the semantic roll / action / intent classifiers.

Now both trigger-match surfaces embed their text and pick the nearest-match
candidate above a similarity threshold. The world's own conditions + scenery
rules are the classes; nothing is hardcoded English vocabulary.

Numeric thresholds (``below 5``, ``above 10``, ``drops to 0``) are STRUCTURED
data, not heuristics — they stay as a small explicit parser.

FAIL LOUD
---------
Both surfaces embed via the data-layer ``embed_text`` /
``embed_batch``; they raise :class:`EmbeddingProviderError` when the provider
is unavailable, and we do NOT silently fall back to substring matching.
"""

from __future__ import annotations

import hashlib
import re as _re
from typing import Any

import structlog

from ._types import SystemData

logger = structlog.get_logger()


_TRIGGER_MIN_SIMILARITY = 0.40  # below this, an event doesn't "match" a trigger


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_tracks(sd: SystemData) -> list[dict[str, Any]]:
    """Return all track definitions from the game system."""
    return list(sd.tracks)


def get_track(sd: SystemData, name: str) -> dict[str, Any] | None:
    """Return a specific track definition by name (case-insensitive)."""
    return sd.track_by_name.get(name.lower())


def evaluate_track_threshold(
    sd: SystemData,
    track_name: str,
    current_value: int,
    max_value: int | None = None,
) -> dict[str, Any]:
    """Evaluate threshold effects for a track at its current value."""
    track = sd.track_by_name.get(track_name.lower())
    if not track:
        return {
            "track": track_name,
            "value": current_value,
            "thresholds_triggered": [],
            "depleted_effect": None,
            "maxed_effect": None,
        }

    triggered: list[str] = []
    for te in track.get("threshold_effects") or []:
        # Schema (ThresholdEffect) keys: value / direction / effect.
        # Tolerate the legacy threshold/label keys for any un-migrated data.
        raw_value = te.get("value")
        if raw_value is None:
            raw_value = te.get("threshold")
        if raw_value is None:
            continue
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        effect = te.get("effect") or te.get("label") or ""
        if not effect:
            continue
        direction = str(te.get("direction") or "at_or_below")
        if direction == "at_or_above":
            crossed = current_value >= value
        elif direction == "exactly":
            crossed = current_value == value
        else:  # at_or_below (default)
            crossed = current_value <= value
        if crossed:
            triggered.append(effect)

    depleted_effect = None
    if current_value <= (track.get("min_value") or 0) and track.get("depleted_effect"):
        depleted_effect = track["depleted_effect"]

    maxed_effect = None
    track_max = max_value or track.get("max_value") or _eval_track_max(track)
    if track_max and current_value >= track_max and track.get("maxed_effect"):
        maxed_effect = track["maxed_effect"]

    return {
        "track": track_name,
        "value": current_value,
        "thresholds_triggered": triggered,
        "depleted_effect": depleted_effect,
        "maxed_effect": maxed_effect,
    }


def get_conditions(sd: SystemData) -> list[dict[str, Any]]:
    """Return all condition definitions from the game system."""
    return list(sd.conditions)


def get_condition(sd: SystemData, name: str) -> dict[str, Any] | None:
    """Return a specific condition definition by name."""
    return sd.condition_by_name.get(name.lower())


async def check_condition_triggers(
    sd: SystemData,
    event: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check which conditions would be triggered by an event (semantic match).

    ``event`` is embedded once and compared (cosine) to each condition's
    ``trigger`` text. Numeric thresholds inside the trigger text (``below 5``,
    ``drops to 0``) still act as structured guards — a trigger that names a
    threshold only fires when the corresponding track value crossed it.
    """
    existing = {c.lower() for c in context.get("active_conditions", [])}
    # Include a condition when it has a name AND either it's stackable (can
    # re-trigger even while active) or it isn't already active. The earlier
    # form ANDed a hard ``not in existing`` in front, which made the
    # ``stackable`` branch dead code — stackable conditions could never
    # re-fire once active.
    candidates = [
        c
        for c in sd.conditions
        if c.get("name") and (c.get("stackable", False) or c.get("name", "").lower() not in existing)
    ]
    if not candidates or not (event or "").strip():
        return []

    trigger_texts = [str(c.get("trigger") or "").strip() or c.get("name", "") for c in candidates]

    from monitor_data.retrieval import default_retrieval_service

    retriever = default_retrieval_service()
    # Trigger texts are stable per system → cache their vectors so only the
    # per-turn event is re-embedded (scenery below stays uncached: its anchors
    # can fold in per-turn user input).
    trigger_key = "condition_triggers:" + hashlib.sha1("\x00".join(trigger_texts).encode("utf-8")).hexdigest()
    scored = await retriever.nearest(event, trigger_texts, top_k=len(trigger_texts), candidates_key=trigger_key)
    score_by_index = {s.index: s.score for s in scored}

    triggered: list[dict[str, Any]] = []
    for i, (cand, trigger_text) in enumerate(zip(candidates, trigger_texts, strict=False)):
        if not trigger_text:
            continue
        if score_by_index.get(i, 0.0) < _TRIGGER_MIN_SIMILARITY:
            continue
        if not _numeric_threshold_passed(trigger_text, context):
            continue
        triggered.append(cand)

    return triggered


def _collect_actor_conditions(context: dict[str, Any] | None) -> list[str]:
    """Pull the active condition list from the context (3 possible shapes)."""
    entities = (context or {}).get("entities", []) or []
    actor_entity = None
    for entity in entities:
        if entity.get("entity_type") != "location" and actor_entity is None:
            actor_entity = entity

    if not actor_entity:
        return []

    props = actor_entity.get("properties", {}) or {}
    raw_conds: Any = None
    for key in ("conditions", "condition_tags", "active_conditions"):
        if key in props:
            raw_conds = props[key]
            break
        if key in actor_entity:
            raw_conds = actor_entity[key]
            break

    if raw_conds is None and "attributes" in props:
        for key in ("conditions", "condition_tags", "active_conditions"):
            if key in (props.get("attributes") or {}):
                raw_conds = props["attributes"][key]
                break

    if isinstance(raw_conds, list):
        return [str(c).lower().strip() for c in raw_conds]
    if isinstance(raw_conds, str):
        return [c.strip().lower() for c in raw_conds.split(",") if c.strip()]
    return []


def _collect_location(
    context: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Return ``(location_description, location_tags)`` from the scene context."""
    entities = (context or {}).get("entities", []) or []
    for entity in entities:
        if entity.get("entity_type") == "location":
            props = entity.get("properties", {}) or {}
            description = str(props.get("description", "") or entity.get("description", "")).lower()
            raw_tags = (
                props.get("state_tags") or props.get("tags") or entity.get("state_tags") or entity.get("tags") or []
            )
            if isinstance(raw_tags, list):
                tags = [str(t).lower().strip() for t in raw_tags]
            elif isinstance(raw_tags, str):
                tags = [t.strip().lower() for t in raw_tags.split(",") if t.strip()]
            else:
                tags = []
            return description, tags
    return "", []


def _condition_modifiers(sd: SystemData, conditions: list[str]) -> tuple[int, bool, bool]:
    """Sum roll modifiers + advantage/disadvantage flags from active conditions."""
    cond_modifier = 0
    has_advantage = False
    has_disadvantage = False
    for c in conditions:
        cond_def = sd.condition_by_name.get(c)
        if not cond_def:
            continue
        mod = cond_def.get("roll_modifier")
        if mod:
            cond_modifier += int(mod)
        mode = cond_def.get("roll_mode_override")
        if mode == "advantage":
            has_advantage = True
        elif mode == "disadvantage":
            has_disadvantage = True
    return cond_modifier, has_advantage, has_disadvantage


async def _scenery_modifiers(
    sd: SystemData,
    location_desc: str,
    location_tags: list[str],
    user_input: str,
) -> tuple[int, list[str], bool, bool]:
    """Compute scenery rule modifiers by semantic match of user input to rule triggers.

    Each scenery rule carries ``keyword`` (matched against location tags/desc —
    structural, not heuristic) plus optional ``trigger_verbs`` (now embedded as
    short anchors). A rule contributes when its keyword matches the location
    AND its trigger phrases are close enough to the user input in embedding
    space. Returns ``(total_modifier, reasons, has_advantage, has_disadvantage)``.
    """
    tag_set = set(location_tags)
    total = 0
    reasons: list[str] = []
    has_advantage = False
    has_disadvantage = False
    user_input_text = (user_input or "").strip()
    if not user_input_text:
        return total, reasons, has_advantage, has_disadvantage

    applicable: list[dict[str, Any]] = []
    rule_anchor_texts: list[str] = []
    for rule in sd.scenery_rules:
        keyword = rule.get("keyword", "").lower()
        if not keyword or (keyword not in tag_set and keyword not in location_desc):
            continue
        verbs = rule.get("trigger_verbs", []) or []
        anchor_text = (
            " ".join(str(v) for v in verbs) if verbs else user_input_text
        )  # empty-verbs rule fires on any user action
        applicable.append(rule)
        rule_anchor_texts.append(anchor_text)

    if not applicable:
        return total, reasons, has_advantage, has_disadvantage

    from monitor_data.retrieval import default_retrieval_service

    retriever = default_retrieval_service()
    scored = await retriever.nearest(user_input_text, rule_anchor_texts, top_k=len(rule_anchor_texts))
    score_by_index = {s.index: s.score for s in scored}

    for i, rule in enumerate(applicable):
        sim = score_by_index.get(i, 0.0)
        # When trigger_verbs is empty the rule is "always-on" for this location.
        trigger_verbs = rule.get("trigger_verbs", []) or []
        if trigger_verbs and sim < _TRIGGER_MIN_SIMILARITY:
            continue
        mod = rule.get("roll_modifier")
        if mod:
            total += int(mod)
        mode = rule.get("roll_mode_override")
        if mode == "advantage":
            has_advantage = True
        elif mode == "disadvantage":
            has_disadvantage = True
        reason = rule.get("reason_text")
        if reason:
            reasons.append(reason)

    return total, reasons, has_advantage, has_disadvantage


async def evaluate_scenery_and_conditions(
    sd: SystemData,
    context: dict[str, Any] | None,
    user_input: str,
    roll_mode: str = "normal",
) -> dict[str, Any]:
    """Evaluate conditions and scenery rules against the active system data.

    Conditions are pulled from the actor entity as before (structural, not a
    heuristic). Scenery-rule modifiers are summed only when the player input
    is semantically close to a rule's trigger verbs (or always-on if the rule
    declares none).
    """
    conditions = _collect_actor_conditions(context)
    location_desc, location_tags = _collect_location(context)
    cond_modifier, cond_adv, cond_dis = _condition_modifiers(sd, conditions)
    scenery_modifier, scenery_reasons, scenery_adv, scenery_dis = await _scenery_modifiers(
        sd, location_desc, location_tags, user_input
    )

    has_advantage = cond_adv or scenery_adv
    has_disadvantage = cond_dis or scenery_dis

    req_adv = roll_mode == "advantage"
    req_dis = roll_mode == "disadvantage"
    final_advantage = has_advantage or req_adv
    final_disadvantage = has_disadvantage or req_dis

    if final_advantage and final_disadvantage:
        combined_roll_mode = "normal"
    elif final_advantage:
        combined_roll_mode = "advantage"
    elif final_disadvantage:
        combined_roll_mode = "disadvantage"
    else:
        combined_roll_mode = "normal"

    return {
        "total_modifier": cond_modifier + scenery_modifier,
        "cond_modifier": cond_modifier,
        "scenery_modifier": scenery_modifier,
        "roll_mode": combined_roll_mode,
        "has_advantage": has_advantage,
        "has_disadvantage": has_disadvantage,
        "reasons": scenery_reasons,
        "conditions": conditions,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _eval_track_max(track: dict[str, Any]) -> int | None:
    max_formula = track.get("max_formula")
    if max_formula:
        try:
            return int(eval(str(max_formula), {"__builtins__": {}}, {}))
        except Exception:
            pass
    return track.get("max_value")


# ---------- Numeric threshold parsing (structured, not heuristic) ----------


_BELOW_RE = _re.compile(r"(?:below|under|less than)\s*(\d+)")
_ABOVE_RE = _re.compile(r"(?:above|over|more than|exceeds?)\s*(\d+)")
_DROP_RE = _re.compile(r"(?:(?:drops?|falls?)\s*(?:to|below|at)?\s*)(\d+)")


def _numeric_threshold_passed(trigger_text: str, context: dict[str, Any]) -> bool:
    """True when the trigger's numeric threshold (if any) is satisfied.

    Pure-data parsing — looks up ``track_values`` in the context to check
    whether a named threshold in the trigger text is currently crossed.
    Returns True for triggers without any numeric threshold.
    """
    track_values: dict[str, Any] = context.get("track_values", {}) or {}
    track_keys = {k.lower(): k for k in track_values}
    trigger_lower = trigger_text.lower()

    matched_track: str | None = None
    for track_lower in track_keys:
        if track_lower in trigger_lower:
            matched_track = track_lower
            break
    if matched_track is None:
        return True  # no named track in the trigger — threshold constraint doesn't apply

    val = track_values[track_keys[matched_track]]
    try:
        num = int(val)
    except (TypeError, ValueError):
        return False

    m = _BELOW_RE.search(trigger_lower)
    if m and num < int(m.group(1)):
        return True
    m = _ABOVE_RE.search(trigger_lower)
    if m and num > int(m.group(1)):
        return True
    m = _DROP_RE.search(trigger_lower)
    if m and num <= int(m.group(1)):
        return True

    # If the trigger mentions both the track AND has *only* numeric clauses,
    # treat any threshold as the gate (don't fire outside a threshold).
    return not (_BELOW_RE.search(trigger_lower) or _ABOVE_RE.search(trigger_lower) or _DROP_RE.search(trigger_lower))
