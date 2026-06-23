# Query-Aware Traversal Implementation Plan

> Purpose: add a retrieval mode that uses MONITOR's existing typed entities and typed relationships to select the right graph neighborhood for a query before summarization or narration.
>
> **Implementation status (April 2026):** Ready for implementation after source-scope routing begins. The repo already has the typed entities, typed relationships, and retrieval orchestration entry point needed for this work, but the traversal-mask and ranked-path layer itself is still not implemented.
>
> Canonical references:
> - `SYSTEM.md`
> - `ARCHITECTURE.md`
> - `docs/architecture/AGENT_ORCHESTRATION.md`
> - `packages/agents/src/monitor_agents/context_assembly.py`
> - `packages/data-layer/src/monitor_data/schemas/entities.py`
> - `packages/data-layer/src/monitor_data/schemas/relationships.py`
>
> Source inspiration:
> - Kwun Hang Lau et al., *Breaking the Static Graph: Context-Aware Traversal for Robust Retrieval-Augmented Generation* (CatRAG), arXiv:2602.01965, 2026. https://arxiv.org/abs/2602.01965
>
> See also:
> - `docs/architecture/futures/HYBRID_MINDSCAPE_AND_TRAVERSAL_PLAN.md` for the combined rollout with mindscape-aware ingestion and source-scope routing.
> - `docs/architecture/futures/INGESTION_FIRST_CONTEXTUAL_RETRIEVAL_PLAN.md` for the recommended execution order that starts with ingestion benefits.

---

## Why this doc exists

MONITOR already has the right primitives for query-aware traversal:

- typed entities in Neo4j
- typed relationships in Neo4j
- vector recall in Qdrant
- a retrieval orchestration point in `ContextAssembly`

The current retrieval path is strong for broad relevance, but it is still mostly **query → search → summarize**. For scene play, NPC reasoning, and lore recall, that is not always enough. We want **query → intent mask → typed graph traversal → evidence selection → summarize**.

The key observation is simple:

> if the query intent can be mapped to a small set of relation families and target node types, then most of the retrieval problem is deterministic filtering plus weighted ranking.

This lets MONITOR stay grounded in canon while reducing drift into generic lore.

---

## Current repo surface

### Already present

| Capability | Current location | Notes |
|---|---|---|
| Turn-time retrieval orchestration | `packages/agents/src/monitor_agents/context_assembly.py` | Best place to add query mask construction and graph-aware reranking |
| Typed relationship enum | `packages/data-layer/src/monitor_data/schemas/relationships.py` | Already exposes structural and emotional relation families |
| Typed entities | `packages/data-layer/src/monitor_data/schemas/entities.py` | Already exposes `entity_type`, `sub_type`, `state_tags`, and canon metadata |
| Neo4j read path | `packages/data-layer/src/monitor_data/db/neo4j.py` | Suitable for bounded neighborhood and path queries |
| Qdrant semantic recall | `packages/data-layer/src/monitor_data/tools/qdrant_tools.py` | Should remain evidence support, not sole ranking signal |

### Architectural fit

This work is layer-safe:

- **data-layer** adds read-only graph query helpers and schemas
- **agents** compute the query mask and rank candidate paths
- **cli / ui** remain consumers only
- **CanonKeeper** remains the only writer to durable graph canon

No new write authority is needed for this phase.

---

## Design goal

Given a player action or GM query, retrieve **the most relevant evidence path**, not just semantically similar snippets.

Examples:

- “Who can get us into the Black Archive?” → social + access + location pathing
- “Why does the Baron hate us?” → causal + event + emotional pathing
- “Where is the ritual key now?” → ownership + containment + location pathing
- “What rule applies if I try to bargain with this ghost?” → rules + system + condition pathing

---

## Core model

### 1. Query mask

For each query, construct a lightweight `TraversalQueryMask` in the agents layer.

Recommended fields:

| Field | Purpose |
|---|---|
| `intent_family` | high-level query class (`social`, `spatial`, `causal`, `rules`, `canon`, `timeline`) |
| `seed_entities` | entities explicitly named or inferred from scene context |
| `target_entity_types` | preferred destination node families |
| `preferred_rel_types` | relation types to amplify |
| `allowed_rel_types` | safe traversal envelope |
| `state_tag_filters` | optional state constraints (`hostile`, `friendly`, `hidden`, etc.) |
| `canon_floor` | minimum canon confidence for evidence |
| `hop_limit` | usually 1–3 for live play |
| `universe_id` / `story_id` / `scene_id` | context scoping |
| `time_bias` | whether recent events should be favored |

This should be an internal planning object, not a new user-facing abstraction.

### 2. Weighted traversal score

Use a simple scoring function first. Avoid overcomplicating the first rollout.

$$
score(path, q)=base(path)\times rel\_match(q)\times type\_match(q)\times scene\_relevance(q)\times canon\_confidence\times recency
$$

Where:

- `base(path)` comes from relation confidence / edge properties
- `rel_match(q)` strongly boosts preferred relation types
- `type_match(q)` boosts the right destination node families
- `scene_relevance(q)` favors currently active entities, factions, threats, and locations
- `canon_confidence` suppresses low-confidence or rumor-heavy evidence when the query needs truth
- `recency` helps with consequence tracing and short-term memory

### 3. Path-first retrieval

Return ranked **paths plus supporting passages**, not only a flat list of nodes.

Desired output shape:

```json
{
  "query_mask": {...},
  "ranked_paths": [
    {
      "score": 0.91,
      "nodes": ["party", "smuggler", "archivist", "black archive"],
      "edges": ["KNOWS", "OWES", "LOCATED_IN"],
      "why": "Best social-access path for the query"
    }
  ],
  "supporting_snippets": [...],
  "summary": "..."
}
```

---

## Intent bundles

The first implementation should be mostly deterministic.

| Intent family | Typical cues | Preferred relation types | Preferred target types |
|---|---|---|---|
| `social` | who knows, who can help, convince, ally, betray | `KNOWS`, `ALLIED_WITH`, `WORKS_FOR`, `TRUSTS`, `DISTRUSTS`, `INDEBTED_TO`, `HOSTILE_TO` | character, faction, party |
| `spatial` | where, located, hidden, inside, route | `LOCATED_IN`, `CONTAINS`, `OWNS`, `CONTROLLED_BY`, `CONTROLS` | place, object, faction |
| `causal` | why, because, consequence, triggered | `PARTICIPATES_IN`, `RELATED_TO`, event links, source-supported facts | event, fact, plot thread |
| `rules` | can I, how does this work, what happens if | `INSTANCE_OF`, `SUBTYPE_OF`, system/profile links, tagged rules evidence | rule, move, mechanic, condition |
| `canon` | is it true, confirmed, what do we know | source-backed fact relations + high-confidence evidence | fact, event, source passage |
| `timeline` | when, last time, before, after | event participation and recency-biased edges | event, scene, story element |

This table is the main reason the feature is practical: MONITOR already has typed graph structure, so we can route by relation family rather than asking the model to rediscover the schema each turn.

---

## Concrete code map

### Layer ownership

| Concern | Put code in | Do not put it in |
|---|---|---|
| Traversal request/response models | `packages/data-layer/src/monitor_data/schemas/` | CLI commands |
| Neo4j bounded read helpers | `packages/data-layer/src/monitor_data/tools/neo4j_tools/` | agents or UI code |
| Intent classification and traversal mask building | new `packages/agents/src/monitor_agents/utils/query_traversal.py` | data-layer |
| Retrieval orchestration and fallback behavior | `packages/agents/src/monitor_agents/context_assembly.py` | random prompt files |

### Symbols to add

#### Agents layer
Create `packages/agents/src/monitor_agents/utils/query_traversal.py` with:
- `TraversalQueryMask`
- `TraversalCandidatePath`
- `INTENT_RELATION_BUNDLES`
- `infer_intent_family()`
- `build_query_mask()`
- `score_candidate_path()`

#### Data-layer
Add read-only query helpers in a new or adjacent Neo4j tools module:
- `neo4j_get_entity_neighborhood()`
- `neo4j_find_ranked_paths()`
- `neo4j_get_scene_relevant_entities()`

Keep them bounded, read-only, and parameterized by relation types and hop limits.

### Concrete file edits

1. `packages/agents/src/monitor_agents/context_assembly.py`
   - call the traversal helper to build a query mask
   - request bounded graph candidates from the data-layer
   - rerank Qdrant evidence using graph path quality plus scene relevance

2. `packages/data-layer/src/monitor_data/tools/neo4j_tools/`
   - add a dedicated retrieval-oriented read module rather than expanding unrelated relationship CRUD code

3. `packages/data-layer/src/monitor_data/db/neo4j.py`
   - reuse the existing read execution path; do not add agent-specific logic here

### Test placement

Add or extend tests in:
- `packages/agents/tests/test_context_assembly.py`
- `packages/data-layer/tests/test_tools/test_relationship_tools.py`
- `packages/data-layer/tests/test_tools/test_topology.py`

### SOLID / DRY guardrails

- do not embed traversal heuristics directly into large `ContextAssembly` methods; keep them in a focused helper module
- keep graph read tools separate from relationship CRUD to preserve SRP
- represent intent-to-relation rules as a mapping table instead of repeated conditional chains across agents

---

## Recommended execution order

Build this only after the source-scope routing helper exists.

1. add the intent-to-relation mapping table in the agents layer
2. expose bounded read-only Neo4j path helpers
3. integrate graph-path scoring into ContextAssembly
4. combine those ranked paths with snippet evidence and scene relevance

## Concrete implementation phases

## Recommended execution order

Build this only after the source-scope routing helper exists.

1. add the intent-to-relation mapping table in the agents layer
2. expose bounded read-only Neo4j path helpers
3. integrate graph-path scoring into ContextAssembly
4. combine those ranked paths with snippet evidence and scene relevance

### Phase 0 — Retrieval contract and schema audit

**Goal:** normalize the relation and type bundles used for traversal.

### Files
- `packages/data-layer/src/monitor_data/schemas/relationships.py`
- `packages/data-layer/src/monitor_data/schemas/entities.py`
- new helper module under `packages/agents/src/monitor_agents/utils/`

### Tasks
1. Audit existing `RelationshipType` and `EmotionalRelationType` coverage.
2. Group them into internal traversal families:
   - social
   - spatial
   - causal
   - taxonomy
   - control / power
   - evidence / canon
3. Add an agents-layer mapping table from query intent → preferred relation bundles and target entity types.
4. Keep the mapping config-driven and testable.

### Acceptance criteria
- a single query can be deterministically mapped to a traversal family bundle without LLM involvement for common cases
- the mapping table is documented and covered by tests

---

### Phase 1 — Query mask generation in `ContextAssembly`

**Goal:** make turn retrieval graph-aware without changing the user surface.

### Files
- `packages/agents/src/monitor_agents/context_assembly.py`
- new file: `packages/agents/src/monitor_agents/utils/query_traversal.py`
- optional prompt refinement in `packages/agents/src/monitor_agents/prompts/context_assembly.py`

### Tasks
1. Add a `TraversalQueryMask` model or lightweight typed dict.
2. Extract:
   - named entities from the turn
   - active scene entities
   - likely intent family
3. Build a ranked seed set using:
   - explicit mentions
   - scene participants
   - current plot hooks
4. Route simple queries through deterministic rules first.
5. Only use DSPy / LLM assistance when the intent is ambiguous.

### Acceptance criteria
- `retrieve_turn_context()` can produce a query mask for common play queries
- ambiguous cases fall back to the current semantic retrieval behavior instead of failing

---

### Phase 2 — Read-only graph traversal helpers in the data-layer

**Goal:** expose the minimum bounded graph queries needed for live play.

### Files
- new read helpers under `packages/data-layer/src/monitor_data/tools/neo4j_tools/`
- `packages/data-layer/src/monitor_data/db/neo4j.py`
- supporting schemas under `packages/data-layer/src/monitor_data/schemas/`

### Recommended read operations
1. `neo4j_get_entity_neighborhood`
   - bounded 1–2 hop read
   - filtered by relation types and entity types
2. `neo4j_find_ranked_paths`
   - bounded path search from seed entities to preferred targets
   - returns nodes, edges, and basic path metadata
3. `neo4j_get_scene_relevant_entities`
   - fast scene-local seed extraction
4. optional later: `neo4j_get_evidence_paths_for_fact`

### Guardrails
- **read only** in this phase
- bounded hops only
- no open-ended graph walks during live play
- always scoped by `universe_id`, and preferably `story_id` / `scene_id` when available

### Acceptance criteria
- graph retrieval returns small, bounded candidate paths quickly enough for turn-time use
- no layer boundary violations are introduced

---

### Phase 3 — Hybrid ranking: graph first, vector evidence second

**Goal:** combine typed path quality with Qdrant evidence recall.

### Files
- `packages/agents/src/monitor_agents/context_assembly.py`
- `packages/data-layer/src/monitor_data/tools/qdrant_tools.py` (likely unchanged API; may need improved filters only)

### Tasks
1. Use the query mask to get candidate paths from Neo4j.
2. Convert the top path nodes and relation labels into better Qdrant retrieval queries.
3. Rerank memory/snippet evidence using:
   - path score
   - snippet score
   - scene relevance
   - canon confidence
4. Feed the top evidence bundle into the existing summarizer.

### Acceptance criteria
- retrieval summaries cite more specific, scene-relevant evidence paths
- broad semantic drift is reduced on targeted queries

---

### Phase 4 — Runtime consumers

**Goal:** let the rest of the system benefit without changing write authority.

### Consumers
- `Narrator` gets better grounded evidence chains
- `NPCVoice` gets sharper social and leverage context
- `Resolver` can pull condition- or rule-specific context more directly
- later, `WorldArchitect` can use traversal to discover unresolved structural gaps

### Acceptance criteria
- social queries pull social paths
- location queries pull location paths
- rules queries pull rules evidence instead of unrelated lore

---

### Phase 5 — Evaluation and observability

**Goal:** verify that this improves grounded play rather than merely changing ranking behavior.

### Metrics
Track:

- path relevance at top-3
- evidence-chain completeness
- scene relevance of returned snippets
- reduction in generic high-degree entity retrieval
- latency per turn

### Suggested evaluation set
Create a small internal benchmark from MONITOR use cases:

- NPC leverage questions
- item location questions
- faction allegiance questions
- unresolved plot thread questions
- rules lookup questions

This should be a repo-local eval, not just a generic RAG benchmark.

---

## Minimal viable rollout

The first shipping version should be deliberately small:

1. deterministic intent classifier
2. relation-family mapping table
3. bounded 1–2 hop neighborhood query
4. simple weighted reranker
5. fallback to current retrieval if confidence is low

This will likely deliver most of the value with modest implementation risk.

---

## Non-goals for the first pass

Do **not** start with:

- open-ended graph agents that wander until they “feel done”
- expensive per-edge LLM scoring at runtime
- auto-canonization changes
- global graph rewrites
- a new storage system

The design should stay conservative and incremental.

---

## Recommended sequence of execution

1. implement the intent → relation/type mapping table
2. add bounded graph neighborhood/path read helpers
3. integrate the query mask in `ContextAssembly`
4. add reranking and fallback behavior
5. evaluate on real MONITOR play traces

This order gives a measurable result quickly and keeps the changes isolated to the right layers.

---

## Expected outcome

If implemented conservatively, MONITOR should become better at:

- following the right social chain
- tracking where things are and who controls them
- grounding “why” questions in actual event structure
- retrieving rules context without lore drift
- staying focused on the current scene instead of the whole world graph

That is the practical payoff of query-aware traversal for this codebase.