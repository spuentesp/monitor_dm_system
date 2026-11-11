#!/usr/bin/env python3
"""Print the model calls a book will take, with no model call (phase 5a, task 10).

Usage:
    uv run python scripts/estimate_book_calls.py path/to/book.pdf

Reads the PDF and the environment only: no database, no provider, no network.
Prints the calls per stage for the current settings, then the same estimate
under the OLD defaults (before phase 5a) so the two can be compared. Graph and
coverage rows follow MONITOR_BOOK_GRAPH / MONITOR_BOOK_COVERAGE, exactly as a
real run would.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from monitor_agents.book_decomposition.estimate import CallEstimate, estimate_calls
from monitor_agents.book_decomposition.settings import DecompositionSettings, OLD
from monitor_agents.book_decomposition.windows import build_windows
from monitor_data.tools.ingest_tools.book_tree import decompose_pdf


def _flag(name: str) -> bool:
    return os.environ.get(name, "0") == "1"


def _print_estimate(label: str, estimate: CallEstimate, settings: DecompositionSettings) -> None:
    print(f"{label}: total={estimate.total} calls")
    for stage, count in estimate.as_dict().items():
        print(f"  {stage:<14} {count}")
    print(
        "  settings: "
        f"window_words={settings.window_words} window_break={settings.window_break} "
        f"extract_max_tokens={settings.extract_max_tokens} review_batch={settings.review_batch} "
        f"graph_batch={settings.graph_batch} coverage_batch={settings.coverage_batch} "
        f"coverage_sample={settings.coverage_sample} skip_non_content={settings.skip_non_content}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("pdf", type=Path, help="The book's PDF; only its text layout is read")
    parser.add_argument("--title", default=None, help="Title to label the estimate with")
    args = parser.parse_args(argv)
    if not args.pdf.exists():
        print(f"No such file: {args.pdf}", file=sys.stderr)
        return 1

    tree = decompose_pdf(
        args.pdf.read_bytes(),
        doc_id=f"estimate:{args.pdf.name}",
        title=args.title or args.pdf.stem,
    )
    current_settings = DecompositionSettings.from_env()
    windows = build_windows(tree, settings=current_settings)
    current = estimate_calls(tree, windows=windows, settings=current_settings)
    old = estimate_calls(tree, settings=OLD)

    print(f"Book: {tree.title} — {len(tree.nodes)} nodes")
    print(
        "Stage flags: "
        f"MONITOR_BOOK_GRAPH={'on' if _flag('MONITOR_BOOK_GRAPH') else 'off'} "
        f"MONITOR_BOOK_COVERAGE={'on' if _flag('MONITOR_BOOK_COVERAGE') else 'off'}"
    )
    print()
    _print_estimate("Current settings", current, current_settings)
    print()
    _print_estimate("OLD defaults (before phase 5a)", old, OLD)
    print(f"\nDifference (old - new): {old.total - current.total} calls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
