"""
Progression Loop — LangGraph StateGraph for character advancement.

LAYER: 2 (agents)
"""

from typing import Any, Dict, List
from uuid import UUID
from pydantic import BaseModel, Field
from langgraph.graph import END, StateGraph


class ProgressionState(BaseModel):
    """State for the progression loop."""

    entity_id: UUID
    universe_id: UUID
    available_xp: int = 0
    available_upgrades: List[Dict[str, Any]] = Field(default_factory=list)
    selected_upgrades: List[Dict[str, Any]] = Field(default_factory=list)
    progression_complete: bool = False


async def load_progression_options(state: ProgressionState) -> Dict[str, Any]:
    """Load available upgrades based on game system and current stats."""
    # Placeholder: In a real implementation, this would use GameSystemRuntime
    # to find what the player can afford.
    upgrades = [
        {"id": "str_up", "name": "Increase Strength", "cost": 5, "stat": "STR", "value": 1},
        {"id": "dex_up", "name": "Increase Dexterity", "cost": 5, "stat": "DEX", "value": 1},
    ]
    return {"available_upgrades": upgrades}


async def finalize_progression(state: ProgressionState) -> Dict[str, Any]:
    """Commit selected upgrades to Neo4j via CanonKeeper."""
    from monitor_agents.canonkeeper import CanonKeeper

    keeper = CanonKeeper()
    for upgrade in state.selected_upgrades:
        # Commit stat change
        # This is a simplification; real logic would fetch current stat first
        await keeper.create_fact(
            {
                "universe_id": str(state.universe_id),
                "statement": f"Character {state.entity_id} increased {upgrade['stat']} via progression.",
                "fact_type": "state_change",
                "entity_ids": [state.entity_id],
                "properties": {"upgrade_id": upgrade["id"]},
            }
        )

    return {"progression_complete": True}


def build_progression_graph() -> StateGraph:
    graph = StateGraph(ProgressionState)

    graph.add_node("load_options", load_progression_options)
    graph.add_node("finalize", finalize_progression)

    graph.set_entry_point("load_options")
    graph.add_edge("load_options", END)  # Awaiting user selection externally
    graph.add_edge("finalize", END)

    return graph


class ProgressionLoop:
    def __init__(self, entity_id: UUID, universe_id: UUID) -> None:
        self.entity_id = entity_id
        self.universe_id = universe_id
        self._graph = build_progression_graph()

    async def start(self, available_xp: int) -> Dict[str, Any]:
        initial = ProgressionState(
            entity_id=self.entity_id, universe_id=self.universe_id, available_xp=available_xp
        )
        # For simplicity in this implementation, we run without checkpointer
        compiled = self._graph.compile()
        return await compiled.ainvoke(initial.model_dump())
