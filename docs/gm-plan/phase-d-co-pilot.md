## Phase D — Co-Pilot Mode (2 weeks)

> **Delivers:** Human GM assistance tools. Session recording. Prep generation.

### D.1 Co-Pilot Session Mode

**Why:** Not every GM wants AI running the game. Many want AI assistance while they GM: stat lookups, NPC voice suggestions, rule reminders, continuity checking.

| Task | File(s) | Details |
|------|---------|---------|
| Co-pilot play mode | `scene_loop.py` + `chat.py` | New `play_mode: "copilot"`. In this mode: (1) player messages are GM input, not character actions, (2) system responds with suggestions, not narration, (3) no auto-roll, (4) CanonKeeper still tracks canon |
| GM control panel | `packages/ui/frontend/` (NEW views) | React views for: (1) session state overview, (2) entity browser, (3) relationship graph viewer, (4) pending proposals queue, (5) manual CanonKeeper triggers |
| Session recording | `chat.py` | Co-pilot mode records all GM descriptions and player actions as turns (even though system isn't generating narration). Enables: session replay, continuity checking, future reference |
| Continuity checker | `agents/continuity.py` (NEW) | Between sessions, scan recorded turns for contradictions. "Session 1: NPC died. Session 2: NPC speaks." → flag continuity error |
| Prep generator | `agents/prep_generator.py` (NEW) | Input: upcoming session notes, world state, active threads. Output: suggested encounters, NPC motivations, scene hooks, possible consequences. Not scripted — just prep material for the human GM |

**Success criteria:**
- [ ] Co-pilot mode accepts GM input and returns suggestions (not narration)
- [ ] Session recording captures all GM/player exchanges
- [ ] Continuity checker detects at least obvious contradictions
- [ ] Prep generator produces usable session prep material

### D.2 GM Control Panel (Backend)

| Task | File(s) | Details |
|------|---------|---------|
| Session state API | `packages/ui/backend/src/monitor_ui/routers/sessions.py` | Endpoint: `GET /api/sessions/{id}/state` — returns current phase, turns count, active threads, pending proposals, entity states |
| Entity browser API | `packages/ui/backend/src/monitor_ui/routers/entities.py` | Endpoint: `GET /api/universes/{id}/entities` — paginated, filterable entity list with relationships |
| Proposal queue API | NEW router or extend `canon.py` | Endpoints: `GET /proposals/pending`, `POST /proposals/{id}/accept`, `POST /proposals/{id}/reject` — manual CanonKeeper control |
| Canon trigger API | NEW router | `POST /api/canon/evaluate` — trigger CanonKeeper evaluation on demand |

**Success criteria:**
- [ ] All GM control panel endpoints functional
- [ ] Entity browser returns paginated results with relationship data
- [ ] Manual CanonKeeper accept/reject works through API

---

