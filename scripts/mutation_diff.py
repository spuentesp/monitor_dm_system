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


class AllowlistError(ValueError):
    """The allowlist file is malformed; refuse to treat it as an implicit pass."""


def filter_in_diff(
    survivors: list[Survivor],
    hunk_ranges: dict[str, set[int]],
) -> tuple[list[Survivor], list[Survivor]]:
    """Split survivors into (inside PR hunks, outside PR hunks) by mutant line."""
    in_diff: list[Survivor] = []
    outside: list[Survivor] = []
    for survivor in survivors:
        lines = hunk_ranges.get(survivor.module_path, set())
        if survivor.line in lines:
            in_diff.append(survivor)
        else:
            outside.append(survivor)
    return in_diff, outside


def evaluate_gate(
    in_diff: list[Survivor],
    outside: list[Survivor],
    allowlist: dict[tuple[str, str, int], str],
) -> int:
    """Policy: only in-diff survivors block, and only when not allowlisted."""
    for survivor in outside:
        print(
            f"[warn] pre-existing survivor outside diff: "
            f"{survivor.module_path}:{survivor.line} {survivor.operator_name} "
            f"occurrence={survivor.occurrence}"
        )
    blocking = [
        s
        for s in in_diff
        if (s.module_path, s.operator_name, s.occurrence) not in allowlist
    ]
    if blocking:
        print("[FAIL] mutation-diff: surviving mutants on changed lines:")
        for s in blocking:
            where = f" in {s.definition_name}" if s.definition_name else ""
            print(
                f"  - {s.module_path}:{s.line} {s.operator_name} "
                f"occurrence={s.occurrence}{where}"
            )
        print(
            "Kill them with real assertions, or (proven equivalent mutants only) add "
            "entries to scripts/mutation_allowlist.toml with a justification."
        )
        return 1
    print(
        f"mutation-diff: {len(in_diff)} in-diff survivor(s) allowlisted; "
        f"{len(outside)} pre-existing survivor(s) outside the diff."
    )
    return 0


def load_allowlist(path: Path) -> dict[tuple[str, str, int], str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    entries: dict[tuple[str, str, int], str] = {}
    for entry in data.get("survivors", []):
        key = (entry["module_path"], entry["operator_name"], int(entry["occurrence"]))
        justification = str(entry.get("justification", "")).strip()
        if not justification:
            raise AllowlistError(
                f"allowlist entry {key} lacks a non-empty 'justification' string"
            )
        entries[key] = justification
    return entries


FALLBACK_OPERATOR_SET = (
    "core/Boolean",
    "core/Break",
    "core/Continue",
    "core/Deletion",
    "core/Number",
    "core/String",
    "core/Variable",
)


def load_known_configs(root: Path) -> dict[str, Path]:
    """Map module-path -> config file for the curated cosmic-ray-*.toml files."""
    known: dict[str, Path] = {}
    for config in sorted(root.glob("cosmic-ray*.toml")):
        data = tomllib.loads(config.read_text(encoding="utf-8"))
        module_path = data.get("cosmic-ray", {}).get("module-path")
        if module_path:
            known[module_path] = config
    return known


def package_root(file: Path, root: Path) -> Path:
    """Nearest ancestor of the file that contains a pyproject.toml."""
    current = (root / file).parent
    while current != root and current != current.parent:
        if (current / "pyproject.toml").exists():
            return current.relative_to(root)
        current = current.parent
    return Path(".")


def write_generated_config(module: Path, root: Path, tmp_dir: Path) -> Path:
    pkg = package_root(module, root)
    test_command = (
        f"python -m pytest {pkg}/tests tests/unit -x -q --timeout=15 "
        f"--tb=line -p no:cacheprovider --no-header"
    )
    operators = "\n".join(f'    "{op}",' for op in FALLBACK_OPERATOR_SET)
    config_text = (
        f'[cosmic-ray]\nmodule-path = "{module}"\npython-version = ""\n'
        f"timeout = 30\nexcluded-modules = []\n"
        f'test-command = "{test_command}"\n\n'
        f'[cosmic-ray.distributor]\nname = "local"\n\n'
        f"[cosmic-ray.operators]\nenabled = [\n{operators}\n]\n"
    )
    config_path = tmp_dir / f"generated-{module.name}.toml"
    config_path.write_text(config_text, encoding="utf-8")
    return config_path


def run_session(config: Path, root: Path) -> Path:
    """Initialize and execute a Cosmic Ray session for one config; return the DB path."""
    session_db = config.with_suffix(".session.sqlite3")
    for command in (
        ["uv", "run", "cosmic-ray", "init", str(config), str(session_db)],
        ["uv", "run", "cosmic-ray", "exec", str(config), str(session_db)],
    ):
        proc = subprocess.run(command, cwd=root, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"{' '.join(command)} failed: {proc.stderr.strip() or proc.stdout.strip()}"
            )
    return session_db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when a surviving mutant lands on a line this PR changed."
    )
    parser.add_argument("--base", required=True, metavar="REF", help="Compare REF...HEAD.")
    parser.add_argument(
        "--allowlist",
        default=str(ROOT / "scripts" / "mutation_allowlist.toml"),
        help="Path to the survivors allowlist (justified equivalent mutants only).",
    )
    args = parser.parse_args(argv)

    try:
        changed = changed_production_files(args.base, ROOT)
        if not changed:
            print("mutation-diff: no production Python changes; nothing to do.")
            return 0

        hunks = parse_hunk_ranges(git_diff_u0(args.base, ROOT, changed))
        known = load_known_configs(ROOT)

        survivors: list[Survivor] = []
        with tempfile.TemporaryDirectory(prefix="mutation-diff-") as tmp:
            tmp_dir = Path(tmp)
            for module in changed:
                config = known.get(str(module)) or write_generated_config(module, ROOT, tmp_dir)
                session = run_session(config, ROOT)
                survivors.extend(extract_survivors(session))

        in_diff, outside = filter_in_diff(survivors, hunks)
        allowlist = load_allowlist(Path(args.allowlist))
        return evaluate_gate(in_diff, outside, allowlist)
    except (RuntimeError, AllowlistError) as exc:
        print(f"[ERROR] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
