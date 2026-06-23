"""
DSPy module for extracting new entities from narrative text during play.

LAYER: 2 (agents)
IMPORTS FROM: dspy
CALLED BY: scene_loop.extract_new_entities

This module analyses GM narration output to identify entities that were
mentioned but don't yet exist in the world. These become ProposedChange
documents that CanonKeeper evaluates and potentially canonizes.

Unlike EntityExtractionModule (ingestion-time archetype extraction),
this module works on short narrative passages and identifies *specific*
new individuals, locations, and objects that should be tracked.
"""

from __future__ import annotations

import dspy


class NarrativeEntityExtractionSignature(dspy.Signature):
    """Identify new entities mentioned in narrative text that don't exist in the world yet.

    Given a GM narration and a list of known entities, identify any NEW entities
    (characters, locations, objects, factions) that were introduced in the narration
    but are NOT in the known entity list.

    Rules:
    - Only extract entities that are NAMED (have a proper name or clear identifier).
    - Do NOT extract entities already in the known_entities list.
    - Do NOT extract generic references ("a guard", "the tavern") unless they have
      a proper name ("Guard Theron", "The Rusty Tankard").
    - Each extracted entity should have a brief description from context.
    - Confidence should reflect how clearly the entity is defined (named = high,
      vague reference = low).
    """

    narration: str = dspy.InputField(desc="The GM's narrative text from the current turn.")
    known_entities: str = dspy.InputField(
        desc=(
            "Comma-separated list of entity names already known in the world. "
            "Do NOT extract any of these as new entities."
        )
    )
    universe_context: str = dspy.InputField(
        desc="Brief description of the universe/setting to ground entity types."
    )

    new_entities: str = dspy.OutputField(
        desc=(
            "JSON array of new entities found in the narration. "
            'Each entity is: {"name": str, "entity_type": str, '
            '"description": str, "confidence": float}. '
            "entity_type must be one of: CHARACTER, FACTION, LOCATION, OBJECT, CONCEPT, ORGANIZATION. "
            "If no new entities, output an empty array: []. "
            'Example: [{"name": "Theron", "entity_type": "CHARACTER", '
            '"description": "A guard at the north gate", "confidence": 0.9}]'
        )
    )


class NarrativeEntityExtractionModule(dspy.Module):
    """Extract new entities from narrative text during play.

    Uses ChainOfThought reasoning to identify named entities that don't
    yet exist in the world, producing structured proposals for CanonKeeper.
    """

    def __init__(self) -> None:
        super().__init__()
        self.extract = dspy.Predict(NarrativeEntityExtractionSignature)

    def forward(
        self,
        narration: str,
        known_entities: str,
        universe_context: str = "",
    ) -> dspy.Prediction:
        from monitor_agents.dspy_runtime import dspy_context_for
        from monitor_data.schemas.llm_config import ModelRole
        with dspy_context_for("indexer", ModelRole.LIGHT):
            return self.extract(
                narration=narration,
                known_entities=known_entities,
                universe_context=universe_context,
            )
