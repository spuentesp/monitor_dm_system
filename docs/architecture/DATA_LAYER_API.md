# MONITOR Data Layer API

*Complete API contract for interacting with MONITOR's multi-database data layer.*

---

## Overview

The Data Layer is a **service interface** between agents and the five storage systems. Agents interact with data exclusively through these APIs, never directly with databases.

**Key principle:** Data layer is stateless and agent-agnostic. It validates, enforces authority, and ensures consistency.

---

## API Architecture

```
┌─────────────────────────────────────────────┐
│           AGENT LAYER                       │
│  (Orchestrator, Narrator, CanonKeeper...)  │
└────────────────┬────────────────────────────┘
                 │
                 ▼ (MCP or gRPC)
┌─────────────────────────────────────────────┐
│        DATA LAYER API                       │
│  - Validation                               │
│  - Authority enforcement                    │
│  - Cross-DB coordination                    │
└─┬───────┬────────┬────────┬────────┬────────┘
  │       │        │        │        │
  ▼       ▼        ▼        ▼        ▼
┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
│Neo4│ │Mongo│ │Qdrant│ │OpenS│ │MinIO│
└────┘ └────┘ └────┘ └────┘ └────┘
```

---

## 1. Neo4j Canonical Operations

### 1.1 Universe & World Structure

#### CreateUniverse
```typescript
interface CreateUniverseRequest {
  multiverse_id: UUID;
  name: string;
  description: string;
  genre?: string;
  tone?: string;
  tech_level?: string;
  authority: "source" | "gm" | "system";
}

interface CreateUniverseResponse {
  universe_id: UUID;
  created_at: timestamp;
}
```

**Authority:** CanonKeeper only
**Validation:** multiverse_id must exist, name required

---

#### GetUniverse
```typescript
interface GetUniverseRequest {
  universe_id: UUID;
}

interface GetUniverseResponse {
  universe_id: UUID;
  name: string;
  description: string;
  genre: string;
  tone: string;
  tech_level: string;
  canon_level: "proposed" | "canon" | "retconned";
  created_at: timestamp;
}
```

**Authority:** Any agent (read-only)

---

#### ListUniverses
```typescript
interface ListUniversesRequest {
  multiverse_id?: UUID;  // filter by multiverse
  canon_level?: "proposed" | "canon" | "retconned";
  limit?: number;
  offset?: number;
}

interface ListUniversesResponse {
  universes: Universe[];
  total: number;
}
```

**Authority:** Any agent (read-only)

---

### 1.2 Entity Operations

#### CreateEntity
```typescript
interface CreateEntityRequest {
  entity_class: "EntityArchetype" | "EntityInstance";
  universe_id: UUID;
  name: string;
  entity_type: "character" | "faction" | "location" | "object" | "concept" | "organization";
  description: string;
  properties: Record<string, any>;
  state_tags?: string[];  // EntityInstance only
  derives_from?: UUID;  // EntityInstance only, optional EntityArchetype reference
  confidence: number;  // 0.0-1.0
  authority: "source" | "gm" | "player" | "system";
  evidence_refs: string[];  // ["source:uuid", "turn:uuid", ...]
}

interface CreateEntityResponse {
  entity_id: UUID;
  canon_level: "proposed" | "canon";
  created_at: timestamp;
}
```

**Authority:** CanonKeeper only
**Validation:**
- universe_id must exist
- confidence ∈ [0.0, 1.0]
- state_tags only for EntityInstance
- derives_from must reference EntityArchetype of same type

---

#### GetEntity
```typescript
interface GetEntityRequest {
  entity_id: UUID;
  include_relationships?: boolean;
  include_state_history?: boolean;
}

interface GetEntityResponse {
  entity_id: UUID;
  entity_class: "EntityArchetype" | "EntityInstance";
  universe_id: UUID;
  name: string;
  entity_type: string;
  description: string;
  properties: Record<string, any>;
  state_tags?: string[];
  canon_level: "proposed" | "canon" | "retconned";
  confidence: number;
  created_at: timestamp;
  updated_at?: timestamp;
  relationships?: Relationship[];  // if requested
}
```

**Authority:** Any agent (read-only)

---

#### UpdateEntityState
```typescript
interface UpdateEntityStateRequest {
  entity_id: UUID;
  state_tag_changes: {
    add?: string[];
    remove?: string[];
  };
  authority: "gm" | "player" | "system";
  evidence_refs: string[];
}

interface UpdateEntityStateResponse {
  entity_id: UUID;
  new_state_tags: string[];
  fact_ids: UUID[];  // created Fact nodes documenting changes
}
```

**Authority:** CanonKeeper only
**Validation:**
- entity must be EntityInstance
- Creates Fact nodes for each state change

---

#### QueryEntities
```typescript
interface QueryEntitiesRequest {
  universe_id?: UUID;
  entity_type?: string;
  entity_class?: "EntityArchetype" | "EntityInstance";
  canon_level?: "proposed" | "canon" | "retconned";
  state_tags?: {
    all_of?: string[];  // has ALL these tags
    any_of?: string[];  // has ANY of these tags
    none_of?: string[];  // has NONE of these tags
  };
  name_pattern?: string;  // regex or LIKE
  limit?: number;
  offset?: number;
}

interface QueryEntitiesResponse {
  entities: Entity[];
  total: number;
}
```

**Authority:** Any agent (read-only)

---

### 1.3 Fact & Event Operations

#### CreateFact
```typescript
interface CreateFactRequest {
  universe_id: UUID;
  statement: string;
  time_ref?: timestamp;
  duration?: number;
  involved_entity_ids: UUID[];
  confidence: number;
  authority: "source" | "gm" | "player" | "system";
  evidence_refs: string[];  // ["source:uuid", "scene:uuid", "turn:uuid"]
}

interface CreateFactResponse {
  fact_id: UUID;
  canon_level: "proposed" | "canon";
  created_at: timestamp;
}
```

**Authority:** CanonKeeper only
**Validation:**
- Creates INVOLVES edges to entities
- Creates SUPPORTED_BY edges to evidence

---

#### CreateEvent
```typescript
interface CreateEventRequest {
  scene_id?: UUID;
  universe_id: UUID;
  title: string;
  description: string;
  time_ref?: timestamp;
  severity: number;  // 0-10
  involved_entity_ids: UUID[];
  causes_event_ids?: UUID[];  // causal edges
  confidence: number;
  authority: "source" | "gm" | "player" | "system";
  evidence_refs: string[];
}

interface CreateEventResponse {
  event_id: UUID;
  canon_level: "proposed" | "canon";
  created_at: timestamp;
}
```

**Authority:** CanonKeeper only
**Validation:**
- Creates CAUSES edges (must be acyclic)
- Creates INVOLVES edges to entities

---

#### QueryFacts
```typescript
interface QueryFactsRequest {
  universe_id?: UUID;
  entity_id?: UUID;  // facts involving this entity
  time_range?: { start: timestamp; end: timestamp };
  canon_level?: "proposed" | "canon" | "retconned";
  authority?: "source" | "gm" | "player" | "system";
  limit?: number;
  offset?: number;
}

interface QueryFactsResponse {
  facts: Fact[];
  total: number;
}
```

**Authority:** Any agent (read-only)

---

### 1.4 Story & Scene Operations

#### CreateStory
```typescript
interface CreateStoryRequest {
  universe_id: UUID;
  title: string;
  story_type: "campaign" | "arc" | "episode" | "one_shot";
  theme?: string;
  premise?: string;
  parent_story_id?: UUID;  // for arcs within campaigns
  start_time_ref?: timestamp;
}

interface CreateStoryResponse {
  story_id: UUID;
  created_at: timestamp;
}
```

**Authority:** CanonKeeper (or Orchestrator for planning)

---

#### CreateCanonicalScene
```typescript
interface CreateCanonicalSceneRequest {
  story_id: UUID;
  title: string;
  purpose?: string;
  order: number;
  time_ref?: timestamp;
  participating_entity_ids: UUID[];
}

interface CreateCanonicalSceneResponse {
  scene_id: UUID;
  created_at: timestamp;
}
```

**Authority:** CanonKeeper only
**Note:** Most scenes stay MongoDB-only. Only create in Neo4j if needed for timeline/continuity.

---

### 1.5 Provenance Operations

#### CreateSource
```typescript
interface CreateSourceRequest {
  universe_id: UUID;
  doc_id: string;  // MongoDB reference
  title: string;
  edition?: string;
  provenance?: string;  // ISBN, URL, etc.
  source_type: "manual" | "rulebook" | "lore" | "session";
  canon_level: "proposed" | "canon" | "authoritative";
}

interface CreateSourceResponse {
  source_id: UUID;
  created_at: timestamp;
}
```

**Authority:** CanonKeeper only

---

#### LinkEvidence
```typescript
interface LinkEvidenceRequest {
  canonical_id: UUID;  // Fact/Event/Entity/Axiom
  canonical_type: "Fact" | "Event" | "Entity" | "Axiom";
  evidence_id: UUID;
  evidence_type: "Source" | "Scene" | "Turn";
}

interface LinkEvidenceResponse {
  edge_id: string;
}
```

**Authority:** CanonKeeper only
**Validation:** Creates SUPPORTED_BY edge

---

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

**Authority:** Orchestrator only
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

**Authority:** Narrator, Orchestrator
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

**Authority:** MemoryManager only
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

**Authority:** ContextAssembly, MemoryManager

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

## 5. Authority Enforcement

### Authority Matrix

| Operation | Allowed Agents | Validation |
|-----------|---------------|-----------|
| CreateEntity | CanonKeeper | Requires evidence_refs |
| CreateFact | CanonKeeper | Requires evidence_refs, involved entities |
| CreateProposedChange | Resolver, Narrator, any | None (staging) |
| EvaluateProposal | CanonKeeper | Authority + confidence checks |
| CreateScene | Orchestrator | Requires valid story_id |
| CreateStory | CanonKeeper, Orchestrator | Planning writes; canonical container |
| AppendTurn | Narrator, Orchestrator | Scene must be active |
| UpdateEntityState | CanonKeeper | Creates Fact nodes |
| EmbedMemory | Indexer | Requires valid memory_id |
| SemanticSearch | Any | Read-only |

### Enforcement Mechanism

```typescript
interface APIRequest {
  agent_id: string;
  agent_type: "Orchestrator" | "CanonKeeper" | "Narrator" | ...;
  operation: string;
  params: Record<string, any>;
}

function enforceAuthority(request: APIRequest): boolean {
  const allowed = AUTHORITY_MATRIX[request.operation];
  return allowed.includes(request.agent_type);
}
```

---

## 6. Transaction Semantics

### 6.1 Scene Canonization Transaction

**Scope:** End of scene batch commit

**Atomicity:**
1. All proposals evaluated atomically (all-or-nothing per proposal)
2. If Neo4j write fails, proposal stays "pending"
3. MongoDB scene state reflects last successful canonization

**Isolation:**
- Concurrent scenes can canonize independently
- Same scene cannot canonize concurrently (lock scene_id)

**Durability:**
- Neo4j writes are durable once committed
- MongoDB proposals track status
- Qdrant updates are eventual (can retry)

---

### 6.2 Entity State Update Transaction

**Scope:** Updating entity state tags

**Operations:**
1. Update EntityInstance.state_tags (Neo4j)
2. Create Fact documenting change (Neo4j)
3. Link INVOLVES edge (Neo4j)
4. Link SUPPORTED_BY evidence (Neo4j)

**Rollback:** If any step fails, rollback all (Neo4j transaction)

---

## 7. Use Case Examples

### P-1: Start New Story

**Data flow:**
```
1. CreateStory (Neo4j)
   → story_id

2. CreateScene (MongoDB)
   → scene_id, status=active

3. Optional: CreateCanonicalScene (Neo4j)
   → canonical scene_id for timeline
```

---

### P-3: User Turn in Active Scene

**Data flow:**
```
1. AppendTurn (MongoDB)
   → turn_id

2. CreateProposedChange (MongoDB) - if action implies changes
   → proposal_id, status=pending

3. No Neo4j writes (deferred)
```

---

### P-8: End Scene (Canonization)

**Data flow:**
```
1. GetPendingProposals (MongoDB)
   → proposals[]

2. For each proposal:
   a. EvaluateProposal (CanonKeeper logic)
   b. If accepted:
      - CreateFact/CreateEvent (Neo4j)
      - LinkEvidence (Neo4j)
      - EvaluateProposal status=accepted (MongoDB)
   c. If rejected:
      - EvaluateProposal status=rejected (MongoDB)

3. FinalizeScene (MongoDB)
   → status=completed, canonical_outcomes=fact_ids

4. EmbedSceneSummary (Qdrant)
   → indexed for recall
```

---

### I-1: Upload Document

**Data flow:**
```
1. CreateSource (Neo4j)
   → source_id

2. CreateDocument (MongoDB)
   → doc_id, minio_ref

3. CreateSnippet × N (MongoDB)
   → snippet_ids[]

4. EmbedSnippet × N (Qdrant)
   → indexed

5. CreateProposedChange × M (MongoDB)
   → proposals for axioms/entities

6. User review → EvaluateProposal × M
   → accepted proposals

7. CreateEntity/CreateAxiom (Neo4j) for accepted
   → canonical_ids
```

---

### Q-1: Semantic Search

**Data flow:**
```
1. SemanticSearch (Qdrant)
   → candidate IDs

2. GetEntity / QueryFacts (Neo4j)
   → canonical data

3. Optional: GetScene (MongoDB) for narrative details
   → narrative context

4. Return composed result
```

---

## 8. Error Handling

### Error Codes

| Code | Meaning | Recovery |
|------|---------|----------|
| `UNAUTHORIZED` | Agent lacks authority for operation | Reject request |
| `NOT_FOUND` | Referenced ID doesn't exist | Check references |
| `VALIDATION_ERROR` | Invalid parameters | Fix parameters |
| `CONSTRAINT_VIOLATION` | DB constraint failed | Check invariants |
| `TRANSACTION_FAILED` | DB write failed | Retry or rollback |
| `ALREADY_CANONIZED` | Scene already finalized | Cannot modify |

### Retry Policy

- **Idempotent operations** (reads): Safe to retry
- **Non-idempotent writes** (creates): Use unique IDs to detect duplicates
- **Transactions**: Rollback on failure, retry entire transaction

---

## 9. Performance Considerations

### Caching Strategy

**What to cache:**
- Frequently accessed entities (PCs, active NPCs)
- Current scene canonical state
- Universe/Story metadata

**Cache invalidation:**
- On entity state update
- On scene canonization
- TTL: 5 minutes for canonical data

### Batch Operations

**CreateProposedChange bulk:**
```typescript
interface CreateProposedChangesBulkRequest {
  proposals: CreateProposedChangeRequest[];
}
```

Reduces round-trips for multi-change turns.

---

## 10. API Versioning

**Current version:** v1

**Breaking changes require v2:**
- Changing request/response schemas
- Removing operations
- Changing authority requirements

**Non-breaking changes (v1.x):**
- Adding optional parameters
- Adding new operations
- Extending response data

---

## 11. Implementation Checklist

To implement this API:

- [ ] Define transport layer (MCP, gRPC, REST)
- [ ] Implement authority enforcement middleware
- [ ] Create validation schemas (JSON Schema, Pydantic)
- [ ] Build composite operations (AssembleSceneContext, CanonizeScene)
- [ ] Implement transaction boundaries
- [ ] Add logging/tracing for all operations
- [ ] Create API client libraries per agent type
- [ ] Write integration tests for use cases
- [ ] Document error codes and recovery procedures
- [ ] Set up monitoring for operation latencies

---

## References

- [DATABASE_INTEGRATION.md](DATABASE_INTEGRATION.md) - Data layer architecture
- [AGENT_ORCHESTRATION.md](AGENT_ORCHESTRATION.md) - Agent roles and authority
- [ONTOLOGY.md](../ontology/ONTOLOGY.md) - Data model specification
- [CONVERSATIONAL_LOOPS.md](CONVERSATIONAL_LOOPS.md) - Loop workflows
