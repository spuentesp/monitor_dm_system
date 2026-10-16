#!/usr/bin/env python3
"""
Gate: fail when a surviving mutant lands on a line this PR changed.

Workflow:
  1. Changed production files: `git diff --name-only <base>...HEAD -- packages/`.
  2. Diff hunks (-U0) give the new-side line numbers this PR actually touched.
  3. For each changed module, run Cosmic Ray (reuse the module's curated
     cosmic-ray-*.toml when one exists, else generate a temporary config) and
     read survivors from the session DB (WorkDB.completed_work_items).
  4. Only survivors whose mutant line falls inside the PR's hunks block;
     everything else is pre-existing debt and only warns.
  5. scripts/mutation_allowlist.toml is the only exception route (equivalent
     mutants, each with a written justification).

Exit codes: 0 clean, 1 blocking survivor, 2 configuration/environment error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")


@dataclass(frozen=True)
class Survivor:
    module_path: str
    operator_name: str
    occurrence: int
    line: int
    definition_name: str | None


def changed_production_files(base: str, root: Path) -> list[Path]:
    """Production .py files under packages/ touched by the PR (tests excluded)."""
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD", "--", "packages/"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git diff failed: {proc.stderr.strip()}")
    out: list[Path] = []
    for line in proc.stdout.splitlines():
        name = line.strip()
        if not name.endswith(".py"):
            continue
        if "/tests/" in f"/{name}":
            continue
        out.append(Path(name))
    return out


def parse_hunk_ranges(diff_text: str) -> dict[str, set[int]]:
    """Map each file in a unified diff to the new-side line numbers it touches."""
    ranges: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        file_match = FILE_RE.match(line)
        if file_match:
            current = file_match.group(1)
            ranges.setdefault(current, set())
            continue
        if current is None:
            continue
        hunk_match = HUNK_RE.match(line)
        if hunk_match:
            start = int(hunk_match.group(1))
            count = 1 if hunk_match.group(2) is None else int(hunk_match.group(2))
            ranges[current].update(range(start, start + count))
    return ranges


def git_diff_u0(base: str, root: Path, paths: list[Path]) -> str:
    proc = subprocess.run(
        ["git", "diff", "-U0", f"{base}...HEAD", "--", *[str(p) for p in paths]],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git diff -U0 failed: {proc.stderr.strip()}")
    return proc.stdout


def extract_survivors(session_db: Path) -> list[Survivor]:
    """Read surviving mutants out of a Cosmic Ray session database."""
    from cosmic_ray.work_db import WorkDB
    from cosmic_ray.work_item import TestOutcome

    survivors: list[Survivor] = []
    db = WorkDB(session_db, WorkDB.Mode.open)
    try:
        for work_item, result in db.completed_work_items:
            if result.test_outcome != TestOutcome.SURVIVED:
                continue
            for spec in work_item.mutations:
                survivors.append(
                    Survivor(
                        module_path=str(spec.module_path),
                        operator_name=spec.operator_name,
                        occurrence=spec.occurrence,
                        line=spec.start_pos[0],
                        definition_name=spec.definition_name,
                    )
                )
    finally:
        db.close()
    return survivors


# ---- Policy layer (Task 4) is appended below this line. ----
