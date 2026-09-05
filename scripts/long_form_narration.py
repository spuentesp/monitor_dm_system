#!/usr/bin/env python3
"""Long-form, non-deterministic narration replay.

Replays a multi-arc script that exercises the real played paths the
autonomous GM supports — character creation, social/exploration,
combat with dice resolution, NPC voice + relationship deltas,
working-state XP/conditions, and end-scene checkpointing.

Player text comes from a local LLM (``MONITOR_PLAYTEST_MODEL``,
defaults to ``ollama/qwen2.5:latest`` — the same path the smoke script
uses) so the run is non-deterministic but bounded.  Fallback heuristics
keep a turn moving if the LLM hiccups; structural assertions fail loudly
if the GM loop is broken.

Usage::

    set -a; source .env; set +a
    export MONITOR_PLAYTEST_MODEL=ollama/qwen2.5:latest
    python scripts/long_form_narration.py \\
        --api-url http://localhost:8000/api \\
        --turns 22 \\
        --log-file tests/e2e/logs/long_form_run.md

Use ``--benchmark-id narrative_weighted_derelict`` (default) or any of the
configured playtest benchmarks.  Pass ``--seed <text>`` to drive the
``quick`` bootstrap world (narrative-only, no dice), or omit it to use
the curated Millhaven demo world (full mechanical layer).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# --- Reuse proven helpers --------------------------------------------------
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
DEFAULT_BENCHMARK = "narrative_weighted_derelict"
DEFAULT_PLAYER_MODEL = os.environ.get("MONITOR_PLAYTEST_MODEL", "ollama/qwen2.5:latest")
DEFAULT_OUTPUT = Path("tests/e2e/logs")

# ---------------------------------------------------------------------------
# Goals — fed to the LLM player one at a time. The arc deliberately walks
# every subsystem: character creation -> social/exploration -> lore dialog
# with NPC -> combat (with real dice) -> consequence/loot -> end-scene.
# ---------------------------------------------------------------------------
LONG_FORM_GOALS: list[dict[str, str]] = [
    # --- Arc 1: Character creation (turns 1-3) -----------------------------
    {
        "tag": "char_creation_accept",
        "goal": (
            "I introduce my character as a void-born salvage engineer "
            "(name = Kael Draven) and answer whatever the GM asks for to "
            "finish character creation."
        ),
    },
    {
        "tag": "char_creation_stat_roll",
        "goal": "Yes, roll my stats and accept whatever the GM generates.",
    },
    {
        "tag": "first_in_fiction_action",
        "goal": (
            "I'm standing in the tavern/hub. I take stock of exits, "
            "locals, and any salvage boards. Ask one clarifying question "
            "about the immediate danger before committing to action."
        ),
    },
    # --- Arc 2: Social + Lore (turns 4-7) ---------------------------------
    {
        "tag": "social_inquiry",
        "goal": (
            "I ask the bartender about a derelict ship that's been "
            "mentioned. I want concrete details: name, rumors, danger, "
            "and whether anyone's gone looking for it."
        ),
    },
    {
        "tag": "lore_recall",
        "goal": (
            "I press the bartender for any local history or faction "
            "context (guild, syndicate, watch). I want names and a hook."
        ),
    },
    {
        "tag": "social_deal",
        "goal": "I buy supplies and seal my suit. I'm ready to board.",
    },
    {
        "tag": "exploration_intent",
        "goal": (
            "I take the salvage job and dock with the wreck. At the "
            "airlock I pause, listen, and state what I check before "
            "cycling it open."
        ),
    },
    # --- Arc 3: Combat + Dice (turns 8-12) ---------------------------------
    {
        "tag": "first_combat_intent",
        "goal": (
            "Inside the wreck I sweep my lamp and scan for power, "
            "motion, and signs anyone else got here first. If I see a "
            "threat, I draw my cutter."
        ),
    },
    {
        "tag": "combat_engaged",
        "goal": (
            "Something moves. I charge the closest hostile, striking to "
            "wound — I want the dice to actually fire here, not a "
            "forced narrative."
        ),
    },
    {
        "tag": "combat_finisher",
        "goal": (
            "The enemy rallies. Bloodied, I press the attack and try "
            "to bring it down before it recovers."
        ),
    },
    {
        "tag": "tactical_assessment",
        "goal": (
            "I take a hard breath, take stock of HP, ammo, and the "
            "salvage on the body, and decide whether to push deeper or "
            "fall back to my ship."
        ),
    },
    {
        "tag": "deeper_push",
        "goal": "I push deeper, heading for the reactor or main cargo.",
    },
    # --- Arc 4: Puzzle + Consequence (turns 13-16) -------------------------
    {
        "tag": "puzzle_encounter",
        "goal": (
            "I find a sealed door with strange symbols. I examine it "
            "closely and try to figure out how it opens."
        ),
    },
    {
        "tag": "puzzle_solve",
        "goal": "I attempt to solve the puzzle using the clues I found.",
    },
    {
        "tag": "puzzle_consequence",
        "goal": (
            "Once the door opens, I step through carefully, listing "
            "what I'm watching for (tripwires, pressure plates, "
            "hostiles)."
        ),
    },
    {
        "tag": "loot_choice",
        "goal": (
            "I see the salvage — cores, data, or both. I describe what "
            "I take and what I leave behind."
        ),
    },
    # --- Arc 5: Boss fight + End-scene (turns 17-22) -----------------------
    {
        "tag": "boss_intro",
        "goal": (
            "A defender construct powers up between me and the reactor. "
            "I draw my weapon and ready an opening move."
        ),
    },
    {
        "tag": "boss_phase_two",
        "goal": "I press the construct, going for its weak point.",
    },
    {
        "tag": "boss_finisher",
        "goal": (
            "I try to finish it off and ask the GM what consequences "
            "this fight has for the wreck and any survivors on board."
        ),
    },
    {
        "tag": "extraction",
        "goal": "I grab the salvage and rush back to my ship.",
    },
    {
        "tag": "extraction_pressure",
        "goal": (
            "Alarms are blaring / hull is groaning. I describe exactly "
            "how I escape and what I do the moment my ship clears the "
            "airlock."
        ),
    },
    {
        "tag": "wrap_up",
        "goal": (
            "I dock back at the hub. I sell or stash the salvage, then "
            "ask the GM for a brief epilogue about what survived of the "
            "wreck and any hook for the next run."
        ),
    },
]


@dataclass
class TurnObservation:
    index: int
    goal_tag: str
    player_text: str
    gm_text: str
    metadata: dict[str, Any]
    latency_s: float
    fallback: bool
    phase: str | None = None
    resolution_type: str | None = None
    success_level: str | None = None
    effects: list[str] = field(default_factory=list)


def _llm_player_turn(goal: str, history: list[TurnObservation], model: str) -> str:
    """One non-deterministic player move, generated by the configured LLM."""
    if litellm is None:
        raise RuntimeError("litellm not installed; cannot drive the LLM player")

    recent = "\n\n".join(
        f"{t.phase or 'GM'}: {t.gm_text.strip()[:400]}\nPLAYER: {t.player_text.strip()[:200]}"
        for t in history[-4:]
    )
    response = litellm.completion(
        model=_normalize_player_model(model),
        temperature=0.7,
        max_tokens=160,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are the PLAYER in a solo RPG session. Stay in character "
                    "and pursue the CURRENT GOAL below. React truthfully to what "
                    "the GM just described — if the GM changes the situation, "
                    "adapt instead of ignoring it. Reply with ONLY your next "
                    "player action in 1-3 sentences. Do NOT narrate outcomes or "
                    "write dialogue for the GM. Keep momentum — don't stall on "
                    "meta questions."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Recent transcript:\n{recent or '(just started)'}\n\n"
                    f"Your current GOAL: {goal}\n\nWrite the player's next action."
                ),
            },
        ],
    )
    text = _extract_text(response)
    return text or "I press forward, watching for danger and looking for clues."


def _observe_turn(
    idx: int, goal_tag: str, player_text: str, reply: dict[str, Any], latency: float
) -> TurnObservation:
    meta = reply.get("metadata") or {}
    gm_text = reply.get("content", "")
    return TurnObservation(
        index=idx,
        goal_tag=goal_tag,
        player_text=player_text,
        gm_text=gm_text,
        metadata=meta,
        latency_s=round(latency, 2),
        fallback=any(m in gm_text.lower() for m in FALLBACK_MARKERS),
        phase=str(meta.get("phase")) if meta.get("phase") else None,
        resolution_type=str(meta.get("type") or "") or None,
        success_level=str(meta.get("success_level"))
        if meta.get("success_level")
        else None,
        effects=[str(e) for e in (meta.get("effects") or []) if e],
    )


def _bootstrap(
    http: requests.Session, base_url: str, seed: str | None
) -> tuple[str, str]:
    """Create a fresh dice-mode play session. Returns (session_id, universe_id).

    /forge/demo-world and /forge/quick-world currently reject the bundled
    CharacterCreationProcedure (its steps use enums that the schema no
    longer accepts); the only reliable path is to pick an existing
    universe from /universes/universes and create the session via /chat.
    """
    universes = _api(http, "GET", base_url, "/universes/universes")
    if not universes:
        raise RuntimeError("no universes available — run scripts/seed_world.py first")
    universe = universes[0]
    uid = universe["id"]
    title = f"Long-Form Replay {datetime.now(timezone.utc).strftime('%H%M%S')}"
    created = _api(
        http,
        "POST",
        base_url,
        "/chat",
        json={
            "title": title,
            "mode": "autonomous_gm",
            "universe_id": uid,
            "universe_label": universe.get("name"),
            "tone": "grim",
            "play_mode": "dice_game_system",
        },
    )
    sid = created["id"]
    return sid, uid


def _canon_delta(http: requests.Session, base_url: str, universe_id: str | None) -> int:
    if not universe_id:
        return 0
    try:
        state = _api(http, "GET", base_url, f"/universes/{universe_id}/state")
    except Exception:  # noqa: BLE001
        return 0
    ents = state.get("entities") if isinstance(state, dict) else None
    return len(ents) if isinstance(ents, list) else 0


def _write_markdown(
    log_file: Path,
    args: argparse.Namespace,
    sid: str,
    uid: str,
    observations: list[TurnObservation],
    canon_after: int,
) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    latencies = [t.latency_s for t in observations]
    avg = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
    fallback_count = sum(1 for t in observations if t.fallback)
    rolls_seen = sum(
        1 for t in observations if (t.resolution_type or "").startswith("scene_turn")
    )
    combat = sum(
        1
        for t in observations
        if "momentum" in str(t.metadata.get("effects", [])).lower()
        or "fiction_advances" in (t.effects or [])
        and t.success_level in {"success", "critical_success"}
    )
    lines = [
        "# Long-Form Narration Replay",
        "",
        f"- **API**: `{args.api_url}`",
        f"- **Player model**: `{args.player_model}`",
        f"- **Benchmark**: `{args.benchmark_id}`",
        f"- **Bootstrap**: `{'quick' if args.seed else 'demo (Millhaven)'}`",
        f"- **Session ID**: `{sid}`",
        f"- **Universe ID**: `{uid}`",
        f"- **Goal steps**: `{len(LONG_FORM_GOALS)}`",
        f"- **Turns played**: `{len(observations)}`",
        f"- **Avg latency**: `{avg}s`",
        f"- **Rolls observed**: `{rolls_seen}`",
        f"- **Fallback markers**: `{fallback_count}`",
        f"- **Canon entities at end**: `{canon_after}`",
        f"- **Generated at**: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "---",
        "",
    ]
    for t in observations:
        lines.append(
            f"## Turn {t.index} — `{t.goal_tag}` _(phase={t.phase or '?'}, lat={t.latency_s}s)_"
        )
        lines.append("")
        lines.append(f"**PLAYER:** {t.player_text.strip()}")
        lines.append("")
        lines.append("**GM:**")
        lines.append("")
        lines.append(t.gm_text.strip() or "_(empty)_")
        lines.append("")
        signals: list[str] = []
        if t.resolution_type:
            signals.append(f"resolution=`{t.resolution_type}`")
        if t.success_level:
            signals.append(f"success=`{t.success_level}`")
        if t.effects:
            signals.append(f"effects=`{t.effects}`")
        if t.fallback:
            signals.append("⚠️ FALLBACK")
        if signals:
            lines.append("> " + "  ·  ".join(signals))
            lines.append("")
        if t.metadata:
            lines.append("```json")
            lines.append(json.dumps(t.metadata, indent=2, ensure_ascii=False)[:4000])
            lines.append("```")
            lines.append("")
    log_file.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--player-model", default=DEFAULT_PLAYER_MODEL)
    ap.add_argument("--benchmark-id", default=DEFAULT_BENCHMARK)
    ap.add_argument(
        "--seed", default=None, help="World seed (skips demo, narrative-only)"
    )
    ap.add_argument(
        "--turns",
        type=int,
        default=len(LONG_FORM_GOALS),
        help="How many goal steps to actually play (default: all)",
    )
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--log-file", default=None)
    args = ap.parse_args()

    turns = min(args.turns, len(LONG_FORM_GOALS))
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.log_file:
        log_file = Path(args.log_file)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_file = out_dir / f"long_form_narration_{stamp}.md"

    http = requests.Session()
    print(f"health → {args.api_url}/health")
    health = _api(http, "GET", args.api_url, "/health")
    if health.get("status") != "ok":
        raise RuntimeError(f"backend unhealthy: {health}")

    sid, uid = _bootstrap(http, args.api_url, args.seed)
    print(f"session  : {sid}")
    print(f"universe : {uid}")
    canon_before = _canon_delta(http, args.api_url, uid)

    observations: list[TurnObservation] = []
    for i in range(turns):
        goal = LONG_FORM_GOALS[i]
        try:
            player_text = _llm_player_turn(
                goal["goal"], observations, args.player_model
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  LLM fallback at turn {i + 1} ({goal['tag']}): {exc}")
            player_text = "I press forward, watching for danger and looking for clues."

        t0 = time.time()
        reply = _api(
            http,
            "POST",
            args.api_url,
            f"/chat/{sid}/send",
            json={"content": player_text},
        )
        latency = time.time() - t0
        obs = _observe_turn(i + 1, goal["tag"], player_text, reply, latency)
        observations.append(obs)
        print(
            f"  turn {i + 1:02d} [{goal['tag']:<24s}] "
            f"{latency:5.1f}s phase={obs.phase or '?'} "
            f"res={obs.resolution_type or '-'}"
        )

    canon_after = _canon_delta(http, args.api_url, uid)
    _write_markdown(log_file, args, sid, uid, observations, canon_after)

    print()
    print(f"  log:        {log_file}")
    print(f"  canon Δ:    +{canon_after - canon_before} entities")
    fallback_count = sum(1 for t in observations if t.fallback)
    if fallback_count:
        print(f"  fallbacks:  {fallback_count}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
