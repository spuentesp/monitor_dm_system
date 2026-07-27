#!/usr/bin/env python3
"""
Perception Layer — Standalone Demo.

Run this script to see the perception pipeline in action.
No database or LLM connection needed.

Usage:
    python scripts/demo_perception.py
    python scripts/demo_perception.py --backend gliner   # if gliner installed
    python scripts/demo_perception.py --benchmark        # timing benchmark
"""

from __future__ import annotations

import argparse
import asyncio
import time

from monitor_data.schemas.perception import (
    DetectedEntityType,
    IntentType,
)
from monitor_data.tools.perception_tools import PerceptionPipeline


# Sample TTRPG inputs covering different scenarios
DEMO_INPUTS = [
    # Combat
    ("I attack the Dragon with my Flame Sword", IntentType.COMBAT),
    ("I cast Fireball at the goblin horde", IntentType.COMBAT),
    (
        "Roll initiative! I strike the Shadow King with a critical hit",
        IntentType.COMBAT,
    ),
    # Exploration
    (
        "I search the room for hidden doors and examine the ancient carvings",
        IntentType.EXPLORATION,
    ),
    ("I open the chest and look inside", IntentType.EXPLORATION),
    (
        "I climb the tower stairs and investigate the locked door",
        IntentType.EXPLORATION,
    ),
    # Dialogue
    ("I tell the guard that we are just passing through", IntentType.DIALOGUE),
    ("I ask the bartender about the missing merchant", IntentType.DIALOGUE),
    ("I whisper to the elf that I don't trust the wizard", IntentType.DIALOGUE),
    # OOC
    ("(( wait, I actually meant to go left ))", IntentType.OOC),
    ("sorry, correction — I actually attack instead", IntentType.OOC),
    ("ooc: can I retcon that action?", IntentType.OOC),
    # Social
    ("I try to persuade the king to let us pass", IntentType.SOCIAL),
    # Investigation
    ("I look for clues about the murder in the library", IntentType.INVESTIGATION),
    # Complex / multi-entity
    (
        'I enter the "Crimson Tavern" and talk to Eldric the wizard about the Shadowfell',
        IntentType.UNKNOWN,
    ),
    (
        "I show the Amber Amulet to High Priestess Selene at the Temple of Light",
        IntentType.UNKNOWN,
    ),
]


def _entity_type_icon(t: DetectedEntityType) -> str:
    icons = {
        DetectedEntityType.CHARACTER: "👤",
        DetectedEntityType.LOCATION: "📍",
        DetectedEntityType.OBJECT: "⚔️",
        DetectedEntityType.SPELL: "✨",
        DetectedEntityType.FACTION: "🏛️",
        DetectedEntityType.ACTION: "⚡",
        DetectedEntityType.CONCEPT: "💭",
    }
    return icons.get(t, "❓")


def _intent_icon(i: IntentType) -> str:
    icons = {
        IntentType.COMBAT: "⚔️",
        IntentType.EXPLORATION: "🔍",
        IntentType.DIALOGUE: "💬",
        IntentType.SOCIAL: "🤝",
        IntentType.INVESTIGATION: "🔎",
        IntentType.OOC: "🔧",
        IntentType.NARRATION: "📖",
        IntentType.UNKNOWN: "❓",
    }
    return icons.get(i, "❓")


async def run_demo(backend: str = "regex") -> None:
    """Run the interactive demo."""
    print("=" * 70)
    print("  MONITOR — Perception Layer Demo")
    print(f"  Backend: {backend}")
    print("=" * 70)
    print()

    known_entities = [
        "dragon",
        "gandalf",
        "moria",
        "flame sword",
        "shadow king",
        "crimson tavern",
        "the king",
    ]

    pipe = PerceptionPipeline(backend=backend, known_entities=known_entities)

    correct_intents = 0
    total = 0
    total_entities = 0
    total_ms = 0.0

    for text, expected_intent in DEMO_INPUTS:
        result = await pipe.detect(text)
        total += 1
        total_entities += len(result.entities)
        total_ms += result.processing_time_ms

        is_correct = result.intent == expected_intent
        correct_intents += int(is_correct)

        # Format output
        intent_str = f"{_intent_icon(result.intent)} {result.intent.value}"
        match_str = "✅" if is_correct else "⚠️"
        time_str = f"{result.processing_time_ms:.1f}ms"

        print(f"📝 Input:    {text}")
        print(
            f"   Intent:   {intent_str} {match_str} (conf: {result.intent_confidence:.0%})"
        )
        print(f"   Entities: {len(result.entities)} detected [{time_str}]")

        for e in result.entities:
            icon = _entity_type_icon(e.entity_type)
            novelty = "🆕" if e.is_known is False else ("✓" if e.is_known else " ")
            print(
                f"     {icon} {e.text:<25} "
                f"({e.entity_type.value:<10} conf={e.confidence:.0%}) {novelty}"
            )

        print()

    # Summary
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Inputs processed:       {total}")
    print(
        f"  Intent accuracy:        {correct_intents}/{total} ({correct_intents / total:.0%})"
    )
    print(f"  Total entities found:   {total_entities}")
    print(f"  Avg processing time:    {total_ms / total:.2f}ms")
    print(f"  Total processing time:  {total_ms:.1f}ms")
    print()


async def run_benchmark(backend: str = "regex", iterations: int = 100) -> None:
    """Run a timing benchmark."""
    print("=" * 70)
    print(f"  Perception Layer Benchmark — {backend} backend")
    print(f"  {iterations} iterations")
    print("=" * 70)
    print()

    pipe = PerceptionPipeline(backend=backend)

    # Warm up
    for _ in range(10):
        await pipe.detect("I attack the Dragon with my Flame Sword")

    # Benchmark
    times: list[float] = []
    for text, _ in DEMO_INPUTS:
        t0 = time.perf_counter()
        for _ in range(iterations):
            await pipe.detect(text)
        elapsed = (time.perf_counter() - t0) * 1000 / iterations
        times.append(elapsed)
        print(f"  {text[:50]:<52} {elapsed:.2f}ms/call")

    print()
    print(f"  Min:  {min(times):.2f}ms")
    print(f"  Max:  {max(times):.2f}ms")
    print(f"  Avg:  {sum(times) / len(times):.2f}ms")
    print(f"  P95:  {sorted(times)[int(len(times) * 0.95)]:.2f}ms")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="MONITOR Perception Layer Demo")
    parser.add_argument(
        "--backend",
        choices=["regex", "spacy", "gliner"],
        default="regex",
        help="Perception backend to use (default: regex)",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run timing benchmark instead of demo",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Benchmark iterations per input (default: 100)",
    )
    args = parser.parse_args()

    if args.benchmark:
        asyncio.run(run_benchmark(args.backend, args.iterations))
    else:
        asyncio.run(run_demo(args.backend))


if __name__ == "__main__":
    main()
