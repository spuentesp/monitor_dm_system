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
from typing import Any
from uuid import UUID

from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.graph import END, StateGraph
from monitor_data.config import settings
from pydantic import BaseModel, Field

from monitor_agents.agent_factory import get_agent_factory

# Pure helpers extracted into a separate module for testability
from monitor_agents.loops.scene_support import (
    coerce_uuid,
    map_action_type,
)
from monitor_agents.services.persistence_service import PersistenceService
from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
from monitor_agents.loops.story_loop import StoryState
from monitor_agents.narrator.agent import compute_pacing
from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource

logger = logging.getLogger(__name__)
_SCENE_GRAPH_TEMPLATE: StateGraph | None = None


def _timed_node(fn):
    """Log per-span wall time for a scene-loop node (T-091 profiling).

    Emits a single grep-able line: ``SCENE_SPAN <node>=<ms>ms``. Profiling
    overhead is a perf_counter pair — negligible — so it's safe to leave on.
    """

    @functools.wraps(fn)
    async def _wrapper(state: SceneState) -> dict[str, Any]:
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
    universe_id: UUID | None = None
    gm_profile_id: UUID | None = None
    gm_profile: dict[str, Any] | None = None

    # Context (built in load_context, read-only thereafter)
    entity_context: list[dict[str, Any]] = Field(default_factory=list)
    memory_context: list[dict[str, Any]] = Field(default_factory=list)
    lorebook_context: list[str] = Field(default_factory=list)
    previous_turns: list[dict[str, Any]] = Field(default_factory=list)
    # Raw game-system document loaded from MongoDB — consumed by GameSystemRuntime in resolver/narrator
    game_context: dict[str, Any] = Field(default_factory=dict)
    source_profile: dict[str, Any] = Field(default_factory=dict)
    # Mechanical resolution mode for this session (set at session start, immutable during play)
    # "narrative" | "dice_standard" | "dice_game_system"
    play_mode: str = Field(default="dice_game_system")
    # Explicit game system selected for the session, if any.
    system_id: str | None = Field(default=None)
    pack_id: str | None = Field(default=None)
    system_source_type: str | None = Field(default=None)
    system_source_id: str | None = Field(default=None)
    # Tone for this session — drives Narrator voice (dramatic/grim/horror/heroic/mystery/adventure)
    session_tone: str = Field(default="dramatic")
    tension_score: float = Field(default=0.5)
    # Deterministic pacing signal (tempo 0..1 + phase). Set in load_context.
    pacing: dict[str, Any] = Field(default_factory=lambda: {"tempo": 0.5, "phase": "setup"})
    # NPC profiles fetched per scene (entity_id -> dict). Rendered by Narrator
    # into the NPC STATE block; never reset across turns.
    npc_profiles: dict[str, Any] = Field(default_factory=dict)
    # Open foreshadowing items for the current scene (loaded in load_context).
    scene_foreshadowing_open: list[dict[str, Any]] = Field(default_factory=list)
    # Optional one-line recap from the previous scene. Rendered once at scene
    # start; cleared after first use.
    opening_recap: str = ""

    # Dice roll mode for this turn — normal, advantage, or disadvantage
    roll_mode: str = Field(default="normal")

    # Current turn
    user_input: str | None = None
    actor_id: UUID | None = None
    actor_context: dict[str, Any] | None = None
    turn_id: UUID | str | None = None
    resolution_id: UUID | str | None = None

    # Resolution from Resolver
    resolution: dict[str, Any] | None = None
    # The GMVerdict that produced this resolution — carries the GM's
    # narrative_draft. The Narrator refines this draft against the
    # outcome; None when GMAgent didn't run (oracle / narrative mode /
    # GMAgent fell through to its seed).
    gm_verdict: Any | None = None

    # Narrative output from Narrator
    narrative_text: str | None = None
    # Set when the Narrator fell back to the GM's raw draft because its
    # own LLM call hit a provider-level failure (rate limit, quota, auth).
    # {"error_class": str, "message": str} or None. Surfaced to the
    # frontend so the player sees why this turn feels flatter than usual.
    degraded: dict[str, Any] | None = None

    # Resource engine outputs (Fase Alto)
    pending_spends: list[dict[str, Any]] = Field(default_factory=list)
    threshold_events: list[dict[str, Any]] = Field(default_factory=list)
    injected_narrative_events: list[dict[str, Any]] = Field(default_factory=list)
    resource_deltas: list[dict[str, Any]] = Field(default_factory=list)

    working_state: dict[str, Any] = Field(default_factory=dict)
    scene_checkpoint: dict[str, Any] = Field(default_factory=dict)
    total_minutes_passed: int = 0

    # Staged proposals (pending canonization)
    pending_proposals: list[dict[str, Any]] = Field(default_factory=list)

    # Flow control
    scene_complete: bool = False
    turns_count: int = 0
    max_turns: int = 50  # safety ceiling per scene

    # Temporal context (P-14)
    temporal_mode: str = Field(default="present")
    time_ref: datetime | None = None

    # Memory extraction (Task 4)
    memories_to_persist: list[dict[str, Any]] = Field(default_factory=list)

    # Story state (Task 2)
    story_state: StoryState | None = None

    # Session-Zero table agreements (lines and veils). Empty lists mean no
    # constraints; the resolver/narrator must still respect them when set.
    agreements_lines: list[str] = Field(default_factory=list)
    agreements_veils: list[str] = Field(default_factory=list)

    # ── Turn Context & Coherence (narrative coherence fixes) ──
    # Deterministic context summary from ContextAssembly._summarise_context.
    # Computed by assemble() but previously discarded by load_context.
    context_summary: str = ""
    # Structured turn context (position, interactables, NPCs, established facts).
    # Built by the build_turn_context node (when available) or None.
    turn_context: dict[str, Any] | None = None
    # Pending roll from a previous turn (propose_roll with success=pending).
    # When set, the resolver must not classify the next action as trivial.
    pending_roll: dict[str, Any] | None = None
    # Optional next-move suggestions from the Narrator (rendered as chips).
    suggested_actions: list[str] = Field(default_factory=list)
    # Established facts extracted from narration (for continuity tracking).
    established_facts: list[str] = Field(default_factory=list)
    # OOC table talk (Q&A pairs) from the session, rendered by the Narrator.
    ooc_exchanges: list[dict[str, Any]] = Field(default_factory=list)
    # Raw recent chat tail (IC + OOC, labeled) rendered by the Narrator.
    recent_chat: list[dict[str, Any]] = Field(default_factory=list)
    # Consistency violations detected by check_consistency node.
    consistency_violations: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# NODES
# =============================================================================


@_timed_node  # type: ignore[untyped-decorator]
async def load_context(state: SceneState) -> dict[str, Any]:
    """
    S1: Load neo4j entities, mongodb turns, qdrant memories, and game system into state.

    Write: nothing (read-only node).
    """
    from monitor_data.schemas.scenes import SceneCreate

    from monitor_agents.utils.db_readers import (
        mongodb_create_scene,
        mongodb_get_scene,
        run_sync_read,
    )

    temporal_mode = state.temporal_mode
    time_ref = state.time_ref
    universe_id = None  # ensure defined for all code paths below

    try:
        scene = await run_sync_read(mongodb_get_scene, state.scene_id)  # type: ignore[var-annotated]
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
        await RoleplayErrorRecorder.record(
            source=RoleplayErrorSource.SCENE_LOOP,
            category=RoleplayErrorCategory.SCENE_BOOTSTRAP_FAILED,
            message=str(exc),
            fatal=True,
            universe_id=universe_id,
            story_id=state.story_id,
            scene_id=state.scene_id,
        )
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
    context = await agent.check_and_compress_if_needed(context, player_action=state.user_input or "")

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
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.SCENE_LOOP,
                category=RoleplayErrorCategory.UNKNOWN,
                message=str(e),
                fatal=False,
                universe_id=universe_id,
                story_id=state.story_id,
                scene_id=state.scene_id,
            )

    # Fetch the character's working state for the ResourceEngine
    working_state_dict = {}
    if state.actor_id and state.scene_id:
        try:
            from monitor_data.tools.mongodb_tools import mongodb_get_working_state

            ws_res = await run_sync_read(mongodb_get_working_state, state.actor_id, state.scene_id)  # type: ignore[var-annotated]
            if ws_res and getattr(ws_res, "state", None):
                # ResourceEngine expects a FLAT resource dict ({"Blood Pool": {current,max}, ...}),
                # not the full CharacterWorkingState. The full model_dump nests resources under a
                # "resources" key, so the engine never found them and emitted no deltas. Pass the
                # flat resource snapshot directly.
                working_state_dict = dict(ws_res.state.resources or {})
        except Exception as e:
            logger.warning("Failed to load working state for actor %s: %s", state.actor_id, e)
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.SCENE_LOOP,
                category=RoleplayErrorCategory.UNKNOWN,
                message=str(e),
                fatal=False,
                universe_id=universe_id,
                story_id=state.story_id,
                scene_id=state.scene_id,
                entity_id=state.actor_id,
            )

    # Fetch NPC profiles for entities in this scene (Task 4). Best-effort:
    # any failure leaves npc_profiles empty and the NPC STATE block degrades.
    npc_profiles: dict[str, Any] = {}
    try:
        entity_ids = [
            UUID(str(e["id"])) for e in state.entity_context
            if isinstance(e, dict) and e.get("id")
        ]
        if entity_ids:
            from monitor_data.tools.mongodb_tools import mongodb_get_npc_profiles_by_entities
            profiles = await run_sync_read(
                mongodb_get_npc_profiles_by_entities, entity_ids,
            )
            npc_profiles = {str(p.entity_id): p.model_dump(mode="json") for p in profiles}
    except Exception as exc:
        logger.warning("load_context: npc profile fetch failed: %s", exc)

    # Fetch open foreshadowing (Task 6). Best-effort: failure leaves the block silent.
    open_foreshadowing: list[dict[str, Any]] = []
    try:
        from monitor_data.tools.mongodb_tools import mongodb_list_open_foreshadowing
        items = await run_sync_read(
            mongodb_list_open_foreshadowing,
            state.scene_id,
            state.story_id,
            limit=5,
        )
        open_foreshadowing = [r.model_dump(mode="json") for r in items]
    except Exception as exc:
        logger.debug("load_context: foreshadowing fetch failed: %s", exc)

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
        "context_summary": context.get("summary", ""),
        "pacing": compute_pacing(state.turns_count, len(state.pending_proposals or [])),
        "npc_profiles": npc_profiles,
        "scene_foreshadowing_open": open_foreshadowing,
    }


@_timed_node  # type: ignore[untyped-decorator]
async def resolve_action(state: SceneState) -> dict[str, Any]:
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
    # resolve_turn returns (resolution_dict, gm_verdict) — the verdict
    # carries the GM's narrative_draft so the Narrator downstream can
    # refine it against the outcome. We pop the internal "_gm_verdict"
    # key from the dict to keep state.resolution clean.
    # The resolver/GMAgent read established facts from source_profile, so
    # merge the player's director notes in there as well.
    source_profile = dict(state.source_profile or {})
    if state.established_facts:
        source_profile["established_facts"] = [
            *state.established_facts,
            *[f for f in source_profile.get("established_facts") or [] if f not in state.established_facts],
        ]
    resolution, gm_verdict = await resolver.resolve_turn(
        scene_id=str(state.scene_id),
        user_input=state.user_input,
        context={
            "entities": state.entity_context,
            "turns": state.previous_turns,
            "source_profile": source_profile,
            "pending_roll": state.pending_roll,
            "agreements": {
                "lines": list(state.agreements_lines or []),
                "veils": list(state.agreements_veils or []),
            },
        },
        game_context=state.game_context,
        play_mode=state.play_mode,
        roll_mode=state.roll_mode,
        tension_score=state.tension_score,
    )
    resolution.pop("_gm_verdict", None)
    proposals = resolution.get("proposals", [])
    if state.universe_id:
        for p in proposals:
            p["universe_id"] = str(state.universe_id)
            if "content" in p and isinstance(p["content"], dict):
                p["content"]["universe_id"] = str(state.universe_id)

    # Pending roll state machine: when the resolver returns propose_roll,
    # persist the roll spec so the next turn knows a roll is pending.
    # When the roll is resolved (not pending), clear it.
    new_pending_roll = state.pending_roll
    res_type = resolution.get("resolution_type")
    if res_type == "propose_roll":
        new_pending_roll = {
            "stat": resolution.get("stat"),
            "dc": resolution.get("difficulty_class"),
            "modifier": resolution.get("modifier"),
            "action": state.user_input,
            "resolution_type": "propose_roll",
        }
    elif res_type in ("dice", "contested", "forced_narrative_pushback"):
        new_pending_roll = None

    return {
        "resolution": resolution,
        "gm_verdict": gm_verdict,
        "pending_proposals": state.pending_proposals + proposals,
        "pending_roll": new_pending_roll,
    }


@_timed_node  # type: ignore[untyped-decorator]
async def narrate(state: SceneState) -> dict[str, Any]:
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
        gm_verdict=state.gm_verdict,
        context={
            "entities": state.entity_context,
            "memories": state.memory_context,
            "turns": state.previous_turns,
            "source_profile": state.source_profile,
            "actor": state.actor_context,
            "context_summary": state.context_summary,
            "turn_context": state.turn_context,
            "established_facts": state.established_facts,
            "ooc_exchanges": state.ooc_exchanges,
            "recent_chat": state.recent_chat,
            "pacing": state.pacing,
            "npc_profiles": state.npc_profiles,
            "agreements": {
                "lines": list(state.agreements_lines or []),
                "veils": list(state.agreements_veils or []),
            },
        },
        game_context=state.game_context,
        session_tone=state.session_tone,
        gm_profile=state.gm_profile,
        lorebook_context=state.lorebook_context,
        story_state=state.story_state,
    )
    PersistenceService.clear_scene_runtime_cache(state.scene_id)
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
        "suggested_actions": result.get("suggested_actions", []),
        "degraded": result.get("degraded"),
    }


async def extract_new_entities(state: SceneState) -> dict[str, Any]:
    """
    P-7 / On-the-fly creation: Detect new entities mentioned in narration.
    """
    factory = get_agent_factory()
    agent = factory.create_extractor()
    return await agent.extract_new_entities(
        narrative_text=state.narrative_text,
        entity_context=state.entity_context,
        game_context=state.game_context,
        universe_id=state.universe_id,
        pending_proposals=state.pending_proposals,
        resolution=state.resolution,
        scene_id=state.scene_id,
    )

async def extract_memories(state: SceneState) -> dict[str, Any]:
    """
    Task 4: Extract salient character memories from the narrative prose.
    """
    factory = get_agent_factory()
    agent = factory.create_extractor()
    return await agent.extract_memories(
        narrative_text=state.narrative_text,
        actor_context=state.actor_context,
        resolution=state.resolution,
    )

async def persist_turn_artifacts(state: SceneState) -> dict[str, Any]:
    """
    Persist a structured DL-24 resolution record tied to the newly created turn.

    This keeps per-turn mechanics queryable without relying on UI metadata blobs.
    """
    if not state.resolution or not state.turn_id:
        return {}

    resolution_type = str(state.resolution.get("resolution_type", "")).lower()
    if resolution_type == "propose_roll":
        return {}

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

    from monitor_agents.utils.db_readers import (
        mongodb_create_resolution,
        mongodb_update_turn_resolution,
        run_sync_read,
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

    def _safe_resolution_type(raw: str, forced: bool) -> ResolutionType:
        if forced:
            return ResolutionType.FORCED_NARRATIVE
        val = (raw or "narrative").strip().lower()
        val = _RESOLUTION_TYPE_ALIASES.get(val, val)
        try:
            return ResolutionType(val)
        except ValueError:
            return ResolutionType.NARRATIVE

    def _safe_success_level(raw: str) -> SuccessLevel:
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
        formula=str(state.resolution.get("roll_breakdown") or resolution_type or "narrative resolution")[:200],
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
        # The action field on ResolutionCreate is capped at 500 chars (full
        # prose belongs in the GM's narrative_text + the turn text, not in
        # this compact resolution record). Real-LLM players generate rich
        # in-voice prose that easily blows past 500 chars; truncate at the
        # schema boundary so the persistence layer never crashes the loop.
        raw_action = state.user_input or "(no action text)"
        if len(raw_action) > 500:
            raw_action = raw_action[:497] + "..."
        params = ResolutionCreate(
            turn_id=turn_uuid,
            scene_id=state.scene_id,
            story_id=state.story_id,
            actor_id=actor_uuid,
            action=raw_action,
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
            success_level=_safe_success_level(state.resolution.get("success_level")),  # type: ignore[arg-type]
            margin=(
                int(state.resolution.get("roll_total") or 0) - int(state.resolution.get("difficulty_class") or 0)
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
        created = await run_sync_read(mongodb_create_resolution, params)  # type: ignore[var-annotated]
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
            state.turn_id if isinstance(state.turn_id, UUID) else UUID(str(state.turn_id)) if state.turn_id else None
        )
        persistence_payload = await PersistenceService.persist_working_state(
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
            state.turn_id  # type: ignore[assignment]
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


async def canonize_checkpoint(state: SceneState) -> dict[str, Any]:
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
    PersistenceService.clear_scene_runtime_cache(state.scene_id, include_entities=True)
    return {"pending_proposals": []}


async def persist_memories_node(state: SceneState) -> dict[str, Any]:
    """
    Persist extracted memories to MongoDB via mongodb_create_memory.

    Called after extract_memories populates state.memories_to_persist.
    """
    if not state.memories_to_persist:
        return {}

    if not state.actor_id:
        logger.warning("persist_memories_node called but no actor_id in state")
        return {}

    from monitor_agents.services.persistence_service import PersistenceService

    try:
        created_ids = await PersistenceService.persist_memories(
            entity_id=state.actor_id,
            scene_id=state.scene_id,
            story_id=state.story_id,
            universe_id=state.universe_id,  # type: ignore[arg-type]
            memories=state.memories_to_persist,
        )
        logger.debug("Persisted %d memories for actor %s", len(created_ids), state.actor_id)
    except Exception as e:
        logger.warning("Failed to persist memories: %s", e)

    # Return empty dict — we only write, no state changes
    return {}


async def complete_current_scene(state: SceneState) -> dict[str, Any]:
    """
    GAP-E: Scene end choreography.

    Called when scene_complete=True. Handles:
    1. Persist any remaining memories (belt-and-suspenders, should already be done)
    2. Advance story state (scenes_completed++, in_game_time)
    3. Signal scene ending (CanonKeeper.end_scene placeholder)
    """
    from datetime import timedelta

    updates: dict[str, Any] = {}

    # 1. Persist any remaining memories (belt-and-suspenders)
    if state.memories_to_persist and state.actor_id:
        from monitor_agents.services.persistence_service import PersistenceService

        try:
            await PersistenceService.persist_memories(
                entity_id=state.actor_id,
                scene_id=state.scene_id,
                story_id=state.story_id,
                universe_id=state.universe_id,  # type: ignore[arg-type]
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
        await RoleplayErrorRecorder.record(
            source=RoleplayErrorSource.CANONKEEPER,
            category=RoleplayErrorCategory.CANONKEEPER_WRITE_FAILED,
            message=str(e),
            fatal=False,
            universe_id=getattr(state, "universe_id", None),
            story_id=state.story_id,
            scene_id=state.scene_id,
            entity_id=state.actor_id,
        )

    # 4. Downtime trigger (P-21): when the story arc reaches "resolution",
    # signal that progression options are available.
    story_state_dict = updates.get("story_state") or {}
    arc_label = story_state_dict.get("arc_label") or (state.story_state.arc_label if state.story_state else None)
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


# =============================================================================
# Narrative coherence nodes (extract_facts + check_consistency)
# =============================================================================


async def extract_facts(state: SceneState) -> dict[str, Any]:
    """
    Extract concrete facts from narration for continuity tracking.
    """
    factory = get_agent_factory()
    agent = factory.create_extractor()
    return await agent.extract_facts(
        narrative_text=state.narrative_text,
        established_facts=state.established_facts,
        scene_id=state.scene_id,
    )

async def check_consistency(state: SceneState) -> dict[str, Any]:
    """
    Lightweight consistency check against established facts.
    """
    factory = get_agent_factory()
    agent = factory.create_world_rules()
    return await agent.check_consistency(
        narrative_text=state.narrative_text,
        established_facts=state.established_facts,
        turn_context=state.turn_context,
        source_profile=state.source_profile,
        scene_id=state.scene_id,
    )

async def check_events(state: SceneState) -> dict[str, Any]:
    """
    FASE ALTO (Item 1): ResourceEngine — detect spends, apply earns, fire thresholds.
    """
    factory = get_agent_factory()
    agent = factory.create_world_rules()
    return await agent.check_events(
        game_context=state.game_context,
        working_state=state.working_state,
        user_input=state.user_input,
        turns_count=state.turns_count,
        scene_complete=state.scene_complete,
        resolution=state.resolution,
    )


async def check_foreshadowing(state: SceneState) -> dict[str, Any]:
    """Propose 0-2 plants and 0-2 payoffs for this turn; persist open plants.

    Best-effort: any failure here is logged and swallowed (the scene continues).
    """
    from monitor_agents.foreshadowing.agent import ForeshadowingAgent
    from monitor_data.schemas.foreshadowing import ForeshadowingCreate
    from monitor_data.tools.mongodb_tools import (
        mongodb_create_foreshadowing,
        mongodb_mark_foreshadowing_paid,
    )
    import anyio

    try:
        agent = ForeshadowingAgent()
        proposals = await agent.propose(
            scene_id=state.scene_id,
            story_id=state.story_id,
            narrative_text=state.narrative_text or "",
            entities=state.entity_context,
            player_action=state.user_input or "",
        )
    except Exception as exc:
        logger.warning("check_foreshadowing: agent failed: %s", exc)
        return {"foreshadowing_planted": 0, "foreshadowing_paid": 0}

    planted = 0
    for plant in proposals.get("plants", []):
        try:
            await anyio.to_thread.run_sync(
                mongodb_create_foreshadowing,
                ForeshadowingCreate(
                    scene_id=state.scene_id,
                    story_id=state.story_id,
                    kind="plant",
                    summary=str(plant.get("summary") or "")[:200],
                    planted_by_turn=state.turns_count,
                    target_turn=int(plant.get("target_turn") or state.turns_count + 5),
                ),
            )
            planted += 1
        except Exception as exc:
            logger.debug("check_foreshadowing: plant write failed: %s", exc)

    open_items = state.scene_foreshadowing_open or []
    open_by_summary = {
        str(o.get("summary") or "").strip().lower(): o
        for o in open_items if isinstance(o, dict)
    }
    paid = 0
    for payoff in proposals.get("payoffs", []):
        summary = str(payoff.get("summary") or "").strip()
        if not summary:
            continue
        match = open_by_summary.get(summary.lower())
        if not match:
            continue
        try:
            await anyio.to_thread.run_sync(
                mongodb_mark_foreshadowing_paid,
                UUID(str(match.get("foreshadowing_id"))),
                paid_at_turn=state.turns_count,
            )
            paid += 1
        except Exception as exc:
            logger.debug("check_foreshadowing: payoff write failed: %s", exc)

    return {"foreshadowing_planted": planted, "foreshadowing_paid": paid}

def _chat_tail(chat_log: Any, *, limit: int = 6) -> list[dict[str, str]]:
    """Last `limit` chat messages as {role, mode, content} dicts (IC/OOC labeled)."""
    if not isinstance(chat_log, list) or not chat_log:
        return []
    tail: list[dict[str, str]] = []
    for m in chat_log[-limit:]:
        if not isinstance(m, dict):
            continue
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        meta: dict[str, Any] = {}
        metadata = m.get("metadata")
        if isinstance(metadata, dict):
            meta = metadata
        mode = str(m.get("chat_mode") or meta.get("chat_mode") or "ic")
        tail.append({"role": str(m.get("role") or "?"), "mode": mode, "content": content})
    return tail


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
    graph.add_node("extract_facts", extract_facts)
    graph.add_node("persist_memories", persist_memories_node)
    graph.add_node("check_consistency", check_consistency)
    graph.add_node("check_events", check_events)
    graph.add_node("check_foreshadowing", check_foreshadowing)
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
    # Fan out: three extractors run concurrently after narrate.
    graph.add_edge("narrate", "extract_new_entities")
    graph.add_edge("narrate", "extract_memories")
    graph.add_edge("narrate", "extract_facts")
    # Fan in: wait for ALL extractors before persisting.
    graph.add_edge("extract_new_entities", "persist_memories")
    graph.add_edge("extract_memories", "persist_memories")
    graph.add_edge("extract_facts", "persist_memories")
    graph.add_edge("persist_memories", "check_consistency")
    graph.add_edge("persist_memories", "check_events")
    graph.add_edge("check_consistency", "persist_turn_artifacts")
    graph.add_edge("check_events", "persist_turn_artifacts")
    # Foreshadowing fires in parallel with consistency/events; its plants/payoffs
    # are persisted straight to MongoDB, no need to fan into persist_turn_artifacts.
    graph.add_edge("persist_memories", "check_foreshadowing")
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
    def get_gm_profile(profile_id: UUID) -> dict[str, Any] | None:
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
        gm_profile: dict[str, Any] | None = None,
        max_turns: int = 50,
        play_mode: str = "dice_game_system",
        system_id: str | None = None,
        pack_id: str | None = None,
        system_source_type: str | None = None,
        system_source_id: str | None = None,
        actor_id: UUID | None = None,
        actor_context: dict[str, Any] | None = None,
        session_tone: str = "dramatic",
        roll_mode: str = "normal",
        tension_score: float = 0.5,
        story_state: dict[str, Any] | None = None,
        agreements_lines: list[str] | None = None,
        agreements_veils: list[str] | None = None,
        director_notes: list[str] | None = None,
        ooc_exchanges: list[dict[str, Any]] | None = None,
        chat_log: list[Any] | None = None,
        opening_recap: str = "",
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
        self.agreements_lines = list(agreements_lines or [])
        self.agreements_veils = list(agreements_veils or [])
        # Player-established facts asserted OOC ("this happens in Santiago").
        # Kept as a REFERENCE to the session's list so notes recorded after
        # this loop was cached still show up on the next turn.
        self.director_notes = director_notes if director_notes is not None else []
        # OOC Q&A exchanges — REFERENCE to the session's list (same pattern
        # as director_notes) so answers given mid-scene show up next turn.
        self.ooc_exchanges = ooc_exchanges if ooc_exchanges is not None else []
        # Live chat-log reference (last 6 messages are derived per-turn via
        # _chat_tail); refresh on every get_scene_loop call.
        self.chat_log = chat_log
        # Optional one-line recap from the previous scene (Task 7).
        self.opening_recap = opening_recap
        self._graph = build_scene_graph()

    async def run(
        self,
        user_input: str,
        resolution_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
                agreements_lines=getattr(self, "agreements_lines", []),
                agreements_veils=getattr(self, "agreements_veils", []),
                # Feed the (otherwise dead) established_facts channel with the
                # player's director notes so the GMAgent and Narrator treat
                # them as established truth instead of improvising settings.
                established_facts=list(getattr(self, "director_notes", []) or []),
                ooc_exchanges=list(getattr(self, "ooc_exchanges", []) or []),
                recent_chat=_chat_tail(getattr(self, "chat_log", None)),
                opening_recap=str(getattr(self, "opening_recap", "") or ""),
                resolution=resolution_override,
            )
            # Add pre-loaded gm_profile to state if available
            gm_profile = getattr(self, "gm_profile", None)
            if gm_profile:
                initial.gm_profile = gm_profile

            result = await compiled.ainvoke(initial.model_dump(), config=config)

            # Combat delegation: if the resolution flagged combat, run CombatLoop.
            # ``subsystem_hint`` / ``action_type`` here come from the semantic
            # action router (embeddings), not a keyword scan — no separate gate.
            resolution = result.get("resolution") or {}
            if resolution.get("subsystem_hint") == "combat" or resolution.get("action_type") == "combat":
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
                        (result.get("narrative_text") or "") + "\n\n" + combat_result.get("narrative_text", "")
                    )
                    result["combat_result"] = combat_result

                    # Extract HP deltas from combat result and merge into
                    # resource_deltas so persist_working_state applies them
                    # to the working state (T-092 carryover fix).
                    combat_deltas = _extract_combat_resource_deltas(combat_result, result.get("entity_context", []))
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

    async def backtrack(self) -> dict[str, Any]:
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
            history = [state async for state in compiled.aget_state_history(config)]  # type: ignore[arg-type]

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
                config,  # type: ignore[arg-type]
                target_state.values,
                as_node=target_state.next[0] if target_state.next else None,
            )

            return target_state.values


async def _run_combat(
    scene_id: UUID,
    story_id: UUID,
    user_input: str,
    entity_context: list[dict[str, Any]],
    game_context: dict[str, Any],
    source_profile: dict[str, Any],
    gm_profile: dict[str, Any] | None = None,
    session_tone: str = "dramatic",
) -> dict[str, Any] | None:
    """
    Bootstrap and run a CombatLoop for the current scene.

    Returns combat result dict or None if combat can't be started.
    """
    from monitor_agents.loops.combat_loop import CombatantState, CombatLoop

    # Build combatants from entity context
    combatants: list[CombatantState] = []
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
        final_narrative += f"\n\nCombat continues — Round {result.get('round_number', 1)}. Your turn. What do you do?"

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
    combat_result: dict[str, Any],
    entity_context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract HP/resource deltas from combat result combatants.

    Compares each combatant's post-combat HP to their pre-combat HP (from
    entity_context properties) and emits resource_delta dicts for the PC
    so that persist_working_state applies the HP change to working_state.

    T-092 carryover: combat damage was computed by CombatLoop.apply_damage
    but never merged back into the scene state's resource_deltas.
    """
    deltas: list[dict[str, Any]] = []
    if not combat_result:
        return deltas

    combatants = combat_result.get("combatants") or []
    if not combatants:
        return deltas

    # Build a lookup of pre-combat HP from entity_context
    pre_hp: dict[str, int] = {}
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
