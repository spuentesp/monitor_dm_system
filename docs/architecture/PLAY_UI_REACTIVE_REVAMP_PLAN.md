# Play UI — Reactive Turn-State Revamp Plan

> **Status:** proposed (rev. 2 — edge-case pass + production hardening)
> **Author:** Play Console UX assessment (frontend revamp follow-up)
> **Scope:** Make the play surface feel alive and legible — an explicit
> turn-state machine that shows *when the player can talk* and *when the GM is
> thinking*, a **queue-one** answer to message accumulation, soft (non-flicker)
> live updates, a decluttered inspector, reading-tuned typography, and the
> production hardening that turns a usable prototype into a shippable UI.
> Keep the existing neon identity; do **not** do a ground-up redesign.

## Context

The play surface today (`packages/ui/frontend/src/components/play/PlayConsole.tsx`,
~1968 lines) drives all roleplay. Its turn lifecycle is encoded as four
independent React booleans — `isTyping`, `streamingMsg`, `sendFailure`,
`pendingDiceRequest` (lines 1143–1149) — with no enforced invariants between
them. Concrete consequences:

- **No input lock, no queue.** `handleSend` (line 1355) only checks for empty
  text. The textarea, Send button and Enter handler stay live while the GM is
  mid-turn, so a player can fire N turns; each resets the watchdog and clobbers
  `lastSentRef`. This is the unhandled "messages accumulate with no response"
  case.
- **Scroll fights the reader.** `scrollIntoView({behavior:"smooth"})` fires on
  every `messages`/`streamingMsg`/`isTyping` change (line 1294) — janky during
  token streaming, and hostile when scrolling up to re-read.
- **Hard updates.** On `done` the handler invalidates + refetches three query
  caches (lines 1193–1195); the whole right rail pops in one step. Optimistic
  echo is a manual `setQueryData` with a random UUID that gets replaced on
  refetch → flicker.
- **Binary "thinking."** Three blinking dots (`TypingIndicator`, line 103). The
  backend computes the *full* reply then fake-streams it word-by-word
  (`packages/ui/backend/src/monitor_ui/routers/chat_ws.py:219-225`,
  `word + " "`), so the real wait is **dead air before `start`** with no signal.
- **Overloaded rail.** The right `aside` (lines 1771–1960) stacks nine
  always-visible cards (Character, Working State, Combat, Story, Canon, Session
  Context, Audit, Social, Benchmark) — information without prioritization.
- **No primitive layer.** Button/Card/Badge/Dropdown are re-implemented inline;
  the tone selector is a `group-hover` div (not keyboard-accessible). Narration
  renders as low-contrast `slate-400` italic over a glowing dot-grid + scan-line
  — fine for a dashboard, tiring for long-form reading.

### Edge cases uncovered during review (E1–E11)

| # | Symptom today | Root cause | Where |
|---|---------------|------------|-------|
| E1 | `done` carries `metadata.dice_request` *and* a `message_id`; current code only inspects `dr` | Client treats `done` as turn-end only; ignores the *id* | `PlayConsole.tsx:1198-1204`, `chat_ws.py:226-233` |
| E2 | Dice-result handler sets `isTyping(true)` (line 1427) and only a fresh WS `done` clears it — but no new turn was sent, so UI sticks on "thinking" | No turn-id correlation between `dice_result` and subsequent `done` | `PlayConsole.tsx:1425-1429` |
| E3 | Phase chip ignores `ooc`, `char_creation`, `completed`, `scene_end` (only `awaiting_character/awaiting_premise/setup/active_play/scene_ended` mapped) | `PHASE_STYLE` incomplete vs. backend phases | `PlayConsole.tsx:191-209`, backend `chat_loops.py:708,749,1123,1340,1441` |
| E4 | Reconnect backoff `1s × 2^retry, cap 30s` (`use-chat-websocket.ts:140-148`) but no surface UI for "we've been retrying 4 minutes"; `setStatus("reconnecting")` is the only signal | Connection status buried in composer, no streak/eta | `use-chat-websocket.ts`, `PlayConsole.tsx:1722` |
| E5 | Two tabs of the same session each open their own WS — both receive `start`/`token`/`done` and append the same message → duplicates | No cross-tab coordination | `chat_ws.py:215-234` (broadcasts to all), `use-chat-websocket.ts` |
| E6 | Page hidden then focused → `done` may have arrived long ago; no `visibilitychange` handling; latent reconciliation gap | (none today) | — |
| E7 | Echo + reconcile: optimistic player bubble uses `crypto.randomUUID()` (line 1320); on `done`-driven refetch the server fetch has a *different* id → bubble appears to duplicate-then-replace | ids not stable across reconcile | `PlayConsole.tsx:1320` |
| E8 | `End scene` (line 1549) calls REST; if WS `done` never arrives the next player turn can race scene-end and corrupt phase | No exclusivity between scene-end and player input | `PlayConsole.tsx:1548-1558, 1375-1390` |
| E9 | `wsSend` is a silent no-op when `readyState !== OPEN` (`use-chat-websocket.ts:194`) — UI thinks the turn was sent; only the 4-minute watchdog eventually fires | `send()` swallows drops | `use-chat-websocket.ts:193-197` |
| E10 | Dice-prompt overlay is mutually exclusive with streaming in JSX (1644-1649) but the machine has no "GM asked me something" concept — only `isTyping` | Missing state | `PlayConsole.tsx:1644` |
| E11 | Connection indicator inside composer (line 1722) collides with the planned `TurnStatusBar` — both render the same data | Layout overlap to resolve in Phase 5 | `PlayConsole.tsx:1722` |

E1–E11 are folded into the phases below, plus a new **Phase 7 — Production
hardening** that owns cross-tab, visibility-pause, reconnect UI, and the
race-condition registry so it stays visible as the codebase grows.

### WebSocket contract (full taxonomy used by the plan)

Server → client (additive; new types are optional and back-compat):
`{type:"phase", phase:"assembling_context|classifying_intent|resolving_dice|narrating|reviewing_canon"}`
`{type:"start", message_id:string}`
`{type:"token", message_id:string, token:string}`
`{type:"done", message_id:string, metadata:{...dice_request?, narrative_pressure?, ...}}`
`{type:"error", detail?:string, message?:string}`
`{type:"pong"}` (heartbeat — already filtered, line 121)

Client → server (additive):
`{type:"message"|"dice_result"|"ping"}`
`{type:"cancel"}` *(new)* — player-initiated stop

### Session phases (server truth)

`awaiting_character`, `char_creation`, `awaiting_premise`, `setup`,
`active_play`, `scene_end`, `scene_ended`, `ooc`, `completed`. Frontend must
treat unknown phases gracefully (Phase 7.7).

**Decisions locked with the user:** accumulation → **queue one** turn;
visual scope → **tune the existing theme**; deliver this plan before any code.

## Architectural rules honored

- Layers: `data-layer (1) → agents (2) → cli/ui (3)`; dependencies flow down only.
  All UI work is layer 3; the only layer-2/backend changes (`phase` events,
  `cancel`) are additive to the existing WS protocol.
- **Only `CanonKeeper` writes Neo4j** — unchanged; this revamp touches no graph
  writes.
- Every change references a use-case ID (`UI-1`..`UI-7`, new for this plan).
- Every change ships tests: Vitest unit tests for the state machine + lib
  helpers, Playwright e2e for the turn lifecycle; backend phase/cancel events
  get a contract test. Integration/e2e gated by existing `RUN_E2E=1`.
- `structlog`, never `print()`, on the backend phase/cancel change.

## Path conventions

- Frontend code under `packages/ui/frontend/src`. New play components live in
  `src/components/play/`; shared primitives in a new `src/components/ui/`.
- Chat WS handled by `src/hooks/use-chat-websocket.ts`; the new turn machine is
  a sibling hook `src/hooks/use-turn-machine.ts`.
- Backend chat WS at `packages/ui/backend/src/monitor_ui/routers/chat_ws.py`
  (and `chat.py` for the REST/streaming twin).

## Tooling adopted (slots into Next 15 / React 19 / Tailwind 3 / framer / lucide)

| Tool | Use | Notes |
|------|-----|-------|
| `xstate` v5 + `@xstate/react` | Turn lifecycle state machine | single source of truth for talk/think/queue/error |
| `react-virtuoso` | Message transcript | auto stick-to-bottom + "N new below" + virtualization in one |
| `sonner` | Soft toasts | "scene saved / canon updated / reconnected" — replaces inline banners |
| `@formkit/auto-animate` | List motion | cheap enter/exit for rail + session list |
| `cmdk` | ⌘K command palette | (Phase 6, optional) cross-app navigation/actions |

Existing `@radix-ui`-style primitives are introduced via lightweight local
components (shadcn-pattern) rather than a full shadcn install, to avoid churn:
`Button`, `Card`, `Badge`, `Tabs`, `Popover`, `Tooltip`, `Dialog`,
`Toast` (sonner).

---

## Phase 1 — Turn-state machine + composer lock/queue + Stop (`UI-1`)

**Goal:** One machine owns who can talk, whether the composer is locked, what
the indicator shows, and how a single queued turn drains. Replaces the four
booleans (and addresses E2, E8, E9, E10).

States: `idle → submitting → thinking → streaming → yourTurn`, plus
`awaitingChoice` (dice/consequence — E10), `error`. Context holds: `queuedTurn`
(at most one), `lastSent`, `currentPhase`, `elapsedMs`, `streamMessageId`.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 1.1 | `useTurnMachine` (XState) modeling the states + a single queued turn; exposes `canTalk`, `isBusy`, `indicator`, `submit`, `enqueue`, `cancelQueued`, `stop` | 3 (fe) | `src/hooks/use-turn-machine.ts` |
| 1.2 | Wire `handleWsMessage` (`phase`/`start`/`token`/`done`/`error`) into machine transitions; **correlate on `message_id`** so a stale `done` for a prior stream cannot clobber the current one (E1, E2) | 3 (fe) | `PlayConsole.tsx` |
| 1.3 | Composer: while `isBusy`, keep textarea live but route Enter → `enqueue` (max 1); render an editable/cancelable "Queued" chip above the input | 3 (fe) | `src/components/play/Composer.tsx` (extracted) |
| 1.4 | Send button becomes **Stop** while busy → `stop()` → WS `{type:"cancel"}`; on `done`, auto-drain `queuedTurn`. **E9**: `wsSend` returns a boolean; if false, surface an inline error and don't set `submitting` | 3 (fe) | `Composer.tsx`, `use-chat-websocket.ts` |
| 1.5 | Positive "Your move" affordance in `yourTurn` (composer border + label) | 3 (fe) | `Composer.tsx` |
| 1.6 | Unit tests: machine transitions incl. queue-one, stop, error→retry, session-switch reset, stale-`done` ignored (E2) | test | `src/hooks/use-turn-machine.test.ts` |
| 1.7 | E2E: typing while busy shows the queued chip; Stop interrupts; `wsStatus !== connected` shows inline error (E9) | test | `e2e/play-turn.spec.ts` |

**Done when:** sending while the GM is thinking queues exactly one turn
(visible, cancelable, auto-sent on completion); Stop interrupts without
waiting on the 4-minute watchdog; the composer clearly signals when it is the
player's move; a stale `done` cannot strangle the active stream.

## Phase 2 — Rich "GM is thinking" via phase events (`UI-2`)

**Goal:** Turn dead-air-before-`start` into an honest sense of a mind at work.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 2.1 | Emit additive `{"type":"phase","phase":...}` events from the loop before `start`; never block the turn if emission fails | 2/3 (be) | `chat_ws.py`, `chat.py`, agent loop hook |
| 2.2 | Machine consumes `phase`; map to copy ("Recalling the world…", "Reading your move…", "Rolling…", "Writing…", "Updating canon…"); unknown phases map to a generic "Thinking…" (E3) | 3 (fe) | `use-turn-machine.ts`, `ThinkingIndicator.tsx` |
| 2.3 | `ThinkingIndicator` shows current phase + elapsed-time hint after ~8s ("still composing…"); reuses `PhaseChip` vocabulary | 3 (fe) | `src/components/play/ThinkingIndicator.tsx` |
| 2.4 | Backend contract test: phase events precede `start`, turn still completes if a phase emit is skipped | test | `packages/ui/backend/tests/test_chat_ws_phases.py` |

**Done when:** the indicator names what the GM is doing through at least 3
honest stages; a turn with no phase events still streams normally (back-compat).

## Phase 3 — Virtualized transcript with smart auto-scroll (`UI-3`)

**Goal:** Stop scroll-fighting; stay pinned to bottom only when already at
bottom; handle long sessions.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 3.1 | Replace the `space-y-4` map (lines 1590–1655) with `react-virtuoso` `followOutput="smooth"` (auto-stick only when at bottom) | 3 (fe) | `src/components/play/Transcript.tsx` (extracted) |
| 3.2 | "↓ N new" pill when scrolled up during streaming; click → jump to bottom | 3 (fe) | `Transcript.tsx` |
| 3.3 | Remove the `scrollIntoView`-on-every-change effect (line 1294) | 3 (fe) | `PlayConsole.tsx` |
| 3.4 | E2E: scroll up mid-stream stays put; pill appears; new turn while at bottom auto-follows | test | `e2e/play-transcript.spec.ts` |

**Done when:** reading history during a stream is not interrupted, and the
bottom auto-follows only when the player is already there.

## Phase 4 — Soft live updates (`UI-4`)

**Goal:** Replace invalidate-and-refetch pops with append + targeted reconcile.
Addresses E7.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 4.1 | Treat the transcript as append-only local state fed by WS; reconcile with server only on reconnect/session-switch (drop the 3× invalidate on `done`, lines 1193–1195) | 3 (fe) | `PlayConsole.tsx` |
| 4.2 | **Stable echo ids (E7):** optimistic player echo uses a *client-generated stable id* persisted until the server fetch returns; on reconcile, replace by `(client_id, server_id)` mapping so the same bubble doesn't double-render | 3 (fe) | `PlayConsole.tsx`, `src/lib/query-keys.ts` |
| 4.3 | `sonner` toasts for out-of-band events (canon updated, scene saved, reconnected) replacing inline banners | 3 (fe) | `src/app/layout.tsx`, `PlayConsole.tsx` |
| 4.4 | `@formkit/auto-animate` on rail cards + session list | 3 (fe) | rail components, `SessionList` |
| 4.5 | Unit test: echo→reconcile produces no duplicate/flicker (stable ids, E7) | test | `src/components/play/transcript-reconcile.test.ts` |

**Done when:** a completed turn updates the transcript and rail without a
full-list refetch flash; player echoes never double-render.

## Phase 5 — Tabbed inspector + persistent turn-status bar (`UI-5`)

**Goal:** Declutter the nine-card rail; surface connection/turn/phase calmly.
Addresses E11.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 5.1 | `Tabs` inspector (`Scene · Character · Mechanics · Canon`) wrapping existing cards; auto-focus Mechanics on roll resolve, Canon on pending review; for `ooc`/`scene_end`/`completed` phases, the Scene tab is the default | 3 (fe) | `src/components/play/Inspector.tsx` |
| 5.2 | Persistent `TurnStatusBar` atop the chat column: connection (always present, calm), whose turn, current phase, elapsed/token count — replaces the buried connection chip (line 1722) and the duplicated one in `ConnectionStatus` | 3 (fe) | `src/components/play/TurnStatusBar.tsx` |
| 5.3 | Move "End scene" into a scene/beat header; **disable player input while `endingScene`** (E8) | 3 (fe) | `PlayConsole.tsx` |
| 5.4 | Skeletons replace "Loading…" text on home + session list + rail | 3 (fe) | `src/components/ui/Skeleton.tsx`, `src/app/page.tsx`, `SessionList` |

**Done when:** the rail shows one relevant tab at a time; connection/turn
state is readable at a glance without opening the composer area; no two
components render the same connection indicator.

## Phase 6 — Primitive layer, reading typography, ⌘K (`UI-6`)

**Goal:** Consistency + legibility polish; split the monolith.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 6.1 | Extract `Button`/`Card`/`Badge`/`Popover`/`Tooltip`/`Dialog` primitives; replace inline re-impls (incl. keyboard-accessible tone selector) | 3 (fe) | `src/components/ui/*` |
| 6.2 | Reading mode for transcript: contrast `slate-300` narration, ~68ch measure, no dot-grid/scan-line behind the message column, optional serif toggle | 3 (fe) | `globals.css`, `ProseBubble`, `Transcript.tsx` |
| 6.3 | Add spacing/typography design tokens (today only colors exist) | 3 (fe) | `tailwind.config.ts`, `globals.css` |
| 6.4 | `cmdk` ⌘K palette: switch session, ask Oracle, roll, change tone, jump to world/entity | 3 (fe) | `src/components/CommandPalette.tsx`, `layout.tsx` |
| 6.5 | Split `PlayConsole.tsx` into `Composer / Transcript / TurnStatusBar / Inspector` shells (enabled by 6.1) | 3 (fe) | `src/components/play/*` |

**Done when:** play UI uses shared primitives, prose is comfortably readable,
and ⌘K provides cross-app navigation.

## Phase 7 — Production hardening (`UI-7`)

**Goal:** Take the working revamp from "feels good in dev" to "shippable."
Closes E3, E4, E5, E6 plus the general race-condition surface that the machine
naming makes easier to spot. New code only — no behavior regression for
existing happy paths.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 7.1 | **Cross-tab coordination (E5):** a `BroadcastChannel` per `sessionId` elects a *primary* tab (smallest tab-id); non-primary tabs close their WS and show a calm "Open in primary tab" badge. Primary sends `{kind:"echo", clientId}` so other tabs append bubbles via local event without holding a WS. Falls back gracefully if `BroadcastChannel` unavailable (Safari < 15.4) | 3 (fe) | `src/hooks/use-session-leader.ts` |
| 7.2 | **Visibility-pause (E6):** `visibilitychange` → on hide, *do not* disconnect (server keeps streaming); on show, fetch messages since `lastSeenSeq` and reconcile with any locally-buffered `streamingMsg`. If `document.visibilityState === "visible"` after >30s hidden, run a one-shot reconcile | 3 (fe) | `PlayConsole.tsx`, `use-chat-websocket.ts` |
| 7.3 | **Reconnect UI (E4):** surface attempt count + ETA in `TurnStatusBar`; cap attempts at N (e.g. 10) and after that, surface a `sonner` toast with manual `Retry`. `wsRef.current?.readyState` is polled to surface a new "dropped" pseudo-status so E9's silent no-op becomes a visible failure | 3 (fe) | `use-chat-websocket.ts`, `TurnStatusBar.tsx` |
| 7.4 | **Phase coverage (E3):** extend `PHASE_STYLE` to `awaiting_character`, `char_creation`, `awaiting_premise`, `setup`, `active_play`, `scene_end`, `scene_ended`, `ooc`, `completed`; unknown phases fall through to the dim default. The Inspector (Phase 5) auto-selects a tab per phase | 3 (fe) | `src/components/play/PhaseChip.tsx` (extracted) |
| 7.5 | **Cancel protocol (E9):** send `{type:"cancel"}`; backend acknowledges with `{type:"cancelled", message_id}`; frontend clears `streamingMsg` and goes to `yourTurn`. Backend contract test | 2/3 | `chat_ws.py`, `use-turn-machine.test.ts`, `tests/test_chat_ws_cancel.py` |
| 7.6 | **Scene-end exclusivity (E8):** while `endingScene`, `composer` is fully locked (`disabled` + aria-busy) and the `Queued` chip (if any) waits for `done` from scene-end before draining | 3 (fe) | `Composer.tsx`, `PlayConsole.tsx` |
| 7.7 | **Unknown-event safety:** any unknown WS event type is logged once via `console.warn` (dev) / `Sentry` (prod) and ignored — never throws, never tears down the socket | 3 (fe) | `use-turn-machine.ts` |
| 7.8 | **Race-condition registry:** `docs/architecture/PLAY_UI_RACE_REGISTRY.md` — every race found (now or later) gets a 1-page entry: trigger, current handling, machine transition responsible, test that catches it. Reviewers add to this doc instead of commenting in code | doc | new file |
| 7.9 | **Performance budgets:** instrument `Transcript.tsx` + `Inspector.tsx` with `web-vitals` (`LCP`, `INP`, `CLS`) and assert budgets in CI (LCP < 2.5s, INP < 200ms at p75) | 3 (fe) + ci | `e2e/play-perf.spec.ts`, `playwright.config.ts` |

**Done when:** all E1–E11 are closed; cross-tab dedupes; reconnect surfaces a
streak + manual retry; unknown WS phases/types don't crash; cancel works;
race-condition registry is in place; perf budgets are asserted in CI.

---

## Race-condition registry (initial entries; lives in `PLAY_UI_RACE_REGISTRY.md`)

| ID | Race | Current handling | Test |
|----|------|------------------|------|
| R1 | `done` arrives after a session switch | Phase 1: machine ignores `done` whose `message_id` ≠ `streamMessageId`; Phase 7.2 reconciles on focus | `use-turn-machine.test.ts` |
| R2 | Player sends during `endingScene` | Phase 7.6: composer locked + queued chip held until scene-end `done` | `e2e/play-turn.spec.ts` |
| R3 | Two tabs both append `done`'s GM bubble | Phase 7.1: `BroadcastChannel` leader election; non-leader does not append | `e2e/play-multitab.spec.ts` |
| R4 | Dice prompt arrives while streaming | Phase 1: `awaitingChoice` is reached *after* `done`; streaming message drains first, then prompt | `use-turn-machine.test.ts` |
| R5 | Optimistic echo id differs from server id | Phase 4.2: stable `client_id` → `server_id` mapping during reconcile | `transcript-reconcile.test.ts` |
| R6 | `wsSend` called while `readyState !== OPEN` | Phase 1.4 / 7.3: `wsSend` returns false; UI shows inline error | `e2e/play-turn.spec.ts` |
| R7 | Token `message_id` mismatch | Phase 1.2: tokens whose `message_id` ≠ `streamMessageId` are buffered for the next stream (rare, but logged) | `use-turn-machine.test.ts` |

---

## Test strategy ("real usage")

The codebase today has 5 frontend unit tests (`combatPanel`, `workingState`,
`historyMapping`, `entitiesApi`, `characterChatApi`), 2 e2e specs
(`pages`, `play-flow`), and 1 backend test (`test_chat_router_ooc.py`). The
revamp must add tests at scale matching that bar.

- **Vitest unit (new):**
  - `use-turn-machine.test.ts` — all transitions incl. queue-one, stop, error
    retry, session reset, stale-`done` ignored, dice-result turn correlation.
  - `transcript-reconcile.test.ts` — stable ids, no duplicate/flicker.
  - `phase-mapping.test.ts` — every server phase + every sub-phase copy.
  - `session-leader.test.ts` — BroadcastChannel election (mocked).
- **Playwright e2e (new, `RUN_E2E=1`):**
  - `play-turn.spec.ts` — submit while busy → queued chip → auto-send; Stop
    interrupts; disconnect → inline error; queued turn survives session switch.
  - `play-transcript.spec.ts` — scroll up mid-stream stays put; "N new" pill.
  - `play-multitab.spec.ts` — two tabs dedupe; only leader appends.
  - `play-perf.spec.ts` — LCP/INP/CLS budgets on `/play` with a seeded 200-message
    session.
- **Backend contract (new):**
  - `test_chat_ws_phases.py` — phase events precede `start`; turn completes if
    phases are skipped.
  - `test_chat_ws_cancel.py` — `{type:"cancel"}` ⇒ `{type:"cancelled",
    message_id}`; further `done` for that id ignored.
- **Manual smoke (recorded in CI artifact):** long session (200+ messages)
  stays smooth; flaky connection shows calm status; ⌘K opens; tab-leader badge
  swaps on tab focus.

## Rollout order

1. **Phase 1** (turn machine + queue-one + Stop + wsSend-failure surface) —
   biggest UX win, frontend-only.
2. **Phase 2** (phase events) — small backend + indicator; unlocks the
   "thinking" story.
3. **Phase 3** (virtualized transcript) — fixes scroll + perf.
4. **Phase 4** (soft updates + stable echo ids) — removes flicker/pops.
5. **Phase 5** (tabbed inspector + status bar) — declutter, use the surface.
6. **Phase 6** (primitives + reading mode + ⌘K) — consistency + polish.
7. **Phase 7** (production hardening + race registry) — must ship before
   public release; Phase 7.4 (phase coverage) and 7.7 (unknown-event safety)
   are cheap and should land alongside Phase 2.

Each phase ships independently and leaves the app working; Phases 1–4 are the
core of "reactive, updates softly, clear turn states." Phases 5–6 are surface
and consistency. Phase 7 is what makes it production-grade.
