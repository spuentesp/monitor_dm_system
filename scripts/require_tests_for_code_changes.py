#!/usr/bin/env python3
"""
Require tests when code changes.

If any files under packages/*/src change between BASE and HEAD, at least one
test file must also change (packages/*/tests or any path containing "test").

Usage:
    python scripts/require_tests_for_code_changes.py --base <commit-ish>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git_diff(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base, "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_code_path(path: str) -> bool:
    p = Path(path)
    parts = p.parts
    return len(parts) > 2 and parts[0] == "packages" and parts[2] == "src"


def is_test_path(path: str) -> bool:
    p = Path(path)
    return "tests" in p.parts or "test" in p.name


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if code changes lack test changes."
    )
    parser.add_argument(
        "--base", required=True, help="Base commit-ish to diff against."
    )
    args = parser.parse_args()

    changed = git_diff(args.base)
    code_changed = [p for p in changed if is_code_path(p)]
    tests_changed = [p for p in changed if is_test_path(p)]

    if code_changed and not tests_changed:
        print("❌ Code changed without accompanying tests.")
        print("Changed code files:")
        for path in code_changed:
            print(f"  - {path}")
        print("\nAdd or update tests under packages/*/tests/ before merging.")
        return 1

    print("✓ Code/test pairing check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
