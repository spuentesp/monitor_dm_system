"""
Live Session Extraction Prompts for Ingestion.

LAYER: 2 (agents)
"""

import dspy
from typing import List
from pydantic import BaseModel, Field


class SessionEvent(BaseModel):
    """An event extracted from a live session."""

    statement: str = Field(description="What happened in the narrative")
    involved_entities: List[str] = Field(description="Names of entities involved")
    consequence: str = Field(description="Potential consequence or follow-up thread")
    is_lore: bool = Field(
        description="True if this reveals world lore, False if it is just a plot event"
    )


class SessionExtraction(BaseModel):
    """The result of live session analysis."""

    events: List[SessionEvent]
    new_lore: List[str] = Field(description="Newly discovered world facts")
    active_threads: List[str] = Field(description="Plot threads that were advanced or created")


class SessionListenerSignature(dspy.Signature):
    """
    Extract lore, events, and plot threads from a sequence of gameplay turns.
    Focus on capturing changes to the world state and character relationships.
    """

    turns = dspy.InputField(desc="A sequence of player and GM turns from a live session")
    context = dspy.InputField(desc="Existing world context")

    extraction: SessionExtraction = dspy.OutputField()


class SessionListenerModule(dspy.Module):
    """DSPy module for live session extraction."""

    def __init__(self):
        super().__init__()
        self.extractor = dspy.Predict(SessionListenerSignature)

    def forward(self, turns: str, context: str = "") -> SessionExtraction:
        return self.extractor(turns=turns, context=context).extraction
