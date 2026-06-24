"""
Unit tests for the CardDrafter (LLM-assisted light-card drafting).

The DSPy predictor + context are mocked; we assert the *contract*: every output
field is populated sensibly, partial LLM output doesn't crash, the name falls
back rather than returning empty, and oversized fields are capped.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import patch

from monitor_agents.prompts import card_draft as cd
from monitor_agents.prompts.card_draft import CardDrafter


def _run(prediction_obj: object, *, given_name: str = "", concept: str = "a character") -> dict:
    drafter = CardDrafter()

    def fake(**_kw):
        return prediction_obj

    with (
        patch.object(cd, "dspy_context_for", return_value=contextlib.nullcontext()),
        patch.object(drafter, "draft", side_effect=fake),
    ):
        return drafter.forward(concept=concept, given_name=given_name)


class TestCardDrafterContract:
    def test_returns_all_five_fields(self):
        out = _run(
            SimpleNamespace(
                name="Ren",
                description="Blacksmith.",
                personality="Blunt.",
                first_message="State your business.",
                gm_notes="Knows the thieves' leader.",
            )
        )
        assert set(out) == {"name", "description", "personality", "first_message", "gm_notes"}
        assert out["name"] == "Ren"
        assert out["first_message"] == "State your business."

    def test_falls_back_to_safe_default_when_name_blank(self):
        out = _run(SimpleNamespace(name="  ", description="x", personality="x",
                                    first_message="x", gm_notes="x"))
        assert out["name"] == "New Character"

    def test_falls_back_to_user_provided_name_when_llm_leaves_blank(self):
        out = _run(
            SimpleNamespace(name="", description="x", personality="x",
                            first_message="x", gm_notes="x"),
            given_name="Halvar",
        )
        assert out["name"] == "Halvar"

    def test_truncates_overlong_fields(self):
        out = _run(
            SimpleNamespace(
                name="X",
                description="d" * 5000,
                personality="p" * 5000,
                first_message="f" * 5000,
                gm_notes="g" * 10000,
            )
        )
        assert len(out["description"]) <= 2000
        assert len(out["personality"]) <= 2000
        assert len(out["first_message"]) <= 2000
        assert len(out["gm_notes"]) <= 5000

    def test_no_name_anywhere_yields_safe_default(self):
        out = _run(
            SimpleNamespace(
                name=None,
                description=None,
                personality=None,
                first_message=None,
                gm_notes=None,
            )
        )
        assert out["name"] == "New Character"
        assert out["description"] == ""
        assert out["first_message"] == ""

    def test_preserves_existing_description_when_llm_returns_empty(self):
        """If the user passed a description and the LLM clears it, keep theirs."""
        drafter = CardDrafter()

        def fake(**_kw):
            return SimpleNamespace(
                name="Lin", description="", personality="", first_message="", gm_notes=""
            )

        with (
            patch.object(cd, "dspy_context_for", return_value=contextlib.nullcontext()),
            patch.object(drafter, "draft", side_effect=fake),
        ):
            out = drafter.forward(
                concept="x",
                existing_description="A weary lighthouse keeper.",
                existing_personality="Quiet.",
            )
        assert out["description"] == "A weary lighthouse keeper."
        assert out["personality"] == "Quiet."