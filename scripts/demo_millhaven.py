#!/usr/bin/env python3
"""One-command demo world (FINAL_FABLE T-045).

Creates the "Millhaven" sample setting from SYSTEM.md against the running
backend: multiverse → universe → canonized content pack (NPCs, locations,
lore) → a ready-to-play session. Open the Play page afterwards and the
session is waiting.

Usage:
    uv run python scripts/demo_millhaven.py [--api-url http://localhost:8001/api]
"""

from __future__ import annotations

import argparse
import os
import sys
from uuid import uuid4

import requests

DEFAULT_API = os.environ.get("MONITOR_API_URL", "http://localhost:8001/api")

LORE = [
    "An unnatural mist clings to Millhaven's streets after dusk.",
    "Villagers have been disappearing for three nights running.",
    "Elder Magda vanished first; her body was never found.",
    "Fresh drag marks lead from the town square toward the old cemetery.",
]

ENTITIES = [
    ("Barnaby the Innkeeper", "character", "A nervous innkeeper who locks his doors at sundown and knows more than he says."),
    ("Elder Magda", "character", "The missing village elder. Her silver amulet has not been seen since the night she vanished."),
    ("Millhaven Inn", "location", "Warm light, thin walls, and the only safe beds in the village."),
    ("Millhaven Cemetery", "location", "Fog-bound graves at the village edge. A freshly disturbed plot lies near the crypt."),
    ("The Shadow Cabal", "faction", "A whispered conspiracy said to trade in stolen villagers and darker things."),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=DEFAULT_API)
    args = parser.parse_args()
    api = args.api_url.rstrip("/")

    try:
        requests.get(f"{api}/health", timeout=5).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"Backend not reachable at {api}: {exc}")
        return 1

    # Idempotency: reuse an existing Millhaven if present
    universes = requests.get(f"{api}/universes/universes", timeout=30).json()
    existing = next((u for u in universes if u.get("name") == "Millhaven"), None)
    if existing:
        print(f"Millhaven already exists ({existing['id']}) — creating a fresh session only.")
        mv_id, u_id = existing.get("multiverse_id"), existing["id"]
    else:
        mv = requests.post(
            f"{api}/universes/multiverses",
            json={"name": "The Mistlands", "description": "Demo setting (Millhaven)"},
            timeout=30,
        )
        mv.raise_for_status()
        mv_id = mv.json()["id"]

        u = requests.post(
            f"{api}/universes/universes",
            json={
                "multiverse_id": mv_id,
                "name": "Millhaven",
                "description": "A fog-bound village where people disappear after dark.",
                "genre": "dark fantasy",
            },
            timeout=30,
        )
        u.raise_for_status()
        u_id = u.json()["id"]
        print(f"Universe created: Millhaven ({u_id})")

        # Canonize the demo content pack straight into the universe
        from monitor_data.schemas.knowledge_packs import (  # noqa: PLC0415
            ExtractedEntityArchetype,
            ExtractedLoreFact,
            KnowledgePackCreate,
            KnowledgePackStatus,
            KnowledgePackType,
        )
        from monitor_data.tools.mongodb_tools import (  # noqa: PLC0415
            mongodb_create_knowledge_pack,
        )

        pack = mongodb_create_knowledge_pack(
            KnowledgePackCreate(
                name=f"Millhaven Demo Pack {uuid4().hex[:6]}",
                description="Demo content for the Millhaven scenario",
                pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
                status=KnowledgePackStatus.READY,
                entity_archetypes=[
                    ExtractedEntityArchetype(name=n, entity_type=t, description=d)
                    for n, t, d in ENTITIES
                ],
                lore_facts=[
                    ExtractedLoreFact(statement=stmt, source_ref="demo") for stmt in LORE
                ],
            )
        )
        canonized = requests.post(
            f"{api}/ingest/packs/{pack.id}/canonize",
            json={"multiverse_id": mv_id, "universe_id": u_id},
            timeout=180,
        )
        canonized.raise_for_status()
        print(f"Canonized demo pack: {len(ENTITIES)} entities, {len(LORE)} facts")

    session = requests.post(
        f"{api}/chat",
        json={
            "title": "The Millhaven Disappearances",
            "mode": "autonomous_gm",
            "multiverse_id": mv_id,
            "universe_id": u_id,
            "universe_label": "Millhaven",
            "tone": "mystery",
        },
        timeout=120,
    )
    session.raise_for_status()
    sid = session.json()["id"]

    print()
    print("Demo ready!")
    print(f"  Universe:  Millhaven ({u_id})")
    print(f"  Session:   The Millhaven Disappearances ({sid})")
    print("  Open http://localhost:3000/play and pick the session —")
    print('  try: "I ask Barnaby about the disappearances."')
    return 0


if __name__ == "__main__":
    sys.exit(main())
