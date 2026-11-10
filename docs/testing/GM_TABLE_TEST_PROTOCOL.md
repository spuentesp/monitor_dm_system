# GM Table Test Protocol (Phase 7 Part B, tasks 5–6)

> **Status:** protocol ready 2026-11-10; the test itself needs a **human GM** and has
> not been run. Tasks 5 and 6 of `conductor/roleplayable/phase-7-light-rp-and-gm-assistant.md`
> are deliberately left open until a real session happens. The findings from the
> session become the "top five" that task 6 fixes.
>
> Conventions: the GM Assistant surface is the web `/gm` page
> (`docs/architecture/GM_ASSISTANT_MODE_PLAN.md`). The prep, lookup and session-log
> flows used below are the Phase 7 Part B endpoints in
> `packages/ui/backend/src/monitor_ui/routers/gm_tools.py`.

## What this test is

A human GM runs **one real session of at least two hours** with the GM assistant
open beside them, and MONITOR helps more than it interrupts. The test is not
about whether the game was good — it is about every lookup: did it help, how
long did it take, and every time the GM gave up and did it by hand.

## Before the session (15–30 min)

1. Stack up: `./dev.sh` (see `AGENTS.md`). A universe with real canon and a
   story for the campaign must exist (apply a pack or use an existing world).
2. Open `/gm`, select the universe. Confirm the rules panel shows the bound
   system.
3. **Prep to table** (the flow under test): paste tonight's notes into the
   **Tonight** panel → *Extract for review* → review/fix the extracted NPCs,
   locations and threads → *Save as tonight's prep*. Confirm "Tonight's table"
   lists them.
4. Start a **recording** (Recorder panel) for the session. Keep the scratchpad
   for anything that does not fit a lookup.
5. Have this document open, with the lookup log (below) ready to copy — one row
   per lookup, filled in **during** the session, not after.

## The script — what will be tried

Run these at natural table moments; do not force them. Each item maps to a
lookup the assistant must serve within a few seconds.

| # | Trigger at the table | Try | Passes when |
|---|---|---|---|
| S1 | An NPC appears and the GM has forgotten them | **Lookups → NPC**: look them up by name | The dossier answers *who is this NPC and what do they want* without a second source |
| S2 | The players ask "what do we know about X?" | **Lookups → Party knows**: pick the party members, ask about X | The answer lists only what the party witnessed or is common knowledge, and gets X right |
| S3 | Continuity across sessions matters | **Lookups → Last session** | The previous session's summary (and transcript tail) is on screen in seconds |
| S4 | The GM needs a name *right now* | **Lookups → Name** (with context) | A usable name appears without breaking the table's flow (≤ ~30 s) |
| S5 | The scene stalls | **Lookups → Complication** | A complication the GM can actually use appears (≤ ~30 s) |
| S6 | A rules dispute | **Lookups → Rules**: ask the question | The answer carries its source (rule name) or says plainly the rules do not cover it |
| S7 | Prep is done in advance | Repeat the **Before** step 3 with real notes | The extraction matches what the GM meant after at most one round of edits |
| S8 | The session ends | **Session Log → Canon**: paste/type what happened | Proposals appear in the Canon Review queue; contradictions with canon are flagged (direct + G-9) |
| S9 | After wrap-up | Review the flagged items | The flags point at real problems (record false alarms in the log) |

Also record any time the GM **gave up and did it by hand** (opened the wiki,
asked a player, flipped a book) instead of using the assistant — that is the
most important data in the test.

## After the session (30 min)

1. **Wrap up** the recording (recap + canon counts + open threads) and run S8/S9
   if not done at the table.
2. In the Canon Review queue, accept/reject the staged proposals; note which
   proposals were wrong extraction (count them).
3. Fill the **session verdict** section of the lookup log.
4. Copy the completed log to `docs/testing/gm_table_test_report_<YYYY-MM-DD>.md`
   with a short narrative. Rank every problem by (frequency × how much it hurt
   the table). The **top five** are the input to task 6 (fix them, list the rest).

## Lookup log template

Copy this into the session report. One row per lookup, filled during the
session. `seconds` is wall-clock from asking to useful answer on screen.

```markdown
# GM table test report — <YYYY-MM-DD>

**GM:** <name>   **Campaign/universe:** <name>   **Session length:** <hh:mm>
**Assistant build:** <commit sha>   **System:** <game system name>

## Lookup log

| # | Time | Lookup kind (S1–S9 or ad-hoc) | What the GM asked/needed | Seconds | Helped? (yes / partial / no / gave up) | Notes |
|---|------|-------------------------------|--------------------------|---------|----------------------------------------|-------|
| 1 |      |                               |                          |         |                                        |       |

## Gave up and did it by hand

| # | What the GM needed | Why the assistant was not used | What was used instead |
|---|--------------------|--------------------------------|-----------------------|
|   |                    |                                |                       |

## Session verdict

- Lookups attempted: <n>  · helped: <n> · partial: <n> · failed/gave up: <n>
- Median time to useful answer: <s>
- Prep extraction edits before commit: <n>
- Proposals staged after the session: <n> · accepted: <n> · rejected: <n>
- Contradiction flags: <n> · true positives: <n> · false alarms: <n>
- Did the assistant help more than it interrupted? <yes/no + one paragraph>

## Problems (ranked)

| Rank | Problem | Where it bit (lookup #) | Frequency | Severity (1–5) | Proposed fix |
|------|---------|-------------------------|-----------|----------------|--------------|
| 1     |         |                         |           |                |              |

### Top five (task 6 input)

1.
2.
3.
4.
5.
```

## Rules for the test

- The GM plays normally; nothing in the session exists to flatter the tool.
- Log every lookup, including trivial ones and repeats — repeats are a signal.
- Do not fix anything mid-session; note it and keep playing.
- No audio capture (descoped, `GM_ASSISTANT_MODE_PLAN.md` P3.1).
- The report is evidence: link it from `docs/STATUS.md` when done.
