## DL-24: Manage Turn Resolutions (MongoDB)

**Purpose:** Store mechanical resolution records for gameplay actions.

- Inputs:
  - Resolution: turn_id, scene_id, actor_id, action, action_type, resolution_type, mechanics, success_level, effects

- Behavior:
  - CRUD resolutions collection
  - Store pre-computed resolution data

- Cross-refs:
  - Turns (DL-4)
  - Game Systems (DL-20)
  - Entities (DL-2)

- Outputs:
  - Resolution documents

**MongoDB Schema:**
```javascript
// resolutions
{
  _id: ObjectId,
  resolution_id: UUID,
  turn_id: UUID,
  scene_id: UUID,
  story_id: UUID,

  actor_id: UUID,
  action: string,
  action_type: enum["combat", "skill", "social", "exploration", "magic", "other"],

  resolution_type: enum["dice", "card", "narrative", "deterministic", "contested"],

  mechanics: {
    game_system_id: UUID,
    formula: string,
    modifiers: [
      {source: string, value: int, reason: string}
    ],
    target: int,
    target_source: string,

    roll: {
      raw_rolls: [int],
      kept_rolls: [int],
      total: int,
      natural: int,
      critical: bool,
      fumble: bool
    },

    card_draw: {
      deck_id: UUID,
      cards: [string],
      interpretation: string
    },

    opposed: {
      defender_id: UUID,
      defender_roll: {...}
    }
  },

  success_level: enum["critical_success", "success", "partial_success", "failure", "critical_failure"],
  margin: int,

  effects: [
    {
      effect_type: enum["damage", "healing", "condition", "resource", "state_change", "narrative"],
      target_id: UUID,
      magnitude: int,
      damage_type: string,
      condition: string,
      duration: string,
      description: string
    }
  ],

  description: string,
  gm_notes: string,

  created_at: ISODate
}
```

**MCP Tools (CRUD only):**
```python
mongodb_create_resolution(turn_id, scene_id, story_id, actor_id, action, action_type, resolution_type, mechanics, success_level, margin?, effects?, description?) -> resolution_id
mongodb_get_resolution(resolution_id) -> Resolution
mongodb_list_resolutions(scene_id?, turn_id?, actor_id?, action_type?, success_level?, limit?, offset?) -> list[Resolution]
mongodb_update_resolution(resolution_id, effects?, description?, gm_notes?)
mongodb_delete_resolution(resolution_id)
```

> **Note:** Dice rolling, success evaluation, damage calculation, and effect application logic live in agents layer utilities. This collection stores the RESULTS of those computations.

---

## DL-25: Manage Combat State (MongoDB)

**Purpose:** Store combat encounter state.

- Inputs:
  - Encounter: scene_id, story_id, participants[], environment
  - Participant: entity_id, name, side, initiative_value, conditions[], resources{}

- Behavior:
  - CRUD combat_encounters collection
  - Store participant state and turn tracking

- Cross-refs:
  - Scenes (DL-4)
  - Entities (DL-2)
  - Resolutions (DL-24)

- Outputs:
  - Combat encounter documents

**MongoDB Schema:**
```javascript
// combat_encounters
{
  _id: ObjectId,
  encounter_id: UUID,
  scene_id: UUID,
  story_id: UUID,

  status: enum["initializing", "initiative", "active", "paused", "resolved"],
  started_at: ISODate,
  ended_at: ISODate,

  participants: [
    {
      entity_id: UUID,
      name: string,
      side: enum["pc", "ally", "enemy", "neutral"],

      initiative_value: int,
      initiative_card: string,

      is_active: bool,
      is_current_turn: bool,
      has_acted_this_round: bool,

      position: { x: int, y: int, zone: string },

      conditions: [
        {
          name: string,
          source: string,
          duration: string,
          rounds_remaining: int,
          effects: map
        }
      ],

      resources: {
        hp: {current: int, max: int},
        temp_hp: int,
        ...
      },

      damage_dealt: int,
      damage_taken: int
    }
  ],

  round: int,
  turn_order: [UUID],
  current_turn_index: int,

  environment: {
    terrain: string,
    lighting: enum["bright", "dim", "dark"],
    hazards: [...],
    cover_positions: [string]
  },

  combat_log: [
    {
      round: int,
      turn: int,
      actor_id: UUID,
      action: string,
      resolution_id: UUID,
      summary: string,
      timestamp: ISODate
    }
  ],

  outcome: {
    result: enum["victory", "defeat", "flee", "surrender", "interrupted"],
    winning_side: string,
    survivors: [UUID],
    casualties: [UUID],
    loot: [string],
    xp_awarded: int
  }
}
```

**MCP Tools (CRUD only):**
```python
# Combat lifecycle
mongodb_create_combat(scene_id, story_id, participants?, environment?) -> encounter_id
mongodb_get_combat(encounter_id) -> CombatEncounter
mongodb_list_combats(scene_id?, story_id?, status?, limit?, offset?) -> list[CombatEncounter]
mongodb_update_combat(encounter_id, status?, round?, turn_order?, current_turn_index?)
mongodb_delete_combat(encounter_id)

# Participant management
mongodb_add_combat_participant(encounter_id, entity_id, name, side, initiative_value?, resources?)
mongodb_update_combat_participant(encounter_id, entity_id, initiative_value?, is_active?, conditions?, resources?, position?)
mongodb_remove_combat_participant(encounter_id, entity_id)

# Combat log
mongodb_add_combat_log_entry(encounter_id, round, turn, actor_id, action, resolution_id?, summary)

# Outcome
mongodb_set_combat_outcome(encounter_id, result, winning_side?, survivors?, casualties?, loot?, xp_awarded?)
```

> **Note:** Initiative rolling, turn advancement, defeat detection, damage/healing application, and combat flow orchestration live in agents layer.

---

## DL-26: Manage Character Working State (MongoDB)

**Purpose:** Store character working state during active gameplay.

- Inputs:
  - Working state: entity_id, scene_id, base_stats, current_stats, resources, modifications[], temporary_effects[]

- Behavior:
  - CRUD character_working_state collection
  - Store stat snapshots and modifications

- Cross-refs:
  - Entities (DL-2) - source of canonical stats
  - Scenes (DL-4) - working state scoped to scene
  - Resolutions (DL-24) - resolutions create modifications

- Outputs:
  - Working state documents

**MongoDB Schema:**
```javascript
// character_working_state
{
  _id: ObjectId,
  state_id: UUID,
  entity_id: UUID,
  scene_id: UUID,
  story_id: UUID,

  base_stats: {
    strength: int,
    dexterity: int,
    ...
  },

  current_stats: {
    strength: int,
    dexterity: int,
    ...
  },

  resources: {
    hp: {current: int, max: int, temp: int},
    mp: {current: int, max: int},
    ...
  },

  modifications: [
    {
      mod_id: UUID,
      stat_or_resource: string,
      change: int,
      source: string,
      source_id: UUID,
      timestamp: ISODate
    }
  ],

  temporary_effects: [
    {
      effect_id: UUID,
      name: string,
      source: string,
      stat_modifiers: map,
      duration_type: enum["rounds", "minutes", "scene", "concentration"],
      duration_remaining: int,
      applied_at: ISODate,
      expires_at: ISODate
    }
  ],

  inventory_changes: [
    {change_type: enum["add", "remove", "use"], item: string, quantity: int}
  ],

  created_at: ISODate,
  updated_at: ISODate,
  canonized: bool,
  canonized_at: ISODate
}
```

**MCP Tools (CRUD only):**
```python
# Working state lifecycle
mongodb_create_working_state(entity_id, scene_id, story_id, base_stats, current_stats, resources) -> state_id
mongodb_get_working_state(entity_id, scene_id) -> CharacterWorkingState
mongodb_get_working_state_by_id(state_id) -> CharacterWorkingState
mongodb_list_working_states(scene_id?, story_id?, canonized?, limit?, offset?) -> list[CharacterWorkingState]
mongodb_update_working_state(state_id, current_stats?, resources?)
mongodb_delete_working_state(state_id)

# Modifications tracking
mongodb_add_modification(state_id, stat_or_resource, change, source, source_id)

# Temporary effects
mongodb_add_temp_effect(state_id, name, source, stat_modifiers, duration_type, duration_remaining)
mongodb_update_temp_effect(state_id, effect_id, duration_remaining?)
mongodb_remove_temp_effect(state_id, effect_id)

# Inventory changes
mongodb_add_inventory_change(state_id, change_type, item, quantity)

# Canonization marker
mongodb_mark_canonized(state_id)
```

> **Note:** State initialization from Neo4j, effective stat calculation, duration ticking, and canonization sync to Neo4j live in agents layer.
