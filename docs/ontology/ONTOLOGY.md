# MONITOR Ontology

*Complete data model for MONITOR: canonical graph, narrative documents, and semantic indices.*

---

## 0. Overview

MONITOR uses **three complementary data layers**:

1. **Neo4j (Graph)** - Canonical truth: what is objectively true in the universe
2. **MongoDB (Documents)** - Narrative artifacts: scenes, turns, proposals, memories
3. **Qdrant (Vectors)** - Semantic index: derived from MongoDB content

This ontology defines the **complete data model** across all three layers.

**Key principle:** Neo4j is the single source of truth. MongoDB proposes, Neo4j canonizes.

---

## 1. Layered Architecture

```
┌─────────────────────────────────────────────────────┐
│  QDRANT (Semantic Index - Derived)                  │
│  Embeddings → point to Neo4j IDs + MongoDB docs     │
└─────────────────────────────────────────────────────┘
                         ↑
                    indexes from
                         │
┌─────────────────────────────────────────────────────┐
│  MONGODB (Narrative Layer - Proposals + Artifacts)  │
│  Scenes, Turns, ProposedChanges, Memories           │
│  References canonical IDs from Neo4j                │
└─────────────────────────────────────────────────────┘
                         │
                    proposes to
                         ↓
┌─────────────────────────────────────────────────────┐
│  NEO4J (Canonical Layer - Truth)                    │
│  Universe, Entities, Facts/Events, Relations        │
│  WITH provenance, confidence, canon_level           │
└─────────────────────────────────────────────────────┘
```

---

## 2. Neo4j Canonical Layer

### 2.1 World Structure

#### Omniverse (root)
```cypher
(:Omniverse {
  id: UUID,
  name: string,
  description: string,
  created_at: timestamp
})
```

**Purpose:** Top-level container for all multiverses.
**Cardinality:** Usually 1 per MONITOR instance.

---

#### Multiverse
```cypher
(:Multiverse {
  id: UUID,
  omniverse_id: UUID,
  name: string,
  system_name: string,  // e.g., "D&D 5e", "Marvel 616"
  description: string,
  created_at: timestamp
})
```

**Purpose:** Collection of related universes (e.g., all Marvel universes).
**Relations:**
- `(:Omniverse)-[:CONTAINS]->(:Multiverse)`

---

#### Universe
```cypher
(:Universe {
  id: UUID,
  multiverse_id: UUID,
  name: string,
  description: string,
  genre: string,
  tone: string,
  tech_level: string,
  created_at: timestamp,
  canon_level: enum["proposed", "canon", "retconned"]
})
```

**Purpose:** A specific fictional universe where stories occur.
**Relations:**
- `(:Multiverse)-[:CONTAINS]->(:Universe)`

---

### 2.2 Source & Provenance

#### Source (documents/manuals)
```cypher
(:Source {
  id: UUID,
  universe_id: UUID,
  doc_id: string,  // MinIO/MongoDB reference
  title: string,
  edition: string,
  provenance: string,  // URL, ISBN, etc.
  source_type: enum["manual", "rulebook", "lore", "session"],
  created_at: timestamp,
  canon_level: enum["proposed", "canon", "authoritative"]
})
```

**Purpose:** Canonical reference to source materials.

**Note on canon_level:** Source nodes use a different enum than other canonical nodes:
- `proposed` - Source uploaded but not yet verified
- `canon` - Source accepted as valid reference
- `authoritative` - Official/primary source (highest trust level, e.g., D&D PHB)

Sources don't use `retconned` because sources themselves aren't revised—only facts derived from them can be retconned.

**Relations:**
- `(:Universe)-[:HAS_SOURCE]->(:Source)`
- `(:Fact)-[:SUPPORTED_BY]->(:Source)`
- `(:Axiom)-[:SUPPORTED_BY]->(:Source)`

---

### 2.3 Axioms & World Rules

#### Axiom (world rules)
```cypher
(:Axiom {
  id: UUID,
  universe_id: UUID,
  statement: string,  // "Magic exists", "FTL travel impossible"
  domain: string,  // "physics", "magic", "society"
  confidence: float,  // 0.0-1.0
  canon_level: enum["proposed", "canon", "retconned"],
  authority: enum["source", "gm", "system"],
  created_at: timestamp
})
```

**Purpose:** Fundamental truths about how the universe works.
**Relations:**
- `(:Universe)-[:HAS_AXIOM]->(:Axiom)`
- `(:Axiom)-[:SUPPORTED_BY]->(:Source)` or `(:Snippet)`

---

### 2.4 Entities

**Entity Hierarchy:**
```
Entity (abstract)
├─ EntityArchetype (archetypes, concepts)
└─ EntityInstance (specific instances)
```

#### EntityArchetype (archetypes)
```cypher
(:EntityArchetype {
  id: UUID,
  universe_id: UUID,
  name: string,  // "Wizard", "Orc", "Magic Sword"
  entity_type: enum["character", "faction", "location", "object", "concept", "organization"],
  description: string,
  properties: map,  // type-specific properties
  canon_level: enum["proposed", "canon", "retconned"],
  confidence: float,
  created_at: timestamp
})
```

**Purpose:** Archetypes, templates, universal concepts.
**Examples:** "Wizard" (archetype), "The Force" (concept), "Orc" (species).

---

#### EntityInstance (instances)
```cypher
(:EntityInstance {
  id: UUID,
  universe_id: UUID,
  name: string,  // "Gandalf", "The One Ring", "Mordor"
  entity_type: enum["character", "faction", "location", "object", "concept", "organization"],
  description: string,
  properties: map,  // type-specific properties
  state_tags: list,  // ["alive", "wounded", "hostile"]
  canon_level: enum["proposed", "canon", "retconned"],
  confidence: float,
  created_at: timestamp,
  updated_at: timestamp
})
```

**Purpose:** Specific instances that exist in the universe.
**Examples:** "Gandalf the Grey", "The One Ring", "Mordor".

**Relations:**
- `(:EntityInstance)-[:DERIVES_FROM]->(:EntityArchetype)` // optional
- `(:EntityInstance)-[:LOCATED_IN]->(:EntityInstance)`
- `(:EntityInstance)-[:MEMBER_OF]->(:EntityInstance)`
- `(:EntityInstance)-[:ALLY_OF]->(:EntityInstance)`
- `(:EntityInstance)-[:ENEMY_OF]->(:EntityInstance)`
- `(:EntityInstance)-[:OWNS]->(:EntityInstance)`

---

#### Entity Properties & State Tags

**Canonical Reference:** See [ENTITY_TAXONOMY.md](ENTITY_TAXONOMY.md) for complete specifications of:
- Type-specific properties for each `entity_type` (character, faction, location, object, concept, organization)
- State tag conventions and domains
- Example property values and validation rules

The `properties` map contains type-specific fields defined in ENTITY_TAXONOMY.md.

---

### 2.5 Stories & Narratives

#### Story (canonical story container)
```cypher
(:Story {
  id: UUID,
  universe_id: UUID,
  title: string,
  story_type: enum["campaign", "arc", "episode", "one_shot"],
  theme: string,
  premise: string,
  status: enum["planned", "active", "completed", "abandoned"],
  start_time_ref: timestamp,  // in-universe time
  end_time_ref: timestamp,
  created_at: timestamp,
  completed_at: timestamp
})
```

**Purpose:** Canonical record of a story/campaign.
**Relations:**
- `(:Universe)-[:HAS_STORY]->(:Story)`
- `(:Story)-[:PARENT_STORY]->(:Story)` // arcs within campaigns
- `(:Story)-[:HAS_SCENE]->(:Scene)` // optional (scenes can be MongoDB-only)

---

#### Scene (canonical, optional)
```cypher
(:Scene {
  id: UUID,
  story_id: UUID,
  title: string,
  purpose: string,
  order: int,
  time_ref: timestamp,  // when it occurred in-universe
  created_at: timestamp
})
```

**Purpose:** Canonical scene marker (optional - can be MongoDB-only).
**When to create:** Only if scene needs to be part of timeline/continuity.
**Relations:**
- `(:Story)-[:HAS_SCENE]->(:Scene)`
- `(:Scene)-[:NEXT]->(:Scene)` // ordering
- `(:EntityInstance)-[:PARTICIPATED_IN]->(:Scene)`

---

### 2.6 Facts & Events

#### Fact (objective truth)
```cypher
(:Fact {
  id: UUID,
  universe_id: UUID,
  statement: string,  // "Gandalf defeated the Balrog"
  time_ref: timestamp,  // when it became true
  duration: int,  // how long it was true (optional)
  confidence: float,  // 0.0-1.0
  canon_level: enum["proposed", "canon", "retconned"],
  authority: enum["source", "gm", "player", "system"],
  created_at: timestamp,
  replaces: UUID  // if this retcons another fact
})
```

**Purpose:** Canonical facts about the universe.
**Examples:** "PC took 5 damage", "Door is broken", "NPC is hostile".

**Relations:**
- `(:Fact)-[:INVOLVES]->(:EntityInstance)`
- `(:Fact)-[:SUPPORTED_BY]->(:Source)` or `(:Scene)` or MongoDB Turn ref (as property)
- `(:Fact)-[:REPLACES]->(:Fact)` // retcons

---

#### Event (causal moment)
```cypher
(:Event {
  id: UUID,
  scene_id: UUID,
  title: string,
  description: string,
  time_ref: timestamp,
  severity: int,  // 0-10
  confidence: float,
  canon_level: enum["proposed", "canon", "retconned"],
  authority: enum["source", "gm", "player", "system"],
  created_at: timestamp
})
```

**Purpose:** Causal moments in narrative (more specific than Fact).
**Examples:** "Orc attacks PC", "PC casts fireball", "Building collapses".

**Relations:**
- `(:Event)-[:CAUSES]->(:Event)` // causal DAG
- `(:Event)-[:INVOLVES]->(:EntityInstance)`
- `(:Event)-[:SUPPORTED_BY]->(:Source)` or `(:Scene)` or Turn ref

---

### 2.7 Plot Threads

#### PlotThread
```cypher
(:PlotThread {
  id: UUID,
  story_id: UUID,
  title: string,
  thread_type: enum["main", "side", "character", "mystery"],
  status: enum["open", "advanced", "resolved", "abandoned"],
  created_at: timestamp
})
```

**Purpose:** Cross-scene narrative threads.
**Relations:**
- `(:Story)-[:HAS_THREAD]->(:PlotThread)`
- `(:PlotThread)-[:ADVANCED_BY]->(:Scene)`
- `(:PlotThread)-[:INVOLVES]->(:EntityInstance)`

---

## 3. MongoDB Narrative Layer

MongoDB stores narrative artifacts, proposals, and working memory.

### 3.1 Scenes (narrative container)

```javascript
Collection: scenes

{
  _id: ObjectId,
  scene_id: UUID,  // canonical ID (may or may not exist in Neo4j)
  story_id: UUID,  // references Neo4j Story
  universe_id: UUID,  // references Neo4j Universe

  title: string,
  purpose: string,

  status: enum["active", "finalizing", "completed"],

  // Canonical references
  order: int,  // optional ordering within the Story
  location_ref: UUID,  // optional EntityInstance ID
  participating_entities: [UUID],  // EntityInstance IDs

  // Narrative content
  turns: [
    {
      turn_id: UUID,
      speaker: enum["user", "gm", "entity"],
      entity_id: UUID,  // if speaker is entity
      text: string,
      timestamp: ISODate,
      resolution_ref: UUID  // optional
    }
  ],

  // Canonization workflow
  proposed_changes: [UUID],  // references proposed_changes collection
  canonical_outcomes: [UUID],  // Fact/Event IDs written to Neo4j

  // Summary for retrieval
  summary: string,

  created_at: ISODate,
  updated_at: ISODate,
  completed_at: ISODate
}

Index: { story_id: 1, order: 1 }
Index: { status: 1 }
Index: { scene_id: 1 } unique
```

---

### 3.2 Turns (append-only log)

Embedded in scenes, or can be separate collection for very long scenes:

```javascript
Collection: turns (optional separate collection)

{
  _id: ObjectId,
  turn_id: UUID,
  scene_id: UUID,

  speaker: enum["user", "gm", "entity"],
  entity_id: UUID,  // if in-character
  text: string,

  proposed_changes: [UUID],  // optional proposed_changes refs
  resolution_ref: UUID,  // optional resolution record

  timestamp: ISODate
}

Index: { scene_id: 1, timestamp: 1 }
```

---

### 3.3 ProposedChange (canonization staging)

```javascript
Collection: proposed_changes

{
  _id: ObjectId,
  proposal_id: UUID,

  scene_id: UUID,
  turn_id: UUID,  // which turn proposed this (optional for ingest/system proposals)

  type: enum["fact", "entity", "relationship", "state_change", "event"],

  content: {
    // Structure depends on type
    // Examples:
    // fact: { statement: "...", entity_ids: [...] }
    // entity: { name: "...", entity_type: "...", properties: {...} }
    // relationship: { from: UUID, to: UUID, rel_type: "...", properties: {...} }
    // state_change: { entity_id: UUID, state_tag: "...", value: ... }
  },

  evidence: [
    {
      type: enum["turn", "snippet", "source", "rule"],
      ref_id: UUID
    }
  ],

  confidence: float,  // 0.0-1.0
  authority: enum["source", "gm", "player", "system"],

  status: enum["pending", "accepted", "rejected"],
  rationale: string,  // why accepted/rejected
  canonical_id: UUID,  // if accepted, the Neo4j node/edge ID

  created_at: ISODate,
  evaluated_at: ISODate
}

Index: { scene_id: 1, status: 1 }
Index: { status: 1 }
Index: { proposal_id: 1 } unique
```

---

### 3.4 Resolutions (rules/dice outcomes)

```javascript
Collection: resolutions

{
  _id: ObjectId,
  resolution_id: UUID,

  turn_id: UUID,
  scene_id: UUID,

  action: string,  // player intent
  resolution_type: enum["dice", "narrative", "deterministic"],

  mechanics: {
    // dice: { formula: "1d20+5", roll: 18, target: 15 }
    // narrative: { outcome: "success" }
  },

  success_level: enum["critical_success", "success", "partial", "failure", "critical_failure"],

  effects: [
    {
      type: string,  // "damage", "state_change", "discovery"
      description: string,
      magnitude: float
    }
  ],

  created_at: ISODate
}

Index: { scene_id: 1 }
Index: { resolution_id: 1 } unique
```

---

### 3.5 Character Memories

```javascript
Collection: character_memories

{
  _id: ObjectId,
  memory_id: UUID,

  entity_id: UUID,  // whose memory (references Neo4j EntityInstance)

  text: string,  // "I remember you saved my life"

  linked_fact_id: UUID,  // optional anchor to canonical Fact
  scene_id: UUID,  // where memory originated

  emotional_valence: float,  // -1.0 to 1.0
  importance: float,  // 0.0-1.0
  certainty: float,  // 0.0-1.0 (can misremember)

  created_at: ISODate,
  last_accessed: ISODate,
  access_count: int
}

Index: { entity_id: 1, importance: -1 }
Index: { memory_id: 1 } unique
```

---

### 3.6 Documents & Snippets (ingested sources)

```javascript
Collection: documents

{
  _id: ObjectId,
  doc_id: UUID,

  source_id: UUID,  // references Neo4j Source
  universe_id: UUID,

  minio_ref: string,  // MinIO object ID

  title: string,
  filename: string,
  file_type: string,  // "pdf", "epub", etc.

  extraction_status: enum["pending", "extracting", "completed", "failed"],

  created_at: ISODate,
  extracted_at: ISODate
}

Index: { doc_id: 1 } unique
Index: { source_id: 1 }
```

```javascript
Collection: snippets

{
  _id: ObjectId,
  snippet_id: UUID,

  doc_id: UUID,
  source_id: UUID,

  text: string,
  page: int,
  section: string,

  chunk_index: int,

  created_at: ISODate
}

Index: { doc_id: 1, chunk_index: 1 }
Index: { snippet_id: 1 } unique
```

---

### 3.7 Character Sheets

```javascript
Collection: character_sheets

{
  _id: ObjectId,
  character_sheet_id: UUID,

  entity_id: UUID,  // references Neo4j EntityInstance

  stats: map,  // system-specific stats
  resources: map,  // HP, MP, etc.

  history_log: [
    {
      timestamp: ISODate,
      change: string,
      scene_id: UUID
    }
  ],

  created_at: ISODate,
  updated_at: ISODate
}

Index: { entity_id: 1 } unique
```

---

### 3.8 Story Outlines (narrative planning)

```javascript
Collection: story_outlines

{
  _id: ObjectId,
  story_id: UUID,  // references Neo4j Story

  theme: string,
  premise: string,
  constraints: [string],

  beats: [
    {
      title: string,
      description: string,
      order: int
    }
  ],

  open_threads: [string],

  created_at: ISODate,
  updated_at: ISODate
}

Index: { story_id: 1 } unique
```

---

## 4. Qdrant Semantic Index Layer

Qdrant stores embeddings with metadata pointing to canonical sources.

### 4.1 Vector Collections

**Collection: scene_chunks**
```json
{
  "id": "uuid",
  "vector": [float],
  "payload": {
    "scene_id": "uuid",
    "story_id": "uuid",
    "universe_id": "uuid",
    "text": "summary or turn text",
    "type": "scene_summary | turn",
    "timestamp": "iso8601"
  }
}
```

**Collection: memory_chunks**
```json
{
  "id": "uuid",
  "vector": [float],
  "payload": {
    "memory_id": "uuid",
    "entity_id": "uuid",
    "text": "memory text",
    "importance": float,
    "timestamp": "iso8601"
  }
}
```

**Collection: snippet_chunks**
```json
{
  "id": "uuid",
  "vector": [float],
  "payload": {
    "snippet_id": "uuid",
    "doc_id": "uuid",
    "source_id": "uuid",
    "universe_id": "uuid",
    "text": "snippet text",
    "page": int,
    "section": "string"
  }
}
```

**Critical:** Qdrant is **never authoritative**. All IDs point to Neo4j or MongoDB.

---

## 5. Cross-Layer Invariants

### 5.1 Reference Rules

| Layer | Can Reference | Cannot Reference |
|-------|--------------|------------------|
| Neo4j | Neo4j nodes only | MongoDB _id, Qdrant IDs |
| MongoDB | Neo4j UUIDs (as properties) | Neo4j internal IDs |
| Qdrant | Neo4j UUIDs + MongoDB UUIDs | - |

### 5.2 Write Authority

| Entity Type | Primary Store | Proposal Store | Who Writes |
|------------|--------------|----------------|-----------|
| Universe | Neo4j | MongoDB (proposals) | CanonKeeper |
| Fact/Event | Neo4j | MongoDB (ProposedChange) | CanonKeeper |
| Entity | Neo4j | MongoDB (ProposedChange) | CanonKeeper |
| Scene | MongoDB | - | Orchestrator |
| Turn | MongoDB | - | Narrator |
| ProposedChange | MongoDB | - | Resolver, Narrator |
| Memory | MongoDB | - | MemoryManager |
| Embedding | Qdrant | - | Indexer |

### 5.3 Canonization Flow

```
Narrative → ProposedChange → CanonKeeper → Neo4j
(MongoDB)   (MongoDB)         (evaluates)    (commits)
```

### 5.4 Evidence Chain

Every canonical node in Neo4j MUST link to evidence:
- `(:Fact)-[:SUPPORTED_BY]->(:Source)` or
- `(:Fact {evidence_refs: ["scene:uuid", "turn:uuid"]})` stored as property

---

## 6. Use Case Mapping

### P-1: Start New Story
**Data flow:**
1. MongoDB: create story_outline
2. Neo4j: create Story node
3. MongoDB: create first Scene (status=active)
4. Neo4j: optionally create Scene node (if canonical)

### P-3: User Turn in Active Scene
**Data flow:**
1. MongoDB: append Turn to scene.turns
2. MongoDB: optionally create ProposedChange records
3. No Neo4j writes (deferred to canonization)

### P-8: End Scene (Canonization)
**Data flow:**
1. CanonKeeper: evaluate ProposedChanges
2. Neo4j: write accepted Facts/Events/Relations
3. Neo4j: create SUPPORTED_BY edges
4. MongoDB: mark scene.status = "completed"
5. MongoDB: update proposal.status = "accepted"/"rejected"
6. Qdrant: embed scene summary + memories

### I-1: Upload Document
**Data flow:**
1. MinIO: store document
2. MongoDB: create document record
3. MongoDB: create snippet records
4. Qdrant: embed snippets
5. MongoDB: create ProposedChanges (axioms/entities)
6. User review → CanonKeeper → Neo4j (canonize accepted)

### Q-1: Semantic Search
**Data flow:**
1. Qdrant: semantic search → candidate IDs
2. Neo4j: fetch canonical nodes by ID
3. MongoDB: fetch narrative details (if needed)
4. Present results

---

## 7. Schema Evolution

### v2.0 Breaking Changes from v1.0

1. **Separated Neo4j from MongoDB** - v1.0 assumed single graph model
2. **Added canonization metadata** - confidence, canon_level, authority
3. **Added Source nodes** - provenance tracking
4. **Split Entity** → EntityArchetype + EntityInstance
5. **Added Fact** (distinct from Event)
6. **Added ProposedChange** flow (staging before canon)
7. **Scene can be Neo4j or MongoDB-only** - not always canonical
8. **Added evidence/provenance** - SUPPORTED_BY relations

### Future v2.x Extensions (non-breaking)

- Add new entity_types
- Add new relationship types
- Add properties to existing nodes (backward compatible)

### v3.0 Considerations (breaking)

- Change canonization_level enum values
- Restructure Entity hierarchy
- Change primary keys

---

## 8. Implementation Checklist

To implement this ontology:

- [ ] Neo4j schema constraints (UUIDs, required properties)
- [ ] MongoDB schema validation (JSON Schema)
- [ ] Qdrant collection creation with proper indices
- [ ] Cross-reference validation (ensure UUIDs exist)
- [ ] Migration scripts from v1.0 (if applicable)
- [ ] API contracts per layer
- [ ] Agent read/write authority enforcement

---

## References

- [DATABASE_INTEGRATION.md](../architecture/DATABASE_INTEGRATION.md) - Data layer architecture
- [CONVERSATIONAL_LOOPS.md](../architecture/CONVERSATIONAL_LOOPS.md) - Loop state machines
- [AGENT_ORCHESTRATION.md](../architecture/AGENT_ORCHESTRATION.md) - Agent roles and coordination
