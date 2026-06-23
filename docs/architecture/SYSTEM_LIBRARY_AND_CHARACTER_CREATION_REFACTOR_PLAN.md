# System Library and Character/NPC Creation Audit + Refactor Plan

> **Status:** Audit and proposed refactor plan  
> **Date:** 2026-04-08  
> **Goal:** keep reusable **generic systems** in one canonical place, keep **integrated systems** inside packs, and make MONITOR produce and save **usable characters** and NPCs.
>
> **Refactor-plan status:** this document is the audit/design reference for system and character-library cleanup. For canonical architecture and workflow context, cross-check `ARCHITECTURE.md`, `docs/USE_CASES.md`, `docs/architecture/AGENT_ORCHESTRATION.md`, and the live chat/bootstrap flow in `packages/ui/backend/src/monitor_ui/routers/chat.py`.

---

## 1. Scope and desired outcome

This plan covers four related problems:

1. **System sprawl** — generic library systems and pack-integrated systems should not blur together.
2. **Character generation without persistence** — MONITOR can already roll preview characters, but the save path is fragmented.
3. **World Architect gaps** — world-building persists world profiles, but not a proper cast/roster workflow.
4. **Usability** — the objective is not just “generate stats”; it is to create **play-ready PCs and NPCs** that can be saved, reused, and advanced.

**Definition of a usable character:**
- has a persistent identity (`EntityInstance`)
- is bound to a specific world/universe and resolved system source
- has mechanical data (`CharacterSheet` or NPC stat snapshot)
- can carry notes/profile data (`NPCProfile` or equivalent)
- can be selected in play without rebuilding from scratch

---

## 2. Verified current repo state

| Area | Verified current state | Evidence | Audit note |
|---|---|---|---|
| **Generic systems** | Reusable systems already live in the `game_systems` collection and built-ins are seeded from `packages/data-layer/src/monitor_data/data/builtin_systems.json`. | `packages/data-layer/src/monitor_data/tools/mongodb_tools.py`, `packages/ui/backend/src/monitor_ui/routers/game_systems.py` | Good foundation for the **generic system library**. |
| **Integrated systems in packs** | Packs already support inline `game_system_data`, and pack responses prefer embedded system data. | `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`, `packages/ui/backend/src/monitor_ui/routers/ingest_shared.py` | Good foundation for **pack-scoped integrated systems**. |
| **Test character generation** | `/systems/{system_id}/test` uses `GameSystemRuntime.roll_character()` and returns a preview sheet. | `packages/ui/backend/src/monitor_ui/routers/entities.py`, `packages/agents/src/monitor_agents/game_system.py` | Useful for testing, but currently **preview-only**. |
| **Pre-play character setup** | Chat setup supports `awaiting_character → char_creation → active_play`, can offer/roll stats, and now attempts to persist a generated/session character before active play. | `packages/ui/backend/src/monitor_ui/routers/chat.py` / `packages/ui/backend/src/monitor_ui/routers/chat_loops.py` | The flow is no longer preview-only, but the long-term canonical target remains `EntityInstance + CharacterSheet` through the canon boundary. |
| **World Architect persistence** | `WorldArchitect` persists `EmbeddedWorldProfile` state to Mongo and commits world proposals through CanonKeeper. | `packages/agents/src/monitor_agents/world_architect.py` | Strong world-building base, but **no character/NPC draft lifecycle** yet. |
| **Canonical character persistence** | `CharacterSheet` and `NPCProfile` schemas already exist. | `packages/data-layer/src/monitor_data/schemas/character_sheets.py`, `packages/data-layer/src/monitor_data/schemas/npc_profiles.py` | Correct long-term stores exist, but they are not the main UI/runtime path yet. |
| **Authority boundary** | `mongodb_create_character_sheet` and `mongodb_update_character_sheet` are CanonKeeper-only. | `packages/data-layer/src/monitor_data/middleware/auth.py` | Any final save flow must respect the canon gate. |
| **Current drift** | The Systems UI reads from a separate `characters` collection, while the canonical sheet model is `character_sheets`. | `packages/ui/backend/src/monitor_ui/routers/entities.py` | This is the biggest structural mismatch to fix first. |

### Summary of the audit

MONITOR already has the right **pieces**, but not one coherent **path**:
- the **system library** exists
- **pack-integrated systems** exist
- **preview generation** exists
- **canonical persistence models** exist

The missing piece is a single, architecture-safe workflow that turns:

`system/pack/world intent → draft character or NPC → preview/test → save to world`

---

## 3. Canon decisions

These should become the documentation and implementation standard.

### 3.1 Generic systems live in one place

**Canonical home:** `game_systems` collection + `/systems` surfaces.

Use this for:
- built-in starter systems
- user-authored reusable systems
- imported SRD-like generic systems
- rulesets that should be available across many worlds

**Do not automatically copy pack-integrated systems into this library.**

---

### 3.2 Integrated systems live inside packs

**Canonical home:** `KnowledgePack.game_system_data`.

Use this for:
- source-derived rules bundled with a pack
- setting-coupled mechanics
- pregens, NPC stat blocks, and creation guidance that should travel with the pack
- exportable “all-in-one” experiences

**Rule:** if the system is part of a pack’s identity, keep it embedded on the pack.  
If the user wants it reusable beyond that pack, add an explicit **“Publish to System Library”** action later.

---

### 3.3 Persistent characters belong to worlds/universes, not packs

**Canonical home for live play characters:**
- Neo4j `EntityInstance` for identity and canon
- Mongo `CharacterSheet` for mechanics
- Mongo `NPCProfile` for personality/social state

**Packs should store templates and examples, not live evolving campaign state.**

---

### 3.4 Multiverses should hold reusable archetypes, not session-state sheets

Use the multiverse level for:
- shared archetypes
- exported cast seeds
- cross-world canonical figures when intentionally global

Use the universe/world level for:
- current HP/resources
- actual party members
- active NPCs with story consequences

---

## 4. Recommended target structure

## 4.1 Systems

| Type | Store | Scope | Editable from | Notes |
|---|---|---|---|---|
| **Generic system** | `game_systems` | global library | `/systems`, import, rules management | reusable across worlds |
| **Integrated pack system** | `KnowledgePack.game_system_data` | pack-local | Forge / pack editor | ships with the pack |
| **Resolved world system binding** | `multiverse`/`universe` binding metadata | world-local | World creation, pack apply, GM setup | points to either library or pack source |

### Recommended binding metadata

When a multiverse or universe selects a rules source, persist enough metadata to answer:
- **where the rules came from** (`generic_library` vs `pack_embedded`)
- **which object is authoritative** (`system_id` or `pack_id`)
- **which version/snapshot was chosen**

This can be a dedicated `system_binding` document or explicit fields on the world records.  
The key point is to avoid ambiguous fallback logic at runtime.

---

## 4.2 Characters and NPCs

| Lifecycle stage | Purpose | Recommended store |
|---|---|---|
| **Template / archetype** | reusable concept or stat pattern | `EntityArchetype`, pack NPC stat blocks, pack creation rules |
| **Draft / preview** | test roll, concept suggestion, uncommitted candidate | **new draft surface** (`character_drafts` / `npc_drafts` or equivalent Mongo working docs) |
| **Persistent live character** | playable PC/NPC in a world | `EntityInstance` + `CharacterSheet` (+ `NPCProfile` when needed) |

### Recommended new draft concept

Add a small draft layer so preview generation and persistence use the same object shape:

- `CharacterDraft`
- `NPCDraft`

These drafts should support:
- `source_type`: `system_test`, `world_architect`, `gm_setup`, `pack_template`, `benchmarks`
- `system_source`: `generic_library` or `pack_embedded`
- `status`: `preview`, `draft`, `committed`, `discarded`
- `save_target`: `pack`, `world`, or `multiverse_template`

This keeps **test generation** and **real creation** on the same path instead of two disconnected implementations.

---

## 5. How creation should work by surface

## 5.1 System Library (`/systems`)

**Purpose:** define and validate generic systems.

Should support:
- preview a **test PC**
- preview a **test NPC**
- verify attribute ranges, derived resources, and creation rules
- optionally **save as draft** or **send to a world**

Should **not** be the main place for persistent campaign state.

### Recommended actions
- `Roll test character`
- `Generate test NPC`
- `Save as draft`
- `Save to selected world`
- `Publish generic template`

---

## 5.2 Packs / Forge

**Purpose:** ship a self-contained package of setting + mechanics + example cast.

Should support:
- embedded `game_system_data`
- `character_creation` rules
- `npc_stat_blocks`
- example pregens or archetypes
- preview/test generation against the pack’s integrated system

### Recommended pack behavior
- save **templates**, **archetypes**, **sample NPCs**, and **pregens** inside the pack
- do **not** treat the pack as the home of live campaign characters
- when the user applies the pack to a world, clone selected templates into that world

---

## 5.3 World Architect

**Purpose:** design a world and its cast before or between play sessions.

This should become the primary surface for:
- creating named NPCs for a world
- creating starter PCs or pregens tied to a world
- defining the “world roster” during setting creation
- promoting templates into live in-world entities

### Recommended World Architect structure

Add a **Characters & NPCs** panel with three modes:

1. **Concept mode**
   - name, role, description, faction ties, motivations
2. **System-grounded mode**
   - suggest or roll stats using the currently bound system
3. **Save mode**
   - `Save as world NPC`
   - `Save as world PC`
   - `Save as multiverse archetype`
   - `Save as pack template` (optional handoff)

World Architect should be able to create:
- **fiction-first concepts** even before full mechanics are known
- then enrich them into `CharacterSheet` / `NPCProfile` data once confirmed

This is the right place to save “test characters” that turn out to be worth keeping.

---

## 5.4 GM Mode / Play Setup

**Purpose:** create/select playable characters during session onboarding.

The current phase flow is close. The router now attempts this handoff, but the canonicalized save path still needs to be hardened:

`player concept confirmed → draft created → save to world → enter active play`

### Recommended GM setup behavior
- let the player describe a concept in natural language
- offer system-grounded options:
  - suggest spread
  - random roll
  - constrained manual assignment
  - narrative-only skip
- on confirmation, create:
  - `EntityInstance`
  - `CharacterSheet`
  - optional `NPCProfile`/backstory notes
- bind the session to that saved character

This turns pre-play from a temporary conversation into a persistent onboarding pipeline.

---

## 5.5 Worlds / Universes

**Purpose:** the source of truth for live playable cast.

Worlds should own:
- party members
- local NPCs
- active roster
- consequences and advancement over time

A world should be able to receive characters/NPCs from:
- a generic system test roll
- a pack template
- World Architect draft creation
- GM setup during session start

All of those should end at the same persistent shape.

---

## 5.6 Multiverses

**Purpose:** higher-level reuse and publishing, not minute-by-minute play state.

Use multiverses for:
- reusable cast seeds
- cross-universe archetypes
- publishing a character/NPC as a reusable reference

Do **not** use multiverses as the primary store for current HP, equipment drift, or in-scene changes.

---

## 5.7 Other useful surface: Benchmarks / Playtests

`monitor playtest` and similar validation flows should be allowed to:
- generate ephemeral characters/NPCs
- save them as drafts for inspection
- optionally promote a good generated result into a world or pack

This gives testing value without polluting canon by default.

---

## 6. Refactor plan

## Phase 0 — Documentation and terminology cleanup

**Objective:** lock the vocabulary before code changes.

Actions:
- standardize on **generic system** vs **integrated pack system**
- standardize on **template / draft / persistent instance** for characters and NPCs
- document that `CharacterSheet` + `EntityInstance` are the live character target

---

## Phase 1 — Storage normalization

**Priority:** P0

Actions:
1. Keep `game_systems` for global reusable systems only.
2. Keep pack-integrated systems in `KnowledgePack.game_system_data`.
3. Add a resolved **system binding** for multiverse/universe/session setup.
4. Stop treating the ad hoc `characters` collection as the primary model.
5. Introduce a draft layer for preview/test results.

**Likely touchpoints:**
- `packages/data-layer/src/monitor_data/schemas/game_systems.py`
- `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`
- `packages/data-layer/src/monitor_data/schemas/character_sheets.py`
- `packages/data-layer/src/monitor_data/schemas/npc_profiles.py`
- `packages/data-layer/src/monitor_data/tools/mongodb_tools.py`

---

## Phase 2 — Shared generation service

**Priority:** P0

**Objective:** use one structured generator for both preview and save flows.

Actions:
1. Extend `GameSystemRuntime` to return structured candidates, not just a formatted sheet string.
2. Add NPC generation parallel to `roll_character()` using:
   - `npc_creation_rules`
   - `npc_stat_blocks`
   - optional role/tier prompts
3. Return a reusable candidate object that can be previewed, edited, or saved.

**Recommended output shape:**
- identity block
- stats/resources/skills
- derived values
- provenance (`generic_library` / `pack_embedded`)
- draft status

**Likely touchpoints:**
- `packages/agents/src/monitor_agents/game_system.py`
- `packages/ui/backend/src/monitor_ui/routers/entities.py`

---

## Phase 3 — Save pipeline through the canon boundary

**Priority:** P0

**Objective:** make “Save to World” real and architecture-safe.

Actions:
1. Add `save draft to world` flow that routes through CanonKeeper.
2. On commit, create/update:
   - Neo4j `EntityInstance`
   - Mongo `CharacterSheet`
   - Mongo `NPCProfile` when appropriate
3. Preserve provenance so the world knows whether the character came from:
   - a generic system
   - a pack-integrated system
   - World Architect
   - GM setup

**Important rule:** final persistence must respect the existing CanonKeeper-only write gate for character sheets.

---

## Phase 4 — Surface integration

**Priority:** P1

### 4A. Systems page
- add `Save to world` after a test roll
- add `Generate NPC` alongside `Roll Character`

### 4B. World Architect
- add world roster panel
- allow concept-first character/NPC creation
- support `preview → edit → save`

### 4C. GM mode / chat pre-play
- after confirmation, persist the character instead of only changing `phase`
- support selecting an existing saved character or creating a new one

### 4D. Forge / packs
- allow saving pregens and NPC templates into the pack
- allow cloning selected templates into a world during apply

---

## Phase 5 — Verification and acceptance tests

**Priority:** P1

Write failing tests first for:

1. **Generic system preview**
   - can roll a test character
   - can generate a test NPC
2. **Save path**
   - preview candidate can be saved into a world as `EntityInstance + CharacterSheet`
3. **Pack-integrated path**
   - character/NPC generation uses `KnowledgePack.game_system_data` when present
4. **World Architect path**
   - can create/save a world NPC or starter PC
5. **GM setup path**
   - pre-play creation persists a usable character before active play starts

---

## 7. Recommended user-facing behavior matrix

| User intent | Best surface | Save target | Default persistence |
|---|---|---|---|
| “I want to design a reusable system.” | `/systems` | generic system library | persistent |
| “I want this book/pack to carry its own mechanics.” | Forge / Packs | `KnowledgePack.game_system_data` | persistent |
| “I want to see if this system makes good characters.” | `/systems` test tools | draft by default | ephemeral unless saved |
| “I want to make a cast for this world.” | World Architect | world/universe roster | persistent |
| “I’m starting a session; help me make my PC.” | GM mode / chat setup | world + session | persistent on confirm |
| “I need a quick shopkeeper/guard/rival right now.” | GM mode quick NPC generator | world NPC | persistent or scene-only draft |
| “I want exportable pregens with my setting.” | Pack editor | pack templates/pregens | persistent in pack |

---

## 8. Practical priorities

### P0 — Do first
- normalize the source-of-truth split: `game_systems` vs `KnowledgePack.game_system_data`
- add one saveable draft pipeline for test characters and NPCs
- wire GM setup to persist characters
- stop relying on disconnected character storage patterns

### P1 — Do next
- add World Architect roster creation
- add pack pregens / template cloning
- add NPC generation and save flow next to character preview

### P2 — Later
- publish pack systems into the generic library by explicit user action
- multiverse-level reusable cast publishing and cross-world cloning tools

---

## 9. Final recommendation

The cleanest long-term model is:

- **Generic systems** → one canonical global library
- **Integrated systems** → embedded on packs
- **Templates/archetypes** → packs and multiverse-level reusable assets
- **Live characters/NPCs** → worlds/universes
- **Test generation** → draft-first, saveable when worth keeping
- **World Architect + GM setup** → both use the same draft → commit pipeline

That structure keeps the repo architecture coherent, reduces duplication, and directly supports the real objective:

> **produce usable characters, not just random stat previews.**
