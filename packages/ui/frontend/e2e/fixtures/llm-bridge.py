#!/usr/bin/env python3
"""LLM-backed Playwright driver.

Reads GM-bubble JSON on stdin (one object per line, e.g.
  {"role": "gm", "content": "...", "intent": "..."}
) and writes the next player turn on stdout
  {"text": "...", "intent": "..."}

Re-uses ``InstructablePlayer.InstructedSpec`` so the test runner can pass
the same model / temperature / max_tokens as ``scripts/e2e_full_loop.py``,
and so behavior matches the harness exactly — same fallback, same retries,
same canonical model name (``ollama/qwen2.5:latest`` via litellm).

Why a subprocess bridge, not a browser-side driver: in-browser JS
chatting directly to Ollama would (a) leak the API to the page bundle,
(b) block the event loop on token generation, and (c) duplicate the
``InstructedSpec`` plumbing. Re-using the Python driver keeps a single
implementation of "LLM-backed player" across the harness and the browser
tests.

Wire protocol
=============

stdin (one JSON object per line)::
    {"role": "system_setup", "concept": "...", "seed": "...", "goal": "..."}
    {"role": "gm",         "content": "..."}
    {"role": "gm",         "content": "..."}
    ... (any number of gm bubbles)
    {"role": "request",    "timeout_s": 60}            <- emits one player turn

stdout (one JSON object per line)::
    {"text": "...", "intent": "in-character", "latency_ms": 1234}

A ``request`` flushes the buffered GM bubbles into the player's history,
calls the LLM, and writes the result. Multiple ``request`` lines drive
multiple turns; a final ``{"role": "shutdown"}`` exits cleanly.

Setup
=====

::

    # from the e2e runner (Node)
    const bridge = spawn("python", ["e2e/fixtures/llm-bridge.py"], {
      env: { ...process.env, MONITOR_PLAYTEST_MODEL: "ollama/qwen2.5:latest" },
      stdio: ["pipe", "pipe", "inherit"],
    });
    bridge.stdout.setEncoding("utf8");
    bridge.stdout.on("data", (chunk) => { ...parse JSON lines... });

Env vars (all optional, all default to InstructedSpec's defaults):
    MONITOR_PLAYTEST_MODEL — e.g. "ollama/qwen2.5:latest"
    MONITOR_PLAYTEST_TEMPERATURE — default 0.7
    MONITOR_PLAYTEST_MAX_TOKENS  — default 220
    MONITOR_PLAYTEST_TIMEOUT_S   — per-turn wall-clock, default 60
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Make the agents + data-layer packages importable without a venv switch.
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages" / "agents" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages" / "data-layer" / "src"))

from monitor_agents.players import (  # noqa: E402  (sys.path tweak above)
    InstructablePlayer,
    InstructedSpec,
    PlayerContext,
)


def main() -> int:
    model = os.environ.get("MONITOR_PLAYTEST_MODEL", "ollama/qwen2.5:latest")
    temperature = float(os.environ.get("MONITOR_PLAYTEST_TEMPERATURE", "0.7"))
    max_tokens = int(os.environ.get("MONITOR_PLAYTEST_MAX_TOKENS", "220"))
    timeout_s = float(os.environ.get("MONITOR_PLAYTEST_TIMEOUT_S", "60"))

    context = PlayerContext(
        concept="",
        seed="",
        goal="drive the scene forward; react to the GM's last narration.",
    )
    spec = InstructedSpec(
        model=model,
        scripted_opens=[],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    player = InstructablePlayer(spec=spec, context=context, recent_turns_max=3)

    history: list[dict[str, str]] = []
    stdin = sys.stdin

    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"bad-json: {exc}"}), flush=True)
            continue

        kind = msg.get("role")
        if kind == "system_setup":
            context.concept = msg.get("concept", context.concept)
            context.seed = msg.get("seed", context.seed)
            context.goal = msg.get("goal", context.goal)
            continue
        if kind == "gm":
            player.observe(
                gm_text=msg.get("content", ""),
                player_text="",
                intent=msg.get("intent", "gm"),
            )
            history.append({"role": "gm", "content": msg.get("content", "")})
            continue
        if kind == "shutdown":
            return 0
        if kind != "request":
            print(json.dumps({"error": f"unknown role {kind!r}"}), flush=True)
            continue

        per_turn_timeout = float(msg.get("timeout_s", timeout_s))
        t0 = time.perf_counter()
        try:
            text, intent = _next_with_timeout(player.next, per_turn_timeout)
        except Exception as exc:  # noqa: BLE001 — surfaced to the runner
            text, intent = "(player timed out)", "fallback (bridge timeout)"
            print(json.dumps({"error": str(exc)}), flush=True)
        latency_ms = (time.perf_counter() - t0) * 1000

        print(
            json.dumps({"text": text, "intent": intent, "latency_ms": latency_ms}),
            flush=True,
        )
    return 0


def _next_with_timeout(coro, timeout_s: float):
    """Wrap asyncio.run around a single coroutine with a hard wall clock."""
    import asyncio

    async def _go():
        return await asyncio.wait_for(coro(), timeout=timeout_s)

    return asyncio.run(_go())


if __name__ == "__main__":
    raise SystemExit(main())