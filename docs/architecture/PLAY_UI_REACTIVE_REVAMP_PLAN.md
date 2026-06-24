# Play UI — Reactive Turn-State Revamp Plan

> **Status:** proposed
> **Author:** Play Console UX assessment (frontend revamp follow-up)
> **Scope:** Make the play surface feel alive and legible — an explicit
> turn-state machine that shows *when the player can talk* and *when the GM is
> thinking*, a **queue-one** answer to message accumulation, soft (non-flicker)
> live updates, a decluttered inspector, and reading-tuned typography. Keep the
> existing neon identity; do **not** do a ground-up redesign.

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
  (`packages/ui/backend/src/monitor_ui/routers/chat_ws.py:222`,
  `word + " "`), so the real wait is **dead air before `start`** with no signal.
- **Overloaded rail.** The right `aside` (lines 1771–1960) stacks nine
  always-visible cards (Character, Working State, Combat, Story, Canon, Session
  Context, Audit, Social, Benchmark) — information without prioritization.
- **No primitive layer.** Button/Card/Badge/Dropdown are re-implemented inline;
  the tone selector is a `group-hover` div (not keyboard-accessible). Narration
  renders as low-contrast `slate-400` italic over a glowing dot-grid + scan-line
  — fine for a dashboard, tiring for long-form reading.

WebSocket contract today (`chat_ws.py`, `chat.py`): server → client emits
`start` / `token` / `done` (`end`) / `error`; client → server sends
`{type:"message"|"dice_result"|"ping"}`. There are **no** per-turn phase events
and **no** cancel path.

**Decisions locked with the user:** accumulation → **queue one** turn;
visual scope → **tune the existing theme** (keep neon chrome, fix legibility);
deliver this plan before any code.

## Architectural rules honored

- Layers: `data-layer (1) → agents (2) → cli/ui (3)`; dependencies flow down only.
  All UI work is layer 3; the only layer-2/backend change (phase events, cancel)
  is additive to the existing WS protocol.
- **Only `CanonKeeper` writes Neo4j** — unchanged; this revamp touches no graph
  writes.
- Every change references a use-case ID (`UI-1`..`UI-6`, new for this plan).
- Every change ships tests: Vitest unit tests for the state machine + lib
  helpers, Playwright e2e for the turn lifecycle; backend phase events get a
  contract test. Integration/e2e gated by existing `RUN_E2E=1`.
- `structlog`, never `print()`, on the backend phase-event change.

## Path conventions

- Frontend code under `packages/ui/frontend/src`. New play components live in
  `src/components/play/`; shared primitives in a new `src/components/ui/`.
- Chat WS handled by `src/hooks/use-chat-websocket.ts`; the new turn machine is a
  sibling hook `src/hooks/use-turn-machine.ts`.
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
`Button`, `Card`, `Badge`, `Tabs`, `Popover`, `Tooltip`, `Dialog`.

---

## Phase 1 — Turn-state machine + composer lock/queue + Stop (`UI-1`)

**Goal:** One machine owns who can talk, whether the composer is locked, what the
indicator shows, and how a single queued turn drains. Replaces the four booleans.

States: `idle → submitting → thinking → streaming → yourTurn`, plus
`awaitingChoice` (dice/consequence), `error`. Context holds: `queuedTurn`
(at most one), `lastSent`, `currentPhase`, `elapsedMs`.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 1.1 | `useTurnMachine` (XState) modeling the states + a single queued turn; exposes `canTalk`, `isBusy`, `indicator`, `submit`, `enqueue`, `cancelQueued`, `stop` | 3 (fe) | `src/hooks/use-turn-machine.ts` |
| 1.2 | Wire `handleWsMessage` (`start`/`token`/`done`/`error`) into machine transitions; retire `isTyping`/`streamingMsg`/`sendFailure` flags | 3 (fe) | `PlayConsole.tsx` |
| 1.3 | Composer: while `isBusy`, keep textarea live but route Enter → `enqueue` (max 1); render an editable/cancelable "Queued" chip above the input | 3 (fe) | `src/components/play/Composer.tsx` (extracted) |
| 1.4 | Send button becomes **Stop** while busy → `stop()` → WS `{type:"cancel"}`; on `done`, auto-drain `queuedTurn` | 3 (fe) | `Composer.tsx`, `PlayConsole.tsx` |
| 1.5 | Positive "Your move" affordance in `yourTurn` (composer border + label) | 3 (fe) | `Composer.tsx` |
| 1.6 | Unit tests: machine transitions incl. queue-one, stop, error→retry, session-switch reset | test | `src/hooks/use-turn-machine.test.ts` |

**Done when:** sending while the GM is thinking queues exactly one turn (visible,
cancelable, auto-sent on completion); Stop interrupts without waiting on the
4-minute watchdog; the composer clearly signals when it is the player's move.

## Phase 2 — Rich "GM is thinking" via phase events (`UI-2`)

**Goal:** Turn dead-air-before-`start` into an honest sense of a mind at work.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 2.1 | Emit additive `{"type":"phase","phase":...}` events from the loop before `start` (`assembling_context`/`classifying_intent`/`resolving_dice`/`narrating`/`reviewing_canon`); never block the turn if emission fails | 2/3 (be) | `chat_ws.py`, `chat.py`, agent loop hook |
| 2.2 | Machine consumes `phase`; map to copy ("Recalling the world…", "Reading your move…", "Rolling…", "Writing…", "Updating canon…") | 3 (fe) | `use-turn-machine.ts` |
| 2.3 | `ThinkingIndicator` shows current phase + elapsed-time hint after ~8s ("still composing…"); reuses `PhaseChip` vocabulary | 3 (fe) | `src/components/play/ThinkingIndicator.tsx` |
| 2.4 | Backend contract test: phase events precede `start`, turn still completes if a phase emit is skipped | test | `packages/ui/backend/tests/test_chat_ws_phases.py` |

**Done when:** the indicator names what the GM is doing through at least 3 honest
stages; a turn with no phase events still streams normally (back-compat).

## Phase 3 — Virtualized transcript with smart auto-scroll (`UI-3`)

**Goal:** Stop scroll-fighting; stay pinned to bottom only when already at bottom;
handle long sessions.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 3.1 | Replace the `space-y-4` map (lines 1590–1655) with `react-virtuoso` `followOutput="smooth"` (auto-stick only when at bottom) | 3 (fe) | `src/components/play/Transcript.tsx` (extracted) |
| 3.2 | "↓ N new" pill when scrolled up during streaming; click → jump to bottom | 3 (fe) | `Transcript.tsx` |
| 3.3 | Remove the `scrollIntoView`-on-every-change effect (line 1294) | 3 (fe) | `PlayConsole.tsx` |
| 3.4 | E2e: scroll up mid-stream stays put; pill appears; new turn while at bottom auto-follows | test | `e2e/play-transcript.spec.ts` |

**Done when:** reading history during a stream is not interrupted, and the bottom
auto-follows only when the player is already there.

## Phase 4 — Soft live updates (`UI-4`)

**Goal:** Replace invalidate-and-refetch pops with append + targeted reconcile.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 4.1 | Treat the transcript as append-only local state fed by WS; reconcile with server only on reconnect/session-switch (drop the 3× invalidate on `done`, lines 1193–1195) | 3 (fe) | `PlayConsole.tsx` |
| 4.2 | Optimistic player echo via `useMutation` w/ stable id + onError rollback (replace manual `setQueryData` + random UUID) | 3 (fe) | `PlayConsole.tsx`, `src/lib/query-keys.ts` |
| 4.3 | `sonner` toasts for out-of-band events (canon updated, scene saved, reconnected) replacing inline banners | 3 (fe) | `src/app/layout.tsx`, `PlayConsole.tsx` |
| 4.4 | `@formkit/auto-animate` on rail cards + session list | 3 (fe) | rail components, `SessionList` |
| 4.5 | Unit test: echo→reconcile produces no duplicate/flicker (stable ids) | test | `src/components/play/transcript-reconcile.test.ts` |

**Done when:** a completed turn updates the transcript and rail without a
full-list refetch flash; player echoes never double-render.

## Phase 5 — Tabbed inspector + persistent turn-status bar (`UI-5`)

**Goal:** Declutter the nine-card rail; surface connection/turn/phase calmly.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 5.1 | `Tabs` inspector (`Scene · Character · Mechanics · Canon`) wrapping existing cards; auto-focus Mechanics on roll resolve, Canon on pending review | 3 (fe) | `src/components/play/Inspector.tsx` |
| 5.2 | Persistent `TurnStatusBar` atop the chat column: connection (always present, calm), whose turn, current phase, elapsed/token count — replaces the buried connection chip (line 1722) | 3 (fe) | `src/components/play/TurnStatusBar.tsx` |
| 5.3 | Move "End scene" into a scene/beat header; keep behavior | 3 (fe) | `PlayConsole.tsx` |
| 5.4 | Skeletons replace "Loading…" text on home + session list + rail | 3 (fe) | `src/components/ui/Skeleton.tsx`, `src/app/page.tsx`, `SessionList` |

**Done when:** the rail shows one relevant tab at a time; connection/turn state
is readable at a glance without opening the composer area.

## Phase 6 — Primitive layer, reading typography, ⌘K (`UI-6`)

**Goal:** Consistency + legibility polish; split the monolith.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 6.1 | Extract `Button`/`Card`/`Badge`/`Popover`/`Tooltip`/`Dialog` primitives; replace inline re-impls (incl. keyboard-accessible tone selector) | 3 (fe) | `src/components/ui/*` |
| 6.2 | Reading mode for transcript: contrast `slate-300` narration, ~68ch measure, no dot-grid/scan-line behind the message column, optional serif toggle | 3 (fe) | `globals.css`, `ProseBubble`, `Transcript.tsx` |
| 6.3 | Add spacing/typography design tokens (today only colors exist) | 3 (fe) | `tailwind.config.ts`, `globals.css` |
| 6.4 | `cmdk` ⌘K palette: switch session, ask Oracle, roll, change tone, jump to world/entity | 3 (fe) | `src/components/CommandPalette.tsx`, `layout.tsx` |
| 6.5 | Split `PlayConsole.tsx` into `Composer / Transcript / TurnStatusBar / Inspector` shells (enabled by 6.1) | 3 (fe) | `src/components/play/*` |

**Done when:** play UI uses shared primitives, prose is comfortably readable, and
⌘K provides cross-app navigation.

---

## Test strategy ("real usage")

- **Vitest unit:** turn machine (all transitions, queue-one, stop, error→retry,
  session reset), transcript reconcile (no duplicate echo), phase→copy mapping.
- **Playwright e2e** (`RUN_E2E=1`): send while busy → one queued chip → auto-send
  on done; Stop interrupts; scroll-up-mid-stream stays put + "N new" pill;
  reconnect path shows toast and reconciles.
- **Backend contract:** phase events precede `start`; turn completes if phase
  emission is skipped (back-compat).
- Manual: long session (200+ messages) stays smooth (virtualization); flaky
  connection shows calm status, not silent failure.

## Rollout order

1. **Phase 1** (turn machine + queue-one + Stop) — biggest UX win, frontend-only.
2. **Phase 2** (phase events) — small backend + indicator; unlocks the "thinking" story.
3. **Phase 3** (virtualized transcript) — fixes scroll + perf.
4. **Phase 4** (soft updates) — removes flicker/pops.
5. **Phase 5** (tabbed inspector + status bar) — declutter, use the surface.
6. **Phase 6** (primitives + reading mode + ⌘K) — consistency + polish.

Each phase ships independently and leaves the app working; Phases 1–4 are the
core of "reactive, updates softly, clear turn states." Phases 5–6 are surface and
consistency.
