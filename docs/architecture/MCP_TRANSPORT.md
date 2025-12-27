# MONITOR MCP Transport Layer

*MCP tool specifications for the Data Layer API.*

---

## Overview

This document defines how agents interact with the Data Layer API via **Model Context Protocol (MCP)**.

**Key principle:** Each Data Layer API operation is exposed as an MCP tool with proper schema validation and authority enforcement.

---

## MCP Architecture

```
┌────────────────────────────────────────────┐
│         AGENT (Claude/LLM)                 │
│  - Orchestrator                            │
│  - Narrator                                │
│  - CanonKeeper                             │
│  - ContextAssembly                         │
│  - etc.                                    │
└────────────────┬───────────────────────────┘
                 │
                 ▼ (MCP Protocol)
┌────────────────────────────────────────────┐
│       MCP SERVER (Data Layer Gateway)      │
│  - Tool registration                       │
│  - Schema validation                       │
│  - Authority enforcement                   │
│  - Request routing                         │
└─┬───────┬────────┬────────┬────────┬───────┘
  │       │        │        │        │
  ▼       ▼        ▼        ▼        ▼
┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
│Neo4│ │Mongo│ │Qdrant│ │OpenS│ │MinIO│
└────┘ └────┘ └────┘ └────┘ └────┘
```

---

## 1. MCP Server Configuration

### 1.1 Server Metadata

```json
{
  "name": "monitor-data-layer",
  "version": "1.0.0",
  "description": "MONITOR Data Layer API via MCP",
  "protocol_version": "2024-11-05",
  "capabilities": {
    "tools": {},
    "resources": {},
    "prompts": {}
  }
}
```

### 1.2 Authority Context

Every MCP request must include agent identity:

```json
{
  "agent_id": "uuid",
  "agent_type": "Orchestrator | CanonKeeper | Narrator | ContextAssembly | Resolver | MemoryManager | Indexer"
}
```

This is passed via MCP context and validated against the authority matrix.

---

## 2. Tool Naming Convention

```
<domain>_<operation>_<entity>

Examples:
- neo4j_create_entity
- neo4j_get_entity
- neo4j_query_entities
- mongodb_create_scene
- mongodb_append_turn
- qdrant_semantic_search
- composite_assemble_scene_context
- composite_canonize_scene
```

---

## 3. Neo4j Tool Specifications

### 3.1 Entity Operations

#### neo4j_create_entity

```json
{
  "name": "neo4j_create_entity",
  "description": "Create a new entity (EntityAxiomatica or EntityConcreta) in the canonical graph. Requires CanonKeeper authority.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "entity_class": {
        "type": "string",
        "enum": ["EntityAxiomatica", "EntityConcreta"],
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
        "description": "State tags (EntityConcreta only)"
      },
      "derives_from": {
        "type": "string",
        "format": "uuid",
        "description": "Optional EntityAxiomatica this derives from (EntityConcreta only)"
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
    "entity_class": "EntityConcreta",
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
        "enum": ["EntityAxiomatica", "EntityConcreta"]
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
  "description": "Create a canonical story container. CanonKeeper or Orchestrator.",
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

## 4. MongoDB Tool Specifications

### 4.1 Scene Operations

#### mongodb_create_scene

```json
{
  "name": "mongodb_create_scene",
  "description": "Create a new scene in MongoDB. Requires Orchestrator authority.",
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
        "description": "EntityConcreta location ID"
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
  "description": "Append a turn to an active scene. Narrator or Orchestrator.",
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
  "description": "Create a character memory. Requires MemoryManager authority.",
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
  "description": "Retrieve character memories. ContextAssembly or MemoryManager.",
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

## 5. Qdrant Tool Specifications

### 5.1 Semantic Search

#### qdrant_semantic_search

```json
{
  "name": "qdrant_semantic_search",
  "description": "Semantic search across embeddings. Read-only, any agent.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query_text": {"type": "string"},
      "collection": {
        "type": "string",
        "enum": ["scene_chunks", "memory_chunks", "snippet_chunks"]
      },
      "filters": {
        "type": "object",
        "properties": {
          "universe_id": {"type": "string", "format": "uuid"},
          "entity_id": {"type": "string", "format": "uuid"},
          "source_id": {"type": "string", "format": "uuid"}
        }
      },
      "limit": {"type": "integer", "default": 10, "maximum": 100},
      "min_score": {"type": "number", "minimum": 0.0, "maximum": 1.0}
    },
    "required": ["query_text", "collection"]
  }
}
```

---

## 6. Composite Tool Specifications

### 6.1 Context Assembly

#### composite_assemble_scene_context

```json
{
  "name": "composite_assemble_scene_context",
  "description": "Assemble full scene context from all three databases. ContextAssembly agent.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "scene_id": {"type": "string", "format": "uuid"},
      "include_canonical": {"type": "boolean", "default": true},
      "include_narrative": {"type": "boolean", "default": true},
      "include_semantic": {"type": "boolean", "default": true},
      "semantic_query": {
        "type": "string",
        "description": "Optional query for semantic recall"
      }
    },
    "required": ["scene_id"]
  }
}
```

**Response structure:**
```json
{
  "canonical": {
    "entities": [...],
    "facts": [...],
    "relations": [...]
  },
  "narrative": {
    "prior_turns": [...],
    "scene_summary": "...",
    "gm_notes": "..."
  },
  "recalled": {
    "similar_scenes": [...],
    "character_memories": [...],
    "rule_excerpts": [...]
  },
  "metadata": {
    "universe_id": "uuid",
    "story_id": "uuid",
    "scene_id": "uuid",
    "timestamp": "2025-01-15T12:00:00Z"
  }
}
```

---

### 6.2 Canonization

#### composite_canonize_scene

```json
{
  "name": "composite_canonize_scene",
  "description": "Canonize a scene (evaluate proposals, write to Neo4j, finalize). Requires CanonKeeper authority.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "scene_id": {"type": "string", "format": "uuid"},
      "evaluate_proposals": {"type": "boolean", "default": true}
    },
    "required": ["scene_id"]
  }
}
```

**Response structure:**
```json
{
  "scene_id": "uuid",
  "accepted_proposals": ["uuid", ...],
  "rejected_proposals": ["uuid", ...],
  "canonical_fact_ids": ["uuid", ...],
  "canonical_event_ids": ["uuid", ...],
  "canonical_entity_ids": ["uuid", ...]
}
```

---

## 7. Authority Enforcement

### 7.1 Request Context

Every MCP tool call includes:

```json
{
  "agent_id": "uuid",
  "agent_type": "Orchestrator | CanonKeeper | Narrator | ContextAssembly | Resolver | MemoryManager | Indexer"
}
```

### 7.2 Authority Matrix

| Tool Pattern | Allowed Agent Types |
|-------------|---------------------|
| `neo4j_create_*` | CanonKeeper |
| `neo4j_create_story` | CanonKeeper, Orchestrator |
| `neo4j_update_*` | CanonKeeper |
| `neo4j_get_*` | Any |
| `neo4j_query_*` | Any |
| `mongodb_create_scene` | Orchestrator |
| `mongodb_append_turn` | Narrator, Orchestrator |
| `mongodb_create_proposed_change` | Any |
| `mongodb_evaluate_proposal` | CanonKeeper |
| `mongodb_finalize_scene` | CanonKeeper |
| `mongodb_create_character_memory` | MemoryManager |
| `qdrant_*` | Any (read-only) |
| `composite_assemble_scene_context` | ContextAssembly |
| `composite_canonize_scene` | CanonKeeper |

### 7.3 Enforcement Logic

```typescript
function enforceAuthority(tool: string, agentType: string): boolean {
  const matrix = {
    "neo4j_create_entity": ["CanonKeeper"],
    "neo4j_update_entity_state": ["CanonKeeper"],
    "neo4j_get_entity": ["*"],
    "mongodb_create_scene": ["Orchestrator"],
    "mongodb_append_turn": ["Narrator", "Orchestrator"],
    "composite_canonize_scene": ["CanonKeeper"],
    // ... etc
  };

  const allowed = matrix[tool] || [];
  return allowed.includes("*") || allowed.includes(agentType);
}
```

---

## 8. Error Handling

### 8.1 MCP Error Codes

```typescript
enum MCPErrorCode {
  UNAUTHORIZED = -32001,          // Agent lacks authority
  NOT_FOUND = -32002,             // Entity/resource not found
  VALIDATION_ERROR = -32003,      // Schema validation failed
  CONSTRAINT_VIOLATION = -32004,  // Database constraint violated
  TRANSACTION_FAILED = -32005,    // DB transaction failed
  ALREADY_CANONIZED = -32006      // Scene already finalized
}
```

### 8.2 Error Response Format

```json
{
  "error": {
    "code": -32001,
    "message": "Agent type 'Narrator' is not authorized to call 'neo4j_create_entity'",
    "data": {
      "tool": "neo4j_create_entity",
      "agent_type": "Narrator",
      "allowed_types": ["CanonKeeper"]
    }
  }
}
```

---

## 9. Validation Schemas

### 9.1 JSON Schema Validation

All tool inputs are validated against JSON Schema before execution.

**Example validation:**
```typescript
import Ajv from "ajv";

const ajv = new Ajv();
const validate = ajv.compile(toolSchema.inputSchema);

if (!validate(arguments)) {
  throw new ValidationError(validate.errors);
}
```

### 9.2 Custom Validators

**UUID format:**
```typescript
const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function validateUUID(value: string): boolean {
  return uuidRegex.test(value);
}
```

**Confidence range:**
```typescript
function validateConfidence(value: number): boolean {
  return value >= 0.0 && value <= 1.0;
}
```

---

## 10. Performance Considerations

### 10.1 Caching

**Tool result caching:**
- `neo4j_get_entity`: Cache for 5 minutes
- `neo4j_query_entities`: Cache for 1 minute
- `mongodb_get_scene`: Cache for 30 seconds (active scenes)

**Cache invalidation:**
- `neo4j_create_entity` → invalidate entity queries for universe
- `mongodb_append_turn` → invalidate scene cache
- `composite_canonize_scene` → invalidate all scene and entity caches

### 10.2 Batching

**Batch tool calls:**
Agents can call multiple tools in parallel when there are no dependencies:

```json
[
  {"name": "neo4j_get_entity", "arguments": {"entity_id": "uuid1"}},
  {"name": "neo4j_get_entity", "arguments": {"entity_id": "uuid2"}},
  {"name": "neo4j_get_entity", "arguments": {"entity_id": "uuid3"}}
]
```

The MCP server executes these in parallel and returns results in order.

---

## 11. Implementation Checklist

To implement this MCP transport layer:

- [ ] Set up MCP server with tool registration
- [ ] Implement JSON Schema validation for all tools
- [ ] Implement authority enforcement middleware
- [ ] Create database adapter layer (Neo4j, MongoDB, Qdrant clients)
- [ ] Implement composite operations (AssembleSceneContext, CanonizeScene)
- [ ] Add request/response logging
- [ ] Implement caching layer
- [ ] Add metrics collection (latency, error rates)
- [ ] Create integration tests for each tool
- [ ] Document error codes and recovery procedures
- [ ] Set up monitoring/alerting

---

## 12. Agent Client Examples

### 12.1 Orchestrator Creating a Scene

```typescript
// Orchestrator agent context
const agentContext = {
  agent_id: "orchestrator-001",
  agent_type: "Orchestrator"
};

// Create story
const story = await mcp.call({
  context: agentContext,
  tool: "neo4j_create_story",
  arguments: {
    universe_id: "universe-uuid",
    title: "The Fellowship of the Ring",
    story_type: "campaign",
    theme: "Heroic journey",
    premise: "Destroy the One Ring"
  }
});

// Create scene
const scene = await mcp.call({
  context: agentContext,
  tool: "mongodb_create_scene",
  arguments: {
    story_id: story.story_id,
    universe_id: "universe-uuid",
    title: "Council of Elrond",
    purpose: "Form the fellowship",
    location_ref: "rivendell-uuid",
    participating_entities: ["gandalf-uuid", "aragorn-uuid", "frodo-uuid"]
  }
});
```

---

### 12.2 Narrator Adding a Turn

```typescript
// Narrator agent context
const agentContext = {
  agent_id: "narrator-001",
  agent_type: "Narrator"
};

// Append GM turn
const turn = await mcp.call({
  context: agentContext,
  tool: "mongodb_append_turn",
  arguments: {
    scene_id: "scene-uuid",
    speaker: "gm",
    text: "Gandalf stands and addresses the council: 'We must destroy the Ring!'"
  }
});
```

---

### 12.3 CanonKeeper Canonizing a Scene

```typescript
// CanonKeeper agent context
const agentContext = {
  agent_id: "canonkeeper-001",
  agent_type: "CanonKeeper"
};

// Canonize scene (composite operation)
const result = await mcp.call({
  context: agentContext,
  tool: "composite_canonize_scene",
  arguments: {
    scene_id: "scene-uuid",
    evaluate_proposals: true
  }
});

console.log(`Accepted ${result.accepted_proposals.length} proposals`);
console.log(`Created ${result.canonical_fact_ids.length} facts`);
```

---

## References

- [DATA_LAYER_API.md](DATA_LAYER_API.md) - Complete API specification
- [AGENT_ORCHESTRATION.md](AGENT_ORCHESTRATION.md) - Agent roles and authority
- [ONTOLOGY.md](../ontology/ONTOLOGY.md) - Data model specification
- MCP Specification: https://modelcontextprotocol.io/
