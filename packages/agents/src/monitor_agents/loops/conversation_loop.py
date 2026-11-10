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

import structlog

import asyncio
import logging
from typing import Any, Literal
from uuid import UUID, uuid4

from langgraph.graph import END, StateGraph
from monitor_data.schemas.conversations import ConversationMode, ConversationStatus
from monitor_data.tenancy import owner_scope, owner_scoped
from pydantic import BaseModel, Field

log = structlog.get_logger()

# Re-export ConversationMode so Layer 3 (CLI) can import it from here
# instead of directly from monitor_data.schemas.conversations.
__all__ = [
    "ConversationClosedError",
    "ConversationMode",
    "LightPreset",
    "PRESETS",
    "get_preset",
]

logger = logging.getLogger(__name__)


class ConversationClosedError(RuntimeError):
    """Raised when a caller attempts to step a closed or exhausted ConversationLoop."""


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
# PRESETS — named configuration over this loop (Phase 7, light RP)
# =============================================================================


class LightPreset(BaseModel):
    """Named configuration over the ConversationLoop — never a new loop.

    The "light" preset is the Conversatory default: pick a character, start
    talking. It declares what light RP explicitly does not run — no dice, no
    GM verdict step, no canonization prompts — and which model tier the voice
    runs on (LIGHT by default, STANDARD when the user opts into more care).

    ``stage_canon_proposals`` is the behavioral knob: light RP is "no canon,
    just talk", so a light-preset close stages no ProposedChange documents
    (the canon review queue stays clean) while per-turn CharacterMemory
    writes — the character's recall — are unaffected.
    """

    name: str = "light"
    model_tier: Literal["light", "standard"] = Field(
        default="light",
        description=(
            "Model tier for the NPC voice. 'light' (default) or 'standard'. "
            "The tier resolves through the LLM registry's npc_voice node."
        ),
    )
    dice: bool = False
    gm_verdict: bool = False
    canonization_prompts: bool = False
    stage_canon_proposals: bool = False


PRESETS: dict[str, LightPreset] = {"light": LightPreset()}


def get_preset(name: str) -> LightPreset:
    """Resolve a named preset. Raises KeyError for unknown names."""
    return PRESETS[name]


# =============================================================================
# STATE SCHEMA
# =============================================================================


class ConversationState(BaseModel):
    """State flowing through the Conversation Loop nodes."""

    # Session identifiers
    conversation_id: UUID
    universe_id: UUID
    mode: ConversationMode
    # Acting owner (multi-tenancy): bound around every turn so write-tool
    # ownership assertions and usage accounting see it (monitor_data.tenancy).
    owner_id: str | None = None

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

    # Lorebook scanning — character ids whose lorebook entries are scanned
    # per turn (light-RP passes the backing character; empty disables the
    # scan). Matched contents are injected into NPCVoice as world facts.
    lorebook_character_ids: list[str] = Field(default_factory=list)

    # Bound persona ("name — description" rendered from the persona card).
    # Injected into the voice module so the NPC knows who they're talking
    # to. Empty when no persona is bound.
    player_persona: str = ""

    # Rendered card text for a character imported from a card. Empty for story NPCs.
    character_card: str = ""

    # Lorebook entry id → active, set by the character's @@activate / @@deactivate
    # directives. Applies to this conversation only; the lorebook isn't changed.
    lorebook_overrides: dict[str, bool] = Field(default_factory=dict)

    # Persona display name (before " — description"). Feeds the CAST block so
    # the player is named when the agency rule is stated. Empty when unbound.
    player_name: str = ""

    # Preset configuration (Phase 7 light RP). Defaults preserve the legacy
    # loop behavior; a LightPreset overrides them via ConversationLoop.start.
    preset_name: str = ""
    model_tier: Literal["light", "standard"] = "light"
    stage_canon_proposals: bool = True

    # Streaming (Phase 7): when True, this turn's NPC memory writes are
    # buffered into deferred_memory_writes instead of running inline, so the
    # caller can flush them after the reply's stream completes.
    defer_memory_writes: bool = False
    deferred_memory_writes: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# NODES
# =============================================================================


def _with_exchange_applied(
    npc_context: dict[str, Any],
    result: dict[str, Any],
    player_entity_id: UUID | None,
    universe_id: UUID,
) -> dict[str, Any]:
    """Return the cached NPC context updated with this exchange's social state.

    The context is loaded once per session, and NPCVoice computes each turn from
    it. Without this, every turn starts again from the session's opening state.
    """
    profile = dict(npc_context.get("profile") or {})
    emotion = result.get("emotional_state_after")
    if emotion:
        profile["current_emotional_state"] = emotion
        profile["current_emotional_state_by_universe"] = {
            **(profile.get("current_emotional_state_by_universe") or {}),
            str(universe_id): emotion,
        }

    snapshot = {k: v for k, v in (result.get("relationship_snapshot") or {}).items() if k != "last_delta"}
    if snapshot and player_entity_id is not None:
        player = str(player_entity_id)
        profile["relationship_states"] = {**(profile.get("relationship_states") or {}), player: snapshot}
        by_universe = dict(profile.get("relationship_states_by_universe") or {})
        by_universe[str(universe_id)] = {**(by_universe.get(str(universe_id)) or {}), player: snapshot}
        profile["relationship_states_by_universe"] = by_universe

    return {**npc_context, "profile": profile}


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


async def _flush_memory_writes(calls: list[dict[str, Any]]) -> int:
    """Run buffered ``_write_npc_memory`` calls through the real NPCVoice.

    Each buffered entry is the exact kwargs ``respond_direct`` would have
    passed to ``NPCVoice._write_npc_memory``; the real callee is invoked here
    so streaming can defer the writes until the stream completes without
    changing what gets written.
    """
    if not calls:
        return 0
    from monitor_agents.npc_voice.agent import NPCVoice

    agent = NPCVoice()
    flushed = 0
    for kwargs in calls:
        await NPCVoice._write_npc_memory(agent, **kwargs)
        flushed += 1
    return flushed


class _DeferredMemoryWriter:
    """Stand-in for ``NPCVoice._write_npc_memory`` while a reply streams.

    Buffers the real write's keyword arguments; the loop replays them through
    the real method via ``_flush_memory_writes`` once the stream completes.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def _make_voice_agent(
    model_tier: str = "light",
    *,
    defer_memory_writes: bool = False,
) -> tuple[Any, _DeferredMemoryWriter | None]:
    """Build the NPCVoice for one turn, honoring the preset's tier and memory policy.

    Returns ``(agent, writer)`` where ``writer`` is the buffering stand-in when
    memory writes are deferred (the caller must flush), else ``None``.
    """
    from monitor_agents.npc_voice.agent import NPCVoice

    agent = NPCVoice()
    writer: _DeferredMemoryWriter | None = None

    if model_tier == "standard":
        from monitor_agents import dspy_runtime
        from monitor_agents.npc_voice.npc_voice import NPCDirectVoiceModule
        from monitor_data.schemas.llm_config import ModelRole

        class _TieredDirectVoiceModule(NPCDirectVoiceModule):
            """NPCDirectVoiceModule bound to the preset's model tier."""

            def forward(self, *args: Any, **kwargs: Any) -> Any:
                # Module-attribute lookup (not a captured name) so tests can
                # patch monitor_agents.dspy_runtime.dspy_context_for.
                with dspy_runtime.dspy_context_for("npc_voice", ModelRole.STANDARD):
                    return self.speak(*args, **kwargs)

        module = _TieredDirectVoiceModule()
        agent._direct_module = module
        if getattr(agent, "_direct_module", None) is not module:
            raise RuntimeError("could not install the tiered voice module on NPCVoice")

    if defer_memory_writes:
        if not hasattr(NPCVoice, "_write_npc_memory"):
            raise RuntimeError("NPCVoice has no _write_npc_memory; cannot defer memory writes")
        writer = _DeferredMemoryWriter()
        agent._write_npc_memory = writer  # type: ignore[method-assign, assignment]

    return agent, writer


def _persona_prompt_block(state: ConversationState, npc_id: UUID, npc_name: str) -> str:
    """Render the bound persona plus the Phase 4 cast block (agency rule).

    The persona goes into the prompt by name and description. The cast is
    built with the Phase 4 builder and rendered with its own ``to_prompt_block``
    so the single source of the agency rule (``monitor_agents.cast``) is reused:
    the character never speaks for the user's player-controlled persona.
    """
    from monitor_agents.cast import build_cast

    player_key = str(state.player_entity_id) if state.player_entity_id else ""
    persona_name = state.player_name or ""
    personas: dict[str, dict[str, Any]] = {}
    if player_key and persona_name:
        personas[player_key] = {"persona_id": player_key, "persona_name": persona_name}
    cast = build_cast(
        controlled_ids=[player_key] if player_key else [],
        speaker_id=player_key or None,
        actor_context={"id": player_key, "name": persona_name or "the player"} if player_key else None,
        personas=personas,
        npc_profiles={str(npc_id): {"name": npc_name}},
    )
    cast_block = cast.to_prompt_block()
    parts = [p for p in (state.player_persona.strip(), cast_block) if p]
    return "\n\n".join(parts)


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
    except Exception:  # noqa: BLE001  # reason: intentional boundary: documented failure tolerance (in open_session)
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
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _load_one)
        log.debug("runtime profile fetch failed for NPCVoice", exc_info=True)

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

    agent, memory_writer = _make_voice_agent(
        state.model_tier,
        defer_memory_writes=state.defer_memory_writes,
    )
    responses: list[dict[str, Any]] = []
    new_proposals: list[dict[str, Any]] = []
    new_turns: list[dict[str, Any]] = list(state.turns)
    npc_contexts = dict(state.npc_contexts)
    lorebook_overrides = dict(state.lorebook_overrides)
    # process_player_turn already appended the line being answered.
    latest = state.turns[-1] if state.turns else {}
    prior_turns = state.turns[:-1] if latest.get("text") == state.current_player_input else state.turns

    # Lorebook scan — light-RP sessions carry the backing character id(s);
    # matched entries become world facts for the voice module. Best-effort:
    # a scan failure must not break the turn.
    lorebook_context: list[str] = []
    if state.lorebook_character_ids:
        try:
            history = [t.get("text", "") for t in prior_turns[-6:] if t.get("text")]
            scan_config = await agent.call_tool(
                "mongodb_get_scan_config", {"character_id": state.lorebook_character_ids[0]}
            )
            lore_result = await agent.call_tool(
                "mongodb_scan_lorebook",
                {
                    "character_ids": state.lorebook_character_ids,
                    "text": state.current_player_input,
                    "history": history,
                    "config": scan_config if isinstance(scan_config, dict) else {},
                    "turn_index": len(state.turns),
                    "increment_triggers": True,
                    "active_overrides": state.lorebook_overrides,
                },
            )
            if isinstance(lore_result, dict):
                lorebook_context = (
                    (lore_result.get("before") or [])
                    + (lore_result.get("after") or [])
                    + (lore_result.get("depth") or [])
                )
        except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in generate_npc_responses)
            logger.warning("conversation_loop: lorebook scan failed, continuing without", exc_info=True)

    from monitor_agents.llm_errors import LLMProviderUnavailable

    succeeded = 0
    last_error: Exception | None = None
    failed_npcs: list[tuple[UUID, str]] = []

    for npc_id in state.npc_ids:
        try:
            # Each NPC hears the replies the others already gave this round,
            # so a group answers as a group instead of in isolation.
            conversation_history = [*prior_turns, *new_turns[len(state.turns) :]]
            if state.mode == ConversationMode.DIRECT:
                result = await agent.respond_direct(
                    conversation_id=state.conversation_id,
                    npc_id=npc_id,
                    player_said=state.current_player_input,
                    conversation_history=conversation_history,
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
                    lorebook_context=lorebook_context,
                    player_persona=_persona_prompt_block(
                        state, npc_id, state.npc_contexts.get(str(npc_id), {}).get("name", str(npc_id))
                    ),
                    character_card=state.character_card,
                    parse_directives=bool(state.lorebook_character_ids),
                )
                npc_name = state.npc_contexts.get(str(npc_id), {}).get("name", str(npc_id))
                # Lorebook output directives (@@activate / @@deactivate) are
                # runtime commands, not prose. NPCVoice strips them before saving;
                # the parse here only covers a voice that didn't. Best-effort.
                npc_text = result["npc_response"]
                if state.lorebook_character_ids and isinstance(npc_text, str):
                    try:
                        from monitor_agents.lorebook_directives import (
                            apply_lorebook_directives,
                            parse_output_directives,
                        )

                        npc_text, leftover = parse_output_directives(npc_text)
                        directives = [*(result.get("lorebook_directives") or []), *leftover]
                        if directives:
                            lorebook_overrides = await apply_lorebook_directives(
                                agent, state.lorebook_character_ids, directives, lorebook_overrides
                            )
                    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in generate_npc_responses)
                        logger.warning(
                            "conversation_loop: lorebook directives failed, continuing",
                            exc_info=True,
                        )
                        npc_text = result["npc_response"]
                responses.append(
                    {
                        "npc_id": str(npc_id),
                        "npc_name": npc_name,
                        "text": npc_text,
                        "emotional_state": result["emotional_state_after"],
                        "social_read": result.get("social_read", {}),
                        "relationship_snapshot": result.get("relationship_snapshot", {}),
                    }
                )
                new_proposals.extend(result.get("proposals", []))
                if str(npc_id) in npc_contexts:
                    npc_contexts[str(npc_id)] = _with_exchange_applied(
                        npc_contexts[str(npc_id)], result, state.player_entity_id, state.universe_id
                    )
                new_turns.append(
                    {
                        "turn_index": len(new_turns),
                        "speaker_role": "npc",
                        "entity_id": str(npc_id),
                        "entity_name": npc_name,
                        "text": npc_text,
                    }
                )
                succeeded += 1

            elif state.mode == ConversationMode.ACTOR:
                result = await agent.respond_actor(
                    conversation_id=state.conversation_id,
                    npc_id=npc_id,
                    gm_question=state.current_player_input,
                    conversation_history=conversation_history,
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
                succeeded += 1
        except LLMProviderUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001  # reason: intentional boundary: documented failure tolerance (in generate_npc_responses)
            # In multi-NPC conversations, one NPC failing shouldn't drop replies
            # from other NPCs; if every NPC fails (including 1:1 chats), propagate.
            logger.warning(
                "NPC %s response generation failed",
                npc_id,
                exc_info=True,
            )
            last_error = exc
            npc_name = state.npc_contexts.get(str(npc_id), {}).get("name", str(npc_id))
            failed_npcs.append((npc_id, npc_name))

    if succeeded == 0 and last_error is not None:
        raise last_error

    for failed_id, failed_name in failed_npcs:
        responses.append(
            {
                "npc_id": str(failed_id),
                "npc_name": failed_name,
                "text": f"({failed_name} pauses, lost in thought…)",
            }
        )

    # Light RP ("no canon"): drop per-turn canon proposals at the source so
    # nothing accumulates for canonization. Memory writes are unaffected.
    if not state.stage_canon_proposals:
        new_proposals = []

    return {
        "current_npc_responses": responses,
        "npc_contexts": npc_contexts,
        "lorebook_overrides": lorebook_overrides,
        "turns": new_turns,
        "pending_proposals": state.pending_proposals + new_proposals,
        "turns_count": state.turns_count + 1,
        "current_player_input": None,  # reset for next turn
        "deferred_memory_writes": (
            state.deferred_memory_writes + list(memory_writer.calls)
            if memory_writer is not None
            else state.deferred_memory_writes
        ),
    }


async def _extract_episodic_memories(state: ConversationState) -> list[dict[str, Any]]:
    """Distill salient episodic memories from the full session transcript.

    Per-turn proposals are state/relationship only — this adds session-level
    "what happened" events so a closed conversation leaves a narrative trace
    CanonKeeper can review and canonize. Best-effort: extraction failures
    never block session close.
    """
    turns = [t for t in state.turns if t.get("text")]
    if len(turns) < 2 or not state.npc_ids:
        return []
    try:
        import anyio

        from monitor_agents.extraction.memory_extraction import MemoryExtractor

        npc_name = (state.npc_contexts.get(str(state.npc_ids[0])) or {}).get("name", "the character")
        transcript = "\n".join(
            f"{t.get('entity_name') or t.get('speaker_role', '?')}: {t['text']}" for t in turns[-30:]
        )[:8000]
        extractor = MemoryExtractor()
        memories = await anyio.to_thread.run_sync(extractor.forward, transcript, "conversation", npc_name)
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _extract_episodic_memories)
        logger.warning("episodic memory extraction failed", exc_info=True)
        return []

    proposals: list[dict[str, Any]] = []
    for m in memories[:5]:
        text = str(m.get("text") or "").strip()
        if not text:
            continue
        try:
            importance = min(1.0, max(0.0, float(m.get("importance", 5) or 5) / 10))
        except (TypeError, ValueError):
            importance = 0.5
        proposals.append(
            {
                "change_type": "event",
                "content": {
                    "description": text,
                    "entity_id": str(state.npc_ids[0]),
                    "importance": importance,
                    "emotional_valence": m.get("emotional_valence", 0.0),
                    "source": "episodic_extraction",
                },
                "confidence": 0.6,
                "proposer": "NPCVoice",
            }
        )
    return proposals


async def _stage_proposal(agent: Any, state: ConversationState, proposal: dict[str, Any]) -> bool:
    """Stage one proposal as a ProposedChange document. Returns success.

    Stamps scene/story/universe scope and conversation evidence; failures
    are logged and swallowed so one bad proposal never blocks the rest.
    """
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
        return True
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _stage_proposal)
        logger.warning(
            "Failed to stage proposal for conversation %s",
            state.conversation_id,
            exc_info=True,
        )
        return False


async def redistill_episodic_proposals(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Re-run episodic extraction for a persisted conversation doc and stage
    the resulting event proposals.

    The transcript in MongoDB is the durable record; episodic proposals are
    derived from it, so they can always be rebuilt — e.g. after a close-time
    LLM failure. Returns the staged proposals (empty when nothing salient).
    """
    from monitor_agents.npc_voice.agent import NPCVoice

    npc_ids = [UUID(n) for n in (doc.get("npc_ids") or [])]
    state = ConversationState(
        conversation_id=UUID(doc["conversation_id"]),
        universe_id=UUID(doc["universe_id"]),
        mode=ConversationMode(doc.get("mode", ConversationMode.DIRECT.value)),
        npc_ids=npc_ids,
        turns=[
            {
                "turn_index": t.get("turn_index", i),
                "speaker_role": t.get("speaker_role"),
                "entity_name": t.get("entity_name"),
                "text": t.get("text", ""),
            }
            for i, t in enumerate(doc.get("turns", []))
        ],
    )

    proposals = await _extract_episodic_memories(state)
    if not proposals:
        return []

    agent = NPCVoice()
    staged: list[dict[str, Any]] = []
    for proposal in proposals:
        if await _stage_proposal(agent, state, proposal):
            staged.append(proposal)
    return staged


async def close_session(state: ConversationState) -> dict[str, Any]:
    """
    Stage any accumulated proposals as ProposedChange documents, then mark
    the ConversationSession as completed in MongoDB.

    Proposals are staged BEFORE marking the conversation completed so that a
    staging failure leaves the session active and recoverable on retry.

    Write: proposals → MongoDB; session status → MongoDB.
    """
    from monitor_agents.npc_voice.agent import NPCVoice

    agent = NPCVoice()

    # Safety net: memory writes deferred for streaming are flushed before the
    # session closes, so an unstreamed close still leaves the recall intact.
    # Cleared only after a successful flush — a failure keeps them buffered
    # (retry beats silent loss) and propagates.
    if state.deferred_memory_writes:
        await _flush_memory_writes(list(state.deferred_memory_writes))
        state.deferred_memory_writes = []

    if state.stage_canon_proposals:
        # Distill session-level episodic memories and stage them alongside the
        # per-turn state/relationship proposals.
        proposals_to_stage = list(state.pending_proposals) + await _extract_episodic_memories(state)

        # Stage proposals for CanonKeeper BEFORE marking completed so failures
        # remain recoverable via resume_conversation / end_conversation.
        unstaged: list[dict[str, Any]] = []
        for proposal in proposals_to_stage:
            if not await _stage_proposal(agent, state, proposal):
                unstaged.append(proposal)

        if unstaged:
            state.pending_proposals = unstaged
            raise RuntimeError(f"Failed to stage {len(unstaged)} proposal(s) for conversation {state.conversation_id}")
    else:
        # Light preset: no canonization — nothing is staged for review.
        proposals_to_stage = []

    # Mark session complete only after all proposals have been safely staged.
    await agent.call_tool(
        "mongodb_update_conversation",
        {
            "conversation_id": str(state.conversation_id),
            "params": {"status": ConversationStatus.COMPLETED.value},
        },
    )

    return {"pending_proposals": proposals_to_stage, "is_complete": True}


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
        lorebook_character_ids: list[str] | None = None,
        player_persona: str | None = None,
        character_card: str | None = None,
        player_name: str | None = None,
        preset: str | LightPreset | None = None,
        owner_id: str | UUID | None = None,
    ) -> None:
        resolved = get_preset(preset) if isinstance(preset, str) else preset
        self.owner_id = str(owner_id) if owner_id is not None else None
        self.state = ConversationState(
            conversation_id=conversation_id,
            universe_id=universe_id,
            mode=mode,
            owner_id=self.owner_id,
            npc_ids=npc_ids,
            scene_id=scene_id,
            story_id=story_id,
            player_entity_id=player_entity_id,
            lorebook_character_ids=lorebook_character_ids or [],
            player_persona=player_persona or "",
            character_card=character_card or "",
            player_name=player_name or "",
            preset_name=resolved.name if resolved else "",
            model_tier=resolved.model_tier if resolved else "light",
            stage_canon_proposals=True if resolved is None else resolved.stage_canon_proposals,
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
        lorebook_character_ids: list[str] | None = None,
        player_persona: str | None = None,
        character_card: str | None = None,
        player_name: str | None = None,
        preset: str | LightPreset | None = None,
        owner_id: str | UUID | None = None,
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
            lorebook_character_ids=lorebook_character_ids or [],
            player_persona=player_persona,
            character_card=character_card,
            player_name=player_name,
            preset=preset,
            owner_id=owner_id,
        )
        # Run open_session + load_npc_context nodes
        with owner_scope(loop.owner_id):
            result = await loop._graph.ainvoke(loop.state.model_dump())
            loop.state = ConversationState(**{**loop.state.model_dump(), **result})
        return loop

    @owner_scoped
    async def add_opening(self, text: str) -> None:
        """Record the character's greeting, so they know what they said first."""
        from monitor_agents.npc_voice.agent import NPCVoice

        npc_id = self.state.npc_ids[0]
        npc_name = self.state.npc_contexts.get(str(npc_id), {}).get("name", str(npc_id))
        await NPCVoice().call_tool(
            "mongodb_append_conversation_turn",
            {
                "conversation_id": str(self.state.conversation_id),
                "params": {
                    "speaker_role": "npc",
                    "entity_id": str(npc_id),
                    "entity_name": npc_name,
                    "text": text,
                    "emotional_state": None,
                },
            },
        )
        self.state.turns = [
            *self.state.turns,
            {
                "turn_index": len(self.state.turns),
                "speaker_role": "npc",
                "entity_id": str(npc_id),
                "entity_name": npc_name,
                "text": text,
            },
        ]

    @owner_scoped
    async def step(self, player_input: str, *, defer_memory_writes: bool = False) -> list[dict[str, Any]]:
        """
        Process one player input → return list of NPC responses.

        Drives the mid-session nodes directly. The compiled graph has a single
        fixed entry point (open_session), so re-invoking it per turn would only
        re-run the setup flow and never reach response generation — hence we
        run process_player_turn → generate_npc_responses explicitly here.

        Args:
            player_input: What the player said / asked.
            defer_memory_writes: When True, this turn's NPC memory writes are
                buffered instead of executed; the caller MUST call
                ``flush_memory_writes()`` after the reply has finished
                streaming (Phase 7: memory writes happen after the stream).

        Returns:
            List of dicts: [{npc_name, text, emotional_state?, canon_insight?}]
        """
        if self._closed or self.state.is_complete or self.state.turns_count >= self.state.max_turns:
            raise ConversationClosedError(f"Conversation {self.state.conversation_id} is already closed")

        prior_turns = list(self.state.turns)
        self.state.current_player_input = player_input
        self.state.defer_memory_writes = defer_memory_writes

        try:
            self._apply(await process_player_turn(self.state))
            self._apply(await generate_npc_responses(self.state))
        except Exception:
            self.state.turns = prior_turns
            self.state.current_player_input = None
            raise
        finally:
            self.state.defer_memory_writes = False

        if not defer_memory_writes:
            await self.flush_memory_writes()

        # Honor the loop's own ceiling (max_turns / explicit completion).
        if route_after_npc_response(self.state) == "close" and not self._closed:
            self._apply(await close_session(self.state))
            self._closed = True

        return self.state.current_npc_responses

    @owner_scoped
    async def flush_memory_writes(self) -> int:
        """Execute buffered NPC memory writes through the real NPCVoice.

        Returns the number of writes flushed. Called by streaming send paths
        after the reply's stream completes; ``close_session`` also flushes any
        leftovers as a safety net. The buffer is cleared only after a
        successful flush — a failure keeps the writes for a retry instead of
        silently dropping them.
        """
        if not self.state.deferred_memory_writes:
            return 0
        calls = list(self.state.deferred_memory_writes)
        flushed = await _flush_memory_writes(calls)
        self.state.deferred_memory_writes = []
        return flushed

    @owner_scoped
    async def finish(self) -> list[dict[str, Any]]:
        """
        Close the session and stage all accumulated proposals.

        Returns:
            Staged proposals list (for caller to display or confirm).
        """
        if not self._closed:
            self._apply(await close_session(self.state))
            self._closed = True
        self.state.is_complete = True
        return self.state.pending_proposals
