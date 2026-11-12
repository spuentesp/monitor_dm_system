# G03 — Mid-session strike/edit of captured entries (CF-1 amendment)

> **Status:** implemented 2026-11-11 (CF-1 amendment: entry edit/strike/restore +
> proposal retract; `docs/use-cases/epic-7-copilot-CF/CF-1/CF-1-specification.md`
> amended). Originally proposed 2026-11-11. Gap: CF-1's spec has the GM annotating
> live ("this is important", "this should not be canon"), and session-log
> proposals exist (`POST /gm/session-log/propose`) — but there is no
> strike/edit/delete of an already-logged entry or a queued candidate fact
> *before* wrap-up. A mis-captured moment is only fixable later in CF-8.

## Goal

While recording, the GM can edit or strike any logged entry and retract or
edit any candidate fact/insight that has been queued as a `ProposedChange`,
in one click, without ending the session.

## Use case

Amend **CF-1** (no new ID): add acceptance criterion "GM can edit or strike
a logged entry in real time and retract a queued candidate proposal before
wrap-up." Update `CF-1-specification.md` flow step 6 and the CF-1 yml.

## Design

- **Layer 1:** extend `mongodb_tools/` session-entry tools with
  `update_entry(entry_id, text)` and `delete_entry(entry_id, soft=True)`
  (soft-delete keeps an audit trail), plus proposed-change tools already
  support status transitions — add `retract`/`edit-draft` on pending
  proposals (`test_proposed_change_tools.py` covers the base).
- **Layer 2:** thin pass-throughs in the capture/ingest agents
  (`ingestion/session_ingest.py`, `capture_insights.py`); retracting a
  candidate fact marks the `ProposedChange` `rejected_by_gm` with reason
  "struck at the table" so CF-8 shows *why* it disappeared.
- **Layer 3:** `PATCH /gm/session-log/entries/{entry_id}`,
  `DELETE /gm/session-log/entries/{entry_id}`,
  `POST /gm/session-log/proposals/{proposal_id}/retract` in
  `routers/gm_tools.py`; Session Log panel gets per-row edit/strike buttons
  (`components/gm/SessionLogPanel.tsx`).

## Phases

1. Data-layer tools + tests (`test_tools/`, soft-delete semantics).
2. Routes + authz tests (owner-only: only the session owner can strike).
3. Panel UI + vitest; live-verification step added to
   `docs/testing/live_gm_assistant_phase_a_2026-11-06.md` successor.

## Acceptance

- Editing an entry updates the draft scene transcript and re-runs insight
  extraction for that entry only (fail-open: LLM failure → entry kept,
  insight skipped).
- Struck entries are hidden from the recorder view but visible in an
  "struck" audit list; retracted proposals appear in CF-8 as rejected with
  the strike reason.
- Green: data-layer, backend, frontend tests; commits reference CF-1.

## Open decisions

- Hard vs. soft delete: v1 soft-delete only (audit trail; CF-8 needs the
  history anyway).
- Whether striking an entry should also retract its already-queued
  proposals automatically (recommended: yes, with one undo).
