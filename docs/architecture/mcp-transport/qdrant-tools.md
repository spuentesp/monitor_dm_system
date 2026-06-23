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

