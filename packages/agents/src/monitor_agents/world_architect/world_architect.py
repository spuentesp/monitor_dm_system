"""
DSPy Signatures and Modules for the World Architect agent.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_data schemas

The World Architect guides users through conversational world creation.
It analyses user descriptions, extracts structured world elements (entities,
axioms, lore facts), and generates collaborative follow-up questions to
flesh out the setting.

Two modules:
  WorldArchitectModule  — Main conversational loop: respond + extract proposals
  WorldGapAnalysisModule — Identify what's missing in the world definition

Split (per LIBRARY_PLAN §1.2):
  World Architect → DSPy (creative, multi-output reasoning chain)
"""

import dspy
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.dspy_runtime import dspy_context_for

# =============================================================================
# SIGNATURES
# =============================================================================


class WorldArchitectSignature(dspy.Signature):  # type: ignore[misc]
    """
    You are the World Architect — a collaborative world-building partner for
    tabletop RPG setting creation.

    Given the user's message, conversation history, and current world state,
    produce TWO things:

    1. A conversational response that:
       - Acknowledges what the user described
       - Confirms what world elements will be created from their input
       - Asks 1-3 targeted follow-up questions to deepen the setting
       - Maintains a warm, collaborative tone (not interrogative)

    2. Structured extraction of world elements from the user's message:
       - Entities (characters, factions, locations, objects, concepts)
       - Axioms (fundamental world truths about magic, physics, society)
       - Lore facts (historical events, relationships, ongoing states)
       - Multiverse/World (top-level setting name, game system, description)
       - Universe (specific timeline/narrative instance)
       - Web Fetch (URLs the user wants you to read for data extraction)

    EXTRACTION RULES:
    - Only extract elements the user explicitly described or strongly implied
    - Do NOT invent details the user didn't mention
    - If unsure about a detail, ask about it in the response instead
    - Each extracted element must have a clear source in the user's message
    - IMPORTANT: When creating a new multiverse or starting from scratch, proactively ask the user for URLs, lore documents, or reference files they want to use as a foundation, and offer to help weave the initial relationships and factions of the world.
    - Entities can be extracted with ANY `entity_type` (e.g. 'spell', 'vehicle', 'technology', 'race'). The system will adapt them.
    """

    user_message: str = dspy.InputField(desc="The user's latest message describing aspects of their world")
    conversation_history: str = dspy.InputField(
        desc=(
            "Previous messages in this session (alternating user/architect). Empty string if this is the first message."
        )
    )
    world_state_summary: str = dspy.InputField(
        desc=(
            "JSON summary of what already exists in this universe: "
            "entity count, axiom count, fact count, and key named items. "
            "Empty object {} if the universe is new."
        )
    )
    world_profile_context: str = dspy.InputField(
        desc=(
            "Structured world-profile framing derived from the current world state and "
            "recent conversation: tone, institutions, lore domains, named anchors, and open questions."
        )
    )
    coverage_summary: str = dspy.InputField(
        desc="Compact summary of what is already defined in the world and what has coverage so far."
    )
    known_open_questions: str = dspy.InputField(
        desc="JSON list of the most important unanswered world-building questions to steer follow-up prompts."
    )

    response: str = dspy.OutputField(
        desc=(
            "Conversational response to the user. 2-4 paragraphs. "
            "Acknowledge what they described, confirm what will be created, "
            "then ask 1-3 follow-up questions to deepen the world. "
            "If creating a new world, ask for URLs/documents to ingest as lore. "
            "Use markdown formatting for emphasis."
        )
    )
    extracted_proposals: str = dspy.OutputField(
        desc=(
            "JSON array of world elements extracted from the user's message. "
            'Each item: {"type": "entity"|"axiom"|"lore_fact"|"multiverse"|"universe"|"web_fetch", ...details}. '
            "\n"
            'For type=entity: {"type": "entity", "name": str, "entity_type": '
            'str (ANY type, e.g., "character", "faction", "location", "technology", etc.), '
            '"description": str, "properties": {}} '
            "\n"
            'For type=axiom: {"type": "axiom", "statement": str, '
            '"domain": "magic"|"physics"|"society"|"religion"|"technology"|"nature"|"general"} '
            "\n"
            'For type=lore_fact: {"type": "lore_fact", "statement": str, '
            '"fact_type": "state"|"relationship"|"attribute"|"occurrence", '
            '"entity_names": [str]} '
            "\n"
            'For type=multiverse: {"type": "multiverse", "name": str, "system_name": str, "description": str} '
            "\n"
            'For type=universe: {"type": "universe", "name": str, "description": str, "genre": str, "tone": str} '
            "\n"
            'For type=web_fetch: {"type": "web_fetch", "url": str, "reason": str} '
            "\n"
            "Return empty array [] if nothing concrete to extract."
        )
    )


class WorldGapAnalysisSignature(dspy.Signature):  # type: ignore[misc]
    """
    Analyse the current state of a world definition and identify gaps.

    Given a summary of what exists (entities, axioms, facts), suggest what
    the user should define next to create a playable, coherent setting.

    Priority order:
    1. Core identity (name, genre, tone, tech/magic level)
    2. Foundational axioms (how does magic/tech/society work)
    3. Geography (major regions, cities, landmarks)
    4. Factions & power structures
    5. Key NPCs and historical figures
    6. History & lore (founding events, wars, eras)
    7. Current conflicts & plot hooks
    """

    world_state_summary: str = dspy.InputField(
        desc=(
            "JSON summary of what's defined: counts of entities by type, "
            "axiom domains covered, fact types present, and named items."
        )
    )
    world_profile_context: str = dspy.InputField(
        desc="Structured world-profile framing derived from current state and recent world-building turns."
    )
    coverage_summary: str = dspy.InputField(
        desc="Compact summary of current world coverage to prevent generic gap recommendations."
    )
    known_open_questions: str = dspy.InputField(
        desc="JSON list of the most important unanswered world-building questions."
    )

    gaps: str = dspy.OutputField(
        desc=(
            "JSON array of gap recommendations, ordered by priority. "
            'Each: {"area": str, "priority": 1-7, "suggestion": str, '
            '"example_prompt": str}. Max 5 items.'
        )
    )


# =============================================================================
# MODULES
# =============================================================================


class WorldArchitectModule(dspy.Module):  # type: ignore[misc]
    """
    Main conversational world-building module.

    Takes user input + context, produces response + structured proposals.
    """

    def __init__(self) -> None:
        super().__init__()
        self.respond = dspy.ChainOfThought(WorldArchitectSignature)

    def forward(
        self,
        user_message: str,
        conversation_history: str,
        world_state_summary: str,
        world_profile_context: str = "",
        coverage_summary: str = "",
        known_open_questions: str = "[]",
    ) -> dspy.Prediction:
        with dspy_context_for("world_architect", ModelRole.STANDARD):
            return self.respond(
                user_message=user_message,
                conversation_history=conversation_history,
                world_state_summary=world_state_summary,
                world_profile_context=world_profile_context,
                coverage_summary=coverage_summary,
                known_open_questions=known_open_questions,
            )


class WorldGapAnalysisModule(dspy.Module):  # type: ignore[misc]
    """Identify missing areas in a world definition."""

    def __init__(self) -> None:
        super().__init__()
        self.analyze = dspy.ChainOfThought(WorldGapAnalysisSignature)

    def forward(
        self,
        world_state_summary: str,
        world_profile_context: str = "",
        coverage_summary: str = "",
        known_open_questions: str = "[]",
    ) -> dspy.Prediction:
        with dspy_context_for("world_architect", ModelRole.LIGHT):
            return self.analyze(
                world_state_summary=world_state_summary,
                world_profile_context=world_profile_context,
                coverage_summary=coverage_summary,
                known_open_questions=known_open_questions,
            )
