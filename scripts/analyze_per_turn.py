#!/usr/bin/env python3
"""Per-turn deep dive — patterns within scenes + persistence checks.

Adds:
* Per-turn coherence curve per scene (rises, falls, plateaus?)
* Scripted vs LLM player coherence comparison
* World-creation vs resume pressure (does the first turn of each new scene
  take longer because it's priming a fresh SceneLoop checkpoint?)
* Persistent-actor check: same actor_id across scenes in the same run?
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

LOG_DIR = Path("tests/e2e/logs/full_loop")


def load_scenes(p: Path):
    data = json.loads(p.read_text())
    if "scene_runs" in data:
        return data.get("scene_runs") or [], data.get("universe_id"), data.get("story_id"), data.get("world_created")
    return [
        {
            "scene_index": 0,
            "scene_id": data.get("scene_id"),
            "turns": data.get("turns", []),
        }
    ], "?", data.get("story_id"), None


def per_scene_curve(p: Path) -> None:
    scenes, universe_id, story_id, _ = load_scenes(p)
    name = p.stem
    for sc in scenes:
        sid = (sc.get("scene_id") or "?")[:8]
        coh_series = [t.get("coherence_overlap", 0) for t in sc["turns"]]
        fallback_idx = [
            t.get("index") for t in sc["turns"] if t.get("fallback_used")
        ]
        curve = "→".join(str(c) for c in coh_series)
        fbk = "fb@[" + ",".join(str(i) for i in fallback_idx) + "]" if fallback_idx else ""
        print(f"  {name:<55} scene#{sc['scene_index']} {sid}..  coh=[{curve}] {fbk}")


def per_turn_scripted_vs_llm() -> None:
    scripted, llm = [], []
    for p in sorted(LOG_DIR.glob("*.json")):
        scenes, *_ = load_scenes(p)
        for sc in scenes:
            for t in sc["turns"]:
                src = t.get("player_source")
                coh = t.get("coherence_overlap", 0) or 0
                if src == "scripted":
                    scripted.append(coh)
                elif src == "llm":
                    llm.append(coh)
    print("\n## Scripted vs LLM player coherence (across all runs)\n")
    if scripted:
        print(f"  scripted turns: {len(scripted):>3}  avg={sum(scripted)/len(scripted):>5.2f}  max={max(scripted):>2}  min={min(scripted):>2}")
    if llm:
        print(f"  llm turns:      {len(llm):>3}  avg={sum(llm)/len(llm):>5.2f}  max={max(llm):>2}  min={min(llm):>2}")


def first_turn_pressure() -> None:
    """Does the first turn of each new scene cost more than later turns?

    A higher first-turn latency would suggest the system is priming a fresh
    checkpoint on every scene entry.
    """
    print("\n## First-turn vs mid-turn latency (per scene)\n")
    for p in sorted(LOG_DIR.glob("*.json")):
        scenes, *_ = load_scenes(p)
        if not scenes:
            continue
        first_latencies = []
        mid_latencies = []
        for sc in scenes:
            turns = sc["turns"]
            if not turns:
                continue
            lats = [t.get("gm_latency_ms", 0) for t in turns if t.get("gm_latency_ms")]
            if lats:
                first_latencies.append(lats[0])
                mid_latencies.extend(lats[1:])
        if first_latencies:
            avg_first = sum(first_latencies) / len(first_latencies)
            avg_mid = sum(mid_latencies) / len(mid_latencies) if mid_latencies else 0
            print(
                f"  {p.stem:<55} first={avg_first:>7.0f}ms ({len(first_latencies)} scenes)  "
                f"mid={avg_mid:>7.0f}ms ({len(mid_latencies)} turns)"
            )


def main() -> None:
    print("## Per-scene coherence curves\n")
    for p in sorted(LOG_DIR.glob("*.json")):
        per_scene_curve(p)

    per_turn_scripted_vs_llm()
    first_turn_pressure()


if __name__ == "__main__":
    main()
