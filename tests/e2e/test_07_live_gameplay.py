"""Live end-to-end gameplay test against the running MONITOR backend.

This test does not use mocks. It drives the actual HTTP API and verifies that a
short autonomous-GM session can complete without fallback narration.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import requests


@pytest.mark.e2e
def test_live_autonomous_gm_session_generates_a_gameplay_log(tmp_path: Path) -> None:
    """Run a real playable session through the live backend and save the transcript."""
    api_url = os.environ.get("MONITOR_API_URL", "http://localhost:8001/api")

    try:
        health = requests.get(f"{api_url}/health", timeout=5)
        health.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"live backend not available: {exc}")

    repo_root = Path(__file__).resolve().parents[2]
    log_file = tmp_path / "live_gameplay_log.md"
    script_path = repo_root / "scripts" / "live_gameplay_smoke.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--api-url",
            api_url,
            "--player-mode",
            "scripted",
            "--turns",
            "6",
            "--log-file",
            str(log_file),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert log_file.exists(), "expected gameplay log to be created"

    log_text = log_file.read_text(encoding="utf-8")
    assert "# Live Gameplay Log" in log_text
    assert "## Opening" in log_text
    assert "## Turn 1" in log_text
    assert "**Player mode:** `scripted`" in log_text
    assert "**Fallback detected:** `0`" in log_text
    assert "Kael Draven" in log_text
