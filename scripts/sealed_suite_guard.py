#!/usr/bin/env python3
"""
Guardrail: keep the sealed verification suites (T_test) out of implementer agents' reach.

Rules:
  - `tests/verification/**` and `tests/property/**` are sealed. The implementer
    agent may not modify or delete files under these paths.
  - A change to a sealed path is only legitimate with maintainer sign-off: the
    PR carries the `sealed-override` label (applied by a maintainer) and passes
    CODEOWNERS review.

Usage:
    python3 scripts/sealed_suite_guard.py --base <ref> [--allow-sealed]   # CI
    python3 scripts/sealed_suite_guard.py --staged [--allow-sealed]       # pre-commit

Exit codes: 0 clean (or override), 1 seal violation, 2 usage/environment error.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SEALED_PATHS: tuple[str, ...] = ("tests/verification/", "tests/property/")


def seal_violations(paths: list[str]) -> list[str]:
    """Return the subset of paths that live under a sealed suite."""
    return [p for p in paths if p.startswith(SEALED_PATHS)]


def evaluate(paths: list[str], allow_sealed: bool) -> tuple[int, str]:
    """Apply the seal rule to a list of changed paths. Pure function; no git."""
    violations = seal_violations(paths)
    if not violations:
        return 0, "Sealed-suite guard passed: no sealed paths touched."
    listing = "\n".join(f"  - {p}" for p in violations)
    if allow_sealed:
        return 0, f"[OVERRIDE] sealed-override active; sealed paths changed:\n{listing}"
    message = (
        "[FAIL] sealed-suite-guard: changes under the sealed verification suites are not "
        "allowed without maintainer sign-off.\n"
        "Rule: implementer agents may not modify or delete tests/verification/** or "
        "tests/property/**.\n"
        "Offending paths:\n"
        f"{listing}\n"
        "Legitimate route: ask a maintainer to apply the 'sealed-override' label to this PR "
        "(CODEOWNERS review still applies), or drop these changes from the PR."
    )
    return 1, message


def _git_lines(*args: str) -> list[str]:
    # Run git in the caller's working tree (like every git tool) so the guard
    # inspects the repo it is invoked against, not the script's install path.
    proc = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def changed_files(base: str) -> list[str]:
    # --no-renames: a pure rename lists only the destination by default, which
    # would let a `git mv` out of a sealed suite slip past the guard.
    return _git_lines("diff", "--name-only", "--no-renames", f"{base}...HEAD")


def staged_files() -> list[str]:
    return _git_lines("diff", "--cached", "--name-only", "--no-renames")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when a change touches the sealed verification suites without override."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--base", metavar="REF", help="Compare REF...HEAD (CI mode).")
    mode.add_argument(
        "--staged",
        action="store_true",
        help="Inspect staged changes (pre-commit mode).",
    )
    parser.add_argument(
        "--allow-sealed",
        action="store_true",
        help="Maintainer override (CI passes this when the PR carries the sealed-override label).",
    )
    args = parser.parse_args(argv)

    try:
        paths = staged_files() if args.staged else changed_files(args.base)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 2

    code, message = evaluate(paths, args.allow_sealed)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
