# CF-11: Advance World Time

**Actor:** Human GM
**Trigger:** Co-Pilot → Prep (mid- or post-session) — clock control in the
`PrepToTablePanel` and the recorder `WrapUpModal`
**Status:** done — implemented 2026-11-11 (gap G04, plan [G04](../../../architecture/gm-assistant-gap-plans/G04-world-clock-CF-11.md))

**Purpose:** Give each story an in-fiction world clock the GM advances
explicitly ("+3 days", "+2 hours", or to an absolute date), have deadlines
react to it, and surface *what changed because time passed* in the next
briefing (CF-7) and recap (CF-2).

**Flow:**

1. **Read the clock:** current world time (ISO-8601 internally, free-form
   display string per universe), due/overdue deadlines, the advance audit
   log, and the last off-screen NPC tick.
2. **Advance time (with confirmation):** relative delta or absolute target;
   the clock is monotonic — equal targets are idempotent no-ops, backwards
   moves are refused (422). Every real advance appends an audit record.
3. **Deadline evaluation (deterministic):** each deadline flips
   `upcoming → due → overdue` by calendar date; a move that crosses
   deadlines reports them as *crossed* and stages one pending
   `ProposedChange` per crossed deadline for the CF-8 review queue —
   never a direct Neo4j write (CanonKeeper stays the only writer).
4. **Off-screen tick (LLM, grounded in canon):** when time actually passed,
   `GmTableAgent.advance_and_summarize` generates a short "what NPCs did
   while time passed" paragraph over canon facts/names (a generation, not a
   simulation) and stores it on the clock for the next CF-7 prep briefing.
5. **Briefing & recap:** the CF-7 prep panel shows elapsed time
   (last advance `from → to`), due/overdue deadlines and the off-screen
   tick; the CF-2 last-session lookup gains `world_time` and a `time_line`
   of advances.

**Amends:**

- **CF-7 (Session Prep Assistant):** briefing gains a "time passed since
  last session" section (clock readout, due/overdue deadlines, off-screen
  NPC summary).
- **CF-2 (Generate Session Recap):** recap payload gains a world-clock
  time line (`world_time` + `time_line`).
- **CF-3 (Unresolved Threads):** deadlines surface alongside threads as
  due/overdue chips in the prep panel.

### Implementation

**Layer 1 (Data Layer):**
```python
# schemas/world_clock.py — WorldClockResponse, DeadlineStatus, parse_time_delta
mongodb_get_world_clock(query)            # read the clock (None if unset)
mongodb_advance_world_clock(params)       # monotonic + idempotent + audit log
mongodb_list_due_deadlines(query)         # due/overdue at current world time
mongodb_upsert_world_deadline(params)     # attach a deadline (clock must exist)
mongodb_record_offscreen_summary(params)  # persist the agent's tick
```

**Layer 2 (Agents):**
```python
GmTableAgent.advance_and_summarize(universe_id, story_id, delta | target_time)
# deterministic deadline flip (Layer 1) + OffScreenSummary typed LLM call
```

**Layer 3 (UI backend):**
```python
GET  /gm/clock/{story_id}?universe_id=...  # CF-7 briefing payload
POST /gm/clock/advance                     # {delta} or {target_time}; owner-guarded
POST /gm/clock/deadline                    # create/replace a deadline
POST /gm/lookup/last-session               # + world_time, time_line (CF-2)
```

**Open decisions (v1 choices):**

- *Calendar model:* ISO-8601 internally + display string; fantasy calendars
  are a per-universe display concern (deferred).
- *Who may advance time:* session owner only — enforced as universe
  ownership (`require_universe_owner`, SYS-6).
- *First set:* a story with no clock accepts only an absolute
  `target_time` (there is nothing to move forward from); relative deltas
  before first set are refused with a 422.

---
