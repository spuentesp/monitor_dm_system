"""Driver for a Death in Space session that goes past the scripted
turns into roll-triggering actions, so we can see the dice system
in action.

Saves a full markdown log to test_logs/death_in_space_dice_runNN.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

DEFAULT_API = os.environ.get("MONITOR_API_URL", "http://localhost:8000/api")
DEFAULT_OUTPUT = Path("test_logs")
BENCHMARK_ID = "death_in_space_onboarding_probe"

# The benchmark's scripted turns, extended with two roll-triggering actions.
TURNS = [
    "Before we begin, what kind of characters can I play in Death in Space? I don't know the options yet.",
    "If I want someone practical and ship-savvy, what's the difference between a drifter and a patcher in this setup?",
    "Alright, let's go with a patcher — Kael Draven, a void-born engineer who's more comfortable in dead hulls than crowded stations.",
    "Yes, let's do character creation and whatever starting stats or choices matter here.",
    "I take the salvage contract, seal my suit, and ask what my first impression is as I approach the wreck.",
    "I pause at the airlock and listen before opening it. If there's something I should know about the risk, tell me.",
    "I cycle the airlock and step inside, gloves tight. Roll Tech to check the pressure differential on the far side.",
    "I unspool the cutting torch and start work on the cargo bay door, scanning for motion as I weld.",
]


def _api(http: requests.Session, method: str, base: str, path: str, **kw):
    r = http.request(method, f"{base}{path}", timeout=180, **kw)
    r.raise_for_status()
    return r.json()


def _collect_text(reply) -> tuple[str, dict]:
    """Local chat-router response → (text, metadata)."""
    return reply.get("content", ""), reply.get("metadata", {})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", default=DEFAULT_API)
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    p.add_argument("--run-index", type=int, default=1)
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    http = requests.Session()
    base = args.api_url

    health = _api(http, "GET", base, "/health")
    if health.get("status") != "ok":
        print("Backend unhealthy:", health, file=sys.stderr)
        return 1

    universes = _api(http, "GET", base, "/universes/universes")
    universe = universes[0]
    benchmarks = _api(http, "GET", base, "/chat/benchmarks")
    benchmark = next((b for b in benchmarks if b["benchmark_id"] == BENCHMARK_ID), None)
    if not benchmark:
        print(f"Benchmark {BENCHMARK_ID} not found.", file=sys.stderr)
        return 1

    created = _api(
        http,
        "POST",
        base,
        "/chat",
        json={
            "title": benchmark.get("session_title", "Death in Space (Dice Run)"),
            "mode": benchmark.get("mode", "autonomous_gm"),
            "universe_id": universe["id"],
            "universe_label": universe.get("name"),
            "tone": benchmark.get("tone", "grim"),
            "play_mode": benchmark.get("play_mode", "dice_game_system"),
            "benchmark_id": benchmark.get("benchmark_id"),
            "benchmark_label": benchmark.get("name"),
        },
    )
    session_id = created["id"]

    log_lines: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_lines.append("# Death in Space — Live Dice Run\n")
    log_lines.append(f"- **API**: `{base}`")
    log_lines.append(f"- **Session ID**: `{session_id}`")
    log_lines.append(f"- **Universe**: `{universe.get('name')}`")
    log_lines.append(f"- **Player mode:** `scripted` (dice-driving extra turns)")
    log_lines.append(f"- **Benchmark:** `{benchmark.get('name')}`")
    log_lines.append(f"- **Generated at**: {stamp}")
    log_lines.append("")
    log_lines.append("---")
    log_lines.append("")

    transcript: list[dict] = []
    gm_clarifications = 0
    fallback_count = 0
    total_gm_chars = 0
    dice_rolls: list[dict] = []
    last_rolls: list[dict] = []

    for i, line in enumerate(TURNS):
        log_lines.append(f"## Turn {i}\n")
        log_lines.append("**PLAYER:**\n")
        log_lines.append(line + "\n")
        log_lines.append("**GM:**\n")
        reply = _api(
            http,
            "POST",
            base,
            f"/chat/{session_id}/send",
            json={"content": line},
        )
        text, metadata = _collect_text(reply)
        log_lines.append(text + "\n")
        log_lines.append("```json")
        log_lines.append(json.dumps(metadata, default=str, indent=2)[:1200] + "\n")
        log_lines.append("```\n")

        # Track fallback markers and dice metadata.
        if any(m in text.lower() for m in ("gathering their thoughts", "couldn't generate", "unable to continue")):
            fallback_count += 1
        if "?" in line:
            gm_clarifications += 1
        total_gm_chars += len(text.strip())

        for key in ("roll", "rolls", "dice", "roll_breakdown"):
            payload = metadata.get(key)
            if payload:
                dice_rolls.append({"turn": i, "key": key, "value": payload})
                if key == "rolls":
                    last_rolls = payload if isinstance(payload, list) else [payload]

        transcript.append({"role": "player", "text": line})
        transcript.append({"role": "gm", "text": text, "metadata": metadata})

    log_lines.append("\n## Roll summary\n")
    if dice_rolls:
        log_lines.append(f"**{len(dice_rolls)} dice-related metadata key(s) seen across turns:**\n")
        for entry in dice_rolls:
            log_lines.append(f"- Turn {entry['turn']} — `{entry['key']}`: `{entry['value']}`")
    else:
        log_lines.append("No explicit `roll` / `rolls` metadata key found in the responses. The dice system binding is active (`play_mode: dice_game_system`) but the year-zero-engine roll output isn't surfaced as a top-level key in the chat reply shape.")

    summary = {
        "session_id": session_id,
        "universe": universe.get("name"),
        "transcript_entries": len(transcript),
        "fallback_count": fallback_count,
        "avg_gm_chars": round(total_gm_chars / max(1, sum(1 for t in transcript if t["role"] == "gm")), 1),
        "clarification_questions": gm_clarifications,
        "dice_metadata_keys": [d["key"] for d in dice_rolls],
    }
    log_lines.append("\n```json\n" + json.dumps(summary, indent=2) + "\n```\n")

    out_path = output_dir / f"death_in_space_dice_run{args.run_index:02d}_{stamp.replace(':', '').replace('-', '')}.md"
    out_path.write_text("\n".join(log_lines), encoding="utf-8")
    print("LIVE DICE RUN")
    print(f"  API:    {base}")
    print(f"  Session: {session_id}")
    print(f"  Transcript entries: {len(transcript)}")
    print(f"  Fallback: {fallback_count}")
    print(f"  Dice metadata: {[d['key'] for d in dice_rolls]}")
    print(f"  Log:    {out_path}")
    return 0 if fallback_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
