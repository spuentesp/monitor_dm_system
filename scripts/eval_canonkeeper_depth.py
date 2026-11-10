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


def _collect_state_change_proposals(
    universe_id: UUID,
    status: str,
    limit: int,
    scene_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Collect committed state-change proposals for the transition-rule replay."""
    mdb = get_mongodb_client()
    coll = mdb.get_collection("proposed_changes")
    collected: list[dict[str, Any]] = []
    for doc in coll.find({"status": status, "change_type": "state_change"}):
        content = doc.get("content") or {}
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                content = {}
        if not isinstance(content, dict):
            continue
        owner = _proposal_universe(doc, scene_map)
        if owner is not None and owner != str(universe_id):
            continue
        entity_id = content.get("entity_id")
        add_tags = content.get("add_tags") or content.get("condition_tags") or []
        remove_tags = content.get("remove_tags") or []
        if not entity_id or not (add_tags or remove_tags):
            continue
        collected.append(
            {
                "proposal_id": str(doc.get("proposal_id") or ""),
                "entity_id": str(entity_id),
                "add_tags": [str(t) for t in add_tags],
                "remove_tags": [str(t) for t in remove_tags],
                "override_reason": content.get("override_reason"),
            }
        )
        if len(collected) >= limit:
            break
    return collected


async def _replay_transition_rules(
    keeper: Any,
    universe_id: UUID,
    proposals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run the deterministic transition rules over committed state changes."""
    from monitor_agents.canonkeeper.transition_rules import check_state_transition

    violations: list[dict[str, Any]] = []
    for proposal in proposals:
        try:
            raw = await keeper.call_tool(
                "neo4j_get_state_tags", {"entity_id": proposal["entity_id"]}
            )
        except Exception as exc:  # noqa: BLE001  # reason: an unreadable entity is skipped, not fatal
            print(
                f"warning: could not read state tags for {proposal['entity_id']}: {exc}",
                file=sys.stderr,
            )
            continue
        current_tags: list[str] = []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = []
        if isinstance(raw, dict):
            raw = raw.get("state_tags") or []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    current_tags.append(item)
                elif isinstance(item, dict) and (item.get("tag") or item.get("value")):
                    current_tags.append(str(item.get("tag") or item.get("value")))

        violation = check_state_transition(
            current_tags=current_tags,
            add_tags=proposal["add_tags"],
            remove_tags=proposal["remove_tags"],
            override_reason=proposal.get("override_reason"),
        )
        if violation is not None:
            violations.append(
                {
                    "proposal_id": proposal["proposal_id"],
                    "entity_id": proposal["entity_id"],
                    "current_tags": current_tags,
                    "add_tags": proposal["add_tags"],
                    "remove_tags": proposal["remove_tags"],
                    "rule": violation.rule,
                    "reason": violation.reason,
                }
            )
    return violations


# ---------------------------------------------------------------------------
# Synthetic corpus (hermetic measurement — no universe, no seeded content)
# ---------------------------------------------------------------------------
#
# The corpus lives in the package (`canonkeeper/synthetic_corpus.py`) so the
# measurement can be pinned by a test; the seeded universes are mechanical and
# the product boundary (2026-11-07) keeps it that way.

from monitor_agents.canonkeeper.synthetic_corpus import (  # noqa: E402
    SYNTHETIC_BAD_TRANSITIONS,
    SYNTHETIC_CANON,
    SYNTHETIC_CONSISTENT,
    SYNTHETIC_CONTRADICTING,
    SYNTHETIC_GOOD_TRANSITIONS,
    replay_transitions,
    synthetic_context,
)


async def _replay_implication(
    context: str,
    statements: list[str],
) -> dict[int, dict[str, str]]:
    """Run the implication module over statements against an explicit context."""
    from monitor_agents.canonkeeper.verification import ImplicationContradictionModule

    module = ImplicationContradictionModule()
    flagged: dict[int, dict[str, str]] = {}
    chunk_size = 15
    for start in range(0, len(statements), chunk_size):
        chunk = statements[start : start + chunk_size]
        numbered = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(chunk))
        result = await asyncio.to_thread(module.forward, context=context, new_facts=numbered)
        for one_based_idx, detail in result.items():
            ci = one_based_idx - 1
            if 0 <= ci < len(chunk):
                flagged[ci] = detail
    return flagged


async def _run_synthetic(sample: int) -> int:
    """Measure both checks against the hermetic narrative corpus."""
    context = synthetic_context()
    consistent = list(SYNTHETIC_CONSISTENT)
    contradicting = list(SYNTHETIC_CONTRADICTING)

    print("Synthetic narrative corpus (hermetic — no universe, no seeded content)")
    print(f"Canon facts      : {len(SYNTHETIC_CANON)}")
    print(f"Consistent probes: {len(consistent)}")
    print(f"Contradicting    : {len(contradicting)}")

    # ── the deterministic rules: no LLM needed ──────────────────────────────
    good_violations = replay_transitions(SYNTHETIC_GOOD_TRANSITIONS)
    bad_violations = replay_transitions(SYNTHETIC_BAD_TRANSITIONS)
    print("\n── deterministic transition rules ──")
    print(f"  false positives: {len(good_violations)} / {len(SYNTHETIC_GOOD_TRANSITIONS)}")
    print(f"  detected       : {len(bad_violations)} / {len(SYNTHETIC_BAD_TRANSITIONS)}")

    # ── the implication check: needs a configured LLM provider ─────────────
    print("\n── implication check (needs a configured LLM provider) ──")
    try:
        consistent_flags = await _replay_implication(context, consistent)
        contradicting_flags = await _replay_implication(context, contradicting)
    except Exception as exc:  # noqa: BLE001  # reason: an unavailable provider is reported, not fatal (in _run_synthetic)
        print(f"  could not run the implication check: {exc}")
        print("  (configure a provider — the LLM registry lives in PostgreSQL)")
        return 0

    fp_rate = len(consistent_flags) / len(consistent) if consistent else 0.0
    detection = len(contradicting_flags) / len(contradicting) if contradicting else 0.0
    print(
        f"  false positives: {len(consistent_flags)} / {len(consistent)}  (FP rate {fp_rate:.1%})"
    )
    print(
        f"  detected       : {len(contradicting_flags)} / {len(contradicting)}  ({detection:.1%})"
    )
    for idx, detail in list(consistent_flags.items())[:sample]:
        print(f"  FP: {consistent[idx]}")
        print(f"      {detail.get('explanation', '')}")
    for idx, detail in list(contradicting_flags.items())[:sample]:
        print(f"  TP: {contradicting[idx]}")
        print(f"      {detail.get('explanation', '')}")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--universe-id",
        default="",
        help="Universe whose canon is the context (not needed with --synthetic)",
    )
    parser.add_argument(
        "--status",
        default="committed",
        help="Proposal status to replay (default: committed — known-good material)",
    )
    parser.add_argument("--limit", type=int, default=100, help="Max candidate statements")
    parser.add_argument("--sample", type=int, default=5, help="How many flagged samples to print")
    parser.add_argument("--json-out", default="", help="Optional path for a JSON report")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help=(
            "Measure against the hermetic narrative corpus instead of a universe. "
            "Needs no seeded content — only a configured LLM provider for the "
            "implication check; the deterministic rules run offline."
        ),
    )
    args = parser.parse_args()

    if args.synthetic:
        return await _run_synthetic(args.sample)

    if not args.universe_id:
        parser.error("--universe-id is required unless --synthetic is used")

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

    if not statements and not _collect_state_change_proposals(
        universe_id, args.status, args.limit, scene_map
    ):
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

    # ── The deterministic transition rules (G-9 Phase 2/3) ──────────────
    # Same principle: committed state changes are known-good, so any rule
    # violation raised against them is a false positive by construction.
    state_changes = _collect_state_change_proposals(universe_id, args.status, args.limit, scene_map)
    print(f"\nState changes replayed: {len(state_changes)} (deterministic transition rules)")
    transition_violations = (
        await _replay_transition_rules(keeper, universe_id, state_changes) if state_changes else []
    )
    if state_changes:
        t_rate = len(transition_violations) / len(state_changes)
        print(
            f"Transition-rule violations: {len(transition_violations)} / "
            f"{len(state_changes)}  (FP rate {t_rate:.1%})"
        )
        for violation in transition_violations[: args.sample]:
            print("\n--- sample violation ---")
            print(f"entity    : {violation['entity_id']}")
            print(f"current   : {violation['current_tags']}")
            print(f"add/remove: {violation['add_tags']} / {violation['remove_tags']}")
            print(f"rule      : {violation['rule']}")
            print(f"reason    : {violation['reason']}")
    else:
        t_rate = 0.0

    if args.json_out:
        report = {
            "universe_id": str(universe_id),
            "status": args.status,
            "candidates": len(statements),
            "flags": len(flags),
            "false_positive_rate": rate,
            "scanned": stats,
            "samples": flags[: args.sample],
            "state_changes_replayed": len(state_changes),
            "transition_violations": len(transition_violations),
            "transition_false_positive_rate": t_rate,
            "transition_samples": transition_violations[: args.sample],
        }
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nJSON report written to {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
