"""
DSPy Signatures and Modules for the Recap agent.

LAYER: 2 (agents)
IMPORTS FROM: dspy
"""

import dspy
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.dspy_runtime import dspy_context_for


class RecapSignature(dspy.Signature):  # type: ignore[misc]
    """
    Summarize the narrative history of a story into a concise "The Story So Far" recap.

    You will receive:
    1. Story Outline (beats, theme, premise)
    2. Scene Summaries (completed scenes)
    3. Significant Facts (high-magnitude events from Neo4j)
    4. The Story Ledger (what happened in each finished scene)

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
    story_ledger: str = dspy.InputField(desc="One entry per finished scene: what happened and when")
    tone_context: str = dspy.InputField(desc="Narrative tone and voice guidance")

    recap_markdown: str = dspy.OutputField(desc="Compelling markdown summary of the story so far")


class RecapModule(dspy.Module):  # type: ignore[misc]
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
        story_ledger: str = "",
        role: ModelRole | None = None,
    ) -> dspy.Prediction:
        with dspy_context_for("recap", role or ModelRole.STANDARD):
            return self.generate(
                story_outline=story_outline,
                scene_summaries=scene_summaries,
                significant_facts=significant_facts,
                story_ledger=story_ledger,
                tone_context=tone_context,
            )


class ArcBeatsSignature(dspy.Signature):  # type: ignore[misc]
    """
    Condense one chunk of a campaign's scene recaps into the arc beats of that chunk (CF-12).

    You will receive the story outline and a JSON list of scenes (oldest first) with
    their titles, statuses, and persisted per-scene summaries. Extract the major
    narrative beats of THIS chunk only — do not attempt to cover the whole campaign.
    """

    story_outline: str = dspy.InputField(desc="JSON representation of the story outline and beats")
    scene_recaps: str = dspy.InputField(
        desc="JSON list of scenes in this chunk, oldest first: {title, status, summary}"
    )
    detail: str = dspy.InputField(desc="Length control: short, standard, or detailed")

    arc_beats: str = dspy.OutputField(
        desc="Markdown bullet list of the major beats of this chunk of scenes, oldest first"
    )


class CampaignRecapSignature(dspy.Signature):  # type: ignore[misc]
    """
    Synthesize a campaign-level (story-arc) recap from per-chunk arc beats (CF-12).

    You will receive:
    1. Story Outline (beats, theme, premise)
    2. Arc Beats — one bullet list per chunk of scenes, in campaign order
    3. Significant Facts (high-magnitude canon events from Neo4j)
    4. Accepted Changes (accepted proposed changes — the ONLY canon deltas that count)
    5. Plot Threads (open and resolved)

    Produce a "where are we in the campaign" document with these sections:
    - Major Arcs: the campaign's acts so far and where the current one stands.
    - Party Journey: how the party has grown, what they have won and lost.
    - Faction Shifts: which powers rose, fell, or changed allegiance.
    - Resolved Threads: mysteries and quests already closed.
    - Open Threads: what is still unresolved and where the story can go next.
    """

    story_outline: str = dspy.InputField(desc="JSON representation of the story outline and beats")
    arc_beats: str = dspy.InputField(desc="Arc beats per chunk of scenes, in campaign order")
    significant_facts: str = dspy.InputField(desc="Key canon events and facts")
    accepted_changes: str = dspy.InputField(desc="Accepted proposed changes (canon deltas) as JSON")
    plot_threads: str = dspy.InputField(desc="Open and resolved plot threads as JSON")
    detail: str = dspy.InputField(desc="Length control: short, standard, or detailed")

    recap_markdown: str = dspy.OutputField(desc="Markdown campaign recap with the sections above")


class ArcRecapModule(dspy.Module):  # type: ignore[misc]
    """
    Hierarchical (map-reduce) campaign recap generator — CF-12.

    Scene recaps are condensed chunk by chunk into arc beats, then the beats
    are synthesized into one campaign-level recap, so arbitrarily long
    campaigns stay within the model's context window.
    """

    def __init__(self) -> None:
        super().__init__()
        self.beats = dspy.ChainOfThought(ArcBeatsSignature)
        self.campaign = dspy.ChainOfThought(CampaignRecapSignature)

    def summarize_chunk(
        self,
        story_outline: str,
        scene_recaps: str,
        detail: str = "standard",
        role: ModelRole | None = None,
    ) -> dspy.Prediction:
        with dspy_context_for("arc_recap_beats", role or ModelRole.STANDARD):
            return self.beats(
                story_outline=story_outline,
                scene_recaps=scene_recaps,
                detail=detail,
            )

    def synthesize_campaign(
        self,
        story_outline: str,
        arc_beats: str,
        significant_facts: str,
        accepted_changes: str,
        plot_threads: str,
        detail: str = "standard",
        role: ModelRole | None = None,
    ) -> dspy.Prediction:
        with dspy_context_for("arc_recap_synthesize", role or ModelRole.STANDARD):
            return self.campaign(
                story_outline=story_outline,
                arc_beats=arc_beats,
                significant_facts=significant_facts,
                accepted_changes=accepted_changes,
                plot_threads=plot_threads,
                detail=detail,
            )
