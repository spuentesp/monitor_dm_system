# Ingestion Revamp Implementation Plan

> **Status:** ✅ All 17 tasks committed on `feat/ingestion-revamp` (2026-04-14).
> Checkboxes below are preserved for reference; all steps are complete.
>
> **For agentic workers:** This plan is FINISHED. Refer to the design spec at `docs/superpowers/specs/2026-04-13-ingestion-revamp-design.md` for architecture context.

**Goal:** Replace the brittle, keyword-tagged ingestion pipeline with a three-pass approach that produces correct KnowledgePacks for any TTRPG system.

**Architecture:** Pass 1 extracts PDF structure (bookmark tree → section hierarchy). Pass 2 enriches sections with LLM semantic categories and chunk/section summaries (mindscape synthesis). Pass 3 runs typed-DSPy extraction against the source-level semantic frame, replacing pipe-delimited parsers. New generalized mechanic schemas (TrackDefinition, TieredAbilitySystem, etc.) replace undersized models, and CanonKeeper writes thin mechanic reference nodes to Neo4j after apply.

**Tech Stack:** PyMuPDF (`fitz`), DSPy `ChainOfThought` (standard — `TypedChainOfThought` does not exist in DSPy 3.1.3; typed list output fields work natively), Pydantic v2, MongoDB (KnowledgePack source-of-truth), Neo4j (thin traversal nodes), Qdrant (vector payload enrichment)

---

## Phase 1 — Generalized Game System Schemas (`game_systems.py`)

### Task 1: Add `TrackDefinition` and `ThresholdEffect`

**Files:**
- Modify: `packages/data-layer/src/monitor_data/schemas/game_systems.py`
- Test: `packages/data-layer/tests/test_tools/test_game_system_tools.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/data-layer/tests/test_tools/test_game_system_tools.py
# Add at bottom of file:

from monitor_data.schemas.game_systems import (
    TrackDefinition,
    ThresholdEffect,
)

def test_track_definition_resource_type():
    track = TrackDefinition(
        name="Blood Pool",
        min_value=0,
        max_value=10,
        default_value=10,
        track_type="resource",
        gain_conditions=["Feed on a mortal"],
        loss_conditions=[],
        spend_conditions=["Spend 1 to activate a Discipline"],
        recovery_rules=[],
        threshold_effects=[],
    )
    assert track.track_type == "resource"
    assert track.max_value == 10

def test_track_definition_degradation_with_thresholds():
    threshold = ThresholdEffect(
        value=3,
        direction="at_or_below",
        effect="Enter Frenzy",
    )
    track = TrackDefinition(
        name="Humanity",
        min_value=0,
        max_value=10,
        default_value=7,
        track_type="degradation",
        gain_conditions=[],
        loss_conditions=["Commit a dehumanizing act"],
        spend_conditions=[],
        recovery_rules=[],
        threshold_effects=[threshold],
    )
    assert track.threshold_effects[0].effect == "Enter Frenzy"

def test_track_definition_max_formula():
    track = TrackDefinition(
        name="Blood Pool",
        min_value=0,
        max_value=None,
        max_formula="15 - (Generation - 5)",
        default_value=10,
        track_type="resource",
        gain_conditions=[],
        loss_conditions=[],
        spend_conditions=[],
        recovery_rules=[],
        threshold_effects=[],
    )
    assert track.max_value is None
    assert "Generation" in track.max_formula
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd packages/data-layer && python -m pytest tests/test_tools/test_game_system_tools.py::test_track_definition_resource_type -v
```
Expected: `ImportError` — `TrackDefinition` not yet defined.

- [ ] **Step 3: Add `ThresholdEffect` and `TrackDefinition` to `game_systems.py`**

Open `packages/data-layer/src/monitor_data/schemas/game_systems.py` and add after the existing imports and before `ResourceDefinition`:

```python
class ThresholdEffect(BaseModel):
    value: int
    direction: Literal["at_or_below", "at_or_above", "exactly"]
    effect: str


class TrackDefinition(BaseModel):
    name: str
    abbreviation: str | None = None
    min_value: int = 0
    max_value: int | None = None
    max_formula: str | None = None
    default_value: int | str = 0
    track_type: Literal["resource", "degradation", "stress", "advancement", "custom"]
    gain_conditions: list[str] = Field(default_factory=list)
    loss_conditions: list[str] = Field(default_factory=list)
    spend_conditions: list[str] = Field(default_factory=list)
    recovery_rules: list[str] = Field(default_factory=list)
    threshold_effects: list[ThresholdEffect] = Field(default_factory=list)
    depleted_effect: str | None = None
    maxed_effect: str | None = None
```

Keep `ResourceDefinition` as-is (backward compat — it is still used in `analyzer.py` and `mongodb_tools.py`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd packages/data-layer && python -m pytest tests/test_tools/test_game_system_tools.py::test_track_definition_resource_type tests/test_tools/test_game_system_tools.py::test_track_definition_degradation_with_thresholds tests/test_tools/test_game_system_tools.py::test_track_definition_max_formula -v
```
Expected: PASS ×3

- [ ] **Step 5: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/game_systems.py packages/data-layer/tests/test_tools/test_game_system_tools.py
git commit -m "feat(data-layer): add TrackDefinition and ThresholdEffect schemas"
```

---

### Task 2: Add `TieredAbilitySystem`, `AbilityTier`, `AdvantageDefinition`

**Files:**
- Modify: `packages/data-layer/src/monitor_data/schemas/game_systems.py`
- Test: `packages/data-layer/tests/test_tools/test_game_system_tools.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to test_game_system_tools.py:

from monitor_data.schemas.game_systems import (
    AbilityTier,
    TieredAbilitySystem,
    AdvantageDefinition,
)

def test_tiered_ability_system_disciplines():
    tier = AbilityTier(
        tier=2,
        name="The Forgetful Mind",
        cost="2 Blood Points",
        effect="Rearrange or remove memories",
        prerequisites=["Dominate 1"],
        duration="Permanent until disrupted",
        roll="Manipulation + Dominate vs Wits + 3",
    )
    system = TieredAbilitySystem(
        name="Dominate",
        parent_category="Discipline",
        tiers=[tier],
        max_tier=5,
        acquisition_rule="Spend XP equal to current tier × 5",
        linked_track="Blood Pool",
        access_restriction="Ventrue, Lasombra, Tremere only",
    )
    assert system.max_tier == 5
    assert system.tiers[0].tier == 2

def test_advantage_definition_flaw():
    adv = AdvantageDefinition(
        name="Prey Exclusion",
        cost=-1,
        category="flaw",
        effect="Cannot feed on a specific group; enter Frenzy if forced to",
        prerequisites=[],
        mutually_exclusive=[],
        tags=["feeding", "frenzy"],
    )
    assert adv.cost == -1
    assert adv.category == "flaw"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd packages/data-layer && python -m pytest tests/test_tools/test_game_system_tools.py::test_tiered_ability_system_disciplines -v
```
Expected: `ImportError`

- [ ] **Step 3: Add models to `game_systems.py`**

After `TrackDefinition`, add:

```python
class AbilityTier(BaseModel):
    tier: int
    name: str
    cost: str | None = None
    effect: str
    prerequisites: list[str] = Field(default_factory=list)
    duration: str | None = None
    roll: str | None = None


class TieredAbilitySystem(BaseModel):
    name: str
    parent_category: str | None = None
    tiers: list[AbilityTier] = Field(default_factory=list)
    max_tier: int
    acquisition_rule: str | None = None
    linked_track: str | None = None
    access_restriction: str | None = None


class AdvantageDefinition(BaseModel):
    name: str
    cost: int | None = None
    category: str  # "merit", "flaw", "advantage", "trait", "hubris", "background"
    effect: str
    prerequisites: list[str] = Field(default_factory=list)
    mutually_exclusive: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd packages/data-layer && python -m pytest tests/test_tools/test_game_system_tools.py::test_tiered_ability_system_disciplines tests/test_tools/test_game_system_tools.py::test_advantage_definition_flaw -v
```
Expected: PASS ×2

- [ ] **Step 5: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/game_systems.py packages/data-layer/tests/test_tools/test_game_system_tools.py
git commit -m "feat(data-layer): add TieredAbilitySystem, AbilityTier, AdvantageDefinition schemas"
```

---

### Task 3: Add `ResolutionMechanic`, `DamageModel`, `ConditionDefinition`, `ActionEconomy`, `AdvancementModel`, `RecoveryModel`

**Files:**
- Modify: `packages/data-layer/src/monitor_data/schemas/game_systems.py`
- Test: `packages/data-layer/tests/test_tools/test_game_system_tools.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to test_game_system_tools.py:

from monitor_data.schemas.game_systems import (
    SuccessDegree,
    ResolutionMechanic,
    DamageType,
    DamageModel,
    ConditionDefinition,
    ActionType,
    ActionEconomy,
    AdvancementCurrency,
    AdvancementTarget,
    AdvancementModel,
    RecoveryEvent,
    RecoveryModel,
)

def test_resolution_mechanic_dice_pool():
    deg = SuccessDegree(threshold="1 success", label="partial", effect="succeed with complication")
    mech = ResolutionMechanic(
        dice_formula="roll Xd10",
        mechanic_type="DICE_POOL",
        difficulty_model="variable_difficulty",
        difficulty_range="Difficulty 4–9",
        success_degrees=[deg],
        success_type="CUMULATIVE",
    )
    assert mech.difficulty_model == "variable_difficulty"
    assert mech.success_degrees[0].label == "partial"

def test_damage_model_vmt():
    dt = DamageType(
        name="Aggravated",
        healing_rate="1 box per week of rest",
        healing_requires="1 Willpower point",
        resisted_by="Fortitude",
        lethality="aggravated",
        bypasses=["natural armour"],
    )
    dm = DamageModel(
        damage_types=[dt],
        damage_track="Wound boxes",
        incapacitated_at="Health boxes filled",
        death_condition="Aggravated fills last box",
    )
    assert dm.damage_types[0].lethality == "aggravated"

def test_condition_definition():
    cond = ConditionDefinition(
        name="Frenzy",
        trigger="Fail Humanity check",
        mechanical_effects=["Cannot use Disciplines", "Must attack nearest creature"],
        ends_when="Willpower roll at diff 6",
        stackable=False,
    )
    assert not cond.stackable

def test_action_economy():
    action = ActionType(
        name="Simple Action",
        count_per_turn=2,
        can_be_used_for=["attack", "activate Discipline", "move"],
        triggers_on=None,
    )
    economy = ActionEconomy(
        action_types=[action],
        turn_structure="each combatant takes two simple actions per turn in initiative order",
        initiative_model="opposed DEX check at combat start",
    )
    assert economy.action_types[0].count_per_turn == 2

def test_advancement_model_xp_spend():
    currency = AdvancementCurrency(name="XP", earn_conditions=["per session", "per story beat"])
    target = AdvancementTarget(
        target_type="ability_tier",
        target_name="Dominate",
        cost_formula="current_tier × 5",
        prerequisites=["Storyteller approval"],
        max_purchases=None,
    )
    model = AdvancementModel(
        currencies=[currency],
        targets=[target],
        uses_levels=False,
        progression_table=[],
    )
    assert not model.uses_levels

def test_recovery_model():
    event = RecoveryEvent(
        name="Daysleep",
        duration="daytime",
        restores=["1 Bashing wound", "all Willpower"],
        requires="safe haven",
        available_when="not in combat",
    )
    model = RecoveryModel(events=[event])
    assert model.events[0].name == "Daysleep"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd packages/data-layer && python -m pytest tests/test_tools/test_game_system_tools.py::test_resolution_mechanic_dice_pool -v
```
Expected: `ImportError`

- [ ] **Step 3: Add models to `game_systems.py`**

After `AdvantageDefinition`, add:

```python
class SuccessDegree(BaseModel):
    threshold: str
    label: str
    effect: str


class ResolutionMechanic(BaseModel):
    dice_formula: str
    mechanic_type: CoreMechanicType
    difficulty_model: Literal[
        "fixed_dc", "variable_difficulty", "opposed", "raises", "margin", "narrative"
    ]
    difficulty_range: str | None = None
    success_degrees: list[SuccessDegree] = Field(default_factory=list)
    success_type: SuccessType
    critical_success: str | None = None
    critical_failure: str | None = None
    consequence_on_failure: str | None = None
    complication_mechanic: str | None = None


class DamageType(BaseModel):
    name: str
    healing_rate: str
    healing_requires: str | None = None
    resisted_by: str | None = None
    lethality: Literal["nonlethal", "lethal", "aggravated", "instant_kill"]
    bypasses: list[str] = Field(default_factory=list)


class DamageModel(BaseModel):
    damage_types: list[DamageType] = Field(default_factory=list)
    damage_track: str
    incapacitated_at: str
    death_condition: str


class ConditionDefinition(BaseModel):
    name: str
    trigger: str
    mechanical_effects: list[str] = Field(default_factory=list)
    ends_when: str
    stackable: bool = False
    source_ref: str | None = None


class ActionType(BaseModel):
    name: str
    count_per_turn: int | str
    can_be_used_for: list[str] = Field(default_factory=list)
    triggers_on: str | None = None


class ActionEconomy(BaseModel):
    action_types: list[ActionType] = Field(default_factory=list)
    turn_structure: str
    initiative_model: str
    surprise_rules: str | None = None


class AdvancementCurrency(BaseModel):
    name: str
    earn_conditions: list[str] = Field(default_factory=list)


class AdvancementTarget(BaseModel):
    target_type: str
    target_name: str | None = None
    cost_formula: str
    prerequisites: list[str] = Field(default_factory=list)
    max_purchases: int | None = None


class AdvancementModel(BaseModel):
    currencies: list[AdvancementCurrency] = Field(default_factory=list)
    targets: list[AdvancementTarget] = Field(default_factory=list)
    uses_levels: bool = False
    max_level: int | None = None
    progression_table: list[AdvancementEntry] = Field(default_factory=list)


class RecoveryEvent(BaseModel):
    name: str
    duration: str
    restores: list[str] = Field(default_factory=list)
    requires: str | None = None
    available_when: str | None = None


class RecoveryModel(BaseModel):
    events: list[RecoveryEvent] = Field(default_factory=list)
```

`AdvancementEntry` is the existing type used in `AdvancementSystem.progression_table`. Verify it exists in the file; if not, add `class AdvancementEntry(BaseModel): level: int; xp_required: int; bonus: str | None = None`.

- [ ] **Step 4: Update `EmbeddedGameSystem` to add the new optional fields**

Locate `class EmbeddedGameSystem` in `game_systems.py` and add these optional fields (keep all existing fields):

```python
# New optional fields — add after existing fields
tracks: list[TrackDefinition] = Field(default_factory=list)
tiered_abilities: list[TieredAbilitySystem] = Field(default_factory=list)
advantages: list[AdvantageDefinition] = Field(default_factory=list)
resolution: ResolutionMechanic | None = None
damage_model: DamageModel | None = None
conditions: list[ConditionDefinition] = Field(default_factory=list)
action_economy: ActionEconomy | None = None
advancement_model: AdvancementModel | None = None
recovery_model: RecoveryModel | None = None
```

- [ ] **Step 5: Run all game_system tests**

```bash
cd packages/data-layer && python -m pytest tests/test_tools/test_game_system_tools.py -v
```
Expected: all PASS (including existing tests — new fields are optional, no existing fields removed)

- [ ] **Step 6: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/game_systems.py packages/data-layer/tests/test_tools/test_game_system_tools.py
git commit -m "feat(data-layer): add ResolutionMechanic, DamageModel, ConditionDefinition, ActionEconomy, AdvancementModel, RecoveryModel; extend EmbeddedGameSystem"
```

---

## Phase 2 — Knowledge Pack Artifact Schemas

### Task 4: Add `ChunkSummaryArtifact`, `SectionSummaryArtifact`, `SourceMindscapeArtifact` to `knowledge_packs.py`

**Files:**
- Modify: `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`
- Test: `packages/data-layer/tests/` — create `test_knowledge_pack_artifacts.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/data-layer/tests/test_knowledge_pack_artifacts.py
from monitor_data.schemas.knowledge_packs import (
    ChunkSummaryArtifact,
    SectionSummaryArtifact,
    SourceMindscapeArtifact,
    KnowledgePackCreate,
)


def test_chunk_summary_artifact_minimal():
    artifact = ChunkSummaryArtifact(
        chunk_id="abc123",
        chunk_index=0,
        summary="Describes the Nosferatu clan's deformity and Obfuscate affinity.",
    )
    assert artifact.confidence == 0.0
    assert artifact.source_ref is None


def test_section_summary_artifact():
    artifact = SectionSummaryArtifact(
        section_key="chapter_3_clans_nosferatu",
        heading_path=["Chapter 3", "Clans", "Nosferatu"],
        chunk_ids=["a1", "a2"],
        summary="Details the Nosferatu, a clan of hideous vampires skilled in Obfuscate.",
        semantic_category="lineage",
    )
    assert artifact.heading_path[2] == "Nosferatu"


def test_source_mindscape_artifact():
    artifact = SourceMindscapeArtifact(
        source_name="Vampire: the Masquerade 20th Anniversary Edition",
        summary="Gothic horror TTRPG where players are vampires navigating politics and the Beast.",
        themes=["gothic horror", "vampire politics", "humanity vs Beast"],
        taxonomy_hints=["Clan", "Discipline", "Path of Enlightenment", "Frenzy"],
        system_name="Vampire: the Masquerade",
    )
    assert "Clan" in artifact.taxonomy_hints
    assert artifact.confidence == 0.0


def test_knowledge_pack_create_backward_compat_without_artifacts():
    # Old packs with no artifact fields must still deserialize cleanly.
    pack = KnowledgePackCreate(
        source_id="src1",
        source_name="Death in Space",
        axioms=[],
        entity_archetypes=[],
        lore_facts=[],
        relationships=[],
        source_profile=None,
        game_system_data=None,
    )
    assert pack.chunk_summaries == []
    assert pack.section_summaries == []
    assert pack.source_mindscape is None


def test_knowledge_pack_create_with_mindscape():
    mindscape = SourceMindscapeArtifact(
        source_name="Death in Space",
        summary="Bleak sci-fi OSR where characters are scavengers in a dying galaxy.",
        themes=["cosmic horror", "resource scarcity"],
        taxonomy_hints=["BDY", "Omens", "Void"],
        system_name="Death in Space",
    )
    pack = KnowledgePackCreate(
        source_id="src2",
        source_name="Death in Space",
        axioms=[],
        entity_archetypes=[],
        lore_facts=[],
        relationships=[],
        source_profile=None,
        game_system_data=None,
        source_mindscape=mindscape,
    )
    assert pack.source_mindscape.system_name == "Death in Space"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd packages/data-layer && python -m pytest tests/test_knowledge_pack_artifacts.py -v
```
Expected: `ImportError` or `ValidationError`

- [ ] **Step 3: Add artifact models to `knowledge_packs.py`**

Add before `KnowledgePackCreate`:

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
    system_name: str | None = None
    confidence: float = 0.0
```

Add to `KnowledgePackCreate` and `KnowledgePackUpdate`:

```python
chunk_summaries: list[ChunkSummaryArtifact] = Field(default_factory=list)
section_summaries: list[SectionSummaryArtifact] = Field(default_factory=list)
source_mindscape: SourceMindscapeArtifact | None = None
```

- [ ] **Step 4: Run tests**

```bash
cd packages/data-layer && python -m pytest tests/test_knowledge_pack_artifacts.py -v
```
Expected: PASS ×5

- [ ] **Step 5: Run full data-layer test suite to verify no regressions**

```bash
cd packages/data-layer && python -m pytest -v
```
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/knowledge_packs.py packages/data-layer/tests/test_knowledge_pack_artifacts.py
git commit -m "feat(data-layer): add ChunkSummaryArtifact, SectionSummaryArtifact, SourceMindscapeArtifact schemas; extend KnowledgePackCreate/Update"
```

---

## Phase 3 — PDF Structure Extraction

### Task 5: Add `SectionBlock` and `extract_pdf_structure()` to `ingest_tools.py`

**Files:**
- Modify: `packages/data-layer/src/monitor_data/tools/ingest_tools.py`
- Test: `packages/data-layer/tests/test_db/test_ingest_tools.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to packages/data-layer/tests/test_db/test_ingest_tools.py:

import io
import fitz  # PyMuPDF
from monitor_data.tools.ingest_tools import extract_pdf_structure, SectionBlock


def _make_pdf_with_toc() -> bytes:
    """Create an in-memory PDF with a two-level bookmark tree."""
    doc = fitz.open()
    page0 = doc.new_page()
    page0.insert_text((72, 72), "Chapter 1 text here.")
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Chapter 2 text here.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Combat rules text here.")
    toc = [
        [1, "Chapter 1", 1],
        [1, "Chapter 2", 2],
        [2, "Combat", 3],
    ]
    doc.set_toc(toc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_pdf_without_toc() -> bytes:
    """Create an in-memory PDF with no bookmarks but heading-like text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "COMBAT\n\nRoll a d20 to attack.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extract_pdf_structure_with_toc():
    pdf_bytes = _make_pdf_with_toc()
    sections = extract_pdf_structure(pdf_bytes)
    assert len(sections) >= 2
    # First section must carry the bookmark title
    names = [s.heading_path[-1] for s in sections]
    assert "Chapter 1" in names or "Chapter 2" in names


def test_extract_pdf_structure_section_block_fields():
    pdf_bytes = _make_pdf_with_toc()
    sections = extract_pdf_structure(pdf_bytes)
    first = sections[0]
    assert isinstance(first, SectionBlock)
    assert isinstance(first.heading_path, list)
    assert isinstance(first.depth, int)
    assert isinstance(first.page_start, int)
    assert isinstance(first.page_end, int)
    assert isinstance(first.text, str)


def test_extract_pdf_structure_fallback_no_toc():
    # PDF with no bookmarks → falls back to heuristic heading detection.
    pdf_bytes = _make_pdf_without_toc()
    sections = extract_pdf_structure(pdf_bytes)
    # Must return at least one section block even without a ToC.
    assert len(sections) >= 1
    assert all(isinstance(s, SectionBlock) for s in sections)


def test_extract_pdf_structure_heading_path_nesting():
    pdf_bytes = _make_pdf_with_toc()
    sections = extract_pdf_structure(pdf_bytes)
    # Depth-2 section ("Combat") must appear with depth 1 (0-indexed)
    combat_sections = [s for s in sections if "Combat" in s.heading_path]
    if combat_sections:
        assert combat_sections[0].depth == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd packages/data-layer && python -m pytest tests/test_db/test_ingest_tools.py::test_extract_pdf_structure_with_toc -v
```
Expected: `ImportError` — `extract_pdf_structure` not defined.

- [ ] **Step 3: Add `SectionBlock` dataclass and `extract_pdf_structure()` to `ingest_tools.py`**

Find the top of `ingest_tools.py` and add the import (fitz is already used in the file; add `dataclasses` if not present):

```python
from dataclasses import dataclass, field
```

Add `SectionBlock` after the imports section:

```python
@dataclass
class SectionBlock:
    heading_path: list[str]
    depth: int
    page_start: int
    page_end: int
    text: str
```

Add `extract_pdf_structure()` before `chunk_text()`:

```python
def extract_pdf_structure(pdf_bytes: bytes) -> list[SectionBlock]:
    """
    Extract PDF bookmark tree and assign page text to each section span.

    Uses fitz.get_toc() for heading hierarchy. If no bookmarks exist,
    falls back to _looks_like_heading() heuristic applied page-by-page.

    Returns list of SectionBlock ordered by page_start.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    toc = doc.get_toc(simple=False)  # [[level, title, page, ...], ...]

    if toc:
        sections: list[SectionBlock] = []
        for i, entry in enumerate(toc):
            level, title, page_1indexed = entry[0], entry[1], entry[2]
            page_start = page_1indexed - 1  # convert to 0-indexed

            # page_end = start of next entry at same or higher level, minus 1
            page_end = doc.page_count - 1
            for j in range(i + 1, len(toc)):
                if toc[j][0] <= level:
                    page_end = toc[j][2] - 2  # 1-indexed → 0-indexed, exclusive
                    break

            # Build heading_path from all ancestor titles at lower levels
            path: list[str] = []
            current_level = level
            for k in range(i - 1, -1, -1):
                if toc[k][0] < current_level:
                    path.insert(0, toc[k][1])
                    current_level = toc[k][0]
                    if current_level == 1:
                        break
            path.append(title)

            # Collect text from the page range
            text_parts: list[str] = []
            for p in range(max(0, page_start), min(doc.page_count, page_end + 1)):
                text_parts.append(doc[p].get_text())
            text = "\n".join(text_parts).strip()

            sections.append(
                SectionBlock(
                    heading_path=path,
                    depth=level - 1,
                    page_start=page_start,
                    page_end=page_end,
                    text=text,
                )
            )
        doc.close()
        return sections

    # Fallback: no bookmarks — use heuristic heading detection page by page
    sections = []
    current_heading: list[str] = ["(untitled)"]
    current_depth = 0
    current_start = 0
    current_texts: list[str] = []

    for page_num in range(doc.page_count):
        page = doc[page_num]
        page_text = page.get_text()
        lines = page_text.splitlines()

        for line in lines:
            stripped = line.strip()
            if stripped and _looks_like_heading(stripped):
                # Save previous section
                if current_texts:
                    sections.append(
                        SectionBlock(
                            heading_path=current_heading,
                            depth=current_depth,
                            page_start=current_start,
                            page_end=page_num,
                            text="\n".join(current_texts).strip(),
                        )
                    )
                current_heading = [stripped]
                current_depth = 0
                current_start = page_num
                current_texts = []
            else:
                current_texts.append(line)

    # Flush last section
    if current_texts or not sections:
        sections.append(
            SectionBlock(
                heading_path=current_heading,
                depth=current_depth,
                page_start=current_start,
                page_end=doc.page_count - 1,
                text="\n".join(current_texts).strip(),
            )
        )

    doc.close()
    return sections
```

- [ ] **Step 4: Run tests**

```bash
cd packages/data-layer && python -m pytest tests/test_db/test_ingest_tools.py -v
```
Expected: all PASS (both new tests and the two existing tests).

- [ ] **Step 5: Commit**

```bash
git add packages/data-layer/src/monitor_data/tools/ingest_tools.py packages/data-layer/tests/test_db/test_ingest_tools.py
git commit -m "feat(data-layer): add SectionBlock and extract_pdf_structure() with ToC and fallback heuristic"
```

---

### Task 6: Raise chunk size to 1024 tokens for rulebook sources in `ingest_tools.py`

**Files:**
- Modify: `packages/data-layer/src/monitor_data/tools/ingest_tools.py`
- Test: `packages/data-layer/tests/test_db/test_ingest_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to test_ingest_tools.py:

def test_chunk_text_uses_larger_size_for_rulebook():
    # A long block of rules text — should produce fewer, larger chunks for a rulebook.
    long_text = "COMBAT\n\n" + " ".join(["Roll a d20 to attack."] * 300)
    chunks_default = chunk_text(long_text, "some_doc", is_rulebook=False)
    chunks_rulebook = chunk_text(long_text, "some_doc", is_rulebook=True)
    # Rulebook chunks should be fewer (each larger).
    assert len(chunks_rulebook) <= len(chunks_default)


def test_chunk_text_is_rulebook_flag_default_false():
    # Without the flag, behavior is unchanged (512-token default).
    chunks = chunk_text("COMBAT\n\nShort text.", "book")
    assert chunks  # just verifies the signature still works without the flag
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/data-layer && python -m pytest tests/test_db/test_ingest_tools.py::test_chunk_text_uses_larger_size_for_rulebook -v
```
Expected: `TypeError` — `chunk_text` does not accept `is_rulebook`.

- [ ] **Step 3: Update `chunk_text()` signature and chunker size selection**

Locate `def chunk_text(` in `ingest_tools.py`. Add the `is_rulebook` parameter with a default of `False` and route the chunk size:

```python
_DEFAULT_CHUNK_SIZE = 512
_RULEBOOK_CHUNK_SIZE = 1024
_CHUNK_OVERLAP_RATIO = 0.10

def chunk_text(
    text: str,
    source_name: str,
    is_rulebook: bool = False,
) -> list[Document]:
    chunk_size = _RULEBOOK_CHUNK_SIZE if is_rulebook else _DEFAULT_CHUNK_SIZE
    overlap = int(chunk_size * _CHUNK_OVERLAP_RATIO)
    # ... rest of existing implementation, replacing hardcoded 512 with chunk_size
    # and hardcoded overlap with overlap
```

Replace the hardcoded `512` and `51` (or whatever the current overlap value is) with `chunk_size` and `overlap` respectively. Do not change any other logic.

- [ ] **Step 4: Run tests**

```bash
cd packages/data-layer && python -m pytest tests/test_db/test_ingest_tools.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/data-layer/src/monitor_data/tools/ingest_tools.py packages/data-layer/tests/test_db/test_ingest_tools.py
git commit -m "feat(data-layer): add is_rulebook flag to chunk_text, use 1024-token chunks for rulebook sources"
```

---

## Phase 4 — LLM Section Categorization at Index Time

### Task 7: Add `SectionCategorizationSignature` and `SectionCategorizationModule` to `prompts/analyzer.py`

**Files:**
- Modify: `packages/agents/src/monitor_agents/prompts/analyzer.py`
- Test: `packages/agents/tests/test_analyzer_support.py` (or create `packages/agents/tests/test_section_categorization.py`)

- [ ] **Step 1: Write the failing test**

```python
# packages/agents/tests/test_section_categorization.py
from unittest.mock import patch, MagicMock
from monitor_agents.prompts.analyzer import SectionCategorizationModule


def test_section_categorization_module_returns_valid_category():
    module = SectionCategorizationModule()
    mock_result = MagicMock()
    mock_result.category = "lineage"

    with patch.object(module, "_predictor") as mock_predictor:
        mock_predictor.return_value = mock_result
        result = module(
            heading_path="Chapter 3 > Clans > Nosferatu",
            section_excerpt="The Nosferatu are hideous vampires who hide in sewers.",
        )
    assert result.category == "lineage"


def test_section_categorization_module_general_fallback():
    module = SectionCategorizationModule()
    mock_result = MagicMock()
    mock_result.category = "general"

    with patch.object(module, "_predictor") as mock_predictor:
        mock_predictor.return_value = mock_result
        result = module(
            heading_path="Table of Contents",
            section_excerpt="1. Introduction ... 2. Character Creation ...",
        )
    assert result.category == "general"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/agents && python -m pytest tests/test_section_categorization.py -v
```
Expected: `ImportError` — `SectionCategorizationModule` not defined.

- [ ] **Step 3: Add `SectionCategorizationSignature` and `SectionCategorizationModule` to `prompts/analyzer.py`**

Open `packages/agents/src/monitor_agents/prompts/analyzer.py`. Locate the block where other `*Signature` and `*Module` classes are defined. Add:

```python
SEMANTIC_CATEGORIES = Literal[
    "power_system",
    "lineage",
    "character_archetype",
    "items_equipment",
    "combat_rules",
    "social_moral",
    "factions",
    "lore_history",
    "creatures_npc",
    "game_mechanics",
    "general",
]


class SectionCategorizationSignature(dspy.Signature):
    """Classify a document section into one universal semantic category for a TTRPG sourcebook."""

    heading_path: str = dspy.InputField(
        desc="Section heading path, e.g. 'Chapter 3 > Clans > Nosferatu'"
    )
    section_excerpt: str = dspy.InputField(
        desc="First ~200 characters of section body text"
    )
    category: SEMANTIC_CATEGORIES = dspy.OutputField(
        desc="One of the canonical semantic categories"
    )


class SectionCategorizationModule(_AnalyzerModule):
    _signature = SectionCategorizationSignature
    _role = ModelRole.LIGHT
```

`_AnalyzerModule` and `ModelRole` are already defined in `prompts/analyzer.py`. Use the same base class pattern as existing modules (e.g., `SectionClassifierModule`).

- [ ] **Step 4: Run tests**

```bash
cd packages/agents && python -m pytest tests/test_section_categorization.py -v
```
Expected: PASS ×2

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/prompts/analyzer.py packages/agents/tests/test_section_categorization.py
git commit -m "feat(agents): add SectionCategorizationSignature and SectionCategorizationModule (ModelRole.LIGHT)"
```

---

### Task 8: Update `Indexer` to call `extract_pdf_structure()` and `SectionCategorizationModule`

**Files:**
- Modify: `packages/agents/src/monitor_agents/indexer.py`
- Test: `packages/agents/tests/test_indexer.py`

- [ ] **Step 1: Write the failing tests**

Open `packages/agents/tests/test_indexer.py`. Add:

```python
# Add to existing test_indexer.py:

from unittest.mock import patch, MagicMock, call


def test_indexer_emits_heading_path_in_qdrant_payload(mock_qdrant, mock_mongo):
    """Chunks from a PDF with ToC must carry heading_path list in their metadata."""
    from monitor_agents.indexer import Indexer

    # Fake extract_pdf_structure to return two section blocks
    fake_section = MagicMock()
    fake_section.heading_path = ["Chapter 3", "Clans", "Nosferatu"]
    fake_section.depth = 1
    fake_section.text = "The Nosferatu are hideous vampires."
    fake_section.page_start = 30
    fake_section.page_end = 32

    with patch(
        "monitor_agents.indexer.extract_pdf_structure", return_value=[fake_section]
    ), patch(
        "monitor_agents.indexer.SectionCategorizationModule"
    ) as mock_cat_cls:
        mock_cat_instance = MagicMock()
        mock_cat_result = MagicMock()
        mock_cat_result.category = "lineage"
        mock_cat_instance.return_value = mock_cat_result
        mock_cat_cls.return_value = mock_cat_instance

        indexer = Indexer(qdrant_client=mock_qdrant, mongo_client=mock_mongo)
        indexer.index(source_id="src1", source_name="VtM20", content_bytes=b"%PDF", content_type="application/pdf")

    # Verify that the Qdrant upsert received a payload with heading_path
    upsert_calls = mock_qdrant.upsert.call_args_list
    assert upsert_calls, "Qdrant upsert should have been called"
    payloads = [pt.payload for call_args in upsert_calls for pt in call_args[1]["points"]]
    assert any("heading_path" in p for p in payloads)


def test_indexer_skips_categorization_when_tagpool_maps_cleanly(mock_qdrant, mock_mongo):
    """If TagPool returns a non-general category, LLM categorizer must not be called."""
    from monitor_agents.indexer import Indexer

    fake_section = MagicMock()
    fake_section.heading_path = ["Chapter 3", "Combat"]
    fake_section.depth = 0
    fake_section.text = "Roll a d20 to attack."
    fake_section.page_start = 10
    fake_section.page_end = 12

    with patch(
        "monitor_agents.indexer.extract_pdf_structure", return_value=[fake_section]
    ), patch(
        "monitor_agents.indexer.SectionCategorizationModule"
    ) as mock_cat_cls, patch(
        "monitor_agents.indexer.TagPool.classify",
        return_value="combat_rules",
    ):
        indexer = Indexer(qdrant_client=mock_qdrant, mongo_client=mock_mongo)
        indexer.index(source_id="src1", source_name="VtM20", content_bytes=b"%PDF", content_type="application/pdf")

    mock_cat_cls.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd packages/agents && python -m pytest tests/test_indexer.py::test_indexer_emits_heading_path_in_qdrant_payload -v
```
Expected: test failure (function not patching correctly or `extract_pdf_structure` not imported in indexer).

- [ ] **Step 3: Update `indexer.py`**

At the top of `indexer.py`, add imports:

```python
from monitor_data.tools.ingest_tools import extract_pdf_structure, SectionBlock
from monitor_agents.prompts.analyzer import SectionCategorizationModule
```

Locate the `index()` method. For PDF content (`content_type == "application/pdf"`), replace the current page-by-page extraction with:

```python
if content_type == "application/pdf":
    section_blocks = extract_pdf_structure(content_bytes)
    categorizer = SectionCategorizationModule()

    all_chunks = []
    for block in section_blocks:
        # TagPool pre-filter
        tag_category = TagPool.classify(block.heading_path[-1] if block.heading_path else "")
        if tag_category == "general":
            result = categorizer(
                heading_path=" > ".join(block.heading_path),
                section_excerpt=block.text[:200],
            )
            category = result.category
        else:
            category = tag_category

        # is_rulebook heuristic — true if category is rule-oriented
        is_rulebook = category in {
            "power_system", "character_archetype", "combat_rules",
            "game_mechanics", "creatures_npc",
        }
        chunks = chunk_text(block.text, source_name, is_rulebook=is_rulebook)
        for chunk in chunks:
            chunk.metadata["semantic_category"] = category
            chunk.metadata["heading_path"] = block.heading_path
            chunk.metadata["section_depth"] = block.depth
        all_chunks.extend(chunks)
else:
    all_chunks = chunk_text(content_bytes.decode("utf-8", errors="replace"), source_name)
```

Then continue with the existing Qdrant embedding + upsert loop over `all_chunks`.

- [ ] **Step 4: Run tests**

```bash
cd packages/agents && python -m pytest tests/test_indexer.py -v
```
Expected: all PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/indexer.py packages/agents/tests/test_indexer.py
git commit -m "feat(agents): update Indexer to use extract_pdf_structure and LLM section categorization; emit heading_path in Qdrant payload"
```

---

## Phase 5 — Mindscape Synthesis in Analyzer

### Task 9: Add mindscape synthesis helpers to `analyzer_support.py`

**Files:**
- Modify: `packages/agents/src/monitor_agents/utils/analyzer_support.py`
- Test: `packages/agents/tests/test_analyzer_support.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to packages/agents/tests/test_analyzer_support.py:

from monitor_agents.utils.analyzer_support import (
    build_section_summary_inputs,
    format_mindscape_context,
    persist_mindscape_artifacts,
)
from monitor_data.schemas.knowledge_packs import (
    ChunkSummaryArtifact,
    SectionSummaryArtifact,
    SourceMindscapeArtifact,
)


def test_build_section_summary_inputs_returns_list_of_dicts():
    sections = [
        {
            "heading_path": ["Chapter 3", "Clans", "Nosferatu"],
            "text": "The Nosferatu are hideous vampires who live in sewers.",
        },
        {
            "heading_path": ["Chapter 3", "Clans", "Tremere"],
            "text": "The Tremere are blood sorcerers who joined Clan Tremere.",
        },
    ]
    inputs = build_section_summary_inputs(sections)
    assert len(inputs) == 2
    assert "heading_path" in inputs[0]
    assert "section_text" in inputs[0]
    # section_text must be truncated to avoid token explosion
    assert len(inputs[0]["section_text"]) <= 2000


def test_build_section_summary_inputs_empty():
    assert build_section_summary_inputs([]) == []


def test_format_mindscape_context_produces_string():
    mindscape = SourceMindscapeArtifact(
        source_name="VtM20",
        summary="Gothic horror TTRPG about vampires.",
        themes=["gothic horror", "vampire politics"],
        taxonomy_hints=["Clan", "Discipline", "Frenzy"],
        system_name="Vampire: the Masquerade",
    )
    ctx = format_mindscape_context(mindscape)
    assert "VtM20" in ctx or "Vampire: the Masquerade" in ctx
    assert "Clan" in ctx


def test_persist_mindscape_artifacts_calls_pack_update(mock_mongo):
    from unittest.mock import MagicMock, patch

    mindscape = SourceMindscapeArtifact(
        source_name="VtM20",
        summary="Gothic horror TTRPG about vampires.",
        themes=[],
        taxonomy_hints=[],
        system_name="Vampire: the Masquerade",
    )

    with patch(
        "monitor_agents.utils.analyzer_support.update_knowledge_pack"
    ) as mock_update:
        persist_mindscape_artifacts(
            pack_id="pack1",
            chunk_summaries=[],
            section_summaries=[],
            mindscape=mindscape,
            mongo_client=mock_mongo,
        )
    mock_update.assert_called_once()
    call_kwargs = mock_update.call_args[1]
    assert call_kwargs["pack_id"] == "pack1"
    assert call_kwargs["update"].source_mindscape == mindscape
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd packages/agents && python -m pytest tests/test_analyzer_support.py::test_build_section_summary_inputs_returns_list_of_dicts -v
```
Expected: `ImportError`

- [ ] **Step 3: Add helpers to `analyzer_support.py`**

```python
# In packages/agents/src/monitor_agents/utils/analyzer_support.py

from monitor_data.schemas.knowledge_packs import (
    ChunkSummaryArtifact,
    SectionSummaryArtifact,
    SourceMindscapeArtifact,
    KnowledgePackUpdate,
)

_SECTION_TEXT_MAX_CHARS = 2000


def build_section_summary_inputs(
    sections: list[dict],
) -> list[dict]:
    """
    Format a list of section dicts into inputs for the section summarization module.

    Each dict must have keys: heading_path (list[str]), text (str).
    Returns list of dicts with heading_path (str) and section_text (str, truncated).
    """
    result = []
    for section in sections:
        heading_path = section.get("heading_path", [])
        text = section.get("text", "")
        result.append(
            {
                "heading_path": " > ".join(heading_path) if heading_path else "(untitled)",
                "section_text": text[:_SECTION_TEXT_MAX_CHARS],
            }
        )
    return result


def format_mindscape_context(mindscape: SourceMindscapeArtifact) -> str:
    """
    Produce the source-profile context string injected into every extraction prompt.
    """
    parts = [f"Source: {mindscape.source_name}"]
    if mindscape.system_name:
        parts.append(f"System: {mindscape.system_name}")
    parts.append(f"Summary: {mindscape.summary}")
    if mindscape.themes:
        parts.append(f"Themes: {', '.join(mindscape.themes)}")
    if mindscape.taxonomy_hints:
        parts.append(f"Key concepts / taxonomy: {', '.join(mindscape.taxonomy_hints)}")
    return "\n".join(parts)


def persist_mindscape_artifacts(
    *,
    pack_id: str,
    chunk_summaries: list[ChunkSummaryArtifact],
    section_summaries: list[SectionSummaryArtifact],
    mindscape: SourceMindscapeArtifact | None,
    mongo_client,
) -> None:
    """
    Write summary artifacts to the KnowledgePack in a single update call.
    """
    from monitor_data.tools.mongodb_tools import update_knowledge_pack

    update = KnowledgePackUpdate(
        chunk_summaries=chunk_summaries,
        section_summaries=section_summaries,
        source_mindscape=mindscape,
    )
    update_knowledge_pack(
        pack_id=pack_id,
        update=update,
        client=mongo_client,
    )
```

- [ ] **Step 4: Run tests**

```bash
cd packages/agents && python -m pytest tests/test_analyzer_support.py -v
```
Expected: all PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/utils/analyzer_support.py packages/agents/tests/test_analyzer_support.py
git commit -m "feat(agents): add build_section_summary_inputs, format_mindscape_context, persist_mindscape_artifacts helpers"
```

---

### Task 10: Add `SectionSummarySignature` and `SourceMindscapeSynthesisSignature` to `prompts/analyzer.py`

**Files:**
- Modify: `packages/agents/src/monitor_agents/prompts/analyzer.py`
- Test: `packages/agents/tests/test_section_categorization.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to packages/agents/tests/test_section_categorization.py:

from monitor_agents.prompts.analyzer import (
    SectionSummaryModule,
    SourceMindscapeSynthesisModule,
)


def test_section_summary_module_returns_summary_and_themes():
    module = SectionSummaryModule()
    mock_result = MagicMock()
    mock_result.summary = "Describes the Nosferatu, hideous vampires skilled in Obfuscate."
    mock_result.themes = ["vampires", "stealth", "lineage"]

    with patch.object(module, "_predictor") as mock_predictor:
        mock_predictor.return_value = mock_result
        result = module(
            heading_path="Chapter 3 > Clans > Nosferatu",
            section_text="The Nosferatu are hideous vampires who live in sewers.",
        )
    assert "Nosferatu" in result.summary
    assert "lineage" in result.themes


def test_source_mindscape_synthesis_module_returns_all_fields():
    module = SourceMindscapeSynthesisModule()
    mock_result = MagicMock()
    mock_result.global_summary = "Gothic horror TTRPG about vampires and politics."
    mock_result.themes = ["gothic horror"]
    mock_result.taxonomy_hints = ["Clan", "Discipline"]
    mock_result.system_name = "Vampire: the Masquerade"

    with patch.object(module, "_predictor") as mock_predictor:
        mock_predictor.return_value = mock_result
        result = module(
            section_summaries="Chapter 3 > Clans: Describes the 13 vampire clans.",
            source_name="VtM20",
        )
    assert result.system_name == "Vampire: the Masquerade"
    assert "Clan" in result.taxonomy_hints
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd packages/agents && python -m pytest tests/test_section_categorization.py::test_section_summary_module_returns_summary_and_themes -v
```
Expected: `ImportError`

- [ ] **Step 3: Add signatures and modules to `prompts/analyzer.py`**

```python
class SectionSummarySignature(dspy.Signature):
    """Summarize what a single TTRPG document section is about."""

    heading_path: str = dspy.InputField(
        desc="Section heading path, e.g. 'Chapter 3 > Clans > Nosferatu'"
    )
    section_text: str = dspy.InputField(desc="Full text of the section, up to 2000 characters")
    summary: str = dspy.OutputField(desc="1–3 sentences, factual, no inference or extrapolation")
    themes: list[str] = dspy.OutputField(desc="Up to 5 keywords capturing the section's topics")


class SectionSummaryModule(_AnalyzerModule):
    _signature = SectionSummarySignature
    _role = ModelRole.LIGHT


class SourceMindscapeSynthesisSignature(dspy.Signature):
    """
    Synthesize a source-level semantic frame from all section summaries.
    The output will guide all extraction prompts for this source.
    """

    section_summaries: str = dspy.InputField(
        desc="Formatted list of (heading_path, summary) pairs for all sections"
    )
    source_name: str = dspy.InputField(desc="The title of the source document")
    global_summary: str = dspy.OutputField(
        desc="3–5 sentences describing what this source is about, its genre, and primary focus"
    )
    themes: list[str] = dspy.OutputField(desc="Up to 10 overarching themes for this source")
    taxonomy_hints: list[str] = dspy.OutputField(
        desc="Key domain-specific terms that a reader would use to navigate this source (Clan, Discipline, Hubris, etc.)"
    )
    system_name: str | None = dspy.OutputField(
        desc="The TTRPG system this source is for, if identifiable; otherwise null"
    )


class SourceMindscapeSynthesisModule(_AnalyzerModule):
    _signature = SourceMindscapeSynthesisSignature
    _role = ModelRole.HEAVY
```

- [ ] **Step 4: Run tests**

```bash
cd packages/agents && python -m pytest tests/test_section_categorization.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/prompts/analyzer.py packages/agents/tests/test_section_categorization.py
git commit -m "feat(agents): add SectionSummarySignature/Module and SourceMindscapeSynthesisSignature/Module"
```

---

### Task 11: Add `synthesize_mindscape()` method to `Analyzer` and wire it into `analyze_source()`

**Files:**
- Modify: `packages/agents/src/monitor_agents/analyzer.py`
- Test: `packages/agents/tests/test_analyzer.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to packages/agents/tests/test_analyzer.py:

from unittest.mock import patch, MagicMock
from monitor_data.schemas.knowledge_packs import SourceMindscapeArtifact


def test_analyze_source_calls_synthesize_mindscape_before_extraction(mock_analyzer):
    """synthesize_mindscape must be called before _batched_extract_all."""
    call_order = []

    with patch.object(mock_analyzer, "synthesize_mindscape", wraps=lambda *a, **kw: call_order.append("mindscape") or MagicMock(spec=SourceMindscapeArtifact)) as mindscape_mock, \
         patch.object(mock_analyzer, "_batched_extract_all", wraps=lambda *a, **kw: call_order.append("extract") or {}) as extract_mock:
        mock_analyzer.analyze_source(source_id="s1", pack_id="p1")

    assert call_order.index("mindscape") < call_order.index("extract")


def test_synthesize_mindscape_returns_source_mindscape_artifact(mock_analyzer, mock_sections):
    with patch(
        "monitor_agents.analyzer.SectionSummaryModule"
    ) as mock_ss_cls, patch(
        "monitor_agents.analyzer.SourceMindscapeSynthesisModule"
    ) as mock_ms_cls:
        # Mock section summary module
        mock_ss = MagicMock()
        mock_ss_result = MagicMock()
        mock_ss_result.summary = "Describes Nosferatu clan."
        mock_ss_result.themes = ["lineage"]
        mock_ss.return_value = mock_ss_result
        mock_ss_cls.return_value = mock_ss

        # Mock global synthesis module
        mock_ms = MagicMock()
        mock_ms_result = MagicMock()
        mock_ms_result.global_summary = "Gothic horror TTRPG."
        mock_ms_result.themes = ["gothic horror"]
        mock_ms_result.taxonomy_hints = ["Clan", "Discipline"]
        mock_ms_result.system_name = "Vampire: the Masquerade"
        mock_ms.return_value = mock_ms_result
        mock_ms_cls.return_value = mock_ms

        artifact = mock_analyzer.synthesize_mindscape(
            sections=mock_sections,
            source_name="VtM20",
            pack_id="p1",
        )

    assert isinstance(artifact, SourceMindscapeArtifact)
    assert artifact.system_name == "Vampire: the Masquerade"
    assert "Clan" in artifact.taxonomy_hints


def test_synthesize_mindscape_persists_artifacts(mock_analyzer, mock_sections):
    with patch(
        "monitor_agents.analyzer.SectionSummaryModule"
    ) as mock_ss_cls, patch(
        "monitor_agents.analyzer.SourceMindscapeSynthesisModule"
    ) as mock_ms_cls, patch(
        "monitor_agents.analyzer.persist_mindscape_artifacts"
    ) as mock_persist:
        mock_ss = MagicMock()
        mock_ss.return_value = MagicMock(summary="s", themes=[])
        mock_ss_cls.return_value = mock_ss

        mock_ms = MagicMock()
        mock_ms.return_value = MagicMock(
            global_summary="g", themes=[], taxonomy_hints=[], system_name=None
        )
        mock_ms_cls.return_value = mock_ms

        mock_analyzer.synthesize_mindscape(
            sections=mock_sections, source_name="VtM20", pack_id="p1"
        )

    mock_persist.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd packages/agents && python -m pytest tests/test_analyzer.py::test_synthesize_mindscape_returns_source_mindscape_artifact -v
```
Expected: `AttributeError` — `synthesize_mindscape` not defined.

- [ ] **Step 3: Add `synthesize_mindscape()` to `Analyzer`**

In `packages/agents/src/monitor_agents/analyzer.py`, add imports at top (near line 85):

```python
from monitor_agents.prompts.analyzer import SectionSummaryModule, SourceMindscapeSynthesisModule
from monitor_agents.utils.analyzer_support import (
    build_section_summary_inputs,
    format_mindscape_context,
    persist_mindscape_artifacts,
)
from monitor_data.schemas.knowledge_packs import (
    ChunkSummaryArtifact,
    SectionSummaryArtifact,
    SourceMindscapeArtifact,
)
```

Add the method to `Analyzer` (before `_detect_game_system`):

```python
def synthesize_mindscape(
    self,
    *,
    sections: list[dict],
    source_name: str,
    pack_id: str,
) -> SourceMindscapeArtifact:
    """
    Generate chunk/section summaries and a source-level semantic frame.
    Persists artifacts to the KnowledgePack and returns the SourceMindscapeArtifact.
    """
    section_summarizer = SectionSummaryModule()
    global_synthesizer = SourceMindscapeSynthesisModule()

    section_inputs = build_section_summary_inputs(sections)
    section_summary_artifacts: list[SectionSummaryArtifact] = []
    formatted_section_summaries: list[str] = []

    for inp in section_inputs:
        result = section_summarizer(
            heading_path=inp["heading_path"],
            section_text=inp["section_text"],
        )
        artifact = SectionSummaryArtifact(
            section_key=inp["heading_path"].replace(" > ", "_").lower(),
            heading_path=inp["heading_path"].split(" > "),
            chunk_ids=[],
            summary=result.summary,
            confidence=0.8,
            semantic_category=None,
        )
        section_summary_artifacts.append(artifact)
        formatted_section_summaries.append(f"{inp['heading_path']}: {result.summary}")

    global_result = global_synthesizer(
        section_summaries="\n".join(formatted_section_summaries),
        source_name=source_name,
    )

    mindscape = SourceMindscapeArtifact(
        source_name=source_name,
        summary=global_result.global_summary,
        themes=global_result.themes or [],
        taxonomy_hints=global_result.taxonomy_hints or [],
        system_name=global_result.system_name,
        confidence=0.85,
    )

    persist_mindscape_artifacts(
        pack_id=pack_id,
        chunk_summaries=[],
        section_summaries=section_summary_artifacts,
        mindscape=mindscape,
        mongo_client=self._mongo_client,
    )

    return mindscape
```

In `analyze_source()`, after `_classify_and_filter_sections()` (around line 1270) and before `_batched_extract_all()`, add:

```python
mindscape = self.synthesize_mindscape(
    sections=classified_sections,
    source_name=source_name,
    pack_id=pack_id,
)
source_profile_context = format_mindscape_context(mindscape)
```

Replace the existing `source_profile_context` string construction with this one-liner if a `source_profile_context` variable is already built before the extraction call.

Also update `_DETECTION_SAMPLE_SIZE` at its definition near line 1486:

```python
_DETECTION_SAMPLE_SIZE = 48  # was 12
```

And update `GameSystemDetectionModule` instantiation in `_detect_game_system` to use `ModelRole.HEAVY`:
Locate `GameSystemDetectionModule()` call and verify the module's `_role` — update `GameSystemDetectionModule._role = ModelRole.HEAVY` in `prompts/analyzer.py` if it is currently `LIGHT`.

- [ ] **Step 4: Run tests**

```bash
cd packages/agents && python -m pytest tests/test_analyzer.py -v
```
Expected: all PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/analyzer.py packages/agents/tests/test_analyzer.py
git commit -m "feat(agents): add synthesize_mindscape() to Analyzer; wire before extraction; raise detection sample to 48; switch detection to HEAVY"
```

---

## Phase 6 — Typed DSPy Output (Replace Pipe Parsers)

### Task 12: Convert `BatchedExtractionSignature` to typed output

**Files:**
- Modify: `packages/agents/src/monitor_agents/prompts/analyzer.py`
- Modify: `packages/agents/src/monitor_agents/analyzer.py`
- Test: `packages/agents/tests/test_analyzer.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to test_analyzer.py:

def test_batched_extraction_returns_typed_lists_not_strings(mock_analyzer, mock_sections):
    """After the migration, _batched_extract_all must return lists of Pydantic objects, not strings."""
    from monitor_data.schemas.knowledge_packs import ExtractedAxiom

    mock_result = MagicMock()
    mock_result.axioms = [ExtractedAxiom(statement="Vampires fear sunlight", confidence=0.9, source_ref=None, tags=[])]
    mock_result.entities = []
    mock_result.lore_facts = []

    with patch("monitor_agents.analyzer.BatchedExtractionModule") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.return_value = mock_result
        mock_cls.return_value = mock_instance

        result = mock_analyzer._batched_extract_all(
            sections=mock_sections,
            source_name="VtM20",
            source_profile_context="Gothic horror TTRPG.",
            known_graph_context="",
        )

    assert isinstance(result["axioms"][0], ExtractedAxiom)
    assert result["axioms"][0].statement == "Vampires fear sunlight"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd packages/agents && python -m pytest tests/test_analyzer.py::test_batched_extraction_returns_typed_lists_not_strings -v
```
Expected: FAIL — current `_batched_extract_all` calls pipe parsers.

- [ ] **Step 3: Update `BatchedExtractionSignature` in `prompts/analyzer.py`**

Replace the current string-output fields with typed Pydantic list fields:

```python
class BatchedExtractionSignature(dspy.Signature):
    """
    Extract all knowledge artifacts from a set of TTRPG source sections.
    Return typed lists only — no prose, no pipe-delimited lines.
    """

    sections_context: str = dspy.InputField(
        desc="Formatted text of multiple source sections to analyze"
    )
    source_name: str = dspy.InputField(desc="Title of the source document")
    known_graph_context: str = dspy.InputField(
        desc="Existing entities and relations in the world graph (may be empty)"
    )
    source_profile_context: str = dspy.InputField(
        desc="Source-level semantic frame: system, themes, taxonomy hints"
    )
    axioms: list[ExtractedAxiom] = dspy.OutputField(
        desc="World truths: facts that are always true in this setting"
    )
    entities: list[ExtractedEntityArchetype] = dspy.OutputField(
        desc="Entity archetypes: races, classes, factions, creature types"
    )
    lore_facts: list[ExtractedLoreFact] = dspy.OutputField(
        desc="Specific lore facts tied to named entities or places"
    )
```

Ensure the class uses `dspy.TypedChainOfThought` — change `BatchedExtractionModule` to inherit from `_TypedAnalyzerModule` if such a base class exists, or instantiate with `dspy.TypedChainOfThought(BatchedExtractionSignature)`.

- [ ] **Step 4: Remove parser calls from `_batched_extract_all()` in `analyzer.py`**

Find the lines calling `parse_axioms()`, `parse_entities()`, `parse_lore_facts()` (near lines 1375–1379). Replace with direct attribute access:

```python
# OLD (remove these lines):
axioms = parse_axioms(result.axioms_reasoning)
entities = parse_entities(result.entities_reasoning)
lore_facts = parse_lore_facts(result.lore_facts_reasoning)

# NEW:
axioms = result.axioms or []
entities = result.entities or []
lore_facts = result.lore_facts or []
```

- [ ] **Step 5: Run tests**

```bash
cd packages/agents && python -m pytest tests/test_analyzer.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/agents/src/monitor_agents/prompts/analyzer.py packages/agents/src/monitor_agents/analyzer.py packages/agents/tests/test_analyzer.py
git commit -m "feat(agents): convert BatchedExtractionSignature to typed DSPy output; remove parse_axioms/entities/lore_facts calls"
```

---

### Task 13: Convert remaining extraction signatures to typed output

**Files:**
- Modify: `packages/agents/src/monitor_agents/prompts/analyzer.py`
- Modify: `packages/agents/src/monitor_agents/analyzer.py`

- [ ] **Step 1: Update `GameRuleExtractionSignature`**

Replace pipe-delimited output fields with:

```python
class GameRuleExtractionSignature(dspy.Signature):
    """Extract structured game mechanics from a TTRPG source section."""

    section_context: str = dspy.InputField(desc="Section text to analyze")
    system_name: str = dspy.InputField(desc="Name of the game system")
    source_profile_context: str = dspy.InputField(desc="Source-level semantic frame")
    rules: list[GameRule] = dspy.OutputField(desc="Generic game rules found in this section")
    tracks: list[TrackDefinition] = dspy.OutputField(
        desc="Bounded numeric tracks (HP, Blood Pool, Humanity, Stress, etc.)"
    )
    tiered_abilities: list[TieredAbilitySystem] = dspy.OutputField(
        desc="Named ability systems with ranked powers (Disciplines, Spell Schools, etc.)"
    )
    conditions: list[ConditionDefinition] = dspy.OutputField(
        desc="Status effects with trigger conditions and mechanical consequences"
    )
    advantages: list[AdvantageDefinition] = dspy.OutputField(
        desc="Character-sheet picks with costs and effects (Merits, Flaws, Advantages)"
    )
```

Add the missing imports at the top of `prompts/analyzer.py`:

```python
from monitor_data.schemas.game_systems import (
    TrackDefinition,
    TieredAbilitySystem,
    ConditionDefinition,
    AdvantageDefinition,
    ResolutionMechanic,
)
```

- [ ] **Step 2: Update `CharacterSheetExtractionSignature`, `NPCExtractionSignature`, `RelationshipInferenceSignature`, `CreationProcedureExtractionSignature`**

For each, replace the `*_reasoning: str` output fields with typed Pydantic list fields matching the existing schemas in `knowledge_packs.py`. Pattern:

```python
# CharacterSheetExtractionSignature
attributes: list[AttributeDefinition] = dspy.OutputField(...)
skills: list[SkillDefinition] = dspy.OutputField(...)

# NPCExtractionSignature  
npcs: list[ExtractedNPC] = dspy.OutputField(...)  # or whatever the existing NPC schema is

# RelationshipInferenceSignature
relationships: list[ExtractedRelationship] = dspy.OutputField(...)

# CreationProcedureExtractionSignature
steps: list[CreationStep] = dspy.OutputField(...)  # use existing schema
```

Check `knowledge_packs.py` and `game_systems.py` for the existing schema names before writing these.

- [ ] **Step 3: Remove remaining parser calls from `analyzer.py`**

Remove all remaining calls to parser functions at lines 1261, 1470, 1544, 1599, 1627, 1695. Replace each with direct result attribute access (same pattern as Task 12 Step 4).

Remove the parser import line at line 85:

```python
# Remove this entire import:
from monitor_agents.parsers.analyzer_parsers import (
    parse_axioms,
    parse_character_sheet,
    parse_confidence,
    parse_creation_procedure,
    parse_entities,
    parse_game_rules,
    parse_lore_facts,
    parse_npc_data,
    parse_relationships,
    parse_section_classifications,
    parse_source_profile,
)
```

- [ ] **Step 4: Run full agents test suite**

```bash
cd packages/agents && python -m pytest -v
```
Expected: all PASS. If `test_analyzer_parsers.py` fails (it tests the deleted parsers), proceed to Task 14.

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/monitor_agents/prompts/analyzer.py packages/agents/src/monitor_agents/analyzer.py
git commit -m "feat(agents): convert all extraction signatures to typed DSPy output; remove all parser import and call sites from analyzer.py"
```

---

### Task 14: Delete `analyzer_parsers.py` and update test files

**Files:**
- Delete: `packages/agents/src/monitor_agents/parsers/analyzer_parsers.py`
- Modify: `packages/agents/tests/test_analyzer.py`
- Delete: `packages/agents/tests/test_analyzer_parsers.py`

- [ ] **Step 1: Verify no remaining imports of `analyzer_parsers`**

```bash
grep -r "analyzer_parsers" packages/
```
Expected: output shows only `test_analyzer_parsers.py` and nothing else.

- [ ] **Step 2: Remove parser imports from `test_analyzer.py`**

In `packages/agents/tests/test_analyzer.py`, remove lines 8–11 (the `from monitor_agents.parsers.analyzer_parsers import ...` block). Verify the test file still imports what it needs from `knowledge_packs` schemas directly.

- [ ] **Step 3: Delete `test_analyzer_parsers.py`**

```bash
rm packages/agents/tests/test_analyzer_parsers.py
```

- [ ] **Step 4: Delete `analyzer_parsers.py`**

```bash
rm packages/agents/src/monitor_agents/parsers/analyzer_parsers.py
```

If the `parsers/` directory becomes empty, check if `__init__.py` exists there and remove it too if empty:

```bash
ls packages/agents/src/monitor_agents/parsers/
# If empty:
rm -r packages/agents/src/monitor_agents/parsers/
```

- [ ] **Step 5: Run full test suite**

```bash
cd packages/agents && python -m pytest -v
```
Expected: all PASS, no import errors.

- [ ] **Step 6: Run layer dependency check**

```bash
python scripts/check_layer_dependencies.py
```
Expected: no violations.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(agents): delete analyzer_parsers.py and test_analyzer_parsers.py; remove parser imports from test_analyzer.py"
```

---

## Phase 7 — Neo4j Thin Mechanic Nodes

### Task 15: Create `neo4j_tools/mechanics.py` with thin mechanic node write tools

**Files:**
- Create: `packages/data-layer/src/monitor_data/tools/neo4j_tools/mechanics.py`
- Test: create `packages/data-layer/tests/test_tools/test_neo4j_tools_mechanics.py`

- [ ] **Step 1: Write the failing tests**

```python
# packages/data-layer/tests/test_tools/test_neo4j_tools_mechanics.py
from unittest.mock import MagicMock, patch
from monitor_data.tools.neo4j_tools.mechanics import (
    neo4j_create_ability_system,
    neo4j_create_track,
    neo4j_create_condition,
    neo4j_link_entity_to_ability,
)


def _mock_session():
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


def test_neo4j_create_ability_system_runs_merge():
    session = _mock_session()
    with patch("monitor_data.tools.neo4j_tools.mechanics._get_session", return_value=session):
        neo4j_create_ability_system(
            name="Dominate",
            system_id="vtm20_system",
            parent_category="Discipline",
        )
    session.run.assert_called_once()
    query = session.run.call_args[0][0]
    assert "MERGE" in query
    assert "AbilitySystem" in query


def test_neo4j_create_track_runs_merge():
    session = _mock_session()
    with patch("monitor_data.tools.neo4j_tools.mechanics._get_session", return_value=session):
        neo4j_create_track(
            name="Blood Pool",
            system_id="vtm20_system",
            track_type="resource",
        )
    session.run.assert_called_once()
    query = session.run.call_args[0][0]
    assert "Track" in query


def test_neo4j_create_condition_runs_merge():
    session = _mock_session()
    with patch("monitor_data.tools.neo4j_tools.mechanics._get_session", return_value=session):
        neo4j_create_condition(name="Frenzy", system_id="vtm20_system")
    session.run.assert_called_once()
    query = session.run.call_args[0][0]
    assert "Condition" in query


def test_neo4j_link_entity_to_ability_creates_relationship():
    session = _mock_session()
    with patch("monitor_data.tools.neo4j_tools.mechanics._get_session", return_value=session):
        neo4j_link_entity_to_ability(
            entity_id="nosferatu_lineage",
            ability_system_name="Obfuscate",
        )
    session.run.assert_called_once()
    query = session.run.call_args[0][0]
    assert "HAS_ACCESS_TO" in query
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd packages/data-layer && python -m pytest tests/test_tools/test_neo4j_tools_mechanics.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `mechanics.py`**

```python
# packages/data-layer/src/monitor_data/tools/neo4j_tools/mechanics.py
"""
Thin mechanic reference node writes for Neo4j.

Authority: CanonKeeper only.
These functions write minimal traversal-oriented nodes.
Full mechanic definitions live in MongoDB KnowledgePacks.
"""
from monitor_data.db.neo4j import _get_session


def neo4j_create_ability_system(
    *,
    name: str,
    system_id: str,
    parent_category: str | None = None,
) -> None:
    """MERGE an :AbilitySystem node. Idempotent."""
    with _get_session() as session:
        session.run(
            """
            MERGE (a:AbilitySystem {name: $name, system_id: $system_id})
            SET a.parent_category = $parent_category
            """,
            name=name,
            system_id=system_id,
            parent_category=parent_category,
        )


def neo4j_create_track(
    *,
    name: str,
    system_id: str,
    track_type: str,
) -> None:
    """MERGE a :Track node. Idempotent."""
    with _get_session() as session:
        session.run(
            """
            MERGE (t:Track {name: $name, system_id: $system_id})
            SET t.track_type = $track_type
            """,
            name=name,
            system_id=system_id,
            track_type=track_type,
        )


def neo4j_create_condition(
    *,
    name: str,
    system_id: str,
) -> None:
    """MERGE a :Condition node. Idempotent."""
    with _get_session() as session:
        session.run(
            """
            MERGE (c:Condition {name: $name, system_id: $system_id})
            """,
            name=name,
            system_id=system_id,
        )


def neo4j_link_entity_to_ability(
    *,
    entity_id: str,
    ability_system_name: str,
) -> None:
    """Create HAS_ACCESS_TO relationship from an entity to an AbilitySystem node."""
    with _get_session() as session:
        session.run(
            """
            MATCH (e {id: $entity_id})
            MATCH (a:AbilitySystem {name: $ability_system_name})
            MERGE (e)-[:HAS_ACCESS_TO]->(a)
            """,
            entity_id=entity_id,
            ability_system_name=ability_system_name,
        )
```

Look at existing files in `packages/data-layer/src/monitor_data/tools/neo4j_tools/` to confirm the correct import path for `_get_session` — use whatever pattern the other files in that directory use.

- [ ] **Step 4: Run tests**

```bash
cd packages/data-layer && python -m pytest tests/test_tools/test_neo4j_tools_mechanics.py -v
```
Expected: all PASS.

- [ ] **Step 5: Add authority check**

Open `packages/data-layer/src/monitor_data/middleware/auth.py`. Add to `AUTHORITY_MATRIX`:

```python
"neo4j_create_ability_system": ["CanonKeeper"],
"neo4j_create_track": ["CanonKeeper"],
"neo4j_create_condition": ["CanonKeeper"],
"neo4j_link_entity_to_ability": ["CanonKeeper"],
```

- [ ] **Step 6: Commit**

```bash
git add packages/data-layer/src/monitor_data/tools/neo4j_tools/mechanics.py packages/data-layer/tests/test_tools/test_neo4j_tools_mechanics.py packages/data-layer/src/monitor_data/middleware/auth.py
git commit -m "feat(data-layer): add neo4j_tools/mechanics.py — thin AbilitySystem, Track, Condition node writes (CanonKeeper authority)"
```

---

### Task 16: Update `CanonKeeper` to write mechanic nodes after game system apply

**Files:**
- Modify: `packages/agents/src/monitor_agents/canonkeeper.py`
- Test: `packages/agents/tests/test_canonkeeper.py` (read existing file first to match patterns)

- [ ] **Step 1: Read the existing canonkeeper test file**

```bash
cat packages/agents/tests/test_canonkeeper.py | head -80
```

Use the existing mock pattern from that file for the tests below.

- [ ] **Step 2: Write the failing test**

```python
# Add to packages/agents/tests/test_canonkeeper.py:

def test_apply_knowledge_pack_writes_mechanic_nodes_when_game_system_present(mock_canonkeeper):
    """When a pack has tiered_abilities, tracks, and conditions, CanonKeeper must create Neo4j nodes."""
    from monitor_data.schemas.game_systems import (
        TieredAbilitySystem,
        TrackDefinition,
        ConditionDefinition,
        EmbeddedGameSystem,
    )
    from unittest.mock import patch

    game_system = EmbeddedGameSystem(
        system_name="Vampire: the Masquerade",
        tiered_abilities=[
            TieredAbilitySystem(name="Dominate", parent_category="Discipline", tiers=[], max_tier=5)
        ],
        tracks=[
            TrackDefinition(
                name="Blood Pool", min_value=0, max_value=10, default_value=10,
                track_type="resource", gain_conditions=[], loss_conditions=[],
                spend_conditions=[], recovery_rules=[], threshold_effects=[],
            )
        ],
        conditions=[ConditionDefinition(name="Frenzy", trigger="Fail Humanity check", ends_when="Willpower roll", stackable=False)],
    )

    with patch("monitor_agents.canonkeeper.neo4j_create_ability_system") as mock_ab, \
         patch("monitor_agents.canonkeeper.neo4j_create_track") as mock_tr, \
         patch("monitor_agents.canonkeeper.neo4j_create_condition") as mock_cn:
        mock_canonkeeper.apply_knowledge_pack(pack_id="p1", game_system=game_system, system_id="vtm20")

    mock_ab.assert_called_once_with(name="Dominate", system_id="vtm20", parent_category="Discipline")
    mock_tr.assert_called_once_with(name="Blood Pool", system_id="vtm20", track_type="resource")
    mock_cn.assert_called_once_with(name="Frenzy", system_id="vtm20")
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd packages/agents && python -m pytest tests/test_canonkeeper.py::test_apply_knowledge_pack_writes_mechanic_nodes_when_game_system_present -v
```
Expected: `AttributeError` or assertion failure.

- [ ] **Step 4: Update `canonkeeper.py`**

Add imports:

```python
from monitor_data.tools.neo4j_tools.mechanics import (
    neo4j_create_ability_system,
    neo4j_create_track,
    neo4j_create_condition,
)
```

Find the `apply_knowledge_pack` method (or the equivalent that runs after game system extraction). After the existing Neo4j entity writes, add:

```python
if game_system:
    system_id = system_id or game_system.system_name or "unknown_system"
    for ability in (game_system.tiered_abilities or []):
        neo4j_create_ability_system(
            name=ability.name,
            system_id=system_id,
            parent_category=ability.parent_category,
        )
    for track in (game_system.tracks or []):
        neo4j_create_track(
            name=track.name,
            system_id=system_id,
            track_type=track.track_type,
        )
    for condition in (game_system.conditions or []):
        neo4j_create_condition(
            name=condition.name,
            system_id=system_id,
        )
```

- [ ] **Step 5: Run tests**

```bash
cd packages/agents && python -m pytest tests/test_canonkeeper.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/agents/src/monitor_agents/canonkeeper.py packages/agents/tests/test_canonkeeper.py
git commit -m "feat(agents): CanonKeeper writes AbilitySystem, Track, Condition Neo4j nodes when applying game system from KnowledgePack"
```

---

## Phase 8 — Integration Verification

### Task 17: Run full test suite and layer dependency check

**Files:** No changes — verification only.

- [ ] **Step 1: Run all three layer test suites**

```bash
cd packages/data-layer && python -m pytest -v
cd packages/agents && python -m pytest -v
cd packages/cli && python -m pytest -v
```
Expected: all PASS.

- [ ] **Step 2: Run layer dependency check**

```bash
python scripts/check_layer_dependencies.py
```
Expected: no violations (agents never import CLI, data-layer never imports agents).

- [ ] **Step 3: Verify backward compatibility — ingest an existing small pack**

If a Death in Space test fixture exists in `docs/example_ingestion/`, run:

```bash
# Deserialize the fixture pack with the updated schemas to confirm no ValidationError
python -c "
import json
from monitor_data.schemas.knowledge_packs import KnowledgePackCreate
with open('docs/example_ingestion/<smallest_fixture>.json') as f:
    data = json.load(f)
pack = KnowledgePackCreate(**data)
print('OK — fields:', list(pack.model_fields_set))
"
```
Expected: no `ValidationError`. All new fields default to empty list / None.

- [ ] **Step 4: Commit if any cleanup was needed**

```bash
git add -A
git commit -m "chore: post-integration cleanup after ingestion revamp"
```

---

## Acceptance Checklist

After all tasks are complete, verify:

- [ ] `KnowledgePack.source_mindscape` is non-null after ingesting any of the four test PDFs
- [ ] `KnowledgePack.game_system_data.tracks` is non-empty for VtM20 and Death in Space packs
- [ ] `KnowledgePack.game_system_data.tiered_abilities` is non-empty for VtM20 (Disciplines)
- [ ] `KnowledgePack.game_system_data.conditions` is non-empty for VtM20 (Frenzy)
- [ ] Qdrant chunk payloads contain `heading_path: list[str]` (not `section_path: str | None`)
- [ ] Neo4j has `:AbilitySystem` nodes with `name: "Dominate"` after VtM20 pack apply
- [ ] `python scripts/check_layer_dependencies.py` passes with zero violations
- [ ] All three layer test suites pass with no regressions
- [ ] Old pack JSON fixtures (without new fields) deserialize without error
