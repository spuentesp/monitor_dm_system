"""Image-generation budget enforcement (Task 10, UI backend).

The router reserves a slot in three budgets **before** invoking the
provider and rolls back on provider/upload failure. This module owns
the counting and rollback logic; the router only calls the helpers.

Three scopes share the same machinery:

- ``scene`` — count of successful generations in the current scene.
- ``conversation`` — count of successful generations in the current
  conversation / play session.
- ``actor_hour`` — count of successful generations per actor in the
  last hour.

Counting strategy:

1. When Redis is available, we use atomic ``INCR`` + ``EXPIRE`` to
   track the counter. This is the clean case: the count reflects
   only successful generations (the increment is rolled back on
   failure), and the expiry keeps the per-hour window honest.
2. When Redis is unavailable, we fall back to deriving the count
   from :class:`monitor_data.schemas.generated_assets.GeneratedAsset`
   documents. The query is the same shape Redis would have used
   (recent assets within the scope); a structlog warning is emitted
   so operators see the fallback happen.

A ``0`` limit in any of the three settings disables that scope's
budget entirely (the test pin is the value the user sees in the UI).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import structlog

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.redis import get_redis_client
from monitor_data.schemas.image_settings import ImageGenerationSettings

log = structlog.get_logger()

_BUDGET_COLLECTION = "generated_assets"
_ACTOR_HOUR_WINDOW = timedelta(hours=1)
_REDIS_BUDGET_PREFIX = "image_budget:"


BudgetScope = Literal["scene", "conversation", "actor_hour"]


@dataclass(frozen=True)
class BudgetDecision:
    """Result of a budget check.

    ``allowed`` is False when the limit is reached. ``used`` and
    ``limit`` are reported so the router can include them in the 429
    payload; ``retry`` is human-readable retry guidance.
    """

    allowed: bool
    scope: BudgetScope
    used: int
    limit: int
    retry: str


def _retry_message(scope: BudgetScope, limit: int, used: int) -> str:
    if scope == "actor_hour":
        return (
            f"Per-actor generation cap reached ({used}/{limit}). "
            "Wait an hour or raise the limit in Settings → Image Generation."
        )
    if scope == "conversation":
        return (
            f"Per-conversation generation cap reached ({used}/{limit}). "
            "Start a new conversation or raise the limit in Settings → Image Generation."
        )
    return (
        f"Per-scene generation cap reached ({used}/{limit}). "
        "Move on to a new scene or raise the limit in Settings → Image Generation."
    )


def _redis_key(scope: BudgetScope, scope_key: str, actor_id: str | None) -> str:
    if scope == "actor_hour":
        return f"{_REDIS_BUDGET_PREFIX}actor_hour:{actor_id or 'unknown'}"
    return f"{_REDIS_BUDGET_PREFIX}{scope}:{scope_key}"


def _ttl_for_scope(scope: BudgetScope) -> int:
    return int(_ACTOR_HOUR_WINDOW.total_seconds()) if scope == "actor_hour" else 0


def _query_assets_for_scope(
    scope: BudgetScope,
    *,
    conversation_id: UUID | None,
    scene_id: UUID | None,
    actor_id: str | None,
    since: datetime | None,
) -> dict[str, Any]:
    """Build the MongoDB query that mirrors the Redis counter's scope."""
    query: dict[str, Any] = {}
    if scope == "scene" and scene_id is not None:
        query["scene_id"] = str(scene_id)
    elif scope == "conversation" and conversation_id is not None:
        query["conversation_id"] = str(conversation_id)
    elif scope == "actor_hour":
        if actor_id is not None:
            query["character_id"] = actor_id
        if since is not None:
            query["created_at"] = {"$gte": since}
    return query


def _derive_used_from_mongo(
    scope: BudgetScope,
    *,
    conversation_id: UUID | None,
    scene_id: UUID | None,
    actor_id: str | None,
    since: datetime | None,
) -> int:
    """Count asset documents within the given scope (fallback for Redis)."""
    query = _query_assets_for_scope(
        scope,
        conversation_id=conversation_id,
        scene_id=scene_id,
        actor_id=actor_id,
        since=since,
    )
    if not query:
        return 0
    try:
        coll = get_mongodb_client().get_collection(_BUDGET_COLLECTION)
        return int(coll.count_documents(query))
    except Exception as exc:
        log.warning(
            "image_budget.mongo_derive_failed",
            scope=scope,
            error=str(exc),
        )
        return 0


def _redis_is_available() -> bool:
    try:
        return bool(get_redis_client().is_available())
    except Exception:
        return False


def _redis_get_count(key: str) -> int | None:
    """Return the current count from Redis, or None if unavailable."""
    try:
        client = get_redis_client()
        if not client.is_available():
            return None
        raw = client._get_client().get(key)
        if raw is None:
            return 0
        return int(raw)
    except Exception:
        return None


def _redis_increment(key: str, ttl: int) -> int | None:
    """Atomic increment with TTL — returns the new value or None on failure.

    The Redis client doesn't expose a generic "increment with TTL"
    primitive, so we implement it as two calls (INCR + EXPIRE). The
    INCR is atomic; the EXPIRE is best-effort. If the process dies
    between them, the next INCR will reset the TTL.
    """
    try:
        client = get_redis_client()
        if not client.is_available():
            return None
        raw_client = client._get_client()
        new_value = int(raw_client.incr(key))
        if ttl > 0:
            try:
                raw_client.expire(key, ttl)
            except Exception:
                pass
        return new_value
    except Exception as exc:
        log.warning(
            "image_budget.redis_increment_failed",
            key=key,
            error=str(exc),
        )
        return None


def _redis_decrement(key: str) -> None:
    """Best-effort decrement used to roll back on provider failure."""
    try:
        client = get_redis_client()
        if not client.is_available():
            return
        raw_client = client._get_client()
        raw_client.decr(key)
    except Exception as exc:
        log.warning(
            "image_budget.redis_decrement_failed",
            key=key,
            error=str(exc),
        )


def _actor_hour_window_start() -> datetime:
    return datetime.now(UTC) - _ACTOR_HOUR_WINDOW


def check_budget(
    settings: ImageGenerationSettings,
    *,
    scope: BudgetScope,
    scope_key: str,
    actor_id: str | None,
) -> BudgetDecision:
    """Read-only check: is there room for one more generation in this scope?

    ``scope_key`` is the conversation/session id for the conversation
    scope, or any stable identifier for the scene scope (the scene
    id when known, otherwise the conversation id). ``actor_id`` is the
    character id for the actor-hour scope (and is unused for the other
    scopes).
    """
    limit = _limit_for(settings, scope)
    if limit == 0:
        return BudgetDecision(
            allowed=True,
            scope=scope,
            used=0,
            limit=0,
            retry="",
        )

    used = _current_used(
        scope=scope,
        scope_key=scope_key,
        actor_id=actor_id,
    )
    if used >= limit:
        return BudgetDecision(
            allowed=False,
            scope=scope,
            used=used,
            limit=limit,
            retry=_retry_message(scope, limit, used),
        )
    return BudgetDecision(
        allowed=True,
        scope=scope,
        used=used,
        limit=limit,
        retry="",
    )


def reserve_budget(
    settings: ImageGenerationSettings,
    *,
    scope: BudgetScope,
    scope_key: str,
    actor_id: str | None,
) -> BudgetDecision:
    """Atomically reserve a slot. Returns a blocked decision if over the cap.

    The reserve is **before** the provider invocation. Pair every
    successful reserve with :func:`release_budget` on any failure
    path so the budget stays honest.
    """
    limit = _limit_for(settings, scope)
    if limit == 0:
        return BudgetDecision(allowed=True, scope=scope, used=0, limit=0, retry="")

    if _redis_is_available():
        key = _redis_key(scope, scope_key, actor_id)
        ttl = _ttl_for_scope(scope)
        count = _redis_increment(key, ttl)
        if count is not None:
            if count > limit:
                # Over the cap after increment — release our slot and reject.
                _redis_decrement(key)
                return BudgetDecision(
                    allowed=False,
                    scope=scope,
                    used=count - 1,
                    limit=limit,
                    retry=_retry_message(scope, limit, count - 1),
                )
            return BudgetDecision(
                allowed=True,
                scope=scope,
                used=count,
                limit=limit,
                retry="",
            )

    # Redis was unavailable: fall back to deriving from Mongo.
    log.warning(
        "image_budget.redis_unavailable_using_mongo_fallback",
        scope=scope,
    )
    used = _derive_used_from_mongo(
        scope,
        conversation_id=UUID(scope_key) if scope == "conversation" else None,
        scene_id=UUID(scope_key) if scope == "scene" else None,
        actor_id=actor_id,
        since=_actor_hour_window_start() if scope == "actor_hour" else None,
    )
    if used >= limit:
        return BudgetDecision(
            allowed=False,
            scope=scope,
            used=used,
            limit=limit,
            retry=_retry_message(scope, limit, used),
        )
    return BudgetDecision(
        allowed=True,
        scope=scope,
        used=used,
        limit=limit,
        retry="",
    )


def release_budget(
    *,
    scope: BudgetScope,
    scope_key: str,
    actor_id: str | None,
) -> None:
    """Roll back a reserved slot (provider/upload failure)."""
    if not _redis_is_available():
        return  # Mongo fallback can't be decremented cleanly
    _redis_decrement(_redis_key(scope, scope_key, actor_id))


def _current_used(
    *,
    scope: BudgetScope,
    scope_key: str,
    actor_id: str | None,
) -> int:
    if _redis_is_available():
        key = _redis_key(scope, scope_key, actor_id)
        count = _redis_get_count(key)
        if count is not None:
            return count
    return _derive_used_from_mongo(
        scope,
        conversation_id=UUID(scope_key) if scope == "conversation" else None,
        scene_id=UUID(scope_key) if scope == "scene" else None,
        actor_id=actor_id,
        since=_actor_hour_window_start() if scope == "actor_hour" else None,
    )


def _limit_for(settings: ImageGenerationSettings, scope: BudgetScope) -> int:
    if scope == "scene":
        return int(settings.image_max_per_scene)
    if scope == "conversation":
        return int(settings.image_max_per_conversation)
    return int(settings.image_max_per_actor_hour)


__all__ = [
    "BudgetDecision",
    "BudgetScope",
    "check_budget",
    "release_budget",
    "reserve_budget",
]
