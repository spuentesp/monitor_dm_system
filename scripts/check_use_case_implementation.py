#!/usr/bin/env python3
"""
Quickly report which documented MONITOR use cases appear in the codebase.

The script parses IDs/headings from docs/USE_CASES.md (e.g., P-1, M-4, ST-3),
searches the packages/ directory for references to each ID, and prints a table
marking whether anything in code mentions the use case. This is a lightweight
way to spot stories that lack even a stub in code.

Usage:
    python scripts/check_use_case_implementation.py
    python scripts/check_use_case_implementation.py --json > status.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
USE_CASE_DOC = ROOT / "docs" / "USE_CASES.md"
SEARCH_ROOT = ROOT / "packages"

USE_CASE_HEADING = re.compile(r"^##\s+([A-Z]{1,3}-\d+):\s+(.*)$")


@dataclass(frozen=True)
class UseCase:
    """Represents a use case extracted from docs/USE_CASES.md."""

    uid: str
    title: str


def parse_use_cases(doc_path: Path) -> list[UseCase]:
    """Return all use cases defined as H2 headings in the reference doc."""
    cases: list[UseCase] = []
    for line in doc_path.read_text().splitlines():
        match = USE_CASE_HEADING.match(line.strip())
        if match:
            uid, title = match.groups()
            cases.append(UseCase(uid=uid, title=title))
    return cases


def search_in_code(pattern: str, roots: Iterable[Path]) -> list[Path]:
    """
    Use ripgrep to find files mentioning the pattern under given roots.

    Returns a list of file paths. If ripgrep is unavailable, falls back to a
    slow text scan.
    """
    try:
        result = subprocess.run(
            ["rg", "-l", pattern, *[str(r) for r in roots]],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return fallback_scan(pattern, roots)

    files = [Path(line) for line in result.stdout.splitlines() if line.strip()]
    return files if files else []


def fallback_scan(pattern: str, roots: Iterable[Path]) -> list[Path]:
    """Slow text scan used only when ripgrep is not installed."""
    hits: list[Path] = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                if pattern in path.read_text():
                    hits.append(path)
            except (UnicodeDecodeError, OSError):
                continue
    return hits


def build_status() -> list[dict]:
    """Generate implementation status rows for all use cases."""
    use_cases = parse_use_cases(USE_CASE_DOC)
    rows: list[dict] = []

    for case in use_cases:
        files = search_in_code(case.uid, [SEARCH_ROOT])
        rows.append(
            {
                "id": case.uid,
                "title": case.title,
                "implemented": bool(files),
                "references": [str(p.relative_to(ROOT)) for p in files],
            }
        )
    return rows


def print_table(rows: list[dict]) -> None:
    """Pretty-print status to the console."""
    implemented = sum(1 for row in rows if row["implemented"])
    total = len(rows)

    print(f"Use case coverage in code: {implemented}/{total} referenced\n")
    print(f"{'ID':<8} {'Status':<12} Title")
    print("-" * 60)
    for row in rows:
        status = "implemented" if row["implemented"] else "missing"
        print(f"{row['id']:<8} {status:<12} {row['title']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report which MONITOR use cases appear in code."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of a table.",
    )
    args = parser.parse_args()

    rows = build_status()

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print_table(rows)


if __name__ == "__main__":
    main()
