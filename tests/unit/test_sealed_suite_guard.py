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
