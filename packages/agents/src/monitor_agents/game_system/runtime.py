"""
GameSystemRuntime — schema-driven game system interpreter (orchestrator).

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libs

This module defines the GameSystemRuntime class which interprets a
``game_systems`` MongoDB document and provides a system-agnostic API for:

  - Rolling a new character (reads attribute generation rules, resources)
  - Calculating stat modifiers (reads modifier_formula per attribute)
  - Routing a player action to the correct stat (reads skill→attribute links)
  - Compacting the system for narrator injection

**NO game-system names, abbreviations, or rules are hardcoded here.**
Everything is derived from the structure stored at ingest time.
"""

from __future__ import annotations

import logging
from typing import Any

from monitor_agents.base import BaseAgent

from ._types import SystemData, build_system_data

logger = logging.getLogger(__name__)


class GameSystemRuntime(BaseAgent):
    """Interprets a ``game_systems`` MongoDB document for runtime use.

    Thin orchestrator: holds a pre-built ``SystemData`` and delegates
    every method to the corresponding pure-function sub-module.

    Inherits from BaseAgent so it shares the standard agent lifecycle,
    tracing, and LLM access (available for future rule-interpretation calls).

    Authority: READ-ONLY (no writes to any database).

    Usage::

        gsr = GameSystemRuntime(system_doc)
        rolled = gsr.roll_character()
        action_type, stat_name, dc = await gsr.infer_action_stat("I try to sneak past the guard")
        modifier = gsr.calc_modifier("DEX", 2)
        context = gsr.compact_for_narrator()
    """

    def __init__(
        self,
        doc: dict[str, Any],
        agent_id: str = "game-system-runtime",
        model: str | None = None,
    ) -> None:
        super().__init__(agent_type="GameSystemRuntime", agent_id=agent_id, model=model)
        self._sd: SystemData = build_system_data(doc)

    # ------------------------------------------------------------------
    # Backward-compat property aliases (resolver.py uses these directly)
    # ------------------------------------------------------------------

    @property
    def _attr_by_abbr(self) -> dict[str, dict[str, Any]]:
        return self._sd.attr_by_abbr

    @property
    def _char_creation(self) -> dict[str, Any]:
        """Character-creation procedure block (character_creation_loop uses this)."""
        return self._sd.char_creation

    @property
    def _doc(self) -> dict[str, Any]:
        """Raw game-system document (character_creation_loop uses this)."""
        return self._sd.doc

    @property
    def _primary_attributes(self) -> list[dict[str, Any]]:
        return self._sd.primary_attributes

    @property
    def _skills(self) -> list[dict[str, Any]]:
        return self._sd.skills

    @property
    def primary_attributes(self) -> list[dict[str, Any]]:
        """Return deduplicated primary attribute list."""
        return self._sd.primary_attributes

    def ability_method_description(self) -> str:
        """Return a one-sentence description of how ability scores are generated."""
        from ._char_generation import ability_method_description

        return ability_method_description(self._sd)

    async def run(self) -> None:
        """No-op — GameSystemRuntime is query-only, not a loop participant."""
        return None

    # ------------------------------------------------------------------
    # Character generation  (→ _char_generation)
    # ------------------------------------------------------------------

    def roll_character(self) -> dict[str, Any]:
        from ._char_generation import roll_character

        return roll_character(self._sd)

    def format_character_sheet(self, rolled: dict[str, Any]) -> str:
        from ._char_generation import format_character_sheet

        return format_character_sheet(self._sd, rolled)

    def derive_resources(self, stats: dict[str, int]) -> dict[str, int]:
        """Compute derived resource values (HP, etc.) from given attribute stats.

        ``stats`` is keyed by attribute abbreviation. Values come from the
        system's resource ``calculation`` formulas (e.g. ``10 + Grit_modifier``),
        never from hardcoded literals.
        """
        from ._char_generation import _derive_resources

        return _derive_resources(self._sd, stats)

    def build_character_candidate(
        self,
        name: str = "Test Character",
        description: str = "",
        concept: str | None = None,
    ) -> dict[str, Any]:
        from ._char_generation import build_character_candidate

        return build_character_candidate(self._sd, name=name, description=description, concept=concept)

    def generate_npc(
        self,
        name: str | None = None,
        tier: str | None = None,
        concept: str | None = None,
    ) -> dict[str, Any]:
        from ._char_generation import generate_npc

        return generate_npc(self._sd, name=name, tier=tier, concept=concept)

    # ------------------------------------------------------------------
    # Action routing  (→ _action_routing)
    # ------------------------------------------------------------------

    async def infer_action_context(
        self,
        user_input: str,
        source_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from ._action_routing import infer_action_context

        return await infer_action_context(self._sd, user_input, source_profile=source_profile)

    async def infer_action_stat(
        self,
        user_input: str,
        source_profile: dict[str, Any] | None = None,
    ) -> tuple[str, str, int]:
        from ._action_routing import infer_action_stat

        return await infer_action_stat(self._sd, user_input, source_profile=source_profile)

    async def infer_subsystem_hint(
        self,
        user_input: str,
        source_profile: dict[str, Any] | None = None,
    ) -> str | None:
        from ._action_routing import infer_subsystem_hint

        return await infer_subsystem_hint(self._sd, user_input, source_profile=source_profile)

    # ------------------------------------------------------------------
    # Tracks & conditions  (→ _tracks_conditions)
    # ------------------------------------------------------------------

    def get_tracks(self) -> list[dict[str, Any]]:
        from ._tracks_conditions import get_tracks

        return get_tracks(self._sd)

    def get_track(self, name: str) -> dict[str, Any] | None:
        from ._tracks_conditions import get_track

        return get_track(self._sd, name)

    def evaluate_track_threshold(
        self,
        track_name: str,
        current_value: int,
        max_value: int | None = None,
    ) -> dict[str, Any]:
        from ._tracks_conditions import evaluate_track_threshold

        return evaluate_track_threshold(self._sd, track_name, current_value, max_value)

    def get_conditions(self) -> list[dict[str, Any]]:
        from ._tracks_conditions import get_conditions

        return get_conditions(self._sd)

    def get_condition(self, name: str) -> dict[str, Any] | None:
        from ._tracks_conditions import get_condition

        return get_condition(self._sd, name)

    async def check_condition_triggers(
        self,
        event: str,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        from ._tracks_conditions import check_condition_triggers

        return await check_condition_triggers(self._sd, event, context)

    async def evaluate_scenery_and_conditions(
        self,
        context: dict[str, Any] | None,
        user_input: str,
        roll_mode: str = "normal",
    ) -> dict[str, Any]:
        from ._tracks_conditions import evaluate_scenery_and_conditions

        return await evaluate_scenery_and_conditions(self._sd, context, user_input, roll_mode)

    # ------------------------------------------------------------------
    # Advanced systems  (→ _advanced_systems)
    # ------------------------------------------------------------------

    def get_tiered_systems(self) -> list[dict[str, Any]]:
        from ._advanced_systems import get_tiered_systems

        return get_tiered_systems(self._sd)

    def get_tiered_system(self, name: str) -> dict[str, Any] | None:
        from ._advanced_systems import get_tiered_system

        return get_tiered_system(self._sd, name)

    def get_available_tiers(
        self,
        system_name: str,
        current_access: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        from ._advanced_systems import get_available_tiers

        return get_available_tiers(self._sd, system_name, current_access)

    def get_damage_model(self) -> dict[str, Any] | None:
        from ._advanced_systems import get_damage_model

        return get_damage_model(self._sd)

    def get_damage_types(self) -> list[dict[str, Any]]:
        from ._advanced_systems import get_damage_types

        return get_damage_types(self._sd)

    def apply_damage(
        self,
        damage_type: str,
        amount: int,
        current_state: dict[str, Any],
    ) -> dict[str, Any]:
        from ._advanced_systems import apply_damage

        return apply_damage(self._sd, damage_type, amount, current_state)

    def get_action_economy(self) -> dict[str, Any] | None:
        from ._advanced_systems import get_action_economy

        return get_action_economy(self._sd)

    def get_action_types(self) -> list[dict[str, Any]]:
        from ._advanced_systems import get_action_types

        return get_action_types(self._sd)

    def get_recovery_model(self) -> dict[str, Any] | None:
        from ._advanced_systems import get_recovery_model

        return get_recovery_model(self._sd)

    def apply_recovery(
        self,
        event_name: str,
        current_state: dict[str, Any],
    ) -> dict[str, Any]:
        from ._advanced_systems import apply_recovery

        return apply_recovery(self._sd, event_name, current_state)

    def get_advancement_model(self) -> dict[str, Any] | None:
        from ._advanced_systems import get_advancement_model

        return get_advancement_model(self._sd)

    def get_resolution_mechanics(self) -> list[dict[str, Any]]:
        from ._advanced_systems import get_resolution_mechanics

        return get_resolution_mechanics(self._sd)

    def find_resolution_mechanic(self, context: str) -> dict[str, Any] | None:
        from ._advanced_systems import find_resolution_mechanic

        return find_resolution_mechanic(self._sd, context)

    def build_initial_track_state(
        self,
        stats: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        from ._advanced_systems import build_initial_track_state

        return build_initial_track_state(self._sd, stats)

    # ------------------------------------------------------------------
    # Narrator context  (→ _narrator)
    # ------------------------------------------------------------------

    def calc_modifier(self, stat_abbr: str, stat_value: int) -> int:
        from ._narrator import calc_modifier

        return calc_modifier(self._sd, stat_abbr, stat_value)

    def compact_for_narrator(self) -> dict[str, Any]:
        from ._narrator import compact_for_narrator

        return compact_for_narrator(self._sd)
