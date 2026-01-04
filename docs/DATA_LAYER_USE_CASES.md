# Data Layer Use Cases (DL-1 .. DL-26)

Data-layer viewpoints for each DL use case: inputs, behavior, cross-references, and outputs. These describe expected MCP tool behavior and storage-only concerns (no agents/CLI).

> **IMPORTANT:** This document describes PURE DATA STORAGE operations only. All business logic (dice rolling, success evaluation, combat flow, canonization sync) lives in the **agents layer**.

## DL-1: Manage Multiverse/Universes (Neo4j)
- Inputs: name, description, tags, parent_id (optional).
- Behavior: create/update/list/delete Universe nodes; validate unique name per parent; maintain HAS_UNIVERSE hierarchy.
- Cross-refs: Axioms, Sources, Entities, Stories link to Universe.
- Outputs: Universe record with id, hierarchy and tags.

## DL-2: Manage Archetypes & Instances (Neo4j)
- Inputs: universe_id, name, entity_type, description, properties, state_tags (instances), archetype_id (instances).
- Behavior: CRUD EntityArchetype/EntityInstance; maintain DERIVES_FROM (instance→archetype); enforce entity_type enum; state_tags only on instances.
- Cross-refs: Relationships, Facts/Events, PlotThreads, Scenes/Turns (participants), Memories.
- Outputs: Entity records with IDs and links.

## DL-3: Manage Facts & Events (Neo4j, provenance)
- Inputs: universe_id, statement/title, fact_type, entities involved, properties, source_ids/scene_ids/snippet_ids, canon_level/confidence, timestamps for timeline.
- Behavior: CRUD facts/events; SUPPORTED_BY edges to Source/Snippet/Scene; INVOLVES/ABOUT edges to entities; optional NEXT/BEFORE/AFTER timeline ordering; enforce canon_level enum.
- Cross-refs: Query/timeline views, provenance chains, PlotThreads.
- Outputs: Fact/Event records with provenance and timeline anchors.

## DL-4: Manage Stories, Scenes, Turns (Neo4j + MongoDB)
- Inputs: story metadata (Neo4j), scene/turn payloads (MongoDB), status transitions.
- Behavior: Create/update Story (Neo4j canonical container); Create/update/list Scene (MongoDB narrative), append Turns; optional canonical Scene node in Neo4j; enforce statuses.
- Cross-refs: Scenes link to Story, locations, participating entities; Turns reference Scene; Facts/Events may reference Scene.
- Outputs: Story IDs; scene/turn documents; status updates.

## DL-5: Manage Proposed Changes (MongoDB)
- Inputs: change_type (fact/entity/relationship/state_change/event), content payload, confidence/status, scope IDs (scene/story/universe).
- Behavior: CRUD ProposedChange; enforce change_type enum; status transitions (pending→accepted/rejected); preserve evidence refs.
- Cross-refs: Canonization consumes these; links to Scene/Story/Universe and Entities.
- Outputs: ProposedChange documents with IDs and status.

## DL-6: Manage Story Outlines & Plot Threads (MongoDB + Neo4j)
- Inputs:
  - Story Outline: story_id, theme, premise, constraints, beats[], structure_type, template, branching_points[], mystery_structure
  - Story Beat: beat_id, title, description, order, status, optional, related_threads[], required_for_threads[]
  - Mystery Structure: truth, question, core_clues[], bonus_clues[], red_herrings[], suspects[], current_player_theories[]
  - Plot Thread: story_id, title, thread_type, status, priority, urgency, deadline, scene_ids[], entity_ids[], foreshadowing_events[], revelation_events[], payoff_status, player_interest_level, gm_importance
- Behavior:
  - MongoDB: CRUD story_outline docs with beat manipulation (add, remove, update, reorder); track mystery clue discovery; auto-calculate pacing metrics (tension, completion, act progression); support branching narratives
  - Neo4j: CRUD PlotThread nodes with 5 relationship types (HAS_THREAD to Story, ADVANCED_BY to Scenes, INVOLVES to Entities, FORESHADOWS from Events, REVEALS from Events); track priority, urgency, deadlines; monitor foreshadowing/payoff status; filter by story/type/status/priority/entity
- Cross-refs: Story, Scenes, Entities, Facts/Events, Turns (beat completion tracking).
- Outputs:
  - Story outline docs with beats, mystery structure, pacing metrics, branching points
  - PlotThread nodes with all relationships and tracking metadata
  - Beat progression status (pending/in_progress/completed/skipped)
  - Clue discovery tracking (hidden/discovered/revealed)
  - Pacing analysis (estimated_completion, tension_level, scenes_since_major_event)

## DL-7: Manage Memories (MongoDB + Qdrant)
- Inputs: entity_id, text, scene_id/fact_id (optional), importance, metadata.
- Behavior: CRUD CharacterMemory docs (MongoDB); embed/recall via Qdrant; enforce importance range.
- Cross-refs: Entities, Scenes/Facts; Qdrant vectors keyed by memory_id/entity_id.
- Outputs: Memory docs; vector IDs; recall results.

## DL-8: Manage Sources, Documents, Snippets, Ingest Proposals (MongoDB + Neo4j)
- Inputs: source (title/type/canon_level/authority), document (minio_ref/filename/file_type), snippet (text/page), ingest proposals (proposal_type/content/confidence/status, evidence_snippet_ids).
- Behavior: CRUD Source (Neo4j) and Document/Snippet/IngestProposal (MongoDB); link Source to Universe; enforce proposal status; store evidence links; maintain provenance chains.
- Cross-refs: Facts/Axioms supported_by Source/Snippet; ingest pipeline consumes/creates proposals; Documents reference MinIO object.
- Outputs: IDs for source/doc/snippet/proposals; provenance links.

## DL-9: Manage Binary Assets (MinIO)
- Inputs: bucket/key/content-type/size/metadata, optional source_id/universe_id.
- Behavior: upload/download/delete/list objects; preserve metadata; return references (bucket/key).
- Cross-refs: Documents/Sources store minio_ref; ingest pipeline links binaries to sources.
- Outputs: Object reference and metadata.

## DL-10: Vector Index Operations (Qdrant)
- Inputs: payload (id, collection, vector, metadata including story_id/scene_id/entity_id/type).
- Behavior: upsert/search/delete embeddings; enforce collection names; return scored matches.
- Cross-refs: Scenes, Memories, Snippets; CLI/query uses these for semantic search.
- Outputs: Qdrant operation result; search hits with payload.

## DL-11: Text Search Index Operations (OpenSearch)
- Inputs: index name, document body (id, type, universe_id, text/snippet), query with filters.
- Behavior: index/update/delete documents; keyword search with filters; return highlights/snippets.
- Cross-refs: Sources/Snippets/Facts/Docs.
- Outputs: index ack; search hits with snippet and metadata.

## DL-12: MCP Server & Middleware (Auth/Validation/Health)
- Inputs: tool registry, authority matrix, schema validators.
- Behavior: register tools; apply auth and validation; expose health/status endpoint.
- Outputs: MCP tool list; health status.

## DL-13: Manage Axioms (Neo4j)
- Inputs: universe_id, statement, domain, confidence/canon_level/authority, source_ids/snippet_ids.
- Behavior: CRUD Axiom nodes; link to Universe and Source/Snippet via SUPPORTED_BY; enforce enums.
- Cross-refs: Facts and rules reasoning; documentation of world rules.
- Outputs: Axiom records with provenance.

## DL-14: Manage Relationships & State Tags (Neo4j)
- Inputs: from_id, to_id, rel_type, properties; state_tags updates (entity_id, tags).
- Behavior: CRUD relationships (membership/ownership/social/spatial/participation/etc.); update state_tags on EntityInstance; enforce rel_type enum; prevent invalid IDs.
- Cross-refs: Entities, Facts/Events, Scenes, PlotThreads.
- Outputs: Relationship records; updated entity state tags.

---

## DL-15: Manage Parties (Neo4j + MongoDB)

**Purpose:** Store party data for stories with multiple PCs/companions.

- Inputs:
  - Party: story_id, name, status
  - Membership: party_id, entity_id, role, position, joined_at
  - Active PC: party_id, entity_id

- Behavior:
  - CRUD Party nodes (Neo4j)
  - CRUD MEMBER_OF edges with role/position properties
  - CRUD ACTIVE_PC edge
  - Store party status enum

- Cross-refs:
  - Story (party belongs to story)
  - EntityInstance (members)
  - Party inventory (DL-16)

- Outputs:
  - Party node with ID
  - Membership edges with metadata

**MCP Tools (CRUD only):**
```python
neo4j_create_party(story_id, name, status?) -> party_id
neo4j_get_party(party_id) -> Party
neo4j_list_parties(story_id?, status?, limit, offset) -> list[Party]
neo4j_update_party(party_id, name?, status?) -> Party
neo4j_delete_party(party_id)

neo4j_add_party_member(party_id, entity_id, role, position?)
neo4j_update_party_member(party_id, entity_id, role?, position?)
neo4j_remove_party_member(party_id, entity_id)

neo4j_set_active_pc(party_id, entity_id)
neo4j_get_active_pc(party_id) -> entity_id
```

---

## DL-16: Manage Party Inventory & Splits (MongoDB)

**Purpose:** Store shared party inventory and split-party state.

- Inputs:
  - Inventory: party_id, items[], gold
  - Item: name, quantity, owner_id (optional), properties
  - Split: party_id, groups[], active_group_index

- Behavior:
  - CRUD party_inventories collection
  - CRUD party_splits collection
  - Store item data and ownership

- Cross-refs:
  - Party (DL-15)
  - EntityInstance (item owners)

- Outputs:
  - Inventory documents
  - Split state documents

**MongoDB Schema:**
```javascript
// party_inventories
{
  _id: ObjectId,
  party_id: UUID,
  items: [
    {
      item_id: UUID,
      name: string,
      quantity: int,
      weight: float,
      owner_id: UUID,
      properties: map
    }
  ],
  gold: int,
  updated_at: ISODate
}

// party_splits
{
  _id: ObjectId,
  split_id: UUID,
  party_id: UUID,
  groups: [
    {
      group_index: int,
      members: [UUID],
      location_id: UUID,
      status: enum["active", "offscreen", "waiting"],
      offscreen_summary: string
    }
  ],
  active_group_index: int,
  split_at: ISODate,
  reunited_at: ISODate
}
```

**MCP Tools (CRUD only):**
```python
mongodb_create_party_inventory(party_id, initial_gold?, initial_items?) -> inventory_id
mongodb_get_party_inventory(party_id) -> PartyInventory
mongodb_add_inventory_item(party_id, item)
mongodb_update_inventory_item(party_id, item_id, updates)
mongodb_remove_inventory_item(party_id, item_id)
mongodb_update_party_gold(party_id, gold)

mongodb_create_party_split(party_id, groups) -> split_id
mongodb_get_party_split(split_id) -> PartySplit
mongodb_get_active_split(party_id) -> PartySplit
mongodb_update_party_split(split_id, active_group_index?, groups?)
mongodb_delete_party_split(split_id)
```

---

## DL-17: Manage Entity Templates (MongoDB)

**Purpose:** Store reusable entity templates for world-building.

- Inputs:
  - Template: universe_id, name, entity_type, base_properties, variable_properties, naming_pattern, parent_template_id

- Behavior:
  - CRUD entity_templates collection
  - Store template structure and inheritance

- Cross-refs:
  - Universe (templates scoped to universe)
  - EntityArchetype (templates may reference archetypes)
  - Random tables (DL-21)

- Outputs:
  - Template documents

**MongoDB Schema:**
```javascript
// entity_templates
{
  _id: ObjectId,
  template_id: UUID,
  universe_id: UUID,
  name: string,
  description: string,

  entity_type: enum["character", "faction", "location", "object", "concept", "organization"],
  base_properties: map,

  variable_properties: [
    {
      property_path: string,
      generation_type: enum["fixed", "choice", "range", "pattern", "table", "llm"],
      options: [string],
      range: [int, int],
      pattern: string,
      table_id: UUID
    }
  ],

  naming_pattern: {
    type: enum["pattern", "numbered", "list", "llm", "user"],
    pattern: string,
    adjectives: [string],
    nouns: [string],
    name_list: [string]
  },

  default_state_tags: [string],
  equipment_options: [map],

  parent_template_id: UUID,

  usage_count: int,
  created_at: ISODate,
  updated_at: ISODate
}
```

**MCP Tools (CRUD only):**
```python
mongodb_create_template(universe_id, name, entity_type, base_properties, variable_properties?, ...) -> template_id
mongodb_get_template(template_id) -> EntityTemplate
mongodb_list_templates(universe_id?, entity_type?, limit, offset) -> list[EntityTemplate]
mongodb_update_template(template_id, updates) -> EntityTemplate
mongodb_delete_template(template_id)
```

> **Note:** Template instantiation logic (variable resolution, stat generation) lives in agents layer.

---

## DL-18: Manage Change Log (MongoDB - Event Sourcing)

**Purpose:** Store all changes to canonical data for audit trail.

- Inputs:
  - Change record: subject_type, subject_id, change_type, field_path, old_value, new_value, author, evidence_id, transaction_id

- Behavior:
  - Append-only change_log collection (never update/delete)
  - Store change records with timestamps
  - Index for efficient queries

- Cross-refs:
  - All Neo4j nodes (via subject_id)
  - Scenes, Turns (as evidence)

- Outputs:
  - Change records
  - Paginated history queries

**MongoDB Schema:**
```javascript
// change_log
{
  _id: ObjectId,
  change_id: UUID,

  subject_type: enum["entity", "fact", "event", "story", "scene", "relationship", "axiom", "party"],
  subject_id: UUID,

  change_type: enum["created", "updated", "deleted", "state_tag_added", "state_tag_removed", "relationship_added", "relationship_removed", "reverted"],

  timestamp: ISODate,

  field_path: string,
  old_value: any,
  new_value: any,

  author: string,
  authority: enum["source", "gm", "player", "system"],

  evidence_type: string,
  evidence_id: UUID,
  reason: string,

  transaction_id: UUID
}

Index: { subject_type: 1, subject_id: 1, timestamp: -1 }
Index: { timestamp: -1 }
Index: { transaction_id: 1 }
```

**MCP Tools (CRUD only):**
```python
mongodb_log_change(subject_type, subject_id, change_type, old_value, new_value, author, evidence_id?, transaction_id?)
mongodb_get_change_history(subject_type, subject_id, limit?, offset?, start_time?, end_time?) -> list[ChangeRecord]
mongodb_get_changes_by_time(start_time, end_time, subject_type?, limit?, offset?) -> list[ChangeRecord]
mongodb_get_transaction_changes(transaction_id) -> list[ChangeRecord]
```

---

## DL-19: Historical Queries (MongoDB)

**Purpose:** Query change log for historical data.

- Inputs:
  - Entity ID + target timestamp
  - Time range for history queries

- Behavior:
  - Query change_log by subject and time range
  - Return change records for reconstruction

- Cross-refs:
  - Change log (DL-18)
  - All canonical nodes

- Outputs:
  - Change records for time range
  - Timeline of changes

**MCP Tools (Query only):**
```python
mongodb_get_changes_after(subject_type, subject_id, after_timestamp) -> list[ChangeRecord]
mongodb_get_changes_between(subject_type, subject_id, start_time, end_time) -> list[ChangeRecord]
mongodb_get_entity_timeline(entity_id, limit?, offset?) -> list[ChangeRecord]
```

> **Note:** State reconstruction algorithms (reverse-apply changes) live in agents layer.

---

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
