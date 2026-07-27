"""
Story Planner — DSPy Signatures & Modules for narrative planning.

LAYER: 2 (agents)
IMPORTS FROM: dspy
CALLED BY: StoryLoop

Determines next scene types and plot hooks based on arc state.
"""

from __future__ import annotations

import dspy


class StoryPlannerSignature(dspy.Signature):  # type: ignore[misc]
    """Determine the next scene type and plot hook based on the current story arc."""

    arc_label = dspy.InputField()
    active_threads = dspy.InputField()
    recent_scenes = dspy.InputField()
    next_scene_type = dspy.OutputField(desc="e.g., combat, social, exploration, downtime")
    plot_hook = dspy.OutputField(desc="A one-sentence hook for the next scene.")


class StoryPlannerModule(dspy.Module):  # type: ignore[misc]
    """Module for planning the next narrative beat."""

    def __init__(self) -> None:
        super().__init__()
        self.plan = dspy.ChainOfThought(StoryPlannerSignature)

    def forward(self, arc_label: str, active_threads: str, recent_scenes: str) -> dict[str, str]:
        result = self.plan(arc_label=arc_label, active_threads=active_threads, recent_scenes=recent_scenes)
        return {"next_scene_type": result.next_scene_type, "plot_hook": result.plot_hook}
