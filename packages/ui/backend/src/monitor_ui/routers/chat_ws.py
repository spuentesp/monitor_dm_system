"""WebSocket fanout and subscription management for the Play chat router.

Extracted from ``chat.py`` to keep the route handler focused on HTTP orchestration
while this module handles real-time event broadcasting via WebSocket and Redis pub/sub.

Responsibilities:
  - Track per-session WebSocket subscribers
  - Broadcast events locally (in-process) and across processes (Redis pub/sub)
  - Fan-out completed GM messages token-by-token for typing effect
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

# Max concurrent WebSocket fanout tasks
_WS_INSTANCE_ID = str(uuid.uuid4())
_WS_TOKEN_DELAY_SECONDS = 0.04
_WS_LISTENER_POLL_TIMEOUT_SECONDS = 1.0
_WS_LISTENER_IDLE_SLEEP_SECONDS = 0.05


# ---------------------------------------------------------------------------
# Mutable state (module-level, scoped to this subsystem)
# ---------------------------------------------------------------------------

_WS_SUBSCRIBERS: dict[str, set[WebSocket]] = {}
_WS_FANOUT_TASKS: dict[str, asyncio.Task[None]] = {}


# ---------------------------------------------------------------------------
# Channel helpers
# ---------------------------------------------------------------------------


def _ws_event_channel(session_id: str) -> str:
    return f"chat_events:{session_id}"


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


async def send_payload(websocket: WebSocket, payload: dict[str, Any]) -> bool:
    """Send a JSON payload to a single WebSocket; return False on failure."""
    try:
        await websocket.send_text(json.dumps(payload))
        return True
    except Exception as exc:
        logger.debug("websocket send failed for %s: %s", payload.get("type"), exc)
        return False


async def broadcast_local(
    session_id: str,
    payload: dict[str, Any],
    *,
    exclude: WebSocket | None = None,
) -> None:
    """Broadcast *payload* to all local subscribers for *session_id*."""
    listeners = list(_WS_SUBSCRIBERS.get(session_id, set()))
    if not listeners:
        return

    stale: list[WebSocket] = []
    for listener in listeners:
        if exclude is not None and listener is exclude:
            continue
        if not await send_payload(listener, payload):
            stale.append(listener)

    for listener in stale:
        unregister(session_id, listener)


def publish_redis_event(session_id: str, payload: dict[str, Any]) -> None:
    """Publish a fanout event to Redis so other backend processes relay it."""
    try:
        from monitor_data.db.redis import get_redis_client

        get_redis_client().publish_json(
            _ws_event_channel(session_id),
            {
                "event_type": "ws_fanout",
                "session_id": session_id,
                "origin": _WS_INSTANCE_ID,
                "payload": payload,
            },
        )
    except Exception as exc:
        logger.debug("publish websocket fanout failed for %s: %s", session_id, exc)


def _ensure_listener(session_id: str) -> None:
    """Create a Redis listener task if one isn't already running."""
    task = _WS_FANOUT_TASKS.get(session_id)
    if task is not None and not task.done():
        return

    try:
        from monitor_data.db.redis import get_redis_client

        client = get_redis_client()
    except Exception as exc:
        logger.debug("Redis websocket fanout unavailable for %s: %s", session_id, exc)
        return

    if not client.is_available():
        return

    _WS_FANOUT_TASKS[session_id] = asyncio.create_task(_listen_for_events(session_id))


def register(session_id: str, websocket: WebSocket) -> None:
    """Subscribe *websocket* to events for *session_id*."""
    _WS_SUBSCRIBERS.setdefault(session_id, set()).add(websocket)
    _ensure_listener(session_id)


def unregister(session_id: str, websocket: WebSocket) -> None:
    """Unsubscribe *websocket*; cancel the listener if no subscribers remain."""
    listeners = _WS_SUBSCRIBERS.get(session_id)
    if listeners is None:
        return
    listeners.discard(websocket)
    if listeners:
        return

    _WS_SUBSCRIBERS.pop(session_id, None)
    task = _WS_FANOUT_TASKS.pop(session_id, None)
    if task is not None and not task.done():
        task.cancel()


async def _listen_for_events(session_id: str) -> None:
    """Long-lived Redis pub/sub listener that relays cross-process events."""
    client = None
    pubsub = None
    try:
        from monitor_data.db.redis import get_redis_client

        client = get_redis_client()
        pubsub = await asyncio.to_thread(client.create_pubsub, _ws_event_channel(session_id))
        if pubsub is None:
            return

        while _WS_SUBSCRIBERS.get(session_id):
            event = await asyncio.to_thread(
                client.get_pubsub_message_json,
                pubsub,
                timeout=_WS_LISTENER_POLL_TIMEOUT_SECONDS,
            )
            if not isinstance(event, dict):
                await asyncio.sleep(_WS_LISTENER_IDLE_SLEEP_SECONDS)
                continue
            if event.get("event_type") != "ws_fanout":
                continue
            if event.get("origin") == _WS_INSTANCE_ID:
                continue
            payload = event.get("payload")
            if isinstance(payload, dict):
                await broadcast_local(session_id, payload)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.debug("Redis websocket listener stopped for %s: %s", session_id, exc)
    finally:
        if client is not None and pubsub is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(client.close_pubsub, pubsub)
        _WS_FANOUT_TASKS.pop(session_id, None)


# ---------------------------------------------------------------------------
# High-level fanout
# ---------------------------------------------------------------------------


async def fanout_event(
    session_id: str,
    payload: dict[str, Any],
    *,
    exclude: WebSocket | None = None,
    publish: bool = True,
) -> None:
    """Broadcast locally and optionally publish to Redis for cross-process relay."""
    await broadcast_local(session_id, payload, exclude=exclude)
    if publish:
        publish_redis_event(session_id, payload)


async def fanout_completed_gm_message(
    session_id: str,
    gm_msg: dict[str, Any],
    *,
    exclude: WebSocket | None = None,
) -> None:
    """Stream a completed GM message token-by-token for the typing effect.

    Emits additive `phase` events before `start` so the frontend can show
    an honest "GM is thinking" indicator (UI-2). The events are best-effort:
    a failure to emit any one of them does NOT block the turn — the rest
    are still streamed. This preserves back-compat: clients that ignore
    `phase` still get `start`/`token`/`done` and the message renders.
    """
    message_id = str(gm_msg.get("id") or uuid.uuid4())

    # Best-effort phase hints. Each emit is independent — if one fails, the
    # rest still go out. The set of phases is intentionally small (3-4) so
    # we don't drown the socket in noise; the frontend has a copy mapping
    # and falls back to "Thinking…" for unknown values.
    for phase in ("assembling_context", "narrating"):
        try:
            await fanout_event(
                session_id,
                {"type": "phase", "phase": phase, "message_id": message_id},
                exclude=exclude,
            )
        except Exception as exc:
            logger.debug(
                "ws.phase emit failed (phase=%s, session=%s): %s",
                phase,
                session_id,
                exc,
            )

    await fanout_event(session_id, {"type": "start", "message_id": message_id}, exclude=exclude)
    for word in str(gm_msg.get("content") or "").split():
        await fanout_event(
            session_id,
            {"type": "token", "message_id": message_id, "token": word + " "},
            exclude=exclude,
        )
        await asyncio.sleep(_WS_TOKEN_DELAY_SECONDS)
    await fanout_event(
        session_id,
        {
            "type": "done",
            "message_id": message_id,
            "metadata": gm_msg.get("metadata", {}),
        },
        exclude=exclude,
    )
