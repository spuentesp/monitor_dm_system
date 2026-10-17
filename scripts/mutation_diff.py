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
import os
import re
import signal
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
        # --diff-filter=ACMR: deleted modules have no mutants to run; cosmic-ray
        # init aborts on missing module paths.
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD", "--", "packages/"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
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
        # Fixture/e2e helper trees are test scaffolding, not mutation targets.
        if "/fixtures/" in f"/{name}" or "/e2e/" in f"/{name}":
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
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git diff -U0 failed: {proc.stderr.strip()}")
    return proc.stdout


def extract_survivors(session_db: Path) -> list[Survivor]:
    """Read surviving mutants out of a Cosmic Ray session database.

    An item whose tests never ran (worker exception / no-test / skipped) is a
    configuration error, never a silent kill: fail closed so a broken
    test-command cannot mark every mutant "killed".
    """
    from cosmic_ray.work_db import WorkDB
    from cosmic_ray.work_item import TestOutcome, WorkerOutcome

    survivors: list[Survivor] = []
    db = WorkDB(session_db, WorkDB.Mode.open)
    try:
        for work_item, result in db.completed_work_items:
            if result.worker_outcome != WorkerOutcome.NORMAL or result.test_outcome is None:
                raise RuntimeError(
                    f"mutation session did not run cleanly (worker={result.worker_outcome}, "
                    f"test={result.test_outcome}, job={work_item.job_id}): fix the test-command "
                    f"before trusting any verdict"
                )
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


def _run_process_group(
    command: str | list[str],
    cwd: Path,
    timeout: int,
    shell: bool = False,
) -> "subprocess.CompletedProcess[str]":
    """Run a command in its own process group; on timeout kill the WHOLE group.

    Killing only the direct child (e.g. the `uv run` wrapper) would leak its
    grandchildren (cosmic-ray/pytest workers) on the runner.
    """
    proc = subprocess.Popen(
        command,
        shell=shell,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        raise subprocess.TimeoutExpired(command, timeout) from exc
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


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
    allowlist: dict[tuple[str, str, int, int], str],
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
        if (s.module_path, s.operator_name, s.occurrence, s.line) not in allowlist
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
    if in_diff:
        print(
            f"mutation-diff: {len(in_diff)} in-diff survivor(s) covered by the "
            f"allowlist; {len(outside)} pre-existing survivor(s) outside the diff."
        )
    else:
        print(
            f"mutation-diff: no surviving mutants on changed lines; "
            f"{len(outside)} pre-existing survivor(s) outside the diff."
        )
    return 0


def load_allowlist(path: Path) -> dict[tuple[str, str, int, int], str]:
    """Load justified equivalent mutants, keyed AND line-anchored.

    The key includes the mutant's source line: occurrence renumbering across
    edits must never let an entry whitelist an unrelated survivor.
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AllowlistError(f"allowlist file missing: {path}") from exc
    except OSError as exc:
        raise AllowlistError(f"allowlist file unreadable: {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise AllowlistError(f"allowlist TOML invalid in {path}: {exc}") from exc
    entries: dict[tuple[str, str, int, int], str] = {}
    try:
        rows = data.get("survivors", [])
        for entry in rows:
            key = (
                str(entry["module_path"]),
                str(entry["operator_name"]),
                int(entry["occurrence"]),
                int(entry["line"]),
            )
            justification = entry.get("justification", "")
            if not isinstance(justification, str) or not justification.strip():
                raise AllowlistError(
                    f"allowlist entry {key} lacks a non-empty string 'justification'"
                )
            entries[key] = justification.strip()
    except AllowlistError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise AllowlistError(f"allowlist entry malformed in {path}: {exc}") from exc
    return entries


# NOTE: cosmic-ray 8 runs the FULL registered operator battery per module; a
# `[cosmic-ray.operators] enabled` list does NOT restrict it (that table only
# parameterizes argument-taking operators). Budgets below assume the full
# battery; bound scope by which modules the PR touches, not by operator names.


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
    raise RuntimeError(
        f"no package root for {file}: expected a pyproject.toml above it "
        f"(mutation targets must live inside a workspace package)"
    )


def tests_for_module(module: Path, root: Path) -> list[Path]:
    """Test files that actually exercise the module (by import), package-wide
    fallback when no test imports it directly."""
    dotted = str(module.with_suffix("")).replace("/", ".").split("src.", 1)[-1]
    pkg = package_root(module, root)
    pkg_tests = root / pkg / "tests"
    if not pkg_tests.is_dir():
        return []
    selected = []
    for test_file in sorted(pkg_tests.rglob("test_*.py")):
        try:
            text = test_file.read_text(encoding="utf-8")
        except OSError:
            continue
        if dotted in text or module.stem in text and f"import {module.stem}" in text:
            selected.append(test_file.relative_to(root))
    if selected:
        return selected
    return sorted(p.relative_to(root) for p in pkg_tests.rglob("test_*.py"))


def write_generated_config(module: Path, root: Path, tmp_dir: Path) -> Path:
    pkg = package_root(module, root)
    # Tests that actually exercise the module (by import), falling back to the
    # owning package's test tree — never the whole repo's suites.
    targets = tests_for_module(module, root) or [f"{pkg}/tests"]
    target_str = " ".join(str(p) for p in targets)
    test_command = (
        f"python -m pytest {target_str} -x -q --timeout=15 "
        f"--tb=line -p no:cacheprovider --no-header"
    )
    config_text = (
        f'[cosmic-ray]\nmodule-path = "{module}"\npython-version = ""\n'
        f"timeout = 30\nexcluded-modules = []\n"
        f'test-command = "{test_command}"\n\n'
        f'[cosmic-ray.distributor]\nname = "local"\nnum-workers = 8\n'
    )
    config_path = tmp_dir / f"generated-{str(module).replace('/', '__')}.toml"
    config_path.write_text(config_text, encoding="utf-8")
    return config_path


def run_session(
    config: Path,
    root: Path,
    module_budget_secs: int = 600,
    session_dir: Path | None = None,
) -> Path:
    """Initialize and execute a Cosmic Ray session for one config; return the DB path.

    module_budget_secs bounds one module's `cosmic-ray exec`; exceeding it is a
    budget error (exit 2 with guidance), never a false survivor verdict.
    session_dir keeps session DBs out of the repo root (defaults to a temp dir).
    """
    if session_dir is None:
        session_dir = Path(tempfile.mkdtemp(prefix="mutation-session-"))
    session_dir.mkdir(parents=True, exist_ok=True)
    session_db = session_dir / f"{config.stem}.session.sqlite3"
    import tomllib as _tomllib

    test_command = _tomllib.loads(config.read_text(encoding="utf-8"))["cosmic-ray"]["test-command"]
    try:
        baseline = _run_process_group(
            test_command, root, module_budget_secs, shell=True
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"mutation budget exceeded: the baseline test-command ran longer than "
            f"{module_budget_secs}s: {test_command}"
        ) from exc
    if baseline.returncode != 0:
        raise RuntimeError(
            f"mutation baseline failed: the unmutated test-command must pass before "
            f"mutants run (exit {baseline.returncode}): {test_command}\n"
            f"{baseline.stderr.strip() or baseline.stdout.strip()}"
        )
    commands = (
        (["uv", "run", "cosmic-ray", "init", str(config), str(session_db)], 60),
        (["uv", "run", "cosmic-ray", "exec", str(config), str(session_db)], module_budget_secs),
    )
    for command, budget in commands:
        try:
            proc = _run_process_group(command, root, budget)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"mutation budget exceeded: {' '.join(command)} ran longer than "
                f"{budget}s. Re-run this module locally without the budget, or land "
                f"the change in smaller PRs: uv run python scripts/mutation_diff.py "
                f"--base <ref> on a branch that touches fewer modules."
            ) from exc
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

        # Fail fast on a malformed allowlist — before any expensive session runs.
        allowlist = load_allowlist(Path(args.allowlist))
        hunks = parse_hunk_ranges(git_diff_u0(args.base, ROOT, changed))
        known = load_known_configs(ROOT)

        survivors: list[Survivor] = []
        with tempfile.TemporaryDirectory(prefix="mutation-diff-") as tmp:
            tmp_dir = Path(tmp)
            for module in changed:
                config = known.get(str(module)) or write_generated_config(module, ROOT, tmp_dir)
                session = run_session(config, ROOT, session_dir=tmp_dir)
                survivors.extend(extract_survivors(session))

        in_diff, outside = filter_in_diff(survivors, hunks)
        return evaluate_gate(in_diff, outside, allowlist)
    except (RuntimeError, AllowlistError) as exc:
        print(f"[ERROR] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
