#!/usr/bin/env python3
"""Seed a curated Session Zero prompt collection for live end-to-end testing.

Creates a ``session_zero`` ``prompt_collection`` bound to a game system so the
preplay flow (SessionZeroLoop via preplay_orchestrator, and the CLI
``build_cli_session_zero_loop``) asks the authored questions verbatim instead
of the LLM-generated interview.

This is the committed counterpart to the "done means it runs for real"
verification: after applying, start a new-character session for the target
system and confirm the interview matches the questions below.

OPERATIONAL WORKFLOW
--------------------
1. ``uv run python scripts/seed_session_zero_prompt_collection.py``           # dry-run, prints planned collection
2. ``uv run python scripts/seed_session_zero_prompt_collection.py --apply``   # writes the collection
3. Re-run step 1; expect "already seeded" (idempotent).

TARGET SYSTEM_ID
----------------
Defaults to the VtM 20th Anniversary system used by the e2e scenarios
(``scripts/e2e_full_loop_scenarios.py:V5_SYSTEM_ID``). Override with
``--system-id`` for another system, or ``--universe-id`` to bind by universe
instead of system.
"""

from __future__ import annotations

import argparse
import sys
from uuid import UUID

from monitor_data.schemas.prompt_collections import (
    PromptCollectionCreate,
    PromptCollectionFilter,
    PromptEntry,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_prompt_collection,
    mongodb_list_prompt_collections,
)

# Matches scripts/e2e_full_loop_scenarios.py:V5_SYSTEM_ID (VtM 20th Anniversary).
DEFAULT_SYSTEM_ID = "a227676a-edab-4a43-80d9-8f76b74ff289"

COLLECTION_NAME = "VtM — Session Zero (seed)"

# Gothic-tone authored interview. Ordered; the last question is_final. These
# are curated inputs to the LLM interview loop, not keyword logic.
QUESTIONS: list[PromptEntry] = [
    PromptEntry(
        order=0,
        category="name",
        question_text="By what name did the living know you — and does the night still use it?",
    ),
    PromptEntry(
        order=1,
        category="origin",
        question_text="Whose blood made you? Tell me of the night you were Embraced.",
    ),
    PromptEntry(
        order=2,
        category="bond",
        question_text="One mortal still matters to you. Who are they, and what do they not know?",
    ),
    PromptEntry(
        order=3,
        category="fear",
        question_text="The Beast whispers. What is the hunger you are most afraid of obeying?",
    ),
    PromptEntry(
        order=4,
        category="motivation",
        question_text="It is your first night answering to the Prince. What do you intend to become?",
        is_final=True,
    ),
]


def _existing(system_id: UUID | None, universe_id: UUID | None):
    listing = mongodb_list_prompt_collections(
        PromptCollectionFilter(category="session_zero", system_id=system_id, universe_id=universe_id)
    )
    for c in listing.collections:
        if c.name == COLLECTION_NAME:
            return c
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform the write (default: dry-run).")
    parser.add_argument("--system-id", default=DEFAULT_SYSTEM_ID, help="Bind to this game system_id.")
    parser.add_argument("--universe-id", default=None, help="Optionally bind to a universe_id instead/also.")
    args = parser.parse_args()

    system_id = UUID(args.system_id) if args.system_id else None
    universe_id = UUID(args.universe_id) if args.universe_id else None

    print(f"Target: system_id={system_id} universe_id={universe_id}")
    print(f"Collection: {COLLECTION_NAME!r} (category=session_zero, {len(QUESTIONS)} questions)")
    for q in QUESTIONS:
        final = " [final]" if q.is_final else ""
        print(f"  {q.order}. ({q.category}){final} {q.question_text}")

    existing = _existing(system_id, universe_id)
    if existing:
        print(f"\nAlready seeded (collection_id={existing.collection_id}). No-op.")
        return 0

    if not args.apply:
        print("\nDry-run. Re-run with --apply to write.")
        return 0

    created = mongodb_create_prompt_collection(
        PromptCollectionCreate(
            name=COLLECTION_NAME,
            description="Curated gothic Session Zero interview for VtM (live-test seed).",
            category="session_zero",
            system_id=system_id,
            universe_id=universe_id,
            tags=["vtm", "gothic", "seed"],
            entries=QUESTIONS,
            version="v1",
        )
    )
    print(f"\nSeeded collection_id={created.collection_id} with {len(created.entries)} questions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
