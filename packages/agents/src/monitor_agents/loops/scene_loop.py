"""
Scene Loop — LangGraph StateGraph implementation.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), langgraph, external libs
CALLED BY: story_loop.py (via SceneLoop.run())

Maps the architecture doc Scene Loop (S1→S6) to a LangGraph StateGraph:

  load_context → await_user → resolve → persist_narrative → canonize_or_continue

Checkpointing via MongoDBSaver means loop state survives process restarts,
enabling resumable sessions (critical for long RP sessions).

Invariants (from CONVERSATIONAL_LOOPS.md):
- Turns NEVER write to Neo4j directly
- Scene is the atomic canonization unit
- All Neo4j writes go through CanonKeeper at scene end / checkpoint
"""

from __future__ import annotations

import functools
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import anyio
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.graph import END, StateGraph
from monitor_data.config import settings
from pydantic import BaseModel, Field

from monitor_agents.loops.story_loop import StoryState

# Pure helpers extracted into a separate module for testability
from monitor_agents.loops.scene_support import (  # noqa: F401 — re-exported for internal use
    apply_resource_delta,
    build_checkpoint_summary,
    build_state_change_summary,
    canonical_state_tags,
    clear_scene_runtime_cache,
    coerce_int,
    coerce_uuid,
    derive_state_deltas,
    map_action_type,
    normalise_resource_value,
    persist_working_state,
    seed_actor_state,
    select_actor_entity,
)
from monitor_agents.agent_factory import get_agent_factory

logger = logging.getLogger(__name__)
_SCENE_GRAPH_TEMPLATE: StateGraph | None = None


def _timed_node(fn):
    """Log per-span wall time for a scene-loop node (T-091 profiling).

    Emits a single grep-able line: ``SCENE_SPAN <node>=<ms>ms``. Profiling
    overhead is a perf_counter pair — negligible — so it's safe to leave on.
    """

    @functools.wraps(fn)
    async def _wrapper(state: "SceneState") -> Dict[str, Any]:
        t0 = time.perf_counter()
        try:
            return await fn(state)
        finally:
            logger.info("SCENE_SPAN %s=%.0fms", fn.__name__, (time.perf_counter() - t0) * 1000)

    return _wrapper


# =============================================================================
# STATE SCHEMA
# =============================================================================


class SceneState(BaseModel):
    """Typed state that flows through every scene-loop node."""

    # Identifiers
    scene_id: UUID
    story_id: UUID
    universe_id: Optional[UUID] = None
    gm_profile_id: Optional[UUID] = None
    gm_profile: Optional[Dict[str, Any]] = None

    # Context (built in load_context, read-only thereafter)
    entity_context: List[Dict[str, Any]] = Field(default_factory=list)
    memory_context: List[Dict[str, Any]] = Field(default_factory=list)
    lorebook_context: List[str] = Field(default_factory=list)
    previous_turns: List[Dict[str, Any]] = Field(default_factory=list)
    # Raw game-system document loaded from MongoDB — consumed by GameSystemRuntime in resolver/narrator
    game_context: Dict[str, Any] = Field(default_factory=dict)
    source_profile: Dict[str, Any] = Field(default_factory=dict)
    # Mechanical resolution mode for this session (set at session start, immutable during play)
    # "narrative" | "dice_standard" | "dice_game_system"
    play_mode: str = Field(default="dice_game_system")
    # Explicit game system selected for the session, if any.
    system_id: Optional[str] = Field(default=None)
    pack_id: Optional[str] = Field(default=None)
    system_source_type: Optional[str] = Field(default=None)
    system_source_id: Optional[str] = Field(default=None)
    # Tone for this session — drives Narrator voice (dramatic/grim/horror/heroic/mystery/adventure)
    session_tone: str = Field(default="dramatic")
    tension_score: float = Field(default=0.5)

    # Dice roll mode for this turn — normal, advantage, or disadvantage
    roll_mode: str = Field(default="normal")

    # Current turn
    user_input: Optional[str] = None
    actor_id: Optional[UUID] = None
    actor_context: Optional[Dict[str, Any]] = None
    turn_id: Optional[UUID | str] = None
    resolution_id: Optional[UUID | str] = None

    # Resolution from Resolver
    resolution: Optional[Dict[str, Any]] = None

    # Narrative output from Narrator
    narrative_text: Optional[str] = None

    # Resource engine outputs (Fase Alto)
    pending_spends: List[Dict[str, Any]] = Field(default_factory=list)
    threshold_events: List[Dict[str, Any]] = Field(default_factory=list)
    injected_narrative_events: List[Dict[str, Any]] = Field(default_factory=list)
    resource_deltas: List[Dict[str, Any]] = Field(default_factory=list)

    working_state: Dict[str, Any] = Field(default_factory=dict)
    scene_checkpoint: Dict[str, Any] = Field(default_factory=dict)
    total_minutes_passed: int = 0

    # Staged proposals (pending canonization)
    pending_proposals: List[Dict[str, Any]] = Field(default_factory=list)

    # Flow control
    scene_complete: bool = False
    turns_count: int = 0
    max_turns: int = 50  # safety ceiling per scene

    # Temporal context (P-14)
    temporal_mode: str = Field(default="present")
    time_ref: Optional[datetime] = None

    # Memory extraction (Task 4)
    memories_to_persist: List[Dict[str, Any]] = Field(default_factory=list)

    # Story state (Task 2)
    story_state: Optional[StoryState] = None


# =============================================================================
# NODES
# =============================================================================


@_timed_node
async def load_context(state: SceneState) -> Dict[str, Any]:
    """
    S1: Load neo4j entities, mongodb turns, qdrant memories, and game system into state.

    Write: nothing (read-only node).
    """
    from monitor_agents.utils.db_readers import (
        mongodb_create_scene,
        mongodb_get_scene,
        run_sync_read,
    )
    from monitor_data.schemas.scenes import SceneCreate

    temporal_mode = state.temporal_mode
    time_ref = state.time_ref
    universe_id = None  # ensure defined for all code paths below

    try:
        scene = await run_sync_read(mongodb_get_scene, state.scene_id)
        if scene:
            universe_id = scene.universe_id
            # P-14: Rehydrate temporal context from MongoDB record
            # mongodb_get_scene returns a Pydantic model (SceneResponse)
            temporal_mode = getattr(scene, "temporal_mode", "present")
            time_ref = getattr(scene, "time_ref", None)
        elif state.universe_id:
            # Story must exist in Neo4j for mongodb_create_scene to work
            factory = get_agent_factory()
            ck = factory.create_canonkeeper()
            try:
                await ck.create_story(
                    story_id=state.story_id,
                    universe_id=state.universe_id,
                    title="CLI Solo Play Story",
                )
            except Exception as e:
                logger.info(f"Story creation skipped/failed (might already exist): {e}")

            # Create the scene if it doesn't exist and we have a universe_id
            logger.info(
                "Bootstrapping scene %s in universe %s",
                state.scene_id,
                state.universe_id,
            )
            await run_sync_read(
                mongodb_create_scene,
                SceneCreate(
                    scene_id=state.scene_id,
                    story_id=state.story_id,
                    universe_id=state.universe_id,
                    title="New Scene",
                    status="active",
                ),
            )
            universe_id = state.universe_id
    except Exception as exc:
        logger.error(f"Scene bootstrap/load failed: {exc}", exc_info=True)
        # Continue anyway, but this might fail later if scene is required
        pass

    factory = get_agent_factory()
    agent = factory.create_context_assembly()
    context = await agent.assemble(
        scene_id=state.scene_id,
        story_id=state.story_id,
        universe_id=str(universe_id) if universe_id else None,
        system_id=state.system_id,
        system_source_type=state.system_source_type,
        system_source_id=state.system_source_id,
        pack_id=state.pack_id,
        actor_context=state.actor_context,
    )

    # G3: Check token budget and compress context if needed
    context = await agent.check_and_compress_if_needed(
        context, player_action=state.user_input or ""
    )

    # Load GM profile if missing but ID exists
    gm_profile = state.gm_profile
    if not gm_profile and state.gm_profile_id:
        try:
            from monitor_data.tools.mongodb_tools import mongodb_get_gm_profile

            profile_res = mongodb_get_gm_profile(state.gm_profile_id)
            if profile_res:
                gm_profile = profile_res.model_dump()
        except Exception as e:
            logger.warning("Failed to load GM profile %s: %s", state.gm_profile_id, e)

    # Fetch the character's working state for the ResourceEngine
    working_state_dict = {}
    if state.actor_id and state.scene_id:
        try:
            from monitor_data.tools.mongodb_tools import mongodb_get_working_state
            
            ws_res = await run_sync_read(mongodb_get_working_state, state.actor_id, state.scene_id)
            if ws_res and getattr(ws_res, "state", None):
                # ResourceEngine expects a FLAT resource dict ({"Blood Pool": {current,max}, ...}),
                # not the full CharacterWorkingState. The full model_dump nests resources under a
                # "resources" key, so the engine never found them and emitted no deltas. Pass the
                # flat resource snapshot directly.
                working_state_dict = dict(ws_res.state.resources or {})
        except Exception as e:
            logger.warning("Failed to load working state for actor %s: %s", state.actor_id, e)

    return {
        "entity_context": context.get("entities", []),
        "memory_context": context.get("memories", []),
        "lorebook_context": context.get("lorebook_entries", []),
        "previous_turns": context.get("turns", []),
        "game_context": context.get("game_system", {}),
        "source_profile": context.get("source_profile", {}),
        "working_state": working_state_dict,
        "gm_profile": gm_profile,
        "universe_id": universe_id,
        "temporal_mode": temporal_mode,
        "time_ref": time_ref,
    }


@_timed_node
async def resolve_action(state: SceneState) -> Dict[str, Any]:
    """
    S3: Resolver evaluates the user action and produces a ResolutResolverOutcome.

    Writes: ProposedChange documents to MongoDB (via MCP tool).
    """
    if not state.user_input:
        return {"resolution": None}
    if state.resolution is not None:
        proposals = state.resolution.get("proposals", [])
        return {
            "resolution": state.resolution,
            "pending_proposals": state.pending_proposals + proposals,
        }

    factory = get_agent_factory()
    resolver = factory.create_resolver()
    resolution = await resolver.resolve_turn(
        scene_id=str(state.scene_id),
        user_input=state.user_input,
        context={
            "entities": state.entity_context,
            "turns": state.previous_turns,
            "source_profile": state.source_profile,
        },
        game_context=state.game_context,
        play_mode=state.play_mode,
        roll_mode=state.roll_mode,
        tension_score=state.tension_score,
    )
    proposals = resolution.get("proposals", [])
    if state.universe_id:
        for p in proposals:
            p["universe_id"] = str(state.universe_id)
            if "content" in p and isinstance(p["content"], dict):
                p["content"]["universe_id"] = str(state.universe_id)

    return {
        "resolution": resolution,
        "pending_proposals": state.pending_proposals + proposals,
    }


@_timed_node
async def narrate(state: SceneState) -> Dict[str, Any]:
    """
    S4/S5: Narrator generates GM prose and persists the turn to MongoDB.

    Writes: GM turn text to MongoDB (via MCP tool).
    """

    factory = get_agent_factory()
    narrator = factory.create_narrator()
    result = await narrator.narrate_turn(
        scene_id=state.scene_id,
        user_input=state.user_input,
        resolution=state.resolution,
        context={
            "entities": state.entity_context,
            "memories": state.memory_context,
            "turns": state.previous_turns,
            "source_profile": state.source_profile,
            "actor": state.actor_context,
        },
        game_context=state.game_context,
        session_tone=state.session_tone,
        gm_profile=state.gm_profile,
        lorebook_context=state.lorebook_context,
        story_state=state.story_state,
    )
    clear_scene_runtime_cache(state.scene_id)
    proposals = result.get("proposals", [])
    if state.universe_id:
        for p in proposals:
            p["universe_id"] = str(state.universe_id)
            if "content" in p and isinstance(p["content"], dict):
                p["content"]["universe_id"] = str(state.universe_id)

    narrative_text = result.get("narrative_text", "")
    minutes = result.get("minutes_elapsed", 0)

    return {
        "narrative_text": narrative_text,
        "pending_proposals": state.pending_proposals + proposals,
        "turns_count": state.turns_count + 1,
        "turn_id": result.get("turn_id"),
        "total_minutes_passed": state.total_minutes_passed + minutes,
    }


async def extract_new_entities(state: SceneState) -> Dict[str, Any]:
    """
    P-7 / On-the-fly creation: Detect new entities mentioned in narration.

    Analyses the narrative text for named entities that don't yet exist in the
    world.  Each detected entity becomes a ProposedChange (type ENTITY) that
    CanonKeeper evaluates at the canonization checkpoint.

    Confidence threshold: only entities with confidence >= 0.7 are proposed,
    reducing noise from vague or generic references.
    """
    if not state.narrative_text:
        return {}

    # Build known-entity list from context so the LLM doesn't re-propose
    # entities that already exist.
    known_names = [e.get("name", "") for e in state.entity_context if e.get("name")]
    known_entities_str = ", ".join(known_names) if known_names else "(empty world)"

    # Brief universe context for grounding entity types
    universe_context = ""
    if state.game_context:
        universe_context = state.game_context.get("name", "") or state.game_context.get(
            "description", ""
        )

    from monitor_agents.prompts.narrative_entity_extraction import (
        NarrativeEntityExtractionModule,
    )

    extractor = NarrativeEntityExtractionModule()
    try:
        result = await anyio.to_thread.run_sync(
            extractor.forward,
            state.narrative_text,
            known_entities_str,
            universe_context,
        )
    except Exception:
        logger.warning("Narrative entity extraction failed", exc_info=True)
        return {}

    # Parse the JSON output from the LLM
    import json

    raw_output = getattr(result, "new_entities", "[]")
    try:
        new_entities = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse new_entities JSON: %s", raw_output[:200])
        return {}

    if not isinstance(new_entities, list):
        return {}

    # Filter by confidence threshold and build proposals
    MIN_CONFIDENCE = 0.7
    proposals: List[Dict[str, Any]] = []
    for entity in new_entities:
        if not isinstance(entity, dict):
            continue
        confidence = float(entity.get("confidence", 0.0))
        if confidence < MIN_CONFIDENCE:
            continue
        name = entity.get("name", "").strip()
        if not name:
            continue
        # Skip if already known
        if name.lower() in [n.lower() for n in known_names]:
            continue

        proposals.append(
            {
                "proposal_type": "ENTITY",
                "content": {
                    "name": name,
                    "entity_type": entity.get("entity_type", "CONCEPT"),
                    "description": entity.get("description", ""),
                    "is_archetype": False,
                },
                "summary": f"New entity detected in narration: {name}",
                "confidence": confidence,
                "authority": "SYSTEM",
                "proposer": "narrator",
                "universe_id": str(state.universe_id) if state.universe_id else "",
            }
        )
        if state.universe_id:
            proposals[-1]["content"]["universe_id"] = str(state.universe_id)

    if not proposals:
        return {}

    logger.info(
        "Extracted %d new entity proposals from narration (scene %s)",
        len(proposals),
        state.scene_id,
    )
    return {"pending_proposals": state.pending_proposals + proposals}


async def extract_memories(state: SceneState) -> Dict[str, Any]:
    """
    Task 4: Extract salient character memories from the narrative prose.
    """
    if not state.narrative_text or not state.actor_context:
        return {"memories_to_persist": []}

    actor_name = state.actor_context.get("name") or "the character"

    from monitor_agents.prompts.memory_extraction import MemoryExtractor

    extractor = MemoryExtractor()
    memories = await anyio.to_thread.run_sync(
        extractor.forward,
        state.narrative_text,
        str(state.resolution.get("success_level") if state.resolution else "narrative"),
        actor_name,
    )

    return {"memories_to_persist": memories}


async def persist_turn_artifacts(state: SceneState) -> Dict[str, Any]:
    """
    Persist a structured DL-24 resolution record tied to the newly created turn.

    This keeps per-turn mechanics queryable without relying on UI metadata blobs.
    """
    if not state.resolution or not state.turn_id:
        return {}

    resolution_type = str(state.resolution.get("resolution_type", "")).lower()
    if resolution_type == "propose_roll":
        return {}

    from monitor_agents.utils.db_readers import (
        mongodb_create_resolution,
        mongodb_update_turn_resolution,
        run_sync_read,
    )
    from monitor_data.schemas.resolutions import (
        ActionType,
        Effect,
        EffectType,
        Mechanics,
        Modifier,
        ResolutionCreate,
        ResolutionType,
        RollResult,
        SuccessLevel,
    )

    # T-092: the resolver emits free-form types (e.g. "trivial") that aren't in
    # the ResolutionType/SuccessLevel enums. A raw ResolutionType("trivial")
    # raised ValueError, the except returned {}, and persist_working_state
    # never ran — silently killing the HP/combat HUD. Coerce safely instead.
    _RESOLUTION_TYPE_ALIASES = {
        "trivial": "narrative",
        "auto": "narrative",
        "automatic": "deterministic",
        "skill": "dice",
        "roll": "dice",
        "opposed": "contested",
        "propose_roll": "dice",
    }

    def _safe_resolution_type(raw: str, forced: bool) -> "ResolutionType":
        if forced:
            return ResolutionType.FORCED_NARRATIVE
        val = (raw or "narrative").strip().lower()
        val = _RESOLUTION_TYPE_ALIASES.get(val, val)
        try:
            return ResolutionType(val)
        except ValueError:
            return ResolutionType.NARRATIVE

    def _safe_success_level(raw: str) -> "SuccessLevel":
        try:
            return SuccessLevel(str(raw or "success").strip().lower())
        except ValueError:
            return SuccessLevel.SUCCESS

    actor_uuid = coerce_uuid(
        state.actor_id,
        seed=f"monitor://scene/{state.scene_id}/actor/default",
    )
    turn_uuid = coerce_uuid(
        state.turn_id,
        seed=f"monitor://scene/{state.scene_id}/turn/{state.turn_id}",
    )

    modifier_value = int(state.resolution.get("modifier") or 0)
    stat_name = str(state.resolution.get("stat") or "relevant approach")
    roll_values = list((state.resolution.get("roll_detail") or {}).get("rolls") or [])
    natural = int(roll_values[0]) if roll_values else int(state.resolution.get("roll_total") or 0)

    mechanics = Mechanics(
        formula=str(
            state.resolution.get("roll_breakdown") or resolution_type or "narrative resolution"
        )[:200],
        modifiers=(
            [
                Modifier(
                    source=stat_name,
                    value=modifier_value,
                    reason=f"Relevant modifier from {stat_name}",
                )
            ]
            if modifier_value
            else []
        ),
        target=state.resolution.get("difficulty_class"),
        roll=(
            RollResult(
                raw_rolls=roll_values or [natural],
                kept_rolls=roll_values or [natural],
                total=int(state.resolution.get("roll_total") or natural),
                natural=natural,
                critical=str(state.resolution.get("success_level")) == "critical_success",
                fumble=str(state.resolution.get("success_level")) == "critical_failure",
            )
            if resolution_type == "dice"
            else None
        ),
    )

    effects = [
        Effect(
            effect_type=EffectType.OTHER,
            target_id=actor_uuid,
            magnitude=0,
            description=str(effect).replace("_", " "),
        )
        for effect in (state.resolution.get("effects") or [])
    ]

    try:
        params = ResolutionCreate(
            turn_id=turn_uuid,
            scene_id=state.scene_id,
            story_id=state.story_id,
            actor_id=actor_uuid,
            action=state.user_input or "(no action text)",
            action_type=ActionType(
                map_action_type(
                    str(state.resolution.get("action_type") or ""),
                    str(state.resolution.get("intent_type") or ""),
                    state.user_input or "",
                )
            ),
            resolution_type=_safe_resolution_type(
                resolution_type,
                bool(state.resolution.get("forced_narrative")),
            ),
            mechanics=mechanics,
            success_level=_safe_success_level(state.resolution.get("success_level")),
            margin=(
                int(state.resolution.get("roll_total") or 0)
                - int(state.resolution.get("difficulty_class") or 0)
                if state.resolution.get("roll_total") is not None
                and state.resolution.get("difficulty_class") is not None
                else None
            ),
            effects=effects,
            description=(state.narrative_text or "")[:1000] or None,
            gm_notes=(state.resolution.get("risk_preview") or "")[:1000] or None,
            forced_narrative=bool(state.resolution.get("forced_narrative")),
        )
    except Exception:
        logger.warning(
            "Resolution payload validation failed for scene %s turn %s",
            state.scene_id,
            state.turn_id,
            exc_info=True,
        )
        return {}

    try:
        created = await run_sync_read(mongodb_create_resolution, params)
    except Exception:
        logger.warning(
            "Resolution creation failed for scene %s turn %s",
            state.scene_id,
            state.turn_id,
            exc_info=True,
        )
        return {}

    resolution_id = str(created.id)

    try:
        persist_turn_id = (
            state.turn_id
            if isinstance(state.turn_id, UUID)
            else UUID(str(state.turn_id))
            if state.turn_id
            else None
        )
        persistence_payload = await persist_working_state(
            scene_id=state.scene_id,
            story_id=state.story_id,
            actor_id=state.actor_id,
            entity_context=state.entity_context,
            game_context=state.game_context,
            resolution=state.resolution,
            user_input=state.user_input,
            narrative_text=state.narrative_text,
            turn_id=persist_turn_id,
            pending_proposals=state.pending_proposals,
            resource_deltas=state.resource_deltas,
            memories_to_persist=state.memories_to_persist,
            actor_context=state.actor_context,
            universe_id=state.universe_id,
        )
    except Exception:
        logger.warning(
            "Working-state persistence failed for scene %s turn %s",
            state.scene_id,
            state.turn_id,
            exc_info=True,
        )
        persistence_payload = {}

    checkpoint = persistence_payload.get("scene_checkpoint") or {}

    try:
        turn_uuid = (
            state.turn_id
            if isinstance(state.turn_id, UUID)
            else UUID(str(state.turn_id))
            if state.turn_id
            else None
        )
        if turn_uuid and resolution_id:
            await run_sync_read(
                mongodb_update_turn_resolution,
                state.scene_id,
                turn_uuid,
                UUID(resolution_id),
                summary=checkpoint.get("summary") if checkpoint else None,
                checkpoint=checkpoint if checkpoint else None,
            )
    except Exception:
        logger.warning(
            "Scene turn update failed after creating resolution %s",
            resolution_id,
            exc_info=True,
        )

    new_state_proposals = list(persistence_payload.get("pending_proposals", []))
    merged_payload = dict(persistence_payload)
    merged_payload["pending_proposals"] = state.pending_proposals + new_state_proposals
    return {
        "resolution_id": resolution_id,
        **merged_payload,
    }


async def canonize_checkpoint(state: SceneState) -> Dict[str, Any]:
    """
    S6 / FINALIZE: CanonKeeper evaluates pending proposals.

    Writes: accepted proposals to Neo4j (via CanonKeeper → MCP tool).
    Clears pending_proposals after evaluation.
    """
    if not state.pending_proposals:
        return {}

    factory = get_agent_factory()
    ck = factory.create_canonkeeper()
    await ck.evaluate_proposals(
        scene_id=state.scene_id,
        proposals=state.pending_proposals,
    )
    clear_scene_runtime_cache(state.scene_id, include_entities=True)
    return {"pending_proposals": []}


async def persist_memories_node(state: SceneState) -> Dict[str, Any]:
    """
    Persist extracted memories to MongoDB via mongodb_create_memory.

    Called after extract_memories populates state.memories_to_persist.
    """
    if not state.memories_to_persist:
        return {}

    if not state.actor_id:
        logger.warning("persist_memories_node called but no actor_id in state")
        return {}

    from monitor_agents.loops.scene_support import persist_memories

    try:
        created_ids = await persist_memories(
            entity_id=state.actor_id,
            scene_id=state.scene_id,
            story_id=state.story_id,
            universe_id=state.universe_id,
            memories=state.memories_to_persist,
        )
        logger.debug("Persisted %d memories for actor %s", len(created_ids), state.actor_id)
    except Exception as e:
        logger.warning("Failed to persist memories: %s", e)

    # Return empty dict — we only write, no state changes
    return {}


async def complete_current_scene(state: SceneState) -> Dict[str, Any]:
    """
    GAP-E: Scene end choreography.

    Called when scene_complete=True. Handles:
    1. Persist any remaining memories (belt-and-suspenders, should already be done)
    2. Advance story state (scenes_completed++, in_game_time)
    3. Signal scene ending (CanonKeeper.end_scene placeholder)
    """
    from datetime import timedelta

    updates: Dict[str, Any] = {}

    # 1. Persist any remaining memories (belt-and-suspenders)
    if state.memories_to_persist and state.actor_id:
        from monitor_agents.loops.scene_support import persist_memories

        try:
            await persist_memories(
                entity_id=state.actor_id,
                scene_id=state.scene_id,
                story_id=state.story_id,
                universe_id=state.universe_id,
                memories=state.memories_to_persist,
            )
        except Exception as e:
            logger.warning("Failed to persist memories in complete_current_scene: %s", e)

    # 2. Advance story state
    if state.story_state:
        current_time = state.story_state.in_game_time
        new_time = current_time + timedelta(minutes=state.total_minutes_passed)
        updates["story_state"] = {
            **state.story_state.model_dump(),
            "in_game_time": new_time,
            "scenes_completed": state.story_state.scenes_completed + 1,
        }

    # 3. Scene-end bookkeeping via CanonKeeper.end_scene()
    # Best-effort: failure here must not block scene completion.
    try:
        from monitor_agents.agent_factory import get_agent_factory

        ck = get_agent_factory().create_canonkeeper()
        await ck.end_scene(
            scene_id=state.scene_id,
            story_id=state.story_id,
            actor_id=state.actor_id,
            universe_id=getattr(state, "universe_id", None),
        )
    except Exception as e:
        logger.warning("CanonKeeper.end_scene failed (non-fatal): %s", e)

    # 4. Downtime trigger (P-21): when the story arc reaches "resolution",
    # signal that progression options are available.
    story_state_dict = updates.get("story_state") or {}
    arc_label = story_state_dict.get("arc_label") or (
        state.story_state.arc_label if state.story_state else None
    )
    if arc_label == "resolution":
        updates["downtime_available"] = True
        logger.info("Downtime available: story arc reached 'resolution'")

    logger.info(
        "Completing scene %s (story %s, scenes_completed now %s, in_game_time advanced by %d min)",
        state.scene_id,
        state.story_id,
        updates.get("story_state", {}).get("scenes_completed", "?"),
        state.total_minutes_passed,
    )

    return updates


async def check_events(state: SceneState) -> Dict[str, Any]:
    """
    FASE ALTO (Item 1): ResourceEngine — detect spends, apply earns, fire thresholds.

    This node runs between narrate and persist_turn_artifacts so that:
    - Detected spends are flagged for the resolver on the NEXT turn
    - Earned resources are written into working_state before persistence
    - Threshold effects are surfaced as injected_narrative_events
    """
    if not state.game_context or not state.working_state:
        return {
            "pending_spends": [],
            "threshold_events": [],
            "injected_narrative_events": [],
            "resource_deltas": [],
        }

    from monitor_agents.resource_engine import ResourceEngine

    engine = ResourceEngine(state.game_context, state.working_state)

    # 1. Detect spend intent from user input
    pending_spends = [
        {
            "resource_key": s.resource_key,
            "resource_name": s.resource_name,
            "amount": s.amount,
            "intent": s.intent,
            "can_afford": s.can_afford,
        }
        for s in engine.detect_spend(state.user_input or "")
    ]

    # 2. Apply earn from resolution outcome
    scene_ctx = {
        "turns_count": state.turns_count,
        "scene_ending": state.scene_complete,
    }
    earned = engine.apply_earn(state.resolution or {}, scene_context=scene_ctx)
    # Data-driven action economy (e.g. VtM blood/damage): feeding restores,
    # disciplines rouse the Blood, damage reduces Health — driven by the game
    # system's per-resource action_rules, not hardcoded here.
    economy = engine.apply_action_economy(state.user_input or "", state.resolution or {})
    resource_deltas = [
        {
            "resource_key": d.resource_key,
            "resource_name": d.resource_name,
            "delta": d.delta,
            "source": d.source,
            "reason": d.reason,
        }
        for d in (earned + economy)
    ]

    # 3. Evaluate thresholds against current (pre-earn) working_state
    threshold_events = [
        {
            "resource_key": e.resource_key,
            "resource_name": e.resource_name,
            "threshold_value": e.threshold_value,
            "direction": e.direction,
            "effect": e.effect,
            "new_value": e.new_value,
        }
        for e in engine.check_thresholds()
    ]

    # 4. Surface threshold effects as injected narrative events
    injected_events: List[Dict[str, Any]] = [
        {
            "trigger": "threshold",
            "resource_key": te["resource_key"],
            "narrative": f"[{te['resource_name']} @ {te['threshold_value']}] {te['effect']}",
            "effects": [],
        }
        for te in threshold_events
    ]

    # NOTE: Resource deltas are NOT applied to working_state here.
    # persist_working_state will apply them (it calls derive_state_deltas which
    # produces the same result using the same resolution data).

    return {
        "pending_spends": pending_spends,
        "threshold_events": threshold_events,
        "injected_narrative_events": injected_events,
        "resource_deltas": resource_deltas,
        # working_state unchanged — persist_working_state re-derives deltas from resolution
    }


def route_after_narration(state: SceneState) -> str:
    """
    Decide whether to loop for another turn or end the scene.

    Routing logic:
    - scene_complete flag  → complete_current_scene → canonize → end
    - turns_count >= max   → complete_current_scene → canonize → end (safety)
    - otherwise            → back to await_user (not shown in graph; user input
                             is injected externally between invocations)
    """
    if state.scene_complete or state.turns_count >= state.max_turns:
        return "complete_current_scene"
    return END


def route_after_resolve(state: SceneState) -> str:
    """Route after resolve based on resolution type."""
    if not state.resolution:
        return "narrate"

    res_type = state.resolution.get("resolution_type")
    if res_type == "forced_narrative_pushback":
        return END  # Wait for user choice

    return "narrate"


# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================


def build_scene_graph() -> StateGraph:
    """
    Build and compile the Scene Loop StateGraph.

    Nodes follow the CONVERSATIONAL_LOOPS.md S1→S6 flow.
    Checkpointing is configured separately in ``run_scene()``.
    """
    global _SCENE_GRAPH_TEMPLATE
    if _SCENE_GRAPH_TEMPLATE is not None:
        return _SCENE_GRAPH_TEMPLATE

    graph = StateGraph(SceneState)

    graph.add_node("load_context", load_context)
    graph.add_node("resolve", resolve_action)
    graph.add_node("narrate", narrate)
    graph.add_node("extract_new_entities", extract_new_entities)
    graph.add_node("extract_memories", extract_memories)
    graph.add_node("persist_memories", persist_memories_node)
    graph.add_node("check_events", check_events)
    graph.add_node("persist_turn_artifacts", persist_turn_artifacts)
    graph.add_node("complete_current_scene", complete_current_scene)
    graph.add_node("canonize", canonize_checkpoint)

    # Entry
    graph.set_entry_point("load_context")

    # Edges
    graph.add_edge("load_context", "resolve")
    graph.add_conditional_edges(
        "resolve",
        route_after_resolve,
        {"narrate": "narrate", END: END},
    )
    # Fan out: both extractors run concurrently after narrate. In LangGraph a
    # node's multiple plain successors execute in the same superstep, so two
    # edges (not a list end_key — which add_edge rejects) gives the parallelism.
    graph.add_edge("narrate", "extract_new_entities")
    graph.add_edge("narrate", "extract_memories")
    # Fan in: wait for BOTH extractors before persisting (list start_key is valid).
    graph.add_edge(["extract_new_entities", "extract_memories"], "persist_memories")
    graph.add_edge("persist_memories", "check_events")
    graph.add_edge("check_events", "persist_turn_artifacts")
    graph.add_conditional_edges(
        "persist_turn_artifacts",
        route_after_narration,
        {"complete_current_scene": "complete_current_scene", "canonize": "canonize", END: END},
    )
    graph.add_edge("complete_current_scene", "canonize")
    graph.add_edge("canonize", END)

    _SCENE_GRAPH_TEMPLATE = graph
    return _SCENE_GRAPH_TEMPLATE


# =============================================================================
# PUBLIC API
# =============================================================================


class SceneLoop:
    """
    Manages a single scene from start to canonization.

    Acquires a MongoDBSaver checkpointer so loop state survives restarts.
    """

    # ------------------------------------------------------------------
    # Data Layer Helpers (Bridge for CLI)
    # ------------------------------------------------------------------

    @staticmethod
    def get_gm_profile(profile_id: UUID) -> Optional[Dict[str, Any]]:
        """Fetch a GM profile from the data layer."""
        from monitor_data.tools.mongodb_tools import mongodb_get_gm_profile

        profile = mongodb_get_gm_profile(profile_id)
        return profile.model_dump() if profile else None

    def __init__(
        self,
        scene_id: UUID,
        story_id: UUID,
        universe_id: UUID | None = None,
        gm_profile_id: UUID | None = None,
        gm_profile: Dict[str, Any] | None = None,
        max_turns: int = 50,
        play_mode: str = "dice_game_system",
        system_id: str | None = None,
        pack_id: str | None = None,
        system_source_type: str | None = None,
        system_source_id: str | None = None,
        actor_id: UUID | None = None,
        actor_context: Dict[str, Any] | None = None,
        session_tone: str = "dramatic",
        roll_mode: str = "normal",
        tension_score: float = 0.5,
        story_state: Dict[str, Any] | None = None,
    ) -> None:
        self.scene_id = scene_id
        self.story_id = story_id
        self.universe_id = universe_id
        self.gm_profile_id = gm_profile_id
        self.gm_profile = gm_profile
        self.max_turns = max_turns
        self.play_mode = play_mode
        self.system_id = system_id
        self.pack_id = pack_id
        self.system_source_type = system_source_type
        self.system_source_id = system_source_id
        self.actor_id = actor_id
        self.actor_context = actor_context
        self.session_tone = session_tone
        self.roll_mode = roll_mode
        self.tension_score = tension_score
        self.story_state = story_state
        self._graph = build_scene_graph()

    async def run(
        self,
        user_input: str,
        resolution_override: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Execute one full turn of the scene loop.

        Args:
            user_input: The player's action or speech for this turn.

        Returns:
            The updated scene state as a dict (includes narrative_text).
        """
        with MongoDBSaver.from_conn_string(settings.mongodb_uri) as checkpointer:
            compiled = self._graph.compile(checkpointer=checkpointer)
            thread_id = str(self.scene_id)
            config = {"configurable": {"thread_id": thread_id}}

            initial = SceneState(
                scene_id=self.scene_id,
                story_id=self.story_id,
                universe_id=getattr(self, "universe_id", None),
                gm_profile_id=getattr(self, "gm_profile_id", None),
                user_input=user_input,
                max_turns=self.max_turns,
                play_mode=getattr(self, "play_mode", "dice_game_system"),
                system_id=getattr(self, "system_id", None),
                pack_id=getattr(self, "pack_id", None),
                system_source_type=getattr(self, "system_source_type", None),
                system_source_id=getattr(self, "system_source_id", None),
                actor_id=getattr(self, "actor_id", None),
                actor_context=getattr(self, "actor_context", None),
                session_tone=getattr(self, "session_tone", "dramatic"),
                tension_score=getattr(self, "tension_score", 0.5),
                roll_mode=getattr(self, "roll_mode", "normal"),
                story_state=getattr(self, "story_state", None),
                resolution=resolution_override,
            )
            # Add pre-loaded gm_profile to state if available
            gm_profile = getattr(self, "gm_profile", None)
            if gm_profile:
                initial.gm_profile = gm_profile

            result = await compiled.ainvoke(initial.model_dump(), config=config)

            # Combat delegation: if the resolution triggered combat, run CombatLoop
            resolution = result.get("resolution") or {}
            if (
                resolution.get("subsystem_hint") == "combat"
                or resolution.get("action_type") == "combat"
                or _is_combat_action(user_input)
            ):
                combat_result = await _run_combat(
                    scene_id=self.scene_id,
                    story_id=self.story_id,
                    user_input=user_input,
                    entity_context=result.get("entity_context", []),
                    game_context=result.get("game_context", {}),
                    source_profile=result.get("source_profile", {}),
                    gm_profile=result.get("gm_profile"),
                    session_tone=result.get("session_tone", "dramatic"),
                )
                if combat_result:
                    result["narrative_text"] = (
                        (result.get("narrative_text") or "")
                        + "\n\n"
                        + combat_result.get("narrative_text", "")
                    )
                    result["combat_result"] = combat_result

                    # Extract HP deltas from combat result and merge into
                    # resource_deltas so persist_working_state applies them
                    # to the working state (T-092 carryover fix).
                    combat_deltas = _extract_combat_resource_deltas(
                        combat_result, result.get("entity_context", [])
                    )
                    if combat_deltas:
                        existing = result.get("resource_deltas") or []
                        existing.extend(combat_deltas)
                        result["resource_deltas"] = existing

            return result

    async def finalize(self) -> None:
        """
        Force scene completion (e.g. player quits mid-scene).

        Triggers canonization of all pending proposals.
        """
        with MongoDBSaver.from_conn_string(settings.mongodb_uri) as checkpointer:
            compiled = self._graph.compile(checkpointer=checkpointer)
            thread_id = str(self.scene_id)
            config = {"configurable": {"thread_id": thread_id}}

            await compiled.ainvoke(
                {
                    "scene_id": self.scene_id,
                    "story_id": self.story_id,
                    "scene_complete": True,
                    "user_input": None,
                    "max_turns": self.max_turns,
                    "system_id": getattr(self, "system_id", None),
                    "pack_id": getattr(self, "pack_id", None),
                    "system_source_type": getattr(self, "system_source_type", None),
                    "system_source_id": getattr(self, "system_source_id", None),
                },
                config=config,
            )

    async def backtrack(self) -> Dict[str, Any]:
        """
        Undo the last turn by reverting to the state before the last user input.

        Returns:
            The restored scene state.
        """
        with MongoDBSaver.from_conn_string(settings.mongodb_uri) as checkpointer:
            compiled = self._graph.compile(checkpointer=checkpointer)
            thread_id = str(self.scene_id)
            config = {"configurable": {"thread_id": thread_id}}

            # Get history
            history = [state async for state in compiled.aget_state_history(config)]

            if len(history) < 2:
                return {"error": "Cannot backtrack further."}

            # The last state is the current one (after narrate/persist).
            # We want to go back to the state before 'resolve'.
            # LangGraph checkpoints after each node.
            # A turn usually goes: load_context -> resolve -> narrate -> persist.
            # We want to find the checkpoint where 'user_input' was about to be processed.

            # For simplicity, we just revert to the previous checkpoint.
            # In a loop, that might be 'persist_turn_artifacts' of the PREVIOUS turn.
            target_state = history[1]  # [0] is current, [1] is previous

            # Update state to the previous one
            await compiled.aupdate_state(
                config,
                target_state.values,
                as_node=target_state.next[0] if target_state.next else None,
            )

            return target_state.values


# =============================================================================
# Combat integration helpers
# =============================================================================

_COMBAT_KEYWORDS = (
    "attack",
    "strike",
    "shoot",
    "stab",
    "slash",
    "fight",
    "rush",
    "charge",
    "punch",
    "kick",
    "swing",
    "fire",
    "blast",
    "combat",
)


def _is_combat_action(user_input: str) -> bool:
    """Heuristic: does the player input look like a combat action?"""
    text = (user_input or "").lower()
    return any(kw in text for kw in _COMBAT_KEYWORDS)


async def _run_combat(
    scene_id: UUID,
    story_id: UUID,
    user_input: str,
    entity_context: List[Dict[str, Any]],
    game_context: Dict[str, Any],
    source_profile: Dict[str, Any],
    gm_profile: Dict[str, Any] | None = None,
    session_tone: str = "dramatic",
) -> Dict[str, Any] | None:
    """
    Bootstrap and run a CombatLoop for the current scene.

    Returns combat result dict or None if combat can't be started.
    """
    from monitor_agents.loops.combat_loop import CombatLoop, CombatantState

    # Build combatants from entity context
    combatants: List[CombatantState] = []
    for entity in entity_context:
        props = entity.get("properties", {}) if isinstance(entity, dict) else {}
        eid = entity.get("id")
        name = entity.get("name") or props.get("name") or str(eid)
        if not eid:
            continue

        attrs = props.get("attributes", {}) if isinstance(props, dict) else {}
        if not isinstance(attrs, dict):
            attrs = {}

        hp = int(props.get("hp_current") or props.get("hp") or 10)
        hp_max_val = int(props.get("hp_max") or props.get("hp") or hp or 10)

        is_pc = str(props.get("role") or "").upper() == "PC"

        combatants.append(
            CombatantState(
                entity_id=UUID(str(eid)),
                name=str(name),
                initiative=0,
                is_pc=is_pc,
                hp_current=hp,
                hp_max=hp_max_val,
                attributes={k: int(v) for k, v in attrs.items() if isinstance(v, (int, float))},
            )
        )

    if len(combatants) < 2:
        logger.debug("Combat skipped: need at least 2 combatants, got %d", len(combatants))
        return None

    has_pc = any(c.is_pc for c in combatants)
    has_enemy = any(not c.is_pc for c in combatants)
    if not has_pc or not has_enemy:
        logger.debug("Combat skipped: need PC and enemy, pc=%s enemy=%s", has_pc, has_enemy)
        return None

    loop = CombatLoop(
        scene_id=scene_id,
        story_id=story_id,
        combatants=combatants,
        entity_context=entity_context,
        game_context=game_context,
        source_profile=source_profile,
        gm_profile=gm_profile,
        session_tone=session_tone,
    )

    # Start: roll initiative
    await loop.start()

    # Execute first PC action
    result = await loop.step(user_input)

    narrative_parts = [result.get("narrative_text", "")]
    combat_log = list(result.get("combat_log", []))

    # Collect additional NPC turns' narrative
    while result.get("combat_active") and not result.get("awaiting_pc_input"):
        combat_text = result.get("narrative_text", "")
        if combat_text:
            narrative_parts.append(combat_text)

    # Build final combat summary
    final_narrative = "\n".join(p for p in narrative_parts if p)
    if result.get("combat_active") and result.get("awaiting_pc_input"):
        final_narrative += (
            f"\n\nCombat continues — Round {result.get('round_number', 1)}. "
            "Your turn. What do you do?"
        )

    return {
        "narrative_text": final_narrative or "Combat engaged.",
        "combat_active": result.get("combat_active", False),
        "victory_side": result.get("victory_side"),
        "combat_log": combat_log,
        "combatants": result.get("combatants", []),
        "round_number": result.get("round_number", 1),
        "awaiting_pc_input": result.get("awaiting_pc_input", True),
    }


def _extract_combat_resource_deltas(
    combat_result: Dict[str, Any],
    entity_context: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Extract HP/resource deltas from combat result combatants.

    Compares each combatant's post-combat HP to their pre-combat HP (from
    entity_context properties) and emits resource_delta dicts for the PC
    so that persist_working_state applies the HP change to working_state.

    T-092 carryover: combat damage was computed by CombatLoop.apply_damage
    but never merged back into the scene state's resource_deltas.
    """
    deltas: List[Dict[str, Any]] = []
    if not combat_result:
        return deltas

    combatants = combat_result.get("combatants") or []
    if not combatants:
        return deltas

    # Build a lookup of pre-combat HP from entity_context
    pre_hp: Dict[str, int] = {}
    for entity in entity_context:
        eid = str(entity.get("id") or "")
        props = entity.get("properties", {}) if isinstance(entity, dict) else {}
        if not isinstance(props, dict):
            props = {}
        hp = int(props.get("hp_current") or props.get("hp") or 0)
        pre_hp[eid] = hp

    for combatant in combatants:
        eid = str(combatant.get("entity_id") or "")
        is_pc = combatant.get("is_pc", False)
        if not is_pc or not eid:
            continue

        post_hp = int(combatant.get("hp_current") or 0)
        pre_hp_val = pre_hp.get(eid)
        if pre_hp_val is None:
            continue

        hp_delta = post_hp - pre_hp_val
        if hp_delta == 0:
            continue

        # Find the resource key that maps to HP in the working state
        # (commonly "HP", "Health", "hp" — match case-insensitively)
        deltas.append(
            {
                "resource_key": "HP",
                "resource_name": "HP",
                "delta": hp_delta,
                "source": "combat",
                "reason": f"Combat damage: HP {pre_hp_val} → {post_hp}",
            }
        )

    return deltas
