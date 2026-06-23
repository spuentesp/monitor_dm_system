#!/usr/bin/env python3
"""Run live MONITOR playtests against the running backend.

This is a real end-to-end smoke test: it talks to the live API, creates a
session, drives a short playable scene, and writes one or more markdown
gameplay logs. It supports both scripted and LLM-driven player modes.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    import litellm
    from monitor_agents import dspy_runtime as _monitor_dspy_runtime  # noqa: F401
except Exception:  # noqa: BLE001
    litellm = None

DEFAULT_API_URL = os.environ.get("MONITOR_API_URL", "http://localhost:8000/api")
DEFAULT_OUTPUT_DIR = Path("tests/e2e/logs")
DEFAULT_LOG_FILE = DEFAULT_OUTPUT_DIR / "live_gameplay_latest.md"
DEFAULT_SESSION_TITLE = "The Wreck of the Penitent Star"
DEFAULT_BENCHMARK_ID = os.environ.get(
    "MONITOR_PLAYTEST_BENCHMARK", "narrative_weighted_derelict"
)
FALLBACK_MARKERS = (
    "gathering their thoughts",
    "couldn't generate",
    "unable to continue",
)
DEFAULT_SCRIPTED_TURNS = [
    "I'm Kael Draven, a void-born engineer from Terminus-9. I survived the loss of my salvage crew when the Penitent Star split open in the black. Since then I take repair work, keep my head down, and try not to think about the sounds the hull made when the air left.",
    "Yes. Roll my stats.",
    "I check the station's job board for salvage contracts. I need credits, and I trust dead ships more than living people.",
    "I take the derelict recovery job, suit up, and dock with the wreck. I pause at the airlock and listen before cycling it open.",
    "I sweep the corridor with my lamp and scan for power, motion, or signs that anyone else got here first.",
    "The cargo bay door is damaged. I pull the panel and try to hotwire it open without frying the lock.",
]


@dataclass
class TranscriptEntry:
    speaker: str
    text: str
    metadata: dict[str, Any]


def _api(
    session: requests.Session, method: str, base_url: str, path: str, **kwargs: Any
) -> Any:
    response = session.request(method, f"{base_url}{path}", timeout=180, **kwargs)
    response.raise_for_status()
    return response.json()


def _extract_text(response: Any) -> str:
    message = (
        response.choices[0].message if getattr(response, "choices", None) else None
    )
    content = getattr(message, "content", "") if message else ""
    if isinstance(content, list):
        return "\n".join(str(part) for part in content).strip()
    return str(content or "").strip()


def _normalize_player_model(model: str) -> str:
    normalized = model.strip()
    lowered = normalized.lower()
    if "/" in normalized:
        return normalized
    if "gemini" in lowered:
        return f"gemini/{normalized}"
    return normalized


def _load_benchmark(
    session: requests.Session, base_url: str, benchmark_id: str | None
) -> dict[str, Any] | None:
    if not benchmark_id:
        return None
    try:
        benchmarks = _api(session, "GET", base_url, "/chat/benchmarks")
    except Exception:  # noqa: BLE001
        return None

    for benchmark in benchmarks:
        if benchmark.get("benchmark_id") == benchmark_id:
            return benchmark

    available = ", ".join(
        sorted(str(b.get("benchmark_id")) for b in benchmarks if b.get("benchmark_id"))
    )
    raise RuntimeError(f"Unknown benchmark_id={benchmark_id!r}. Available: {available}")


def _scripted_turns_for(benchmark: dict[str, Any] | None) -> list[str]:
    if (
        benchmark
        and isinstance(benchmark.get("scripted_turns"), list)
        and benchmark["scripted_turns"]
    ):
        return [str(turn) for turn in benchmark["scripted_turns"]]
    return list(DEFAULT_SCRIPTED_TURNS)


def _extract_metrics(transcript: list[TranscriptEntry]) -> dict[str, Any]:
    gm_entries = [entry for entry in transcript if entry.speaker == "GM"]
    player_entries = [entry for entry in transcript if entry.speaker == "PLAYER"]

    success_levels = [
        str(entry.metadata.get("success_level"))
        for entry in gm_entries
        if entry.metadata.get("success_level")
    ]
    roll_breakdowns = [
        str(entry.metadata.get("roll_breakdown"))
        for entry in gm_entries
        if entry.metadata.get("roll_breakdown")
    ]
    effects_seen = sorted(
        {
            str(effect)
            for entry in gm_entries
            for effect in (entry.metadata.get("effects") or [])
            if effect
        }
    )
    phase_sequence = [
        str(entry.metadata.get("phase"))
        for entry in gm_entries
        if entry.metadata.get("phase")
    ]

    avg_gm_reply_chars = (
        round(
            sum(len(entry.text.strip()) for entry in gm_entries) / len(gm_entries),
            1,
        )
        if gm_entries
        else 0.0
    )
    avg_player_reply_chars = (
        round(
            sum(len(entry.text.strip()) for entry in player_entries)
            / len(player_entries),
            1,
        )
        if player_entries
        else 0.0
    )

    return {
        "avg_gm_reply_chars": avg_gm_reply_chars,
        "avg_player_reply_chars": avg_player_reply_chars,
        "clarification_question_count": sum(
            1 for entry in player_entries if "?" in entry.text
        ),
        "question_marks_from_gm": sum(entry.text.count("?") for entry in gm_entries),
        "success_levels": success_levels,
        "roll_breakdowns": roll_breakdowns,
        "effects_seen": effects_seen,
        "phase_sequence": phase_sequence,
    }


def _llm_player_turn(
    transcript: list[TranscriptEntry],
    turn_index: int,
    *,
    player_mode: str,
    benchmark: dict[str, Any] | None = None,
) -> str:
    last_gm = next(
        (entry for entry in reversed(transcript) if entry.speaker == "GM"), None
    )
    last_phase = (last_gm.metadata or {}).get("phase") if last_gm else None
    last_text = (last_gm.text if last_gm else "").lower()

    if last_phase == "char_creation":
        return "Yes. Roll my stats."
    scripted_turns = _scripted_turns_for(benchmark)
    if last_phase == "awaiting_character" or "who are you" in last_text:
        return scripted_turns[0]

    if litellm is None:
        raise RuntimeError("litellm is not installed; cannot use --player-mode llm")

    model = os.environ.get("MONITOR_PLAYTEST_MODEL")
    if not model:
        raise RuntimeError(
            "MONITOR_PLAYTEST_MODEL must be set for --player-mode llm "
            "(for example: gemini/gemini-2.5-flash-lite)"
        )
    model = _normalize_player_model(model)

    history = "\n\n".join(
        f"{entry.speaker}: {entry.text.strip()}" for entry in transcript[-8:]
    )
    response = litellm.completion(
        model=model,
        temperature=0.7,
        max_tokens=140,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are the PLAYER in a solo sci-fi horror RPG playtest. "
                    + (
                        "Act as an adversarial but fair playtester: ask clarifying questions, push for concrete options, and politely expose vague or inconsistent GM guidance. "
                        if player_mode == "adversarial_llm"
                        else "Stay in character, keep momentum, and reply with only the next player action in 1-2 sentences. "
                    )
                    + (
                        str(benchmark.get("llm_player_brief", "")) + " "
                        if benchmark
                        else ""
                    )
                    + "Do not narrate outcomes or write for the GM."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Recent transcript:\n{history}\n\n"
                    + (
                        "Benchmark starter probes: "
                        + " | ".join(benchmark.get("starter_questions", [])[:3])
                        + "\n"
                        if benchmark and benchmark.get("starter_questions")
                        else ""
                    )
                    + (
                        "Adversarial goals: "
                        + " | ".join(benchmark.get("adversarial_goals", [])[:3])
                        + "\n"
                        if benchmark and benchmark.get("adversarial_goals")
                        else ""
                    )
                    + f"This is turn {turn_index + 1}. Write the player's next move."
                ),
            },
        ],
    )
    text = _extract_text(response)
    return text or "I move deeper into the wreck, scanning for danger and salvage."


def _next_player_text(
    player_mode: str,
    transcript: list[TranscriptEntry],
    turn_index: int,
    benchmark: dict[str, Any] | None = None,
) -> str:
    if player_mode in {"llm", "adversarial_llm"}:
        return _llm_player_turn(
            transcript,
            turn_index,
            player_mode=player_mode,
            benchmark=benchmark,
        )
    scripted_turns = _scripted_turns_for(benchmark)
    if turn_index < len(scripted_turns):
        return scripted_turns[turn_index]
    return (
        "I push farther into the wreck, checking for salvage, survivors, and trouble."
    )


def run_live_session(
    base_url: str,
    *,
    player_mode: str = "scripted",
    turn_limit: int = 6,
    session_title: str = DEFAULT_SESSION_TITLE,
    benchmark_id: str | None = None,
) -> tuple[dict[str, Any], list[TranscriptEntry], int]:
    http = requests.Session()

    health = _api(http, "GET", base_url, "/health")
    if health.get("status") != "ok":
        raise RuntimeError(f"Backend unhealthy: {health}")

    benchmark = _load_benchmark(http, base_url, benchmark_id)

    universes = _api(http, "GET", base_url, "/universes/universes")
    if not universes:
        raise RuntimeError("No universes available for live gameplay test")

    universe = universes[0]
    created = _api(
        http,
        "POST",
        base_url,
        "/chat",
        json={
            "title": benchmark.get("session_title", session_title)
            if benchmark
            else session_title,
            "mode": benchmark.get("mode", "autonomous_gm")
            if benchmark
            else "autonomous_gm",
            "universe_id": universe["id"],
            "universe_label": universe.get("name"),
            "tone": benchmark.get("tone", "grim") if benchmark else "grim",
            "play_mode": benchmark.get("play_mode", "dice_game_system")
            if benchmark
            else "dice_game_system",
            "benchmark_id": benchmark.get("benchmark_id") if benchmark else None,
            "benchmark_label": benchmark.get("name") if benchmark else None,
        },
    )
    session_id = created["id"]

    history = _api(http, "GET", base_url, f"/chat/{session_id}/messages")
    transcript: list[TranscriptEntry] = [
        TranscriptEntry(
            speaker=message["role"].upper(),
            text=message["content"],
            metadata=message.get("metadata", {}),
        )
        for message in history
    ]

    fallback_count = 0
    for turn_index in range(turn_limit):
        player_text = _next_player_text(player_mode, transcript, turn_index, benchmark)
        transcript.append(
            TranscriptEntry(speaker="PLAYER", text=player_text, metadata={})
        )
        reply = _api(
            http,
            "POST",
            base_url,
            f"/chat/{session_id}/send",
            json={"content": player_text},
        )
        text = reply["content"]
        metadata = reply.get("metadata", {})
        if any(marker in text.lower() for marker in FALLBACK_MARKERS):
            fallback_count += 1
        transcript.append(TranscriptEntry(speaker="GM", text=text, metadata=metadata))

    summary = {
        "api_url": base_url,
        "session_id": session_id,
        "universe_id": universe["id"],
        "universe_name": universe.get("name"),
        "player_mode": player_mode,
        "benchmark_id": benchmark.get("benchmark_id") if benchmark else None,
        "benchmark_name": benchmark.get("name") if benchmark else None,
        "comparison_group": benchmark.get("comparison_group") if benchmark else None,
        "fallback_count": fallback_count,
        "entries": len(transcript),
        "session_title": benchmark.get("session_title", session_title)
        if benchmark
        else session_title,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **_extract_metrics(transcript),
    }
    return summary, transcript, fallback_count


def write_markdown_log(
    log_file: Path, summary: dict[str, Any], transcript: list[TranscriptEntry]
) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Live Gameplay Log",
        "",
        f"- **API**: `{summary['api_url']}`",
        f"- **Session ID**: `{summary['session_id']}`",
        f"- **Universe**: `{summary['universe_name']}` (`{summary['universe_id']}`)",
        f"- **Player mode:** `{summary['player_mode']}`",
        f"- **Benchmark:** `{summary.get('benchmark_name') or summary.get('benchmark_id') or 'custom'}`",
        f"- **Fallback detected:** `{summary['fallback_count']}`",
        f"- **Transcript entries**: `{summary['entries']}`",
        f"- **Average GM reply chars:** `{summary.get('avg_gm_reply_chars', 0)}`",
        f"- **Clarification questions:** `{summary.get('clarification_question_count', 0)}`",
        f"- **Generated at**: `{summary['generated_at']}`",
        "",
        "---",
        "",
    ]

    turn_index = 0
    for entry in transcript:
        if entry.speaker == "PLAYER":
            turn_index += 1
            lines.append(f"## Turn {turn_index}")
            lines.append("")
        elif turn_index == 0 and entry.speaker == "GM":
            lines.append("## Opening")
            lines.append("")

        lines.append(f"**{entry.speaker}:**")
        lines.append("")
        lines.append(entry.text.strip())
        lines.append("")
        if entry.metadata:
            lines.append("```json")
            lines.append(json.dumps(entry.metadata, indent=2, ensure_ascii=False))
            lines.append("```")
            lines.append("")

    log_file.write_text("\n".join(lines), encoding="utf-8")


def _log_path_for_run(
    *,
    output_dir: Path,
    player_mode: str,
    run_index: int,
    runs: int,
    explicit_log_file: str | None,
) -> Path:
    if explicit_log_file and runs == 1:
        return Path(explicit_log_file)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return output_dir / f"live_gameplay_{player_mode}_run{run_index:02d}_{stamp}.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-url", default=DEFAULT_API_URL, help="Backend API base URL"
    )
    parser.add_argument(
        "--player-mode",
        choices=["scripted", "llm", "adversarial_llm"],
        default="scripted",
    )
    parser.add_argument(
        "--turns", type=int, default=6, help="Number of player turns to run"
    )
    parser.add_argument(
        "--runs", type=int, default=1, help="Number of sessions to execute"
    )
    parser.add_argument(
        "--benchmark-id",
        default=DEFAULT_BENCHMARK_ID,
        help="Configured benchmark flow id to run",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for gameplay logs",
    )
    parser.add_argument(
        "--log-file", default=None, help="Markdown log output path for a single run"
    )
    parser.add_argument("--title", default=DEFAULT_SESSION_TITLE, help="Session title")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_summaries: list[dict[str, Any]] = []
    all_ok = True
    for run_index in range(1, args.runs + 1):
        summary, transcript, fallback_count = run_live_session(
            args.api_url,
            player_mode=args.player_mode,
            turn_limit=args.turns,
            session_title=args.title,
            benchmark_id=args.benchmark_id,
        )
        log_path = _log_path_for_run(
            output_dir=output_dir,
            player_mode=args.player_mode,
            run_index=run_index,
            runs=args.runs,
            explicit_log_file=args.log_file,
        )
        write_markdown_log(log_path, summary, transcript)
        summary["log_file"] = str(log_path)
        all_summaries.append(summary)

        print(f"LIVE SESSION RESULT {run_index}/{args.runs}")
        print(f"  API URL:            {summary['api_url']}")
        print(f"  Session ID:         {summary['session_id']}")
        print(f"  Universe:           {summary['universe_name']}")
        print(f"  Player mode:        {summary['player_mode']}")
        print(
            f"  Benchmark:          {summary.get('benchmark_name') or summary.get('benchmark_id') or 'custom'}"
        )
        print(f"  Transcript entries: {summary['entries']}")
        print(f"  Fallback detected:  {fallback_count}")
        print(f"  Avg GM chars:       {summary.get('avg_gm_reply_chars', 0)}")
        print(f"  Clarification Qs:   {summary.get('clarification_question_count', 0)}")
        print(f"  Gameplay log:       {log_path}")
        print()

        if fallback_count != 0:
            all_ok = False

    summary_path = output_dir / "live_gameplay_summary.json"
    summary_path.write_text(json.dumps(all_summaries, indent=2), encoding="utf-8")
    print(f"Summary JSON:         {summary_path}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
