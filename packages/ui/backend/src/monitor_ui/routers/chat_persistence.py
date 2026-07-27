"""Mongo-backed persistence helpers for Play chat sessions and messages.

Phase 2 adds an optional Redis layer for hot shared-cache reads across backend
processes. MongoDB remains the source of truth; Redis is write-through and
best-effort only.
"""

from __future__ import annotations

import logging
from typing import Any

from monitor_data.config import settings

logger = logging.getLogger(__name__)

_CHAT_CACHE_TTL_SECONDS = max(int(getattr(settings, "redis_cache_ttl_seconds", 30) or 30) * 20, 300)
_CHAT_MESSAGES_LIMIT = 500
_SESSION_INDEX_KEY = "chat_sessions:index"


def _session_cache_key(session_id: str) -> str:
    return f"chat_session:{session_id}"


def _messages_cache_key(session_id: str) -> str:
    return f"chat_messages:{session_id}"


def _redis_get_json(key: str) -> Any | None:
    try:
        from monitor_data.db.redis import get_redis_client

        return get_redis_client().get_json(key)
    except Exception as exc:
        logger.debug("redis get failed for %s: %s", key, exc)
        return None


def _redis_set_json(key: str, value: Any) -> None:
    try:
        from monitor_data.db.redis import get_redis_client

        get_redis_client().set_json(key, value, ttl=_CHAT_CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.debug("redis set failed for %s: %s", key, exc)


def _redis_delete(*keys: str) -> int:
    try:
        from monitor_data.db.redis import get_redis_client

        return get_redis_client().delete(*keys)
    except Exception as exc:
        logger.debug("redis delete failed for %s: %s", keys, exc)
        return 0


def _publish_chat_event(session_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Publish a lightweight coordination event for future websocket fan-out."""
    try:
        from monitor_data.db.redis import get_redis_client

        get_redis_client().publish_json(
            f"chat_events:{session_id}",
            {
                "event_type": event_type,
                "session_id": session_id,
                **payload,
            },
        )
    except Exception as exc:
        logger.debug("publish_chat_event failed for %s: %s", session_id, exc)


def purge_chat_runtime_cache(session_id: str) -> None:
    """Remove cached session/message state for a deleted or reset session."""
    _redis_delete(_session_cache_key(session_id), _messages_cache_key(session_id))
    cached_sessions = _redis_get_json(_SESSION_INDEX_KEY)
    if isinstance(cached_sessions, list):
        filtered = [row for row in cached_sessions if row.get("id") != session_id]
        _redis_set_json(_SESSION_INDEX_KEY, filtered)


def db_save_session(session: dict[str, Any]) -> None:
    """Upsert a session dict to MongoDB `chat_sessions` and warm the Redis cache."""
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        mdb = get_mongodb_client()
        col = mdb.get_collection("chat_sessions")
        col.replace_one({"id": session["id"]}, session, upsert=True)

        _redis_set_json(_session_cache_key(session["id"]), session)
        cached_sessions = _redis_get_json(_SESSION_INDEX_KEY)
        rows = cached_sessions if isinstance(cached_sessions, list) else []
        rows = [row for row in rows if row.get("id") != session["id"]]
        rows.append(session)
        rows.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
        _redis_set_json(_SESSION_INDEX_KEY, rows[:200])
        _publish_chat_event(session["id"], "session_saved", {"updated_at": session.get("updated_at")})
    except Exception as exc:
        logger.debug("db_save_session failed: %s", exc)


def db_load_sessions() -> list[dict[str, Any]]:
    """Load all chat sessions, preferring the shared Redis cache when warm."""
    cached = _redis_get_json(_SESSION_INDEX_KEY)
    if isinstance(cached, list):
        return cached

    try:
        from monitor_data.db.mongodb import get_mongodb_client

        mdb = get_mongodb_client()
        col = mdb.get_collection("chat_sessions")
        rows = list(col.find({}, {"_id": 0}, sort=[("updated_at", -1)]))
        _redis_set_json(_SESSION_INDEX_KEY, rows)
        for row in rows[:200]:
            session_id = row.get("id")
            if session_id:
                _redis_set_json(_session_cache_key(str(session_id)), row)
        return rows
    except Exception as exc:
        logger.debug("db_load_sessions failed: %s", exc)
        return []


def db_save_message(msg: dict[str, Any]) -> None:
    """Upsert a single message into MongoDB `chat_messages` and refresh Redis state."""
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        mdb = get_mongodb_client()
        col = mdb.get_collection("chat_messages")
        col.replace_one({"id": msg["id"]}, msg, upsert=True)

        session_id = str(msg.get("session_id") or "")
        if session_id:
            cache_key = _messages_cache_key(session_id)
            cached_messages = _redis_get_json(cache_key)
            if isinstance(cached_messages, list):
                existing_index = next(
                    (i for i, item in enumerate(cached_messages) if item.get("id") == msg["id"]),
                    None,
                )
                if existing_index is None:
                    cached_messages.append(msg)
                else:
                    cached_messages[existing_index] = msg
                cached_messages.sort(key=lambda row: row.get("timestamp", ""))
                _redis_set_json(cache_key, cached_messages[-_CHAT_MESSAGES_LIMIT:])
            else:
                rows = list(col.find({"session_id": session_id}, {"_id": 0}, sort=[("timestamp", 1)]))
                _redis_set_json(cache_key, rows[-_CHAT_MESSAGES_LIMIT:])

            _publish_chat_event(
                session_id,
                "message_saved",
                {
                    "message_id": msg.get("id"),
                    "role": msg.get("role"),
                    "timestamp": msg.get("timestamp"),
                },
            )
    except Exception as exc:
        logger.debug("db_save_message failed: %s", exc)


def db_load_messages(session_id: str) -> list[dict[str, Any]]:
    """Load all messages for a session, preferring the shared Redis cache when warm."""
    cache_key = _messages_cache_key(session_id)
    cached = _redis_get_json(cache_key)
    if isinstance(cached, list):
        return cached

    try:
        from monitor_data.db.mongodb import get_mongodb_client

        mdb = get_mongodb_client()
        col = mdb.get_collection("chat_messages")
        rows = list(col.find({"session_id": session_id}, {"_id": 0}, sort=[("timestamp", 1)]))
        _redis_set_json(cache_key, rows[-_CHAT_MESSAGES_LIMIT:])
        return rows
    except Exception as exc:
        logger.debug("db_load_messages failed: %s", exc)
        return []


def ensure_sessions_loaded(
    sessions: dict[str, dict[str, Any]],
    *,
    loaded_from_db: bool,
) -> bool:
    """Rehydrate the in-process sessions cache from MongoDB on first access."""
    if loaded_from_db:
        return True

    for row in db_load_sessions():
        session_id = row.get("id")
        if session_id and session_id not in sessions:
            sessions[session_id] = row
    return True
