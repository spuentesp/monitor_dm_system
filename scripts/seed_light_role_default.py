#!/usr/bin/env python3
"""Mark ``ollama-local`` the default ``llm_providers`` row for role='light'.

WHY THIS EXISTS
---------------
Three rows share ``role='light'`` (minimax-light, ollama-local, google-
gemini-light) and — before this script — none had ``is_default=True``.
``provider_get_by_role('light')`` (the lookup ``Embedder``/``PairLLM``/
the pair-contract boot gate all use) breaks the tie with
``ORDER BY is_default DESC, created_at`` — with no default set, that
silently resolved to whichever row happened to be oldest/newest
depending on the code path, NOT the pair's intended
``ollama/qwen2.5:latest``. Caught live during the 2026-07-20
embedding-gatekeeper rollout as an ``IncompatiblePairError`` naming a
completely different model (``gemini-2.5-flash-lite``) than the one
the active pair actually pins for hyde/rerank.

This was fixed by hand in that session's live database but never
committed as reproducible code — a DB reset or fresh environment would
silently reintroduce the ambiguity. This script is that fix, checked
in. It only ever sets ``is_default``/``status`` on the ``ollama-local``
row by id (``provider_upsert``'s ``ON CONFLICT (id)`` scopes the write
to that one row) — it does not touch the other two role='light' rows.

USAGE
-----
    uv run python scripts/seed_light_role_default.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "packages/data-layer/src")

_PROVIDER_ID = "ollama-local"


async def _seed() -> None:
    from monitor_data.db.postgres import PostgresClient

    pg = PostgresClient()
    try:
        row = await pg.provider_get(_PROVIDER_ID)
        if row is None:
            print(f"  ! no llm_providers row with id={_PROVIDER_ID!r} — nothing to fix.")
            raise SystemExit(1)

        row["status"] = "connected"
        row["is_default"] = True
        await pg.provider_upsert(row)
        print(f"  updated {_PROVIDER_ID!r}: status=connected, is_default=True")

        resolved = await pg.provider_get_by_role("light")
        assert resolved is not None
        print(
            f"  provider_get_by_role('light') now resolves to: "
            f"{resolved['id']} ({resolved['model']}, {resolved['provider']})"
        )
        if resolved["id"] != _PROVIDER_ID:
            print(
                "  ! resolved to a different row than expected — check for a "
                "newer is_default row on role='light'."
            )
            raise SystemExit(1)
    finally:
        await pg.close()


def main() -> int:
    asyncio.run(_seed())
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
