"""
Combat Loop — LangGraph StateGraph for tactical combat encounters.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), langgraph, external libs
CALLED BY: scene_loop.py (conditional edge after resolve_action)

Flow: roll_initiative → choose_combatant → resolve_action → narrate_combat → check_victory
                                                                                    ↓
                                                                     [next_combatant | end_combat]

Invariants:
- Turns NEVER write to Neo4j directly
- All state changes are proposed via MongoDB
- Combat is embedded within a Scene; never standalone
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# STATE SCHEMAS
# =============================================================================


class CombatantState(BaseModel):
    """State for a single combat participant."""

    entity_id: UUID
    name: str
    initiative: int
    is_pc: bool
    hp_current: int
    hp_max: int
    conditions: List[str] = Field(default_factory=list)
    is_active: bool = True  # False if dead / fled / incapacitated
    attributes: Dict[str, int] = Field(default_factory=dict)


class CombatState(BaseModel):
    """Typed state flowing through every combat-loop node."""

    scene_id: UUID
    story_id: UUID
    combatants: List[CombatantState] = Field(default_factory=list)
    initiative_order: List[UUID] = Field(default_factory=list)  # entity_ids in initiative order
    current_index: int = 0
    current_combatant_id: Optional[UUID] = None
    round_number: int = 1
    combat_log: List[Dict[str, Any]] = Field(default_factory=list)
    pending_proposals: List[Dict[str, Any]] = Field(default_factory=list)
    combat_active: bool = True
    victory_side: Optional[str] = None  # "pc" | "enemy" | None

    # Context from SceneLoop
    entity_context: List[Dict[str, Any]] = Field(default_factory=list)
    game_context: Dict[str, Any] = Field(default_factory=dict)
    source_profile: Dict[str, Any] = Field(default_factory=dict)
    gm_profile: Optional[Dict[str, Any]] = None
    session_tone: str = Field(default="dramatic")

    # Current action
    user_input: Optional[str] = None
    resolution: Optional[Dict[str, Any]] = None
    narrative_text: Optional[str] = None

    # Flow control
    awaiting_pc_input: bool = False


# =============================================================================
# HELPERS
# =============================================================================


def _calculate_modifier_from_attributes(
    attributes: Dict[str, int],
    stat_name: str,
    gsr: Any | None = None,
) -> int:
    """Calculate a modifier for a stat from attributes dict."""
    from monitor_data.utils.dice import calculate_modifier

    _DEFAULT = "(VALUE - 10) // 2"
    value = 0
    for key in (stat_name, stat_name.upper(), stat_name.lower(), stat_name.title()):
        if key in attributes:
            value = int(attributes.get(key, 0))
            break
    if gsr:
        try:
            return gsr.calc_modifier(stat_name, value)
        except Exception:
            pass
    return calculate_modifier(value, _DEFAULT)


# =============================================================================
# NODES
# =============================================================================


async def roll_initiative(state: CombatState) -> Dict[str, Any]:
    """
    Roll initiative for all combatants and sort by result.

    Uses the game system's initiative stat if available (DEX by default).
    """
    from monitor_data.utils.dice import roll_dice

    initiative_stat = "DEX"
    gsr = None
    if state.game_context:
        try:
            from monitor_agents.game_system import GameSystemRuntime

            gsr = GameSystemRuntime(state.game_context)
            initiative_stat = getattr(gsr, "initiative_stat_name", "DEX")
        except Exception:
            pass

    rolled: List[CombatantState] = []
    initiative_values: List[tuple[UUID, int]] = []

    for c in state.combatants:
        modifier = _calculate_modifier_from_attributes(c.attributes, initiative_stat, gsr)
        roll = roll_dice("1d20")
        total = roll.total + modifier
        c.initiative = total
        rolled.append(c)
        initiative_values.append((c.entity_id, total))
        state.combat_log.append(
            {
                "event": "initiative",
                "combatant": c.name,
                "roll": roll.rolls,
                "modifier": modifier,
                "total": total,
            }
        )

    # Sort by initiative descending
    initiative_values.sort(key=lambda x: x[1], reverse=True)
    order = [eid for eid, _ in initiative_values]

    first = order[0] if order else None
    first_name = next((c.name for c in rolled if c.entity_id == first), "Unknown")

    logger.info(
        "Combat initiative: %d combatants, first=%s (%d)",
        len(order),
        first_name,
        initiative_values[0][1] if initiative_values else 0,
    )

    return {
        "combatants": [c.model_dump() for c in rolled],
        "initiative_order": order,
        "current_index": 0,
        "current_combatant_id": first,
        "round_number": 1,
        "awaiting_pc_input": any(c.is_pc and c.entity_id == first for c in rolled),
    }


async def choose_combatant(state: CombatState) -> Dict[str, Any]:
    """
    Select the current combatant's action.

    If the current combatant is a PC, set awaiting_pc_input=True and pause.
    If NPC, auto-resolve with a simple decision.
    """
    order = state.initiative_order
    if not order or state.current_index >= len(order):
        return {"combat_active": False}

    eid = order[state.current_index]
    combatant = next((c for c in state.combatants if c.entity_id == eid), None)
    if combatant is None or not combatant.is_active:
        # Skip dead/inactive combatants
        return {
            "current_index": state.current_index + 1,
            "current_combatant_id": None,
        }

    state.current_combatant_id = eid

    if combatant.is_pc:
        return {
            "current_combatant_id": eid,
            "awaiting_pc_input": True,
        }

    # NPC auto-action: pick a simple combat action
    target = _pick_npc_target(state, eid)
    if target is None:
        # No valid target — skip NPC turn
        return {
            "current_index": state.current_index + 1,
            "current_combatant_id": None,
        }

    action = f"{combatant.name} attacks {target.name}"
    state.user_input = action
    return {
        "current_combatant_id": eid,
        "user_input": action,
        "awaiting_pc_input": False,
    }


def _pick_npc_target(
    state: CombatState,
    npc_id: UUID,
) -> CombatantState | None:
    """Pick a valid target for an NPC: prefer PCs, fall back to nearest active."""
    pc_targets = [c for c in state.combatants if c.is_pc and c.is_active]
    if pc_targets:
        return pc_targets[0]
    other_targets = [c for c in state.combatants if c.entity_id != npc_id and c.is_active]
    return other_targets[0] if other_targets else None


async def resolve_combat_action(state: CombatState) -> Dict[str, Any]:
    """
    Resolve the current combatant's action using opposed checks.

    Attacker vs Defender → Resolver.resolve_opposed_check().
    """
    if state.awaiting_pc_input or not state.user_input:
        return {}

    from monitor_agents.resolver import Resolver

    attacker = next(
        (c for c in state.combatants if c.entity_id == state.current_combatant_id),
        None,
    )
    if attacker is None:
        return {}

    # Find target from combat log or pick nearest enemy
    target = _find_target_in_action(state, attacker)

    resolver = Resolver()
    gsr = None
    if state.game_context:
        from monitor_agents.game_system import GameSystemRuntime

        gsr = GameSystemRuntime(state.game_context)

    if target is not None:
        # Infer combat stat: e.g. "Strength" for melee, "Dexterity" for ranged
        # For now, default to Strength or use GSR to infer from user_input
        stat_name = "Strength"
        if gsr:
            try:
                # Use GSR to infer the best stat for the action
                inferred_stat, _, _ = gsr.infer_action_stat(state.user_input)
                if inferred_stat:
                    stat_name = inferred_stat
            except Exception:
                pass

        # Opposed check: attacker vs target
        result = await resolver.resolve_opposed_check(
            actor_id=str(attacker.entity_id),
            target_id=str(target.entity_id),
            stat_name=stat_name,
            context={"entities": state.entity_context, "turns": []},
            gsr=gsr,
        )
    else:
        # No target — simple action resolution
        result = await resolver.resolve_turn(
            scene_id=str(state.scene_id),
            user_input=state.user_input or "attack",
            context={"entities": state.entity_context, "turns": []},
            game_context=state.game_context,
            play_mode="dice_standard",
        )

    # Apply HP damage based on result
    if target is not None:
        margin = result.get("margin", 0)
        if result.get("winner") == "actor" and margin > 0:
            damage = max(1, margin)
            _apply_damage(state, target.entity_id, damage, gsr=gsr)
            state.combat_log.append(
                {
                    "event": "hit",
                    "attacker": attacker.name,
                    "target": target.name,
                    "damage": damage,
                    "margin": margin,
                    "target_hp_after": _get_hp(state, target.entity_id),
                }
            )
        else:
            state.combat_log.append(
                {
                    "event": "miss",
                    "attacker": attacker.name,
                    "target": target.name,
                }
            )

    return {
        "resolution": result,
        "combat_log": state.combat_log,
        "combatants": [c.model_dump() for c in state.combatants],
    }


def _find_target_in_action(
    state: CombatState,
    attacker: CombatantState,
) -> CombatantState | None:
    """Find the target of the attacker's action. Default: nearest enemy."""
    enemies = [c for c in state.combatants if c.is_pc != attacker.is_pc and c.is_active]
    return enemies[0] if enemies else None


def _apply_damage(
    state: CombatState,
    entity_id: UUID,
    damage: int,
    gsr: Any | None = None,
) -> None:
    """Apply damage to a combatant, using GameSystemRuntime for rules if available."""
    for c in state.combatants:
        if c.entity_id == entity_id:
            if gsr:
                try:
                    # Map CombatantState to a flat dict for gsr
                    current_stats = {**c.attributes, "HP": c.hp_current}
                    # Default damage type to "lethal" or "standard"
                    damage_result = gsr.apply_damage("standard", damage, current_stats)

                    # Update HP from track_updates
                    track_name = (
                        gsr.get_damage_model().get("damage_track", "HP")
                        if gsr.get_damage_model()
                        else "HP"
                    )
                    new_hp = damage_result["track_updates"].get(track_name, c.hp_current - damage)
                    c.hp_current = max(0, int(new_hp))

                    if damage_result.get("incapacitated") or damage_result.get("dead"):
                        c.is_active = False
                        c.conditions.append("incapacitated")
                    return
                except Exception as exc:
                    logger.warning("GSR apply_damage failed: %s", exc)

            # Fallback to simple HP subtraction
            c.hp_current = max(0, c.hp_current - damage)
            if c.hp_current <= 0:
                c.is_active = False
                c.conditions.append("unconscious")
            break


def _get_hp(state: CombatState, entity_id: UUID) -> int:
    """Get current HP for a combatant."""
    for c in state.combatants:
        if c.entity_id == entity_id:
            return c.hp_current
    return 0


async def narrate_combat(state: CombatState) -> Dict[str, Any]:
    """
    Generate combat narration for the current action.

    Uses Narrator with compact combat context.
    """
    if not state.resolution or state.awaiting_pc_input:
        return {}

    from monitor_agents.narrator import Narrator

    # Build compact combat context for the Narrator
    combat_context = _format_combat_context(state)
    enriched_context = {
        "entities": state.entity_context,
        "memories": [],
        "turns": [{"turn_id": "combat", "content": combat_context}],
        "source_profile": state.source_profile,
    }

    narrator = Narrator()
    result = await narrator.narrate_turn(
        scene_id=state.scene_id,
        user_input=state.user_input,
        resolution=state.resolution,
        context=enriched_context,
        game_context=state.game_context,
        session_tone=state.session_tone,
        gm_profile=state.gm_profile,
    )

    return {
        "narrative_text": result.get("narrative_text", ""),
        "proposals": result.get("proposals", []),
    }


def _format_combat_context(state: CombatState) -> str:
    """Build a compact textual summary of the combat state for the Narrator."""
    lines = [
        f"COMBAT — Round {state.round_number}",
        "Initiative order:",
    ]
    for eid in state.initiative_order:
        c = next((c for c in state.combatants if c.entity_id == eid), None)
        if c:
            marker = "→ " if c.entity_id == state.current_combatant_id else "  "
            status = f"HP {c.hp_current}/{c.hp_max}" if c.is_active else "DOWN"
            lines.append(f"{marker}{c.name} ({status})")

    lines.append("\nRecent events:")
    for entry in state.combat_log[-5:]:
        ev = entry.get("event", "?")
        if ev == "initiative":
            lines.append(f"  {entry['combatant']} initiative {entry['total']}")
        elif ev == "hit":
            lines.append(
                f"  {entry['attacker']} hits {entry['target']} for {entry['damage']} damage"
            )
        elif ev == "miss":
            lines.append(f"  {entry['attacker']} misses {entry['target']}")

    return "\n".join(lines)


async def check_victory(state: CombatState) -> Dict[str, Any]:
    """
    Check if combat should end.

    Victory conditions:
    - All PCs are inactive → enemy victory
    - All enemies are inactive → PC victory
    - Otherwise → advance to next combatant
    """
    pcs = [c for c in state.combatants if c.is_pc]
    enemies = [c for c in state.combatants if not c.is_pc]

    pcs_active = [c for c in pcs if c.is_active]
    enemies_active = [c for c in enemies if c.is_active]

    if not pcs_active:
        logger.info("Combat ended: all PCs down")
        return {
            "combat_active": False,
            "victory_side": "enemy",
        }

    if not enemies_active:
        logger.info("Combat ended: all enemies defeated")
        return {
            "combat_active": False,
            "victory_side": "pc",
        }

    # Advance to next combatant
    next_index = state.current_index + 1
    if next_index >= len(state.initiative_order):
        # Start new round
        next_index = 0
        new_round = state.round_number + 1
    else:
        new_round = state.round_number

    next_eid = (
        state.initiative_order[next_index] if next_index < len(state.initiative_order) else None
    )
    next_is_pc = any(c.is_pc and c.entity_id == next_eid and c.is_active for c in state.combatants)

    return {
        "current_index": next_index,
        "round_number": new_round,
        "current_combatant_id": next_eid,
        "awaiting_pc_input": next_is_pc,
        "combat_active": True,
        "resolution": None,
        "narrative_text": None,
        "user_input": None,
        "combatants": [c.model_dump() for c in state.combatants],
    }


# =============================================================================
# ROUTING
# =============================================================================


def route_after_choose(state: CombatState) -> str:
    """After choosing combatant: resolve if NPC, pause if PC."""
    if state.awaiting_pc_input:
        return "pause"
    return "resolve"


def route_after_check(state: CombatState) -> str:
    """After victory check: continue or end."""
    if state.combat_active:
        return "choose"
    return "end"


# =============================================================================
# PUBLIC API
# =============================================================================


class CombatLoop:
    """
    Manages a single tactical combat encounter within a scene.

    Combat is embedded in SceneLoop — when the scene detects a combat action,
    it delegates to CombatLoop until combat ends.

    Usage:
        loop = CombatLoop(
            scene_id=scene_id,
            story_id=story_id,
            combatants=[...],
            entity_context=entities,
            game_context=game_system_doc,
        )
        # For PC turns: call step(user_input) and check state.awaiting_pc_input
        # For NPC turns: call advance() repeatedly until awaiting_pc_input
        result = await loop.step("I attack the orc")
    """

    def __init__(
        self,
        scene_id: UUID,
        story_id: UUID,
        combatants: List[CombatantState],
        entity_context: List[Dict[str, Any]] | None = None,
        game_context: Dict[str, Any] | None = None,
        source_profile: Dict[str, Any] | None = None,
        gm_profile: Dict[str, Any] | None = None,
        session_tone: str = "dramatic",
    ) -> None:
        self.scene_id = scene_id
        self.story_id = story_id
        self.state = CombatState(
            scene_id=scene_id,
            story_id=story_id,
            combatants=combatants,
            entity_context=entity_context or [],
            game_context=game_context or {},
            source_profile=source_profile or {},
            gm_profile=gm_profile,
            session_tone=session_tone,
        )

    async def start(self) -> Dict[str, Any]:
        """Roll initiative and prepare the first turn."""
        updates = await roll_initiative(self.state)
        self._apply_updates(updates)
        # Choose the first combatant
        choose_updates = await choose_combatant(self.state)
        self._apply_updates(choose_updates)
        return self._snapshot()

    async def step(self, user_input: str) -> Dict[str, Any]:
        """
        Execute one PC combat action.

        Call this when awaiting_pc_input is True.
        """
        self.state.user_input = user_input
        self.state.awaiting_pc_input = False

        # Resolve
        resolve_updates = await resolve_combat_action(self.state)
        self._apply_updates(resolve_updates)

        # Narrate
        narrate_updates = await narrate_combat(self.state)
        self._apply_updates(narrate_updates)

        # Check victory and advance
        check_updates = await check_victory(self.state)
        self._apply_updates(check_updates)

        # If next combatant is NPC, auto-advance
        if self.state.combat_active and not self.state.awaiting_pc_input:
            await self._advance_npc_turns()

        return self._snapshot()

    async def _advance_npc_turns(self) -> None:
        """Auto-resolve NPC turns until next PC turn or combat end."""
        max_iter = 20  # safety limit
        for _ in range(max_iter):
            if not self.state.combat_active or self.state.awaiting_pc_input:
                break

            choose_updates = await choose_combatant(self.state)
            self._apply_updates(choose_updates)

            if self.state.awaiting_pc_input:
                break

            resolve_updates = await resolve_combat_action(self.state)
            self._apply_updates(resolve_updates)

            narrate_updates = await narrate_combat(self.state)
            self._apply_updates(narrate_updates)

            check_updates = await check_victory(self.state)
            self._apply_updates(check_updates)

    def _apply_updates(self, updates: Dict[str, Any]) -> None:
        """Apply a dict of updates to the CombatState fields."""
        for key, value in updates.items():
            if hasattr(self.state, key):
                if key == "combatants" and isinstance(value, list):
                    self.state.combatants = [
                        CombatantState(**c) if isinstance(c, dict) else c for c in value
                    ]
                elif key == "combat_log" and isinstance(value, list):
                    self.state.combat_log = value
                else:
                    setattr(self.state, key, value)

    def _snapshot(self) -> Dict[str, Any]:
        """Return a dict snapshot of the current combat state for SceneLoop."""
        return {
            "combat_active": self.state.combat_active,
            "victory_side": self.state.victory_side,
            "narrative_text": self.state.narrative_text or "",
            "combat_log": self.state.combat_log,
            "combatants": [
                {
                    "entity_id": str(c.entity_id),
                    "name": c.name,
                    "initiative": c.initiative,
                    "is_pc": c.is_pc,
                    "hp_current": c.hp_current,
                    "hp_max": c.hp_max,
                    "is_active": c.is_active,
                    "conditions": c.conditions,
                }
                for c in self.state.combatants
            ],
            "round_number": self.state.round_number,
            "awaiting_pc_input": self.state.awaiting_pc_input,
            "pending_proposals": self.state.pending_proposals,
            "resolution": self.state.resolution,
        }
