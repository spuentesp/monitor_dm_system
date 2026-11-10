#!/usr/bin/env python3
"""
Move existing standalone characters into per-user Conversatory universes.

Before multi-tenancy, every standalone character's backing entity lived in
one shared hidden universe named "Conversatory". Each user now gets their
own Conversatory (found through the Postgres ownership registry,
``worlds.kind = 'conversatory'``). This script re-homes every character
incarnation that still lives in the shared legacy universe onto its owner's
universe.

Idempotent — characters with no incarnation in the legacy universe are
skipped, so the script can be re-run safely. Dry-run by default; pass
--apply to write. Prints only ids and counts.

Usage (from repo root, with Postgres/Mongo/Neo4j up):

    uv run python scripts/migrate_conversatory_per_user.py [--apply]

This script is written to be run by the operator/coordinator, not by the
implementing agent. The legacy universe is identified ONCE by name (that is
what it is: a one-off data-migration lookup); all new lookups go through the
ownership registry.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, "packages/data-layer/src")
sys.path.insert(0, "packages/agents/src")
sys.path.insert(0, "packages/ui/backend/src")


async def _migrate(apply: bool) -> None:
    from monitor_data.schemas.universe import UniverseFilter
    from monitor_data.tools.neo4j_tools.core import neo4j_list_universes

    from monitor_ui.auth import LOCAL_USER_ID
    from monitor_ui.routers.character_conversation import (
        _CONVERSATORY_UNIVERSE_NAME,
        delete_incarnation,
        ensure_character_backed,
        ensure_conversatory_universe,
    )
    from monitor_ui.routers.character_storage import list_characters

    # The one name-based lookup in this script: identifying the LEGACY shared
    # universe. Everything after this goes through the ownership registry.
    legacy_id: str | None = None
    for u in await asyncio.to_thread(neo4j_list_universes, UniverseFilter(limit=1000)):
        if getattr(u, "name", None) == _CONVERSATORY_UNIVERSE_NAME:
            legacy_id = str(u.id)
            break
    if legacy_id is None:
        print("No legacy shared Conversatory universe found — nothing to migrate.")
        return
    print(f"Legacy shared Conversatory universe: {legacy_id}")

    docs, total = await asyncio.to_thread(list_characters, 500, 0)
    print(f"{total} standalone character(s) to check.")

    moved = 0
    skipped = 0
    for doc in docs:
        character_id = str(doc.get("id"))
        owner = doc.get("owner_id") or str(LOCAL_USER_ID)
        target = await ensure_conversatory_universe(owner)
        versions = list(doc.get("versions") or [])
        stale = [
            v for v in versions if str(v.get("universe_id")) == legacy_id and target != legacy_id
        ]
        legacy_top_level = (
            str(doc.get("source_universe_id") or "") == legacy_id
            and target != legacy_id
            and not versions
        )
        if not stale and not legacy_top_level:
            skipped += 1
            continue
        print(
            f"character {character_id} (owner {owner}): {len(stale) or 1} incarnation(s) -> {target}"
        )
        if not apply:
            continue
        # New incarnation on the owner's Conversatory, then drop the legacy one.
        await ensure_character_backed(character_id, universe_id=target)
        for v in stale:
            await delete_incarnation(character_id, str(v["universe_id"]))
        # Legacy top-level (pre-versions) incarnations have no version entry to
        # delete; their entity stays in the shared universe, unreferenced — the
        # operator can drop that universe wholesale afterwards.
        moved += 1

    verb = "moved" if apply else "would move"
    print(f"Done — {verb} {moved} character(s); {skipped} already per-user.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args()
    asyncio.run(_migrate(args.apply))
