#!/usr/bin/env python3
"""
Encrypt existing llm_providers.api_key values at rest (multi-tenancy Phase 6).

Idempotent — rows whose value already decrypts with the configured key are
skipped, so the script can be re-run safely. Dry-run by default; pass
--apply to write. NEVER prints key material — only row ids and counts.

Requires MONITOR_PROVIDER_KEY_ENCRYPTION_KEY (a url-safe base64 32-byte
Fernet key). Generate one with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Usage (from repo root, with Postgres up):

    uv run python scripts/migrate_encrypt_provider_keys.py [--apply]

This script is written to be run by the operator/coordinator, not by the
implementing agent.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, "packages/data-layer/src")


async def _migrate(apply: bool) -> None:
    from monitor_data.db.postgres import (
        PROVIDER_KEY_ENV,
        PostgresClient,
        decrypt_provider_api_key,
        encrypt_provider_api_key,
        provider_key_encryption_enabled,
    )

    if not provider_key_encryption_enabled():
        print(f"ERROR: {PROVIDER_KEY_ENV} is not set — refusing to migrate.")
        print("Set it first; without it there is no key to encrypt with.")
        sys.exit(1)

    pg = PostgresClient()
    await pg.connect()  # auto-applies schema

    pool = await pg._get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, api_key FROM llm_providers")

    already = 0
    to_encrypt: list[tuple[str, str]] = []
    for row in rows:
        raw = row["api_key"] or ""
        if not raw:
            already += 1
            continue
        # An idempotency probe: a value that already decrypts with the
        # configured key was migrated (or written) in encrypted form.
        if decrypt_provider_api_key(raw) != raw:
            already += 1
            continue
        to_encrypt.append((row["id"], raw))

    print(f"{len(rows)} provider rows: {already} already encrypted/empty, {len(to_encrypt)} to encrypt.")
    if not apply:
        print("Dry run — pass --apply to write. No rows changed.")
        await pg.close()
        return

    async with pool.acquire() as conn:
        for provider_id, raw in to_encrypt:
            # encrypt_provider_api_key is idempotent and never logs the value.
            await conn.execute(
                "UPDATE llm_providers SET api_key = $1, updated_at = now() WHERE id = $2",
                encrypt_provider_api_key(raw),
                provider_id,
            )
            print(f"encrypted provider {provider_id}")

    await pg.close()
    print(f"Done — {len(to_encrypt)} row(s) encrypted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the encrypted values (default: dry run)",
    )
    args = parser.parse_args()
    asyncio.run(_migrate(args.apply))
