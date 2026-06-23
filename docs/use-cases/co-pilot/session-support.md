# Co-Pilot: Session Support (CF-1 to CF-4)

> **Source of truth:** YAML specs and per-use-case specifications in
> [`../epic-7-copilot-CF/`](../epic-7-copilot-CF/). This file is a **narrative index** that
> groups the four use cases by user-facing workflow.

This sub-file is a **companion reading aid**, not the canonical spec.
The canonical specs are:

- [CF-1: Record or Capture Assisted Session](../epic-7-copilot-CF/CF-1/CF-1-specification.md)
- [CF-2: Generate Session Recap](../epic-7-copilot-CF/CF-2/CF-2-specification.md)
- [CF-3: Track Unresolved Threads](../epic-7-copilot-CF/CF-3/CF-3-specification.md)
- [CF-4: Suggest Plot Hooks](../epic-7-copilot-CF/CF-4/CF-4-specification.md)

---

## User Workflow

1. **CF-1 — Record session.** GM starts a capture session (text, audio, or hybrid).
   System parses incoming material, creates draft story/scene documents in MongoDB,
   and queues `ProposedChange` items with timestamp, participants, location.
2. **CF-2 — Generate recap.** After a session ends, MONITOR summarizes what happened
   for the GM and players.
3. **CF-3 — Track unresolved threads.** Open questions, dangling NPCs, prophecies,
   and untriggered events are surfaced between sessions.
4. **CF-4 — Suggest plot hooks.** Based on the current canon, recent events, and
   unresolved threads, MONITOR proposes 3-5 plot hooks the GM can use next session.

All four feed into **CF-8** (CanonKeeper Review Queue, see
[`analysis-prep.md`](analysis-prep.md)) so the GM can approve, reject, or edit
each proposed change before it is canonized.

---

## Implementation Status (verified 2026-06-05)

| ID | Backend | Frontend | Notes |
|----|---------|----------|-------|
| CF-1 | ✅ | ✅ | Capture mode + passive parsing in `packages/agents/src/monitor_agents/session_ingest.py` |
| CF-2 | ✅ | ✅ | `build_story_recap()` in `packages/agents/src/monitor_agents/loops/story_loop.py:988` |
| CF-3 | ✅ | ✅ | `PlotHookAgent` + `unresolved_threads` query in `packages/agents/src/monitor_agents/plot_hooks.py` |
| CF-4 | ✅ | ✅ | `POST /gm/hooks` in `packages/ui/backend/src/monitor_ui/routers/gm_tools.py` |

See [`epic-7-copilot-CF/CF-N/CF-N.yml`](../epic-7-copilot-CF/CF-N/) for canonical YAML.

---

*Last verified: 2026-06-07. If a link is broken, the canonical spec lives one directory up at `epic-7-copilot-CF/CF-N/`.*
