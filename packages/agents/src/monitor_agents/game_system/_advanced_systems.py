"""Advanced systems — tiered abilities, damage, action economy, recovery, advancement, resolution.

All functions are pure: they receive a ``SystemData`` snapshot
(and any extra parameters) and return plain data structures.
"""

from __future__ import annotations

import re as _re
from contextlib import suppress
from typing import Any, Dict, List, Optional

from ._types import SystemData


# ---------------------------------------------------------------------------
# Tiered Ability Systems (Disciplines, Spell Schools, Mutations)
# ---------------------------------------------------------------------------


def get_tiered_systems(sd: SystemData) -> List[Dict[str, Any]]:
    """Return all tiered ability system definitions."""
    return list(sd.tiered_abilities)


def get_tiered_system(sd: SystemData, name: str) -> Optional[Dict[str, Any]]:
    """Return a specific tiered ability system (e.g. 'Protean', 'Evocation')."""
    return sd.tiered_by_name.get(name.lower())


def get_available_tiers(
    sd: SystemData,
    system_name: str,
    current_access: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get tiers available to a character for a tiered ability system."""
    system = sd.tiered_by_name.get(system_name.lower())
    if not system:
        return []

    restriction = system.get("access_restriction", "")
    if restriction and current_access is not None:
        restricted_to = [r.strip().lower() for r in restriction.split(",")]
        has_access = any(a.lower() in restricted_to for a in current_access)
        if not has_access:
            return []

    return system.get("tiers") or []


# ---------------------------------------------------------------------------
# Damage Model
# ---------------------------------------------------------------------------


def get_damage_model(sd: SystemData) -> Optional[Dict[str, Any]]:
    """Return the damage model (Bashing/Lethal/Aggravated/etc)."""
    return sd.damage_model


def get_damage_types(sd: SystemData) -> List[Dict[str, Any]]:
    """Return available damage types."""
    if not sd.damage_model:
        return []
    return sd.damage_model.get("damage_types") or []


def apply_damage(
    sd: SystemData,
    damage_type: str,
    amount: int,
    current_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply damage of a given type and return updated state."""
    from ._tracks_conditions import _eval_track_max

    result: Dict[str, Any] = {
        "damage_applied": amount,
        "track_updates": {},
        "conditions_triggered": [],
        "incapacitated": False,
        "dead": False,
    }

    if not sd.damage_model:
        hp = current_state.get("HP", current_state.get("Hit Points", 0))
        result["track_updates"]["HP"] = max(0, hp - amount)
        return result

    damage_track = sd.damage_model.get("damage_track") or "HP"
    current_val = current_state.get(damage_track, 0)

    for dt in sd.damage_model.get("damage_types") or []:
        if dt.get("name", "").lower() == damage_type.lower():
            break

    new_val = current_val + amount
    result["track_updates"][damage_track] = new_val

    inc_at = sd.damage_model.get("incapacitated_at")
    if inc_at is not None:
        try:
            threshold = int(inc_at)
            if new_val >= threshold:
                result["incapacitated"] = True
        except (ValueError, TypeError):
            pass

    death_cond = sd.damage_model.get("death_condition")
    if death_cond:
        death_lower = str(death_cond).lower()
        if "aggravated" in death_lower and damage_type.lower() == "aggravated":
            if new_val >= (sd.damage_model.get("incapacitated_at") or 999):
                result["dead"] = True
        elif "max" in death_lower and "damage" in death_lower:
            track_max = _eval_track_max(sd.track_by_name.get(damage_track.lower()) or {})
            if track_max and new_val >= track_max:
                result["dead"] = True

    return result


# ---------------------------------------------------------------------------
# Action Economy
# ---------------------------------------------------------------------------


def get_action_economy(sd: SystemData) -> Optional[Dict[str, Any]]:
    """Return action economy definition (actions per turn, initiative model)."""
    return sd.action_economy


def get_action_types(sd: SystemData) -> List[Dict[str, Any]]:
    """Return available action types (Standard, Bonus, Reaction, etc.)."""
    if not sd.action_economy:
        return []
    return sd.action_economy.get("action_types") or []


# ---------------------------------------------------------------------------
# Recovery Model
# ---------------------------------------------------------------------------


def get_recovery_model(sd: SystemData) -> Optional[Dict[str, Any]]:
    """Return recovery model (Long Rest, Short Rest, etc.)."""
    return sd.recovery


def apply_recovery(
    sd: SystemData,
    event_name: str,
    current_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply a recovery event and return updated resource/track values."""
    from ._tracks_conditions import _eval_track_max

    result: Dict[str, Any] = {"event": event_name, "restores": {}, "conditions_removed": []}

    if not sd.recovery:
        return result

    for rev in sd.recovery.get("events") or []:
        if rev.get("name", "").lower() == event_name.lower():
            for restore in rev.get("restores") or []:
                target = restore.get("track") or restore.get("resource")
                if target:
                    amount = restore.get("amount") or restore.get("formula")
                    current = current_state.get(target, 0)
                    if isinstance(amount, (int, float)):
                        result["restores"][target] = current + int(amount)
                    elif isinstance(amount, str) and amount == "full":
                        track = sd.track_by_name.get(target.lower()) or {}
                        max_val = track.get("max_value") or _eval_track_max(track)
                        result["restores"][target] = max_val or current
            break

    return result


# ---------------------------------------------------------------------------
# Advancement Model
# ---------------------------------------------------------------------------


def get_advancement_model(sd: SystemData) -> Optional[Dict[str, Any]]:
    """Return advancement model (XP, levels, progression)."""
    return sd.advancement


# ---------------------------------------------------------------------------
# Resolution Mechanics
# ---------------------------------------------------------------------------


def get_resolution_mechanics(sd: SystemData) -> List[Dict[str, Any]]:
    """Return specialized resolution mechanics."""
    return list(sd.resolution_mechanics)


def find_resolution_mechanic(
    sd: SystemData,
    context: str,
) -> Optional[Dict[str, Any]]:
    """Find a resolution mechanic matching the given context."""
    context_lower = context.lower()
    for rm in sd.resolution_mechanics:
        rm_type = (rm.get("mechanic_type") or "").lower()
        if context_lower in rm_type:
            return rm
        tags = [t.lower() for t in (rm.get("tags") or rm.get("mechanic_type") or "").split(",")]
        if any(context_lower in t for t in tags):
            return rm
    return None


# ---------------------------------------------------------------------------
# Initial track state builder (for character creation and scene seed)
# ---------------------------------------------------------------------------


def build_initial_track_state(
    sd: SystemData,
    stats: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Build initial state for all tracks defined in the game system."""

    result: Dict[str, Any] = {
        "tracks": {},
        "track_maxes": {},
        "active_conditions": [],
        "action_economy": {},
    }
    stats = stats or {}

    for track in sd.tracks:
        name = track.get("name", "")
        if not name:
            continue

        default = track.get("default_value")
        max_formula = track.get("max_formula")
        max_val = track.get("max_value")

        if max_formula:
            resolved = str(max_formula)
            for stat_abbr, val in stats.items():
                resolved = _re.sub(
                    rf"\b{_re.escape(stat_abbr)}\b",
                    str(val),
                    resolved,
                    flags=_re.IGNORECASE,
                )
            with suppress(Exception):
                max_val = int(eval(resolved, {"__builtins__": {}}, {}))  # noqa: S307

        if default is not None:
            current = default
        elif track.get("track_type") in ("resource", "stress", "advancement"):
            current = max_val or 0
        else:
            current = track.get("min_value", 0)

        result["tracks"][name] = current
        if max_val is not None:
            result["track_maxes"][name] = max_val

    if sd.action_economy:
        for at in sd.action_economy.get("action_types") or []:
            at_name = at.get("name", "")
            count = at.get("count_per_turn", 1)
            if at_name:
                result["action_economy"][at_name] = count

    return result
