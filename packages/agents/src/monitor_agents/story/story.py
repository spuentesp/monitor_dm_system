"""
Story Planner — DSPy Signatures & Modules for narrative planning.

LAYER: 2 (agents)
IMPORTS FROM: dspy
CALLED BY: StoryLoop

Determines next scene types and plot hooks based on arc state.
"""

from __future__ import annotations

import dspy
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.dspy_runtime import dspy_context_for


class StoryPlannerSignature(dspy.Signature):  # type: ignore[misc]
    """Determine the next scene type and plot hook based on the current story arc."""

    arc_label = dspy.InputField()
    active_threads = dspy.InputField()
    recent_scenes = dspy.InputField()
    world_moves = dspy.InputField(desc="What the world did between scenes (NPC agenda moves).")
    next_scene_type = dspy.OutputField(desc="e.g., combat, social, exploration, downtime")
    plot_hook = dspy.OutputField(desc="A one-sentence hook for the next scene.")


class StoryPlannerModule(dspy.Module):  # type: ignore[misc]
    """Module for planning the next narrative beat."""

    def __init__(self) -> None:
        super().__init__()
        self.plan = dspy.ChainOfThought(StoryPlannerSignature)

    def forward(
        self,
        arc_label: str,
        active_threads: str,
        recent_scenes: str,
        world_moves: str = "None",
    ) -> dict[str, str]:
        result = self.plan(
            arc_label=arc_label,
            active_threads=active_threads,
            recent_scenes=recent_scenes,
            world_moves=world_moves,
        )
        return {"next_scene_type": result.next_scene_type, "plot_hook": result.plot_hook}


class StoryLedgerSignature(dspy.Signature):  # type: ignore[misc]
    """Write the ledger entry for a scene that has just ended.

    The ledger is the campaign's memory: what happened, what changed, what is
    still open, and when it happened in the world's own time.
    """

    scene_turns: str = dspy.InputField(desc="The turns of the scene that just ended, oldest first.")
    previous_ledger: str = dspy.InputField(desc="Earlier ledger entries, one line each (may be empty).")
    agenda_moves: str = dspy.InputField(desc="What the world did while the scene was playing.")
    scene_time: str = dspy.InputField(desc="The scene's in-game start and end time.")

    summary: str = dspy.OutputField(
        desc="A 150-300 word summary of the scene: what the characters did, what it changed, "
        "and what it set up. Plain prose, no headings."
    )
    state_changes: str = dspy.OutputField(
        desc='JSON list of objects with "who", "what" and "where" keys. One per meaningful change.'
    )
    open_questions: str = dspy.OutputField(desc="JSON list of strings: the questions the scene left open.")


class StoryLedgerModule(dspy.Module):  # type: ignore[misc]
    """Module that turns a finished scene into a ledger entry."""

    def __init__(self) -> None:
        super().__init__()
        self.write = dspy.ChainOfThought(StoryLedgerSignature)

    def forward(
        self,
        scene_turns: str,
        previous_ledger: str,
        agenda_moves: str,
        scene_time: str,
        role: ModelRole | None = None,
    ) -> dspy.Prediction:
        with dspy_context_for("story_ledger", role or ModelRole.STANDARD):
            return self.write(
                scene_turns=scene_turns,
                previous_ledger=previous_ledger,
                agenda_moves=agenda_moves,
                scene_time=scene_time,
            )


class StoryArcSignature(dspy.Signature):  # type: ignore[misc]
    """Judge where the campaign stands after a scene, from what actually happened.

    The judge reads the story's ledger and its plot threads. The scene count is
    only an upper bound: the arc moves when the story's own events move it.
    """

    ledger: str = dspy.InputField(desc="The story's ledger entries, oldest first.")
    plot_threads: str = dspy.InputField(desc="The story's plot threads with their status.")
    current_phase: str = dspy.InputField(desc="The arc phase the story is in now.")
    current_tension: str = dspy.InputField(desc="The current tension, 0.0 to 1.0.")
    scenes_completed: str = dspy.InputField(desc="How many scenes have been played.")
    scene_budget: str = dspy.InputField(desc="The upper bound on scenes for this story.")
    agenda_moves: str = dspy.InputField(desc="What the world did between scenes.")

    arc_phase: str = dspy.OutputField(desc="One of: rising_action, climax, falling_action, resolution, new_thread.")
    tension: float = dspy.OutputField(desc="Narrative tension from 0.0 (calm) to 1.0 (peak).")
    advanced_threads: str = dspy.OutputField(desc="JSON list of thread names that moved forward in this scene.")
    closed_threads: str = dspy.OutputField(desc="JSON list of thread names that were resolved.")
    story_complete: bool = dspy.OutputField(
        desc="True only when the story's conflict is resolved and nothing is left open."
    )
    reasoning: str = dspy.OutputField(desc="Why the phase and threads are what they are.")


class StoryArcModule(dspy.Module):  # type: ignore[misc]
    """Module that judges the campaign's arc from the ledger and the plot threads."""

    def __init__(self) -> None:
        super().__init__()
        self.judge = dspy.ChainOfThought(StoryArcSignature)

    def forward(
        self,
        ledger: str,
        plot_threads: str,
        current_phase: str,
        current_tension: str,
        scenes_completed: str,
        scene_budget: str,
        agenda_moves: str,
        role: ModelRole | None = None,
    ) -> dspy.Prediction:
        with dspy_context_for("story_arc", role or ModelRole.STANDARD):
            return self.judge(
                ledger=ledger,
                plot_threads=plot_threads,
                current_phase=current_phase,
                current_tension=current_tension,
                scenes_completed=scenes_completed,
                scene_budget=scene_budget,
                agenda_moves=agenda_moves,
            )


class StoryTimeSeedSignature(dspy.Signature):  # type: ignore[misc]
    """Estimate the in-world date a campaign starts on, from the world itself."""

    universe_name: str = dspy.InputField(desc="The name of the universe the story runs in.")
    universe_description: str = dspy.InputField(desc="What the universe is: setting, era, technology.")
    genre: str = dspy.InputField(desc="The universe's genre.")
    tech_level: str = dspy.InputField(desc="The universe's technology level.")

    start_time: str = dspy.OutputField(
        desc="The date the campaign starts on, as an ISO-8601 timestamp (YYYY-MM-DDTHH:MM:SS+00:00). "
        "Use a year that fits the setting, not the present day."
    )
    reasoning: str = dspy.OutputField(desc="Why that date fits the world.")


class StoryTimeSeedModule(dspy.Module):  # type: ignore[misc]
    """Module that estimates a world's starting date for in-game time."""

    def __init__(self) -> None:
        super().__init__()
        self.estimate = dspy.ChainOfThought(StoryTimeSeedSignature)

    def forward(
        self,
        universe_name: str,
        universe_description: str,
        genre: str,
        tech_level: str,
        role: ModelRole | None = None,
    ) -> dspy.Prediction:
        with dspy_context_for("story_time_seed", role or ModelRole.STANDARD):
            return self.estimate(
                universe_name=universe_name,
                universe_description=universe_description,
                genre=genre,
                tech_level=tech_level,
            )


class StoryXpAwardSignature(dspy.Signature):  # type: ignore[misc]
    """
    Judge how much experience a finished scene is worth, from the scene's
    own ledger entry — what happened in it, what it changed in the world,
    and where the arc stood.

    Rules:
    - The award is a whole number between 1 and 10. A quiet scene that
      simply happened is worth 1; a scene that changed the world, resolved
      a thread, or carried the arc's hardest moments is worth the most.
    - Judge the scene described by the entry — never its word count or its
      number of turns.
    - Keep the reason to one line, in the voice of a GM telling the player
      why the scene earned what it earned.
    """

    ledger_entry: str = dspy.InputField(
        desc="The scene's ledger entry: summary, state changes, open questions, in-game start/end times, arc phase."
    )
    xp_award: int = dspy.OutputField(desc="Experience the scene is worth: a whole number between 1 and 10.")
    reason: str = dspy.OutputField(desc="One line: why the scene is worth that much.")


class StoryXpAwardModule(dspy.Module):  # type: ignore[misc]
    """Judge a finished scene's experience award from its ledger entry."""

    def __init__(self) -> None:
        super().__init__()
        self.judge = dspy.ChainOfThought(StoryXpAwardSignature)

    def forward(self, ledger_entry: str, role: ModelRole | None = None) -> dspy.Prediction:
        # LIGHT role: one bounded judgment over one entry.
        with dspy_context_for("story_xp_award", role or ModelRole.LIGHT):
            return self.judge(ledger_entry=ledger_entry)
