# G10 — Spec/doc drift cleanup (DOC-1)

> **Status:** implemented 2026-11-11 (DOC-1; docs-only cleanup, shipped with the
> wave-1 gap merges). Originally proposed 2026-11-11. Gap: every CF spec still documents a
> `monitor copilot …` CLI as its Layer 3 surface, but the settled decision
> (GAP_REMEDIATION_PLAN §G-5 Option A, adopted in `GM_ASSISTANT_MODE_PLAN.md`)
> is web-only `/gm`. Meanwhile the CF yml files say `status: done` while
> `docs/1_product/epics.md` rates EPIC 7 "Partially". Contributors reading
> the specs will build the wrong thing.

## Goal

Make the docs tell one story: web `/gm` is the only copilot surface; the
canonical yml status is the source of truth; the epic coverage row matches.

## Use case

**DOC-1** (documentation governance) — no new UC ID.

## Tasks

1. **CF specs (8 files):** in each
   `docs/use-cases/epic-7-copilot-CF/CF-N/CF-N-specification.md`, replace
   the "Layer 3 (CLI)" `monitor copilot …` block with the web surface
   (`/gm` panel + the concrete `/gm/...` / `/canon-review/...` routes), and
   add the standard note already used in `docs/USE_CASES.md`: "the CLI
   examples describe the intended workflow; the wired surface is the web
   API". Where a spec's CLI block is aspirational, either implement the
   route or mark it future work.
2. **CF-1 spec input modes:** keep the P3.1 descope note until G02 ships
   (then update per `G02-audio-capture-CF-10.md`).
3. **`docs/1_product/epics.md` EPIC 7 row:** reword to match reality —
   "CF-1…CF-8 implemented on the web `/gm` surface (117 targeted tests green,
   live pass 11/11 2026-11-06); field validation pending (G11 table test);
   new gaps planned in `docs/architecture/gm-assistant-gap-plans/`."
4. **`docs/USE_CASES.md`:** add the proposed new IDs CF-9…CF-15 as
   `proposed` rows pointing at the gap plans, so the catalog and the plans
   stay in sync (catalog "evolves over time").
5. **Status tables:** refresh the "Last verified" dates in
   `session-support.md` / `analysis-prep.md` after edits.
6. **Check for other stale `monitor copilot` references:**
   `grep -rn "monitor copilot" docs/ packages/` — fix or mark aspirational;
   `packages/cli/IMPLEMENTATION.md` mentions CF — verify it doesn't promise
   a copilot command.

## Acceptance

- `grep -rn "monitor copilot" docs/ packages/` returns only intentional
  "not shipped, web-only" notes.
- EPIC 7 coverage row and CF yml statuses agree.
- Commits reference DOC-1 (and CF-N where a spec changed).

## Effort

S — a focused docs pass, no code.
