"""
Resolver Agent implementation.

LAYER: 2 (agents)
Authority: MongoDB (resolutions, proposals), Character State
"""

from monitor_agents.base import BaseAgent


"""
Resolver Agent implementation.

LAYER: 2 (agents)
Authority: MongoDB (resolutions, proposals), Character State
"""

import json
import logging
from typing import Dict, Any, Optional

from monitor_agents.base import BaseAgent
from monitor_data.utils.dice import roll_dice, calculate_modifier

logger = logging.getLogger(__name__)

class Resolver(BaseAgent):
    """
    Agent responsible for resolving rules, mechanic checks, and character state changes.
    """

    def __init__(self, agent_id: str = "resolver-cli-1") -> None:
        super().__init__(agent_type="Resolver", agent_id=agent_id)

    async def run(self) -> None:
        pass

    async def resolve_check(
        self, entity_id: str, stat_name: str, dc: int = 15
    ) -> Dict[str, Any]:
        """
        Resolve a statistic check (Attribute/Skill) for an entity.
        
        Workflow:
        1. Get Entity -> Universe -> Multiverse -> System Name.
        2. Get Game System rules.
        3. Get Entity working state (not strictly needed for basic attrib check, but good for context).
        4. Get Entity properties (attributes).
        5. Calculate modifier.
        6. Roll dice.
        7. Determine outcome.
        """
        try:
            # 1. Get Entity to find Universe/System
            # We need to parse the JSON result from call_tool
            entity_json = await self.call_tool("neo4j_get_entity", {"entity_id": entity_id})
            if not entity_json:
                return {"error": "Entity not found"}
            
            entity_data = json.loads(entity_json)
            # entity_data is { ... } response model
            
            universe_id = entity_data.get("universe_id")
            
            # 2. Get Universe to find Multiverse
            universe_json = await self.call_tool("neo4j_get_universe", {"universe_id": str(universe_id)})
            if not universe_json:
                return {"error": "Universe not found"}
            universe_data = json.loads(universe_json)
            multiverse_id = universe_data.get("multiverse_id")
            
            # 3. Get Multiverse to find System Name
            multiverse_json = await self.call_tool("neo4j_get_multiverse", {"multiverse_id": str(multiverse_id)})
            if not multiverse_json:
                 # Fallback: try to guess system or default
                 system_name = "Standard Fantasy v5"
            else:
                multiverse_data = json.loads(multiverse_json)
                system_name = multiverse_data.get("system_name")

            # 4. Get Game System
            # list systems and filter by name (since we don't have get_by_name yet, or we simulate it)
            # For now, we grab the first matching one
            systems_json = await self.call_tool("mongodb_list_game_systems", {"limit": 100, "include_builtin": True, "offset": 0})
            systems_data = json.loads(systems_json)
            
            system = None
            for sys in systems_data.get("systems", []):
                if sys["name"] == system_name:
                    system = sys
                    break
            
            if not system:
                return {"error": f"Game system '{system_name}' not found"}

            # 5. Get Entity Attributes (Properties)
            # Assuming 'properties' field in Entity contains attributes map: {"Strength": 16, ...}
            # Or formatted as {"attributes": {"Strength": 16}}
            props = entity_data.get("properties", {})
            attributes = props.get("attributes", {})
            
            # Handle case where props form is flat {"Strength": 16}
            if not attributes:
                attributes = props

            # Find attribute definition in system
            target_attr_def = next((a for a in system["attributes"] if a["name"].lower() == stat_name.lower()), None)
            
            if not target_attr_def:
                # Is it a skill?
                target_skill_def = next((s for s in system["skills"] if s["name"].lower() == stat_name.lower()), None)
                if target_skill_def:
                    # It's a skill check
                    linked_attr = target_skill_def["linked_attribute"]
                    stat_value = attributes.get(linked_attr, 10) # Default 10 if missing
                    # We might add a proficiency bonus here if we knew user's level/proficiency
                    # For MVP, we treat it as Attribute Check using linked attribute
                else:
                    return {"error": f"Stat '{stat_name}' not found in system '{system_name}'"}
            else:
                # It's an attribute
                stat_value = attributes.get(target_attr_def["name"], target_attr_def.get("default_value", 10))

            # 6. Calculate Modifier
            mod_formula = target_attr_def.get("modifier_formula")
            if mod_formula:
                modifier = calculate_modifier(stat_value, mod_formula)
            else:
                modifier = 0

            # 7. Roll Dice
            core_mechanic = system["core_mechanic"]
            # e.g., "1d20 + ATTRIBUTE_MOD" -> we simplify to just rolling d20 + mod
            # A real parser would replace variables in formula string.
            
            # Simple implementation for D20 and Dice Pool
            if "d20" in core_mechanic["type"]:
                base_roll = roll_dice("1d20")
                total = base_roll.total + modifier
                success = total >= dc
                details = f"Rolled {base_roll.total} + Mod {modifier} = {total} (DC {dc})"
                
            elif "dice_pool" in core_mechanic["type"]:
                # Assume attribute = number of dice
                pool_size = stat_value # + skill if applicable
                dice_res = roll_dice(f"{pool_size}d10") # Vampire uses d10s
                # Count successes >= threshold
                threshold = int(core_mechanic.get("success_threshold", 6))
                successes = sum(1 for d in dice_res.rolls if d >= threshold)
                total = successes
                success = successes > 0 # Simple success
                details = f"Rolled {pool_size}d10: {dice_res.rolls} -> {successes} successes"
                
            else:
                 return {"error": f"Unsupported mechanic type: {core_mechanic['type']}"}

            return {
                "success": success,
                "total": total,
                "details": details,
                "system": system_name,
                "stat": stat_name,
                "modifier": modifier
            }

        except Exception as e:
            logger.exception("Error resolving check")
            return {"error": str(e)}
