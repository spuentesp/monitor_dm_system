"""
DSPy Signatures and Modules for the NPC/Scene Generator agent.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_data schemas

Takes extracted data from a KnowledgePack (ExtractedAgenda, ExtractedRandomTable,
ExtractedEntityArchetype) and produces usable NPC profiles and scene prompts.

Two modules:
  NPCSceneGeneratorModule — Main: extract agendas → NPC profiles + scene setups
  ScenePromptModule — Secondary: given a random table, produce a concrete scene
"""

import dspy
from typing import Any

from monitor_data.schemas.agendas import ExtractedAgenda
from monitor_data.schemas.knowledge_packs import ExtractedRandomTable, ExtractedEntityArchetype
from monitor_data.schemas.llm_config import ModelRole
from monitor_data.schemas.npc_scene_generator import (
    ScenePrompt,
    NPCSceneGeneratorOutput,
)


# =============================================================================
# SIGNATURES
# =============================================================================


class NPCSceneGeneratorSignature(dspy.Signature):
    """
    Generate usable NPC profiles and scene prompts from ingested source data.

    You are a TTRPG game master assistant. Given extracted data from a rulebook
    (agendas, random tables, entity archetypes), produce:

    1. NPC PROFILES — Each ExtractedAgenda with an owner_name becomes a concrete NPC:
       - Derive a name (use random table for names if available)
       - Derive a role/personality from the agenda's description
       - Assign behavior triggers based on agenda type
       - Provide dialogue hooks that surface the agenda naturally

    2. SCENE PROMPTS — Each ExtractedRandomTable becomes a scene setup:
       - Pick one entry from the table (or roll)
       - Build a 1-3 sentence scenario around that entry
       - Name which NPCs are involved and which agenda clocks are ticking

    ── INPUT ──────────────────────────────────────────────────────────────

    agendas: List of extracted faction/NPC agendas from the source.
    random_tables: List of extracted random tables (encounter, loot, names, misc).
    entity_archetypes: Named entity templates from the source.
    genre_tone: Genre/tone tags (e.g. "gothic horror", "space opera").
    system_name: Name of the game system for flavor text.

    ── OUTPUT FORMAT ──────────────────────────────────────────────────────

    Return a JSON object with 'npcs' and 'scenes' keys:

    {
      "npcs": [
        {
          "name": "Zara the Broken",
          "role": "fortune teller",
          "personality_summary": "Spiteful and paranoid, speaks in riddles",
          "current_goal": "Track down the merchant who sold her cursed tea",
          "agenda_title": "The Cursed Tea Conspiracy",
          "behavior_triggers": [
            {"trigger_topic": "tea", "reaction": "Flinches and grips her pendant"},
            {"trigger_topic": "merchants", "reaction": "Eyes narrow with cold fury"}
          ],
          "suggested_dialogue_hooks": [
            "You there — I sense betrayal in your future",
            "Ask about the tea. I dare you.",
            "The stars warned me about someone like you"
          ],
          "suggested_scene_invitations": [
            "A fortune teller at the crossroads blocks the path, demanding to read your palms",
            "The party finds Zara alone in her tent, surrounded by maps of trade routes"
          ],
          "tags": ["npc", "gothic", "merchant feud"]
        }
      ],
      "scenes": [
        {
          "title": "Ambush in the Sewers",
          "setup": "The party is exploring the old aqueducts when a gang of RatCatchers springs an ambush using alchemy-based traps",
          "npcs_involved": ["Zara the Broken"],
          "random_table_rolls": [
            {"table": "Sewer Encounters", "roll": "14", "result": "2d4 RatCatchers with smoke bombs"}
          ],
          "agenda_clocks_active": ["The Cursed Tea Conspiracy"],
          "suggested_conflict": "The RatCatchers are clearing the tunnels for a larger purposes — are they working for someone?",
          "tags": ["encounter", "urban", "sewers"]
        }
      ]
    }
    """

    agendas: list[ExtractedAgenda] = dspy.InputField(
        desc="Extracted agendas from the source (may be empty)"
    )
    random_tables: list[ExtractedRandomTable] = dspy.InputField(
        desc="Extracted random tables from the source (may be empty)"
    )
    entity_archetypes: list[ExtractedEntityArchetype] = dspy.InputField(
        desc="Extracted entity archetypes from the source (may be empty)"
    )
    genre_tone: str = dspy.InputField(
        desc="Genre and tone tags from the source (e.g. 'gothic horror, tactical combat, space opera')"
    )
    system_name: str = dspy.InputField(desc="Name of the game system")

    npc_scene_output: NPCSceneGeneratorOutput = dspy.OutputField(
        desc="Generated NPC profiles and scene prompts"
    )


class ScenePromptSignature(dspy.Signature):
    """
    Generate a single concrete scene prompt from one random table entry.

    Given a specific random table entry, build a vivid scene setup that
    a GM can use immediately — including the setup, NPCs involved, and
    the dramatic tension.
    """

    table_name: str = dspy.InputField(desc="Name of the random table")
    entry_value: str = dspy.InputField(
        desc="The specific table entry value (e.g. '2d4 RatCatchers')"
    )
    table_type: str = dspy.InputField(desc="Table type: encounter, loot, names, misc")
    min_roll: int = dspy.InputField(desc="Minimum roll that produces this entry")
    max_roll: int = dspy.InputField(desc="Maximum roll that produces this entry")
    dice_formula: str = dspy.InputField(desc="Dice formula for this table (e.g. '1d20')")
    genre_tone: str = dspy.InputField(desc="Genre/tone tags for flavor")
    system_name: str = dspy.InputField(desc="Game system name")

    scene: ScenePrompt = dspy.OutputField(desc="A single scene prompt for this table entry")


# =============================================================================
# MODULES
# =============================================================================


class _GeneratorModule(dspy.Module):
    """Base class for NPC/Scene Generator modules."""

    _signature: type | None = None
    _role: ModelRole = ModelRole.HEAVY
    _max_tokens: int = 16384

    def __init__(self) -> None:
        super().__init__()
        self._chain = dspy.ChainOfThought(self._signature)

    def forward(self, **kwargs) -> Any:
        return self._chain(**kwargs)


class NPCSceneGeneratorModule(_GeneratorModule):
    """Generate NPC profiles and scene prompts from KnowledgePack extraction data."""

    _signature = NPCSceneGeneratorSignature
    _role = ModelRole.HEAVY
    _max_tokens = 16384


class ScenePromptModule(_GeneratorModule):
    """Generate a single scene prompt from a random table entry."""

    _signature = ScenePromptSignature
    _role = ModelRole.STANDARD
    _max_tokens = 4096
