## 3. Qdrant Semantic Operations

### 3.1 Embedding Operations

#### EmbedSceneSummary
```typescript
interface EmbedSceneSummaryRequest {
  scene_id: UUID;
  story_id: UUID;
  universe_id: UUID;
  text: string;
  timestamp: Date;
}

interface EmbedSceneSummaryResponse {
  vector_id: UUID;
  collection: "scene_chunks";
}
```

**Authority:** Indexer only

---

#### EmbedMemory
```typescript
interface EmbedMemoryRequest {
  memory_id: UUID;
  entity_id: UUID;
  text: string;
  importance: number;
  timestamp: Date;
}

interface EmbedMemoryResponse {
  vector_id: UUID;
  collection: "memory_chunks";
}
```

**Authority:** Indexer only

---

### 3.2 Retrieval Operations

#### SemanticSearch
```typescript
interface SemanticSearchRequest {
  query_text: string;
  collection: "scene_chunks" | "memory_chunks" | "snippet_chunks";
  filters?: {
    universe_id?: UUID;
    entity_id?: UUID;  // for memories
    source_id?: UUID;  // for snippets
  };
  limit?: number;
  min_score?: number;
}

interface SemanticSearchResponse {
  results: Array<{
    id: UUID;
    score: number;
    payload: Record<string, any>;
    text: string;
  }>;
}
```

**Authority:** ContextAssembly, any retrieval agent

---

## 4. Composite Operations (Cross-DB)

### 4.1 Context Assembly

#### AssembleSceneContext
```typescript
interface AssembleSceneContextRequest {
  scene_id: UUID;
  include_canonical?: boolean;
  include_narrative?: boolean;
  include_semantic?: boolean;
  semantic_query?: string;
}

interface AssembleSceneContextResponse {
  canonical: {
    entities: Entity[];
    facts: Fact[];
    relations: Relationship[];
  };
  narrative: {
    prior_turns: Turn[];
    scene_summary?: string;
    gm_notes?: string;
  };
  recalled: {
    similar_scenes?: Scene[];
    character_memories?: Memory[];
    rule_excerpts?: Snippet[];
  };
  metadata: {
    universe_id: UUID;
    story_id: UUID;
    scene_id: UUID;
    timestamp: Date;
  };
}
```

**Authority:** ContextAssembly agent
**Data sources:**
- Neo4j: canonical state
- MongoDB: narrative logs
- Qdrant: semantic recall

---

### 4.2 Canonization

#### CanonizeScene
```typescript
interface CanonizeSceneRequest {
  scene_id: UUID;
  evaluate_proposals?: boolean;  // default true
}

interface CanonizeSceneResponse {
  scene_id: UUID;
  accepted_proposals: UUID[];
  rejected_proposals: UUID[];
  canonical_fact_ids: UUID[];
  canonical_event_ids: UUID[];
  canonical_entity_ids: UUID[];
}
```

**Authority:** CanonKeeper only
**Operations:**
1. Fetch pending proposals from MongoDB
2. Evaluate each (authority + confidence checks)
3. Write accepted to Neo4j (Facts/Events/Entities)
4. Create SUPPORTED_BY edges
5. Update MongoDB proposals status
6. Finalize scene in MongoDB
7. Trigger Indexer

---

