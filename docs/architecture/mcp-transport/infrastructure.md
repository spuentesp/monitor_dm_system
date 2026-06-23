## 7. Authority Enforcement

### 7.1 Request Context

Every MCP tool call includes:

```json
{
  "agent_id": "uuid",
  "agent_type": "CanonKeeper | Narrator | ContextAssembly | Resolver | Indexer | Analyzer | IngestionPipeline | WorldArchitect | NPCVoice"
}
```

### 7.2 Authority Matrix

| Tool Pattern | Allowed Agent Types |
|-------------|---------------------|
| `neo4j_create_*` | CanonKeeper |
| `neo4j_create_story` | CanonKeeper |
| `neo4j_create_ability_system` | CanonKeeper |
| `neo4j_create_track` | CanonKeeper |
| `neo4j_create_condition` | CanonKeeper |
| `neo4j_link_entity_to_ability` | CanonKeeper |
| `neo4j_update_*` | CanonKeeper |
| `neo4j_get_*` | Any |
| `neo4j_query_*` | Any |
| `mongodb_create_scene` | Any |
| `mongodb_append_turn` | Narrator, NPCVoice |
| `mongodb_create_proposed_change` | Any |
| `mongodb_evaluate_proposal` | CanonKeeper |
| `mongodb_finalize_scene` | CanonKeeper |
| `mongodb_create_character_memory` | Narrator, NPCVoice |
| `qdrant_*` | Any (read-only) |
| `composite_assemble_scene_context` | ContextAssembly |
| `composite_canonize_scene` | CanonKeeper |

### 7.3 Enforcement Logic

```typescript
function enforceAuthority(tool: string, agentType: string): boolean {
  const matrix = {
    "neo4j_create_entity": ["CanonKeeper"],
    "neo4j_create_story": ["CanonKeeper"],
    "neo4j_update_entity_state": ["CanonKeeper"],
    "neo4j_get_entity": ["*"],
    "mongodb_create_scene": ["*"],
    "mongodb_append_turn": ["Narrator", "NPCVoice"],
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

### 12.1 Narrator Creating a Scene Turn

```typescript
// Narrator agent context (called from SceneLoop 'narrate' node)
const agentContext = {
  agent_id: "narrator-001",
  agent_type: "Narrator"  // Loops call agents; agents call tools
};

// Narrator persists the GM turn to MongoDB
const turn = await mcp.call({
  context: agentContext,
  tool: "mongodb_append_turn",
  arguments: {
    scene_id: "scene-uuid",
    speaker: "GM",
    text: "Gandalf steps forward...",
    turn_type: "narrative"
  }
});
```

> **Note:** `SceneLoop` is a LangGraph `StateGraph`, not a `BaseAgent`. Loops *call agents*; agents hold an `agent_type` and call MCP tools. A loop node never passes `agent_type: "SceneLoop"` to the MCP server.

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
