"""
Chat router — session management, message routing, and WebSocket streaming.

Delegates to sibling modules:
  chat_schemas    — Pydantic request/response models
  chat_persistence — MongoDB session/message I/O
  chat_game_system — game system doc resolution
  chat_support    — shared helpers (messages, tones, OOC detection)
  chat_ws         — WebSocket subscriber registry & fanout
  chat_opening    — story/scene bootstrap & GM opening messages
  chat_loops      — turn runners (pre-play, world architect, scene loop)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from monitor_agents.dspy_runtime import stream_callback_var
from monitor_agents.loops.preplay_finalize import finalize_preplay
from monitor_agents.loops.preplay_orchestrator import (
    start_character_interview,
    start_story_agreements,
)
from monitor_agents.loops.preplay_support import is_begin_story_command

from .chat_game_system import (
    _GSR_AVAILABLE,
)
from .chat_game_system import (
    get_benchmark_config as _get_benchmark_config,
)
from .chat_game_system import (
    resolve_universe_system_binding as _resolve_universe_system_binding,
)
from .chat_game_system import (
    session_game_system_doc as _session_game_system_doc,
)

from .chat_loops import (
    pop_character_creation_loop as _pop_char_creation_loop,
)
from .chat_loops import (
    pop_conversation_loop as _pop_conversation_loop,
)
from .chat_loops import (
    pop_scene_loop as _pop_scene_loop,
)
from .chat_loops import (
    pop_session_zero_loop as _pop_session_zero_loop,
)
from .chat_loops import (
    run_end_scene as _run_end_scene,
)
from .chat_loops import (
    run_preplay_turn as _run_preplay_turn,
)
from .chat_loops import (
    run_scene_turn as _run_scene_turn,
)
from .chat_loops import (
    run_world_architect_turn as _run_world_architect_turn,
)

# reason: chat_opening.py re-exports bootstrap_story_scene (with a noqa F401 marker on the source import) without declaring __all__; mypy's --no-implicit-reexport rejects the access
from .chat_opening import (  # type: ignore
    bootstrap_story_scene as _bootstrap_story_scene,
)
from .chat_opening import (
    build_gm_opening as _build_gm_opening,
)
from .chat_persistence import (
    db_load_messages,
    db_load_sessions,
    db_save_message,
    db_save_session,
    ensure_sessions_loaded,
    purge_chat_runtime_cache,
)
from .chat_schemas import (
    Message,
    MessageSend,
    Session,
    SessionCreate,
    SessionPatch,
    SessionStateResponse,
    WrapUpCanonItem,
    WrapUpDigest,
)
from .chat_support import (
    VALID_TONES as _VALID_TONES,
)
from .chat_support import (
    as_uuid,
    build_session_state_payload,
    handle_tone_command,
    make_gm_message,
    make_player_message,
    make_system_message,
    now_iso,
)
from .chat_ws import (
    _WS_FANOUT_TASKS,
    _WS_SUBSCRIBERS,
    _WS_TOKEN_DELAY_SECONDS,
    fanout_completed_gm_message,
    fanout_event,
)
from .chat_ws import (
    register as ws_register,
)
from .chat_ws import (
    send_payload as _send_ws_payload,
)
from .chat_ws import (
    unregister as ws_unregister,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Optional layer imports (graceful degradation)
# ---------------------------------------------------------------------------

try:
    from monitor_agents.loops.world_building_loop import WorldBuildingLoop

    _WORLD_ARCHITECT_AVAILABLE = True
except Exception:
    _WORLD_ARCHITECT_AVAILABLE = False

try:
    from monitor_agents.utils.db_readers import run_sync_read as _run_sync_read
    from monitor_data.schemas.proposed_changes import ProposedChangeFilter
    from monitor_data.tools.mongodb_tools import mongodb_list_proposed_changes

    _WRAP_UP_READS_AVAILABLE = True
except Exception:
    _WRAP_UP_READS_AVAILABLE = False

# ---------------------------------------------------------------------------
# In-process write-through cache
# ---------------------------------------------------------------------------
# reason: `dict` is the bare generic missing type parameters; in-process sessions cache holds heterogeneous per-session dict shapes (mode/title/ids/timestamps)
_SESSIONS: dict[str, dict] = {}  # type: ignore
# reason: `list[dict]` is the bare generic missing type parameters; in-process messages cache holds per-session message lists with heterogeneous metadata shapes
_MESSAGES: dict[str, list[dict]] = {}  # type: ignore
_MESSAGES_MAX = 50
_SESSIONS_LOADED_FROM_DB: bool = False


# ---------------------------------------------------------------------------
# Cache eviction
# ---------------------------------------------------------------------------


def _evict_messages_cache() -> None:
    while len(_MESSAGES) > _MESSAGES_MAX:
        oldest = next(iter(_MESSAGES))
        del _MESSAGES[oldest]


# ---------------------------------------------------------------------------
# Thin helpers (kept for backward-compat with tests that monkeypatch them)
# ---------------------------------------------------------------------------


def _now() -> str:
    return now_iso()


def _make_system_msg(session_id: str, content: str) -> dict[str, Any]:
    return make_system_message(session_id, content)


# reason: `metadata: dict | None` — `dict` is the bare generic missing type parameters; helper accepts an untyped metadata dict and forwards it unchanged
def _make_gm_msg(session_id: str, content: str, metadata: dict | None = None) -> dict[str, Any]:  # type: ignore
    # Defense in depth: chat_loops.run_scene_turn already strips entity
    # tags before returning, but the WS path in this module splits the
    # narrative on words BEFORE that strip (see chat.py around the
    # streaming-token loop). Stripping here as well catches any path
    # that bypassed chat_loops — including the test mock, which patches
    # _run_scene_turn at this module's namespace. The strip is
    # idempotent on already-stripped text, so a double strip is a no-op.
    # See monitor_agents.loops.scene_support.strip_entity_tags for the
    # canonical implementation; the regex must stay in lockstep.
    from monitor_agents.loops.scene_support import strip_entity_tags

    content = strip_entity_tags(content or "")
    return make_gm_message(session_id, content, metadata)


# ---------------------------------------------------------------------------
# MongoDB persistence wrappers (monkeypatched by tests)
# ---------------------------------------------------------------------------


def _db_save_session(session: dict[str, Any]) -> None:
    db_save_session(session)


def _db_load_sessions() -> list[dict[str, Any]]:
    return db_load_sessions()


def _db_save_message(msg: dict[str, Any]) -> None:
    db_save_message(msg)


def _db_load_messages(session_id: str) -> list[dict[str, Any]]:
    return db_load_messages(session_id)


def _ensure_sessions_loaded() -> None:
    global _SESSIONS_LOADED_FROM_DB
    _SESSIONS_LOADED_FROM_DB = ensure_sessions_loaded(
        _SESSIONS,
        loaded_from_db=_SESSIONS_LOADED_FROM_DB,
    )


def _build_session_state(session_id: str) -> SessionStateResponse:
    from fastapi import HTTPException

    _ensure_sessions_loaded()
    if session_id not in _MESSAGES:
        loaded = _db_load_messages(session_id)
        if loaded:
            _MESSAGES[session_id] = loaded
            _evict_messages_cache()

    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = _MESSAGES.get(session_id, [])
    payload = build_session_state_payload(session, messages)
    return SessionStateResponse(
        session=Session(**session, message_count=len(messages)),
        **payload,
    )


def _handle_tone_command(content: str, session_id: str) -> tuple[str, dict[str, Any]] | None:
    return handle_tone_command(
        content,
        session_id=session_id,
        sessions=_SESSIONS,
        save_session=_db_save_session,
        now_fn=_now,
    )


# ===========================================================================
# REST endpoints
# ===========================================================================


@router.get("", response_model=list[Session])
async def list_sessions() -> list[Session]:
    _ensure_sessions_loaded()
    return [
        Session(
            id=sid,
            title=s.get("title", ""),
            mode=s.get("mode", "gm"),
            multiverse_id=s.get("multiverse_id"),
            multiverse_label=s.get("multiverse_label"),
            universe_id=s.get("universe_id"),
            universe_label=s.get("universe_label"),
            world_id=s.get("world_id"),
            character_id=s.get("character_id"),
            speaker_character_id=s.get("speaker_character_id"),
            speaker_label=s.get("speaker_label"),
            controlled_character_ids=s.get("controlled_character_ids", []),
            system_id=s.get("system_id"),
            pack_id=s.get("pack_id"),
            system_source_type=s.get("system_source_type"),
            system_source_id=s.get("system_source_id"),
            system_label=s.get("system_label"),
            benchmark_id=s.get("benchmark_id"),
            benchmark_label=s.get("benchmark_label"),
            tone=s.get("tone", "dramatic"),
            play_mode=s.get("play_mode", "narrative"),
            chat_mode=s.get("chat_mode", "ic"),
            scene_id=s.get("scene_id"),
            story_id=s.get("story_id"),
            phase=s.get("phase", "awaiting_character"),
            created_at=s.get("created_at") or _now(),
            updated_at=s.get("updated_at") or _now(),
            message_count=len(_MESSAGES.get(sid, [])),
            recap_text=s.get("recap_text"),
            wrapped_up_at=s.get("wrapped_up_at"),
        )
        for sid, s in _SESSIONS.items()
    ]


@router.get("/benchmarks")
async def list_playtest_benchmarks() -> list[dict[str, Any]]:
    try:
        from monitor_data.defaults.playtest_benchmarks import (
            resolve_playtest_benchmarks,
        )

        return await asyncio.to_thread(resolve_playtest_benchmarks, include_scripted_turns=True)
    except Exception as exc:
        logger.debug("list_playtest_benchmarks failed: %s", exc)
        return []


@router.post("", response_model=Session, status_code=201)
async def create_session(body: SessionCreate) -> Session:
    sid = str(uuid.uuid4())
    now = _now()
    benchmark = _get_benchmark_config(body.benchmark_id)
    provided_fields = set(getattr(body, "model_fields_set", set()))

    title = body.title
    mode = body.mode
    tone = body.tone
    play_mode = body.play_mode
    system_id = body.system_id
    pack_id = body.pack_id
    system_source_type = body.system_source_type
    system_source_id = body.system_source_id or body.pack_id
    system_label = body.system_label
    benchmark_label = body.benchmark_label

    if benchmark:
        if "title" not in provided_fields and benchmark.get("session_title"):
            title = str(benchmark["session_title"])
        if "mode" not in provided_fields and benchmark.get("mode"):
            mode = str(benchmark["mode"])
        if "tone" not in provided_fields and benchmark.get("tone"):
            tone = str(benchmark["tone"])
        if "play_mode" not in provided_fields and benchmark.get("play_mode"):
            play_mode = str(benchmark["play_mode"])
        if "system_id" not in provided_fields and benchmark.get("resolved_system_id"):
            system_id = str(benchmark["resolved_system_id"])
        if "system_label" not in provided_fields and benchmark.get("resolved_system_name"):
            system_label = str(benchmark["resolved_system_name"])
        if "benchmark_label" not in provided_fields and benchmark.get("name"):
            benchmark_label = str(benchmark["name"])

    universe_id = body.universe_id or body.world_id
    if universe_id:
        binding = _resolve_universe_system_binding(universe_id)
        if "system_id" not in provided_fields and not system_id and binding.get("system_id"):
            system_id = str(binding["system_id"])
        if "system_source_type" not in provided_fields and not system_source_type and binding.get("system_source_type"):
            system_source_type = str(binding["system_source_type"])
        if "system_source_id" not in provided_fields and not system_source_id and binding.get("system_source_id"):
            system_source_id = str(binding["system_source_id"])
        if (
            "pack_id" not in provided_fields
            and not pack_id
            and binding.get("system_source_type") == "pack_embedded"
            and binding.get("system_source_id")
        ):
            pack_id = str(binding["system_source_id"])
        if "system_label" not in provided_fields and not system_label and binding.get("system_name"):
            system_label = str(binding["system_name"])

    if pack_id and not system_source_type:
        system_source_type = "pack_embedded"
    if pack_id and not system_source_id:
        system_source_id = str(pack_id)
    if system_id and not system_source_type:
        system_source_type = "generic_library"
    if system_id and not system_source_id:
        system_source_id = str(system_id)
    if system_source_type == "pack_embedded" and not pack_id and system_source_id:
        pack_id = str(system_source_id)

    speaker_character_id = body.speaker_character_id or body.character_id
    controlled = body.controlled_character_ids or ([body.character_id] if body.character_id else [])

    session: dict[str, Any] = {
        "id": sid,
        "title": title,
        "mode": mode,
        "multiverse_id": body.multiverse_id,
        "multiverse_label": body.multiverse_label,
        "universe_id": universe_id,
        "universe_label": body.universe_label,
        "world_id": universe_id,
        "character_id": body.character_id,
        "speaker_character_id": speaker_character_id,
        "speaker_label": body.speaker_label,
        "persona_id": body.persona_id,
        "controlled_character_ids": controlled,
        "system_id": system_id,
        "pack_id": pack_id,
        "system_source_type": system_source_type,
        "system_source_id": system_source_id,
        "system_label": system_label,
        "benchmark_id": body.benchmark_id,
        "benchmark_label": benchmark_label,
        "tone": tone,
        "story_premise": body.story_premise,
        "gm_profile_id": body.gm_profile_id,
        "play_mode": play_mode,
        "chat_mode": body.chat_mode,
        "scene_id": body.scene_id,
        "story_id": body.story_id,
        "selected_character_id": body.selected_character_id,
        "authored_prompt_collection_id": body.authored_prompt_collection_id,
        "created_at": now,
        "updated_at": now,
    }

    story_id: str | None = None
    scene_id: str | None = None
    bootstrap_error: str | None = None

    # Captured BEFORE _bootstrap_story_scene runs: that function returns a
    # non-None story_id whether it just created one for a brand-new session
    # OR reused an existing one, so it can't itself distinguish "new" from
    # "resuming." body.story_id (the raw client-supplied value) is the only
    # reliable signal that this session is meant to continue an existing
    # story rather than start one -- see PLAY_AND_FORGE_DIRECTION.md S5.
    is_resume = bool(body.story_id)
    defer_autonomous_preplay = mode == "autonomous_gm" and not is_resume

    if body.mode != "world_architect" and not defer_autonomous_preplay:
        story_id, scene_id, bootstrap_error = _bootstrap_story_scene(session)
        session["story_id"] = story_id
        session["scene_id"] = scene_id

    # A player who selected an existing character at setup binds it directly
    # (the "select" half of select-or-create) and skips Session Zero.
    if body.selected_character_id and not session.get("character_id"):
        session["character_id"] = body.selected_character_id
        session["speaker_character_id"] = body.selected_character_id
        if body.selected_character_id not in session["controlled_character_ids"]:
            session["controlled_character_ids"].append(body.selected_character_id)

    if body.mode == "world_architect" or is_resume:
        session["phase"] = "active_play"
    elif defer_autonomous_preplay:
        session["phase"] = "session_zero" if session.get("character_id") else "character_interview"
    elif body.character_id or body.controlled_character_ids or body.selected_character_id:
        session["phase"] = "active_play"
    else:
        # Preserve the existing GM-assistant setup behavior.
        session["phase"] = "awaiting_character"

    _SESSIONS[sid] = session
    _db_save_session(session)

    # Build opening messages
    messages: list[dict[str, Any]] = []

    if body.mode == "world_architect":
        context_lines = []
        if body.multiverse_label:
            context_lines.append(f"Setting: **{body.multiverse_label}**")
        if body.universe_label:
            context_lines.append(f"Universe: **{body.universe_label}**")

        messages.append(
            _make_system_msg(
                sid,
                "\n".join(
                    [
                        "Session started in **World Architect** mode.",
                        *context_lines,
                        "World Architect: **ready** — describe your world to begin building.",
                    ]
                ),
            )
        )

        if _WORLD_ARCHITECT_AVAILABLE and as_uuid(universe_id):
            try:
                loop = WorldBuildingLoop(
                    session_id=sid,
                    universe_id=as_uuid(universe_id),
                    multiverse_id=as_uuid(body.multiverse_id),
                )
                welcome = await loop.run(user_input="", conversation_history=[])
                welcome_text = welcome.get("response_text", "")
                if welcome_text:
                    messages.append(_make_gm_msg(sid, welcome_text, {"type": "world_architect_welcome"}))
            except Exception:
                messages.append(
                    _make_gm_msg(
                        sid,
                        "Welcome to the **World Architect**! Describe your world — "
                        "its genre, tone, key factions, geography, or anything else — "
                        "and I'll help you build it piece by piece.",
                        {"type": "world_architect_welcome"},
                    )
                )
        else:
            messages.append(
                _make_gm_msg(
                    sid,
                    "Welcome to the **World Architect**! Describe your world — "
                    "its genre, tone, key factions, geography, or anything else — "
                    "and I'll help you build it piece by piece.\n\n"
                    "You can also upload documents via the **Ingest** tab to extract lore automatically.",
                    {"type": "world_architect_welcome"},
                )
            )
    else:
        if defer_autonomous_preplay:
            system_doc = _session_game_system_doc(session)
            if session.get("character_id"):
                gm_text, gm_meta = await start_story_agreements(
                    sid,
                    session,
                    system_doc=system_doc,
                )
            else:
                from .chat_opening import fetch_opening_hook

                lore_data = await fetch_opening_hook(session)
                gm_text, gm_meta = await start_character_interview(
                    sid,
                    session,
                    system_doc=system_doc,
                    world_lore=(lore_data.get("axioms", []) + lore_data.get("facts", [])),
                )
            _db_save_session(session)
        else:
            gm_text, gm_meta = await _build_gm_opening(
                sid,
                session,
                session_game_system_doc=_session_game_system_doc,
                is_resume=is_resume,
            )
        messages.append(_make_gm_msg(sid, gm_text, gm_meta))

    _MESSAGES[sid] = messages
    _evict_messages_cache()
    for msg in messages:
        _db_save_message(msg)

    return Session(**session, message_count=len(messages))


@router.get("/{session_id}/state", response_model=SessionStateResponse)
async def get_session_state(session_id: str) -> SessionStateResponse:
    return _build_session_state(session_id)


@router.get("/{session_id}/messages", response_model=list[Message])
async def get_messages(session_id: str) -> list[Message]:
    if session_id not in _MESSAGES:
        loaded = _db_load_messages(session_id)
        if loaded:
            _MESSAGES[session_id] = loaded
            _evict_messages_cache()
    return [Message(**m) for m in _MESSAGES.get(session_id, [])]


@router.get("/{session_id}/recap")
async def get_session_recap(session_id: str) -> dict[str, Any]:
    """
    Generate a "Story So Far" narrative recap for the session's active story.

    Calls RecapAgent which synthesizes the story outline, completed scenes,
    and high-magnitude facts from Neo4j into a prose summary. Sessions that
    have been wrapped up (P1.4) return their persisted recap artifact
    instead of regenerating.
    """
    _ensure_sessions_loaded()
    session = _SESSIONS.get(session_id)
    if not session:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Session not found")

    story_id = session.get("story_id")
    universe_id = session.get("universe_id") or session.get("world_id")

    persisted_recap = session.get("recap_text")
    if persisted_recap:
        return {
            "recap": persisted_recap,
            "story_id": story_id,
            "universe_id": universe_id,
            "persisted": True,
        }

    if not story_id or not universe_id:
        return {
            "recap": "No story is active yet. Start playing to build history.",
            "story_id": story_id,
            "universe_id": universe_id,
        }

    try:
        from monitor_agents.recap.agent import RecapAgent

        agent = RecapAgent()
        recap_text = await agent.generate_recap(
            story_id=uuid.UUID(story_id),
            universe_id=uuid.UUID(universe_id),
            tone_context="Evocative narrative summary for the player.",
        )
        if not recap_text or len(recap_text.strip()) < 20:
            recap_text = "The story is just beginning. Every legend starts with a first step."
    except ImportError:
        recap_text = "The recap engine is not available right now."
    except Exception as exc:
        logger.warning("RecapAgent endpoint failed (session=%s): %s", session_id, exc)
        recap_text = "I couldn't gather the story threads right now. Try again later."

    return {
        "recap": recap_text,
        "story_id": story_id,
        "universe_id": universe_id,
    }


def _canon_item_label(content: dict[str, Any], change_type: str) -> str:
    """Best-effort human-readable label for a proposed change's content."""
    for key in ("description", "name", "title", "text", "summary", "content"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return change_type.replace("_", " ")


@router.post("/{session_id}/wrap-up", response_model=WrapUpDigest)
async def wrap_up_session(session_id: str) -> WrapUpDigest:
    """
    Guided end-of-session wrap-up for gm_assistant recordings (P1.3).

    One click sequences: scene-end canonization (if the scene is still open),
    the RecapAgent recap, the CanonKeeper decision tally for the capture
    story, open plot threads, and a next-session prep teaser. The recap is
    persisted onto the session doc (P1.4) so later reads skip the LLM.
    """
    from fastapi import HTTPException

    _ensure_sessions_loaded()
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.get("mode") != "gm_assistant":
        raise HTTPException(
            status_code=409,
            detail="Wrap-up is only available for gm_assistant (recording) sessions.",
        )

    story_id = session.get("story_id")
    universe_id = session.get("universe_id") or session.get("world_id")

    # 1. Canonize first so the digest reflects the final decision state.
    if session.get("phase") != "scene_ended":
        await _run_end_scene(
            session_id,
            session,
            sessions=_SESSIONS,
            messages=_MESSAGES,
            db_save_session=_db_save_session,
            db_load_messages=_db_load_messages,
            bootstrap_story_scene=_bootstrap_story_scene,
        )

    # 2. Recap (kept for persistence below).
    recap_text = ""
    if story_id and universe_id:
        try:
            from monitor_agents.recap.agent import RecapAgent

            agent = RecapAgent()
            recap_text = await agent.generate_recap(
                story_id=uuid.UUID(story_id),
                universe_id=uuid.UUID(universe_id),
                tone_context="Evocative narrative summary for the GM.",
            )
        except ImportError:
            recap_text = "The recap engine is not available right now."
        except Exception as exc:
            logger.warning("Wrap-up recap failed (session=%s): %s", session_id, exc)
            recap_text = "I couldn't gather the story threads right now."
    if not recap_text or len(recap_text.strip()) < 20:
        recap_text = "The story is just beginning. Every legend starts with a first step."

    # 3. Canon decisions for the capture story, grouped by status.
    accepted = rejected = pending = 0
    canon_items: list[WrapUpCanonItem] = []
    if story_id and _WRAP_UP_READS_AVAILABLE:
        try:
            # reason: `resp` would need an explicit annotation because `_run_sync_read`'s `func` is typed as bare `callable` (not Callable), so mypy cannot infer the return at the call site
            resp = await _run_sync_read(  # type: ignore
                mongodb_list_proposed_changes,
                ProposedChangeFilter(story_id=uuid.UUID(story_id), limit=1000),
            )
            for proposal in resp.proposed_changes:
                status = proposal.status.value
                if status == "accepted":
                    accepted += 1
                elif status == "rejected":
                    rejected += 1
                else:
                    pending += 1
                canon_items.append(
                    WrapUpCanonItem(
                        proposal_id=str(proposal.proposal_id),
                        change_type=proposal.change_type.value,
                        status=status,
                        label=_canon_item_label(proposal.content, proposal.change_type.value),
                    )
                )
        except Exception as exc:
            logger.warning("Wrap-up canon tally failed (session=%s): %s", session_id, exc)

    # 4. Open threads + next-session prep teaser.
    open_threads: list[str] = []
    next_prep: Any = None
    if story_id and universe_id:
        try:
            from monitor_agents.plot_hooks import PlotHookAgent

            prep_agent = PlotHookAgent()
            next_prep = await prep_agent.generate_session_prep(uuid.UUID(universe_id), uuid.UUID(story_id))
            open_threads = list(next_prep.open_threads)
        except ImportError:
            logger.debug("PlotHookAgent unavailable for wrap-up (session=%s)", session_id)
        except Exception as exc:
            logger.warning("Wrap-up session prep failed (session=%s): %s", session_id, exc)

    # 5. Persist the wrap-up artifacts onto the session doc (P1.4).
    now = _now()
    session["recap_text"] = recap_text
    session["wrapped_up_at"] = now
    session["updated_at"] = now
    _db_save_session(session)

    return WrapUpDigest(
        recap=recap_text,
        accepted=accepted,
        rejected=rejected,
        pending=pending,
        canon_items=canon_items,
        open_threads=open_threads,
        next_prep=next_prep,
    )


@router.post("/{session_id}/greet", response_model=Message)
async def greet_character(session_id: str, character_id: str) -> Message:
    """
    Bootstrap a session with a character greeting.
    Creates a 'character' role message using the character's first_message.
    """
    _ensure_sessions_loaded()
    session = _SESSIONS.get(session_id)
    if not session:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Session not found")

    from .character_storage import get_character

    char = get_character(character_id)
    if not char or char.get("status") == "retconned":
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Character not found")

    msgs = _MESSAGES.setdefault(session_id, [])

    # Idempotency check
    for m in msgs:
        if (
            m.get("metadata", {}).get("character_id") == character_id
            and m.get("metadata", {}).get("type") == "first_message"
        ):
            return Message(**m)

    content = char.get("first_message") or f"Hello, I am {char['name']}."

    gm_msg = make_gm_message(
        session_id,
        content,
        metadata={
            "character_id": character_id,
            "character_name": char["name"],
            "type": "first_message",
        },
    )
    # The test expects role='character'
    gm_msg["role"] = "character"

    msgs.append(gm_msg)
    db_save_message(gm_msg)

    asyncio.create_task(fanout_completed_gm_message(session_id, gm_msg))
    return Message(**gm_msg)


def _begin_story_intent(session: dict[str, Any], content: str) -> bool:
    """True when a chat message should trigger the same path as Begin Story.

    Mirrors ``begin_story``'s own guards: only while Session Zero agreements
    are awaiting confirmation. Without this, typing "begin story" in chat was
    swallowed by the story-agreements loop as a *revision* and the summary
    was re-presented endlessly.
    """
    if session.get("phase") != "session_zero" or session.get("preplay_finalized_at"):
        return False
    agreements = session.get("story_agreements")
    if not isinstance(agreements, dict) or agreements.get("confirmed"):
        return False
    return is_begin_story_command(content)


@router.post("/{session_id}/begin", response_model=Message)
async def begin_story(session_id: str) -> Message:
    """Confirm Session Zero and create the first in-fiction narration once."""
    _ensure_sessions_loaded()
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    msgs = _MESSAGES.setdefault(session_id, [])
    if session.get("preplay_finalized_at"):
        for message in msgs:
            metadata = message.get("metadata") or {}
            if metadata.get("type") == "gm_opening" and metadata.get("preplay_finalized"):
                return Message(**message)
        raise HTTPException(status_code=409, detail="Story was already begun")

    if session.get("phase") != "session_zero":
        raise HTTPException(status_code=409, detail="Session Zero is not awaiting Begin Story")
    agreements = session.get("story_agreements")
    if not isinstance(agreements, dict) or agreements.get("confirmed"):
        raise HTTPException(status_code=409, detail="Session Zero agreements are incomplete")

    system_doc = _session_game_system_doc(session)
    try:
        narrative, metadata = await finalize_preplay(session, system_doc=system_doc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("begin_story failed for %s", session_id)
        raise HTTPException(status_code=500, detail="Could not begin the story") from exc
    # The router's session reference and the dict finalize_preplay mutated are
    # the same object; re-store it so concurrent reads see the latest state.
    _SESSIONS[session_id] = session

    session["updated_at"] = _now()
    _db_save_session(session)
    gm_msg = _make_gm_msg(session_id, narrative, metadata)
    msgs.append(gm_msg)
    _db_save_message(gm_msg)
    asyncio.create_task(fanout_completed_gm_message(session_id, gm_msg))
    return Message(**gm_msg)


@router.post("/{session_id}/send", response_model=Message)
async def send_message(session_id: str, body: MessageSend) -> Message:
    _ensure_sessions_loaded()
    if session_id not in _SESSIONS:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Session not found")
    if session_id not in _MESSAGES:
        loaded = _db_load_messages(session_id)
        if loaded:
            _MESSAGES[session_id] = loaded
            _evict_messages_cache()

    now = _now()
    msgs = _MESSAGES.setdefault(session_id, [])

    _player_meta: dict[str, Any] = {}
    if body.character_id:
        _player_meta["character_id"] = body.character_id
    if body.chat_mode:
        _player_meta["chat_mode"] = body.chat_mode
    player_msg = make_player_message(
        session_id,
        body.content,
        timestamp=now,
        metadata=_player_meta or None,
    )
    msgs.append(player_msg)
    _db_save_message(player_msg)

    session = _SESSIONS.get(session_id, {})

    tone_result = _handle_tone_command(body.content, session_id)
    if tone_result is not None:
        narrative, meta = tone_result
        gm_msg = _make_gm_msg(session_id, narrative, meta)
        msgs.append(gm_msg)
        _db_save_message(gm_msg)
        asyncio.create_task(fanout_completed_gm_message(session_id, gm_msg))
        return Message(**gm_msg)

    # === OOC / AI Persona mode (chat_mode == "ooc") ===
    if body.chat_mode == "ooc" and body.character_id:
        from .chat_loops import run_ooc_turn

        narrative, meta = await run_ooc_turn(
            session_id,
            body.content,
            body.character_id,
            sessions=_SESSIONS,
            messages=_MESSAGES,
            db_save_session=_db_save_session,
        )
        gm_msg = _make_gm_msg(session_id, narrative, meta)
        msgs.append(gm_msg)
        _db_save_message(gm_msg)
        gm_msg["chat_mode"] = "ooc"
        gm_msg["character_id"] = body.character_id
        asyncio.create_task(fanout_completed_gm_message(session_id, gm_msg))
        return Message(**gm_msg)

    # === IC with is_ooc_persona (skip SceneLoop, bare character context) ===
    if body.is_ooc_persona and body.character_id:
        from .chat_loops import run_ooc_turn

        narrative, meta = await run_ooc_turn(
            session_id,
            body.content,
            body.character_id,
            sessions=_SESSIONS,
            messages=_MESSAGES,
            db_save_session=_db_save_session,
        )
        gm_msg = _make_gm_msg(session_id, narrative, meta)
        msgs.append(gm_msg)
        _db_save_message(gm_msg)
        gm_msg["chat_mode"] = "ooc"
        gm_msg["character_id"] = body.character_id
        asyncio.create_task(fanout_completed_gm_message(session_id, gm_msg))
        return Message(**gm_msg)

    # === IC with character_id: update session speaker so SceneLoop uses it ===
    if body.character_id and body.chat_mode == "ic":
        session["speaker_character_id"] = body.character_id
        # Invalidate cached scene loop so it picks up the new actor
        _SESSIONS[session_id] = session
        _pop_scene_loop(session_id)

    if session.get("mode") == "world_architect":
        narrative, meta = await _run_world_architect_turn(
            session_id,
            body.content,
            sessions=_SESSIONS,
            messages=_MESSAGES,
            db_save_session=_db_save_session,
            db_load_messages=_db_load_messages,
        )
    elif _begin_story_intent(session, body.content):
        # Typed "begin story" (or "confirm", "looks good", …) while Session
        # Zero awaits confirmation — run the same finalize path as the button.
        return await begin_story(session_id)
    elif session.get("phase") in (
        "awaiting_character",
        "character_interview",
        "char_creation",
        "session_zero",
    ):
        narrative, meta = await _run_preplay_turn(
            session_id,
            body.content,
            sessions=_SESSIONS,
            messages=_MESSAGES,
            db_save_session=_db_save_session,
            db_save_message=_db_save_message,
            session_game_system_doc=_session_game_system_doc,
            gsr_available=_GSR_AVAILABLE,
        )
    elif session.get("phase") == "scene_ended":
        # Between scenes: bootstrap the next scene or let the player continue
        story_id, scene_id, _ = _bootstrap_story_scene(session)
        _db_save_session(session)
        if scene_id:
            narrative = "The world settles. A new scene opens before you — what do you do?"
            meta = {
                "type": "scene_resume",
                "phase": "active_play",
                "story_id": story_id,
                "scene_id": scene_id,
            }
        else:
            narrative, meta = await _run_scene_turn(
                session_id,
                body.content,
                sessions=_SESSIONS,
                messages=_MESSAGES,
                db_save_session=_db_save_session,
                db_load_messages=_db_load_messages,
                bootstrap_story_scene=_bootstrap_story_scene,
                session_game_system_doc=_session_game_system_doc,
                gsr_available=_GSR_AVAILABLE,
            )
    else:
        narrative, meta = await _run_scene_turn(
            session_id,
            body.content,
            sessions=_SESSIONS,
            messages=_MESSAGES,
            db_save_session=_db_save_session,
            db_load_messages=_db_load_messages,
            bootstrap_story_scene=_bootstrap_story_scene,
            session_game_system_doc=_session_game_system_doc,
            gsr_available=_GSR_AVAILABLE,
        )
    gm_msg = _make_gm_msg(session_id, narrative, meta)
    msgs.append(gm_msg)
    _db_save_message(gm_msg)

    if session_id in _SESSIONS:
        if meta.get("working_state"):
            _SESSIONS[session_id]["latest_working_state"] = meta["working_state"]
        if meta.get("scene_checkpoint"):
            _SESSIONS[session_id]["latest_scene_checkpoint"] = meta["scene_checkpoint"]
        if meta.get("social_read"):
            _SESSIONS[session_id]["latest_social_read"] = meta["social_read"]
        if meta.get("relationship_snapshot"):
            _SESSIONS[session_id]["latest_relationship_snapshot"] = meta["relationship_snapshot"]
        _SESSIONS[session_id]["updated_at"] = now
        _db_save_session(_SESSIONS[session_id])

    asyncio.create_task(fanout_completed_gm_message(session_id, gm_msg))
    return Message(**gm_msg)


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    _ensure_sessions_loaded()
    _SESSIONS.pop(session_id, None)
    _MESSAGES.pop(session_id, None)
    _pop_scene_loop(session_id)
    _pop_char_creation_loop(session_id)
    _pop_session_zero_loop(session_id)
    _pop_conversation_loop(session_id)
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        mdb = get_mongodb_client()
        mdb.get_collection("chat_sessions").delete_one({"id": session_id})
        mdb.get_collection("chat_messages").delete_many({"session_id": session_id})
    except Exception as exc:
        logger.debug("delete_session DB cleanup failed: %s", exc)

    listeners = list(_WS_SUBSCRIBERS.pop(session_id, set()))
    task = _WS_FANOUT_TASKS.pop(session_id, None)
    if task is not None and not task.done():
        task.cancel()
    for listener in listeners:
        with contextlib.suppress(Exception):
            await listener.close(code=1000)

    purge_chat_runtime_cache(session_id)


@router.patch("/{session_id}", response_model=Session)
async def update_session(
    session_id: str,
    body: SessionPatch | None = None,
) -> Session:
    _ensure_sessions_loaded()
    session = _SESSIONS.get(session_id)
    if not session:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Session not found")
    if body is not None and body.title is not None:
        title = body.title.strip()
        if title:
            session["title"] = title[:200]
    if body is not None and body.tone is not None:
        if body.tone not in _VALID_TONES:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail=f"Invalid tone. Must be one of: {', '.join(sorted(_VALID_TONES))}",
            )
        session["tone"] = body.tone
    scene_id = body.scene_id if body is not None else None
    story_id = body.story_id if body is not None else None
    if body is not None and body.gm_profile_id is not None:
        session["gm_profile_id"] = body.gm_profile_id
        session["tone"] = session.get("tone", "dramatic")
    if scene_id is not None:
        session["scene_id"] = scene_id
    if story_id is not None:
        session["story_id"] = story_id
    if body is not None and body.chat_mode is not None:
        if body.chat_mode not in ("ic", "ooc"):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail="Invalid chat_mode. Must be one of: ic, ooc",
            )
        session["chat_mode"] = body.chat_mode
    if body is not None and body.roll_model is not None:
        if body.roll_model not in ("tap", "manual", "gm"):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail="Invalid roll_model. Must be one of: tap, manual, gm",
            )
        session["roll_model"] = body.roll_model
    session["updated_at"] = _now()
    _db_save_session(session)
    return Session(**session, message_count=len(_MESSAGES.get(session_id, [])))


# ---------------------------------------------------------------------------
# Scene lifecycle — explicit scene-end endpoint (Phase 0.4)
# ---------------------------------------------------------------------------


@router.post("/{session_id}/end-scene", response_model=Message)
async def end_scene(session_id: str) -> Message:
    """
    Force scene completion: canonize pending proposals, advance the story,
    and prepare the next scene for play.

    This is the REST equivalent of sending ``/end-scene`` via chat.
    """
    _ensure_sessions_loaded()
    session = _SESSIONS.get(session_id)
    if not session:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Session not found")

    scene_id = session.get("scene_id")
    story_id = session.get("story_id")
    if not scene_id or not story_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="No active scene to end. Start a scene first.",
        )

    narrative, meta = await _run_end_scene(
        session_id,
        session,
        sessions=_SESSIONS,
        messages=_MESSAGES,
        db_save_session=_db_save_session,
        db_load_messages=_db_load_messages,
        bootstrap_story_scene=_bootstrap_story_scene,
    )

    now = _now()
    gm_msg = _make_gm_msg(session_id, narrative, meta)
    msgs = _MESSAGES.setdefault(session_id, [])
    msgs.append(gm_msg)
    _db_save_message(gm_msg)

    # Persist updated session state
    if session_id in _SESSIONS:
        if meta.get("working_state"):
            _SESSIONS[session_id]["latest_working_state"] = meta["working_state"]
        if meta.get("scene_checkpoint"):
            _SESSIONS[session_id]["latest_scene_checkpoint"] = meta["scene_checkpoint"]
        if meta.get("social_read"):
            _SESSIONS[session_id]["latest_social_read"] = meta["social_read"]
        if meta.get("relationship_snapshot"):
            _SESSIONS[session_id]["latest_relationship_snapshot"] = meta["relationship_snapshot"]
        _SESSIONS[session_id]["updated_at"] = now
        _db_save_session(_SESSIONS[session_id])

    asyncio.create_task(fanout_completed_gm_message(session_id, gm_msg))
    return Message(**gm_msg)


# ---------------------------------------------------------------------------
# Skip-preplay — [G-1](c) affordance to jump from Session Zero / character
# creation straight into active_play.
# ---------------------------------------------------------------------------


_PREPLAY_PHASES = frozenset({"awaiting_character", "character_interview", "session_zero", "char_creation"})
_CHARACTER_SETUP_PHASES = frozenset({"awaiting_character", "character_interview", "char_creation"})


@router.post("/{session_id}/skip-preplay", response_model=Message)
async def skip_preplay(session_id: str) -> Message:
    """Use safe defaults for Session Zero and invoke the normal Begin path.

    Character selection/creation remains an invariant: a player cannot skip
    into narration without a bound character. Once a character exists, this
    endpoint persists explicit default agreements and uses the same idempotent
    finalizer as the Begin Story action.
    """
    _ensure_sessions_loaded()
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    current_phase = session.get("phase", "")
    if current_phase not in _PREPLAY_PHASES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot skip-preplay from phase '{current_phase}'",
        )
    if current_phase in _CHARACTER_SETUP_PHASES and not session.get("character_id"):
        raise HTTPException(
            status_code=409,
            detail="Select or create a player character before beginning the story",
        )

    system_doc = _session_game_system_doc(session)
    if current_phase != "session_zero":
        await start_story_agreements(
            session_id,
            session,
            system_doc=system_doc,
        )

    from monitor_agents.story_agreements import StoryAgreements

    existing = session.get("story_agreements")
    if isinstance(existing, dict):
        agreements = StoryAgreements.model_validate(existing).model_copy(
            update={"source": "skipped", "confirmed": False, "confirmed_at": None}
        )
    else:
        agreements = StoryAgreements(
            story_premise=str(session.get("story_premise") or "").strip(),
            tone=session.get("tone", "dramatic"),
            source="skipped",
        )
    session["story_agreements"] = agreements.model_dump(mode="json")
    session["phase"] = "session_zero"
    session["updated_at"] = _now()
    _db_save_session(session)

    _pop_session_zero_loop(session_id)
    _pop_char_creation_loop(session_id)
    return await begin_story(session_id)


# ---------------------------------------------------------------------------
# WebSocket — streaming GM responses
# ---------------------------------------------------------------------------


@router.websocket("/ws/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    ws_register(session_id, websocket)
    _ensure_sessions_loaded()
    if session_id not in _MESSAGES:
        loaded = _db_load_messages(session_id)
        if loaded:
            _MESSAGES[session_id] = loaded
            _evict_messages_cache()

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type: str = data.get("type", "message")
            raw_content = data.get("content", "")
            content = raw_content if isinstance(raw_content, str) else ""

            # Heartbeats are transport control frames, not player turns.  The
            # browser sends one every 30 seconds; letting it fall through would
            # persist an empty player message and invoke the GM indefinitely.
            if msg_type == "ping":
                if not await _send_ws_payload(websocket, {"type": "pong"}):
                    break
                continue

            # Reject blank normal turns at the protocol boundary so malformed
            # clients cannot trigger narration without player input.
            if msg_type == "message" and not content.strip():
                if not await _send_ws_payload(
                    websocket,
                    {"type": "error", "detail": "Message content cannot be empty."},
                ):
                    break
                continue

            now = _now()
            msgs = _MESSAGES.setdefault(session_id, [])

            # Handle dice_result
            if msg_type == "dice_result":
                spec: str = data.get("spec", "")
                value: int = int(data.get("value", 0))
                # reason: `list` is the bare generic missing type parameters; `data` is `Any` (json.loads return), so `.get("rolls", [])` is `Any` and cannot be parameterized without narrowing
                rolls: list = data.get("rolls", [])  # type: ignore
                reason: str = data.get("reason", spec)

                rolls_str = f"[{', '.join(str(r) for r in rolls)}]" if rolls else ""
                content = (
                    f"[DICE RESULT] {reason}: rolled {spec}{' ' + rolls_str if rolls_str else ''} = {value}. "
                    "Continue the narrative taking this result into account."
                )
                player_display = (
                    f"🎲 **{reason}** — rolled *{spec}*: {rolls_str} = **{value}**"
                    if rolls_str
                    else f"🎲 **{reason}** — *{spec}* = **{value}** *(manual)*"
                )
                player_msg = make_player_message(
                    session_id,
                    player_display,
                    timestamp=now,
                    metadata={
                        "type": "dice_result",
                        "spec": spec,
                        "value": value,
                        "rolls": rolls,
                        "reason": reason,
                    },
                )
                msgs.append(player_msg)
                _db_save_message(player_msg)
            elif msg_type == "roll_request":
                # Server-authoritative tap-to-roll: the player asked for a roll
                # but the SERVER generates the dice (see _server_roll_from_pending).
                spec = data.get("spec", "1d20")
                reason = data.get("reason", spec)
                content = (
                    f"[ROLL REQUEST] {reason}: roll {spec}. "
                    "Roll on the server and continue the narrative with the result."
                )
                player_display = f"🎲 **{reason}** — rolling *{spec}*…"
                player_msg = make_player_message(
                    session_id,
                    player_display,
                    timestamp=now,
                    metadata={"type": "roll_request", "spec": spec, "reason": reason},
                )
                msgs.append(player_msg)
                _db_save_message(player_msg)
            else:
                player_msg = make_player_message(session_id, content, timestamp=now)
                msgs.append(player_msg)
                _db_save_message(player_msg)

            gm_id = str(uuid.uuid4())

            # Inline /tone command
            tone_result = _handle_tone_command(content, session_id)
            if tone_result is not None:
                _narrative, _meta = tone_result
                gm_msg = _make_gm_msg(session_id, _narrative, _meta)
                gm_msg["id"] = gm_id
                msgs.append(gm_msg)
                _db_save_message(gm_msg)

                start_payload = {"type": "start", "message_id": gm_id}
                # Tone changes have no thinking phase — emit composing + done
                # directly so the UI flow stays consistent.
                composing_payload = {"type": "composing", "message_id": gm_id}
                token_payload = {
                    "type": "token",
                    "message_id": gm_id,
                    "token": _narrative,
                }
                done_payload = {"type": "done", "message_id": gm_id, "metadata": _meta}

                if not await _send_ws_payload(websocket, start_payload):
                    break
                await fanout_event(session_id, start_payload, exclude=websocket)
                if not await _send_ws_payload(websocket, composing_payload):
                    break
                await fanout_event(session_id, composing_payload, exclude=websocket)
                if not await _send_ws_payload(websocket, token_payload):
                    break
                await fanout_event(session_id, token_payload, exclude=websocket)
                if not await _send_ws_payload(websocket, done_payload):
                    break
                await fanout_event(session_id, done_payload, exclude=websocket)
                continue

            # Typed "begin story" while Session Zero awaits confirmation —
            # same finalize path as the Begin Story button. begin_story
            # persists the opening and streams it to every subscriber
            # (this socket included) via fanout_completed_gm_message.
            if _begin_story_intent(_SESSIONS.get(session_id, {}), content):
                try:
                    await begin_story(session_id)
                    continue
                except HTTPException:
                    pass  # fall through to the normal pre-play turn

            start_payload = {"type": "start", "message_id": gm_id}
            composing_payload = {"type": "composing", "message_id": gm_id}
            if not await _send_ws_payload(websocket, start_payload):
                break
            await fanout_event(session_id, start_payload, exclude=websocket)
            if not await _send_ws_payload(websocket, composing_payload):
                break
            await fanout_event(session_id, composing_payload, exclude=websocket)

            streamed_tokens = False
            delivered = True

            # reason: `data` parameter intentionally untyped and return intentionally absent — stream runtime emits heterogeneous payload shapes (str/dict/None) and this callback dispatches on kind
            async def on_event(kind: str, data):  # type: ignore
                """Dispatch a stream callback from dspy_runtime.

                The runtime emits three kinds:
                  - "thinking_chunk": pre-narrative CoT text
                  - "thinking_end": transition to narrative prose
                  - "narrative_token": a piece of narrative prose

                Each is forwarded as a typed WS payload so the client can render
                thinking bubbles, typing indicators, and streaming prose
                distinctly. We tolerate the legacy single-arg shape so callers
                that haven't been updated don't crash.
                """
                nonlocal streamed_tokens, delivered
                if not delivered:
                    return
                if kind == "narrative_token" and isinstance(data, str):
                    streamed_tokens = True
                    payload = {"type": "token", "message_id": gm_id, "token": data}
                elif kind == "thinking_chunk" and isinstance(data, str):
                    payload = {"type": "thinking", "message_id": gm_id, "delta": data}
                elif kind == "thinking_end":
                    payload = {"type": "thinking_end", "message_id": gm_id}
                elif kind == "tool_call" and isinstance(data, dict):
                    # Phase 2B: an MCP tool is being invoked. Forward to the
                    # client so it can render an inline tool card while the
                    # tool runs. The client correlates the matching
                    # tool_result via the shared `id`.
                    payload = {
                        "type": "tool_call",
                        "message_id": gm_id,
                        # reason: `data` is `Any` (no annotation on on_event); `.get()` returns `Any | None` which the dict literal cannot narrow to str
                        "id": data.get("id"),  # type: ignore
                        # reason: same as above — `Any | None` cannot narrow to str
                        "name": data.get("name"),  # type: ignore
                        # reason: same as above — `Any | dict[Any, Any]` cannot narrow to dict[str, Any] for the literal value
                        "args": data.get("args") or {},  # type: ignore
                    }
                elif kind == "tool_result" and isinstance(data, dict):
                    payload = {
                        "type": "tool_result",
                        "message_id": gm_id,
                        # reason: `data` is `Any` (no annotation on on_event); `.get()` returns `Any | None` which the dict literal cannot narrow to str
                        "tool_call_id": data.get("tool_call_id"),  # type: ignore
                        # reason: same as above — `Any | None` cannot narrow to str
                        "name": data.get("name"),  # type: ignore
                        # reason: same as above — `Any | None` cannot narrow to str
                        "result_preview": data.get("result_preview"),  # type: ignore
                        # reason: same as above — `Any | None` cannot narrow to str
                        "error": data.get("error"),  # type: ignore
                    }
                else:
                    # Unknown kind or legacy single-arg call: treat as narrative token.
                    if isinstance(data, str):
                        streamed_tokens = True
                        payload = {"type": "token", "message_id": gm_id, "token": data}
                    else:
                        return
                if not await _send_ws_payload(websocket, payload):
                    delivered = False
                else:
                    await fanout_event(session_id, payload, exclude=websocket)

            # reason: `stream_callback_var` is `ContextVar[None]` (no type parameter at the var site), so `.set()` is typed as accepting only None; passing the `on_event` callback to register it for this turn violates that
            token_cv = stream_callback_var.set(on_event)  # type: ignore
            try:
                session = _SESSIONS.get(session_id, {})
                if session.get("mode") == "world_architect":
                    narrative, meta = await _run_world_architect_turn(
                        session_id,
                        content,
                        sessions=_SESSIONS,
                        messages=_MESSAGES,
                        db_save_session=_db_save_session,
                        db_load_messages=_db_load_messages,
                    )
                elif session.get("phase") in (
                    "awaiting_character",
                    "character_interview",
                    "char_creation",
                    "session_zero",
                ):
                    narrative, meta = await _run_preplay_turn(
                        session_id,
                        content,
                        sessions=_SESSIONS,
                        messages=_MESSAGES,
                        db_save_session=_db_save_session,
                        db_save_message=_db_save_message,
                        session_game_system_doc=_session_game_system_doc,
                        gsr_available=_GSR_AVAILABLE,
                    )
                else:
                    narrative, meta = await _run_scene_turn(
                        session_id,
                        content,
                        sessions=_SESSIONS,
                        messages=_MESSAGES,
                        db_save_session=_db_save_session,
                        db_load_messages=_db_load_messages,
                        bootstrap_story_scene=_bootstrap_story_scene,
                        session_game_system_doc=_session_game_system_doc,
                        gsr_available=_GSR_AVAILABLE,
                    )
            finally:
                stream_callback_var.reset(token_cv)

            if not delivered:
                break

            if meta.get("type") == "llm_provider_error":
                # A provider-level failure (rate limit, quota, auth) with no
                # narration to show. Surface it through the same "error"
                # frame + sendFailure card the frontend already renders for
                # client-side timeouts, instead of streaming a fake GM
                # message — the player should see "the AI hit a limit,
                # retry", not a blank or placeholder turn.
                error_payload = {
                    "type": "error",
                    "message_id": gm_id,
                    "detail": narrative,
                    "error_class": meta.get("error_class"),
                }
                await _send_ws_payload(websocket, error_payload)
                await fanout_event(session_id, error_payload, exclude=websocket)
                break

            if not streamed_tokens:
                for word in narrative.split():
                    token_payload = {
                        "type": "token",
                        "message_id": gm_id,
                        "token": word + " ",
                    }
                    if not await _send_ws_payload(websocket, token_payload):
                        delivered = False
                        break
                    await fanout_event(session_id, token_payload, exclude=websocket)
                    await asyncio.sleep(_WS_TOKEN_DELAY_SECONDS)

            if not delivered:
                break

            gm_msg = _make_gm_msg(session_id, narrative, meta)
            gm_msg["id"] = gm_id
            msgs.append(gm_msg)
            _db_save_message(gm_msg)

            if session_id in _SESSIONS:
                if meta.get("working_state"):
                    _SESSIONS[session_id]["latest_working_state"] = meta["working_state"]
                if meta.get("scene_checkpoint"):
                    _SESSIONS[session_id]["latest_scene_checkpoint"] = meta["scene_checkpoint"]
                if meta.get("social_read"):
                    _SESSIONS[session_id]["latest_social_read"] = meta["social_read"]
                if meta.get("relationship_snapshot"):
                    _SESSIONS[session_id]["latest_relationship_snapshot"] = meta["relationship_snapshot"]
                _SESSIONS[session_id]["updated_at"] = _now()
                _db_save_session(_SESSIONS[session_id])

            done_payload = {"type": "done", "message_id": gm_id, "metadata": meta}
            if not await _send_ws_payload(websocket, done_payload):
                break
            await fanout_event(session_id, done_payload, exclude=websocket)

    except WebSocketDisconnect:
        pass
    finally:
        ws_unregister(session_id, websocket)
