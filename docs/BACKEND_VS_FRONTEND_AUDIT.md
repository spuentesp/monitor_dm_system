# MONITOR Backend vs Frontend Capability Audit

> **Date**: 2026-06-03  
> **Verdict**: The frontend exposes roughly **35-40%** of backend capability. Major gaps exist in agent configuration, performance monitoring, tone management, temporal tools, NLP tools, combat/progression loops, and the full depth of the story/scene loop configuration.

---

## 1. Backend Routers vs Frontend API Coverage

### Router Inventory (31 routers)

| Router | Endpoints | Frontend API Defined? | Frontend Actually Used? | Gap |
|--------|-----------|----------------------|------------------------|-----|
| `chat.py` | Sessions CRUD, messages, WebSocket, send, patch, delete, benchmarks, session state | ✅ `chatApi` | ✅ PlayConsole, Settings | Minor — benchmarks only partially exposed |
| `modes.py` | list, getActive, setActive | ✅ `modesApi` | ❌ **Never used in any component** | **FULL GAP** — mode switching has no UI |
| `ingest.py` | upload, sources, jobs, stream, rescan, unlock, cancel, purge | ✅ `ingestApi` | ✅ Forge/UploadCard/SourceLibrary/IngestionJobsList | Partial — unlock/cancel/purge not in UI |
| `pack_library.py` | packs CRUD, merge, canonize, export, import, clone, slice, apply | ✅ `ingestApi` | ✅ PackLibrary | Partial — merge/export/import/clone/slice/apply not in UI |
| `llm_mgmt.py` | providers CRUD, test, duplicate, models, assignments CRUD | ✅ `llmApi` | ✅ Settings page | Partial — assignments not in UI |
| `databases.py` | allStatus, getStatus | ✅ `dbApi` | ❌ **Never used in any component** | **FULL GAP** — no DB health dashboard |
| `entities.py` | NPCs, systems, characters, search, generate | ✅ `entitiesApi` | ✅ PlayConsole, CharacterPanel, MemoryInspector | Partial — generate/search not in UI |
| `game_systems.py` | list, get, rules | ✅ `entitiesApi` | Partial | Rules endpoint not exposed in UI |
| `graph.py` | world graph | ✅ `graphApi` | ✅ Worlds page | OK |
| `prompts.py` | list, getModule, updateInstructions, resetOverride, test | ✅ `promptsApi` | ✅ Settings page | OK |
| `stories.py` | get, patch (DM override) | ✅ `storiesApi` | ✅ StoryPanel | Partial — patch/override not in UI |
| `gm_tools.py` | hooks, contradictions, session-prep, handouts | ✅ `gmApi` | ✅ GM page | OK |
| `tone.py` | profiles CRUD, libraries CRUD, tag definitions CRUD, tag suggestions | ❌ **No frontend API** | ❌ | **FULL GAP** — entire tone system invisible |
| `lorebook.py` | entries CRUD, bulk create, inject, stats, top entries | ❌ **No frontend API** | ❌ | **FULL GAP** — lorebook has editor component but no API bridge |
| `search.py` | semantic search across all collections | ❌ **No frontend API** | ❌ | **FULL GAP** — no semantic search UI |
| `templates.py` | CRUD for entity templates | ✅ `templatesApi` | ✅ TemplateBrowser | OK |
| `random_tables.py` | CRUD + roll | ✅ `randomTablesApi` | ✅ RandomTableEditor | OK |
| `universes.py` | multiverses, universes CRUD, activate | ✅ `universesApi` | ✅ PlayConsole, Worlds | OK |
| `character_resolution.py` | resolve actor character | ❌ Internal only | ❌ | N/A — internal helper |
| `character_storage.py` | standalone character CRUD | ❌ Internal only | ❌ | N/A — internal helper |
| `performance.py` | overview, patterns, slow queries, report | ❌ **No frontend API** | ❌ | **FULL GAP** — no performance dashboard |
| `chat_game_system.py` | resolve universe→system binding | ❌ Internal only | ❌ | N/A |
| `chat_loops.py` | scene loop lifecycle, pre-play, world architect turns | ❌ Internal only | ❌ | N/A |
| `chat_opening.py` | story/scene bootstrap, GM opening | ❌ Internal only | ❌ | N/A |
| `chat_persistence.py` | MongoDB session/message I/O | ❌ Internal only | ❌ | N/A |
| `chat_schemas.py` | Pydantic models | ❌ Internal only | ❌ | N/A |
| `chat_support.py` | shared helpers | ❌ Internal only | ❌ | N/A |
| `chat_ws.py` | WebSocket subscriber registry | ❌ Internal only | ❌ | N/A |
| `ingest_shared.py` | shared helpers | ❌ Internal only | ❌ | N/A |
| `entities_schemas.py` | Pydantic models | ❌ Internal only | ❌ | N/A |
| `modes_schemas.py` | Pydantic models | ❌ Internal only | ❌ | N/A |

### Summary: 6 Entire Routers with ZERO Frontend Exposure

1. **`tone.py`** — Full tone profile/library/tag system
2. **`lorebook.py`** — Lorebook CRUD + injection + stats
3. **`search.py`** — Semantic search across all collections
4. **`performance.py`** — Neo4j query performance monitoring
5. **`databases.py`** — DB health dashboard (API defined but never used)
6. **`modes.py`** — Mode switching (API defined but never used)

---

## 2. Agent Configuration Gaps

### BaseAgent (`base.py`)

| Config Parameter | Backend Support | Frontend Exposure | Gap |
|-----------------|----------------|-------------------|-----|
| `agent_type` | ✅ | ❌ | No agent type display |
| `agent_id` | ✅ | ❌ | No agent instance tracking |
| `model` (per-agent) | ✅ via LLMRegistry | ❌ | No per-agent model picker |
| `call_llm_structured` max_tokens | ✅ (default 2048) | ❌ | Not configurable from UI |
| Retry policy (attempts, min/max wait) | ✅ via `settings` | ❌ | Not configurable from UI |
| Logfire tracing | ✅ | ❌ | No observability UI |

### Narrator (`narrator.py`)

| Config Parameter | Backend Support | Frontend Exposure | Gap |
|-----------------|----------------|-------------------|-----|
| Session tone (dramatic/grim/horror/etc.) | ✅ | ✅ (session create) | OK but limited |
| GM profile override | ✅ | ❌ | No GM profile picker in session setup |
| Lorebook context injection | ✅ | ❌ | No lorebook management UI |
| Story state (arc, tension, threads) | ✅ | ❌ | StoryPanel is read-only |
| Minutes elapsed per turn | ✅ | ❌ | Not shown in UI |
| DSPy module (NarratorModule) | ✅ | ✅ (prompts page) | OK |

### CanonKeeper (`canonkeeper.py`)

| Config Parameter | Backend Support | Frontend Exposure | Gap |
|-----------------|----------------|-------------------|-----|
| Policy check module | ✅ | ✅ (prompts page) | OK |
| Reasoning module | ✅ | ✅ (prompts page) | OK |
| Commit ordering | ✅ | ❌ | No visibility into commit pipeline |
| Detail level derivation | ✅ | ❌ | Not shown in UI |
| State tag normalization | ✅ | ❌ | Not configurable |

### Resolver (`resolver.py`)

| Config Parameter | Backend Support | Frontend Exposure | Gap |
|-----------------|----------------|-------------------|-----|
| Play mode (narrative/dice_standard/dice_game_system) | ✅ | ✅ (session create) | OK |
| Forced narrative detection | ✅ | ❌ | No UI feedback when detected |
| Roll necessity classification | ✅ | ❌ | Not shown to player |
| Game system runtime | ✅ | ❌ | No game system runtime config UI |
| Intent classification | ✅ | ❌ | No intent display |

### WorldArchitect (`world_architect.py`)

| Config Parameter | Backend Support | Frontend Exposure | Gap |
|-----------------|----------------|-------------------|-----|
| Gap analysis module | ✅ | ❌ | No "what to define next" UI |
| World profile tracking | ✅ | ❌ | No world profile dashboard |
| Coverage summary | ✅ | ❌ | Not shown |
| Auto-commit proposals | ✅ | ❌ | No visibility |

### ContextAssembly (`context_assembly.py`)

| Config Parameter | Backend Support | Frontend Exposure | Gap |
|-----------------|----------------|-------------------|-----|
| Token budget (per role) | ✅ | ❌ | No token budget display |
| Redis caching | ✅ | ❌ | No cache management UI |
| Query formulation module | ✅ | ✅ (prompts page) | OK |
| Source scope support | ✅ | ❌ | Not configurable |
| Dialogue context windows | ✅ | ❌ | Not configurable |

### Agents with ZERO Frontend Exposure

| Agent | Backend Capability | Frontend |
|-------|-------------------|----------|
| **NPCVoice** | Direct NPC dialogue, actor-mode reflection, relationship tracking | ❌ No UI |
| **Oracle** | Binary question resolution with probability tiers | ❌ No UI |
| **SimulacrumAgent** | Off-screen world simulation, faction agenda advancement | ❌ No UI |
| **RecapAgent** | "The Story So Far" narrative recaps | ❌ No UI |
| **CharacterCreator** | Guided character creation via CharacterCreationLoop | ❌ No UI |
| **Indexer** | Document analysis and extraction pipeline | ❌ No UI (only via ingest) |
| **NPCSceneGenerator** | NPC scene generation | ❌ No UI |

---

## 3. LLM Management Gaps

### Backend Capabilities (`llm_mgmt.py`)

| Feature | Backend | Frontend API | Frontend UI | Gap |
|---------|---------|-------------|-------------|-----|
| List providers | ✅ | ✅ | ✅ | OK |
| Add provider | ✅ | ✅ | ✅ | OK |
| Update provider | ✅ | ✅ | ✅ | OK |
| Delete provider | ✅ | ✅ | ✅ | OK |
| Duplicate provider | ✅ | ✅ | ✅ | OK |
| Test provider | ✅ | ✅ | ✅ | OK |
| List available models | ✅ | ✅ | ✅ | OK |
| **Node assignments** (per-agent model routing) | ✅ | ✅ `listAssignments`, `setAssignment`, `deleteAssignment` | ❌ **No UI** | **MAJOR GAP** |
| Provider roles (light/standard/heavy) | ✅ | ✅ | ✅ | OK |
| `param_overrides` per node | ✅ | ✅ | ❌ | No UI for per-node params |
| Auto-seed from env | ✅ | ❌ | ❌ | No visibility |
| 10 provider types supported | ✅ | ✅ | ✅ | OK |

### LLMRegistry Advanced Features (No UI)

- **Dynamic role escalation**: Narrator auto-escalates to HEAVY for dramatic moments — not visible or configurable
- **Per-node model assignment**: Can assign different models to narrator vs canonkeeper vs context_assembly — **no UI**
- **`param_overrides`**: Temperature, max_tokens per node — **no UI**
- **Background registry cache**: Auto-invalidated on provider changes — no visibility
- **LLM call logging** (`MONITOR_LLM_LOG=1`): Full request/response audit trail — no UI

---

## 4. Mode System Gaps

### Backend (`modes.py`)

Three modes defined:
1. **World Architect** — Build the Omniverse
2. **Autonomous GM** — Solo Play
3. **GM Assistant** — Co-Pilot for Human GMs

Each mode has: `id`, `label`, `tagline`, `description`, `capabilities[]`, `color`, `icon`

Active mode tracks: `mode_id`, `world_id`, `character_id`, `tone`, `context_depth`

### Frontend Gap

- `modesApi` is **defined in api.ts** but **never imported or used in any component**
- No mode selector UI exists
- No mode-specific capability display
- No `context_depth` configuration
- Mode capabilities are not surfaced anywhere

---

## 5. Performance/Monitoring Gaps

### Backend (`performance.py`) — 4 Endpoints

| Endpoint | Description | Frontend |
|----------|-------------|----------|
| `GET /performance` | Overview (total queries, avg time, slow query rate, uptime) | ❌ |
| `GET /performance/patterns` | Query patterns sorted by count/avg_time/max_time/slow_count | ❌ |
| `GET /performance/slow` | Recent slow queries with execution details | ❌ |
| `GET /performance/report` | Complete report with overview + top patterns + slowest patterns | ❌ |

**No frontend API defined. No UI.** Entire performance monitoring system is invisible.

### Database Health (`databases.py`)

- `dbApi` is defined in `api.ts` but **never used in any component**
- No DB health dashboard
- No latency/version/stats display
- Probes: Neo4j, MongoDB, Qdrant, MinIO, OpenSearch — all invisible

---

## 6. Game System Configuration Gaps

### Backend Capabilities

| Feature | Backend | Frontend | Gap |
|---------|---------|----------|-----|
| List game systems | ✅ | ✅ | OK |
| Get game system details | ✅ | ✅ | OK |
| Get system rules (filtered by type) | ✅ | ❌ | Rules not browsable |
| Update game system | ✅ | ✅ | OK |
| Delete game system | ✅ | ✅ | OK |
| Test game system | ✅ | ✅ | OK |
| Test game system NPC | ✅ | ✅ | OK |
| **RPG Ontology tools** (PostgreSQL-backed) | ✅ `rpg_tools.py` | ❌ | **FULL GAP** — character sheets, equipment catalog, schema validation |
| **Character sheet CRUD** (typed, validated) | ✅ | ❌ | **FULL GAP** |
| **Equipment catalog** | ✅ | ❌ | **FULL GAP** |
| **Schema inspection** | ✅ | ❌ | **FULL GAP** |

---

## 7. Scene Loop Configuration Gaps

### SceneState Fields (not configurable from UI)

| Field | Default | Configurable? | UI? |
|-------|---------|---------------|-----|
| `play_mode` | `dice_game_system` | ✅ (session create) | ✅ |
| `session_tone` | `dramatic` | ✅ (session create/patch) | ✅ |
| `max_turns` | 50 | ❌ Hardcoded | ❌ |
| `roll_mode` | `normal` | ❌ | ❌ |
| `temporal_mode` | `present` | ❌ | ❌ |
| `time_ref` | None | ❌ | ❌ |
| `tension_score` | 0.5 | ❌ | ❌ |
| `gm_profile_id` | None | ✅ (session create) | ❌ Not in UI |
| `system_id` | None | ✅ (session create) | ✅ |
| `pack_id` | None | ✅ (session create) | ✅ |

### Scene Loop Nodes (no UI visibility)

- `load_context` → `await_user` → `resolve` → `persist_narrative` → `canonize_or_continue`
- No visualization of the state machine
- No ability to pause/resume/restart scenes
- No checkpoint management UI

---

## 8. Story Loop Configuration Gaps

### StoryState Fields (not configurable from UI)

| Field | Default | UI? |
|-------|---------|-----|
| `arc_label` | `rising_action` | ❌ Read-only in StoryPanel |
| `tension_score` | 0.3 | ❌ Read-only |
| `active_threads` | [] | ❌ Read-only |
| `completed_threads` | [] | ❌ Read-only |
| `next_scene_type` | None | ❌ |
| `scene_hook` | None | ❌ |
| `in_game_time` | 1000-01-01 | ❌ |
| `world_ticks` | 0 | ❌ |
| `world_tone` | `dramatic` | ❌ |

### Backend supports PATCH for DM overrides — Frontend doesn't use it

The `stories.py` router has a `PATCH /{story_id}` endpoint that allows GMs to:
- Override `arc_label` (force climax, etc.)
- Override `tension_score`
- Override `active_threads`

**None of this is exposed in the UI.** The StoryPanel is read-only.

---

## 9. MCP Tools — Backend Only (No UI)

### Neo4j Tools (`neo4j_tools/`)

| Tool Group | Functions | UI? |
|-----------|-----------|-----|
| `core.py` | create/get/list multiverses, universes | Partial (via universes API) |
| `entities.py` | create/get/list/update/delete entities, state tags | Partial (via entities API) |
| `facts/` | create/list/get facts, lore facts | ❌ No fact browser UI |
| `relationships.py` | create/list/get relationships | ❌ No relationship editor |
| `mechanics.py` | create ability systems, conditions, resolution mechanics, tracks | ❌ **FULL GAP** |
| `stories.py` | create/list/get stories | Partial (via stories API) |
| `agendas.py` | create/list/get/update agendas | ❌ **FULL GAP** |
| `parties.py` | create/list/get parties | ❌ **FULL GAP** |
| `traversal.py` | graph traversal, blast radius | ❌ **FULL GAP** |
| `contextual_relationships.py` | contextual relationship management | ❌ **FULL GAP** |

### MongoDB Tools (`mongodb_tools/`)

| Tool Group | Functions | UI? |
|-----------|-----------|-----|
| `game_systems.py` | CRUD for game systems | Partial |
| `characters.py` | Standalone character CRUD | ✅ |
| `character_sheets.py` | Typed character sheet CRUD | ❌ **FULL GAP** |
| `combat.py` | Combat state management | ❌ **FULL GAP** |
| `conversations.py` | Conversation session management | ❌ **FULL GAP** |
| `documents.py` | Source document management | Partial (via ingest) |
| `ingestion_jobs.py` | Job tracking | ✅ |
| `knowledge_packs.py` | Pack CRUD | Partial |
| `lorebook_tools.py` | Lorebook CRUD + injection | ❌ **FULL GAP** (API exists, no frontend bridge) |
| `memories.py` | Character memory CRUD | Partial (MemoryInspector) |
| `merge_candidates.py` | Merge candidate detection | ❌ **FULL GAP** |
| `npc_profiles.py` | NPC profile management | ❌ **FULL GAP** |
| `party.py` | Party management | ❌ **FULL GAP** |
| `profiles.py` | GM profiles | ❌ **FULL GAP** |
| `proposals.py` | Proposed change review | Partial (via ingest review) |
| `random_tables.py` | Random table CRUD | ✅ |
| `resolutions.py` | Resolution records | ❌ **FULL GAP** |
| `scenes.py` | Scene CRUD | Partial |
| `snapshots.py` | World state snapshots | ❌ **FULL GAP** |
| `stories.py` | Story outline CRUD | Partial |
| `tag_registry.py` | Tag definition CRUD | ❌ **FULL GAP** |
| `templates.py` | Entity template CRUD | ✅ |
| `tone_libraries.py` | Tone library CRUD | ❌ **FULL GAP** |
| `tone_profiles.py` | Tone profile CRUD | ❌ **FULL GAP** |
| `webhook_tools.py` | Webhook management | ❌ **FULL GAP** |
| `working_state.py` | Character working state | ❌ **FULL GAP** |

### Other Tool Groups

| Tool Group | Functions | UI? |
|-----------|-----------|-----|
| `qdrant_tools.py` | Vector search, upsert, delete | ❌ No direct UI |
| `rpg_tools.py` | System register, character sheets, equipment catalog | ❌ **FULL GAP** |
| `perception_tools.py` | Fast entity detection (regex/spaCy/GLiNER) | ❌ **FULL GAP** |
| `nlp_tools.py` | GLiNER NER extraction | ❌ **FULL GAP** |
| `temporal_tools/` | Fact expiration, scene temporal validation | ❌ **FULL GAP** |
| `plot_thread_tools/` | Scene thread detection | ❌ **FULL GAP** |
| `ingest_tools/` | Chunking, dedup, delta detection, PDF processing | ❌ Internal only |
| `lain_tools.py` | Lain MCP bridge | ❌ Internal only |
| `pack_completeness.py` | Pack completeness scoring | ❌ **FULL GAP** |

---

## 10. Settings/Environment Variables (No UI)

### All Configurable via Environment (invisible to frontend)

| Category | Variables | UI? |
|----------|-----------|-----|
| **Neo4j** | URI, user, password | ❌ |
| **MongoDB** | URI, database, timeouts | ❌ |
| **Qdrant** | URL, API key, path | ❌ |
| **MinIO** | Endpoint, keys, bucket, secure, region | ❌ |
| **OpenSearch** | URL, user, password | ❌ |
| **Redis** | URL, enabled, TTL, timeouts | ❌ |
| **Embeddings** | Model, dimension, OpenAI key | ❌ |
| **LLM** | Model, Anthropic key, vision model | ❌ |
| **PostgreSQL** | Host, port, user, password, DB | ❌ |
| **Reliability** | DB retry attempts/waits, LLM retry attempts/waits | ❌ |
| **NLP** | Enabled, backend, GLiNER URL/model/params | ❌ |
| **Ingest** | Max workers, timeout | ❌ |
| **LLM Logging** | `MONITOR_LLM_LOG`, `MONITOR_LLM_LOG_FILE` | ❌ |

---

## 11. Frontend API Methods — Defined vs Used

### API Client Exports (14 total)

| API Object | Methods Defined | Methods Used in Components | Unused Methods |
|-----------|----------------|---------------------------|---------------|
| `chatApi` | 9 | 8 | `patchSession` (barely) |
| `modesApi` | 3 | **0** | **ALL** — list, getActive, setActive |
| `ingestApi` | ~30 | ~12 | ~18 (merge, export, import, clone, slice, apply, proposals, batch review, commit, cancel, purge, etc.) |
| `llmApi` | 9 | 7 | `listAssignments`, `setAssignment`, `deleteAssignment` |
| `dbApi` | 2 | **0** | **ALL** — allStatus, getStatus |
| `entitiesApi` | 14 | 6 | `listNPCs`, `getNPC`, `listSystems`, `getSystem`, `updateSystem`, `deleteSystem`, `testSystem`, `testSystemNpc`, `generateEntity`, `search`, `getStandaloneCharacter`, `createStandaloneCharacter`, `updateStandaloneCharacter` |
| `universesApi` | 8 | 4 | `getUniverse`, `createUniverse`, `updateUniverse`, `deleteUniverse`, `activateUniverse` |
| `graphApi` | 1 | 1 | None |
| `promptsApi` | 5 | 4 | `resetOverride` (barely) |
| `storiesApi` | 2 | 1 | `listScenes` |
| `gmApi` | 4 | 4 | None |
| `templatesApi` | 5 | 2 | `get`, `create`, `update` |
| `randomTablesApi` | 6 | 4 | `get`, `create` |

### APIs Defined in api.ts but NOT in Backend Routers

- **`toneApi`** — Does not exist. Backend has full `tone.py` router.
- **`lorebookApi`** — Does not exist. Backend has full `lorebook.py` router.
- **`searchApi`** — Does not exist. Backend has full `search.py` router.
- **`performanceApi`** — Does not exist. Backend has full `performance.py` router.

---

## 12. Frontend Pages — What They Expose vs What They Could

### `/play` (PlayConsole)
**Currently exposes**: Session list, create, delete, send messages, tone selector, character panel, memory inspector, story panel  
**Could additionally expose**:
- Mode switching (World Architect / Autonomous GM / GM Assistant)
- Per-session play_mode configuration (narrative vs dice)
- Roll mode toggle (normal/advantage/disadvantage)
- GM profile selection
- Scene checkpoint management
- Forced narrative detection feedback
- Resolution details display
- Resource engine state (HP, spell slots, etc.)
- Working state editor
- Temporal mode / time reference

### `/forge` (World Forge)
**Currently exposes**: Source upload, pack library, asset management, template browser, random table editor  
**Could additionally expose**:
- Pack merge/split/clone/export/import UI
- Pack apply to existing world (with conflict resolution)
- Proposal review workflow (accept/reject/batch)
- Commit accepted proposals
- Lorebook editor (backend exists, component exists but no API bridge)
- Entity archetype browser
- World profile / coverage dashboard
- Gap analysis ("what to define next")
- Semantic search across all collections

### `/settings`
**Currently exposes**: LLM providers, prompt modules, benchmark sessions  
**Could additionally expose**:
- **Node assignments** (per-agent model routing) — **CRITICAL GAP**
- Database health dashboard
- Performance monitoring
- Redis cache management
- NLP/GLiNER configuration
- Environment variable viewer
- LLM call log viewer
- Token budget configuration per role

### `/gm` (GM Toolkit)
**Currently exposes**: Plot hooks, contradictions, session prep, handouts  
**Could additionally expose**:
- Recap generation ("The Story So Far")
- Oracle questions (binary world-truth resolution)
- NPC voice / actor mode
- Simulacrum world simulation controls
- Combat loop management
- Party management
- World state snapshots
- Agenda/clock management

### `/architect` (World Architect)
**Currently exposes**: Basic page  
**Could additionally expose**:
- Full WorldBuildingLoop integration
- World profile dashboard
- Coverage summary visualization
- Priority gaps display
- Auto-commit proposal visibility

### `/worlds` (World Graph)
**Currently exposes**: ReactFlow world graph  
**Could additionally expose**:
- Entity detail panels (click to edit)
- Relationship editor
- Fact browser
- Agenda/clock visualization
- Temporal timeline view
- Blast radius analysis

### `/systems` (Game Systems)
**Currently exposes**: Basic page  
**Could additionally expose**:
- Full game system browser with rules
- Character sheet templates
- Equipment catalog
- Schema inspector
- System test bench

### `/prompts` (Prompt Lab)
**Currently exposes**: Basic page  
**Could additionally expose**:
- Full prompt module browser (already in settings)
- A/B testing of prompt variants
- Prompt performance metrics
- Override management dashboard

---

## 13. Loop Systems with Zero UI

| Loop | File | Purpose | UI? |
|------|------|---------|-----|
| **CharacterCreationLoop** | `character_creation_loop.py` | Guided character creation | ❌ |
| **CombatLoop** | `combat_loop.py` | Turn-based combat management | ❌ |
| **ConversationLoop** | `conversation_loop.py` | NPC direct dialogue sessions | ❌ |
| **IngestionLoop** | `ingestion_loop.py` | Document processing pipeline | Partial (via ingest) |
| **ProgressionLoop** | `progression_loop.py` | Character advancement | ❌ |
| **WorldBuildingLoop** | `world_building_loop.py` | Collaborative world creation | ❌ |

---

## 14. Priority Gap Summary

### 🔴 Critical (Core functionality invisible)

1. **LLM Node Assignments** — Backend fully supports per-agent model routing, frontend API exists, **zero UI**
2. **Tone System** — Full CRUD for tone profiles, libraries, tag definitions — **no frontend API, no UI**
3. **Lorebook System** — Backend has full CRUD + injection + stats — **no frontend API bridge** (component exists)
4. **Mode Switching** — API defined, **never used** — no mode selector
5. **Database Health** — API defined, **never used** — no health dashboard
6. **Performance Monitoring** — Full backend, **no frontend API, no UI**

### 🟠 Major (Significant capability gaps)

7. **Story Override** — PATCH endpoint exists for DM overrides, **not used in UI**
8. **Semantic Search** — Full cross-collection search backend, **no frontend API, no UI**
9. **NPC Voice/Conversation** — Full agent + loop, **no UI**
10. **Oracle** — Binary question resolution, **no UI**
11. **Simulacrum** — World simulation engine, **no UI**
12. **Recap** — "The Story So Far" generation, **no UI**
13. **Combat Loop** — Full combat management, **no UI**
14. **Character Creation Loop** — Guided creation, **no UI**
15. **RPG Ontology** — Typed character sheets, equipment catalog, **no UI**
16. **Pack Operations** — Merge/export/import/clone/slice/apply all missing from UI
17. **Proposal Review** — Full workflow exists, only partial UI

### 🟡 Moderate (Configuration gaps)

18. **Token Budget** — Per-role budgets exist, not visible or configurable
19. **Scene Loop Config** — max_turns, roll_mode, temporal_mode not configurable
20. **Resource Engine** — HP/spell slots/tracks engine exists, no UI
21. **Working State** — Character working state management, no UI
22. **Agenda/Clock System** — Neo4j agenda tracking, no UI
23. **World Snapshots** — Snapshot management, no UI
24. **GM Profiles** — Profile CRUD exists, not in session setup UI
25. **NLP/GLiNER** — Entity extraction pipeline, no configuration UI
26. **Temporal Tools** — Fact expiration, scene validation, no UI
27. **Ingest Advanced** — Cancel/purge/unlock queue not in UI
28. **Entity Search** — Backend supports search, not exposed in entities UI
29. **Entity Generation** — Backend supports LLM-powered entity generation, not in UI

---

## 15. Quantitative Summary

| Category | Backend Endpoints/Tools | Frontend API Methods | Frontend UI Pages/Components | Coverage |
|----------|------------------------|---------------------|------------------------------|----------|
| Routers | 31 | 14 API objects (~100 methods) | ~8 pages, ~15 components | ~35% |
| Agents | 10 agent classes | 0 direct | 0 direct | 0% |
| Loops | 7 loop classes | 0 direct | 0 direct | 0% |
| MCP Tool Groups | 12+ groups (~80+ functions) | ~30 methods | ~10 components | ~25% |
| Settings/Env Vars | 40+ | 0 | 0 | 0% |
| DSPy Prompt Modules | 12 registered | 5 methods | 1 page | ~40% |

**Overall estimated frontend coverage: ~35-40% of backend capability.**