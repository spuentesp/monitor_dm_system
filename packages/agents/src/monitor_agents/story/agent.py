"""
Story Agent for MONITOR.

Encapsulates logic for arc evaluation, scene transition, and world simulation.
LAYER: 2 (agents)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, TYPE_CHECKING
from uuid import UUID

from monitor_agents.base import BaseAgent
from monitor_agents.agent_factory import get_agent_factory

if TYPE_CHECKING:
    from monitor_agents.loops.story_loop import StoryState

logger = logging.getLogger(__name__)


class StoryAgent(BaseAgent):
    """Agent responsible for story-level narrative arc and world simulation."""

    def __init__(self, agent_id: str = "story-1"):
        super().__init__(agent_type="story", agent_id=agent_id)

    async def run(self) -> None:
        """Main agent execution method. Not used directly in loop nodes."""
        pass

    async def _plan_next_scene(self, state: StoryState) -> dict[str, Any]:
        """
        DSPy-powered story planning helper.
        Wraps synchronous DSPy calls in asyncio.to_thread to prevent blocking.
        """
        from monitor_agents.story.story import StoryPlannerModule

        # Format recent scenes for prompt context
        recent = []
        for s in state.scenes_history[-3:]:  # Last 3 scenes
            idx = s.get("scene_index", "?")
            label = s.get("arc_label", "unknown")
            recent.append(f"Scene {idx} ({label})")

        planner = StoryPlannerModule()
        # DSPy calls are sync, wrap in to_thread to avoid blocking the event loop
        result = await asyncio.to_thread(
            planner.forward,
            arc_label=state.arc_label,
            active_threads=", ".join(state.active_threads),
            recent_scenes="; ".join(recent) if recent else "None",
        )
        return result

    async def evaluate_arc(self, state: StoryState) -> dict[str, Any]:
        """
        Evaluate the narrative arc after each scene.

        Uses heuristics based on scenes_completed, tension trends, and
        thread counts to classify the arc phase.  A DSPy-powered version
        can override this with LLM-driven evaluation in the future.
        """
        scenes_done = state.scenes_completed
        active = len(state.active_threads)
        completed_threads = len(state.completed_threads)
        tension = state.tension_score

        # Heuristic arc evaluation
        if scenes_done <= 2:
            label = "rising_action"
            tension = min(0.5, tension + 0.15 * scenes_done)
        elif tension >= 0.7 and active >= 2:
            label = "climax"
            tension = min(1.0, tension + 0.1)
        elif completed_threads > active and tension > 0.5:
            label = "falling_action"
            tension = max(0.3, tension - 0.15)
        elif active == 0 and completed_threads > 0:
            label = "resolution"
            tension = max(0.1, tension - 0.2)
        elif active == 0 and scenes_done >= 3:
            label = "new_thread"
            tension = 0.3
        else:
            label = "rising_action"
            tension = min(0.6, tension + 0.1)

        # Suggest next scene type based on arc phase
        next_type = {
            "rising_action": "exploration",
            "climax": "combat",
            "falling_action": "dialogue",
            "resolution": "rest",
            "new_thread": "revelation",
        }.get(label, "action")

        # Auto-complete story after resolution if no new threads
        story_complete = label == "resolution" and active == 0

        # Seed threads if none exist yet (world-building phase)
        if not state.active_threads and scenes_done <= 1:
            active_threads = ["central_conflict", "character_motivation"]
        else:
            active_threads = state.active_threads

        # P-6: Automated Story Outlining - Call DSPy planner
        plan = await self._plan_next_scene(state)
        next_type = plan.get("next_scene_type") or next_type
        scene_hook = plan.get("plot_hook")

        logger.info(
            "Arc eval: scenes=%d label=%s tension=%.2f active_threads=%d next=%s hook=%s complete=%s",
            scenes_done,
            label,
            tension,
            len(active_threads),
            next_type,
            scene_hook,
            story_complete,
        )

        # Track scene in history
        history_entry = {
            "scene_index": scenes_done,
            "arc_label": label,
            "tension_score": tension,
            "active_threads": active_threads,
            "scene_type": next_type,
            "scene_hook": scene_hook,
        }
        history = list(state.scenes_history) + [history_entry]

        return {
            "arc_label": label,
            "tension_score": tension,
            "active_threads": active_threads,
            "next_scene_type": next_type,
            "scene_hook": scene_hook,
            "story_complete": story_complete,
            "scenes_history": history,
        }

    def _arc_label_to_purpose(self, arc_label: str) -> str:
        """Map arc phase labels to human-readable scene purposes."""
        return {
            "rising_action": "Tension Building",
            "climax": "Climactic Confrontation",
            "falling_action": "Aftermath",
            "resolution": "Resolution",
            "new_thread": "New Development",
        }.get(arc_label, "Story Continues")

    async def transition_scene(self, state: StoryState) -> dict[str, Any]:
        """
        Create the next scene using arc evaluation context.

        Uses ``next_scene_type`` from arc evaluation to set the scene purpose.
        If no arc evaluation ran yet, defaults to a balanced next scene.
        """
        if state.story_complete:
            return {}

        next_order = state.scenes_completed
        purpose = self._arc_label_to_purpose(state.arc_label)
        scene_type_hint = state.next_scene_type or "exploration"

        from monitor_agents.loops.story_loop import _create_scene

        scene_id = await _create_scene(
            state.story_id,
            state.universe_id,
            order=next_order,
            purpose=f"{purpose} ({scene_type_hint})",
        )

        # P-19: Procedural Scene Population
        # Seed the new scene with entities from Random Tables
        from monitor_agents.world_architect.agent import WorldArchitect

        architect = WorldArchitect()
        try:
            await architect.populate_scene_procedurally(
                universe_id=state.universe_id,
                scene_id=scene_id,
                location_type=scene_type_hint,
            )
        except Exception as exc:
            logger.warning("Procedural population failed for scene %s: %s", scene_id, exc)

        return {
            "scenes": state.scenes + [scene_id],
            "current_scene_id": scene_id,
            "scenes_completed": state.scenes_completed + 1,
            "next_scene_type": None,  # consumed
        }

    async def simulate_world_advance(self, state: StoryState) -> dict[str, Any]:
        """
        S-Tick: Resolve off-screen faction agency and environmental shifts.

        This node runs after a scene ends but before a new one starts.
        It advances the world clock and calls the Simulacrum Council.
        """
        from monitor_data.schemas.facts import FactFilter
        from monitor_data.tools.neo4j_tools.entities import neo4j_tick_agendas

        from monitor_agents.simulacrum.agent import SimulacrumAgent
        from monitor_agents.utils.db_readers import (
            neo4j_list_facts,
            run_sync_read,
        )

        # 1. Advance the absolute world clock
        new_time = state.in_game_time + timedelta(minutes=state.last_scene_duration_minutes)

        # 2. Tick NPC Agendas (S-Tick)
        try:
            agenda_moves = await asyncio.to_thread(neo4j_tick_agendas, str(state.universe_id))
            if agenda_moves:
                logger.info("NPC Agendas advanced: %s", agenda_moves)
        except Exception as exc:
            logger.warning("NPC Agenda tick failed for universe %s: %s", state.universe_id, exc)

        # 3. Fetch context for simulation
        high_impact = await run_sync_read(  # type: ignore[var-annotated]
            neo4j_list_facts, FactFilter(universe_id=state.universe_id, min_magnitude=5, limit=10)
        )

        # 3. Run Simulacrum council
        sim = SimulacrumAgent()
        proposals = await sim.run_world_tick(
            universe_id=state.universe_id,
            current_time=new_time,
            recent_high_impact_events=[f.model_dump() for f in high_impact],
            world_tone=state.world_tone,
        )

        # 4. Commit simulation outcomes via CanonKeeper
        if proposals:
            factory = get_agent_factory()
            keeper = factory.create_canonkeeper()
            # Simulation proposals are auto-accepted as they are world-truth moves
            for p in proposals:
                change_type = p.get("change_type")
                actor_id = p["content"].get("actor_id")
                actor_name = p["content"].get("actor_name", "Unknown")
                move_details = p["content"].get("move_details", p["summary"])

                if change_type == "clock_advance" and actor_id:
                    # Progress a specific objective clock in Neo4j
                    # For now we represent this as a Fact + property update on the actor
                    await keeper.create_fact(
                        {
                            "universe_id": str(state.universe_id),
                            "statement": f"{actor_name} advances agenda: {move_details}",
                            "fact_type": "occurrence",
                            "magnitude": p.get("magnitude", 5),
                            "scope": p.get("scope", "regional"),
                            "time_ref": new_time.isoformat(),
                            "properties": p.get("content", {}),
                            "entity_ids": [UUID(actor_id)] if actor_id else [],
                        }
                    )

                elif change_type == "entity_update" and actor_id:
                    # Future: implement direct entity property updates in CanonKeeper
                    # For now, record the shift as a Fact
                    await keeper.create_fact(
                        {
                            "universe_id": str(state.universe_id),
                            "statement": f"{actor_name} state shift: {move_details}",
                            "fact_type": "state",
                            "magnitude": p.get("magnitude", 4),
                            "scope": p.get("scope", "local"),
                            "time_ref": new_time.isoformat(),
                            "properties": p.get("content", {}),
                            "entity_ids": [UUID(actor_id)] if actor_id else [],
                        }
                    )

                else:
                    # Default: create an occurrence Fact
                    fact_params = {
                        "universe_id": str(state.universe_id),
                        "statement": f"{actor_name}: {move_details}",
                        "fact_type": "occurrence",
                        "magnitude": p.get("magnitude", 5),
                        "scope": p.get("scope", "regional"),
                        "canon_level": "canon",
                        "confidence": 1.0,
                        "authority": "system",
                        "time_ref": new_time.isoformat(),
                        "properties": p.get("content", {}),
                        "entity_ids": [UUID(actor_id)] if actor_id else [],
                    }
                    await keeper.create_fact(fact_params)

        logger.info(f"World tick {state.world_ticks} resolved. Time: {new_time}")

        return {
            "in_game_time": new_time,
            "world_ticks": state.world_ticks + 1,
            "last_scene_duration_minutes": 0,  # Reset for next scene
        }

    async def finalize_story(self, state: StoryState) -> dict[str, Any]:
        """
        Write story completion to Neo4j via CanonKeeper.

        Writes: Story.status = "completed", story recap to MongoDB.
        """
        from monitor_agents.canonkeeper.agent import CanonKeeper

        ck = CanonKeeper()
        await ck.finalize_story(story_id=state.story_id)
        return {}
