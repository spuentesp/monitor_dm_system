#!/usr/bin/env python3
"""Light-RP recall check: 30 turns over two sittings against /v1/chat/completions.

Drives the OpenAI-compatible endpoint in session mode (``character_id`` +
``stream=true``) exactly as an external client would:

  * Sitting 1 — a short chat that plants a distinctive detail (a random
    code word tied to the player's "childhood village").
  * A pause (``--gap`` seconds) so the sittings are genuinely separate.
  * Sitting 2 — a fresh conversation (empty client history) with more
    chat, then recall probes that ask for the planted detail.

PASS: at least one probe reply contains the planted code word — the
character recalled a detail from the first sitting across conversations.

This script needs a live backend with a configured LLM; the coordinator runs
it (it is not part of the hermetic suite). It never prints or stores the API
token. Usage:

    MONITOR_API_TOKEN=... uv run python scripts/light_rp_recall_check.py \
        --base-url http://localhost:8000 --turns 30 --out /tmp/recall.md

Optionally ``--character-id`` reuses an existing standalone character card;
otherwise a throwaway card is created for the run.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TURNS = 30
DEFAULT_GAP_SECONDS = 60


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------


def make_code_word() -> str:
    """A random token the model cannot confabulate."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))  # noqa: S311
    return f"zephyr-{suffix}"


def plan_turns(total_turns: int, code_word: str) -> tuple[list[str], list[str], list[str]]:
    """Split the run into (sitting_1_lines, sitting_2_lines, probe_lines).

    The detail is planted early in sitting 1 so later turns put distance
    (and a conversation boundary) between it and the probes. Each sitting is
    padded with small-talk filler to fill the requested turn budget.
    """
    base_1 = [
        "Hi! I've been looking forward to this.",
        f"By the way, remember this for next time: the safe word for my childhood village is {code_word}.",
        "Just settling in — how have you been lately?",
        "Anyway, what does the evening look like around here?",
        "That sounds lovely. Tell me more about the people here.",
        "Do they celebrate any festivals?",
        "What's the food like this time of year?",
        "You always describe it so well.",
    ]
    base_2 = [
        "Hello again — I'm back for another chat.",
        "Different day, same strange world. What's new?",
        "I was thinking about our earlier talks.",
        "What would you say is your favourite place to sit and think?",
        "That's a good answer. How do you usually spend your mornings?",
        "Do you remember how we first met?",
    ]
    probes = [
        "Before we stop — do you remember the safe word I told you for my childhood village?",
        "One more thing: what was that safe word again? Just the word.",
    ]
    filler = [
        "Tell me something small and true about today.",
        "What's on your mind?",
        "How does the weather treat you?",
        "Who do you trust most around here?",
        "What are you hoping for this week?",
        "Describe a sound you love.",
    ]
    total = max(6, int(total_turns))
    half = (total + 1) // 2
    rest = total - half

    def _fill(base: list[str], count: int) -> list[str]:
        out = base[:count]
        i = 0
        while len(out) < count:
            out.append(filler[i % len(filler)])
            i += 1
        return out

    return _fill(base_1, half), _fill(base_2, rest), probes


def check_recall(probe_replies: list[str], code_word: str) -> bool:
    """PASS when any probe reply carries the planted code word."""
    needle = code_word.lower()
    return any(needle in (reply or "").lower() for reply in probe_replies)


def parse_sse_chunks(body: str) -> list[dict[str, Any]]:
    """Parse ``data:`` SSE frames into JSON payloads (skipping [DONE])."""
    out: list[dict[str, Any]] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            out.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return out


def reply_text_from_chunks(chunks: list[dict[str, Any]]) -> tuple[str, str | None]:
    """Reassemble the streamed reply text and the session id (when echoed)."""
    parts: list[str] = []
    session_id: str | None = None
    for chunk in chunks:
        session_id = session_id or chunk.get("monitor_session_id")
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                parts.append(delta["content"])
    return "".join(parts), session_id


# ---------------------------------------------------------------------------
# HTTP (stdlib only — no extra deps for a coordinator-run script)
# ---------------------------------------------------------------------------


def _request(
    base_url: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 300.0,
) -> tuple[int, str, dict[str, str]]:
    url = base_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers.items())
    except urllib.error.HTTPError as exc:  # surface the server's detail
        return exc.code, exc.read().decode("utf-8", "replace"), dict(exc.headers.items())


class LightRpClient:
    """Thin session-mode client over the OpenAI-compatible endpoint."""

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token

    def create_character(self, name: str) -> dict[str, Any]:
        status, body, _ = _request(
            self.base_url,
            self.token,
            "POST",
            "/api/entities/characters",
            {"name": name, "description": "Throwaway card for the light-RP recall check."},
        )
        if status >= 300:
            raise RuntimeError(f"create_character failed ({status}): {body[:500]}")
        return json.loads(body)

    def chat(
        self,
        messages: list[dict[str, str]],
        character_id: str,
        persona_id: str | None,
        stream: bool = True,
    ) -> tuple[str, str | None]:
        """One streamed completion in session mode. Returns (reply, session_id)."""
        payload: dict[str, Any] = {
            "model": "monitor-default",
            "messages": messages,
            "stream": stream,
            "character_id": character_id,
        }
        if persona_id:
            payload["persona_character_id"] = persona_id
        status, body, headers = _request(
            self.base_url,
            self.token,
            "POST",
            "/api/v1/chat/completions",
            payload,
        )
        if status >= 300:
            raise RuntimeError(f"chat failed ({status}): {body[:500]}")
        if stream:
            chunks = parse_sse_chunks(body)
            text, session_id = reply_text_from_chunks(chunks)
            session_id = session_id or headers.get("X-Monitor-Session-Id")
            return text, session_id
        doc = json.loads(body)
        return doc["choices"][0]["message"]["content"], doc.get("monitor_session_id")

    def end_conversation(self, character_id: str, conversation_id: str) -> None:
        status, body, _ = _request(
            self.base_url,
            self.token,
            "POST",
            f"/api/entities/characters/{character_id}/conversations/{conversation_id}/end",
        )
        if status >= 300:
            raise RuntimeError(f"end_conversation failed ({status}): {body[:500]}")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    token = os.environ.get(args.token_env, "").strip()
    if not token:
        print(
            f"error: set {args.token_env} (the API token) — it is never printed.", file=sys.stderr
        )
        return 2

    client = LightRpClient(args.base_url, token)
    code_word = make_code_word()
    sitting_1, sitting_2, probes = plan_turns(args.turns, code_word)
    transcript: list[str] = [
        "# Light-RP recall check transcript",
        "",
        f"- base url: {args.base_url}",
        f"- turns: {args.turns} over 2 sittings (+{len(probes)} probe turns)",
        f"- planted code word: `{code_word}`",
        "",
    ]

    if args.character_id:
        character_id = args.character_id
    else:
        char = client.create_character(f"Recall Check {int(time.time())}")
        character_id = str(char["id"])
    transcript.append(f"- character: `{character_id}`")

    probe_replies: list[str] = []
    session_ids: list[str] = []

    def run_sitting(label: str, lines: list[str]) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        transcript.append(f"\n## {label}\n")
        for i, line in enumerate(lines, 1):
            history.append({"role": "user", "content": line})
            started = time.monotonic()
            reply, session_id = client.chat(history, character_id, args.persona_id, stream=True)
            elapsed = time.monotonic() - started
            history.append({"role": "assistant", "content": reply})
            if session_id and session_id not in session_ids:
                session_ids.append(session_id)
            transcript.append(f"### {label} turn {i} ({elapsed:.1f}s, session `{session_id}`)")
            transcript.append(f"- user: {line}")
            transcript.append(f"- character: {reply.strip()}")
            transcript.append("")
            print(f"[{label} {i}/{len(lines)}] {elapsed:.1f}s")
        return history

    # ── Sitting 1 ────────────────────────────────────────────────────────
    run_sitting("Sitting 1", sitting_1)
    if session_ids:
        client.end_conversation(character_id, session_ids[-1])

    # ── Gap between sittings ────────────────────────────────────────────
    if args.gap > 0:
        print(f"waiting {args.gap}s between sittings…")
        time.sleep(args.gap)

    # ── Sitting 2 (fresh conversation) + recall probes ──────────────────
    history = run_sitting("Sitting 2", sitting_2)
    transcript.append("\n## Recall probes\n")
    for i, probe in enumerate(probes, 1):
        history.append({"role": "user", "content": probe})
        reply, session_id = client.chat(history, character_id, args.persona_id, stream=True)
        history.append({"role": "assistant", "content": reply})
        probe_replies.append(reply)
        transcript.append(f"### Probe {i} (session `{session_id}`)")
        transcript.append(f"- user: {probe}")
        transcript.append(f"- character: {reply.strip()}")
        transcript.append("")
        print(f"[probe {i}] {reply.strip()[:120]}")

    if session_ids:
        try:
            client.end_conversation(character_id, session_ids[-1])
        except RuntimeError as exc:
            print(f"warning: {exc}", file=sys.stderr)

    passed = check_recall(probe_replies, code_word)
    transcript.append(f"\n## Result: {'PASS' if passed else 'FAIL'}\n")
    transcript.append(
        "PASS — the character recalled the code word from sitting 1."
        if passed
        else f"FAIL — no probe reply contains the code word `{code_word}`."
    )
    out_path = os.path.abspath(args.out)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(transcript) + "\n")
    print(f"\n{'PASS' if passed else 'FAIL'} — transcript written to {out_path}")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("MONITOR_LIGHT_RP_BASE_URL", DEFAULT_BASE_URL)
    )
    parser.add_argument(
        "--token-env", default="MONITOR_API_TOKEN", help="env var holding the API token"
    )
    parser.add_argument(
        "--character-id", default=None, help="reuse an existing standalone character"
    )
    parser.add_argument("--persona-id", default=None, help="persona card to play as")
    parser.add_argument(
        "--turns", type=int, default=DEFAULT_TURNS, help="conversational turns across both sittings"
    )
    parser.add_argument(
        "--gap", type=int, default=DEFAULT_GAP_SECONDS, help="seconds between sittings"
    )
    parser.add_argument(
        "--out", default="light_rp_recall_transcript.md", help="transcript output path"
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
