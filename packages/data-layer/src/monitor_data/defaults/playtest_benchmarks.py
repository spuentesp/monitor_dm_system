"""Config-backed playtest benchmark catalog.

Stores benchmark conversational flows in JSON so the CLI, smoke tests, and UI can
all use the same curated scenarios for comparison runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_BENCHMARK_SYSTEM_FALLBACKS: dict[str, list[str]] = {
    "death in space": ["Narrative Weighted", "Narrative Pure"],
    "lancer": ["Narrative Weighted", "Narrative Pure"],
    "monster of the week": ["Powered by the Apocalypse", "Narrative Weighted"],
    "motw": ["Powered by the Apocalypse", "Narrative Weighted"],
    "7th sea": ["Narrative Weighted", "Fate Core"],
}


def _catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "playtest_benchmarks.json"


def _normalize_benchmark(raw: dict[str, Any]) -> dict[str, Any]:
    benchmark = dict(raw)
    benchmark.setdefault("tags", [])
    benchmark.setdefault("focus_areas", [])
    benchmark.setdefault("expected_signals", [])
    benchmark.setdefault("comparison_metrics", [])
    benchmark.setdefault("adversarial_goals", [])
    benchmark.setdefault("starter_questions", [])
    benchmark.setdefault("player_persona", "")
    benchmark.setdefault("llm_player_brief", "")
    benchmark.setdefault("ui_notes", "")
    benchmark.setdefault("mode", "autonomous_gm")
    benchmark.setdefault("tone", "dramatic")
    benchmark.setdefault("play_mode", "dice_game_system")
    benchmark.setdefault("scripted_turns", [])
    benchmark["scripted_turn_count"] = len(benchmark.get("scripted_turns", []))
    return benchmark


def _fallback_candidates(benchmark: dict[str, Any]) -> list[str]:
    """Return benchmark-safe fallback systems when the exact pack is unavailable."""
    requested = str(benchmark.get("system_name") or "").strip().lower()
    play_mode = str(benchmark.get("play_mode") or "").strip().lower()

    candidates: list[str] = []
    candidates.extend(_BENCHMARK_SYSTEM_FALLBACKS.get(requested, []))

    if play_mode == "narrative":
        candidates.append("Narrative Pure")
    elif play_mode == "dice_game_system":
        candidates.append("Narrative Weighted")

    candidates.append("Narrative Pure")

    deduped: list[str] = []
    for name in candidates:
        if name and name not in deduped:
            deduped.append(name)
    return deduped


def load_playtest_benchmarks() -> list[dict[str, Any]]:
    """Load the configured benchmark catalog from disk."""
    catalog_path = _catalog_path()
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Playtest benchmark catalog not found: {catalog_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Playtest benchmark catalog contains invalid JSON: {catalog_path}") from exc

    if not isinstance(data, list):
        raise ValueError("Playtest benchmark catalog must contain a JSON list")

    return [_normalize_benchmark(item) for item in data if isinstance(item, dict)]


def resolve_playtest_benchmarks(*, include_scripted_turns: bool = True) -> list[dict[str, Any]]:
    """Attach runtime metadata such as resolved `system_id` for each benchmark."""
    benchmarks = load_playtest_benchmarks()

    collection = None
    try:
        from monitor_data.tools.mongodb_tools import _ensure_builtin_systems_seeded

        _ensure_builtin_systems_seeded()
    except Exception:
        pass

    try:
        from monitor_data.db.mongodb import get_mongodb_client

        mdb = get_mongodb_client()
        collection = mdb.get_collection("game_systems")
    except Exception:
        collection = None

    resolved_rows: dict[str, dict[str, Any]] = {}
    if collection is not None:
        names: set[str] = set()
        for benchmark in benchmarks:
            system_name = benchmark.get("system_name")
            if system_name:
                names.add(str(system_name))
            names.update(_fallback_candidates(benchmark))

        if names:
            try:
                for row in collection.find(
                    {"name": {"$in": sorted(names)}},
                    {"_id": 0, "system_id": 1, "name": 1, "core_mechanic": 1, "is_builtin": 1},
                ):
                    if row.get("name"):
                        resolved_rows[str(row["name"])] = row
            except Exception:
                # Best-effort metadata attach: a dead MongoDB must not break
                # benchmark resolution (cursor iteration is what actually dials).
                resolved_rows = {}

    resolved: list[dict[str, Any]] = []
    for benchmark in benchmarks:
        item = dict(benchmark)
        system_name = item.get("system_name")
        exact_doc = resolved_rows.get(str(system_name), {}) if system_name else {}

        fallback_doc: dict[str, Any] = {}
        if not exact_doc:
            for fallback_name in _fallback_candidates(item):
                candidate = resolved_rows.get(fallback_name, {})
                if candidate:
                    fallback_doc = candidate
                    break

        system_doc = exact_doc or fallback_doc
        used_fallback = bool(fallback_doc and not exact_doc)

        item["resolved_system_id"] = system_doc.get("system_id")
        item["resolved_system_name"] = system_doc.get("name") or system_name
        item["system_available"] = bool(system_doc)
        item["requested_system_available"] = bool(exact_doc)
        item["system_match_type"] = "exact" if exact_doc else "fallback" if fallback_doc else "missing"
        item["system_fallback_used"] = used_fallback
        item["fallback_reason"] = (
            f"Exact system '{system_name}' is not seeded yet; using benchmark-safe fallback '{system_doc.get('name')}'."
            if used_fallback and system_name and system_doc.get("name")
            else None
        )
        item["core_mechanic"] = (system_doc.get("core_mechanic") or {}).get("formula")
        if not include_scripted_turns:
            item.pop("scripted_turns", None)
        resolved.append(item)

    return resolved


def get_playtest_benchmark(
    benchmark_id: str,
    *,
    include_scripted_turns: bool = True,
) -> dict[str, Any] | None:
    """Return a single benchmark definition by id, if present."""
    for benchmark in resolve_playtest_benchmarks(include_scripted_turns=include_scripted_turns):
        if benchmark.get("benchmark_id") == benchmark_id:
            return benchmark
    return None
