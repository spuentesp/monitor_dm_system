"""Tracks & conditions — track management, threshold evaluation, condition triggers.

All functions are pure: they receive a ``SystemData`` snapshot
(and any extra parameters) and return plain data structures.
"""

from __future__ import annotations

import re as _re
from typing import Any, Dict, List, Optional

from ._types import SystemData


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_tracks(sd: SystemData) -> List[Dict[str, Any]]:
    """Return all track definitions from the game system."""
    return list(sd.tracks)


def get_track(sd: SystemData, name: str) -> Optional[Dict[str, Any]]:
    """Return a specific track definition by name (case-insensitive)."""
    return sd.track_by_name.get(name.lower())


def evaluate_track_threshold(
    sd: SystemData,
    track_name: str,
    current_value: int,
    max_value: Optional[int] = None,
) -> Dict[str, Any]:
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

    triggered: List[str] = []
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


def get_conditions(sd: SystemData) -> List[Dict[str, Any]]:
    """Return all condition definitions from the game system."""
    return list(sd.conditions)


def get_condition(sd: SystemData, name: str) -> Optional[Dict[str, Any]]:
    """Return a specific condition definition by name."""
    return sd.condition_by_name.get(name.lower())


def check_condition_triggers(
    sd: SystemData,
    event: str,
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Check which conditions would be triggered by an event."""
    triggered: List[Dict[str, Any]] = []
    existing = set(c.lower() for c in context.get("active_conditions", []))

    for cond in sd.conditions:
        cond_name = cond.get("name", "")
        if cond_name.lower() in existing:
            continue
        if not cond.get("stackable", False):
            if cond_name.lower() in existing:
                continue

        trigger = cond.get("trigger", "")
        if _event_matches_trigger(event, trigger, context):
            triggered.append(cond)

    return triggered


def evaluate_scenery_and_conditions(
    sd: SystemData,
    context: Dict[str, Any] | None,
    user_input: str,
    roll_mode: str = "normal",
) -> Dict[str, Any]:
    """Evaluate conditions and scenery rules against the active system data."""
    context = context or {}
    entities = context.get("entities", []) or []

    actor_entity = None
    location_entity = None
    for entity in entities:
        if entity.get("entity_type") == "location":
            location_entity = entity
        elif not actor_entity:
            actor_entity = entity

    conditions = []
    if actor_entity:
        props = actor_entity.get("properties", {}) or {}
        raw_conds = None
        for key in ["conditions", "condition_tags", "active_conditions"]:
            if key in props:
                raw_conds = props[key]
                break
            if key in actor_entity:
                raw_conds = actor_entity[key]
                break

        if not raw_conds and "attributes" in props:
            attrs = props.get("attributes", {}) or {}
            for key in ["conditions", "condition_tags", "active_conditions"]:
                if key in attrs:
                    raw_conds = attrs[key]
                    break

        if isinstance(raw_conds, list):
            conditions = [str(c).lower().strip() for c in raw_conds]
        elif isinstance(raw_conds, str):
            conditions = [c.strip().lower() for c in raw_conds.split(",") if c.strip()]

    location_desc = ""
    location_tags = []
    if location_entity:
        loc_props = location_entity.get("properties", {}) or {}
        location_desc = str(
            loc_props.get("description", "") or location_entity.get("description", "")
        ).lower()
        raw_tags = (
            loc_props.get("state_tags")
            or loc_props.get("tags")
            or location_entity.get("state_tags")
            or location_entity.get("tags")
            or []
        )
        if isinstance(raw_tags, list):
            location_tags = [str(t).lower().strip() for t in raw_tags]
        elif isinstance(raw_tags, str):
            location_tags = [t.strip().lower() for t in raw_tags.split(",") if t.strip()]

    cond_modifier = 0
    has_advantage = False
    has_disadvantage = False

    for c in conditions:
        cond_def = sd.condition_by_name.get(c)
        if cond_def:
            mod = cond_def.get("roll_modifier")
            if mod:
                cond_modifier += int(mod)
            mode_override = cond_def.get("roll_mode_override")
            if mode_override == "advantage":
                has_advantage = True
            elif mode_override == "disadvantage":
                has_disadvantage = True

    scenery_modifier = 0
    scenery_reasons = []
    user_input_lower = user_input.lower()

    for rule in sd.scenery_rules:
        keyword = rule.get("keyword", "").lower()
        if keyword in location_tags or keyword in location_desc:
            verbs = rule.get("trigger_verbs", [])
            if not verbs or any(verb.lower() in user_input_lower for verb in verbs):
                mod = rule.get("roll_modifier")
                if mod:
                    scenery_modifier += int(mod)
                mode_override = rule.get("roll_mode_override")
                if mode_override == "advantage":
                    has_advantage = True
                elif mode_override == "disadvantage":
                    has_disadvantage = True
                reason = rule.get("reason_text")
                if reason:
                    scenery_reasons.append(reason)

    req_advantage = roll_mode == "advantage"
    req_disadvantage = roll_mode == "disadvantage"

    final_advantage = has_advantage or req_advantage
    final_disadvantage = has_disadvantage or req_disadvantage

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


def _eval_track_max(track: Dict[str, Any]) -> Optional[int]:
    """Evaluate max_formula if present, otherwise use max_value."""
    max_formula = track.get("max_formula")
    if max_formula:
        try:
            return int(eval(str(max_formula), {"__builtins__": {}}, {}))  # noqa: S307
        except Exception:  # noqa: BLE001
            pass
    return track.get("max_value")


def _event_matches_trigger(
    event: str,
    trigger: str,
    context: Dict[str, Any],
) -> bool:
    """Check if an event matches a condition's trigger pattern."""
    if not trigger:
        return False
    trigger_lower = trigger.lower()
    event_lower = event.lower()

    if event_lower in trigger_lower or trigger_lower in event_lower:
        return True

    for track_name, track_val in context.get("track_values", {}).items():
        if track_name.lower() in trigger_lower:
            nums = _re.findall(r"(?:below|under|less than)\s*(\d+)", trigger_lower)
            if nums and track_val < int(nums[0]):
                return True
            nums = _re.findall(r"(?:above|over|more than|exceeds?)\s*(\d+)", trigger_lower)
            if nums and track_val > int(nums[0]):
                return True
            nums = _re.findall(r"(?:(?:drops?|falls?)\s*(?:to|below|at)?\s*)(\d+)", trigger_lower)
            if nums and track_val <= int(nums[0]):
                return True

    return False
