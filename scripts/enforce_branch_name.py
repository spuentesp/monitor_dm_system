#!/usr/bin/env python3
"""
Enforce branch naming convention: feature/<USECASE>-short-desc or bugfix/<USECASE>-short-desc.
Valid use-case prefixes: P-, M-, Q-, I-, SYS-, CF-, ST-, RS-.

Usage (CI):
    python scripts/enforce_branch_name.py --branch "$GITHUB_HEAD_REF"
"""

from __future__ import annotations

import argparse
import re
import sys

PATTERN = re.compile(r"^(feature|bugfix)/((?:DL|P|M|Q|I|SYS|CF|ST|RS|DOC)-\d+)-[a-z0-9-]+$", re.IGNORECASE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce branch naming convention.")
    parser.add_argument("--branch", required=True, help="Branch name to validate.")
    args = parser.parse_args()

    if PATTERN.match(args.branch):
        print("✓ Branch name OK.")
        return 0

    print(
        "❌ Branch name must match: feature/<USECASE>-short-desc or bugfix/<USECASE>-short-desc "
        "(e.g., feature/P-6-answer-question)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
