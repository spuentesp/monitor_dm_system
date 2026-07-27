#!/usr/bin/env python3
"""Quantitative analysis of every full-loop harness transcript.

Reads every JSON in tests/e2e/logs/full_loop/ and emits a CSV + a
human-readable summary grouped by scenario × mode × driver.

Usage: python scripts/analyze_full_loop_logs.py
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

LOG_DIR = Path("tests/e2e/logs/full_loop")


def load_json(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text())


def path_label(p: Path) -> str:
    return p.stem.replace("full_loop_", "")


def classify(name: str) -> tuple[str, str, str]:
    """Map filename → (mode, scenario, system)."""
    mode = (
        "create-world" if "_new_" in name
        else "resume" if "_resume_" in name
        else "pick-world"
    )
    # Filename: full_loop_<scenario>_<mode>_<stamp>.json or
    #           full_loop_<scenario>_<UTC>.json (older).
    parts = name.split("_")
    if "_new_" in name or "_resume_" in name or "_pick_" in name:
        scenario = parts[1] + "_" + parts[2]  # vtm_primogen
    else:
        scenario = "_".join(parts[1:-1])  # older format
    return mode, scenario, "vtm" if "vtm" in name else "dis"


def summarize_one(name: str, data: dict[str, Any]) -> dict[str, Any]:
    mode, scenario, system = classify(name)
    # New schema has scene_runs (list of scenes); old schema has top-level
    # turns (single scene). Normalize.
    if "scene_runs" in data:
        scenes = data.get("scene_runs") or []
        universe_id = data.get("universe_id", "?")
        story_id = data.get("story_id", "?")
        world_created = data.get("world_created")
    else:
        scenes = [{
            "scene_index": 0,
            "scene_id": data.get("scene_id"),
            "turns": data.get("turns", []),
        }]
        universe_id = "?"
        story_id = data.get("story_id", "?")
        world_created = None

    all_turns = [t for s in scenes for t in s.get("turns", [])]
    n_scenes = len(scenes)
    n_turns = len(all_turns)
    fallback = sum(1 for t in all_turns if t.get("fallback_used"))
    fallback_rate = (fallback / n_turns) if n_turns else 0.0
    gm_lat = [t.get("gm_latency_ms", 0) for t in all_turns if t.get("gm_latency_ms")]
    pl_lat = [t.get("player_latency_ms", 0) for t in all_turns if t.get("player_latency_ms")]
    coh = [t.get("coherence_overlap", 0) for t in all_turns]
    scripted_turns = sum(1 for t in all_turns if t.get("player_source") == "scripted")
    llm_turns = sum(1 for t in all_turns if t.get("player_source") == "llm")
    n_unique_scenes = len({s.get("scene_id") for s in scenes if s.get("scene_id")})

    def ms(xs):
        return sum(xs) / len(xs) if xs else 0.0

    return {
        "filename": name,
        "mode": mode,
        "scenario": scenario,
        "system": system,
        "universe_id": universe_id,
        "story_id": story_id,
        "world_created_this_run": world_created,
        "scenes_in_run": n_scenes,
        "unique_scene_ids": n_unique_scenes,
        "turns": n_turns,
        "scripted_player_turns": scripted_turns,
        "llm_player_turns": llm_turns,
        "fallback_turns": fallback,
        "fallback_rate": round(fallback_rate, 3),
        "avg_gm_latency_ms": round(ms(gm_lat), 1),
        "max_gm_latency_ms": round(max(gm_lat), 1) if gm_lat else 0,
        "avg_player_latency_ms": round(ms(pl_lat), 1),
        "avg_coherence": round(ms(coh), 2),
        "max_coherence": max(coh) if coh else 0,
        "min_coherence": min(coh) if coh else 0,
    }


def main() -> None:
    rows = []
    for p in sorted(LOG_DIR.glob("*.json")):
        try:
            data = load_json(p)
        except Exception as exc:
            print(f"skip {p}: {exc}")
            continue
        rows.append(summarize_one(path_label(p), data))

    if not rows:
        print("No transcripts to analyze.")
        return

    # CSV
    out_csv = LOG_DIR / "summary.csv"
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"CSV: {out_csv}")

    # Group by (system, scenario, mode) to surface patterns.
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["system"], r["scenario"])].append(r)

    print("\n## Per-run summary (chronological order)\n")
    print(
        f"{'run':<55} {'mode':<13} {'scenes':>5} {'turns':>5} {'scripted':>8} {'llm':>3} "
        f"{'fallbacks':>9} {'avg_gm_ms':>10} {'avg_coh':>9}"
    )
    print("-" * 124)
    for r in rows:
        print(
            f"{r['filename']:<55} {r['mode']:<13} {r['scenes_in_run']:>5} {r['turns']:>5} "
            f"{r['scripted_player_turns']:>8} {r['llm_player_turns']:>3} "
            f"{r['fallback_turns']:>9} {r['avg_gm_latency_ms']:>10.0f} {r['avg_coherence']:>9.2f}"
        )

    print("\n## Per-scenario aggregate\n")
    print(
        f"{'system':<6} {'scenario':<16} {'runs':>4} {'total_turns':>11} "
        f"{'total_fb':>9} {'fb_rate':>7} {'avg_gm_ms':>10} {'avg_coh':>9}"
    )
    print("-" * 80)
    for (sys_name, sc), runs in sorted(groups.items()):
        t = sum(r["turns"] for r in runs)
        f = sum(r["fallback_turns"] for r in runs)
        rate = f / t if t else 0.0
        gm = sum(r["avg_gm_latency_ms"] * r["turns"] for r in runs) / t if t else 0.0
        coh = sum(r["avg_coherence"] * r["turns"] for r in runs) / t if t else 0.0
        print(
            f"{sys_name:<6} {sc:<16} {len(runs):>4} {t:>11} {f:>9} "
            f"{rate:>7.1%} {gm:>10.0f} {coh:>9.2f}"
        )

    # Failure analysis: which turns were the fallback ones?
    print("\n## Failure analysis (which turns fell back)\n")
    for p in sorted(LOG_DIR.glob("*.json")):
        data = load_json(p)
        if "scene_runs" in data:
            scenes = data.get("scene_runs") or []
        else:
            scenes = [{"scene_id": data.get("scene_id"), "turns": data.get("turns", [])}]
        for si, scene in enumerate(scenes):
            for t in scene.get("turns", []):
                if t.get("fallback_used"):
                    print(
                        f"  {path_label(p):<55} scene#{si} turn#{t['index']}: "
                        f"player='{(t['player_text'] or '')[:60]}' "
                        f"gm='{(t.get('gm_narrative_text') or '')[:60]}'"
                    )


if __name__ == "__main__":
    main()
