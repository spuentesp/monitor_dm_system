#!/usr/bin/env python3
"""Live LLM-GM-vs-LLM-player roleplay test — drives the REAL production API.

General by design: takes a universe_id and hits the same POST /api/chat +
POST /api/chat/{id}/send endpoints any real user or the real web UI would.
No per-system scenario data, no hardcoded system choices — the "player"
side is a small LLM loop that reads the GM's last message and improvises
the next line, the same way a human would type into the chat box.

Usage:
    uv run python scripts/live_llm_gm_vs_player_test.py \
        --universe-id <uuid> --world-label "Fallout" --turns 8 \
        --api-url http://localhost:8000/api \
        --output-dir docs/testing/live_gm_vs_player

Requires the UI backend server running (uv run monitor-ui) and a local
Ollama instance for the player model (default: qwen2.5:latest — cheap,
local, doesn't compete with the GM's own provider for rate limit).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import litellm
import requests

litellm.request_timeout = 60
litellm.num_retries = 1
litellm.drop_params = True

PLAYER_SYSTEM_PROMPT = """You are role-playing as a player character in a tabletop RPG session, \
talking to an AI Game Master through a chat interface. Stay in character. Write ONE short \
message (1-4 sentences) as your next thing to say or do -- either in-character action/dialogue, \
or (only during character creation questions) a direct answer to the GM's question.

Rules:
- Never break character or mention you are an AI.
- Never refer to game mechanics, dice, or "the GM" directly unless your character would \
plausibly do so in-fiction.
- Keep responses concise -- this is a chat window, not a novel.
- Be a little unpredictable and take initiative; don't just passively wait for instructions.
- If the GM asks a character-creation question, answer it directly and specifically.
"""


def call_player_llm(model: str, transcript: list[dict[str, str]]) -> str:
    messages = [{"role": "system", "content": PLAYER_SYSTEM_PROMPT}]
    for turn in transcript:
        role = "assistant" if turn["speaker"] == "player" else "user"
        messages.append({"role": role, "content": turn["content"]})
    response = litellm.completion(
        model=model,
        messages=messages,
        temperature=0.9,
        max_tokens=200,
        timeout=60,
    )
    return response.choices[0].message.content.strip()


def create_session(api_url: str, universe_id: str, title: str) -> dict[str, Any]:
    resp = requests.post(
        f"{api_url}/chat",
        json={"universe_id": universe_id, "title": title, "mode": "play"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def send_message(api_url: str, session_id: str, content: str, timeout: float) -> dict[str, Any]:
    resp = requests.post(
        f"{api_url}/chat/{session_id}/send",
        json={"content": content},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def run_session(
    *,
    api_url: str,
    universe_id: str,
    world_label: str,
    turns: int,
    player_model: str,
    send_timeout: float,
    opening_line: str,
) -> dict[str, Any]:
    log: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc)

    session = create_session(api_url, universe_id, f"Live GM-vs-LLM-player: {world_label}")
    session_id = session["id"]
    print(f"[{world_label}] session created: {session_id} (phase={session.get('phase')})", flush=True)

    transcript: list[dict[str, str]] = []
    turn_no = 0
    error: str | None = None

    # create_session()'s response only carries Session fields -- the actual
    # opening GM message (build_gm_opening(), a real hook-ending paragraph)
    # is generated server-side as part of session creation and only visible
    # via the messages endpoint. Fetch it now so the transcript reflects the
    # true first turn instead of starting mid-conversation.
    try:
        existing = requests.get(f"{api_url}/chat/{session_id}/messages", timeout=15).json()
        if existing and existing[0].get("role") == "gm":
            opening_msg = existing[0]
            print(
                f"[{world_label}] turn 0 — gm opening: {opening_msg.get('content', '')[:100]}",
                flush=True,
            )
            transcript.append({"speaker": "gm", "content": opening_msg.get("content", "")})
            log.append({
                "turn": 0,
                "speaker": "gm",
                "content": opening_msg.get("content", ""),
                "metadata": opening_msg.get("metadata", {}),
                "timestamp": opening_msg.get("timestamp", datetime.now(timezone.utc).isoformat()),
            })
    except Exception as exc:  # noqa: BLE001
        print(f"[{world_label}] WARNING: could not fetch opening message: {exc}", flush=True)

    player_line = opening_line

    try:
        while turn_no < turns:
            turn_no += 1
            print(f"[{world_label}] turn {turn_no}/{turns} — player: {player_line[:80]}", flush=True)
            transcript.append({"speaker": "player", "content": player_line})
            log.append({
                "turn": turn_no,
                "speaker": "player",
                "content": player_line,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            t0 = time.monotonic()
            gm_msg = send_message(api_url, session_id, player_line, send_timeout)
            elapsed = time.monotonic() - t0

            gm_content = gm_msg.get("content", "")
            metadata = gm_msg.get("metadata", {})
            print(
                f"[{world_label}] turn {turn_no}/{turns} — gm ({elapsed:.1f}s, "
                f"phase={metadata.get('phase')}): {gm_content[:100]}",
                flush=True,
            )
            transcript.append({"speaker": "gm", "content": gm_content})
            log.append({
                "turn": turn_no,
                "speaker": "gm",
                "content": gm_content,
                "metadata": metadata,
                "elapsed_seconds": round(elapsed, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            player_line = call_player_llm(player_model, transcript)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        print(f"[{world_label}] ERROR at turn {turn_no}: {error}", flush=True)

    return {
        "world_label": world_label,
        "universe_id": universe_id,
        "session_id": session_id,
        "player_model": player_model,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "turns_completed": turn_no,
        "turns_requested": turns,
        "error": error,
        "log": log,
    }


def write_outputs(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = result["world_label"].lower().replace(" ", "_")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"{slug}_{stamp}.json"
    md_path = output_dir / f"{slug}_{stamp}.md"

    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        f"# Live GM-vs-LLM-player transcript — {result['world_label']}",
        "",
        f"- universe_id: `{result['universe_id']}`",
        f"- session_id: `{result['session_id']}`",
        f"- player_model: `{result['player_model']}`",
        f"- turns: {result['turns_completed']}/{result['turns_requested']}",
        f"- error: {result['error'] or 'none'}",
        "",
        "---",
        "",
    ]
    for entry in result["log"]:
        speaker = "**Player**" if entry["speaker"] == "player" else "**GM**"
        lines.append(f"### Turn {entry['turn']} — {speaker}")
        lines.append("")
        lines.append(entry["content"])
        if entry["speaker"] == "gm" and entry.get("metadata"):
            meta = entry["metadata"]
            interesting = {
                k: meta.get(k)
                for k in (
                    "phase", "resolution_type", "success_level", "roll_breakdown",
                    "stat", "difficulty_class", "intent_type",
                )
                if meta.get(k) is not None
            }
            if interesting:
                lines.append("")
                lines.append(f"*meta: {interesting}*")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[{result['world_label']}] wrote {json_path} and {md_path}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--universe-id", required=True)
    ap.add_argument("--world-label", required=True)
    ap.add_argument("--turns", type=int, default=8)
    ap.add_argument("--api-url", default="http://localhost:8000/api")
    ap.add_argument("--player-model", default="ollama/qwen2.5:latest")
    ap.add_argument("--send-timeout", type=float, default=90.0)
    ap.add_argument(
        "--opening-line",
        default="I want to play someone who's survived a long time out here by being careful and watching everyone.",
    )
    ap.add_argument("--output-dir", default="docs/testing/live_gm_vs_player")
    args = ap.parse_args()

    result = run_session(
        api_url=args.api_url,
        universe_id=args.universe_id,
        world_label=args.world_label,
        turns=args.turns,
        player_model=args.player_model,
        send_timeout=args.send_timeout,
        opening_line=args.opening_line,
    )
    write_outputs(result, Path(args.output_dir))

    return 1 if result["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
