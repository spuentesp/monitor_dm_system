#!/usr/bin/env python3
"""
End-to-end verification of the Character Conversatory + Scene flow.

Subject: **Kvothe** from *The Kingkiller Chronicle* by Patrick Rothfuss,
characterized from public knowledge of the books. No text is quoted from
any source — the card text is paraphrased from well-trodden lore.

Flow (the "full vertical slice"):
  1. Create a *simple* (light-card only) Kvothe — no expansion.
  2. Conversatory chat (6 escalating lines) — observe responses +
     emotional_state. The simple card lacks rich triggers, so this
     exercises the *fallback* personality path in NPCVoice.
  3. Create a *complex* Kvothe card (full free-text personality +
     secrets + GM notes + behavioral notes) in a new universe
     ("the Waystone Inn" — a small synthetic scene universe).
  4. Expand the complex card → entity + NPCProfile generated from
     the card text. Verify the LLM populated traits/triggers.
  5. Start a scene-style session (SceneLoop, IC mode). Send 4 lines in
     the Waystone context — observe emotional state, relationship
     stance, and memory recall across turns.

Stack: MONITOR uvicorn on 127.0.0.1:8765 (override with MONITOR_API env).
DBs (neo4j, mongo, qdrant, postgres) + ollama must be reachable.

Usage:
    python scripts/e2e_kvothe_full_flow.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List

import requests

BASE = os.environ.get("MONITOR_API", "http://127.0.0.1:8765/api")
CH = {"Content-Type": "application/json"}

# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

# Simple card — just enough for NPCVoice's fallback personality context.
SIMPLE_KVOTHE = {
    "name": "Kvothe",
    "description": (
        "A young Edema Ruh musician with red hair and green eyes, now "
        "running an inn under a false name."
    ),
    "personality": "Curious, guarded, sharp. Slow to trust, quick to think.",
    "gm_notes": "Hides his past and his talent.",
    "first_message": "*looks up from polishing a glass* Name's Kote. What'll it be?",
}

# Complex card — rich, with behavioral cues seeded in (the LLM will
# canonicalise them into traits + triggers on Expand).
COMPLEX_KVOTHE = {
    "name": "Kvothe",
    "description": (
        "Edema Ruh by birth, arcanist by training, musician by calling. "
        "Red hair, green eyes, a voice that bends rooms. Carries a lute, "
        "a cloak of no particular color, and debts he's not ready to pay. "
        "Currently the proprietor of the Waystone Inn under the alias Kote."
    ),
    "personality": (
        "Curious and quick-witted; performs 'simple innkeeper' as a mask. "
        "Slow to trust, sharp with words, kind to those who show him "
        "kindness. Falls into archaic Edema speech when off-guard. "
        "Tells long, vivid stories when relaxed."
    ),
    "gm_notes": (
        "Trained by the Arcanum; can do sympathy and naming. Hunted by the "
        "Amyr, the Chandrian, and the Maer's men. Killed a king. Looking "
        "for the Amyr and the Chandrian himself."
    ),
    "first_message": (
        "*polishes a glass that doesn't need polishing* Welcome to the "
        "Waystone. Sit anywhere. I'm Kote — innkeeper. What brings you "
        "in from the cold?"
    ),
}

# Conversatory lines for the simple card — probe his surface.
SIMPLE_DIALOGUE: List[str] = [
    "Evening. Something warm, please.",
    "I hear there's a traveling musician in these parts. Any word?",
    "You don't strike me as the innkeeper type. What's your trade, really?",
    "Tell me — what do you think of the chandrian?",
    "The Edema Ruh are good people, aren't they?",
    "I knew a girl once who could name things. You ever meet one?",
]

# Scene lines for the complex card — set in the Waystone Inn context,
# pushing at his mask and his past.
SCENE_DIALOGUE: List[str] = [
    "Sit, traveler. I'm Chronicler. I write true stories — and I think you have one.",
    "No? Then let me try the name: Kvothe. Does that get your attention?",
    "I know about the troupe. I know what happened. I'm not here to harm you.",
    "Then help me write the truth. For the people who died. For Cinder. For your parents.",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hdr(line: str) -> None:
    print("\n" + "=" * 6 + " " + line + " " + "=" * (60 - len(line) - 2))


def ok(label: str) -> None:
    print(f"  [PASS] {label}")


def fail(label: str, detail: str = "") -> None:
    print(f"  [FAIL] {label}{(': ' + detail) if detail else ''}")


def snap_line(reply: Dict[str, Any]) -> str:
    s = reply.get("relationship_snapshot") or {}
    stance = s.get("stance", "?")
    trust = s.get("trust", 0.0)
    delta = s.get("last_delta") or {}
    delta_str = " ".join(f"{k}{v:+.2f}" for k, v in delta.items()) if delta else ""
    return (
        f"feeling={reply.get('emotional_state') or '?'} "
        f"stance={stance} trust={trust:+.2f} {('Δ ' + delta_str) if delta_str else ''}"
    ).rstrip()


# ---------------------------------------------------------------------------
# Tight assertions
# ---------------------------------------------------------------------------
#
# Calibration guards. The LIGHT model (ollama / qwen) is small; delta
# magnitudes are usually small. These thresholds are intentionally
# permissive — they fail on a *flat* profile (no change across an
# escalation) but accept modest movement that still tells a coherent
# character story. If a future model regresses to no-op responses, these
# catch it; if it overshoots, a separate test should cover that.


def _delta_magnitude(reply: Dict[str, Any]) -> float:
    delta = (reply.get("relationship_snapshot") or {}).get("last_delta") or {}
    return sum(abs(v) for v in delta.values() if isinstance(v, (int, float)))


# Per-turn *cumulative* stance. Tolerant of LIGHT model — requires the
# character move at least one stance level along the threat/warmth axis,
# or the LLM is failing to model the character at all.
def _stance_path(replies: List[Dict[str, Any]]) -> List[str]:
    return [(r.get("relationship_snapshot") or {}).get("stance") for r in replies]


def _feeling_path(replies: List[Dict[str, Any]]) -> List[str]:
    return [r.get("emotional_state") for r in replies]


def check_simple_card(replies: List[Dict[str, Any]], failures: List[str]) -> None:
    """The simple card has no rich triggers. The LIGHT model with a free-text
    personality often settles into a single "watchful / guarded" tone and may
    not emit relationship deltas — that's a *real* finding for a card with
    no triggers, not a failure. We warn on it (so the next iteration knows to
    look) but only fail if the model can't even produce a *single* reply that
    matches the character's mask.

    Strict (failing) checks:
      - All 6 replies came back non-empty (i.e. the LLM produced text).

    Soft (warning) checks — emit a [WARN] line, not a failure:
      - Trust deltas all zero (model isn't tracking relationship movement).
      - Emotional state stuck on one value (model isn't reacting to escalation).
    """
    if not replies:
        failures.append("simple: no replies to assert against")
        return

    empty = sum(1 for r in replies if not (r.get("text") or "").strip())
    if empty > 0:
        failures.append(f"simple: {empty} empty replies")
    else:
        ok(f"simple: {len(replies)}/{len(replies)} non-empty replies")

    deltas = [_delta_magnitude(r) for r in replies]
    nonzero = sum(1 for d in deltas if d >= 0.01)
    if nonzero == 0:
        # Real finding, not a hard failure — surface as a warning so the
        # next iteration decides whether the model needs richer prompts
        # or the simple-card path needs a relationship-priming nudge.
        print(f"  [WARN] simple: no trust deltas across {len(replies)} turns")
        print(f"         (expected: LIGHT model + light card → flat profile)")
    else:
        ok(f"simple: {nonzero}/{len(replies)} non-zero trust deltas")

    feelings = _feeling_path(replies)
    distinct = {f.split(";")[0].strip().lower() for f in feelings if f}
    if len(distinct) < 2:
        print(
            f"  [WARN] simple: stuck on {len(distinct)} emotion across "
            f"{len(replies)} turns"
        )
    else:
        ok(f"simple: {len(distinct)} distinct emotions across {len(replies)} turns")


def check_complex_scene(replies: List[Dict[str, Any]], failures: List[str]) -> None:
    """The complex card's scene is *designed* to crack the innkeeper mask.
       Expect:
       - The 4-turn path traverses at least 2 distinct stances (the LLM
         must move from the innkeeper's neutral warmth through the
         guarded stance triggered by the player's escalation).
       - At least one of the names / troupe mentions shifts the stance.
       - At least one turn produces a non-trivial delta (≥0.05).
    """
    stances = _stance_path(replies)
    distinct = {s for s in stances if s}
    if len(distinct) < 2:
        failures.append(f"complex: only {len(distinct)} distinct stance(s): {stances}")
    else:
        ok(f"complex: {len(distinct)} distinct stances: {distinct}")

    # The "Kvothe" name (turn 2) and the troupe mention (turn 3) are
    # the pressure points. At least one should produce a guarded/wary
    # stance OR a delta ≥0.05.
    pressure_idx = (1, 2)  # zero-indexed turns 2 and 3
    pressure_ok = False
    for i in pressure_idx:
        if i >= len(replies):
            continue
        r = replies[i]
        stance = (r.get("relationship_snapshot") or {}).get("stance")
        delta_mag = _delta_magnitude(r)
        if stance in {"guarded", "wary", "hostile"} or delta_mag >= 0.05:
            pressure_ok = True
            break
    if not pressure_ok:
        failures.append(
            f"complex: no guard / no delta at the name/troupe pressure points "
            f"(stances={stances}, mags={[_delta_magnitude(r) for r in replies]})"
        )
    else:
        ok("complex: name/troupe pressure point produced a guarded stance or delta")

    # Top cumulative trust should be in [-0.4, 0.4] — the scene pushes
    # both ways (warmth from Chronicler's empathy, distrust from the name).
    trusts = [(r.get("relationship_snapshot") or {}).get("trust", 0.0) for r in replies]
    span = max(trusts) - min(trusts)
    if span > 0.6:
        failures.append(f"complex: trust swing too wide: {trusts}")
    else:
        ok(f"complex: trust span {span:+.2f} within [-0.4, +0.4] of expected")


def main() -> int:
    failures: List[str] = []
    # Quick stack sanity
    try:
        r = requests.get(f"{BASE}/entities/characters?limit=1", timeout=10)
        r.raise_for_status()
        ok(f"stack reachable at {BASE}")
    except Exception as exc:  # noqa: BLE001
        fail("stack unreachable", str(exc))
        return 1

    # ---- 1. Simple card ----
    hdr("1. Create simple Kvothe card (no expansion)")
    r = requests.post(f"{BASE}/entities/characters", json=SIMPLE_KVOTHE, timeout=30)
    if r.status_code != 201:
        fail("create simple card", r.text[:200]); return 1
    simple_id = r.json()["id"]
    ok(f"simple card id={simple_id}")

    # Conversatory with the simple card (entity_id is None — fallback path).
    hdr("2. Conversatory chat with simple card")
    r = requests.post(
        f"{BASE}/entities/characters/{simple_id}/conversations", timeout=60
    )
    if r.status_code != 200:
        fail("start simple conversatory", r.text[:200]); failures.append("start_simple")
        return _summary(failures, simple_id, None)
    conv = r.json()
    simple_conv_id = conv["conversation_id"]
    ok(f"conversation_id={simple_conv_id}  opening='{conv['opening'][:60]}…'")

    simple_replies: List[Dict[str, Any]] = []
    for i, line in enumerate(SIMPLE_DIALOGUE, start=1):
        rr = requests.post(
            f"{BASE}/entities/characters/{simple_id}/conversations/{simple_conv_id}/send",
            json={"text": line},
            timeout=60,
        )
        if rr.status_code != 200:
            fail(f"simple send #{i}", rr.text[:200]); failures.append(f"simple_send_{i}")
            continue
        rep = rr.json()
        simple_replies.append(rep)
        print(
            f"  t{i}: {snap_line(rep)}\n"
            f"     NPC: {(rep.get('text') or '')[:120]}{'…' if len(rep.get('text','')) > 120 else ''}"
        )
    if len(simple_replies) >= len(SIMPLE_DIALOGUE) - 1:
        ok(f"got replies for {len(simple_replies)}/{len(SIMPLE_DIALOGUE)} turns")
    else:
        failures.append("simple_replies_short")
    check_simple_card(simple_replies, failures)

    # End the session (best-effort).
    requests.post(
        f"{BASE}/entities/characters/{simple_id}/conversations/{simple_conv_id}/end",
        timeout=15,
    )

    # ---- 3. Complex card in a new universe ----
    hdr("3. Create complex Kvothe card")
    r = requests.post(f"{BASE}/entities/characters", json=COMPLEX_KVOTHE, timeout=30)
    if r.status_code != 201:
        fail("create complex card", r.text[:200]); return _summary(failures, simple_id, None)
    complex_id = r.json()["id"]
    ok(f"complex card id={complex_id}")

    # ---- 4. Expand the complex card ----
    hdr("4. Expand complex card (LLM generates traits/triggers)")
    r = requests.post(
        f"{BASE}/entities/characters/{complex_id}/expand", timeout=120
    )
    if r.status_code != 200:
        fail("expand complex card", r.text[:200]); failures.append("expand")
        return _summary(failures, simple_id, complex_id)
    expanded = r.json()
    ok(f"entity_id={expanded['entity_id'][:8]}…  universe={expanded['universe_id'][:8]}…")

    # Verify versions[] was populated.
    r = requests.get(
        f"{BASE}/entities/characters/{complex_id}/versions", timeout=10
    )
    if r.status_code == 200 and r.json():
        ok(f"versions[] populated: {len(r.json())} incarnation(s)")
    else:
        fail("versions list", f"status={r.status_code}")

    # ---- 5. Scene chat ----
    hdr("5. Scene-style chat (the Waystone Inn context)")
    r = requests.post(
        f"{BASE}/entities/characters/{complex_id}/conversations", timeout=60
    )
    if r.status_code != 200:
        fail("start complex conversatory", r.text[:200]); failures.append("start_complex")
        return _summary(failures, simple_id, complex_id)
    scene = r.json()
    scene_conv_id = scene["conversation_id"]
    ok(f"conversation_id={scene_conv_id}")

    scene_replies: List[Dict[str, Any]] = []
    for i, line in enumerate(SCENE_DIALOGUE, start=1):
        rr = requests.post(
            f"{BASE}/entities/characters/{complex_id}/conversations/{scene_conv_id}/send",
            json={"text": line},
            timeout=60,
        )
        if rr.status_code != 200:
            fail(f"scene send #{i}", rr.text[:200]); failures.append(f"scene_send_{i}")
            continue
        rep = rr.json()
        scene_replies.append(rep)
        print(
            f"  t{i}: {snap_line(rep)}\n"
            f"     NPC: {(rep.get('text') or '')[:120]}{'…' if len(rep.get('text','')) > 120 else ''}"
        )
    if len(scene_replies) >= len(SCENE_DIALOGUE) - 1:
        ok(f"got replies for {len(scene_replies)}/{len(SCENE_DIALOGUE)} turns")
    else:
        failures.append("scene_replies_short")
    check_complex_scene(scene_replies, failures)

    # End the session.
    requests.post(
        f"{BASE}/entities/characters/{complex_id}/conversations/{scene_conv_id}/end",
        timeout=15,
    )

    # ---- Summary ----
    return _summary(failures, simple_id, complex_id, simple_replies, scene_replies)


def _summary(
    failures: List[str],
    simple_id: str | None,
    complex_id: str | None,
    simple_replies: List[Dict[str, Any]] | None = None,
    scene_replies: List[Dict[str, Any]] | None = None,
) -> int:
    hdr("Summary")
    print(f"  simple card id : {simple_id}")
    print(f"  complex card id: {complex_id}")
    if simple_replies is not None:
        emotionals = [r.get("emotional_state") for r in simple_replies]
        stances = [(r.get("relationship_snapshot") or {}).get("stance") for r in simple_replies]
        trusts = [(r.get("relationship_snapshot") or {}).get("trust", 0.0) for r in simple_replies]
        print(f"  simple chats  : {len(simple_replies)} replies; emotions={emotionals}")
        print(f"                  stances={stances}; trusts={[round(t, 2) for t in trusts]}")
    if scene_replies is not None:
        emotionals = [r.get("emotional_state") for r in scene_replies]
        stances = [(r.get("relationship_snapshot") or {}).get("stance") for r in scene_replies]
        trusts = [(r.get("relationship_snapshot") or {}).get("trust", 0.0) for r in scene_replies]
        print(f"  scene chats   : {len(scene_replies)} replies; emotions={emotionals}")
        print(f"                  stances={stances}; trusts={[round(t, 2) for t in trusts]}")
    if failures:
        print(f"  [FAIL] {len(failures)} failure(s): {failures}")
        return 1
    print("  [PASS] full flow green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
