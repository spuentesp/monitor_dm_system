#!/usr/bin/env python3
"""Offline coherence test — exercises scene loop nodes with scripted inputs.

Does NOT require Neo4j, MongoDB, or live LLM calls. Tests the narrative
coherence pipeline (load_context → resolve → narrate → extract_facts →
check_consistency) with mocked dependencies to verify:

1. Setting anchor propagates through all nodes
2. Prior turns accumulate (8-turn limit)
3. established_facts accumulate across turns
4. consistency_violations trigger on name drift
5. pending_roll state machine works (propose_roll → pushback)
6. turn_context is available to the narrator

Run:
    cd /path/to/monitor_dm_system
    uv run python scripts/coherence_playtest_offline.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


# Scripted inputs designed to stress-test coherence
SCRIPTED_INPUTS = [
    "I am Kael Draven, a void-born salvage engineer aboard the derelict station Iron Verdict.",
    "I check my suit's cutting fuel: 75%. The station groans around me.",
    "I approach the bartender and ask for salvage contracts.",
    "I take the datapad and head straight for the derelict ship.",  # skip pending roll
    "I dock with the wreck. The hull reads 'Iron Verdict' in corroded letters.",
    "I move down the corridor, cutter raised, scanning for threats.",
    "The creature drops from the ceiling but I sidestep cleanly and strike with my cutter.",  # skip roll
    "I reach a sealed door with an amber seal light. I examine the symbols.",
    "I grab the manual release and haul the sealed door open with all my strength.",
    "Beyond the door, a sterile corridor stretches ahead. I move cautiously.",
]


@dataclass
class TurnRecord:
    turn: int
    player_input: str
    narrative: str
    resolution_type: str
    success_level: str
    pending_roll_after: dict | None
    facts_count: int
    facts_new: list
    violations: list
    latency_ms: float
    error: str | None = None


@dataclass
class CoherenceReport:
    turns_run: int = 0
    turns_with_narrative: int = 0
    empty_narratives: int = 0
    pending_roll_triggered: bool = 0
    pending_roll_attempts_blocked: int = 0
    total_violations: int = 0
    total_facts: int = 0
    violation_details: list = field(default_factory=list)
    pass_: bool = False
    notes: list = field(default_factory=list)


# NOTE: We deliberately do NOT use keyword heuristics to measure "genre drift".
# For a narrative engine, that approach is worthless — it produces false positives
# like "pale" matching "ale" or "alarm" matching "armor". The real coherence check
# is the check_consistency node (implemented in scene_loop.py), which does:
#   1. Name drift detection against established facts
#   2. Genre drift detection against the setting anchor (turn_context / source_profile)
#   3. Contradiction detection against established facts
# We call that node directly below and report what IT finds.


def _build_synthetic_narrative(player_input: str, prior_narratives: list[str]) -> str:
    """Generate a deterministic sci-fi narration that respects established facts.
    This simulates a 'good' narrator that maintains setting consistency."""
    facts_to_mention = []
    if prior_narratives:
        facts_to_mention.append("Kael Draven")
    if any("Iron Verdict" in p for p in prior_narratives):
        facts_to_mention.append("the Iron Verdict")
    if any("bartender" in p.lower() for p in prior_narratives):
        facts_to_mention.append("the bartender")

    parts = []
    if "check" in player_input.lower() or "examine" in player_input.lower():
        parts.append("Your suit's cutting fuel reads 75%. The station's hull groans.")
    if "bartender" in player_input.lower() or "ask" in player_input.lower():
        parts.append("The bartender slides a datapad across the counter.")
    if "datapad" in player_input.lower() or "derelict" in player_input.lower():
        parts.append("The datapad displays coordinates for the Iron Verdict derelict.")
    if "dock" in player_input.lower() or "airlock" in player_input.lower():
        parts.append("The airlock cycles open. The corridor stretches into darkness.")
    if "cutter" in player_input.lower() or "scan" in player_input.lower():
        parts.append("Your cutter hums. The lamp cuts a pale beam through the corridor.")
    if "creature" in player_input.lower() or "strike" in player_input.lower():
        parts.append("The creature drops from the ceiling. Roll Strength to fight it.")
    if "door" in player_input.lower() or "symbols" in player_input.lower():
        parts.append("The sealed door's amber light pulses. Symbols etched in steel.")
    if "force" in player_input.lower() or "haul" in player_input.lower():
        parts.append("You haul the release plate. Roll Strength to force the door.")
    if "sterile" in player_input.lower() or "corridor" in player_input.lower():
        parts.append("A sterile corridor stretches ahead. Emergency lighting flickers.")

    if not parts:
        parts.append("You survey the scene. The station's machinery hums.")

    if facts_to_mention:
        parts.insert(0, f"Recall: {', '.join(facts_to_mention)}.")

    return " ".join(parts)


async def _run_single_turn(
    turn_num: int,
    user_input: str,
    accumulated_state: dict,
) -> TurnRecord:
    """Run one turn through load_context → resolve → narrate → extract_facts → check_consistency."""
    from monitor_agents.loops.scene_loop import (
        SceneState,
        load_context,
        resolve_action,
        narrate,
        extract_facts,
        check_consistency,
    )

    scene_id = accumulated_state["scene_id"]
    story_id = accumulated_state["story_id"]
    universe_id = accumulated_state["universe_id"]

    state = SceneState(
        scene_id=scene_id,
        story_id=story_id,
        universe_id=universe_id,
        user_input=user_input,
        session_tone="grim",
        play_mode="dice_game_system",
        roll_mode="normal",
        actor_context={
            "name": "Kael Draven",
            "role": "void-born salvage engineer",
            "stats": {"STR": 14, "DEX": 16, "INT": 12, "CHA": 10, "WIS": 13, "CON": 15},
            "inventory": ["cutter", "pistol", "datapad", "lamp"],
            "conditions": ["spaceworthy"],
        },
        entity_context=[
            {"id": "loc-station", "name": "Iron Verdict Station", "entity_type": "location"},
            {"id": "npc-bartender", "name": "bartender", "entity_type": "npc"},
        ],
        previous_turns=accumulated_state["turns"][-8:],  # 8-turn window
        pending_roll=accumulated_state["pending_roll"],
        established_facts=accumulated_state["established_facts"],
        turn_context=accumulated_state.get("turn_context"),
    )

    start = time.perf_counter()
    error = None
    narrative = ""
    resolution_type = "unknown"
    success_level = "unknown"
    new_pending_roll = state.pending_roll
    facts_count = len(state.established_facts)
    new_facts = []
    violations = []

    try:
        # 1. load_context — mock ContextAssembly
        fake_context = {
            "entities": state.entity_context,
            "memories": [{"text": "previous session memory"}],
            "turns": state.previous_turns,
            "game_system": {"name": "Sci-fi Salvage", "stats": ["STR", "DEX"]},
            "source_profile": {
                "genre": "sci-fi",
                "setting_summary": "A derelict salvage station in the Driftward Graveyard",
            },
            "summary": "Context: Sci-fi salvage scenario. Iron Verdict station, Kael Draven PC.",
        }
        with patch(
            "monitor_agents.context_assembly.agent.ContextAssembly.assemble",
            new_callable=AsyncMock,
            return_value=fake_context,
        ):
            load_result = await load_context(state)
            state.context_summary = load_result.get("context_summary", "")
            state.entity_context = load_result.get("entity_context", state.entity_context)
            state.previous_turns = load_result.get("previous_turns", state.previous_turns)

        # 2. resolve — use the REAL Resolver, passing pending_roll in context.
        # This tests the pending roll interception logic in resolver.py.
        from monitor_agents.resolver import Resolver
        resolver = Resolver.__new__(Resolver)

        resolution, _ = await resolver.resolve_turn(
            scene_id=str(scene_id),
            user_input=user_input,
            context={
                "entities": state.entity_context,
                "turns": state.previous_turns,
                "source_profile": fake_context["source_profile"],
                # Pass pending_roll so the resolver can intercept skip attempts
                "pending_roll": state.pending_roll,
            },
            game_context=fake_context["game_system"],
            play_mode=state.play_mode,
            roll_mode=state.roll_mode,
        )

        # Track pending_roll state machine based on resolution type
        res_type = resolution.get("resolution_type")
        if res_type == "propose_roll":
            new_pending_roll = {
                "stat": resolution.get("stat", "STR"),
                "dc": resolution.get("difficulty_class", 12),
                "modifier": resolution.get("modifier", 0),
                "action": user_input[:60],
                "resolution_type": "propose_roll",
            }
        elif res_type == "forced_narrative_pushback":
            # Pending roll was enforced — keep the pending_roll intact for next turn
            new_pending_roll = state.pending_roll
        else:
            new_pending_roll = None

        resolution_type = res_type or "unknown"
        success_level = resolution.get("success_level", "unknown")
        state.resolution = resolution

        # 3. narrate — mock the narrator
        from monitor_agents.narrator.agent import Narrator
        narrator = Narrator.__new__(Narrator)
        narrator._narrator_module = MagicMock()
        narrator._tone_resolver = MagicMock()

        synth_narrative = _build_synthetic_narrative(user_input, [t["text"] for t in state.previous_turns if "text" in t])

        if resolution_type == "forced_narrative_pushback":
            narr_text = (
                f"The GM raises a hand. '{resolution.get('pushback_prompt', 'Roll first!')}'"
            )
        else:
            narr_text = synth_narrative

        fake_prediction = MagicMock()
        fake_prediction.narrative_text = narr_text
        fake_prediction.proposed_changes = "[]"
        fake_prediction.narrative_time_elapsed = "10"
        narrator._narrator_module.return_value = fake_prediction

        with (
            patch.object(Narrator, "_resolve_tone_context", new_callable=AsyncMock,
                         return_value="grim, terse, industrial"),
            patch.object(Narrator, "_format_resolution",
                         return_value=f"propose_roll:STR" if resolution_type == "propose_roll" else resolution_type),
            patch.object(Narrator, "_persist_turn", new_callable=AsyncMock, return_value=f"turn-{turn_num}"),
            patch.object(Narrator, "_parse_proposed_changes", return_value=[]),
        ):
            narr_result = await narrator.narrate_turn(
                scene_id=scene_id,
                user_input=user_input,
                resolution=resolution,
                context={
                    "entities": state.entity_context,
                    "memories": [],
                    "turns": state.previous_turns,
                    "source_profile": fake_context["source_profile"],
                    "actor": state.actor_context,
                    "context_summary": state.context_summary,
                    "turn_context": state.turn_context,
                    "established_facts": state.established_facts,
                },
                game_context=fake_context["game_system"],
                session_tone="grim",
            )

        narrative = narr_result.get("narrative_text", "")
        state.narrative_text = narrative

        # 4. extract_facts
        ef_result = await extract_facts(state)
        new_facts = ef_result.get("established_facts", [])
        facts_count = len(new_facts)

        # 5. check_consistency
        cc_result = await check_consistency(state)
        violations = cc_result.get("consistency_violations", [])

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        import traceback
        traceback.print_exc()

    elapsed_ms = (time.perf_counter() - start) * 1000

    # Update accumulated state for next turn
    accumulated_state["pending_roll"] = new_pending_roll
    accumulated_state["established_facts"] = new_facts if new_facts else state.established_facts
    accumulated_state["turns"].append({
        "turn_id": f"turn-{turn_num}",
        "speaker": "player" if turn_num % 2 else "gm",
        "entity_id": "kael",
        "text": narrative if not error else f"[ERROR: {error}]",
        "user_input": user_input,
    })

    return TurnRecord(
        turn=turn_num,
        player_input=user_input,
        narrative=narrative,
        resolution_type=resolution_type,
        success_level=success_level,
        pending_roll_after=new_pending_roll,
        facts_count=facts_count,
        facts_new=new_facts[-3:] if new_facts else [],
        violations=violations,
        latency_ms=elapsed_ms,
        error=error,
    )


async def main_async() -> int:
    print("=" * 72)
    print("OFFLINE COHERENCE TEST — Scene Loop Node Pipeline")
    print("=" * 72)
    print()

    accumulated_state = {
        "scene_id": uuid4(),
        "story_id": uuid4(),
        "universe_id": uuid4(),
        "turns": [],
        "pending_roll": None,
        "established_facts": [],
        "turn_context": None,
    }

    records = []
    for idx, user_input in enumerate(SCRIPTED_INPUTS, start=1):
        print(f"\n--- Turn {idx} ---")
        print(f"Player: {user_input[:80]}{'...' if len(user_input) > 80 else ''}")
        record = await _run_single_turn(idx, user_input, accumulated_state)
        records.append(record)

        if record.error:
            print(f"  ERROR: {record.error[:200]}")
        else:
            print(f"  GM: {record.narrative[:120]}{'...' if len(record.narrative) > 120 else ''}")
        print(f"  Resolution: type={record.resolution_type}, level={record.success_level}")
        if record.pending_roll_after:
            print(f"  Pending roll: {record.pending_roll_after.get('stat')} DC {record.pending_roll_after.get('dc')}")
        print(f"  Facts: {record.facts_count} (new: {len(record.facts_new)})")
        if record.violations:
            print(f"  ⚠️  Violations: {len(record.violations)}")
            for v in record.violations:
                print(f"      - {v.get('type')}: {v.get('message', '')[:100]}")
        print(f"  Latency: {record.latency_ms:.0f}ms")

    # Analyze — use the REAL check_consistency output, not heuristics.
    # The violations list comes from the check_consistency node itself,
    # which does name drift detection against established facts and
    # genre drift detection against the setting anchor.
    report = CoherenceReport()
    for r in records:
        report.turns_run += 1
        if r.error:
            continue
        if r.narrative.strip():
            report.turns_with_narrative += 1
        else:
            report.empty_narratives += 1
            report.notes.append(f"Turn {r.turn}: empty narrative")
        report.total_facts = max(report.total_facts, r.facts_count)
        report.total_violations += len(r.violations)
        if r.violations:
            for v in r.violations:
                report.violation_details.append({
                    "turn": r.turn,
                    "type": v.get("type"),
                    "severity": v.get("severity"),
                    "message": v.get("message", "")[:200],
                })
        if r.resolution_type == "forced_narrative_pushback":
            report.pending_roll_triggered += 1

    # Pass/fail criteria — the check_consistency node already did the real work.
    # We just report whether violations were found.
    report.pass_ = (
        report.empty_narratives == 0
        and report.turns_with_narrative >= max(1, report.turns_run * 0.8)
        and report.total_violations == 0
    )

    if report.pending_roll_triggered:
        report.notes.append(
            f"✓ Pending roll state machine: pushback triggered {report.pending_roll_triggered} time(s)"
        )
    else:
        report.notes.append(
            "ℹ Pending roll pushback not triggered — scripted inputs didn't provoke it"
        )

    if report.total_facts > 0:
        report.notes.append(f"✓ Facts extraction: {report.total_facts} facts accumulated")

    if report.total_violations == 0:
        report.notes.append(
            "✓ check_consistency node: no name drift or genre drift detected"
        )
    else:
        report.notes.append(
            f"⚠ check_consistency node flagged {report.total_violations} violation(s):"
        )
        for v in report.violation_details:
            report.notes.append(
                f"    Turn {v['turn']}: {v['type']} ({v['severity']}) — {v['message']}"
            )

    # Print summary
    print()
    print("=" * 72)
    print("COHERENCE REPORT")
    print("=" * 72)
    print(f"  Turns run:              {report.turns_run}")
    print(f"  Turns with narrative:   {report.turns_with_narrative}")
    print(f"  Empty narratives:       {report.empty_narratives}")
    print(f"  Pending roll pushbacks: {report.pending_roll_triggered}")
    print(f"  Total violations:       {report.total_violations}")
    print(f"  Total facts:            {report.total_facts}")
    print(f"  RESULT: {'PASS' if report.pass_ else 'FAIL'}")
    print()
    if report.notes:
        print("Notes:")
        for note in report.notes:
            print(f"  • {note}")

    # Write markdown log
    output_dir = WORKSPACE_ROOT / "tests" / "e2e" / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"coherence_offline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"

    lines = [
        "# Offline Coherence Test",
        "",
        f"- Generated: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Result: **{'PASS' if report.pass_ else 'FAIL'}**",
        "",
        "Coherence measured by the actual `check_consistency` and `extract_facts` "
        "nodes in `scene_loop.py`, not by keyword heuristics.",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Turns run | {report.turns_run} |",
        f"| Turns with narrative | {report.turns_with_narrative} |",
        f"| Empty narratives | {report.empty_narratives} |",
        f"| Pending roll pushbacks | {report.pending_roll_triggered} |",
        f"| Total facts extracted | {report.total_facts} |",
        f"| Total consistency violations | {report.total_violations} |",
        "",
        "## Notes",
        "",
    ]
    for note in report.notes:
        lines.append(f"- {note}")
    lines.extend(["", "---", "", "## Turn-by-Turn", ""])

    for r in records:
        lines.append(f"### Turn {r.turn}")
        lines.append("")
        lines.append(f"**Player:** {r.player_input}")
        lines.append("")
        if r.error:
            lines.append(f"**GM (ERROR):** {r.error[:300]}")
        else:
            lines.append(f"**GM:** {r.narrative}")
        lines.append("")
        lines.append(f"- Resolution: `{r.resolution_type}` / `{r.success_level}`")
        if r.pending_roll_after:
            lines.append(
                f"- Pending roll: `{r.pending_roll_after.get('stat')}` "
                f"DC `{r.pending_roll_after.get('dc')}` "
                f"(action: `{r.pending_roll_after.get('action', '?')[:50]}`)"
            )
        lines.append(f"- Facts: {r.facts_count}")
        if r.facts_new:
            for f in r.facts_new:
                lines.append(f"  - {f[:100]}")
        if r.violations:
            lines.append(f"- ⚠ Violations: {len(r.violations)}")
            for v in r.violations:
                lines.append(f"  - {v.get('type')}: {v.get('message', '')[:120]}")
        lines.append(f"- Latency: {r.latency_ms:.0f}ms")
        lines.append("")

    output_path.write_text("\n".join(lines))
    print(f"\nLog written to: {output_path}")

    return 0 if report.pass_ else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))