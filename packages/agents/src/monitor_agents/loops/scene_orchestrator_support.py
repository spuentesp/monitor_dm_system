import re
from typing import Any

_ROLL_REQUEST_MARKER = "[ROLL REQUEST]"
_DICE_RESULT_MARKER = "[DICE RESULT]"
_PLAIN_DICE_SPEC_RE = re.compile(
    r"^(?P<amount>\d*)d(?P<sides>\d+)(?:k(?P<keep_dir>[hl])(?P<keep_n>\d+))?(?P<mod>[+-]\d+)?$",
    re.IGNORECASE,
)


def _format_dice_spec(
    modifier: int,
    *,
    roll_under: bool = False,
    roll_mode: str = "normal",
) -> str:
    """Return the client dice spec for a pending d20 check."""
    if roll_mode == "advantage":
        base = "2d20kl1" if roll_under else "2d20kh1"
    elif roll_mode == "disadvantage":
        base = "2d20kh1" if roll_under else "2d20kl1"
    else:
        base = "1d20"
    if roll_under:
        return base
    if modifier > 0:
        return f"{base}+{modifier}"
    if modifier < 0:
        return f"{base}{modifier}"
    return base


def _dice_request_from_resolution(
    resolution: dict[str, Any],
    user_content: str,
) -> dict[str, Any] | None:
    """Convert a Resolver propose_roll result into frontend prompt metadata."""
    if resolution.get("resolution_type") not in ("propose_roll", "forced_narrative_pushback"):
        return None

    try:
        modifier = int(resolution.get("modifier") or 0)
    except (TypeError, ValueError):
        modifier = 0
    stat = str(resolution.get("stat") or "relevant stat")
    dc = resolution.get("difficulty_class")
    roll_under = bool(resolution.get("roll_under"))
    roll_mode = str(resolution.get("roll_mode") or "normal")
    if roll_mode not in ("normal", "advantage", "disadvantage"):
        roll_mode = "normal"

    is_pool = (
        resolution.get("mechanic_type") == "dice_pool"
        or resolution.get("roll_type") == "pool"
        or resolution.get("pool_size") is not None
    )
    pool_extra: dict[str, Any] = {}
    if is_pool:
        try:
            pool_size = max(1, int(resolution.get("pool_size") or 1))
        except (TypeError, ValueError):
            pool_size = 1
        try:
            die_sides = max(2, int(resolution.get("pool_die_sides") or 10))
        except (TypeError, ValueError):
            die_sides = 10
        try:
            threshold = int(resolution.get("success_threshold") or dc or 6)
        except (TypeError, ValueError):
            threshold = 6
        spec = f"{pool_size}d{die_sides}"
        roll_mode = "normal"
        pool_extra = {
            "mechanic_type": "dice_pool",
            "pool_size": pool_size,
            "pool_die_sides": die_sides,
            "success_threshold": threshold,
        }
    else:
        spec = _format_dice_spec(modifier, roll_under=roll_under, roll_mode=roll_mode)

    reason = str(
        resolution.get("roll_invitation")
        or resolution.get("pushback_prompt")
        or f"{stat} check"
        or "Roll to resolve the action"
    )

    return {
        "spec": spec,
        "reason": reason,
        "stat": stat,
        "difficulty_class": dc,
        "modifier": modifier,
        "roll_under": roll_under,
        "roll_mode": roll_mode,
        **pool_extra,
        "action_type": resolution.get("action_type"),
        "intent_type": resolution.get("intent_type"),
        "risk_preview": resolution.get("risk_preview"),
        "original_action": user_content,
    }


def _parse_dice_result_message(content: str) -> dict[str, Any] | None:
    """Extract spec, rolls, and total from the websocket dice-result message."""
    if _DICE_RESULT_MARKER not in content:
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
    roll_mode: str = "normal",
) -> tuple[str, bool | None, str]:
    """Resolve the submitted roll using the pending check metadata."""
    if dc is None:
        return "success", True, "submitted roll"

    die_label = "2d20kh1" if roll_mode == "advantage" else ("2d20kl1" if roll_mode == "disadvantage" else "1d20")
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
        breakdown = f"{die_label}({natural}) <= {dc} + {modifier} = {target}"
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
        breakdown = f"{die_label}({natural}) + {modifier} = {total} vs DC {dc}"

    return level, level in {"success", "critical_success"}, breakdown


def _build_dice_resolution(
    session: dict[str, Any],
    pending: dict[str, Any],
    *,
    spec: str,
    rolls: list[int],
    total: int,
    natural: int,
    kept_rolls: list[int] | None = None,
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

    roll_mode = str(pending.get("roll_mode") or "normal")
    if roll_mode not in ("normal", "advantage", "disadvantage"):
        roll_mode = "normal"

    is_pool = pending.get("mechanic_type") == "dice_pool" or pending.get("pool_size") is not None
    success: bool | None
    if is_pool:
        try:
            threshold = int(pending.get("success_threshold") or dc or 6)
        except (TypeError, ValueError):
            threshold = 6
        if rolls:
            successes = sum(1 for r in rolls if r >= threshold)
            botches = sum(1 for r in rolls if r == 1)
        else:
            successes = max(0, total)
            botches = 0
        total = successes
        if botches > 0 and successes == 0:
            level = "critical_failure"
        elif successes >= 1:
            level = "success"
        else:
            level = "failure"
        success = level in {"success", "critical_success"}
        breakdown = f"Pool {spec} ({rolls}): {successes} successes (diff {threshold})"
    else:
        roll_under = bool(pending.get("roll_under"))
        level, success, breakdown = _success_level_from_roll(
            total=total,
            natural=natural,
            dc=dc,
            modifier=modifier,
            roll_under=roll_under,
            roll_mode=roll_mode,
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
    detail: dict[str, Any] = {
        "spec": spec,
        "total": total,
        "rolls": rolls,
        "reason": reason,
        "roll_mode": roll_mode,
    }
    if kept_rolls is not None:
        detail["kept_rolls"] = kept_rolls

    resolution = {
        "scene_id": session.get("scene_id"),
        "action_type": pending.get("action_type") or "action",
        "intent_type": pending.get("intent_type") or "action",
        "roll_type": "pool" if is_pool else "check",
        "intent_target": None,
        "requires_clarification": False,
        "stat": pending.get("stat"),
        "difficulty_class": dc,
        "attribute_value": None,
        "modifier": modifier,
        "roll_mode": roll_mode,
        "roll_total": total,
        "roll_breakdown": breakdown,
        "roll_detail": detail,
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


def _parse_pending_spec_full(spec: Any) -> tuple[int, int, int, str | None, int | None] | None:
    """Return ``(amount, sides, modifier, keep_dir, keep_n)`` for a dice spec, else ``None``."""
    match = _PLAIN_DICE_SPEC_RE.match(str(spec or "").replace(" ", ""))
    if not match:
        return None
    amount = int(match.group("amount") or 1)
    sides = int(match.group("sides"))
    if amount < 1 or sides < 2:
        return None
    raw_keep = match.group("keep_dir")
    keep_dir = raw_keep.lower() if raw_keep else None
    keep_n = int(match.group("keep_n")) if match.group("keep_n") else None
    if keep_n is not None and (keep_n < 1 or keep_n > amount):
        return None
    return amount, sides, int(match.group("mod") or 0), keep_dir, keep_n


def _parse_pending_spec(spec: Any) -> tuple[int, int, int] | None:
    """Return (amount, sides, modifier) for a plain ``NdS+M`` spec, else None."""
    parsed = _parse_pending_spec_full(spec)
    if parsed is None:
        return None
    amount, sides, mod, _, _ = parsed
    return amount, sides, mod


def _manual_roll_rejection(session: dict[str, Any], content: str) -> str | None:
    """Explain why a submitted roll can't be accepted, or None if it can.

    Only a session in the manual roll model may supply its own dice, and the
    result must be possible for the spec the server asked for. Protocol roll
    markers sent when no roll is pending are rejected instead of leaking to
    the GM as declared-outcome prose.
    """
    has_result_marker = _DICE_RESULT_MARKER in content
    has_request_marker = _ROLL_REQUEST_MARKER in content
    if not has_result_marker and not has_request_marker:
        return None

    pending = session.get("pending_dice_request")
    if not isinstance(pending, dict):
        return "No dice roll is currently pending. Describe what your character does first."

    if has_request_marker and not has_result_marker:
        return None

    if session.get("roll_model") != "manual":
        return "This session rolls on the server, so typed results aren't accepted. Tap the die to roll."

    spec = str(pending.get("spec") or "1d20")
    parsed = _parse_dice_result_message(content)
    limits = _parse_pending_spec_full(spec)
    if parsed is None or limits is None:
        return f"I couldn't read that roll. Enter your {spec} result again."

    amount, sides, modifier, keep_dir, keep_n = limits
    total = parsed["total"]
    rolls = parsed["rolls"]

    is_pool = pending.get("mechanic_type") == "dice_pool" or pending.get("pool_size") is not None
    if is_pool:
        try:
            threshold = int(pending.get("success_threshold") or pending.get("difficulty_class") or 6)
        except (TypeError, ValueError):
            threshold = 6
        if not 0 <= total <= amount:
            return f"{total} successes isn't possible on {spec}. Enter your result again."
        if rolls and (
            len(rolls) != amount
            or any(not 1 <= die <= sides for die in rolls)
            or sum(1 for die in rolls if die >= threshold) != total
        ):
            return (
                f"Those dice don't match {total} successes on {spec} "
                f"(difficulty {threshold}+). Enter your result again."
            )
        return None

    eff_dice = keep_n if keep_n is not None else amount
    if not eff_dice + modifier <= total <= eff_dice * sides + modifier:
        return f"{total} isn't possible on {spec}. Enter your result again."

    if rolls:
        if len(rolls) != amount or any(not 1 <= die <= sides for die in rolls):
            return f"Those dice don't add up to {total} on {spec}. Enter your result again."
        kept = (sorted(rolls, reverse=(keep_dir == "h"))[:keep_n]) if (keep_dir and keep_n) else rolls
        if sum(kept) + modifier != total:
            return f"Those dice don't add up to {total} on {spec}. Enter your result again."
    return None


def _resolved_roll_from_pending(
    session: dict[str, Any],
    content: str,
) -> tuple[str, dict[str, Any]] | None:
    """Manual roll model: the player supplied a die value."""
    pending = session.get("pending_dice_request")
    parsed = _parse_dice_result_message(content)
    if not isinstance(pending, dict) or not parsed or _manual_roll_rejection(session, content):
        return None

    # The server's spec is authoritative, whatever spec the message claims.
    spec = str(pending.get("spec") or "1d20")
    limits = _parse_pending_spec_full(spec)
    spec_modifier = limits[2] if limits else 0
    keep_dir = limits[3] if limits else None
    keep_n = limits[4] if limits else None
    total = int(parsed["total"])
    rolls = list(parsed.get("rolls") or [])
    kept_rolls: list[int] | None = None
    if rolls and keep_dir and keep_n:
        kept_rolls = sorted(rolls, reverse=(keep_dir == "h"))[:keep_n]
        natural = kept_rolls[0]
    else:
        natural = rolls[0] if rolls else total - spec_modifier
    narrated_input, resolution = _build_dice_resolution(
        session,
        pending,
        spec=spec,
        rolls=rolls,
        total=total,
        natural=natural,
        kept_rolls=kept_rolls,
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
    kept = list(roll.kept_rolls) if roll.kept_rolls else list(rolls)
    total = int(roll.total)
    natural = kept[0] if kept else (rolls[0] if rolls else total)
    return _build_dice_resolution(
        session,
        pending,
        spec=spec,
        rolls=rolls,
        total=total,
        natural=natural,
        kept_rolls=kept,
    )
