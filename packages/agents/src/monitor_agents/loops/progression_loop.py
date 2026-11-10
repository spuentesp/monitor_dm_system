"""
Progression Loop — LangGraph StateGraph for character advancement.

LAYER: 2 (agents)
"""

from typing import Any
from uuid import UUID

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field


class ProgressionState(BaseModel):
    """State for the progression loop."""

    entity_id: UUID
    universe_id: UUID
    available_xp: int = 0
    available_upgrades: list[dict[str, Any]] = Field(default_factory=list)
    selected_upgrades: list[dict[str, Any]] = Field(default_factory=list)
    progression_complete: bool = False


async def load_progression_options(state: ProgressionState) -> dict[str, Any]:
    """Load available upgrades based on game system and current stats."""
    # Placeholder: In a real implementation, this would use GameSystemRuntime
    # to find what the player can afford.
    upgrades = [
        {"id": "str_up", "name": "Increase Strength", "cost": 5, "stat": "STR", "value": 1},
        {"id": "dex_up", "name": "Increase Dexterity", "cost": 5, "stat": "DEX", "value": 1},
    ]
    return {"available_upgrades": upgrades}


async def finalize_progression(state: ProgressionState) -> dict[str, Any]:
    """Commit selected upgrades to Neo4j via CanonKeeper."""
    from monitor_agents.canonkeeper.agent import CanonKeeper

    keeper = CanonKeeper()
    for upgrade in state.selected_upgrades:
        # Commit stat change
        # This is a simplification; real logic would fetch current stat first
        await keeper.create_fact(
            {
                "universe_id": str(state.universe_id),
                "statement": f"Character {state.entity_id} increased {upgrade['stat']} via progression.",
                "fact_type": "state",
                "entity_ids": [str(state.entity_id)],
                "properties": {"upgrade_id": upgrade["id"]},
            }
        )

    return {"progression_complete": True}


def _route_after_options(state: ProgressionState) -> str:
    """A present selection applies immediately; an empty one waits for the
    player's choice (the ``start`` contract)."""
    return "finalize" if state.selected_upgrades else "await_selection"


def build_progression_graph() -> StateGraph[Any, Any, Any]:
    graph = StateGraph(ProgressionState)

    graph.add_node("load_options", load_progression_options)
    graph.add_node("finalize", finalize_progression)

    graph.set_entry_point("load_options")
    # The finalize node is reachable from ``apply_upgrade`` (which runs the
    # graph with a selection); ``start`` ends after loading options and waits
    # for the player's choice externally.
    graph.add_conditional_edges(
        "load_options",
        _route_after_options,
        {"finalize": "finalize", "await_selection": END},
    )
    graph.add_edge("finalize", END)

    return graph


class ProgressionLoop:
    def __init__(self, entity_id: UUID, universe_id: UUID) -> None:
        self.entity_id = entity_id
        self.universe_id = universe_id
        self._graph = build_progression_graph()

    async def start(self, available_xp: int) -> dict[str, Any]:
        """Offer the progression options and wait for the player's choice.

        Nothing is applied here (P-21): the award is only offered, and the
        player's selection is applied by ``apply_upgrade``.
        """
        initial = ProgressionState(entity_id=self.entity_id, universe_id=self.universe_id, available_xp=available_xp)
        # For simplicity in this implementation, we run without checkpointer
        compiled = self._graph.compile()
        return await compiled.ainvoke(initial.model_dump())

    async def apply_upgrade(self, upgrade_ids: list[str], *, available_xp: int = 0) -> dict[str, Any]:
        """Apply the player's chosen upgrades (P-21).

        The entry point that applies the selection ``start`` offered: the
        ids are validated against the offered options and the award, then
        committed through ``finalize_progression`` (CanonKeeper). Raises
        ``ValueError`` for an id that was never offered or a selection that
        costs more than the award — a player choice is required and must fit
        what the scene earned.
        """
        if not upgrade_ids:
            raise ValueError("no upgrades selected")
        offer_state = ProgressionState(
            entity_id=self.entity_id,
            universe_id=self.universe_id,
            available_xp=available_xp,
        )
        options = await load_progression_options(offer_state)
        offered = {str(upgrade.get("id")): upgrade for upgrade in options.get("available_upgrades") or []}
        selected: list[dict[str, Any]] = []
        spent = 0
        for raw_id in upgrade_ids:
            upgrade = offered.get(str(raw_id))
            if upgrade is None:
                raise ValueError(f"upgrade {raw_id} was not offered")
            selected.append(upgrade)
            spent += int(upgrade.get("cost") or 0)
        if available_xp and spent > available_xp:
            raise ValueError(f"selection costs {spent} XP but only {available_xp} is available")

        initial = offer_state.model_copy(update={"selected_upgrades": selected})
        compiled = self._graph.compile()
        result: dict[str, Any] = await compiled.ainvoke(initial.model_dump())
        return {
            **result,
            "xp_spent": spent,
            "xp_remaining": max(0, available_xp - spent),
        }
