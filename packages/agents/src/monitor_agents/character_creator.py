"""
CharacterCreator — Agent for creating characters (M-13).

Guides character creation through archetype selection, stat assignment,
and entity persistence. Uses game system schemas for validation.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libraries
CALLED BY: CLI (Layer 3), CharacterCreationLoop
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from monitor_agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when character parameters fail validation."""

    pass


# Default stat names for common game systems
DEFAULT_STATS = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]


class CharacterCreator(BaseAgent):
    """
    Create characters with validation, stat assignment, and persistence.

    Uses MCP tools to create entities in Neo4j and character sheets
    in MongoDB.
    """

    def __init__(
        self,
        agent_type: str = "CharacterCreator",
        agent_id: str = "character-creator-001",
        model: Optional[str] = None,
        mcp_client: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        super().__init__(agent_type=agent_type, agent_id=agent_id, model=model)
        self._mcp_client = mcp_client
        self._llm_client = llm_client

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call an MCP tool, using injected client if available."""
        if self._mcp_client is not None:
            return await self._mcp_client.call_tool(tool_name, arguments)
        return await super().call_tool(tool_name, arguments)

    def validate_character_params(
        self,
        name: str,
        role: str = "PC",
        description: str = "",
        stats: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        Validate character creation parameters.

        Args:
            name: Character name (1-200 characters).
            role: Character role (PC, NPC, ally, enemy, etc.).
            description: Character description.
            stats: Character stats dict (e.g., {"STR": 16, "DEX": 14, ...}).

        Returns:
            Validated parameters dict.

        Raises:
            ValidationError: If parameters are invalid.
        """
        # Validate name
        if not name or len(name) < 1:
            raise ValidationError("Name must be 1-200 characters")
        if len(name) > 200:
            raise ValidationError("Name must be 1-200 characters")

        # Validate role
        valid_roles = {"PC", "NPC", "ally", "enemy", "neutral", "mentor", "antagonist"}
        if role not in valid_roles:
            logger.warning("Unusual role '%s', proceeding anyway", role)

        # Validate stats if provided
        if stats is not None:
            if not isinstance(stats, dict):
                raise ValidationError("Stats must be a dictionary")
            for stat_name, stat_value in stats.items():
                if not isinstance(stat_value, int):
                    raise ValidationError(
                        f"Stat {stat_name} must be an integer, got {type(stat_value)}"
                    )
                if stat_value < 1 or stat_value > 30:
                    raise ValidationError(
                        f"Stat {stat_name} must be between 1 and 30, got {stat_value}"
                    )

        return {
            "name": name,
            "role": role,
            "description": description,
            "stats": stats or {},
        }

    async def create_character(
        self,
        universe_id: str,
        name: str,
        role: str = "PC",
        description: str = "",
        stats: Optional[Dict[str, int]] = None,
        archetype_id: Optional[str] = None,
        resources: Optional[Dict[str, int]] = None,
        abilities: Optional[List[str]] = None,
        equipment: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a character entity in Neo4j and a character sheet in MongoDB.

        Args:
            universe_id: Universe to create the character in.
            name: Character name.
            role: Character role (PC, NPC, etc.).
            description: Character description.
            stats: Character stats dict.
            archetype_id: Optional archetype to derive from.
            resources: Character resources (hp, mp, etc.).
            abilities: List of ability names.
            equipment: List of equipment names.

        Returns:
            Dict with entity_id, character_sheet_id, and status.
        """
        # Validate parameters
        validated = self.validate_character_params(name, role, description, stats)

        # Create entity in Neo4j
        entity_result = await self.call_tool(
            "neo4j_create_entity",
            {
                "universe_id": universe_id,
                "entity_type": "character",
                "params": {
                    "name": validated["name"],
                    "description": validated["description"],
                    "role": validated["role"],
                    "properties": {},
                    "state_tags": [],
                    "canon_level": "canon",
                },
            },
        )

        entity_id = str(entity_result) if entity_result else str(uuid4())

        # Create DERIVES_FROM relationship if archetype specified
        if archetype_id:
            try:
                await self.call_tool(
                    "neo4j_create_relationship",
                    {
                        "from_id": entity_id,
                        "to_id": archetype_id,
                        "relationship_type": "DERIVES_FROM",
                        "properties": {},
                    },
                )
            except Exception as exc:
                logger.warning("Failed to create DERIVES_FROM relationship: %s", exc)

        # Create character sheet in MongoDB
        character_sheet_result = None
        try:
            character_sheet_result = await self.call_tool(
                "mongodb_create_character_sheet",
                {
                    "entity_id": entity_id,
                    "stats": stats or {},
                    "resources": resources or {},
                    "abilities": abilities or [],
                    "equipment": equipment or [],
                },
            )
        except Exception as exc:
            logger.warning("Failed to create character sheet: %s", exc)

        return {
            "entity_id": entity_id,
            "character_sheet_id": str(character_sheet_result) if character_sheet_result else None,
            "status": "created",
        }

    def prompt_character_stats(
        self,
        game_system: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a prompt for character stat assignment.

        Args:
            game_system: Game system document defining available stats.

        Returns:
            Dict with prompt text and available stats.
        """
        if game_system and "character_creation" in game_system:
            creation_data = game_system["character_creation"]
            steps = creation_data.get("steps", [])
            stat_names = []
            for step in steps:
                if step.get("type") == "assign_stats":
                    stat_names = step.get("stats", DEFAULT_STATS)
                    break
            if not stat_names:
                stat_names = DEFAULT_STATS
        else:
            stat_names = DEFAULT_STATS

        prompt = "Assign your character's stats. Available stats: " + ", ".join(stat_names)
        return {
            "prompt": prompt,
            "available_stats": stat_names,
        }

    def calculate_hp(
        self,
        constitution: int,
        level: int = 1,
        hit_die: str = "d8",
    ) -> int:
        """
        Calculate hit points based on constitution, level, and hit die.

        Args:
            constitution: Constitution score.
            level: Character level.
            hit_die: Hit die type (d6, d8, d10, d12).

        Returns:
            Calculated HP value.
        """

        die_map = {"d4": 2, "d6": 3, "d8": 4, "d10": 5, "d12": 6}
        die_avg = die_map.get(hit_die.lower(), 4)

        # Constitution modifier
        con_mod = (constitution - 10) // 2

        # HP = (die_avg + con_mod) * level, minimum 1 per level
        hp = max(1, die_avg + con_mod) * level
        return hp

    async def select_archetype(
        self,
        universe_id: str,
        archetype_id: Optional[str] = None,
        archetype_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Select an archetype for the character.

        Args:
            universe_id: Universe to search in.
            archetype_id: Specific archetype ID.
            archetype_name: Archetype name to search for.

        Returns:
            Dict with archetype details.
        """
        if archetype_id:
            result = await self.call_tool(
                "neo4j_get_entity",
                {"entity_id": archetype_id},
            )
            return {"archetype": result, "archetype_id": archetype_id}

        if archetype_name:
            results = await self.call_tool(
                "neo4j_search_entities",
                {
                    "universe_id": universe_id,
                    "query": archetype_name,
                    "entity_type": "archetype",
                },
            )
            return {"archetypes": results or []}

        # List all archetypes
        results = await self.call_tool(
            "neo4j_list_archetypes",
            {"universe_id": universe_id},
        )
        return {"archetypes": results or []}

    async def run(self) -> Dict[str, Any]:
        """Run the character creation workflow. Entry point for BaseAgent.run()."""
        # Default: prompt for stats and return prompt info
        return self.prompt_character_stats()
