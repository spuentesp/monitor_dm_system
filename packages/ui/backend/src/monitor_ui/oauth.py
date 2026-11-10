"""Google OAuth2 (OIDC) sign-in: authorization URL, code exchange, profile fetch.

Flow: ``GET /api/auth/oauth/google`` redirects to Google with a random
``state`` (stored in a short-lived HttpOnly cookie). The callback validates
the state, exchanges the code for tokens, reads the verified profile from
the userinfo endpoint, then finds-or-creates the local user and opens a
normal session. Password login stays available; OAuth accounts get a random
unusable password hash.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from monitor_data.db.postgres import PostgresClient
from monitor_data.schemas.users import normalize_login
from monitor_data.security import hash_password

from monitor_ui.config import UISettings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
OAUTH_PROVIDER = "google"
_HTTP_TIMEOUT = httpx.Timeout(15.0)


@dataclass(frozen=True)
class GoogleProfile:
    """Verified identity claims from Google's userinfo endpoint."""

    provider_account_id: str
    email: str
    email_verified: bool
    name: str


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def build_google_auth_url(settings: UISettings, state: str) -> str:
    """Google consent URL requesting openid email profile."""
    assert settings.google_client_id is not None  # guarded by route
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{httpx.QueryParams(params)}"


async def exchange_code(settings: UISettings, code: str) -> str:
    """Exchange an authorization code for an access token. Raises on failure."""
    assert settings.google_client_id is not None and settings.google_client_secret is not None
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise ValueError(f"Google token exchange failed: {resp.status_code}")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise ValueError("Google token exchange returned no access_token")
    return str(token)


async def fetch_google_profile(access_token: str) -> GoogleProfile:
    """Fetch the verified profile; raises if the email is not verified."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise ValueError(f"Google userinfo failed: {resp.status_code}")
    data = resp.json()
    email = str(data.get("email", "")).strip()
    if not email or not data.get("email_verified"):
        raise ValueError("Google account email is missing or not verified")
    return GoogleProfile(
        provider_account_id=str(data["sub"]),
        email=email,
        email_verified=True,
        name=str(data.get("name", ""))[:200],
    )


async def _unique_username(db: PostgresClient, base: str) -> str:
    """Derive a unique username from an email local part."""
    candidate = base[:50]
    suffix = 0
    while await db.user_get_by_login(normalize_login(candidate)) is not None:
        suffix += 1
        candidate = f"{base[:44]}-{suffix}"
    return candidate


async def find_or_create_oauth_user(
    db: PostgresClient,
    profile: GoogleProfile,
) -> dict[str, Any]:
    """Resolve a Google profile to a local user, linking or creating as needed.

    Existing OAuth link → that user. Else existing account with the same
    verified email → link it (and mark the email verified). Else create a new
    account (never admin; random unusable password).
    """
    email_normalized = normalize_login(profile.email)
    linked = await db.oauth_account_get(OAUTH_PROVIDER, profile.provider_account_id)
    if linked is not None:
        await db.oauth_account_upsert(
            {
                "user_id": linked["user_id"],
                "provider": OAUTH_PROVIDER,
                "provider_account_id": profile.provider_account_id,
                "email": profile.email,
            }
        )
        user = await db.user_get_by_id(UUID(str(linked["user_id"])))
        if user is None:
            raise ValueError("OAuth account points at a deleted user")
        await db.user_set_email_verified(user["id"], True)
        user["email_verified"] = True
        return user

    existing = await db.user_get_by_login(email_normalized)
    if existing is not None:
        await db.oauth_account_upsert(
            {
                "user_id": existing["id"],
                "provider": OAUTH_PROVIDER,
                "provider_account_id": profile.provider_account_id,
                "email": profile.email,
            }
        )
        await db.user_set_email_verified(existing["id"], True)
        existing["email_verified"] = True
        return existing

    username = await _unique_username(db, email_normalized.partition("@")[0] or "user")
    user = await db.user_create(
        {
            "email": profile.email,
            "email_normalized": email_normalized,
            "username": username,
            "username_normalized": normalize_login(username),
            "password_hash": hash_password(secrets.token_urlsafe(32)),
            "display_name": profile.name,
            "is_admin": False,
        }
    )
    await db.user_set_email_verified(user["id"], True)
    user["email_verified"] = True
    await db.oauth_account_upsert(
        {
            "user_id": user["id"],
            "provider": OAUTH_PROVIDER,
            "provider_account_id": profile.provider_account_id,
            "email": profile.email,
        }
    )
    return user
