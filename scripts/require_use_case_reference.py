#!/usr/bin/env python3
"""
Fail if the PR (commit range) does not mention a use-case ID.

Valid patterns: P-#, M-#, Q-#, I-#, SYS-#, CF-#, ST-#, RS-# in commit messages
or in the PR body (when run in CI with GITHUB_EVENT_PATH).

Usage:
    python scripts/require_use_case_reference.py --base <commit-ish>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

USE_CASE_RE = re.compile(r"\b(?:DL|P|M|Q|I|SYS|CF|ST|RS|DOC)-\d+\b")


def git_commit_messages(base: str) -> str:
    result = subprocess.run(
        ["git", "log", "--format=%B", f"{base}..HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def pr_body_from_event() -> str:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).exists():
        return ""
    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)
    return event.get("pull_request", {}).get("body", "") or ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Require a use-case ID reference.")
    parser.add_argument(
        "--base", required=True, help="Base commit-ish to diff against."
    )
    args = parser.parse_args()

    text = git_commit_messages(args.base) + "\n" + pr_body_from_event()

    if not USE_CASE_RE.search(text):
        print("❌ No use-case ID (e.g., P-1, ST-3) found in commits or PR body.")
        print("Please reference at least one documented use case.")
        return 1

    print("✓ Use-case reference found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
