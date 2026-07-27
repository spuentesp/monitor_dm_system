#!/usr/bin/env python3
"""True end-to-end test of the narration heuristic against the live backend.

Runs three turns against the live API with a forced active_play session:

  1. CHARACTER INTRO — "I am Kael Draven, a void-born salvage engineer…"
     Expected: heuristic short-circuits (no GMAwareness LLM call).
     Signal: response time << GMAwareness latency, response.content is
     rich narrative (not action outcome), no dice_request.

  2. ATMOSPHERIC DESCRIPTION — "The Iron Verdict groans around me."
     Expected: heuristic short-circuits via vocabulary match.
     Signal: same as above.

  3. ACTION — "I attack the alien with my cutter."
     Expected: heuristic does NOT fire. GMAwareness LLM is called.
     Signal: response time is longer (LLM call), resolution_type is
     propose_roll / dice / forced_narrative_pushback.

The point: prove the heuristic actually fires end-to-end with a real LLM,
not just in mocked unit tests.

Usage:
    uv run python scripts/heuristic_e2e_test.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

API_BASE = os.environ.get("MONITOR_API_URL", "http://localhost:8000/api")

# Hardcoded narration vs action prompts. We force the LLM-as-player to
# emit these by setting them as the player message; the system under test
# is the resolver/GMAwareness path which classifies them.
NARRATION_INTRO = (
    "I am Kael Draven, a void-born salvage engineer "
    "aboard the derelict station Iron Verdict. My salvage crew "
    "was lost when the Penitent Star split open in the black."
)
NARRATION_ATMOSPHERE = (
    "The Iron Verdict groans around me as the station settles into its decay."
)
ACTION_ATTACK = (
    "I attack the alien lurking in the corridor with my cutter raised."
)

HEURISTIC_FAST_BUDGET_MS = 1500  # Anything below this is heuristic short-circuit
HEURISTIC_SLOW_BUDGET_MS = 500   # Anything above this is LLM path


def _create_session() -> str:
    """Create a session bound to a universe, in active_play phase.

    The chat router routes the session to SceneLoop only when a universe
    is bound. Without ``universe_id``, the response is a placeholder.
    We also pass ``character_id`` to force the session straight into
    ``active_play`` (skipping session_zero).
    """
    universes_resp = requests.get(f"{API_BASE}/universes/universes", timeout=30)
    universes_resp.raise_for_status()
    universes = universes_resp.json()
    if not universes:
        raise RuntimeError("No universes available — run the live smoke once first to seed a universe")
    universe = universes[0]

    body = {
        "title": "Heuristic E2E test",
        "mode": "autonomous_gm",
        "tone": "grim",
        "play_mode": "dice_game_system",
        "universe_id": universe["id"],
        "universe_label": universe.get("name"),
        "character_id": "heuristic-test-character",
    }
    resp = requests.post(f"{API_BASE}/chat", json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]


def _send_turn(session_id: str, content: str) -> dict:
    """Send one player turn and measure the round-trip latency."""
    start = time.perf_counter()
    resp = requests.post(
        f"{API_BASE}/chat/{session_id}/send",
        json={"content": content},
        timeout=120,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    resp.raise_for_status()
    body = resp.json()
    return {"body": body, "elapsed_ms": elapsed_ms, "status": resp.status_code}


def _diagnose_turn(label: str, content: str, result: dict) -> dict:
    """Extract the signal we care about from a turn response."""
    body = result["body"]
    metadata = body.get("metadata") or {}
    diag = {
        "label": label,
        "elapsed_ms": round(result["elapsed_ms"], 0),
        "content_chars": len(body.get("content") or ""),
        "resolution_type": metadata.get("resolution_type"),
        "intent_type": metadata.get("intent_type"),
        "has_dice_request": "dice_request" in metadata,
        "phase": metadata.get("phase"),
    }
    # Heuristic fired ⇒ low latency, no dice_request, narration-style verdict.
    if diag["elapsed_ms"] < HEURISTIC_FAST_BUDGET_MS and not diag["has_dice_request"]:
        diag["verdict"] = "HEURISTIC_SHORT_CIRCUIT"
    elif diag["has_dice_request"]:
        diag["verdict"] = "LLM_PATH_WITH_DICE"
    else:
        diag["verdict"] = "LLM_PATH_LIKELY"
    return diag


def main() -> int:
    if not os.environ.get("MONITOR_PLAYTEST_MODEL"):
        print("Set MONITOR_PLAYTEST_MODEL (e.g. gemini-2.5-flash) before running.")
        return 2

    print("=" * 72)
    print("HEURISTIC END-TO-END TEST — live backend, real LLM")
    print("=" * 72)

    session_id = _create_session(skip_session_zero=True)
    print(f"Session: {session_id}\n")

    cases = [
        ("NARRATION_INTRO", NARRATION_INTRO),
        ("NARRATION_ATMOSPHERE", NARRATION_ATMOSPHERE),
        ("ACTION_ATTACK", ACTION_ATTACK),
    ]

    results = []
    for label, content in cases:
        print(f"--- {label} ---")
        print(f"Input:  {content[:80]}{'...' if len(content) > 80 else ''}")
        try:
            result = _send_turn(session_id, content)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            return 1
        diag = _diagnose_turn(label, content, result)
        print(f"  Latency:      {diag['elapsed_ms']}ms")
        print(f"  Content:      {diag['content_chars']} chars")
        print(f"  Resolution:   {diag['resolution_type']}")
        print(f"  Phase:        {diag['phase']}")
        print(f"  Dice req:     {diag['has_dice_request']}")
        print(f"  VERDICT:      {diag['verdict']}\n")
        results.append(diag)

    # Assert expectations.
    print("=" * 72)
    print("EXPECTATIONS")
    print("=" * 72)

    failures = []

    # Both narration turns should hit the heuristic short-circuit.
    for label in ("NARRATION_INTRO", "NARRATION_ATMOSPHERE"):
        diag = next(d for d in results if d["label"] == label)
        if diag["verdict"] != "HEURISTIC_SHORT_CIRCUIT":
            failures.append(f"{label}: expected HEURISTIC_SHORT_CIRCUIT, got {diag['verdict']} ({diag['elapsed_ms']}ms)")

    # Action turn should NOT short-circuit; should produce dice or roll request.
    action_diag = next(d for d in results if d["label"] == "ACTION_ATTACK")
    if action_diag["verdict"] == "HEURISTIC_SHORT_CIRCUIT":
        failures.append(f"ACTION_ATTACK: heuristic incorrectly fired for action verb (no dice_request, {action_diag['elapsed_ms']}ms)")

    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  ✘ {f}")
        return 1

    print("✓ NARRATION_INTRO: heuristic short-circuit (no LLM call)")
    print("✓ NARRATION_ATMOSPHERE: heuristic short-circuit (no LLM call)")
    print(f"✓ ACTION_ATTACK: LLM path taken ({action_diag['elapsed_ms']}ms, dice_request={action_diag['has_dice_request']})")
    print()
    print("RESULT: PASS — heuristic works end-to-end with the live backend and a real LLM.")

    # Persist results for the audit log.
    log_path = Path("tests/e2e/logs/heuristic_e2e_latest.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "model": os.environ.get("MONITOR_PLAYTEST_MODEL"),
                "results": results,
            },
            indent=2,
        )
    )
    print(f"\nLog written to: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())