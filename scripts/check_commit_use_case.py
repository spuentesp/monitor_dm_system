#!/usr/bin/env python3
"""
Ensure every commit message in a range references a documented use-case ID.

Valid patterns: P-#, M-#, Q-#, I-#, SYS-#, CF-#, ST-#, RS-#, DOC-#

Usage:
    python scripts/check_commit_use_case.py --base <commit-ish>
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

USE_CASE_RE = re.compile(r"\b(?:P|M|Q|I|SYS|CF|ST|RS|DOC)-\d+\b")


def git_commits(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "log", "--format=%H:%s", f"{base}..HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Require use-case ID in each commit message.")
    parser.add_argument("--base", required=True, help="Base commit-ish to diff against.")
    args = parser.parse_args()

    commits = git_commits(args.base)
    failures = []
    for entry in commits:
        sha, _, message = entry.partition(":")
        if not USE_CASE_RE.search(message):
            failures.append((sha, message))

    if failures:
        print("❌ Commit messages missing use-case ID:")
        for sha, msg in failures:
            print(f"  - {sha[:7]}: {msg}")
        return 1

    print("✓ All commits include a use-case ID.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
