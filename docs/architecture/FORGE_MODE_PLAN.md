# Forge Mode Plan

> **Status:** proposed (2026-07-23). Every inventory claim below was verified by
> direct code inspection on 2026-07-23 (page-by-page reads plus frontend↔backend
> call-site greps); re-verify before implementing each item. Builds on
> [PLAY_AND_FORGE_DIRECTION.md](PLAY_AND_FORGE_DIRECTION.md) §4 (Forge/Play split —
> shipped as route groups, minimal as a *mode*) and
> [docs/1_product/vision_and_modes.md](../1_product/vision_and_modes.md) (World
> Design mode = "Architect"). Sibling plans: [GAP_REMEDIATION_PLAN.md](GAP_REMEDIATION_PLAN.md)
> (G-6 character templates, G-9 CanonKeeper depth — cross-referenced, not duplicated).
>
> **Companion docs:**
> - [`FORGE_INVENTORY.md`](FORGE_INVENTORY.md) — file:line-level map of every Forge page, every router mount, every endpoint, the 6 BROKEN endpoints, and the F1-5 scope.
> - [`FORGE_EXPANSION.md`](FORGE_EXPANSION.md) — Tier 3 exploration notes (F1-6, F2-1, F2-2). Drop-in plan-section updates for each.
>
> **2026-07-23 audit deltas (see Expansion §1-§18):**
> - **F1-6** is now bigger than the plan said: the wizard's conflict-resolution step is dead UX (backend always returns `conflicts: []` at `pack_library.py:1304`). MP-7/MP-8 is silently broken. Plus collapse the redundant PackLibrary direct-Apply path.
> - **F2-1** is now M-L (was M): eight coverage dimensions, half of them need new loader plumbing (relationships, mechanics, random tables).
> - **F2-2** is now L (was M-L): nine distinct gaps, including "no router endpoints for Fact/Axiom/Event CRUD" — Neo4j tools exist but no UI exposes them.
> - **F2-3** is now M (was S-M): `CanonReviewPanel` has a bug where the user's reason input is dropped (`CanonReviewPanel.tsx:309-345`). F1-4 has 4 lifecycle bugs that block F2-3.
> - **F2-4** is now S-M (was S): the contract is broken — `_job_to_dict` drops `pack_id`, `total_attempts`, `failed_sections`; `last_error` is now structured but typed as string; SSE updates that don't change progress are silently discarded.
> - **F3-4** is now M (was S-M): ToneTab inline vs component is functionally identical (zero diff). The plan's S-M estimate undercounts F3-4.3 (tag definitions) as the bulk.
> - **F3-2** is now M (was S-M): backend full CRUD, frontend only list/delete. `InstantiateEntityRequest` schema exists but is unused. `usage_count` never increments. RandomTable create button missing. No backend tests.
> - **F3-3** is now M (was M): Multiverse router exposes only 3 endpoints. No update/move/archive. The list endpoint returns a reduced shape that drops `system_name`, `is_template`. Stale `/forge/apply` copy.
> - **F1-3** is now M (was M): 5 paths confirmed. `QuickWorldBuilder` is the shared primitive. Zero test coverage for any creation endpoint. Plan's "Backend: none" understates the test gap.
> - **F1-2** is now M/S-M (was M): pending-proposals card is N+1 (no global endpoint). `/api/jobs/health` drops 6/13 statuses. Dashboard links to packs/reviews unreliable until F2-4/F1-4 fix.
> - **F3-1** is now M (was M): merge/clone/slice/export/import all shipped. F3-1 is polish + correctness (dry-run preview, lineage display, export/import envelope fix, slice UI 3/10 collections).
> - **P3.2** is now S hint-line (was "decide: M if built"): option (a) recommended. Option (b) is more than 3 one-line changes (pipeline has no story context; story queue ignores proposals without scene_id).
>
> Conventions: DSPy modules are co-located with their respective agents; MCP calls async; `structlog` (no
> print); pydantic v2; line-length 100; mypy strict; layer rules — UI backend
> routers (Layer 3) call data-layer tools directly and drive agents
> (`monitor_agents`) for LLM work; **only CanonKeeper writes Neo4j**; frontend
> never imports backend internals. Frontend: Next.js App Router + react-query +
> vitest/testing-library (happy-dom pragma per test file, config
> `packages/ui/frontend/vitest.config.ts`). Backend tests: flat
> `packages/ui/backend/tests/test_*.py`, one file per router/feature. Agent tests:
> `FakeMCPClient`/`FakeLLMClient` (`tests/conftest.py:165,261`). Every commit
> references a use-case ID — CI-enforced (`scripts/check_commit_use_case.py`,
> `scripts/require_tests_for_code_changes.py`).

---

## 1. Product Definition

### 1.1 What "Forge" is

**The idea in plain terms.** Forge is the **authoring studio** — everything
about *creating and curating* a world, cleanly separated from *playing* in it
(the way SillyTavern separates card/lorebook editing from chat). Today,
building a world means CLI commands and half-wired pages; Forge makes it one
coherent place where you:

1. **Create a world** — from scratch via a wizard, or by ingesting content:
   drop in a PDF rulebook, a wiki export, your campaign notes. The pipeline
   extracts axioms, entities, lore, and rules into a knowledge pack, with
   visibility into what was extracted and what failed.
2. **Curate it** — browse and edit the ontology: entities (NPCs, places,
   items), facts, relationships, game-system rules. Review every proposed
   change before it becomes canon (the CanonKeeper gate) from one triage queue.
3. **Shape the experience** — set tone and style, author character templates,
   define how the world should feel in play.
4. **Package and version it** — compose packs (merge, slice, clone, export),
   snapshot a world, or fork it at a point in history to explore "what if this
   went differently".

Then when you hit Play, none of that authoring machinery is in your way — and
when you're in Forge, nothing about play sessions clutters the authoring view.

Forge is MONITOR's **authoring surface** — the World Design mode
(`vision_and_modes.md:22-27`, "World Architect"). It is where a user creates,
stocks, curates, and maintains fictional worlds *before and between* play
sessions. The Forge/Play split already exists as route groups (P&F §4, shipped);
this plan turns the scattered authoring pages into **one coherent mode** with a
single information architecture, no dark endpoints, and no duplicated flows.

The authoring workflows Forge must cover end-to-end:

1. **Create a world from scratch** — blank universe, one-sentence quick seed
   (`forge.py:373` quick-world), conversational building (WorldBuildingLoop), or
   the curated demo (`forge.py:180`). Use cases M-1…M-8.
2. **Import / ingest content** — upload PDFs and documents, watch extraction
   jobs, curate the resulting knowledge pack. Use cases I-1…I-16.
3. **Curate ontology & entities** — entities, axioms, lore, relationships,
   archetypes (EntityTemplates), random tables, game systems. Use cases
   M-12…M-25, M-32, M-33, RS-*.
4. **Review canon proposals** — accept/reject/commit `ProposedChange`s from
   ingestion and play sessions; CanonKeeper remains the only Neo4j writer.
   Use cases I-4, CF-8 (review half).
5. **Compose & share packs** — create, merge, slice, clone, export/import,
   apply to new or existing worlds with conflict resolution. Use cases MP-1…MP-9.
6. **Manage tone & style** — tone profiles/libraries, tag definitions,
   lorebook entries.
7. **Snapshot & fork** — world state history, restore, compare, fork.
   Use cases M-34, M-35.

### 1.2 Who uses it

- **The world author** building a setting from scratch or from source books.
- **The GM** preparing a campaign: ingesting a rulebook, curating the pack,
  applying it to a world, reviewing what play sessions added to canon.
- Same person as the player, different *hat* — Forge is write-heavy, Play is
  read-mostly (P&F §4). One web app, two route groups; the separate-deployables
  question stays open and is explicitly **not** decided here.

### 1.3 Non-goals

- **Forge is not Play.** No turn loop, no dice, no session-zero, no narration.
  Play surfaces (`/play`, PlayConsole) are untouched except where they mount
  shared components (CanonReviewPanel, LorebookEditor).
- **Forge is not the GM Assistant.** Live table support (session recorder,
  hooks, contradictions) stays at `/gm` (G-5 in GAP_REMEDIATION_PLAN).
- **No new agent layer.** WorldBuildingLoop/WorldArchitect already exist; Forge
  consumes them. New LLM behavior, if any, goes through `monitor_agents` —
  never direct LLM calls in routers.
- **No mode gating.** The `modes.py` active-mode switch is cosmetic by design
  (in-memory `_ACTIVE`, `modes.py:81-87`; `ModeSwitcher.tsx` is a plain select
  with zero UI effect). Forge mode is *navigational* (route group + section
  nav), not a permission/state system. Decision: keep it that way.
- **CLI parity is out of scope.** `monitor manage`/`monitor universe` already
  exist (`packages/cli/src/monitor_cli/main.py:61-62`); no new CLI surface.

---

## 2. Current-State Inventory (verified 2026-07-23)

> **Detail doc:** [`FORGE_INVENTORY.md`](FORGE_INVENTORY.md) — single-page map of every Forge page, every router mount, every endpoint, and every dark/broken caller. Read this before scoping F1-1 / F1-5. The summary tables in §2.1/§2.2 below are the high-level view; the inventory doc has the file:line-level detail.

### 2.1 Frontend surfaces

Status: **works** (complete, wired) · **partial** (functional but incomplete
or mis-homed) · **dark** (no caller / unreachable) · **broken** (would fail at
runtime).

| Surface | File | What it is | Status |
|---|---|---|---|
| `/architect` | `app/architect/page.tsx:343` (creates chat sessions `mode="world_architect"`), MiniGraph poll `:102-111`, coverage panel `:365-384` | Conversational world building via WorldBuildingLoop | **works** — mis-homed (top-level, not under `/forge`) |
| `/forge` hub | `app/forge/page.tsx` (1941 lines); Packs/Sources/Assets mode bar `:884`; pack detail tabs via `FORGE_TABS` (`lib/forge.ts:28-36`) rendered `:1585-1614`; metadata chips I-10/I-11 `:779-871` | Pack library + pack editor + ingest entry | **works** — overloaded (hub + packs + ingest + assets in one page) |
| `/forge/apply` | `app/forge/apply/page.tsx:243,335,490` | Apply-pack wizard, conflict resolution (MP-7/MP-8) | **works** |
| `/forge/editor` | `app/forge/editor/page.tsx:227` | Pack slice → new pack (MP-6) | **partial** — slice only; header comment `:6-13` falsely claims merge redirects here |
| `/forge/review` | `app/forge/review/page.tsx:253-318` | Ingest-scoped proposal review + commit (I-4) | **works** — covers only pack proposals, not scene/story queues |
| `/worlds` | `app/worlds/page.tsx:72-76` | 3 tabs: graph, hierarchy (create multiverse/universe `:302,363`), entities/NPC grid `:584` | **works** — mis-homed |
| `/snapshots` | `app/snapshots/page.tsx:65-122` | Snapshot create/restore/delete/compare + fork (M-34/M-35) | **works** — mis-homed; minor wart `setState` during render `:45-61` |
| `/systems` | `app/systems/page.tsx` | Game-system library, test rolls (RS-*) | **works** — read-mostly; creation via ingest only |
| `/characters` | `app/characters/page.tsx:36-467` | Standalone-character roster, draft/expand, card import/export, versions | **works** — wart: incarnation add needs a raw UUID `:393` |
| `/explorer` | `app/explorer/page.tsx:114-210` | Q-11 graph drill-down; on-canvas entity/relationship create, batch delete | **works** |
| Tone management | `app/settings/page.tsx:2074-2088` (local inline `ToneTab`) | Tone profile CRUD | **partial** — duplicate implementations; component file orphaned (§2.3) |
| Lorebook editor | `components/play/LorebookEditor.tsx:21` | Lorebook CRUD via `lorebookApi` | **works** — mounted only in Play (`CharacterPanel.tsx:333` → `PlayConsole.tsx:647`), unreachable from Forge |
| Canon review panel | `components/canon/CanonReviewPanel.tsx:316-349` | Story/scene canon queue + verdicts (CF-8) | **works** — mounted only in Play/GM (`PlayConsole.tsx:670`, `SessionRecorder.tsx:306`), unreachable from Forge |
| Quick Start | `components/forge/ingest/QuickStartPanel.tsx:153` | One-sentence world seed via `forgeApi.quickWorld` | **works** |
| Pack batch ops | `components/forge/ingest/PackLibrary.tsx:597-638` | Merge/Export/Clone/Slice batch bar; apply via `canonizePack` `:83` | **works** — second, conflicting apply path (§2.3) |
| Ingestion jobs | `components/forge/ingest/IngestionJobsList.tsx:66-148` | Poll + per-job SSE stream (`ingestApi.streamJob` `:76`), cancel/delete/retry `:177-217` | **works** |
| Demo world | `components/play/OnboardingWizard.tsx:21` | `forgeApi.demoWorld` | **works** |
| Template browser | `components/forge/TemplateBrowser.tsx:207,212` | List/delete EntityTemplates; instantiate via `TemplateInstantiator.tsx:34` → `entities.py:902 /generate` | **partial** — no create/edit UI (M-32 half-met) |
| Random tables | `components/forge/RandomTableEditor.tsx` | Full CRUD + roll (M-33) | **works** — buried as a pack-detail tab |

### 2.2 Backend routers (Forge-relevant; mounts at `main.py:254-279`)

| Router | Prefix | Endpoints | Status |
|---|---|---|---|
| `pack_library.py` | `/api/ingest` | packs CRUD `:141-934`, promote `:355`, item patch `:450-608`, merge `:710`, canonize `:839`, export `:959`, import `:988`, clone `:1080`, slice `:1143`, apply new/existing `:1199,:1255`, proposals `:1406-1541`, commit `:1595` | **works** — heavily used by `/forge` pages |
| `canon_review.py` | `/api` | scene queue `:103`, story queue `:144`, **by-ingest `:202`**, verdicts `:259`, accept/reject `:294,:319` | **partial** — by-ingest is **dark** (no frontend caller); rest wired via CanonReviewPanel (Play/GM only) |
| `forge.py` | `/api/forge` | demo-world `:180`, quick-world `:373` | **works** |
| `universes.py` | `/api/universes` | multiverses `:170-201`, universes CRUD `:214-276`, **activate `:286`**, **seed `:338`**, fork `:376`, snapshots `:409-524` | **partial** — activate dark (and a documented no-op, `:288-289`); seed dark **and broken** (`asyncio.run()` inside an async endpoint, `:354` — raises `RuntimeError` under uvicorn; no test covers it) |
| `entities.py` | `/api/entities` | NPCs `:458-476`, systems `:546-862`, generate `:902`, characters `:1054-1313`, **save-template `:1169`** | **partial** — save-template **dark** (no `api.ts` wrapper at all); owned by G-6 |
| `ingest.py` | `/api/ingest` | sources `:660-984`, jobs `:1174-1452` (incl. SSE stream `:1452`), assets `:1520-1706` | **works** |
| `tone.py` | `/api/tone` | profiles `:70-136`, libraries `:154-214`, tags `:232-293` | **partial** — profiles wired; libraries read-only in UI; tags dark |
| `lorebook.py` | `/api` | entries/bulk/inject/stats `:45-146` | **works** — only from Play surface |
| `templates.py` | `/api` | EntityTemplate CRUD `:42-91` | **partial** — list/delete/instantiate wired; create/edit dark |
| `random_tables.py` | `/api` | CRUD + roll `:72-244` | **works** |
| `jobs_health.py` | `/api` | `/jobs/health` `:86` | **dark** — zero frontend references |
| `universes` legacy | — | `app/universes/page.tsx` = 2-line `redirect("/worlds")` | the redirect-shim pattern to reuse |
| `modes.py` | `/api/modes` | list/active `:95-105` | works, cosmetic only (§1.3) |

### 2.3 Structural problems this plan fixes

1. **Forge is not one place.** Authoring lives across 7+ top-level routes
   (`/architect`, `/forge`, `/worlds`, `/snapshots`, `/systems`, `/characters`,
   `/explorer`, plus tone under `/settings`). The sidebar groups them loosely
   ("Modes"/"Build", `Sidebar.tsx:31-62`) but nothing reads as a mode.
2. **Two parallel pack-apply flows.** `PackLibrary.tsx:83` (`canonizePack`) vs
   the `/forge/apply` wizard (`applyPackNewWorld`/`applyPackExistingWorld`).
   Different UX, different conflict handling — only the wizard handles
   conflicts (`apply/page.tsx:53-63`).
3. **Two parallel canon-review surfaces.** `/forge/review` (ingest-scoped,
   `pack_library.py:1406-1595`) vs `CanonReviewPanel` (scene/story-scoped,
   `canon_review.py:103,144`). The backend's bridging endpoint
   `canon_review.py:202` (by-ingest) is dark, and the scene/story panel is
   unreachable from Forge.
4. **Duplicate `ToneTab`.** `app/settings/page.tsx:2074-2088` defines a local
   `ToneTab` and renders it, shadowing `components/settings/ToneTab.tsx` —
   which is the one with the test (`ToneTab.test.tsx`). The two implementations
   have diverged; exactly which features differ must be diffed before merging
   (F1-5a).
5. **Dark/broken endpoints** (table above): `by-ingest`, `jobs/health`,
   `activate` (no-op), `seed` (broken `asyncio.run`), `save-template` (G-6's),
   template create/edit, tone tags.

   **Critical from `FORGE_INVENTORY.md §3`:** the snapshot endpoints (5 of them
   at `universes.py:418,453,489,504,533`) are **BROKEN, not dark** — they work
   server-side but the frontend wrappers in `api.ts:918-963` emit
   `/api/universes/{id}/...` while the backend routes include a second
   `/universes` segment, so every call returns 404. Same pattern for
   `seed` (with the additional `asyncio.run()` runtime bug at
   `universes.py:363`). Fix is six wrappers in `api.ts` + the `await` swap at
   `universes.py:363`. These are **latent user-visible bugs** — the
   `/snapshots` page works in the UI but every save/restore/compare call
   404s. **This is the highest-priority F1-5 work.**
6. **No unified world-creation entry.** Five creation paths (blank form at
   `/worlds`, QuickStartPanel seed, demo-world onboarding, pack→new-world
   wizard, fork at `/snapshots`) with no common front door.

### 2.4 The agent layer (what Forge can build on)

- **WorldBuildingLoop** (`packages/agents/src/monitor_agents/loops/world_building_loop.py:218-280`)
  — 3-node LangGraph (`load_world_context → process_user_input →
  format_response`, `:197-210`). Driven **only** by chat sessions with
  `mode="world_architect"`: session bootstrap `chat.py:398-466`, per-turn
  `chat_loops.py:1116-1140`. Returns `world_profile`, `coverage_summary`,
  `known_open_questions`, `priority_gaps` (`:270-279`) — all already carried in
  GM-message metadata and rendered raw by the architect page
  (`architect/page.tsx:365-384`).
- **WorldArchitect** (`world_architect.py`) — DSPy extraction + auto-commit via
  CanonKeeper (`:14-16`, `:150`); deterministic world profile + priority gaps
  (`:102-118`); `suggest_next` (`:170`); `seed_universe` (`:219`, currently
  reachable only through the broken endpoint).
- **No gap in agent capability for Phase 1–2** — the missing part is UI
  consumption (gap-checklist affordances, seed wiring), not new agents.

---

## 3. Target Information Architecture

One route group, section-nav via a Forge layout. Existing routes become
redirect shims (pattern: `app/universes/page.tsx`).

| Section | Route | Contents | Source |
|---|---|---|---|
| **Overview** | `/forge` | Dashboard: worlds, packs, pending reviews, active jobs, pipeline health, quick actions | NEW (current hub moves to `/forge/packs`) |
| **Worlds** | `/forge/worlds` | Hierarchy (multiverse/universe CRUD), entities tab, world graph | MOVE `/worlds` |
| **Architect** | `/forge/architect` | Conversational building + coverage/gaps workbench | MOVE `/architect` |
| **Ingest Studio** | `/forge/ingest` | Upload, sources, assets, jobs (SSE), Quick Start | EXTRACT from hub (`SourcesPanel`, `AssetsPanel`, `UploadCard`, `IngestionJobsList`, `QuickStartPanel`) |
| **Packs** | `/forge/packs` | Pack library + detail tabs + batch ops; apply/editor stay nested | MOVE current `/forge` hub; `/forge/apply`, `/forge/editor` unchanged |
| **Canon Review** | `/forge/review` | Unified queues: ingest jobs (by-ingest), pack proposals, scene/story | EXTEND current page |
| **Systems** | `/forge/systems` | Game systems, test rolls | MOVE `/systems` |
| **Style** | `/forge/style` | Tone profiles/libraries/tags + lorebook management | NEW (absorbs ToneTab; mounts LorebookEditor) |
| **Templates** | `/forge/templates` | EntityTemplates + random tables (also still reachable as pack tabs) | PROMOTE from pack-detail tabs |
| **Snapshots** | `/forge/snapshots` | History, restore, compare, fork | MOVE `/snapshots` |

Sidebar (`Sidebar.tsx:31-62`): "Modes" keeps Play/GM/Characters; the "Build"
group collapses to a single **Forge** entry (plus Search/Explorer/History,
which are read-only canon *query* surfaces — Q-* use cases, not authoring).
`/characters` stays top-level (it is a cross-mode roster, not world authoring).

---

## 4. Phase 1 — Consolidate & Wire

> Goal: everything that exists is discoverable and functional under one Forge
> IA. No new agents, almost no new backend.

### F1-1 · Forge route-group consolidation — effort M — deps: none

- [x] **Track F1-1** — sections live under `/forge/*`, old routes redirect. (DONE 2026-07-24)

**Goal:** the §3 IA becomes real; old routes keep working via redirects.

- **(a)** New `packages/ui/frontend/src/app/forge/layout.tsx` — Forge section
  nav (the 10 sections above), active-section highlight; mirrors the existing
  sidebar idiom (`Sidebar.tsx:157-209`, same `cn`/accent classes).
- **(b)** Moves (git mv + fix imports, all internal links updated):
  - `app/worlds/page.tsx` → `app/forge/worlds/page.tsx` (+ `GraphTab`,
    `NPCDetailPanel`, `HierarchyTab` siblings)
  - `app/architect/` → `app/forge/architect/` (page + `ArchitectMessageBubble.tsx`)
  - `app/snapshots/page.tsx` → `app/forge/snapshots/page.tsx`
  - `app/systems/page.tsx` → `app/forge/systems/page.tsx`
  - Current `app/forge/page.tsx` (1941 lines) → `app/forge/packs/page.tsx`
    unchanged except its default `forgeMode` (`:884`, becomes `"packs"`).
- **(c)** Redirect shims at the four old routes: `redirect("/forge/worlds")`
  etc. — copy the 2-line `app/universes/page.tsx` pattern. Preserve query
  params where they exist (`?universe=`, `?pack=` deep links,
  `forge/page.tsx:942-947`, `worlds/page.tsx:719`).
- **(d)** `Sidebar.tsx:31-62` — regroup: Modes (Play, GM Assistant,
  Characters), Forge (single entry), Query (Search, Explorer, History), System.
- **(e)** Sweep internal `href`/`router.push` references (grep `/worlds`,
  `/architect`, `/snapshots`, `/systems` under `packages/ui/frontend/src`).

**Tests:** vitest: Sidebar group membership test (pattern
`components/WorldPicker.test.tsx`); playwright smoke: each old URL lands on the
new one (e2e config `packages/ui/frontend/playwright.config.ts` already exists).
Use-case IDs: M-3, M-5.

**Risks:** deep links in docs/scripts (`grep -rn "app/forge\|/worlds" docs/
scripts/`) — update after the move; react-query keys unaffected (no data change).

---

### F1-2 · Forge overview dashboard + wire `jobs/health` — effort M — deps: F1-1

- [x] **Track F1-2** — dashboard live; health chip wired. (DONE 2026-07-24)

**Goal:** `/forge` becomes the mode's front door: state of the authoring world
at a glance, one click into every workflow.

- **(a)** New `app/forge/page.tsx` (dashboard): cards for universes
  (`universesApi.listUniverses`, `api.ts`), packs with `review_pending` count
  (logic exists at `forge/page.tsx:917-920` — reuse), active/failed ingestion
  jobs (`ingestApi.listJobs`), pending canon proposals (see (c)), quick
  actions ("New world" → F1-3, "Upload document", "Open Architect").
- **(b)** Wire the dark health endpoint: `GET /api/jobs/health`
  (`jobs_health.py:86`, mounted `main.py:276`). Add `jobsHealthApi` to
  `api.ts`; render a pipeline-health chip on the dashboard and in Ingest
  Studio. Stale/queue-blocked states already have semantics in the jobs router
  (`ingest.py:648` unlock, `test_recover_stale_jobs.py`).
- **(c)** Pending-proposals count: compose from existing endpoints —
  `pack_library.py:1406` list proposals (per pack, status filter) and
  `canon_review.py:144` story queue `total_pending`. **No new backend
  endpoint**; aggregate client-side over the already-fetched lists (packs and
  jobs are on the dashboard anyway). Keep it cheap: counts only on the cards
  that are already loaded.

**Tests:** frontend `app/forge/page.test.tsx` — mocked fetch per
`vitest.config.ts` conventions (pattern `components/settings/ToneTab.test.tsx`),
assert card rendering + health chip states. Backend: none (no new endpoints).
Use-case IDs: I-4, M-5, M-6.

---

### F1-3 · World-creation wizard — effort M — deps: F1-1

- [x] **Track F1-3** — all five creation paths reachable from one wizard. (DONE 2026-07-24)

**Goal:** one front door for all five creation paths, fixing §2.3.6.

- **(a)** New `app/forge/worlds/new/page.tsx` — step 1: method picker (Blank /
  Quick seed / From pack / Fork / Demo). Step 2 embeds the existing flow for
  the chosen method; step 3: confirm + land on the new world
  (`/forge/worlds?universe=<id>` deep link already supported).
  - *Blank* — reuse the hierarchy-tab create form (`worlds/page.tsx:363`,
    `universesApi.createUniverse`; multiverse create `:302`).
  - *Quick seed* — reuse `QuickStartPanel`'s form + `forgeApi.quickWorld`
    (`QuickStartPanel.tsx:153` → `forge.py:373`). Extract the form from the
    panel into `components/forge/worlds/QuickSeedForm.tsx`; QuickStartPanel
    re-exports it so Ingest Studio keeps working.
  - *From pack* — link to `/forge/apply` (wizard already handles target
    selection + conflicts, `apply/page.tsx:243-490`).
  - *Fork* — reuse the fork dialog (`snapshots/page.tsx:121`,
    `universesApi.forkUniverse` → `universes.py:376`).
  - *Demo* — `forgeApi.demoWorld` (`forge.py:180`; idempotent, `reused` flag
    `:177`).
- **(b)** Entry points: "New world" button on `/forge/worlds`, dashboard quick
  action (F1-2), empty-state CTA in Architect.

**Tests:** frontend wizard test (method switch renders the right step; blank
submit calls `createUniverse`). Backend: none. Use-case IDs: M-2, M-4, MP-7,
M-35.

**Explicitly not in the wizard:** the broken `seed` endpoint — see F1-5(b).

---

### F1-4 · Unified Canon Review + wire `by-ingest` — effort M — deps: F1-1

- [x] **Track F1-4** — three review scopes under one page; by-ingest wired. (DONE 2026-07-24, incl. the 5 backend lifecycle corrections from FORGE_EXPANSION §6)

**Goal:** one review surface at `/forge/review` covering all three proposal
sources, fixing §2.3.3.

- **(a)** Extend `app/forge/review/page.tsx` with a source scope switcher:
  1. **Pack proposals** (existing tabs `:46-57`, `ingestApi.listProposals` /
     `reviewProposal` / `batchReview` / `commitAccepted` →
     `pack_library.py:1406-1595`) — unchanged.
  2. **Ingestion jobs** — NEW tab calling the dark
     `GET /api/canon-review/by-ingest/{job_id}` (`canon_review.py:202-251`):
     `canonApi.byIngest(jobId)` in `api.ts`, job picker fed by
     `ingestApi.listJobs`, verdicts via the existing
     `POST /canon-review/verdicts` (`canon_review.py:259`). Deep-link
     `?job=<id>`.
  3. **Story / scene queues** — lift `CanonReviewPanel`
     (`components/canon/CanonReviewPanel.tsx`) into a tab. It already calls
     story queue + scene review + verdicts (`:316-349`); only its *mount
     points* are Play/GM (`PlayConsole.tsx:670`, `SessionRecorder.tsx:306`) —
     mounting it in Forge is additive, those stay.
- **(b)** Cross-link: `IngestionJobsList.tsx:177-217` action column gains
  "Review proposals" → `/forge/review?job=<id>` for completed/partial jobs.
- **(c)** Docstring hygiene: `canon_review.py:1-8` says "CF-8" scene review —
  note the Forge mount in the module docstring when (a) lands.

**Tests:** new `packages/ui/backend/tests/test_canon_review_by_ingest.py`
(pattern `test_tone.py` / `test_universes.py`; `db_op` + tool mocking per
existing router tests): seeds proposals tagged `source=ingestion_job:<uuid>`,
asserts grouping and status filter (`:208-211`). Frontend: tab-switch test +
verdict mutation test on the by-ingest tab. Use-case IDs: I-4, CF-8.

---

### F1-5 · Fix the duplicated and the dark — effort S — deps: none (parallel with F1-1)

- [x] **Track F1-5** — one ToneTab; seed repaired and wired (or removed);
  activate removed; stale comment fixed. (DONE 2026-07-24; seed generation-quality live check still pending infra)

- **(a) Dedupe ToneTab (S).** Delete the inline `ToneTab` in
  `app/settings/page.tsx:2074-2088`; render the shared
  `components/settings/ToneTab.tsx` (the tested one, `ToneTab.test.tsx`) from
  both `/settings` and the new `/forge/style` section (F1-1 layout gives it a
  home; the settings tab becomes a link). Diff the two implementations first —
  port any feature the inline one has that the component lacks into the
  component + its test.
- **(b) `seed_universe` — repair or remove (S).** `universes.py:354` calls
  `asyncio.run(architect.seed_universe(...))` inside an `async def` — this
  raises `RuntimeError` under uvicorn, so the endpoint is **broken**, not just
  dark. It is also the only caller of `WorldArchitect.seed_universe`
  (`world_architect.py:219`). Fix minimally: `await architect.seed_universe(...)`
  (drop `asyncio.run`, drop the `import asyncio` at `:347`). Then wire it as a
  "Seed from tables" action on empty universes in `/forge/worlds`
  (`api.ts:906` wrapper already exists) — it is a genuinely useful
  blank-world onramp (M-33 adjacent). If the wiring shows the generation
  quality is not shippable, remove endpoint + agent method + wrapper instead;
  decide with one live run.
- **(c) `activate_universe` — remove (S).** `universes.py:286-300` is a
  self-documented no-op ("there is no 'active' universe concept at DB level");
  the real mechanism is client-side `useWorldContext` (`WorldPicker.tsx:15,81`).
  Delete the endpoint and the `api.ts:902` wrapper. Cheaper than maintaining a
  lie. (If a server-side active world is ever needed, it belongs in
  `modes.py`'s `ActiveMode`, not here.)
- **(d) `forge/editor` stale comment (S).** Header comment
  `app/forge/editor/page.tsx:6-13` claims merge redirects here; the code is
  slice-only (`:227`). Fix the comment — merge already lives in
  `MergeModal` (`forge/page.tsx:372-498`) and the PackLibrary batch bar
  (`PackLibrary.tsx:597-638`).
- **(e) `save-template` (`entities.py:1169`) — no work here.** Owned by G-6
  Phase 2 (GAP_REMEDIATION_PLAN); noted so the dark-endpoint list is complete.

**Tests:** (b) new happy-path test in `test_universes.py` mocking
`WorldArchitect.seed_universe` (asserts the endpoint awaits and maps the
result; this is the test that would have caught the `asyncio.run` bug);
(c) grep-assert nothing references `activateUniverse`; existing
`test_universes.py` stays green minus any activate case. Use-case IDs: M-33,
M-4.

---

### F1-6 · Reconcile the two pack-apply paths — effort S — deps: F1-1

- [x] **Track F1-6** — single apply flow (the wizard); library Apply deep-links. (DONE 2026-07-24; canonize route retired, script callers migrated)

**Goal:** §2.3.2 — one apply flow. The `/forge/apply` wizard wins (only it
handles conflicts, `apply/page.tsx:53-63`).

- **(a)** `PackLibrary.tsx:83` — replace the inline `canonizePack` apply flow
  with a route to `/forge/apply?pack=<id>`. Keep `canonizePack` the *endpoint*
  (`pack_library.py:839` — used by scripts/e2e) but remove the duplicate UI.
- **(b)** Verify `/forge/apply` honors `?pack=` preselection (the hub's Apply
  button already deep-links, `forge/page.tsx:1492`); add preselect handling if
  missing.
- **(c)** PackLibrary batch bar keeps Merge/Export/Clone/Slice untouched —
  those are pack-ops, not apply.

**Tests:** frontend: PackLibrary "Apply" navigates with the right query param;
`/forge/apply` preselects from `?pack=`. Use-case IDs: MP-7, MP-8.

---

## 5. Phase 2 — Depth

> Goal: turn working surfaces into good workflows. UI depth on top of existing
> agent/backend capability; still no new agents.

### F2-1 · Architect workbench: coverage-driven building — effort M — deps: F1-1

- [x] **Track F2-1** — gap checklist + chips + suggest-next live in the Architect. (DONE 2026-07-24; formal coverage API + workbench panel + gap→prompt chips)

**Goal:** the `/forge/architect` chat stops being a transcript with a raw
metadata dump (`architect/page.tsx:365-384`) and becomes a guided workbench.
All data already flows — WorldBuildingLoop returns `priority_gaps`,
`known_open_questions`, `coverage_summary` (`world_building_loop.py:270-279`),
built deterministically by `build_world_profile`/`build_priority_gaps`
(`world_architect.py:102-118`).

- **(a)** New `components/forge/architect/CoveragePanel.tsx`: priority gaps as
  a checklist (domain → defined/missing), coverage summary, open questions.
  Replaces the raw panel; fed from the same GM-message metadata.
- **(b)** Gap chips: each missing-coverage item renders a chip; clicking it
  pre-fills the Composer (`useChatSession` already exposes the composer path,
  `architect/page.tsx:321`) with "Tell me about the world's <gap>" — the user
  edits or sends. No new backend.
- **(c)** "Suggest next" button → sends the suggestion produced by
  `WorldArchitect.suggest_next` (`world_architect.py:170`, already used for
  first-turn welcomes at `world_building_loop.py:113`). Surface it via the
  existing chat path: a quick-action entry in the Composer's `QuickAction`
  mechanism (`architect/page.tsx:40` imports it) that asks the architect for a
  suggestion as a normal turn. **No new endpoint.**
- **(d)** MiniGraph stays (`:102-111`, 8 s poll) — after F2-2 lands, node
  clicks deep-link to the entity editor.

**Tests:** frontend CoveragePanel test (gaps → chips → composer prefill);
behavior: existing world-building e2e (`tests/e2e/test_09_mode_walkthroughs.py`
world-architect walkthrough) stays green. Use-case IDs: M-6, M-12.

---

### F2-2 · Entity & ontology management — effort M–L — deps: F1-1

- [x] **Track F2-2** — entity detail editor + universe pickers, no raw UUIDs. (DONE 2026-07-24; /forge/ontology + Fact/Axiom/Event CRUD + rel edit/delete + NPC profile editor)

**Goal:** M-12…M-22 (entity CRUD, relationships, memories) usable without
pasting UUIDs or hunting across three pages.

- **(a)** Entities tab upgrade in `/forge/worlds`: the NPC grid
  (`worlds/page.tsx:584`) gains an **entity detail editor** — extend
  `NPCDetailPanel` (worlds route sibling) with edit (M-19), relationships
  (M-21), and memories (M-22; endpoints `entities.py:1181-1222`) sections.
  Backend endpoints exist; UI-only.
- **(b)** Universe pickers replace raw UUID entry — the
  `characters/page.tsx:393` incarnation-add wart and any similar inputs get a
  dropdown fed by `universesApi.listUniverses` (component once, in
  `components/forge/`).
- **(c)** Explorer stays the visual editor (on-canvas create
  `explorer/page.tsx:190-210`, batch delete `:167`); link entities tab ↔
  explorer per universe (`/explorer?universe=<id>`).
- **(d)** Scope guard: do **not** build a generic ontology-schema editor
  (custom entity types/fields) — the `ENTITY_TYPE_CONFIG` taxonomy
  (`lib/forge.ts`) is fixed by the data-layer enums; changing that is a
  data-layer project, not a Forge UI item. Said out loud to avoid over-scoping.

**Tests:** frontend detail-editor test (load → edit → PUT); backend:
`test_entities_crud.py` already covers the endpoints — add only if (a) exposes
an uncovered path. Use-case IDs: M-16, M-19, M-21, M-22.

---

### F2-3 · Canon-review triage — effort S–M — deps: F1-4; optional dep: G-9 Phase 2

- [x] **Track F2-3** — filters + bulk ergonomics; needs_review badge if G-9 lands. (DONE 2026-07-24; needs_review badge deferred with G-9 Phase 2)

**Goal:** review queues are triageable at volume.

- **(a)** Filters on `/forge/review`: by change type (counts already computed
  backend-side, `canon_review.py:119-128`), by source, by confidence tier
  (tiers exist in the page, `review/page.tsx:46-57` — make them filters, not
  just groupings), and text search over payload names/statements. Client-side
  over the already-paginated lists; no backend change.
- **(b)** Bulk ergonomics: select-all-in-tier + batch verdict (batch endpoint
  exists, `canon_review.py:259`; `batchReview` exists pack-side,
  `pack_library.py:1541`).
- **(c)** `needs_review` badge — **only if G-9 Phase 2 has landed**
  (GAP_REMEDIATION_PLAN: proposals stamped `meta.needs_review`): badge + filter
  in all three scopes. Otherwise defer with a TODO comment referencing G-9.

**Tests:** frontend filter/batch tests on the review page; backend none unless
(c) activates (then the G-9 filter tests apply). Use-case IDs: I-4, CF-8.

---

### F2-4 · Ingestion job visibility — effort S — deps: F1-2, F1-4

- [ ] **Track F2-4** — warnings visible per job; deep links to review and pack.

**Goal:** an operator always knows what the pipeline did and where its output
went.

- **(a)** Surface `IngestionJob.warnings` (schema field exists,
  `schemas/ingestion_jobs.py:141`; populated by G-8's skip-surfacing) in
  `IngestionJobsList.tsx` — expand-row rendering next to the existing
  failed-batch detail.
- **(b)** Job → review deep link (shipped with F1-4(b)); job → pack deep link
  where `pack_id` is known.
- **(c)** Jobs-health chip in Ingest Studio header (endpoint wired in F1-2(b)).

**Tests:** frontend warnings-render test; backend none. Use-case IDs: I-1, I-2,
I-4.

---

## 6. Phase 3 — Advanced

> Goal: the composition/sharing workflows get real UX. Each item is
> independently shippable; order within the phase by demand.

### F3-1 · Pack composition UX — effort M — deps: Phase 1

- [ ] **Track F3-1** — merge preview (dry-run) + lineage display.

- **(a)** **Merge preview.** `POST /packs/merge` (`pack_library.py:710`)
  currently commits blind. Add a `dry_run: bool = False` request field
  (additive, backwards-compatible): same dedup pass, returns the would-be
  merged pack (entity/axiom/lore counts + duplicate list) without persisting.
  MergeModal (`forge/page.tsx:372-498`) shows the preview before confirming.
  Implementation: factor the dedup logic out of the persist step inside
  `pack_library.py` — router-level, data-layer tools only.
- **(b)** **Lineage display.** MP-5/MP-6 lineage (parent pack on
  slice/clone) rendered on pack detail (badge + link to parent) — fields
  already set by slice/clone (`pack_library.py:1080-1198`); display-only.
- **(c)** Pack diff (nice-to-have, **cut first** if the phase slips): compare
  two packs' item lists by name/statement — client-side over two fetches.

**Tests:** backend `test_pack_library_merge_dryrun.py` (or extend the existing
pack test file): dry-run returns the same shape as merge, writes nothing
(assert collection unchanged); non-dry-run path byte-identical behavior.
Frontend preview-modal test. Use-case IDs: MP-4, MP-5, MP-6.

### F3-2 · Template authoring UI — effort M — deps: F1-1 (Templates section)

- [x] **Track F3-2** — create/edit EntityTemplates from the UI. (DONE 2026-07-24; /forge/templates + instantiate + random-table create)

- **(a)** Create/edit forms for EntityTemplates in `/forge/templates` —
  `templates.py:42-91` has full CRUD; `TemplateBrowser.tsx` today only lists
  (`:207`) and deletes (`:212`). Form fields follow
  `schemas/entity_templates.py`; generation preview reuses the instantiate flow
  (`TemplateInstantiator.tsx` → `entities.py:902 /generate`).
- **(b)** Random tables get their tab in the same section (editor exists,
  `RandomTableEditor.tsx`; roll endpoint `random_tables.py:244` already powers
  test rolls).
- **(c)** Character (persona) templates are **not here** — G-6 owns them
  (schema + `save-template` endpoint + `CharacterEditor.tsx` extension).

**Tests:** frontend template-form test (create → POST → list refresh);
backend: verify `templates.py` router coverage, add create/update cases if
missing. Use-case IDs: M-32, M-33.

### F3-3 · Multiverse management — effort M — deps: F1-1

- [ ] **Track F3-3** — multiverse edit/delete + universe metadata edit in the UI.

- **(a)** Multiverse edit/delete UI in `/forge/worlds` hierarchy tab —
  endpoints exist (`universes.py:186,201`); delete needs a confirm dialog
  (pattern `confirmDelete` in `forge/page.tsx:897`) and a non-empty guard
  (refuse or cascade-with-explicit-confirm; pick refuse — safer, and fork
  exists for restructuring).
- **(b)** Universe metadata edit (PUT `universes.py:260` — name, description,
  genre, tone) via an edit dialog on the world row; check whether
  `worlds/page.tsx` already exposes edit (create/delete confirmed `:363,:453`,
  edit unclear — verify, add if missing).
- **(c)** `is_template` flag surfacing on multiverse/universe rows (field
  exists on create schemas, e.g. `forge.py:255,268`) — display + filter only;
  template-*instantiation* flows stay with packs/fork.
- **(d)** Cross-universe entity move/copy: **deferred** — needs a CanonKeeper-
  mediated copy operation (Neo4j write authority), not a UI item. Note as a
  future data-layer task if demanded.

**Tests:** frontend hierarchy-tab edit/delete tests; backend extend
`test_universes.py` for the delete-guard behavior if the guard is implemented
router-side (recommended: router-side 409 when the multiverse has universes).
Use-case IDs: M-1, M-7, M-8.

### F3-4 · Style section depth — effort S–M — deps: F1-1, F1-5(a)

- [x] **Track F3-4** — tone libraries + tag definitions + lorebook in Forge. (DONE 2026-07-24)

- **(a)** Tone libraries CRUD UI — `tone.py:154-214` endpoints exist; the UI is
  a read-only list today (`ToneTab.tsx`). Add create/edit/delete using the
  profiles tab as the pattern.
- **(b)** Tag definitions editor — `tone.py:232-293` (incl. `/tags/suggest`
  `:251`) is fully dark on the frontend; wire into `/forge/style`.
- **(c)** Lorebook management in Forge — mount `LorebookEditor.tsx` in
  `/forge/style` with a universe scope selector (it is universe-scoped via
  `lorebookApi`; today reachable only mid-play via
  `CharacterPanel.tsx:333`). Verify the component accepts a universe prop or
  add one — keep the play-surface mount untouched.

**Tests:** extend `ToneTab.test.tsx` for library CRUD; new tag-editor test;
lorebook mount smoke test. Use-case IDs: M-19 (tone on universe), I-9 adjacent
(lorebook curation).

---

## 7. Explicit cross-references (do not duplicate)

| Topic | Owner | Forge touches it only to… |
|---|---|---|
| Portable character templates, `save-template` dark endpoint, `CharacterEditor.tsx` | G-6 (GAP_REMEDIATION_PLAN) | link the roster from Forge when G-6 lands |
| `needs_review` flagging, CanonKeeper depth | G-9 Phases 1–2 | consume the flag in F2-3(c) |
| Co-Pilot surfaces, SessionRecorder | G-5 | leave CanonReviewPanel's GM mount alone |
| Authored-module intros, `intro_text` | G-2 | none |
| Play surfaces (PlayConsole, dice, session zero) | P&F §1–3 | none |
| Separate Forge deployable | P&F §4 open question | stays open; route groups suffice |

---

## 8. Sequencing

1. **F1-5 + F1-6** — small, independent, unblocks an honest inventory. Do first
   (one PR each or one combined "forge hygiene" PR).
2. **F1-1** — the route move. Everything else lands cleaner on the new IA.
3. **F1-2, F1-3, F1-4** — parallel after F1-1 (dashboard / wizard / review
   unification touch disjoint files).
4. **F2-1 → F2-4** — depth; F2-3(c) only after G-9 Phase 2, otherwise ship
   F2-3 (a)+(b) first.
5. **F3-1 → F3-4** — by demand; F3-2 and F3-4 are the most self-contained.

Effort roll-up: Phase 1 ≈ 2M + 4S; Phase 2 ≈ 2M + 1S–M + 1S + 1M–L; Phase 3 ≈
3M + 1S–M. S ≈ ≤1 day, M ≈ 2–4 days, L ≈ 1 week+ (matches
GAP_REMEDIATION_PLAN usage).

---

## 9. Verification (applies to all items)

- `uv run pytest packages tests -q` green; new behavior gets tests per repo
  conventions (backend `packages/ui/backend/tests/test_*.py`; agents via
  `FakeMCPClient`/`FakeLLMClient`, `tests/conftest.py:165,261`; CI blocks
  code-only PRs via `scripts/require_tests_for_code_changes.py`).
- `uv run ruff check packages`;
  `uv run mypy packages/*/src --cache-dir /tmp/mypy-cache`;
  `python scripts/check_layer_dependencies.py`.
- Frontend: `cd packages/ui/frontend && npm run test` (vitest),
  `npm run type-check`, `npm run lint`; playwright smoke for route moves and
  the wizard.
- Every commit references the use-case IDs listed per item (CI:
  `scripts/check_commit_use_case.py`).
- **Manual pass per phase** (stack up via `./dev.sh`):
  - Phase 1: walk all 10 Forge sections from the sidebar; confirm every old
    URL redirects; create a world via each wizard method; run one ingest →
    review → commit round-trip from `/forge/review` (both pack and by-ingest
    scopes); confirm `seed` on an empty universe (live check of the F1-5(b)
    fix) and that `activate` is gone from the OpenAPI surface.
  - Phase 2: build a small world in the Architect workbench using only gap
    chips; edit an entity + relationship + memory from `/forge/worlds`; triage
    a ≥20-proposal queue with filters + batch verdicts.
  - Phase 3: merge two packs with preview → confirm; author a template and
    instantiate it; edit multiverse/universe metadata; manage a tone library
    and a lorebook from `/forge/style`.
- After each item lands: tick its checkbox here and update `docs/STATUS.md`
  (and P&F §4's status marker when the mode is declared full).
