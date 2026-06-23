"""
DSPy Signatures and Modules for the Recap agent.

LAYER: 2 (agents)
IMPORTS FROM: dspy
"""

import dspy
from typing import Optional
from monitor_agents.dspy_runtime import dspy_context_for
from monitor_data.schemas.llm_config import ModelRole


class RecapSignature(dspy.Signature):
    """
    Summarize the narrative history of a story into a concise "The Story So Far" recap.

    You will receive:
    1. Story Outline (beats, theme, premise)
    2. Scene Summaries (completed scenes)
    3. Significant Facts (high-magnitude events from Neo4j)

    Your goal is to produce a compelling, cohesive summary that helps a player
    re-orient themselves when resuming a game.
    Focus on:
    - Major plot milestones achieved.
    - Current active threads or mysteries.
    - Immediate situational context (where we left off).
    """

    story_outline: str = dspy.InputField(desc="JSON representation of the story outline and beats")
    scene_summaries: str = dspy.InputField(desc="List of summaries from completed scenes")
    significant_facts: str = dspy.InputField(desc="Key events and facts discovered or occurred")
    tone_context: str = dspy.InputField(desc="Narrative tone and voice guidance")

    recap_markdown: str = dspy.OutputField(desc="Compelling markdown summary of the story so far")


class RecapModule(dspy.Module):
    """
    Recap generator — synthesizes story state into a player-facing summary.
    """

    def __init__(self) -> None:
        super().__init__()
        self.generate = dspy.ChainOfThought(RecapSignature)

    def forward(
        self,
        story_outline: str,
        scene_summaries: str,
        significant_facts: str,
        tone_context: str,
        role: Optional[ModelRole] = None,
    ) -> dspy.Prediction:
        with dspy_context_for("recap", role or ModelRole.STANDARD):
            return self.generate(
                story_outline=story_outline,
                scene_summaries=scene_summaries,
                significant_facts=significant_facts,
                tone_context=tone_context,
            )
