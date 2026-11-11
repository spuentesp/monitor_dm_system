# G04 — In-fiction world clock & time advancement (proposed CF-11)

> **Status:** proposed 2026-11-11. Gap: the CF-7 briefing schema has
> `world_date` and `urgent_deadlines`, but nothing advances in-fiction time
> between sessions. Deadlines are listed, never triggered; "three days
> pass" is invisible to the system.

## Goal

Give each universe/story a world clock the GM can advance explicitly
("+3 days", "+2 hours", or to an absolute date), have deadlines and
time-sensitive facts react to it, and surface "what changed because time
passed" in the next prep briefing (CF-7) and recap (CF-2).

## Use case

Propose **CF-11 "Advance World Time"** in
`docs/use-cases/epic-7-copilot-CF/CF-11/`; amends CF-7 (briefing gains a
"time passed since last session" section) and CF-2 (recap gains time line).

## Scope

**In:** per-story world clock (date + time, timezone-less fantasy calendar
supported as free-form string + sortable epoch internally); GM advance
action with confirmation; deadline model (`urgent_deadlines`) that flips to
*overdue* and appears in prep + threads (CF-3); scheduled events hooks
(facts/events with `at` timestamps) surfaced when crossed; NPC "off-screen"
activity tick in prep ("what NPCs did while time passed") as an LLM
generation over canon, not a simulation.
**Out (v1):** automatic time passage from real-world elapsed time, complex
calendar math (use ISO 8601 internally, display string per universe), weather
simulation.

## Design

- **Layer 1:** `schemas/world_clock.py` + `mongodb_tools/world_clock.py`
  (`get_clock`, `advance_clock`, `list_due_deadlines`). Deadlines stored on
  story docs; events keep `at` in Neo4j (read via existing list tools) —
  **no Neo4j writes except via CanonKeeper**.
- **Layer 2:** `GmTableAgent` (or new `ClockAgent`) method
  `advance_and_summarize(story_id, delta)` — deterministic deadline
  evaluation + DSPy module for the "off-screen" summary paragraph.
- **Layer 3:** `POST /gm/clock/advance` (+ `GET /gm/clock/{story_id}`) in
  `gm_tools.py`; UI: clock readout + advance control in the "Tonight" prep
  panel (`PrepToTablePanel.tsx`) and recorder wrap-up.

## Phases

1. Schema + tools + tests (`test_world_clock_tools.py`): advance, overdue
   computation, idempotency (advancing is monotonic; store an audit log of
   advances).
2. Agent method + tests (FakeLLMClient): off-screen summary; deterministic
   deadline flip has plain unit tests.
3. Routes + authz; wire into CF-7 briefing and CF-2 recap payloads.
4. UI: clock control in prep panel + wrap-up; vitest.
5. Canon effects of time passing (e.g., "the ritual completes") stage as
   `ProposedChange` for CF-8 — never direct writes.

## Acceptance

- GM advances time mid- or post-session; the next CF-7 briefing shows
  elapsed time, due/overdue deadlines, and an off-screen NPC summary.
- CF-3 threads can carry deadlines and surface as overdue.
- Commits reference CF-11; all new tests green; layer check clean.

## Open decisions

- Calendar model: v1 ISO-8601 internally + display string; fantasy calendars
  are a per-universe display concern (defer).
- Who may advance time: session owner only (tenancy rule, SYS-6).
