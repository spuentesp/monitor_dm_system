# P-10: Combat Mode

**Actor:** User
**Trigger:** Combat initiated

**Flow:**
1. Identify combatants (PCs, NPCs, enemies)
2. Roll initiative (or use fixed order)
3. **Combat loop:**
   ```
   FOR each round:
     FOR each combatant (initiative order):
       IF PC: await player action → P-4
       IF NPC: Narrator decides action → P-4
       Apply resolution
       Check: death, flee, surrender, incapacitated
     END FOR
     Check: combat end conditions
   END FOR
   ```
4. On combat end:
   - Summarize results
   - Update entity states (HP, conditions)
   - Create facts (who won, casualties)
5. Return to P-3 or P-8

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_list_entities(location_id, type="character")  # Get combatants
mongodb_get_character_sheets(entity_ids)            # Get stats/HP
mongodb_update_character_sheet(entity_id, changes)  # Update HP/conditions
mongodb_append_turn(scene_id, combat_turn)          # Log combat actions
mongodb_create_proposal(scene_id, ...)              # State changes (death, etc.)
```

**Layer 2 (Agents):**
- `Orchestrator.enter_combat_mode(scene_id, combatants)` - Initialize combat
- `Resolver.roll_initiative(combatants)` - Roll and order
- `Resolver.resolve_attack(attacker, target, action)` - Combat resolution
- `Narrator.describe_combat_action(action, resolution)` - Narrate results
- `Narrator.decide_npc_action(npc, context)` - AI-controlled enemies

**Combat State Machine:**
```python
@dataclass
class CombatState:
    scene_id: UUID
    round: int = 1
    turn_order: list[Combatant] = field(default_factory=list)
    current_index: int = 0
    status: CombatStatus = CombatStatus.ACTIVE

class CombatStatus(Enum):
    INITIALIZING = "initializing"
    ACTIVE = "active"
    ENDING = "ending"
    ENDED = "ended"

@dataclass
class Combatant:
    entity_id: UUID
    name: str
    initiative: int
    is_pc: bool
    hp_current: int
    hp_max: int
    conditions: list[str] = field(default_factory=list)
    is_active: bool = True  # False if dead/fled/incapacitated
```

**Initiative Roll:**
```python
async def roll_initiative(combatants: list[UUID]) -> list[Combatant]:
    """Roll initiative for all combatants and return sorted order."""
    results = []

    for entity_id in combatants:
        entity = await neo4j_get_entity(entity_id)
        sheet = await mongodb_get_character_sheet(entity_id)

        # Roll 1d20 + DEX modifier (or initiative bonus)
        dex_mod = calculate_modifier(sheet.stats.get("DEX", 10))
        init_roll = roll_dice(f"1d20+{dex_mod}")

        results.append(Combatant(
            entity_id=entity_id,
            name=entity.name,
            initiative=init_roll.total,
            is_pc=(entity.properties.get("role") == "PC"),
            hp_current=sheet.resources.get("hp_current", 10),
            hp_max=sheet.resources.get("hp_max", 10)
        ))

    # Sort by initiative (descending), ties broken by DEX
    return sorted(results, key=lambda c: c.initiative, reverse=True)
```

**Combat Loop:**
```python
async def run_combat_loop(combat: CombatState, context: Context):
    """Main combat loop."""
    while combat.status == CombatStatus.ACTIVE:
        combatant = combat.turn_order[combat.current_index]

        if not combatant.is_active:
            # Skip incapacitated combatants
            combat.current_index = (combat.current_index + 1) % len(combat.turn_order)
            continue

        # Display turn prompt
        display_combat_status(combat)

        if combatant.is_pc:
            # Wait for player input
            action = await prompt_player_action(combatant)
        else:
            # AI decides NPC action
            action = await narrator.decide_npc_action(combatant, combat, context)

        # Resolve action
        resolution = await resolver.resolve_combat_action(action, combat, context)

        # Apply effects
        await apply_combat_effects(resolution, combat)

        # Log turn
        await mongodb_append_turn(context.scene_id, {
            "speaker": "entity" if not combatant.is_pc else "user",
            "entity_id": combatant.entity_id,
            "text": format_combat_action(action, resolution),
            "resolution_ref": resolution.id
        })

        # Check end conditions
        if check_combat_end(combat):
            combat.status = CombatStatus.ENDING
            break

        # Next turn
        combat.current_index = (combat.current_index + 1) % len(combat.turn_order)
        if combat.current_index == 0:
            combat.round += 1

    # Combat ended
    await end_combat(combat, context)
```

**Combat Resolution:**
```python
async def resolve_combat_action(
    action: CombatAction,
    combat: CombatState,
    context: Context
) -> CombatResolution:
    """Resolve a combat action (attack, spell, etc.)."""
    match action.type:
        case "attack":
            # Roll to hit
            attack_roll = roll_dice(f"1d20+{action.attack_bonus}")
            target_ac = await get_target_ac(action.target_id)

            if attack_roll.total >= target_ac:
                # Hit - roll damage
                damage_roll = roll_dice(action.damage_formula)
                return CombatResolution(
                    action=action,
                    attack_roll=attack_roll,
                    hit=True,
                    damage=damage_roll.total,
                    effects=[DamageEffect(action.target_id, damage_roll.total)]
                )
            else:
                return CombatResolution(action=action, attack_roll=attack_roll, hit=False)

        case "spell":
            # Handle spell save or attack
            pass

        case "move":
            # Handle movement
            pass

        case "disengage":
            # Allow flee without opportunity attack
            pass
```

**Combat End Conditions:**
```python
def check_combat_end(combat: CombatState) -> bool:
    """Check if combat should end."""
    pcs = [c for c in combat.turn_order if c.is_pc and c.is_active]
    enemies = [c for c in combat.turn_order if not c.is_pc and c.is_active]

    # All PCs down
    if not pcs:
        return True

    # All enemies down
    if not enemies:
        return True

    return False

async def end_combat(combat: CombatState, context: Context):
    """Finalize combat and create proposals for state changes."""
    # Create proposals for deaths
    for combatant in combat.turn_order:
        if combatant.hp_current <= 0:
            await mongodb_create_proposal(context.scene_id, {
                "type": "state_change",
                "content": {
                    "entity_id": combatant.entity_id,
                    "changes": {"add": ["dead"], "remove": ["alive"]}
                },
                "evidence": [context.scene_id],
                "authority": "system"
            })

    # Update character sheets with final HP
    for combatant in combat.turn_order:
        await mongodb_update_character_sheet(combatant.entity_id, {
            "resources.hp_current": max(0, combatant.hp_current)
        })

    # Generate combat summary
    summary = await narrator.summarize_combat(combat)
    await mongodb_append_turn(context.scene_id, {
        "speaker": "gm",
        "text": f"**Combat Ended**\n{summary}"
    })
```

**Database Writes:**

| Database | Collection | Data |
|----------|------------|------|
| MongoDB | `scenes.turns` | Combat action turns with resolution refs |
| MongoDB | `resolutions` | Attack rolls, damage, saves |
| MongoDB | `character_sheets` | HP updates during combat |
| MongoDB | `proposed_changes` | State changes (death, conditions) |

---
