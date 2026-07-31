"""Preflight dedupe plan for the live Mongo + Neo4j state.

Reads the same canonical keys as :mod:`scripts.audit_duplicates`, but
also:
  * groups universes by (multiverse_id, name) and picks the canonical
    universe per group;
  * groups multiverses by name and lists the multiverse each test/probe
    artifact belongs to;
  * lists characters and knowledge packs with the same canonical key.

The script writes a JSON plan to stdout. Re-run it any time; it is
read-only.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from typing import Any

from monitor_data.config import settings  # noqa: F401  (ensures env is loaded)


TEST_MV_NAME_RE = re.compile(
    r"^(Walkthrough MV|Test Multiverse|CRUD Test Multiverse|"
    r"Split/Merge Test MV|LoopE2E Multiverse|"
    r"StressProbe\d*|TraceProbe\d*|"
    r"Repro Multiverse|Roleplay Test MV|"
    r"observe-ingest|"
    r"Death in Space — Live Proof|"
    r"Death in Space \(live-test\)|"
    r"Test Multiverse \d|§.*$|TBD|TBD — awaiting|"
    r"Roleplay Test MV \d|LoopE2E Multiverse \d|"
    r"Walkthrough MV [a-f0-9]{6})",
    re.IGNORECASE,
)

TEST_UNIVERSE_NAME_RE = re.compile(
    r"^(LoopE2E Universe|Repro Universe|DiS Test Universe|"
    r"Entity Promotion (Full Run )?Verification|"
    r"Awakening in Seattle.*|Fallout Re-ingest Drill|"
    r"Entity Promotion Verification|Solo|Repro Universe|§.*$|test|"
    r"DiS Test Universe \d|LoopE2E Universe \d|"
    r"Test|Entity Promotion)",  # noqa: E501
    re.IGNORECASE,
)


def _connect_mongo():
    from monitor_data.db.mongodb import get_mongodb_client

    return get_mongodb_client()


def _connect_neo4j():
    from monitor_data.db.neo4j import get_neo4j_client

    return get_neo4j_client()


def _is_test_mv(name: str) -> bool:
    return bool(TEST_MV_NAME_RE.match(name or "")) or "Test" in (name or "")


def _is_test_universe(name: str) -> bool:
    return bool(TEST_UNIVERSE_NAME_RE.match(name or "")) or "Test" in (name or "")


def _test_character(name: str) -> bool:
    return name in {
        "Kvothe",
        "Property Tester",
        "Property",
        "Property Simple",
        "Maeve Thornwick",
        "Sister Veil",
        "Adventurer",
        "Player Character",
        "Test Lantern-Bearer",
    }


def plan_multiverses(neo_client) -> dict[str, Any]:
    rows = (
        neo_client.execute_read(
            "MATCH (n:Multiverse) RETURN n.id AS id, n.name AS name, n.created_at AS created_at"
        )
        or []
    )
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_name[r.get("name", "") or ""].append(r)
    delete: list[dict[str, Any]] = []
    keep: list[dict[str, Any]] = []
    for name, group in by_name.items():
        if _is_test_mv(name):
            for r in group:
                delete.append({"id": r.get("id"), "name": r.get("name")})
        else:
            group_sorted = sorted(group, key=lambda r: r.get("created_at", ""))
            keep.append(
                {
                    "id": group_sorted[0].get("id"),
                    "name": group_sorted[0].get("name"),
                    "duplicates": [r.get("id") for r in group_sorted[1:]],
                }
            )
    return {"delete": delete, "keep": keep, "row_count": len(rows)}


def plan_universes(neo_client) -> dict[str, Any]:
    rows = (
        neo_client.execute_read(
            "MATCH (n:Universe) RETURN n.id AS id, n.name AS name, n.multiverse_id AS multiverse_id, n.created_at AS created_at"
        )
        or []
    )
    by_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = (r.get("name", "") or "", r.get("multiverse_id") or "")
        by_name[key].append(r)
    delete: list[dict[str, Any]] = []
    keep: list[dict[str, Any]] = []
    for (name, mv_id), group in by_name.items():
        if _is_test_universe(name):
            for r in group:
                delete.append({"id": r.get("id"), "name": name, "multiverse_id": mv_id})
        else:
            for r in group[1:]:
                delete.append({"id": r.get("id"), "name": name, "multiverse_id": mv_id})
            keep.append(
                {"id": group[0].get("id"), "name": name, "multiverse_id": mv_id}
            )
    return {"delete": delete, "keep": keep, "row_count": len(rows)}


def plan_characters(mongo_client) -> dict[str, Any]:
    rows = list(mongo_client.get_collection("characters").find({}, {"_id": 0}))
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_name[r.get("name", "")].append(r)
    delete: list[dict[str, Any]] = []
    keep: list[dict[str, Any]] = []
    for name, group in by_name.items():
        if _test_character(name):
            for r in group:
                delete.append({"id": r.get("id"), "name": name})
        else:
            for r in group[1:]:
                delete.append({"id": r.get("id"), "name": name})
            keep.append({"id": group[0].get("id"), "name": name})
    return {"delete": delete, "keep": keep, "row_count": len(rows)}


def plan_knowledge_packs(mongo_client) -> dict[str, Any]:
    rows = list(mongo_client.get_collection("knowledge_packs").find({}))
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_name[r.get("name", "")].append(r)
    delete: list[dict[str, Any]] = []
    keep: list[dict[str, Any]] = []
    for name, group in by_name.items():
        for r in group[1:]:
            delete.append({"id": str(r.get("_id")), "name": name})
        if group:
            keep.append({"id": str(group[0].get("_id")), "name": name})
    return {"delete": delete, "keep": keep, "row_count": len(rows)}


def plan_neo4j_duplicates(
    client,
    label: str,
    *,
    canonical: list[str],
    limit: int | None = None,
) -> dict[str, Any]:
    selected = list(dict.fromkeys([*canonical, "id"]))
    props = ", ".join(f"n.{p} AS {p}" for p in selected)
    rows = client.execute_read(f"MATCH (n:{label}) RETURN {props}") or []
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = tuple(row.get(field) or "" for field in canonical)
        groups[key].append(row)
    delete: list[dict[str, Any]] = []
    for k, v in groups.items():
        if len(v) > 1:
            for row in v[1:limit]:
                delete.append(
                    {
                        "label": label,
                        "key": dict(zip(canonical, k)),
                        "id": str(row.get("id") or row.get("_id")),
                    }
                )
    return {
        "label": label,
        "duplicate_rows_to_delete": len(delete),
        "sample": delete[:limit],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    _ = args

    mdb = _connect_mongo()
    neo = _connect_neo4j()

    plan: dict[str, Any] = {
        "multiverses": plan_multiverses(neo),
        "universes": plan_universes(neo),
        "characters": plan_characters(mdb),
        "knowledge_packs": plan_knowledge_packs(mdb),
        "neo4j": {
            "Story": plan_neo4j_duplicates(neo, "Story", canonical=["title"]),
            "Entity": plan_neo4j_duplicates(
                neo, "Entity", canonical=["name", "entity_type"]
            ),
            "Fact": plan_neo4j_duplicates(neo, "Fact", canonical=["statement"]),
            "Axiom": plan_neo4j_duplicates(neo, "Axiom", canonical=["statement"]),
        },
    }
    print(json.dumps(plan, indent=2, default=str))


if __name__ == "__main__":
    main()
