# MONITOR Database Integration Architecture

*How five complementary memory systems work together to build narrative intelligence.*

---

## Core Principle

MONITOR is **not "one database with features."**

It is a **system of complementary memories**, each optimized for a different kind of question.

**There is one source of truth for logic, and supporting stores for recall, text, and media.**

---

## The Five Memory Systems

### 1️⃣ Graph Database (Neo4j) — The Truth Layer

**What it is:**

The **authoritative model of reality** in MONITOR.

If something is true, happened, exists, or relates, **it must be expressible here**.

**What it stores:**

- **Entities**
  - Axiomatic (concepts, archetypes, roles)
  - Concrete (this Spider-Man, this city, this NPC)

- **Facts / Events (objective)**
  - What happened
  - When it happened
  - Where it happened

- **Relationships**
  - `PARTICIPATED_IN`
  - `DERIVES_FROM`
  - `ALLY_OF` / `ENEMY_OF`
  - `LOCATED_IN`

- **State & tags**
  - alive/dead
  - wounded
  - faction member

- **Temporal logic**
  - started_at / ended_at
  - overlaps
  - causality

**What it does well:**

- Continuity checking
- Timeline reconstruction
- Contradiction detection
- Branching universes
- Canon enforcement

**What it does NOT do:**

- Store long narrative text
- Store conversations
- Store subjective opinions
- Do fuzzy recall

**📌 Rule:**

> **If MONITOR needs to reason about it → it belongs in the graph.**

---

### 2️⃣ Document Database (MongoDB) — The Narrative Memory

**What it is:**

The **human-facing memory**: stories, sessions, notes, memories.

This is where **how things were experienced or described** lives.

**What it stores:**

- **Session logs**
  - Turn-by-turn roleplay
  - Dialogue
  - Story prose

- **Scenes**
  - Recaps
  - GM notes
  - Ideas
  - TODOs

- **Character memory**
  - "I remember you saved me"
  - Bias, emotion, misunderstandings

- **Document metadata**
  - What was uploaded
  - Where the file lives (MinIO)
  - Pointers to the graph:
    - `entity_id`
    - `fact_id`
    - `universe_id`

**What it does well:**

- Flexible text storage
- Evolving schemas
- Fast retrieval of whole documents
- Natural fit for sessions & notes

**What it does NOT do:**

- Decide what is objectively true
- Detect contradictions
- Resolve causality

**📌 Rule:**

> **If it's narrative, subjective, conversational, or editorial → MongoDB.**

---

### 3️⃣ Vector Database (Qdrant) — The Recall Engine

**What it is:**

The **associative memory** of MONITOR.

It answers: **"What feels relevant to this question?"**

**What it stores:**

Embeddings of:

- Document chunks (manuals, lore)
- Scene fragments
- Character memory entries
- Notes

Each vector includes metadata:

- `entity_id`
- `fact_id`
- `story_id`
- `universe_id`

**What it does well:**

- Fuzzy recall
- Context assembly
- "Find similar moments"
- NPC memory recall

**What it does NOT do:**

- Store truth
- Enforce logic
- Replace canonical data

**📌 Rule:**

> **Qdrant never decides. It only suggests.**

---

### 4️⃣ Full-Text Search (OpenSearch) — The Index (Optional)

**What it is:**

A **precision search tool**.

Use when you want:

- Exact names
- Filters
- Keywords

**Why optional:**

Semantic search (Qdrant) handles most narrative use cases.

FTS helps when:

- Manuals are large
- You want "find rule X exactly"

**📌 Rule:**

> **Use when precision > creativity.**

---

### 5️⃣ Object Storage (MinIO) — The Raw Material Vault

**What it is:**

A **binary store** for original sources.

**What it stores:**

- PDFs
- Images
- Audio
- Maps

**Important distinction:**

**Having a PDF ≠ understanding a PDF**

The file lives here, but:

- Text is extracted → MongoDB
- Meaning is embedded → Qdrant
- Facts are promoted → Neo4j

**📌 Rule:**

> **MinIO is storage, not knowledge.**

---

## How They Work Together

### Example Flow 1: Uploading a TTRPG Manual

```
1. You upload a TTRPG manual
   ↓
2. MinIO
   → Stores the PDF (raw file)
   ↓
3. MongoDB
   → Stores extracted text chunks
   → Stores document metadata
   ↓
4. Qdrant
   → Embeds chunks for semantic recall
   ↓
5. Neo4j
   → When validated, axioms/rules/entities are promoted as nodes & relations
```

### Example Flow 2: During Roleplay

```
1. Player asks something
   ↓
2. Qdrant recalls relevant memories & docs
   ↓
3. MongoDB provides narrative context
   ↓
4. Neo4j verifies continuity
   ↓
5. Agents respond
```

### Example Flow 3: Recording a Session

```
1. Recorder processes session
   ↓
2. Story text → MongoDB
   ↓
3. Facts → Neo4j
   ↓
4. Embeddings → Qdrant
```

---

## The Promotion Path

**Critical concept: Data flows from subjective → reviewed → canonical**

```
Raw Input (MinIO)
    ↓
Narrative/Subjective (MongoDB)
    ↓
[Human or Agent Review]
    ↓
Canonical Truth (Neo4j)
    ↓
Embedded for Recall (Qdrant)
```

**This ensures:**

- Single source of truth (graph)
- No duplication of logic
- Clear authority boundaries
- Reviewable promotion process

---

## The Canonization Gate

**Core principle: Not everything becomes truth.**

MONITOR distinguishes between:
- **Narrative** (what was said, experienced, proposed) → MongoDB
- **Canon** (what is objectively true in the universe) → Neo4j

The **canonization gate** is the explicit decision point where narrative becomes canon.

### When Canonization Happens

**Primary: End of Scene**

A Scene is the natural narrative checkpoint. When a scene ends:
- All canonical deltas from the scene are batched
- Facts/Events are written to Neo4j
- Relationships and state tags are updated
- Evidence links are created

**Rationale:** Cheaper, cleaner, enforces scene as natural narrative unit.

**Optional: Mid-Scene Checkpoints (Phase 2)**

Canonization can occur mid-scene for:
- Critical state changes (character death, major discoveries)
- Very long scenes (prevent loss of progress)
- Explicit user/GM `/commit` command

**Note:** Mid-scene canonization is a Phase 2 feature. For MVP, only end-of-scene canonization is implemented. The API method would be `composite_commit_mid_scene(scene_id, proposal_ids)`.

**Never: Per-Turn**

Individual turns are narrative artifacts. They stay in MongoDB.

Turns may *propose* canonical changes, but only the scene commit writes to Neo4j.

### What Gets Canonized

**✅ Becomes Canon (→ Neo4j):**
- Facts/Events: "X happened at time T"
- Entity creation: new NPCs, locations, items
- Relationship changes: "A became ally of B"
- State transitions: alive→dead, healthy→wounded
- Temporal metadata: when it happened, duration

**❌ Stays Narrative (→ MongoDB):**
- Turn transcripts (what was said)
- GM/player notes and commentary
- Subjective interpretations and character memories
- Proposals that were rejected
- Narrative flavor that doesn't affect continuity

### The Proposal → Acceptance Flow

```
1. Narrative happens (turns, actions, resolutions)
   → MongoDB: Turn records

2. System/GM extracts potential canonical changes
   → MongoDB: ProposedChange records

3. Canonization gate evaluates proposals
   → Accept or reject based on policy

4. Accepted proposals become canon
   → Neo4j: Facts/Events + Relations + State

5. Provenance is preserved
   → Neo4j: SUPPORTED_BY edges to Sources/Turns
```

**Key insight:** MongoDB is the staging area. Neo4j is the commit target.

### Evidence and Provenance

Every canonical fact MUST have evidence.

**Source-derived facts** link to:
- Source node (the manual/document)
- Snippet ID (page/section reference)

**Play-derived facts** link to:
- Scene ID
- Turn range (e.g., turns 15-23)
- Resolution record (if rules-based)

**Why this matters:**
- **Traceability:** "Why is this true?"
- **Auditability:** "Who/what decided this?"
- **Retcon support:** "What depends on this fact?"

Without provenance, you cannot safely revise canon.

### Scene as Data Container

A Scene is not just narrative—it's a **canonization boundary**.

**Scene structure (MongoDB):**
```javascript
{
  scene_id: "uuid",
  story_id: "uuid",
  universe_id: "uuid",
  status: "active" | "completed",
  order: int,  // optional ordering within the Story
  location_ref: "entity_id",  // optional canonical location
  participating_entities: ["entity_id", ...],  // canonical entities present
  turns: [Turn],  // narrative log
  proposed_changes: [ProposedChange],  // candidates for canon
  canonical_outcomes: ["fact_id", ...],  // written at scene end
  summary: "text recap",  // for embedding/recall
  created_at: timestamp,
  completed_at: timestamp
}
```

**Turn structure (MongoDB):**
```javascript
{
  turn_id: "uuid",
  scene_id: "uuid",
  speaker: "user" | "gm" | "entity",
  entity_id: "uuid",  // required if speaker is "entity"
  text: "narrative content",
  timestamp: timestamp,
  proposed_changes: [ProposedChange],  // optional
  resolution_ref: "resolution_id"  // if dice/rules were used
}
```

**ProposedChange structure (MongoDB):**
```javascript
{
  proposal_id: "uuid",
  scene_id: "uuid",
  turn_id: "uuid",  // which turn proposed this (optional for ingest/system proposals)
  type: "fact" | "entity" | "relationship" | "state_change" | "event",
  content: {...},  // structured delta
  evidence: ["turn_id", "snippet_id", ...],
  status: "pending" | "accepted" | "rejected",
  rationale: "why accepted/rejected"
}
```

**On scene end (canonization):**
1. Review all proposed_changes
2. Accept/reject each based on policy
3. Write accepted proposals → Neo4j as Facts/Events/Relations
4. Create SUPPORTED_BY edges from Facts → Scene/Turns
5. Mark scene status = "completed"
6. Update Qdrant with scene summary + key memory entries

### Canonization Policies

Who can assert canon?

| Authority Level | Can Canonize | Examples |
|----------------|-------------|----------|
| Manual/Source | Auto (high confidence) | "Wizards can cast spells" from D&D PHB |
| GM Explicit | Always | GM declares outcome directly |
| Player Action | Via resolution | Dice/rules determine success/failure |
| System Inference | With review | Extracted from context (lower confidence) |

**Confidence & Canon Level:**

All canonical nodes carry metadata:
- `confidence`: 0.0-1.0 (how certain are we?)
- `canon_level`: See below
- `authority`: See below

**canon_level by node type:**
| Node Type | Values | Notes |
|-----------|--------|-------|
| Axiom, Entity, Fact, Event | `proposed`, `canon`, `retconned` | Standard lifecycle |
| Source | `proposed`, `canon`, `authoritative` | Sources don't get retconned; `authoritative` = official |

**authority by node type:**
| Node Type | Values | Notes |
|-----------|--------|-------|
| Fact, Event, Entity | `source`, `gm`, `player`, `system` | Full set |
| Axiom | `source`, `gm`, `system` | No `player` - world rules can't be player-created |

This supports graduated canonization and later revision.

### Retcon and Correction

Canon can be revised without data loss:

1. Mark old fact: `canon_level: "retconned"`
2. Create new fact with `replaces: "old_fact_id"`
3. Preserve both for audit trail
4. Optionally propagate updates to dependent facts

**NEVER delete canonical facts.** Mark as superseded instead.

This allows time-travel queries and "what was true when?" analysis.

---

## Why This Architecture is Correct

1. **Single source of truth** (graph)
   - Prevents contradictions
   - Enables reasoning

2. **No duplication of logic**
   - Each system has a clear purpose
   - No overlap in responsibility

3. **Clear promotion path**
   - subjective → reviewed → canonical
   - Traceable provenance

4. **Scales cognitively**
   - Matches how humans remember:
     - **Facts** (Neo4j)
     - **Stories** (MongoDB)
     - **Associations** (Qdrant)

5. **Future-proof**
   - Can add new memory types
   - Systems are loosely coupled
   - Each can be optimized independently

---

## Invariants

### Database Authority

| Database   | Authoritative For           | Never Authoritative For  |
| ---------- | --------------------------- | ------------------------ |
| Neo4j      | Truth, logic, state         | Narrative, subjective    |
| MongoDB    | Narrative, sessions, docs   | Canonical facts          |
| Qdrant     | Similarity, relevance       | Truth, decisions         |
| OpenSearch | Precision text search       | Meaning, context         |
| MinIO      | Raw file storage            | Interpreted content      |

### Cross-Database References

- All databases **may reference** Neo4j IDs (`entity_id`, `fact_id`, `universe_id`)
- Neo4j **never references** external DB primary keys
- MongoDB and Qdrant **point to** Neo4j as source of truth
- MinIO **is referenced by** MongoDB metadata

### Write Authority

| Operation                  | Primary DB | Secondary Updates        |
| -------------------------- | ---------- | ------------------------ |
| Create entity              | Neo4j      | —                        |
| Create scene transcript    | MongoDB    | → Qdrant (embed)         |
| Upload manual              | MinIO      | → MongoDB → Qdrant       |
| Promote text to fact       | Neo4j      | (from MongoDB)           |
| Store character memory     | MongoDB    | → Qdrant (embed)         |
| Update entity state        | Neo4j      | —                        |

---

## Next Steps

To operationalize this architecture, we need to define:

1. **✅ Canonization Rules** — DEFINED
   - When text becomes fact → End of scene (primary)
   - What gets canonized → Facts/Events/Relations (not turns)
   - Proposal → acceptance flow → MongoDB stages, Neo4j commits
   - See [The Canonization Gate](#the-canonization-gate) above

2. **Write Contracts**
   - Who is allowed to write to which DB
   - Validation rules per database
   - Transaction boundaries
   - API/service layer enforcement

3. **Query Patterns**
   - Standard multi-DB query compositions
   - Retrieval patterns for context assembly
   - Caching strategies
   - Performance budgets

4. **Consistency Guarantees**
   - Eventual consistency handling
   - Rollback/compensation strategies
   - Conflict resolution
   - Scene-level transaction semantics

5. **Implementation Roadmap**
   - Minimum viable schemas (Scene, Turn, ProposedChange, Fact/Event contracts)
   - Service boundaries
   - API contracts
   - Sprint 1-2 concrete tasks

---

## References

- [ONTOLOGY.md](../ontology/ONTOLOGY.md) - Canonical data model
- [ERD_DIAGRAM.md](../ontology/ERD_DIAGRAM.md) - Graph structure
- [ENTITY_TAXONOMY.md](../ontology/ENTITY_TAXONOMY.md) - Entity types
