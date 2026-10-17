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


def _init_scratch_repo(tmp_path: Path) -> Path:
    import subprocess as sp

    repo = tmp_path / "repo"
    (repo / "tests" / "property").mkdir(parents=True)
    (repo / "tests" / "unit").mkdir(parents=True)
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@t"],
        ["git", "config", "user.name", "t"],
    ):
        sp.run(cmd, cwd=repo, check=True, capture_output=True)
    return repo


def test_staged_rename_out_of_sealed_is_flagged(tmp_path: Path) -> None:
    """A pure rename out of a sealed suite must NOT slip past the guard (git hides
    the source path unless rename detection is disabled)."""
    import subprocess as sp

    repo = _init_scratch_repo(tmp_path)
    src = repo / "tests" / "property" / "test_sealed.py"
    src.write_text("assert True\n")
    sp.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "mv", "tests/property/test_sealed.py", "tests/unit/test_sealed.py"], cwd=repo, check=True, capture_output=True)

    proc = sp.run(
        [sys.executable, str(SCRIPT_PATH), "--staged"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, f"rename out of sealed suite must fail the guard: {proc.stdout}{proc.stderr}"
    assert "tests/property/test_sealed.py" in proc.stdout


def test_staged_rename_detection_sees_both_sides(tmp_path: Path) -> None:
    """changed_files/staged_files must use --no-renames so a pure rename lists
    the sealed source path too (guard input contract)."""
    import subprocess as sp

    repo = _init_scratch_repo(tmp_path)
    (repo / "tests" / "property" / "test_sealed.py").write_text("assert True\n")
    sp.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "mv", "tests/property/test_sealed.py", "tests/unit/test_sealed.py"], cwd=repo, check=True, capture_output=True)

    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("guard_under_test", SCRIPT_PATH)
    guard_mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(guard_mod)
    import os
    old_cwd = os.getcwd()
    os.chdir(repo)
    try:
        staged = guard_mod.staged_files()
    finally:
        os.chdir(old_cwd)
    assert "tests/property/test_sealed.py" in staged
    assert "tests/unit/test_sealed.py" in staged


def test_codeowners_owns_the_enforcement_surface() -> None:
    """C1 pin: the guard, gate, allowlist, workflows and meta-tests must be
    CODEOWNERS-protected — a PR must not rewrite the checks that police it."""
    owners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    for required in (
        "tests/verification/**",
        "tests/property/**",
        "scripts/sealed_suite_guard.py",
        "scripts/mutation_diff.py",
        "scripts/mutation_allowlist.toml",
        "tests/unit/test_sealed_suite_guard.py",
        "tests/unit/test_mutation_diff.py",
        ".github/workflows/**",
        ".github/CODEOWNERS",
    ):
        assert required in owners, f"{required} must be CODEOWNERS-protected"
