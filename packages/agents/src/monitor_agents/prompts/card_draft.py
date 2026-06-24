"""
DSPy Signature + Module for LLM-assisted character-card drafting.

LAYER: 2 (agents)

Given a short concept (and optionally a name and/or partial fields), draft the
"light card" fields a user would otherwise type by hand: description,
personality, an in-character first message, and author/GM notes. This is the
"ask for aid to fill the card" path — the output is a plain card, which can
then be expanded into a full MONITOR NPCProfile by npc_profile_gen.

Uses discrete OutputFields (not a JSON blob) so there is no brittle parsing —
DSPy populates each field directly.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import dspy

from monitor_agents.dspy_runtime import dspy_context_for
from monitor_data.schemas.llm_config import ModelRole

logger = logging.getLogger(__name__)


class CardDraftSignature(dspy.Signature):
    """
    Draft a roleplay character card from a concept.

    You are a character designer. Expand the concept into a vivid but concise
    character others can chat with. Respect any fields the user already filled
    (echo/refine them; do not contradict them). Write in the card's own world —
    no meta commentary.
    """

    concept: str = dspy.InputField(desc="Short free-text concept / premise for the character")
    given_name: str = dspy.InputField(desc="Name the user already chose, or empty to invent one")
    existing_description: str = dspy.InputField(desc="Any description the user already wrote (may be empty)")
    existing_personality: str = dspy.InputField(desc="Any personality notes already written (may be empty)")

    name: str = dspy.OutputField(desc="The character's name (1-4 words)")
    description: str = dspy.OutputField(
        desc="2-4 sentence description: who they are, appearance, situation"
    )
    personality: str = dspy.OutputField(
        desc="2-4 sentence personality: temperament, manner, how they treat strangers"
    )
    first_message: str = dspy.OutputField(
        desc="An in-character opening line the character says when a chat begins (1-3 sentences)"
    )
    gm_notes: str = dspy.OutputField(
        desc="Author/GM notes: hidden motivations, secrets, or behavioral guidance (1-3 sentences)"
    )


class CardDrafter(dspy.Module):
    """ChainOfThought card drafter. Run under ModelRole.STANDARD."""

    def __init__(self) -> None:
        super().__init__()
        self.draft = dspy.ChainOfThought(CardDraftSignature)

    def forward(
        self,
        concept: str,
        given_name: str = "",
        existing_description: str = "",
        existing_personality: str = "",
        role: Optional[ModelRole] = None,
    ) -> Dict[str, str]:
        with dspy_context_for("card_draft", role or ModelRole.STANDARD):
            pred = self.draft(
                concept=concept or "",
                given_name=given_name or "",
                existing_description=existing_description or "",
                existing_personality=existing_personality or "",
            )

        def _clean(value: object, limit: int) -> str:
            return str(value or "").strip()[:limit]

        # Never return an empty name — fall back to the user's input or concept.
        name = _clean(getattr(pred, "name", ""), 200) or given_name.strip() or "New Character"
        return {
            "name": name[:200],
            "description": _clean(getattr(pred, "description", ""), 2000)
            or existing_description.strip(),
            "personality": _clean(getattr(pred, "personality", ""), 2000)
            or existing_personality.strip(),
            "first_message": _clean(getattr(pred, "first_message", ""), 2000),
            "gm_notes": _clean(getattr(pred, "gm_notes", ""), 5000),
        }
