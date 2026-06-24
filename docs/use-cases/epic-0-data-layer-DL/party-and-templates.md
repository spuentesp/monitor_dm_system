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

