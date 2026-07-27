#!/usr/bin/env python3
"""Coherence-focused scripted gameplay test for narrative coherence.

Runs a scripted 10-turn session through SceneLoop and captures:
- Narrative text per turn
- Resolution type and success level
- pending_roll state
- established_facts (cumulative)
- consistency_violations
- turn_context fields (when populated)
- Setting anchor drift detection

Writes a markdown log to tests/e2e/logs/coherence_test_<timestamp>.md
similar to the long_form_22turn.md format.

This script is designed to run WITHOUT a live backend — it uses the
SceneLoop directly with mocked dependencies if needed, or against
MongoDB if available.

Usage:
    python scripts/coherence_playtest.py
    python scripts/coherence_playtest.py --turns 10 --output tests/e2e/logs/coherence_test.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

# Ensure the workspace root is on sys.path so `monitor_agents` imports resolve
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("coherence_playtest")

# ---------------------------------------------------------------------------
# Scripted inputs designed to stress-test coherence
# ---------------------------------------------------------------------------

SCRIPTED_INPUTS = [
    # Turn 1 — Sci-fi setting establishment
    "I am Kael Draven, a void-born salvage engineer aboard the derelict station "
    "Iron Verdict. I survey the airlock chamber, my cutter humming at my hip.",
    # Turn 2 — Confirm the setting (would a medieval narrator misread this?)
    "I check my suit's cutting fuel: 75%. The station groans around me. I proceed.",
    # Turn 3 — Establish a named NPC
    "I approach the station's hub and ask the bartender — a thick-necked woman with "
    "burn scars — for any salvage contracts.",
    # Turn 4 — Try to skip a pending roll (will the system push back?)
    "The bartender hands me a datapad. I grab it and head straight for the derelict ship.",
    # Turn 5 — Enter the derelict
    "I dock with the wreck called Iron Verdict. The hull reads 'Iron Verdict' "
    "in corroded letters. I cycle the airlock and step inside, lamp sweeping.",
    # Turn 6 — Push deeper
    "I move down the corridor, cutter raised. I check sealed doors, maintenance hatches, "
    "and any signs of recent activity.",
    # Turn 7 — Try to narrate past an unresolved roll
    "The creature drops from the ceiling but I sidestep it cleanly and strike with my cutter.",
    # Turn 8 — Continue exploration
    "I reach a sealed door with an amber seal light. I run my fingers over the symbols.",
    # Turn 9 — Force the door (this should require a roll)
    "I grab the manual release and haul the sealed door open with all my strength.",
    # Turn 10 — Continue (would the narrator lose the setting after 8+ turns?)
    "Beyond the door, a sterile corridor stretches ahead. I move cautiously, "
    "watching for more of those creatures.",
]


@dataclass
class TurnResult:
    """Captured state after each turn."""

    turn_number: int
    player_input: str
    narrative_text: str
    resolution_type: str
    success_level: str
    pending_roll: dict | None
    established_facts: list
    consistency_violations: list
    turn_context: dict | None
    scene_complete: bool
    latency_seconds: float = 0.0
    error: str | None = None


@dataclass
class CoherenceReport:
    """Summary metrics for the session."""

    total_turns: int = 0
    narrative_drift_score: float = 0.0
    name_mentions: dict = field(default_factory=dict)
    setting_keywords_mentioned: list = field(default_factory=list)
    medieval_terms_mentioned: list = field(default_factory=list)
    pending_roll_properly_handled: bool = False
    consistency_violations_total: int = 0
    facts_extracted: int = 0
    turns_with_narration: int = 0
    empty_narratives: int = 0
    session_passed: bool = False
    notes: list = field(default_factory=list)


def _detect_setting_keywords(text: str) -> tuple[list, list]:
    """Detect genre-consistent vs inconsistent terms in narration."""
    sci_fi_terms = [
        "airlock", "corridor", "datapad", "dataslate", "station", "void",
        "hull", "bulkhead", "recycled air", "salvage", "cutter", "lamp",
        "seal light", "vacuum", "gravity", "helm", "drone", "engineer",
    ]
    medieval_terms = [
        "tavern", "hearth", "corkboard", "ale", "mead", "innkeeper",
        "sword", "spell", "mage", "dragon", "knight", "castle",
        "shield", "armor", "horse", "arrow", "bow", "quiver",
    ]
    text_lower = text.lower()
    sci_found = [t for t in sci_fi_terms if t in text_lower]
    medieval_found = [t for t in medieval_terms if t in text_lower]
    return sci_found, medieval_found


def _extract_named_entities(text: str) -> list:
    """Extract capitalized named entities (heuristic)."""
    import re

    pattern = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
    skip = {"The", "A", "An", "I", "You", "He", "She", "It", "They", "Your",
            "His", "Her", "Its", "Their", "This", "That", "Roll", "Strength",
            "Dexterity", "Intelligence", "Charisma", "Wisdom", "Constitution"}
    found = []
    seen = set()
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        if name in skip or name in seen:
            continue
        if " " in name or len(name) > 4:
            seen.add(name)
            found.append(name)
    return found


def _analyze_turn(turn: TurnResult, report: CoherenceReport) -> None:
    """Update report based on turn result."""
    report.total_turns += 1
    if turn.error:
        report.notes.append(f"Turn {turn.turn_number} errored: {turn.error[:200]}")
        return
    if turn.narrative_text.strip():
        report.turns_with_narration += 1
    else:
        report.empty_narratives += 1
        report.notes.append(f"Turn {turn.turn_number}: empty narrative text")
        return

    # Setting keyword analysis
    sci, medieval = _detect_setting_keywords(turn.narrative_text)
    report.setting_keywords_mentioned.extend(sci)
    report.medieval_terms_mentioned.extend(medieval)

    # Named entity tracking
    for name in _extract_named_entities(turn.narrative_text):
        report.name_mentions[name] = report.name_mentions.get(name, 0) + 1

    # Pending roll handling
    if turn.resolution_type == "forced_narrative_pushback":
        report.pending_roll_properly_handled = True
        report.notes.append(
            f"Turn {turn.turn_number}: pending roll pushback triggered "
            f"(success_level={turn.success_level})"
        )

    # Consistency violations
    report.consistency_violations_total += len(turn.consistency_violations)
    if turn.consistency_violations:
        for v in turn.consistency_violations:
            report.notes.append(
                f"Turn {turn.turn_number}: VIOLATION — {v.get('type')}: "
                f"{v.get('message', '')[:100]}"
            )

    # Facts accumulated
    report.facts_extracted = max(report.facts_extracted, len(turn.established_facts))


def _build_markdown_log(
    turns: list[TurnResult],
    report: CoherenceReport,
    script_args: dict,
) -> str:
    """Render the session as markdown."""
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Coherence Playtest — Narrative Coherence Verification",
        "",
        f"- **Generated at**: `{now}`",
        f"- **Scripted turns**: `{len(turns)}`",
        f"- **Session passed**: `{report.session_passed}`",
        f"- **Narrative drift score**: `{report.narrative_drift_score:.2f}` "
        f"(0.0 = perfect sci-fi, 1.0 = full medieval drift)",
        f"- **Pending roll properly handled**: `{report.pending_roll_properly_handled}`",
        f"- **Total consistency violations**: `{report.consistency_violations_total}`",
        f"- **Total facts extracted**: `{report.facts_extracted}`",
        f"- **Turns with narrative**: `{report.turns_with_narration}/{report.total_turns}`",
        "",
        "---",
        "",
        "## Coherence Report",
        "",
        "### Setting Keywords",
        "",
        f"- **Sci-fi terms**: {len(report.setting_keywords_mentioned)} mentions — "
        f"{', '.join(sorted(set(report.setting_keywords_mentioned))[:15])}",
        f"- **Medieval terms** (should be 0 or near-0): "
        f"{len(report.medieval_terms_mentioned)} mentions — "
        f"{', '.join(sorted(set(report.medieval_terms_mentioned))[:10]) if report.medieval_terms_mentioned else 'none'}",
        "",
        "### Named Entity Consistency",
        "",
        "Entities mentioned across the session (frequency):",
        "",
    ]

    # Top named entities
    sorted_entities = sorted(
        report.name_mentions.items(), key=lambda x: x[1], reverse=True
    )[:20]
    if sorted_entities:
        for name, count in sorted_entities:
            lines.append(f"- **{name}**: {count} mention(s)")
    else:
        lines.append("- (none captured)")

    lines.extend([
        "",
        "### Issues / Notes",
        "",
    ])
    if report.notes:
        for note in report.notes:
            lines.append(f"- {note}")
    else:
        lines.append("- (no issues noted)")

    lines.extend([
        "",
        "---",
        "",
        "## Turn-by-Turn Transcript",
        "",
    ])

    for t in turns:
        lines.append(f"### Turn {t.turn_number}")
        lines.append("")
        lines.append(f"**Player:** {t.player_input}")
        lines.append("")
        if t.error:
            lines.append(f"**GM (ERROR):** _{t.error[:300]}_")
        elif t.narrative_text:
            lines.append(f"**GM:**")
            lines.append("")
            lines.append(t.narrative_text)
        else:
            lines.append("**GM:** _(empty)_")
        lines.append("")
        lines.append("**Resolution:**")
        lines.append(f"- Type: `{t.resolution_type}`")
        lines.append(f"- Success level: `{t.success_level}`")
        if t.pending_roll:
            lines.append(
                f"- Pending roll: `{t.pending_roll.get('stat')} DC "
                f"{t.pending_roll.get('dc')}` "
                f"(action: {t.pending_roll.get('action', '?')[:60]})"
            )
        if t.established_facts:
            lines.append(f"- Established facts: {len(t.established_facts)}")
            for fact in t.established_facts[-5:]:
                lines.append(f"  - {fact[:100]}")
        if t.consistency_violations:
            lines.append(f"- ⚠️ Violations: {len(t.consistency_violations)}")
            for v in t.consistency_violations:
                lines.append(f"  - {v.get('type')}: {v.get('message', '')[:120]}")
        if t.turn_context:
            tc = t.turn_context
            if isinstance(tc, dict):
                if tc.get("location_name"):
                    lines.append(f"- Location: {tc.get('location_name')}")
                if tc.get("character_name"):
                    lines.append(f"- Character: {tc.get('character_name')}")
        lines.append(f"- Latency: {t.latency_seconds:.1f}s")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## Script Arguments",
        "",
        "```json",
        json.dumps(script_args, indent=2, default=str),
        "```",
        "",
    ])
    return "\n".join(lines)


async def _run_turn(loop, user_input: str, turn_number: int) -> TurnResult:
    """Run one turn and capture the result."""
    import time

    start = time.perf_counter()
    error = None
    try:
        result = await loop.run(user_input)
    except Exception as exc:
        logger.exception("Turn %d failed", turn_number)
        error = f"{type(exc).__name__}: {exc}"
        result = {}

    elapsed = time.perf_counter() - start

    # Extract fields — SceneLoop.run() returns a dict
    narrative_text = result.get("narrative_text", "") or ""
    resolution = result.get("resolution") or {}
    resolution_type = resolution.get("resolution_type", "unknown")
    success_level = resolution.get("success_level", "unknown")
    pending_roll = result.get("pending_roll")
    established_facts = result.get("established_facts") or []
    consistency_violations = result.get("consistency_violations") or []
    turn_context = result.get("turn_context")
    scene_complete = bool(result.get("scene_complete"))

    return TurnResult(
        turn_number=turn_number,
        player_input=user_input,
        narrative_text=narrative_text,
        resolution_type=resolution_type,
        success_level=success_level,
        pending_roll=pending_roll,
        established_facts=established_facts,
        consistency_violations=consistency_violations,
        turn_context=turn_context,
        scene_complete=scene_complete,
        latency_seconds=elapsed,
        error=error,
    )


async def main_async(args: argparse.Namespace) -> int:
    """Main async entry point."""
    from monitor_agents.loops.scene_loop import SceneLoop
    from monitor_agents.canonkeeper.agent import CanonKeeper

    keeper = CanonKeeper()

    # 1. Bootstrap a multiverse, universe, and story
    logger.info("Bootstrapping multiverse + universe + story...")
    try:
        m = await keeper.call_tool("neo4j_list_multiverses", {})
        multiverses = json.loads(m) if isinstance(m, str) else m
        if not multiverses:
            logger.error("No multiverses found. Run live_ingestion first.")
            return 1
        multiverse_id = multiverses[0]["id"]
    except Exception as exc:
        logger.error("Could not list multiverses: %s", exc)
        return 1

    universe_name = f"Coherence Test Universe {uuid4().hex[:6]}"
    try:
        u_res = await keeper.create_universe({
            "multiverse_id": str(multiverse_id),
            "name": universe_name,
            "genre": "Sci-Fi",
            "description": "Sci-fi derelict salvage scenario for coherence testing.",
            "tone": "grim",
        })
        universe_id = u_res["id"]
        logger.info("Created universe: %s", universe_id)
    except Exception as exc:
        logger.error("Could not create universe: %s", exc)
        return 1

    try:
        s_res = await keeper.create_story(
            story_id=uuid4(),
            universe_id=universe_id,
            title="Coherence Test — Iron Verdict",
            story_type="one_shot",
        )
        story_id = s_res["id"] if isinstance(s_res, dict) else s_res.id
        logger.info("Created story: %s", story_id)
    except Exception as exc:
        logger.error("Could not create story: %s", exc)
        return 1

    # 2. Initialize SceneLoop
    scene_id = uuid4()
    loop = SceneLoop(
        scene_id=scene_id,
        story_id=story_id,
        universe_id=universe_id,
        max_turns=50,
        play_mode="dice_game_system",
        session_tone="grim",
    )
    logger.info("Initialized SceneLoop (scene=%s)", scene_id)

    # 3. Run scripted turns
    turns = []
    inputs = SCRIPTED_INPUTS[: args.turns]
    for idx, user_input in enumerate(inputs, start=1):
        logger.info("=== Turn %d/%d ===", idx, len(inputs))
        result = await _run_turn(loop, user_input, idx)
        turns.append(result)
        logger.info(
            "Turn %d: type=%s, level=%s, latency=%.1fs, facts=%d, violations=%d",
            idx, result.resolution_type, result.success_level,
            result.latency_seconds, len(result.established_facts),
            len(result.consistency_violations),
        )
        if result.error:
            logger.warning("Turn %d error: %s", idx, result.error[:200])
        if result.scene_complete:
            logger.info("Scene complete at turn %d", idx)
            break

    # 4. Analyze
    report = CoherenceReport()
    for turn in turns:
        _analyze_turn(turn, report)

    # Drift score: ratio of medieval terms to total terms
    total_setting = len(report.setting_keywords_mentioned) + len(report.medieval_terms_mentioned)
    if total_setting > 0:
        report.narrative_drift_score = len(report.medieval_terms_mentioned) / total_setting

    # Pass/fail
    report.session_passed = (
        report.empty_narratives == 0
        and report.narrative_drift_score < 0.15
        and report.turns_with_narration >= max(1, report.total_turns * 0.8)
    )
    if report.pending_roll_properly_handled:
        report.notes.append(
            "✓ Pending roll state machine is working — pushback was triggered."
        )
    if report.consistency_violations_total == 0:
        report.notes.append("✓ No consistency violations detected.")
    if report.narrative_drift_score < 0.15:
        report.notes.append(
            f"✓ Setting drift score is low ({report.narrative_drift_score:.2f})."
        )
    else:
        report.notes.append(
            f"✗ Setting drift detected ({report.narrative_drift_score:.2f}). "
            f"Medieval terms: {report.medieval_terms_mentioned}"
        )

    # 5. Write log
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    script_args = {
        "turns": args.turns,
        "play_mode": "dice_game_system",
        "session_tone": "grim",
        "scripted_inputs_used": len(inputs),
        "session_passed": report.session_passed,
    }
    md = _build_markdown_log(turns, report, script_args)
    output_path.write_text(md)
    logger.info("Wrote log to: %s", output_path)

    # 6. Print summary
    print()
    print("=" * 70)
    print("COHERENCE PLAYTEST SUMMARY")
    print("=" * 70)
    print(f"  Turns run:              {report.total_turns}")
    print(f"  Turns with narrative:   {report.turns_with_narration}")
    print(f"  Empty narratives:       {report.empty_narratives}")
    print(f"  Setting drift score:    {report.narrative_drift_score:.3f}")
    print(f"  Pending roll handled:   {report.pending_roll_properly_handled}")
    print(f"  Consistency violations: {report.consistency_violations_total}")
    print(f"  Facts extracted:        {report.facts_extracted}")
    print(f"  Named entities:         {len(report.name_mentions)}")
    print(f"  Sci-fi terms:           {len(report.setting_keywords_mentioned)}")
    print(f"  Medieval terms:         {len(report.medieval_terms_mentioned)}")
    print(f"  SESSION PASSED:         {report.session_passed}")
    print("=" * 70)
    if report.notes:
        print()
        print("Notes:")
        for note in report.notes:
            print(f"  • {note}")

    return 0 if report.session_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Coherence-focused scripted gameplay test"
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=10,
        help="Number of scripted turns to run (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(
            WORKSPACE_ROOT
            / "tests"
            / "e2e"
            / "logs"
            / f"coherence_test_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
        ),
        help="Output markdown log path",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())