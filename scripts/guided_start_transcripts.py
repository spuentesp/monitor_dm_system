#!/usr/bin/env python3
"""Guided-start live transcripts — LLM player vs live auto-GM, per world.

Phase 2 (guided start) acceptance material: plays the full pre-play flow —
setting intro, the start question with this world's options, the question
series, table agreements, and the opening scene — with an LLM player
driving the REAL production API, and writes one transcript per world under
docs/testing/.

Two worlds are covered by default:
  1. a fresh Quick World universe (POST /forge/quick-world), and
  2. an applied-pack universe (a small pack applied via
     POST /ingest/packs/{id}/apply/new-world, accepted and committed).

Usage (backend + databases + a local player model required):
    uv run python scripts/guided_start_transcripts.py \
        --api-url http://localhost:8001/api \
        --player-model ollama/qwen2.5:latest \
        --output-dir docs/testing

Pass --universe-id UUID (repeatable) to skip world creation and play
existing worlds instead. The player model follows the same convention as
scripts/live_llm_gm_vs_player_test.py — cheap and local so it doesn't
compete with the GM's provider.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import litellm
import requests

litellm.request_timeout = 90
litellm.num_retries = 1
litellm.drop_params = True

PLAYER_SYSTEM_PROMPT = """You are role-playing as a player at a tabletop RPG table, \
talking to an AI Game Master through a chat interface during setup (before the first scene).

Rules:
- If the GM asks how you want to begin and offers concrete options, PICK ONE OPTION BY ITS \
EXACT NAME (or say "surprise me"). Never invent a different opening when options are offered.
- If the GM asks who you are, invent a short, vivid character (name, origin, looks).
- Answer each question directly and specifically, in 1-3 sentences.
- When the GM asks to confirm table agreements and nothing is objectionable, reply exactly: \
begin story
- Never mention that you are an AI. Keep it in the spirit of a keen player.
"""

MAX_PLAYER_TURNS = 12


def call_player_llm(model: str, transcript: list[dict[str, str]]) -> str:
    messages = [{"role": "system", "content": PLAYER_SYSTEM_PROMPT}]
    for turn in transcript:
        role = "assistant" if turn["speaker"] == "player" else "user"
        messages.append({"role": role, "content": turn["content"]})
    response = litellm.completion(
        model=model,
        messages=messages,
        temperature=0.9,
        max_tokens=220,
        timeout=90,
    )
    return response.choices[0].message.content.strip()


def _require_ok(response: requests.Response) -> dict[str, Any]:
    if response.status_code >= 400:
        raise RuntimeError(f"{response.status_code}: {response.text[:500]}")
    return response.json() if response.text else {}


def create_quick_world(api_url: str, seed: str) -> dict[str, Any]:
    data = _require_ok(
        requests.post(f"{api_url}/forge/quick-world", json={"seed": seed}, timeout=300)
    )
    return {
        "label": "quick_world",
        "universe_id": data["universe_id"],
        "multiverse_id": data.get("multiverse_id"),
        "world_name": data.get("world_name", seed[:40]),
    }


def create_pack_world(api_url: str) -> dict[str, Any]:
    """A small pack applied to a brand-new world, accepted and committed."""
    from monitor_data.schemas.knowledge_packs import (
        ExtractedAgenda,
        ExtractedEntityArchetype,
        ExtractedLoreFact,
        ExtractedPlotThread,
        KnowledgePackCreate,
        KnowledgePackStatus,
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools import mongodb_create_knowledge_pack

    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    pack = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name=f"Guided Start Transcript Pack {stamp}",
            description="Transcript content pack for the guided start",
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
            status=KnowledgePackStatus.READY,
            entity_archetypes=[
                ExtractedEntityArchetype(
                    name="Sister Aveline",
                    entity_type="character",
                    description="A bell-keeper of the drowned cathedral.",
                ),
                ExtractedEntityArchetype(
                    name="Cass the Ferryman",
                    entity_type="character",
                    description="Ferries the dead across the flooded nave.",
                ),
                ExtractedEntityArchetype(
                    name="The Drowned Cathedral",
                    entity_type="location",
                    description="A cathedral half-sunk in the harbour.",
                ),
            ],
            lore_facts=[
                ExtractedLoreFact(
                    statement="The cathedral bells ring below the waterline.",
                    source_ref="transcript",
                )
            ],
            agendas=[
                ExtractedAgenda(
                    title="Silence the bells", description="Aveline wants the bells stopped."
                )
            ],
            plot_threads=[
                ExtractedPlotThread(
                    title="Who rings the bells", description="The ringers drowned years ago."
                ),
                ExtractedPlotThread(
                    title="Cass's last fare", description="One passenger never paid."
                ),
            ],
        )
    )
    applied = _require_ok(
        requests.post(
            f"{api_url}/ingest/packs/{pack.id}/apply/new-world",
            json={"world_name": f"Drowned See {stamp}"},
            timeout=180,
        )
    )
    proposals = _require_ok(
        requests.get(
            f"{api_url}/ingest/packs/{pack.id}/proposals",
            params={"status": "pending", "per_page": 500},
            timeout=60,
        )
    )
    pending = proposals.get("proposals", [])
    if pending:
        _require_ok(
            requests.post(
                f"{api_url}/ingest/proposals/batch",
                json={
                    "actions": [
                        {
                            "proposal_id": p["proposal_id"],
                            "action": "accept",
                            "reason": "transcript auto-accept",
                        }
                        for p in pending
                    ]
                },
                timeout=120,
            )
        )
        _require_ok(requests.post(f"{api_url}/ingest/packs/{pack.id}/commit", timeout=180))
    return {
        "label": "pack_world",
        "universe_id": applied["universe_id"],
        "multiverse_id": applied.get("multiverse_id"),
        "world_name": applied.get("world_name", "pack world"),
    }


def play_preplay(api_url: str, world: dict[str, Any], player_model: str) -> dict[str, Any]:
    """Play the guided start with an LLM player; return the transcript."""
    session = _require_ok(
        requests.post(
            f"{api_url}/chat",
            json={
                "title": f"Guided start transcript — {world['label']}",
                "mode": "autonomous_gm",
                "tone": "dramatic",
                "universe_id": world["universe_id"],
                "multiverse_id": world.get("multiverse_id"),
            },
            timeout=120,
        )
    )
    session_id = session["id"]

    messages = _require_ok(requests.get(f"{api_url}/chat/{session_id}/messages", timeout=60))
    transcript: list[dict[str, str]] = []
    gm_turns = 0
    start_options: list[Any] = []
    materialized: dict[str, Any] = {}
    phase = "character_interview"

    for message in messages:
        if message.get("role") == "gm":
            gm_turns += 1
            transcript.append({"speaker": "gm", "content": message.get("content", "")})
            meta = message.get("metadata") or {}
            if meta.get("start_options"):
                start_options = meta["start_options"]

    for _ in range(MAX_PLAYER_TURNS):
        if phase == "active_play":
            break
        player_line = call_player_llm(player_model, transcript)
        transcript.append({"speaker": "player", "content": player_line})
        response = _require_ok(
            requests.post(
                f"{api_url}/chat/{session_id}/send",
                json={"content": player_line},
                timeout=240,
            )
        )
        gm_turns += 1
        meta = response.get("metadata") or {}
        transcript.append({"speaker": "gm", "content": response.get("content", "")})
        if meta.get("materialized_start"):
            materialized = meta["materialized_start"]
        if meta.get("preplay_finalized"):
            phase = "active_play"
            break
        if meta.get("phase"):
            phase = meta["phase"]

    return {
        "session_id": session_id,
        "gm_turns": gm_turns,
        "phase": phase,
        "start_options": start_options,
        "materialized": materialized,
        "transcript": transcript,
    }


def write_transcript(output_dir: Path, world: dict[str, Any], run: dict[str, Any]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = output_dir / f"guided_start_{world['label']}_{stamp}.md"
    lines = [
        f"# Guided start transcript — {world['world_name']} ({world['label']})",
        "",
        f"- Date: {stamp} (UTC)",
        f"- Universe: `{world['universe_id']}`",
        f"- Session: `{run['session_id']}`",
        f"- GM turns taken: {run['gm_turns']} (done-when: at most 5)",
        f"- End phase: {run['phase']}",
        "",
        "## Start options offered",
        "",
    ]
    for option in run["start_options"]:
        lines.append(
            f"- **{option.get('title')}** — {option.get('summary') or option.get('hook') or ''}"
        )
    lines += [
        "",
        "## Materialized start",
        "",
        "```json",
        json.dumps(run["materialized"], indent=2),
        "```",
        "",
        "## Transcript",
        "",
    ]
    for turn in run["transcript"]:
        speaker = "MONITOR" if turn["speaker"] == "gm" else "Player"
        lines.append(f"**{speaker}:** {turn['content']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8001/api")
    parser.add_argument("--player-model", default="ollama/qwen2.5:latest")
    parser.add_argument("--output-dir", default="docs/testing")
    parser.add_argument(
        "--universe-id",
        action="append",
        default=[],
        help="Play an existing universe instead of creating worlds (repeatable).",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    worlds: list[dict[str, Any]] = []
    if args.universe_id:
        for universe_id in args.universe_id:
            worlds.append(
                {
                    "label": f"universe_{universe_id[:8]}",
                    "universe_id": universe_id,
                    "world_name": universe_id,
                }
            )
    else:
        worlds.append(
            create_quick_world(args.api_url, "a rain-soaked port where the tide-locks are failing")
        )
        worlds.append(create_pack_world(args.api_url))

    written: list[Path] = []
    for world in worlds:
        print(f"Playing guided start in {world['label']} ({world['universe_id']})...", flush=True)
        run = play_preplay(args.api_url, world, args.player_model)
        path = write_transcript(output_dir, world, run)
        written.append(path)
        print(f"  -> {run['gm_turns']} GM turns, phase {run['phase']}; wrote {path}", flush=True)

    print("Done. Transcripts:")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
