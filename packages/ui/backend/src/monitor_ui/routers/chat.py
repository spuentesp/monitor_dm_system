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

from monitor_agents.dspy_runtime import stream_callback_var

import asyncio
import contextlib
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .chat_schemas import (
    Message,
    MessageSend,
    Session,
    SessionCreate,
    SessionPatch,
    SessionStateResponse,
)
from .chat_persistence import (
    db_load_messages,
    db_load_sessions,
    db_save_message,
    db_save_session,
    ensure_sessions_loaded,
    purge_chat_runtime_cache,
)
from .chat_game_system import (
    _GSR_AVAILABLE,
    get_benchmark_config as _get_benchmark_config,
    resolve_universe_system_binding as _resolve_universe_system_binding,
    session_game_system_doc as _session_game_system_doc,
)
from .chat_ws import (
    _WS_FANOUT_TASKS,
    _WS_SUBSCRIBERS,
    _WS_TOKEN_DELAY_SECONDS,
    fanout_completed_gm_message,
    fanout_event,
    register as ws_register,
    send_payload as _send_ws_payload,
    unregister as ws_unregister,
)
from .chat_support import (
    VALID_TONES as _VALID_TONES,
    as_uuid,
    build_session_state_payload,
    handle_tone_command,
    make_gm_message,
    make_player_message,
    make_system_message,
    now_iso,
)
from .chat_opening import (
    bootstrap_story_scene as _bootstrap_story_scene,
    build_gm_opening as _build_gm_opening,
)
from .chat_loops import (
    pop_scene_loop as _pop_scene_loop,
    run_end_scene as _run_end_scene,
    run_preplay_turn as _run_preplay_turn,
    run_scene_turn as _run_scene_turn,
    run_world_architect_turn as _run_world_architect_turn,
)
from .chat_loops import (  # noqa: F401 — re-export for delete_session
    _CHAR_CREATION_LOOPS,
    pop_character_creation_loop as _pop_char_creation_loop,
    pop_conversation_loop as _pop_conversation_loop,
    pop_session_zero_loop as _pop_session_zero_loop,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Optional layer imports (graceful degradation)
# ---------------------------------------------------------------------------

try:
    from monitor_agents.loops.world_building_loop import WorldBuildingLoop

    _WORLD_ARCHITECT_AVAILABLE = True
except Exception:  # noqa: BLE001
    _WORLD_ARCHITECT_AVAILABLE = False

# ---------------------------------------------------------------------------
# In-process write-through cache
# ---------------------------------------------------------------------------
_SESSIONS: dict[str, dict] = {}
_MESSAGES: dict[str, list[dict]] = {}
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


def _make_gm_msg(
    session_id: str, content: str, metadata: dict | None = None
) -> dict[str, Any]:
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


def _handle_tone_command(
    content: str, session_id: str
) -> tuple[str, dict[str, Any]] | None:
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
            play_mode=s.get("play_mode", "dice_game_system"),
            chat_mode=s.get("chat_mode", "ic"),
            scene_id=s.get("scene_id"),
            story_id=s.get("story_id"),
            phase=s.get("phase", "awaiting_character"),
            created_at=s.get("created_at") or _now(),
            updated_at=s.get("updated_at") or _now(),
            message_count=len(_MESSAGES.get(sid, [])),
        )
        for sid, s in _SESSIONS.items()
    ]


@router.get("/benchmarks")
async def list_playtest_benchmarks() -> list[dict[str, Any]]:
    try:
        from monitor_data.defaults.playtest_benchmarks import (
            resolve_playtest_benchmarks,
        )

        return await asyncio.to_thread(
            resolve_playtest_benchmarks, include_scripted_turns=True
        )
    except Exception as exc:  # noqa: BLE001
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
        if "system_label" not in provided_fields and benchmark.get(
            "resolved_system_name"
        ):
            system_label = str(benchmark["resolved_system_name"])
        if "benchmark_label" not in provided_fields and benchmark.get("name"):
            benchmark_label = str(benchmark["name"])

    universe_id = body.universe_id or body.world_id
    if universe_id:
        binding = _resolve_universe_system_binding(universe_id)
        if (
            "system_id" not in provided_fields
            and not system_id
            and binding.get("system_id")
        ):
            system_id = str(binding["system_id"])
        if (
            "system_source_type" not in provided_fields
            and not system_source_type
            and binding.get("system_source_type")
        ):
            system_source_type = str(binding["system_source_type"])
        if (
            "system_source_id" not in provided_fields
            and not system_source_id
            and binding.get("system_source_id")
        ):
            system_source_id = str(binding["system_source_id"])
        if (
            "pack_id" not in provided_fields
            and not pack_id
            and binding.get("system_source_type") == "pack_embedded"
            and binding.get("system_source_id")
        ):
            pack_id = str(binding["system_source_id"])
        if (
            "system_label" not in provided_fields
            and not system_label
            and binding.get("system_name")
        ):
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
    controlled = body.controlled_character_ids or (
        [body.character_id] if body.character_id else []
    )

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
        "controlled_character_ids": controlled,
        "system_id": system_id,
        "pack_id": pack_id,
        "system_source_type": system_source_type,
        "system_source_id": system_source_id,
        "system_label": system_label,
        "benchmark_id": body.benchmark_id,
        "benchmark_label": benchmark_label,
        "tone": tone,
        "gm_profile_id": body.gm_profile_id,
        "play_mode": play_mode,
        "chat_mode": body.chat_mode,
        "scene_id": body.scene_id,
        "story_id": body.story_id,
        "created_at": now,
        "updated_at": now,
    }

    story_id: str | None = None
    scene_id: str | None = None
    bootstrap_error: str | None = None

    if body.mode != "world_architect":
        story_id, scene_id, bootstrap_error = _bootstrap_story_scene(session)
        session["story_id"] = story_id
        session["scene_id"] = scene_id

    if body.mode == "world_architect":
        session["phase"] = "active_play"
    elif body.character_id or body.controlled_character_ids:
        session["phase"] = "active_play"
    else:
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
                    messages.append(
                        _make_gm_msg(
                            sid, welcome_text, {"type": "world_architect_welcome"}
                        )
                    )
            except Exception:  # noqa: BLE001
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
        gm_text, gm_meta = await _build_gm_opening(
            sid,
            session,
            session_game_system_doc=_session_game_system_doc,
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
    and high-magnitude facts from Neo4j into a prose summary.
    """
    _ensure_sessions_loaded()
    session = _SESSIONS.get(session_id)
    if not session:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Session not found")

    story_id = session.get("story_id")
    universe_id = session.get("universe_id") or session.get("world_id")

    if not story_id or not universe_id:
        return {
            "recap": "No story is active yet. Start playing to build history.",
            "story_id": story_id,
            "universe_id": universe_id,
        }

    try:
        from monitor_agents.recap_agent import RecapAgent

        agent = RecapAgent()
        recap_text = await agent.generate_recap(
            story_id=uuid.UUID(story_id),
            universe_id=uuid.UUID(universe_id),
            tone_context="Evocative narrative summary for the player.",
        )
        if not recap_text or len(recap_text.strip()) < 20:
            recap_text = (
                "The story is just beginning. Every legend starts with a first step."
            )
    except ImportError:
        recap_text = "The recap engine is not available right now."
    except Exception as exc:  # noqa: BLE001
        logger.warning("RecapAgent endpoint failed (session=%s): %s", session_id, exc)
        recap_text = "I couldn't gather the story threads right now. Try again later."

    return {
        "recap": recap_text,
        "story_id": story_id,
        "universe_id": universe_id,
    }


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
    elif session.get("phase") in ("awaiting_character", "char_creation", "session_zero"):
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
    elif session.get("phase") == "scene_end":
        # Between scenes: bootstrap the next scene or let the player continue
        story_id, scene_id, _ = _bootstrap_story_scene(session)
        _db_save_session(session)
        if scene_id:
            narrative = (
                "The world settles. A new scene opens before you — what do you do?"
            )
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
            _SESSIONS[session_id]["latest_relationship_snapshot"] = meta[
                "relationship_snapshot"
            ]
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
    except Exception as exc:  # noqa: BLE001
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
            content: str = data.get("content", "")

            now = _now()
            msgs = _MESSAGES.setdefault(session_id, [])

            # Handle dice_result
            if msg_type == "dice_result":
                spec: str = data.get("spec", "")
                value: int = int(data.get("value", 0))
                rolls: list = data.get("rolls", [])
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

            async def on_event(kind: str, data):
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
                        "id": data.get("id"),
                        "name": data.get("name"),
                        "args": data.get("args") or {},
                    }
                elif kind == "tool_result" and isinstance(data, dict):
                    payload = {
                        "type": "tool_result",
                        "message_id": gm_id,
                        "tool_call_id": data.get("tool_call_id"),
                        "name": data.get("name"),
                        "result_preview": data.get("result_preview"),
                        "error": data.get("error"),
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

            token_cv = stream_callback_var.set(on_event)
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
