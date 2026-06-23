# Mindscape-Aware Ingestion Implementation Plan

> Purpose: turn long sources into reusable semantic assets that preserve document-wide meaning for later retrieval, extraction, and querying.
>
> **Implementation status (April 2026):**
> - ✅ `SectionSummaryArtifact`, `SourceMindscapeArtifact`, `ChunkSummaryArtifact` schemas added to `knowledge_packs.py`
> - ✅ `SectionSummarySignature/Module` and `SourceMindscapeSynthesisSignature/Module` added to `prompts/analyzer.py`
> - ✅ `build_section_summary_inputs()`, `format_mindscape_context()`, `persist_mindscape_artifacts()` helpers in `utils/analyzer_support.py`
> - ✅ `synthesize_mindscape()` method wired into `Analyzer.analyze_source()` before extraction
> - ✅ Mindscape `summary + taxonomy_hints` injected as `source_profile_context` into all extraction calls
> - ✅ `KnowledgePackCreate/Update` gain `chunk_summaries`, `section_summaries`, `source_mindscape` fields
> - Remaining: stronger runtime mindscape-scoped retrieval, source-scope routing, and dialogue-situated consumption of the persisted artifacts
>
> Source inspiration:
> - Yuqing Li et al., *Mindscape-Aware Retrieval Augmented Generation for Improved Long Context Understanding* (MiA-RAG), arXiv:2512.17220, 2025. https://arxiv.org/abs/2512.17220
>
> Related MONITOR docs:
> - `docs/architecture/PROFILE_DRIVEN_EXTRACTION_AND_WORLD_BUILDING_PLAN.md`
> - `docs/architecture/futures/HYBRID_MINDSCAPE_AND_TRAVERSAL_PLAN.md`
> - `docs/architecture/futures/INGESTION_FIRST_CONTEXTUAL_RETRIEVAL_PLAN.md`

---

## Goal

Make ingestion produce a persistent semantic frame for each long source so runtime retrieval does not start from disconnected chunks.

The main output is a reusable source-level semantic scaffold:

- chunk summaries
- section summaries
- one global source summary
- structured source profile metadata
- evidence links from entities and relations back to those summaries

---

## Why this matters in MONITOR

This directly benefits:

- long RPG book ingestion
- rules lookup from large manuals
- lore recall across setting books
- world-building grounded in source structure
- retrieval over session archives and campaign notes

Instead of remembering only raw chunks, MONITOR can remember what the source is broadly about and which sections carry which meaning.

---

## Primary outputs per source

| Output | Purpose |
|---|---|
| Chunk summary | compact meaning of a local span |
| Section summary | mid-level routing and retrieval target |
| Global summary | document-wide semantic frame |
| Source profile | taxonomy, system, genre, narrative frame, domain hints |
| Evidence map | links entities/relations to sections and chunks |

---

## Proposed ingestion flow

```text
raw source
  -> chunking
  -> chunk summarization
  -> section grouping and section summarization
  -> source-level global summary
  -> profile synthesis
  -> extraction with profile context
  -> persistence of semantic artifacts
```

---

## Concrete code map

### Layer ownership

| Concern | Put code in | Do not put it in |
|---|---|---|
| Pure data models for summary artifacts | `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py` | agents prompt modules |
| Summary generation and orchestration | `packages/agents/src/monitor_agents/analyzer.py` | CLI or data-layer |
| Reusable summary / grouping helpers | `packages/agents/src/monitor_agents/utils/analyzer_support.py` or a new `source_mindscape_support.py` | inside oversized analyzer methods |
| Prompt signatures for summary generation | `packages/agents/src/monitor_agents/prompts/analyzer.py` | schema modules |
| Storage and retrieval payload wiring | existing Mongo/Qdrant write paths | ad-hoc JSON blobs in unrelated files |

### Symbols to add

#### Data-layer
Add new pure-data models in `knowledge_packs.py`:
- `SectionSummaryArtifact`
- `SourceMindscapeArtifact`
- optional `ChunkSummaryArtifact`

These should be nested data containers only: no retrieval logic, no formatting logic.

#### Agents layer
Add or extend these symbols:
- `SourceMindscapeSynthesisModule` in `prompts/analyzer.py`
- `build_section_summary_inputs()` helper in `utils/analyzer_support.py`
- `synthesize_source_mindscape()` method in `Analyzer`
- `persist_source_mindscape()` helper in `Analyzer`

### Concrete file edits

1. `packages/agents/src/monitor_agents/analyzer.py`
   - call the new summary synthesis path after section classification and before final extraction
   - persist chunk / section / source-level summary artifacts on the knowledge pack

2. `packages/agents/src/monitor_agents/prompts/analyzer.py`
   - add structured prompt signatures for:
     - chunk summary generation
     - section summary generation
     - source-level summary generation

3. `packages/agents/src/monitor_agents/utils/analyzer_support.py`
   - add grouping and dedup helpers so summary-building logic is shared and testable
   - keep trimming, ranking, grouping, and summary formatting here to avoid growing `Analyzer` further

4. `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`
   - add the new artifact models and response fields
   - keep them optional and backward-compatible

### Test placement

Add or extend tests in:
- `packages/agents/tests/test_analyzer.py`
- `packages/agents/tests/test_analyzer_support.py`
- `packages/data-layer/tests/test_tools/test_ingestion_job_tools.py` if API payload shape changes

### SOLID / DRY guardrails

- keep `Indexer` focused on raw ingest and embedding, not semantic summarization
- keep summary synthesis in `Analyzer` or analyzer helpers only
- extract reusable grouping / formatting helpers instead of duplicating summary code across agents
- do not store the same summary text in multiple incompatible places; keep the knowledge pack as the canonical summary payload
- do not bury new orchestration inside already large methods; extract focused helpers with single-purpose names

---

## Proposed data contract

The first implementation should define one canonical summary payload shape and reuse it everywhere.

### Suggested schema shape

Add nested artifact models in `knowledge_packs.py` with fields like:

```python
class ChunkSummaryArtifact(BaseModel):
    chunk_id: str
    chunk_index: int
    source_ref: str | None = None
    summary: str
    confidence: float = 0.0
    tags: list[str] = Field(default_factory=list)

class SectionSummaryArtifact(BaseModel):
    section_key: str
    heading_path: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    summary: str
    confidence: float = 0.0
    semantic_category: str | None = None

class SourceMindscapeArtifact(BaseModel):
    source_name: str
    summary: str
    themes: list[str] = Field(default_factory=list)
    taxonomy_hints: list[str] = Field(default_factory=list)
    confidence: float = 0.0
```

Keep these payloads:
- serializable
- backward-compatible
- independent from retrieval implementation details

### Persistence rule

The knowledge pack should be the canonical storage home for these artifacts.
Qdrant should store retrieval-oriented projections of them, not become the source of truth.

---

## PR-sized implementation backlog

This work should be delivered in small, architecture-safe batches.

### Batch 1 — Schema and parser-safe payloads

**Purpose:** introduce the new artifact shapes without changing runtime behavior.

**Code changes**
- `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`
- serializer / update paths already used by the analyzer

**What to code**
- new optional fields for chunk, section, and source-level summaries
- default factories so old packs still deserialize cleanly
- validation for maximum text length and confidence bounds

**Tests**
- schema round-trip tests
- backward compatibility tests for old pack payloads

**Done when**
- creating or updating a knowledge pack with summary artifacts works without breaking existing ingestion tests

### Batch 2 — Shared section grouping helpers

**Purpose:** create the reusable foundation before touching the main analyzer flow.

**Code changes**
- `packages/agents/src/monitor_agents/utils/analyzer_support.py`

**What to code**
- helper to cluster chunks into section groups from heading paths and semantic categories
- helper to build compact summary inputs
- helper to trim or merge noisy sections
- helper to derive stable section keys

**Why this is important**
This is the main DRY seam. If skipped, summary grouping logic will get copied into `Analyzer`, test fixtures, and prompt adapters.

**Tests**
- section grouping tests
- stable key generation tests
- noisy-reference-section filtering tests

### Batch 3 — Summary prompt modules

**Purpose:** add structured, auditable summary generation rather than freeform prose blobs.

**Code changes**
- `packages/agents/src/monitor_agents/prompts/analyzer.py`

**What to code**
- chunk summary signature
- section summary signature
- source mindscape summary signature
- return structured fields only, not narrative paragraphs with hidden formatting assumptions

**Tests**
- module output parsing tests
- failure / empty-result fallback tests

### Batch 4 — Analyzer orchestration

**Purpose:** wire the new summary pipeline into the real ingestion flow.

**Code changes**
- `packages/agents/src/monitor_agents/analyzer.py`

**What to code**
- call chunk-to-section summarization after section classification
- call source-level synthesis after section summaries are available
- persist artifacts to the knowledge pack before or alongside extracted pack content
- attach traceable source refs to each artifact

**Keep out of scope**
- no new Neo4j writes
- no runtime retrieval changes yet

**Tests**
- extend `packages/agents/tests/test_analyzer.py`
- verify the final pack includes summary artifacts
- verify failures degrade gracefully to current behavior

### Batch 5 — Retrieval persistence and runtime consumption

**Purpose:** let the rest of the system actually use the new artifacts.

**Code changes**
- `packages/agents/src/monitor_agents/context_assembly.py`
- existing Qdrant write / payload paths
- optional consumers in `narrator.py` and `npc_voice.py`

**What to code**
- embed section summaries for routing
- allow retrieval to ask for source, section, or chunk level evidence
- pass the source-level mindscape into runtime context summaries when the query is broad or ambiguous

**Tests**
- extend `packages/agents/tests/test_context_assembly.py`
- verify broad queries prefer section or source summary guidance over random chunk drift

---

## Detailed phase plan

### Phase 1 — Stable summary artifacts

**Files**
- `packages/agents/src/monitor_agents/analyzer.py`
- `packages/agents/src/monitor_agents/prompts/analyzer.py`
- `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`

**Tasks**
1. generate concise chunk summaries during ingestion
2. group chunks into section summaries
3. synthesize a source-level global summary
4. persist all summaries with source references and confidence metadata

**Acceptance checkpoint**
- the analyzer can finish a run and create a pack with summary artifacts even if downstream retrieval does not yet consume them

### Phase 2 — Profile and taxonomy alignment

**Files**
- existing source-profile schemas and analyzer prompts
- helper logic in `analyzer_support.py`

**Tasks**
1. align the global summary with the source profile
2. persist profile-level hints for system, taxonomy, tone, institutions, and lore domains
3. use those hints to improve extraction routing
4. keep only one canonical profile merge path to avoid drift between summary-derived and profile-derived metadata

**Acceptance checkpoint**
- extracted summaries and extracted profile agree on the main source identity and domain vocabulary

### Phase 3 — Retrieval-ready persistence

**Files**
- knowledge-pack schemas in the data-layer
- Qdrant payload write path

**Tasks**
1. embed chunk summaries and section summaries for retrieval
2. attach section and source identifiers to Qdrant payloads
3. ensure later retrieval can ask for chunk, section, or source-summary level evidence
4. keep payload keys stable so reranking logic can rely on them

**Acceptance checkpoint**
- a retrieval call can distinguish whether a hit came from a raw chunk, a section summary, or the source mindscape

### Phase 4 — Runtime consumption

**Files**
- `packages/agents/src/monitor_agents/context_assembly.py`
- `packages/agents/src/monitor_agents/narrator.py`
- `packages/agents/src/monitor_agents/npc_voice.py`

**Tasks**
1. allow agents to request global summary and section summary context
2. include mindscape context in retrieval expansion and summarization
3. use it to resolve ambiguous queries against large sources
4. keep the added retrieval rules in shared helpers where possible

**Acceptance checkpoint**
- the same ambiguous query produces more stable, source-aware context bundles than before

---

## Verification plan

Use small, relevant checks after each batch rather than waiting until the end.

### Minimum checks
- `pytest packages/agents/tests/test_analyzer.py`
- `pytest packages/agents/tests/test_analyzer_support.py`
- `pytest packages/agents/tests/test_context_assembly.py`
- `pytest packages/data-layer/tests/test_tools/test_ingestion_job_tools.py`
- `python scripts/check_layer_dependencies.py`

### Functional proof points
Manually verify at least one:
- lore-heavy sourcebook
- mechanics-heavy rulebook
- mixed source with appendices or reference sections

The evidence to look for is:
- coherent source-level summary
- useful section boundaries
- fewer misrouted extractions from indexes and appendix noise

---

## Risks and rollback

| Risk | Why it happens | Mitigation |
|---|---|---|
| Analyzer becomes too large | new orchestration gets added inline | extract helper functions early |
| Duplicate summary storage | same artifact copied into multiple payload shapes | keep knowledge pack canonical |
| Summary drift from evidence | summaries over-abstract or hallucinate | persist source refs and confidence; keep extraction evidence-first |
| Ingestion latency increases too much | too many sequential summary calls | batch by section and cache intermediate artifacts |
| Runtime ignores new assets | summaries are stored but never consumed | add explicit source / section retrieval path in `ContextAssembly` |

If the rollout causes regressions:
- keep all new fields optional
- feature-flag runtime usage of mindscape context
- allow analyzer to fall back to the current extraction-only path

---

## Acceptance criteria

- long sourcebooks produce a usable global summary
- section-level retrieval works cleanly
- profile-aware extraction improves routing and precision
- runtime retrieval can use source summaries without re-reading the whole book
- old ingestion flows still work when the new fields are absent

---

## Recommended first implementation

Start with this concrete slice:

1. add the artifact schemas
2. add grouping helpers
3. add section and source summary synthesis in `Analyzer`
4. persist the artifacts on the knowledge pack
5. verify with the analyzer and layer-dependency tests

That is the smallest high-value batch and the right place to start.