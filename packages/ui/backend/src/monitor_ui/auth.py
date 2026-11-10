"""Authentication, principal resolution, CSRF, and rate limiting for the UI backend.

Implements Phase 2 of docs/architecture/MULTI_TENANCY_PLAN.md:

- Opaque browser session tokens (cookie holds the raw token, Postgres stores
  only its SHA-256 hash) and per-user revocable API tokens for non-browser
  OpenAI-compatible clients (Authorization: Bearer).
- ``MONITOR_AUTH_DISABLED=true`` resolves every request to a fixed local
  admin account — an explicit local-development exception, never a production
  rollback mechanism.
- ``get_current_ws_principal`` is the WebSocket counterpart of
  ``get_current_user``: the same credentials, but a failed handshake is closed
  with a WebSocket close code instead of an HTTP status.
- Deny by default: no valid session/API token → 401. Missing or expired
  server-side credentials fail closed.
- In-memory per-key rate limiting for login attempts (keyed by normalized
  login + trusted client IP).

CSRF protection for cookie-authenticated unsafe requests lives in
``main.py`` (``_csrf_middleware``) so it covers every router without
per-route wiring.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Request, WebSocket, WebSocketException, status

from monitor_data.db.postgres import PostgresClient, get_postgres_client
from monitor_data.schemas.users import UserResponse
from monitor_data.security import hash_password, hash_token

from monitor_ui.config import UISettings, get_settings

log = structlog.get_logger()

# Fixed identity for MONITOR_AUTH_DISABLED local-development mode (plan D5).
LOCAL_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
LOCAL_USER_EMAIL = "local@monitor.invalid"
LOCAL_USER_USERNAME = "local"


def is_local_mode(principal: "Principal") -> bool:
    """True in auth-disabled local mode.

    Fail closed: a principal without a ``via`` attribute (e.g. a raw Depends
    default leaked into a direct call) raises AttributeError instead of being
    silently treated as local mode.
    """
    return principal.via == "local"


@dataclass(frozen=True)
class Principal:
    """The authenticated caller for one request. Never carries secrets."""

    user_id: UUID
    is_admin: bool
    via: str  # "session" | "api_token" | "local"


def public_user(row: dict[str, Any]) -> UserResponse:
    """Project a raw ``users`` row onto the secret-free response contract."""
    return UserResponse(
        id=row["id"],
        email=row["email"],
        username=row["username"],
        display_name=row.get("display_name", ""),
        is_admin=bool(row.get("is_admin", False)),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def get_postgres() -> PostgresClient:
    """FastAPI dependency: connected shared Postgres client (ownership registry)."""
    client = get_postgres_client()
    await client.connect()
    return client


# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per-process; adequate for a single-instance UI)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Fixed-window-per-key limiter. ``hit`` returns True when allowed."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self._limit = max(1, limit)
        self._window = max(1, window_seconds)
        self._hits: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    _MAX_KEYS = 10_000  # bound memory: spraying fake keys cannot grow this forever

    async def hit(self, key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            if len(self._hits) >= self._MAX_KEYS and key not in self._hits:
                # evict an arbitrary (oldest-inserted) key to stay bounded
                self._hits.pop(next(iter(self._hits)))
            dq = self._hits.setdefault(key, deque())
            while dq and now - dq[0] >= self._window:
                dq.popleft()
            if len(dq) >= self._limit:
                return False
            dq.append(now)
            return True


_login_limiter: RateLimiter | None = None


def get_login_limiter(settings: UISettings) -> RateLimiter:
    """Process-wide login limiter configured from settings.

    Recreated when settings change so tests can adjust limits via env vars.
    """
    global _login_limiter
    if (
        _login_limiter is None
        or _login_limiter._limit != settings.auth_login_rate_limit
        or _login_limiter._window != settings.auth_rate_window_seconds
    ):
        _login_limiter = RateLimiter(settings.auth_login_rate_limit, settings.auth_rate_window_seconds)
    return _login_limiter


_signup_limiter: RateLimiter | None = None


def get_signup_limiter(settings: UISettings) -> RateLimiter:
    """Process-wide signup limiter (per client IP), configured from settings."""
    global _signup_limiter
    if (
        _signup_limiter is None
        or _signup_limiter._limit != settings.auth_signup_rate_limit
        or _signup_limiter._window != settings.auth_rate_window_seconds
    ):
        _signup_limiter = RateLimiter(settings.auth_signup_rate_limit, settings.auth_rate_window_seconds)
    return _signup_limiter


def client_ip(request: Request, settings: UISettings) -> str:
    """Client IP, honoring X-Forwarded-For only from configured trusted proxies."""
    host = request.client.host if request.client else "unknown"
    if host in settings.trusted_proxies_list:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return host


# ---------------------------------------------------------------------------
# Principal resolution
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_expired(expires_at: Any) -> bool:
    if expires_at is None:
        return False
    if isinstance(expires_at, str):
        # Some rows cross the asyncpg boundary as ISO strings; normalize.
        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return bool(expires_at <= _utcnow())


def _check_not_banned(user: dict[str, Any]) -> None:
    """Banned accounts get 403 on every authenticated request."""
    if user.get("is_banned"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended.",
        )


async def _principal_from_session(db: PostgresClient, raw_token: str) -> Principal:
    token_hash = hash_token(raw_token)
    session = await db.session_get(token_hash)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if _is_expired(session.get("expires_at")):
        await db.session_delete(token_hash)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    await db.session_touch(token_hash)
    user = await db.user_get_by_id(session["user_id"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    _check_not_banned(user)
    return Principal(user_id=user["id"], is_admin=bool(user.get("is_admin", False)), via="session")


async def _principal_from_api_token(db: PostgresClient, raw_token: str) -> Principal:
    token_hash = hash_token(raw_token)
    token = await db.api_token_get_by_hash(token_hash)
    if token is None or token.get("revoked_at") is not None or _is_expired(token.get("expires_at")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    await db.api_token_touch(token_hash)
    user = await db.user_get_by_id(token["user_id"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    _check_not_banned(user)
    return Principal(user_id=user["id"], is_admin=bool(user.get("is_admin", False)), via="api_token")


async def _local_principal(db: PostgresClient) -> Principal:
    """Auth-disabled mode: resolve to the fixed local admin account.

    The local account is created on first use with a random, unusable
    password hash — an operator enabling auth later must set its password
    explicitly via the local password-setting command (plan D5).
    """
    user = await db.user_get_by_id(LOCAL_USER_ID)
    if user is None:
        user = await db.user_create(
            {
                "id": LOCAL_USER_ID,
                "email": LOCAL_USER_EMAIL,
                "email_normalized": LOCAL_USER_EMAIL,
                "username": LOCAL_USER_USERNAME,
                "username_normalized": LOCAL_USER_USERNAME,
                "password_hash": hash_password(secrets.token_urlsafe(32)),
                "display_name": "Local developer",
                "is_admin": True,
            }
        )
    return Principal(user_id=user["id"], is_admin=True, via="local")


async def resolve_principal(
    *,
    authorization: str | None,
    cookies: dict[str, str],
    settings: UISettings,
    db: PostgresClient,
) -> Principal:
    """Resolve a principal from raw credentials (HTTP or WebSocket). Raises 401.

    Shared by the HTTP dependency and the WebSocket handler so both surfaces
    enforce identical rules: bearer token first, then session cookie, else 401.
    """
    if settings.monitor_auth_disabled:
        return await _local_principal(db)
    if authorization and authorization.lower().startswith("bearer "):
        return await _principal_from_api_token(db, authorization[7:].strip())
    session_cookie = cookies.get(settings.auth_session_cookie)
    if session_cookie:
        return await _principal_from_session(db, session_cookie)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_current_user(
    request: Request,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
) -> Principal:
    """Resolve the authenticated principal or raise 401. Deny by default."""
    return await resolve_principal(
        authorization=request.headers.get("authorization"),
        cookies=dict(request.cookies),
        settings=settings,
        db=db,
    )


async def get_optional_principal(
    request: Request,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
) -> Principal | None:
    """Like get_current_user but returns None when unauthenticated (public routes)."""
    try:
        return await get_current_user(request, settings, db)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return None
        raise


async def get_current_ws_principal(
    websocket: WebSocket,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
) -> Principal:
    """Resolve the principal for a WebSocket handshake, or close the socket.

    The WebSocket surface cannot answer with an HTTP status code, so an
    unauthenticated handshake is closed with 4401 and a rejected (non-401)
    credential with 4404 — the codes the chat WebSocket has always used.

    ``WebSocketException`` is what Starlette's exception middleware turns
    into a clean ``websocket.close`` frame; a bare ``WebSocketDisconnect``
    would escape the middleware and the ASGI server would answer with an
    internal-error close instead of the code the client expects.
    Fails closed on any unexpected error.
    """
    try:
        return await resolve_principal(
            authorization=websocket.headers.get("authorization"),
            cookies=dict(websocket.cookies),
            settings=settings,
            db=db,
        )
    except HTTPException as exc:
        code = 4401 if exc.status_code == status.HTTP_401_UNAUTHORIZED else 4404
        raise WebSocketException(code=code) from None
    except Exception as exc:  # noqa: BLE001  # reason: WS boundary fails closed on any unexpected error
        log.warning("websocket auth failed", exc_info=True)
        raise WebSocketException(code=4401) from exc


async def require_admin(principal: Principal = Depends(get_current_user)) -> Principal:
    """Operator-only routes: authenticated AND admin, else 403."""
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return principal


# ---------------------------------------------------------------------------
# Daily usage quota (multi-tenancy)
# ---------------------------------------------------------------------------
#
# Daily caps come from ``MONITOR_DAILY_TOKEN_CAP`` / ``MONITOR_DAILY_CALL_CAP``
# (unset = no cap); a per-user override row (``user_usage_limits``, admin-
# managed) wins over the env defaults. Admins and the auth-disabled local
# account are never capped. Every model-spending request charges one call
# through ``usage_quota_guard``; real token counts are added by the LLM layer
# via ``PostgresClient.usage_record`` (see MULTI_TENANCY_PLAN.md).

QUOTA_TOKEN_CAP_ENV = "MONITOR_DAILY_TOKEN_CAP"
QUOTA_CALL_CAP_ENV = "MONITOR_DAILY_CALL_CAP"

_quota_env_warned: set[str] = set()


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


async def effective_quota(principal: Principal, db: PostgresClient) -> tuple[int | None, int | None]:
    """The (token_cap, call_cap) in force for the user; ``None`` = no cap."""
    limits = await db.usage_limit_get(principal.user_id)
    token_cap = (limits or {}).get("daily_token_cap")
    if token_cap is None:
        token_cap = _env_cap(QUOTA_TOKEN_CAP_ENV)
    call_cap = (limits or {}).get("daily_call_cap")
    if call_cap is None:
        call_cap = _env_cap(QUOTA_CALL_CAP_ENV)
    return token_cap, call_cap


async def usage_quota_guard(
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> None:
    """Charge one call against the user's daily model quota (429 at the cap).

    Mounted on model-spending routes. Usage is recorded for every caller;
    caps apply to non-admin, non-local, non-exempt users only. The error is
    a readable 429 naming the cap and the UTC reset.
    """
    await db.usage_record(principal.user_id, calls=1)
    if principal.is_admin or is_local_mode(principal):
        return
    limits = await db.usage_limit_get(principal.user_id)
    if limits and limits.get("exempt"):
        return
    token_cap = (limits or {}).get("daily_token_cap")
    if token_cap is None:
        token_cap = _env_cap(QUOTA_TOKEN_CAP_ENV)
    call_cap = (limits or {}).get("daily_call_cap")
    if call_cap is None:
        call_cap = _env_cap(QUOTA_CALL_CAP_ENV)
    if call_cap is None and token_cap is None:
        return
    usage = await db.usage_get(principal.user_id)
    if call_cap is not None and int(usage.get("calls", 0)) > call_cap:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily model-call limit reached ({call_cap} calls). "
                "The limit resets at 00:00 UTC. Ask an admin to raise it if you need more."
            ),
        )
    if token_cap is not None and int(usage.get("tokens", 0)) >= token_cap:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily token limit reached ({token_cap} tokens). "
                "The limit resets at 00:00 UTC. Ask an admin to raise it if you need more."
            ),
        )


# ---------------------------------------------------------------------------
# Session-cookie helpers used by the auth router
# ---------------------------------------------------------------------------


def session_expiry(settings: UISettings) -> datetime:
    return _utcnow() + timedelta(hours=settings.auth_session_ttl_hours)


__all__ = [
    "LOCAL_USER_EMAIL",
    "LOCAL_USER_ID",
    "LOCAL_USER_USERNAME",
    "QUOTA_CALL_CAP_ENV",
    "QUOTA_TOKEN_CAP_ENV",
    "Principal",
    "RateLimiter",
    "client_ip",
    "effective_quota",
    "get_current_user",
    "get_current_ws_principal",
    "get_login_limiter",
    "get_signup_limiter",
    "get_optional_principal",
    "get_postgres",
    "public_user",
    "require_admin",
    "resolve_principal",
    "session_expiry",
    "usage_quota_guard",
]
