### 4. CanonKeeper Agent

> **Implementation:** `packages/agents/src/monitor_agents/canonkeeper.py`

**Responsibility:** Enforce canonization policy and write to Neo4j

**Authority:**
- Read: all databases
- Write: **Neo4j (only agent with Neo4j write access)**
- Write: MongoDB (proposal status updates)
- Canonize: **yes (exclusive authority)**

**What it does:**
- Evaluate ProposedChanges by policy
- Accept/reject proposals (authority + confidence checks)
- Batch write to Neo4j (Facts, Relations, State)
- Create SUPPORTED_BY provenance edges
- Detect contradictions
- Enforce temporal consistency
- Handle retcons

**What it does NOT do:**
- Generate proposals (receives them)
- Generate narrative
- Resolve actions

**Canonization Policy Evaluation:**
```python
def evaluate_proposal(proposal):
    # Check authority
    if proposal.authority == "source":
        confidence = 1.0
    elif proposal.authority == "gm":
        confidence = 1.0
    elif proposal.authority == "player":
        confidence = 0.8  # via resolution
    elif proposal.authority == "system":
        confidence = 0.5  # inferred

    # Check evidence
    if not proposal.evidence:
        confidence *= 0.5  # penalize unsupported

    # Check contradictions
    if contradicts_canon(proposal):
        if proposal.authority == "gm":
            # GM override: allow retcon
            mark_contradicted_facts_retconned()
        else:
            return "rejected", "contradicts canon"

    # Decide
    if confidence >= THRESHOLD:
        return "accepted", confidence
    else:
        return "pending", confidence  # needs review
```

**Canonization execution:**
```python
def finalize_scene(scene_id):
    proposals = ProposedChange.get_pending(scene_id)

    accepted = []
    rejected = []

    for proposal in proposals:
        status, reason = evaluate_proposal(proposal)

        if status == "accepted":
            # Write to Neo4j
            fact = create_fact(proposal)
            neo4j.create(fact)

            # Create evidence edges
            for evidence_id in proposal.evidence:
                neo4j.create_edge(fact, "SUPPORTED_BY", evidence_id)

            accepted.append(proposal.id)
        else:
            rejected.append((proposal.id, reason))

    # Update MongoDB
    ProposedChange.mark_accepted(accepted)
    ProposedChange.mark_rejected(rejected)

    # Update scene
    Scene.update(scene_id, {
        "status": "completed",
        "canonical_outcomes": [f.id for f in accepted]
    })
```

---

### 5. Indexer Agent (Background)

> **Implementation:** `packages/agents/src/monitor_agents/indexer.py`

**Responsibility:** Convert raw documents into searchable Qdrant vectors; keep semantic indices up-to-date

**Authority:**
- Read: MongoDB, MinIO
- Write: **Qdrant (exclusive write access to `snippets` collection)**
- Canonize: no

**What it does:**
- Ingest any supported format (PDF, EPUB, DOCX, MD, HTML, TXT, images, URIs)
- Chunk text via `ingest_tools` (tiktoken `cl100k_base`, 512 tokens, 10% overlap)
- Embed via `embed_batch()` (litellm → 1536-dim vectors)
- Upsert to Qdrant in batches of 64
- Analyse images with LLM vision (GPT-4o-mini / Claude 3 / Gemini class)
- Re-index existing content when the embedding model changes

**What it does NOT do:**
- Extract structured knowledge (that's Analyzer)
- Write to Neo4j (proposals go through CanonKeeper)

---

