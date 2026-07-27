"""
World Building Loop — LangGraph StateGraph for conversational world creation.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), langgraph, external libs
CALLED BY: chat router (Layer 3 / backend) via WorldBuildingLoop.run()

The World Building Loop handles the World Architect mode where users
collaboratively define their setting through conversation.  Unlike the
Scene Loop (interactive narrative), this loop:

- Has NO dice/resolution mechanics
- Uses WorldArchitect agent instead of Narrator
- Auto-commits proposals (user is defining their world deliberately)
- Tracks creation progress and suggests gaps

Flow:
  load_world_context → process_user_input → commit_proposals →
    format_response → (return to caller, await next input)

This loop is driven externally — each call to ``run()`` processes one
user turn and returns the architect's response.  The chat router manages
the outer message loop.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

# =============================================================================
# STATE SCHEMA
# =============================================================================


class WorldBuildingState(BaseModel):
    """State flowing through the World Building Loop nodes."""

    # Session identifiers
    session_id: str
    universe_id: UUID | None = None
    multiverse_id: UUID | None = None

    # Conversation context
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    current_user_input: str = ""

    # World state (loaded each turn for freshness)
    world_summary: dict[str, Any] = Field(default_factory=dict)
    world_profile: dict[str, Any] = Field(default_factory=dict)
    coverage_summary: str = ""
    known_open_questions: list[str] = Field(default_factory=list)
    priority_gaps: list[dict[str, Any]] = Field(default_factory=list)

    # Turn output
    response_text: str = ""
    extracted_proposals: list[dict[str, Any]] = Field(default_factory=list)
    committed_count: int = 0
    commit_errors: list[str] = Field(default_factory=list)

    # Flow control
    turns_count: int = 0
    is_first_turn: bool = True


# =============================================================================
# NODES
# =============================================================================


async def load_world_context(state: WorldBuildingState) -> dict[str, Any]:
    """
    Load current universe state from Neo4j for context injection.

    This runs at the start of every turn to ensure the architect has
    an up-to-date view of what exists in the world.

    Write: nothing (read-only node).
    """
    from monitor_agents.world_architect.agent import WorldArchitect

    architect = WorldArchitect()
    world_summary = await architect._load_world_state(state.universe_id)

    # On first turn with an empty universe, generate a welcome message
    is_first = state.turns_count == 0 and not state.conversation_history

    return {
        "world_summary": world_summary,
        "is_first_turn": is_first,
    }


async def process_user_input(state: WorldBuildingState) -> dict[str, Any]:
    """
    Process the user's message through the WorldArchitect agent.

    This is the core node — it runs the DSPy module to generate both
    a conversational response and structured proposal extractions.

    Write: nothing directly (proposals are committed in next node).
    """
    from monitor_agents.world_architect.agent import WorldArchitect

    architect = WorldArchitect()

    # If this is the very first turn and no input, generate a welcome
    if state.is_first_turn and not state.current_user_input:
        suggestion = await architect.suggest_next(state.universe_id)
        return {
            "response_text": (
                "Welcome to the **World Architect**! I'm here to help you build "
                "your setting from the ground up.\n\n"
                f"{suggestion}\n\n"
                "Describe your world however feels natural — I'll extract the key "
                "elements and add them to your universe."
            ),
            "extracted_proposals": [],
            "is_first_turn": False,
        }

    result = await architect.process_turn(
        user_message=state.current_user_input,
        universe_id=state.universe_id,
        conversation_history=state.conversation_history,
        multiverse_id=state.multiverse_id,
    )

    # Capture newly created container IDs
    newly_created = result.get("newly_created", {})
    updates: dict[str, Any] = {
        "response_text": result["response"],
        "extracted_proposals": result["proposals"],
        "committed_count": result["committed"],
        "commit_errors": result["errors"],
        "world_profile": result.get("world_profile", {}),
        "coverage_summary": result.get("coverage_summary", ""),
        "known_open_questions": result.get("known_open_questions", []),
        "priority_gaps": result.get("priority_gaps", []),
        "is_first_turn": False,
    }

    if "multiverse_id" in newly_created:
        updates["multiverse_id"] = newly_created["multiverse_id"]
    if "universe_id" in newly_created:
        updates["universe_id"] = newly_created["universe_id"]

    return updates


async def format_response(state: WorldBuildingState) -> dict[str, Any]:
    """
    Append creation summary to the response if proposals were committed.

    This enriches the architect's natural language response with a
    structured summary of what was actually added to Neo4j.

    Write: nothing.
    """
    response = state.response_text
    committed = state.committed_count
    proposals = state.extracted_proposals
    errors = state.commit_errors

    # Add creation summary footer
    if committed > 0:
        created_items = []
        for p in proposals[:committed]:
            p_type = p.get("proposal_type", "element")
            name = p.get("payload", {}).get("name") or p.get("payload", {}).get("statement", "")[:50]
            if name:
                created_items.append(f"  - {p_type.title()}: **{name}**")

        if created_items:
            response += "\n\n---\n_Added to your world:_\n" + "\n".join(created_items)

    if errors:
        response += f"\n\n_({len(errors)} element(s) could not be added — will retry on next turn)_"

    return {
        "response_text": response,
        "turns_count": state.turns_count + 1,
    }


# =============================================================================
# GRAPH BUILDER
# =============================================================================


def build_world_building_graph() -> StateGraph:
    """Construct the World Building Loop StateGraph."""
    graph = StateGraph(WorldBuildingState)

    graph.add_node("load_world_context", load_world_context)
    graph.add_node("process_user_input", process_user_input)
    graph.add_node("format_response", format_response)

    graph.set_entry_point("load_world_context")
    graph.add_edge("load_world_context", "process_user_input")
    graph.add_edge("process_user_input", "format_response")
    graph.add_edge("format_response", END)

    return graph


# =============================================================================
# LOOP CLASS
# =============================================================================


class WorldBuildingLoop:
    """
    High-level interface for the World Building Loop.

    Each call to ``run()`` processes one user turn through the graph
    and returns the architect's response.

    Usage:
        loop = WorldBuildingLoop(
            session_id="abc",
            universe_id=UUID("..."),
        )
        result = await loop.run(user_input="I want a dark fantasy world")
        print(result["response_text"])
    """

    def __init__(
        self,
        session_id: str,
        universe_id: UUID | None = None,
        multiverse_id: UUID | None = None,
    ) -> None:
        self.session_id = session_id
        self.universe_id = universe_id
        self.multiverse_id = multiverse_id
        self._graph = build_world_building_graph().compile()

    async def run(
        self,
        user_input: str = "",
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Execute one world-building turn.

        Args:
            user_input: The user's message.
            conversation_history: Prior messages for context.

        Returns:
            Dict with response_text, extracted_proposals, committed_count, etc.
        """
        initial_state = WorldBuildingState(
            session_id=self.session_id,
            universe_id=self.universe_id,
            multiverse_id=self.multiverse_id,
            conversation_history=conversation_history or [],
            current_user_input=user_input,
        )

        result = await self._graph.ainvoke(initial_state.model_dump())

        return {
            "response_text": result.get("response_text", ""),
            "extracted_proposals": result.get("extracted_proposals", []),
            "committed_count": result.get("committed_count", 0),
            "commit_errors": result.get("commit_errors", []),
            "turns_count": result.get("turns_count", 0),
            "world_profile": result.get("world_profile", {}),
            "coverage_summary": result.get("coverage_summary", ""),
            "known_open_questions": result.get("known_open_questions", []),
            "priority_gaps": result.get("priority_gaps", []),
        }
