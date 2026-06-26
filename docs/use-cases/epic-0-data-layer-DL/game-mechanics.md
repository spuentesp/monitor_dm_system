## DL-20: Manage Game Systems & Rules (MongoDB)

**Purpose:** Store game system definitions for system-agnostic play.

- Inputs:
  - Game system: name, description, core_mechanic, attributes, skills, resources, custom_dice
  - Rule override: scope, scope_id, target, original, override, reason

- Behavior:
  - CRUD game_systems collection
  - CRUD rule_overrides collection
  - Store built-in system definitions

- Cross-refs:
  - Universe (system_name reference)
  - Resolutions (DL-24)

- Outputs:
  - Game system documents
  - Rule override documents

**MongoDB Schema:**
```javascript
// game_systems
{
  _id: ObjectId,
  system_id: UUID,
  name: string,
  description: string,
  version: string,

  core_mechanic: {
    type: enum["d20", "dice_pool", "percentile", "card", "narrative"],
    formula: string,
    success_type: enum["meet_or_beat", "count_successes", "highest_wins"],
    success_threshold: string,
    critical_success: string,
    critical_failure: string
  },

  attributes: [
    {
      name: string,
      abbreviation: string,
      min_value: int,
      max_value: int,
      default_value: int,
      modifier_formula: string
    }
  ],

  skills: [...],
  resources: [...],
  custom_dice: map,

  is_builtin: bool,
  created_at: ISODate,
  updated_at: ISODate
}

// rule_overrides
{
  _id: ObjectId,
  override_id: UUID,
  scope: enum["one_time", "scene", "story", "universe"],
  scope_id: UUID,
  target: string,
  original: string,
  override: string,
  reason: string,
  times_used: int,
  active: bool,
  created_at: ISODate
}
```

**MCP Tools (CRUD only):**
```python
mongodb_create_game_system(name, description, core_mechanic, attributes, ...) -> system_id
mongodb_get_game_system(system_id) -> GameSystem
mongodb_list_game_systems(include_builtin?, limit?, offset?) -> list[GameSystem]
mongodb_update_game_system(system_id, updates) -> GameSystem
mongodb_delete_game_system(system_id)

mongodb_create_rule_override(scope, scope_id, target, original, override, reason) -> override_id
mongodb_get_rule_override(override_id) -> RuleOverride
mongodb_list_rule_overrides(scope, scope_id, active_only?) -> list[RuleOverride]
mongodb_update_rule_override(override_id, active?, times_used?)
mongodb_delete_rule_override(override_id)
```

> **Note:** Rule interpretation and dice mechanics live in agents layer utilities.

---

## DL-21: Manage Random Tables (MongoDB)

**Purpose:** Store table definitions for procedural generation.

- Inputs:
  - Table: universe_id, name, table_type, entries[], dice_formula, weighted
  - Entry: value, weight, min_roll, max_roll, subtable_id, conditions

- Behavior:
  - CRUD random_tables collection
  - Store table entries with roll ranges or weights

- Cross-refs:
  - Entity templates (DL-17)
  - Universe

- Outputs:
  - Table documents

**MongoDB Schema:**
```javascript
// random_tables
{
  _id: ObjectId,
  table_id: UUID,
  universe_id: UUID,

  name: string,
  description: string,
  table_type: enum["encounter", "loot", "name", "trait", "weather", "custom"],

  dice_formula: string,
  weighted: bool,

  entries: [
    {
      min_roll: int,
      max_roll: int,
      weight: float,
      value: string,
      subtable_id: UUID,
      conditions: map
    }
  ],

  created_at: ISODate,
  updated_at: ISODate
}
```

**MCP Tools (CRUD only):**
```python
mongodb_create_random_table(universe_id, name, table_type, dice_formula?, entries) -> table_id
mongodb_get_random_table(table_id) -> RandomTable
mongodb_list_random_tables(universe_id?, table_type?, limit?, offset?) -> list[RandomTable]
mongodb_update_random_table(table_id, updates) -> RandomTable
mongodb_delete_random_table(table_id)

mongodb_add_table_entry(table_id, entry)
mongodb_update_table_entry(table_id, entry_index, updates)
mongodb_remove_table_entry(table_id, entry_index)
```

> **Note:** Dice rolling and entry selection logic live in agents layer utilities.

---

## DL-22: Manage Card Deck State (MongoDB)

**Purpose:** Store card deck definitions and runtime state.

- Inputs:
  - Deck Definition: game_system_id, deck_type, cards[], suit_meanings
  - Deck State: story_id, deck_id, draw_pile[], discard_pile[], held_cards{}
  - Card Draw: state_id, drawn_by, cards[], purpose

- Behavior:
  - CRUD card_decks collection (definitions)
  - CRUD deck_states collection (runtime)
  - CRUD card_draws collection (history)

- Cross-refs:
  - Game systems (DL-20)
  - Stories (deck state per story)
  - Entities (hands per character)

- Outputs:
  - Deck definition documents
  - Runtime state documents
  - Draw history documents

**MongoDB Schema:**
```javascript
// card_decks (definitions)
{
  _id: ObjectId,
  deck_id: UUID,
  game_system_id: UUID,
  name: string,
  deck_type: enum["standard", "standard_jokers", "tarot", "custom"],
  cards: [
    {
      card_id: string,
      suit: string,
      value: string,
      numeric_value: int,
      display_name: string,
      short_name: string
    }
  ],
  suit_meanings: map,
  reshuffle_on: [string],
  created_at: ISODate
}

// deck_states (runtime)
{
  _id: ObjectId,
  state_id: UUID,
  deck_id: UUID,
  story_id: UUID,
  draw_pile: [string],
  discard_pile: [string],
  held_cards: map,
  total_draws: int,
  last_draw: ISODate,
  created_at: ISODate
}

// card_draws (history)
{
  _id: ObjectId,
  draw_id: UUID,
  state_id: UUID,
  scene_id: UUID,
  turn_id: UUID,
  drawn_by: UUID,
  cards: [string],
  draw_type: string,
  purpose: string,
  interpretation: string,
  drawn_at: ISODate
}
```

**MCP Tools (CRUD only):**
```python
# Deck definitions
mongodb_create_card_deck(game_system_id, name, deck_type, cards, ...) -> deck_id
mongodb_get_card_deck(deck_id) -> CardDeck
mongodb_list_card_decks(game_system_id?, deck_type?) -> list[CardDeck]
mongodb_update_card_deck(deck_id, updates)
mongodb_delete_card_deck(deck_id)

# Runtime state
mongodb_create_deck_state(deck_id, story_id, draw_pile, discard_pile?, held_cards?) -> state_id
mongodb_get_deck_state(state_id) -> DeckState
mongodb_get_deck_state_by_story(story_id, deck_id) -> DeckState
mongodb_update_deck_state(state_id, draw_pile?, discard_pile?, held_cards?, total_draws?)
mongodb_delete_deck_state(state_id)

# Draw history
mongodb_create_card_draw(state_id, scene_id?, turn_id?, drawn_by, cards, draw_type, purpose?)
mongodb_list_card_draws(state_id?, scene_id?, drawn_by?, limit?) -> list[CardDraw]
```

> **Note:** Shuffle algorithms, card selection, and hand management logic live in agents layer utilities.

---

## DL-23: Manage World Snapshots (MongoDB)

**Purpose:** Store point-in-time snapshots of world state.

- Inputs:
  - Snapshot: scope, scope_id, name, trigger
  - Captured state: entities[], facts[], relationships[], axioms[]

- Behavior:
  - CRUD world_snapshots collection
  - Store denormalized state data

- Cross-refs:
  - Neo4j (source of captured state)
  - Stories/Scenes (auto-snapshot at milestones)

- Outputs:
  - Snapshot documents

**MongoDB Schema:**
```javascript
// world_snapshots
{
  _id: ObjectId,
  snapshot_id: UUID,

  name: string,
  description: string,

  scope: enum["universe", "story", "region"],
  scope_id: UUID,

  entities: [
    {
      entity_id: UUID,
      entity_type: string,
      name: string,
      properties: map,
      state_tags: [string]
    }
  ],

  facts: [...],
  relationships: [...],
  axioms: [...],

  story_state: {
    current_scene_id: UUID,
    scene_count: int,
    turn_count: int,
    story_status: string
  },

  trigger: enum["manual", "story_start", "milestone", "pre_branch", "pre_flashback", "scheduled"],
  created_at: ISODate,
  created_by: string,

  entity_count: int,
  fact_count: int,
  total_size_kb: int,

  parent_snapshot_id: UUID,
  branched_to: [UUID]
}
```

**MCP Tools (CRUD only):**
```python
mongodb_create_snapshot(scope, scope_id, name, trigger, entities, facts, relationships, axioms, story_state?) -> snapshot_id
mongodb_get_snapshot(snapshot_id) -> WorldSnapshot
mongodb_list_snapshots(scope?, scope_id?, trigger?, limit?, offset?) -> list[WorldSnapshot]
mongodb_delete_snapshot(snapshot_id)
```

> **Note:** Snapshot capture orchestration (batch read from Neo4j) and diff algorithms live in agents layer.

---

