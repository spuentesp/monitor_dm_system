#!/usr/bin/env python3
"""
End-to-end verification of the character conversatory against the live stack.

  1. Create a light card (POST /api/entities/characters).
  2. Expand it (POST /api/entities/characters/{id}/expand) → entity + NPCProfile.
  3. Start a conversation (POST .../conversations) → conversation_id + opening.
  4. Send 4 escalating lines (POST .../conversations/{id}/send) and observe
     emotional_state + relationship_snapshot each turn.
  5. End the session.
  6. List past conversations to confirm persistence.

Usage:
    python scripts/e2e_character_conversatory.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests

BASE = os.environ.get("MONITOR_API", "http://127.0.0.1:8765/api")


def hdr(line: str) -> None:
    print("\n" + "=" * 8 + " " + line + " " + "=" * (60 - len(line) - 2))


def main() -> int:
    hdr("1. Create light card")
    card = {
        "name": "Maeve (e2e)",
        "description": "A weary dockside tavern keeper hiding a smuggling past.",
        "personality": (
            "Dry, watchful, slow to trust. Warms only to those who show kindness "
            "to her niece Wren."
        ),
        "gm_notes": "Hides an informant past; panics if accused directly.",
        "first_message": "*polishes a glass* You look like trouble. Sit.",
    }
    r = requests.post(f"{BASE}/entities/characters", json=card, timeout=30)
    r.raise_for_status()
    ch = r.json()
    cid = ch["id"]
    print(f"  created id={cid}  entity_id={ch.get('entity_id')}")

    hdr("2. Expand to MONITOR profile")
    r = requests.post(f"{BASE}/entities/characters/{cid}/expand", timeout=60)
    r.raise_for_status()
    exp = r.json()
    print(f"  entity_id={exp['entity_id'][:8]}…  universe_id={exp['universe_id'][:8]}…")

    hdr("3. Start conversation")
    r = requests.post(f"{BASE}/entities/characters/{cid}/conversations", timeout=60)
    r.raise_for_status()
    conv = r.json()
    conv_id = conv["conversation_id"]
    print(f"  conversation_id={conv_id}")
    print(f"  opening: {conv['opening']}")

    hdr("4. Send 4 escalating lines")
    lines = [
        "Evening. Something warm, please.",
        "I heard there've been disappearances on the docks. You hear anything?",
        "Your niece Wren — is she around?",
        "I know about the syndicate, Maeve. I also know about the informant money that bought this place.",
    ]
    for i, line in enumerate(lines, 1):
        r = requests.post(
            f"{BASE}/entities/characters/{cid}/conversations/{conv_id}/send",
            json={"text": line},
            timeout=60,
        )
        r.raise_for_status()
        rep = r.json()
        snap = rep.get("relationship_snapshot", {}) or {}
        trust = snap.get("trust", 0.0)
        stance = snap.get("stance", "?")
        delta = snap.get("last_delta", {})
        print(f"\n  turn {i} (player: {line[:60]}{'…' if len(line) > 60 else ''})")
        print(f"    char  : {rep.get('text','')[:120]}{'…' if len(rep.get('text','')) > 120 else ''}")
        print(f"    feel  : {rep.get('emotional_state')}")
        print(f"    stance: {stance}  trust={trust:+.2f}  delta={delta}")
        time.sleep(0.2)

    hdr("5. End conversation")
    r = requests.post(
        f"{BASE}/entities/characters/{cid}/conversations/{conv_id}/end", timeout=30
    )
    r.raise_for_status()
    end = r.json()
    print(f"  {end}")

    hdr("6. List past conversations")
    r = requests.get(
        f"{BASE}/entities/characters/{cid}/conversations", timeout=10
    )
    r.raise_for_status()
    hist = r.json()
    for h in hist[:3]:
        print(
            f"  {h.get('conversation_id','?')[:8]}…  status={h.get('status')}  "
            f"turns={h.get('turn_count')}  updated={h.get('updated_at')}"
        )

    hdr("Done")
    print(f"  character id: {cid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
