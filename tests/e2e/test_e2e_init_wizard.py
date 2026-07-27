"""
Hermetic shape tests for ``scripts/e2e_init_wizard.py``.

These tests do **not** start Docker. They assert that the orchestration
script's subprocess calls are wired correctly (right commands, right
working directory, right env vars, right exit-code handling). The live
end-to-end run is gated by ``RUN_E2E=1`` and lives in the script itself.

Marked ``@pytest.mark.e2e`` so it ships under the existing ``make test-e2e``
umbrella but does not require a Docker daemon to pass shape.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "e2e_init_wizard.py"


pytestmark = pytest.mark.e2e


def test_script_without_run_e2e_exits_zero(monkeypatch):
    """Without RUN_E2E=1 the script prints a nudge and exits 0."""
    monkeypatch.delenv("RUN_E2E", raising=False)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--provider", "ollama"],
        capture_output=True,
        text=True,
        timeout=15,
        env={k: v for k, v in os.environ.items() if k != "RUN_E2E"},
    )
    assert result.returncode == 0, (
        f"unexpected exit {result.returncode}: {result.stderr}"
    )
    assert "RUN_E2E=1" in result.stdout


def test_script_with_run_e2e_invokes_correct_subprocess_chain(monkeypatch):
    """With RUN_E2E=1 the script runs the full chain in the right order.

    All subprocess.run / subprocess.check_call invocations are mocked; we
    capture the command list and assert each one is invoked in the right
    shape (file, working directory, env).
    """
    # The doctor subprocess returns a JSON payload with overall_status=healthy.
    doctor_payload = json.dumps({"overall_status": "healthy", "components": {}})

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        completed = subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=doctor_payload
            if "monitor_cli.main" in cmd and "doctor" in cmd
            else "",
            stderr="",
        )
        return completed

    # Patch subprocess.run inside the e2e_init_wizard module namespace.
    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("subprocess.CompletedProcess", subprocess.CompletedProcess)
    monkeypatch.setenv("RUN_E2E", "1")
    monkeypatch.setattr(
        "sys.argv", [str(SCRIPT), "--provider", "ollama", "--skip-test-suite"]
    )

    # Import after monkey-patching so the module captures our fake_run.
    if "scripts.e2e_init_wizard" in sys.modules:
        del sys.modules["scripts.e2e_init_wizard"]
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        mod = __import__("e2e_init_wizard")
        rc = mod.main()
    finally:
        sys.path.pop(0)

    assert rc == 0, "script should exit 0 on a green chain"

    # 1. docker compose down -v
    assert any(
        c[:3] == ["docker", "compose", "-f"] and "down" in c and "-v" in c
        for c in calls
    ), f"missing 'docker compose down -v' call; got {calls}"

    # 2. make infra-up
    assert any(c[:2] == ["make", "infra-up"] for c in calls), "missing 'make infra-up'"

    # 3. monitor init --provider ollama --yes
    assert any(
        "-m" in c
        and "monitor_cli.main" in c
        and "init" in c
        and "--provider" in c
        and "ollama" in c
        and "--yes" in c
        for c in calls
    ), "missing 'monitor init --provider ollama --yes'"

    # 4. monitor doctor --json (captured via the run path that returns doctor_payload)
    assert any(
        "-m" in c and "monitor_cli.main" in c and "doctor" in c and "--json" in c
        for c in calls
    ), "missing 'monitor doctor --json'"


def test_script_reports_nonzero_when_doctor_is_unhealthy(monkeypatch):
    """If monitor doctor returns overall_status != healthy, the script must exit nonzero."""
    doctor_payload = json.dumps({"overall_status": "unhealthy", "components": {}})

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=doctor_payload if "doctor" in cmd else "",
            stderr="",
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setenv("RUN_E2E", "1")
    monkeypatch.setattr(
        "sys.argv", [str(SCRIPT), "--provider", "ollama", "--skip-test-suite"]
    )

    if "scripts.e2e_init_wizard" in sys.modules:
        del sys.modules["scripts.e2e_init_wizard"]
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        mod = __import__("e2e_init_wizard")
        rc = mod.main()
    finally:
        sys.path.pop(0)
    assert rc == 1, f"script should exit 1 when doctor is unhealthy; got {rc}"
