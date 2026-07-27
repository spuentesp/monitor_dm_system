#!/usr/bin/env python3
"""Unified entry point for the MONITOR live-narration / GM-assistant replay suite.

Runs each replay script in sequence against the running backend and writes a
combined markdown report. Designed to be the single command to run "all
the things that exercise the live app through the chat / forge / GM API
surfaces." Each suite runs independently — a failure in one does not
abort the others.

Suites (each is a script under ``scripts/``):

  1. ``forge_replay``            — every /forge* + bootstrap surface
  2. ``live_copilot_observe``    — CF-2..CF-7 GM co-pilot surfaces
  3. ``long_form_narration``     — 22-turn char creation → combat → boss → epilogue
  4. ``subsystem_replay``        — 14-turn NPC / lore / faction / negotiation
  5. ``character_creation_replay`` — 10-step full char-creation arc
  6. ``live_session_observe``    — heuristic arc observation (llm_actor mode)

The SceneLoop-only full-loop harness lives at ``scripts/e2e_full_loop.py``
(see ``docs/testing/HARNESS_FULL_LOOP.md``); it is not part of the
full-stack replay suite because it exercises the loop in-process.

Usage::

    set -a; source .env; set +a
    export MONITOR_PLAYTEST_MODEL=ollama/qwen2.5:latest   # any local/cloud LLM
    python scripts/run_e2e_replays.py                     # full suite
    python scripts/run_e2e_replays.py --only forge,long   # subset
    python scripts/run_e2e_replays.py --api-url http://localhost:8001/api
    python scripts/run_e2e_replays.py --output-dir tests/e2e/logs/replays

Each suite writes its own log; the entry script writes ``replay_run.md``
summarizing the pass/fail status of every suite.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
DEFAULT_OUTPUT = REPO_ROOT / "tests" / "e2e" / "logs" / "replays"
PLAYER_MODEL = os.environ.get("MONITOR_PLAYTEST_MODEL", "ollama/qwen2.5:latest")
DEFAULT_API_URL = os.environ.get("MONITOR_API_URL", "http://localhost:8000/api")


@dataclass
class Suite:
    name: str
    description: str
    cmd: list[str]
    timeout_s: int
    expect: str = "log"  # log | md | both


SUITES: list[Suite] = [
    Suite(
        name="forge",
        description="Forge + bootstrap surface coverage (10 endpoints)",
        cmd=[
            sys.executable, str(ROOT / "forge_replay.py"),
            "--api-url", "{api_url}",
            "--log-file", "{log_dir}/forge_run.md",
        ],
        timeout_s=180,
    ),
    Suite(
        name="copilot",
        description="GM co-pilot (CF-2..CF-7): recap, hooks, contradictions, session-prep, handout, threads",
        cmd=[
            sys.executable, str(ROOT / "live_copilot_observe.py"),
            "--api-url", "{api_url}",
            "--no-judge",
            "--output-dir", "{log_dir}",
        ],
        timeout_s=300,
    ),
    Suite(
        name="long_form",
        description="22-turn non-deterministic narration: char creation → combat → boss → epilogue",
        cmd=[
            sys.executable, str(ROOT / "long_form_narration.py"),
            "--api-url", "{api_url}",
            "--player-model", PLAYER_MODEL,
            "--turns", "22",
            "--log-file", "{log_dir}/long_form_22turn.md",
        ],
        timeout_s=2400,
    ),
    Suite(
        name="subsystem",
        description="14-turn subsystem coverage: relationship, lore, faction, negotiation, npc_voice",
        cmd=[
            sys.executable, str(ROOT / "subsystem_replay.py"),
            "--api-url", "{api_url}",
            "--player-model", PLAYER_MODEL,
            "--turns", "14",
            "--log-file", "{log_dir}/subsystem_14turn.md",
        ],
        timeout_s=1800,
    ),
    Suite(
        name="char_creation",
        description="10-step character-creation arc (species/class/stats/equipment/lock-in)",
        cmd=[
            sys.executable, str(ROOT / "character_creation_replay.py"),
            "--api-url", "{api_url}",
            "--player-model", PLAYER_MODEL,
            "--turns", "10",
            "--log-file", "{log_dir}/char_creation_10step.md",
        ],
        timeout_s=1500,
    ),
    Suite(
        name="session_observe",
        description="Heuristic llm_actor pass (live_session_observe): arc + judge-free latencies",
        cmd=[
            sys.executable, str(ROOT / "live_session_observe.py"),
            "--api-url", "{api_url}",
            "--mode", "llm_actor",
            "--turns", "8",
            "--no-judge",
            "--output-dir", "{log_dir}",
        ],
        timeout_s=1800,
    ),
]


def _format(cmd: list[str], api_url: str, log_dir: Path) -> list[str]:
    out: list[str] = []
    for c in cmd:
        out.append(c.format(api_url=api_url, log_dir=str(log_dir)))
    return out


def _run_one(suite: Suite, api_url: str, log_dir: Path) -> dict[str, Any]:
    cmd = _format(suite.cmd, api_url, log_dir)
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("MONITOR_PLAYTEST_MODEL", PLAYER_MODEL)
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=suite.timeout_s,
            check=False,
        )
        duration = round(time.time() - t0, 1)
        return {
            "suite": suite.name,
            "description": suite.description,
            "cmd": cmd,
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "duration_s": duration,
            "stdout_tail": result.stdout[-800:] if result.stdout else "",
            "stderr_tail": result.stderr[-800:] if result.stderr else "",
            "timeout_s": suite.timeout_s,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "suite": suite.name,
            "description": suite.description,
            "cmd": cmd,
            "ok": False,
            "exit_code": -1,
            "duration_s": round(time.time() - t0, 1),
            "stdout_tail": (exc.stdout or "")[-400:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-400:] if isinstance(exc.stderr, str) else "",
            "timeout_s": suite.timeout_s,
            "timed_out": True,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--only", default="",
                    help="Comma-separated subset of: forge,copilot,long_form,subsystem,char_creation,session_observe,narration_dis")
    ap.add_argument("--skip", default="",
                    help="Comma-separated subset to skip (applied after --only)")
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--report", default=None,
                    help="Path for the combined markdown report")
    args = ap.parse_args()

    log_dir = Path(args.output_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = Path(args.report) if args.report else log_dir / f"replay_run_{stamp}.md"
    json_path = report_path.with_suffix(".json")

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    selected = [
        s for s in SUITES
        if (not only or s.name in only) and s.name not in skip
    ]

    if not selected:
        print("No suites selected. Use --only or --skip to filter.")
        return 2

    print(f"Running {len(selected)} suite(s) against {args.api_url}")
    print(f"Logs → {log_dir}")
    print()

    results: list[dict[str, Any]] = []
    for suite in selected:
        print(f"=== {suite.name}: {suite.description} ===")
        r = _run_one(suite, args.api_url, log_dir)
        results.append(r)
        ok = "OK  " if r["ok"] else "FAIL"
        if r.get("timed_out"):
            ok = "TIMEOUT"
        print(f"  [{ok}] {r['duration_s']}s  exit={r['exit_code']}")
        if not r["ok"]:
            tail = (r["stderr_tail"] or r["stdout_tail"] or "").strip()
            for line in tail.splitlines()[-6:]:
                print(f"    {line}")
        print()

    # Combined report ----------------------------------------------------
    lines = [
        "# MONITOR E2E Replay Suite",
        "",
        f"- **API**: `{args.api_url}`",
        f"- **Player model**: `{PLAYER_MODEL}`",
        f"- **Generated at**: `{datetime.now(timezone.utc).isoformat()}`",
        f"- **Total suites**: `{len(selected)}`",
        f"- **Passed**: `{sum(1 for r in results if r['ok'])}`",
        f"- **Failed**: `{sum(1 for r in results if not r['ok'])}`",
        "",
        "## Suite results",
        "",
        "| Suite | OK | Duration | Exit | Description |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        ok = "✅" if r["ok"] else ("⏱️" if r.get("timed_out") else "❌")
        lines.append(
            f"| `{r['suite']}` | {ok} | {r['duration_s']}s | {r['exit_code']} | {r['description']} |"
        )
    failures = [r for r in results if not r["ok"]]
    if failures:
        lines += ["", "## Failures", ""]
        for r in failures:
            lines.append(f"### `{r['suite']}`")
            lines.append("")
            lines.append("```")
            tail = (r["stderr_tail"] or r["stdout_tail"] or "").strip()
            lines.append(tail[-1500:] if tail else "(no output captured)")
            lines.append("```")
            lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"Report:  {report_path}")
    print(f"JSON:    {json_path}")
    print()
    for r in results:
        ok = "OK  " if r["ok"] else "FAIL"
        print(f"  [{ok}] {r['suite']:<16s} {r['duration_s']:7.1f}s")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
