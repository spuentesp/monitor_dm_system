#!/usr/bin/env python3
"""Create (or promote) the first MONITOR admin account.

Signup is invite-only by default and a fresh signup is never made admin
(plan UX-2), so a new deployment has no operator until this script runs.

- validates exactly like ``POST /api/auth/signup`` (``monitor_data.schemas.users.UserCreate``)
- hashes with ``monitor_data.security.hash_password`` (Argon2id)
- writes through ``PostgresClient.user_create`` / ``user_set_admin``
- idempotent: re-running against an already-admin account is a no-op
- never prints the password (it is read via ``--password`` or ``getpass``)

Usage (from the repo root, Postgres up):

    uv run python scripts/create_admin.py --email op@example.com --username operator
    uv run python scripts/create_admin.py --email op@example.com --username operator \\
        --password 'choose-a-long-password'          # non-interactive
    uv run python scripts/create_admin.py --email op@example.com --username operator \\
        --promote-existing                           # make an existing account admin

Exit codes: 0 success (created / promoted / already admin), 1 refused,
2 invalid arguments or failed validation.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Make ``monitor_data`` importable when run from a checkout without an
# installed workspace (same pattern as migrate_encrypt_provider_keys.py).
_DATA_LAYER_SRC = Path(__file__).resolve().parent.parent / "packages" / "data-layer" / "src"
if str(_DATA_LAYER_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_LAYER_SRC))


class CreateAdminError(Exception):
    """A user-facing refusal. The message is always safe to print."""


async def create_admin(
    db: Any,
    *,
    email: str,
    username: str,
    password: str | None,
    display_name: str = "",
    promote_existing: bool = False,
    password_prompt: Callable[[], str] | None = None,
) -> str:
    """Create an admin account, or promote an existing one.

    Returns ``"created"``, ``"promoted"`` or ``"already_admin"``.
    Raises :class:`CreateAdminError` for refusals and pydantic's
    ``ValidationError`` when the signup payload is invalid.
    """
    from monitor_data.schemas.users import UserCreate, normalize_login
    from monitor_data.security import hash_password

    email_normalized = normalize_login(email)
    username_normalized = normalize_login(username)

    by_email = await db.user_get_by_login(email_normalized)
    by_username = await db.user_get_by_login(username_normalized)
    existing = by_email or by_username

    if existing is not None:
        # Same conflict rule as signup: the login must match on BOTH columns
        # to be "the same account" — otherwise email or username is taken.
        if (
            existing["email_normalized"] != email_normalized
            or existing["username_normalized"] != username_normalized
        ):
            raise CreateAdminError(
                "an account with this email or username already exists with different details"
            )
        if existing.get("is_admin"):
            return "already_admin"
        if not promote_existing:
            raise CreateAdminError(
                "account exists but is not an admin — re-run with --promote-existing"
            )
        await db.user_set_admin(existing["id"], True)
        return "promoted"

    # New account: a password is required (prompted interactively when the
    # caller supplies a prompt; never echoed back by this script).
    if password is None and password_prompt is not None:
        password = password_prompt()
    if not password:
        raise CreateAdminError("no password given (pass --password or run interactively)")

    # Identical validation to /api/auth/signup (email shape, username
    # pattern, password length). ValidationError propagates to the caller.
    validated = UserCreate(
        email=email,
        username=username,
        password=password,
        display_name=display_name,
    )
    payload = {
        "email": validated.email,
        "email_normalized": normalize_login(validated.email),
        "username": validated.username,
        "username_normalized": normalize_login(validated.username),
        "password_hash": hash_password(validated.password),
        "display_name": validated.display_name,
        "is_admin": True,
    }
    await db.user_create(payload)
    return "created"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--username", required=True, help="Admin username")
    parser.add_argument(
        "--password",
        default=None,
        help="Password (>=12 chars). Omitted = prompt via getpass (never echoed).",
    )
    parser.add_argument(
        "--display-name",
        default="",
        help="Optional display name for the new account",
    )
    parser.add_argument(
        "--promote-existing",
        action="store_true",
        help="If the account already exists without admin, grant admin instead of refusing",
    )
    return parser


async def _run(args: argparse.Namespace, db: Any, password_prompt: Callable[[], str] | None) -> int:
    await db.connect()
    try:
        try:
            status = await create_admin(
                db,
                email=args.email,
                username=args.username,
                password=args.password,
                display_name=args.display_name,
                promote_existing=args.promote_existing,
                password_prompt=password_prompt,
            )
        except CreateAdminError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001  # reason: boundary — any failure becomes a clean CLI error
            # Never str()-format pydantic errors: they embed input values
            # (including the password). Print the type and field messages only.
            errors = getattr(exc, "errors", None)
            if callable(errors):
                try:
                    details = "; ".join(
                        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in errors()
                    )
                except Exception:  # noqa: BLE001  # reason: fall back to the error type alone
                    details = type(exc).__name__
                print(f"ERROR: validation failed — {details}", file=sys.stderr)
                return 2
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    finally:
        close = getattr(db, "close", None)
        if close is not None:
            await close()

    if status == "created":
        print(f"PASS: admin created (email={args.email}, username={args.username})")
    elif status == "promoted":
        print(
            f"PASS: existing account promoted to admin (email={args.email}, username={args.username})"
        )
    else:
        print(f"PASS: account is already an admin (email={args.email}, username={args.username})")
    return 0


def main(
    argv: list[str] | None = None,
    *,
    db_factory: Callable[[], Any] | None = None,
    password_prompt: Callable[[], str] | None = None,
) -> int:
    """CLI entry point. ``db_factory``/``password_prompt`` are test seams."""
    args = build_parser().parse_args(argv)
    if db_factory is None:
        from monitor_data.db.postgres import PostgresClient

        db_factory = PostgresClient
    if password_prompt is None:
        password_prompt = lambda: getpass.getpass("Password for the new admin: ")  # noqa: E731
    return asyncio.run(_run(args, db_factory(), password_prompt))


if __name__ == "__main__":
    sys.exit(main())
