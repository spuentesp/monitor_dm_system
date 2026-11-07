# Live verification — GM Assistant (Co-Pilot), Phase A

> **Date:** 2026-11-06 · **Scope:** `GM_ASSISTANT_MODE_PLAN.md` §8 live pass ·
> **Method:** API-level pass against the live stack (backend + Mongo/Neo4j/
> Qdrant + a live chat provider). Browser rendering is covered by vitest, not
> by this pass.
> **Result:** 11/11 steps passed.

## Environment

| Piece | State |
|---|---|
| Infra | `monitor-mongodb`, `monitor-neo4j`, `monitor-qdrant`, `monitor-postgres`, `monitor-redis` — all up (docker) |
| Backend | uvicorn `monitor_ui.main:app` on `127.0.0.1:8000` — `/api/health` ok |
| Chat provider | registry provider `minimax-std` (live, ~0.9 s round-trip) |
| Universe | `324588d9-1907-4f87-9ca8-8a713d4aab4a` ("Live check"), bound system `04dba354-…` |

## Steps

| # | Step | Result | Observed |
|---|---|---|---|
| 1 | Create a `gm_assistant` recording | PASS | `POST /api/chat` → 201, `mode=gm_assistant`, story/scene bootstrapped |
| 2 | Log an entry (GM turn) | PASS | `POST /api/chat/{id}/send` → 200; co-pilot replied `"What is your character's name?"` (fresh recording → session bootstrap asks for the character) |
| 3 | Per-entry insights (P1.2) | PASS | `POST /api/gm/capture/insights` → participants `["Mira"]`, locations `["the sunken chapel"]`, candidate fact `"Mira is at the sunken chapel"` |
| 4 | Live contradiction check (P1.1) | PASS | `POST /api/gm/capture/contradiction-check` → `{"alert": null}` — correct: this universe carries no canon that contradicts the entry |
| 5 | Wrap-up digest (P1.3) | PASS | `POST /api/chat/{id}/wrap-up` → recap + canon counts (`0/0/0`) + open threads + `next_prep` teaser |
| 6 | Persisted recap (P1.4) | PASS | `GET /api/chat/{id}/recap` → `{"persisted": true}` — served from the session doc, no regeneration |
| 7 | Archive flag round-trip (P3.3, new) | PASS | `PATCH /api/chat/{id}` `{"archived": true}` → 200, `archived: true` |
| 8 | Archived flag visible in the list (P3.3, new) | PASS | `GET /api/chat` → the session reports `archived: true` |
| 9 | Server dice (P2.1) | PASS | `POST /api/gm/roll` `2d6+3` → rolls `[1, 4]`, total `8` (= 1+4+3) |
| 10 | Scratchpad persistence (P2.3) | PASS | `GET` empty → `PUT` note → `GET` returns the note |
| 11 | Universe → bound system (P2.2) | PASS | the selected universe resolves `default_game_system_id` |

## Observations (not failures)

- The recording's recap is generic ("The story is just beginning…") because
  this universe carries almost no canon, and the recording's first turn is the
  character bootstrap. A populated universe (Fallout/VtM seeds) produces a
  richer digest — that was verified separately for Session Zero
  (`live_verification_g1_2026-07-23.md`).
- Step 4's `alert: null` is the expected outcome here; the alert path itself
  is covered by unit/backend/frontend tests (P1.1).

## Not covered by this pass

- Browser rendering of the recorder UI (Active/Archived `<optgroup>`s, the
  Archive button, the scratchpad ingest hint) — covered by
  `packages/ui/frontend/src/components/gm/SessionRecorder.test.tsx` and
  `packages/ui/frontend/src/app/gm/page.test.tsx` (vitest).
- Multi-world breadth — this is a single-universe smoke pass, not the
  three-world protocol of the Session Zero verification.
