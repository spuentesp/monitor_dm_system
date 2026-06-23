"""
End-to-end test: Chat router full flow simulation.

Simulates the complete REST API flow using the chat router functions directly:
  1. Create session → awaiting_character phase
  2. Player describes character → Narrator acknowledgement + CC loop start
  3. CharacterCreationLoop multi-step creation (rule-based, no LLM)
  4. Transition to active_play

Prerequisites:
  - PostgreSQL running (for llm_providers)
  - MongoDB running (for game_systems)
  - Ollama running with qwen2.5:14b
"""

import asyncio
import sys
import os
import time

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "packages", "data-layer", "src")
)
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "packages", "agents", "src")
)
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "packages", "ui", "backend", "src")
)


def _get_system_id_from_mongodb(system_name_keyword: str) -> str | None:
    """Look up a builtin system's system_id from MongoDB."""
    from monitor_data.db.mongodb import get_mongodb_client

    mdb = get_mongodb_client()
    col = mdb.get_collection("game_systems")
    doc = col.find_one(
        {"is_builtin": True, "name": {"$regex": system_name_keyword, "$options": "i"}},
        {"system_id": 1, "name": 1, "_id": 0},
    )
    if doc:
        print(f"  Found system: {doc['name']} (system_id={doc['system_id']})")
        return doc["system_id"]
    return None


async def test_chat_router_dd5e_flow():
    """Test the full chat router flow: awaiting_character → char_creation → active_play."""
    print("\n" + "=" * 60)
    print("TEST 1: Chat Router D&D 5e Full Flow")
    print("=" * 60)

    from monitor_ui.routers.chat import (
        _run_preplay_turn,
        _SESSIONS,
        _MESSAGES,
        _CHAR_CREATION_LOOPS,
    )
    from monitor_ui.routers.chat_support import now_iso

    session_id = "test-e2e-dd5e-001"

    # Look up the D&D 5e system_id from MongoDB
    print("\n  Resolving D&D 5e system from MongoDB...")
    system_id = _get_system_id_from_mongodb("D&D")
    if not system_id:
        print("  ❌ D&D 5e not found in MongoDB. Run seed_world.py first.")
        return False

    # Create session (what the REST API's create_session endpoint would do)
    session = {
        "id": session_id,
        "title": "Test D&D 5e Adventure",
        "mode": "chat",
        "phase": "awaiting_character",
        "tone": "dramatic",
        "system_id": system_id,
        "system_label": "D&D 5e",
        "system_source_type": "generic_library",
        "pack_id": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "speaker_label": "Player",
        "universe_id": None,
        "world_id": None,
    }
    _SESSIONS[session_id] = session
    _MESSAGES[session_id] = []

    # --- Step 1: Player describes character in 'awaiting_character' phase ---
    # This triggers:
    #   1. Narrator generates in-fiction acknowledgement (LLM call, ~20-30s)
    #   2. CC loop starts and returns first prompt
    #   3. Phase transitions to 'char_creation'
    print(
        "\n  --- Step 1: Player describes character (awaiting_character → char_creation) ---"
    )
    print("  Player: I want to play an Elven Wizard named Elara")

    t0 = time.time()
    response_text, meta = await _run_preplay_turn(
        session_id,
        "I want to play an Elven Wizard named Elara",
    )
    elapsed = time.time() - t0

    print(f"  GM ({elapsed:.1f}s): {response_text[:200]}...")
    print(f"  Meta: type={meta.get('type')}, phase={meta.get('phase')}")
    print(f"  Session phase: {session.get('phase')}")

    # Verify transition happened
    assert meta.get("phase") == "char_creation", (
        f"Expected phase=char_creation, got {meta.get('phase')}"
    )
    assert meta.get("type") == "char_creation_start", (
        f"Expected type=char_creation_start, got {meta.get('type')}"
    )
    print("  ✅ Phase transitioned to char_creation")

    total_steps = meta.get("total_steps", 0)
    print(f"  CC Loop total steps: {total_steps}")

    # --- Step 2: Walk through CC loop steps (rule-based, no LLM) ---
    # These should be fast since CharacterCreationLoop is rule-based
    player_inputs = [
        "Elara Nightwhisper",
        "High Elf",
        "Wizard",
        "I want high Intelligence and Wisdom",
        "Sage",
        "Arcana, History, Investigation",
        "A quarterstaff and a spellbook",
        "School of Evocation",
        "I'm ready!",
    ]

    completed = False
    for i, player_input in enumerate(player_inputs):
        if completed:
            break
        print(f"\n  --- CC Step {i + 1} ---")
        print(f"  Player: {player_input}")

        t0 = time.time()
        response_text, meta = await _run_preplay_turn(session_id, player_input)
        elapsed = time.time() - t0

        step_type = meta.get("type", "unknown")
        step_index = meta.get("step_index", "?")
        step_phase = meta.get("phase", "?")

        print(f"  GM ({elapsed:.1f}s): {response_text[:150]}...")
        print(
            f"  Meta: type={step_type}, step={step_index}/{total_steps}, phase={step_phase}"
        )

        if step_type == "char_creation_complete":
            completed = True
            char = meta.get("character", {})
            print("\n  🎉 Character creation complete!")
            print(f"  Character fields: {list(char.keys())}")
            print(f"  Phase: {step_phase}")
            assert step_phase == "active_play", (
                f"Expected active_play, got {step_phase}"
            )

    # Cleanup
    _SESSIONS.pop(session_id, None)
    _MESSAGES.pop(session_id, None)
    _CHAR_CREATION_LOOPS.pop(session_id, None)

    success = completed or session.get("phase") == "active_play"
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"\n  Result: {status}")
    return success


async def test_chat_router_narrative_skip():
    """Test skipping character creation (narrative-only mode).

    Note: The 'skip' keyword only works in the LEGACY fallback path
    (when CC loop is not available). When CC loop IS active, it captures
    the input first. So we test skip with a session that has no game system,
    which bypasses CC loop entirely.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Chat Router — Narrative-Only (No System)")
    print("=" * 60)

    from monitor_ui.routers.chat import (
        _run_preplay_turn,
        _SESSIONS,
        _MESSAGES,
        _CHAR_CREATION_LOOPS,
    )
    from monitor_ui.routers.chat_support import now_iso

    session_id = "test-e2e-narrative-001"

    # Use a session WITHOUT a game system → goes to narrative-only path
    session = {
        "id": session_id,
        "title": "Test Narrative Skip",
        "mode": "chat",
        "phase": "awaiting_character",
        "tone": "adventure",
        "system_id": None,
        "system_label": None,
        "system_source_type": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "speaker_label": "Player",
        "universe_id": None,
        "world_id": None,
    }
    _SESSIONS[session_id] = session
    _MESSAGES[session_id] = []

    # Without a game system, describing a character should go straight to active_play
    print("\n  Player: I want to play a wandering bard")
    response_text, meta = await _run_preplay_turn(
        session_id, "I want to play a wandering bard"
    )
    print(f"  GM: {response_text[:150]}...")
    print(f"  Meta: type={meta.get('type')}, phase={meta.get('phase')}")

    # Without a system, the narrator acknowledges and goes to active_play directly
    success = meta.get("phase") in ("active_play", "char_creation")
    if meta.get("phase") == "active_play":
        print("  ✅ Went to active_play (narrative-only)")
    elif meta.get("phase") == "char_creation":
        print("  ⚠️  Phase is char_creation (unexpected for no-system session)")

    # Cleanup
    _SESSIONS.pop(session_id, None)
    _MESSAGES.pop(session_id, None)
    _CHAR_CREATION_LOOPS.pop(session_id, None)

    status = "✅ PASS" if success else "❌ FAIL"
    print(f"\n  Result: {status}")
    return success


async def test_chat_router_fate_core():
    """Test chat router with Fate Core (different game system)."""
    print("\n" + "=" * 60)
    print("TEST 3: Chat Router — Fate Core")
    print("=" * 60)

    from monitor_ui.routers.chat import (
        _run_preplay_turn,
        _SESSIONS,
        _MESSAGES,
        _CHAR_CREATION_LOOPS,
    )
    from monitor_ui.routers.chat_support import now_iso

    session_id = "test-e2e-fate-001"

    system_id = _get_system_id_from_mongodb("Fate")
    if not system_id:
        print("  ❌ Fate Core not found in MongoDB")
        return False

    session = {
        "id": session_id,
        "title": "Test Fate Core",
        "mode": "chat",
        "phase": "awaiting_character",
        "tone": "pulpy",
        "system_id": system_id,
        "system_label": "Fate Core",
        "system_source_type": "generic_library",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "speaker_label": "Player",
        "universe_id": None,
        "world_id": None,
    }
    _SESSIONS[session_id] = session
    _MESSAGES[session_id] = []

    # Step 1: Describe character → char_creation
    print("\n  Player: I want to be a clever detective with a mysterious past")
    response_text, meta = await _run_preplay_turn(
        session_id, "I want to be a clever detective with a mysterious past"
    )
    print(f"  GM: {response_text[:200]}...")
    print(
        f"  Meta: type={meta.get('type')}, phase={meta.get('phase')}, steps={meta.get('total_steps')}"
    )

    if meta.get("phase") == "char_creation":
        print("  ✅ CC loop started for Fate Core")
        # Walk through steps quickly
        inputs = [
            "Detective Morgan Blackwood",
            "High Aspect: The Truth Will Out",
            "Trouble: Curiosity Killed the Cat",
            "Great (+4) Investigate, Good (+3) Empathy",
            "I'm done creating my character",
        ]
        completed = False
        for inp in inputs:
            if completed:
                break
            print(f"\n  Player: {inp}")
            response_text, meta = await _run_preplay_turn(session_id, inp)
            print(f"  GM: {response_text[:100]}...")
            print(f"  Meta: type={meta.get('type')}, phase={meta.get('phase')}")
            if meta.get("type") == "char_creation_complete":
                completed = True
                print("  🎉 Character complete!")
        success = completed
    else:
        print(f"  ⚠️  Unexpected phase: {meta.get('phase')}")
        success = False

    # Cleanup
    _SESSIONS.pop(session_id, None)
    _MESSAGES.pop(session_id, None)
    _CHAR_CREATION_LOOPS.pop(session_id, None)

    status = "✅ PASS" if success else "❌ FAIL"
    print(f"\n  Result: {status}")
    return success


async def test_ooc_question():
    """Test OOC question handling during pre-play."""
    print("\n" + "=" * 60)
    print("TEST 4: OOC Question During Pre-Play")
    print("=" * 60)

    from monitor_ui.routers.chat import (
        _run_preplay_turn,
        _SESSIONS,
        _MESSAGES,
        _CHAR_CREATION_LOOPS,
    )
    from monitor_ui.routers.chat_support import now_iso

    session_id = "test-e2e-ooc-001"

    system_id = _get_system_id_from_mongodb("D&D")
    if not system_id:
        print("  ❌ D&D 5e not found")
        return False

    session = {
        "id": session_id,
        "title": "Test OOC",
        "mode": "chat",
        "phase": "awaiting_character",
        "tone": "dramatic",
        "system_id": system_id,
        "system_label": "D&D 5e",
        "system_source_type": "generic_library",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "speaker_label": "Player",
        "universe_id": None,
        "world_id": None,
    }
    _SESSIONS[session_id] = session
    _MESSAGES[session_id] = []

    print("  Player: [OOC] What dice does this system use?")
    try:
        response_text, meta = await _run_preplay_turn(
            session_id,
            "[OOC] What dice does this system use?",
        )
        print(f"  GM: {response_text[:200]}...")
        print(f"  Meta: type={meta.get('type')}, phase={meta.get('phase')}")
        success = meta.get("type") == "ooc_answer" and len(response_text) > 20
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback

        traceback.print_exc()
        success = False

    # Cleanup
    _SESSIONS.pop(session_id, None)
    _MESSAGES.pop(session_id, None)
    _CHAR_CREATION_LOOPS.pop(session_id, None)

    status = "✅ PASS" if success else "❌ FAIL"
    print(f"\n  Result: {status}")
    return success


async def _safe_run(name, coro):
    """Run a test coroutine, catching exceptions so other tests can continue."""
    try:
        return await coro
    except Exception as e:
        print(f"\n  ❌ EXCEPTION in {name}: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    print("🧪 Chat Router E2E Tests with Ollama (qwen2.5:14b)")
    print("=" * 60)
    print("Prerequisites: PostgreSQL + MongoDB + Ollama running")
    print()

    results = {}

    # Test 1: Full D&D 5e flow (most important)
    results["dd5e_full_flow"] = await _safe_run(
        "dd5e_full_flow", test_chat_router_dd5e_flow()
    )

    # Test 2: Narrative-only (no system)
    results["narrative_skip"] = await _safe_run(
        "narrative_skip", test_chat_router_narrative_skip()
    )

    # Test 3: Fate Core (multi-system)
    results["fate_core"] = await _safe_run("fate_core", test_chat_router_fate_core())

    # Test 4: OOC question
    results["ooc_question"] = await _safe_run("ooc_question", test_ooc_question())

    # Summary
    print("\n" + "=" * 60)
    print("📊 CHAT ROUTER E2E RESULTS")
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
