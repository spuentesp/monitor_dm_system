"""
Story Loop — LangGraph StateGraph for campaign/arc progression.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), langgraph, external libs
CALLED BY: main_loop.py (via StoryLoop.run())

Manages scene sequences within a story arc.  Delegates interactive
narrative to SceneLoop, handles scene transitions, and writes the
story-level canonical record (Story node in Neo4j) via CanonKeeper.

Flow: init_story → [scene_loop per scene] → finalize_story
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.graph import END, StateGraph
from monitor_data.config import settings
from pydantic import BaseModel, Field

from monitor_agents.agent_factory import get_agent_factory
from monitor_agents.utils.db_readers import (
    mongodb_create_scene,
    mongodb_create_story_outline,
    mongodb_get_story_outline,
    mongodb_list_scenes,
    run_sync_read,
)

logger = logging.getLogger(__name__)

# =============================================================================
# STATE SCHEMA
# =============================================================================


class StoryState(BaseModel):
    """State that flows across the Story Loop."""

    story_id: UUID
    universe_id: UUID

    # Temporal tracking
    in_game_time: datetime = Field(
        default_factory=lambda: datetime(1000, 1, 1, 12, 0, tzinfo=UTC),
        description="The current absolute time within the fictional world.",
    )
    world_ticks: int = Field(default=0, description="Total number of regional/global simulation steps.")
    last_scene_duration_minutes: int = Field(default=0, description="Minutes passed in the last scene.")

    # Narrative context
    world_tone: str = Field(default="dramatic")
    story_outline: dict[str, Any] | None = None
    story_premise: str | None = Field(
        default=None,
        description=(
            "Player-stated pitch for what this story should be about "
            "(character-template plan Q3). A hard content constraint the "
            "Narrator carries forward into setting_anchor on every scene "
            "turn, not just the opening."
        ),
    )

    # Scene tracking
    scenes: list[UUID] = Field(default_factory=list)
    current_scene_id: UUID | None = None
    scenes_completed: int = 0

    # Flow control
    story_complete: bool = False

    # Arc evaluation (Phase A.1)
    arc_label: str = Field(
        default="rising_action",
        description="Current narrative arc phase: rising_action, climax, falling_action, resolution, new_thread",
    )
    tension_score: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Narrative tension from 0 (calm) to 1 (peak)",
    )
    active_threads: list[str] = Field(
        default_factory=list,
        description="Open plot threads still in play",
    )
    completed_threads: list[str] = Field(
        default_factory=list,
        description="Resolved plot threads",
    )
    next_scene_type: str | None = Field(
        default=None,
        description="Suggested next scene type: action, dialogue, exploration, rest, combat, revelation",
    )
    scene_hook: str | None = Field(
        default=None,
        description="LLM-generated hook or prompt for the next scene.",
    )
    scenes_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Summaries of completed scenes for arc evaluation context",
    )

    # Session-Zero table agreements (lines + veils) — P-19 redesign. These
    # are session-scoped player constraints, not canon; the resolver/narrator
    # consume them as context but they are never written to Neo4j.
    agreements_lines: list[str] = Field(
        default_factory=list,
        description="Subjects that must never be depicted or introduced.",
    )
    agreements_veils: list[str] = Field(
        default_factory=list,
        description="Subjects that may exist but must fade to black.",
    )


# =============================================================================
# NODES
# =============================================================================


async def init_story(state: StoryState) -> dict[str, Any]:
    """
    Bootstrap story and scene initialization.

    This node ensures that:
    1. The story exists in Neo4j (creates it if needed)
    2. The story outline exists in MongoDB (creates it if needed)
    3. The first scene exists in MongoDB (creates it if needed)

    This improved bootstrap supports complex campaign setups and "Session Zero" flows.

    Writes: Story node to Neo4j via CanonKeeper (if new story), Scene doc to MongoDB.
    """
    factory = get_agent_factory()
    ck = factory.create_canonkeeper()

    # Step 1: Ensure story exists in Neo4j
    story_exists = await ck.story_exists(state.story_id)

    if not story_exists:
        # Create the story in Neo4j with default values
        await ck.create_story(
            story_id=state.story_id,
            universe_id=state.universe_id,
            title=f"Story {state.story_id}",
            story_type="campaign",
        )

    # Step 2: Carry tone from state/session bootstrap. Avoid an extra Neo4j
    # read here; StoryLoop must be able to bootstrap even when universe metadata
    # is unavailable or the graph store is degraded.
    tone = state.world_tone or "dramatic"

    # Step 3: Load or create story outline in MongoDB
    story_outline = await _load_story_outline(state.story_id)
    if not story_outline:
        story_outline = await _create_story_outline(state.story_id, state.universe_id)

    # Step 4: Ensure first scene exists in MongoDB
    if not state.current_scene_id:
        scene_id = await _create_scene(state.story_id, state.universe_id, order=0)
        return {
            "story_outline": story_outline,
            "scenes": [scene_id],
            "current_scene_id": scene_id,
            "world_tone": tone,
        }

    return {"story_outline": story_outline, "world_tone": tone}


async def run_scene(state: StoryState) -> dict[str, Any]:
    """
    Delegate to SceneLoop for the current scene.

    This node is called after a scene has completed (driven externally by
    the CLI REPL via SceneLoop.run() / SceneLoop.finalize()).  It records
    the outcome at story level so the graph can decide whether to
    transition or finalize.
    """
    # The CLI layer drives user input into SceneLoop directly.
    # This node merely records the scene completion count so the graph
    # can route correctly on the next advance() call.
    completed = state.scenes_completed
    return {"scenes_completed": completed, "scenes_history": state.scenes_history}


async def _plan_next_scene(state: StoryState) -> dict:
    """
    DSPy-powered story planning helper.
    """
    factory = get_agent_factory()
    agent = factory.create_story_agent()
    return await agent._plan_next_scene(state)


async def evaluate_arc(state: StoryState) -> dict[str, Any]:
    """
    Evaluate the narrative arc after each scene.
    Delegates to StoryAgent.
    """
    factory = get_agent_factory()
    agent = factory.create_story_agent()
    return await agent.evaluate_arc(state)


async def transition_scene(state: StoryState) -> dict[str, Any]:
    """
    Create the next scene using arc evaluation context.
    Delegates to StoryAgent.
    """
    factory = get_agent_factory()
    agent = factory.create_story_agent()
    return await agent.transition_scene(state)


async def simulate_world_advance(state: StoryState) -> dict[str, Any]:
    """
    S-Tick: Resolve off-screen faction agency and environmental shifts.
    Delegates to StoryAgent.
    """
    factory = get_agent_factory()
    agent = factory.create_story_agent()
    return await agent.simulate_world_advance(state)


async def finalize_story(state: StoryState) -> dict[str, Any]:
    """
    Write story completion to Neo4j via CanonKeeper.
    Delegates to StoryAgent.
    """
    factory = get_agent_factory()
    agent = factory.create_story_agent()
    return await agent.finalize_story(state)


def route_after_scene(state: StoryState) -> str:
    """Continue story or finalize."""
    if state.story_complete:
        return "finalize"
    return "transition"


# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================


def build_story_graph() -> StateGraph:
    """Build the Story Loop StateGraph."""
    graph = StateGraph(StoryState)

    graph.add_node("init_story", init_story)
    graph.add_node("run_scene", run_scene)
    graph.add_node("evaluate_arc", evaluate_arc)
    graph.add_node("world_advance", simulate_world_advance)
    graph.add_node("transition", transition_scene)
    graph.add_node("finalize", finalize_story)

    graph.set_entry_point("init_story")
    # The interactive SceneLoop is driven externally by the UI/CLI.  Keeping
    # bootstrap as the only automatic edge prevents start_or_resume() from
    # recursively creating scenes until LangGraph hits its recursion limit.
    graph.add_edge("init_story", END)
    # After scene completion: evaluate arc → transition or finalize
    graph.add_edge("run_scene", "evaluate_arc")
    graph.add_conditional_edges(
        "evaluate_arc",
        route_after_scene,
        {"transition": "transition", "finalize": "finalize"},
    )
    graph.add_edge("transition", END)
    graph.add_edge("finalize", END)

    return graph


# =============================================================================
# HELPERS
# =============================================================================


async def _load_story_outline(story_id: UUID) -> dict[str, Any] | None:
    """Load a story outline document as a plain dict."""
    return await run_sync_read(mongodb_get_story_outline, story_id)


async def _create_story_outline(story_id: UUID, universe_id: UUID) -> dict[str, Any]:
    """Create the minimal story outline required before scene play starts."""
    from monitor_data.schemas.story_outlines import StoryOutlineCreate

    params = StoryOutlineCreate(
        story_id=story_id,
        theme="dramatic campaign",
        premise="Session started from the play loop.",
    )
    created = await run_sync_read(mongodb_create_story_outline, params)  # type: ignore[var-annotated]
    outline = created.model_dump(mode="json") if hasattr(created, "model_dump") else dict(created)
    outline.setdefault("universe_id", str(universe_id))
    return outline


async def _create_scene(
    story_id: UUID,
    universe_id: UUID,
    order: int,
    temporal_mode: Any = "present",
    purpose: str = "New Scene",
    time_description: str = "The present",
) -> UUID:
    """Insert a new scene document in MongoDB and return its UUID."""
    from monitor_data.schemas.base import SceneStatus, TemporalMode
    from monitor_data.schemas.scenes import SceneCreate

    mode_val = temporal_mode.value if hasattr(temporal_mode, "value") else temporal_mode

    scene_params = SceneCreate(
        story_id=story_id,
        universe_id=universe_id,
        title=f"Scene {order}",
        purpose=purpose,
        narrative_order=order,
        temporal_mode=TemporalMode(mode_val) if isinstance(mode_val, str) else mode_val,
        time_description=time_description,
        status=SceneStatus.ACTIVE,
    )
    result = await run_sync_read(mongodb_create_scene, scene_params)  # type: ignore[var-annotated]
    scene_id = result.get("scene_id") if isinstance(result, dict) else result.scene_id
    return scene_id  # type: ignore[return-value]


# =============================================================================
# PUBLIC API
# =============================================================================


class StoryLoop:
    """Manages the campaign-level state machine for a story arc."""

    def __init__(self, story_id: UUID, universe_id: UUID) -> None:
        self.story_id = story_id
        self.universe_id = universe_id
        self._graph = build_story_graph()

    async def start_or_resume(self) -> dict[str, Any]:
        """Start a new story or resume from checkpoint."""
        with MongoDBSaver.from_conn_string(settings.mongodb_uri) as checkpointer:
            compiled = self._graph.compile(checkpointer=checkpointer)
            thread_id = f"story-{self.story_id}"
            config = {"configurable": {"thread_id": thread_id}}

            initial = StoryState(
                story_id=self.story_id,
                universe_id=self.universe_id,
            )
            result = await compiled.ainvoke(initial.model_dump(), config=config)
            return result

    async def plan_next_scene(self, state: StoryState) -> dict:
        """Thin wrapper for external callers to plan the next scene beat."""
        return await _plan_next_scene(state)

    async def advance(self, story_complete: bool = False) -> dict[str, Any]:
        """Advance the story state after a scene completes."""
        state = StoryState(
            story_id=self.story_id,
            universe_id=self.universe_id,
            story_complete=story_complete,
        )
        if story_complete:
            await finalize_story(state)
            return {"story_complete": True}

        world_update: dict[str, Any] = {}
        try:
            world_update = await simulate_world_advance(state)
            state = state.model_copy(update=world_update)
        except Exception:
            logger.warning(
                "Story world-advance failed for story %s",
                self.story_id,
                exc_info=True,
            )

        transition_update = await transition_scene(state)
        return {
            **state.model_dump(),
            **world_update,
            **transition_update,
        }

    async def complete_current_scene(
        self,
        scene_id: UUID,
        outcome: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Mark the current scene as completed and advance the story graph.

        Flow: run_scene → evaluate_arc → (transition/create_next | finalize_story)

        Called by the CLI/UI after SceneLoop.finalize() returns.  Creates the
        next scene (or finalizes the story) based on arc evaluation.

        Args:
            scene_id: The scene that just finished.
            outcome: Metadata from SceneLoop (including total_minutes_passed).

        Returns:
            Updated StoryState dict.
        """
        force_complete = bool((outcome or {}).get("scene_complete", False))
        duration = int((outcome or {}).get("total_minutes_passed") or 0)

        with MongoDBSaver.from_conn_string(settings.mongodb_uri) as checkpointer:
            compiled = self._graph.compile(checkpointer=checkpointer)
            thread_id = f"story-{self.story_id}"
            config = {"configurable": {"thread_id": thread_id}}

            # Load current checkpoint state
            try:
                current = await compiled.aget_state(config)  # type: ignore[arg-type]
                state_values = dict(current.values) if current.values else {}
            except Exception:
                state_values = {}

            # Build state with scene completion context
            previous_scenes = list(state_values.get("scenes", []))
            previous_history = list(state_values.get("scenes_history", []))
            previous_threads = list(state_values.get("active_threads", []))
            previous_completed = list(state_values.get("completed_threads", []))

            run_state = StoryState(
                story_id=self.story_id,
                universe_id=self.universe_id,
                current_scene_id=scene_id,
                story_complete=force_complete,
                last_scene_duration_minutes=duration,
                scenes=previous_scenes,
                scenes_completed=state_values.get("scenes_completed", 0) + 1,
                scenes_history=previous_history,
                world_tone=state_values.get("world_tone", "dramatic"),
                arc_label=state_values.get("arc_label", "rising_action"),
                tension_score=float(state_values.get("tension_score", 0.3)),
                active_threads=previous_threads,
                completed_threads=previous_completed,
            )

            if force_complete:
                await finalize_story(run_state)
                return {"story_complete": True, "completed_scene_id": scene_id}

            # Step 1: Run world simulation
            world_update: dict[str, Any] = {}
            try:
                world_update = await simulate_world_advance(run_state)
                run_state = run_state.model_copy(update=world_update)
            except Exception:
                logger.warning(
                    "Story world-advance failed after scene %s",
                    scene_id,
                    exc_info=True,
                )

            # Step 2: Evaluate arc
            arc_update = await evaluate_arc(run_state)
            run_state = run_state.model_copy(update=arc_update)

            # P-22: NPC Agenda Tick — advance off-screen NPC agendas
            agenda_moves: list[str] = []
            try:
                agenda_result = await self.call_tool(
                    "neo4j_tick_agendas",
                    {"universe_id": str(self.universe_id)},
                )
                if isinstance(agenda_result, list):
                    agenda_moves = agenda_result
                elif isinstance(agenda_result, dict):
                    agenda_moves = agenda_result.get("moves", [])
                if agenda_moves:
                    logger.info(
                        "NPC agenda tick: %d moves for universe %s",
                        len(agenda_moves),
                        self.universe_id,
                    )
            except Exception:
                logger.warning("NPC agenda tick failed", exc_info=True)

            # P-21: Progression Phase
            # Trigger progression if we are in resolution phase or a downtime scene just ended
            progression_update: dict[str, Any] = {}
            if arc_update.get("arc_label") == "resolution" or (outcome or {}).get("scene_purpose") == "rest":
                from monitor_agents.loops.progression_loop import ProgressionLoop

                # We need the PC's entity_id. For now assume it's in the outcome or we find it.
                pc_id = (outcome or {}).get("actor_id")
                if pc_id:
                    prog_loop = ProgressionLoop(entity_id=UUID(str(pc_id)), universe_id=self.universe_id)
                    # For now, we just start it and get the options.
                    # Real implementation would wait for user selection.
                    prog_res = await prog_loop.start(available_xp=5)  # Default 5 XP for now
                    progression_update = {"progression_options": prog_res}

            if arc_update.get("story_complete"):
                await finalize_story(run_state)
                return {
                    **run_state.model_dump(),
                    **progression_update,
                    "completed_scene_id": scene_id,
                }

            # Step 3: Create next scene via transition
            transition_update = await transition_scene(run_state)
            return {
                **run_state.model_dump(),
                **transition_update,
                **progression_update,
                "agenda_moves": agenda_moves,
                "completed_scene_id": scene_id,
            }

    async def create_flashback(
        self,
        purpose: str,
        time_description: str,
    ) -> dict[str, Any]:
        """
        Create a flashback scene and advance the story graph to it.
        """
        from monitor_data.schemas.base import TemporalMode

        with MongoDBSaver.from_conn_string(settings.mongodb_uri) as checkpointer:
            compiled = self._graph.compile(checkpointer=checkpointer)
            thread_id = f"story-{self.story_id}"
            config = {"configurable": {"thread_id": thread_id}}

            # Fetch current state to get next order
            state = await compiled.aget_state(config)  # type: ignore[arg-type]
            next_order = state.values.get("scenes_completed", 0)

            scene_id = await _create_scene(
                self.story_id,
                self.universe_id,
                order=next_order,
                temporal_mode=TemporalMode.FLASHBACK,
                purpose=purpose,
                time_description=time_description,
            )

            # Update state with the new flashback scene
            await compiled.aupdate_state(
                config,  # type: ignore[arg-type]
                {
                    "scenes": state.values.get("scenes", []) + [scene_id],
                    "current_scene_id": scene_id,
                    "scenes_completed": next_order + 1,
                },
            )

            # Return the values from the updated state
            new_state = await compiled.aget_state(config)  # type: ignore[arg-type]
            return new_state.values

    async def finalize(self) -> dict[str, Any]:
        """Finalize the story — mark complete in Neo4j via CanonKeeper."""
        result = await self.advance(story_complete=True)
        return result

    # ------------------------------------------------------------------
    # P-6: Story completion (active -> completed -> archived)
    # ------------------------------------------------------------------

    async def complete_story(
        self,
        current_status: str = "active",
        include_recap: bool = True,
    ) -> dict[str, Any]:
        """Mark this story as completed.

        Validates the status transition (default: ``active`` -> ``completed``),
        writes the completion to Neo4j via CanonKeeper, and optionally
        generates a story recap.

        Args:
            current_status: The current StoryStatus value (default "active").
            include_recap: Whether to generate a recap from scene history.

        Returns:
            Dict with keys: ``story_id``, ``previous_status``,
            ``new_status``, ``recap`` (if ``include_recap``).

        Raises:
            ValueError: If the transition is invalid.
        """
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        try:
            current = StoryStatus(current_status)
        except ValueError as exc:
            raise ValueError(f"Unknown current status: {current_status!r}") from exc

        if not transition_story_status(current, StoryStatus.COMPLETED):
            raise ValueError(f"Cannot transition story from {current.value!r} to {StoryStatus.COMPLETED.value!r}")

        from monitor_agents.canonkeeper.agent import CanonKeeper
        from monitor_agents.utils.metrics import AsyncTimer, metrics
        from monitor_agents.utils.resilience import get_breaker

        metrics.incr("story.complete.attempted")
        ck_breaker = get_breaker("neo4j")

        async with AsyncTimer("story.complete.duration_ms"):
            ck = CanonKeeper()
            try:
                await ck_breaker.call(ck.finalize_story, story_id=self.story_id)
                metrics.incr("story.complete.success")
            except Exception:
                metrics.incr("story.complete.failure")
                raise

        result: dict[str, Any] = {
            "story_id": str(self.story_id),
            "previous_status": current.value,
            "new_status": StoryStatus.COMPLETED.value,
        }

        if include_recap:
            try:
                result["recap"] = await build_story_recap(story_id=self.story_id, universe_id=self.universe_id)
            except Exception as exc:
                # Recap failure must not block story completion
                logger.warning("Story recap failed for %s: %s", self.story_id, exc)
                result["recap"] = {
                    "error": str(exc),
                    "scenes": [],
                    "total_scenes": 0,
                    "arc_progression": [],
                }

        return result

    async def archive_story(self, current_status: str = "completed") -> dict[str, Any]:
        """Archive a completed (or abandoned) story.

        Args:
            current_status: The current StoryStatus value (default "completed").

        Returns:
            Dict with keys: ``story_id``, ``previous_status``, ``new_status``.

        Raises:
            ValueError: If the transition is invalid.
        """
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        try:
            current = StoryStatus(current_status)
        except ValueError as exc:
            raise ValueError(f"Unknown current status: {current_status!r}") from exc

        if not transition_story_status(current, StoryStatus.ARCHIVED):
            raise ValueError(f"Cannot transition story from {current.value!r} to {StoryStatus.ARCHIVED.value!r}")

        from monitor_agents.canonkeeper.agent import CanonKeeper

        ck = CanonKeeper()
        await ck.call_tool(
            "neo4j_update_story_status",
            {
                "story_id": str(self.story_id),
                "status": StoryStatus.ARCHIVED.value,
                "completed_at": "archive",
            },
        )

        return {
            "story_id": str(self.story_id),
            "previous_status": current.value,
            "new_status": StoryStatus.ARCHIVED.value,
        }

    async def abandon_story(self, current_status: str = "active") -> dict[str, Any]:
        """Abandon a story that's still active (or planned).

        Args:
            current_status: The current StoryStatus value (default "active").

        Returns:
            Dict with keys: ``story_id``, ``previous_status``, ``new_status``.

        Raises:
            ValueError: If the transition is invalid.
        """
        from monitor_data.schemas.base import StoryStatus, transition_story_status

        try:
            current = StoryStatus(current_status)
        except ValueError as exc:
            raise ValueError(f"Unknown current status: {current_status!r}") from exc

        if not transition_story_status(current, StoryStatus.ABANDONED):
            raise ValueError(f"Cannot transition story from {current.value!r} to {StoryStatus.ABANDONED.value!r}")

        from monitor_agents.canonkeeper.agent import CanonKeeper

        ck = CanonKeeper()
        await ck.call_tool(
            "neo4j_update_story_status",
            {
                "story_id": str(self.story_id),
                "status": StoryStatus.ABANDONED.value,
                "completed_at": "abandoned",
            },
        )

        return {
            "story_id": str(self.story_id),
            "previous_status": current.value,
            "new_status": StoryStatus.ABANDONED.value,
        }


# =============================================================================
# P-6: STORY RECAP BUILDER
# =============================================================================


async def build_story_recap(story_id: UUID, universe_id: UUID) -> dict[str, Any]:
    """Build a story recap from scene history.

    The recap is a pure aggregation (no LLM) that summarizes the scenes
    completed in the story. Used by ``StoryLoop.complete_story`` to
    persist a final summary to MongoDB and surface it in the UI.

    Args:
        story_id: The story to recap.
        universe_id: The universe the story belongs to.

    Returns:
        Dict with keys: ``scenes``, ``total_scenes``, ``arc_progression``,
        ``generated_at``.
    """
    from datetime import datetime

    from monitor_data.schemas.scenes import SceneFilter

    from monitor_agents.utils.db_readers import (
        run_sync_read,
    )

    try:
        filter_obj = SceneFilter(story_id=story_id, universe_id=universe_id, limit=100)
        scenes_response = await run_sync_read(mongodb_list_scenes, filter_obj)  # type: ignore[var-annotated]
    except Exception as exc:
        logger.warning("Failed to fetch scenes for recap: %s", exc)
        scenes_response = {}

    raw_scenes: list[dict[str, Any]] = []
    if isinstance(scenes_response, dict):
        raw_scenes = list(scenes_response.get("scenes", []) or [])
    elif isinstance(scenes_response, list):
        raw_scenes = scenes_response

    arc_progression: list[str] = []
    scene_summaries: list[dict[str, Any]] = []
    for scene in raw_scenes:
        scene_dict = scene.model_dump(mode="json") if hasattr(scene, "model_dump") else dict(scene)
        scene_summaries.append(
            {
                "scene_id": str(scene_dict.get("scene_id") or scene_dict.get("id", "")),
                "title": scene_dict.get("title", "Untitled"),
                "purpose": scene_dict.get("purpose"),
                "narrative_order": scene_dict.get("narrative_order"),
            }
        )
        purpose = scene_dict.get("purpose")
        if purpose:
            arc_progression.append(str(purpose))

    return {
        "scenes": scene_summaries,
        "total_scenes": len(scene_summaries),
        "arc_progression": arc_progression,
        "generated_at": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# P-6: STORY OUTLINE / BEAT / ENCOUNTER / SCHEDULE HELPERS
# (ST-1, ST-2, ST-6, ST-7)
# =============================================================================


def build_story_outline(
    scenes: list[dict[str, Any]] | None = None,
    *,
    max_beats: int = 8,
) -> dict[str, Any]:
    """Build a story outline from scene history (ST-1).

    Pure function: groups scenes into beats by ``narrative_order`` and
    produces a hierarchical outline ready for UI display or further
    generation.

    Args:
        scenes: Optional scene dicts (must have ``title``, ``narrative_order``).
        max_beats: Maximum number of beats to include.

    Returns:
        Dict with: ``beats`` (list of beat dicts), ``total_scenes``,
        ``total_beats``.
    """
    if not scenes:
        return {"beats": [], "total_scenes": 0, "total_beats": 0}

    sorted_scenes = sorted(scenes, key=lambda s: s.get("narrative_order") or 0)
    beats: list[dict[str, Any]] = []
    for index, scene in enumerate(sorted_scenes[:max_beats]):
        beats.append(
            {
                "beat_index": index,
                "title": scene.get("title", f"Scene {index + 1}"),
                "purpose": scene.get("purpose"),
                "scene_count": 1,
            }
        )

    return {
        "beats": beats,
        "total_scenes": len(scenes),
        "total_beats": len(beats),
    }


def generate_beats(
    outline: dict[str, Any],
    *,
    beats_per_arc: int = 3,
) -> list[dict[str, Any]]:
    """Decompose an outline into individual narrative beats (ST-2).

    Pure function: takes an outline produced by ``build_story_outline``
    and produces a flat list of beats with structural labels
    (setup, complication, climax, resolution).

    Args:
        outline: An outline dict (from ``build_story_outline``).
        beats_per_arc: How many beats per arc phase.

    Returns:
        List of beat dicts with: ``beat_index``, ``label``, ``title``,
        ``arc_phase``.
    """
    base_beats = outline.get("beats", []) or []
    arc_phases = ["setup", "complication", "climax", "resolution"]
    flat_beats: list[dict[str, Any]] = []

    for beat in base_beats:
        for offset in range(beats_per_arc):
            arc_index = min(offset, len(arc_phases) - 1)
            flat_beats.append(
                {
                    "beat_index": len(flat_beats),
                    "label": f"{beat.get('title', f'Beat {len(flat_beats)}')} - {arc_phases[arc_index]}",
                    "title": beat.get("title"),
                    "arc_phase": arc_phases[arc_index],
                }
            )

    return flat_beats


def generate_encounter(
    location_type: str = "generic",
    *,
    difficulty: str = "medium",
    party_size: int = 4,
    party_level: int = 1,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a context-aware random encounter (ST-6).

    Pure function: deterministic given a seed. Used by ``WorldArchitect``
    or any scene that needs a quick encounter.

    Args:
        location_type: ``forest`` / ``dungeon`` / ``city`` / ``road`` /
            ``generic``.
        difficulty: ``easy`` / ``medium`` / ``hard`` / ``deadly``.
        party_size: Number of PCs.
        party_level: Average party level.
        seed: Optional integer seed for deterministic output.

    Returns:
        Dict with: ``location_type``, ``difficulty``, ``enemies``,
        ``seed``.
    """
    import random

    rng = random.Random(seed) if seed is not None else random

    creature_table: dict[str, list[str]] = {
        "forest": ["Wolf", "Goblin Scout", "Bandit", "Awakened Tree", "Owlbear"],
        "dungeon": ["Skeleton", "Gelatinous Cube", "Cultist", "Mind Flayer", "Beholder"],
        "city": ["Pickpocket", "Drunken Brawler", "Spy", "Doppelganger", "Mage"],
        "road": ["Bandit", "Wolves", "Caravan Guard", "Centaur", "Roc"],
        "generic": ["Goblin", "Bandit", "Wolf", "Cultist", "Mage"],
    }

    diff_multiplier = {
        "easy": 0.5,
        "medium": 1.0,
        "hard": 1.5,
        "deadly": 2.0,
    }.get(difficulty, 1.0)

    base_count = max(1, int(party_size * party_level / 4))
    enemy_count = max(1, int(base_count * diff_multiplier))

    candidates = creature_table.get(location_type, creature_table["generic"])
    enemies: list[str] = []
    for _ in range(enemy_count):
        enemies.append(rng.choice(candidates))

    return {
        "location_type": location_type,
        "difficulty": difficulty,
        "party_size": party_size,
        "party_level": party_level,
        "enemies": enemies,
        "seed": seed,
    }


def schedule_event(
    *,
    in_game_time: datetime | None = None,
    trigger_after: timedelta | None = None,
    event_type: str = "world_tick",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Schedule a time-based event trigger (ST-7).

    Pure function: returns a schedule entry that the StoryLoop can
    queue and execute on the next world tick.

    Args:
        in_game_time: Absolute in-universe time the event should fire.
        trigger_after: Relative offset from now (UTC) for the event.
        event_type: Type of event (``world_tick``, ``scene_transition``,
            ``agenda_advance``, custom).
        payload: Optional dict of event-specific data.

    Returns:
        Dict with: ``scheduled_at``, ``event_type``, ``payload``,
        ``trigger_after_seconds``.
    """
    base = in_game_time or datetime.now(UTC)
    fire_at = base + trigger_after if trigger_after is not None else base

    trigger_seconds: float | None = None
    if trigger_after is not None:
        trigger_seconds = trigger_after.total_seconds()

    return {
        "scheduled_at": fire_at.isoformat() if isinstance(fire_at, datetime) else str(fire_at),
        "event_type": event_type,
        "payload": payload or {},
        "trigger_after_seconds": trigger_seconds,
    }
