#!/usr/bin/env python3
"""Targeted subsystem replays — exercises NPCs, factions, lore, relationships.

Drives the autonomous GM through a single long session that focuses on
NPC interaction, relationship deltas, lore surfacing, and faction
hooks.  Each turn has an explicit subsystem tag (relationship_shift,
lore_recall, faction_probe, social_negotiation, npc_voice) so we can
inspect whether the GM loop actually engaged that subsystem.

Run::

    set -a; source .env; set +a
    python scripts/subsystem_replay.py \\
        --api-url http://localhost:8000/api \\
        --turns 14 \\
        --log-file tests/e2e/logs/subsystem_run.md
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
from live_gameplay_smoke import (  # noqa: E402
    _api,
    _extract_text,
    _normalize_player_model,
    FALLBACK_MARKERS,
)

try:
    import litellm  # noqa: F401
except Exception:  # noqa: BLE001
    litellm = None  # type: ignore[assignment]


DEFAULT_API_URL = os.environ.get("MONITOR_API_URL", "http://localhost:8000/api")
DEFAULT_PLAYER_MODEL = os.environ.get("MONITOR_PLAYTEST_MODEL", "ollama/qwen2.5:latest")
DEFAULT_OUTPUT = Path("tests/e2e/logs")


@dataclass
class Goal:
    tag: str
    subsystem: str
    goal: str


SUBSYSTEM_GOALS: list[Goal] = [
    Goal("intro", "social",
         "I introduce myself (Kael Draven) to the barkeep and ask what's worth knowing tonight."),
    Goal("trust_seed", "relationship",
         "I share a small piece of personal history — the Penitent Star — and watch how she responds."),
    Goal("lore_recall", "lore",
         "I ask the barkeep what she remembers about the Penitent Star and any salvage crews that went looking."),
    Goal("faction_probe", "faction",
         "I press her on who's been asking similar questions lately — guild, watch, syndicate, anyone."),
    Goal("social_negotiation", "negotiation",
         "I offer credits for a private room and discretion; I want to see what she says yes to."),
    Goal("npc_voice", "npc_voice",
         "I ask her something personal — what keeps her here, who she worries about. Watch her register."),
    Goal("lore_event", "lore",
         "I describe a faint sound I heard earlier; ask her what it usually means at this hour."),
    Goal("relationship_mirror", "relationship",
         "I thank her sincerely for the information and ask what I can do in return — small favor first."),
    Goal("faction_hook", "faction",
         "I ask her who would notice if the wreck I just boarded came back empty."),
    Goal("social_deal", "negotiation",
         "I name a specific amount and ask for one concrete piece of evidence — names, a sigil, anything physical."),
    Goal("npc_test", "npc_voice",
         "I probe whether she's afraid of anyone in this room. Watch how she reads the silence."),
    Goal("lore_blacksite", "lore",
         "I ask if there's any place in this system people don't come back from."),
    Goal("relationship_close", "relationship",
         "I leave her a token — a tin coin from my last salvage — and tell her where I'll be docked."),
    Goal("wrap_up", "social",
         "I leave the bar cleanly, naming the dock and the time I'll be back, and step into the night."),
]


def _llm_turn(goal: Goal, history: list[dict[str, Any]], model: str) -> str:
    if litellm is None:
        raise RuntimeError("litellm missing")
    recent = "\n\n".join(
        f"{h['speaker']}: {h['text'][:400]}" for h in history[-6:]
    )
    response = litellm.completion(
        model=_normalize_player_model(model),
        temperature=0.65,
        max_tokens=180,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are the PLAYER in a solo RPG. Stay in character and pursue "
                    "the CURRENT GOAL. Adapt to what the GM just said — don't ignore "
                    "new NPCs or new context. Reply with only the next player line "
                    "(1-3 sentences). Do NOT narrate GM outcomes."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Recent transcript:\n{recent or '(just started)'}\n\n"
                    f"CURRENT GOAL ({goal.subsystem}): {goal.goal}\n\n"
                    "Write the player's next action."
                ),
            },
        ],
    )
    text = _extract_text(response)
    return text or "I wait a beat and then continue the conversation."


def _bootstrap(http: requests.Session, base_url: str) -> tuple[str, str]:
    universes = _api(http, "GET", base_url, "/universes/universes")
    if not universes:
        raise RuntimeError("no universes available")
    universe = universes[0]
    uid = universe["id"]
    created = _api(
        http,
        "POST",
        base_url,
        "/chat",
        json={
            "title": f"Subsystem Replay {datetime.now(timezone.utc).strftime('%H%M%S')}",
            "mode": "autonomous_gm",
            "universe_id": uid,
            "universe_label": universe.get("name"),
            "tone": "grim",
            "play_mode": "narrative",
        },
    )
    return created["id"], uid


def _main(args: argparse.Namespace) -> int:
    http = requests.Session()
    health = _api(http, "GET", args.api_url, "/health")
    if health.get("status") != "ok":
        raise RuntimeError(f"backend unhealthy: {health}")
    sid, uid = _bootstrap(http, args.api_url)
    print(f"session  : {sid}")
    print(f"universe : {uid}")

    turns = min(args.turns, len(SUBSYSTEM_GOALS))
    history: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for i in range(turns):
        goal = SUBSYSTEM_GOALS[i]
        try:
            player_text = _llm_turn(goal, history, args.player_model)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  LLM fallback at turn {i+1}: {exc}")
            player_text = "I stay quiet for a moment and let her read me before I speak."

        t0 = time.time()
        reply = _api(http, "POST", args.api_url, f"/chat/{sid}/send", json={"content": player_text})
        latency = time.time() - t0
        gm_text = reply.get("content", "")
        meta = reply.get("metadata") or {}
        fallback = any(m in gm_text.lower() for m in FALLBACK_MARKERS)
        history.append({"speaker": "PLAYER", "text": player_text})
        history.append({"speaker": "GM", "text": gm_text})
        rows.append(
            {
                "index": i + 1,
                "tag": goal.tag,
                "subsystem": goal.subsystem,
                "player_text": player_text,
                "gm_text": gm_text,
                "metadata": meta,
                "latency_s": round(latency, 2),
                "fallback": fallback,
                "phase": meta.get("phase"),
                "resolution_type": meta.get("type") or meta.get("resolution_type"),
                "success_level": meta.get("success_level"),
                "effects": meta.get("effects") or [],
                "social_read": meta.get("social_read"),
                "relationship_snapshot": meta.get("relationship_snapshot"),
            }
        )
        print(
            f"  turn {i+1:02d} [{goal.subsystem:<14s}/{goal.tag}] "
            f"{latency:5.1f}s phase={meta.get('phase') or '?'}"
        )

    log_file = Path(args.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Subsystem Replay",
        "",
        f"- **API**: `{args.api_url}`",
        f"- **Player model**: `{args.player_model}`",
        f"- **Session ID**: `{sid}`",
        f"- **Universe ID**: `{uid}`",
        f"- **Goals played**: `{turns}`",
        f"- **Subsystems covered**: relationship, lore, faction, social, npc_voice",
        f"- **Generated at**: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "---",
        "",
    ]
    for r in rows:
        lines.append(f"## Turn {r['index']} — `{r['subsystem']}` / `{r['tag']}` (phase={r['phase']})")
        lines.append("")
        lines.append(f"**PLAYER:** {r['player_text'].strip()}")
        lines.append("")
        lines.append("**GM:**")
        lines.append("")
        lines.append(r["gm_text"].strip() or "_(empty)_")
        lines.append("")
        signals: list[str] = []
        if r.get("success_level"):
            signals.append(f"success=`{r['success_level']}`")
        if r.get("effects"):
            signals.append(f"effects=`{r['effects']}`")
        if r.get("social_read"):
            signals.append(f"social_read=`{r['social_read']}`")
        if r.get("relationship_snapshot"):
            signals.append(f"rel_snapshot=`{r['relationship_snapshot']}`")
        if r.get("fallback"):
            signals.append("⚠️ FALLBACK")
        if signals:
            lines.append("> " + "  ·  ".join(signals))
            lines.append("")
    log_file.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"  log: {log_file}")
    fallback_count = sum(1 for r in rows if r.get("fallback"))
    if fallback_count:
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--player-model", default=DEFAULT_PLAYER_MODEL)
    ap.add_argument("--turns", type=int, default=len(SUBSYSTEM_GOALS))
    ap.add_argument("--log-file", default=None)
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = ap.parse_args()
    if not args.log_file:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.log_file = str(Path(args.output_dir) / f"subsystem_replay_{stamp}.md")
    return _main(args)


if __name__ == "__main__":
    raise SystemExit(main())
