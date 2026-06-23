# Ingestion Revamp Design

> **Status:** ✅ Implemented (all 17 tasks committed on `feat/ingestion-revamp`, 2026-04-14)
> **Date:** 2026-04-13
> **Scope:** Full ingestion pipeline revamp — extraction quality, data model generalizations, graph/storage architecture
> **Test systems:** Death in Space, Vampire: the Masquerade 20th Anniversary, 7th Sea 2e, Zweihänder
> **Related futures docs:**
> - `docs/architecture/futures/INGESTION_FIRST_CONTEXTUAL_RETRIEVAL_PLAN.md`
> - `docs/architecture/futures/MINDSCAPE_AWARE_INGESTION_IMPLEMENTATION_PLAN.md`
>
> **Implementation commits:**
> - `920c87b` — TrackDefinition, ThresholdEffect schemas
> - `fc352e2` — TieredAbilitySystem, AbilityTier, AdvantageDefinition
> - `8860acf` — ResolutionMechanic, DamageModel, ConditionDefinition, ActionEconomy, AdvancementModel, RecoveryModel
> - `7078689` — ChunkSummaryArtifact, SectionSummaryArtifact, SourceMindscapeArtifact on KnowledgePack
> - `25ffa00` — SectionBlock + extract_pdf_structure()
> - `1bfcdec` — 1024-token chunks for rulebook sources
> - `0841e2b` — SectionCategorizationSignature/Module
> - `2a16a88` — Indexer uses extract_pdf_structure + SectionCategorizationModule
> - `bf991e2` — analyzer_support.py helpers
> - `c5e9dce` — SectionSummaryModule + SourceMindscapeSynthesisModule
> - `fa78836` — synthesize_mindscape() in Analyzer; detection → HEAVY + 48 chunks
> - `f56fa49` — All signatures → typed DSPy output; delete analyzer_parsers.py
> - `116d99c` — neo4j_tools/mechanics.py (AbilitySystem, Track, Condition nodes)
> - `03fdff6` (not shown in log) — CanonKeeper mechanic node writes

---

## Problem Statement

The ingestion pipeline produces KnowledgePacks with wrong/hallucinated content. Three consistent failure modes:

- **B** — extracted content is low-quality or incorrect
- **C** — game system detection does not fire reliably
- **D** — rules are extracted but missing fields or mistyped

Root causes:

1. `_classify_semantic_category()` uses `TagPool` keyword matching. Game-system-specific vocabulary (VtM Disciplines, 7th Sea Raises/Hubris, Zweihänder Professions/Chaos Alignment, Death in Space Void/Omens) fails to map correctly. Wrong tags → wrong sections fed to each extractor → LLM hallucinates against off-topic content.
2. Game system detection uses 12 sample chunks via a LIGHT (local) model — high miss rate especially for non-d20 systems.
3. 512-token sliding-window chunking ignores PDF bookmark trees, destroying section hierarchy.
4. Pipe-delimited output format is brittle — LLM deviations cause silent parse failures.
5. The data model flattens runtime-critical mechanics (damage types, conditions, action economy, moral tracks, tiered abilities) to unstructured prose strings, making them unusable for Narrator adjudication at runtime.

---

## Architecture Overview

The revamped pipeline replaces the current linear flow with a **three-pass approach** before extraction:

```
CURRENT:
  raw bytes
    → chunk (512-token sliding window, keyword-tag)
    → embed → Qdrant
    → Analyzer: pulls chunks by tag → DSPy pipe-format → parse
    → KnowledgePack

REVAMPED:
  raw bytes
    → Pass 1: Structure extraction (PDF ToC + headings → section tree)
    → Pass 2: Semantic enrichment  (LLM categorization per section + chunk/section summaries)
    → Pass 3: Mindscape synthesis  (source-level global summary → extraction context)
    → Extraction (profile-guided, typed structured output)
    → KnowledgePack (enriched schema)
    → CanonKeeper → Neo4j (world entities + thin mechanic reference nodes)
```

### Layer ownership

| Concern | Layer | File |
|---|---|---|
| PDF structure extraction | 1 (data-layer) | `ingest_tools.py` |
| LLM section categorization signature | 2 (agents) | `prompts/analyzer.py` |
| Mindscape synthesis orchestration | 2 (agents) | `analyzer.py` |
| Mindscape/summary helper utilities | 2 (agents) | `utils/analyzer_support.py` |
| New artifact + mechanic schemas | 1 (data-layer) | `knowledge_packs.py`, `game_systems.py` |
| Neo4j thin mechanic node writes | 1 (data-layer) | `neo4j_tools/mechanics.py` (new) |
| CanonKeeper mechanic node commit | 2 (agents) | `canonkeeper.py` |

### What does NOT change

- Pipeline orchestration in `ingestion_pipeline.py`
- CLI ingest command
- Layer boundaries — no skip-layer imports
- MinIO upload, Neo4j Source creation
- CanonKeeper flow for world entities

---

## Section 1: PDF Structure Extraction

### Problem

PyMuPDF is used page-by-page with a sliding-window token splitter. PDF bookmark trees (`/Outlines`) are ignored. All structural knowledge — chapter names, section hierarchy, subsection nesting — is lost before chunking begins. The only heading detection is a heuristic (`_looks_like_heading`) that misses bookmarked headings.

### Change

Add `extract_pdf_structure()` as a **pre-pass before chunking** in `ingest_tools.py`.

```python
def extract_pdf_structure(pdf_bytes: bytes) -> list[SectionBlock]:
    """
    Extract bookmark tree + page text into structured section blocks.

    Uses fitz.get_toc() for the heading hierarchy, then assigns page text
    to each section span. Falls back to _looks_like_heading() heuristic
    when no bookmarks exist (scanned PDFs, some EPUBs).

    Returns list of SectionBlock, each with:
      heading_path: list[str]   — ["Chapter 2", "Combat", "Attack Rolls"]
      depth: int                — nesting depth (0 = chapter, 1 = section, ...)
      page_start: int
      page_end: int
      text: str                 — raw page text for this section span
    """
```

Chunks produced from this pass carry `heading_path: list[str]` and `section_depth: int` in their Qdrant payload, replacing the current single `section_path: str | None`.

**Fallback:** For PDFs with no bookmarks, `_looks_like_heading()` heuristic is retained unchanged.

**Why this matters:** The LLM categorizer (Section 2) can classify `["Chapter 3", "Character Creation", "Clans", "Nosferatu"]` accurately for any game system — no vocabulary knowledge required.

---

## Section 2: LLM-at-Ingest Categorization

### Problem

`_classify_semantic_category()` uses `TagPool` keyword matching. System-specific vocabulary from any of the four test systems fails to map to canonical semantic categories. Misclassified chunks get routed to the wrong extractor, which receives irrelevant content and hallucinates.

### Change

Replace keyword scan with a lightweight LLM call per **section** at index time in `Indexer`.

#### New DSPy signature (`prompts/analyzer.py`)

```python
class SectionCategorizationSignature(dspy.Signature):
    """Classify a document section into one universal semantic category."""
    heading_path: str      # e.g. "Chapter 3 > Clans > Nosferatu"
    section_excerpt: str   # first ~200 chars of body text
    → category: Literal[
        "power_system", "lineage", "character_archetype",
        "items_equipment", "combat_rules", "social_moral",
        "factions", "lore_history", "creatures_npc",
        "game_mechanics", "general"
    ]

class SectionCategorizationModule(_AnalyzerModule):
    _signature = SectionCategorizationSignature
    _role = ModelRole.LIGHT   # small input + single enum output — fast local model
```

#### Design decisions

- Called **once per section** during `Indexer.index()`, not once per chunk. All chunks in a section inherit the category.
- `TagPool` is retained as a **zero-cost pre-filter**: if the heading maps cleanly, skip the LLM call. LLM invoked only when TagPool returns `"general"`.
- Result stored in `chunk.metadata["semantic_category"]` as before — no downstream Analyzer changes needed for retrieval.
- `TagPool.register()` remains available for operator-supplied vocabulary overrides at runtime.

---

## Section 3: Mindscape Synthesis

### Problem

The Analyzer runs extraction immediately after chunk retrieval. It has no document-wide awareness — each LLM call sees 8 sections with no knowledge of what the book is broadly about. For a VtM sourcebook, the LLM does not know it is reading a vampire game until the extraction prompt, which is too late to guide categorization.

### Change

Add a synthesis pass in `Analyzer.analyze_source()` **before** extraction producing three artifact types.

#### New schemas (`knowledge_packs.py`)

All fields are optional and backward-compatible with existing packs.

```python
class ChunkSummaryArtifact(BaseModel):
    chunk_id: str
    chunk_index: int
    source_ref: str | None
    summary: str          # 1–2 sentences: what this chunk is about
    confidence: float = 0.0
    tags: list[str] = []

class SectionSummaryArtifact(BaseModel):
    section_key: str
    heading_path: list[str]
    chunk_ids: list[str]
    summary: str          # paragraph: what this section covers
    semantic_category: str | None
    confidence: float = 0.0

class SourceMindscapeArtifact(BaseModel):
    source_name: str
    summary: str              # 3–5 sentences: what this source is
    themes: list[str]         # ["vampire politics", "gothic horror"]
    taxonomy_hints: list[str] # ["Clan", "Discipline", "Path of Enlightenment"]
    system_name: str | None
    confidence: float = 0.0
```

`KnowledgePackCreate` and `KnowledgePackUpdate` gain optional fields:
```python
chunk_summaries: list[ChunkSummaryArtifact] = []
section_summaries: list[SectionSummaryArtifact] = []
source_mindscape: SourceMindscapeArtifact | None = None
```

#### New prompts (`prompts/analyzer.py`)

```python
class SectionSummarySignature(dspy.Signature):
    """Summarize what a single document section is about."""
    heading_path: str
    section_text: str
    → summary: str          # 1–3 sentences, factual, no inference
    → themes: list[str]

class SourceMindscapeSynthesisSignature(dspy.Signature):
    """Synthesize a source-level semantic frame from all section summaries."""
    section_summaries: str   # formatted list of (heading_path, summary) pairs
    source_name: str
    → global_summary: str
    → themes: list[str]
    → taxonomy_hints: list[str]
    → system_name: str | None
```

#### Revised `analyze_source()` flow

```
1. Section retrieval        (existing)
2. Section classification   (existing)
3. [NEW] synthesize_mindscape()
      → section summaries    (batch, LIGHT, one per section)
      → source mindscape     (HEAVY, all section summaries as input)
      → persist to KnowledgePack
      → set source_profile_context = mindscape summary + taxonomy_hints
4. Game system detection    (existing, now mindscape-guided)
5. Batched extraction       (existing, now mindscape-guided)
```

The `SourceMindscapeArtifact.summary + taxonomy_hints` replace the current `source_profile_context` string injected into every extraction call. The LLM knows "this is Vampire: the Masquerade 20th Anniversary — gothic horror TTRPG, d10 dice pools, Clans / Disciplines / Paths" before it reads a single extraction section.

#### Helpers (`utils/analyzer_support.py`)

- `build_section_summary_inputs(sections)` — formats sections for batch summarization
- `format_mindscape_context(mindscape)` — produces the injected context string
- `persist_mindscape_artifacts(pack_id, chunk_summaries, section_summaries, mindscape)` — single call, keeps `analyze_source()` clean

---

## Section 4: Structured Output

### Problem

All extraction signatures output free-text pipe-delimited format (`ENTITY | name | type | ...`). Parsers in `parsers/analyzer_parsers.py` use regex to extract fields. LLM deviations (newline mid-field, missing pipe, reordered columns) cause silent parse failures producing garbage items.

### Change

Replace pipe-delimited `dspy.OutputField` strings with `dspy.TypedChainOfThought` backed by the Pydantic models already defined in `knowledge_packs.py`.

#### Updated `BatchedExtractionSignature`

```python
class BatchedExtractionSignature(dspy.Signature):
    sections_context: str = dspy.InputField(...)
    source_name: str = dspy.InputField(...)
    known_graph_context: str = dspy.InputField(...)
    source_profile_context: str = dspy.InputField(...)
    # Typed outputs — schema enforced by DSPy at framework level
    axioms: list[ExtractedAxiom] = dspy.OutputField(...)
    entities: list[ExtractedEntityArchetype] = dspy.OutputField(...)
    lore_facts: list[ExtractedLoreFact] = dspy.OutputField(...)
```

DSPy `TypedChainOfThought` enforces the Pydantic schema automatically — invalid output triggers an internal retry with a schema-correction prompt, without custom parser code.

The same pattern applies to `GameRuleExtractionSignature`, `CharacterSheetExtractionSignature`, `NPCExtractionModule`, and `RelationshipInferenceModule`.

#### Parser removal

`parsers/analyzer_parsers.py` — `parse_entities()`, `parse_axioms()`, `parse_lore_facts()`, `parse_game_rules()`, `parse_character_sheet()`, `parse_npc_data()`, `parse_relationships()` — can be **deleted**. The Pydantic models already exist in `knowledge_packs.py`.

#### Game system detection fix

- Raise `_DETECTION_SAMPLE_SIZE` from 12 → 48 chunks
- Switch `GameSystemDetectionModule` from `ModelRole.LIGHT` to `ModelRole.HEAVY`
- Detection output becomes typed: `is_game_system: bool`, `system_name: str | None`, `confidence: float`
- The mindscape `system_name` field pre-confirms detection in most cases; the detection call becomes a verification step

---

## Section 5: Data Model Generalizations

### 5.1 Replace `ResourceDefinition` with `TrackDefinition`

All bounded numeric tracks — hit points, blood pools, moral tracks, stress tracks, corruption — are the same mechanic with different names. `ResourceDefinition` and the previously proposed `MoralTrack` are unified into one model.

```python
class ThresholdEffect(BaseModel):
    value: int
    direction: Literal["at_or_below", "at_or_above", "exactly"]
    effect: str           # "Enter Frenzy", "Gain Disorder", "Unconscious"

class TrackDefinition(BaseModel):
    name: str                  # "Blood Pool", "Humanity", "Stress", "HP"
    abbreviation: str | None
    min_value: int             # usually 0
    max_value: int | None      # None = formula-driven
    max_formula: str | None    # "10 - (Generation - 5)" for VtM blood
    default_value: int | str
    track_type: Literal[
        "resource",      # spend-down pool (Blood, HP, spell slots)
        "degradation",   # lose as consequence (Humanity, Sanity, Corruption)
        "stress",        # gain as consequence (Blades Stress, Void corruption)
        "advancement",   # spend to improve (XP, beats)
        "custom"
    ]
    gain_conditions: list[str]    # "Feed on a mortal", "Long rest"
    loss_conditions: list[str]    # "Commit a dehumanizing act", "Take damage"
    spend_conditions: list[str]   # "Spend 1 to activate a Discipline"
    recovery_rules: list[str]
    threshold_effects: list[ThresholdEffect]
    depleted_effect: str | None
    maxed_effect: str | None
```

`EmbeddedGameSystem.resources: list[ResourceDefinition]` → `tracks: list[TrackDefinition]`

**Covers:** D&D HP, VtM Blood Pool / Humanity / Willpower / Generation, Death in Space BDY / Void, 7th Sea Wounds / Reputation, Zweihänder Corruption / Peril, Blades Stress, Call of Cthulhu Sanity.

### 5.2 Add `TieredAbilitySystem`

Many systems have named ability groups where each level unlocks a distinct power with its own cost and effect. These have no current representation beyond flattened `GameRule` descriptions.

```python
class AbilityTier(BaseModel):
    tier: int                       # 1–5 (VtM), 1–9 (D&D spells), 1–3 (Zweihänder)
    name: str                       # "The Forgetful Mind", "Fireball"
    cost: str | None                # "2 Blood Points", "3rd-level spell slot"
    effect: str
    prerequisites: list[str]        # "Dominate 2", "Intelligence 13"
    duration: str | None
    roll: str | None                # "Manipulation + Dominate vs Wits + 3"

class TieredAbilitySystem(BaseModel):
    name: str                       # "Dominate", "Evocation", "Sorcery: Glamour"
    parent_category: str | None     # "Discipline", "Spell School", "Sorcery Style"
    tiers: list[AbilityTier]
    max_tier: int
    acquisition_rule: str | None    # "Learned with XP at current_tier × 5"
    linked_track: str | None        # "Blood Pool" — which track fuels this
    access_restriction: str | None  # "Nosferatu only", "Glamour bloodline"
```

`EmbeddedGameSystem` gains `tiered_abilities: list[TieredAbilitySystem]`.

**Covers:** VtM Disciplines, D&D spell levels + school specializations, 7th Sea Sorcery styles, Zweihänder talent tiers, Lancer license ranks, PbtA moves.

### 5.3 Add `AdvantageDefinition`

Character-sheet picks with a point cost and discrete effect — neither skills, resources, nor world entities.

```python
class AdvantageDefinition(BaseModel):
    name: str
    cost: int | None          # positive = merit/advantage, negative = flaw/disadvantage
    category: str             # "merit", "flaw", "advantage", "trait", "hubris", "background"
    effect: str
    prerequisites: list[str]
    mutually_exclusive: list[str]  # names of incompatible picks
    tags: list[str]
```

`EmbeddedGameSystem` gains `advantages: list[AdvantageDefinition]`.

**Covers:** VtM Merits & Flaws, 7th Sea Advantages / Hubris, Zweihänder Traits, D&D Feats (as optional picks with prerequisites).

### 5.4 Generalize `CoreMechanic` → `ResolutionMechanic`

`CoreMechanic` captures the dice formula but not how difficulty scales or what success degrees mean. The Narrator cannot adjudicate a roll without this.

```python
class SuccessDegree(BaseModel):
    threshold: str     # "1 success", "3+ raises", "margin ≥ 30"
    label: str         # "partial", "full", "critical"
    effect: str        # "succeed with complication", "full effect", "exceptional result"

class ResolutionMechanic(BaseModel):
    dice_formula: str                 # "roll Xd10", "1d20 + modifier", "d100"
    mechanic_type: CoreMechanicType   # existing enum: D20, DICE_POOL, PERCENTILE, etc.
    difficulty_model: Literal[
        "fixed_dc",          # D&D: beat a set number
        "variable_difficulty",# VtM: difficulty 4–9 set by ST
        "opposed",           # both sides roll, compare
        "raises",            # 7th Sea: group dice into sets of 10
        "margin",            # Zweihänder: how far you beat/miss the target
        "narrative"          # no difficulty, effect narrated
    ]
    difficulty_range: str | None      # "DC 5–30", "Difficulty 4–9"
    success_degrees: list[SuccessDegree]
    success_type: SuccessType         # existing enum
    critical_success: str | None
    critical_failure: str | None
    consequence_on_failure: str | None  # "complication", "position worsens", "harm"
    complication_mechanic: str | None   # "7th Sea Opportunities", "devil's bargain"
```

`EmbeddedGameSystem.core_mechanic: CoreMechanic` → `resolution: ResolutionMechanic`.

### 5.5 Add `DamageModel`

Damage types have mechanically different healing rates and resistance rules. Currently `NPCAttack.damage` is a string — the Narrator cannot adjudicate damage type interactions without this structure.

```python
class DamageType(BaseModel):
    name: str                     # "Lethal", "Fire", "Aggravated", "Dramatic Wound"
    healing_rate: str             # "1 box per day of rest", "1 per Long Rest"
    healing_requires: str | None  # "Aggravated requires 1 Willpower + 1 week"
    resisted_by: str | None       # "Constitution save", "Fortitude", "armour value"
    lethality: Literal["nonlethal", "lethal", "aggravated", "instant_kill"]
    bypasses: list[str]           # ["natural armour", "damage resistance"]

class DamageModel(BaseModel):
    damage_types: list[DamageType]
    damage_track: str             # "Wound boxes", "HP pool", "Dramatic Wounds"
    incapacitated_at: str         # "0 HP", "3 Dramatic Wounds", "BDY 0"
    death_condition: str          # "0 HP + failed death save", "Aggravated fills last box"
```

`EmbeddedGameSystem` gains `damage_model: DamageModel | None`.

### 5.6 Add `ConditionDefinition`

Status effects are reused constantly at runtime. The Narrator needs structured mechanical effects, not a prose paragraph buried in `GameRule.description`.

```python
class ConditionDefinition(BaseModel):
    name: str                       # "Frenzy", "Prone", "Broken", "Frightened"
    trigger: str                    # "Fail Humanity check", "Knocked down"
    mechanical_effects: list[str]   # ["Cannot use Disciplines", "-1 die to all rolls"]
    ends_when: str                  # "Willpower roll at diff 6", "Use action to stand"
    stackable: bool
    source_ref: str | None
```

`EmbeddedGameSystem` gains `conditions: list[ConditionDefinition]`.

### 5.7 Add `ActionEconomy`

Action economy defines the turn skeleton the Narrator uses to sequence every combat round. Currently absorbed into `GameRule` type `ACTION` as prose.

```python
class ActionType(BaseModel):
    name: str                    # "Action", "Bonus Action", "Simple Action", "Free Action"
    count_per_turn: int | str    # 1, 2, "unlimited", "until Raises spent"
    can_be_used_for: list[str]   # ["attack", "spell", "skill check", "movement"]
    triggers_on: str | None      # "any creature's turn" for Reaction

class ActionEconomy(BaseModel):
    action_types: list[ActionType]
    turn_structure: str          # "each combatant takes one turn per round in initiative order"
    initiative_model: str        # "d20+DEX at combat start", "opposed DEX check", "cards"
    surprise_rules: str | None
```

`EmbeddedGameSystem` gains `action_economy: ActionEconomy | None`.

### 5.8 Generalize `AdvancementSystem` → `AdvancementModel`

The existing `AdvancementSystem` is XP-table centric (D&D style). VtM spends XP directly on targets at per-item costs; 7th Sea uses story beats; Zweihänder uses profession tiers. All are instances of "currency earned by condition, spent on specific targets."

```python
class AdvancementCurrency(BaseModel):
    name: str              # "XP", "Beats", "Freebie Points", "Prestige"
    earn_conditions: list[str]   # "per session", "per story beat", "per scene"

class AdvancementTarget(BaseModel):
    target_type: str       # "ability_tier", "attribute", "skill", "track_max", "level"
    target_name: str | None  # None = applies to all of target_type
    cost_formula: str      # "current_tier × 5", "flat 3", "10 - current_rating"
    prerequisites: list[str]
    max_purchases: int | None

class AdvancementModel(BaseModel):
    currencies: list[AdvancementCurrency]
    targets: list[AdvancementTarget]
    uses_levels: bool        # False for VtM/7th Sea, True for D&D/Zweihänder
    max_level: int | None
    progression_table: list[AdvancementEntry]  # kept from existing schema, empty if not level-based
```

`EmbeddedGameSystem.character_creation.advancement: AdvancementSystem` → `AdvancementModel`.

### 5.9 Add `RecoveryModel`

Rest/recovery is system-defining. Currently absorbed into `TrackDefinition.recovery_rules: list[str]` (prose). Structured recovery lets the Narrator answer "how does this character heal?" without parsing prose.

```python
class RecoveryEvent(BaseModel):
    name: str              # "Long Rest", "Daysleep", "Feed", "Scene End"
    duration: str          # "8 hours", "daytime", "1 round"
    restores: list[str]    # ["HP to max", "all spell slots", "1 Willpower dot"]
    requires: str | None   # "safe location", "consume 1 Blood Point"
    available_when: str | None  # "not in combat", "during downtime only"
```

`EmbeddedGameSystem` gains `recovery_model: RecoveryModel | None`.

---

## Section 6: Graph and Storage Architecture

### Current split (correct, incomplete)

| Data | Storage | Rationale |
|---|---|---|
| World entities (characters, factions, axioms, lore facts) | Neo4j | traversal across world state |
| System definitions (rules, attributes, mechanics) | MongoDB | lookup by system |
| Ingestion artifacts (jobs, packs, documents) | MongoDB | operational/transient |

### What is missing

**Mechanic-to-entity relationships** have nowhere to live. The Narrator cannot answer "what can a Nosferatu do in this situation?" without traversing from the entity to its available mechanics and their trigger conditions.

### Addition: thin mechanic reference nodes in Neo4j

MongoDB remains the **source of truth** for full mechanic definitions. Neo4j gains **thin reference nodes** — just `name` + `system_id` — whose purpose is to serve as traversal endpoints.

#### New Neo4j node labels

| Label | Fields | Purpose |
|---|---|---|
| `:AbilitySystem` | `name`, `system_id`, `parent_category` | Discipline, Spell School, Sorcery Style |
| `:Track` | `name`, `system_id`, `track_type` | Blood Pool, Humanity, HP, Stress |
| `:Condition` | `name`, `system_id` | Frenzy, Prone, Frightened |

#### New Neo4j relationship types

```cypher
// Entity-to-mechanic access
(:Lineage {name: "Nosferatu"})-[:HAS_ACCESS_TO]->(:AbilitySystem {name: "Obfuscate"})
(:Lineage {name: "Nosferatu"})-[:HAS_ACCESS_TO]->(:AbilitySystem {name: "Animalism"})

// Track trigger chains (runtime Narrator adjudication)
(:Track {name: "BloodHunger"})-[:TRIGGERS_AT {threshold: 5}]->(:Condition {name: "Frenzy"})
(:Condition {name: "Frenzy"})-[:RESISTED_BY]->(:Track {name: "Willpower"})

// Prerequisite chains (character progression)
(:AbilityTier {name: "Dominate", tier: 3})-[:REQUIRES]->(:AbilityTier {name: "Dominate", tier: 2})

// Runtime entity state
(:EntityInstance)-[:HAS_CONDITION]->(:Condition)
(:EntityInstance)-[:HAS_ABILITY {tier: 3}]->(:AbilitySystem)
(:EntityInstance)-[:TRACK_VALUE {current: 7}]->(:Track)
```

#### CanonKeeper additions

CanonKeeper gains authority to write `:AbilitySystem`, `:Track`, and `:Condition` nodes. These are written when a KnowledgePack containing a detected game system is applied. Full definitions remain in MongoDB; Neo4j nodes are written with only the fields needed for traversal.

New file: `packages/data-layer/src/monitor_data/tools/neo4j_tools/mechanics.py`

Functions:
- `neo4j_create_ability_system(params)` — authority: CanonKeeper
- `neo4j_create_track(params)` — authority: CanonKeeper
- `neo4j_create_condition(params)` — authority: CanonKeeper
- `neo4j_link_entity_to_ability(entity_id, ability_system_name)` — authority: CanonKeeper

### Persistence rule

The KnowledgePack is the **canonical storage home** for all mechanic definitions and ingestion artifacts. Neo4j stores only traversal-oriented projections — never duplicate definition text.

---

## Section 7: Extraction Prompt Updates

Because Section 4 replaces all pipe-delimited output with typed DSPy, the mechanic extraction follows the same pattern. When the source profile indicates a game system, the extraction signatures gain additional typed output fields:

#### `GameRuleExtractionSignature` additions

```python
class GameRuleExtractionSignature(dspy.Signature):
    section_context: str = dspy.InputField(...)
    system_name: str = dspy.InputField(...)
    source_profile_context: str = dspy.InputField(...)
    # Existing
    rules: list[GameRule] = dspy.OutputField(...)
    # New typed fields
    tracks: list[TrackDefinition] = dspy.OutputField(
        desc="Bounded numeric tracks found in this section (HP, Blood Pool, Humanity, Stress, etc.)"
    )
    tiered_abilities: list[TieredAbilitySystem] = dspy.OutputField(
        desc="Named ability systems with ranked powers (Disciplines, Spell Schools, Sorcery styles, etc.)"
    )
    conditions: list[ConditionDefinition] = dspy.OutputField(
        desc="Status effects with trigger conditions and mechanical consequences"
    )
    advantages: list[AdvantageDefinition] = dspy.OutputField(
        desc="Character-sheet picks with costs and effects (Merits, Flaws, Advantages, Traits)"
    )
```

The `Analyzer` aggregates these typed outputs across all rule-section batches and writes them into `EmbeddedGameSystem` on the KnowledgePack. No separate parsing step — DSPy enforces the schema.

---

## Section 8: Chunk Size Increase

Current: 512 tokens, 10% overlap.
Revised: **1024 tokens, 10% overlap** for documents with confirmed game system content (detected via source profile during indexing).

TTRPG rulebook sections — stat blocks, discipline descriptions, procedure steps — routinely span 800–1500 tokens. 512-token chunks fragment coherent rule descriptions across multiple chunks, forcing the Analyzer to see incomplete rules. Raising to 1024 keeps most single rules or entries intact while staying within Qdrant payload limits.

Plain text, markdown, and session notes retain the 512-token default.

---

## File-Level Change Summary

### New files
- `packages/data-layer/src/monitor_data/tools/neo4j_tools/mechanics.py` — thin mechanic node writes

### Modified files

| File | Change |
|---|---|
| `packages/data-layer/src/monitor_data/tools/ingest_tools.py` | Add `extract_pdf_structure()`, `SectionBlock` dataclass, raise chunk size to 1024 for rulebooks |
| `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py` | Add `ChunkSummaryArtifact`, `SectionSummaryArtifact`, `SourceMindscapeArtifact`; add fields to `KnowledgePackCreate`/`KnowledgePackUpdate` |
| `packages/data-layer/src/monitor_data/schemas/game_systems.py` | Replace `ResourceDefinition` with `TrackDefinition`; add `TieredAbilitySystem`, `AbilityTier`, `AdvantageDefinition`, `ResolutionMechanic`, `SuccessDegree`, `DamageModel`, `DamageType`, `ConditionDefinition`, `ActionEconomy`, `ActionType`, `AdvancementModel`, `AdvancementCurrency`, `AdvancementTarget`, `RecoveryModel`, `RecoveryEvent`; update `EmbeddedGameSystem` |
| `packages/agents/src/monitor_agents/prompts/analyzer.py` | Add `SectionCategorizationSignature/Module`, `SectionSummarySignature`, `SourceMindscapeSynthesisSignature`; convert all extraction signatures to typed DSPy output |
| `packages/agents/src/monitor_agents/analyzer.py` | Add `synthesize_mindscape()` pass; raise `_DETECTION_SAMPLE_SIZE` to 48; switch detection to HEAVY model; remove pipe-format parsing calls |
| `packages/agents/src/monitor_agents/utils/analyzer_support.py` | Add `build_section_summary_inputs()`, `format_mindscape_context()`, `persist_mindscape_artifacts()` |
| `packages/agents/src/monitor_agents/indexer.py` | Call `extract_pdf_structure()` pre-pass; call `SectionCategorizationModule` per section; emit `heading_path` + `section_depth` in Qdrant payload |
| `packages/agents/src/monitor_agents/canonkeeper.py` | Add mechanic node write calls after game system application |

### Deleted files / removals
- `packages/agents/src/monitor_agents/parsers/analyzer_parsers.py` — all pipe-format parsers removed (replaced by typed DSPy output)

---

## Testing

Tests follow existing layer-separation patterns.

### data-layer tests
- `test_ingest_tools.py` — `extract_pdf_structure()` with and without bookmarks, fallback to heuristic, chunk size routing
- `test_knowledge_packs.py` — schema round-trips for new artifact types, backward compat with old packs (no new required fields)
- `test_game_systems.py` — `TrackDefinition`, `TieredAbilitySystem`, `AdvantageDefinition`, `ResolutionMechanic`, `ConditionDefinition`, `ActionEconomy`, `AdvancementModel`, `RecoveryModel` all have validation tests
- `test_neo4j_tools_mechanics.py` — mechanic node write/read round-trips

### agents tests
- `test_indexer.py` — section categorization path (LLM mock), `heading_path` in Qdrant payload
- `test_analyzer.py` — mindscape synthesis pass fires before extraction; typed output path; detection uses 48 chunks
- `test_analyzer_support.py` — `build_section_summary_inputs()`, `format_mindscape_context()`, `persist_mindscape_artifacts()`

### Acceptance criteria for the four test PDFs
After full ingestion:
1. `KnowledgePack.source_mindscape` is non-null and contains correct `system_name` and `taxonomy_hints`
2. `KnowledgePack.game_system_data` has non-empty `tracks`, `tiered_abilities`, `conditions`
3. `KnowledgePack.entity_archetypes` contains correct lineages/classes with proper `parent_entity_name`
4. `KnowledgePack.axioms` are world truths, not rule descriptions
5. Neo4j contains `:AbilitySystem` nodes with `:HAS_ACCESS_TO` edges from lineage nodes after CanonKeeper apply

---

## Relation to Futures Docs

This spec implements **Phase 1** of `INGESTION_FIRST_CONTEXTUAL_RETRIEVAL_PLAN.md` (mindscape-aware ingestion artifacts). Phases 2–5 (situated retrieval, source-scope routing, query-aware graph traversal, conversational specialization) are unaffected and remain planned. The semantic artifacts produced here (`ChunkSummaryArtifact`, `SectionSummaryArtifact`, `SourceMindscapeArtifact`) are the substrate those later phases depend on.
