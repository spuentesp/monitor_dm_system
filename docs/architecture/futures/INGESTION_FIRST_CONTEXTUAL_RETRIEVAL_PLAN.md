# Ingestion-First Contextual Retrieval Plan

> Purpose: combine long-text mindscape construction, situated conversational retrieval, and query-aware graph traversal into one rollout order that maximizes immediate value for MONITOR ingestion.
>
> **Implementation status (April 2026):**
> - **Phase 1 (Improve ingestion artifacts):** 🟡 Partially implemented via the ingestion revamp. Section summaries, source mindscape, structured source profiles, and chunk summaries are now generated and persisted on KnowledgePacks, and the Forge review surface can inspect and approve them. Those artifacts are also projected into Qdrant as retrieval signals. Remaining gaps are stronger runtime routing and richer situated retrieval use of the persisted summaries.
> - **Phase 2 (Situated retrieval for chunks/turns):** ⚪ Not started.
> - **Phase 3 (Source-scope routing):** ⚪ Not started.
> - **Phase 4 (Query-aware traversal):** ⚪ Not started.
> - **Phase 5 (Conversational specialization):** ⚪ Not started.
>
> Canonical references:
> - `SYSTEM.md`
> - `ARCHITECTURE.md`
> - `docs/architecture/PROFILE_DRIVEN_EXTRACTION_AND_WORLD_BUILDING_PLAN.md`
> - `docs/architecture/futures/HYBRID_MINDSCAPE_AND_TRAVERSAL_PLAN.md`
> - `docs/architecture/futures/QUERY_AWARE_TRAVERSAL_IMPLEMENTATION_PLAN.md`
>
> Source inspirations:
> - Kwun Hang Lau et al., *Breaking the Static Graph: Context-Aware Traversal for Robust Retrieval-Augmented Generation* (CatRAG), arXiv:2602.01965, 2026. https://arxiv.org/abs/2602.01965
> - Yuqing Li et al., *Mindscape-Aware Retrieval Augmented Generation for Improved Long Context Understanding* (MiA-RAG), arXiv:2512.17220, 2025. https://arxiv.org/abs/2512.17220
> - Junjie Wu et al., *SitEmb-v1.5: Improved Context-Aware Dense Retrieval for Semantic Association and Long Story Comprehension*, arXiv:2508.01959, 2025. https://arxiv.org/abs/2508.01959

---

## Decision

The best next step for MONITOR is an **ingestion-first combined rollout**.

If we implement only one thing first, it should be:

1. generate better source-level and section-level semantic artifacts during ingestion
2. make chunk retrieval context-aware using situated summaries / situated embeddings
3. then add query-aware traversal on top of that improved substrate

This ordering is stronger than starting with graph traversal alone.

---

## Why this order wins

### MiA-RAG gives us global source awareness

It helps MONITOR understand the overall meaning of a long book or note collection by producing a persistent semantic frame.

### SitEmb gives us better local evidence units

It helps MONITOR retrieve short passages, transcript turns, and snippets **with awareness of surrounding context**. This is especially valuable for:

- dialogue transcripts
- scene recaps
- rules examples embedded in long chapters
- lore passages whose meaning depends on nearby sections

### CatRAG gives us better path selection

Once the document and snippet layers are stronger, graph traversal becomes far more effective because it is operating over better-scoped evidence.

---

## Architecture summary

The combined retrieval stack should look like this:

```text
INGESTION
  source text
    -> chunk summaries
    -> section summaries
    -> source-level mindscape
    -> source profile
    -> entities + relationships + evidence links
    -> situated chunk / turn embeddings

RUNTIME QUERY
  user query + scene context
    -> source scope
    -> traversal mask
    -> bounded graph traversal
    -> situated snippet retrieval
    -> hybrid reranking
    -> answer / narration / rules response
```

This stack gives MONITOR three layers of context:

1. **global** — what the source is broadly about
2. **local-situated** — what a chunk or turn means inside its neighborhood
3. **path-specific** — what relation chain matters for the active question

---

## Phase 1 — Improve ingestion artifacts first

**Goal:** create reusable semantic assets that make all later retrieval better.

### Primary changes
- generate concise chunk summaries
- generate section summaries
- generate a source-level global summary (mindscape)
- store these artifacts with confidence and source references
- embed section summaries and chunk summaries into Qdrant

### Why this comes first
This benefits:
- ingestion quality
- later retrieval quality
- world building
- rules lookup
- lore query precision

It also creates a stable foundation without requiring new runtime graph complexity.

### Acceptance criteria
- long sourcebooks get a usable global summary
- sections can be retrieved as meaningful units
- chunks are no longer only raw text fragments

### Current verified state
- ✅ section summaries are synthesized and stored on knowledge packs
- ✅ a source-level mindscape is synthesized and stored on knowledge packs
- ✅ source profiles are synthesized and used for light runtime query expansion
- ✅ chunk summaries are now materially generated from section provenance and stored on knowledge packs
- ✅ chunk, section, and source-level summary artifacts are now projected into Qdrant as first-class retrieval signals
- ⚠️ runtime retrieval still only uses these artifacts lightly; situated turn/chunk retrieval and source-scope routing remain future work

---

## Phase 2 — Add situated retrieval for chunks and turns

**Goal:** improve retrieval of short evidence spans whose meaning depends on nearby context.

### Primary idea
Do not only embed the raw chunk or transcript turn.
Also produce a contextualized representation derived from its local neighborhood.

### MONITOR applications
- session transcript retrieval
- NPC dialogue recall
- recap snippet identification
- examples and rules passages inside large chapters
- clue and callback recovery from prior scenes

### Data products
For each chunk or turn, store:
- raw text
- short local summary
- neighboring context summary
- embedding of the local evidence span
- optional embedding of the situated representation

### Acceptance criteria
- retrieval of transcript turns improves on context-dependent questions
- semantically ambiguous lines retrieve the right nearby evidence more often

---

## Phase 3 — Add source-scope routing

**Goal:** use the new semantic assets to decide which source, pack, or section family should be searched first.

### Inputs
- source profile
- global summary
- section summaries
- current scene and universe context
- active system / setting vocabulary

### Outputs
A lightweight `SourceScope` object answering:
- which sources are most relevant?
- which sections should be prioritized?
- which vocabularies and taxonomy families should be activated?

### Acceptance criteria
- queries stop drifting across unrelated sourcebooks
- retrieval focuses on the correct setting or system more often

---

## Phase 4 — Add query-aware traversal on top of scoped retrieval

**Goal:** apply the existing traversal plan only after source scope is known.

### Why it comes later
Graph traversal is most valuable when:
- the relevant source region is already narrowed
- the chunk evidence is already context-aware
- the graph nodes link back to good textual evidence

### Runtime flow
1. compute source scope
2. compute traversal mask
3. run bounded graph queries in the scoped neighborhood
4. attach supporting snippets from situated retrieval
5. rerank and summarize

### Acceptance criteria
- social questions retrieve social chains plus supporting dialogue or lore
- causal questions retrieve event paths plus the right book passages
- rules questions retrieve the right system section and supporting graph context

---

## Phase 5 — Conversational specialization

**Goal:** explicitly support dialogue-heavy play and assistant interactions.

### Recommended additions
- treat each turn as a local evidence unit with speaker metadata
- generate turn-neighborhood summaries for conversations
- link turns to scene, NPC, party, and plot-thread entities
- prefer situated retrieval for dialogue recall before broader semantic search

### Example use cases
- “what exactly did the Duke promise us?”
- “why is this NPC suddenly suspicious?”
- “what clue did we miss in the tavern scene?”

This is where the SitEmb paper is most directly useful.

---

## Suggested file-level execution order

### First wave
- `packages/agents/src/monitor_agents/indexer.py`
- `packages/agents/src/monitor_agents/analyzer.py`
- `packages/agents/src/monitor_agents/prompts/analyzer.py`
- relevant knowledge-pack schemas in the data-layer

### Second wave
- `packages/agents/src/monitor_agents/context_assembly.py`
- helper utilities for scope selection and situated reranking
- Qdrant payload/ranking improvements

### Third wave
- Neo4j read helpers for bounded path retrieval
- traversal-mask utilities in the agents layer

---

## Evaluation priorities

Measure the following in real MONITOR workflows:

- source selection accuracy for long books
- section targeting quality
- transcript-turn retrieval quality
- clue recall in dialogue-heavy scenes
- multi-hop completeness for social and causal questions
- answer grounding quality for Narrator and NPCVoice

---

## Final recommendation

The best merged plan is:

1. **Mindscape-aware ingestion**
2. **Situated chunk / turn retrieval**
3. **Source-scope routing**
4. **Query-aware graph traversal**

This order maximizes ingestion benefit first, then improves conversational recall, and finally adds higher-precision graph reasoning.