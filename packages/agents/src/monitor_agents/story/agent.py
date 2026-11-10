"""
Story Agent for MONITOR.

Encapsulates logic for arc evaluation, scene transition, and world simulation.
LAYER: 2 (agents)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, TYPE_CHECKING
from uuid import UUID

from monitor_agents.base import BaseAgent
from monitor_agents.agent_factory import get_agent_factory

if TYPE_CHECKING:
    from monitor_agents.loops.story_loop import StoryState

logger = logging.getLogger(__name__)

# The arc phases a story moves through. The model picks one; the phase order
# itself is a contract, not a heuristic.
ARC_PHASES = ("rising_action", "climax", "falling_action", "resolution", "new_thread")

# Plot-thread statuses that mean the thread is no longer open.
_CLOSED_THREAD_STATUSES = {"resolved", "closed", "abandoned"}

# The time a story falls back to when the world cannot say when it starts.
# It is a placeholder, not a world date: every story that can reach the
# world seed or the model gets a date of its own.
_FALLBACK_IN_GAME_TIME = datetime(1000, 1, 1, 12, 0, tzinfo=UTC)


def _parse_instant(value: Any) -> datetime | None:
    """Read a timestamp from a model answer, a tool payload or a datetime.

    Returns ``None`` for anything that is not a timestamp, so a malformed
    answer never becomes a story's clock.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _render_ledger_for_prompt(entries: list[dict[str, Any]]) -> str:
    """Render ledger entries as one line each, oldest first."""
    lines: list[str] = []
    for entry in entries:
        summary = str(entry.get("summary") or "").strip().replace("\n", " ")
        if not summary:
            continue
        lines.append(f"Scene {entry.get('scene_index', '?')}: {summary}")
    return "\n".join(lines)


def _render_turns_for_prompt(turns: list[dict[str, Any]]) -> str:
    """Render the turns of a scene as ``speaker: text`` lines, oldest first."""
    lines: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        speaker = str(turn.get("speaker") or turn.get("name") or "GM")
        text = str(turn.get("text") or turn.get("content") or "").strip()
        if not text:
            continue
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _parse_json_list(raw: Any) -> list[Any]:
    """Parse a model answer that should be a JSON list.

    Models answer with a JSON array, sometimes wrapped in prose or fenced in
    a code block. Anything that cannot be read as a list yields an empty
    list rather than raising, so one malformed field never loses the rest of
    the answer.
    """
    if isinstance(raw, list):
        return raw
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_state_changes(raw: Any) -> list[dict[str, str]]:
    """Parse the model's state changes into ``who``/``what``/``where`` rows."""
    changes: list[dict[str, str]] = []
    for item in _parse_json_list(raw):
        if not isinstance(item, dict):
            continue
        changes.append(
            {
                "who": str(item.get("who") or "").strip(),
                "what": str(item.get("what") or "").strip(),
                "where": str(item.get("where") or "").strip(),
            }
        )
    return changes


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

        from monitor_data.schemas.llm_config import ModelRole

        from monitor_agents.dspy_runtime import dspy_context_for

        planner = StoryPlannerModule()

        def _plan() -> dict[str, Any]:
            # DSPy only has a model inside a bound context; without one every
            # call fails with "No LM is loaded".
            with dspy_context_for("story_planner", ModelRole.STANDARD):
                return planner.forward(
                    arc_label=state.arc_label,
                    active_threads=", ".join(state.active_threads),
                    recent_scenes="; ".join(recent) if recent else "None",
                    world_moves="; ".join(state.world_moves) if state.world_moves else "None",
                )

        # DSPy calls are sync, wrap in to_thread to avoid blocking the event loop
        return await asyncio.to_thread(_plan)

    async def write_ledger_entry(
        self,
        state: StoryState,
        *,
        scene_id: UUID,
        scene_turns: list[dict[str, Any]],
        agenda_moves: list[str] | None = None,
        start_time: datetime,
        end_time: datetime,
        scene_index: int | None = None,
    ) -> dict[str, Any]:
        """
        Write the ledger entry for the scene that just ended (ST-1, P-8).

        One STANDARD-tier call turns the scene into a 150-300 word summary, a
        list of state changes and the questions it left open. The entry is
        appended to the story's ledger in MongoDB — never overwritten — so the
        campaign keeps every scene it has played.

        Args:
            state: The story state the scene belongs to.
            scene_id: The scene that just ended.
            scene_turns: The scene's turns, oldest first.
            agenda_moves: What the world did while the scene was playing.
            start_time: The scene's in-game start time.
            end_time: The scene's in-game end time.
            scene_index: The scene's position in the campaign.

        Returns:
            The stored ledger entry as a plain dict (empty when the entry
            could not be written; the failure is recorded).
        """
        from monitor_data.schemas.roleplay_errors import (
            RoleplayErrorCategory,
            RoleplayErrorSource,
        )
        from monitor_data.schemas.stories import (
            StoryLedgerEntryCreate,
            StoryLedgerStateChange,
        )

        from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
        from monitor_agents.story.story import StoryLedgerModule

        moves = list(agenda_moves or [])
        turns_text = _render_turns_for_prompt(scene_turns)
        previous_text = _render_ledger_for_prompt(list(state.ledger_entries))
        scene_time = f"{start_time.isoformat()} -> {end_time.isoformat()}"

        summary = ""
        state_changes: list[dict[str, str]] = []
        open_questions: list[str] = []

        module = StoryLedgerModule()

        def _write() -> Any:
            return module.forward(
                scene_turns=turns_text or "(the scene had no recorded turns)",
                previous_ledger=previous_text or "(this is the first scene)",
                agenda_moves="; ".join(moves) if moves else "(the world stood still)",
                scene_time=scene_time,
            )

        try:
            prediction = await asyncio.to_thread(_write)
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in write_ledger_entry)
            # The ledger must not cost the player their scene transition, but
            # the failure has to stay visible.
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.STORY_LOOP,
                category=RoleplayErrorCategory.LLM,
                message=f"Story ledger write failed: {exc}",
                fatal=False,
                universe_id=state.universe_id,
                story_id=state.story_id,
                scene_id=scene_id,
            )
            summary = self._fallback_summary(turns_text)
        else:
            summary = str(getattr(prediction, "summary", "") or "").strip()
            state_changes = _parse_state_changes(getattr(prediction, "state_changes", ""))
            open_questions = [
                str(question).strip()
                for question in _parse_json_list(getattr(prediction, "open_questions", ""))
                if str(question).strip()
            ]
            if not summary:
                summary = self._fallback_summary(turns_text)

        params = StoryLedgerEntryCreate(
            story_id=state.story_id,
            universe_id=state.universe_id,
            scene_id=scene_id,
            scene_index=state.scenes_completed if scene_index is None else scene_index,
            summary=summary,
            state_changes=[StoryLedgerStateChange(**change) for change in state_changes],
            open_questions=open_questions,
            start_time=start_time,
            end_time=end_time,
            world_moves=moves,
            arc_label=state.arc_label,
            tension_score=state.tension_score,
        )

        try:
            await self.call_tool(
                "mongodb_append_story_ledger_entry",
                {"params": params.model_dump(mode="json")},
            )
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in write_ledger_entry)
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.STORY_LOOP,
                category=RoleplayErrorCategory.UNKNOWN,
                message=f"Story ledger append failed: {exc}",
                fatal=False,
                universe_id=state.universe_id,
                story_id=state.story_id,
                scene_id=scene_id,
            )
            return {}

        entry = params.model_dump(mode="json")
        entry["summary"] = summary
        entry["state_changes"] = state_changes
        entry["open_questions"] = open_questions
        logger.info(
            "Ledger entry written for scene %s (%d change(s), %d open question(s))",
            scene_id,
            len(state_changes),
            len(open_questions),
        )
        return entry

    @staticmethod
    def _fallback_summary(turns_text: str) -> str:
        """Mechanical summary used when the model call fails.

        It transcribes what was said — it does not judge it — so the ledger
        keeps a record of the scene even when the model is unavailable.
        """
        text = " ".join(turns_text.split())
        if not text:
            return "The scene ended without a recorded exchange."
        return text[:2000]

    async def seed_in_game_time(self, universe_id: UUID, story_id: UUID) -> tuple[datetime, str]:
        """Work out the in-game time a story starts on (ST-1).

        The time comes from the world, in this order:

        1. the story's own ``start_time_ref`` (an authored date);
        2. the world seed, when the pre-play flow installed one;
        3. a model estimate read from the universe itself;
        4. a documented fallback, recorded so it can be looked up.

        Returns:
            The start time and where it came from.
        """
        story = await self._read_story(story_id)
        if story:
            authored = story.get("start_time_ref")
            parsed = _parse_instant(authored)
            if parsed is not None:
                return parsed, "story"

        seeded = await self._ask_world_seed(universe_id)
        if seeded is not None:
            return seeded, "world_seed"

        estimated = await self._estimate_start_time(universe_id)
        if estimated is not None:
            return estimated, "model"

        logger.warning(
            "No in-game time could be read for universe %s; falling back to the default epoch",
            universe_id,
        )
        return _FALLBACK_IN_GAME_TIME, "fallback"

    async def _read_story(self, story_id: UUID) -> dict[str, Any] | None:
        """Read the story's Neo4j record (read-only)."""
        try:
            raw = await self.call_tool("neo4j_get_story", {"story_id": str(story_id)})
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _read_story)
            logger.warning("Could not read story %s: %s", story_id, exc)
            return None
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return None
        return raw if isinstance(raw, dict) else None

    async def _read_universe(self, universe_id: UUID) -> dict[str, Any] | None:
        """Read the universe's Neo4j record (read-only)."""
        try:
            raw = await self.call_tool("neo4j_get_universe", {"universe_id": str(universe_id)})
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _read_universe)
            logger.warning("Could not read universe %s: %s", universe_id, exc)
            return None
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return None
        return raw if isinstance(raw, dict) else None

    async def _ask_world_seed(self, universe_id: UUID) -> datetime | None:
        """Ask the world seed for the universe's starting date.

        The world seed is the pre-play flow's answer to "when does this world
        start?". It is optional: when it is not installed, the caller falls
        back to a model estimate.
        """
        try:
            from monitor_agents import world_seed  # type: ignore[attr-defined]
        except ImportError:
            return None

        estimate = getattr(world_seed, "estimate_start_time", None)
        if callable(estimate):
            result = estimate(universe_id)
        else:
            agent_cls = getattr(world_seed, "WorldSeed", None)
            if agent_cls is None:
                return None
            method = getattr(agent_cls, "estimate_start_time", None)
            if method is None:
                return None
            result = method(agent_cls(), universe_id)

        if hasattr(result, "__await__"):
            result = await result
        return _parse_instant(result)

    async def _estimate_start_time(self, universe_id: UUID) -> datetime | None:
        """Ask the model for a starting date that fits the universe."""
        from monitor_data.schemas.llm_config import ModelRole

        from monitor_agents.story.story import StoryTimeSeedModule

        universe = await self._read_universe(universe_id)
        if not universe:
            return None

        module = StoryTimeSeedModule()

        def _estimate() -> Any:
            return module.forward(
                universe_name=str(universe.get("name") or ""),
                universe_description=str(universe.get("description") or ""),
                genre=str(universe.get("genre") or ""),
                tech_level=str(universe.get("tech_level") or ""),
                role=ModelRole.STANDARD,
            )

        try:
            prediction = await asyncio.to_thread(_estimate)
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _estimate_start_time)
            logger.warning("Could not estimate the start time of universe %s: %s", universe_id, exc)
            return None
        return _parse_instant(getattr(prediction, "start_time", ""))

    async def _fetch_plot_threads(self, story_id: UUID) -> list[dict[str, Any]]:
        """Read the story's plot threads from Neo4j (read-only)."""
        try:
            raw = await self.call_tool(
                "neo4j_list_plot_threads",
                {"params": {"story_id": str(story_id), "limit": 50}},
            )
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _fetch_plot_threads)
            logger.warning("Could not read plot threads for story %s: %s", story_id, exc)
            return []

        payload = raw
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return []
        if isinstance(payload, dict):
            threads = payload.get("threads") or []
        elif isinstance(payload, list):
            threads = payload
        else:
            threads = []
        return [thread for thread in threads if isinstance(thread, dict)]

    async def evaluate_arc(self, state: StoryState) -> dict[str, Any]:
        """
        Evaluate the narrative arc after each scene (ST-1).

        The arc is judged from what happened: the story's ledger (one entry
        per finished scene) and the plot threads recorded in Neo4j. A model
        reads both and returns the phase, the tension, the threads that moved
        and the threads that closed.

        The scene budget stays an upper bound: a story that reaches it
        resolves, but a story never reaches it early because a counter said
        so.
        """
        from monitor_data.schemas.roleplay_errors import (
            RoleplayErrorCategory,
            RoleplayErrorSource,
        )

        from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
        from monitor_agents.story.story import StoryArcModule

        scenes_done = state.scenes_completed
        budget = state.scene_budget
        ledger_entries = list(state.ledger_entries)
        plot_threads = await self._fetch_plot_threads(state.story_id)

        ledger_text = _render_ledger_for_prompt(ledger_entries) or "(no scenes have been played yet)"
        threads_text = self._render_threads_for_prompt(plot_threads)
        moves_text = "; ".join(state.world_moves) if state.world_moves else "(none)"

        module = StoryArcModule()

        def _judge() -> Any:
            return module.forward(
                ledger=ledger_text,
                plot_threads=threads_text,
                current_phase=state.arc_label,
                current_tension=str(state.tension_score),
                scenes_completed=str(scenes_done),
                scene_budget=str(budget),
                agenda_moves=moves_text,
            )

        try:
            prediction = await asyncio.to_thread(_judge)
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in evaluate_arc)
            # A story without an arc reading keeps running on the arc it
            # already had; the failure is recorded so it can be looked up.
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.STORY_LOOP,
                category=RoleplayErrorCategory.LLM,
                message=f"Story arc evaluation failed: {exc}",
                fatal=False,
                universe_id=state.universe_id,
                story_id=state.story_id,
            )
            label = state.arc_label if state.arc_label in ARC_PHASES else "rising_action"
            tension = state.tension_score
            advanced: list[str] = []
            closed: list[str] = []
            model_complete = False
        else:
            label = str(getattr(prediction, "arc_phase", "") or "").strip()
            if label not in ARC_PHASES:
                label = state.arc_label if state.arc_label in ARC_PHASES else "rising_action"
            try:
                tension = float(getattr(prediction, "tension", state.tension_score))
            except (TypeError, ValueError):
                tension = state.tension_score
            tension = max(0.0, min(1.0, tension))
            advanced = [str(item).strip() for item in _parse_json_list(getattr(prediction, "advanced_threads", ""))]
            closed = [str(item).strip() for item in _parse_json_list(getattr(prediction, "closed_threads", ""))]
            model_complete = bool(getattr(prediction, "story_complete", False))

        active_threads, completed_threads = self._apply_thread_verdicts(
            state,
            plot_threads=plot_threads,
            advanced=advanced,
            closed=closed,
        )

        # The budget is an upper bound, not the driver: a story that has used
        # its budget resolves whether or not the model says so.
        story_complete = model_complete and not active_threads
        if scenes_done >= budget:
            label = "resolution"
            story_complete = True

        # P-6: Automated Story Outlining - Call DSPy planner
        plan = await self._plan_next_scene(state)
        next_type = plan.get("next_scene_type") or self._default_scene_type(label)
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
            "completed_threads": completed_threads,
            "next_scene_type": next_type,
            "scene_hook": scene_hook,
            "story_complete": story_complete,
            "scenes_history": history,
        }

    @staticmethod
    def _render_threads_for_prompt(plot_threads: list[dict[str, Any]]) -> str:
        """Render plot threads as ``title (status)`` lines for the model."""
        lines: list[str] = []
        for thread in plot_threads:
            title = str(thread.get("title") or thread.get("id") or "").strip()
            if not title:
                continue
            status = str(thread.get("status") or "open").strip()
            lines.append(f"- {title} ({status})")
        return "\n".join(lines) if lines else "(the story has no plot threads yet)"

    @staticmethod
    def _default_scene_type(label: str) -> str:
        """The scene type that fits an arc phase when the planner is silent."""
        return {
            "rising_action": "exploration",
            "climax": "combat",
            "falling_action": "dialogue",
            "resolution": "rest",
            "new_thread": "revelation",
        }.get(label, "action")

    @staticmethod
    def _apply_thread_verdicts(
        state: StoryState,
        *,
        plot_threads: list[dict[str, Any]],
        advanced: list[str],
        closed: list[str],
    ) -> tuple[list[str], list[str]]:
        """Work out which threads are open and which are done.

        The plot threads recorded in Neo4j are the story's real threads; the
        model only says which of them moved and which closed. A thread the
        model closes stops being open, and a thread the model closes that the
        story has never heard of is still recorded as done.
        """
        open_titles: list[str] = []
        known_titles: set[str] = set()
        for thread in plot_threads:
            title = str(thread.get("title") or "").strip()
            if not title:
                continue
            known_titles.add(title.lower())
            status = str(thread.get("status") or "open").strip().lower()
            if status in _CLOSED_THREAD_STATUSES:
                continue
            open_titles.append(title)

        closed_keys = {item.lower() for item in closed if item}
        active_threads = [title for title in open_titles if title.lower() not in closed_keys]

        completed_threads = list(state.completed_threads)
        for item in closed:
            name = item.strip()
            if not name:
                continue
            if name not in completed_threads:
                completed_threads.append(name)

        # A thread the model reports as advanced stays open.
        for item in advanced:
            name = item.strip()
            if not name:
                continue
            if name.lower() in {title.lower() for title in completed_threads}:
                continue
            if name not in active_threads and name.lower() in known_titles:
                active_threads.append(name)

        return active_threads, completed_threads

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
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in transition_scene)
            logger.warning("Procedural population failed for scene %s: %s", scene_id, exc)

        return {
            "scenes": state.scenes + [scene_id],
            "current_scene_id": scene_id,
            # The caller counts the scene it just finished; the transition
            # only opens the next one.
            "scenes_completed": state.scenes_completed,
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
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in simulate_world_advance)
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
