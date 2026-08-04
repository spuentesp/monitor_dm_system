"""
Restore llm_providers + llm_node_assignments from a JSON backup.

Idempotent — uses provider_upsert (ON CONFLICT) so it can be re-run safely.

Usage:
    uv run python scripts/_restore_llm_providers.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "packages/data-layer/src")

BACKUP_DIR = Path("test_logs/backup")
PROVIDERS_BACKUP = BACKUP_DIR / "llm_providers_pre_wipe.json"
ASSIGNMENTS_BACKUP = BACKUP_DIR / "llm_node_assignments_pre_wipe.json"


async def _restore() -> None:
    if not PROVIDERS_BACKUP.exists() or not ASSIGNMENTS_BACKUP.exists():
        print(f"ERROR: backup files not found in {BACKUP_DIR}")
        sys.exit(1)

    providers = json.loads(PROVIDERS_BACKUP.read_text())
    assignments = json.loads(ASSIGNMENTS_BACKUP.read_text())

    from monitor_data.db.postgres import PostgresClient

    pg = PostgresClient()
    try:
        await pg.connect()  # auto-applies schema
        print(f"Restoring {len(providers)} providers...")
        for p in providers:
            # Strip keys the upsert doesn't write — schema/audit columns are
            # managed by the DB.
            row = {
                k: v
                for k, v in p.items()
                if k
                in {
                    "id",
                    "name",
                    "provider",
                    "model",
                    "api_key",
                    "base_url",
                    "model_params",
                    "role",
                    "status",
                    "latency_ms",
                    "is_default",
                }
            }
            await pg.provider_upsert(row)
            key_len = len(row.get("api_key") or "")
            print(
                f"  ✓ {row['id']:40s} role={row['role']:10s} "
                f"key_len={key_len} default={row['is_default']}"
            )

        print()
        print(f"Restoring {len(assignments)} node assignments...")
        for a in assignments:
            await pg.node_assignment_set(
                node_name=a["node_name"],
                provider_id=a["provider_id"],
                param_overrides=a.get("param_overrides") or {},
                notes=a.get("notes"),
            )
            print(f"  ✓ {a['node_name']:10s} -> {a['provider_id']}")

        print()
        # Sanity check
        listed = await pg.providers_list()
        print(f"Verification: llm_providers now has {len(listed)} rows")
    finally:
        await pg.close()


def main() -> None:
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    asyncio.run(_restore())


if __name__ == "__main__":
    main()
