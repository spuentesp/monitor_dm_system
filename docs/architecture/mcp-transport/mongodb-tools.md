## 4. MongoDB Tool Specifications

### 4.1 Scene Operations

#### mongodb_create_scene

```json
{
  "name": "mongodb_create_scene",
  "description": "Create a new scene in MongoDB.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "story_id": {"type": "string", "format": "uuid"},
      "universe_id": {"type": "string", "format": "uuid"},
      "title": {"type": "string"},
      "purpose": {"type": "string"},
      "order": {
        "type": "integer",
        "description": "Optional ordering of scene within Story"
      },
      "location_ref": {
        "type": "string",
        "format": "uuid",
        "description": "EntityInstance location ID"
      },
      "participating_entities": {
        "type": "array",
        "items": {"type": "string", "format": "uuid"}
      }
    },
    "required": ["story_id", "universe_id", "title", "participating_entities"]
  }
}
```

---

#### mongodb_append_turn

```json
{
  "name": "mongodb_append_turn",
  "description": "Append a turn to an active scene. Narrator or NPCVoice.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "scene_id": {"type": "string", "format": "uuid"},
      "speaker": {
        "type": "string",
        "enum": ["user", "gm", "entity"]
      },
      "entity_id": {
        "type": "string",
        "format": "uuid",
        "description": "Required if speaker is 'entity'"
      },
      "text": {"type": "string"},
      "resolution_ref": {
        "type": "string",
        "format": "uuid",
        "description": "Optional resolution ID"
      }
    },
    "required": ["scene_id", "speaker", "text"]
  }
}
```

---

#### mongodb_get_scene

```json
{
  "name": "mongodb_get_scene",
  "description": "Retrieve scene by ID. Read-only, any agent.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "scene_id": {"type": "string", "format": "uuid"},
      "include_turns": {"type": "boolean", "default": true},
      "include_proposals": {"type": "boolean", "default": false},
      "turn_limit": {
        "type": "integer",
        "description": "Limit to last N turns"
      }
    },
    "required": ["scene_id"]
  }
}
```

---

#### mongodb_finalize_scene

```json
{
  "name": "mongodb_finalize_scene",
  "description": "Mark scene as completed. Requires CanonKeeper authority.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "scene_id": {"type": "string", "format": "uuid"},
      "canonical_outcome_ids": {
        "type": "array",
        "items": {"type": "string", "format": "uuid"},
        "description": "Neo4j Fact/Event IDs created during canonization"
      },
      "summary": {"type": "string"}
    },
    "required": ["scene_id", "canonical_outcome_ids", "summary"]
  }
}
```

---

### 4.2 ProposedChange Operations

#### mongodb_create_proposed_change

```json
{
  "name": "mongodb_create_proposed_change",
  "description": "Create a proposed change (staging for canonization). Any agent can propose.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "scene_id": {"type": "string", "format": "uuid"},
      "turn_id": {
        "type": "string",
        "format": "uuid",
        "description": "Optional turn reference (ingest/system proposals may omit)"
      },
      "type": {
        "type": "string",
        "enum": ["fact", "entity", "relationship", "state_change", "event"]
      },
      "content": {
        "type": "object",
        "description": "Type-specific content",
        "additionalProperties": true
      },
      "evidence": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "type": {
              "type": "string",
              "enum": ["turn", "snippet", "source", "rule"]
            },
            "ref_id": {"type": "string", "format": "uuid"}
          },
          "required": ["type", "ref_id"]
        }
      },
      "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
      "authority": {
        "type": "string",
        "enum": ["source", "gm", "player", "system"]
      }
    },
    "required": ["scene_id", "type", "content", "evidence", "confidence", "authority"]
  }
}
```

---

#### mongodb_evaluate_proposal

```json
{
  "name": "mongodb_evaluate_proposal",
  "description": "Accept or reject a proposed change. Requires CanonKeeper authority.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "proposal_id": {"type": "string", "format": "uuid"},
      "decision": {
        "type": "string",
        "enum": ["accepted", "rejected"]
      },
      "rationale": {"type": "string"},
      "canonical_id": {
        "type": "string",
        "format": "uuid",
        "description": "Neo4j node/edge ID if accepted"
      }
    },
    "required": ["proposal_id", "decision"]
  }
}
```

---

#### mongodb_get_pending_proposals

```json
{
  "name": "mongodb_get_pending_proposals",
  "description": "Get pending proposals for evaluation. CanonKeeper.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "scene_id": {"type": "string", "format": "uuid"},
      "type": {
        "type": "string",
        "enum": ["fact", "entity", "relationship", "state_change", "event"]
      },
      "limit": {"type": "integer", "default": 50}
    }
  }
}
```

---

### 4.3 Memory Operations

#### mongodb_create_character_memory

```json
{
  "name": "mongodb_create_character_memory",
  "description": "Create a character memory. Narrator or NPCVoice authority.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string", "format": "uuid"},
      "text": {"type": "string"},
      "linked_fact_id": {"type": "string", "format": "uuid"},
      "scene_id": {"type": "string", "format": "uuid"},
      "emotional_valence": {"type": "number", "minimum": -1.0, "maximum": 1.0},
      "importance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
      "certainty": {"type": "number", "minimum": 0.0, "maximum": 1.0}
    },
    "required": ["entity_id", "text", "emotional_valence", "importance", "certainty"]
  }
}
```

---

#### mongodb_retrieve_character_memories

```json
{
  "name": "mongodb_retrieve_character_memories",
  "description": "Retrieve character memories. ContextAssembly, Narrator, or NPCVoice.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string", "format": "uuid"},
      "limit": {"type": "integer", "default": 20},
      "min_importance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
      "semantic_query": {
        "type": "string",
        "description": "Optional semantic search query"
      }
    },
    "required": ["entity_id"]
  }
}
```

---

