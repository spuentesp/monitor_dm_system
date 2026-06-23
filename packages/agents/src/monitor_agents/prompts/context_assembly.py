"""
DSPy Signature and Module for context assembly — query formulation helpers.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_data schemas

Context assembly is responsible for:
  1. Formulating retrieval queries from the player's action (for Qdrant)
  2. Ranking and summarising raw context (see also narrator.py for the
     ContextAssemblyModule used in the Narrator pipeline)

The ContextAssemblyModule in narrator.py handles the *summarisation* step.
This module handles the *query formulation* step (upstream of retrieval).
"""

import dspy

from monitor_agents.dspy_runtime import dspy_context_for
from monitor_data.schemas.llm_config import ModelRole


# =============================================================================
# SIGNATURES
# =============================================================================


class QueryFormulationSignature(dspy.Signature):
    """
    Formulate optimised semantic search queries from a player's action.

    Given a player's declared action, the current scene summary, and
    character metadata, produce dense retrieval queries for each knowledge
    source (Qdrant collections, Neo4j Cypher stub).
    """

    player_action: str = dspy.InputField(
        desc="The player's declared action or dialogue for this turn"
    )
    scene_summary: str = dspy.InputField(
        desc="Brief summary of the current scene (location, NPCs, active threats)"
    )
    character_name: str = dspy.InputField(desc="Name of the player character performing the action")
    character_tags: str = dspy.InputField(
        desc="Comma-separated tags/traits describing the character (e.g. 'fighter,noble,PTSD')"
    )

    # Outputs
    memory_query: str = dspy.OutputField(
        desc=(
            "Semantic query for the Qdrant 'memories' collection. "
            "Focus on character memories relevant to this action."
        )
    )
    snippet_query: str = dspy.OutputField(
        desc=(
            "Semantic query for the Qdrant 'snippets' collection. "
            "Focus on world-lore or background documents relevant to this action."
        )
    )
    entity_filter: str = dspy.OutputField(
        desc=(
            "Comma-separated entity names or IDs that should be included in the "
            "Neo4j context fetch. Include NPCs, locations, and items relevant to the action."
        )
    )


# DEPRECATED: TurnIntentSignature / TurnIntentModule — unused LLM-based intent
# classifier.  Resolver._infer_intent_type() handles intent classification with
# fast heuristics.  If richer classification is needed in the future, extend
# Resolver rather than reviving this DSPy module.  Removal tracked in Fix #7.
#
# class TurnIntentSignature(dspy.Signature):  # noqa: ERA001
#     ...
# class TurnIntentModule(dspy.Module):        # noqa: ERA001
#     ...


# =============================================================================
# MODULES
# =============================================================================


class QueryFormulationModule(dspy.Module):
    """
    Formulates retrieval queries for all three context sources.

    Used by ContextAssembly.assemble() before parallel Qdrant + Neo4j fetches.
    """

    def __init__(self) -> None:
        super().__init__()
        # Predict (no CoT) — this is a routing/classification task,
        # not creative generation, so CoT overhead is unnecessary.
        self.formulate = dspy.Predict(QueryFormulationSignature)

    def forward(
        self,
        player_action: str,
        scene_summary: str,
        character_name: str,
        character_tags: str,
    ) -> dspy.Prediction:
        with dspy_context_for("context_assembly", ModelRole.LIGHT):
            return self.formulate(
                player_action=player_action,
                scene_summary=scene_summary,
                character_name=character_name,
                character_tags=character_tags,
            )
