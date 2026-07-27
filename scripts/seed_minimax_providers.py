#!/usr/bin/env python3
"""
Seed MiniMax as the active chat/embedding provider for live game tests.

Why MiniMax:
  - Already configured (env: ``MINIMAX_API_KEY``, base ``api.minimax.io``).
  - Connected rows exist for ``standard`` / ``heavy`` / ``light`` roles.
  - No Google quota to blow up — keeps Gemini out of the loop entirely.

Embeddings:
  - MiniMax's free tier is rate-limited per minute; embedding ~40 anchor
    phrases would take 40+ minutes. The ``RollNecessityClassifier`` ships
    with a **health probe** that detects non-semantic (hash) embeddings and
    falls back to the LLM GMAwareness verdict's roll_necessity instead.
  - So we let embeddings resolve to the local hash fallback (no row), and
    the classifier gracefully defers. This is the *designed* behaviour.

This script is idempotent — re-running just upserts the same rows. Safe to
run after the infra stack is up.

Usage:
    uv run python scripts/seed_minimax_providers.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Repo root on sys.path so ``monitor_*`` imports resolve when run from any cwd.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from monitor_data.db.postgres import PostgresClient

# MiniMax model names — we deliberately use the M3 family here.
#
# The M2.x series (M2.7 / M2.5 / M2.1 / M2) has *always-on* thinking mode
# that consumes the entire ``max_tokens`` budget on its own, leaving no
# room for the requested answer — which makes the JSON-extraction use
# case in the ingestion test useless and the chat path produce truncated
# or empty replies. M3 supports ``thinking: {"type": "disabled"}`` and
# behaves like a normal chat model otherwise.
#
# Override via env if you want to test against a different model.
MINIMAX_TEXT = os.environ.get("MINIMAX_TEXT_MODEL", "MiniMax-M3")
MINIMAX_LIGHT = os.environ.get("MINIMAX_LIGHT_MODEL", "MiniMax-M3")


async def main() -> int:
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        print("ERROR: MINIMAX_API_KEY not set in env")
        return 1

    pg = PostgresClient()
    await pg.connect()
    try:
        rows = [
            {
                # Re-upsert the canonical standard row so the api_key + status
                # are guaranteed current even if the row was originally seeded
                # without them.
                "id": "minimax-std",
                "name": "MiniMax M3 (Standard)",
                "provider": "minimax",
                "model": MINIMAX_TEXT,
                "api_key": api_key,
                "role": "standard",
                "status": "connected",
                "is_default": True,
                "model_params": {"max_tokens": 4096, "temperature": 0.7},
            },
            {
                "id": "minimax-m27",
                "name": "MiniMax M3 (Heavy)",
                "provider": "minimax",
                "model": MINIMAX_TEXT,
                "api_key": api_key,
                "role": "heavy",
                "status": "connected",
                "is_default": False,
                "model_params": {"max_tokens": 4096, "temperature": 0.7},
            },
            {
                "id": "minimax-light",
                "name": "MiniMax M3 (Light)",
                "provider": "minimax",
                "model": MINIMAX_LIGHT,
                "api_key": api_key,
                "role": "light",
                "status": "connected",
                "is_default": False,
                "model_params": {"max_tokens": 2048, "temperature": 0.3},
            },
        ]
        for row in rows:
            await pg.provider_upsert(row)
            print(f"  ✓ upserted {row['id']} ({row['role']}, {row['model']})")

        # Pin the `player` node to the MiniMax standard row so scripted +
        # unscripted tests don't drift to a role-default that may be Google
        # or an unconfigured provider.
        await pg.node_assignment_set(
            "player", "minimax-std", notes="MiniMax M3 for live game tests"
        )
        print("  ✓ assigned node=player → minimax-std")

        # Reassign the indexer too — it currently points to Google's heavy
        # row, which burns Google quota on extraction jobs. MiniMax can do
        # indexing just as well for this test workload.
        try:
            await pg.node_assignment_set(
                "indexer", "minimax-m27", notes="MiniMax for live game tests"
            )
            print("  ✓ assigned node=indexer → minimax-m27")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  ! could not reassign indexer ({exc})")
    finally:
        await pg.close()

    # Force the data-layer embedding client to re-resolve on next call. We
    # intentionally leave the embedding role empty so the local hash
    # fallback is used; the RollNecessityClassifier's health probe will
    # detect it and defer to the LLM verdict.
    try:
        from monitor_data.retrieval import reset_retrieval_service

        reset_retrieval_service()
        print("  reset retrieval-service singleton")
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  ! could not clear embedding cache ({exc})")

    print("\nMiniMax providers seeded. Live tests can now run on MiniMax M3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
