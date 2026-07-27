#!/usr/bin/env python3
"""Forge replay — exercises every /forge* + related world-bootstrap surface.

Hits:
  * POST /forge/quick-world         (currently fails — documents why)
  * POST /forge/demo-world          (currently fails — documents why)
  * GET  /universes/universes       (used as the existing-world fallback)
  * POST /chat                      (the path that actually works)
  * GET  /universes/{id}/state      (universe state read)
  * GET  /graph/world               (graph view)
  * GET  /ingest/packs              (ingest pack list)

Writes a per-surface markdown report. Heuristic only — never asserts.

Run::

    python scripts/forge_replay.py \\
        --api-url http://localhost:8000/api \\
        --log-file tests/e2e/logs/forge_run.md
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_gameplay_smoke import _api  # noqa: E402


DEFAULT_API_URL = os.environ.get("MONITOR_API_URL", "http://localhost:8000/api")
DEFAULT_OUTPUT = Path("tests/e2e/logs")


def _timed(fn) -> tuple[Any, float, str | None]:
    t0 = time.time()
    try:
        return fn(), round(time.time() - t0, 2), None
    except Exception as exc:  # noqa: BLE001
        return None, round(time.time() - t0, 2), str(exc)[:300]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--log-file", default=None)
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = Path(args.log_file) if args.log_file else (
        out_dir / f"forge_replay_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
    )

    http = requests.Session()
    surfaces: list[dict[str, Any]] = []

    # health
    health, lat, err = _timed(lambda: _api(http, "GET", args.api_url, "/health"))
    surfaces.append({
        "surface": "GET /health",
        "ok": err is None and isinstance(health, dict) and health.get("status") == "ok",
        "latency_s": lat, "error": err,
        "summary": (health or {}).get("status", "?"),
    })

    # quick-world
    qw_body = {
        "seed": "A snowy mining outpost at the edge of the Pale Wastes",
        "genre": "dark fantasy",
        "tone": "grim",
        "start_playing": True,
    }
    qw, lat, err = _timed(
        lambda: _api(http, "POST", args.api_url, "/forge/quick-world", json=qw_body)
    )
    surfaces.append({
        "surface": "POST /forge/quick-world",
        "ok": err is None and isinstance(qw, dict) and qw.get("universe_id"),
        "latency_s": lat, "error": err,
        "summary": (
            "universe_id=" + str((qw or {}).get("universe_id")) if qw else
            (err or "no response")[:160]
        ),
    })

    # demo-world
    dw, lat, err = _timed(
        lambda: _api(http, "POST", args.api_url, "/forge/demo-world?start_playing=true", json={})
    )
    surfaces.append({
        "surface": "POST /forge/demo-world",
        "ok": err is None and isinstance(dw, dict) and dw.get("universe_id"),
        "latency_s": lat, "error": err,
        "summary": (
            "universe_id=" + str((dw or {}).get("universe_id")) if dw else
            (err or "no response")[:160]
        ),
    })

    # universes list (the fallback path the other scripts use)
    ulist, lat, err = _timed(
        lambda: _api(http, "GET", args.api_url, "/universes/universes")
    )
    universe_id = None
    if isinstance(ulist, list) and ulist:
        universe_id = ulist[0].get("id")
    surfaces.append({
        "surface": "GET /universes/universes",
        "ok": err is None and isinstance(ulist, list) and len(ulist) > 0,
        "latency_s": lat, "error": err,
        "summary": f"count={len(ulist) if isinstance(ulist, list) else 0}, first={universe_id}",
    })

    # pick an existing universe and use the /chat path that actually works
    if universe_id:
        chat_body = {
            "title": f"Forge Replay {datetime.now(timezone.utc).strftime('%H%M%S')}",
            "mode": "autonomous_gm",
            "universe_id": universe_id,
            "tone": "grim",
            "play_mode": "dice_game_system",
        }
        chat, lat, err = _timed(
            lambda: _api(http, "POST", args.api_url, "/chat", json=chat_body)
        )
        sid = (chat or {}).get("id")
        surfaces.append({
            "surface": "POST /chat (existing-universe bootstrap)",
            "ok": err is None and sid,
            "latency_s": lat, "error": err,
            "summary": f"session_id={sid}",
        })

        # universe state (canonical endpoint is /universes/universes/{id})
        if sid:
            ustate, lat, err = _timed(
                lambda: _api(http, "GET", args.api_url, f"/universes/universes/{universe_id}")
            )
            ent_count = len(ustate.get("entities") or []) if isinstance(ustate, dict) else 0
            surfaces.append({
                "surface": "GET /universes/universes/{id}",
                "ok": err is None and isinstance(ustate, dict),
                "latency_s": lat, "error": err,
                "summary": f"entities={ent_count}",
            })

            # session state
            sstate, lat, err = _timed(
                lambda: _api(http, "GET", args.api_url, f"/chat/{sid}/state")
            )
            sess = (sstate or {}).get("session") or {}
            surfaces.append({
                "surface": "GET /chat/{sid}/state",
                "ok": err is None and isinstance(sstate, dict),
                "latency_s": lat, "error": err,
                "summary": f"phase={sess.get('phase')}, turns={sess.get('turns_count', '?')}",
            })

            # recap
            recap, lat, err = _timed(
                lambda: _api(http, "GET", args.api_url, f"/chat/{sid}/recap")
            )
            rtext = (recap or {}).get("recap", "") if recap else ""
            surfaces.append({
                "surface": "GET /chat/{sid}/recap (CF-2)",
                "ok": err is None,
                "latency_s": lat, "error": err,
                "summary": f"chars={len(rtext)}",
            })

            # graph/world
            gw, lat, err = _timed(
                lambda: _api(http, "GET", args.api_url, "/graph/world")
            )
            gw_summary = "ok" if isinstance(gw, dict) and not err else "fail"
            surfaces.append({
                "surface": "GET /graph/world",
                "ok": err is None and isinstance(gw, dict),
                "latency_s": lat, "error": err,
                "summary": gw_summary,
            })

    # ingest packs
    packs, lat, err = _timed(
        lambda: _api(http, "GET", args.api_url, "/ingest/packs")
    )
    pcount = (
        len(packs.get("packs") or [])
        if isinstance(packs, dict)
        else len(packs) if isinstance(packs, list) else 0
    )
    surfaces.append({
        "surface": "GET /ingest/packs",
        "ok": err is None and pcount >= 0,
        "latency_s": lat, "error": err,
        "summary": f"count={pcount}",
    })

    # --- write markdown --------------------------------------------------
    lines = [
        "# Forge Replay",
        "",
        f"- **API**: `{args.api_url}`",
        f"- **Generated at**: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "## Surface coverage",
        "",
        "| Surface | OK | Latency | Summary |",
        "|---|---|---|---|",
    ]
    for s in surfaces:
        ok = "✅" if s["ok"] else "❌"
        summary = (s["summary"] or "")[:120].replace("|", "\\|")
        lines.append(f"| `{s['surface']}` | {ok} | {s['latency_s']}s | {summary} |")

    failures = [s for s in surfaces if not s["ok"]]
    if failures:
        lines += ["", "## Failures", ""]
        for s in failures:
            lines.append(f"### `{s['surface']}`")
            lines.append("")
            lines.append(f"```\n{(s['error'] or 'no error')}\n```")
            lines.append("")

    log_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"log: {log_file}")
    print()
    for s in surfaces:
        ok = "OK " if s["ok"] else "FAIL"
        print(f"  [{ok}] {s['surface']:<46s}  {s['latency_s']:5.2f}s  {s['summary'][:80]}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
