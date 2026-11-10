"""Per-owner daily model-usage accounting and quota enforcement (multi-tenancy).

LAYER: 1 (data-layer)
IMPORTS FROM: monitor_data.db, monitor_data.tenancy, external libraries only
CALLED BY: the LLM runtime (``monitor_agents.dspy_runtime``) and every other
    place that calls a model directly, plus the UI's ``usage_quota_guard``.

Spending is counted **per model call**, not per HTTP request: every model
call records ``calls=1`` plus the prompt/completion tokens for the acting
owner (``monitor_data.tenancy``), and the next model call fails with
:class:`QuotaExceededError` once the owner is over their daily token or call
cap. The HTTP ``usage_quota_guard`` is the pre-request face of the same
check and no longer charges per request (that would double-count).

No owner in context (auth-disabled local mode, scripts, ingestion workers,
tests) means no accounting and no enforcement — existing behavior there is
unchanged. Admin and exempt owners are recorded but never refused.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import structlog

from monitor_data.tenancy import get_owner_id

log = structlog.get_logger(__name__)

QUOTA_TOKEN_CAP_ENV = "MONITOR_DAILY_TOKEN_CAP"
QUOTA_CALL_CAP_ENV = "MONITOR_DAILY_CALL_CAP"

_quota_env_warned: set[str] = set()


class QuotaExceededError(RuntimeError):
    """Typed refusal: the acting owner is over their daily token or call cap.

    The HTTP layer maps this to a readable 429 and the chat WebSocket to a
    readable error event. ``kind`` is ``"token"`` or ``"call"``.
    """

    def __init__(self, kind: str, cap: int) -> None:
        self.kind = kind
        self.cap = cap
        self.user_message = (
            f"Daily {'token' if kind == 'token' else 'model-call'} limit reached ({cap} "
            f"{'tokens' if kind == 'token' else 'calls'}). The limit resets at 00:00 UTC. "
            "Ask an admin to raise it if you need more."
        )
        super().__init__(self.user_message)


def _env_cap(name: str) -> int | None:
    """Parse a daily-cap env var. Unset or invalid = no cap (warn once)."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        if name not in _quota_env_warned:
            _quota_env_warned.add(name)
            log.warning("quota_env_invalid", env=name, detail="not an integer; treated as no cap")
        return None
    return value if value >= 0 else None


def _effective_caps(limits: dict[str, Any] | None) -> tuple[int | None, int | None]:
    """The (token_cap, call_cap) in force: the per-user override wins over env."""
    token_cap = (limits or {}).get("daily_token_cap")
    if token_cap is None:
        token_cap = _env_cap(QUOTA_TOKEN_CAP_ENV)
    call_cap = (limits or {}).get("daily_call_cap")
    if call_cap is None:
        call_cap = _env_cap(QUOTA_CALL_CAP_ENV)
    return token_cap, call_cap


async def effective_caps(db: Any, user_id: UUID) -> tuple[int | None, int | None]:
    """The (token_cap, call_cap) in force for the user; ``None`` = no cap."""
    limits = await db.usage_limit_get(user_id)
    return _effective_caps(limits)


async def enforce_usage_quota(db: Any, user_id: UUID) -> None:
    """Raise :class:`QuotaExceededError` when the user is over their daily cap.

    Admins and exempt users are never refused. No cap configured = no
    enforcement. This is the single enforcement implementation shared by the
    pre-model-call check and the HTTP ``usage_quota_guard``.
    """
    limits = await db.usage_limit_get(user_id)
    if limits and limits.get("exempt"):
        return
    user = await db.user_get_by_id(user_id)
    if user and user.get("is_admin"):
        return
    token_cap, call_cap = _effective_caps(limits)
    if token_cap is None and call_cap is None:
        return
    usage = await db.usage_get(user_id)
    if call_cap is not None and int(usage.get("calls", 0)) >= call_cap:
        raise QuotaExceededError("call", call_cap)
    if token_cap is not None and int(usage.get("tokens", 0)) >= token_cap:
        raise QuotaExceededError("token", token_cap)


async def record_usage(db: Any, user_id: UUID, *, tokens: int = 0, calls: int = 0) -> None:
    """Add ``tokens``/``calls`` to the user's daily usage. Never raises.

    A failed usage write is logged and recorded (roleplay error doc) but
    never propagated into the turn it was accounting for.
    """
    try:
        await db.usage_record(user_id, tokens=tokens, calls=calls)
    except Exception as exc:  # noqa: BLE001  # reason: an accounting failure must never break the turn it describes
        log.warning("usage_record_failed", user_id=str(user_id), tokens=tokens, calls=calls, error=str(exc))
        await _record_usage_failure(exc)


async def _record_usage_failure(exc: Exception) -> None:
    """Best-effort durable record of a failed usage write. Never raises."""
    try:
        from monitor_data.schemas.roleplay_errors import (
            RoleplayError,
            RoleplayErrorCategory,
            RoleplayErrorSource,
        )
        from monitor_data.tools.mongodb_tools import mongodb_record_roleplay_error

        mongodb_record_roleplay_error(
            RoleplayError(
                source=RoleplayErrorSource.USAGE_ACCOUNTING,
                category=RoleplayErrorCategory.USAGE_WRITE_FAILED,
                message=f"usage_record_failed: {exc}",
                fatal=False,
            )
        )
    except Exception:  # noqa: BLE001  # reason: recording an error must never itself raise
        log.debug("usage_failure_record_failed", exc_info=True)


# ---------------------------------------------------------------------------
# Context-aware entry points for model-call sites (sync and async)
# ---------------------------------------------------------------------------


def _resolve_owner(expected_owner_id: str | UUID | None) -> UUID | None:
    raw = expected_owner_id if expected_owner_id is not None else get_owner_id()
    if raw is None:
        return None
    return UUID(str(raw))


def enforce_owner_quota(*, expected_owner_id: str | UUID | None = None) -> None:
    """Sync pre-model-call cap check for the acting owner (no owner = no-op)."""
    from monitor_data.db._utils import run_sync
    from monitor_data.db.postgres import get_postgres_client

    owner = _resolve_owner(expected_owner_id)
    if owner is None:
        return
    run_sync(enforce_usage_quota(get_postgres_client(), owner))


def record_model_usage(
    *,
    tokens: int = 0,
    calls: int = 1,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Sync post-model-call usage write for the acting owner (no owner = no-op)."""
    from monitor_data.db._utils import run_sync
    from monitor_data.db.postgres import get_postgres_client

    owner = _resolve_owner(expected_owner_id)
    if owner is None:
        return
    run_sync(record_usage(get_postgres_client(), owner, tokens=int(tokens), calls=int(calls)))


async def enforce_owner_quota_async(*, expected_owner_id: str | UUID | None = None) -> None:
    """Async pre-model-call cap check for the acting owner (no owner = no-op)."""
    from monitor_data.db.postgres import get_postgres_client

    owner = _resolve_owner(expected_owner_id)
    if owner is None:
        return
    await enforce_usage_quota(get_postgres_client(), owner)


async def record_model_usage_async(
    *,
    tokens: int = 0,
    calls: int = 1,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Async post-model-call usage write for the acting owner (no owner = no-op)."""
    from monitor_data.db.postgres import get_postgres_client

    owner = _resolve_owner(expected_owner_id)
    if owner is None:
        return
    await record_usage(get_postgres_client(), owner, tokens=int(tokens), calls=int(calls))


def tokens_from_response(response: Any) -> tuple[int, int] | None:
    """(prompt_tokens, completion_tokens) from a provider response's usage.

    Understands OpenAI-style (``prompt_tokens`` / ``completion_tokens``) and
    Anthropic-style (``input_tokens`` / ``output_tokens``) usage objects.
    ``None`` when the response carries no usable usage.
    """
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None
    get = usage.get if isinstance(usage, dict) else lambda k, d=None: getattr(usage, k, d)
    prompt = get("prompt_tokens", None)
    if prompt is None:
        prompt = get("input_tokens", None)
    completion = get("completion_tokens", None)
    if completion is None:
        completion = get("output_tokens", None)
    if prompt is None and completion is None:
        return None
    return int(prompt or 0), int(completion or 0)


def estimate_text_tokens(text: str) -> int:
    """Offline token estimate for a text (litellm counter, chars/4 fallback)."""
    try:
        import litellm

        return int(litellm.token_counter(text=text))
    except Exception:  # noqa: BLE001  # reason: estimation must never fail the call it describes
        return max(1, len(text) // 4)


async def record_completion_usage(
    *,
    messages: list[Any] | None = None,
    response: Any = None,
    output_text: str = "",
    calls: int = 1,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Record one text-model call against the acting owner's daily usage.

    Uses the provider response's real usage when present, offline estimates
    otherwise. Never raises (see :func:`record_usage`).
    """
    real = tokens_from_response(response)
    if real is not None:
        total = real[0] + real[1]
    else:
        prompt_text = "".join(str(m.get("content", "")) for m in (messages or []))
        total = estimate_text_tokens(prompt_text) + estimate_text_tokens(output_text)
    await record_model_usage_async(tokens=total, calls=calls, expected_owner_id=expected_owner_id)
