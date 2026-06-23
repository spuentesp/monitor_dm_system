# MONITOR — Frontend Overhaul Plan

> **Created:** 2026-06-03  
> **Status:** Phase A COMPLETE ✅ — Phase B next  
> **Goal:** Transform the UI from a fragile demo into a production-grade control surface that exposes the full power of the MONITOR platform.

---

## 0. Executive Summary

**Current state:** The frontend exposes ~35-40% of backend capability. It works when everything is perfect (backend running, WebSocket connected, data seeded) but has zero resilience. Three critical bugs break the core play loop. Entire backend routers (tone, lorebook, search, performance, databases, modes) have zero UI. The prompt editing page is a redirect. The CanonKeeper proposal workflow — the system's core innovation — has no frontend.

**Target state:** A resilient, comprehensive control surface where every backend capability has a UI, every agent is configurable, every workflow is completable, and errors are handled gracefully.

---

## 1. Critical Bug Fixes (Do First)

These break the core experience right now.

### 1.1 Query Key Mismatch in PlayConsole 🔴

**Problem:** Optimistic message updates write to `["messages", sessionId]` but the query reads from `PLAY_KEYS.messages(sessionId)` = `["play-messages", sessionId]`. Different cache keys = duplicate/missing messages.

**Fix:** Replace all `["messages", activeSessionId]` in `PlayConsole.tsx` with `PLAY_KEYS.messages(activeSessionId)`.

**Lines:** 980, 1027, 1034, 1060

### 1.2 WebSocket Reconnection 🔴

**Problem:** `createChatWebSocket()` is bare `new WebSocket()`. No heartbeat, no reconnect, no status indicator. Connection drops silently kill the play session.

**Fix:**
1. Create `useChatWebSocket()` hook with:
   - Auto-reconnect with exponential backoff (1s → 2s → 4s → 8s → max 30s)
   - Ping/pong heartbeat every 30s
   - Connection status state (`connecting` / `connected` / `disconnected` / `reconnecting`)
   - Visual indicator in the chat UI (green dot = connected, yellow = reconnecting, red = disconnected)
2. Replace raw `createChatWebSocket()` calls in PlayConsole and Architect pages

### 1.3 React Error Boundary 🔴

**Problem:** Zero `ErrorBoundary` components. Any render error crashes the entire page with a white screen.

**Fix:**
1. Create `ErrorBoundary` component with:
   - Friendly error message with "Try again" button
   - `componentDidCatch` logging via structlog-style console.error
   - Per-page boundary wrapping each route
2. Wrap each page in `app/layout.tsx` or per-page `error.tsx` (Next.js convention)
3. Add `global-error.tsx` for root-level catches

### 1.4 Request Timeout & Abort 🟡

**Problem:** `req()` helper has no `AbortController` or timeout. Hung backend = infinite spinner.

**Fix:**
1. Add `AbortController` with 30s default timeout to `req()` in `api.ts`
2. TanStack Query already supports `signal` — pass it through
3. Add `staleTime` override for long-running operations (LLM calls)

---

## 2. Missing Workflow UIs (High Impact)

These are complete backend workflows with zero frontend.

### 2.1 Proposal Review & Canonization 🔥

**Why critical:** This is the CanonKeeper's core innovation — the pipeline from `ProposedChange` → review → accept/reject → commit to Neo4j. Currently packs get stuck in `review_pending` with no way to act.

**UI:**
- New `ProposalReviewPanel` component in Forge
- List proposals with: entity name, type, source (narrator/GM/ingest), confidence, canon_level
- Accept/reject individual or batch
- "Commit Accepted" button that triggers CanonKeeper commit
- Diff view: show what the proposal would add/change
- Filter by: source, entity_type, confidence threshold, canon_level

**API methods already exist:** `listProposals`, `reviewProposal`, `batchReview`, `commitAccepted`

### 2.2 Canonize Pack UI 🔥

**Why critical:** The primary path from Forge → World has no button.

**UI:**
- "Canonize Pack" button in pack detail view
- Modal with: target universe selector, apply mode (new world / existing world)
- Progress indicator during canonization
- Result summary (entities created, facts added, errors)

**API methods already exist:** `canonizePack`, `applyPackNewWorld`, `applyPackExistingWorld`

### 2.3 Prompt Module Editor 🔥

**Why critical:** Full backend exists, `/prompts` redirects to `/settings` which has no prompt tab. Users cannot customize agent behavior.

**UI:**
- New `/prompts` page (remove redirect)
- Left sidebar: list of DSPy modules (NarratorProse, CanonKeeperDecision, ResolverIntent, etc.)
- Main panel: module detail — name, role, current instructions, signature
- Instructions editor: rich text area with save/reset
- "Test Prompt" button: send test input, see output
- "Reset Override" button: restore default instructions
- Role mapping: which LLM node handles which module

**API methods already exist:** `promptsApi.list`, `getModule`, `updateInstructions`, `resetOverride`, `test`

### 2.4 Universe Snapshots, Fork & Seed 🔥

**Why critical:** 5 backend endpoints with zero frontend. World management is incomplete.

**UI:**
- Add to `/worlds` universe detail view:
  - **Snapshots tab**: list snapshots, create snapshot, restore snapshot, compare two snapshots (diff view)
  - **Fork button**: "Fork Universe" with confirmation dialog, name for fork
  - **Seed button**: "Seed Universe" with template/table selectors, entity count preview
- Add API methods to `api.ts`: `seedUniverse`, `forkUniverse`, `createSnapshot`, `listSnapshots`, `restoreSnapshot`, `compareSnapshots`

### 2.5 Performance Monitoring Dashboard

**Why critical:** 10+ backend endpoints, zero frontend. No visibility into system health.

**UI:**
- New `/monitoring` page (or tab in Settings)
- **Overview**: request rate, avg latency, error rate, p50/p95/p99
- **Slow queries**: table of slowest Neo4j queries with timestamps
- **Alerts**: active alerts, alert configuration (thresholds, cooldown)
- **Baselines**: set/query performance baselines
- **Health**: per-database health status with latency bars

**API methods needed:** Add `performanceApi` to `api.ts` with all performance endpoints

---

## 3. Agent Configuration Surface (The Big Gap)

The system has 10 agents, 7 loops, ~80 MCP tool functions, and ~500+ configurable parameters. The UI exposes almost none of this.

### 3.1 Agent Dashboard

**New page: `/agents`**

| Section | What It Shows |
|---------|---------------|
| **Agent cards** | 10 agents: Narrator, CanonKeeper, Resolver, WorldArchitect, ContextAssembly, NPCVoice, Oracle, Simulacrum, RecapAgent, CharacterCreator |
| **Per-agent config** | Model assignment, temperature, max_tokens, system prompt override |
| **Status** | Available/unavailable, last used, call count |
| **Test** | "Test agent" button — send input, see output |

**Backend needed:** New router `agents.py` with:
- `GET /agents` — list agents with status
- `GET /agents/{name}` — agent detail + config
- `PATCH /agents/{name}/config` — update runtime config (temperature, max_tokens, etc.)
- `POST /agents/{name}/test` — test agent with sample input

### 3.2 LLM Node Assignments

**Currently:** `llmApi.listAssignments`/`setAssignment`/`deleteAssignment` exist but have zero UI.

**UI:**
- Add "Node Assignments" tab to Settings → LLM Providers
- Table: Role (narrator, canonkeeper, resolver, context_assembly, etc.) → Assigned Provider/Model
- Dropdown to change assignment
- "Auto" option: let the system pick based on tier (Light/Standard/Heavy)
- "Test Assignment" button: verify the assigned model works

### 3.3 Token Budget Configuration

**Currently:** Hardcoded per role (LIGHT=2000, STANDARD=4000, HEAVY=8000). No UI.

**UI:**
- Add "Token Budgets" section to Settings → Agents tab
- Per-role budget sliders: Light, Standard, Heavy
- Per-agent override: "Narrator always uses Heavy budget"
- Live preview: "Current session using 3,847 / 4,000 tokens"
- Warning when approaching budget limit

**Backend needed:** New endpoints for token budget CRUD

### 3.4 Context Assembly Weights

**Currently:** Hardcoded in `context_assembly.py` — action overlap weight 0.7, profile overlap weight 0.3.

**UI:**
- Add "Context Assembly" section to `/agents` page
- Sliders for: action_overlap_weight, profile_overlap_weight (must sum to 1.0)
- Max context entries slider
- Min relevance threshold slider
- "Preview context" button: show what context would be assembled for a sample scene

### 3.5 Scene Loop Configuration

**Currently:** `max_turns` hardcoded at 50. No UI for loop phase configuration.

**UI:**
- Add "Scene Loop" section to `/agents` page
- Max turns slider (10-200, default 50)
- Enable/disable phases: narrate, resolve, extract_entities, extract_memories, canonize_checkpoint
- Auto-canonize threshold slider (confidence ≥ X → auto-promote)
- Scene-end behavior: auto-end vs manual confirmation

### 3.6 Resolver Configuration

**Currently:** 10+ hardcoded regex patterns for intent classification. No UI.

**UI:**
- Add "Resolver" section to `/agents` page
- Intent pattern table: pattern → action mapping
- Add/edit/delete patterns
- "Test resolver" button: input text → see detected intent

### 3.7 Oracle Configuration

**Currently:** Hardcoded 7-entry DC map. No UI.

**UI:**
- Add "Oracle" section to `/agents` page
- DC map table: likelihood label → DC value → response probabilities
- Add/edit entries
- "Ask Oracle" test: input question → see oracle response

---

## 4. Play Page Overhaul

### 4.1 Session Configuration Panel (Expanded)

**Currently:** Basic setup with mode, tone, universe, system, character selectors.

**Add:**
- **Agent selection**: which agents are active for this session (checkboxes)
- **Model override**: override the default LLM for this session
- **Token budget**: Light/Standard/Heavy selector
- **Scene loop config**: max turns, auto-canonize threshold
- **Lorebook toggle**: enable/disable lorebook injection
- **Controlled characters**: multi-select PCs (not just one)
- **Play mode**: explicit dropdown (freeform, structured, combat, conversation)

### 4.2 Live Session State Panel

**Currently:** `getSessionState` is called but only used for benchmark tab.

**Add:**
- Collapsible "Session State" panel showing:
  - Current scene ID, status, turn count
  - Active story ID, arc, tension
  - Token usage (current / budget)
  - Pending proposals count
  - Last canonization timestamp
  - Active agents and their last call time

### 4.3 Wire LorebookEditor

**Currently:** `LorebookEditor` component exists in `components/play/` but is never imported.

**Fix:**
- Import and render `LorebookEditor` in PlayConsole
- Add "Lorebook" tab or collapsible panel
- Wire to `lorebookApi` (new API methods needed)

### 4.4 Story/Scene Navigation

**Currently:** No way to switch scenes or stories mid-session.

**Add:**
- Scene list dropdown (from `storiesApi.listScenes`)
- "New Scene" button
- "End Scene" button (triggers `complete_current_scene`)
- "End Story" button (triggers `StoryLoop.complete_story()`)

### 4.5 NPC Voice Sessions

**New feature:** Direct 1:1 conversation with an NPC in character.

**UI:**
- "Talk to NPC" button in character panel
- Opens a sub-chat with the NPC's voice agent
- NPC responds in character using `NPCVoice` agent
- Conversation is recorded as a scene in the story

**Backend needed:** New endpoint `POST /chat/ws/{sessionId}/npc/{characterId}`

### 4.6 Oracle Tool

**New feature:** "Ask the Oracle" — binary world-truth questions.

**UI:**
- "Oracle" button in play toolbar
- Input: yes/no question
- Output: Yes / No / Maybe with likelihood explanation
- Uses `Oracle` agent with configurable DC map

**Backend needed:** New endpoint `POST /gm/oracle`

### 4.7 Recap Generator

**New feature:** "The Story So Far" — generate a recap of the session.

**UI:**
- "Recap" button in play toolbar
- Output: formatted recap of recent scenes, decisions, consequences
- Uses `RecapAgent`

**Backend needed:** New endpoint `POST /gm/recap`

---

## 5. Forge Page Overhaul

### 5.1 Proposal Review Panel

(See §2.1 above)

### 5.2 Canonize & Apply Pack

(See §2.2 above)

### 5.3 Batch Entity Operations

**Currently:** 3 backend endpoints, no UI.

**UI:**
- Multi-select checkboxes in entity list
- Bulk action bar: Create Batch, Update Batch, Delete Batch
- Batch create: paste CSV or JSON, or use template
- Batch update: select field → new value → apply to all selected
- Batch delete: confirmation dialog with count

### 5.4 Entity Relationships

**Currently:** Backend exists, no UI.

**UI:**
- "Relationships" tab in entity detail
- Add relationship: source entity → relationship type → target entity
- Relationship type dropdown (from ontology)
- Visual: relationship graph for selected entity

### 5.5 Entity Generation

**Currently:** `entitiesApi.generateEntity` exists but unused.

**UI:**
- "Generate Entity" button in entity list
- Modal: entity type, description prompt, universe context
- Preview generated entity before saving
- "Save as Template" option

### 5.6 Pack Slice UI

**Currently:** `slicePack` API exists but unused.

**UI:**
- "Slice Pack" button in pack detail
- Select entities to include in slice
- Name the new sub-pack
- Preview before creating

---

## 6. GM Page Overhaul

### 6.1 Combat Management

**New feature:** Initiative tracker, HP pools, condition tracking.

**UI:**
- "Combat" tab in GM page
- Initiative order with drag-to-reorder
- HP/resource bars per combatant
- Condition badges (poisoned, stunned, etc.)
- "Next Turn" button
- Auto-roll initiative option

**Backend needed:** New combat state endpoints

### 6.2 Encounter Builder

**New feature:** Build encounters with difficulty estimation.

**UI:**
- "Encounters" tab in GM page
- Add NPCs/monsters from entity list
- Difficulty calculator (based on party level vs encounter CR)
- "Start Encounter" button → pushes to combat tracker

### 6.3 Random Table Quick-Roll

**Currently:** Random tables exist in Forge but no quick-roll from GM page.

**UI:**
- "Tables" tab in GM page
- List available tables
- One-click roll with result display
- "Roll All" for session prep

### 6.4 Lorebook Management

**Currently:** Backend exists, no link from GM page.

**UI:**
- "Lorebook" tab in GM page
- CRUD for lorebook entries
- "Inject into context" button
- Stats: top triggered entries, total entries

### 6.5 Simulacrum

**New feature:** "What would this NPC do?" — off-screen world simulation.

**UI:**
- "Simulate" tab in GM page
- Select NPC + scenario description
- Output: NPC's likely actions/reactions
- Uses `Simulacrum` agent

**Backend needed:** New endpoint `POST /gm/simulacrum`

---

## 7. Architect Page Overhaul

### 7.1 Fix Edit/Delete Buttons

**Currently:** Inspector panel has Edit/Delete buttons with no `onClick` handlers.

**Fix:**
- Edit: open inline edit form for entity properties
- Delete: confirmation dialog → `entitiesApi.deleteEntity`

### 7.2 Seed Universe UI

(See §2.4 above)

### 7.3 Fork Universe UI

(See §2.4 above)

### 7.4 Snapshot Management

(See §2.4 above)

### 7.5 Entity Search in Graph

**Currently:** No search bar to find/jump to a specific entity.

**Add:**
- Search bar above graph canvas
- Type entity name → graph focuses on that node
- Uses `entitiesApi.search`

### 7.6 Relationship Creation from Graph

**Currently:** No UI to create relationships between graph nodes.

**Add:**
- Shift+click two nodes → "Create Relationship" dialog
- Relationship type dropdown
- Bidirectional toggle

---

## 8. Settings Page Overhaul

### 8.1 LLM Node Assignments Tab

(See §3.2 above)

### 8.2 Agent Configuration Tab

(See §3.1 above — expand the existing stub tab)

### 8.3 Token Budgets Section

(See §3.3 above)

### 8.4 Performance Monitoring Tab

(See §2.5 above)

### 8.5 Mode Switching

**Currently:** `modesApi` completely unused.

**UI:**
- "Modes" section in Settings
- Current mode display (Autonomous GM / GM Assistant / World Architect)
- Mode switch with confirmation
- Per-mode configuration (which agents are active, default tone, etc.)

### 8.6 Database Configuration

**Currently:** Can view status but can't configure connections.

**UI:**
- Per-database connection config (host, port, database name)
- "Test Connection" button
- "Reconnect" button
- Connection pool stats

### 8.7 Ingestion Tuning

**Currently:** Env-var only, no UI.

**UI:**
- Workers count slider
- Timeout slider
- Max file size config
- Cache management: "Clear Cache" button, cache stats
- Queue management: "Unlock Queue" button

---

## 9. New Pages

### 9.1 `/agents` — Agent Dashboard

(See §3.1 above)

### 9.2 `/monitoring` — Performance Dashboard

(See §2.5 above)

### 9.3 `/prompts` — Prompt Editor (Real Page)

(See §2.3 above — remove redirect, build real page)

---

## 10. Resilience & UX Improvements

### 10.1 Connection Status Indicator

- Global indicator in sidebar: backend connected (green) / disconnected (red)
- Per-page WebSocket status: connected (green dot) / reconnecting (yellow) / disconnected (red)
- "Reconnect" button when disconnected

### 10.2 Loading States

- Skeleton loaders for all data-fetching components (not just spinners)
- Progressive loading: show structure first, then populate with data
- Empty states with helpful CTAs ("Create your first universe" → button)

### 10.3 Offline / No-Backend Mode

- Detect backend unavailability on app load
- Show "Backend Unavailable" banner with setup instructions
- Cache last-known data in localStorage for read-only viewing
- "Retry Connection" button

### 10.4 Toast Notifications

- Standardize all error/success toasts
- WebSocket events → toasts ("Scene ended", "Entity canonized", "Proposal ready for review")
- Dismissible with undo option where applicable

### 10.5 Keyboard Shortcuts

- `Ctrl+Enter` — send message
- `Ctrl+Shift+R` — roll dice
- `Ctrl+Shift+S` — save current entity
- `Ctrl+/` — command palette

### 10.6 Responsive Layout

- Sidebar collapses on small screens
- Play page chat takes full width on mobile
- GM tools stack vertically on narrow screens

---

## 11. Implementation Priority

### Phase A: Critical Fixes (1-2 days) ✅ COMPLETE
1. ✅ Fix query key mismatch in PlayConsole
2. ✅ Add WebSocket reconnection with status indicator (`useChatWebSocket` hook)
3. ✅ Add React Error Boundary (`error.tsx`, `global-error.tsx`, `ErrorBoundary` component)
4. ✅ Add request timeout to `req()` (30s default, AbortController)
5. ✅ Add global connection status indicator in Sidebar (`ConnectionStatus` component)

### Phase B: Missing Workflows (3-5 days)
1. Proposal Review Panel (CanonKeeper workflow)
2. Canonize Pack UI
3. Prompt Module Editor (real `/prompts` page)
4. Universe Snapshots/Fork/Seed UI
5. Performance Monitoring Dashboard

### Phase C: Agent Configuration (5-7 days)
1. Agent Dashboard page (`/agents`)
2. LLM Node Assignments UI
3. Token Budget configuration
4. Context Assembly weights
5. Scene Loop configuration
6. Resolver pattern management
7. Oracle DC map configuration

### Phase D: Play Page Expansion (3-5 days)
1. Expanded session config panel
2. Live session state panel
3. Wire LorebookEditor
4. Story/Scene navigation
5. NPC Voice sessions
6. Oracle tool
7. Recap generator

### Phase E: Forge & GM Expansion (3-5 days)
1. Batch entity operations
2. Entity relationships UI
3. Entity generation button
4. Pack slice UI
5. Combat management
6. Encounter builder
7. Random table quick-roll from GM
8. Lorebook management in GM
9. Simulacrum tool

### Phase F: Architect & Settings Polish (2-3 days)
1. Fix Edit/Delete buttons in inspector
2. Entity search in graph
3. Relationship creation from graph
4. Mode switching UI
5. Database configuration
6. Ingestion tuning
7. Loading states & empty states
8. Offline detection

### Phase G: UX Polish (2-3 days)
1. Keyboard shortcuts
2. Toast standardization
3. Responsive layout
4. Command palette

---

## 12. Backend Endpoints Needed

These endpoints don't exist yet but are needed for the UI overhaul:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/agents` | GET | List agents with status |
| `/agents/{name}` | GET | Agent detail + config |
| `/agents/{name}/config` | PATCH | Update runtime config |
| `/agents/{name}/test` | POST | Test agent with sample input |
| `/gm/oracle` | POST | Ask oracle a binary question |
| `/gm/recap` | POST | Generate session recap |
| `/gm/simulacrum` | POST | Simulate NPC behavior |
| `/chat/ws/{sessionId}/npc/{characterId}` | WS | NPC voice chat |
| `/token-budgets` | GET | List token budget config |
| `/token-budgets/{role}` | PATCH | Update budget for role |
| `/context-weights` | GET/PATCH | Context assembly weight config |
| `/scene-loop/config` | GET/PATCH | Scene loop configuration |
| `/resolver/patterns` | GET/POST/DELETE | Resolver intent patterns |
| `/oracle/dc-map` | GET/PATCH | Oracle DC map configuration |
| `/combat/state` | GET/POST/PATCH | Combat tracker state |
| `/encounters` | POST | Build and start encounter |

---

## 13. API Methods to Add to `api.ts`

| Group | Method | Endpoint |
|-------|--------|----------|
| `universesApi` | `seedUniverse` | `POST /universes/{id}/seed` |
| `universesApi` | `forkUniverse` | `POST /universes/{id}/fork` |
| `universesApi` | `createSnapshot` | `POST /universes/{id}/snapshots` |
| `universesApi` | `listSnapshots` | `GET /universes/{id}/snapshots` |
| `universesApi` | `restoreSnapshot` | `POST /universes/{id}/snapshots/{sid}/restore` |
| `universesApi` | `compareSnapshots` | `GET /universes/{id}/snapshots/compare` |
| `universesApi` | `updateUniverse` | `PUT /universes/{id}` |
| `performanceApi` | `getOverview` | `GET /performance` |
| `performanceApi` | `getSlowQueries` | `GET /performance/slow-queries` |
| `performanceApi` | `getAlerts` | `GET /performance/alerts` |
| `performanceApi` | `configureAlerts` | `PUT /performance/alerts/config` |
| `performanceApi` | `setBaseline` | `POST /performance/baseline` |
| `performanceApi` | `resetMetrics` | `POST /performance/reset` |
| `performanceApi` | `checkHealth` | `POST /performance/alerts/check-health` |
| `lorebookApi` | `listEntries` | `GET /lorebook/entries` |
| `lorebookApi` | `createEntry` | `POST /lorebook/entries` |
| `lorebookApi` | `updateEntry` | `PATCH /lorebook/entries/{id}` |
| `lorebookApi` | `deleteEntry` | `DELETE /lorebook/entries/{id}` |
| `lorebookApi` | `bulkCreate` | `POST /lorebook/bulk` |
| `lorebookApi` | `inject` | `POST /lorebook/inject` |
| `lorebookApi` | `getStats` | `GET /lorebook/stats` |
| `lorebookApi` | `getTop` | `GET /lorebook/top` |
| `searchApi` | `search` | `GET /search` |
| `searchApi` | `searchUniverse` | `GET /search/universes/{id}/search` |
| `entitiesApi` | `batchCreate` | `POST /entities/batch` |
| `entitiesApi` | `batchUpdate` | `PATCH /entities/batch` |
| `entitiesApi` | `batchDelete` | `DELETE /entities/batch` |
| `entitiesApi` | `createRelationship` | `POST /entities/relationships` |
| `entitiesApi` | `linkArchetype` | `POST /entities/{id}/link-archetype/{aid}` |
| `entitiesApi` | `saveTemplate` | `POST /entities/{id}/save-template` |
| `entitiesApi` | `listCharacterSheets` | `GET /character-sheets` |
| `entitiesApi` | `getCharacterSheet` | `GET /character-sheets/{id}` |
| `entitiesApi` | `updateCharacterSheet` | `PATCH /character-sheets/{id}` |
| `entitiesApi` | `deleteCharacterSheet` | `DELETE /character-sheets/{id}` |
| `ingestApi` | `clearCache` | `POST /ingest/cache/clear` |
| `ingestApi` | `unlockQueue` | `POST /ingest/queue/unlock` |
| `promptsApi` | `getStatus` | `GET /prompts/status` |
| `storiesApi` | `listScenes` | `GET /stories/{id}/scenes` |

---

## 14. File Structure (New Components)

```
packages/ui/frontend/src/
├── app/
│   ├── agents/page.tsx              # NEW: Agent Dashboard
│   ├── monitoring/page.tsx          # NEW: Performance Dashboard
│   ├── prompts/page.tsx             # REPLACE: Real prompt editor (remove redirect)
│   └── error.tsx                     # NEW: Next.js error boundary
│
├── components/
│   ├── ErrorBoundary.tsx            # NEW: React error boundary
│   ├── ConnectionStatus.tsx         # NEW: Backend connection indicator
│   ├── CommandPalette.tsx           # NEW: Ctrl+/ command palette
│   │
│   ├── play/
│   │   ├── SessionStatePanel.tsx    # NEW: Live session state
│   │   ├── OracleTool.tsx           # NEW: Ask the oracle
│   │   ├── RecapGenerator.tsx       # NEW: Session recap
│   │   └── NpcVoiceChat.tsx         # NEW: NPC dialogue
│   │
│   ├── forge/
│   │   ├── ProposalReviewPanel.tsx  # NEW: CanonKeeper proposals
│   │   ├── CanonizePackModal.tsx    # NEW: Canonize workflow
│   │   ├── BatchEntityPanel.tsx     # NEW: Batch operations
│   │   ├── RelationshipEditor.tsx   # NEW: Entity relationships
│   │   └── EntityGenerator.tsx     # NEW: Generate entity
│   │
│   ├── gm/
│   │   ├── CombatTracker.tsx        # NEW: Initiative + HP
│   │   ├── EncounterBuilder.tsx     # NEW: Encounter difficulty
│   │   ├── SimulacrumTool.tsx       # NEW: NPC simulation
│   │   └── LorebookManager.tsx      # NEW: Lorebook CRUD
│   │
│   ├── agents/
│   │   ├── AgentCard.tsx            # NEW: Agent status card
│   │   ├── AgentConfigPanel.tsx     # NEW: Per-agent config
│   │   ├── TokenBudgetPanel.tsx     # NEW: Token budget sliders
│   │   ├── ContextWeightsPanel.tsx  # NEW: Context assembly weights
│   │   ├── SceneLoopConfig.tsx      # NEW: Scene loop config
│   │   ├── ResolverPatterns.tsx     # NEW: Intent pattern table
│   │   └── OracleDcMap.tsx          # NEW: Oracle DC map editor
│   │
│   ├── monitoring/
│   │   ├── PerformanceOverview.tsx  # NEW: Metrics dashboard
│   │   ├── SlowQueriesTable.tsx     # NEW: Slow query list
│   │   ├── AlertsPanel.tsx          # NEW: Alert config
│   │   └── BaselinePanel.tsx        # NEW: Performance baselines
│   │
│   └── worlds/
│       ├── SnapshotManager.tsx      # NEW: Snapshot CRUD
│       ├── SnapshotCompare.tsx      # NEW: Snapshot diff view
│       ├── ForkUniverseModal.tsx    # NEW: Fork dialog
│       └── SeedUniverseModal.tsx    # NEW: Seed dialog
│
├── hooks/
│   └── useChatWebSocket.ts          # NEW: Reconnecting WebSocket hook
│
└── lib/
    ├── api.ts                       # EXPAND: Add all missing API methods
    └── query-keys.ts                 # EXPAND: Add new key groups
```

---

*This plan is a living document. Update as implementation progresses.*