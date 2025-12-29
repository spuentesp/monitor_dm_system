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

# Pattern for human-created branches (require use case ID)
HUMAN_PATTERN = re.compile(r"^(feature|bugfix)/((?:DL|P|M|Q|I|SYS|CF|ST|RS|DOC)-\d+)-[a-z0-9-]+$", re.IGNORECASE)

# Pattern for copilot/bot branches (more flexible - just require reasonable naming)
COPILOT_PATTERN = re.compile(r"^copilot/[a-z0-9-]+$", re.IGNORECASE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce branch naming convention.")
    parser.add_argument("--branch", required=True, help="Branch name to validate.")
    args = parser.parse_args()

    branch = args.branch

    # Allow copilot branches with flexible naming
    if COPILOT_PATTERN.match(branch):
        print("✓ Branch name OK (copilot branch).")
        return 0

    # Human branches require use case ID
    if HUMAN_PATTERN.match(branch):
        print("✓ Branch name OK.")
        return 0

    print(
        "❌ Branch name must match:\n"
        "   - feature/<USECASE>-short-desc (e.g., feature/P-6-answer-question)\n"
        "   - bugfix/<USECASE>-short-desc (e.g., bugfix/DL-3-fix-validation)\n"
        "   - copilot/<description> (e.g., copilot/manage-facts-and-events)"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
