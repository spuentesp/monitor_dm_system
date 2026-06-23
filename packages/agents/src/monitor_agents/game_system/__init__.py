"""
GameSystemRuntime — schema-driven game system interpreter (orchestrator).

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libs

This package reads the ``game_systems`` MongoDB document and provides a
system-agnostic API for:

  - Rolling a new character (reads attribute generation rules, resources)
  - Calculating stat modifiers (reads modifier_formula per attribute)
  - Routing a player action to the correct stat (reads skill→attribute links)
  - Compacting the system for narrator injection

**NO game-system names, abbreviations, or rules are hardcoded here.**
Everything is derived from the structure stored at ingest time.

Architecture: thin orchestrator + pure-function sub-modules.
  - ``runtime.py``       → ``GameSystemRuntime`` class (orchestrator)
  - ``_types.py``         → ``SystemData`` frozen dataclass (shared context)
  - ``_action_routing.py`` → action → stat routing (pure functions)
  - ``_char_generation.py`` → character rolling & formatting (pure functions)
  - ``_tracks_conditions.py`` → track/condition management (pure functions)
  - ``_advanced_systems.py`` → damage, recovery, tiered, action economy (pure functions)
  - ``_narrator.py``       → modifier calc & narrator compaction (pure functions)
  - ``_constants.py``      → regex signal patterns
"""

from __future__ import annotations

from typing import Any, Dict

from .runtime import GameSystemRuntime

# Export the class for backward compatibility
__all__ = ["GameSystemRuntime", "load_game_system_runtime"]


# ---------------------------------------------------------------------------
# Module-level loader (backward compat)
# ---------------------------------------------------------------------------


def load_game_system_runtime(system_doc: Dict[str, Any]) -> GameSystemRuntime:
    """Construct a GameSystemRuntime from a raw game_systems document."""
    return GameSystemRuntime(system_doc)
