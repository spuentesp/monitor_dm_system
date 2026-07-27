"""
General-purpose DSPy module for matching free text against a fixed list
of options.

LAYER: 2 (agents)
IMPORTS FROM: dspy
CALLED BY: character_creation_loop.py (class/species/background/perk
choices), chat_support.py (consequence-choice resolution), and any
future caller with the same shape of problem: "the player said something
in free text; which of these N known options did they mean?"

This was originally built (and, before that, duplicated as plain
substring matching) for character creation specifically, then generalized
here on its second real use site (consequence-choice matching) rather
than staying duplicated -- see the `no-brittle-patches` project rule.
Never match free text against options via substring/keyword heuristics;
this is the shared, general answer.
"""

from __future__ import annotations

import dspy


class OptionMatchSignature(dspy.Signature):  # type: ignore[misc]
    """Match free text to one option from a fixed list.

    The caller is offering a choice between a small set of options (e.g.
    a character-creation pick, a consequence to accept, a menu of story
    choices), and the player answered in free text. Read their answer and
    return the option they meant, even if they paraphrased, abbreviated,
    or embedded it in a full sentence (e.g. "Take the Rad Resistant perk"
    -> "Rad Resistant", "I'll eat the cost to my nerves" -> "Take 2 stress
    and expose your position"). Return the option text EXACTLY as it
    appears in available_options -- never invent, reword, or partially
    quote an option. If the answer clearly doesn't match any listed
    option, return an empty string rather than guessing.

    Some phrasing is genuinely ambiguous between two options rather than
    matching one clearly -- e.g. it names an image or reaction ("let it
    slip", "freeze up") that could plausibly support either reading
    depending on what the missing object/referent is. When the answer
    could honestly be read as picking more than one option, and nothing
    in the wording favors one over the other, return an empty string
    instead of resolving the tie by guesswork -- the caller re-asks in
    that case rather than silently committing to a coin flip.
    """

    player_answer: str = dspy.InputField(desc="The player's free-text answer to this choice.")
    choice_context: str = dspy.InputField(
        desc="What this choice is about, for context (e.g. 'Choose Your First Perk', 'Choosing a consequence to accept')."
    )
    available_options: str = dspy.InputField(
        desc="JSON array of the valid option strings, verbatim from their source (game system schema, offered consequence list, etc.)."
    )

    matched_option: str = dspy.OutputField(
        desc=(
            "The exact option string (copied verbatim from available_options) "
            "the player chose, or an empty string if no option matches OR "
            "if the answer is genuinely ambiguous between two or more options."
        )
    )


class OptionMatchModule(dspy.Module):  # type: ignore[misc]
    """Matches free-text answers against a fixed list of options."""

    def __init__(self) -> None:
        super().__init__()
        self.match = dspy.Predict(OptionMatchSignature)

    def forward(
        self,
        player_answer: str,
        choice_context: str,
        available_options: str,
    ) -> dspy.Prediction:
        from monitor_data.schemas.llm_config import ModelRole

        from monitor_agents.dspy_runtime import dspy_context_for

        with dspy_context_for("text_matching", ModelRole.LIGHT):
            return self.match(
                player_answer=player_answer,
                choice_context=choice_context,
                available_options=available_options,
            )
