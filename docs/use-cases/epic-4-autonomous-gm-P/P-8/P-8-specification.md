# P-8: End Scene (Canonization)

**Actor:** User / scene runtime
**Trigger:** Scene goal met, user `/end`, or narrative signal

**Flow:**
1. Narrator generates scene closing narration
2. Display closing
3. **Canonization gate:**
   - Fetch pending ProposedChanges for scene
   - For each proposal:
     - Evaluate: authority, confidence, contradictions
     - Accept → write to Neo4j (Fact/Event/Entity)
     - Reject → mark rejected with rationale
   - Link evidence (SUPPORTED_BY edges)
4. Update scene status = "completed"
5. Generate scene summary
6. Embed summary in Qdrant
7. Prompt: New scene (→ P-2), End session (→ SYS-3), or Continue story

### Implementation

**Layer 1 (Data Layer):**
```python
# Canonization tools (CanonKeeper only):
mongodb_list_pending_proposals(scene_id)  # Get pending proposals
neo4j_create_fact(params) -> fact_id      # Write accepted fact
neo4j_create_event(params) -> event_id    # Write accepted event
neo4j_create_entity(params) -> entity_id  # Write new entity
neo4j_set_state_tags(entity_id, changes)  # Update entity state
neo4j_link_evidence(canonical_id, refs)   # SUPPORTED_BY edges
mongodb_evaluate_proposal(id, decision)   # Mark accepted/rejected
mongodb_update_scene(scene_id, status)    # Complete scene
qdrant_embed_scene(scene_id, summary)     # Index for recall
```

**Layer 2 (Agents / runtime):**
- `SceneLoop` reaches its canonization/finalization node at scene end
- `Narrator.generate_scene_closing(context)` - Closing narration
- `CanonKeeper.canonize_scene(scene_id)` - **Critical: only agent that writes ongoing scene canon to Neo4j**
- `Indexer.embed_scene_summary(scene_id, summary)` - Vectorize for recall

**Canonization Algorithm:**
```python
async def canonize_scene(scene_id: UUID) -> CanonizationResult:
    proposals = await mongodb_list_pending_proposals(scene_id)

    accepted = []
    rejected = []

    for proposal in proposals:
        decision = await evaluate_proposal(proposal)

        if decision.accept:
            # Write to Neo4j based on proposal type
            canonical_id = await write_to_canon(proposal)

            # Link evidence
            await neo4j_link_evidence(canonical_id, proposal.evidence)

            # Mark accepted
            await mongodb_evaluate_proposal(
                proposal.id,
                status="accepted",
                canonical_id=canonical_id
            )
            accepted.append(canonical_id)
        else:
            await mongodb_evaluate_proposal(
                proposal.id,
                status="rejected",
                rationale=decision.rationale
            )
            rejected.append(proposal.id)

    return CanonizationResult(accepted=accepted, rejected=rejected)

async def evaluate_proposal(proposal: ProposedChange) -> Decision:
    """Evaluate if proposal should be canonized."""

    # 1. Check authority weight
    authority_weight = {
        "source": 1.0,
        "gm": 0.9,
        "player": 0.7,
        "system": 0.5
    }[proposal.authority]

    # 2. Check for contradictions with existing facts
    contradictions = await neo4j_check_contradictions(proposal)
    if contradictions:
        return Decision(accept=False, rationale=f"Contradicts: {contradictions}")

    # 3. Check confidence threshold
    min_confidence = 0.5
    if proposal.confidence * authority_weight < min_confidence:
        return Decision(accept=False, rationale="Below confidence threshold")

    return Decision(accept=True)

async def write_to_canon(proposal: ProposedChange) -> UUID:
    """Write proposal to appropriate Neo4j node type."""
    match proposal.type:
        case "fact":
            return await neo4j_create_fact(proposal.content)
        case "event":
            return await neo4j_create_event(proposal.content)
        case "entity":
            return await neo4j_create_entity(proposal.content)
        case "state_change":
            await neo4j_set_state_tags(
                proposal.content["entity_id"],
                proposal.content["changes"]
            )
            # State changes also create a fact documenting the change
            return await neo4j_create_fact({
                "statement": f"Entity state changed",
                "involved_entity_ids": [proposal.content["entity_id"]]
            })
        case "relationship":
            return await neo4j_create_relationship(proposal.content)
```

**Database Writes:**

| Phase | Database | Operation | Data |
|-------|----------|-----------|------|
| 1 | MongoDB | Read | `proposed_changes WHERE scene_id AND status=pending` |
| 2 | Neo4j | Write | `(:Fact)`, `(:Event)`, `(:EntityInstance)`, relationships |
| 3 | Neo4j | Write | `(:Fact)-[:SUPPORTED_BY]->(:Turn)` edges |
| 4 | MongoDB | Update | `proposed_changes.status = accepted/rejected` |
| 5 | MongoDB | Update | `scenes.status = completed, canonical_outcomes = [...]` |
| 6 | Qdrant | Upsert | Scene summary embedding |

**Invariants:**
- Only CanonKeeper writes ongoing scene canon to Neo4j; the current web bootstrap path may create the initial `Story` container during setup
- Every canonical fact/event MUST have evidence (SUPPORTED_BY edge)
- Rejected proposals keep their data for audit trail
- Scene status: `active` → `finalizing` → `completed`

---
