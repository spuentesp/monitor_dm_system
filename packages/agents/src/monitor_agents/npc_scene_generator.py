"""
NPC/Scene Generator Agent — generates usable content from KnowledgePack extraction data.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts

Responsibilities:
- Takes a KnowledgePack (with ExtractedAgenda, ExtractedRandomTable,
  ExtractedEntityArchetype) and produces GeneratedNPCProfile and ScenePrompt
  objects via DSPy modules.
- The output is NOT stored in the KnowledgePack — it's returned to the caller
  for immediate use in play sessions.

Pipeline:
  1. Load KnowledgePack from MongoDB
  2. NPCSceneGeneratorModule (DSPy) → NPCSceneGeneratorOutput (npcs + scenes)
  3. Return output to caller (or attach to session context)
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from monitor_agents.base import BaseAgent
from monitor_agents.prompts.npc_scene_generator import (
    NPCSceneGeneratorModule,
    ScenePromptModule,
)

logger = logging.getLogger(__name__)


class NPCSceneGenerator(BaseAgent):
    """
    Generates usable NPC profiles and scene prompts from KnowledgePack data.

    This agent is stateless — it reads from MongoDB and returns structured
    output without storing anything permanently.
    """

    def __init__(self, agent_id: str = "npc-scene-generator-1") -> None:
        super().__init__(agent_type="NPCSceneGenerator", agent_id=agent_id)
        self._npc_scene_module = NPCSceneGeneratorModule()
        self._scene_module = ScenePromptModule()

    async def run(self) -> None:
        pass  # Driven by external caller

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def generate_from_knowledge_pack(
        self,
        pack_id: UUID,
    ) -> Dict[str, Any]:
        """
        Load a KnowledgePack and generate NPC profiles + scene prompts.

        Args:
            pack_id: UUID of the KnowledgePack to process.

        Returns:
            Dict with keys:
              - npcs: List[GeneratedNPCProfile]
              - scenes: List[ScenePrompt]
              - pack_name: str
              - system_name: str
              - pack_id: str
        """
        from monitor_data.tools.mongodb_tools import mongodb_get_knowledge_pack

        pack = mongodb_get_knowledge_pack(pack_id)
        if not pack:
            raise ValueError(f"KnowledgePack {pack_id} not found")

        genre_tone = ""
        if pack.source_profile_data:
            genre_tone = ", ".join(pack.source_profile_data.genre_tone or [])
        system_name = pack.system_name or "Unknown System"

        # Run the main NPC/Scene generator
        result = self._npc_scene_module(
            agendas=pack.agendas,
            random_tables=pack.random_tables,
            entity_archetypes=pack.entity_archetypes,
            genre_tone=genre_tone,
            system_name=system_name,
        )

        output = result.npc_scene_output
        return {
            "npcs": output.npcs,
            "scenes": output.scenes,
            "pack_name": pack.name,
            "system_name": system_name,
            "pack_id": str(pack_id),
            "genre_tone": genre_tone,
        }

    async def generate_single_scene(
        self,
        table_name: str,
        entry_value: str,
        table_type: str,
        min_roll: int,
        max_roll: int,
        dice_formula: str,
        genre_tone: str,
        system_name: str,
    ) -> Dict[str, Any]:
        """
        Generate a single scene prompt from one random table entry.

        Useful when the GM wants to roll on a specific table and get an
        immediate scene setup rather than processing the whole pack.
        """
        result = self._scene_module(
            table_name=table_name,
            entry_value=entry_value,
            table_type=table_type,
            min_roll=min_roll,
            max_roll=max_roll,
            dice_formula=dice_formula,
            genre_tone=genre_tone,
            system_name=system_name,
        )
        return {"scene": result.scene}
