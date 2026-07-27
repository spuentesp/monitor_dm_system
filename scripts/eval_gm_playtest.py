#!/usr/bin/env python
"""GM-quality eval harness (T-095).

Drives (or loads) a short autonomous-GM transcript and scores it with an
LLM judge against a fixed rubric — canon-consistency, continuity,
contradiction-freeness, pacing, and player-agency (0-5 each). Writes a JSON
report under ``docs/testing/`` and prints the rubric. This is the instrument
that turns "is the GM any good?" into a tracked number across later changes.

Usage:
    uv run python scripts/eval_gm_playtest.py                 # fresh demo, 6 turns
    uv run python scripts/eval_gm_playtest.py --session <id>  # score an existing session
    uv run python scripts/eval_gm_playtest.py --turns 8

Requires: the dockerized stack up (for the transcript) and GOOGLE_API_KEY
(or set --judge-model / the matching key) for the judge.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = os.getenv("MONITOR_API", "http://localhost:8001/api")

DEFAULT_TURNS = [
    "I step into the Millhaven Inn and ask Barnaby what happened to Elder Magda.",
    "I press him about the Shadow Cabal — does he know where they meet?",
    "I head to the old cemetery to find the freshly disturbed grave.",
    "I follow the drag marks leading away from the crypt.",
    "A cloaked figure blocks my path in the fog; I demand they identify themselves.",
    "I make my move to end the threat to Millhaven tonight.",
]

RUBRIC = {
    "canon_consistency": "Does the GM respect established canon (named NPCs, places, axioms) without inventing contradictions?",
    "continuity": "Does each turn build on prior turns rather than resetting or forgetting?",
    "contradiction_freeness": "Is the narrative internally consistent (no self-contradiction across turns)?",
    "pacing": "Does tension build sensibly — neither stalling nor rushing to resolution?",
    "player_agency": "Does the GM honor the player's stated actions instead of railroading or ignoring them?",
    # Soft dimensions for heuristic session observation (live_session_observe.py).
    "narration_quality": "Is the prose vivid and well-voiced (sensory, distinctive, in-genre) rather than flat or generic?",
    "adaptivity": "Does the GM react to and reshape what the player does — offering real choices and pushing back — rather than rubber-stamping every action?",
    "consequence_carry": "Does a decision or outcome in an earlier turn visibly change the world or situation in a later turn?",
    "mechanical_engagement": "Do dice/rolls, HP/resources, or conditions actually surface in the fiction, or is it pure prose with no mechanical stakes?",
}


def post(path: str, body: dict, timeout: int = 200) -> dict:
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(path: str, timeout: int = 60) -> dict | list:
    with urllib.request.urlopen(API + path, timeout=timeout) as r:
        return json.loads(r.read())


def build_transcript(session_id: str | None, n_turns: int) -> tuple[str, list[dict]]:
    if session_id is None:
        demo = post("/forge/demo-world?start_playing=true", {}, timeout=90)
        session_id = demo["session_id"]
        print(f"fresh demo session: {session_id}")
        for i, t in enumerate(DEFAULT_TURNS[:n_turns], 1):
            t0 = time.time()
            post(f"/chat/{session_id}/send", {"content": t})
            print(f"  played turn {i} ({time.time()-t0:.0f}s)")
    msgs = get(f"/chat/{session_id}/messages")
    turns = []
    for m in msgs:
        role = m.get("role")
        if role in ("player", "user"):
            turns.append({"role": "player", "text": m.get("content", "")})
        elif role in ("gm", "assistant"):
            turns.append({"role": "gm", "text": m.get("content", "")})
    return session_id, turns


def judge(transcript: list[dict], model: str) -> dict:
    import litellm

    convo = "\n\n".join(f"[{t['role'].upper()}] {t['text']}" for t in transcript if t["text"])
    rubric_lines = "\n".join(f"- {k}: {v}" for k, v in RUBRIC.items())
    prompt = (
        "You are a strict tabletop-RPG GM evaluator. Score the following solo-play "
        "transcript on each rubric dimension from 0 (terrible) to 5 (excellent). "
        "Be critical and specific.\n\n"
        f"RUBRIC:\n{rubric_lines}\n\n"
        f"TRANSCRIPT:\n{convo}\n\n"
        "Respond with ONLY a JSON object: "
        '{\"scores\": {\"canon_consistency\": int, \"continuity\": int, '
        '\"contradiction_freeness\": int, \"pacing\": int, \"player_agency\": int}, '
        '\"justification\": \"2-3 sentences\"}.'
    )
    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.0,
    )
    text = resp["choices"][0]["message"]["content"]
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default=None)
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--judge-model", default=os.getenv("GM_EVAL_JUDGE", "gemini/gemini-2.5-flash"))
    args = ap.parse_args()

    session_id, transcript = build_transcript(args.session, args.turns)
    gm_turns = [t for t in transcript if t["role"] == "gm" and t["text"]]
    print(f"\ntranscript: {len(transcript)} messages ({len(gm_turns)} GM turns)")

    result = judge(transcript, args.judge_model)
    scores = result.get("scores", {})
    avg = sum(scores.values()) / len(scores) if scores else 0.0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "judge_model": args.judge_model,
        "gm_turns": len(gm_turns),
        "scores": scores,
        "average": round(avg, 2),
        "justification": result.get("justification", ""),
        "rubric": RUBRIC,
    }

    out_dir = Path(__file__).resolve().parent.parent / "docs" / "testing"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"gm_eval_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2))

    print("\n=== GM QUALITY RUBRIC ===")
    for k, v in scores.items():
        print(f"  {k:<24} {v}/5")
    print(f"  {'AVERAGE':<24} {avg:.2f}/5")
    print(f"\njustification: {report['justification']}")
    print(f"\nreport: {out_path}")


if __name__ == "__main__":
    main()
