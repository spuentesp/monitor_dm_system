# Data Layer Use Cases (DL-1 .. DL-14)

Data-layer viewpoints for each DL use case: inputs, behavior, cross-references, and outputs. These describe expected MCP tool behavior and storage-only concerns (no agents/CLI).

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
- Inputs: story_id, beats, pc_ids, status (outline); title/thread_type/status/description (plot thread).
- Behavior: CRUD story_outline docs (MongoDB); CRUD PlotThread nodes (Neo4j); link PlotThreads to Story and Scenes (ADVANCED_BY); optional linkage to Facts/Events.
- Cross-refs: Story, Scenes, Entities, Facts/Events.
- Outputs: Outline docs; PlotThread nodes/edges.

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

**Purpose:** Support party management for stories with multiple PCs/companions traveling together.

- Inputs:
  - Party: story_id, name, status
  - Membership: party_id, entity_id, role (pc/companion/hireling/mount), position (front/middle/rear), joined_at
  - Active PC: party_id, entity_id

- Behavior:
  - Create/update/delete Party nodes (Neo4j)
  - Manage MEMBER_OF edges with role/position properties
  - Track ACTIVE_PC edge (one per party)
  - Enforce one party per story (or allow multiple for complex stories)
  - Track party status: traveling, camping, in_scene, combat, split, resting

- Cross-refs:
  - Story (party belongs to story)
  - EntityInstance (members)
  - Scene (party participates in scene)
  - Party inventory (DL-16)

- Outputs:
  - Party node with ID
  - Membership edges with metadata
  - Active PC reference

**Cypher Examples:**
```cypher
// Create party
CREATE (p:Party {id: $id, story_id: $story_id, name: $name, status: "traveling", created_at: datetime()})

// Add member
MATCH (p:Party {id: $party_id}), (e:EntityInstance {id: $entity_id})
CREATE (e)-[:MEMBER_OF {role: $role, position: $position, joined_at: datetime()}]->(p)

// Set active PC
MATCH (p:Party {id: $party_id})-[old:ACTIVE_PC]->()
DELETE old
WITH p
MATCH (e:EntityInstance {id: $entity_id})
CREATE (p)-[:ACTIVE_PC]->(e)

// Get party with members
MATCH (p:Party {id: $party_id})<-[m:MEMBER_OF]-(e:EntityInstance)
RETURN p, collect({entity: e, role: m.role, position: m.position}) as members
```

---

## DL-16: Manage Party Inventory & Splits (MongoDB)

**Purpose:** Track shared party inventory and split-party state.

- Inputs:
  - Inventory: party_id, items[], gold, encumbrance
  - Item: name, quantity, owner_id (optional), properties
  - Split: party_id, groups[], active_group_index

- Behavior:
  - CRUD party_inventories collection
  - Add/remove/transfer items
  - Calculate encumbrance based on game system
  - Track item ownership within party (who's carrying what)
  - CRUD party_splits for split-party scenarios
  - Track which group is "active" (player focus)
  - Store off-screen summaries for inactive groups

- Cross-refs:
  - Party (DL-15)
  - EntityInstance (item owners)
  - Scene (splits may span scenes)

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
      owner_id: UUID,  // who's carrying it (null = party shared)
      properties: map
    }
  ],
  gold: int,
  encumbrance: { current: float, max: float },
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

---

## DL-17: Manage Entity Templates (MongoDB)

**Purpose:** Store reusable entity templates for efficient world-building.

- Inputs:
  - Template: universe_id, name, entity_type, base_properties, variable_properties, naming_pattern, stat_generation, default_state_tags, equipment_options, parent_template_id
  - Variable property: property_path, generation_type (fixed/choice/range/pattern/table/llm), options/range/pattern
  - Instantiation request: template_id, overrides, count

- Behavior:
  - CRUD entity_templates collection
  - Validate template structure (required fields per entity_type)
  - Support template inheritance (parent_template_id)
  - Generate entities from template with variable property resolution
  - Bulk instantiation with unique variations
  - Track template usage count

- Cross-refs:
  - Universe (templates scoped to universe)
  - EntityArchetype (templates may reference archetypes)
  - EntityInstance (created from templates)
  - Random tables (for table-based generation)

- Outputs:
  - Template documents
  - Generated entity parameters (for neo4j_create_entity)

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
      options: [string],      // for choice
      range: [int, int],      // for range
      pattern: string,        // for pattern
      table_id: UUID          // for table
    }
  ],

  naming_pattern: {
    type: enum["pattern", "numbered", "list", "llm", "user"],
    pattern: string,
    adjectives: [string],
    nouns: [string],
    name_list: [string]
  },

  stat_generation: {
    method: string,
    formulas: map,
    constraints: map
  },

  default_state_tags: [string],
  equipment_options: [map],

  parent_template_id: UUID,

  usage_count: int,
  created_at: ISODate,
  updated_at: ISODate
}
```

---

## DL-18: Manage Change Log (MongoDB - Event Sourcing)

**Purpose:** Record all changes to canonical data for audit trail and history reconstruction.

- Inputs:
  - Change record: subject_type, subject_id, change_type, field_path, old_value, new_value, author, authority, evidence_type, evidence_id, reason, transaction_id

- Behavior:
  - Append-only change_log collection (never update/delete)
  - Auto-capture all Neo4j write operations
  - Group related changes by transaction_id
  - Support filtering by subject, time range, change type, author
  - Efficient pagination for history queries

- Cross-refs:
  - All Neo4j nodes (via subject_id)
  - Scenes, Turns (as evidence)
  - Users/agents (as authors)

- Outputs:
  - Change records
  - Paginated history queries
  - Transaction groups

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

  field_path: string,  // e.g., "state_tags", "properties.hp"
  old_value: any,
  new_value: any,

  state_before: map,   // full snapshot (optional, for complex changes)
  state_after: map,

  author: string,      // "CanonKeeper", "User:123", "System"
  authority: enum["source", "gm", "player", "system"],

  evidence_type: string,  // "scene", "turn", "proposal", "manual"
  evidence_id: UUID,
  reason: string,

  transaction_id: UUID  // groups related changes
}

Index: { subject_type: 1, subject_id: 1, timestamp: -1 }
Index: { timestamp: -1 }
Index: { transaction_id: 1 }
Index: { author: 1, timestamp: -1 }
```

**Middleware Integration:**
All data-layer write operations MUST call `log_change()` before returning:
```python
async def log_change(
    subject_type: str,
    subject_id: UUID,
    change_type: str,
    old_value: Any,
    new_value: Any,
    author: str,
    evidence_id: UUID = None,
    transaction_id: UUID = None
):
    """Log a change to the audit trail."""
    await mongodb.change_log.insert_one({
        "change_id": str(uuid4()),
        "subject_type": subject_type,
        "subject_id": str(subject_id),
        "change_type": change_type,
        "timestamp": datetime.utcnow(),
        "old_value": old_value,
        "new_value": new_value,
        "author": author,
        "evidence_id": str(evidence_id) if evidence_id else None,
        "transaction_id": str(transaction_id) if transaction_id else None
    })
```

---

## DL-19: Historical Queries & State Reconstruction (Neo4j + MongoDB)

**Purpose:** Reconstruct entity state at any past point in time.

- Inputs:
  - Entity ID + target timestamp
  - Time range for history queries
  - Comparison timestamps (time_a, time_b)

- Behavior:
  - Query change_log to find all changes after target timestamp
  - Reverse-apply changes to reconstruct historical state
  - Support entity, fact, and relationship history
  - Compare two points in time (diff)
  - Support revert operation (creates new change, doesn't delete history)

- Cross-refs:
  - Change log (DL-18)
  - All canonical nodes
  - Facts (for revert evidence)

- Outputs:
  - Historical entity state
  - Change diff between timestamps
  - Timeline of changes

**Key Operations:**
```python
# Get entity at past time
async def get_entity_at_time(entity_id: UUID, target_time: datetime) -> Entity:
    # 1. Get current state
    current = await neo4j_get_entity(entity_id)

    # 2. Get all changes after target_time
    changes = await mongodb.change_log.find({
        "subject_type": "entity",
        "subject_id": str(entity_id),
        "timestamp": {"$gt": target_time}
    }).sort("timestamp", -1).to_list(None)

    # 3. Reverse-apply changes
    historical = reverse_apply_changes(current, changes)

    return historical

# Compare two points in time
async def compare_entity_versions(
    entity_id: UUID,
    time_a: datetime,
    time_b: datetime
) -> Comparison:
    state_a = await get_entity_at_time(entity_id, time_a)
    state_b = await get_entity_at_time(entity_id, time_b)

    changes = await mongodb.change_log.find({
        "subject_type": "entity",
        "subject_id": str(entity_id),
        "timestamp": {"$gt": time_a, "$lte": time_b}
    }).to_list(None)

    return Comparison(
        state_a=state_a,
        state_b=state_b,
        changes=changes,
        diff=compute_diff(state_a, state_b)
    )

# Revert to past state (creates new change, preserves history)
async def revert_entity_to_time(
    entity_id: UUID,
    target_time: datetime,
    reason: str
) -> UUID:
    historical = await get_entity_at_time(entity_id, target_time)

    # Update entity to historical state
    await neo4j_update_entity(entity_id, historical.to_dict())

    # Log as "reverted" change type
    await log_change(
        subject_type="entity",
        subject_id=entity_id,
        change_type="reverted",
        old_value=current.to_dict(),
        new_value=historical.to_dict(),
        author="User",
        reason=reason
    )

    # Create fact documenting the revert
    fact_id = await neo4j_create_fact({
        "statement": f"State reverted to {target_time}",
        "authority": "gm"
    })

    return fact_id
```

---

## DL-20: Manage Game Systems & Rules (MongoDB)

**Purpose:** Store and retrieve game system definitions for system-agnostic play.

- Inputs:
  - Game system: name, description, core_mechanic, attributes, skills, resources, combat_rules, custom_dice
  - Character template: system_id, sections, creation_rules, advancement_rules
  - Rule override: scope, target, original, override, reason

- Behavior:
  - CRUD game_systems collection
  - CRUD character_templates (nested in game_systems or separate)
  - CRUD rule_overrides (scoped to story/scene/universe)
  - Validate system definitions (required fields)
  - Support built-in templates (D&D 5e, Fate, etc.)
  - Import/export systems as JSON

- Cross-refs:
  - Multiverse/Universe (system_name reference)
  - Character sheets (use system for stat definitions)
  - Resolver agent (uses system for dice mechanics)

- Outputs:
  - Game system documents
  - Character templates
  - Active rule overrides

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

  skills: [
    {
      name: string,
      attribute: string,
      category: string,
      trained_bonus: int
    }
  ],

  resources: [
    {
      name: string,
      abbreviation: string,
      max_formula: string,
      recovery_rules: string,
      depleted_effect: string
    }
  ],

  custom_dice: map,  // {"advantage": "2d20kh1"}

  character_template: {...},

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

  target: enum["dice", "threshold", "resource", "skill", "custom"],
  original: string,
  override: string,

  reason: string,
  created_by: string,

  times_used: int,
  active: bool,

  created_at: ISODate
}
```

---

## DL-21: Manage Random Tables (MongoDB)

**Purpose:** Support table-based random generation for templates, encounters, and narrative elements.

- Inputs:
  - Table: universe_id, name, table_type, entries[], dice_formula, weighted
  - Entry: value, weight, min_roll, max_roll, subtable_id

- Behavior:
  - CRUD random_tables collection
  - Roll on table with dice formula
  - Support weighted entries
  - Support subtables (nested rolls)
  - Support conditional entries (based on context)

- Cross-refs:
  - Entity templates (DL-17)
  - Universe (tables scoped to universe or global)
  - Game systems (dice formulas)

- Outputs:
  - Table documents
  - Roll results

**MongoDB Schema:**
```javascript
// random_tables
{
  _id: ObjectId,
  table_id: UUID,
  universe_id: UUID,  // null for global tables

  name: string,
  description: string,
  table_type: enum["encounter", "loot", "name", "trait", "weather", "custom"],

  dice_formula: string,  // "1d100", "2d6"
  weighted: bool,

  entries: [
    {
      min_roll: int,
      max_roll: int,
      weight: float,       // for weighted tables
      value: string,       // the result
      subtable_id: UUID,   // optional nested table
      conditions: map      // optional conditions
    }
  ],

  created_at: ISODate,
  updated_at: ISODate
}
```

---

## DL-22: Manage Card Deck State (MongoDB)

**Purpose:** Support card-based RPG mechanics with deck, discard pile, and hand management.

- Inputs:
  - Deck Definition: game_system_id, deck_type, cards[], include_jokers, reshuffle_on[], suit_meanings
  - Deck State: story_id, deck_id, draw_pile[], discard_pile[], held_cards{}
  - Hand: story_id, entity_id, cards[]

- Behavior:
  - CRUD card_decks (deck definitions) collection
  - CRUD deck_states (runtime state) collection
  - Draw cards (random from draw_pile, move to discard or hand)
  - Shuffle deck (combine discard + draw_pile, randomize)
  - Return cards to deck or discard
  - Track hands per entity
  - Handle special cards (jokers trigger reshuffle)

- Cross-refs:
  - Game systems (deck definitions tied to rules)
  - Stories (deck state per story)
  - Entities (hands per character)
  - RS-5 (Card-Based Mechanics use case)

- Outputs:
  - Deck definitions
  - Runtime deck states
  - Hand states
  - Card draw results

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
      card_id: string,      // "hearts_ace", "major_fool"
      suit: string,         // "hearts", "major_arcana", null
      value: string,        // "ace", "2", "king", "fool"
      numeric_value: int,   // For comparison
      display_name: string, // "Ace of Hearts"
      short_name: string,   // "A♥"
      meaning: string       // Optional interpretation
    }
  ],

  include_jokers: bool,
  joker_count: int,

  reshuffle_on: [string],   // ["joker", "scene_end", "empty"]
  show_discards: bool,
  allow_hands: bool,
  max_hand_size: int,

  suit_meanings: map,       // {"hearts": "social", "spades": "combat"}
  value_scale: map,         // {"ace": 14} or {"ace": 1}
  special_cards: [
    {
      card_id: string,
      effect: string,
      trigger_reshuffle: bool
    }
  ],

  created_at: ISODate,
  updated_at: ISODate
}

// deck_states (runtime)
{
  _id: ObjectId,
  state_id: UUID,
  deck_id: UUID,
  story_id: UUID,

  draw_pile: [string],      // Card IDs in shuffled order
  discard_pile: [string],   // Card IDs in discard
  held_cards: {             // entity_id -> [card_id]
    "<entity_uuid>": ["hearts_ace", "spades_king"]
  },

  total_draws: int,
  cards_remaining: int,
  jokers_drawn: int,

  last_shuffled: ISODate,
  last_draw: ISODate,

  created_at: ISODate,
  updated_at: ISODate
}

// card_draws (history)
{
  _id: ObjectId,
  draw_id: UUID,
  deck_id: UUID,
  story_id: UUID,
  scene_id: UUID,
  turn_id: UUID,

  drawn_by: UUID,           // Entity ID
  cards: [string],          // Card IDs drawn
  draw_type: enum["single", "multiple_best", "multiple_choose", "opposed", "hand_play"],
  purpose: string,          // "initiative", "skill_check", etc.

  interpretation: string,   // What the draw means
  outcome: string,          // Resolved result

  drawn_at: ISODate
}
```

---

## DL-23: Manage World Snapshots (MongoDB)

**Purpose:** Store point-in-time snapshots of world state for backup, comparison, branching, and "what-if" exploration.

- Inputs:
  - Snapshot: scope (universe/story/region), scope_id, name, description, trigger
  - State capture: entities[], facts[], relationships[], axioms[]

- Behavior:
  - CRUD world_snapshots collection
  - Capture current state from Neo4j (batch read)
  - Compare snapshots (diff entities, facts, relationships)
  - Compare snapshot to current state
  - Support restore (with CanonKeeper coordination)
  - Track snapshot lineage for forked universes

- Cross-refs:
  - Neo4j (source of captured state)
  - Stories/Scenes (auto-snapshot at milestones)
  - M-34 (World Snapshots use case)
  - M-35 (Universe Fork use case)

- Outputs:
  - Snapshot documents
  - Snapshot diffs
  - Restore operations (via CanonKeeper)

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

  // Captured state (denormalized from Neo4j)
  entities: [
    {
      entity_id: UUID,
      entity_type: string,
      name: string,
      properties: map,
      state_tags: [string]
    }
  ],

  facts: [
    {
      fact_id: UUID,
      fact_type: string,
      statement: string,
      properties: map
    }
  ],

  relationships: [
    {
      relationship_id: UUID,
      type: string,
      from_id: UUID,
      to_id: UUID,
      properties: map
    }
  ],

  axioms: [
    {
      axiom_id: UUID,
      type: string,
      content: string,
      properties: map
    }
  ],

  // For story scope
  story_state: {
    current_scene_id: UUID,
    scene_count: int,
    turn_count: int,
    story_status: string
  },

  // Metadata
  trigger: enum["manual", "story_start", "milestone", "pre_branch", "pre_flashback", "scheduled"],
  created_at: ISODate,
  created_by: string,       // "system" or user ID

  // Size metrics
  entity_count: int,
  fact_count: int,
  relationship_count: int,
  total_size_kb: int,

  // Lineage (for forked universes)
  parent_snapshot_id: UUID,  // If forked from another snapshot
  branched_to: [UUID]        // Universes forked from this snapshot
}
```

**Snapshot Operations:**
```python
# Capture snapshot
async def capture_snapshot(scope: str, scope_id: UUID, name: str, trigger: str) -> UUID:
    # 1. Batch read from Neo4j based on scope
    entities = await neo4j_list_entities(scope_id=scope_id)
    facts = await neo4j_list_facts(scope_id=scope_id)
    relationships = await neo4j_list_relationships(scope_id=scope_id)
    axioms = await neo4j_list_axioms(scope_id=scope_id)

    # 2. Create snapshot document
    snapshot = WorldSnapshot(
        scope=scope,
        scope_id=scope_id,
        name=name,
        trigger=trigger,
        entities=serialize_entities(entities),
        facts=serialize_facts(facts),
        relationships=serialize_relationships(relationships),
        axioms=serialize_axioms(axioms)
    )

    # 3. Store in MongoDB
    return await mongodb_create_snapshot(snapshot)

# Compare snapshots
async def compare_snapshots(snapshot_a_id: UUID, snapshot_b_id: UUID) -> SnapshotDiff:
    a = await mongodb_get_snapshot(snapshot_a_id)
    b = await mongodb_get_snapshot(snapshot_b_id)

    return SnapshotDiff(
        added_entities=find_added(a.entities, b.entities),
        modified_entities=find_modified(a.entities, b.entities),
        deleted_entities=find_deleted(a.entities, b.entities),
        # ... same for facts, relationships
    )
```

---

## DL-24: Manage Turn Resolutions (MongoDB)

**Purpose:** Store and process mechanical resolutions for player/NPC actions during gameplay. This is the core data layer for turn-by-turn game mechanics.

> **CRITICAL:** This DL use case backs P-4 (Player Action) and P-9 (Dice Rolls). Without it, the system cannot run actual gameplay.

- Inputs:
  - Resolution: turn_id, action, entity_id, resolution_type, mechanics
  - Mechanics: formula, modifiers[], target, roll_result
  - Effects: type, target_id, magnitude, duration

- Behavior:
  - CRUD resolutions collection
  - Execute dice/card rolls
  - Evaluate success against targets
  - Calculate and apply effects
  - Track resolution history per scene

- Cross-refs:
  - Turns (DL-4) - resolution belongs to turn
  - Game Systems (DL-20) - resolution uses system rules
  - Card Decks (DL-22) - for card-based resolution
  - Entities (DL-2) - effects target entities

- Outputs:
  - Resolution documents
  - Roll results
  - Success levels
  - Effect calculations

**MongoDB Schema:**
```javascript
// resolutions
{
  _id: ObjectId,
  resolution_id: UUID,
  turn_id: UUID,
  scene_id: UUID,
  story_id: UUID,

  // What was attempted
  actor_id: UUID,              // Entity performing action
  action: string,              // "attack goblin", "pick lock", etc.
  action_type: enum["combat", "skill", "social", "exploration", "magic", "other"],

  // Resolution method
  resolution_type: enum["dice", "card", "narrative", "deterministic", "contested"],

  // Mechanics (for dice/card resolution)
  mechanics: {
    game_system_id: UUID,
    formula: string,           // "1d20+5", "2d6", etc.
    modifiers: [
      {source: string, value: int, reason: string}
    ],
    target: int,               // DC, TN, etc.
    target_source: string,     // "skill_dc", "opposed_roll", "fixed"

    // Roll result
    roll: {
      raw_rolls: [int],        // Individual dice
      kept_rolls: [int],       // After keep highest/lowest
      total: int,              // Sum + modifiers
      natural: int,            // Unmodified roll (for crit detection)
      critical: bool,
      fumble: bool
    },

    // For card-based
    card_draw: {
      deck_id: UUID,
      cards: [string],
      interpretation: string
    },

    // For contested
    opposed: {
      defender_id: UUID,
      defender_roll: {...}     // Same structure as roll
    }
  },

  // Outcome
  success_level: enum["critical_success", "success", "partial_success", "failure", "critical_failure"],
  margin: int,                 // How much over/under target

  // Effects generated
  effects: [
    {
      effect_type: enum["damage", "healing", "condition", "resource", "state_change", "narrative"],
      target_id: UUID,         // Entity affected
      magnitude: int,          // Amount (for numeric effects)
      damage_type: string,     // "slashing", "fire", etc. (for damage)
      condition: string,       // "poisoned", "prone", etc. (for conditions)
      duration: string,        // "instant", "1_round", "scene", "permanent"
      description: string      // Narrative description
    }
  ],

  // Narrative
  description: string,         // What happened narratively
  gm_notes: string,            // Internal notes

  created_at: ISODate
}
```

**MCP Tools:**
```python
# Core resolution
mongodb_create_resolution(turn_id, action, params) -> resolution_id
mongodb_get_resolution(resolution_id) -> Resolution
mongodb_list_resolutions(scene_id=None, turn_id=None) -> list[Resolution]

# Dice mechanics
roll_dice(formula: str, modifiers: list[Modifier] = []) -> DiceResult
evaluate_success(roll: int, target: int, system_id: UUID) -> SuccessLevel

# Effect calculation
calculate_damage(base: str, modifiers: list, resistances: list) -> int
apply_effect(entity_id: UUID, effect: Effect) -> EffectResult

# Full resolution pipeline
async def resolve_action(
    turn_id: UUID,
    actor_id: UUID,
    action: str,
    target_id: UUID | None,
    game_system_id: UUID,
    context: Context
) -> Resolution:
    # 1. Determine action type and applicable skill/stat
    action_type, skill = parse_action(action, context)

    # 2. Get actor stats and modifiers
    actor = await neo4j_get_entity(actor_id)
    modifiers = calculate_modifiers(actor, action_type, skill, context)

    # 3. Determine target number
    target = determine_target(action_type, target_id, context)

    # 4. Get game system rules
    system = await mongodb_get_game_system(game_system_id)

    # 5. Roll dice (or draw cards)
    if system.core_mechanic.type in ["d20", "dice_pool", "percentile"]:
        roll = roll_dice(system.core_mechanic.formula, modifiers)
    elif system.core_mechanic.type == "card":
        roll = await draw_cards(context.story_id, system.deck_id)

    # 6. Evaluate success
    success_level = evaluate_success(roll.total, target, system)

    # 7. Calculate effects
    effects = calculate_effects(action_type, success_level, actor, target_id, context)

    # 8. Create resolution record
    resolution = Resolution(
        turn_id=turn_id,
        actor_id=actor_id,
        action=action,
        action_type=action_type,
        resolution_type="dice",
        mechanics={...},
        success_level=success_level,
        effects=effects
    )

    # 9. Persist
    await mongodb_create_resolution(resolution)

    return resolution
```

**Success Level Evaluation:**
```python
def evaluate_success(roll: int, target: int, system: GameSystem) -> SuccessLevel:
    margin = roll - target

    # Check for criticals first
    if system.core_mechanic.critical_success:
        if meets_critical(roll, system.core_mechanic.critical_success):
            return SuccessLevel.CRITICAL_SUCCESS

    if system.core_mechanic.critical_failure:
        if meets_critical(roll, system.core_mechanic.critical_failure):
            return SuccessLevel.CRITICAL_FAILURE

    # Standard success evaluation
    if margin >= 0:
        if system.core_mechanic.partial_success:
            threshold = parse_partial_threshold(system.core_mechanic.partial_success)
            if margin < threshold:
                return SuccessLevel.PARTIAL_SUCCESS
        return SuccessLevel.SUCCESS

    return SuccessLevel.FAILURE
```

---

## DL-25: Manage Combat State (MongoDB)

**Purpose:** Track combat encounter state including initiative, turn order, participant status, and environmental factors.

- Inputs:
  - Encounter: scene_id, participants[], environment
  - Participant state: entity_id, initiative, position, conditions[], resources{}
  - Round/turn progression

- Behavior:
  - CRUD combat_encounters collection
  - Initialize combat (roll/draw initiative)
  - Track turn order and current turn
  - Manage participant conditions and resources
  - Handle defeat/victory detection
  - Support tactical positioning (optional)

- Cross-refs:
  - Scenes (DL-4) - combat belongs to scene
  - Entities (DL-2) - participants are entities
  - Resolutions (DL-24) - combat actions create resolutions
  - Card Decks (DL-22) - for card-based initiative

- Outputs:
  - Combat encounter documents
  - Initiative order
  - Combat state updates
  - Victory/defeat outcomes

**MongoDB Schema:**
```javascript
// combat_encounters
{
  _id: ObjectId,
  encounter_id: UUID,
  scene_id: UUID,
  story_id: UUID,

  // Status
  status: enum["initializing", "initiative", "active", "paused", "resolved"],
  started_at: ISODate,
  ended_at: ISODate,

  // Participants
  participants: [
    {
      entity_id: UUID,
      name: string,                    // Cached for display
      side: enum["pc", "ally", "enemy", "neutral"],

      // Initiative
      initiative_value: int,
      initiative_card: string,         // For card-based
      initiative_modifiers: [string],

      // Current state
      is_active: bool,                 // Still in combat
      is_current_turn: bool,
      has_acted_this_round: bool,

      // Position (for tactical combat)
      position: {
        x: int,
        y: int,
        zone: string                   // "melee_range", "ranged", "cover"
      },

      // Conditions and effects
      conditions: [
        {
          name: string,                // "poisoned", "prone", "stunned"
          source: string,              // What caused it
          duration: string,            // "1_round", "save_ends", "scene"
          rounds_remaining: int,
          effects: map                 // Mechanical effects
        }
      ],

      // Combat resources (snapshot from character)
      resources: {
        hp: {current: int, max: int},
        temp_hp: int,
        // System-specific resources
        spell_slots: map,
        ki_points: int,
        rage_rounds: int
      },

      // Tracking
      damage_dealt: int,
      damage_taken: int,
      kills: int
    }
  ],

  // Turn tracking
  round: int,
  turn_order: [UUID],                  // Entity IDs in initiative order
  current_turn_index: int,
  current_entity_id: UUID,

  // Environment
  environment: {
    terrain: string,                   // "forest", "dungeon", "urban"
    lighting: enum["bright", "dim", "dark"],
    hazards: [
      {name: string, area: string, effect: string, damage: string}
    ],
    cover_positions: [string],
    difficult_terrain: [string]
  },

  // Combat log
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

  // Outcome
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

**MCP Tools:**
```python
# Combat lifecycle
mongodb_create_combat(scene_id, participants, environment) -> encounter_id
mongodb_get_combat(encounter_id) -> CombatEncounter
mongodb_end_combat(encounter_id, outcome) -> CombatOutcome

# Initiative
mongodb_roll_initiative(encounter_id, game_system_id) -> list[InitiativeResult]
mongodb_set_initiative(encounter_id, entity_id, value)
mongodb_reroll_initiative(encounter_id)  # For systems that reroll each round

# Turn management
mongodb_get_current_turn(encounter_id) -> TurnInfo
mongodb_advance_turn(encounter_id) -> NextTurnInfo
mongodb_delay_turn(encounter_id, entity_id)
mongodb_ready_action(encounter_id, entity_id, trigger, action)

# Participant state
mongodb_update_participant(encounter_id, entity_id, updates)
mongodb_apply_damage(encounter_id, entity_id, damage, damage_type) -> DamageResult
mongodb_apply_healing(encounter_id, entity_id, amount) -> HealingResult
mongodb_add_condition(encounter_id, entity_id, condition) -> ConditionResult
mongodb_remove_condition(encounter_id, entity_id, condition_name)
mongodb_update_position(encounter_id, entity_id, position)

# Combat queries
mongodb_get_valid_targets(encounter_id, entity_id, action_type) -> list[UUID]
mongodb_check_line_of_sight(encounter_id, from_id, to_id) -> bool
mongodb_get_distance(encounter_id, from_id, to_id) -> int

# Defeat detection
mongodb_check_combat_end(encounter_id) -> CombatEndCheck
```

**Combat Flow:**
```python
async def run_combat_round(encounter_id: UUID) -> RoundResult:
    encounter = await mongodb_get_combat(encounter_id)

    round_results = []

    # Process each participant in initiative order
    for entity_id in encounter.turn_order:
        participant = get_participant(encounter, entity_id)

        if not participant.is_active:
            continue

        # Mark current turn
        await mongodb_update_participant(encounter_id, entity_id, {"is_current_turn": True})

        # Get action (from user, PC-Agent, or NPC-Agent)
        if participant.side == "pc":
            action = await get_pc_action(entity_id, encounter)
        else:
            action = await get_npc_action(entity_id, encounter)

        # Resolve action
        resolution = await resolve_combat_action(encounter_id, entity_id, action)
        round_results.append(resolution)

        # Apply effects
        for effect in resolution.effects:
            await apply_combat_effect(encounter_id, effect)

        # Check for combat end
        end_check = await mongodb_check_combat_end(encounter_id)
        if end_check.should_end:
            await mongodb_end_combat(encounter_id, end_check.outcome)
            return RoundResult(ended=True, outcome=end_check.outcome)

        # Clear current turn
        await mongodb_update_participant(encounter_id, entity_id, {
            "is_current_turn": False,
            "has_acted_this_round": True
        })

    # Advance round
    await mongodb_advance_round(encounter_id)

    return RoundResult(ended=False, actions=round_results)
```

---

## DL-26: Manage Character Working State (MongoDB)

**Purpose:** Track character stats and resources during active gameplay, separate from canonical Neo4j state.

> **Design Decision:** Neo4j stores permanent/canonical character data. MongoDB stores scene-scoped working state that syncs to Neo4j at canonization.

- Inputs:
  - Character state: entity_id, scene_id, stats{}, resources{}, temporary_effects[]
  - Stat modifications (buffs, debuffs, damage)
  - Temporary effects with duration

- Behavior:
  - Initialize working state from Neo4j at scene start
  - Track all mid-scene modifications
  - Apply temporary effects with duration tracking
  - Sync back to Neo4j at canonization
  - Support "what would happen" queries without committing

- Cross-refs:
  - Entities (DL-2) - source of canonical stats
  - Scenes (DL-4) - working state scoped to scene
  - Resolutions (DL-24) - resolutions modify working state
  - Combat (DL-25) - combat uses working state

- Outputs:
  - Working state documents
  - Effective stat calculations
  - State diffs for canonization

**MongoDB Schema:**
```javascript
// character_working_state
{
  _id: ObjectId,
  state_id: UUID,
  entity_id: UUID,
  scene_id: UUID,
  story_id: UUID,

  // Snapshot of canonical stats (from Neo4j at scene start)
  base_stats: {
    // Game-system specific
    strength: int,
    dexterity: int,
    // ...
  },

  // Current working values (base + modifications)
  current_stats: {
    strength: int,
    dexterity: int,
    // ...
  },

  // Resources with current/max
  resources: {
    hp: {current: int, max: int, temp: int},
    mp: {current: int, max: int},
    // Game-system specific
  },

  // Modifications applied this scene
  modifications: [
    {
      mod_id: UUID,
      stat_or_resource: string,
      change: int,
      source: string,          // "combat_damage", "healing_potion", "spell_buff"
      source_id: UUID,         // Resolution or effect that caused it
      timestamp: ISODate
    }
  ],

  // Temporary effects
  temporary_effects: [
    {
      effect_id: UUID,
      name: string,            // "bless", "haste", "rage"
      source: string,
      stat_modifiers: map,     // {dexterity: +2, ac: +1}
      duration_type: enum["rounds", "minutes", "scene", "concentration"],
      duration_remaining: int,
      applied_at: ISODate,
      expires_at: ISODate
    }
  ],

  // Inventory changes (not yet canonized)
  inventory_changes: [
    {change_type: enum["add", "remove", "use"], item: string, quantity: int}
  ],

  // For diff/canonization
  created_at: ISODate,
  updated_at: ISODate,
  canonized: bool,
  canonized_at: ISODate
}
```

**MCP Tools:**
```python
# Working state lifecycle
mongodb_init_working_state(entity_id, scene_id) -> state_id  # Load from Neo4j
mongodb_get_working_state(entity_id, scene_id) -> CharacterWorkingState
mongodb_delete_working_state(state_id)  # Cleanup after scene

# Stat/resource modification
mongodb_modify_stat(state_id, stat, change, source, source_id)
mongodb_modify_resource(state_id, resource, change, source, source_id)
mongodb_set_resource(state_id, resource, value)

# Temporary effects
mongodb_add_temp_effect(state_id, effect) -> effect_id
mongodb_remove_temp_effect(state_id, effect_id)
mongodb_tick_effect_durations(state_id)  # Called at round/turn end
mongodb_get_expired_effects(state_id) -> list[Effect]

# Effective stat calculation
def get_effective_stat(state: CharacterWorkingState, stat: str) -> int:
    base = state.current_stats.get(stat, 0)
    for effect in state.temporary_effects:
        if stat in effect.stat_modifiers:
            base += effect.stat_modifiers[stat]
    return base

# Canonization
mongodb_get_state_diff(state_id) -> StateDiff  # What changed from base
mongodb_mark_canonized(state_id)

# Sync to Neo4j
async def canonize_working_state(state_id: UUID):
    state = await mongodb_get_working_state(state_id)
    diff = await mongodb_get_state_diff(state_id)

    # Only permanent changes go to Neo4j
    permanent_changes = filter_permanent(diff)

    if permanent_changes.hp_change:
        await neo4j_update_entity(state.entity_id, {
            "stats.hp.current": state.resources.hp.current
        })

    if permanent_changes.stat_changes:
        for stat, value in permanent_changes.stat_changes.items():
            await neo4j_update_entity(state.entity_id, {
                f"stats.{stat}": value
            })

    # Mark canonized
    await mongodb_mark_canonized(state_id)
```

**Integration with Scene Loop:**
```python
# At scene start (S1):
for entity_id in scene.participant_ids:
    await mongodb_init_working_state(entity_id, scene.id)

# During turns (S2-S5):
# All stat/resource changes go to working state, not Neo4j

# At scene end (S6):
for entity_id in scene.participant_ids:
    await canonize_working_state(entity_id, scene.id)
```
