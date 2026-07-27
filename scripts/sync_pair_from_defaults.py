#!/usr/bin/env python3
"""Re-derive the active model_pair row from llm_providers.is_default.

2026-07-22 centralization: this is the operator-side knob for the
"pair is a derived projection" model. After flipping any
``is_default=true`` in ``llm_providers``, run this and the pair
auto-aligns. Idempotent — running it on an already-aligned pair is a
no-op (writes the same values back).

Examples
--------
    python scripts/sync_pair_from_defaults.py
    python scripts/sync_pair_from_defaults.py --name vtm5-flash-nomic
    python scripts/sync_pair_from_defaults.py --dry-run
    python scripts/sync_pair_from_defaults.py --lock-after-sync   # auto_sync=false
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Repo root on sys.path so `from monitor_data...` works when the script
# is invoked from anywhere.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from monitor_data.db.postgres import PostgresClient
from monitor_data.retrieval.pair_sync import (
    derive_active_pair_from_defaults,
    sync_active_pair_from_defaults,
)
from monitor_data.retrieval.pairs import PairRegistry


async def _run(
    name: str | None,
    dry_run: bool,
    lock_after_sync: bool,
    verbose: bool,
) -> int:
    client = PostgresClient()
    try:
        target_name = name or "auto"
        # If the operator didn't pass --name, prefer the existing
        # active row's name so we update in place rather than creating
        # a second pair.
        if name is None:
            active_rows = await client.model_pair_list_active()
            if active_rows:
                target_name = active_rows[0].get("name") or "auto"

        if dry_run:
            pair = await derive_active_pair_from_defaults(client, name=target_name)
            print(json.dumps({
                "dry_run": True,
                "target_name": pair.name,
                "chat": {"model": pair.chat_model, "provider": pair.chat_provider, "role": pair.chat_role},
                "embedding": {"model": pair.embedding_model, "provider": pair.embedding_provider, "dimension": pair.embedding_dimension},
                "hyde": {"model": pair.hyde_model, "provider": pair.hyde_provider, "role": pair.hyde_role},
                "rerank": {"model": pair.rerank_model, "provider": pair.rerank_provider, "role": pair.rerank_role},
            }, indent=2))
            return 0

        pair = await sync_active_pair_from_defaults(
            client,
            name=target_name,
            auto_sync=not lock_after_sync,
        )
        if pair is None:
            print(f"[sync] ERROR: failed to derive pair", file=sys.stderr)
            return 2

        # Run the validator to confirm the new pair boots.
        reg = PairRegistry(pg=client)
        validated = await reg.validate_active_pair()

        if verbose:
            print(json.dumps({
                "synced": True,
                "target_name": pair.name,
                "auto_sync": not lock_after_sync,
                "validated_name": validated.name,
                "chat": {"model": validated.chat_model, "provider": validated.chat_provider, "role": validated.chat_role},
                "embedding": {"model": validated.embedding_model, "provider": validated.embedding_provider, "dimension": validated.embedding_dimension},
                "hyde": {"model": validated.hyde_model, "provider": validated.hyde_provider, "role": validated.hyde_role},
                "rerank": {"model": validated.rerank_model, "provider": validated.rerank_provider, "role": validated.rerank_role},
            }, indent=2))
        else:
            print(
                f"[sync] OK pair={validated.name} "
                f"chat=({validated.chat_model},{validated.chat_provider},{validated.chat_role}) "
                f"embed=({validated.embedding_model},{validated.embedding_provider},"
                f"dim={validated.embedding_dimension}) "
                f"hyde=({validated.hyde_model},{validated.hyde_provider},{validated.hyde_role}) "
                f"rerank=({validated.rerank_model},{validated.rerank_provider},"
                f"{validated.rerank_role})"
            )
        return 0
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-derive the active model_pair from llm_providers.is_default.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Pair name to upsert (default: existing active row, or 'auto').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the pair but skip the DB write.",
    )
    parser.add_argument(
        "--lock-after-sync",
        action="store_true",
        help="Set auto_sync=false after upsert so future resolves won't overwrite.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the resulting pair as JSON.",
    )
    args = parser.parse_args()
    return asyncio.run(
        _run(
            name=args.name,
            dry_run=args.dry_run,
            lock_after_sync=args.lock_after_sync,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())