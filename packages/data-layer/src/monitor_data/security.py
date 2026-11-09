"""Password hashing and opaque-token helpers for account authentication.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (argon2-cffi, stdlib)
CALLED BY: UI backend auth service, migration/backfill scripts

Passwords are hashed with Argon2id via argon2-cffi using the library-
recommended parameters. Sessions and API tokens are opaque random strings;
only their SHA-256 hashes are persisted, so a database leak does not leak
usable credentials.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Library-recommended Argon2id parameters (time_cost=3, memory_cost=64 MiB,
# parallelism=4). check_needs_rehash() drives rehash-on-login when these
# defaults change between releases.
_hasher = PasswordHasher()

SESSION_TOKEN_BYTES = 32
API_TOKEN_PREFIX = "mntk"
API_TOKEN_PREFIX_DISPLAY_LEN = 12


def hash_password(password: str) -> str:
    """Return an Argon2id hash of ``password``."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return True iff ``password`` matches ``password_hash``.

    Never raises on malformed hashes — a corrupt stored hash is simply
    treated as a non-match so callers can fail closed.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Return True if the hash should be re-generated with current parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def new_session_token() -> str:
    """Return a new opaque browser-session token (raw, stored only client-side)."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def new_csrf_token() -> str:
    """Return a new double-submit CSRF token (stored in a readable cookie)."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest stored server-side for a raw token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_api_token() -> tuple[str, str, str]:
    """Return ``(raw_token, display_prefix, token_hash)`` for a new API token.

    The raw token is shown to the user exactly once; only ``token_hash`` is
    persisted. ``display_prefix`` is a non-secret identifier for listings.
    """
    raw = f"{API_TOKEN_PREFIX}_{secrets.token_urlsafe(SESSION_TOKEN_BYTES)}"
    prefix = raw[:API_TOKEN_PREFIX_DISPLAY_LEN]
    return raw, prefix, hash_token(raw)
