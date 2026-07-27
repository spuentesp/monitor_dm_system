"""Shared helper utilities for the Play chat router.

This keeps `chat.py` focused on route orchestration while the pure message,
session-state, OOC, and tone helpers live in a smaller, testable module.
"""

from __future__ import annotations

import logging
import re as _re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

VALID_TONES = frozenset({"dramatic", "grim", "horror", "heroic", "mystery", "adventure"})

_OOC_PATTERNS = _re.compile(
    r"\b(ooc|out of character|what (can|type|kind|sort|class|race|species|character|role|archetype)|"
    r"how (do|does|can|should|would)|who (can|could) i|what are (the|my|available)|"
    r"how (does|do) (combat|dice|roll|stat|skill|check|the game)|"
    r"what (is|are) (the|a|an)? ?(rule|mechanic|stat|attribute|skill|ability|dice|system)|"
    r"what (looks|seems|feels) (most )?(dangerous|risky|off|wrong)|"
    r"what('?s| is) (the )?(risk|danger|catch)|first impression|"
    r"before i commit|before i go in|before i board|if there's something i should know|"
    r"explain|tell me about|can (i|you)|what if i|is there a|do i have|before we (start|begin))\b",
    _re.IGNORECASE,
)
_OOC_BLOCK_RE = _re.compile(r"^\s*\(\((?P<content>.*?)\)\)\s*$", _re.IGNORECASE | _re.DOTALL)


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def make_system_message(session_id: str, content: str) -> dict[str, Any]:
    """Create a standardized system message payload."""
    return {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": "system",
        "content": content,
        "timestamp": now_iso(),
        "metadata": {},
    }


def make_gm_message(
    session_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a standardized GM message payload."""
    return {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": "gm",
        "content": content,
        "timestamp": now_iso(),
        "metadata": metadata or {},
    }


def make_player_message(
    session_id: str,
    content: str,
    *,
    timestamp: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a standardized player message payload."""
    return {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": "player",
        "content": content,
        "timestamp": timestamp or now_iso(),
        "metadata": metadata or {},
    }


def as_uuid(value: str | None) -> uuid.UUID | None:
    """Convert a string-ish value into a UUID or return `None`."""
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def get_universe_id(session: dict[str, Any]) -> uuid.UUID | None:
    """Get universe_id from session, with fallback to legacy world_id."""
    raw = session.get("universe_id") or session.get("world_id")
    return as_uuid(raw)


def get_character_id(session: dict[str, Any]) -> uuid.UUID | None:
    """Get character_id from session, with fallback to speaker_character_id."""
    raw = session.get("character_id") or session.get("speaker_character_id")
    return as_uuid(raw)


def build_session_state_payload(session: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive the compact state payload fields from a session and its messages."""
    latest_gm = next((message for message in reversed(messages) if message.get("role") == "gm"), None)
    recent_phase_sequence = [
        str(message.get("metadata", {}).get("phase"))
        for message in messages
        if message.get("role") == "gm" and message.get("metadata", {}).get("phase")
    ][-10:]
    recent_success_levels = [
        str(message.get("metadata", {}).get("success_level"))
        for message in messages
        if message.get("role") == "gm" and message.get("metadata", {}).get("success_level")
    ][-10:]
    recent_npc_stances = [
        str(
            message.get("metadata", {}).get("social_read", {}).get("stance_after")
            or message.get("metadata", {}).get("relationship_snapshot", {}).get("stance")
        )
        for message in messages
        if message.get("role") == "gm"
        and (
            message.get("metadata", {}).get("social_read", {}).get("stance_after")
            or message.get("metadata", {}).get("relationship_snapshot", {}).get("stance")
        )
    ][-10:]

    latest_metadata = latest_gm.get("metadata", {}) if latest_gm else {}
    return {
        "message_count": len(messages),
        "latest_gm_message_id": latest_gm.get("id") if latest_gm else None,
        "latest_gm_metadata": latest_metadata,
        "recent_phase_sequence": recent_phase_sequence,
        "recent_success_levels": recent_success_levels,
        "recent_npc_stances": recent_npc_stances,
        "pending_consequence": session.get("pending_consequence", {}) or {},
        "last_consequence_choice": session.get("last_consequence_choice"),
        "latest_working_state": latest_metadata.get("working_state", session.get("latest_working_state", {})) or {},
        "latest_scene_checkpoint": latest_metadata.get("scene_checkpoint", session.get("latest_scene_checkpoint", {}))
        or {},
        "latest_social_read": latest_metadata.get("social_read", session.get("latest_social_read", {})) or {},
        "latest_relationship_snapshot": latest_metadata.get(
            "relationship_snapshot",
            session.get("latest_relationship_snapshot", {}),
        )
        or {},
    }


def normalize_ooc_text(text: str) -> str:
    """Strip explicit `(( ... ))` OOC wrappers when present."""
    raw = (text or "").strip()
    match = _OOC_BLOCK_RE.match(raw)
    return (match.group("content") if match else raw).strip()


_EXACT_NUMBER_CHOICE_RE = _re.compile(r"^#?([1-9])\.?$")


async def match_consequence_choice(user_text: str, options: list[str]) -> str | None:
    """Resolve a player's follow-up into one of the offered consequence options.

    LLM-matched against the options verbatim (schema-free -- these are
    server-generated cost descriptions, not a fixed game-system vocabulary),
    replacing a bare-digit-anywhere-in-the-message regex that could pick
    an option off an unrelated number in the player's sentence (e.g. "give
    me 2 secs to think" silently "chose" option 2) and a stopword-blind
    word-overlap fallback. See the `no-brittle-patches` project rule.
    """
    stripped = (user_text or "").strip()
    if not stripped or not options:
        return None

    # A bare numbered-menu selection ("2", "#2", "2.") is a structured pick,
    # not free text needing interpretation -- same class as the "roll"/
    # "skip" exact-command precedent elsewhere in this codebase. Only the
    # ENTIRE (stripped) message being just a number counts; a number
    # anywhere inside a longer sentence does not.
    exact_number = _EXACT_NUMBER_CHOICE_RE.match(stripped)
    if exact_number:
        idx = int(exact_number.group(1)) - 1
        if 0 <= idx < len(options):
            return options[idx]

    try:
        import json

        from monitor_agents.character_creator.text_matching import OptionMatchModule

        module = OptionMatchModule()
        prediction = module(
            player_answer=stripped,
            choice_context="Choosing which consequence/cost to accept",
            available_options=json.dumps(options, default=str),
        )
        matched = str(getattr(prediction, "matched_option", "") or "").strip()
    except Exception as exc:
        logger.warning("Consequence choice LLM match failed: %s", exc)
        return None

    return matched if matched in options else None


async def resolve_pending_consequence_choice(
    session: dict[str, Any],
    user_content: str,
    *,
    save_session: Callable[[dict[str, Any]], None],
    now_fn: Callable[[], str] = now_iso,
) -> tuple[str, dict[str, Any]] | None:
    """Handle the player choosing one of the previously offered mixed-success costs."""
    pending = session.get("pending_consequence") or {}
    options = list(pending.get("options") or [])
    if not options:
        return None

    chosen = await match_consequence_choice(user_content, options)
    if chosen is None:
        prompt = "Choose one of the offered costs before we continue:\n" + "\n".join(
            f"{idx + 1}. {option}" for idx, option in enumerate(options[:3])
        )
        return (
            prompt,
            {
                "type": "consequence_choice_prompt",
                "phase": session.get("phase", "active_play"),
                "awaiting_consequence_choice": True,
                "consequence_options": options,
                "turn_id": pending.get("turn_id"),
            },
        )

    session.pop("pending_consequence", None)
    session["last_consequence_choice"] = chosen
    session["updated_at"] = now_fn()
    save_session(session)

    return (
        f"Understood — {chosen} The scene absorbs that cost, and the pressure shifts around you. What do you do next?",
        {
            "type": "consequence_choice",
            "phase": session.get("phase", "active_play"),
            "chosen_consequence": chosen,
            "awaiting_consequence_choice": False,
            "turn_id": pending.get("turn_id"),
        },
    )


def is_ooc_question(text: str) -> bool:
    """Return `True` when the player's text looks like an OOC rules/world-info question."""
    raw = (text or "").strip()
    if _OOC_BLOCK_RE.match(raw):
        return True
    return bool(_OOC_PATTERNS.search(normalize_ooc_text(raw)))


def handle_tone_command(
    content: str,
    *,
    session_id: str,
    sessions: dict[str, dict[str, Any]],
    save_session: Callable[[dict[str, Any]], None],
    now_fn: Callable[[], str] = now_iso,
) -> tuple[str, dict[str, Any]] | None:
    """Parse `/tone` and update the given session store when valid."""
    cmd = content.strip().lower()
    if not cmd.startswith("/tone"):
        return None

    parts = cmd.split()
    requested = parts[1] if len(parts) > 1 else ""
    session = sessions.get(session_id, {})
    if requested in VALID_TONES:
        session["tone"] = requested
        session["updated_at"] = now_fn()
        save_session(session)
        return (
            f"Tone shifted to **{requested}**. The GM adjusts their voice.",
            {"type": "tone_change", "tone": requested},
        )

    return (
        f"Unknown tone '{requested}'. Available tones: " + ", ".join(sorted(VALID_TONES)) + ".",
        {"type": "tone_error"},
    )


# ---------------------------------------------------------------------------
# Meta-command detection (GAP 4, GAP 2)
# ---------------------------------------------------------------------------

_META_END_SCENE_RE = _re.compile(
    r"^\s*(/end_scene|/end|\(\(end scene\)\)|\(\(end\)\))\s*$",
    _re.IGNORECASE,
)
_META_RECAP_RE = _re.compile(
    r"^\s*(/recap|\(\(recap\)\)|\(\(story so far\)\)|\(\(what happened\?\)\))\s*$",
    _re.IGNORECASE,
)
_META_TALK_TO_RE = _re.compile(
    r"^\s*/talk_to\s+(.+)$",
    _re.IGNORECASE,
)
_META_END_CONVERSATION_RE = _re.compile(
    r"^\s*(/end_talk|/end_conversation|\(\(end conversation\)\))\s*$",
    _re.IGNORECASE,
)


def is_end_scene_command(text: str) -> bool:
    """Detect explicit end-scene meta-command from the player."""
    return bool(_META_END_SCENE_RE.match((text or "").strip()))


def is_recap_command(text: str) -> bool:
    """Detect recap/story-so-far meta-command from the player."""
    return bool(_META_RECAP_RE.match((text or "").strip()))


def is_start_conversation_command(text: str) -> str | None:
    """Return the NPC name/description if the player is starting a dedicated conversation."""
    match = _META_TALK_TO_RE.match((text or "").strip())
    return match.group(1).strip() if match else None


def is_end_conversation_command(text: str) -> bool:
    """Detect end-conversation meta-command from the player."""
    return bool(_META_END_CONVERSATION_RE.match((text or "").strip()))
