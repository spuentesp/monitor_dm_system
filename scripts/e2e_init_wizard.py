#!/usr/bin/env python3
"""
End-to-end live verification for ``monitor init`` + ``monitor doctor``.

This is the cross-phase gate for the "make MONITOR downloadable" body of work.
Run it against a fresh checkout with Docker available; it will:

  1. Wipe all infra state (`docker compose down -v`).
  2. Bring up infra (`make infra-up`).
  3. Run the wizard non-interactively (`monitor init --provider ollama --yes`).
  4. Run the doctor (`monitor doctor --json`) and assert ``overall_status == healthy``.
  5. Run the full e2e test suite (`make test-e2e`).

Usage::

    # Default — Ollama path. Requires `ollama serve` running on the host.
    python scripts/e2e_init_wizard.py

    # BYOK path with Anthropic (skips the model pull step).
    ANTHROPIC_API_KEY=sk-ant-... python scripts/e2e_init_wizard.py --provider anthropic

Environment gates:
    RUN_E2E=1 is required — without it the script prints a friendly nudge and exits 0.
    Run from the repo root so the relative paths (./scripts/, ./infra/) resolve.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], *, cwd: Path = ROOT, timeout: int = 1800) -> subprocess.CompletedProcess:
    """Run a subprocess, streaming stdout to the terminal; raise on nonzero exit."""
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=True, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        default="ollama",
        choices=["ollama", "anthropic", "openai", "github_models", "google_ai_studio", "minimax", "zai"],
        help="Provider to seed via the wizard (default: ollama).",
    )
    parser.add_argument(
        "--skip-test-suite",
        action="store_true",
        help="Skip `make test-e2e` at the end (faster iteration during wizard development).",
    )
    args = parser.parse_args()

    if os.getenv("RUN_E2E") != "1":
        print(
            "This script starts Docker containers and runs the full e2e suite.\n"
            "Re-run with RUN_E2E=1 to enable it. Example:\n"
            "    RUN_E2E=1 python scripts/e2e_init_wizard.py"
        )
        return 0

    # 1. Wipe infra state
    _run(["docker", "compose", "-f", "infra/docker-compose.yml", "down", "-v"])

    # 2. Bring infra up
    _run(["make", "infra-up"], timeout=600)

    # 3. Run the wizard non-interactively
    env = os.environ.copy()
    env.setdefault("MONITOR_OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:latest")
    env.setdefault("OLLAMA_MODEL", "qwen2.5:latest")
    _run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "monitor_cli.main",
            "init",
            "--provider",
            args.provider,
            "--yes",
        ],
        timeout=1200,
    )

    # 4. Doctor must report healthy
    doctor = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "monitor_cli.main",
            "doctor",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=ROOT,
    )
    if doctor.returncode != 0:
        print("monitor doctor exited nonzero:", doctor.returncode)
        print(doctor.stdout)
        print(doctor.stderr, file=sys.stderr)
        return doctor.returncode

    try:
        report = json.loads(doctor.stdout)
    except json.JSONDecodeError as exc:
        print(f"monitor doctor --json output was not JSON: {exc}")
        print(doctor.stdout)
        return 1

    overall = report.get("overall_status")
    if overall != "healthy":
        print(f"\n✘ monitor doctor reports '{overall}', expected 'healthy'")
        print(json.dumps(report, indent=2, default=str))
        return 1
    print(f"\n✔ monitor doctor overall_status = {overall}")

    # 5. Full e2e suite
    if not args.skip_test_suite:
        _run(["make", "test-e2e"], timeout=3600)

    print("\n✅ e2e_init_wizard: all steps green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
