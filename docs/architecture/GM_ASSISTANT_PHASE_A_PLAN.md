# GM Assistant Phase A — Implementation Guide

> **Status:** implemented (2026-11-06) — A1–A4 shipped. Live pass 11/11
> (`docs/testing/live_gm_assistant_phase_a_2026-11-06.md`). Anchors verified
> against code on this branch (head `64fb76b`). Closes the three remaining
> open items of `GM_ASSISTANT_MODE_PLAN.md` (P3.1, P3.2, P3.3) plus the
> live-verification gap, then fixes the stale "GM plan now fully closed" claim
> in `FORGE_EXPANSION.md` (§18 rows 18–20).
>
> Conventions (from `AGENTS.md`): pydantic v2; line-length 100; mypy strict;
> layer rules (UI/CLI → agents → data-layer); `structlog` in Python, no
> print. **Never modify `tests/verification/**` or `tests/property/**`
> (sealed).** New tests go in `packages/ui/backend/tests/` and
> `packages/ui/frontend/src/**/*.test.tsx`.

---

## Scope

| ID | Item | Effort | Type |
|----|------|--------|------|
| A1 | P3.1 — descope audio/hybrid capture (decision + docs) | 15–30 min | docs |
| A2 | P3.2 — "Proposals land in Forge → Review" hint (option a) | 1–2 h | frontend + test |
| A3 | P3.3 — recording archive metadata (`archived` end-to-end) | ~1 day | backend + frontend + tests |
| A4 | Live verification pass of capture → wrap-up → archive | ~1 day | manual, recorded in docs |

Suggested PR order: **A1 → A2 → A3 → A4** (A3 is independent of A2 but both
touch `packages/ui/frontend/src/app/gm/` — land A2 before A3 to avoid merge
overlap in `page.test.tsx` / `page.tsx`; A4 is last, after the code ships).

---

## A1 · P3.1 — Audio/hybrid capture descope (docs only)

**Decision (recommended, per `GM_ASSISTANT_MODE_PLAN.md` P3.1):** descope.
Text capture covers the persona's table workflow; audio needs a transcription
vendor, a new ingest path, and diarization — its own plan. Code grep confirms
0% shipped (`whisper|transcrib|microphone|audio_capture|audio-upload` has no
capture hits in `packages/`).

### Edits

1. **`docs/use-cases/epic-7-copilot-CF/CF-1/CF-1-specification.md:22-26`** —
   "Input Modes" list currently includes two audio bullets. Replace with:

   ```markdown
   **Input Modes:**
   - Live text/chat notes entered during play
   - Uploaded or pasted transcript after play
   - Hybrid notes + post-session cleanup
   ```

   Audio/hybrid capture is **future work, out of CF-1 shipped scope** (decision:
   `docs/architecture/GM_ASSISTANT_MODE_PLAN.md` P3.1) — add that sentence as a
   bold note under the list, and update the doc's "Last verified" date.

2. **`docs/use-cases/epic-7-copilot-CF/session-support.md:19`** — "(text,
   audio, or hybrid)" → "(text)". Refresh the status table's "Last verified"
   date.

3. **`docs/use-cases/epic-7-copilot-CF/CF-1/CF-1.yml`** — `acceptance_criteria`
   is `["TBD"]` (auto-scaffolded stub), so there is nothing to remove. Replace
   `"TBD"` with one real criterion, e.g. `"GM can create a recording and log
   text entries that produce story-scoped draft proposals (text input only;
   audio/hybrid explicitly out of scope)"`. Update `status` to `"shipped"`.

4. **`docs/architecture/GM_ASSISTANT_MODE_PLAN.md`** P3.1 section (after
   :508) — append the decision marker:

   ```markdown
   **Status: DECIDED 2026-11-06 — descoped.** Text input is CF-1's shipped
   scope; audio/hybrid is future work. Spec bullets edited accordingly (see
   `GM_ASSISTANT_PHASE_A_PLAN.md` A1). If audio is ever built: transcription
   feeds the existing text ingest pipeline — never a parallel capture loop.
   ```

### Acceptance

- `rg -n -i "microphone|audio capture|text, audio, or hybrid"` across
  `docs/use-cases/epic-7-copilot-CF/` returns only the explicit "future work"
  note and the descope decision.
- No code touched. No tests.

---

## A2 · P3.2 — Scratchpad ingest hint line (frontend + test)

**Design (plan option a):** a permanent hint line under the scratchpad
**Ingest** button: *"Proposals land in Forge → Review"*. The note tells the
GM where document-pipeline proposals surface; it does not thread `story_id`
(option b defers pending a product decision — see `FORGE_EXPANSION.md` §17).

### Edits

1. **`packages/ui/frontend/src/app/gm/page.tsx`**, `SessionNotebook` toolbar
   (Ingest button at :405-413, inside the toolbar `div` that starts :388).
   Add a hint span after the button and extend the button `title`:

   ```tsx
   <button
     onClick={() => ingestNotes.mutate()}
     disabled={!notes.trim() || ingestNotes.isPending}
     className={cn("btn-ghost text-xs py-0.5 px-2", !notes.trim() && "opacity-40 cursor-not-allowed")}
     title="Ingest notes into the world knowledge base. Proposals land in Forge → Review."
   >
     {ingestNotes.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />} Ingest
   </button>
   <span
     data-testid="ingest-hint"
     className="hidden sm:inline text-[10px] text-slate-700"
   >
     Proposals land in Forge → Review
   </span>
   ```

   No Tooltip component exists in `components/ui/` (verified) — the repo's
   convention is the native `title` attribute, so no new dependency.

2. **`packages/ui/frontend/src/app/gm/page.test.tsx`** — extend the
   "GM Assistant scratchpad (P2.3 — server-backed, no localStorage)" describe
   block (:204) with one case:

   ```tsx
   it("shows where ingest proposals land (P3.2)", async () => {
     mockUniverseApis([makeUniverse("u-1", "Alpha World", "sys-1")], [makeSystem("sys-1", "Bound")]);
     renderPage();
     expect(await screen.findByTestId("ingest-hint")).toHaveTextContent(
       "Proposals land in Forge → Review",
     );
   });
   ```

   Reuse the existing `renderPage` helper of that describe block.

### Acceptance

- `npx vitest run src/app/gm/page.test.tsx` — new test green, block green.
- No backend change; the ingest flow itself is untouched.

---

## A3 · P3.3 — Recording archive metadata (backend + frontend)

**Goal:** recordings are distinguishable in session lists and archivable.
`wrapped_up_at` (P1.4) and the `SessionList` mode badge (:175) already exist;
what's missing is the `archived` field and the Recorder dropdown grouping.

### Backend

1. **`packages/ui/backend/src/monitor_ui/routers/chat_schemas.py`** —
   `Session` (:103-141), next to the P1.4 fields (:139-141):

   ```python
   recap_text: str | None = None
   wrapped_up_at: str | None = None
   # P3.3 — GM archive flag for recordings (additive; old docs read as None).
   archived: bool | None = None
   ```

2. **`.../chat_schemas.py`** — `SessionPatch` (:173-182), add:

   ```python
   archived: bool | None = None
   ```

3. **`packages/ui/backend/src/monitor_ui/routers/chat.py`** — PATCH handler
   (`update_session`, :1068-1121). Insert after the `roll_model` block
   (:1110-1118), before `session["updated_at"] = _now()` (:1119):

   ```python
   if body is not None and body.archived is not None:
       session["archived"] = body.archived
   ```

   Persistence is already handled by the existing `_db_save_session(session)`
   at :1120 — no other write path.

4. **`.../chat.py`** — `list_sessions` serializer (:267-299) builds `Session`
   **explicitly per field** (unlike `_build_session_state` :246 and the PATCH
   return :1121, which use `Session(**session, ...)` and pick up new keys
   automatically). Add after `wrapped_up_at=s.get("wrapped_up_at"),`:

   ```python
   archived=s.get("archived"),
   ```

   This is the one serializer that must be edited by hand; skip it and the
   field never reaches the UI list.

### Frontend

5. **`packages/ui/frontend/src/lib/types.ts`** — `Session` (:34-36):

   ```ts
   recap_text?: string | null;
   wrapped_up_at?: string | null;
   // P3.3 — GM archive flag for gm_assistant recordings.
   archived?: boolean;
   ```

6. **`packages/ui/frontend/src/lib/api.ts`** — `patchSession` data type
   (:251-258): add `archived?: boolean` to the inline union, e.g.
   `{ title?: string; tone?: string; scene_id?: string; story_id?: string; roll_model?: string; archived?: boolean }`.

7. **`packages/ui/frontend/src/components/gm/SessionRecorder.tsx`**:

   - Dropdown (:191-204): split `recordings` into active / archived and render
     `<optgroup>`s:

     ```tsx
     const activeRecordings = recordings.filter((r) => !r.archived);
     const archivedRecordings = recordings.filter((r) => r.archived);
     ```

     then in the `<select>`, after the empty-state `<option>`:

     ```tsx
     {activeRecordings.length > 0 && (
       <optgroup label="Active">
         {activeRecordings.map((r) => (
           <option key={r.id} value={r.id}>
             {r.title} · {formatRelativeTime(r.updated_at)}
             {r.wrapped_up_at ? " · wrapped up" : ""}
           </option>
         ))}
       </optgroup>
     )}
     {archivedRecordings.length > 0 && (
       <optgroup label="Archived">
         {archivedRecordings.map((r) => (
           <option key={r.id} value={r.id}>{r.title} · {formatRelativeTime(r.updated_at)}</option>
         ))}
       </optgroup>
     )}
     ```

     Update the `useEffect` default-selection (:84-87) to keep preferring the
     latest *active* recording: derive `recordings[0]` from
     `activeRecordings[0] ?? archivedRecordings[0]` (or keep behaviour — pick
     the newest non-archived; an archived selection is still allowed).

   - Archive action — next to "Wrap up session" (:228-235), visible only for
     a wrapped-up, not-yet-archived recording:

     ```tsx
     {active && active.wrapped_up_at && !active.archived && (
       <button
         onClick={() =>
           chatApi.patchSession(active.id, { archived: true }).then(() => {
             qc.invalidateQueries({ queryKey: ["sessions"] });
           })
         }
         className="btn-ghost text-xs py-1 px-2.5 border border-white/10"
         title="Archive this wrapped-up recording (P3.3)"
       >
         <Archive className="w-3 h-3" /> Archive
       </button>
     )}
     ```

     Import `Archive` from `lucide-react` (add to the import block :6-23).
     Keep the action out of the transcript area; placement in the toolbar is
     fine.

### Tests

8. **`packages/ui/backend/tests/test_session_api.py`** — follow the
   `test_patch_session_chat_mode` pattern (:129-142):

   - `test_patch_session_archived_true` — PATCH `{"archived": true}` → 200,
     response `archived is True`; also assert a second PATCH back to `false`
     flips it (idempotence).
   - `test_patch_session_archived_invalid` — PATCH `{"archived": "yes"}` → 422.
   - Extend one existing list test to assert `archived` round-trips through
     `GET /chat` (the explicit list serializer is the regression risk).

9. **`packages/ui/frontend/src/components/gm/SessionRecorder.test.tsx`** —
   extend the `vi.mock("@/lib/api", ...)` factory (:17-28) with
   `patchSession: vi.fn()`:
   - dropdown renders an `optgroup` per group and places an `archived: true`
     recording under "Archived";
   - Archive button hidden for unwrapped recordings, visible for
     wrapped-and-unarchived, and clicking it calls
     `chatApi.patchSession("rec-1", { archived: true })` and moves the
     recording into the Archived group after the ["sessions"] invalidation
     refetches.

### Acceptance

- `uv run pytest packages/ui/backend/tests/test_session_api.py -q` green
  (plus one manual `GET /chat` round-trip assertion).
- `npx vitest run src/components/gm/SessionRecorder.test.tsx` green.
- Layer check clean (`python scripts/check_layer_dependencies.py`) — no new
  imports across layers.

---

## A4 · Live verification pass (manual, then record)

**Goal:** the plan marks P1.1–P2.3 SHIPPED but they were never exercised
together (`FORGE_EXPANSION.md:261`). Run `GM_ASSISTANT_MODE_PLAN.md` §8's
7-step pass and record it.

### Prereqs

```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d   # DBs
./dev.sh                                                            # backend + frontend
```

Use a populated universe, e.g. Fallout `b492380f-9f7e-4deb-b4fd-ba51f2a91c8a`
or VtM `7c737c26-7b84-4704-9ff6-4fc19492eac4` (real canon, ~580-980 entities).

### The 7-step pass (from the mode plan §8)

1. `/gm` → select the universe → **New recording**.
2. Log an entry consistent with canon → participant/location chips appear; no
   alert.
3. Log an entry contradicting an established fact (e.g. in VtM: "the Camarilla
   publicly executes a kindred by sunlight at noon") → amber alert card under
   the entry within a few seconds.
4. Log 2–3 more entries → **Wrap up session** → digest shows recap, canon
   counts, open threads, next-prep teaser.
5. Reload the page → recording shows `wrapped up`; Recap opens instantly from
   the persisted artifact (no LLM spinner).
6. **Archive** the recording → it moves under the "Archived" `<optgroup>`;
   `GET /api/chat` shows `"archived": true`.
7. Dice panel: `2d6+3` → network tab shows `POST /api/gm/roll`; history shows
   server values. Rules panel shows the universe's bound system without
   touching the dropdown; scratchpad notes survive a hard refresh.

### Record (this is the A4 deliverable)

- **`docs/STATUS.md`** — "Live smoke" section: add a dated paragraph
  (2026-11-06, GM Assistant verified pass) with the universe used, the steps
  run, and the observations; note 0 errors.
- **`docs/use-cases/epic-7-copilot-CF/session-support.md`** — refresh the
  status table "Last verified" date.
- **`docs/architecture/GM_ASSISTANT_MODE_PLAN.md`** — tick the P3.1/P3.2/P3.3
  sections with shipped/decided markers (P3.1 decision text from A1; P3.2
  "shipped — hint line"; P3.3 "shipped — archived end-to-end").
- **`docs/architecture/FORGE_EXPANSION.md`** §18 table — rows 18-20 now read
  DONE (2026-11-06), and the "GM plan now fully closed" line at :1184 becomes
  true — add the date.

---

## Global verification (each PR)

```bash
uv run ruff check packages
uv run mypy packages/*/src --cache-dir /tmp/mypy-cache
python scripts/check_layer_dependencies.py
uv run pytest packages/ui/backend/tests/test_session_api.py packages/ui/backend/tests/test_wrap_up.py packages/ui/backend/tests/test_gm_notes.py -q
cd packages/ui/frontend && npx tsc --noEmit && npx vitest run src/app/gm/page.test.tsx src/components/gm/SessionRecorder.test.tsx
```

Full suite before the final PR (A4): `uv run pytest packages tests -q`
(~5–15 min — the hermetic suite, no keys/network).

## Do-not list

- Do **not** build audio capture, CLI `monitor copilot`, or P3.2 option (b)
  (`story_id` threading) — decisions are settled; options (b) reopening is a
  product call, not an implementation one.
- Do **not** touch `tests/verification/**`, `tests/property/**` (sealed).
- Do **not** flip engine defaults (`resolver.py`, `scene_loop.py`, …) — out of
  Phase A scope.
- Do **not** add a dependency (no Tooltip lib; `title` attribute suffices).
