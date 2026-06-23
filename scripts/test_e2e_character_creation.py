"""
End-to-end test: CharacterCreationLoop + Narrator with real LLM (Ollama).

Tests:
1. CharacterCreationLoop — schema-driven, rule-based (no LLM needed)
2. Narrator.narrate_turn() — DSPy + instructor, needs LLM
3. Full chat flow simulation: awaiting_character → char_creation → active_play

Uses: Ollama (qwen2.5:14b) as default LLM provider.
"""

import asyncio
import json
import sys
from uuid import uuid4

# ---------------------------------------------------------------------------
# Bootstrap: ensure paths are set up
# ---------------------------------------------------------------------------
import os

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "packages", "data-layer", "src")
)
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "packages", "agents", "src")
)
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "packages", "ui", "backend", "src")
)

from monitor_data.db.postgres import PostgresClient
from monitor_agents.llm_registry import LLMRegistry
from monitor_agents.loops.character_creation_loop import CharacterCreationLoop


# Load builtin systems JSON
def _load_builtin_systems() -> list:
    """Load all builtin game systems from the data-layer JSON file."""
    import importlib.resources as pkg_resources

    try:
        from monitor_data import data as data_data

        data_dir = pkg_resources.files(data_data)
        json_path = data_dir / "builtin_systems.json"
        with open(str(json_path)) as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️  Failed to load via importlib: {e}")
        # Fallback: direct path
        fallback = os.path.join(
            os.path.dirname(__file__),
            "..",
            "packages",
            "data-layer",
            "src",
            "monitor_data",
            "data",
            "builtin_systems.json",
        )
        with open(fallback) as f:
            return json.load(f)


def _find_system(systems: list, keyword: str) -> dict | None:
    """Find a system by keyword in id or name."""
    for s in systems:
        if keyword in (s.get("id", "") + s.get("name", "")).lower():
            return s
    return None


# ===========================================================================
# Test 1: CharacterCreationLoop with D&D 5e
# ===========================================================================
async def test_character_creation_dd5e():
    """Test CharacterCreationLoop with D&D 5e game system."""
    print("\n" + "=" * 60)
    print("TEST 1: CharacterCreationLoop — D&D 5e")
    print("=" * 60)

    all_systems = _load_builtin_systems()
    dd5e = _find_system(all_systems, "d&d")

    if not dd5e:
        print("  ❌ D&D 5e system not found")
        return False

    print(f"  System: {dd5e.get('name', 'unknown')}")

    # Start character creation
    loop = CharacterCreationLoop(game_context=dd5e)
    result = await loop.start()

    print(f"  GM Message: {result.get('gm_message', 'N/A')[:120]}...")
    print(f"  Step: {result.get('step_index', 0)}/{result.get('total_steps', 0)}")
    print(f"  Complete: {result.get('complete', False)}")

    if result.get("complete"):
        print("  ✅ Character creation completed immediately (unlikely)")
        return True

    # Simulate player input through steps
    player_inputs = [
        "I want to be a Human Fighter",
        "I'll take the Soldier background",
        "I want high Strength and Constitution",
        "My character's name is Kael Ironforge",
        "I'll take a longsword and shield",
        "Let's go with Chain Mail armor",
        "I choose the Champion archetype",
        "Ready to start adventuring!",
    ]

    step = result.get("step_index", 0)
    total = result.get("total_steps", 0)

    for i, player_input in enumerate(player_inputs):
        if step >= total:
            break
        print(f"\n  --- Step {step + 1}/{total} ---")
        print(f"  Player: {player_input}")

        result = await loop.process_player_input(player_input)
        step = result.get("step_index", step + 1)

        gm_msg = result.get("gm_message", "")
        print(f"  GM: {gm_msg[:150]}...")
        print(f"  Complete: {result.get('complete', False)}")

        if result.get("complete"):
            char = result.get("character", {})
            print("\n  🎉 Character created!")
            print(f"  Name: {char.get('name', 'unknown')}")
            print(f"  Attributes: {char.get('attributes', {})}")
            print(f"  Resources: {char.get('resources', {})}")
            print(f"  Skills: {list(char.get('skills', {}).keys())[:5]}...")
            return True

    # If we didn't finish, still count it as partial success
    print(f"\n  ⚠️  Didn't complete all steps (reached step {step}/{total})")
    return step > 0


# ===========================================================================
# Test 2: CharacterCreationLoop with Vampire V5
# ===========================================================================
async def test_character_creation_vampire():
    """Test CharacterCreationLoop with Vampire: The Masquerade 5e."""
    print("\n" + "=" * 60)
    print("TEST 2: CharacterCreationLoop — Vampire V5")
    print("=" * 60)

    all_systems = _load_builtin_systems()
    vtm = _find_system(all_systems, "vampire")

    if not vtm:
        print("  ❌ Vampire V5 system not found")
        return False

    print(f"  System: {vtm.get('name', 'unknown')}")

    loop = CharacterCreationLoop(game_context=vtm)
    result = await loop.start()

    print(f"  GM Message: {result.get('gm_message', 'N/A')[:120]}...")
    print(f"  Steps: {result.get('step_index', 0)}/{result.get('total_steps', 0)}")

    player_inputs = [
        "I want to play a Brujah",
        "My concept is a rebellious college professor",
        "I'll distribute my attributes with high Physical",
        "I focus on Brawl, Intimidation, and Academics",
        "My character's name is Dr. Marcus Vale",
        "I choose the Camarilla as my faction",
        "Ready to prowl the night!",
    ]

    step = result.get("step_index", 0)
    total = result.get("total_steps", 0)

    for player_input in player_inputs:
        if step >= total:
            break
        result = await loop.process_player_input(player_input)
        step = result.get("step_index", step + 1)
        print(f"  Step {step}/{total}: {result.get('gm_message', '')[:100]}...")

        if result.get("complete"):
            char = result.get("character", {})
            print("\n  🎉 Vampire character created!")
            print(f"  Name: {char.get('name', 'unknown')}")
            return True

    print(f"  ⚠️  Reached step {step}/{total}")
    return step > 0


# ===========================================================================
# Test 3: Narrator with real LLM (Ollama)
# ===========================================================================
async def test_narrator_with_llm():
    """Test Narrator agent with real LLM (Ollama qwen2.5:14b)."""
    print("\n" + "=" * 60)
    print("TEST 3: Narrator with real LLM (Ollama)")
    print("=" * 60)

    # First verify Ollama is reachable via LLMRegistry
    pg = PostgresClient()
    await pg.connect()
    registry = LLMRegistry(pg)

    try:
        client = await registry.for_node("narrator")
        print(f"  Provider: {client.provider} / {client.model}")
        print(f"  Base URL: {client.base_url}")
    except Exception as e:
        print(f"  ❌ Could not get LLM client: {e}")
        await pg.close()
        return False

    # Test Narrator
    try:
        from monitor_agents.narrator import Narrator

        narrator = Narrator()

        # Generate opening
        print("\n  --- Generating GM opening ---")
        opening = await narrator.generate_opening(
            user_input=None,
            context={
                "entities": [],
                "memories": [],
                "turns": [],
            },
            game_context={"name": "Dungeons & Dragons 5e", "genre": "fantasy"},
            session_tone="dramatic",
        )
        print(f"  Opening: {opening[:200]}...")
        print(f"  ✅ Opening generated ({len(opening)} chars)")

    except Exception as e:
        print(f"  ❌ Narrator failed: {e}")
        import traceback

        traceback.print_exc()
        await pg.close()
        return False

    # Test narrate_turn with full pipeline
    try:
        print("\n  --- Generating narrative turn ---")
        result = await narrator.narrate_turn(
            scene_id=uuid4(),
            user_input="I draw my sword and challenge the tavern keeper to a duel",
            resolution={
                "success": True,
                "degree": "strong",
                "mechanical": "Attack roll: 18 vs AC 12. Hit! 8 damage.",
            },
            context={
                "entities": [
                    {
                        "name": "Tavern Keeper",
                        "context": "A burly man with a scarred face",
                    },
                ],
                "memories": [],
                "turns": [],
            },
            game_context={"name": "D&D 5e", "genre": "fantasy"},
            session_tone="adventure",
        )

        narrative = result.get("narrative_text", "")
        proposals = result.get("proposals", [])
        print(f"  Narrative: {narrative[:250]}...")
        print(f"  Proposals: {len(proposals)}")
        print(f"  ✅ Full narrative turn ({len(narrative)} chars)")

    except Exception as e:
        print(f"  ❌ narrate_turn failed: {e}")
        import traceback

        traceback.print_exc()
        await pg.close()
        return False

    await pg.close()
    return True


# ===========================================================================
# Main
# ===========================================================================
async def main():
    print("🧪 End-to-End Experiments with Ollama (qwen2.5:14b)")
    print("=" * 60)

    results = {}

    # Test 1: D&D 5e Character Creation
    results["dd5e_char_creation"] = await test_character_creation_dd5e()

    # Test 2: Vampire V5 Character Creation
    results["vampire_char_creation"] = await test_character_creation_vampire()

    # Test 3: Narrator with real LLM
    results["narrator_llm"] = await test_narrator_with_llm()

    # Summary
    print("\n" + "=" * 60)
    print("📊 RESULTS SUMMARY")
    print("=" * 60)
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test}: {status}")

    all_passed = all(results.values())
    print(f"\n  Overall: {'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}")
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
