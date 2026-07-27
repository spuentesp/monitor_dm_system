#!/usr/bin/env python3
"""Point the ``embedding`` provider row at the local Ollama nomic-embed-text.

The data-layer embedding client resolves its provider from the PostgreSQL
``llm_providers`` table (role='embedding') BEFORE falling back to the
``EMBEDDING_MODEL`` env var. If a stale DB row points at a rate-limited
cloud provider (e.g. Gemini free tier, 1000 embeds/day), the whole
semantic-classifier stack stalls once the quota is hit — even though the
``.env`` says ``EMBEDDING_PROVIDER=ollama``.

This script upserts the embedding row to the local Ollama model so
embeddings are free, unlimited, and never rate-limited. nomic-embed-text
is a 137M model producing 768-dim vectors — as good as the cloud model
for the nearest-class classification the GM tools do.

Requires Ollama running locally with nomic-embed-text pulled:
    ollama pull nomic-embed-text

Usage:
    uv run python scripts/seed_ollama_embedding_provider.py
    uv run python scripts/seed_ollama_embedding_provider.py --model ollama/nomic-embed-text
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, "packages/data-layer/src")


async def _seed(model: str, base_url: str, sync_pair: bool = False) -> None:
    import asyncpg

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "monitor")
    password = os.getenv("POSTGRES_PASSWORD", "")
    database = os.getenv("POSTGRES_DB", "monitor")

    conn = await asyncpg.connect(
        host=host, port=port, user=user, password=password, database=database
    )
    try:
        existing = await conn.fetch("SELECT id, model, provider FROM llm_providers WHERE role='embedding'")
        if existing:
            for row in existing:
                await conn.execute(
                    """
                    UPDATE llm_providers
                    SET model=$1, provider='ollama', base_url=$2, api_key='', updated_at=NOW()
                    WHERE id=$3
                    """,
                    model, base_url, row["id"],
                )
                print(f"  updated embedding row {row['id']}: {row['model']} ({row['provider']}) -> {model} (ollama)")
        else:
            await conn.execute(
                """
                INSERT INTO llm_providers (name, provider, model, api_key, base_url, status, is_default, role, created_at, updated_at)
                VALUES ('Ollama nomic-embed-text', 'ollama', $1, '', $2, 'error', false, 'embedding', NOW(), NOW())
                """,
                model, base_url,
            )
            print(f"  inserted embedding row: {model} (ollama)")

        # Probe the model BEFORE marking it 'connected'. The previous
        # behaviour wrote 'connected' on insert and the failure surfaced
        # only at the first ingest's embed call — which on a 178 MB PDF
        # is 30+ minutes into the run. The probe is cheap (~10 s) and
        # surfaces the real cause before we even leave the operator's
        # terminal: 'model not pulled' vs. 'ollama unreachable' vs.
        # 'embedding dim mismatch'.
        sys.path.insert(0, "packages/data-layer/src")
        from monitor_data.retrieval.embedding_health import EmbeddingHealthChecker

        checker = EmbeddingHealthChecker(
            model=model,
            provider="ollama",
            base_url=base_url,
            expected_dim=int(os.getenv("EMBEDDING_DIMENSION", "768")),
        )
        try:
            status = await checker.verify()
        except Exception as exc:  # noqa: BLE001
            status = None
            print(f"  ! health probe raised: {exc}")

        if status is not None and status.healthy:
            await conn.execute(
                "UPDATE llm_providers SET status='connected', updated_at=NOW() "
                "WHERE role='embedding'"
            )
            print(
                f"  health probe ok: {status.detail} "
                f"(dim={status.vector_dim})"
            )
        else:
            detail = status.detail if status else "probe raised"
            await conn.execute(
                "UPDATE llm_providers SET status='error', updated_at=NOW() "
                "WHERE role='embedding'"
            )
            print(
                f"  ! health probe FAILED: {detail}\n"
                f"    The row was inserted/updated but marked 'error'. "
                f"Run:\n      ollama pull {model}\n    Then re-run this script."
            )

        # Drop the retrieval-service singleton so the next call re-resolves
        # the active pair (and re-validates it against the llm_providers
        # rows we just upserted).
        try:
            from monitor_data.retrieval import reset_retrieval_service

            reset_retrieval_service()
            print("  reset retrieval-service singleton")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! could not reset retrieval-service singleton ({exc})")

        # 2026-07-22 centralization: --sync-pair re-derives the active
        # pair from llm_providers.is_default so the embedding flip
        # auto-propagates to model_pairs.embedding_{model,provider,dim}.
        if sync_pair:
            from monitor_data.db.postgres import PostgresClient
            from monitor_data.retrieval.pair_sync import sync_active_pair_from_defaults

            pg = PostgresClient()
            try:
                active_rows = await pg.model_pair_list_active()
                name = active_rows[0].get("name") if active_rows else "auto"
                pair = await sync_active_pair_from_defaults(pg, name=name or "auto")
                if pair is not None:
                    print(
                        f"  [sync-pair] updated pair={pair.name} "
                        f"embed=({pair.embedding_model}, {pair.embedding_provider}, "
                        f"dim={pair.embedding_dimension})"
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"  ! --sync-pair failed: {exc}")
            finally:
                await pg.close()
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # Canonical Ollama model name. The historical default
    # 'ollama/nomic-embed-text' (with library prefix) is wrong — Ollama
    # rejected it with 'model not found' and litellm mis-routed it because
    # the provider prefix is added by the embedder, not stored in
    # llm_providers.model.
    ap.add_argument("--model", default="nomic-embed-text:latest")
    ap.add_argument(
        "--base-url",
        default=os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434"),
    )
    ap.add_argument(
        "--sync-pair",
        action="store_true",
        help=(
            "After upserting the embedding row, re-derive the active "
            "model_pair from llm_providers.is_default so the embedding "
            "side of the pair auto-aligns with the new row."
        ),
    )
    args = ap.parse_args()
    asyncio.run(_seed(args.model, args.base_url, args.sync_pair))
    print("Done. Restart the backend to pick up the change if it's already running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
