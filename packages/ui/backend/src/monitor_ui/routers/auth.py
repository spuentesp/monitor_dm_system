"""Authentication routes: signup, login, logout, current user, API tokens.

Phase 2 of docs/architecture/MULTI_TENANCY_PLAN.md. All private routes
resolve the caller through ``monitor_ui.auth.get_current_user``; browser
mutations additionally pass the double-submit CSRF middleware in main.py.

Password hashes and raw tokens never appear in responses or logs: the
session cookie holds the raw opaque token while Postgres stores only its
SHA-256 hash, and an API token's raw value is returned exactly once at
creation.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from monitor_data.db.postgres import PostgresClient
from monitor_data.schemas.users import (
    ApiTokenCreate,
    ApiTokenCreatedResponse,
    ApiTokenMetadataResponse,
    AuthModeResponse,
    LoginRequest,
    PasswordChangeRequest,
    SessionListResponse,
    SessionMetadataResponse,
    UserCreate,
    UserResponse,
    normalize_login,
)
from monitor_data.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_api_token,
    new_csrf_token,
    new_session_token,
    verify_password,
)

from monitor_ui.auth import (
    Principal,
    client_ip,
    get_signup_limiter,
    get_current_user,
    get_login_limiter,
    get_postgres,
    public_user,
    session_expiry,
)
from monitor_ui.config import UISettings, get_settings
from monitor_ui.oauth import (
    build_google_auth_url,
    exchange_code,
    fetch_google_profile,
    find_or_create_oauth_user,
    new_oauth_state,
)

# Constant-work dummy target so unknown logins take the same Argon2 time as
# wrong passwords (prevents user enumeration via response timing).
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))

router = APIRouter()


def _set_auth_cookies(
    response: Response,
    settings: UISettings,
    raw_session_token: str,
    expires_at: datetime,
) -> None:
    """Set the HttpOnly session cookie and the readable double-submit CSRF cookie."""
    response.set_cookie(
        key=settings.auth_session_cookie,
        value=raw_session_token,
        expires=expires_at,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=settings.auth_csrf_cookie,
        value=new_csrf_token(),
        expires=expires_at,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response, settings: UISettings) -> None:
    response.delete_cookie(key=settings.auth_session_cookie, path="/")
    response.delete_cookie(key=settings.auth_csrf_cookie, path="/")


async def _create_session(db: PostgresClient, user_id: UUID, settings: UISettings) -> tuple[str, datetime]:
    """Create a server session; returns (raw_token, expires_at). Rotates on every login."""
    raw = new_session_token()
    expires_at = session_expiry(settings)
    await db.session_create(token_hash=hash_token(raw), user_id=user_id, expires_at=expires_at)
    return raw, expires_at


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    body: UserCreate,
    request: Request,
    response: Response,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
) -> UserResponse:
    """Self-serve signup. The first signup never becomes admin and never claims legacy data."""
    if settings.monitor_auth_disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup is unavailable while MONITOR_AUTH_DISABLED=true (local development mode).",
        )
    if not await get_signup_limiter(settings).hit(f"signup:{client_ip(request, settings)}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many signup attempts. Try again later.",
        )
    email_normalized = normalize_login(body.email)
    username_normalized = normalize_login(body.username)
    if await db.user_get_by_login(email_normalized) or await db.user_get_by_login(username_normalized):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email or username already exists.",
        )
    try:
        user = await db.user_create(
            {
                "email": body.email,
                "email_normalized": email_normalized,
                "username": body.username,
                "username_normalized": username_normalized,
                "password_hash": hash_password(body.password),
                "display_name": body.display_name,
                "is_admin": False,
            }
        )
    except asyncpg.UniqueViolationError:
        # Signup race: database uniqueness is authoritative.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email or username already exists.",
        ) from None
    raw, expires_at = await _create_session(db, user["id"], settings)
    _set_auth_cookies(response, settings, raw, expires_at)
    return public_user(user)


@router.post("/login", response_model=UserResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
) -> UserResponse:
    """Email-or-username + password login with generic failures and rate limiting."""
    if settings.monitor_auth_disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login is unavailable while MONITOR_AUTH_DISABLED=true (local development mode).",
        )
    limiter = get_login_limiter(settings)
    key = f"login:{body.login}:{client_ip(request, settings)}"
    if not await limiter.hit(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )
    user = await db.user_get_by_login(body.login)
    if user is None:
        # Timing equalization: run the same Argon2 verify against a dummy
        # hash so an unknown login costs the same as a wrong password.
        verify_password(body.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login or password.",
        )
    if not verify_password(body.password, user["password_hash"]):
        # Generic failure: identical response for unknown login and wrong password.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login or password.",
        )
    if user.get("is_banned"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended.",
        )
    if needs_rehash(user["password_hash"]):
        await db.user_update_password_hash(user["id"], hash_password(body.password))
    raw, expires_at = await _create_session(db, user["id"], settings)
    _set_auth_cookies(response, settings, raw, expires_at)
    return public_user(user)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
    principal: Principal = Depends(get_current_user),
) -> dict[str, bool]:
    """Delete the server session and clear cookies. Requires CSRF for cookie auth."""
    session_cookie = request.cookies.get(settings.auth_session_cookie)
    if session_cookie:
        await db.session_delete(hash_token(session_cookie))
    _clear_auth_cookies(response, settings)
    return {"ok": True}


@router.get("/config", response_model=dict[str, bool])
async def auth_config(
    settings: UISettings = Depends(get_settings),
) -> dict[str, bool]:
    """Public auth capabilities (no private data): which providers are enabled."""
    return {
        "auth_disabled": settings.monitor_auth_disabled,
        "google_oauth": settings.google_oauth_configured,
    }


@router.get("/me", response_model=AuthModeResponse)
async def me(
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
    principal: Principal = Depends(get_current_user),
) -> AuthModeResponse:
    """Current authenticated user, plus whether local auth-disabled mode is active."""
    user = await db.user_get_by_id(principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return AuthModeResponse(auth_disabled=settings.monitor_auth_disabled, user=public_user(user))


@router.post("/tokens", response_model=ApiTokenCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_token(
    body: ApiTokenCreate,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
    principal: Principal = Depends(get_current_user),
) -> ApiTokenCreatedResponse:
    """Create a revocable per-user API token for non-browser clients.

    The raw token is returned exactly once here; only its hash is stored.
    """
    raw, prefix, token_hash = new_api_token()
    # Client-supplied expiry is clamped to a server-side maximum.
    expires_at = body.expires_at
    if expires_at is not None:
        max_expiry = datetime.now(UTC) + timedelta(days=settings.api_token_max_ttl_days)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        expires_at = min(expires_at, max_expiry)
    row = await db.api_token_create(
        {
            "user_id": principal.user_id,
            "name": body.name,
            "token_prefix": prefix,
            "token_hash": token_hash,
            "expires_at": expires_at,
        }
    )
    return ApiTokenCreatedResponse(
        id=row["id"],
        name=row["name"],
        token=raw,
        token_prefix=row["token_prefix"],
        created_at=row["created_at"],
        expires_at=row.get("expires_at"),
    )


@router.get("/tokens", response_model=list[ApiTokenMetadataResponse])
async def list_api_tokens(
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
    principal: Principal = Depends(get_current_user),
) -> list[ApiTokenMetadataResponse]:
    rows = await db.api_tokens_list(principal.user_id)
    return [
        ApiTokenMetadataResponse(
            id=row["id"],
            name=row["name"],
            token_prefix=row["token_prefix"],
            created_at=row["created_at"],
            expires_at=row.get("expires_at"),
            last_used_at=row.get("last_used_at"),
            revoked_at=row.get("revoked_at"),
        )
        for row in rows
    ]


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_token(
    token_id: UUID,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
    principal: Principal = Depends(get_current_user),
) -> Response:
    """Revoke one of the caller's own API tokens. Foreign IDs return 404."""
    revoked = await db.api_token_revoke(token_id, principal.user_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Password change + session management
# ---------------------------------------------------------------------------


@router.post("/password")
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
    principal: Principal = Depends(get_current_user),
) -> dict[str, Any]:
    """Change the caller's password. Requires the current password; revokes
    every other session so a stolen cookie dies with the change."""
    user = await db.user_get_by_id(principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid current password.")
    await db.user_update_password_hash(user["id"], hash_password(body.new_password))
    current_hash = hash_token(request.cookies.get(settings.auth_session_cookie, ""))
    revoked = await db.session_delete_all_for_user(user["id"], except_token_hash=current_hash)
    return {"ok": True, "other_sessions_revoked": revoked}


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
    principal: Principal = Depends(get_current_user),
) -> SessionListResponse:
    """List the caller's browser sessions (hash prefix only, never the token)."""
    current_hash = hash_token(request.cookies.get(settings.auth_session_cookie, ""))
    rows = await db.sessions_list_for_user(principal.user_id)
    return SessionListResponse(
        sessions=[
            SessionMetadataResponse(
                token_hash_prefix=row["token_hash"][:12],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                last_seen_at=row.get("last_seen_at"),
                current=row["token_hash"] == current_hash,
            )
            for row in rows
        ]
    )


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_sessions(
    response: Response,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
    principal: Principal = Depends(get_current_user),
) -> Response:
    """Revoke ALL of the caller's sessions (including the current one) and
    clear the cookies — the "log me out everywhere" escape hatch."""
    await db.session_delete_all_for_user(principal.user_id)
    _clear_auth_cookies(response, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Google OAuth sign-in
# ---------------------------------------------------------------------------


def _frontend_redirect(settings: UISettings, path: str) -> RedirectResponse:
    return RedirectResponse(url=f"{settings.auth_frontend_url.rstrip('/')}{path}")


@router.get("/oauth/google")
async def google_login(
    settings: UISettings = Depends(get_settings),
) -> RedirectResponse:
    """Redirect to Google's consent screen with a state cookie for CSRF."""
    if not settings.google_oauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured (GOOGLE_CLIENT_ID/SECRET).",
        )
    state = new_oauth_state()
    redirect = RedirectResponse(url=build_google_auth_url(settings, state))
    # Set on the returned response: FastAPI does not merge the `response`
    # parameter when the handler returns a Response directly.
    redirect.set_cookie(
        key=settings.oauth_state_cookie,
        value=state,
        max_age=settings.oauth_state_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return redirect


@router.get("/oauth/google/callback")
async def google_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    settings: UISettings = Depends(get_settings),
    db: PostgresClient = Depends(get_postgres),
) -> RedirectResponse:
    """Handle Google's redirect: validate state, exchange code, open a session."""
    if error:
        return _frontend_redirect(settings, f"/login?error={error}")
    expected_state = request.cookies.get(settings.oauth_state_cookie)
    if not code or not state or not expected_state or not secrets.compare_digest(state, expected_state):
        return _frontend_redirect(settings, "/login?error=invalid_state")
    try:
        access_token = await exchange_code(settings, code)
        profile = await fetch_google_profile(access_token)
        user = await find_or_create_oauth_user(db, profile)
    except ValueError:
        return _frontend_redirect(settings, "/login?error=oauth_failed")
    if user.get("is_banned"):
        return _frontend_redirect(settings, "/login?error=suspended")
    raw, expires_at = await _create_session(db, user["id"], settings)
    redirect = _frontend_redirect(settings, "/")
    _set_auth_cookies(redirect, settings, raw, expires_at)
    redirect.delete_cookie(key=settings.oauth_state_cookie, path="/")
    return redirect
