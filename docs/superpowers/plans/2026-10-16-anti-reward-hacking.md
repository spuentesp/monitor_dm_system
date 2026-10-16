# Anti-Reward-Hacking Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make it impossible for a code agent to weaken MONITOR's verification layer or fake a green test run without maintainer sign-off — sealed `T_test` suites, a zero-survivors mutation gate on the PR diff, and topology checks against no-op bypasses.

**Architecture:** Three enforcement layers (local pre-commit as best effort, CI as the hard gate, CODEOWNERS as governance) around one shared guard script (`scripts/sealed_suite_guard.py`); a diff-scoped Cosmic Ray mutation gate (`scripts/mutation_diff.py`); lightweight invocation counters in the existing DST suite. Sealing is in place — `tests/verification/` and `tests/property/` are never moved or renamed.

**Tech Stack:** Python 3.11, uv workspace, pytest, Cosmic Ray (already configured: 13 `cosmic-ray-*.toml` + weekly `mutation.yml`), ruff (BLE001/S110/S112/E722), inline-snapshot, GitHub Actions, pre-commit, CODEOWNERS.

**Spec:** `docs/superpowers/specs/2026-10-16-anti-reward-hacking-design.md`

## Global Constraints

- Python `>=3.11`; all commands run through `uv run` from the repo root.
- Sealed paths are exactly `tests/verification/` and `tests/property/` (constant `SEALED_PATHS` in `scripts/sealed_suite_guard.py`). They are never moved, renamed, or deleted.
- Override label is exactly `sealed-override`; CODEOWNERS owner is exactly `@spuentesp`.
- Mutation gate: zero surviving mutants on lines inside the PR diff; `scripts/mutation_allowlist.toml` is the only exception route; survivors outside diff hunks warn but never block.
- Ruff rules enabled for `packages/**`: `BLE001`, `S110`, `S112`, `E722`. User decision: fix **all** existing violations in this change (537 BLE001 + 62 S110 + 5 S112 at plan time); `# noqa: BLE001  # reason: <why>` is allowed only for genuinely intentional broad catches (watchdog loops, middleware boundaries) — never as a way to skip work.
- No new runtime dependencies. The only new dependency is dev-only `inline-snapshot`.
- Layer rules stay green: `python scripts/check_layer_dependencies.py` must pass after every task.
- `uv run pytest packages tests -q` must pass after every task (hermetic suite; `tests/conftest.py` forces fake keys and `pytest-socket` blocks the network).
- Scripts follow the style of `scripts/check_layer_dependencies.py`: stdlib-only where possible, `print()` output, `if __name__ == "__main__": sys.exit(main())`. `structlog` is for `packages/**`, not `scripts/`.
- The rollout PR itself edits a sealed path (Task 9) — it must carry the `sealed-override` label to pass its own guard job.

## Review Focus

1. **Fail-closed on unlabeled sealed changes.** A PR whose diff touches `tests/property/**` and carries no labels must exit 1 with an actionable message; an empty or unrelated diff must exit 0. Pinned by `test_evaluate_flags_sealed_paths` and `test_evaluate_clean_for_unrelated_paths` (Task 1).
2. **Docs-only PRs must cost zero mutation minutes.** When the diff has no production Python files under `packages/`, `mutation_diff.py` exits 0 without invoking Cosmic Ray. Pinned by `test_no_production_changes_short_circuits` (Task 3).
3. **Only in-diff survivors block.** A surviving mutant on a line outside the PR's hunks (pre-existing debt in a touched module) prints a warning and exits 0. Pinned by `test_out_of_diff_survivor_only_warns` (Task 4).
4. **A malformed allowlist cannot silently allow.** An entry without a non-empty `justification` is a configuration error (exit 2), not an implicit pass. Pinned by `test_allowlist_entry_without_justification_is_error` (Task 4).
5. **The BLE001 sweep must not change runtime behavior.** Broad catches in worker/watchdog/middleware loops stay broad (with justified `# noqa: BLE001`); only genuinely narrowable catches get narrowed. Pinned by per-package `uv run pytest packages tests -q` after each sweep (Tasks 6–8) plus a taxonomy with worked examples enforced by review.

---

### Task 1: Sealed-suite guard script + meta-tests

**Files:**
- Create: `scripts/sealed_suite_guard.py`
- Test: `tests/unit/test_sealed_suite_guard.py`

**Interfaces:**
- Consumes: nothing (stdlib only; runs `git` via `subprocess`).
- Produces: `scripts/sealed_suite_guard.py` CLI — `--base <ref>` or `--staged` (mutually exclusive, one required), optional `--allow-sealed`. Exit codes: `0` clean/override, `1` seal violation, `2` usage or git error. Module-level `evaluate(paths: list[str], allow_sealed: bool) -> tuple[int, str]`, `SEALED_PATHS: tuple[str, ...] = ("tests/verification/", "tests/property/")`. Task 2 invokes the CLI; no other task imports the module.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_sealed_suite_guard.py`:

```python
"""Meta-tests for scripts/sealed_suite_guard.py (T_val — visible suite).

The guard is the enforcement mechanism for the sealed T_test suites, so its own
tests must live outside the sealed paths and run in the default hermetic suite.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "sealed_suite_guard.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("sealed_suite_guard", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


def test_evaluate_clean_for_unrelated_paths() -> None:
    code, message = guard.evaluate(
        ["packages/agents/src/monitor_agents/narrator/agent.py", "docs/_index.md"],
        allow_sealed=False,
    )
    assert code == 0
    assert "passed" in message


def test_evaluate_empty_diff_is_clean() -> None:
    code, _ = guard.evaluate([], allow_sealed=False)
    assert code == 0


def test_evaluate_flags_sealed_paths() -> None:
    code, message = guard.evaluate(
        [
            "tests/property/test_scene_properties.py",
            "packages/agents/src/monitor_agents/narrator/agent.py",
        ],
        allow_sealed=False,
    )
    assert code == 1
    assert "tests/property/test_scene_properties.py" in message
    assert "sealed-override" in message


def test_evaluate_flags_verification_path() -> None:
    code, message = guard.evaluate(
        ["tests/verification/test_monitor_wiring_dst.py"],
        allow_sealed=False,
    )
    assert code == 1
    assert "tests/verification/test_monitor_wiring_dst.py" in message


def test_evaluate_override_label_allows_sealed_changes() -> None:
    code, message = guard.evaluate(
        ["tests/verification/test_monitor_wiring_dst.py"],
        allow_sealed=True,
    )
    assert code == 0
    assert "[OVERRIDE]" in message


def test_seal_violations_uses_prefix_tuple() -> None:
    assert guard.seal_violations(["tests/property/x.py"]) == ["tests/property/x.py"]
    assert guard.seal_violations(["tests/unit/test_x.py"]) == []
    assert guard.seal_violations(["tests/property_notes.md"]) == []


def test_cli_without_mode_exits_2() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 2
    assert "usage" in (proc.stderr + proc.stdout).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_sealed_suite_guard.py -v`
Expected: collection error — `FileNotFoundError` / `ModuleNotFoundError` because `scripts/sealed_suite_guard.py` does not exist.

- [ ] **Step 3: Implement `scripts/sealed_suite_guard.py`**

```python
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
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def changed_files(base: str) -> list[str]:
    return _git_lines("diff", "--name-only", f"{base}...HEAD")


def staged_files() -> list[str]:
    return _git_lines("diff", "--cached", "--name-only")


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_sealed_suite_guard.py -v`
Expected: 7 passed.

- [ ] **Step 5: Verify the CLI in a real git invocation**

Run: `uv run python scripts/sealed_suite_guard.py --base HEAD~1`
Expected: exit 0 with "Sealed-suite guard passed" (or `[OVERRIDE]`/`[FAIL]` if the local diff touches sealed paths — acceptable while developing; the unit tests are the contract).

- [ ] **Step 6: Commit**

```bash
git add scripts/sealed_suite_guard.py tests/unit/test_sealed_suite_guard.py
git commit -m "feat(guard): add sealed-suite guard for T_test protection"
```

---

### Task 2: Seal enforcement surface — pre-commit, CODEOWNERS, CI job, docs

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `.github/CODEOWNERS`
- Modify: `.github/workflows/ci.yml` (new `sealed-suite-guard` job)
- Modify: `CONTRIBUTING.md` (new section; fix stale pre-commit line)
- Modify: `AGENTS.md` (Key Conventions)
- Modify: `CLAUDE.md` (Key Constraints)

**Interfaces:**
- Consumes: `scripts/sealed_suite_guard.py` CLI from Task 1 (`--base`, `--staged`, `--allow-sealed`, exit codes 0/1/2).
- Produces: the enforcement surface. No code interfaces for later tasks; later tasks must know the rollout PR needs the `sealed-override` label (Task 10).

- [ ] **Step 1: Create `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: local
    hooks:
      - id: sealed-suite-guard
        name: sealed-suite guard (T_test protection)
        entry: python3 scripts/sealed_suite_guard.py --staged
        language: system
        pass_filenames: false
        always_run: true
```

- [ ] **Step 2: Create `.github/CODEOWNERS`**

```
# Sealed verification suites (T_test): changes require maintainer review.
# Enable "Require review from Code Owners" in branch protection to enforce.
tests/verification/** @spuentesp
tests/property/** @spuentesp
```

- [ ] **Step 3: Add the `sealed-suite-guard` job to `.github/workflows/ci.yml`**

Insert after the `lint` job (same indentation as the other jobs):

```yaml
  sealed-suite-guard:
    name: Sealed-suite guard (T_test)
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Guard sealed verification suites
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          LABELS: ${{ join(github.event.pull_request.labels.*.name, ',') }}
        run: |
          ALLOW=""
          case ",${LABELS}," in
            *,sealed-override,*) ALLOW="--allow-sealed" ;;
          esac
          python3 scripts/sealed_suite_guard.py --base "${BASE_SHA}" ${ALLOW}
```

Note: the job is stdlib-only — no `uv sync` step. `fetch-depth: 0` is required so `git diff base...HEAD` can resolve the PR's changes.

- [ ] **Step 4: Document the rules in `CONTRIBUTING.md`**

Append this section before `## Optional Tools`, and replace the stale line
"`pre-commit install` to run mypy pytest/mypy/pytest hook before commits." with
"`pre-commit install` to run the sealed-suite guard before commits.":

```markdown
## Sealed Verification Suites (T_val / T_test)

This repo splits its tests into two trust tiers:

- **T_val (visible, freely editable):** `tests/unit/`, `tests/api/`, `tests/contracts/`,
  `tests/behavior/`, `tests/e2e/`, `tests/smoke/` and per-package `tests/` dirs. Iterate
  here as fast as you need.
- **T_test (sealed):** `tests/verification/` (DST + cross-store oracle) and
  `tests/property/` (Hypothesis properties). **Implementers may not modify or delete
  files under these paths.**

Enforcement:

1. Pre-commit runs `scripts/sealed_suite_guard.py --staged` (best effort).
2. CI job `sealed-suite-guard` fails any PR whose diff touches sealed paths unless the
   PR carries the `sealed-override` label. Labels require write access — an agent cannot
   label its own PR.
3. `.github/CODEOWNERS` routes sealed-path changes to `@spuentesp`. Enable *Require
   review from Code Owners* in branch protection to enforce reviews.

A legitimate sealed-suite change (new property, stronger invariant, DST extension) lands
via: open the PR, explain why the sealed suite must change, and ask a maintainer to apply
`sealed-override` and review.

Mutation gate: `mutation-diff.yml` runs Cosmic Ray on the modules your PR touches and
fails when a mutant on a changed line survives. Kill it with a real assertion; the only
exception is `scripts/mutation_allowlist.toml`, which requires a written justification
(use it for proven equivalent mutants only).
```

- [ ] **Step 5: Add agent rules to `AGENTS.md`**

Append to the `## Key Conventions` section:

```markdown
### Sealed Test Suites (Anti-Reward-Hacking)

`tests/verification/**` and `tests/property/**` are sealed (`T_test`). Implementer
agents MUST NOT modify or delete files under these paths; CI enforces this via
`scripts/sealed_suite_guard.py` (override label `sealed-override` is maintainer-only).
Write tests for your changes in `tests/unit/`, `tests/api/`, `tests/contracts/`, or the
per-package `tests/` dirs instead. Mutants surviving on lines your PR changes fail CI
(`scripts/mutation_diff.py`); weaken nothing to get a green run.
```

- [ ] **Step 6: Mirror the rule in `CLAUDE.md`**

Append to the `## Key Constraints (From AGENTS.md)` section:

```markdown
- Sealed suites: never modify or delete `tests/verification/**` or `tests/property/**`
  (T_test). CI blocks it via `scripts/sealed_suite_guard.py`; only a maintainer applying
  the `sealed-override` label can land such changes. Never weaken asserts or hardcode
  responses to turn tests green — the mutation gate (`scripts/mutation_diff.py`) rejects
  survivors on changed lines.
```

- [ ] **Step 7: Verify guard + docs consistency**

Run: `uv run pytest tests/unit/test_sealed_suite_guard.py -q && python scripts/sealed_suite_guard.py --staged`
Expected: tests pass; guard exits 0 on the current staged set (docs/scripts only).

Run: `python scripts/check_layer_dependencies.py`
Expected: "All layer dependency checks passed."

- [ ] **Step 8: Commit**

```bash
git add .pre-commit-config.yaml .github/CODEOWNERS .github/workflows/ci.yml CONTRIBUTING.md AGENTS.md CLAUDE.md
git commit -m "feat(guard): enforce sealed T_test suites via pre-commit, CODEOWNERS and CI"
```

---

### Task 3: Mutation analysis core — changed modules, diff hunks, survivors

**Files:**
- Create: `scripts/mutation_diff.py`
- Test: `tests/unit/test_mutation_diff.py`

**Interfaces:**
- Consumes: Cosmic Ray Python API — `cosmic_ray.work_db.WorkDB` (constructor `(path, WorkDB.Mode.open)`; property `completed_work_items` yielding `(WorkItem, WorkResult)`), `cosmic_ray.work_item.TestOutcome` (`SURVIVED`, `KILLED`, `INCOMPETENT`), `WorkItem.mutations` (tuple of `MutationSpec`), `MutationSpec.start_pos: tuple[int, int]` (line, col of the mutant).
- Produces (module `scripts.mutation_diff`, loaded via `importlib` in tests exactly like Task 1):
  - `changed_production_files(base: str, root: Path) -> list[Path]` — `.py` files under `packages/` excluding any `tests/` dir.
  - `parse_hunk_ranges(diff_text: str) -> dict[str, set[int]]` — file path → new-side line numbers touched (from a `-U0` unified diff).
  - `extract_survivors(session_db: Path) -> list[Survivor]` where `Survivor` is a frozen dataclass with fields `module_path: str`, `operator_name: str`, `occurrence: int`, `line: int`, `definition_name: str | None`.
  - Task 4 consumes all four.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_mutation_diff.py`:

```python
"""Meta-tests for scripts/mutation_diff.py (T_val — visible suite).

Extraction is tested against a real cosmic_ray.WorkDB built in a tmp dir and
against synthetic unified-diff text; no Cosmic Ray run happens in these tests.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "mutation_diff.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("mutation_diff", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


md = _load_mod()


def test_parse_hunk_ranges_zero_context_diff() -> None:
    diff = (
        "diff --git a/packages/agents/src/monitor_agents/narrator/agent.py "
        "b/packages/agents/src/monitor_agents/narrator/agent.py\n"
        "--- a/packages/agents/src/monitor_agents/narrator/agent.py\n"
        "+++ b/packages/agents/src/monitor_agents/narrator/agent.py\n"
        "@@ -10,0 +11,2 @@\n"
        "+added_line_11\n"
        "+added_line_12\n"
        "@@ -40 +42 @@\n"
        "-old\n"
        "+new_line_42\n"
    )
    ranges = md.parse_hunk_ranges(diff)
    assert ranges["packages/agents/src/monitor_agents/narrator/agent.py"] == {11, 12, 42}


def test_parse_hunk_ranges_empty_new_side() -> None:
    diff = (
        "--- a/packages/agents/src/x.py\n"
        "+++ b/packages/agents/src/x.py\n"
        "@@ -5,2 +4,0 @@\n"
        "-deleted_a\n"
        "-deleted_b\n"
    )
    assert md.parse_hunk_ranges(diff) == {"packages/agents/src/x.py": set()}


def test_extract_survivors_reads_workdb(tmp_path: Path) -> None:
    from cosmic_ray.work_db import WorkDB
    from cosmic_ray.work_item import (
        MutationSpec,
        TestOutcome,
        WorkerOutcome,
        WorkItem,
        WorkResult,
    )

    db_path = tmp_path / "session.sqlite3"
    db = WorkDB(db_path, WorkDB.Mode.create)
    try:
        survivor_spec = MutationSpec(
            module_path=Path("packages/agents/src/monitor_agents/narrator/agent.py"),
            operator_name="core/Number",
            occurrence=0,
            start_pos=(11, 4),
            end_pos=(11, 8),
            definition_name="render_draft",
        )
        killed_spec = MutationSpec(
            module_path=Path("packages/agents/src/monitor_agents/narrator/agent.py"),
            operator_name="core/String",
            occurrence=1,
            start_pos=(42, 4),
            end_pos=(42, 9),
            definition_name="render_draft",
        )
        db.add_work_item(WorkItem.single("job-survivor", survivor_spec))
        db.add_work_item(WorkItem.single("job-killed", killed_spec))
        db.set_result(
            "job-survivor",
            WorkResult(worker_outcome=WorkerOutcome.NORMAL, test_outcome=TestOutcome.SURVIVED),
        )
        db.set_result(
            "job-killed",
            WorkResult(worker_outcome=WorkerOutcome.NORMAL, test_outcome=TestOutcome.KILLED),
        )
    finally:
        db.close()

    survivors = md.extract_survivors(db_path)
    assert len(survivors) == 1
    only = survivors[0]
    assert only.module_path == "packages/agents/src/monitor_agents/narrator/agent.py"
    assert only.operator_name == "core/Number"
    assert only.occurrence == 0
    assert only.line == 11
    assert only.definition_name == "render_draft"


def test_extract_survivors_ignores_incompetent_and_pending(tmp_path: Path) -> None:
    from cosmic_ray.work_db import WorkDB
    from cosmic_ray.work_item import (
        MutationSpec,
        TestOutcome,
        WorkerOutcome,
        WorkItem,
        WorkResult,
    )

    db_path = tmp_path / "session.sqlite3"
    db = WorkDB(db_path, WorkDB.Mode.create)
    try:
        spec = MutationSpec(
            module_path=Path("packages/data-layer/src/monitor_data/db/neo4j.py"),
            operator_name="core/Deletion",
            occurrence=3,
            start_pos=(7, 0),
            end_pos=(7, 10),
        )
        db.add_work_item(WorkItem.single("job-incompetent", spec))
        db.add_work_item(
            WorkItem.single(
                "job-pending",
                MutationSpec(
                    module_path=Path("packages/data-layer/src/monitor_data/db/neo4j.py"),
                    operator_name="core/Deletion",
                    occurrence=4,
                    start_pos=(9, 0),
                    end_pos=(9, 10),
                ),
            )
        )
        db.set_result(
            "job-incompetent",
            WorkResult(worker_outcome=WorkerOutcome.NORMAL, test_outcome=TestOutcome.INCOMPETENT),
        )
    finally:
        db.close()

    assert md.extract_survivors(db_path) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_mutation_diff.py -v`
Expected: collection error — `scripts/mutation_diff.py` does not exist.

- [ ] **Step 3: Implement the extraction core of `scripts/mutation_diff.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_mutation_diff.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/mutation_diff.py tests/unit/test_mutation_diff.py
git commit -m "feat(mutation): extract diff hunks and surviving mutants"
```

---

### Task 4: Mutation gate policy — line filter, allowlist, CLI, workflow

**Files:**
- Modify: `scripts/mutation_diff.py` (replace the trailing marker with the policy layer + `main`)
- Modify: `tests/unit/test_mutation_diff.py` (append policy tests)
- Create: `scripts/mutation_allowlist.toml`
- Create: `.github/workflows/mutation-diff.yml`
- Modify: `CONTRIBUTING.md` (already mentions the gate in Task 2; no change needed — verify wording matches this behavior)

**Interfaces:**
- Consumes: `Survivor`, `parse_hunk_ranges`, `changed_production_files`, `extract_survivors` from Task 3.
- Produces:
  - `filter_in_diff(survivors: list[Survivor], hunk_ranges: dict[str, set[int]]) -> tuple[list[Survivor], list[Survivor]]` — `(in_diff, outside)`.
  - `load_allowlist(path: Path) -> dict[tuple[str, str, int], str]` — key `(module_path, operator_name, occurrence)` → justification. Raises `AllowlistError` on an entry without a non-empty `justification`.
  - `map_modules_to_configs(changed: list[Path], root: Path) -> list[tuple[Path, Path]]` and `run_session(config: Path, root: Path) -> Path`.
  - CLI: `python3 scripts/mutation_diff.py --base <ref> [--allowlist <path>]`; exit 0/1/2 as above.

- [ ] **Step 1: Append the failing policy tests to `tests/unit/test_mutation_diff.py`**

```python
def test_filter_in_diff_splits_by_hunk_lines() -> None:
    inside = md.Survivor("packages/agents/src/monitor_agents/narrator/agent.py", "core/Number", 0, 11, "f")
    outside = md.Survivor("packages/agents/src/monitor_agents/narrator/agent.py", "core/String", 1, 90, "f")
    hunks = {"packages/agents/src/monitor_agents/narrator/agent.py": {11, 12}}
    in_diff, out = md.filter_in_diff([inside, outside], hunks)
    assert in_diff == [inside]
    assert out == [outside]


def test_out_of_diff_survivor_only_warns(tmp_path: Path) -> None:
    survivor = md.Survivor("packages/agents/src/x.py", "core/Number", 0, 99, "f")
    hunks = {"packages/agents/src/x.py": {10}}
    in_diff, outside = md.filter_in_diff([survivor], hunks)
    assert in_diff == []
    assert outside == [survivor]
    # With no in-diff survivors, the gate is green regardless of pre-existing debt.
    assert md.evaluate_gate(in_diff, outside, allowlist={}) == 0


def test_gate_fails_on_unallowlisted_in_diff_survivor() -> None:
    survivor = md.Survivor("packages/agents/src/x.py", "core/Number", 0, 10, "f")
    assert md.evaluate_gate([survivor], [], allowlist={}) == 1


def test_gate_allowlist_entry_passes() -> None:
    survivor = md.Survivor("packages/agents/src/x.py", "core/Number", 0, 10, "f")
    key = ("packages/agents/src/x.py", "core/Number", 0)
    assert md.evaluate_gate([survivor], [], allowlist={key: "equivalent mutant: flip has no effect"}) == 0


def test_load_allowlist_roundtrip(tmp_path: Path) -> None:
    allow = tmp_path / "allow.toml"
    allow.write_text(
        '[[survivors]]\n'
        'module_path = "packages/agents/src/x.py"\n'
        'operator_name = "core/Number"\n'
        'occurrence = 0\n'
        'justification = "equivalent mutant: constant is unused"\n'
    )
    loaded = md.load_allowlist(allow)
    assert loaded == {("packages/agents/src/x.py", "core/Number", 0): "equivalent mutant: constant is unused"}


def test_allowlist_entry_without_justification_is_error(tmp_path: Path) -> None:
    allow = tmp_path / "allow.toml"
    allow.write_text(
        '[[survivors]]\n'
        'module_path = "packages/agents/src/x.py"\n'
        'operator_name = "core/Number"\n'
        'occurrence = 0\n'
    )
    with pytest.raises(md.AllowlistError, match="justification"):
        md.load_allowlist(allow)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_mutation_diff.py -v`
Expected: the 6 new tests fail with `AttributeError` (`filter_in_diff`/`evaluate_gate`/`load_allowlist`/`AllowlistError` missing).

- [ ] **Step 3: Implement the policy layer in `scripts/mutation_diff.py`**

Replace the trailing marker comment with:

```python
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
```

- [ ] **Step 4: Run the full meta-test file**

Run: `uv run pytest tests/unit/test_mutation_diff.py -v`
Expected: 10 passed (4 from Task 3 + 6 new).

- [ ] **Step 5: Create `scripts/mutation_allowlist.toml`**

```toml
# Justified equivalent mutants (the ONLY exception route for the mutation gate).
#
# Each entry must carry a non-empty justification. The gate keys entries by
# (module_path, operator_name, occurrence) and fails closed on any entry that
# lacks a justification. Start empty; add entries only for proven equivalent
# mutants, in the same PR that documents why the mutant cannot be killed.
survivors = []
```

- [ ] **Step 6: Create `.github/workflows/mutation-diff.yml`**

```yaml
name: Mutation (diff)

on:
  pull_request:

concurrency:
  group: mutation-diff-${{ github.ref }}
  cancel-in-progress: true

jobs:
  mutation-diff:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"
      - run: uv sync --frozen || uv sync
      - name: Mutation gate (zero survivors on changed lines)
        run: uv run python scripts/mutation_diff.py --base "${{ github.event.pull_request.base.sha }}"
```

- [ ] **Step 7: Verify the empty-diff short circuit locally**

Run: `uv run python scripts/mutation_diff.py --base HEAD`
Expected: "mutation-diff: no production Python changes; nothing to do." and exit 0.

- [ ] **Step 8: End-to-end seed-module check (slow; run once, not part of the hermetic suite)**

This is the spec's stated verification: a seed module with an empty-assert test must
produce a surviving mutant and a non-zero exit. Create a throwaway workspace (do NOT
commit it):

```bash
mkdir -p /tmp/mutation_seed
cat > /tmp/mutation_seed/seed_mod.py <<'EOF'
def add(a: int, b: int) -> int:
    return a + b
EOF
cat > /tmp/mutation_seed/cosmic-ray-seed.toml <<'EOF'
[cosmic-ray]
module-path = "/tmp/mutation_seed/seed_mod.py"
python-version = ""
timeout = 30
excluded-modules = []
test-command = "python -m pytest /tmp/mutation_seed/test_seed.py -x -q --timeout=15 --tb=line -p no:cacheprovider --no-header"

[cosmic-ray.distributor]
name = "local"

[cosmic-ray.operators]
enabled = ["core/Number", "core/Variable", "core/Deletion"]
EOF
cat > /tmp/mutation_seed/test_seed.py <<'EOF'
import sys
sys.path.insert(0, "/tmp/mutation_seed")
import seed_mod  # noqa: F401
def test_no_real_assertion():
    assert True
EOF
```

Run Cosmic Ray (`uv run cosmic-ray init/exec /tmp/mutation_seed/cosmic-ray-seed.toml /tmp/mutation_seed/session.sqlite3`),
then read the survivors from the session DB with `extract_survivors` and check
`evaluate_gate` returns 1 for a survivor whose line is in the fake hunk set `{3}`
(`parse_hunk_ranges` on a synthetic diff covering line 3 of `seed_mod.py`). Then edit
`test_seed.py` to add a real assertion (`assert seed_mod.add(2, 3) == 5`), re-run
`cosmic-ray init/exec` on a fresh session, and confirm zero survivors.
Expected: empty-assert run → survivor(s) → gate exit 1; real-assert run → no survivors →
gate exit 0. This proves the whole chain (Cosmic Ray → WorkDB → line filter → gate).

- [ ] **Step 9: Commit**

```bash
git add scripts/mutation_diff.py tests/unit/test_mutation_diff.py scripts/mutation_allowlist.toml .github/workflows/mutation-diff.yml
git commit -m "feat(mutation): zero-survivor gate scoped to PR diff with justified allowlist"
```

---

### Task 5: Ruff anti-silent-except rules + real fixes for S110/S112

**Files:**
- Modify: `pyproject.toml` (`[tool.ruff]` + `[tool.ruff.lint]`)
- Modify: `packages/**/*.py` — every `S110` (`try-except-pass`) and `S112` (`try-except-continue`) violation (62 + 5 at plan time)

**Interfaces:**
- Consumes: nothing.
- Produces: ruff config with `BLE001`, `S110`, `S112`, `E722` active for `packages/**`; zero `S110`/`S112` violations. Tasks 6–8 own the `BLE001` debt.

- [ ] **Step 1: Add the ruff config to `pyproject.toml`**

Append at the end of the file:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
# Anti-reward-hacking: silent exception swallowing is the classic "fix" that
# turns a failing pipeline green by disabling it. E722 (bare except) is already
# on via the default E7 ruleset; listed here so the policy is explicit.
extend-select = ["BLE001", "S110", "S112", "E722"]
```

- [ ] **Step 2: Inventory the S110/S112 violations**

Run: `uv run ruff check packages --select S110,S112 --output-format=concise | tee /tmp/s110_s112.txt`
Expected: 67 lines (62 `S110`, 5 `S112`), each with file:line.

- [ ] **Step 3: Fix every S110/S112 violation with the decision taxonomy**

Hard rules for this sweep (S110/S112 are the reward-hacking pattern itself — `pass`/`continue` after a catch never survives):

1. **Silent swallow → visible outcome.** If the handler body is `pass`, replace with one of:
   - re-raise: bare `raise` (keeps the original traceback) when the caller should see the failure;
   - structured log + continue: `log.warning("...", exc_info=True)` when the surrounding loop must go on (module-level `structlog.get_logger()` in `packages/**`, per AGENTS.md);
   - explicit fallback value assignment when the code clearly intends one.
2. **`except: continue` →** log at `debug`/`warning` with the item name, then `continue`. The iteration survives; the failure stays visible.
3. **Never widen** the caught exception. If narrowing is also warranted, that is Task 6–8 territory — this task only removes the silent `pass`/`continue`.

Worked examples (before → after):

```python
# S110, silent data loss in a loop → log + continue
# before
for chunk in chunks:
    try:
        process(chunk)
    except Exception:
        pass

# after
for chunk in chunks:
    try:
        process(chunk)
    except Exception:
        log.warning("chunk processing failed", chunk_id=chunk.get("id"), exc_info=True)
        continue
```

```python
# S110, best-effort cleanup where failure must not propagate → log, never pass
# before
try:
    self._driver.close()
except Exception:
    pass

# after
try:
    self._driver.close()
except Exception:
    log.warning("driver close failed during cleanup", exc_info=True)
```

```python
# S112, skip-bad-record loop → visible skip
# before
for record in records:
    try:
        parse(record)
    except Exception:
        continue

# after
for record in records:
    try:
        parse(record)
    except Exception:
        log.debug("skipping unparsable record", record_id=record.get("id"), exc_info=True)
        continue
```

- [ ] **Step 4: Verify zero S110/S112 and green suite**

Run: `uv run ruff check packages --select S110,S112`
Expected: "All checks passed!"

Run: `uv run ruff check packages`
Expected: reports only `BLE001` findings (Task 6–8 will clear those).

Run: `uv run pytest packages tests -q`
Expected: all pass — if a test asserted on the old silent behavior, fix the test's expectation, not the log call.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml packages
git commit -m "fix(lint): eliminate silent except-pass/except-continue in packages"
```

---

### Task 6: BLE001 sweep — `packages/agents/src` (244 violations at plan time)

**Files:**
- Modify: `packages/agents/src/**/*.py` — every `BLE001` (blind `except`) violation

**Interfaces:**
- Consumes: the ruff config from Task 5.
- Produces: `uv run ruff check packages/agents --select BLE001` clean. No behavioral change.

- [ ] **Step 1: Inventory**

Run: `uv run ruff check packages/agents --select BLE001 --output-format=concise | tee /tmp/ble_agents.txt`
Expected: 244 lines (planning snapshot; use whatever count the inventory reports).

- [ ] **Step 2: Work through the files with the BLE001 decision taxonomy**

For each violation, pick exactly one bucket. **Behavior preservation is the hard constraint: a bucket change is only legal when the narrowed type provably covers every exception the old broad catch handled.**

1. **Narrow (preferred).** The block handles one failure mode (parse error, missing key, driver error) → catch the specific type(s): `except (json.JSONDecodeError, KeyError):`. Inspect the call inside the `try` and its contract before choosing the type.
2. **Translate.** The block converts failures into a domain error → `except Exception as exc: raise DomainError(...) from exc` and annotate `# noqa: BLE001  # reason: translates any downstream failure into <DomainError>` — the broad catch is the translation boundary and stays broad on purpose.
3. **Boundary, stays broad.** Watchdog loops, worker supervisors, middleware, plugin loaders, top-level command handlers: `except Exception:` remains, annotated `# noqa: BLE001  # reason: <boundary name> must survive any single failure` + structured log (`log.warning(..., exc_info=True)`).
4. **Delete the `try`.** If the `try` wraps one call whose only handler was `except Exception: pass` (already emptied in Task 5) and nothing else needs protection, remove the try/except entirely and let the error propagate.

Worked examples:

```python
# Bucket 1 — narrow to the real failure mode
# before
def parse_payload(raw: str) -> dict:
    try:
        return json.loads(raw)["payload"]
    except Exception:
        return {}

# after
def parse_payload(raw: str) -> dict:
    try:
        return json.loads(raw)["payload"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}
```

```python
# Bucket 2 — translation boundary stays broad, explicitly
# before
try:
    result = self._client.call_tool(name, args)
except Exception:
    raise ToolExecutionError(name)

# after
try:
    result = self._client.call_tool(name, args)
except Exception as exc:  # noqa: BLE001  # reason: any transport failure surfaces as ToolExecutionError
    raise ToolExecutionError(name) from exc
```

```python
# Bucket 3 — watchdog boundary stays broad, explicitly
# before
while self._running:
    try:
        self._tick()
    except Exception:
        pass  # (Task 5 already replaced the pass with a log line)

# after (after Task 5's log fix, this task only adds the justified annotation)
while self._running:
    try:
        self._tick()
    except Exception:  # noqa: BLE001  # reason: watchdog must survive any single tick failure
        log.warning("watchdog tick failed", exc_info=True)
```

Process: go file by file (the inventory is sorted — work top-down, `tee` progress). Record a per-bucket count in the final task report (like T-013's audit trail).

- [ ] **Step 3: Verify the package**

Run: `uv run ruff check packages/agents --select BLE001`
Expected: "All checks passed!"

Run: `uv run ruff check packages/agents`
Expected: clean.

Run: `uv run pytest packages/agents packages/data-layer tests -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add packages/agents
git commit -m "fix(lint): resolve BLE001 blind-except debt in packages/agents"
```

---

### Task 7: BLE001 sweep — `packages/ui/backend` (163 violations at plan time)

**Files:**
- Modify: `packages/ui/backend/**/*.py` — every `BLE001` violation (routers are the hot spot: `monitor_ui/routers/*`)

**Interfaces:**
- Consumes: ruff config (Task 5).
- Produces: `uv run ruff check packages/ui/backend --select BLE001` clean. No behavioral change.

- [ ] **Step 1: Inventory**

Run: `uv run ruff check packages/ui/backend --select BLE001 --output-format=concise | tee /tmp/ble_ui.txt`
Expected: 163 lines (planning snapshot).

- [ ] **Step 2: Sweep every violation with the BLE001 decision taxonomy**

For each violation, pick exactly one bucket. **Behavior preservation is the hard constraint: a bucket change is only legal when the narrowed type provably covers every exception the old broad catch handled.**

1. **Narrow (preferred).** The block handles one failure mode (parse error, missing key, driver error) → catch the specific type(s), e.g. `except (json.JSONDecodeError, KeyError):`. Inspect the call inside the `try` and its contract before choosing the type.
2. **Translate.** The block converts failures into a domain error or HTTP error response → `except Exception as exc: raise HTTPException(status_code=500, ...) from exc` (or the router's established error shape), annotated `# noqa: BLE001  # reason: handler maps unexpected errors to HTTP 500` — the broad catch is the translation boundary and stays broad on purpose.
3. **Boundary, stays broad.** Watchdog loops, worker supervisors, middleware, plugin loaders, WebSocket/chat loops: `except Exception:` remains, annotated `# noqa: BLE001  # reason: <boundary name> must survive any single failure` + structured log (`log.warning(..., exc_info=True)`).
4. **Delete the `try`.** If the `try` wraps one call whose only handler was `except Exception: pass` (already emptied in Task 5) and nothing else needs protection, remove the try/except entirely and let the error propagate.

- [ ] **Step 3: Verify the package**

Run: `uv run ruff check packages/ui/backend --select BLE001`
Expected: "All checks passed!"

Run: `uv run pytest packages/ui/backend tests -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add packages/ui/backend
git commit -m "fix(lint): resolve BLE001 blind-except debt in packages/ui/backend"
```

---

### Task 8: BLE001 sweep — `packages/data-layer/src`, `packages/cli/src`, test stragglers

**Files:**
- Modify: `packages/data-layer/src/**/*.py` (71 at plan time), `packages/cli/src/**/*.py` (57 at plan time), plus the 3 stray violations in `packages/*/tests` reported by the inventory

**Interfaces:**
- Consumes: ruff config (Task 5).
- Produces: `uv run ruff check packages --select BLE001` clean repo-wide — this task closes the BLE001 debt.

- [ ] **Step 1: Inventory the remainder**

Run: `uv run ruff check packages --select BLE001 --output-format=concise | tee /tmp/ble_rest.txt`
Expected: the remaining ~131 lines (whatever Tasks 6–7 did not cover).

- [ ] **Step 2: Sweep every violation with the BLE001 decision taxonomy**

For each violation, pick exactly one bucket. **Behavior preservation is the hard constraint: a bucket change is only legal when the narrowed type provably covers every exception the old broad catch handled.**

1. **Narrow (preferred).** The block handles one failure mode (parse error, missing key, driver error) → catch the specific type(s). DB client wrappers (`monitor_data/db/*`) catch driver errors specifically here: `neo4j.exceptions.*`, `pymongo.errors.*`, `qdrant_client.*` exceptions (the types are already named in the mypy overrides in `pyproject.toml`).
2. **Translate.** The block converts failures into a domain error → `except Exception as exc: raise StorageError(...) from exc` at the client boundary, annotated `# noqa: BLE001  # reason: any driver failure surfaces as StorageError` — the broad catch is the translation boundary and stays broad on purpose.
3. **Boundary, stays broad.** Watchdog loops, worker supervisors, middleware, plugin loaders, CLI command entry points (a crashed command must print an error, not traceback-dump): `except Exception:` remains, annotated `# noqa: BLE001  # reason: <boundary name> must survive any single failure` + structured log (`log.warning(..., exc_info=True)`).
4. **Delete the `try`.** If the `try` wraps one call whose only handler was `except Exception: pass` (already emptied in Task 5) and nothing else needs protection, remove the try/except entirely and let the error propagate.

- [ ] **Step 3: Repo-wide verification of the whole lint policy**

Run: `uv run ruff check packages`
Expected: "All checks passed!" (zero BLE001/S110/S112/E722 anywhere in `packages`).

Run: `uv run pytest packages tests -q && python scripts/check_layer_dependencies.py`
Expected: all pass; "All layer dependency checks passed."

- [ ] **Step 4: Commit**

```bash
git add packages
git commit -m "fix(lint): close BLE001 blind-except debt in data-layer, cli and tests"
```

---

### Task 9: DST topology counters + inline-snapshot (anti no-op bypass)

**Files:**
- Modify: `pyproject.toml` (dev dependency `inline-snapshot` in both `[project.optional-dependencies].dev` and `[dependency-groups].dev`)
- Modify: `tests/verification/test_monitor_wiring_dst.py` (sealed path — this task and the whole rollout PR need the `sealed-override` label)

**Interfaces:**
- Consumes: `StrictMCPWireBridge.call_audit_log` (list of `{"tool", "request", "response"}` appended on every successful wire call — `tests/verification/test_monitor_wiring_dst.py:124`) and the two harness scenarios `ingest_manual_end_to_end` / `execute_scene_turn_with_cold_checkpoint` (`IntegratedMonitorRuntimeHarness`, line 573).
- Produces (all inside the DST module): `MIN_TOOL_INVOCATIONS: Dict[str, int]`, `InvocationLedger` with `tool_counts() -> Dict[str, int]`, `trace() -> List[str]`, `assert_topology(minimums) -> None`, `assert_no_failed_responses() -> None`. Nothing outside the sealed suite consumes these.

- [ ] **Step 1: Add the dev dependency**

In `pyproject.toml`, append `"inline-snapshot>=0.20",` to **both** the `[project.optional-dependencies] dev` list and the `[dependency-groups] dev` list (they are kept in sync today). Then run:

Run: `uv sync`
Expected: lockfile updates, `inline-snapshot` installed.

- [ ] **Step 2: Write the failing topology assertions in the DST suite**

In `tests/verification/test_monitor_wiring_dst.py`, add after the `StrictMCPWireBridge` class (section 1) and before section 2:

```python
# --- Topología de ejecución (anti "no-op bypass") ---------------------------------
# Un "fix" que hace return temprano o traga errores deja los tests verdes pero el
# pipeline muerto. Estos contadores exigen que cada tool crítico se invoque al menos
# N veces en cada escenario y que ninguna respuesta haya fallado en silencio.

MIN_TOOL_INVOCATIONS: Dict[str, int] = {
    "ingest_store_document": 1,
    "qdrant_upsert_chunk": 1,
    "mongo_propose_change": 1,
    "canonkeeper_commit_proposal": 1,
    "context_query_world_at_tick": 1,
    "langgraph_save_checkpoint": 1,
    "langgraph_load_checkpoint": 1,
}


class InvocationLedger:
    """Cuenta invocaciones reales de tools MCP a partir del audit log del puente."""

    def __init__(self, bridge: StrictMCPWireBridge) -> None:
        self._bridge = bridge

    def tool_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in self._bridge.call_audit_log:
            counts[entry["tool"]] = counts.get(entry["tool"], 0) + 1
        return counts

    def trace(self) -> List[str]:
        return [entry["tool"] for entry in self._bridge.call_audit_log]

    def assert_topology(self, minimums: Dict[str, int]) -> None:
        counts = self.tool_counts()
        missing = {
            tool: {"invoked": counts.get(tool, 0), "required": minimum}
            for tool, minimum in minimums.items()
            if counts.get(tool, 0) < minimum
        }
        assert not missing, (
            "Topología de ejecución incompleta (posible no-op bypass): "
            f"tools por debajo del mínimo {missing}"
        )

    def assert_no_failed_responses(self) -> None:
        failed = [
            entry["tool"]
            for entry in self._bridge.call_audit_log
            if isinstance(entry["response"], dict) and entry["response"].get("ok") is False
        ]
        assert not failed, (
            f"Respuestas fallidas tragadas durante el escenario de aceptación: {failed}"
        )
```

Then extend the acceptance scenario `test_02_full_pipeline_ingest_to_canon_to_multiturn_timeline_travel`
with these final lines (after the last `assertEqual`):

```python
        ledger = InvocationLedger(harness.mcp)
        ledger.assert_topology(MIN_TOOL_INVOCATIONS)
        ledger.assert_no_failed_responses()
        assert ledger.trace() == snapshot(
            [
                # Created on the first run; reviewed and committed as-is because the
                # scenario is fully deterministic (seed=7, fixed call sequence).
            ]
        )
```

And extend `test_04_deterministic_multi_seed_campaign_simulation` inside the per-seed loop
(after the final `assertEqual`) with:

```python
                ledger = InvocationLedger(harness.mcp)
                ledger.assert_topology(MIN_TOOL_INVOCATIONS)
                ledger.assert_no_failed_responses()
```

(Note: test_04 gets **no** snapshot — its per-seed traces vary with the seeded RNG;
only the per-seed topology invariants are asserted there.)

Add the import to the module's import block:

```python
from inline_snapshot import snapshot
```

- [ ] **Step 3: Run the DST suite to create the snapshot and verify the counters**

Run: `uv run pytest tests/verification/test_monitor_wiring_dst.py -v`
Expected: all tests pass; inline-snapshot reports the `snapshot()` in test_02 as **created**.
Open the diff and check the created trace against the expected sequence
(`ingest_store_document`, `qdrant_upsert_chunk`, `mongo_propose_change`, `canonkeeper_commit_proposal`
per extracted entity, `context_query_world_at_tick`, then per turn `langgraph_load_checkpoint`,
`mongo_propose_change`, `canonkeeper_commit_proposal`, `langgraph_save_checkpoint`, plus the
three tick queries). If the trace does not match, the counter wiring is wrong — fix the
wiring, not the snapshot.

Run again: `uv run pytest tests/verification/test_monitor_wiring_dst.py -v`
Expected: pass with no snapshot modifications (idempotent).

- [ ] **Step 4: Negative check — the counters must actually bite**

Temporarily edit `MIN_TOOL_INVOCATIONS` in the module: set `"context_query_world_at_tick": 99`.

Run: `uv run pytest tests/verification/test_monitor_wiring_dst.py -k test_02 -q`
Expected: FAIL with "Topología de ejecución incompleta". Revert the value to `1` and
re-run to confirm green. (Do not commit the temporary edit.)

- [ ] **Step 5: Full suite + lint**

Run: `uv run pytest packages tests -q && uv run ruff check packages`
Expected: all pass.

- [ ] **Step 6: Commit (needs `sealed-override` on the rollout PR — see Task 10)**

```bash
git add pyproject.toml uv.lock tests/verification/test_monitor_wiring_dst.py
git commit -m "feat(dst): invocation topology counters and inline-snapshot trace"
```

---

### Task 10: Final verification + CI smoke

**Files:**
- Modify: none (verification + one documented manual step)

**Interfaces:**
- Consumes: everything from Tasks 1–9.
- Produces: the Definition of Done evidence; the smoke result recorded in the PR body.

- [ ] **Step 1: Full local gate**

Run each command; all must pass:

```bash
uv run ruff check packages
uv run python scripts/check_layer_dependencies.py
uv run pytest packages tests -q
uv run pytest tests/unit/test_sealed_suite_guard.py tests/unit/test_mutation_diff.py -v
python scripts/sealed_suite_guard.py --base origin/main --allow-sealed   # rollout PR edits a sealed path
```

Expected: ruff clean, layer check "All layer dependency checks passed.", pytest green
(including the 17 meta-tests across the two new files), guard exit 0 with `[OVERRIDE]`.

- [ ] **Step 2: Open the rollout PR with `sealed-override`**

Open the PR. It touches `tests/verification/**` (Task 9), so:
1. Ask the maintainer to apply the `sealed-override` label before the `sealed-suite-guard`
   job runs (or re-run it after labeling).
2. PR body records: the seal-rule evidence (guard meta-tests), the mutation-gate evidence
   (meta-tests + empty-diff short circuit), the ruff sweep counts per bucket (Tasks 6–8),
   and the DST negative check from Task 9 Step 4.

- [ ] **Step 3: CI smoke (documented, one throwaway PR after merge)**

After the rollout PR merges, verify the enforcement end to end:
1. Branch off `main`, edit one comment in `tests/property/test_scene_properties.py`, open a
   PR **without** labels → expect `sealed-suite-guard` **red** with the actionable message.
2. Apply `sealed-override` to that PR → expect the job **green** (and CODEOWNERS review
   requested).
3. Close the throwaway PR without merging. Record both outcomes in the rollout PR body as
   the smoke evidence (DoD items 1–2).

- [ ] **Step 4: Definition of Done checklist (fill in the PR body)**

| # | DoD item | Evidence |
|---|----------|----------|
| 1 | Unlabeled sealed-path PR is red with actionable message | Smoke step 3.1 |
| 2 | Same PR with label is green; CODEOWNERS demands review | Smoke step 3.2 |
| 3 | Surviving mutant on a changed line is red; allowlist is the only route | `tests/unit/test_mutation_diff.py` gate tests |
| 4 | New `except Exception: pass` in `packages/**` fails ruff | S110 active + zero violations (Task 5) |
| 5 | DST run with an uninvoked tool/node fails the suite | Task 9 Step 4 negative check |
| 6 | `pytest packages tests -q`, `ruff check packages`, `check_layer_dependencies.py` green | Task 10 Step 1 |
| 7 | `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md` document the rules | Task 2 Steps 4–6 |

- [ ] **Step 5: Final commit (if the DoD table is committed to the PR description only, no commit needed)**

No code changes in this task. If the team wants the smoke results in-repo, append them to
`docs/testing/INDEX.md` and commit as `docs(testing): record sealed-suite smoke evidence`.
