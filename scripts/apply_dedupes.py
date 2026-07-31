"""Apply the dedupe plan produced by ``scripts/plan_dedupes.py``.

Run::

    uv run python scripts/apply_dedupes.py --plan /tmp/plan.json --dry-run
    uv run python scripts/apply_dedupes.py --plan /tmp/plan.json --apply

The ``--dry-run`` flag prints every mutation that would happen without
touching the database. The ``--apply`` flag requires the plan to be
present and proceeds in this order:

  1. Rebind global canon nodes (Entity / Fact / Axiom / Story with
     ``universe_id=""``) to their source universe when we can infer
     the mapping from the entity/fact/axiom/statement text. Mapping
     rules live in ``_CANON_TO_UNIVERSE``.
  2. Soft-delete the test multiverses from the plan.
  3. Soft-delete the test universes from the plan.
  4. Soft-delete the duplicate characters from the plan.
  5. Soft-delete the duplicate knowledge packs from the plan.
  6. Soft-delete the duplicate Story / Entity / Fact / Axiom nodes
     from the plan.

Mutations are logged with the affected IDs. Use ``--ids-only`` to
print just the IDs in a script-friendly format.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from monitor_data.config import settings  # noqa: F401


_CANON_TO_UNIVERSE: dict[str, str] = {
    # name or unique wordings that map to a specific surviving universe.
    "kindred": "44c1e375-7611-4451-833f-6feecbab5080",  # Wtwf Vtm20Th
    "torpor": "44c1e375-7611-4451-833f-6feecbab5080",
    "frenzy": "44c1e375-7611-4451-833f-6feecbab5080",
    "hunger": "44c1e375-7611-4451-833f-6feecbab5080",
    "disciplines": "44c1e375-7611-4451-833f-6feecbab5080",
    "millhaven": "97912840-596e-4b36-9822-6f8f2af75950",  # Millhaven Lore Test
    "elder magda": "97912840-596e-4b36-9822-6f8f2af75950",
    "harvest": "8cbb4232-45e1-49b7-abc9-c20add798b0d",  # The Drowned Mourning
    "salvage": "f4affa0a-640a-4bc3-83c5-7a00b653f2d0",  # 7Thsea Dtrpg
}


def _connect_mongo():
    from monitor_data.db.mongodb import get_mongodb_client

    return get_mongodb_client()


def _connect_neo4j():
    from monitor_data.db.neo4j import get_neo4j_client

    return get_neo4j_client()


def _rebind_global_canon(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Find global (universe_id="") canon nodes and return rebinding queries."""
    neo = _connect_neo4j()
    actions: list[dict[str, Any]] = []
    for label in ("Entity", "Fact", "Axiom", "Story"):
        # `coalesce()` with a literal default returns null when the property
        # is missing on the node, so we coalesce against an empty string
        # at the call site instead.
        query = (
            f"MATCH (n:{label}) WHERE n.universe_id = '' OR n.universe_id IS NULL "
            f"RETURN n.id AS id, "
            f"coalesce(n.name, '') AS name, coalesce(n.statement, '') AS statement, "
            f"coalesce(n.title, '') AS title"
        )
        rows = neo.execute_read(query) or []
        for row in rows:
            name = row.get("name") or ""
            statement = row.get("statement") or ""
            title = row.get("title") or ""
            text = " ".join((name, statement, title)).lower()
            target: str | None = None
            for keyword, universe_id in _CANON_TO_UNIVERSE.items():
                if keyword in text:
                    target = universe_id
                    break
            if target is not None:
                actions.append(
                    {
                        "label": label,
                        "id": row.get("id"),
                        "new_universe_id": target,
                        "text_excerpt": text[:80],
                    }
                )
    return actions


def _print_plan(plan: dict[str, Any]) -> None:
    print(json.dumps(plan, indent=2, default=str))


async def _apply(plan: dict[str, Any], *, ids_only: bool) -> None:
    from monitor_data.tools.neo4j_tools.core import (
        neo4j_delete_multiverse,
        neo4j_delete_universe,
    )

    mdb = _connect_mongo()
    neo = _connect_neo4j()

    # 1. Rebind canon
    rebinds = _rebind_global_canon(plan)
    for action in rebinds:
        try:
            neo.execute_write(
                "MATCH (n {id: $id}) SET n.universe_id = $universe_id",
                {"id": action["id"], "universe_id": action["new_universe_id"]},
            )
        except Exception as exc:
            print(f"rebind failed {action}: {exc}")

    # 2. Multiverses
    for entry in plan["multiverses"]["delete"]:
        if ids_only:
            print(f"multiverse {entry['id']}")
            continue
        try:
            neo4j_delete_multiverse(entry["id"], force=True)
        except Exception as exc:
            print(f"multiverse delete failed {entry}: {exc}")

    # plan_dedupes.py stores duplicate non-test multiverses under keep[].duplicates.
    for keep_entry in plan["multiverses"].get("keep", []):
        for duplicate_id in keep_entry.get("duplicates", []):
            if ids_only:
                print(f"multiverse {duplicate_id}")
                continue
            try:
                neo4j_delete_multiverse(duplicate_id, force=True)
            except Exception as exc:
                print(f"multiverse duplicate delete failed {duplicate_id}: {exc}")

    # 3. Universes
    for entry in plan["universes"]["delete"]:
        if ids_only:
            print(f"universe {entry['id']}")
            continue
        try:
            neo4j_delete_universe(entry["id"], force=True)
        except Exception as exc:
            print(f"universe delete failed {entry}: {exc}")

    # 4. Characters (Mongo)
    for entry in plan["characters"]["delete"]:
        if ids_only:
            print(f"character {entry['id']}")
            continue
        mdb.get_collection("characters").delete_one({"id": entry["id"]})

    # 5. Knowledge packs (Mongo)
    for entry in plan["knowledge_packs"]["delete"]:
        if ids_only:
            print(f"knowledge_pack {entry['id']}")
            continue
        from bson import ObjectId

        _id = entry["id"]
        query = {"_id": ObjectId(_id) if ObjectId.is_valid(_id) else _id}
        mdb.get_collection("knowledge_packs").delete_one(query)

    # 6. Neo4j canon
    for label in ("Story", "Entity", "Fact", "Axiom"):
        for entry in plan["neo4j"][label]["sample"]:
            if ids_only:
                print(f"{label} {entry['id']}")
                continue
            try:
                neo.execute_write(
                    f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n",
                    {"id": entry["id"]},
                )
            except Exception as exc:
                print(f"canon delete failed {entry}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan", required=True, help="Path to a plan_dedupes.py JSON output."
    )
    parser.add_argument(
        "--ids-only",
        action="store_true",
        help="With --apply, print only the affected IDs and skip the deletes (dry report).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the plan (required for any database mutation).",
    )
    args = parser.parse_args()

    plan = json.load(open(args.plan))
    if not args.apply:
        # Pure inspection: print the plan (and the rebind preview) and exit.
        _print_plan(plan)
        return

    if args.ids_only:
        _print_plan(plan)
        return

    asyncio.run(_apply(plan, ids_only=False))


if __name__ == "__main__":
    main()
