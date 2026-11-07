#!/usr/bin/env python3
"""CanonKeeper depth evaluation — false-positive measurement for the
implication-level contradiction check (G-9 Phase 1).

The implication check flags candidates that conflict with canon through a
*chain of reasoning* rather than an outright negation ("the canon implies X,
the candidate denies X"). That extra reasoning step is exactly where false
positives come from, so before the check is allowed to influence anything, we
measure how often it fires on material that is known-good.

Method: replay **committed** proposals. A committed proposal is by definition
accepted canon, so any implication flag raised against it is a false positive
by construction. The script reports the flag rate and prints samples for manual
spot-checking — per ``docs/architecture/GAP_REMEDIATION_PLAN.md`` §G-9,
implication-level detection stays flag-only until that rate is demonstrably
low.

Usage::

    uv run python scripts/eval_canonkeeper_depth.py --universe-id <uuid>
    uv run python scripts/eval_canonkeeper_depth.py --universe-id <uuid> \
        --status committed --limit 200 --sample 10
    uv run python scripts/eval_canonkeeper_depth.py --universe-id <uuid> \
        --json-out /tmp/canonkeeper-depth.json

Read-only: it never writes to Neo4j or MongoDB. It costs one HEAVY LLM call
per chunk of candidates, so point it at a populated universe.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_data.db.mongodb import get_mongodb_client


def _scene_universe_map() -> dict[str, str]:
    """Map scene_id -> universe_id so proposals can be scoped to a universe."""
    mdb = get_mongodb_client()
    mapping: dict[str, str] = {}
    for doc in mdb.get_collection("scenes").find({}, {"scene_id": 1, "universe_id": 1}):
        scene_id = doc.get("scene_id")
        universe_id = doc.get("universe_id")
        if scene_id and universe_id:
            mapping[str(scene_id)] = str(universe_id)
    return mapping


def _proposal_universe(doc: dict[str, Any], scene_map: dict[str, str]) -> str | None:
    content = doc.get("content") or {}
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = {}
    if not isinstance(content, dict):
        content = {}
    universe_id = content.get("universe_id") or doc.get("universe_id")
    if universe_id:
        return str(universe_id)
    scene_id = doc.get("scene_id")
    if scene_id and str(scene_id) in scene_map:
        return scene_map[str(scene_id)]
    return None


def _statement_of(doc: dict[str, Any]) -> str:
    content = doc.get("content") or {}
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = {}
    if not isinstance(content, dict):
        content = {}
    for key in ("statement", "summary", "description"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _collect_candidates(
    universe_id: UUID,
    status: str,
    limit: int,
    scene_map: dict[str, str],
) -> tuple[list[str], dict[str, int]]:
    """Collect known-good candidate statements for the given universe."""
    mdb = get_mongodb_client()
    coll = mdb.get_collection("proposed_changes")
    statements: list[str] = []
    stats = {"scanned": 0, "other_universe": 0, "no_statement": 0}
    for doc in coll.find({"status": status}):
        stats["scanned"] += 1
        owner = _proposal_universe(doc, scene_map)
        if owner is not None and owner != str(universe_id):
            stats["other_universe"] += 1
            continue
        statement = _statement_of(doc)
        if not statement:
            stats["no_statement"] += 1
            continue
        statements.append(statement)
        if len(statements) >= limit:
            break
    return statements, stats


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-id", required=True, help="Universe whose canon is the context")
    parser.add_argument(
        "--status",
        default="committed",
        help="Proposal status to replay (default: committed — known-good material)",
    )
    parser.add_argument("--limit", type=int, default=100, help="Max candidate statements")
    parser.add_argument("--sample", type=int, default=5, help="How many flagged samples to print")
    parser.add_argument("--json-out", default="", help="Optional path for a JSON report")
    args = parser.parse_args()

    try:
        universe_id = UUID(args.universe_id)
    except ValueError:
        print(f"--universe-id is not a UUID: {args.universe_id}", file=sys.stderr)
        return 2

    scene_map = _scene_universe_map()
    statements, stats = _collect_candidates(universe_id, args.status, args.limit, scene_map)

    print(f"Universe        : {universe_id}")
    print(f"Replayed status : {args.status}")
    print(
        f"Proposals       : {stats['scanned']} scanned, "
        f"{stats['other_universe']} skipped (other universe), "
        f"{stats['no_statement']} skipped (no statement text)"
    )
    print(f"Candidates      : {len(statements)}")

    if len(statements) < 10:
        print(
            "\nWARNING: fewer than 10 candidates — the false-positive rate below is "
            "not statistically meaningful.",
            file=sys.stderr,
        )

    if not statements:
        print("\nNo known-good candidates to replay. Nothing measured.")
        return 2

    keeper = CanonKeeper()
    flags = await keeper.implication_conflict_flags(universe_id, statements)

    rate = len(flags) / len(statements)
    print(f"\nImplication flags: {len(flags)} / {len(statements)}  (FP rate {rate:.1%})")
    print("Every flag above is a FALSE POSITIVE by construction (committed material).")

    for flag in flags[: args.sample]:
        print("\n--- sample flag ---")
        print(f"statement   : {flag['statement']}")
        print(f"explanation : {flag['explanation']}")
        print(f"implications: {flag['implications']}")
        print(f"type/severity: {flag['contradiction_type']} / {flag['severity']}")

    if args.json_out:
        report = {
            "universe_id": str(universe_id),
            "status": args.status,
            "candidates": len(statements),
            "flags": len(flags),
            "false_positive_rate": rate,
            "scanned": stats,
            "samples": flags[: args.sample],
        }
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nJSON report written to {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
