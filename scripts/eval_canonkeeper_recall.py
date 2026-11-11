#!/usr/bin/env python3
"""CanonKeeper recall measurement — per-class detection on the G08 corpus.

The implication check flagged 25% of eight hand-written contradictions on
2026-11-07. Eight cases is too small to act on and one percentage hides
*which* kind of contradiction is missed. This script replays the labeled
corpus (`monitor_agents.canonkeeper.recall_corpus`) and reports recall per
class, so "the check is weak" can be separated from "the check misses
timeline violations specifically".

Three shapes are measured, because the shape of the check is the thing
under suspicion:

``batch``
    What ships today: one call per chunk of 15 candidates, the whole canon
    in context. The 2026-11-07 baseline.

``per-candidate``
    One call per candidate. The batch form asks the model to hold 15
    candidates and a whole canon in its head at once; this asks it to hold
    one.

``focused``
    One call per candidate, and the context is narrowed to the canon that
    bears on *that* candidate (its entities, one hop out, plus the axioms).

Usage::

    uv run python scripts/eval_canonkeeper_recall.py --mode per-candidate
    uv run python scripts/eval_canonkeeper_recall.py --mode focused --json-out /tmp/recall.json
    uv run python scripts/eval_canonkeeper_recall.py --mode batch --sample 3

Needs a configured LLM provider (the registry lives in PostgreSQL). Exits
non-zero when a class falls below its recall floor or the false-positive
rate goes above the ceiling, so it can gate a release.

Read-only: it never writes to Neo4j or MongoDB.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from monitor_agents.canonkeeper.recall_corpus import (
    CLASS_TARGETS,
    FALSE_POSITIVE_CEILING,
    RECALL_CASES,
    RecallCase,
    evaluate,
    focused_context,
    render_context,
)

CHUNK_SIZE = 15


async def _run_batch(
    context: str, statements: list[str]
) -> tuple[set[str], set[str]]:
    """The shipped shape: batched direct + implication checks."""
    from monitor_agents.canonkeeper.verification import (
        BatchContradictionModule,
        ImplicationContradictionModule,
    )

    direct: set[str] = set()
    implication: set[str] = set()

    direct_module = BatchContradictionModule()
    implication_module = ImplicationContradictionModule()

    for start in range(0, len(statements), CHUNK_SIZE):
        chunk = statements[start : start + CHUNK_SIZE]
        numbered = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(chunk))

        flagged = await asyncio.to_thread(
            direct_module.forward, context=context, new_facts=numbered
        )
        for one_based_idx in flagged:
            ci = one_based_idx - 1
            if 0 <= ci < len(chunk):
                direct.add(chunk[ci])

        flagged_implication = await asyncio.to_thread(
            implication_module.forward, context=context, new_facts=numbered
        )
        for one_based_idx in flagged_implication:
            ci = one_based_idx - 1
            if 0 <= ci < len(chunk):
                implication.add(chunk[ci])

    return direct, implication


async def _run_per_candidate(
    context: str, statements: list[str]
) -> tuple[set[str], set[str]]:
    """One call per candidate: the direct check's own single-fact shape."""
    from monitor_agents.canonkeeper.verification import (
        ContradictionModule,
        ImplicationContradictionModule,
    )

    direct: set[str] = set()
    implication: set[str] = set()

    direct_module = ContradictionModule()
    implication_module = ImplicationContradictionModule()

    for statement in statements:
        result = await asyncio.to_thread(
            direct_module.forward, context=context, new_fact=statement
        )
        if result.get("has_contradiction"):
            direct.add(statement)

        flagged = await asyncio.to_thread(
            implication_module.forward, context=context, new_facts=f"1. {statement}"
        )
        if 1 in flagged:
            implication.add(statement)

    return direct, implication


async def _run_focused(
    context: str, statements: list[str]
) -> tuple[set[str], set[str]]:
    """One call per candidate, with the context narrowed to that candidate."""
    from monitor_agents.canonkeeper.verification import (
        ContradictionModule,
        ImplicationContradictionModule,
    )

    direct: set[str] = set()
    implication: set[str] = set()

    direct_module = ContradictionModule()
    implication_module = ImplicationContradictionModule()

    for statement in statements:
        scoped = focused_context(statement)
        result = await asyncio.to_thread(
            direct_module.forward, context=scoped, new_fact=statement
        )
        if result.get("has_contradiction"):
            direct.add(statement)

        flagged = await asyncio.to_thread(
            implication_module.forward, context=scoped, new_facts=f"1. {statement}"
        )
        if 1 in flagged:
            implication.add(statement)

    return direct, implication


_RUNNERS = {
    "batch": _run_batch,
    "per-candidate": _run_per_candidate,
    "focused": _run_focused,
}


def _print_table(report: Any) -> None:
    header = f"{'class':<22} {'n':>3} {'recall':>8} {'direct':>8} {'implic':>8} {'target':>7}  ok"
    print(header)
    print("-" * len(header))
    for name in sorted(report.classes):
        entry = report.classes[name]
        target = f"{entry.target:.0%}" if entry.target is not None else "-"
        ok = "" if entry.target is None else ("yes" if entry.meets_target else "NO")
        recall = f"{entry.recall:.0%}"
        direct = f"{entry.direct_recall:.0%}"
        implication = f"{entry.implication_recall:.0%}"
        print(
            f"{name:<22} {entry.total:>3} {recall:>8} {direct:>8} "
            f"{implication:>8} {target:>7}  {ok}"
        )
    print()
    print(f"false-positive rate: {report.false_positive_rate:.1%} (ceiling {FALSE_POSITIVE_CEILING:.0%})")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        default="focused",
        choices=sorted(_RUNNERS),
        help="Shape of the check to measure (default: focused)",
    )
    parser.add_argument(
        "--class",
        action="append",
        default=[],
        dest="classes",
        help="Only measure these case classes (repeatable)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=3,
        help="How many missed/false-positive samples to print",
    )
    parser.add_argument("--json-out", default="", help="Optional path for a JSON report")
    args = parser.parse_args()

    cases: tuple[RecallCase, ...] = RECALL_CASES
    if args.classes:
        wanted = set(args.classes)
        cases = tuple(c for c in RECALL_CASES if c.case_class in wanted)

    if not cases:
        print("No cases selected.", file=sys.stderr)
        return 2

    statements = [c.statement for c in cases]
    context = render_context()

    print(f"CanonKeeper recall measurement — mode: {args.mode}")
    print(f"Canon facts      : {len(context.splitlines())} context lines")
    print(f"Cases            : {len(cases)}")
    print("")

    try:
        direct, implication = await _RUNNERS[args.mode](context, statements)
    except Exception as exc:  # noqa: BLE001  # reason: an unavailable provider is reported, not fatal
        print(f"could not run the checks: {exc}")
        print("  (configure a provider — the LLM registry lives in PostgreSQL)")
        return 2

    report = evaluate(cases, direct, implication)
    _print_table(report)

    misses = [
        c.statement
        for c in cases
        if c.expects_violation and c.statement not in direct and c.statement not in implication
    ]
    false_positives = [
        c.statement
        for c in cases
        if not c.expects_violation and (c.statement in direct or c.statement in implication)
    ]
    if misses:
        print(f"\nmissed ({len(misses)}):")
        for statement in misses[: args.sample]:
            print(f"  - {statement}")
    if false_positives:
        print(f"\nfalse positives ({len(false_positives)}):")
        for statement in false_positives[: args.sample]:
            print(f"  - {statement}")

    if args.json_out:
        payload = report.to_dict()
        payload["mode"] = args.mode
        payload["missed"] = misses
        payload["false_positives"] = false_positives
        Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nJSON report written to {args.json_out}")

    below = [
        name
        for name, entry in report.classes.items()
        if entry.target is not None and not entry.meets_target
    ]
    if below:
        print(f"\nBELOW TARGET: {', '.join(sorted(below))}")
        return 1
    if report.false_positive_rate > FALSE_POSITIVE_CEILING:
        print(f"\nABOVE FALSE-POSITIVE CEILING ({report.false_positive_rate:.1%})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
