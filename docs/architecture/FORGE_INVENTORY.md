# Forge Mode — Route & Endpoint Inventory

> **Status:** Ground-truth survey, 2026-07-23. Built from `grep`, `Read`, and `git log` only — no live calls. Use this before scoping any F1-1 work; the F1-1 keystone cost is roughly "every referential change below + sidebar updates" so the cost scales with how live the inventory already is.

This document replaces the inline inventory in `FORGE_MODE_PLAN.md §2.1/§2.2`. The plan keeps the **intent** — the bigger refactor and the new IA — but the file:line-level detail now lives here.

---

## 1. Frontend pages

### 1.1 Pages currently under `/forge/*`

| URL | File | Description | Status | Last touched |
|---|---|---|---|---|
| `/forge` | `packages/ui/frontend/src/app/forge/page.tsx` | Hub — overloaded with pack library + pack detail tabs (Packs/Sources/Assets/Profile/Mindscape) + ingest entry + templates + random tables. ~1941 lines. | live (sidebar) | 2026-06-28 |
| `/forge/apply` | `packages/ui/frontend/src/app/forge/apply/page.tsx` | Apply-pack wizard (MP-7/MP-8): target picker → new-world or existing-world, with per-item conflict resolution. Entry: `/forge/apply?pack=<id>`. | live (deep link from hub, no sidebar) | 2026-06-28 |
| `/forge/editor` | `packages/ui/frontend/src/app/forge/editor/page.tsx` | Pack slice editor (MP-4). Header comment falsely claims merge redirects here (see F1-5(d)). | live (deep link from hub, no sidebar) | 2026-06-22 |
| `/forge/review` | `packages/ui/frontend/src/app/forge/review/page.tsx` | Proposal review (I-4) — ingest-scoped: load `?pack=` proposals, grouped by type (entities/axioms/lore/relationships/mechanics), accept/reject + commit to CanonKeeper. | live (deep link from hub, no sidebar) | 2026-06-28 |

### 1.2 Planned pages that don't exist yet

| Planned route | Status | Where it lives today |
|---|---|---|
| `/forge` (Overview dashboard) | planned; current hub moves to `/forge/packs` per F1-1(b) | overloaded hub at `/forge` |
| `/forge/worlds` | missing — plan says MOVE `/worlds` | `/worlds/page.tsx` |
| `/forge/architect` | missing — plan says MOVE `/architect` | `/architect/page.tsx` |
| `/forge/ingest` | missing — plan says EXTRACT from hub | embedded in `/forge` hub (SourcesPanel, AssetsPanel, UploadCard, IngestionJobsList, QuickStartPanel) |
| `/forge/packs` | missing — current hub moves here | `/forge/page.tsx` |
| `/forge/systems` | missing — MOVE `/systems` | `/systems/page.tsx` |
| `/forge/style` | missing — NEW; absorbs ToneTab + LorebookEditor | tone under `/settings/page.tsx:2074-2088`; lorebook only mounted in Play |
| `/forge/templates` | missing — PROMOTE from pack-detail tabs | pack-detail tabs only (`TemplateBrowser.tsx`, `RandomTableEditor.tsx`) |
| `/forge/snapshots` | missing — MOVE `/snapshots` | `/snapshots/page.tsx` |
| `/forge/worlds/new` | missing — planned world-creation wizard (F1-3) | none — five creation paths today |

### 1.3 Sidebar nav (Source: `components/Sidebar.tsx:31-62`)

| Group | Label | href | Mis-homed? |
|---|---|---|---|
| Modes | World Architect | `/architect` | **yes** — should be `/forge/architect` |
| Modes | Play | `/play` | no (explicitly out of Forge) |
| Modes | Characters | `/characters` | no (cross-mode) |
| Modes | GM Assistant | `/gm` | no (explicitly out of Forge) |
| Build | Search | `/search` | no (Query surface) |
| Build | Worlds | `/worlds` | **yes** — should be `/forge/worlds` |
| Build | Explorer | `/explorer` | no (Query surface) |
| Build | Snapshots | `/snapshots` | **yes** — should be `/forge/snapshots` |
| Build | History | `/history` | no (Query surface) |
| Build | World Forge | `/forge` | no |
| Build | Systems | `/systems` | **yes** — should be `/forge/systems` |
| System | Settings | `/settings` | partial — tone belongs in `/forge/style` |

### 1.4 Cross-cutting pages

| URL | File | Status (forge-reachability) |
|---|---|---|
| `/settings` | `app/settings/page.tsx` | live, but contains inline `ToneTab:2074-2088` shadowing the tested `components/settings/ToneTab.tsx` |
| `/universes` | `app/universes/page.tsx` | **dark** — 2-line `redirect("/worlds")` shim, no nav |
| `/prompts` | `app/prompts/page.tsx` | **dark** — client-side `router.replace("/settings")` |
| `/ingest` | — | missing — ingestion lives inside `/forge` hub |
| `/multiverses` | — | missing — managed under `/worlds` (hierarchy tab) |
| `/characters` | `app/characters/page.tsx` | live (cross-mode, stays top-level per plan §3) |
| `/explorer` | `app/explorer/page.tsx` | live (Query surface) |
| `/search` | `app/search/page.tsx` | live (Query surface) |
| `/history` | `app/history/page.tsx` | live (Query surface) |
| `/play` | `app/play/page.tsx` | live (explicitly out of Forge) |
| `/gm` | `app/gm/page.tsx` | live (explicitly out of Forge) |
| `/` | `app/page.tsx` | live (root) — mounts `OnboardingWizard` |

### 1.5 Component-level "dark from Forge"

| Component | File | Currently mounted in | Wanted in (per F1-1/F3-4) |
|---|---|---|---|
| `LorebookEditor` | `components/play/LorebookEditor.tsx:21` | Play only (`CharacterPanel.tsx:333`) | `/forge/style` |
| `CanonReviewPanel` | `components/canon/CanonReviewPanel.tsx:316-349` | Play/GM only | `/forge/review` (already routed, but only ingest scope) |

---

## 2. Backend routers — mounts at a glance

Source: `packages/ui/backend/src/monitor_ui/main.py:256-282`.

| Mount prefix | Router file | Endpoint count | Notes |
|---|---|---|---|
| `/api/chat` | `chat.py` | 38 | owns sessions + wrap-up |
| `/api/modes` | `modes.py` | 3 | live |
| `/api/ingest` | `ingest.py` (re-includes `pack_library`) | 22 | ingest surfaces; `pack_library` ALSO mounted at `/api/ingest` (duplicate registration, `main.py:268`) |
| `/api/llm` | `llm_mgmt.py` | — | live |
| `/api/databases` | `databases.py` | — | live |
| `/api/entities` | `entities.py` | large | character + entity + system + generation + save-template |
| `/api/search` | `search.py` | — | live |
| `/api/universes` | `universes.py` | 14 | **double-prefix issue — see §3.1** |
| `/api/graph` | `graph.py` | — | live |
| `/api/prompts` | `prompts.py` | — | live |
| `/api` (game-systems) | `game_systems.py` | — | live |
| `/api` (performance) | `performance.py` | — | live |
| `/api/ingest` (pack-library) | `pack_library.py` | 11 | merged with ingest mount |
| `/api` (random-tables) | `random_tables.py` | 6 | live |
| `/api/tone` | `tone.py` | — | profiles wired; libraries read-only; tags dark |
| `/api/stories` | `stories.py` (+ `scenes_router`) | — | live |
| `/api/forge` | `forge.py` | — | live |
| `/api` (templates) | `templates.py` | 5 | live (EntityTemplate CRUD) |
| `/api` (gm-tools) | `gm_tools.py` | — | shipped P1.x + P2.x |
| `/api` (lorebook) | `lorebook.py` | 9 | live (Play-only mount) |
| `/api/canon-review` | `canon_review.py` | 4 | partial — by-ingest dark |
| `/jobs` (ingestion-jobs tag) | `jobs_health.py` | 1 | dark — `/jobs/health` has no caller |
| `/api/parties` | `parties.py` | 5 | **dark** — zero callers |
| `/api` (change-log) | `change_log.py` | 1 | live |
| `/api/play-sessions` | `play_sessions.py` | — | live |
| `/api` (gm-notes) | `gm_notes.py` | 2 | **shipped P2.3** (just landed) |

Helper modules (no `APIRouter`, no independent mount): `character_cards.py`, `character_conversation.py`, `character_resolution.py`, `character_storage.py` — used inline by `entities.py`.

---

## 3. Critical findings (must-fix before F1-1)

### 3.1 Universes: BROKEN endpoints from double-prefix mismatch

**Symptom:** Frontend wrappers in `api.ts:918-963` emit `/api/universes/{id}/seed`, `/api/universes/{id}/snapshots`, etc. — but the backend router (`universes.py`) is mounted at `/api/universes` and its routes repeat the segment: `/api/universes/universes/{id}/seed`. So every frontend call to seed/snapshot/active/restore/etc. goes to `/api/universes/{id}/...` which is **404** (no such route).

Affected endpoints (from `routers/universes.py`):

| Method | Actual route | Decorator line | Wrapper bug |
|---|---|---|---|
| POST | `/api/universes/universes/{id}/seed` | 346 | `api.ts:918` emits `/api/universes/{id}/seed` |
| POST | `/api/universes/universes/{id}/snapshots` | 418 | `api.ts:937` emits `/api/universes/{id}/snapshots` |
| GET | `/api/universes/universes/{id}/snapshots` | 453 | `api.ts:943` emits `/api/universes/{id}/snapshots` |
| DELETE | `/api/universes/universes/{id}/snapshots/{sid}` | 489 | `api.ts:952` emits `/api/universes/{id}/snapshots/{sid}` |
| POST | `/api/universes/universes/{id}/snapshots/{sid}/restore` | 504 | `api.ts:946` emits same path |
| GET | `/api/universes/universes/{id}/snapshots/compare` | 533 | `api.ts:955` emits same path |

**Decision:** the wrappers are wrong. The backend route is the canonical mount; the wrappers need to add the second `/universes` segment. (Or, equivalently, the backend route should drop the second `universes` from its path — but the existing route has it, leave it.) Fix at `api.ts:918-963` (six wrapper functions).

### 3.2 Universes: `seed` endpoint is BROKEN at runtime

**File:** `packages/ui/backend/src/monitor_ui/routers/universes.py:346-365`

```python
@router.post("/universes/{universe_id}/seed")  # line 346
async def seed_universe(...):                    # line 347
    import asyncio                               # line 354
    ...
    architect = await _run_in_thread(...WorldArchitect, ...)  # OK
    result = asyncio.run(architect.run(...))     # line 363 — RAISES RuntimeError
```

`asyncio.run()` inside an async endpoint running under uvicorn's loop raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. The fix is to `await` the coroutine, not call `asyncio.run()`. The plan has this as F1-5(b); the line is 363, not 354 (the agent's intermediate note had the wrong line for the actual call).

**Fix:** replace `asyncio.run(...)` with `await ...` and resolve the import.

### 3.3 Universes: `activate` is a documented no-op

**File:** `packages/ui/backend/src/monitor_ui/routers/universes.py:294-304`

```python
@router.post("/universes/{universe_id}/activate")
async def activate_universe(universe_id: str, ...) -> UniverseResponse:
    """
    No DB-level active-universe concept. This endpoint exists for API
    symmetry but performs no work — it just reads the universe and
    returns it with is_active: true added to the response.
    """
```

F1-5(c) — remove the endpoint, update any client docs.

### 3.4 Pack library: duplicate `include_router` in `main.py`

`main.py:268` mounts `pack_library.router` at `/api/ingest` and `main.py:259` mounts `ingest.router` (which itself includes `pack_library` at `ingest.py:1758`). Both mounts work but the same routes are reachable through two paths. F1-1 should consolidate.

### 3.5 Dark endpoints mass

These endpoints have no frontend caller in `api.ts` AND no production `.tsx` call site (grep-verified). Each is a candidate for **remove** unless it's a public API contract:

| Method | URL | File:line | Why dark |
|---|---|---|---|
| GET | `/api/ingest/kgs` | `pack_library.py:1347` | legacy KG proxy; no caller |
| POST | `/api/ingest/kgs` | `pack_library.py:1356` | legacy stub; no caller |
| GET | `/api/ingest/sources/{id}` | `ingest.py:699` | wrapper exists, no .tsx caller |
| POST | `/api/ingest/cache/clear` | `ingest.py:1284` | unwrapped |
| GET | `/api/ingest/jobs/{id}` | `ingest.py:1414` | wrapper exists, no .tsx caller |
| GET | `/api/ingest/jobs/{id}/attempts` | `ingest.py:1424` | wrapper exists, no .tsx caller |
| GET | `/api/ingest/assets/{id}` | `ingest.py:1654` | wrapper exists, no .tsx caller |
| POST | `/api/ingest/assets/{id}/replace` | `ingest.py:1710` | wrapper exists, no .tsx caller |
| DELETE | `/api/universes/multiverses/{id}` | `universes.py:209` | wrapper exists, no .tsx caller |
| GET | `/api/universes/universes/{id}/state` | `universes.py:244` | unwrapped |
| PUT | `/api/universes/universes/{id}` | `universes.py:268` | wrapper exists, no .tsx caller |
| POST | `/api/universes/universes/{id}/activate` | `universes.py:294` | no-op (see §3.3) |
| POST | `/api/universes/universes/{id}/seed` | `universes.py:346` | broken (see §3.2) |
| POST | `/api/parties` | `parties.py:40` | zero callers |
| GET | `/api/parties` | `parties.py:63` | zero callers |
| POST | `/api/parties/{id}/members` | `parties.py:85` | zero callers |
| DELETE | `/api/parties/{id}/members/{eid}` | `parties.py:107` | zero callers |
| POST | `/api/parties/{id}/active-pc` | `parties.py:127` | zero callers |
| GET | `/api/lorebook/entries/by-tags` | `lorebook.py:47` | unwrapped |
| GET | `/api/lorebook/entries/{id}` | `lorebook.py:74` | unwrapped |
| POST | `/api/lorebook/inject` | `lorebook.py:121` | unwrapped |
| GET | `/api/lorebook/top` | `lorebook.py:142` | unwrapped |
| GET | `/api/random-tables/{id}` | `random_tables.py:101` | wrapper exists, no .tsx caller |
| POST | `/api/random-tables` | `random_tables.py:152` | wrapper exists, no .tsx caller |
| GET | `/api/jobs/health` | `jobs_health.py:83` | zero callers — F1-2(b) wires this |
| GET | `/api/canon-review/by-ingest/{id}` | `canon_review.py:202` | zero callers — F1-4(a) wires this |
| — | `/api/entities/{id}/save-template` | `entities.py:1194` | "saves" a Neo4j `EntityTemplate` (NPC), not a portable persona — misnamed. No `api.ts` wrapper. |
| POST | `/api/tone/tags` (and `/tags/suggest`) | `tone.py:232-293` | fully dark — F3-4(b) wires |
| (CRUD) | `EntityTemplate` create/update | `templates.py:42-91` | wired backend, missing frontend UI (F3-2) |

### 3.6 The `/api/ingest` prefix collision

`/api/ingest` is mounted twice: `main.py:259` (ingest.py) and `main.py:269` (pack_library.py). The `pack_library` routes are also independently included inside `ingest.py:1758`. Two paths for the same routes; ambiguous which one wins. F1-1 should pick one.

---

## 4. Snapshot — what's live vs dark vs broken

Of the ~80 endpoints reachable via `/api/...` for Forge-relevant functionality:

- **LIVE** (frontend caller + .tsx call site): ~55
- **DARK** (no frontend caller; backend wired): ~25
- **BROKEN** (frontend wired but 404 due to prefix mismatch, or runtime error): ~6 (5 snapshots + seed)

The 6 BROKEN endpoints are all in `universes.py` and all in active pages (`/snapshots`, `/worlds`). These are **latent user-visible bugs**, not just dark.

---

## 5. What F1-5 actually is

The plan's "F1-5 — fix the duplicated and the dark" is concretely:

- **F1-5(a)** dedupe ToneTab (delete inline at `settings/page.tsx:2074-2088`, render the tested `components/settings/ToneTab.tsx`).
- **F1-5(b)** remove `asyncio.run` bug at `universes.py:363` (replace with `await`).
- **F1-5(c)** remove the `activate` no-op at `universes.py:294-304`.
- **F1-5(d)** fix the stale "merge redirects here" comment in `forge/editor/page.tsx` header.
- **F1-5(e)** *new from this inventory:* fix the 6 snapshot/seed BROKEN endpoints (api.ts:918-963 wrapper prefix mismatch).

That's a 1-2 day PR, all in `universes.py` + `api.ts` + `settings/page.tsx` + `forge/editor/page.tsx`. No new files.

---

## 6. What F1-1 will cost

The keystone (move /forge-style pages under `/forge` route group) touches:

- **Sidebar:** 4 relabeled hrefs (`/architect`, `/worlds`, `/snapshots`, `/systems` → `/forge/architect`, `/forge/worlds`, `/forge/snapshots`, `/forge/systems`).
- **Page files:** 4 moves (`/architect/page.tsx` → `/forge/architect/page.tsx`, same for the other three). Each move requires updating the `react-query` cache keys and any absolute navigation imports.
- **Routers:** 0 changes — all four already share backend prefixes that don't begin with `/forge`, and the `main.py:include_router` lines for them are already at `/api/...` (not `/api/forge/...`). F1-1 is purely a frontend move.
- **Hub split:** `/forge/page.tsx` (1941 lines) needs to be split into `/forge/packs/page.tsx` (current pack-library + pack-detail tabs) and `/forge/page.tsx` (dashboard). The dashboard is a new page; the pack tab is the existing hub minus the dashboard bits.
- **Inline ToneTab:** `settings/page.tsx:2074-2088` needs to be lifted into a shared component (refactor, not removal).

**Estimated:** 1 week for F1-1 honest, 1.5 weeks if the dashboard UX is shaped from scratch rather than stubbed.

---

## 7. Adjacent gaps that block Forge items

### G-6 — Portable character templates (P&F §6)
- **Plan:** Inventory (template authoring) → Phase 1 (formal `CharacterTemplate` schema, additive fields on `characters` collection) → Phase 2 (extend `_seed_answers_from_persona` + `CharacterEditor.tsx` with `backstory_beats` and `voice`) → Phase 3 (`TemplateAnswerDraftingModule` LIGHT in `packages/agents/src/monitor_agents/character_creator/character_creation.py`).
- **Current state:** ~25% complete. The `characters` collection shape exists; `_seed_answers_from_persona` only emits 4 fields (no `backstory_beats`/`voice`); `CharacterEditor.tsx` has no template fields; no `CharacterTemplate` schema; no `TemplateAnswerDraftingModule`. The `save-template` endpoint at `entities.py:1194` writes a Neo4j `EntityTemplate` (the NPC path), not a portable persona — misnamed.
- **What works:** `CharacterSheetCreate.source_persona_id` (the Session Zero bridge), persona import/export via `entities.py:1086-1115` (SillyTavern chara_card_v2).
- **Blocks:** F3-2 (template authoring UI) — the plan defers character templates to G-6.

### F3-2 — Template authoring UI
- **Plan:** Create/edit forms for `EntityTemplate` in `/forge/templates`; random tables in the same section.
- **Current state:** ~20% complete. Backend `EntityTemplate` CRUD is fully wired (`templates.py:42-91`). `templatesApi` exposes `create`/`update`/`delete` (`api.ts:1174-1211`). Frontend `TemplateBrowser.tsx` only lists and deletes; no Create button, no edit form, no instantiate preview. `RandomTableEditor.tsx` exists; mounted as `RandomTableBrowser` in the `tables` tab, not the templates section.
- **Ready to ship in a focused PR:** (a) only — frontend create/edit form + generation preview. Backend is ready.

### F1-6 — Reconcile the two pack-apply paths
- The plan says "two paths" but the inventory shows clearly: `forge/apply/page.tsx` is the wizard, and `forge/page.tsx` has a `handleApply`/`UsePack` button that links to the wizard. The two paths are (1) Apply via the wizard, (2) Apply via the hub's "Apply" button. Both go to the same backend endpoints.
- **Decision: probably not a code conflict — it's a UX framing.** F1-6 is small: pick one entry point per pack (the wizard) and remove the hub's direct-Apply button. 1-2 days.

---
