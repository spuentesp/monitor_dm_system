#!/usr/bin/env python3
"""Run the MONITOR observability suite — these three specific heuristic tests.

Orchestrates the controlled real-LLM observers, one per product mode, against a
live dockerized stack:

  1. ``live_session_observe.py``   — Autonomous GM (play loop, mechanical layer)
  2. ``live_ingestion_observe.py`` — World Architect (ingestion recall/quality)
  3. ``live_copilot_observe.py``   — GM Assistant (hooks/contradictions/handouts)

Each observer is run as a subprocess so one failure can't abort the others. The
runner checks stack health once, runs the selected observers, then collects the
newest JSON report each produced and writes a combined index + headline summary
under ``docs/testing/``. These are heuristic observers (no pass/fail asserts);
the exit code only reflects whether each observer *ran* (rc == 0), not whether
the GM "was good".

Usage:
    docker compose --env-file .env -f infra/docker-compose.yml up -d
    uv run python scripts/run_observability.py --api-url http://localhost:8001/api
    uv run python scripts/run_observability.py --only session,copilot --no-judge
    uv run python scripts/run_observability.py --player-model gemini/gemini-2.5-flash-lite

Requires the dockerized stack up + an LLM provider. The judge needs
GOOGLE_API_KEY (or a matching key for --judge-model); skip it with --no-judge.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

SCRIPTS = Path(__file__).resolve().parent
DEFAULT_API_URL = "http://localhost:8001/api"
DEFAULT_OUTPUT_DIR = Path("docs/testing")

# name -> (script filename, JSON prefix it writes, extra-arg builder)
OBSERVERS: dict[str, tuple[str, str]] = {
    "session": ("live_session_observe.py", "observe_summary_"),
    "ingestion": ("live_ingestion_observe.py", "observe_ingest_"),
    "copilot": ("live_copilot_observe.py", "observe_copilot_"),
}


def _extra_args(name: str, args: argparse.Namespace) -> list[str]:
    extra: list[str] = ["--api-url", args.api_url, "--output-dir", args.output_dir]
    if args.no_judge:
        extra.append("--no-judge")
    else:
        extra += ["--judge-model", args.judge_model]
    if name == "session":
        extra += ["--mode", args.mode, "--turns", str(args.turns)]
        if args.player_model:
            extra += ["--player-model", args.player_model]
    if name == "ingestion":
        extra += ["--timeout", str(args.ingest_timeout)]
    return extra


def _newest_json(out_dir: Path, prefix: str, after: float) -> Path | None:
    candidates = [
        p for p in out_dir.glob(f"{prefix}*.json") if p.stat().st_mtime >= after - 1
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _headline(name: str, data: Any) -> list[str]:
    """One or two lines of the most decision-relevant numbers per observer."""
    lines: list[str] = []
    try:
        if name == "session" and isinstance(data, list):
            for p in data:
                j = p.get("judge", {}).get("scores", {})
                avg = round(sum(j.values()) / len(j), 2) if j else "—"
                lines.append(
                    f"  - **{p.get('mode')}**: {p.get('turn_count')} turns · "
                    f"latency median {p.get('latency_median_s')}s · "
                    f"mechanical_engaged={p.get('mechanical_engaged')} · "
                    f"xp={p.get('total_xp_gained')} · fallbacks={p.get('fallback_count')} · "
                    f"judge {avg}"
                )
        elif name == "ingestion" and isinstance(data, dict):
            s = data.get("scores", {})
            j = data.get("judge", {}).get("scores", {})
            avg = round(sum(j.values()) / len(j), 2) if j else "—"
            lines.append(
                f"  - recall {s.get('recall_pct')}% ({s.get('recall_hits')}/"
                f"{s.get('planted_entities')}) · noise {s.get('precision_noise_count')} · "
                f"lore {s.get('lore_facts')} · axiom_found {s.get('planted_axiom_found')} · "
                f"job {data.get('job_status')} ({data.get('wall_s')}s) · judge {avg}"
            )
        elif name == "copilot" and isinstance(data, dict):
            sf = data.get("surfaces", {})
            j = data.get("judge", {}).get("scores", {})
            avg = round(sum(j.values()) / len(j), 2) if j else "—"
            h = sf.get("hooks", {})
            lines.append(
                f"  - hooks {h.get('count')} ({h.get('grounded_pct')}% grounded) · "
                f"contradictions {sf.get('contradictions', {}).get('count')} · "
                f"handout {sf.get('handout', {}).get('chars')} chars · "
                f"recap {sf.get('recap', {}).get('chars')} chars · judge {avg}"
            )
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  - (could not summarize: {exc})")
    return lines or ["  - (no JSON report found)"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    ap.add_argument(
        "--only",
        default="session,ingestion,copilot",
        help="Comma list of observers to run (session,ingestion,copilot)",
    )
    ap.add_argument("--no-judge", action="store_true", help="Skip the LLM judge in every observer")
    ap.add_argument("--judge-model", default="gemini/gemini-2.5-flash")
    ap.add_argument("--player-model", default=None, help="LLM-actor player model (session observer)")
    ap.add_argument("--mode", default="both", choices=["scripted", "llm_actor", "both"])
    ap.add_argument("--turns", type=int, default=8)
    ap.add_argument("--ingest-timeout", type=int, default=300)
    args = ap.parse_args()

    selected = [s.strip() for s in args.only.split(",") if s.strip() in OBSERVERS]
    if not selected:
        print(f"no valid observers in --only={args.only!r}", file=sys.stderr)
        return 2

    # Single health check up front so we fail fast with a clear message.
    try:
        h = requests.get(f"{args.api_url}/health", timeout=5).json()
        if h.get("status") != "ok":
            print(f"backend unhealthy: {h}", file=sys.stderr)
            return 1
    except Exception as exc:  # noqa: BLE001
        print(
            f"cannot reach backend at {args.api_url}: {exc}\n"
            "Start the stack: docker compose --env-file .env -f infra/docker-compose.yml up -d",
            file=sys.stderr,
        )
        return 1

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_start = time.time()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results: list[dict[str, Any]] = []

    for name in selected:
        script, prefix = OBSERVERS[name]
        cmd = [sys.executable, str(SCRIPTS / script), *_extra_args(name, args)]
        print(f"\n{'=' * 60}\n▶ {name}: {' '.join(cmd[2:])}\n{'=' * 60}")
        t0 = time.time()
        proc = subprocess.run(cmd, text=True)  # stream output live
        dur = round(time.time() - t0, 1)
        report = _newest_json(out_dir, prefix, t0)
        data = None
        if report is not None:
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                data = None
        results.append(
            {
                "observer": name,
                "rc": proc.returncode,
                "duration_s": dur,
                "report": str(report) if report else None,
                "data": data,
            }
        )

    # Combined index + headline summary.
    md = [
        f"# Observability Run — {stamp}",
        "",
        f"- **API**: `{args.api_url}`",
        f"- **Observers**: {', '.join(selected)}",
        f"- **Judge**: {'disabled' if args.no_judge else args.judge_model}",
        f"- **Total wall**: {round(time.time() - run_start, 1)}s",
        "",
        "## Headlines",
        "",
    ]
    all_ok = True
    for r in results:
        status = "✅ ran" if r["rc"] == 0 else f"❌ rc={r['rc']}"
        all_ok = all_ok and r["rc"] == 0
        link = f" — [report]({Path(r['report']).name})" if r["report"] else ""
        md.append(f"### {r['observer']} ({status}, {r['duration_s']}s){link}")
        md += _headline(r["observer"], r["data"])
        md.append("")

    combined = out_dir / f"observability_run_{stamp}.md"
    combined.write_text("\n".join(md), encoding="utf-8")
    summary_json = out_dir / f"observability_run_{stamp}.json"
    summary_json.write_text(
        json.dumps(
            {"generated_at": stamp, "api_url": args.api_url, "results": results},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"\n{'=' * 60}\nOBSERVABILITY RUN COMPLETE\n{'=' * 60}")
    for r in results:
        print(f"  {r['observer']:<10} rc={r['rc']} ({r['duration_s']}s) -> {r['report']}")
    print(f"\nCombined index: {combined}")
    print(f"Summary JSON:   {summary_json}")
    # Exit nonzero only if an observer failed to run (crash/unreachable), not on
    # low quality scores — these are heuristic observers, not gates.
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
