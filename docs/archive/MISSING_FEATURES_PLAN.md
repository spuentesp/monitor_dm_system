# Missing Features — Implementation Roadmap

> Features that have specifications and `.yml` definitions but **no code implementation** yet.

---

## Stack Reference

| Layer | Tech | Location |
|-------|------|----------|
| **Data Layer** (L1) | Python, MCP tools | `packages/data-layer/src/monitor_data/tools/` |
| **Agents** (L2) | Python, LangGraph, DSPy | `packages/agents/src/monitor_agents/` |
| **Backend API** (L3) | FastAPI, WebSocket | `packages/ui/backend/src/monitor_ui/routers/` |
| **Frontend** (L3) | Next.js, TailwindCSS | `packages/ui/frontend/src/` |

### Existing Frontend Surfaces

| Route | Page | Purpose |
|-------|------|---------|
| `/play` | `app/play/page.tsx` | Live play chat (WebSocket) |
| `/worlds` | `app/worlds/page.tsx` | Entity graph browser (66KB) |
| `/forge` | `app/forge/page.tsx` | Pack library & sources (75KB) |
| `/architect` | `app/architect/` | World Architect mode |
| `/systems` | `app/systems/` | Game system browser |
| `/settings` | `app/settings/` | LLM, DB config |
| `/gm` | `app/gm/` | GM Assistant mode |

---

## Feature Group 1: Core Play Loop (P-3 → P-9)

> These features form the heart of the solo RPG experience.

| ID | Feature | Status |
|----|---------|--------|
| P-3 | Turn Loop | Partial (chat_loops.py has SceneLoop) |
| P-4 | Resolve Action | Partial (Resolver agent exists) |
| P-5 | Handle Dialogue | Partial (Narrator handles this) |
| P-6 | Answer Question | Not implemented |
| P-7 | Meta Commands | Not implemented |
| P-8 | End Scene (Canonization) | Not implemented |
| P-9 | Dice Roll | Not implemented |

### Data Layer (L1)
- **[NEW]** `tools/dice_tools.py` — `roll_dice(formula: str)`, `evaluate_dc(action, context)`
- **[MODIFY]** `tools/mongodb_tools/scene_tools.py` — Add `finalize_scene()`, `get_scene_summary()`
- **[MODIFY]** `tools/neo4j_tools/fact_tools.py` — Add `commit_proposed_changes(scene_id)` for canonization

### Agents (L2)
- **[MODIFY]** `loops/scene_loop.py` — Add meta-command interception before input parsing
- **[NEW]** `prompts/question_answerer.py` — DSPy module for P-6 (query canon to answer player questions)
- **[MODIFY]** `agents/resolver.py` — Integrate `roll_dice` tool, add DC calculation

### Backend API (L3)
- **[MODIFY]** `routers/chat_loops.py` — Add `/`-command routing before SceneLoop processing
- **[NEW]** `routers/dice.py` — `POST /api/dice/roll` for standalone dice rolling (used by GM Assistant too)

### Frontend (L3)
- **[MODIFY]** `app/play/page.tsx` — Add dice roll UI widget (inline roll results with animation)
- **[MODIFY]** `components/play/` — Add `DiceRoller.tsx` (interactive dice selector + roll button)
- **[MODIFY]** `components/play/` — Add `MetaCommandPalette.tsx` (slash-command autocomplete overlay triggered by `/`)
- **[MODIFY]** `app/play/page.tsx` — Add "End Scene" button in the scene header bar, triggering P-8 canonization flow with a confirmation modal showing proposed changes

---

## Feature Group 2: Combat Mode (P-10)

| ID | Feature | Status |
|----|---------|--------|
| P-10 | Combat Mode | Not implemented |

### Data Layer (L1)
- **[NEW]** `tools/mongodb_tools/combat_tools.py` — `get_combatants()`, `update_hp()`, `log_combat_turn()`
- **[MODIFY]** `tools/mongodb_tools/character_tools.py` — Add `get_character_sheets(entity_ids)`, `update_character_sheet()`

### Agents (L2)
- **[NEW]** `loops/combat_loop.py` — LangGraph state machine: `INITIATIVE → TURN → RESOLVE → CHECK_END → NEXT_TURN`
- **[MODIFY]** `agents/resolver.py` — Add `resolve_attack()`, `resolve_spell()` methods
- **[MODIFY]** `agents/narrator.py` — Add `describe_combat_action()`, `decide_npc_action()`

### Backend API (L3)
- **[MODIFY]** `routers/chat_loops.py` — Detect combat trigger in SceneLoop, switch to CombatLoop WebSocket stream
- **[NEW]** `routers/combat.py` — `POST /api/combat/initiative`, `POST /api/combat/action`

### Frontend (L3)
- **[NEW]** `components/play/CombatTracker.tsx` — Initiative order sidebar, HP bars, turn indicator, action buttons
- **[MODIFY]** `app/play/page.tsx` — When combat is active, render `CombatTracker` alongside the chat stream; highlight the active combatant's turn; show attack/spell/move action buttons instead of free text input

---

## Feature Group 3: Conversation Mode (P-11)

| ID | Feature | Status |
|----|---------|--------|
| P-11 | Conversation Mode | Not implemented |

### Data Layer (L1)
- **[MODIFY]** `tools/mongodb_tools/memory_tools.py` — Add `get_npc_memories()`, `create_npc_memory()`
- **[MODIFY]** `tools/qdrant_tools.py` — Add `search_npc_memories(npc_id, query)`

### Agents (L2)
- **[NEW]** `loops/conversation_loop.py` — LangGraph state machine for focused NPC dialogue
- **[NEW]** `prompts/npc_voice.py` — DSPy module that generates in-character NPC responses using personality + secrets + memories
- **[NEW]** `context/npc_context.py` — `get_npc_full_context(npc_id)` assembling personality, goals, secrets, relationships, memories

### Backend API (L3)
- **[MODIFY]** `routers/chat_loops.py` — Detect conversation trigger, switch to ConversationLoop

### Frontend (L3)
- **[NEW]** `components/play/ConversationPanel.tsx` — NPC portrait, relationship meter, topic tracker, "revealed secrets" log
- **[MODIFY]** `app/play/page.tsx` — When in conversation mode, render NPC context panel alongside chat; show NPC name and portrait in chat header; display relationship delta feedback after conversation ends

---

## Feature Group 4: Story Continuity (P-12 → P-14)

| ID | Feature | Status |
|----|---------|--------|
| P-12 | Continue Story | Not implemented |
| P-13 | Party Management | Not implemented |
| P-14 | Flashback Mode | Not implemented |

### Data Layer (L1)
- **[MODIFY]** `tools/mongodb_tools/scene_tools.py` — Add `get_latest_scene(story_id)`, `get_party_state()`
- **[MODIFY]** `tools/neo4j_tools/entity_tools.py` — Add `get_party_members()`, `update_party_composition()`
- **[NEW]** `tools/neo4j_tools/timeline_tools.py` — `create_flashback_branch()`, `validate_timeline_consistency()`

### Agents (L2)
- **[MODIFY]** `loops/scene_loop.py` — Add `continue_story()` entry point that bootstraps from last canon state
- **[NEW]** `agents/party_manager.py` — Agent for party splits, merges, inventory redistribution
- **[NEW]** `loops/flashback_loop.py` — Time-locked scene loop that validates outputs against current canon

### Backend API (L3)
- **[MODIFY]** `routers/chat_opening.py` — Add "Continue Story" flow alongside "New Story"
- **[NEW]** `routers/party.py` — `GET /api/party/{story_id}`, `POST /api/party/split`, `POST /api/party/merge`

### Frontend (L3)
- **[MODIFY]** `app/play/page.tsx` — Add "Continue Story" button on the play landing page (shows list of in-progress stories with last scene summary)
- **[NEW]** `components/play/PartyPanel.tsx` — Party roster sidebar with drag-and-drop for splits/merges, shared inventory view
- **[NEW]** `components/play/FlashbackBanner.tsx` — Visual indicator when in flashback mode (sepia-toned UI, timeline warning bar)

---

## Feature Group 5: World Management (M-32 → M-35)

| ID | Feature | Status |
|----|---------|--------|
| M-32 | Manage Archetypes | Not implemented |
| M-33 | Manage Random Tables | Not implemented |
| M-34 | World Snapshots | Not implemented |
| M-35 | Universe Fork | Not implemented |

### Data Layer (L1)
- **[NEW]** `tools/mongodb_tools/archetype_tools.py` — CRUD for entity templates
- **[NEW]** `tools/mongodb_tools/random_table_tools.py` — CRUD + `roll_on_table(table_id)`
- **[NEW]** `tools/neo4j_tools/snapshot_tools.py` — `snapshot_universe()`, `restore_snapshot()`, `fork_universe()`

### Agents (L2)
- **[NEW]** `agents/world_manager.py` — Agent that orchestrates archetype instantiation, snapshot creation, and universe forking via MCP tools

### Backend API (L3)
- **[NEW]** `routers/archetypes.py` — Full CRUD: `GET/POST/PUT/DELETE /api/archetypes`
- **[NEW]** `routers/random_tables.py` — CRUD + `POST /api/tables/{id}/roll`
- **[NEW]** `routers/snapshots.py` — `POST /api/universes/{id}/snapshot`, `POST /api/universes/{id}/fork`

### Frontend (L3)
- **[NEW]** `app/worlds/archetypes/page.tsx` — Archetype library browser with template editor (form-based creation of entity templates with default stats, traits, etc.)
- **[NEW]** `app/worlds/tables/page.tsx` — Random table editor (nested table builder UI, "Roll" button with animated result)
- **[MODIFY]** `app/universes/page.tsx` — Add "Snapshot" and "Fork" buttons to each universe card; snapshot history timeline; fork confirmation dialog showing estimated duplication size
- **[MODIFY]** `components/Sidebar.tsx` — Add "Archetypes" and "Tables" sub-items under the "Build → Worlds" section

---

## Implementation Priority

| Priority | Group | Rationale |
|----------|-------|-----------|
| **P0** | Core Play Loop (P-3–P-9) | Dice, meta commands, and canonization are blockers for every play session |
| **P1** | Combat Mode (P-10) | Core RPG mechanic, high user demand |
| **P1** | Conversation Mode (P-11) | Core RPG mechanic, differentiator for narrative AI |
| **P2** | Story Continuity (P-12–P-14) | Required for multi-session campaigns |
| **P3** | World Management (M-32–M-35) | Power-user features, enhances world building depth |
