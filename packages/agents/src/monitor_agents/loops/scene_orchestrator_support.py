import re
from typing import Any

_ROLL_REQUEST_MARKER = "[ROLL REQUEST]"


def _format_dice_spec(modifier: int, *, roll_under: bool = False) -> str:
    """Return the client dice spec for a pending d20 check."""
    if roll_under:
        return "1d20"
    if modifier > 0:
        return f"1d20+{modifier}"
    if modifier < 0:
        return f"1d20{modifier}"
    return "1d20"


def _dice_request_from_resolution(
    resolution: dict[str, Any],
    user_content: str,
) -> dict[str, Any] | None:
    """Convert a Resolver propose_roll result into frontend prompt metadata."""
    if resolution.get("resolution_type") != "propose_roll":
        return None

    try:
        modifier = int(resolution.get("modifier") or 0)
    except (TypeError, ValueError):
        modifier = 0
    stat = str(resolution.get("stat") or "relevant stat")
    dc = resolution.get("difficulty_class")
    roll_under = bool(resolution.get("roll_under"))
    spec = _format_dice_spec(modifier, roll_under=roll_under)
    reason = str(resolution.get("roll_invitation") or f"{stat} check" or "Roll to resolve the action")

    return {
        "spec": spec,
        "reason": reason,
        "stat": stat,
        "difficulty_class": dc,
        "modifier": modifier,
        "roll_under": roll_under,
        "action_type": resolution.get("action_type"),
        "intent_type": resolution.get("intent_type"),
        "risk_preview": resolution.get("risk_preview"),
        "original_action": user_content,
    }


def _parse_dice_result_message(content: str) -> dict[str, Any] | None:
    """Extract spec, rolls, and total from the websocket dice-result message."""
    if "[DICE RESULT]" not in content:
        return None
    match = re.search(
        r"rolled\s+(?P<spec>\S+)(?:\s+\[(?P<rolls>[^\]]*)\])?\s*=\s*(?P<total>-?\d+)",
        content,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    rolls_raw = match.group("rolls") or ""
    rolls = [int(part.strip()) for part in rolls_raw.split(",") if part.strip().lstrip("-").isdigit()]
    return {
        "spec": match.group("spec"),
        "rolls": rolls,
        "total": int(match.group("total")),
    }


def _success_level_from_roll(
    *,
    total: int,
    natural: int,
    dc: int | None,
    modifier: int,
    roll_under: bool,
) -> tuple[str, bool | None, str]:
    """Resolve the submitted roll using the pending check metadata."""
    if dc is None:
        return "success", True, "submitted roll"

    if roll_under:
        target = dc + modifier
        if natural == 1:
            level = "critical_success"
        elif natural == 20:
            level = "critical_failure"
        elif natural <= target:
            level = "success"
        elif natural <= target + 2:
            level = "partial_success"
        else:
            level = "failure"
        breakdown = f"1d20({natural}) <= {dc} + {modifier} = {target}"
    else:
        if natural == 20:
            level = "critical_success"
        elif natural == 1:
            level = "critical_failure"
        elif total >= dc:
            level = "success"
        elif total >= dc - 2:
            level = "partial_success"
        else:
            level = "failure"
        breakdown = f"1d20({natural}) + {modifier} = {total} vs DC {dc}"

    return level, level in {"success", "critical_success"}, breakdown


def _build_dice_resolution(
    session: dict[str, Any],
    pending: dict[str, Any],
    *,
    spec: str,
    rolls: list[int],
    total: int,
    natural: int,
) -> tuple[str, dict[str, Any]]:
    """Assemble a Resolver-compatible dice resolution from a rolled result."""
    try:
        modifier = int(pending.get("modifier") or 0)
    except (TypeError, ValueError):
        modifier = 0
    dc_raw = pending.get("difficulty_class")
    try:
        dc = int(dc_raw) if dc_raw is not None else None
    except (TypeError, ValueError):
        dc = None

    roll_under = bool(pending.get("roll_under"))
    level, success, breakdown = _success_level_from_roll(
        total=total,
        natural=natural,
        dc=dc,
        modifier=modifier,
        roll_under=roll_under,
    )
    effects = ["momentum_gained" if success else "setback", "fiction_advances"]
    pressure = {
        "critical_success": "surging",
        "success": "steady",
        "partial_success": "rising",
        "failure": "high",
        "critical_failure": "spiking",
    }.get(level, "steady")

    reason = str(pending.get("reason") or pending.get("stat") or spec)
    resolution = {
        "scene_id": session.get("scene_id"),
        "action_type": pending.get("action_type") or "action",
        "intent_type": pending.get("intent_type") or "action",
        "roll_type": "check",
        "intent_target": None,
        "requires_clarification": False,
        "stat": pending.get("stat"),
        "difficulty_class": dc,
        "attribute_value": None,
        "modifier": modifier,
        "roll_total": total,
        "roll_breakdown": breakdown,
        "roll_detail": {
            "spec": spec,
            "total": total,
            "rolls": rolls,
            "reason": reason,
        },
        "resolution_type": "dice",
        "forced_narrative": False,
        "success": success,
        "success_level": level,
        "effects": effects,
        "risk_preview": pending.get("risk_preview"),
        "consequence_options": [],
        "requires_player_choice": False,
        "narrative_pressure": pressure,
        "proposals": [],
        "roll_necessity": "accepted_roll",
    }
    narrated_input = str(pending.get("original_action") or "The pending action")
    return narrated_input, resolution


def _resolved_roll_from_pending(
    session: dict[str, Any],
    content: str,
) -> tuple[str, dict[str, Any]] | None:
    """Manual roll model: the player supplied a die value."""
    pending = session.get("pending_dice_request")
    parsed = _parse_dice_result_message(content)
    if not isinstance(pending, dict) or not parsed:
        return None

    try:
        modifier = int(pending.get("modifier") or 0)
    except (TypeError, ValueError):
        modifier = 0
    total = int(parsed["total"])
    rolls = list(parsed.get("rolls") or [])
    natural = rolls[0] if rolls else max(1, total - modifier)
    narrated_input, resolution = _build_dice_resolution(
        session, pending, spec=parsed["spec"], rolls=rolls, total=total, natural=natural
    )
    return f"{narrated_input}\n\n{content}", resolution


def _server_roll_from_pending(
    session: dict[str, Any],
    content: str,
) -> tuple[str, dict[str, Any]] | None:
    """Server-authoritative roll model."""
    pending = session.get("pending_dice_request")
    if not isinstance(pending, dict) or _ROLL_REQUEST_MARKER not in content:
        return None

    from monitor_data.utils.dice import roll_dice

    spec = str(pending.get("spec") or "1d20")
    try:
        roll = roll_dice(spec)
    except ValueError:
        roll = roll_dice("1d20")
    rolls = list(roll.rolls)
    total = int(roll.total)
    natural = roll.kept_rolls[0] if roll.kept_rolls else (rolls[0] if rolls else total)
    return _build_dice_resolution(session, pending, spec=spec, rolls=rolls, total=total, natural=natural)
