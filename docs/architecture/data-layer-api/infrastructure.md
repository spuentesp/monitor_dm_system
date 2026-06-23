## 5. Authority Enforcement

### Authority Matrix

| Operation | Allowed Agents | Validation |
|-----------|---------------|-----------|
| CreateEntity | CanonKeeper | Requires evidence_refs |
| CreateFact | CanonKeeper | Requires evidence_refs, involved entities |
| CreateProposedChange | Resolver, Narrator, any | None (staging) |
| EvaluateProposal | CanonKeeper | Authority + confidence checks |
| CreateScene | Any | Requires valid story_id |
| CreateStory | CanonKeeper | Canonical write |
| AppendTurn | Narrator, NPCVoice | Scene must be active |
| UpdateEntityState | CanonKeeper | Creates Fact nodes |
| EmbedMemory | Indexer | Requires valid memory_id |
| SemanticSearch | Any | Read-only |

### Enforcement Mechanism

```typescript
interface APIRequest {
  agent_id: string;
  agent_type: "CanonKeeper" | "Narrator" | "ContextAssembly" | "Resolver" | "Indexer" | "Analyzer" | "IngestionPipeline" | "WorldArchitect" | "NPCVoice";
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
