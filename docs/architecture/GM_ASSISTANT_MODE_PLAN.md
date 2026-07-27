# GM Assistant (Co-Pilot) Mode — Implementation Plan

> **Status:** proposed (2026-07-23). Every claim verified against code on
> 2026-07-23. Supersedes the gap list in `GAP_REMEDIATION_PLAN.md` §G-5, whose
> decision (Option A: the web `/gm` page is THE copilot surface — no CLI
> `monitor copilot`) is adopted here as settled.
>
> Conventions: DSPy modules are co-located with their respective agents;
> MCP calls async; `structlog` (no print); pydantic v2; line-length 100; mypy
> strict; layer rules (UI/CLI → agents → data-layer, only CanonKeeper writes
> Neo4j). Test fixtures: `FakeMCPClient`/`FakeLLMClient` in
> `tests/conftest.py:165,261`.

---

## 1. Product definition

**The idea in plain terms.** You are a human GM running a session at your table
(or online). MONITOR sits next to you on a laptop as your **memory and analyst**,
not as the GM. Three things it does:

1. **It remembers everything, so you don't have to.** You start a recording for
   your campaign and log quick entries as play happens — "Mira pocketed the
   key", "the party burned the docks". MONITOR keeps the transcript, tags who
   was there and where, and extracts candidate facts from each entry.
2. **It watches for continuity mistakes.** You narrate "the baron greets them
   warmly" — but three sessions ago the players killed the baron. MONITOR flags
   that *as you log it*, not after the session. It also surfaces unresolved
   threads, suggests hooks when you're stuck, and answers rules questions for
   your game system. Dice rolls are server-side and honest.
3. **It archives the session.** On close, every world change you logged is
   queued for your approval before it becomes canon — nothing writes itself
   into the world. You get a wrap-up digest: recap, what changed, what's still
   open, prep notes for next time. Months later you can answer "what happened
   in session 12?"

The human keeps full narrative control; the system is the perfect secretary
that never forgets and catches contradictions.

**Persona.** A human GM running a tabletop session — physical or online — with
MONITOR open on a laptop/tablet beside them. The GM leads; MONITOR is "Memory +
Analyst" (`docs/1_product/vision_and_modes.md:25`) during play and "Archivist"
(`:27`) after. The GM glances at panels between table moments; nothing may
require typed conversation with the system to be useful.

**The three workflows.**

1. **Live session capture (CF-1).** The GM starts a recording for a universe
   and logs entries as play happens ("Mira pocketed the key"). MONITOR keeps
   the transcript, tags participants/locations, shows candidate facts per
   entry, and fires continuity alerts when an entry collides with canon.
2. **During-play assistance (CF-3..CF-7).** Glanceable panels: rules reference
   for the universe's bound system, server-authoritative dice, unresolved
   threads, plot hooks, contradiction checks, session prep, player handouts.
3. **Post-session archival (CF-2, CF-8).** "Close session" queues every world
   change for canon review; a guided wrap-up digest (recap + canon decisions +
   thread delta + next-prep teaser) is persisted as the session's artifact, so
   "what happened in session 12?" is answerable months later.

**Non-goals.**

- No CLI `monitor copilot` surface (decision from GAP_REMEDIATION_PLAN §G-5).
- No auto-canonization from capture: only CanonKeeper writes Neo4j, and only
  via human-approved `ProposedChange`s. Live alerts and candidate facts are
  advisory; they never write.
- No replacement of the GM's rulings: dice results, alerts, and digests are
  inputs to human judgment, not adjudication.
- No audio capture in this plan (descoped in P3.1 unless explicitly built).
- No second UX for solo play: the Play Console (`/play`) stays the solo-GM
  surface; nothing here changes `SceneLoop` turn mechanics for play sessions.
- No authoring surface: world building, ingestion, and pack management live in
  the Forge (`/forge`, see `FORGE_MODE_PLAN.md`). The three modes are Solo Play
  (`/play`, MONITOR is the GM), GM Assistant (`/gm`, you are the GM, MONITOR
  assists), and Forge (`/forge`, you build the world) — one app, three hats.

---

## 2. Current-state inventory

| Surface | What exists | Status | File refs |
|---|---|---|---|
| `/gm` page | 9 panels, 3-column desktop layout + tabbed mobile | Works | `packages/ui/frontend/src/app/gm/page.tsx:1064-1074` (`GM_PANELS`), `:1153-1245` |
| Universe/system selector | Multiverse→universe cascade; manual system dropdown | Works, but system is manual-only | `page.tsx:990-1058` (`GMSelector`), system select `:1047-1055` |
| Session Recorder (CF-1) | `gm_assistant` chat session per recording; entries via `chatApi.sendMessage`; auto story+scene bootstrap ("Human-led session capture and review"); close → `endScene`; proposals → `CanonReviewPanel`; RecapModal → RecapAgent | Works; insights are the generic Narrator response | `components/gm/SessionRecorder.tsx:92-153`; `loops/session_bootstrap.py:121-139`; `routers/chat.py:602-769` (send → `_run_scene_turn`, no mode branch); `chat_loops.py:1792-1893` (`run_end_scene`) |
| Rules reference | Renders core mechanic/attributes/resources/rules for a `systemId` | Works, not universe-aware | `page.tsx:181-304` (`RulesPanel`) |
| Dice roller | Quick dice, expression input, 20-roll history | Works, **client `Math.random`** — violates server-authoritative dice doctrine | `page.tsx:46-61` (`rollDie`/`parseDiceExpression`), `:73-175`; doctrine: `PLAY_AND_FORGE_DIRECTION.md` §2 (`:127-130`) |
| Scratchpad | Notes textarea + Save + Ingest (full document pipeline) | Ephemeral (`localStorage` only); ingest proposals disconnected from recording | `page.tsx:310-414` (`SessionNotebook`; `STORAGE_KEY` `:320`, save `:332-340`, ingest `:342-356`) |
| Plot hooks (CF-4) | `POST /gm/hooks` → `PlotHookAgent.suggest_hooks` | Works | `routers/gm_tools.py:103-117`; `agents/plot_hooks.py:136-230` |
| Contradiction detection (CF-5) | `POST /gm/contradictions` → `PlotHookAgent.detect_contradictions` (whole-canon scan) | Works, **manual button only** | `gm_tools.py:120-135`; `plot_hooks.py:236-321`; button `page.tsx:524-531` |
| Unresolved threads (CF-3) | Story-scoped thread list | Works | `page.tsx:743-831`; `storiesApi.listThreads` |
| Session prep (CF-7) | `POST /gm/session-prep` → recap/threads/hooks/NPC reminders | Works, on-demand only | `gm_tools.py:138-152`; `plot_hooks.py:327-395` |
| Handouts (CF-6) | `POST /gm/handouts` → type/tone/spoiler-level handout | Works | `gm_tools.py:155-171`; `plot_hooks.py:401-527` |
| Recap (CF-2) | `GET /chat/{id}/recap` → `RecapAgent.generate_recap` | Works, **regenerated every call, never persisted** | `routers/chat.py:499-545`; `agents/recap_agent.py:42-107`; `components/play/RecapModal.tsx` |
| Canon review (CF-8) | Scene/story/ingest-job queues + verdicts | Works | `routers/canon_review.py:103-341`; `components/canon/CanonReviewPanel` |
| CanonKeeper contradiction machinery | `ContradictionModule` (DSPy), per-fact `verify_fact`, scene-end `_check_contradiction` | Works, **runs only at proposal evaluation** | `agents/canonkeeper.py:327-360` (`verify_fact`), `:2411-2529` (`_check_contradiction`), `packages/agents/src/monitor_agents/canonkeeper/verification.py` |
| Server dice utility | Expression parser + roller (`NdS±M`, keep-high/low) | Exists in data-layer, unused by `/gm` | `packages/data-layer/src/monitor_data/utils/dice.py:63` (`roll_dice`) |
| Universe→system binding | `Universe.default_game_system_id`; already resolved server-side for chat | Exists, **not surfaced to `/gm`** | `schemas/universe.py:167`; `routers/chat_game_system.py:53-54` |
| CLI copilot | Nothing | Doc debt only: `main.py:10-17` docstring, `vision_and_modes.md:25,27`, `session-support.md:39` (cites deleted `session_ingest.py`) | — |
| Audio/hybrid capture (CF-1 spec) | Nothing | Spec-only | `CF-1/CF-1-specification.md:22-26` |

**Mode-card note.** `routers/modes.py:60-76` already advertises "continuity
alerts" and "automatic entity extraction" as GM Assistant capabilities — both
are aspirational today. Phase 1 makes the card true.

---

## 3. Phase 0 — Doc alignment (S, do first)

**Goal:** docs stop promising a CLI copilot and stop citing deleted modules, so
later phases are judged against the real spec.

- [x] `docs/1_product/vision_and_modes.md:22-27` — modes table: Assisted GM
  target surface `monitor copilot` → "web `/gm` (GM Assistant)"; Post-Session
  Analysis `monitor copilot, monitor query` → "web `/gm` + `monitor query`".
  *(Done 2026-07-23 — surfaces also updated for Solo Play/World Design rows;
  `monitor query` doesn't exist, so Post-Session reads "web `/gm` (wrap-up &
  archive)".)*
- [x] `packages/cli/src/monitor_cli/main.py:10-17` — module docstring: drop the
  `$ monitor copilot` line; note the copilot lives in the web UI.
  *(Done 2026-07-23 — docstring rewritten to list only registered commands;
  `monitor query`/`monitor story` phantom entries dropped too.)*
- [x] `docs/use-cases/epic-7-copilot-CF/session-support.md:35-42` — status
  table: CF-1 backend row cites deleted
  `packages/agents/src/monitor_agents/session_ingest.py` → cite
  `SessionRecorder.tsx` + `session_bootstrap.py:121-139`; CF-2 row cites
  `story_loop.py:988` → cite `recap_agent.py` + `routers/chat.py:499-545`.
  Refresh the "Last verified" date. *(Done 2026-07-23.)*
- [x] `docs/use-cases/epic-7-copilot-CF/CF-1/CF-1-specification.md:46-50` —
  remove the `monitor copilot record` CLI block; replace with the `/gm`
  recorder flow. Layer-2 section (:40-44) cites `Orchestrator.start_recording_session`
  / `Narrator.parse_gm_input` which do not exist → replace with
  `session_bootstrap.bootstrap_story_scene` + the P1.2 capture-insights module.
  *(Done 2026-07-23 — P1.2 module cited as planned.)*
- [x] `docs/STATUS.md:100` — rewrite the "Co-Pilot mode polish" bullet to point
  at this plan. *(Done 2026-07-23 — gap 4 bullet links here.)*

**Tests:** none (docs only). **Effort:** S (~0.5 day). **Depends on:** nothing.

---

## 4. Phase 1 — Core capture loop

### P1.1 · Live contradiction alerts during capture (M)

**Goal:** an entry that collides with canon raises an inline alert in the
recorder within a beat — not after scene end. Reuses CanonKeeper machinery;
does not duplicate it, and writes nothing (advisory only).

**Design.** CanonKeeper already exposes the per-fact check as a public method:
`verify_fact(new_fact, context)` (`canonkeeper.py:327-360`, DSPy
`ContradictionModule` with heuristic fallback). What it lacks is a public
entry point that assembles its own context — `_fetch_canon_facts` /
`_fetch_canon_axioms` are private (`:2379`, `:2395`) and used only inside
proposal evaluation (`:2472-2473`).

1. **Agents — one public method.** In `packages/agents/src/monitor_agents/canonkeeper.py`,
   next to `verify_fact` (:360), add:

   ```python
   async def check_live_entry(
       self, universe_id: UUID, entry_text: str
   ) -> Dict[str, Any]:
       """Advisory contradiction check for a capture entry (CF-1).

       Read-only: never creates proposals, never writes to Neo4j."""
   ```

   Body: `facts = await self._fetch_canon_facts(universe_id)` and axioms
   likewise, build `context` strings exactly as `_check_contradiction` does
   (:2475-2481), return `{"has_contradiction": False, ...}` early when context
   or entry is empty, else `await self.verify_fact(entry_text, context)`.
   One LLM call per invocation.
2. **Backend — one endpoint.** In `routers/gm_tools.py` (after :171):

   `POST /gm/capture/contradiction-check` — request
   `{universe_id: UUID, entry_text: str (1..4000)}`; response
   `{alert: Contradiction | None}` reusing the `Contradiction` model imported
   from `monitor_agents.plot_hooks` (:56-66). Instantiates `CanonKeeper()` per
   request (same per-request agent pattern as :106) and maps
   `has_contradiction` + `explanation` into a `Contradiction`
   (`fact_a` = canon context summary, `fact_b` = entry excerpt, severity
   "medium", `suggestion` = "review before canonizing"). Exceptions → 500 with
   the same `HTTPException` shape as :114-117. structlog warning on failure.
3. **Frontend — recorder wiring.** In `SessionRecorder.tsx` `logEntry`
   (:107-137): after `sendMessage` resolves, fire
   `gmApi.checkEntryContradiction(universeId, text)` (new `api.ts` method,
   non-blocking, no `setWaiting`). On a hit, store
   `{messageText, alert}` in local state and render an amber `AlertTriangle`
   alert card directly under the matching transcript entry (the transcript map
   at :236-267). Client-side guard: skip entries < 12 chars to avoid trivial
   checks. Manual "Detect" panel (`page.tsx:502-575`) stays as-is — whole-canon
   scan, different job.

**Tests.**
- `packages/agents/tests/` new `test_canonkeeper_live_entry.py`: with
  `FakeMCPClient`/`FakeLLMClient` (`tests/conftest.py:165,261`) — empty canon
  → no alert, no LLM call; contradiction found → explanation propagated;
  `ContradictionModule` raising → heuristic fallback engaged (pattern of
  `verify_fact` tests, `canonkeeper.py:355-360`).
- `packages/ui/backend/tests/test_gm_capture_alerts.py` (modeled on
  `test_dice_server_roll.py`): mock `CanonKeeper.check_live_entry`; 200 with
  alert, 200 with null alert, 422 on empty `entry_text`.
- Frontend: extend a new `SessionRecorder.test.tsx` (vitest + Testing Library,
  pattern of `PlayConsole.test.tsx`): alert card renders when the API resolves
  with a contradiction; absent otherwise.

**Risks:** one STANDARD LLM call per entry — acceptable at human typing
cadence; document cost in the endpoint docstring. False positives are cheap
(advisory only). **Effort:** M. **Depends on:** Phase 0 (cosmetic ordering
only — technically independent). **Status: SHIPPED 2026-07-23** —
`CanonKeeper.check_live_entry` (read-only, early-return on empty canon/entry),
`POST /api/gm/capture/contradiction-check`, non-blocking check in
`SessionRecorder.logEntry` (≥12 chars) with amber inline alert cards. Tests: 4
agents + 5 backend + 3 frontend, all green; layer-check clean.

### P1.2 · Capture-specific per-entry insights (M)

**Goal:** each logged entry is analyzed for **participants, locations, and
candidate facts** and shows them inline — CF-1 spec steps 3/5
(`CF-1-specification.md:13-17`) — instead of today's generic Narrator reply
(the recorder's send path is the unmodified play turn, `chat.py:732-745`).

**Design.**

1. **DSPy module.** Extend `packages/agents/src/monitor_agents/ingestion/session_ingest.py`
   (it already holds the live-session extraction signature used by
   `ingestion_loop.py:174` — same domain, right home). Add
   `CaptureEntrySignature` + `CaptureEntryModule` (`dspy.Predict`, role
   `ModelRole.LIGHT` — per-entry volume): inputs `entry_text`,
   `known_entities` (name list), `open_threads`; outputs
   `participants: List[str]`, `locations: List[str]`,
   `candidate_facts: List[str]`, `advances_thread: str` ("" if none).
   Docstring rules: only name participants/locations grounded in `entry_text`;
   prefer canonical names from `known_entities`; candidate facts are
   world-state claims only ("the key is now with Mira"), no dialogue, no
   trivia.
2. **Agent.** New thin `packages/agents/src/monitor_agents/capture_insights.py`
   mirroring `plot_hooks.py`'s structure: `CaptureInsightAgent(BaseAgent)`
   with `run()` stub (:533-535 pattern) and
   `async analyze_entry(universe_id, entry_text) -> CaptureInsight` (pydantic
   model in the same file). Fetches known entity names via
   `neo4j_list_entities` and open threads via `neo4j_list_plot_threads` through
   `self.call_tool` (pattern :153-172), then `asyncio.to_thread` on the module
   (pattern `canonkeeper.py:349-353`). LLM failure → structlog warning + empty
   insight (never block logging).
3. **Backend.** `POST /gm/capture/insights` in `gm_tools.py`: request
   `{universe_id, entry_text}`; response `CaptureInsight`. Same per-request
   agent + `HTTPException` pattern.
4. **Frontend.** `SessionRecorder.tsx`: after each `logEntry` resolves, call
   `gmApi.captureInsights(...)`; render under the entry: participant/location
   chips (existing chip styling at :287-295) and a collapsible "Candidate
   facts" list.

**Deliberately out of scope (stated to avoid over-scoping):** auto-creating
`ProposedChange`s per entry. Scene-end proposals already land in
`CanonReviewPanel`; per-entry auto-proposals would flood the CF-8 queue.
Candidate facts are *visible, not proposed*; the GM's close-session review is
the promotion path.

**Tests.**
- `packages/agents/tests/test_capture_insights.py`: `FakeMCPClient` supplies
  entities/threads; module mocked (DSPy path, cf. G-4 note — assert prompt
  construction and result mapping, not canned text); failure path returns
  empty insight.
- Behavior test (pattern `tests/behavior/`): signature docstring contains the
  grounding rule ("only name participants/locations grounded in the entry").
- Backend test: 200 shape, 422 on empty text.
- Frontend: chips + candidate-facts list render from a mocked API response.

**Effort:** M. **Depends on:** none (pairs naturally with P1.1 in the UI).
**Status: SHIPPED 2026-07-23** — `CaptureEntrySignature`/`CaptureEntryModule`
(LIGHT) in `packages/agents/src/monitor_agents/ingestion/session_ingest.py`, new `capture_insights.py` agent
(fail-open: LLM failure → empty insight, never blocks logging), `POST
/api/gm/capture/insights`, participant/location chips + "Advances: thread" +
collapsible candidate-facts under each entry (alongside P1.1 alerts).
Auto-proposals deliberately not built. Tests: 20 targeted (agents + behavior +
backend + frontend) all green; layer-check clean.

### P1.3 · Guided end-of-session wrap-up digest (M)

**Goal:** one "Wrap up" action that sequences what exists today unsequenced:
recap (RecapAgent), canon decisions (CF-8 queue), open-threads state, and a
next-session prep teaser (PlotHookAgent).

**Design.**

1. **Backend — endpoint in the chat router** (it owns sessions and already
   hosts `/recap`). In `routers/chat.py` next to `get_session_recap`
   (:499-545): `POST /{session_id}/wrap-up`. Flow:
   - Load session; 404 unknown; 409 unless `mode == "gm_assistant"` (this is a
     recording affordance, not a play one).
   - If `phase != "scene_ended"`, run `run_end_scene` first (imported at :75)
     so wrap-up includes canonization — one click for the GM.
   - Recap via `RecapAgent` (:525-528 pattern).
   - Canon decisions: `mongodb_list_proposed_changes(ProposedChangeFilter(story_id=...))`
     (data-layer read; `canon_review.py` already imports data-layer directly
     from a router, and `chat_loops.py` uses `run_sync_read` — :1824-1829)
     → counts + items grouped ACCEPTED/REJECTED/PENDING.
   - Open threads + next-prep teaser via
     `PlotHookAgent.generate_session_prep(universe_id, story_id)`
     (`plot_hooks.py:327-395`).
   - Response `WrapUpDigest` (new pydantic model in `chat_schemas.py`):
     `{recap, accepted: int, rejected: int, pending: int, canon_items: list,
     open_threads: list[str], next_prep: SessionPrep}`.
   - Persist `{recap, wrapped_up_at}` onto the session doc via
     `_db_save_session` — this is the P1.4 artifact hook; do both together.
2. **Frontend.** New `components/gm/WrapUpModal.tsx` (modeled on
   `components/play/RecapModal.tsx`): sections Recap / Canon changes
   (accepted vs rejected counts + item list) / Open threads / Next session
   teaser. `SessionRecorder.tsx` toolbar (:190-209): "Close session" becomes
   "Wrap up session" calling `chatApi.wrapUp(activeId)` (180s timeout, like
   `endScene` in `api.ts:230-231`), then opens `WrapUpModal`. Keep
   `chatApi.endScene` for play sessions untouched.

**Tests.**
- `packages/ui/backend/tests/test_wrap_up.py` (pattern
  `test_build_gm_opening_resume.py`): 404/409 cases; happy path with
  RecapAgent/PlotHookAgent/data-readers mocked asserts digest shape, that
  `run_end_scene` is invoked when phase isn't `scene_ended`, and that the
  session doc gains `recap_text`/`wrapped_up_at`.
- Frontend `WrapUpModal.test.tsx` (pattern `RecapModal.test.tsx`): section
  rendering, loading/error states.

**Risks:** wrap-up latency (recap + prep = several LLM calls) — surface a
progress state in the modal; do not parallelize across agents in v1 (keep it
simple, agents are independent so this is a later one-line optimization).
**Effort:** M. **Depends on:** nothing hard; lands best after P1.1/P1.2 so the
digest reflects alerts/candidate facts in the transcript. **Status: SHIPPED
2026-07-23** — `POST /chat/{session_id}/wrap-up` in `chat.py:615` (409 unless
`mode == "gm_assistant"`; runs `run_end_scene` if `phase != "scene_ended"` so
wrap-up includes canonization; recap + canon decisions + open threads +
next-prep teaser). `WrapUpDigest` schema in `chat_schemas.py:208`. Persists
`recap_text`/`wrapped_up_at` on the session doc. Frontend: `WrapUpModal.tsx`
mounted in `SessionRecorder.tsx:442`, "Wrap up session" toolbar action. Tests:
`test_wrap_up.py` (404/409/happy path) + `WrapUpModal.test.tsx` (sections +
loading/error states) green.

### P1.4 · Persisted recap artifacts + session archive (M)

**Goal:** recaps stop being ephemeral (`chat.py:533-541` regenerates on every
call); a closed recording answers "what happened in session 12?" without
re-running the LLM.

**Design.**

1. **Schema.** `routers/chat_schemas.py` `Session` (:90-128): add
   `recap_text: str | None = None` and `wrapped_up_at: str | None = None`
   (additive, optional — no migration; old docs read as None). Populate in the
   list serializer (:209-235) from the session doc.
2. **Persist on wrap-up** — done in P1.3 step 1 (same `_db_save_session`
   write; implement together, one PR).
3. **Read path.** `get_session_recap` (`chat.py:499-545`): if
   `session.get("recap_text")`, return it immediately with
   `{"recap": ..., "persisted": True}`; else generate as today (play sessions
   keep live recap).
4. **Frontend.** `RecapModal` shows a "saved" badge when `persisted` (extend
   its query type in `api.ts:233-235`). `SessionRecorder` recordings dropdown
   (:163-175): append a `· wrapped up` marker when `wrapped_up_at` is set —
   first piece of archive differentiation (P3.3 completes it).

**Tests.**
- Backend: wrap-up → GET recap returns persisted text without calling
  RecapAgent (assert mock not called); fresh session still generates.
- Schema: `Session` round-trip with the two new fields in
  `test_session_api.py`.
- Frontend: dropdown marker renders for wrapped-up recordings.

**Effort:** M (S if shipped as part of P1.3's PR — recommended).
**Depends on:** P1.3 (shares the persist write). **Status: SHIPPED
2026-07-23** — `Session` schema gains `recap_text`/`wrapped_up_at` (additive,
no migration). `get_session_recap` returns persisted text when present
(`{"recap": ..., "persisted": True}`); fresh sessions still generate as today.
Frontend: `RecapModal` shows "Saved" badge when `persisted`; `SessionRecorder`
recordings dropdown appends `· wrapped up` marker when `wrapped_up_at` is
set. Tests: backend `test_wrap_up.py` (asserts no RecapAgent call after
wrap-up) + frontend `WrapUpModal.test.tsx` (dropdown marker) green.

---

## 5. Phase 2 — Surface consistency

### P2.1 · Server-authoritative dice for the `/gm` roller (S)

**Goal:** the roller obeys the shipped doctrine ("Server-authoritative rolls…
not client-cheatable", `PLAY_AND_FORGE_DIRECTION.md:127-130`) instead of
`Math.random` (`page.tsx:46-48`).

**Design.**

1. **Backend.** `POST /gm/roll` in `gm_tools.py`: request
   `{expression: str (1..100)}`; calls `roll_dice(expression)` from
   `monitor_data.utils.dice` (:63) — a pure Layer-1 utility; routers may
   import data-layer directly (precedent: `canon_review.py:21-33`). Response:
   `DiceResult.to_dict()` (`{total, rolls, expression, kept_rolls}`) +
   `modifier` parsed for display. Invalid expression (`ValueError` from
   `roll_dice`) → 422. No DB, no agent, no LLM.
2. **Frontend.** `page.tsx`: delete `rollDie` (:46-48) and the client roll
   computation in `parseDiceExpression` (:50-61) — keep the regex as
   client-side input validation only (disable the button, no rolling).
   `DiceRoller.doRoll` (:78-88) becomes a `useMutation` on
   `gmApi.rollDice(expression)`; history entries built from the server
   response (crit/fumble styling at :137-138 recomputed from returned `rolls`
   — presentation only, explicitly non-authoritative).

**Tests.**
- `packages/ui/backend/tests/test_gm_roll.py` (pattern
  `test_dice_server_roll.py`): `1d20+3` → rolls within range, total ==
  sum + 3; `2d20kh1` keep-high honored; garbage → 422; 100+ dice expression →
  422/400 per `dice.py` limits.
- Frontend `page.test.tsx` (new, or extend an existing gm-page test if one
  appears): mutation called with the expression; history renders server
  values; `Math.random` no longer imported (grep assertion in CI is
  overkill — code review suffices).

**Effort:** S. **Depends on:** none. **Status: SHIPPED 2026-07-23** — `POST
/api/gm/roll` in `gm_tools.py` (with `_MAX_DICE=100`/`_MAX_SIDES=1000` router
guards, since `dice.py` has no caps), `gmApi.rollDice`, `DiceRoller` fully
server-driven (no `Math.random` left in `page.tsx`). Tests: 7 backend
(`test_gm_roll.py`) + 3 frontend (`page.test.tsx`) green; layer-check clean.

### P2.2 · Universe-aware rules panel (S)

**Goal:** the rules panel follows the selected universe's bound system instead
of a manual dropdown (`page.tsx:1047-1055`). The binding already exists:
`Universe.default_game_system_id` (`schemas/universe.py:167`), already
resolved server-side for chat (`chat_game_system.py:53-54`) and set by pack
application (`pack_library.py:120`).

**Design.**

1. **Plumb the field to the frontend.** Verify the universe GET/list responses
   include `default_game_system_id` (schema has it at `universe.py:197,217`;
   if the router serializer drops it, add it — one line). Extend the
   `Universe` interface in `packages/ui/frontend/src/lib/types.ts:739-751`.
2. **Frontend.** In `GMAssistantPageContent` (`page.tsx:1080-1115`): when
   `universeId` changes, set `systemId` from the selected universe's
   `default_game_system_id` **unless the GM manually overrode it** (track
   `systemOverridden` state; the dropdown in `GMSelector` stays as an
   override). `RulesPanel` (:181-304) unchanged — it already renders whatever
   `systemId` it gets.

**Tests.**
- Backend: universe response carries the field (extend
  `packages/ui/backend/tests/test_universes.py`).
- Frontend: selecting a universe with a bound system populates the rules
  panel; manual selection wins over re-select.

**Effort:** S. **Depends on:** none. **Status: SHIPPED 2026-07-23** — router
serializer `_u_to_dict` now carries `default_game_system_id`; page fetches the
selected universe (`["universe", id]` query) and follows its bound system via a
`systemOverridden` flag (manual dropdown choice is never clobbered). Tests: 2
backend (`test_universes.py`) + 2 frontend (`page.test.tsx`) green.

### P2.3 · Scratchpad persistence (S–M)

**Goal:** session notes survive browser/machine changes — replace
`localStorage` (`page.tsx:320-340`) with server persistence. Scope is a
per-universe scratch pad (one doc per universe), not a note-taking app.

**Design.**

1. **Data-layer.** New `schemas/gm_notes.py`: `GmNoteUpsert` (`universe_id`,
   `content` ≤ 50_000 chars), `GmNoteResponse` (`universe_id`, `content`,
   `updated_at`) — quintet conventions per `character_sheets.py`. New
   `mongodb_tools/gm_notes.py`: `mongodb_get_gm_note(universe_id)` /
   `mongodb_upsert_gm_note(params)` modeled on `templates.py` (:30-133);
   single-collection `gm_notes`, upsert keyed on `universe_id`. Register in
   `mongodb_tools/__init__.py` + `schemas/__init__.py`. **No
   `middleware/auth.py` entry** — user notes, not canon (same reasoning as
   character templates in GAP §G-6).
2. **Backend.** New small router `routers/gm_notes.py` (data-layer-direct
   pattern of `canon_review.py`, using `db_op`/`validate_uuid` from
   `ingest_shared`): `GET /gm/notes/{universe_id}` (404 → empty note) and
   `PUT /gm/notes/{universe_id}`. Register in the FastAPI app where
   `gm_tools` router is included.
3. **Frontend.** `SessionNotebook` (`page.tsx:310-414`): replace
   `STORAGE_KEY`/load/save (:320-340) with `useQuery` + debounced
   `useMutation` (autosave on blur/2s idle, replacing the Save button; keep
   the "Saved" indicator). Ingest button (:342-356) unchanged here — its
   queue-linkage question is P3.2.

**Tests.**
- Data-layer: tool round-trip with `FakeMCPClient` pattern (get-miss →
  upsert → get-hit; second upsert overwrites, one doc per universe).
- Backend: GET empty → 200 empty; PUT → GET returns content.
- Frontend: notes hydrate from API; autosave fires; localStorage untouched.

**Effort:** S–M. **Depends on:** none.

---

## 6. Phase 3 — Scope calls (decide, then implement or document)

### P3.1 · Audio/hybrid capture — descope (S, recommended) or build (L)

**Status (2026-07-23 audit):** 0% shipped. Grep across `packages/agents/` +
`packages/data-layer/` + `packages/ui/` confirms no `whisper`, no
`transcribe*`, no `microphone`, no `audio_capture`/`audio-upload` (only audio
in the "voice/dialogue" sense, not capture). The spec items at
`CF-1-specification.md:22-26` and `session-support.md:19` still list audio
as in-scope.

**Recommended call: descope now.** Edit `CF-1-specification.md:22-26` and
`session-support.md:19` to mark audio/hybrid as **future work, out of CF-1's
shipped scope**; drop it from `CF-1.yml` acceptance criteria. Rationale: text
capture covers the persona's actual table workflow (GM types between moments);
audio adds a transcription vendor decision, a new ingest path, and
diarization problems that deserve their own plan.

**If build is chosen instead (L):** separate plan; minimum shape is a
transcription step feeding the *existing* text ingest pipeline
(`ingestApi.uploadSource` path, `page.tsx:342-356`) — never a parallel capture
loop.

### P3.2 · Notes→canon review linkage (decide; M if built)

**Status (2026-07-23 audit):** 0% shipped. The data plumbing is fully
present (`ProposedChange.story_id` field is filterable;
`ProposedChangeFilter` accepts both `source` and `story_id`),
`canon_review.py:144-194` and `:202-251` both work, but the scratchpad ingest
path at `page.tsx:342-356` does not thread `story_id` through, and there is
no hint line under the Ingest button. Either option (a) "hint line" or
option (b) "thread story_id" is a small PR.

**Finding:** scratchpad "Ingest" fires the full document pipeline
(`page.tsx:342-356`), whose proposals are tagged `source=ingestion_job:<uuid>`
and surface at `/canon-review/by-ingest` (`canon_review.py:202-251`) and
`/forge/review` — **not** in the recording's story-scoped queue that
`SessionRecorder` embeds (`SessionRecorder.tsx:300-308`,
`canon_review.py:144-194`).

**Options.**
- **(a) Document as-is (S, recommended for now).** The ingest queue is the
  designed surface for document-pipeline proposals; add a hint line under the
  scratchpad Ingest button ("Proposals land in Forge → Review").
- **(b) Link to the recording (M).** Thread an optional `story_id` from the
  scratchpad (the active recording's `story_id`) through
  `ingestApi.uploadSource` → ingest router → pipeline →
  `ProposedChangeCreate(story_id=...)` (field already exists,
  `proposed_changes.py:75`). Ingest proposals then also appear in the
  recording's story-level canon queue. Verify no filter regresses:
  `ProposedChangeFilter` already supports both `source` and `story_id`
  (:180-186). Build only if GM testing shows the split queues confuse.

### P3.3 · Recording archive metadata (S)

**Status (2026-07-23 audit):** 0% shipped but the dep is now ready. P1.4's
`wrapped_up_at` field has shipped (round-tripped in `test_wrap_up.py` and
`test_session_api.py:338-358`). The "archived" half is missing:
`SessionPatch` (`chat_schemas.py:163-172`) has no `archived` field;
`SessionRecorder` dropdown has no `<optgroup>` separation; `SessionList.tsx`
has no mode badge.

**Goal:** recordings are distinguishable in session lists (today only
`SessionRecorder`'s own dropdown filters them, `:58-64`).

**Design.**

1. `chat_schemas.py` `SessionPatch` (:159+): allow `archived: bool`; PATCH
   handler (`chat.py:799-857`) persists it (same shape as the `roll_model`
   patch, :841-849).
2. `SessionRecorder` dropdown (:163-175): group options "Active" vs
   "Archived" (`<optgroup>`), using `wrapped_up_at` (P1.4) + `archived`;
   "Archive" affordance on wrapped-up recordings.
3. `components/play/SessionList.tsx`: small mode badge ("Recording") for
   `mode === "gm_assistant"` sessions so play sessions and recordings are
   visually distinct in the global list.

**Tests:** PATCH 200/422; dropdown grouping + badge rendering (extend
`SessionList.test.tsx`). **Effort:** S. **Depends on:** P1.4 (uses
`wrapped_up_at`).

---

## 7. Dependencies and sequencing

```
Phase 0 (docs) ──────────────────────────────────────────┐
                                                         ▼
P1.1 live alerts ──┐                              (ordering only)
P1.2 entry insights ┼──► P1.3 wrap-up ──► P1.4 recap artifacts ──► P3.3 archive metadata
                   │         ▲
P2.1 dice ─────────┤         │ (digest is richer once capture items exist;
P2.2 rules ────────┤         │  technically independent)
P2.3 scratchpad ───┘         │
P3.1 descope docs ◄──────────┘ (any time; pairs with Phase 0)
P3.2 decision ── any time after P2.3
```

Recommended PR order: **P0 → P2.1 → P2.2 → P1.1 → P1.2 → P1.3+P1.4 (one PR)
→ P2.3 → P3.3 → P3.1/P3.2 decisions.** P2.1/P2.2 are S-sized, independent,
and remove a doctrine violation first; Phase 1 items build on each other in
the UI; P3.3 needs P1.4's field.

Layer-rule check for everything above: UI backend routers call agents
(`gm_tools.py` → `PlotHookAgent`/`CanonKeeper`/`CaptureInsightAgent`) or
data-layer read tools directly (`canon_review.py` precedent); agents call data
via MCP/`run_sync_read`; **no item writes Neo4j** — capture alerts and
candidate facts are advisory, and canonization stays behind the existing
CF-8 verdict flow.

---

## 8. Verification (applies to all phases)

- `uv run pytest packages tests -q` green; new behavior gets tests per item
  (backend: `packages/ui/backend/tests/`; agents: `packages/agents/tests/`
  with `FakeMCPClient`/`FakeLLMClient` from `tests/conftest.py:165,261`;
  frontend: vitest + Testing Library beside the component, per
  `PlayConsole.test.tsx` / `RecapModal.test.tsx`).
- `uv run ruff check packages`;
  `uv run mypy packages/*/src --cache-dir /tmp/mypy-cache`;
  `python scripts/check_layer_dependencies.py`.
- Frontend: `cd packages/ui/frontend && npx vitest run` for touched
  components.
- **Live manual pass** (after Phase 1, `./dev.sh` stack up):
  1. `/gm` → select a universe with canon (e.g. a populated Fallout/VtM
     universe) → New recording.
  2. Log an entry that matches canon → insight chips (participants/locations)
     appear; no alert.
  3. Log an entry contradicting an established fact → amber alert card under
     the entry within a few seconds.
  4. Log 2–3 more entries → "Wrap up session" → digest shows recap, canon
     counts, open threads, next-prep teaser.
  5. Reload the page → recording shows `wrapped up`; Recap opens instantly
     from the persisted artifact (no LLM spinner).
  6. Dice panel: roll `2d6+3` → network tab shows `POST /gm/roll`; history
     shows server values.
  7. Rules panel shows the universe's bound system without touching the
     dropdown; scratchpad notes survive a hard refresh.
- After each phase lands: tick the boxes here and update `docs/STATUS.md`
  (and `session-support.md`'s status table where applicable).
