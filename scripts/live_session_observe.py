#!/usr/bin/env python3
"""Controlled real-LLM session observer (heuristic, not a gate).

Bootstraps a *known* dice-system world (so the mechanical layer can actually
surface), then drives the same arc through two passes from identical starting
conditions:

  * ``scripted``   — fixed player lines; only the GM uses the real LLM, so the
    run is comparable turn-to-turn and any divergence is the GM's.
  * ``llm_actor``  — the player is a real LLM seeded with the scripted beats as
    *goals*, free to adapt to GM pushback; surfaces emergent decisions that
    change the script.

It makes **no assertions**. It captures a rich per-turn observation — GM prose,
latency, the live ``working_state`` (stats / resources / conditions / xp /
level), success levels, phase, and heuristic divergence signals — and writes a
human-readable markdown log per pass plus a combined JSON report. Optionally it
runs the LLM-judge rubric from ``eval_gm_playtest.py`` over each transcript.

Usage:
    docker compose --env-file .env -f infra/docker-compose.yml up -d
    uv run python scripts/live_session_observe.py \
        --api-url http://localhost:8001/api \
        --player-model gemini/gemini-2.5-flash-lite \
        --judge-model  gemini/gemini-2.5-flash

Requires the dockerized stack up. The judge needs GOOGLE_API_KEY (or a matching
key for --judge-model); skip it with --no-judge.
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

# Reuse the proven helpers from the existing smoke script (same dir on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_gameplay_smoke import (  # noqa: E402
    _api,
    _extract_text,
    _normalize_player_model,
)

try:
    import litellm
    from monitor_agents import dspy_runtime as _monitor_dspy_runtime  # noqa: F401
except Exception:  # noqa: BLE001
    litellm = None

DEFAULT_API_URL = os.environ.get("MONITOR_API_URL", "http://localhost:8001/api")
DEFAULT_OUTPUT_DIR = Path("docs/testing")

# A controlled seed that guarantees a threat to fight (so combat/HP can surface)
# and a central problem to resolve (so the resolution arc / downtime can trigger).
DEFAULT_SEED = (
    "A lonely frontier outpost on the edge of the ash wastes, besieged after dark "
    "by raiders and worse. The player is the last defender still standing."
)

# Scripted intents. Each is both the fixed line (scripted pass) and the GOAL fed
# to the LLM actor (llm_actor pass). Designed to walk the full arc:
# explore -> social -> combat (force HP/resource deltas) -> consequence ->
# resolution (force the arc toward downtime).
DEFAULT_ARC: list[str] = [
    "I take stock of the outpost, scanning for threats, exits, and anything I can use.",
    "I find the nearest survivor and demand to know what is really attacking us.",
    "I draw my weapon and charge the closest raider, striking to wound.",
    "Bloodied, I press the attack and try to bring the enemy down before they rally.",
    "I tend my wounds, search the fallen for anything useful, and take a hard breath.",
    "I move to end the siege for good — straight at whatever is leading them.",
]

CHAR_CREATION_ACCEPT = "Yes. Roll my stats."
FALLBACK_MARKERS = ("gathering their thoughts", "couldn't generate", "unable to continue")


@dataclass
class TurnObservation:
    index: int
    player_intent: str
    player_text: str
    gm_text: str
    latency_s: float
    phase: str | None
    success_level: str | None
    working_state: dict[str, Any]
    gm_effects: list[Any]
    resource_deltas: dict[str, float]
    conditions_added: list[str]
    xp_gained: int
    offered_choice: bool
    fallback: bool


@dataclass
class PassResult:
    mode: str
    session_id: str
    universe_id: str
    character_id: str | None
    seed: str
    turns: list[TurnObservation] = field(default_factory=list)
    canon_before: int = 0
    canon_after: int = 0
    change_log_entries: int = 0
    judge: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Bootstrap + read-back
# --------------------------------------------------------------------------- #
def _bootstrap_universe(
    http: requests.Session, base_url: str, seed: str, mode: str = "demo"
) -> tuple[str, str | None]:
    """Build ONE controlled dice world + bound PC; return (universe_id, character_id).

    Both passes reuse this single universe so they start from identical canon.

    ``mode="demo"`` (default) uses the curated, deterministic Millhaven demo
    world — the only bootstrap that reliably seeds the mechanical layer
    (Grit/Wits/Resolve + Health/Nerve + conditions). ``mode="quick"`` uses an
    LLM-built world from ``seed``; note that quick-world does NOT bind a game
    system, so the mechanical layer stays empty — useful only for narrative-mode
    observation.
    """
    if mode == "quick":
        built = _api(
            http,
            "POST",
            base_url,
            "/forge/quick-world",
            json={"seed": seed, "genre": "dark fantasy", "tone": "grim", "start_playing": True},
        )
    else:
        built = _api(http, "POST", base_url, "/forge/demo-world?start_playing=true", json={})
    universe_id = built.get("universe_id")
    if not universe_id:
        raise RuntimeError(f"world bootstrap did not return a universe_id: {built}")
    character_id = None
    session_id = built.get("session_id")
    if session_id:
        state = _api(http, "GET", base_url, f"/chat/{session_id}/state")
        character_id = (state.get("session") or {}).get("character_id")
    return universe_id, character_id


def _new_session(
    http: requests.Session,
    base_url: str,
    universe_id: str,
    character_id: str | None,
    title: str,
) -> str:
    """Create a fresh dice-mode play session bound to an existing universe + PC."""
    created = _api(
        http,
        "POST",
        base_url,
        "/chat",
        json={
            "title": title,
            "mode": "autonomous_gm",
            "universe_id": universe_id,
            "character_id": character_id,
            "controlled_character_ids": [character_id] if character_id else [],
            "play_mode": "dice_game_system",
            "tone": "grim",
        },
    )
    return created["id"]


def _read_state(http: requests.Session, base_url: str, session_id: str) -> dict[str, Any]:
    return _api(http, "GET", base_url, f"/chat/{session_id}/state")


def _resources_of(working_state: dict[str, Any]) -> dict[str, float]:
    """Flatten resources to {name: value} from whatever shape the WS uses."""
    out: dict[str, float] = {}
    res = working_state.get("resources")
    if isinstance(res, dict):
        for k, v in res.items():
            val = v.get("current") if isinstance(v, dict) else v
            if isinstance(val, (int, float)):
                out[str(k)] = float(val)
    elif isinstance(res, list):
        for item in res:
            if isinstance(item, dict):
                name = item.get("name") or item.get("label")
                val = item.get("current", item.get("value"))
                if name is not None and isinstance(val, (int, float)):
                    out[str(name)] = float(val)
    return out


def _conditions_of(working_state: dict[str, Any]) -> list[str]:
    conds = working_state.get("conditions") or []
    out: list[str] = []
    for c in conds:
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, dict):
            out.append(str(c.get("name") or c.get("label") or c))
    return out


def _canon_count(http: requests.Session, base_url: str, universe_id: str | None) -> int:
    if not universe_id:
        return 0
    try:
        state = _api(http, "GET", base_url, f"/universes/{universe_id}/state")
    except Exception:  # noqa: BLE001
        return 0
    ents = state.get("entities") if isinstance(state, dict) else None
    if isinstance(ents, list):
        return len(ents)
    if isinstance(state, dict) and isinstance(state.get("entity_count"), int):
        return state["entity_count"]
    return 0


# --------------------------------------------------------------------------- #
# Player turn generation
# --------------------------------------------------------------------------- #
def _llm_actor_turn(history: list[tuple[str, str]], goal: str, model: str) -> str:
    if litellm is None:
        raise RuntimeError("litellm not installed; cannot run --mode llm_actor")
    convo = "\n\n".join(f"{spk}: {txt}" for spk, txt in history[-8:])
    resp = litellm.completion(
        model=_normalize_player_model(model),
        temperature=0.7,
        max_tokens=120,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are the PLAYER in a solo dark-fantasy RPG. Pursue your current "
                    "GOAL, but react truthfully to what the GM just described — if the GM "
                    "changes the situation, adapt instead of ignoring it. Reply with ONLY "
                    "your next action in 1-2 sentences. Never narrate outcomes or write for "
                    "the GM."
                ),
            },
            {
                "role": "user",
                "content": f"Recent transcript:\n{convo}\n\nYour current GOAL: {goal}\n\nWrite your next action.",
            },
        ],
    )
    return _extract_text(resp) or goal


def _next_player_text(
    mode: str,
    phase: str | None,
    history: list[tuple[str, str]],
    intent: str,
    player_model: str | None,
) -> str:
    # Always satisfy character creation deterministically so the arc lines up.
    if phase in {"awaiting_character", "char_creation"}:
        return CHAR_CREATION_ACCEPT
    if mode == "llm_actor":
        if not player_model:
            raise RuntimeError("--player-model is required for --mode llm_actor")
        return _llm_actor_turn(history, intent, player_model)
    return intent  # scripted


# --------------------------------------------------------------------------- #
# Run one pass
# --------------------------------------------------------------------------- #
def run_pass(
    base_url: str,
    mode: str,
    *,
    session_id: str,
    universe_id: str,
    character_id: str | None,
    seed: str,
    arc: list[str],
    player_model: str | None,
    max_turns: int,
) -> PassResult:
    http = requests.Session()
    canon_before = _canon_count(http, base_url, universe_id)
    result = PassResult(
        mode=mode,
        session_id=session_id,
        universe_id=universe_id,
        character_id=character_id,
        seed=seed,
        canon_before=canon_before,
    )

    history: list[tuple[str, str]] = []
    prev_resources: dict[str, float] = {}
    prev_conditions: set[str] = set()
    prev_xp = 0
    prev_success_len = 0
    intent_cursor = 0

    for turn_index in range(max_turns):
        intent, player_text, phase = "?", "", None
        try:
            state = _read_state(http, base_url, session_id)
            phase = (state.get("session") or {}).get("phase")

            # Char-creation turns don't consume an arc beat.
            if phase in {"awaiting_character", "char_creation"}:
                intent = "(character creation)"
            else:
                if intent_cursor >= len(arc):
                    break
                intent = arc[intent_cursor]
                intent_cursor += 1

            player_text = _next_player_text(mode, phase, history, intent, player_model)
            history.append(("PLAYER", player_text))

            t0 = time.time()
            reply = _api(http, "POST", base_url, f"/chat/{session_id}/send", json={"content": player_text})
            latency = time.time() - t0
            gm_text = reply.get("content", "")
            history.append(("GM", gm_text))

            # Read mechanical state *after* the turn settles.
            post = _read_state(http, base_url, session_id)
            ws = post.get("latest_working_state") or {}
            meta = post.get("latest_gm_metadata") or {}
            success_levels = post.get("recent_success_levels") or []

            resources = _resources_of(ws)
            conditions = _conditions_of(ws)
            xp_now = int(ws.get("xp", 0) or 0)

            # Only attribute a success level to THIS turn if the rolling list grew —
            # otherwise we'd repeat the prior turn's level on narrative-only turns.
            this_success = (
                str(success_levels[-1])
                if success_levels and len(success_levels) > prev_success_len
                else None
            )
            resource_deltas = {
                k: round(resources[k] - prev_resources.get(k, resources[k]), 2)
                for k in resources
                if k in prev_resources and resources[k] != prev_resources[k]
            }
            conditions_added = sorted(set(conditions) - prev_conditions)
            gl = gm_text.lower()
            # A real choice prompt, not just any atmospheric '?' in the prose.
            offered_choice = any(
                kw in gl for kw in ("do you", "will you", "which ", "what do you", "choose")
            )

            result.turns.append(
                TurnObservation(
                    index=turn_index + 1,
                    player_intent=intent,
                    player_text=player_text,
                    gm_text=gm_text,
                    latency_s=round(latency, 1),
                    phase=phase,
                    success_level=this_success,
                    working_state=ws,
                    gm_effects=meta.get("effects") or [],
                    resource_deltas=resource_deltas,
                    conditions_added=conditions_added,
                    xp_gained=max(0, xp_now - prev_xp),
                    offered_choice=offered_choice,
                    fallback=any(m in gl for m in FALLBACK_MARKERS),
                )
            )

            prev_resources = resources or prev_resources
            prev_conditions = set(conditions)
            prev_xp = xp_now
            prev_success_len = len(success_levels)
        except Exception as exc:  # noqa: BLE001
            # Heuristic tool: never lose the partial log to one bad turn (a 500,
            # a timeout, a fallback). Record the failure and stop the pass.
            result.turns.append(
                TurnObservation(
                    index=turn_index + 1,
                    player_intent=intent,
                    player_text=player_text,
                    gm_text=f"[ERROR: {exc}]",
                    latency_s=0.0,
                    phase=phase,
                    success_level=None,
                    working_state={},
                    gm_effects=[],
                    resource_deltas={},
                    conditions_added=[],
                    xp_gained=0,
                    offered_choice=False,
                    fallback=True,
                )
            )
            break

    result.canon_after = _canon_count(http, base_url, universe_id)
    try:
        log = _api(http, "GET", base_url, "/change-log")
        result.change_log_entries = len(log) if isinstance(log, list) else 0
    except Exception:  # noqa: BLE001
        result.change_log_entries = 0
    return result


# --------------------------------------------------------------------------- #
# Judge (optional) + reporting
# --------------------------------------------------------------------------- #
def _run_judge(result: PassResult, judge_model: str) -> dict[str, Any]:
    try:
        # reason: eval_gm_playtest is a sibling module not installed as a package; suppress the optional-import error since the judge is opportunistic and the script tolerates its absence
        from eval_gm_playtest import RUBRIC, judge  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"error": f"judge unavailable: {exc}"}
    transcript = []
    for t in result.turns:
        transcript.append({"role": "player", "text": t.player_text})
        transcript.append({"role": "gm", "text": t.gm_text})
    try:
        scored = judge(transcript, judge_model)
        scored["rubric"] = RUBRIC
        return scored
    except Exception as exc:  # noqa: BLE001
        return {"error": f"judge failed: {exc}"}


def _latencies(result: PassResult) -> list[float]:
    return [t.latency_s for t in result.turns if t.phase not in {"awaiting_character", "char_creation"}]


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else round((s[n // 2 - 1] + s[n // 2]) / 2, 1)


def write_markdown(path: Path, result: PassResult) -> None:
    lat = _latencies(result)
    L = [
        f"# Live Session Observation — `{result.mode}`",
        "",
        f"- **Session**: `{result.session_id}`",
        f"- **Universe**: `{result.universe_id}`  ·  **Character**: `{result.character_id}`",
        f"- **Seed**: {result.seed}",
        f"- **Turns**: {len(result.turns)}",
        f"- **Latency** (play turns): median `{_median(lat)}s`, max `{max(lat) if lat else 0}s`",
        f"- **Canon entities**: {result.canon_before} → {result.canon_after} "
        f"(+{result.canon_after - result.canon_before})",
        f"- **Change-log entries**: {result.change_log_entries}",
    ]
    if result.judge and "scores" in result.judge:
        scores = result.judge["scores"]
        avg = round(sum(scores.values()) / len(scores), 2) if scores else 0
        L += ["", "## Judge rubric", "", f"**Average: {avg}/5**", ""]
        for k, v in scores.items():
            L.append(f"- {k}: **{v}/5**")
        if result.judge.get("justification"):
            L += ["", f"> {result.judge['justification']}"]
    L += ["", "---", ""]

    for t in result.turns:
        L.append(f"## Turn {t.index} — `{t.phase}`")
        L.append("")
        if t.player_intent != t.player_text:
            L.append(f"*intent:* {t.player_intent}")
            L.append("")
        L.append(f"**PLAYER:** {t.player_text}")
        L.append("")
        L.append(f"**GM** _(success={t.success_level}, {t.latency_s}s):_")
        L.append("")
        L.append(t.gm_text.strip())
        L.append("")
        signals = []
        if t.resource_deltas:
            signals.append(f"resource Δ: `{t.resource_deltas}`")
        if t.conditions_added:
            signals.append(f"conditions+: `{t.conditions_added}`")
        if t.xp_gained:
            signals.append(f"xp +{t.xp_gained}")
        if t.gm_effects:
            signals.append(f"effects: `{t.gm_effects}`")
        if t.offered_choice:
            signals.append("offered choice")
        if t.fallback:
            signals.append("⚠️ FALLBACK")
        if signals:
            L.append("> " + "  ·  ".join(signals))
            L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


def _observation_dict(result: PassResult) -> dict[str, Any]:
    lat = _latencies(result)
    return {
        "mode": result.mode,
        "session_id": result.session_id,
        "universe_id": result.universe_id,
        "character_id": result.character_id,
        "seed": result.seed,
        "turn_count": len(result.turns),
        "latency_median_s": _median(lat),
        "latency_max_s": max(lat) if lat else 0,
        "canon_entities_delta": result.canon_after - result.canon_before,
        "change_log_entries": result.change_log_entries,
        "turns_with_resource_change": sum(1 for t in result.turns if t.resource_deltas),
        "turns_with_condition_change": sum(1 for t in result.turns if t.conditions_added),
        "turns_with_resources_present": sum(1 for t in result.turns if _resources_of(t.working_state)),
        # True = the mechanical layer seeded resources but NOTHING ever changed
        # them (the "HP doesn't decrement from combat" gap).
        "resources_seeded_but_static": (
            any(_resources_of(t.working_state) for t in result.turns)
            and not any(t.resource_deltas for t in result.turns)
        ),
        "total_xp_gained": sum(t.xp_gained for t in result.turns),
        "distinct_success_levels": sorted({t.success_level for t in result.turns if t.success_level}),
        "turns_offering_choice": sum(1 for t in result.turns if t.offered_choice),
        "fallback_count": sum(1 for t in result.turns if t.fallback),
        "mechanical_engaged": any(t.resource_deltas or t.conditions_added or t.xp_gained for t in result.turns),
        "judge": result.judge,
        "turns": [
            {
                "index": t.index,
                "phase": t.phase,
                "intent": t.player_intent,
                "player_text": t.player_text,
                "success_level": t.success_level,
                "latency_s": t.latency_s,
                "resource_deltas": t.resource_deltas,
                "conditions_added": t.conditions_added,
                "xp_gained": t.xp_gained,
                "offered_choice": t.offered_choice,
                "working_state": t.working_state,
            }
            for t in result.turns
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument(
        "--mode",
        choices=["scripted", "llm_actor", "both"],
        default="both",
        help="Which player pass(es) to run (default: both, from identical seeds)",
    )
    ap.add_argument(
        "--bootstrap",
        choices=["demo", "quick"],
        default="demo",
        help="demo = curated Millhaven (engages mechanical layer); quick = LLM world from --seed (narrative only)",
    )
    ap.add_argument("--seed", default=DEFAULT_SEED, help="World seed (quick bootstrap only)")
    ap.add_argument("--turns", type=int, default=8, help="Max sends per pass (incl. char-creation)")
    ap.add_argument("--player-model", default=os.getenv("MONITOR_PLAYTEST_MODEL"))
    ap.add_argument("--judge-model", default=os.getenv("GM_EVAL_JUDGE", "gemini/gemini-2.5-flash"))
    ap.add_argument("--no-judge", action="store_true", help="Skip the LLM-judge rubric")
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    modes = ["scripted", "llm_actor"] if args.mode == "both" else [args.mode]
    observations: list[dict[str, Any]] = []

    # Prepare a ready-to-play session per pass, all sharing ONE universe so the
    # passes start from identical canon. In demo mode each pass gets its own
    # seeded session from the idempotent demo-world (shared Millhaven); in quick
    # mode we build the universe once and add a session per pass.
    http = requests.Session()
    health = _api(http, "GET", args.api_url, "/health")
    if health.get("status") != "ok":
        print(f"backend unhealthy: {health}", file=sys.stderr)
        return 1

    print(f"bootstrapping controlled universe ({args.bootstrap}, shared by all passes)...")
    sessions: dict[str, tuple[str, str, str | None]] = {}  # mode -> (session, universe, char)
    if args.bootstrap == "quick":
        universe_id, character_id = _bootstrap_universe(http, args.api_url, args.seed, "quick")
        for mode in modes:
            sid = _new_session(http, args.api_url, universe_id, character_id, f"observe-{mode}")
            sessions[mode] = (sid, universe_id, character_id)
    else:
        for mode in modes:
            demo = _api(http, "POST", args.api_url, "/forge/demo-world?start_playing=true", json={})
            uid = demo.get("universe_id")
            sid = demo.get("session_id")
            if not sid:
                print(f"demo-world returned no session_id: {demo}", file=sys.stderr)
                return 1
            cid = (_api(http, "GET", args.api_url, f"/chat/{sid}/state").get("session") or {}).get("character_id")
            sessions[mode] = (sid, uid, cid)
    any_uni = next(iter(sessions.values()))[1]
    print(f"  universe: {any_uni}")

    for mode in modes:
        sid, uid, cid = sessions[mode]
        print(f"\n=== PASS: {mode} (session {sid}, character {cid}) ===")
        result = run_pass(
            args.api_url,
            mode,
            session_id=sid,
            universe_id=uid,
            character_id=cid,
            seed=args.seed,
            arc=DEFAULT_ARC,
            player_model=args.player_model,
            max_turns=args.turns,
        )
        if not args.no_judge:
            print("  judging transcript...")
            result.judge = _run_judge(result, args.judge_model)
        md_path = out_dir / f"observe_{mode}_{stamp}.md"
        write_markdown(md_path, result)
        obs = _observation_dict(result)
        obs["log_file"] = str(md_path)
        observations.append(obs)

        print(f"  session:        {result.session_id}")
        print(f"  turns:          {len(result.turns)}")
        print(f"  latency median: {obs['latency_median_s']}s (max {obs['latency_max_s']}s)")
        print(f"  mechanical:     engaged={obs['mechanical_engaged']} "
              f"(res Δ turns={obs['turns_with_resource_change']}, "
              f"cond turns={obs['turns_with_condition_change']}, "
              f"xp={obs['total_xp_gained']})")
        print(f"  success levels: {obs['distinct_success_levels']}")
        print(f"  canon Δ:        +{obs['canon_entities_delta']} entities")
        print(f"  fallbacks:      {obs['fallback_count']}")
        if result.judge.get("scores"):
            s = result.judge["scores"]
            print(f"  judge avg:      {round(sum(s.values())/len(s), 2)}/5")
        print(f"  log:            {md_path}")

    json_path = out_dir / f"observe_summary_{stamp}.json"
    json_path.write_text(json.dumps(observations, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSummary JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
