"""Dry-run audit for duplicate runtime data in MONITOR's MongoDB and Neo4j.

Reads only. Lists every cluster of duplicate rows / nodes that share the
same canonical key (e.g. characters with the same name in the same
universe, axioms with the same statement) along with the row IDs and a
few reference counts.

Usage::

    uv run python scripts/audit_duplicates.py [--limit 25]

The audit is intentionally conservative: "duplicate" means there are at
least two rows with the same canonical key in the *same parent scope*.
For global entities (e.g. knowledge packs), canonical key is the
(pack_type, name) tuple.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

from monitor_data.config import settings  # noqa: F401


def _connect_mongo():
    from monitor_data.db.mongodb import get_mongodb_client

    return get_mongodb_client()


def _connect_neo4j():
    from monitor_data.db.neo4j import get_neo4j_client

    return get_neo4j_client()


def _group_duplicates(
    collection_name: str,
    rows: list[dict[str, Any]],
    *,
    canonical: list[str],
    parent: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if parent is not None and not row.get(parent):
            continue
        key = tuple(row.get(field) or "" for field in canonical)
        groups[key].append(row)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    return {
        "collection": collection_name,
        "scope": parent or "<global>",
        "canonical": canonical,
        "rows_scanned": len(rows),
        "duplicate_groups": [
            {
                "key": dict(zip(canonical, k)),
                "count": len(v),
                "ids": [str(r.get("id") or r.get("_id")) for r in v[:limit]],
                "updated_at": sorted({str(r.get("updated_at") or "") for r in v}),
            }
            for k, v in list(dupes.items())[:limit]
        ],
        "duplicate_row_total": sum(len(v) for v in dupes.values()),
    }


def _neo4j_duplicates(
    client,
    label: str,
    *,
    scope_property: str | None,
    canonical: list[str],
    limit: int,
) -> dict[str, Any]:
    props = ", ".join(f"n.{p} AS {p}" for p in canonical)
    scope_select = ""
    if scope_property:
        scope_select = f", n.{scope_property} AS _scope"
    query = f"MATCH (n:{label}) RETURN {props}{scope_select}"
    rows = client.execute_read(query, {}) or []
    canonical = list(canonical) + (
        [scope_property] if scope_property and scope_property not in canonical else []
    )
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = tuple(row.get(field) or "" for field in canonical)
        groups[key].append(row)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    return {
        "label": label,
        "scope_property": scope_property,
        "canonical": canonical,
        "nodes_scanned": len(rows),
        "duplicate_groups": [
            {
                "key": dict(zip(canonical, k)),
                "count": len(v),
                "ids": [str(row.get("id") or row.get("_id")) for row in v[:limit]],
            }
            for k, v in list(dupes.items())[:limit]
        ],
        "duplicate_node_total": sum(len(v) for v in dupes.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Max duplicate groups to print per section.",
    )
    args = parser.parse_args()
    limit: int = args.limit

    mdb = _connect_mongo()
    neo = _connect_neo4j()

    sections: list[dict[str, Any]] = []

    for coll, canon, parent in [
        ("characters", ["name", "universe_id"], "universe_id"),
        ("characters", ["name"], None),
        ("multiverses", ["name"], None),
        ("universes", ["name", "multiverse_id"], "multiverse_id"),
        ("universes", ["name"], None),
        ("sessions", ["title"], None),
        ("stories", ["title", "universe_id"], "universe_id"),
        ("knowledge_packs", ["name"], None),
        ("knowledge_graphs", ["name"], None),
        ("llm_providers", ["name"], None),
    ]:
        try:
            rows = list(mdb.get_collection(coll).find({}))
        except Exception as exc:
            sections.append({"collection": coll, "error": str(exc)})
            continue
        sections.append(
            _group_duplicates(coll, rows, canonical=canon, parent=parent, limit=limit)
        )

    for label, scope, canon in [
        ("Story", "universe_id", ["title"]),
        ("Entity", "universe_id", ["name", "entity_type"]),
        ("Fact", "universe_id", ["statement"]),
        ("Axiom", "universe_id", ["statement"]),
    ]:
        try:
            sections.append(
                _neo4j_duplicates(
                    neo, label, scope_property=scope, canonical=canon, limit=limit
                )
            )
        except Exception as exc:
            sections.append({"label": label, "error": str(exc)})

    import json

    print(json.dumps(sections, indent=2, default=str))


if __name__ == "__main__":
    main()
