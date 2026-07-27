"""Game-system resolution and benchmark configuration for the Play chat router.

Extracted from ``chat.py`` to keep the route handler focused on HTTP orchestration
while this module resolves which rule-set (game system) applies to a given session.

Responsibilities:
  - Resolve universe → default game-system binding
  - Look up game-system documents from MongoDB
  - Extract pack-embedded rulesets
  - Resolve playtest benchmark configurations
"""

from __future__ import annotations

import logging
from typing import Any

from .chat_support import as_uuid

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag — checked once at import time
# ---------------------------------------------------------------------------

try:
    _GSR_AVAILABLE = True
except Exception:
    _GSR_AVAILABLE = False


# ---------------------------------------------------------------------------
# Universe → system binding
# ---------------------------------------------------------------------------


def resolve_universe_system_binding(universe_id: str | None) -> dict[str, Any]:
    """Resolve a universe's default rules binding, including pack-embedded sources."""
    if not universe_id:
        return {}
    try:
        from monitor_data.tools.neo4j_tools import neo4j_get_universe

        uid = as_uuid(universe_id)
        if uid is None:
            return {}

        universe = neo4j_get_universe(uid)
        if universe is None:
            return {}

        return {
            "system_id": str(universe.default_game_system_id)
            if getattr(universe, "default_game_system_id", None)
            else None,
            "system_source_type": getattr(universe, "default_system_source_type", None),
            "system_source_id": getattr(universe, "default_system_source_id", None),
            "system_name": getattr(universe, "default_system_name", None),
        }
    except Exception as exc:
        logger.debug("resolve_universe_system_binding failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Game-system document resolution
# ---------------------------------------------------------------------------


def get_game_system_doc(
    universe_id: str | None,
    system_id: str | None = None,
    *,
    system_source_type: str | None = None,
    system_source_id: str | None = None,
    pack_id: str | None = None,
) -> dict[str, Any] | None:
    """Return the resolved game-system document for the session or universe binding."""
    if not _GSR_AVAILABLE:
        return None
    try:
        from monitor_data.db.mongodb import get_mongodb_client
        from monitor_data.tools.mongodb_tools import mongodb_get_knowledge_pack

        binding = resolve_universe_system_binding(universe_id) if universe_id else {}
        resolved_system_id = system_id or binding.get("system_id")
        resolved_source_type = system_source_type or binding.get("system_source_type")
        resolved_source_id = system_source_id or pack_id or binding.get("system_source_id")

        if not resolved_source_type and pack_id:
            resolved_source_type = "pack_embedded"

        if not resolved_system_id and resolved_source_type == "generic_library" and resolved_source_id:
            resolved_system_id = str(resolved_source_id)

        if resolved_source_type == "pack_embedded" and resolved_source_id:
            pack_uuid = as_uuid(str(resolved_source_id))
            if pack_uuid is not None:
                pack = mongodb_get_knowledge_pack(pack_uuid)
                if pack is not None:
                    embedded = getattr(pack, "game_system_data", None)
                    if embedded is not None:
                        return embedded.model_dump(mode="json")  # type: ignore
                    if not resolved_system_id and getattr(pack, "game_system_id", None):
                        resolved_system_id = str(pack.game_system_id)

        if not resolved_system_id:
            logger.debug(
                "get_game_system_doc: no explicit binding resolved for universe=%s; using generic play mode",
                universe_id,
            )
            return None

        mdb = get_mongodb_client()
        col = mdb.get_collection("game_systems")
        found = col.find_one({"system_id": resolved_system_id}, projection={"_id": 0})
        if found is not None:
            return found  # type: ignore

        logger.debug(
            "get_game_system_doc: resolved system_id '%s' was not found; using generic play mode",
            resolved_system_id,
        )
        return None
    except Exception as exc:
        logger.debug("get_game_system_doc failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Session-level convenience
# ---------------------------------------------------------------------------


def session_game_system_doc(session: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve the active rules document for a session, including pack-bound rulesets."""
    return get_game_system_doc(
        session.get("universe_id") or session.get("world_id"),
        session.get("system_id"),
        system_source_type=session.get("system_source_type"),
        system_source_id=session.get("system_source_id"),
        pack_id=session.get("pack_id"),
    )


# ---------------------------------------------------------------------------
# Benchmark configuration
# ---------------------------------------------------------------------------


def get_benchmark_config(benchmark_id: str | None) -> dict[str, Any] | None:
    """Resolve a configured playtest benchmark by id for UI and session setup."""
    if not benchmark_id:
        return None
    try:
        from monitor_data.defaults.playtest_benchmarks import get_playtest_benchmark

        return get_playtest_benchmark(benchmark_id, include_scripted_turns=True)
    except Exception as exc:
        logger.debug("get_benchmark_config failed: %s", exc)
        return None
