"""
Live Session Extraction Prompts for Ingestion.

LAYER: 2 (agents)
"""

import dspy
from pydantic import BaseModel, Field


class SessionEvent(BaseModel):
    """An event extracted from a live session."""

    statement: str = Field(description="What happened in the narrative")
    involved_entities: list[str] = Field(description="Names of entities involved")
    consequence: str = Field(description="Potential consequence or follow-up thread")
    is_lore: bool = Field(description="True if this reveals world lore, False if it is just a plot event")


class SessionExtraction(BaseModel):
    """The result of live session analysis."""

    events: list[SessionEvent]
    new_lore: list[str] = Field(description="Newly discovered world facts")
    active_threads: list[str] = Field(description="Plot threads that were advanced or created")


class SessionListenerSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract lore, events, and plot threads from a sequence of gameplay turns.
    Focus on capturing changes to the world state and character relationships.
    """

    turns = dspy.InputField(desc="A sequence of player and GM turns from a live session")
    context = dspy.InputField(desc="Existing world context")

    extraction: SessionExtraction = dspy.OutputField()


class SessionListenerModule(dspy.Module):  # type: ignore[misc]
    """DSPy module for live session extraction."""

    def __init__(self) -> None:
        super().__init__()
        self.extractor = dspy.Predict(SessionListenerSignature)

    def forward(self, turns: str, context: str = "") -> SessionExtraction:
        return self.extractor(turns=turns, context=context).extraction  # type: ignore[no-any-return]


class CaptureEntrySignature(dspy.Signature):  # type: ignore[misc]
    """
    Analyze a single Session Recorder entry for inline capture insights (CF-1).

    Only name participants/locations grounded in the entry text — never invent
    entities that are not stated or clearly implied by it. Prefer canonical
    names from known_entities over ad-hoc spellings from the entry. Candidate
    facts are world-state claims only (e.g. "the key is now with Mira") — no
    dialogue, no trivia.
    """

    entry_text = dspy.InputField(desc="One logged entry from a human-run table session")
    known_entities = dspy.InputField(desc="Canonical entity names known in this universe")
    open_threads = dspy.InputField(desc="Titles of currently open plot threads")

    participants: list[str] = dspy.OutputField(desc="Characters/NPCs who act or are clearly referenced in the entry")
    locations: list[str] = dspy.OutputField(desc="Places grounded in the entry text")
    candidate_facts: list[str] = dspy.OutputField(
        desc="World-state claims implied by the entry (no dialogue, no trivia)"
    )
    advances_thread: str = dspy.OutputField(desc="Title of the open thread this entry advances, or an empty string")


class CaptureEntryModule(dspy.Module):  # type: ignore[misc]
    """DSPy module for per-entry capture insights (CF-1, P1.2).

    High-volume path (one call per logged entry) — run under
    ``dspy_context_for(<node>, ModelRole.LIGHT)`` at the call site.
    """

    def __init__(self) -> None:
        super().__init__()
        self.analyzer = dspy.Predict(CaptureEntrySignature)

    def forward(
        self,
        entry_text: str,
        known_entities: list[str] | None = None,
        open_threads: list[str] | None = None,
    ) -> CaptureEntrySignature:
        return self.analyzer(  # type: ignore[no-any-return]
            entry_text=entry_text,
            known_entities=known_entities or [],
            open_threads=open_threads or [],
        )
