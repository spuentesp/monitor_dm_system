## 3. Neo4j Tool Specifications

### 3.1 Entity Operations

#### neo4j_create_entity

```json
{
  "name": "neo4j_create_entity",
  "description": "Create a new entity (EntityArchetype or EntityInstance) in the canonical graph. Requires CanonKeeper authority.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "entity_class": {
        "type": "string",
        "enum": ["EntityArchetype", "EntityInstance"],
        "description": "Whether this is an archetype or concrete instance"
      },
      "universe_id": {
        "type": "string",
        "format": "uuid",
        "description": "Universe this entity belongs to"
      },
      "name": {
        "type": "string",
        "description": "Entity name"
      },
      "entity_type": {
        "type": "string",
        "enum": ["character", "faction", "location", "object", "concept", "organization"],
        "description": "Entity classification"
      },
      "description": {
        "type": "string",
        "description": "Entity description"
      },
      "properties": {
        "type": "object",
        "description": "Type-specific properties",
        "additionalProperties": true
      },
      "state_tags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "State tags (EntityInstance only)"
      },
      "derives_from": {
        "type": "string",
        "format": "uuid",
        "description": "Optional EntityArchetype this derives from (EntityInstance only)"
      },
      "confidence": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "Confidence level"
      },
      "authority": {
        "type": "string",
        "enum": ["source", "gm", "player", "system"],
        "description": "Authority source"
      },
      "evidence_refs": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Evidence references (e.g., 'source:uuid', 'turn:uuid')"
      }
    },
    "required": ["entity_class", "universe_id", "name", "entity_type", "description", "properties", "confidence", "authority", "evidence_refs"]
  }
}
```

**Example call:**
```json
{
  "name": "neo4j_create_entity",
  "arguments": {
    "entity_class": "EntityInstance",
    "universe_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Gandalf the Grey",
    "entity_type": "character",
    "description": "Istari wizard sent to Middle-earth",
    "properties": {
      "role": "NPC",
      "archetype": "wizard"
    },
    "state_tags": ["alive", "traveling"],
    "confidence": 1.0,
    "authority": "source",
    "evidence_refs": ["source:550e8400-e29b-41d4-a716-446655440001"]
  }
}
```

**Response:**
```json
{
  "entity_id": "650e8400-e29b-41d4-a716-446655440002",
  "canon_level": "canon",
  "created_at": "2025-01-15T12:00:00Z"
}
```

---

#### neo4j_get_entity

```json
{
  "name": "neo4j_get_entity",
  "description": "Retrieve an entity by ID. Any agent can read.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "entity_id": {
        "type": "string",
        "format": "uuid",
        "description": "Entity ID"
      },
      "include_relationships": {
        "type": "boolean",
        "default": false,
        "description": "Include related entities"
      },
      "include_state_history": {
        "type": "boolean",
        "default": false,
        "description": "Include state change history (Facts)"
      }
    },
    "required": ["entity_id"]
  }
}
```

---

#### neo4j_update_entity_state

```json
{
  "name": "neo4j_update_entity_state",
  "description": "Update entity state tags. Requires CanonKeeper authority. Creates Fact nodes to document changes.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "entity_id": {
        "type": "string",
        "format": "uuid"
      },
      "state_tag_changes": {
        "type": "object",
        "properties": {
          "add": {
            "type": "array",
            "items": {"type": "string"}
          },
          "remove": {
            "type": "array",
            "items": {"type": "string"}
          }
        }
      },
      "authority": {
        "type": "string",
        "enum": ["gm", "player", "system"]
      },
      "evidence_refs": {
        "type": "array",
        "items": {"type": "string"}
      }
    },
    "required": ["entity_id", "state_tag_changes", "authority", "evidence_refs"]
  }
}
```

---

#### neo4j_query_entities

```json
{
  "name": "neo4j_query_entities",
  "description": "Query entities by filters. Read-only, any agent.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "universe_id": {
        "type": "string",
        "format": "uuid"
      },
      "entity_type": {
        "type": "string",
        "enum": ["character", "faction", "location", "object", "concept", "organization"]
      },
      "entity_class": {
        "type": "string",
        "enum": ["EntityArchetype", "EntityInstance"]
      },
      "canon_level": {
        "type": "string",
        "enum": ["proposed", "canon", "retconned"]
      },
      "state_tags": {
        "type": "object",
        "properties": {
          "all_of": {"type": "array", "items": {"type": "string"}},
          "any_of": {"type": "array", "items": {"type": "string"}},
          "none_of": {"type": "array", "items": {"type": "string"}}
        }
      },
      "name_pattern": {
        "type": "string"
      },
      "limit": {
        "type": "integer",
        "default": 50,
        "maximum": 500
      },
      "offset": {
        "type": "integer",
        "default": 0
      }
    }
  }
}
```

---

### 3.2 Fact & Event Operations

#### neo4j_create_fact

```json
{
  "name": "neo4j_create_fact",
  "description": "Create a canonical fact. Requires CanonKeeper authority.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "universe_id": {
        "type": "string",
        "format": "uuid"
      },
      "statement": {
        "type": "string",
        "description": "Fact statement"
      },
      "time_ref": {
        "type": "string",
        "format": "date-time",
        "description": "When fact became true"
      },
      "duration": {
        "type": "integer",
        "description": "How long fact was true (optional)"
      },
      "involved_entity_ids": {
        "type": "array",
        "items": {"type": "string", "format": "uuid"},
        "description": "Entities involved in this fact"
      },
      "confidence": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0
      },
      "authority": {
        "type": "string",
        "enum": ["source", "gm", "player", "system"]
      },
      "evidence_refs": {
        "type": "array",
        "items": {"type": "string"}
      }
    },
    "required": ["universe_id", "statement", "involved_entity_ids", "confidence", "authority", "evidence_refs"]
  }
}
```

---

#### neo4j_create_event

```json
{
  "name": "neo4j_create_event",
  "description": "Create a canonical event. Requires CanonKeeper authority.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "scene_id": {
        "type": "string",
        "format": "uuid"
      },
      "universe_id": {
        "type": "string",
        "format": "uuid"
      },
      "title": {
        "type": "string"
      },
      "description": {
        "type": "string"
      },
      "time_ref": {
        "type": "string",
        "format": "date-time"
      },
      "severity": {
        "type": "integer",
        "minimum": 0,
        "maximum": 10
      },
      "involved_entity_ids": {
        "type": "array",
        "items": {"type": "string", "format": "uuid"}
      },
      "causes_event_ids": {
        "type": "array",
        "items": {"type": "string", "format": "uuid"},
        "description": "Events caused by this event (causal edges)"
      },
      "confidence": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0
      },
      "authority": {
        "type": "string",
        "enum": ["source", "gm", "player", "system"]
      },
      "evidence_refs": {
        "type": "array",
        "items": {"type": "string"}
      }
    },
    "required": ["universe_id", "title", "description", "involved_entity_ids", "confidence", "authority", "evidence_refs"]
  }
}
```

---

#### neo4j_query_facts

```json
{
  "name": "neo4j_query_facts",
  "description": "Query facts by filters. Read-only, any agent.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "universe_id": {"type": "string", "format": "uuid"},
      "entity_id": {"type": "string", "format": "uuid"},
      "time_range": {
        "type": "object",
        "properties": {
          "start": {"type": "string", "format": "date-time"},
          "end": {"type": "string", "format": "date-time"}
        }
      },
      "canon_level": {
        "type": "string",
        "enum": ["proposed", "canon", "retconned"]
      },
      "authority": {
        "type": "string",
        "enum": ["source", "gm", "player", "system"]
      },
      "limit": {"type": "integer", "default": 50},
      "offset": {"type": "integer", "default": 0}
    }
  }
}
```

---

### 3.3 Story & Source Operations

#### neo4j_create_story

```json
{
  "name": "neo4j_create_story",
  "description": "Create a canonical story container. Requires CanonKeeper authority.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "universe_id": {"type": "string", "format": "uuid"},
      "title": {"type": "string"},
      "story_type": {
        "type": "string",
        "enum": ["campaign", "arc", "episode", "one_shot"]
      },
      "theme": {"type": "string"},
      "premise": {"type": "string"},
      "parent_story_id": {
        "type": "string",
        "format": "uuid",
        "description": "For arcs within campaigns"
      },
      "start_time_ref": {"type": "string", "format": "date-time"}
    },
    "required": ["universe_id", "title", "story_type"]
  }
}
```

---

#### neo4j_create_source

```json
{
  "name": "neo4j_create_source",
  "description": "Create a canonical source node. Requires CanonKeeper authority.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "universe_id": {"type": "string", "format": "uuid"},
      "doc_id": {"type": "string"},
      "title": {"type": "string"},
      "edition": {"type": "string"},
      "provenance": {"type": "string"},
      "source_type": {
        "type": "string",
        "enum": ["manual", "rulebook", "lore", "session"]
      },
      "canon_level": {
        "type": "string",
        "enum": ["proposed", "canon", "authoritative"]
      }
    },
    "required": ["universe_id", "doc_id", "title", "source_type", "canon_level"]
  }
}
```

---

### 3.N Mechanic Reference Node Operations (added April 2026)

> These tools create thin traversal-oriented nodes in Neo4j. Full mechanic definitions live in MongoDB (`KnowledgePack.game_system_data`). Neo4j stores only `name` + `system_id` for graph traversal.
>
> All four functions are CanonKeeper-only. See `packages/data-layer/src/monitor_data/tools/neo4j_tools/mechanics.py`.

| Tool | Creates | Key params |
|------|---------|------------|
| `neo4j_create_ability_system` | `:AbilitySystem` node | `name`, `system_id`, `parent_category`, `universe_id` |
| `neo4j_create_track` | `:Track` node | `name`, `system_id`, `track_type`, `universe_id` |
| `neo4j_create_condition` | `:Condition` node | `name`, `system_id`, `universe_id` |
| `neo4j_link_entity_to_ability` | `(:Entity)-[:HAS_ACCESS_TO]->(:AbilitySystem)` | `entity_id`, `ability_system_name` |

---

