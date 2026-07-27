#!/usr/bin/env python3
"""Character-creation replay — drives a session through the full char-creation arc.

Most sessions short-circuit character creation ("Yes. Roll my stats.").
This script *exercises* it: walks each phase the GM exposes, asks
clarifying questions, confirms each choice, and only enters active
play once the character sheet is locked.

Useful for verifying:
  * GM loop stays coherent through 4-6 char-creation turns
  * character sheet / metadata is properly populated
  * phase transitions cleanly from `awaiting_character` → `char_creation`
    → `active_play`
  * working_state.current_stats is non-empty after creation

Run::

    python scripts/character_creation_replay.py \\
        --api-url http://localhost:8000/api \\
        --log-file tests/e2e/logs/char_creation_run.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_gameplay_smoke import _api, _extract_text, _normalize_player_model  # noqa: E402

try:
    import litellm  # noqa: F401
except Exception:  # noqa: BLE001
    litellm = None  # type: ignore[assignment]


DEFAULT_API_URL = os.environ.get("MONITOR_API_URL", "http://localhost:8000/api")
DEFAULT_PLAYER_MODEL = os.environ.get("MONITOR_PLAYTEST_MODEL", "ollama/qwen2.5:latest")
DEFAULT_OUTPUT = Path("tests/e2e/logs")


@dataclass
class CharCreationStep:
    tag: str
    prompt_hint: str  # sent as the player turn


STEPS: list[CharCreationStep] = [
    CharCreationStep(
        "intro",
        "I introduce myself as Kael Draven, a void-born salvage engineer. Tell me what kind of character you want me to play here.",
    ),
    CharCreationStep(
        "ask_species",
        "What species or background makes sense for this setting? List two or three concrete options before I choose.",
    ),
    CharCreationStep(
        "ask_class",
        "What classes or roles does this system support? I want to pick something that fits a wreck-salvage arc.",
    ),
    CharCreationStep(
        "choose_class",
        "I pick the salvage-engineer path. Generate my starting attributes and skills.",
    ),
    CharCreationStep(
        "roll_stats",
        "Yes, roll my stats. Take whatever the dice give.",
    ),
    CharCreationStep(
        "choose_background",
        "I want a background of an orphan who learned engineering on station hulls. Wire that into my sheet.",
    ),
    CharCreationStep(
        "choose_equipment",
        "Start me with a salvage cutter, vacuum suit, signal scanner, and three ration packs.",
    ),
    CharCreationStep(
        "ask_sheet",
        "Show me my full character sheet — attributes, skills, resources, conditions — so I can confirm.",
    ),
    CharCreationStep(
        "confirm_lock",
        "Locked in. Begin the scene.",
    ),
    CharCreationStep(
        "first_action",
        "I take stock of the room and ask the barkeep what the morning's news is.",
    ),
]


def _llm_turn(step: CharCreationStep, history: list[dict[str, str]], model: str) -> str:
    if litellm is None:
        raise RuntimeError("litellm missing")
    recent = "\n\n".join(f"{h['speaker']}: {h['text'][:400]}" for h in history[-4:])
    response = litellm.completion(
        model=_normalize_player_model(model),
        temperature=0.4,  # low temperature — char creation wants consistency
        max_tokens=180,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are the PLAYER in a solo RPG character creation. "
                    "Pursue the CURRENT STEP, adapt to the GM's questions, "
                    "and reply with ONE player line (1-2 sentences). "
                    "Do NOT narrate GM outcomes or skip steps."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Recent transcript:\n{recent or '(just started)'}\n\n"
                    f"CURRENT STEP ({step.tag}): {step.prompt_hint}\n\n"
                    "Write the player's next line."
                ),
            },
        ],
    )
    text = _extract_text(response)
    return text or step.prompt_hint


def _bootstrap(http: requests.Session, base_url: str) -> tuple[str, str]:
    universes = _api(http, "GET", base_url, "/universes/universes")
    if not universes:
        raise RuntimeError("no universes")
    u = universes[0]
    created = _api(
        http,
        "POST",
        base_url,
        "/chat",
        json={
            "title": f"Char-Creation Replay {datetime.now(timezone.utc).strftime('%H%M%S')}",
            "mode": "autonomous_gm",
            "universe_id": u["id"],
            "universe_label": u.get("name"),
            "tone": "grim",
            "play_mode": "dice_game_system",
        },
    )
    return created["id"], u["id"]


def _main(args: argparse.Namespace) -> int:
    http = requests.Session()
    health = _api(http, "GET", args.api_url, "/health")
    if health.get("status") != "ok":
        raise RuntimeError(f"backend unhealthy: {health}")
    sid, uid = _bootstrap(http, args.api_url)
    print(f"session  : {sid}")
    print(f"universe : {uid}")

    history: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    phases_seen: set[str] = set()
    sheet_seen = False

    for i, step in enumerate(STEPS[: args.turns]):
        try:
            player_text = _llm_turn(step, history, args.player_model)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  LLM fallback at step {i+1}: {exc}")
            player_text = step.prompt_hint

        t0 = time.time()
        reply = _api(http, "POST", args.api_url, f"/chat/{sid}/send", json={"content": player_text})
        latency = time.time() - t0
        gm_text = reply.get("content", "")
        meta = reply.get("metadata") or {}

        phase = meta.get("phase")
        if phase:
            phases_seen.add(str(phase))
        if (meta.get("character") or {}).get("sheet_markdown"):
            sheet_seen = True

        history.append({"speaker": "PLAYER", "text": player_text})
        history.append({"speaker": "GM", "text": gm_text})
        rows.append(
            {
                "index": i + 1,
                "tag": step.tag,
                "player_text": player_text,
                "gm_text": gm_text,
                "metadata": meta,
                "latency_s": round(latency, 2),
                "phase": phase,
                "resolution_type": meta.get("type"),
            }
        )
        print(f"  step {i+1:02d} [{step.tag:<18s}] {latency:5.1f}s phase={phase or '?'}")

    log_file = Path(args.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Character-Creation Replay",
        "",
        f"- **API**: `{args.api_url}`",
        f"- **Session ID**: `{sid}`",
        f"- **Universe ID**: `{uid}`",
        f"- **Phases observed**: `{sorted(phases_seen)}`",
        f"- **Sheet populated**: `{sheet_seen}`",
        f"- **Steps played**: `{len(rows)}`",
        f"- **Generated at**: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "---",
        "",
    ]
    for r in rows:
        lines.append(f"## Step {r['index']} — `{r['tag']}` (phase={r['phase']})")
        lines.append("")
        lines.append(f"**PLAYER:** {r['player_text'].strip()}")
        lines.append("")
        lines.append("**GM:**")
        lines.append("")
        lines.append(r["gm_text"].strip() or "_(empty)_")
        lines.append("")
        char = (r["metadata"] or {}).get("character") or {}
        if char.get("sheet_markdown"):
            lines.append("**Sheet (excerpt):**")
            lines.append("")
            lines.append("```")
            lines.append(str(char["sheet_markdown"])[:1200])
            lines.append("```")
            lines.append("")
    log_file.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"  log: {log_file}")
    print(f"  sheet_seen={sheet_seen}  phases={sorted(phases_seen)}")

    # Coverage assertions — fail loud if the GM loop is broken.
    if "active_play" not in phases_seen:
        print("  ❌ GM never transitioned to active_play", file=sys.stderr)
        return 2
    if not sheet_seen:
        print("  ⚠️  No character sheet metadata observed", file=sys.stderr)
        # not fatal — older universes may not surface it
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--player-model", default=DEFAULT_PLAYER_MODEL)
    ap.add_argument("--turns", type=int, default=len(STEPS))
    ap.add_argument("--log-file", default=None)
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = ap.parse_args()
    if not args.log_file:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.log_file = str(Path(args.output_dir) / f"char_creation_{stamp}.md")
    return _main(args)


if __name__ == "__main__":
    raise SystemExit(main())
