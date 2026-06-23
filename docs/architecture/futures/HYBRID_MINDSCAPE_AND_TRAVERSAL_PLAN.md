# Hybrid Mindscape + Situated Retrieval + Query-Aware Traversal Plan

> Purpose: combine global document awareness during ingestion, situated short-span retrieval, and query-aware graph traversal during runtime retrieval, so MONITOR can answer long-context and conversational questions with both broad semantic grounding and precise path selection.
>
> **Implementation status (April 2026):**
> - **Step 1 (Mindscape-aware ingestion):** 🟡 Partially implemented. Section summaries, source mindscape synthesis, structured source profiles, and chunk summaries are generated and persisted on KnowledgePacks; Forge review and approval surfaces now exist; and the summary artifacts are projected into Qdrant. Remaining gaps are stronger runtime routing and situated retrieval from those artifacts.
> - **Step 2 (Situated conversational retrieval):** ⚪ Not started.
> - **Step 3 (Query-aware traversal):** ⚪ Not started.
>
> Canonical references:
> - `SYSTEM.md`
> - `ARCHITECTURE.md`
> - `docs/architecture/AGENT_ORCHESTRATION.md`
> - `docs/architecture/PROFILE_DRIVEN_EXTRACTION_AND_WORLD_BUILDING_PLAN.md`
> - `docs/architecture/futures/MINDSCAPE_AWARE_INGESTION_IMPLEMENTATION_PLAN.md`
> - `docs/architecture/futures/SITUATED_CONVERSATIONAL_RETRIEVAL_IMPLEMENTATION_PLAN.md`
> - `docs/architecture/futures/QUERY_AWARE_TRAVERSAL_IMPLEMENTATION_PLAN.md`
> - `docs/architecture/futures/INGESTION_FIRST_CONTEXTUAL_RETRIEVAL_PLAN.md`
>
> Source inspirations:
> - Kwun Hang Lau et al., *Breaking the Static Graph: Context-Aware Traversal for Robust Retrieval-Augmented Generation* (CatRAG), arXiv:2602.01965, 2026. https://arxiv.org/abs/2602.01965
> - Yuqing Li et al., *Mindscape-Aware Retrieval Augmented Generation for Improved Long Context Understanding* (MiA-RAG), arXiv:2512.17220, 2025. https://arxiv.org/abs/2512.17220
> - Junjie Wu et al., *SitEmb-v1.5: Improved Context-Aware Dense Retrieval for Semantic Association and Long Story Comprehension*, arXiv:2508.01959, 2025. https://arxiv.org/abs/2508.01959

---

## Recommendation

A **joint plan is stronger** than treating the three papers separately.

They solve adjacent parts of the same MONITOR problem:

- **MiA-RAG** improves long-text ingestion and retrieval by adding a persistent, document-level semantic frame.
- **SitEmb** improves local retrieval by representing short chunks or turns with awareness of their nearby context.
- **CatRAG** improves runtime retrieval by steering graph traversal toward the right evidence path for the active query.

### Separate implementation tracks

Use these detail pages for the concrete work:

- `docs/architecture/futures/MINDSCAPE_AWARE_INGESTION_IMPLEMENTATION_PLAN.md`
- `docs/architecture/futures/SITUATED_CONVERSATIONAL_RETRIEVAL_IMPLEMENTATION_PLAN.md`
- `docs/architecture/futures/QUERY_AWARE_TRAVERSAL_IMPLEMENTATION_PLAN.md`

For MONITOR, the best next sequence is:

1. finish the remaining ingestion substrate gaps
2. generate situated chunk and turn representations
3. use the persisted mindscape and profile artifacts to scope search at query time
4. run query-aware traversal inside the scoped graph neighborhood
5. return grounded evidence bundles for narration, rules, or play assistance

---

## Problem this solves

MONITOR needs to answer questions that are both:

- **globally scoped** across long rulebooks, lore books, notes, and session archives
- **locally precise** about the current scene, actor, relationship, rule, or consequence chain

A chunk-only approach misses the global frame.
A graph-only approach can drift without document guidance.

The combined approach addresses all three layers:

- the **mindscape** tells the system what kind of document or source region matters
- the **situated evidence layer** preserves the meaning of short chunks and turns inside their local neighborhood
- the **traversal mask** tells the system which typed paths matter for the current question

---

## Concrete execution sequence

### Step 1 — Mindscape-aware ingestion

**Code here:**
- `packages/agents/src/monitor_agents/analyzer.py`
- `packages/agents/src/monitor_agents/prompts/analyzer.py`
- `packages/agents/src/monitor_agents/utils/analyzer_support.py`
- `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`

**What to code:**
- chunk, section, and source-level summary artifacts
- persistence of those artifacts on the knowledge pack
- shared helper functions for grouping, trimming, and summary preparation

### Step 2 — Situated conversational retrieval

**Code here:**
- `packages/agents/src/monitor_agents/context_assembly.py`
- `packages/agents/src/monitor_agents/npc_voice.py`
- `packages/agents/src/monitor_agents/loops/conversation_loop.py`
- new `packages/agents/src/monitor_agents/utils/conversation_retrieval.py`
- optional schema enrichments in `packages/data-layer/src/monitor_data/schemas/conversations.py`

**What to code:**
- turn-window metadata
- short local context summaries for dialogue retrieval
- scene / speaker-aware reranking for transcript and clue recall

### Step 3 — Query-aware traversal

**Code here:**
- `packages/agents/src/monitor_agents/context_assembly.py`
- new `packages/agents/src/monitor_agents/utils/query_traversal.py`
- new Neo4j read helpers under `packages/data-layer/src/monitor_data/tools/neo4j_tools/`

**What to code:**
- traversal masks
- bounded neighborhood and path queries
- hybrid reranking using source scope, situated evidence, and graph-path relevance

### Architectural rules to preserve

- `cli` stays a consumer only
- `agents` own orchestration and decision logic
- `data-layer` owns schemas and read/write tools only
- Neo4j writes still flow only through CanonKeeper
- shared heuristics belong in helper modules, not duplicated inline across agents

---

## Combined architecture

### Ingestion-time layer: build the mindscape

For each ingested source, MONITOR should produce and persist:

1. **chunk summaries**
2. **section summaries**
3. **one source-level global summary**
4. **a structured source profile**
5. **entity and relationship extraction linked back to those summaries**

This creates a hierarchy:

```text
Source
 ├─ global summary (mindscape)
 ├─ section summaries
 ├─ chunks
 ├─ entities
 └─ relationships
```

### Query-time layer: use the mindscape to focus situated retrieval and traversal

At runtime, retrieval should become:

```text
query
  -> identify likely source / section scope using mindscape + profile
  -> retrieve situated chunks or turns from the relevant local neighborhoods
  -> build traversal query mask using intent + scene context
  -> run bounded graph traversal in the scoped neighborhood
  -> pull supporting vector evidence from the winning nodes, sections, and turns
  -> summarize for downstream agents
```

This gives MONITOR **global relevance**, **local coherence**, and **path precision**.

---

## MONITOR-specific design

### 1. Source mindscape artifacts

These should live beside the existing source-profile work.

Recommended artifacts per source:

| Artifact | Purpose | Best home |
|---|---|---|
| Global summary | document-level semantic frame | knowledge pack / Mongo payload |
| Section summaries | mid-level routing and retrieval | knowledge pack metadata + Qdrant |
| Chunk summaries | denser semantic anchors | Qdrant payload |
| Topic / taxonomy hints | improve routing and query expansion | embedded source profile |
| Entity-to-section links | connect graph to textual evidence | Neo4j + payload refs |

### 2. Retrieval pipeline

At query time, the runtime should compute two things:

#### A. Mindscape scope
A lightweight scope object derived from:
- source profile
- global summary
- section summaries
- current universe / story / scene context

This answers:
- which source or pack is most relevant?
- which section families matter?
- which vocabulary or taxonomy should be activated?

#### B. Traversal mask
A lightweight pathing object derived from:
- user query
- active scene entities
- intent family
- target types
- preferred relation bundles

This answers:
- which graph paths should be explored?
- which node types are likely destinations?
- which edges should be boosted or suppressed?

---

## Retrieval equation

A simple first-pass ranking function is enough:

$$
final\_score = source\_scope \times path\_score \times snippet\_score \times scene\_relevance \times canon\_confidence
$$

Where:

- `source_scope` comes from the mindscape and source profile
- `path_score` comes from query-aware graph traversal
- `snippet_score` comes from vector similarity / reranking
- `scene_relevance` keeps the answer focused on the active play state
- `canon_confidence` suppresses unsupported or low-confidence evidence

---

## Why the combined plan is better

### What MiA-RAG contributes

- better long-text ingestion
- better source-level and section-level framing
- stronger retrieval for ambiguous questions
- less confusion when multiple topics coexist in one book or corpus

### What SitEmb contributes

- better retrieval of short evidence spans whose meaning depends on nearby context
- stronger transcript-turn and conversation recall
- better clue and callback recovery from scenes and recaps
- improved conversational grounding without needing huge chunks

### What CatRAG contributes

- better multi-hop retrieval
- reduced graph drift into hub entities
- better social, causal, and spatial pathing
- more complete reasoning chains

### What the combination gives MONITOR

- better retrieval from long sourcebooks and campaign archives
- better focus on the right part of a world or system
- better recall of what characters said, promised, implied, or discovered
- better answers to “who / where / why / what rule applies” questions
- better grounding for Narrator, NPCVoice, Resolver, and World Architect

---

## Implementation plan

### Phase A — Finish and reuse the existing source-profile foundation

**Goal:** avoid duplicate work by building on the profile-driven extraction foundation already present in the repo.

### Tasks
1. Treat the existing source profile as the canonical home for mindscape metadata.
2. Add a dedicated global summary field if not already represented cleanly.
3. Ensure section-level summaries are persisted with source references and confidence metadata.
4. Thread these artifacts into pack retrieval and agent context assembly.

### Acceptance criteria
- every significant ingested source has a reusable global summary and section summary layer
- runtime agents can request those artifacts without re-summarizing the source

---

### Phase B — Add hierarchical summary generation to ingestion

**Goal:** make long-text ingestion explicitly mindscape-aware.

### Files
- `packages/agents/src/monitor_agents/indexer.py`
- `packages/agents/src/monitor_agents/analyzer.py`
- `packages/agents/src/monitor_agents/prompts/analyzer.py`
- related knowledge-pack schemas in the data-layer

### Tasks
1. generate concise chunk summaries during ingestion
2. fold chunk summaries into section summaries
3. fold section summaries into a source-level mindscape
4. store all three levels as reusable retrieval artifacts
5. embed section summaries and global summaries into Qdrant for routing

### Acceptance criteria
- a long source can be retrieved by chunk, section, or source-summary route
- the ingestion pipeline produces stable mindscape artifacts for later reuse

---

### Phase C — Add source-scope routing before graph traversal

**Goal:** use the mindscape to narrow the search space before path search.

### Files
- `packages/agents/src/monitor_agents/context_assembly.py`
- new helper under `packages/agents/src/monitor_agents/utils/`

### Tasks
1. compute a `SourceScope` object for each runtime query
2. rank likely packs, sources, and section families
3. expand the query with source vocabulary and taxonomy hints
4. pass the scoped source identifiers into graph and Qdrant retrieval

### Acceptance criteria
- the system can distinguish between multiple similar sources or lore domains more reliably
- irrelevant packs or sections are filtered out earlier in the process

---

### Phase D — Add bounded query-aware traversal inside the scoped source set

**Goal:** combine the current traversal work with the new source scope.

### Files
- `packages/agents/src/monitor_agents/context_assembly.py`
- new read helpers in `packages/data-layer/src/monitor_data/tools/neo4j_tools/`
- helper logic in `packages/agents/src/monitor_agents/utils/query_traversal.py`

### Tasks
1. build the traversal mask from the user query and scene context
2. use the source scope to constrain graph traversal candidates
3. run bounded 1–3 hop pathing against preferred relation families
4. rerank evidence based on both scope and path quality
5. return path-aware evidence bundles to downstream agents

### Acceptance criteria
- the system pulls the right evidence path from the right source region
- long-context questions no longer degrade into broad but shallow recall

---

### Phase E — Runtime consumers

**Goal:** let the main play surfaces exploit the improved retrieval model.

### Consumers
- `ContextAssembly` becomes scope-aware and traversal-aware
- `Narrator` receives stronger evidence bundles with global framing
- `NPCVoice` gains better social and memory context
- `Resolver` gets more direct rules and condition retrieval
- `WorldArchitect` gains better overview and gap detection across source material

---

### Phase F — Evaluation

**Goal:** measure whether the combined approach improves real MONITOR tasks.

### Bench categories
- long rulebook rule lookup
- faction / relationship tracing
- item location and control tracing
- world-history causality questions
- campaign recap and unresolved-thread retrieval
- NPC motive and leverage retrieval

### Success signals
- fewer irrelevant generic snippets
- better section targeting in long books
- better multi-hop path completeness
- lower confusion between similar entities or systems
- higher quality grounded answers in play and assistant modes

---

## Suggested execution order

This should be implemented in this order:

1. reuse and stabilize the existing profile-driven ingestion layer
2. add hierarchical summary artifacts for long sources
3. add situated chunk and turn retrieval for transcript and snippet recall
4. add source-scope routing in runtime retrieval
5. integrate query-aware graph traversal inside that scoped search space
6. evaluate on real MONITOR play and ingestion cases

This is lower-risk than building advanced graph steering first and trying to retrofit global context later.

---

## Decision

For MONITOR, **the best next plan is a combined one**.

If forced to choose order:

- do **mindscape-aware ingestion and source-scope routing first**
- then do **query-aware traversal inside that scoped retrieval space**

That sequence should produce the most practical benefit for long books, deep lore, and multi-hop in-play queries.