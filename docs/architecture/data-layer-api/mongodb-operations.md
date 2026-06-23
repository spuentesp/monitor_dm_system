## 2. MongoDB Narrative Operations

### 2.1 Scene Operations

#### CreateScene
```typescript
interface CreateSceneRequest {
  story_id: UUID;  // Neo4j reference
  universe_id: UUID;  // Neo4j reference
  title: string;
  purpose?: string;
  order?: number;  // optional ordering within the Story
  location_ref?: UUID;  // EntityInstance ID
  participating_entities: UUID[];  // EntityInstance IDs
}

interface CreateSceneResponse {
  scene_id: UUID;
  status: "active";
  created_at: Date;
}
```

**Authority:** Any agent (scene creation is a MongoDB write)
**Storage:** MongoDB scenes collection

---

#### AppendTurn
```typescript
interface AppendTurnRequest {
  scene_id: UUID;
  speaker: "user" | "gm" | "entity";
  entity_id?: UUID;  // if speaker is entity
  text: string;
  resolution_ref?: UUID;
}

interface AppendTurnResponse {
  turn_id: UUID;
  timestamp: Date;
}
```

**Authority:** Narrator, NPCVoice
**Storage:** Appends to scenes.turns array or separate turns collection

---

#### GetScene
```typescript
interface GetSceneRequest {
  scene_id: UUID;
  include_turns?: boolean;
  include_proposals?: boolean;
  turn_limit?: number;  // last N turns
}

interface GetSceneResponse {
  scene_id: UUID;
  story_id: UUID;
  universe_id: UUID;
  title: string;
  status: "active" | "finalizing" | "completed";
  order?: number;
  location_ref?: UUID;
  participating_entities: UUID[];
  turns?: Turn[];
  proposed_changes?: UUID[];
  canonical_outcomes?: UUID[];
  summary?: string;
  created_at: Date;
  updated_at: Date;
  completed_at?: Date;
}
```

**Authority:** Any agent (read-only)

---

#### FinalizeScene
```typescript
interface FinalizeSceneRequest {
  scene_id: UUID;
  canonical_outcome_ids: UUID[];  // Neo4j Fact/Event IDs
  summary: string;
}

interface FinalizeSceneResponse {
  scene_id: UUID;
  status: "completed";
  completed_at: Date;
}
```

**Authority:** CanonKeeper (after canonization)
**Side effects:**
- Updates scene.status = "completed"
- Sets canonical_outcomes
- Triggers Indexer to embed summary

---

### 2.2 ProposedChange Operations

#### CreateProposedChange
```typescript
interface CreateProposedChangeRequest {
  scene_id: UUID;
  turn_id?: UUID;  // optional for ingest/system proposals
  type: "fact" | "entity" | "relationship" | "state_change" | "event";
  content: Record<string, any>;  // structure depends on type
  evidence: Array<{
    type: "turn" | "snippet" | "source" | "rule";
    ref_id: UUID;
  }>;
  confidence: number;
  authority: "source" | "gm" | "player" | "system";
}

interface CreateProposedChangeResponse {
  proposal_id: UUID;
  status: "pending";
  created_at: Date;
}
```

**Authority:** Resolver, Narrator, any agent proposing changes
**Storage:** MongoDB proposed_changes collection

---

#### EvaluateProposal
```typescript
interface EvaluateProposalRequest {
  proposal_id: UUID;
  decision: "accepted" | "rejected";
  rationale?: string;
  canonical_id?: UUID;  // if accepted, the Neo4j node/edge ID
}

interface EvaluateProposalResponse {
  proposal_id: UUID;
  status: "accepted" | "rejected";
  evaluated_at: Date;
}
```

**Authority:** CanonKeeper only
**Side effects:**
- Updates proposal status
- If accepted, links to canonical_id

---

#### GetPendingProposals
```typescript
interface GetPendingProposalsRequest {
  scene_id?: UUID;
  type?: "fact" | "entity" | "relationship" | "state_change" | "event";
  limit?: number;
}

interface GetPendingProposalsResponse {
  proposals: ProposedChange[];
  total: number;
}
```

**Authority:** CanonKeeper (for evaluation)

---

### 2.3 Memory Operations

#### CreateCharacterMemory
```typescript
interface CreateCharacterMemoryRequest {
  entity_id: UUID;  // Neo4j EntityInstance
  text: string;
  linked_fact_id?: UUID;  // optional Neo4j Fact anchor
  scene_id?: UUID;
  emotional_valence: number;  // -1.0 to 1.0
  importance: number;  // 0.0-1.0
  certainty: number;  // 0.0-1.0
}

interface CreateCharacterMemoryResponse {
  memory_id: UUID;
  created_at: Date;
}
```

**Authority:** Narrator, NPCVoice
**Side effects:** Triggers Indexer to embed memory

---

#### RetrieveCharacterMemories
```typescript
interface RetrieveCharacterMemoriesRequest {
  entity_id: UUID;
  limit?: number;
  min_importance?: number;
  semantic_query?: string;  // if provided, uses Qdrant
}

interface RetrieveCharacterMemoriesResponse {
  memories: Memory[];
  total: number;
}
```

**Authority:** ContextAssembly, Narrator, NPCVoice

---

### 2.4 Document & Snippet Operations

#### CreateDocument
```typescript
interface CreateDocumentRequest {
  source_id: UUID;  // Neo4j Source
  universe_id: UUID;
  minio_ref: string;
  title: string;
  filename: string;
  file_type: string;
}

interface CreateDocumentResponse {
  doc_id: UUID;
  extraction_status: "pending";
  created_at: Date;
}
```

**Authority:** Ingest pipeline

---

#### CreateSnippet
```typescript
interface CreateSnippetRequest {
  doc_id: UUID;
  source_id: UUID;
  text: string;
  page?: number;
  section?: string;
  chunk_index: number;
}

interface CreateSnippetResponse {
  snippet_id: UUID;
  created_at: Date;
}
```

**Authority:** Ingest pipeline
**Side effects:** Triggers Indexer to embed snippet

---

