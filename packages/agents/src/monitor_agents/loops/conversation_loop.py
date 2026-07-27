"""
Conversation Loop — LangGraph StateGraph for NPC dialogue sessions.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), langgraph, external libs
CALLED BY: CLI (Layer 3) via ConversationLoop.run()

The Conversation Loop handles two NPC interaction modes:

  DIRECT — Real-time in-character dialogue.
    Player speaks; NPCVoice responds AS the NPC using a LIGHT model.
    Multiple NPCs can participate sequentially.
    Loop runs until player exits with a meta-command.

  ACTOR  — Out-of-character actor reflection for GM prep.
    GM asks questions; NPCVoice reflects as an actor on their role.
    No dice, no scene mechanics. Pure conversation.

This loop is much lighter than SceneLoop:
- No Resolver (no dice rolls)
- No CanonKeeper mid-loop (proposals staged, written at loop end)
- Scene is the durability boundary: ConversationSession is ephemeral
  within it. Scene checkpoint = memory writes + proposal staging.

Flow (DIRECT mode):
  open_session → load_npc_context → [LOOP]: player_turn →
    npc_response (per NPC) → persist_turn → check_exit →
  close_session → stage_proposals

Flow (ACTOR mode):
  open_session → load_npc_context → [LOOP]: gm_turn →
    actor_response → persist_turn → check_exit →
  close_session → stage_proposals
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from langgraph.graph import END, StateGraph
from monitor_data.schemas.conversations import ConversationMode, ConversationStatus
from pydantic import BaseModel, Field

# Re-export ConversationMode so Layer 3 (CLI) can import it from here
# instead of directly from monitor_data.schemas.conversations.
__all__ = ["ConversationMode"]


def _normalize_conversation_change_type(change_type: str) -> str:
    """Map legacy NPC proposal labels into canonical ProposedChange types."""
    normalized = (change_type or "fact").strip().lower()
    mapping = {
        "npc_emotional_state": "state_change",
        "relationship_delta": "relationship",
        "npc_profile_update": "entity",
        "fact_proposal": "fact",
    }
    return mapping.get(normalized, normalized)


_NPC_CONTEXT_LOAD_CONCURRENCY = 4


# =============================================================================
# STATE SCHEMA
# =============================================================================


class ConversationState(BaseModel):
    """State flowing through the Conversation Loop nodes."""

    # Session identifiers
    conversation_id: UUID
    universe_id: UUID
    mode: ConversationMode

    # NPC roster for this session
    npc_ids: list[UUID] = Field(default_factory=list)
    scene_id: UUID | None = None
    story_id: UUID | None = None
    player_entity_id: UUID | None = None

    # Cached NPC context (loaded once, reused across turns)
    npc_contexts: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Keys are str(npc_id); values are {name, role, profile, facts}",
    )
    source_profile: dict[str, Any] = Field(default_factory=dict)

    # Turn tracking
    turns: list[dict[str, Any]] = Field(default_factory=list)
    current_player_input: str | None = None
    current_npc_responses: list[dict[str, Any]] = Field(default_factory=list)

    # Accumulated proposals (flushed at session end)
    pending_proposals: list[dict[str, Any]] = Field(default_factory=list)

    # Flow control
    is_complete: bool = False
    turns_count: int = 0
    max_turns: int = 100  # safety ceiling for a single session

    # NPC memory scoping — when True, NPCVoice recall broadens past the
    # current universe so a character version from a sibling universe can
    # answer (e.g. canon Sister Veil across incarnations). Default False
    # to preserve per-universe incarnation isolation.
    include_cross_incarnation: bool = False


# =============================================================================
# NODES
# =============================================================================


def _extract_conversation_id(result: Any) -> UUID | None:
    """Pull the persisted conversation_id out of a create-conversation response."""
    raw: Any = None
    if isinstance(result, dict):
        raw = result.get("conversation_id")
    elif result is not None and hasattr(result, "conversation_id"):
        raw = result.conversation_id
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return None


async def open_session(state: ConversationState) -> dict[str, Any]:
    """
    Create the ConversationSession document in MongoDB and adopt its ID.

    The create tool always mints its own conversation_id, so we read it back
    and propagate it into state — otherwise every later append/persist/close
    would target a non-existent session.

    Write: ConversationSession → MongoDB.
    """
    try:
        from monitor_agents.npc_voice.agent import NPCVoice

        agent = NPCVoice()
        result = await agent.call_tool(
            "mongodb_create_conversation",
            {
                "params": {
                    "universe_id": str(state.universe_id),
                    "mode": state.mode.value,
                    "npc_ids": [str(nid) for nid in state.npc_ids],
                    "scene_id": str(state.scene_id) if state.scene_id else None,
                    "story_id": str(state.story_id) if state.story_id else None,
                    "player_entity_id": (str(state.player_entity_id) if state.player_entity_id else None),
                    "metadata": {},
                },
            },
        )
        conversation_id = _extract_conversation_id(result)
        if conversation_id is not None:
            return {"conversation_id": conversation_id}
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to create ConversationSession in MongoDB",
            exc_info=True,
        )
    return {}


async def load_npc_context(state: ConversationState) -> dict[str, Any]:
    """
    Pre-load all NPC entity data (entity + profile + facts) into state.

    This avoids re-querying Neo4j on every turn.
    Write: nothing.
    """
    from monitor_agents.npc_voice.agent import NPCVoice

    agent = NPCVoice()
    include_secrets = state.mode == ConversationMode.ACTOR
    contexts: dict[str, dict[str, Any]] = {}
    semaphore = asyncio.Semaphore(_NPC_CONTEXT_LOAD_CONCURRENCY)

    async def _load_one(npc_id: UUID) -> tuple[str, dict[str, Any]]:
        async with semaphore:
            try:
                npc_data = await agent._load_npc_data(npc_id, include_secrets=include_secrets)
                return str(npc_id), npc_data
            except ValueError:
                return str(npc_id), {
                    "name": f"Unknown NPC ({npc_id})",
                    "role": "unknown",
                    "profile": {},
                    "facts": [],
                }

    loaded_contexts = await asyncio.gather(*[_load_one(npc_id) for npc_id in state.npc_ids])
    contexts = dict(loaded_contexts)

    # Load the active source profile so NPCVoice receives setting vocabulary context.
    source_profile: dict[str, Any] = {}
    try:
        from monitor_agents.context_assembly.agent import ContextAssembly

        ca = ContextAssembly()
        source_profile = await ca._fetch_runtime_profile()
    except Exception:
        pass

    return {"npc_contexts": contexts, "source_profile": source_profile}


async def process_player_turn(state: ConversationState) -> dict[str, Any]:
    """
    Append the player's input turn to the session in MongoDB.

    Write: player ConversationTurn → MongoDB.
    """
    if not state.current_player_input:
        return {}

    from monitor_agents.npc_voice.agent import NPCVoice

    agent = NPCVoice()
    await agent.call_tool(
        "mongodb_append_conversation_turn",
        {
            "conversation_id": str(state.conversation_id),
            "params": {
                "speaker_role": "player",
                "entity_id": str(state.player_entity_id) if state.player_entity_id else None,
                "entity_name": "Player",
                "text": state.current_player_input,
                "emotional_state": None,
            },
        },
    )

    new_turn = {
        "turn_index": len(state.turns),
        "speaker_role": "player",
        "text": state.current_player_input,
    }
    return {"turns": state.turns + [new_turn], "current_npc_responses": []}


async def generate_npc_responses(state: ConversationState) -> dict[str, Any]:
    """
    Generate responses from all NPCs in this session.

    For DIRECT mode: NPCVoice speaks as each NPC in turn.
    For ACTOR mode: NPCVoice reflects as the actor.

    Write: NPC ConversationTurn(s) → MongoDB (via NPCVoice).
    """
    if not state.current_player_input:
        return {}

    from monitor_agents.npc_voice.agent import NPCVoice

    agent = NPCVoice()
    responses: list[dict[str, Any]] = []
    new_proposals: list[dict[str, Any]] = []
    new_turns: list[dict[str, Any]] = list(state.turns)

    for npc_id in state.npc_ids:
        try:
            if state.mode == ConversationMode.DIRECT:
                result = await agent.respond_direct(
                    conversation_id=state.conversation_id,
                    npc_id=npc_id,
                    player_said=state.current_player_input,
                    conversation_history=state.turns,
                    player_entity_id=state.player_entity_id,
                    scene_id=state.scene_id,
                    story_id=state.story_id,
                    source_profile=state.source_profile,
                    npc_data=state.npc_contexts.get(str(npc_id)),
                    # Character-versions: thread the loop's universe_id so
                    # NPCVoice scopes recall, working state, and proposals
                    # to this incarnation.
                    universe_id=state.universe_id,
                    include_cross_incarnation=getattr(state, "include_cross_incarnation", False),
                )
                npc_name = state.npc_contexts.get(str(npc_id), {}).get("name", str(npc_id))
                responses.append(
                    {
                        "npc_id": str(npc_id),
                        "npc_name": npc_name,
                        "text": result["npc_response"],
                        "emotional_state": result["emotional_state_after"],
                        "social_read": result.get("social_read", {}),
                        "relationship_snapshot": result.get("relationship_snapshot", {}),
                    }
                )
                new_proposals.extend(result.get("proposals", []))
                new_turns.append(
                    {
                        "turn_index": len(new_turns),
                        "speaker_role": "npc",
                        "entity_id": str(npc_id),
                        "entity_name": npc_name,
                        "text": result["npc_response"],
                    }
                )

            elif state.mode == ConversationMode.ACTOR:
                result = await agent.respond_actor(
                    conversation_id=state.conversation_id,
                    npc_id=npc_id,
                    gm_question=state.current_player_input,
                    conversation_history=state.turns,
                    source_profile=state.source_profile,
                    npc_data=state.npc_contexts.get(str(npc_id)),
                )
                npc_name = state.npc_contexts.get(str(npc_id), {}).get("name", str(npc_id))
                responses.append(
                    {
                        "npc_id": str(npc_id),
                        "npc_name": npc_name,
                        "text": result["actor_response"],
                        "canon_insight": result["canon_insight"],
                    }
                )
                new_proposals.extend(result.get("proposals", []))
                new_turns.append(
                    {
                        "turn_index": len(new_turns),
                        "speaker_role": "npc",
                        "entity_id": str(npc_id),
                        "entity_name": npc_name,
                        "text": result["actor_response"],
                    }
                )
        except Exception:
            # Individual NPC failure shouldn't crash the whole conversation
            import logging

            logging.getLogger(__name__).warning(
                "NPC %s response generation failed",
                npc_id,
                exc_info=True,
            )
            npc_name = state.npc_contexts.get(str(npc_id), {}).get("name", str(npc_id))
            responses.append(
                {
                    "npc_id": str(npc_id),
                    "npc_name": npc_name,
                    "text": f"({npc_name} pauses, lost in thought…)",
                }
            )

    return {
        "current_npc_responses": responses,
        "turns": new_turns,
        "pending_proposals": state.pending_proposals + new_proposals,
        "turns_count": state.turns_count + 1,
        "current_player_input": None,  # reset for next turn
    }


async def close_session(state: ConversationState) -> dict[str, Any]:
    """
    Mark the ConversationSession as completed in MongoDB.
    Stage any accumulated proposals as ProposedChange documents.

    Write: session status → MongoDB; proposals → MongoDB.
    """
    from monitor_agents.npc_voice.agent import NPCVoice

    agent = NPCVoice()

    # Mark session complete
    await agent.call_tool(
        "mongodb_update_conversation",
        {
            "conversation_id": str(state.conversation_id),
            "params": {"status": ConversationStatus.COMPLETED.value},
        },
    )

    # Stage proposals for CanonKeeper (written to proposed_changes collection)
    for proposal in state.pending_proposals:
        try:
            params: dict[str, Any] = {
                "change_type": _normalize_conversation_change_type(proposal.get("change_type", "fact")),
                "content": proposal.get("content", {}),
                "confidence": proposal.get("confidence", 0.5),
                "authority": proposal.get("authority", "system"),
                "proposer": proposal.get("proposer", "NPCVoice"),
                "evidence": [{"type": "snippet", "ref_id": str(state.conversation_id)}],
            }
            if state.scene_id is not None:
                params["scene_id"] = str(state.scene_id)
            if state.story_id is not None:
                params["story_id"] = str(state.story_id)
            # Stamp the incarnation's universe on every staged proposal so
            # CanonKeeper (and downstream readers) can route the change to
            # the right character-version partition.
            if state.universe_id is not None:
                params["universe_id"] = str(state.universe_id)
                # Also stamp on content if NPCVoice didn't already.
                content = params.setdefault("content", {})
                if isinstance(content, dict) and "universe_id" not in content:
                    content["universe_id"] = str(state.universe_id)

            turn_id = proposal.get("turn_id") or proposal.get("content", {}).get("turn_id")
            if turn_id is not None:
                params["turn_id"] = str(turn_id)

            await agent.call_tool(
                "mongodb_create_proposed_change",
                {"params": params},
            )
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to stage proposal for conversation %s",
                state.conversation_id,
                exc_info=True,
            )

    return {}


def route_after_npc_response(state: ConversationState) -> str:
    """Route back to player turn or end the session."""
    if state.is_complete or state.turns_count >= state.max_turns:
        return "close"
    return END  # CLI layer drives the next player input injection


# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================


def build_conversation_graph() -> StateGraph:
    """Build and compile the Conversation Loop StateGraph."""
    graph = StateGraph(ConversationState)

    graph.add_node("open_session", open_session)
    graph.add_node("load_npc_context", load_npc_context)
    graph.add_node("process_player_turn", process_player_turn)
    graph.add_node("generate_npc_responses", generate_npc_responses)
    graph.add_node("close_session", close_session)

    graph.set_entry_point("open_session")
    graph.add_edge("open_session", "load_npc_context")
    graph.add_edge("load_npc_context", END)  # CLI injects player input after this

    # Mid-session flow (player input → NPC response)
    graph.add_edge("process_player_turn", "generate_npc_responses")
    graph.add_conditional_edges(
        "generate_npc_responses",
        route_after_npc_response,
        {"close": "close_session", END: END},
    )
    graph.add_edge("close_session", END)

    return graph


# =============================================================================
# PUBLIC API
# =============================================================================


class ConversationLoop:
    """
    Manages a full NPC conversation session (DIRECT or ACTOR mode).

    Lifecycle:
        loop = await ConversationLoop.start(...)      # opens session, loads context
        for player_input in player_inputs:
            responses = await loop.step(player_input) # one exchange
        await loop.finish()                           # closes + stages proposals

    The loop is stateless between calls except for conversation_id and
    the in-memory LangGraph state (which is lightweight).
    """

    def __init__(
        self,
        conversation_id: UUID,
        universe_id: UUID,
        mode: ConversationMode,
        npc_ids: list[UUID],
        scene_id: UUID | None = None,
        story_id: UUID | None = None,
        player_entity_id: UUID | None = None,
    ) -> None:
        self.state = ConversationState(
            conversation_id=conversation_id,
            universe_id=universe_id,
            mode=mode,
            npc_ids=npc_ids,
            scene_id=scene_id,
            story_id=story_id,
            player_entity_id=player_entity_id,
        )
        self._graph = build_conversation_graph().compile()
        self._closed = False

    def _apply(self, update: dict[str, Any]) -> None:
        """Merge a node's partial-state update back into self.state."""
        if update:
            self.state = ConversationState(**{**self.state.model_dump(), **update})

    @classmethod
    async def start(
        cls,
        universe_id: UUID,
        mode: ConversationMode,
        npc_ids: list[UUID],
        scene_id: UUID | None = None,
        story_id: UUID | None = None,
        player_entity_id: UUID | None = None,
    ) -> ConversationLoop:
        """Open a new ConversationSession and pre-load NPC context."""
        conversation_id = uuid4()
        loop = cls(
            conversation_id=conversation_id,
            universe_id=universe_id,
            mode=mode,
            npc_ids=npc_ids,
            scene_id=scene_id,
            story_id=story_id,
            player_entity_id=player_entity_id,
        )
        # Run open_session + load_npc_context nodes
        result = await loop._graph.ainvoke(loop.state.model_dump())
        loop.state = ConversationState(**{**loop.state.model_dump(), **result})
        return loop

    async def step(self, player_input: str) -> list[dict[str, Any]]:
        """
        Process one player input → return list of NPC responses.

        Drives the mid-session nodes directly. The compiled graph has a single
        fixed entry point (open_session), so re-invoking it per turn would only
        re-run the setup flow and never reach response generation — hence we
        run process_player_turn → generate_npc_responses explicitly here.

        Args:
            player_input: What the player said / asked.

        Returns:
            List of dicts: [{npc_name, text, emotional_state?, canon_insight?}]
        """
        self.state.current_player_input = player_input

        self._apply(await process_player_turn(self.state))
        self._apply(await generate_npc_responses(self.state))

        # Honor the loop's own ceiling (max_turns / explicit completion).
        if route_after_npc_response(self.state) == "close" and not self._closed:
            self._apply(await close_session(self.state))
            self._closed = True

        return self.state.current_npc_responses

    async def finish(self) -> list[dict[str, Any]]:
        """
        Close the session and stage all accumulated proposals.

        Returns:
            Staged proposals list (for caller to display or confirm).
        """
        self.state.is_complete = True
        if not self._closed:
            self._apply(await close_session(self.state))
            self._closed = True
        return self.state.pending_proposals
