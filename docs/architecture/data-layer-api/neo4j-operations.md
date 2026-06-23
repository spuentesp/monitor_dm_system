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

**Authority:** CanonKeeper only.

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

