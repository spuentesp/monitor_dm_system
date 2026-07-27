#!/usr/bin/env python3
"""[G-8](e) — One-off data fix for the legacy VtM 20th Anniversary system
(`system_id = 2418a85d-…`/legacy `a227676a-edab-…`).

The bad doc predates every ``scripts/vtm_game_system.py`` seed.
``mongodb_update_game_system`` rejects ``is_builtin`` docs, so even
once-corrected tool paths can't rewrite it — this script writes directly
via ``update_one`` (mirroring ``scripts/vtm_game_system.py:114-127``).

The legacy extraction was wrong at two step types:

* ``steps[3].step_type`` ``"choose_class"`` → ``"choose_disciplines"``
* ``steps[4].step_type`` ``"choose_skills"`` → ``"choose_background"``

Preconditions (asserted before any write):
  * Doc exists.
  * ``character_creation.steps`` has ≥ 5 entries.
  * Step titles match the expected mapping (defence against partial
    rewrites when other seeds changed the canonical text).

Plus ``$set: hand_authored: True`` so the G-8(c) provenance gate, when
this doc is eventually rewriteable through the tool path, finds an
authoritative stamp.

Idempotent: a re-run after a successful apply is a no-op (both step
types already corrected).

OPERATIONAL WORKFLOW
--------------------
1. ``uv run python scripts/fix_vtm_seed_creation_steps.py``            # dry-run, prints planned writes
2. ``uv run python scripts/fix_vtm_seed_creation_steps.py --apply``   # performs the writes
3. Re-run step 1; expect a clean dry-run.

TARGET SYSTEM_ID
----------------
The plan references ``a227676a-edab-4a43-80d9-8f76b74ff289`` (per
``docs/architecture/INGESTION_PIPELINE_AUDIT.md`` Finding 4 / the
``audit_ingestion_documents.py:12`` audit context). The system_id is
configurable via ``--system-id`` for re-runs after a stale id migration.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

# Default target per docs/architecture/INGESTION_PIPELINE_AUDIT.md Finding 4.
DEFAULT_VTM_SYSTEM_ID = "a227676a-edab-4a43-80d9-8f76b74ff289"

# Required title mapping — both step titles must match exactly for the
# precondition to be considered satisfied. Mismatch = abort.
EXPECTED_STEP3_TITLE = "Disciplines"  # was mislabeled "Clan" historically
EXPECTED_STEP4_TITLE = "Background"   # was mislabeled "Skills" historically

# Map of step_type rewrites.
STEP_FIXES = {
    3: {"expected_title": EXPECTED_STEP3_TITLE, "wrong": "choose_class", "right": "choose_disciplines"},
    4: {"expected_title": EXPECTED_STEP4_TITLE, "wrong": "choose_skills", "right": "choose_background"},
}


def _get_db() -> Any:
    """Lazy MongoDB client import (matches the rest of ``scripts/``)."""
    from monitor_data.db.mongodb import get_mongodb_client

    return get_mongodb_client()


def _load_doc(system_id: str) -> dict[str, Any] | None:
    """Return the legacy VtM doc, or ``None`` if not found."""
    coll = _get_db().get_collection("game_systems")
    return coll.find_one({"system_id": system_id})


def _validate(doc: dict[str, Any], system_id: str) -> list[str]:
    """Return a list of failure messages. Empty = OK to proceed."""
    failures: list[str] = []
    if doc is None:
        return [f"VtM system_id={system_id!r} not found in game_systems collection"]

    steps_obj = (doc.get("character_creation") or {}).get("steps") or []
    if not isinstance(steps_obj, list) or len(steps_obj) < 5:
        failures.append(
            f"character_creation.steps has fewer than 5 entries ({len(steps_obj)})"
        )
        return failures

    for step_idx, fix in STEP_FIXES.items():
        # step_idx is 1-indexed in the doc; the array is 0-indexed.
        step = steps_obj[step_idx - 1]
        if not isinstance(step, dict):
            failures.append(f"steps[{step_idx}] is not a dict")
            continue
        title = (step.get("title") or "").strip()
        if title != fix["expected_title"]:
            failures.append(
                f"steps[{step_idx}].title={title!r} != expected {fix['expected_title']!r} — "
                "this script doesn't know if a different step already occupies that index"
            )
    return failures


def _plan_writes(doc: dict[str, Any], system_id: str) -> dict[str, Any]:
    """Build the MongoDB ``$set`` payload (no I/O)."""
    steps_obj = (doc.get("character_creation") or {}).get("steps") or []
    set_payload: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc),
        "hand_authored": True,
    }
    for step_idx, fix in STEP_FIXES.items():
        set_payload[f"character_creation.steps.{step_idx - 1}.step_type"] = fix["right"]
    return set_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="[G-8](e) Fix the legacy VtM seed ``character_creation.steps`` step_types."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the writes. Default: dry-run only (prints the planned writes).",
    )
    parser.add_argument(
        "--system-id",
        default=DEFAULT_VTM_SYSTEM_ID,
        help=f"VtM system_id to fix. Default: {DEFAULT_VTM_SYSTEM_ID}",
    )
    args = parser.parse_args(argv)

    print(f"[G-8(e)] Fix VtM seed: system_id={args.system_id}")
    print(f"[G-8(e)] Mode: {'APPLY' if args.apply else 'DRY-RUN'}")

    doc = _load_doc(args.system_id)
    failures = _validate(doc, args.system_id)
    if failures:
        print("[G-8(e)] Precondition failures — aborting:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 2  # distinguishable exit code for the operator

    # At this point ``doc`` is guaranteed not-None.
    assert doc is not None
    set_payload = _plan_writes(doc, args.system_id)
    print("[G-8(e)] Planned write payload:")
    print(json.dumps(set_payload, indent=2, default=str))

    if not args.apply:
        print("[G-8(e)] Dry-run complete — no writes performed. Re-run with --apply.")
        return 0

    coll = _get_db().get_collection("game_systems")
    result = coll.update_one(
        {"system_id": args.system_id},
        {"$set": set_payload},
    )
    print(
        f"[G-8(e)] Applied — matched {result.matched_count}, "
        f"modified {result.modified_count}, system_id={args.system_id}"
    )
    if result.modified_count == 0:
        # Idempotent: re-run after a successful apply surfaces a no-op.
        print("[G-8(e)] No-op (already correct) — nothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
