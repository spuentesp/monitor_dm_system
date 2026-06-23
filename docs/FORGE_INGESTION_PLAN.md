# World Forge: Ingestion Repair & Seed-to-Playable Plan (Phase 7)

> **Created:** 2026-06-12, after the report "we have not been able to ingest a
> single PDF in the World Forge UI". Tasks T-082+ in `FINAL_FABLE_TASKS.md`.
> Companion to `docs/UI_REVAMP_PLAN.md` (Phase 6).
>
> **Goal hierarchy:** (A) a PDF dropped in the Forge reliably becomes a
> reviewed knowledge pack — or fails *loudly* with a reason and a retry path →
> (B) a one-sentence seed becomes a playable universe in under two minutes
> (Emochi/SillyTavern-style), because most roleplay worlds start from a vibe,
> not a 300-page lorebook → (C) both paths land in the same place: a bound,
> playable session.

## A. Ingestion truth & repair (T-082..T-086)

### A1. Live diagnosis first (T-082)

Drive a real PDF through `POST /api/ingest/sources/upload` exactly as
`UploadCard.tsx` does and record where it actually dies (job stage, container
log, DB state). Fix the breakage found — not the breakage guessed. Repeat
until a small text PDF completes: upload → scan → extract → pack created.

**Verify:** a 1-page PDF reaches `status: completed` with a pack in the
library, from the UI, on the dockerized stack.

### A2. Edge-case matrix (T-083) — ✅ closed

Every row gets a test (unit or live) and a defined UX outcome — either it
works or it fails with a visible reason. No silent hangs. Recovery controls
and the backend-restart path are documented in
`docs/gameplay-examples/forge-ingestion-troubleshooting.md`.

| Case | Expected outcome |
|---|---|
| Text PDF (happy path) | completes; pack with entities/lore/axioms |
| Scanned/no-text-layer PDF | fails fast: "no extractable text (scanned image?)" |
| Encrypted PDF | fails fast: "password-protected" |
| Malformed/truncated PDF | fails fast with parser error, job not stuck |
| Huge PDF (≥50MB / 500+ pages) | streams, chunked stages, progress visible |
| Empty file / 0 bytes | rejected at upload (422), no job created |
| Duplicate upload (same content) | allowed but flagged; no queue deadlock |
| .txt / .md / .docx / .epub | all complete via multi_format path |
| Unsupported type (.png, .zip) | rejected at upload with clear message |
| LLM provider down mid-job | job → failed with stage + cause; retry works |
| Embedding service down | job fails clearly (no empty-vector writes — T-054 guard) |
| Backend restart mid-job | job recoverable: unlock + rescan path documented in UI |
| Queue locked by stale run | Unlock button visible and functional |
| Cancel mid-stage | job → cancelled; queue moves on |

### A3. Failure visibility & controls in the Forge UI (T-084, supersedes T-062)

- Job rows surface `error_message` and the failing stage *prominently* (red
  card, not buried in metadata), with **Retry** (rescan), **Cancel**,
  **Unlock queue**, and **Purge failed** wired to existing endpoints.
- Stage log viewer per job (jobs already stream stages via SSE).
- Upload validation client-side: type/size checks before the POST.

### A4. Hardening fixes that fall out of A1/A2 (T-085)

Backend repairs discovered by the matrix (parser guards, timeout per stage,
clearer error propagation from `ingestion_pipeline` into the job document).

### A5. Regression net (T-086)

- Unit: pdf_processing edge cases (encrypted/scanned/truncated fixtures).
- Live e2e (`RUN_E2E=1`): tiny-PDF round trip to `completed` + pack assert.

## B. Seed-to-playable: light worlds, not just lorebooks (T-087..T-090)

The Emochi/SillyTavern insight: a playable world needs *a premise, a place,
two or three characters with wants, and an opening beat* — about one LLM call
of content. The Forge should treat that as a first-class input.

### B1. Quick-world backend (T-087)

`POST /api/forge/quick-world` with `{ seed: string, genre?, tone?, name?,
start_playing?: bool }`:

1. One structured LLM call (existing dspy/instructor stack) expands the seed
   into: world name + description, 1 axiom, 3–4 entities (ally, antagonist,
   location, optional faction — each with description, wants, state tags),
   2–3 lore facts, an opening scenario hook, and a suggested PC concept.
2. Commits directly via data-layer tools (multiverse → universe → entities →
   facts → axiom), `canon_level: canon` — quick worlds skip review by design.
3. Returns ids + a summary payload; with `start_playing` also creates a chat
   session bound to the universe (reusing the session bootstrap) and returns
   `session_id`.

**Verify:** curl with a one-line seed → universe exists in the tree with
entities/facts; `start_playing` returns a session that narrates turn 1.

### B2. Character-card import, SillyTavern-compatible (T-088)

Import `chara_card_v2` JSON (and PNG-embedded tEXt variant if cheap) into the
existing `StandaloneCharacter` model (`name`, `description`, `personality`,
`first_message` map 1:1). Export the same shape. This is the bridge for the
SillyTavern ecosystem: drop a card → chat with it in Play.

**Verify:** a real ST card JSON imports; the character appears in the Play
character panel; `first_message` opens the chat.

### B3. Forge "Quick Start" tab (T-089)

New first tab in the Forge: a seed textarea ("A rain-soaked noir city where
memories are currency…"), genre/tone chips, optional name, a **Forge world**
button with progress states, and a result card: what was created, **Play here
now** (deep link, uses the global world context from T-077) and **Open in
tree**. Below it, the character-card dropzone (B2). The current upload/pack
machinery stays as the "Lorebook ingestion" tab — the heavy path.

### B4. Docs & walkthrough (T-090)

`docs/gameplay-examples/quick-world-walkthrough.md`: seed → forge → play in
under two minutes, plus the card-import flow.

## C. Acceptance for "Forge complete"

1. A real PDF ingests to a reviewed pack from the UI; every matrix row
   behaves as specified; failures are visible and retryable.
2. A one-sentence seed becomes a playable universe + bound session in <2 min
   wall-clock on the dockerized stack.
3. A SillyTavern card imports and is immediately playable.
4. Ledger updated; e2e specs cover both paths.

### Execution rules

Work A before B (a Forge that can't ingest is lying about its core promise);
within each phase, top to bottom; every task lands with its verify step green
on the live stack.
