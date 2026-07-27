"""
DSPy modules for extracting structured character-creation answers from
free text.

LAYER: 2 (agents)
IMPORTS FROM: dspy
CALLED BY: character_creation_loop.process_input

Character creation asks the player free-text questions (attribute
allocation, class/species/background/perk choice, etc.) driven entirely
by the ingested game system's own schema -- no game-specific names
hardcoded anywhere in this file or in character_creation_loop.py.

This replaces regex/substring parsing of those answers, which broke on
any phrasing a hand-written pattern didn't anticipate ("put 2 into
Perception" vs the only form the old regex accepted, "2 Perception" with
nothing but whitespace between number and name). Standing project rule:
brittle parsing/classification is replaced with genuine LLM extraction,
not patched to cover one more phrasing -- see the `no-brittle-patches`
memory.

Option-matching (was here too, hardcoding Storyteller-specific category
names into otherwise system-agnostic code) moved to
``prompts/text_matching.py`` on its second real use site (consequence-
choice matching in chat_support.py) since it was never actually
character-creation-specific.
"""

from __future__ import annotations

import dspy


class AttributeAssignmentSignature(dspy.Signature):  # type: ignore[misc]
    """Extract attribute and resource point assignments from a player's free-text answer.

    The player is allocating points to attributes (and possibly related
    resources/tracks) defined by their game system. Read their answer and
    determine the NEW value for each attribute or resource they mentioned
    -- by name, abbreviation, or clear natural-language reference (e.g.
    "put 2 into Perception", "PER=7", "5 Physical" as a category total to
    split across its attributes, "2 more Agility", "Willpower 5"). Only
    include attributes/resources the answer actually addresses; leave
    unmentioned ones out of your response entirely -- the caller keeps
    their current values for anything you omit.

    If the answer requests a random/automatic roll ("roll", "random",
    "surprise me") rather than stating values, return empty objects for
    both fields -- the caller handles randomization separately.
    """

    player_answer: str = dspy.InputField(desc="The player's free-text answer to the attribute-allocation step.")
    available_attributes: str = dspy.InputField(
        desc=(
            "JSON array of this game system's own attributes: "
            '[{"name": str, "abbreviation": str, "current_value": int, '
            '"min_value": int, "max_value": int}, ...]. Names/abbreviations '
            "are system-specific -- read them from here, never assume "
            "D&D-style ability names or any other fixed vocabulary."
        )
    )
    available_resources: str = dspy.InputField(
        desc=(
            "JSON array of resources/tracks this system also allows "
            "assigning in the same breath as attributes (e.g. Willpower in "
            "Storyteller games): "
            '[{"name": str, "current_value": int}, ...]. May be an empty array.'
        )
    )

    attribute_assignments: str = dspy.OutputField(
        desc=(
            "JSON object mapping attribute abbreviation (from "
            "available_attributes) to its new value, e.g. "
            '{"PER": 7, "AGI": 6}. Only include attributes the answer '
            "actually addresses. Empty object {} if none, or if the "
            "answer requests a random roll instead."
        )
    )
    resource_assignments: str = dspy.OutputField(
        desc=(
            "JSON object mapping resource name (from available_resources) "
            'to its new value, e.g. {"Willpower": 5}. Only include '
            "resources the answer actually addresses. Empty object {} if none."
        )
    )


class SkillSelectionSignature(dspy.Signature):  # type: ignore[misc]
    """Extract skill selections (and optional ranks) from a player's free-text answer.

    The player is picking skills -- as a plain list ("Sneak, Survival, and
    Guns"), tagged/prioritized picks ("tag Sneak, Survival, and Guns"), or
    with explicit ranks ("Empathy 4, Persuasion 2") -- from the game
    system's own skill list. Match their answer against available_skills
    (paraphrase-tolerant: "sneaking" -> "Sneak" if that's the listed
    name) and return only the skills actually mentioned. Never invent a
    skill not present in available_skills.
    """

    player_answer: str = dspy.InputField(desc="The player's free-text answer to the skill-selection step.")
    available_skills: str = dspy.InputField(
        desc="JSON array of this game system's own skill names, verbatim from the schema."
    )

    skill_selections: str = dspy.OutputField(
        desc=(
            "JSON object mapping each mentioned skill name (copied verbatim "
            "from available_skills) to its rank if the player stated one, "
            "or `true` if they just named it with no rank, e.g. "
            '{"Sneak": true, "Empathy": 4}. Empty object {} if none mentioned.'
        )
    )


class AttributeAssignmentModule(dspy.Module):  # type: ignore[misc]
    """Extracts attribute/resource point assignments from free text."""

    def __init__(self) -> None:
        super().__init__()
        self.extract = dspy.Predict(AttributeAssignmentSignature)

    def forward(
        self,
        player_answer: str,
        available_attributes: str,
        available_resources: str = "[]",
    ) -> dspy.Prediction:
        from monitor_data.schemas.llm_config import ModelRole

        from monitor_agents.dspy_runtime import dspy_context_for

        with dspy_context_for("character_creation", ModelRole.LIGHT):
            return self.extract(
                player_answer=player_answer,
                available_attributes=available_attributes,
                available_resources=available_resources,
            )


class SkillSelectionModule(dspy.Module):  # type: ignore[misc]
    """Extracts skill selections (with optional ranks) from free text."""

    def __init__(self) -> None:
        super().__init__()
        self.select = dspy.Predict(SkillSelectionSignature)

    def forward(self, player_answer: str, available_skills: str) -> dspy.Prediction:
        from monitor_data.schemas.llm_config import ModelRole

        from monitor_agents.dspy_runtime import dspy_context_for

        with dspy_context_for("character_creation", ModelRole.LIGHT):
            return self.select(
                player_answer=player_answer,
                available_skills=available_skills,
            )
