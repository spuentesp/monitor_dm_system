# Profile-Driven Extraction and World-Building Plan

> **Purpose:** Add a structured profile layer that helps MONITOR understand what it is reading or building **before** it extracts data, asks follow-up questions, or drives runtime narration.

---

## Scope

This plan covers four connected workstreams:

1. **Document ingestion** (`Indexer` → `Analyzer` → `KnowledgePack`)
2. **Lore-aware extraction** (axioms, lore facts, relationships, institutions)
3. **Runtime consumption** (retrieval, narration, resolution, NPC voice)
4. **World Architect world/multiverse creation**

Canonical architecture rules still apply:
- `data-layer` stores schemas and persistence only
- `agents` perform synthesis, extraction, and orchestration
- `cli`/`ui` consume and review the results

See also: `SYSTEM.md`, `STRUCTURE.md`, `ARCHITECTURE.md`, `docs/USE_CASES.md`.

---

## Implementation status (April 14, 2026)

| Area | Status | Notes |
|---|---|---|
| Phase 0 — Schema and audit foundations | ✅ Ready | `EmbeddedSourceProfile` now persists on `KnowledgePack` create/update/response flows and is exposed through the pack API serializer. |
| Phase 1 — Source profiling in the Analyzer | ✅ Ready | `Analyzer.analyze_source()` now classifies sections, synthesizes/persists a source profile, logs a summary, and keeps a generic fallback path for low-confidence cases. |
| Phase 2 — TOC/index/glossary structure signals | ✅ Ready | Ingestion revamp (`feat/ingestion-revamp`) replaces keyword tagging with PDF structure extraction (`extract_pdf_structure()`), LLM section categorization (`SectionCategorizationModule`), and section/source mindscape synthesis. Reference sections now seed taxonomy containers, alias lexicons, and profile hints. |
| Phase 3 — Lore-aware extraction | ✅ Ready | Mindscape `summary + taxonomy_hints` are injected as `source_profile_context` into all batched extraction calls. Typed DSPy output fields replace pipe-delimited parsing. |
| Phase 4 — Mechanics-aware extraction | ✅ Ready | Generalized mechanic schemas (`TrackDefinition`, `TieredAbilitySystem`, `ResolutionMechanic`, `DamageModel`, `ConditionDefinition`, `ActionEconomy`, `AdvancementModel`, `RecoveryModel`) added. Typed DSPy extraction for game rules, character sheets, creation procedures, NPCs, and relationships. Thin mechanic reference nodes (`:AbilitySystem`, `:Track`, `:Condition`) written to Neo4j via CanonKeeper. |
| Phase 5 — Runtime consumers | ✅ Ready | Context Assembly, Narrator, Resolver, and NPCVoice are now profile-aware and bounded by the embedded source profile. |
| Phase 6 — World Architect live profiling | 🟡 In progress | The World Architect now derives a live `EmbeddedWorldProfile`-style context, coverage summary, and open-question set each turn; deeper persistence and structured profile update flows remain. |
| Phase 7 — UI and review surfaces | 🟡 In progress | `source_profile_data` is now available at the API layer; dedicated review/edit UI is still pending. |

### Objective alignment status

| Objective | Status | Current rollout impact |
|---|---|---|
| `O1` Persistent Fictional Worlds | ✅ Profile-foundation ready | Knowledge packs now preserve setting/system framing, taxonomy families, and evidence-backed context. |
| `O3` System-Agnostic Rules Handling | ✅ Profile-foundation ready | Extraction now has a structured vocabulary layer for unusual systems instead of relying on generic interpretation alone. |
| `O4` Assisted Human GMing | ✅ Profile-foundation ready | Pack/API responses now carry inspectable profile metadata for later review surfaces. |
| `O2` / `O5` | 🟡 Pending downstream rollout | Runtime play and long-term world evolution still need the later phases below. |

---

## Problem Statement

MONITOR already extracts structured data from books and can build worlds conversationally, but the current flow is still mostly **generic** at interpretation time. This creates several quality risks:

- system-specific concepts are flattened into generic entities or lore facts
- taxonomy containers (`Clan`, `Discipline`, `Class`, `Frame`) are not always distinguished from institutions
- world truths, historical facts, and relationship structures can be blurred together
- TOC/index/glossary signals are available but underused as navigation and framing metadata
- World Architect asks useful questions, but it does not yet maintain a formal, evolving model of the world being built

The proposed solution is to add a **profile-first pass** that generates a structured understanding of the source or world, then feeds that profile into the existing stable prompts and agent workflows.

---

## Core Design Principle

Do **not** allow the LLM to freely rewrite its own extraction prompts.

Use this pattern instead:

1. **Profile / framing pass**
   - infer what the source or world appears to be
   - infer which domains, taxonomies, institutions, and vocabularies matter
2. **Execution pass**
   - run the existing extraction / questioning prompts with the generated profile injected as structured context

This preserves:
- auditability
- determinism
- easier debugging
- versioning and rollback safety

---

## Shared Data Model

## `SettingProfile` Family

Use one shared conceptual model with two concrete variants:

- **`EmbeddedSourceProfile`** — generated from ingested documents
- **`EmbeddedWorldProfile`** — generated and updated during World Architect conversations

Both profiles should share the same semantic backbone.

### Recommended fields

| Field | Purpose |
|---|---|
| `profile_type` | `source` or `world` |
| `source_kind` | `rulebook`, `setting_supplement`, `adventure_module`, `wiki`, `notes`, `mixed` |
| `world_kind` | fantasy, gothic horror, sci-fi, post-apocalypse, mythic, mixed |
| `system_name`, `edition`, `family` | game/ruleset identity when applicable |
| `genre_tone` | high-level tone and mood |
| `narrative_frame` | political, tragic, investigative, military, survival, horror |
| `lore_domains` | cosmology, history, religion, geography, factions, morality, metaphysics |
| `taxonomy_containers` | named category families such as `Clan`, `Discipline`, `Class`, `Frame`, `License` |
| `institution_model` | how power, belonging, identity, and authority are organized |
| `relationship_patterns` | likely important relationship types (`member_of`, `subtype_of`, `opposes`, `controls`, etc.) |
| `term_lexicon` / `aliases` | retrieval and extraction synonym support |
| `canon_signal_terms` | words that indicate world-truth, event, lineage, rank, sect, rite, etc. |
| `coverage_summary` | what is already known or extracted |
| `known_open_questions` | unresolved gaps |
| `confidence_by_field` | per-field confidence |
| `evidence_refs` | page/section/message references supporting the profile |
| `profile_version`, `prompt_version`, `model_used`, `generated_at` | audit metadata |

---

## Step-by-Step Implementation Plan

## Phase 0 — Schema and audit foundations ✅ Ready

**Goal:** establish the persistence and versioning model before wiring in new logic.

### Files
- `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`
- `packages/data-layer/src/monitor_data/schemas/game_systems.py` (reference only; no cross-layer logic)
- optional future world-building storage surface in Mongo-backed world artifacts

### Tasks
1. Add `EmbeddedSourceProfile` to `knowledge_packs.py`.
2. Add optional `source_profile_data` fields to:
   - `KnowledgePackCreate`
   - `KnowledgePackUpdate`
   - `KnowledgePackResponse`
3. Include:
   - evidence refs
   - field-level confidence
   - prompt/model/version metadata
4. Keep the profile purely data-oriented; no logic in Layer 1.

### Acceptance criteria
- a knowledge pack can store and return a structured profile payload
- profile fields survive CRUD round trips without lossy serialization

---

## Phase 1 — Source profiling in the Analyzer ✅ Ready

**Goal:** synthesize a `SourceProfile` before extraction begins.

### Primary files
- `packages/agents/src/monitor_agents/prompts/analyzer.py`
- `packages/agents/src/monitor_agents/analyzer.py`
- `packages/agents/tests/test_analyzer.py`

### Tasks
1. Add a new DSPy signature/module in `prompts/analyzer.py`:
   - `SourceProfileSynthesisSignature`
   - `SourceProfileSynthesisModule`
2. Inputs should include:
   - representative sections
   - heading paths
   - selected TOC/index/glossary snippets
   - source name
3. Output should be **structured profile JSON**, not prose prompt rewriting.
4. In `Analyzer.analyze_source()`:
   - run section classification/filtering first
   - synthesize the profile next
   - persist it on the draft/ready pack
   - append summary data to the ingestion job activity log
5. Add fallback behavior:
   - low confidence → keep extraction in generic mode
   - partial confidence → pass only the stable, high-confidence profile fields downstream

### Acceptance criteria
- Analyzer can synthesize a profile for at least one rulebook and one lore-heavy source
- profile generation failure does not block ingestion

---

## Phase 2 — Use TOC, index, glossary, and appendices as structure signals 🟡 In progress

**Goal:** exploit reference sections as navigation and framing metadata without treating them as direct canon evidence.

### Primary files
- `packages/agents/src/monitor_agents/prompts/analyzer.py`
- `packages/agents/src/monitor_agents/utils/analyzer_support.py`
- `packages/agents/src/monitor_agents/analyzer.py`

### Why this matters
Contents pages, indexes, glossaries, and appendices are often the fastest way to infer:
- the kind of book
- major domain groupings
- important taxonomies
- important named term families
- section routing priorities

### Tasks
1. Keep current filtering of reference sections, but split their role into two modes:
   - **support mode** for profile synthesis and lexicon expansion
   - **extraction mode** only when supported by actual body text
2. Extend the support helpers to:
   - detect candidate taxonomy containers from TOC/index/glossary entries
   - build alias maps from glossary-style definitions
   - prioritize sections by heading patterns and TOC evidence
3. Explicitly prevent direct lore emission from:
   - table of contents entries
   - plain index lines
   - ads / credits / legal pages
   unless corroborated by body text.
4. Use appendix/reference sections to recover:
   - character sheet fields
   - named power families
   - subsystem names
   - repeated mechanical vocabulary

### Acceptance criteria
- TOC/index data improves profile accuracy and section ranking
- reference pages no longer inflate lore/entity noise

---

## Phase 3 — Lore-aware extraction improvements 🟡 In progress

**Goal:** improve axioms, lore facts, and relationship extraction using the profile as a reading frame.

### Primary files
- `packages/agents/src/monitor_agents/prompts/analyzer.py`
- `packages/agents/src/monitor_agents/analyzer.py`

### Affected modules
- `AxiomExtractionSignature`
- `EntityExtractionSignature`
- `LoreFactExtractionSignature`
- `RelationshipInferenceSignature`
- `BatchedExtractionSignature`

### Tasks
1. Add `source_profile_context` input to the above signatures.
2. Feed in only the most useful profile data:
   - `lore_domains`
   - `taxonomy_containers`
   - `institution_model`
   - `relationship_patterns`
   - `canon_signal_terms`
   - `narrative_frame`
3. Update extraction instructions so the model distinguishes:
   - **Axiom** → enduring truth of reality/world order
   - **LoreFact** → specific event/state/relationship/attribute in canon
   - **EntityArchetype** → reusable group/type/template
   - **Relationship** → graph edge between meaningful nodes
4. Improve routing of sections to extraction layers:
   - history-heavy → lore facts
   - cosmology-heavy → axioms
   - institutional/political → entities + relationships
5. Keep evidence-first behavior:
   - profile can shape interpretation
   - profile cannot justify unsupported facts

### Acceptance criteria
- clearer separation between axioms, lore facts, institutions, and taxonomy
- improved relationship precision on factional or metaphysical sourcebooks

---

## Phase 4 — Mechanics-aware extraction improvements 🟡 In progress

**Goal:** use the profile to interpret nonstandard system vocabularies and schemas.

### Primary files
- `packages/agents/src/monitor_agents/prompts/analyzer.py`
- `packages/agents/src/monitor_agents/analyzer.py`

### Affected modules
- `GameSystemDetectionSignature`
- `GameRuleExtractionSignature`
- `CharacterSheetExtractionSignature`
- `CreationProcedureExtractionSignature`
- `NPCExtractionSignature`

### Tasks
1. Add `source_profile_context` to the game-system and schema-extraction prompts.
2. Use profile fields such as:
   - `system_name` / `family`
   - `taxonomy_containers`
   - `term_lexicon`
   - `important_named_sets`
3. Improve recognition of:
   - resource systems
   - power families
   - stat categories
   - NPC tier models
   - subsystem boundaries (duels, ship combat, sorcery, downtime, etc.)
4. Keep the game-system schema stored both as:
   - standalone `game_system_id` reference
   - embedded `game_system_data` on the pack

### Acceptance criteria
- books with unusual naming conventions are still mapped into the canonical schema cleanly
- fewer system-specific examples are needed inside the prompt bodies over time

---

## Phase 5 — Runtime consumers of the profile 🟡 In progress

**Goal:** make the rest of the play stack benefit from the same vocabulary and structure.

### 5A. Context Assembly ✅ Ready

**Files:**
- `packages/agents/src/monitor_agents/context_assembly.py`
- `packages/agents/src/monitor_agents/prompts/context_assembly.py`

**Tasks:**
1. Use `term_lexicon` and `aliases` to expand retrieval queries.
2. Improve snippet search for systems with unusual terminology.
3. Prefer profile-relevant snippets during context compression.

### 5B. Narrator ✅ Ready

**Files:**
- `packages/agents/src/monitor_agents/narrator.py`
- `packages/agents/src/monitor_agents/prompts/narrator.py`

**Tasks:**
1. Inject a compact narrative lexicon built from the profile.
2. Use `genre_tone`, `narrative_frame`, and institution terms to shape prose.
3. Keep the narrator in-world; never dump taxonomy labels directly unless the fiction supports it.

### 5C. Resolver and `GameSystemRuntime` ✅ Ready

**Files:**
- `packages/agents/src/monitor_agents/resolver.py`
- `packages/agents/src/monitor_agents/game_system.py`

**Tasks:**
1. Use profile aliases as a fallback when the embedded game schema is incomplete.
2. Improve action-to-stat routing for nonstandard vocabularies.
3. Use subsystem hints to choose the right rule family.

### 5D. NPCVoice ✅ Ready

**Files:**
- `packages/agents/src/monitor_agents/npc_voice.py`
- `packages/agents/src/monitor_agents/prompts/npc_voice.py`

**Tasks:**
1. Use profile vocabulary to support:
   - social ranks
   - faction identities
   - forms of address
   - culturally appropriate jargon
2. Keep the NPC bounded to what the profile and canon actually support.

### Acceptance criteria
- runtime narration and retrieval feel more native to the setting/system
- profile data improves quality without becoming mandatory for basic play

---

## Phase 6 — World Architect: live world and multiverse profiling 🟡 In progress

**Goal:** give the World Architect a formal, evolving model of the world being built so it can create **all world data** progressively and ask the right next questions.

### Primary files
- `packages/agents/src/monitor_agents/prompts/world_architect.py`
- future world-building storage and review surfaces in Layer 1 / UI

### Why this matters
The World Architect is not just a Q&A assistant. Its long-term role is to help define:
- multiverse structure
- universes and timelines
- cosmology and metaphysical laws
- civilizations, factions, cultures, institutions
- geography and locations
- core entities and relationships
- historical eras and conflicts
- play-relevant hooks and constraints

### Tasks
1. Add a live **`EmbeddedWorldProfile`** concept.
2. Update `WorldArchitectSignature` to take:
   - `world_profile_context`
   - `coverage_summary`
   - `known_open_questions`
3. Add outputs such as:
   - `profile_updates`
   - `priority_gaps`
   - `recommended_next_questions`
   - `structured_world_proposals`
4. Update `WorldGapAnalysisSignature` so it reasons from current coverage rather than generic checklists alone.
5. Ensure the World Architect can progressively produce structured proposals for:
   - multiverse definition
   - universe definition
   - cosmology
   - factions and institutions
   - geography
   - named entities
   - axioms and lore facts
   - active conflicts and themes
6. Persist profile updates over the course of a world-building conversation.

### Acceptance criteria
- World Architect asks fewer generic questions and more targeted ones
- the world profile becomes richer turn by turn
- resulting proposals cover world and multiverse data more systematically

---

## Phase 7 — UI and review surfaces 🟡 In progress

**Goal:** make the profile inspectable, editable, and trustworthy.

### Likely files
- `packages/ui/backend/src/monitor_ui/routers/ingest_shared.py`
- `packages/ui/frontend/src/app/forge/page.tsx`
- future World Architect UI surfaces

### Tasks
1. Show source profile summary in the pack review/Forge experience:
   - inferred book/source kind
   - major domains
   - taxonomy containers
   - institutions
   - confidence and evidence refs
2. Allow conservative manual overrides for high-value fields.
3. Show world profile coverage and gaps during World Architect sessions.
4. Keep the UI read-mostly at first; do not block ingestion on the editor surface.

### Acceptance criteria
- users can inspect why the system interpreted a source/world the way it did
- profile quality can be audited without digging through raw logs

---

## Guardrails

These rules should stay in force throughout the rollout:

- **No self-rewriting prompts.** Profile output must be structured data.
- **Evidence before claims.** TOC/index/glossary terms are scaffolding, not proof of canon by themselves.
- **Low-confidence fallback.** The system must still ingest and build worlds in generic mode when needed.
- **Stable prompt contracts.** Add profile context as an extra input; do not destabilize existing schema outputs.
- **Human review.** Expose the profile for inspection and, later, editing.
- **Version everything.** Prompt version, model used, and profile version should be stored with the result.

---

## Testing Strategy

### Primary test targets
- `packages/agents/tests/test_analyzer.py`
- future World Architect tests in the agents test suite

### Test groups

#### Source/profile synthesis
- VtM/Storyteller-like rulebook → detects clans, disciplines, sects, morality metaphysics
- d20 fantasy rulebook → detects classes, species, spell schools, HP/resources
- sci-fi/mech book → detects frames, licenses, manufacturers, subsystem terms
- lore-only setting book → profile stays lore-heavy without inventing a game system
- mixed/adventure module → partial profile with low-confidence fallbacks

#### Lore quality
- ontology truth vs historical event separation
- institution vs taxonomy separation
- relationship inference quality for factional books
- reduced noise from index/TOC pages

#### World Architect behavior
- improved question prioritization from partial world state
- useful gap detection over multiple turns
- progressive structured proposal creation
- profile evolution is persisted and inspectable

---

## Suggested rollout order

### Milestone 1 — safest high-value MVP
1. Add `EmbeddedSourceProfile` schema
2. Add `SourceProfileSynthesisModule`
3. Run it in `Analyzer.analyze_source()`
4. Persist the profile on the pack
5. Use it only for lore + relationship extraction first

### Milestone 2 — broader analyzer adoption
1. wire profile context into mechanics extraction
2. improve TOC/index/glossary use for routing and lexicon recovery
3. expand tests to more systems/source types

### Milestone 3 — runtime consumers
1. ContextAssembly query expansion
2. Narrator vocabulary/tone support
3. Resolver fallback alias support
4. NPCVoice setting vocabulary support

### Milestone 4 — World Architect evolution
1. add `EmbeddedWorldProfile`
2. update world-building prompts to use and update the profile
3. persist profile growth over time
4. expose profile coverage and gaps in the UI

---

## Definition of Done

This initiative is complete when MONITOR can:

1. **Ingest a new source** and first infer what it is, how it is organized, and which concepts matter.
2. **Extract lore and mechanics** with better separation between ontology, history, institutions, taxonomy, and relationships.
3. **Use the same structured understanding at runtime** for retrieval, narration, resolution, and NPC voice.
4. **Build worlds conversationally** with a persistent `WorldProfile` that drives better questions and more complete structured world/multiverse data.
5. **Show its work** through audit-friendly stored profile data, evidence refs, confidence, and versioning.

---

## Immediate next action

Implement **Milestone 1** first:
- add `EmbeddedSourceProfile`
- add `SourceProfileSynthesisModule`
- wire it into `Analyzer.analyze_source()`
- inject `source_profile_context` into lore and relationship extraction

That gives the highest value with the lowest architectural disruption.
