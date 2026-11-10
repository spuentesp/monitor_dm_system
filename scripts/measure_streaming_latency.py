#!/usr/bin/env python3
"""Measure time-to-first-token and total reply time against a live backend.

Drives the streaming endpoints exactly as a client would and timestamps each
SSE frame as it arrives, so the numbers reflect what a player experiences:

  * ``--mode openai``       — POST /v1/chat/completions with ``stream=true``
    in session mode (``character_id`` or ``monitor_session_id``), the same
    path SillyTavern uses.
  * ``--mode send-stream``  — the Conversatory's streaming send
    (``POST /api/entities/characters/{id}/conversations/{cid}/send-stream``).

Per run it reports: time to first token (TTFT), time to the final frame,
total bytes/tokens streamed. The summary reports min / median / max TTFT.

This script needs a live backend with a configured model; the coordinator
runs it (it is not part of the hermetic suite). It never prints or stores the
API token. Usage:

    MONITOR_API_TOKEN=... uv run python scripts/measure_streaming_latency.py \
        --mode openai --character-id <id> --message "Well met." --runs 3

    MONITOR_API_TOKEN=... uv run python scripts/measure_streaming_latency.py \
        --mode send-stream --character-id <id> --conversation-id <id> --runs 3

Without a backend it fails fast with a connection error — it is a
measurement tool, not a test.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_MESSAGE = "Well met! What brings you to these parts?"
DEFAULT_RUNS = 3


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------


def sse_payload(line: str) -> str | None:
    """Return the ``data:`` payload of one SSE line, else None."""
    if not line.startswith("data: "):
        return None
    return line[len("data: ") :].strip() or None


def parse_frame(line: str) -> tuple[str, dict[str, Any] | None]:
    """Classify one SSE line as ('data', payload) | ('done', None) | ('skip', None)."""
    payload = sse_payload(line)
    if payload is None:
        return "skip", None
    if payload == "[DONE]":
        return "done", None
    try:
        return "data", json.loads(payload)
    except json.JSONDecodeError:
        return "skip", None


def frame_text(payload: dict[str, Any], mode: str) -> str:
    """Extract the streamed text delta from one frame, per endpoint shape."""
    if mode == "send-stream":
        if payload.get("type") == "token":
            return str(payload.get("text") or "")
        return ""
    out: list[str] = []
    for choice in payload.get("choices") or []:
        delta = choice.get("delta") or {}
        if isinstance(delta.get("content"), str):
            out.append(delta["content"])
    return "".join(out)


def is_final_frame(payload: dict[str, Any], mode: str) -> bool:
    """True for the frame that completes the reply on each endpoint."""
    if mode == "send-stream":
        return payload.get("type") == "done"
    for choice in payload.get("choices") or []:
        if choice.get("finish_reason"):
            return True
    return False


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-run measurements into a compact summary."""
    ttfts = [r["ttft_seconds"] for r in runs if r.get("ttft_seconds") is not None]
    totals = [r["total_seconds"] for r in runs]
    return {
        "runs": len(runs),
        "ttft_seconds": {
            "min": min(ttfts) if ttfts else None,
            "median": statistics.median(ttfts) if ttfts else None,
            "max": max(ttfts) if ttfts else None,
        },
        "total_seconds": {
            "min": min(totals) if totals else None,
            "median": statistics.median(totals) if totals else None,
            "max": max(totals) if totals else None,
        },
        "first_token_before_completion": all(
            r.get("ttft_seconds") is not None and r["ttft_seconds"] < r["total_seconds"]
            for r in runs
        ),
    }


# ---------------------------------------------------------------------------
# HTTP (stdlib only — no extra deps for a coordinator-run script)
# ---------------------------------------------------------------------------


def _open_stream(
    base_url: str, token: str, path: str, payload: dict[str, Any], timeout: float
) -> Any:
    req = urllib.request.Request(  # noqa: S310
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310


def measure_run(base_url: str, token: str, mode: str, args: argparse.Namespace) -> dict[str, Any]:
    """One streamed request; returns the timing measurement for it."""
    if mode == "send-stream":
        path = (
            f"/api/entities/characters/{args.character_id}"
            f"/conversations/{args.conversation_id}/send-stream"
        )
        payload: dict[str, Any] = {"text": args.message, "include_cross_incarnation": False}
    else:
        path = "/v1/chat/completions"
        payload = {
            "model": args.model,
            "messages": [{"role": "user", "content": args.message}],
            "stream": True,
            "character_id": args.character_id,
        }
        if args.session_id:
            payload.pop("character_id", None)
            payload["monitor_session_id"] = args.session_id

    run: dict[str, Any] = {
        "mode": mode,
        "ttft_seconds": None,
        "total_seconds": None,
        "chunks": 0,
        "chars": 0,
        "finished": False,
        "error": None,
    }
    started = time.monotonic()
    try:
        with _open_stream(base_url, token, path, payload, args.timeout) as resp:
            if resp.status >= 300:
                run["error"] = f"HTTP {resp.status}"
                run["total_seconds"] = time.monotonic() - started
                return run
            for raw in resp:
                kind, frame = parse_frame(raw.decode("utf-8", "replace").strip())
                if kind == "skip":
                    continue
                now = time.monotonic()
                if kind == "done":
                    run["finished"] = True
                    break
                if frame is None:
                    continue
                text = frame_text(frame, mode)
                if text:
                    if run["ttft_seconds"] is None:
                        run["ttft_seconds"] = now - started
                    run["chunks"] += 1
                    run["chars"] += len(text)
                if is_final_frame(frame, mode):
                    run["finished"] = True
                    break
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        run["error"] = f"{type(exc).__name__}: {exc}"
    run["total_seconds"] = time.monotonic() - started
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--mode", choices=("openai", "send-stream"), default="openai")
    parser.add_argument("--character-id")
    parser.add_argument("--conversation-id", help="send-stream mode: the conversation to continue")
    parser.add_argument(
        "--session-id", help="openai mode: resume a monitor_session_id instead of character_id"
    )
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--model", default="monitor-default")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--out", help="write the JSON report to this path as well")
    args = parser.parse_args(argv)

    if args.mode == "send-stream" and not (args.character_id and args.conversation_id):
        parser.error("--mode send-stream requires --character-id and --conversation-id")
    if args.mode == "openai" and not (args.character_id or args.session_id):
        parser.error("--mode openai requires --character-id (or --session-id to resume)")

    token = os.environ.get("MONITOR_API_TOKEN", "")
    runs: list[dict[str, Any]] = []
    for i in range(max(1, args.runs)):
        run = measure_run(args.base_url, token, args.mode, args)
        runs.append(run)
        print(f"run {i + 1}: {json.dumps(run)}", flush=True)

    report = {"runs": runs, "summary": summarize(runs)}
    print(json.dumps(report, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:  # noqa: S105
            json.dump(report, fh, indent=2)
    return 0 if all(r["finished"] and not r["error"] for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
