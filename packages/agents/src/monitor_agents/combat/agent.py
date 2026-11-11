"""
CombatAgent — at-the-table encounter support for the human GM (CF-9).

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1) schemas, monitor_agents.base, game_system
CALLED BY: UI backend routers/gm_tools.py (GM Assistant /gm page)

State transitions (start, HP math, initiative order, rounds, end) are plain
code: every one delegates to the session-combat MongoDB tools over MCP
(``mongodb_combat_*``) — never an LLM call, never a Neo4j write. Permanent
world effects (deaths, faction shifts) leave the encounter only as
``ProposedChange`` items staged by the router for the CF-8 queue.

The three optional LLM bits live in the co-located DSPy module:
initiative narration, condition explanation when the bound game system has no
structured definition, and the end-of-encounter summary.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, TypeVar
from uuid import UUID

import structlog
from monitor_data.schemas.combat import (
    CombatEnd,
    CombatNextRound,
    CombatSessionState,
    CombatSetInitiative,
    CombatStart,
    CombatUpdateCombatant,
)
from monitor_data.schemas.llm_config import ModelRole
from pydantic import BaseModel, Field

from monitor_agents.base import BaseAgent
from monitor_agents.combat.module import CombatModule

log = structlog.get_logger()

_T = TypeVar("_T")

# The data-layer MCP server reports a refused or failed tool as text.
_TOOL_ERROR_PREFIXES = ("Authorization error:", "Validation error:", "Error executing tool:")


def _raise_on_tool_error(result: Any) -> Any:
    """Raise ``ValueError`` when the MCP server returned a failure as text.

    Tool functions raise ``ValueError`` for state-machine violations (missing
    encounter, unknown combatant, round after end). The server catches those
    and returns ``"Error executing tool: ..."`` — without this guard the agent
    would silently treat the failure string as a state payload.
    """
    if isinstance(result, str) and result.startswith(_TOOL_ERROR_PREFIXES):
        raise ValueError(result)
    return result


class ConditionExplanation(BaseModel):
    """What a condition tag means, with its provenance."""

    condition: str = Field(description="The condition tag as tracked on the combatant")
    source: str = Field(description="'system' when the bound game system defines it, else 'free_text'")
    description: str = Field(description="Human-readable effect description")
    mechanical_effects: list[str] = Field(default_factory=list)
    ends_when: str | None = Field(None, description="How the condition is removed, when known")


class CombatAgent(BaseAgent):
    """Deterministic combat-state operations plus optional table-side LLM bits.

    All state reads/writes go through ``call_tool`` (MCP, async). The DSPy
    module is only reached by the three ``*_narration``/``explain``/``summary``
    methods — HP math and round advance never touch an LLM.
    """

    def __init__(
        self,
        agent_type: str = "CombatAgent",
        agent_id: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(
            agent_type=agent_type,
            agent_id=agent_id or "combat-agent",
            model=model,
        )
        self.module = CombatModule()

    def _default_model_role(self) -> ModelRole:
        # At-the-table speed: narration and summaries are LIGHT-tier calls.
        return ModelRole.LIGHT

    async def run(self) -> None:
        pass  # every method is called directly by the /gm router

    # ------------------------------------------------------------------
    # Deterministic state transitions (plain code → MCP tools)
    # ------------------------------------------------------------------

    async def start_encounter(self, params: CombatStart) -> CombatSessionState:
        """Start (or restart) the encounter for (universe, session)."""
        return await self._call_state_tool("mongodb_combat_start", params)

    async def get_state(self, universe_id: UUID, session_id: str) -> CombatSessionState | None:
        """Return the live encounter state, or ``None`` when none exists."""
        result = _raise_on_tool_error(
            await self.call_tool(
                "mongodb_combat_get",
                {"universe_id": str(universe_id), "session_id": session_id},
            )
        )
        if result is None:
            return None
        return CombatSessionState.model_validate(result)

    async def update_combatant(self, params: CombatUpdateCombatant) -> CombatSessionState:
        """Apply HP / condition / flag changes to one combatant."""
        return await self._call_state_tool("mongodb_combat_update_combatant", params)

    async def set_initiative(self, params: CombatSetInitiative) -> CombatSessionState:
        """Record initiative rolls and compute the deterministic turn order."""
        return await self._call_state_tool("mongodb_combat_set_initiative", params)

    async def next_round(self, params: CombatNextRound) -> CombatSessionState:
        """Advance the round counter."""
        return await self._call_state_tool("mongodb_combat_next_round", params)

    async def end_encounter(self, params: CombatEnd) -> CombatSessionState:
        """End the encounter (status → RESOLVED)."""
        return await self._call_state_tool("mongodb_combat_end", params)

    async def _call_state_tool(self, tool_name: str, params: BaseModel) -> CombatSessionState:
        """Run a state tool over MCP with UUIDs stringified for JSON transport."""
        raw = params.model_dump(mode="json")
        result = _raise_on_tool_error(await self.call_tool(tool_name, raw))
        return CombatSessionState.model_validate(result)

    # ------------------------------------------------------------------
    # Optional LLM bits (DSPy module)
    # ------------------------------------------------------------------

    async def narrate_initiative(self, state: CombatSessionState) -> str:
        """One short paragraph announcing the initiative order (read-aloud)."""
        # turn_order is authoritative; fall back to current list order.
        by_id = {c.id: c for c in state.combatants}
        ordered = [by_id[t] for t in state.turn_order if t in by_id] or list(state.combatants)
        payload = json.dumps(
            [
                {
                    "name": c.name,
                    "side": c.side.value if hasattr(c.side, "value") else str(c.side),
                    "initiative": c.initiative,
                }
                for c in ordered
            ],
            default=str,
        )
        narration = await _to_thread(self.module.narrate_initiative, payload)
        log.info(
            "combat_initiative_narrated",
            agent_id=self.agent_id,
            combatants=len(ordered),
        )
        return narration

    async def explain_condition(
        self,
        condition: str,
        system_id: UUID | None = None,
        system_name: str | None = None,
    ) -> ConditionExplanation:
        """Explain a condition tag.

        Delegates to the bound game system first (structured ``conditions``
        definitions via ``GameSystemRuntime``); falls back to the DSPy module's
        free-text guidance when the system has no structured definition or no
        system is bound — per the G01 open decision.
        """
        if system_id is not None:
            result = _raise_on_tool_error(
                await self.call_tool("mongodb_get_game_system", {"system_id": str(system_id)})
            )
            if isinstance(result, dict) and result:
                from monitor_agents.game_system import GameSystemRuntime

                gsr = GameSystemRuntime(result)
                definition = gsr.get_condition(condition)
                if definition is not None:
                    effects = [str(e) for e in (definition.get("mechanical_effects") or [])]
                    description = (
                        "; ".join(effects) or str(definition.get("trigger") or "") or f"{condition} is active."
                    )
                    return ConditionExplanation(
                        condition=condition,
                        source="system",
                        description=description,
                        mechanical_effects=effects,
                        ends_when=definition.get("ends_when"),
                    )

        context = system_name or "none"
        explanation = await _to_thread(self.module.explain_condition, condition, context)
        return ConditionExplanation(
            condition=condition,
            source="free_text",
            description=explanation,
        )

    async def summarize_encounter(self, state: CombatSessionState) -> str:
        """Summarize the finished encounter for the GM's records (best-effort).

        The deterministic end transition has already happened when this runs;
        a failed summary never rolls back state — the router logs and carries
        on with staging proposals.
        """
        payload = state.model_dump_json()
        return await _to_thread(self.module.summarize_encounter, payload)


async def _to_thread(fn: Callable[..., _T], *args: Any) -> _T:
    """Run a blocking DSPy call off the event loop (mirrors dspy runtime use)."""
    return await asyncio.to_thread(fn, *args)
