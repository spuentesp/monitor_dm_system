# Live verification — GM Assistant entry correction (G03, CF-1 amendment)

> **Date:** 2026-11-10 · **Scope:** G03 gap plan
> (`docs/architecture/gm-assistant-gap-plans/G03-entry-correction.md`)
> Phase 3 live pass — successor to `live_gm_assistant_phase_a_2026-11-06.md`
> for the mid-session strike/edit surface.
> **Method:** API-level pass against the live stack (backend + Mongo/Neo4j +
> a live chat provider). Browser rendering is covered by vitest
> (`SessionRecorder.test.tsx`, `SessionLogPanel.test.tsx`), not by this pass.
> **Result:** PENDING — needs a live stack; run after `./dev.sh` is up.

## Steps

| # | Step | Result | Observed |
|---|---|---|---|
| 1 | Create a `gm_assistant` recording and log two entries | PENDING | `POST /api/chat` → 201; `POST /api/chat/{id}/send` ×2 → 200 |
| 2 | Edit the first entry | PENDING | `PATCH /api/gm/session-log/entries/{id}` `{"universe_id": …, "text": …}` → 200; `GET /api/chat/{id}/messages` serves the edited text (cache evicted), `edited_at` set |
| 3 | Strike the second entry | PENDING | `DELETE /api/gm/session-log/entries/{id}` → 200, `entry.struck: true`; the recorder hides it and lists it under **Struck entries** |
| 4 | Undo the strike | PENDING | `POST /api/gm/session-log/entries/{id}/restore` → 200, `entry.struck: false`; the entry is back in the transcript |
| 5 | Strike an entry that has queued capture proposals | PENDING | entry logged with story/scene context → `POST /api/gm/capture/insights` staged ≥1 proposal; strike → `retracted_proposal_ids` non-empty; CF-8 (`/forge/review` or the Canon panel) shows the proposal **rejected** with reason `struck at the table` |
| 6 | Retract a staged session-log proposal directly | PENDING | `POST /api/gm/session-log/proposals/{id}/retract` → 200, `status: rejected`, reason recorded; appears in CF-8 as rejected with that reason |
| 7 | Owner-only strike (enforced auth mode) | PENDING | second user `DELETE`s the first user's entry → 404 `{"detail": "Not found"}`; owner → 200 |

## Acceptance mapping (G03)

- **Edit updates the transcript and re-runs insight extraction for that entry
  only, fail-open** → step 2 (inspect the PATCH response: `insight` present,
  or `insight_skipped: true` with the entry still updated).
- **Struck entries hidden from the recorder view, visible in a struck audit
  list; retracted proposals appear in CF-8 as rejected with the strike
  reason** → steps 3 + 5.
- **Owner-only strike** → step 7.

## Not covered by this pass

- Browser rendering of the edit/strike buttons, the struck audit list, and
  the panel's per-row **Retract** — covered by vitest.
- Struck entries are still visible to wrap-up/recap transcript consumers in
  v1 (the strike is recorder-view + CF-8 scoped); revisit if the table test
  (G11) flags it.
