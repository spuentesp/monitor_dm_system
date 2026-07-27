# Co-Pilot: Analysis & Prep (CF-5 to CF-8)

> **Source of truth:** YAML specs and per-use-case specifications in
> [`../epic-7-copilot-CF/`](../epic-7-copilot-CF/). This file is a **narrative index** that
> groups the four use cases by user-facing workflow.

This sub-file is a **companion reading aid**, not the canonical spec.
The canonical specs are:

- [CF-5: Detect Contradictions](../epic-7-copilot-CF/CF-5/CF-5-specification.md)
- [CF-6: Generate Player Handouts](../epic-7-copilot-CF/CF-6/CF-6-specification.md)
- [CF-7: Session Prep Assistant](../epic-7-copilot-CF/CF-7/CF-7-specification.md)
- [CF-8: Review Session Ingestion and CanonKeeper Queue](../epic-7-copilot-CF/CF-8/CF-8-specification.md)

---

## User Workflow

These four use cases are the **GM-side analysis & preparation toolkit**.
They take the captured session data (CF-1..CF-4) and turn it into a
reviewable, well-prepared next session.

1. **CF-5 — Detect contradictions.** Scan recent facts and the existing canon
   for logical contradictions. Surface them for GM review before canonization.
2. **CF-6 — Generate player handouts.** Create distributable documents
   (letters, maps, rumors, prophecies) from world data.
3. **CF-7 — Session prep assistant.** Generate prep materials — suggested
   scenes, NPC reminders, hooks to revisit — for the next session.
4. **CF-8 — Review CanonKeeper queue.** The audit gate: per scene, show what
   MONITOR is about to add to the world, with Accept / Reject / Defer / Edit
   verdicts per item.

CF-8 is the **final gate** before canonization: it reads the same
`ProposedChange` documents that CF-5/CF-6/CF-7 produce, and the GM's verdict
controls whether CanonKeeper commits them to Neo4j.

---

## Implementation Status (verified 2026-06-05)

| ID | Backend | Frontend | Notes |
|----|---------|----------|-------|
| CF-5 | ✅ | ✅ | `ContradictionModule` in `packages/agents/src/monitor_agents/canonkeeper/verification.py:27`; `POST /gm/contradictions` |
| CF-6 | ✅ | ✅ | `PlotHookAgent.generate_handout()`; `POST /gm/handouts`; `Handout` schema |
| CF-7 | ✅ | ✅ | `PlotHookAgent.generate_session_prep()`; `POST /gm/session-prep` |
| CF-8 | ✅ | ✅ | **`packages/ui/backend/src/monitor_ui/routers/canon_review.py`** (9.4KB, implemented 2026-06-05); accept/reject/list/batch-verdict endpoints |

> **Note on CF-8:** The 2026-06-03 audit incorrectly listed CF-8 as "Procedural
> Generation, not implemented" because it confused CF-8 with an older draft.
> The canonical CF-8 spec is the CanonKeeper Review Queue, and it IS
> implemented in `canon_review.py` (see bug fix 2026-06-05).

See [`epic-7-copilot-CF/CF-N/CF-N.yml`](../epic-7-copilot-CF/CF-N/) for canonical YAML.

---

*Last verified: 2026-06-07. If a link is broken, the canonical spec lives one directory up at `epic-7-copilot-CF/CF-N/`.*
