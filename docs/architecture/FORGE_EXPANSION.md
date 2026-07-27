# Forge Mode — Expansion Notes (Tier 3 exploration, 2026-07-23)

> Three read-only explorations that fill the remaining gaps in the Forge plan. Sibling to `FORGE_INVENTORY.md` (which is the file:line-level map of every page/endpoint). Each section here is a \[finding + plan-section update\] — drop the updates into `FORGE_MODE_PLAN.md` when the plan is next revised.

---

## 1. F1-6 — Pack-apply paths (verified)

### Finding

The plan's "two paths" framing is **partly wrong, partly right**. The actual topology:

- **Two UI entry points** to pack apply:
  1. `components/forge/ingest/PackLibrary.tsx:323-341` — inline panel with multiselect + confirmation dialog (lines 542-594). Fires `ingestApi.canonizePack(...)` at line 81-102.
  2. `app/forge/page.tsx:1490-1496` — single "Apply" button → `router.push('/forge/apply?pack=${pack.id}')`.
- **Three backend endpoints**:
  - `POST /api/ingest/packs/{id}/canonize` — `pack_library.py:838`. Used only by PackLibrary. Calls `apply_pack_to_universe(..., auto_accept=True)`. **No conflict handling.**
  - `POST /api/ingest/packs/{id}/apply/new-world` — `pack_library.py:1198`. Used by wizard "new world" path. `auto_accept=False`, returns `review_pending`.
  - `POST /api/ingest/packs/{id}/apply/{universe_id}` — `pack_library.py:1254`. Used by wizard "existing world" path. **Hardcoded `"conflicts": []`** in the response — the wizard's "Conflicts" step is **dead UX**.

### Critical: the wizard's conflict UX is currently unreachable

The wizard (`app/forge/apply/page.tsx:46-63`) defines 5 resolution strategies (`pack_wins | world_wins | llm_merged | human_picked`) and a step-3 conflict picker. The backend endpoint that handles the request **never returns a conflict list**, so:
- The user's MP-7/MP-8 conflict-resolution promise is **silently broken**.
- The picker code is dead — every wizard test path passes through the success branch.

This is the **single biggest correctness bug** in the Forge surface today.

### Plan-section update: F1-6

```
### F1-6 — Reconcile pack-apply (M → S, with backend prerequisite)

**Status (2026-07-23 audit):** The plan's "two paths" framing is partly wrong.
There are two UI entry points and three backend endpoints. The wizard's
conflict-resolution step is dead UX because the backend always returns
``conflicts: []`` (the wizard's MP-7/MP-8 promise is silently broken).

**Goal (revised):** One path through the wizard; backend returns real
conflicts so the wizard's resolver step actually fires.

**Steps (revised PR plan):**

1. **Backend — restore conflict detection** (`pack_library.py:1304`):
   compute conflicts by diffing pack items against the universe's current
   items (schema already defines `PackConflict` per `lib/types.ts:41`).
   Return them on the first call when non-empty; honour `resolved_conflicts`
   on the second call. Also honour `entity_indices`/`axiom_indices`/
   `lore_indices` (currently accepted but unused) so the user can apply
   a subset. ~0.5-1 day.

2. **Frontend — delete PackLibrary direct-Apply** (`PackLibrary.tsx`):
   remove the Apply button (323-341), inline panel (386-501), confirmation
   dialog (542-594), and `canonize` mutation (81-102). Replace with a
   single router-push button mirroring `forge/page.tsx:1490`. ~0.5 day.

3. **Frontend — remove dead api surface**: drop `canonizePack` from
   `api.ts:377`. < 1 hour.

4. **Backend — retire `canonize_pack` route** (`pack_library.py:831-895`).
   < 1 hour.

5. **Tests**: integration test for the wizard that **returns conflicts**
   and verifies the resolver step fires.

**Effort:** 2-3 days (was M; this is S+1 day for the backend prerequisite).
```

---

## 2. F2-1 — Coverage model (formalized)

### Finding

"Coverage" is undefined in the codebase. There are three protean fields on different objects:

| Field | Where it lives | What it actually is |
|---|---|---|
| `coverage_summary` | `AgentTurnMetadata` and `WorldArchitect.process_turn()` return | Prose string: "N entities, N axioms, N lore facts. Named anchors: … Tone cues: … Power structures: …" (`utils/world_profile_support.py:136-153`). Not a percentage, not a score. |
| `known_open_questions` | `WorldArchitect` return payload | List derived from absence heuristics: no name → "no world name"; no location/city entity → "no geography"; no faction → "no power structures"; zero axioms → "no foundational rule"; <2 facts → "no conflict"; no character → "no NPC" (`utils/world_profile_support.py:156-179`). |
| `priority_gaps` | `WorldArchitect` return payload | Categories mapped from open questions: Core identity, Power structures, Geography, World rules, Current conflict (`utils/world_profile_support.py:182-242`). Fallback to first 3 categories. |

`WorldArchitect._load_world_state_summary` (`world_architect.py:452-503`) only queries Neo4j entities, axioms, and facts. **It does NOT query relationships, game systems, random tables, or mechanics.** This is a major gap — a world can have hundreds of entities and still be "disconnected" with no edges.

The current `ArchitectMessageBubble` renders only **up to 3 open questions** and a "World changes" card. The `coverage_summary` and `priority_gaps` are derived but **never visibly rendered** (`ArchitectMessageBubble.tsx:16-60`).

`AnalyzeRunResult` does not emit coverage; it has ingestion reliability counters only.

### Plan-section update: F2-1

```
### F2-1 — Architect workbench: coverage-driven building (M → M-L)

**Status (2026-07-23 audit):** The plumbing for "coverage" exists in
``WorldArchitect`` (``coverage_summary``/``known_open_questions``/
``priority_gaps``) but is inconsistently surfaced: ``ArchitectMessageBubble``
only renders 3 open questions; the loader queries only entities/axioms/facts
(``world_architect.py:452-503``); relationships/mechanics/random-tables are
not loaded. The workbench needs to:
1. Define a formal coverage model (not just prose counts).
2. Load the missing dimensions (relationships, mechanics, random tables).
3. Render the gap cards in a real workbench page, not as a derived
   `useMemo` on the architect page.

**Coverage dimensions (8 — each becomes a card on the workbench):**

- **A. Identity** — name, genre, tone, narrative frame, default system.
  Source: `world_architect.py:452-503`. Open-questions machinery
  already covers this.
- **B. Entity taxonomy** — counts + detail-level histogram per entity type
  (character/faction/location/object/concept/organization,
  `schemas/base.py:139-148`). Detail-level distinction matters:
  "NPC exists but is only a stub" (`canonkeeper.py:108-157`).
- **C. Fact taxonomy** — total active facts + break-down by `FactType`
  (`state|relationship|attribute|occurrence`), facts with entity
  references, with provenance, current conflict, historical/founding.
  Source: `schemas/facts.py:32-39`, `:73-94`.
- **D. Foundational axioms** — count + domains covered
  (physics/society/metaphysics/genre, `schemas/base.py:116-123`).
  CanonKeeper maps free-text domains to enum (`canonkeeper.py:57-76`).
- **E. Relationships & connectivity** — total edges, categories
  (social/membership/ownership/spatial/temporal/taxonomic/power/generic,
  `schemas/relationships.py:27-67`), isolated entities, factions without
  members, NPCs without affiliations. **NEW: must extend the loader.**
- **F. Game system & mechanics** — linked system, core mechanic, success
  method, attributes/skills, resolution mechanics, combat/social rules,
  conditions, advancement, character creation (per
  `schemas/game_systems.py:29-58`, `:168-237`). **Currently NOT loaded by
  ``WorldArchitect`` — must add.**
- **G. Random generation assets** — table count, types covered
  (encounter/loot/NPC/location/event/etc., `schemas/random_tables.py:33-46`),
  tables linked to universe/system. **Currently NOT loaded.**
- **H. Provenance & confidence** — primitives with source refs,
  evidence snippets, confidence, canon level, review status.

**Recommended semantics (top of the workbench doc):**

> Coverage is the set of world-building and play-enabling primitives
> currently represented, connected, sufficiently detailed, and trusted
> in a universe, compared against a context-dependent baseline.

A complete world does not require every category. Identity + at least
one axiom is the floor. NPCs, locations, factions, facts, relationships
are setting/playability dimensions. Game-system mechanics and random
tables are required only when the world is intended for mechanical play
or procedural generation. Provenance is required for ingested material
but not for direct GM declarations. Thresholds are configurable by world
intent, genre, game system, and selected build mode.

**Effort:** M-L (it expands to L because the loader needs to grow to
cover relationships + mechanics + random tables, the schema gets 8 new
gap-types, and the Architect page needs a re-design — but the underlying
plumbing is mostly there).
```

---

## 3. F2-2 — Entity & ontology management (formalized)

### Finding

The data model is rich but the management UI is sparse. Concrete gaps:

| Gap | Evidence | Severity |
|---|---|---|
| **No router endpoints for Fact/Axiom/Event CRUD.** Neo4j tools (`neo4j_tools/facts.py:100,308,366,490,563`) have full CRUD primitives for Fact, but **`entities.py` has no `@router` for facts/axioms/events**. UI is unreachable. The graph tool update/delete exists for Fact but not for Axiom or Event. | Highest | 
| **No relationship update/delete API.** `entitiesApi.createRelationship` exists (`api.ts:638-691`); `listRelationships` exists; **no `updateRelationship` or `deleteRelationship`**. Even when on-canvas creation works (`explorer/page.tsx:188-190`), edits/deletes are unreachable. | High |
| **`TemplateBrowser` lacks create/edit UI.** Backend `templates.py:42-91` has full CRUD; `api.ts:1174-1211` exposes `create`/`update`; **frontend `TemplateBrowser.tsx:206-214` only list/delete**. The M-32 phase item is half-met. | High |
| **`GameSystem` authoring is read-only.** `entities.py:557-704` has full CRUD; `api.ts` exposes it; **`game_systems.py:75-113` router is read-only**; **`/systems/page.tsx:646` says "Ingest a rulebook" when empty**. The intended authoring path is ingest-only, which is a gap. | Medium |
| **NPC profile has no dedicated management UI.** NPCProfile schema is rich (`npc_profiles.py:110-209`) but no router surfaces it as CRUD; `worlds/page.tsx` NPC detail panel only displays. Profile is read-only via `worlds/InspectorPanel` and `NPCDetailPanel`. | Medium |
| **Lorebook has no Forge-side page.** `lorebook.py:41-145` is full CRUD; `LorebookEditor` is mounted only in Play (`CharacterPanel.tsx:333`); no dedicated Forge tab. | Low (F3-4) |
| **`EntityType` is a fixed enum.** `schemas/base.py:139-148` is closed (`character/faction/location/object/concept/organization`). No user-defined taxonomy. The create-entity payload accepts `entity_type` as a string but it's coerced to the enum. | Low |
| **KnowledgePack editing is for proposals, not canonical nodes.** `ForgeRows.tsx:233+` edits embedded extracted axioms/lore facts and moves lore fact to axiom — but saves as **pack proposals**, not standalone Neo4j Axiom/Fact. The "save to canon" round-trip goes through `/forge/review`. | Architecture |

### Plan-section update: F2-2

```
### F2-2 — Entity & ontology management (M → L)

**Status (2026-07-23 audit):** Backend CRUD is largely complete (entities,
characters, NPCs, relationships, random tables, lorebook). The UI is
asymmetric: there are 9 distinct gaps ranked by user impact (see the
inventory doc). The biggest single gap is "no router endpoints for
Fact/Axiom/Event CRUD" — the Neo4j tools exist but no UI exposes them.
The second biggest is relationship update/delete (Explorer creates on
canvas but cannot edit/delete edges).

**Goal (revised):** Build the missing CRUD surfaces and consolidate
them into a single ``/forge/ontology`` page (or fold into the F2-1
workbench).

**Implementation phases (revised):**

1. **Backend — add Fact/Axiom/Event CRUD routers** (`routers/entities.py`,
   near the generic entity routes at :1538). New endpoints:
   - `POST /entities/{universe_id}/facts` (FactCreate)
   - `GET /entities/{universe_id}/facts` (list with filters)
   - `PATCH /entities/facts/{id}` (update)
   - `DELETE /entities/facts/{id}`
   - Same for `axioms` and `events`. Also fix Neo4j `Axiom` and `Event`
     to expose update/delete (currently only create/get/list).
   - Effort: 1 day.

2. **Backend — add relationship update/delete** (`entities.py` near :1652).
   ~0.5 day.

3. **Frontend — `TemplateBrowser` create/edit** (`TemplateBrowser.tsx:200-300`).
   Backend already supports this. New form modal + entity create/update
   mutation wiring. ~2 days.

4. **Frontend — relationship edit/delete in Explorer** (`explorer/page.tsx:188-219`).
   Right-click context menu on edges. ~0.5 day.

5. **Frontend — NPC profile editor** (in `/forge/worlds` entity inspector).
   Reads `npcProfiles`; new modal. ~1 day.

6. **Frontend — `/forge/ontology` page** (or fold into workbench).
   Tabs for Entities / Facts / Axioms / Events / Relationships / Templates.
   Pulls from the new endpoints.
   ~1 week.

7. **Backend — `GameSystem` authoring router** (lift from `entities.py`
   into a new `game_systems.py` author-facing router; OR enhance the
   existing router to expose create/update/delete). ~0.5 day.

**Effort:** L (was M; this expands because the data model is broader than
the plan anticipated).
```

---

## 4. Cross-cutting recommendations

After three Tier 3 explorations, the Forge plan's risk profile has shifted:

- **F1-5** now has a clear customer: the 6 BROKEN endpoints (5 snapshot + 1 seed runtime). 1-day PR.
- **F1-6** is bigger than expected: the conflict-detection bug is a real correctness issue, not a UX choice. 2-3 days.
- **F1-1** is bounded by the inventory — 1 honest week, 1.5 if the dashboard is shaped from scratch.
- **F2-1** is bigger than expected: 8 coverage dimensions, half of them require loader work. M-L.
- **F2-2** is bigger than expected: 9 distinct gaps, one of them (Fact/Axiom/Event CRUD) requires Neo4j tool work. L.

**Re-sequencing recommendation:**

1. **F1-5(e) + F1-6 step 1 (backend conflict detection) first** — both are bugs in active pages. ~3 days.
2. **F2-2 step 1 (Fact/Axiom/Event CRUD routers)** — small backend change, unlocks a lot of the audit. ~1 day.
3. **F1-1 (route consolidation)** — the keystone. Once this is done, F1-2, F1-3, F1-4 land cleaner. ~1 week.
4. **F1-5 (a, b, c) + F1-6 (collapse PackLibrary)** — page-level cleanup. ~3 days.
5. **F2-1 (workbench)** — the M-L build. Block on F1-1 (route consolidation) so the workbench lives under `/forge/architect`. ~2-3 weeks.
6. **F2-2 (ontology management)** — depends on F2-1 (workbench hosts the UI). ~2-3 weeks.
7. **F3-1, F3-2, F3-3** — sequential after Phase 2. ~3 weeks.

**Total: 2-3 months solo developer, starting with the F1-5/F1-6 backlog burn-down.**

---

## 5. What's still unknown

After Tier 3, the remaining uncertainties are:

- **F1-1 spike** — actual import/SPA-runtime cost of moving one route to the new IA. Recommended as a 1-day prototype before scoping the F1-1 PR.
- **GM Assistant live verification** — the plan marks 6 items SHIPPED but no one has run all of them together. Recommended as a 1-day end-to-end test of capture → wrap-up → archive.
- **F3-4 (Style section depth)** — F1-5(a) (ToneTab dedup) is half of this; the second half (lorebook management in Forge) is a small UI move. Not yet explored.
- **G-6 (Portable character templates)** — at ~25% complete. Up to the user whether this gates F3-2 (template authoring UI) or runs in parallel.

---

## 6. F2-3 — Canon-review triage (verified)

### Finding

Three active review surfaces exist with inconsistent affordances:

| Surface | Files | Status filter | Change-type filter | Confidence | Bulk | Reason capture |
|---|---|---|---|---|---|---|
| `CanonReviewPanel` (story/scene) | `components/canon/CanonReviewPanel.tsx:316-349` | per-scene tabs | counts only | badge (medium at 0.6) | "Accept All" only | **broken — input never persisted** |
| `/forge/review` (pack) | `app/forge/review/page.tsx:177-205` | none | clickable tabs | badge (medium at 0.7) | Accept/Reject all + Accept High Conf | yes |
| `by-ingest` (dark) | `canon_review.py:194-248` | backend enum | none | data only | exact IDs only | no UI |

**Critical bug**: `CanonReviewPanel` has a `reason` state (line 68-69) and input field, but the card invokes `onAccept(id)` without passing the reason (line 137-165). The parent's `acceptReason`/`rejectReason` state is never updated. **Users type a reason, hit accept, but the typed reason is silently dropped. The mutation sends its default strings.**

**Critical prerequisite**: F1-4 has 4 lifecycle bugs that block F2-3 from being useful:
1. `_auto_canonize_enabled()` is unreachable in the enqueue branch (`ingestion_pipeline.py:620-638, 862-883`).
2. Direct enqueue writes `status="pending_review"` which is not a valid `ProposalStatus` enum value.
3. Job attribution is not established at proposal creation — current code queries all pending proposals in the universe, misattributing unrelated proposals.
4. No by-ingest commit path. The pack commit method queries `source=knowledge_pack:<id>` but by-ingest proposals have `source=ingestion_job:<id>`, so accepted by-ingest proposals cannot be committed.

**Other gaps** (ranked by user impact):
- **P1**: Per-proposal diff (before/after) — currently only short preview text.
- **P1**: Safe selective bulk operations — current "all" is "all loaded" (max 200/500/1000).
- **P1**: Unified prioritization filters — `?status`, date range, text search, sort control.
- **P2**: Provenance & source-side grouping (per source page, per ingestion job, per scene).
- **P2**: Confidence, authority, canon-level breakdown.
- **P2**: Retry or re-extract from review.
- **P3**: Snooze, defer, assign workflow (requires schema changes).
- **P3**: Undo/reopen (currently terminal).

### Plan-section update: F2-3

```
### F2-3 — Canon-review triage — effort S-M → M — deps: corrected F1-4; optional dep: G-9 Phase 2

**Status (2026-07-23 audit):** Three inconsistent review surfaces today.
``CanonReviewPanel`` has a broken reason-capture (the input is filled but
never persisted to the verdict). Many gaps ranked by user impact (see
FORGE_EXPANSION.md §6). F1-4 has 4 lifecycle bugs that block F2-3 from
being useful — they must be fixed first.

**Goal (revised):** A normalized review workbench with finding, prioritization,
provenance, and selective bulk verdicts. Retry, assignment, and a universal
semantic diff should NOT be hidden inside the S-M budget.

**Preconditions owned by F1-4:**
- Default ingestion produces schema-valid pending proposals attributed only
  to the current job (not every pending proposal in the universe).
- By-ingest proposals use a schema-valid lifecycle (no `pending_review`).
- Proposal/job/pack lineage is exact and preserved.
- All three scopes expose a normalized proposal shape.
- By-ingest has an accepted-proposal commit path.
- `/forge/review` has scope selection (Pack / Ingestion job / Story-scene).

**Sub-items (revised):**

- **(a) Shared triage model and controls** (~1 day). One frontend review-item
  adapter used by all three scopes. Expose IDs, scope, change_type,
  proposal_type, status, source/job/pack/scene/turn lineage, content,
  source_ref, confidence, authority, proposer, canon level when available,
  decision metadata, created/updated/decided dates, optional `needs_review`.
  Shared filter bar: status, change type, confidence tier, date range, text
  search, sort by newest/oldest/confidence. Persist scope and filter state
  in URL query parameters.

- **(b) Detail and provenance drawer** (~1-2 days). Each row opens a drawer
  showing complete structured payload, specific operation subtype, evidence
  references, source page/section, scene/turn/job/pack context, authority,
  proposer, timestamps, existing decision reason. For create proposals, label
  "Proposed value." For state/update proposals, render explicit add/remove/change
  sections when payload has them. Do NOT call this a universal "diff" until
  the proposal contract contains a canonical target and before/after values.

- **(c) Selection and bulk ergonomics** (~1-2 days). Per-row checkbox. Select
  visible. Select all matching active filters. Clear selection. Accept/reject
  selected. Required/shared reason dialog. Confirmation with affected count.
  Per-item failure summary and retry. "Select all matching" must NOT silently
  mean "the first 200/500/1000 items." A server-side bulk-by-filter request
  with a preview token is recommended.

- **(d) Existing behavior fixes** (~0.5 day). Pass the typed user-entered
  CanonReviewPanel reason. Fix scene-mode Accept All. Add reject-selected to
  story/scene scope. Support `state_change` and `event` in frontend types.
  Use one confidence-tier definition across all scopes. Include story-level
  proposals that have no scene. Make batch partial-failure behavior match its
  contract.

- **(e) Optional G-9 Phase 2 integration** (~0.5-1 day). Only if G-9 Phase 2
  lands first. Expose typed `needs_review`, `review_reason`, `review_source`.
  Add a high-visibility badge. Add a `needs_review` filter and count in every
  scope.

- **(f) Tests** (~1 day). Frontend: each filter and combined, URL state/deep
  links, select visible vs select all matching, batch accept/reject payload and
  reason, partial-failure rendering, state-change/event rendering,
  detail/provenance drawer, optional G-9 badge/filter.

**Effort conclusion:**
- Plan literal: client-side filters + select currently loaded tier — S-M (2-3 days).
- Recommended triage: shared filters, detail/provenance, selection, fixes, tests — M (4-7 days).
- Safe server-side "all matching" with pagination/indexes — additional M (2-4 days).
- True generic before/after canon diff — separate M (3-5 days).
- Retry/re-extract workflow — separate S-M.
- Snooze/defer/assign/reopen lifecycle — separate M (changes schema).
```

---

## 7. F2-4 — Ingestion job visibility (verified)

### Finding

The data model is rich but the serializer drops most of it. Three concrete contract bugs:

1. [FIXED 2026-07-24] **`_job_to_dict` omits `pack_id`** (`ingest_shared.py:265-299`). The frontend "View Result" action (`IngestionJobsList.tsx:334-341`) needs `pack_id` to navigate. Today it's usually `undefined`, so the link is dead.

2. **SSE serializer calls `json.dumps(_job_to_dict(job))` directly** (`ingest.py:1506-1507`). If `job.last_error` is the new structured `LastError` model, `json.dumps` may fail on a Pydantic object. The frontend `last_error?: string | null` type can't render an object.

3. **`total_attempts` and `failed_sections` are in the schema but never persisted** by `mongodb_update_ingestion_job` (`ingestion_jobs.py:222-247`). The document-to-response converter `failed_sections` defaults to `[]` and `total_attempts` to `0`.

**Frontend misses actionable content:**
- `IngestionJobsList` never renders `job.warnings` — the field is shipped empty.
- The expanded row shows only snippets/entities/axioms/proposals tiles, then `activity_log` and `error`. No `failed_sections`, no batch counts, no attempts, no provider/model, no durations, no reliability breakdown.
- `FAILED_JOB_STATUSES` (`ingest-constants.ts:24-34`) excludes `failed_non_retryable`, `blocked_provider`, `cancelled` — those red-badge terminal states don't auto-expand and don't get the Retry action.
- `/api/jobs/health` is fully dark — no frontend API wrapper, no hook, no chip. 6 of 13 valid `IngestionStatus` values are silently dropped from the `counts` object.

**SSE merge bug**: the message handler rejects any update where `status` is unchanged AND cached progress ≥ incoming (`IngestionJobsList.tsx:101-109`). Warnings, activity entries, retry counts, and provider changes can change without progress changing. **Those SSE updates are silently discarded; they only arrive 5 seconds later via polling.**

**Rescan destroys history**: `ingest.py:1091-1104` deletes all existing job rows for a source before re-ingestion. This blocks any "retry success rate" or "time-series" view — the data is gone.

### Plan-section update: F2-4

```
### F2-4 — Ingestion job visibility — effort S → S-M — deps: F1-2, F1-4

**Status (2026-07-23 audit):** Most data exists; the contract is broken.
``_job_to_dict`` drops ``pack_id``, ``total_attempts``, ``failed_sections``,
``universe_id``; ``last_error`` is now structured but the frontend type
expects a string; SSE updates that don't change progress are silently
discarded. Warnings are persisted but never rendered. The health endpoint
drops 6 of 13 valid statuses. If F1-2 (health wiring) and F1-4 (job review)
land first, F2-4 remains S. From the current checkout, F2-4 is S-M.

**Goal (revised):** An operator can tell what an ingestion did, what was
skipped or failed, whether intervention is needed, and where the usable
output went.

**Sub-items (revised):**

- **(a) Repair the job visibility contract** (~0.5-1 day). Persist
  ``total_attempts`` and ``failed_sections`` in
  ``mongodb_update_ingestion_job`` / ``_convert_ingestion_job_doc``. Add
  ``total_attempts``, ``failed_sections``, and ``pack_id`` to
  ``_job_to_dict``. Serialize ``last_error`` as a structured JSON object;
  expose a separate display-safe ``error`` string from ``last_error.message``.
  Align the frontend ``IngestJob`` type. Add regression tests including SSE
  with structured ``last_error``.

- **(b) Make expanded job rows actionable** (~0.75-1.25 days). Render a
  warning-count badge on collapsed rows. In expanded rows, render warnings
  separately from fatal errors. Add reliability tiles: succeeded/total
  batches, failed batches, retries/attempts, provider/model, duration.
  Render ``failed_sections`` as section path + stage + reason, capped for
  long lists. Lazy-load ``/jobs/{id}/attempts`` only when the operator
  opens "Attempt details". Group retries by ``batch_id``. Treat
  ``failed_non_retryable``, ``blocked_provider``, and ``cancelled``
  consistently in failed/terminal status sets.

- **(c) Complete output navigation** (~0.25 day after F1-4). Completed/partial
  jobs with proposals get "Review proposals" → ``/forge/review?job=<job_id>``.
  Jobs with ``pack_id`` get "Open pack" → ``/forge/editor?pack=<id>``
  (NOT ``/forge?pack=<id>`` — that page defaults to Sources mode).

- **(d) Surface jobs health** (~0.25 day if F1-2 landed; 0.75 day otherwise).
  Reuse F1-2's ``jobsHealthApi``. Add health chip next to the Lorebook
  active-job chip. Extend health counts to include every ``IngestionStatus``
  (or return a dynamic status map plus aggregate ``active``, ``failed``,
  ``terminal`` totals).

- **(e) Fix SSE merge semantics** (~0.25-0.5 day). Accept same-progress
  snapshots so warnings, attempts, provider state, and activity logs update
  live. Prevent only progress regression, rather than discarding the complete
  newer snapshot. Verify stream closure for all backend terminal statuses.

- **(f) Tests** (~0.5-0.75 day). Data-layer: warning append remains capped;
  ``failed_sections``/``total_attempts`` round-trip. Backend: REST and SSE
  serializers expose ``pack_id``, failed detail, and structured error safely.
  Frontend: warnings render, failed sections render, status variants get
  correct actions, pack/review links correct, same-progress SSE update adds
  a warning, health chip healthy/stale/disabled/unreachable states.

**Effort:** S (2-3 dev-days) with F1-2 + F1-4 done; S-M (3.5-5 dev-days)
from the current checkout.

**Out of scope (separates):** Cross-source analytics, time-series view,
accurate cost/token telemetry, retry lineage retention. These become a
separate F2-5 or F3 item at M-L effort.
```

---

## 8. F3-4 — Style section depth (verified)

### Finding

**ToneTab inline vs component is functionally identical** (zero behavior diff):
- `app/settings/page.tsx:2088-2228` (inline, 141 lines) — module-local, no `"use client"`, no tests.
- `components/settings/ToneTab.tsx` (153 lines) — exported, `"use client"`, 4 tests passing.

The inline copy is a near-byte-for-byte duplicate of the component. F1-5(a) is correct: delete the inline, import the component. Diff is mechanical.

**Tone backend inventory** (`routers/tone.py`):

| Group | Wired | Dark |
|---|---|---|
| Profiles (6 endpoints) | 4 wired (`list`, `create`, `delete`, partial `update`) | 2 dark (`builtin`, `get-by-id`) |
| Libraries (6 endpoints) | 1 wired (`list` read-only) | 5 dark (`get-default`, `get-by-id`, `create`, `update`, `delete`) |
| Tags (6 endpoints) | 0 wired | 6 dark (the entire tag group) |

`api.ts:558-572` has 5 toneApi wrappers; 13 endpoints are unwrapped.

**Lorebook backend inventory** (`routers/lorebook.py`):

| Endpoint | Wired | Notes |
|---|---|---|
| `POST /lorebook/entries` | yes | create |
| `GET /lorebook/entries/by-tags` | dark | |
| `GET /lorebook/entries` | yes | list |
| `GET /lorebook/entries/{id}` | dark | |
| `PATCH /lorebook/entries/{id}` | yes | update |
| `DELETE /lorebook/entries/{id}` | yes | delete |
| `POST /lorebook/bulk` | yes | bulk create (used by ingest) |
| `POST /lorebook/inject` | dark | agent-side runtime scan |
| `GET /lorebook/stats` | yes | |
| `GET /lorebook/top` | dark | |

**`LorebookEditor` is hard-scoped to characters** (`LorebookEditor.tsx:29-32`). The `character_id` field accepts the literal string `"universe:<universe_id>"` (`lorebook.py:21-23`) as a convention for universe-wide entries. To make it work in Forge, the editor needs a `universeId?: string` prop and a character picker scoped to a universe.

**Sizing**: `ToneTab` is trivial (153 lines, one form, list with create+delete). `LorebookEditor` is a real editor (644 lines, 4 panels, search/sort, batched ingest with progress). The migration cost is mostly prop change + mount site, not a rewrite.

**The plan's S-M estimate undercounts F3-4.3 (tag definitions) as the bulk** — 6 endpoints, 4 categories, autocomplete integration. ~2.5 days alone.

### Plan-section update: F3-4

```
### F3-4 — Style section depth — effort S-M → M — deps: F1-1, F1-5(a)

**Status (2026-07-23 audit):** ToneTab inline copy is functionally identical
to the component (zero diff). Backend tone endpoints are 23% wired (5 of 22).
Lorebook endpoints are 55% wired (6 of 11). ``LorebookEditor`` is hard-scoped
to characters — needs a ``universeId?: string`` prop. The plan's S-M estimate
undercounts F3-4.3 (tag definitions) as the bulk.

**Goal (revised):** Move ToneTab and LorebookEditor to ``/forge/style``.
Add full CRUD for tone libraries and tag definitions. Add a character picker
scoped to a universe.

**Sub-items (revised):**

- **(F3-4.0) Page skeleton** (~0.5 day). New ``app/forge/style/page.tsx`` +
  sidebar entry. Tabbed UI: Profiles, Libraries, Tags, Lorebook.

- **(F3-4.1) Lift ToneTab** (~1 day). Move from ``/settings`` to
  ``/forge/style``. Add ``updateProfile`` mutation (endpoint exists,
  wrapper exists, no UI). Add ``category``, ``language`` selectors on the
  create form (the schema supports 7 fields, the UI only uses 3).

- **(F3-4.2) Libraries CRUD UI** (~1.5 days). New ``LibrariesPanel`` using
  ``createLibrary`` / ``updateLibrary`` / ``deleteLibrary`` / ``getDefault``.
  Add the 5 missing ``toneApi`` wrappers. Schema has
  ``tone_profile_ids: list[UUID]`` — picker must be wired to the profiles
  list (from F3-4.1).

- **(F3-4.3) Tag definitions editor** (~2.5 days). Add 6 ``toneApi``
  wrappers; new ``TagDefinitionsPanel`` with create/edit/delete + 4 category
  tabs (``TONE`` / ``THEME`` / ``STYLE`` / ``CONCEPT``). Use ``suggestTags``
  for autocomplete on the profile form (the existing ``tags`` input is a
  freeform comma-separated list).

- **(F3-4.4) LorebookEditor in Forge** (~1.5 days). Add ``universeId?: string``
  prop to ``LorebookEditor``. In Forge: when set, show a character selector
  for the universe (or a "universe-wide" pseudo-character using the
  ``universe:<id>`` convention). Reuse the existing component; pass
  ``onClose={undefined}`` to disable the X. The existing CharacterPanel
  mount at ``CharacterPanel.tsx:333`` stays.

- **(F3-4.5) Tests** (~1 day). Extend ``ToneTab.test.tsx`` (update flow,
  library CRUD cases); new ``TagDefinitionsPanel.test.tsx``; new
  ``LibrariesPanel.test.tsx``; smoke test for ``/forge/style`` page mount.

**Effort:** ~8 dev-days = M (1.5 weeks solo, ~1 week paired). The plan's
S-M upper bound is right; the plan undercounts because F3-4.3 (tag editor)
is the bulk and the plan lists it as one bullet under (b).

**Risks (called out in PR):**
- ``LorebookEditor`` is a full-height modal (``:354``: ``flex flex-col
  h-full bg-gray-950``). When embedded in ``/forge/style`` it expects the
  parent to be a height-bounded column. Plan for a small CSS wrapper.
- ``LorebookEntry.character_id = "universe:<id>"`` convention is documented
  but ``LorebookEditor`` does not currently support creating or viewing
  such entries. Small but real change.

**Out of scope:**
- Speech style / voice (NPC profile field) — owned by G-6.
- ``GMProfile.tone_tags`` — consumer of tones/libraries; editing lives in
  GM Assistant.
- ``KnowledgePack.ExtractedToneProfile`` — pack-internal; lives in
  ``/forge/packs``.
- ``TagPool`` — separate from tag definitions; do not merge.
```

---

## 9. Re-sequencing after Tier 3

With F2-3, F2-4, and F3-4 now scoped, the recommended order is:

| Priority | Item | Effort | Why first |
|---|---|---|---|
| 1 | F1-5(e) + F1-6 step 1 (backend conflict detection) | 3 days | bugs in active pages |
| 2 | F2-4(a) (job visibility contract) | 0.5-1 day | small, enables honest F2-4 |
| 3 | F1-4 (5 corrections: enqueue, status, lineage, response contract, commit) | 2-3 days | F2-3 blocker |
| 4 | F2-2 step 1 (Fact/Axiom/Event CRUD routers) | 1 day | small backend, unlocks audit |
| 5 | F1-1 (route consolidation) | 1 week | keystone |
| 6 | F3-4.0 + F3-4.1 (ToneTab dedup + lift) | 1.5 days | F1-5(a) prerequisite |
| 7 | F1-2 (dashboard) + F1-3 (wizard) + F1-4 (now corrected) | 1 week/dispatch | parallel after F1-1 |
| 8 | F1-5 (a, b, c) + F1-6 (collapse PackLibrary) | 3 days | page-level cleanup |
| 9 | F3-4.2 + F3-4.3 + F3-4.4 (libraries, tags, lorebook in Forge) | 5.5 days | F3-4 main work |
| 10 | F2-1 (workbench) | 2-3 weeks | M-L build |
| 11 | F2-3 (triage) | 4-7 days | F2-3 main work |
| 12 | F2-2 (ontology management) | 2-3 weeks | depends on F2-1 |
| 13 | F3-1, F3-2, F3-3 | 3 weeks | sequential after Phase 2 |

**Total: 2-3 months solo developer**, starting with the F1-5/F1-6/F2-4 bug-fix burn-down. The F1-4 lifecycle corrections are now a P0 prerequisite for any review-triage work; F2-3 cannot be useful without them.

---

## 10. F3-2 — Template authoring UI (verified)

### Finding

Backend `EntityTemplate` CRUD is fully wired (`templates.py:41-95`, 5 routes) and the schema is rich (`entity_templates.py:139-232` + sub-models). `templatesApi` (`api.ts:1174-1211`) exposes `list`/`get`/`create`/`update`/`delete` — **only `list` and `delete` are wired from the frontend**. `randomTablesApi.list` is the only random-table call from the frontend; `create`/`update` are unused.

**Critical gaps:**
- **`TemplateBrowser.tsx` (323 lines) only lists and deletes.** No "New Template" button, no edit form, no create/edit mutations.
- **`InstantiateEntityRequest` schema exists (`entity_templates.py:240-260`) but is unused by any router or frontend.** The instantiate flow goes through `entitiesApi.generateEntity` (`TemplateInstantiator.tsx:34-40`) with `concept: template.description` and `state_tags: template.default_state_tags` — the template's structured fields (`variable_properties`, `naming_pattern`, `parent_template_id`) are display-only in the browser and inert in the generate flow.
- **`usage_count` is always 0.** `mongodb_increment_template_usage` exists (`mongodb_tools/templates.py:131-136`) but no router or generate-path code calls it.
- **`RandomTableEditor.tsx` (418 lines) has no Create button.** Only inline editing of existing tables. `randomTablesApi.create` exists but is never called.
- **No backend tests for `templates.py`.** Grep for `EntityTemplate` in `packages/ui/backend/tests` returns zero matches. The router is untested.

**G-6 dependency is clear:** no `CharacterTemplate` schema exists. F3-2 must not touch persona templates; those are G-6's.

### Plan-section update: F3-2

```
### F3-2 — Template authoring UI — revised (effort M → M-L)

**Status (2026-07-23 audit):** Backend EntityTemplate CRUD is fully wired (5
routes) and the schema is rich. templatesApi exposes create/update but the
frontend only calls list/delete. InstantiateEntityRequest is defined but unused;
the template's structured fields are inert in the generate flow. usage_count
never increments. RandomTableEditor has no Create button. No backend tests for
templates.py. G-6's CharacterTemplate is not in scope.

**Goal (revised):** Ship the create + edit UI for EntityTemplate and a create
button for RandomTable. Wire the instantiate flow to actually exercise the
template's variable_properties + naming_pattern + usage_count accounting.

**Sub-tasks (revised):**

- **(a) Backend holes** (~0.5 day). Wire mongodb_increment_template_usage
  (POST /templates/{id}/increment-usage or fold into instantiate). Add
  POST /templates/{id}/instantiate that actually exercises variable_properties
  and naming_pattern, returns a populated EntityInstance, bumps usage_count.
  Add router tests in tests/contracts/test_entity_templates_contracts.py +
  new tests/api/test_templates_api.py (~150 lines).

- **(b) Create + edit forms** (~1.5-2 days). New TemplateEditorModal.tsx
  (DialogShell-based), two modes. Fields: name, description, entity_type,
  base_properties, variable_properties, naming_pattern, stat_generation,
  default_state_tags, default_detail_level, default_personality, parent_template_id,
  universe_id. Mount via "New Template" button in TemplateBrowser toolbar and
  Edit2 icon on cards. Add universeId plumbing.

- **(c) Instantiate wiring** (~0.5 day). Change TemplateInstantiator to call
  the new templatesApi-equivalent instantiate route (or chain: instantiate
  → entitiesApi.generateEntity for LLM elaboration). Add a "preview" affordance
  resolving variable_properties client-side.

- **(d) Random-table Create button** (~0.5 day). Add Plus button to
  RandomTableEditor toolbar. Inline CreateRandomTableModal. Submit
  randomTablesApi.create; drop user into TableEditor mode on success.

- **(e) Relocation to /forge/templates** (~0.5-1 day, depends on F1-1). Move
  TemplateBrowser + RandomTableBrowser out of pack-detail tab list into
  new app/forge/templates/page.tsx.

- **(f) Tests** (~0.5 day). tests/contracts + tests/api + TemplateBrowser.test.tsx
  + TemplateInstantiator.test.tsx + RandomTableEditor.test.tsx.

**Effort:** M (4-5 days) with F1-1 landed; M-L (5-6 days) without. The plan's
S-M is too low; the Backend (a) instantiate work plus the random-table create
add ~1 extra day the plan doesn't account for.

**Out of scope:** CharacterTemplate (G-6). The entities.py:1194 and
entities.py:1478 save-template endpoints (misnamed, dark — leave for G-6).
```

---

## 11. F3-3 — Multiverse management (verified)

### Finding

The Multiverse schema exists (`universe.py:64-127`) but the router exposes only three endpoints:
- `GET /multiverses` (wired, but returns reduced shape — drops `system_name`, `is_template`, `knowledge_tree_type`, `parent_multiverse_id`)
- `POST /multiverses` (wired but the frontend-facing form only sends `name`, `description`, `tags`)
- `DELETE /multiverses/{mv_id}` (wired, always `force=True` — no non-empty guard)

**Missing endpoints (router-side):**
- `PUT/PATCH /multiverses/{mv_id}` — schema exists but no router. Renaming/describing is unimplemented.
- Move universe between multiverses — no endpoint, schema doesn't even include `multiverse_id` on `UniverseUpdate`.
- Archive multiverse — no schema field, no endpoint.
- Merge multiverses — no endpoint (correctly omitted per product direction).

**Frontend today:** `/worlds` hierarchy tab is the only place multiverses are managed. `CreateMultiverseForm` (`:290-346`) and `CreateUniverseForm` (`:348-440`) live inline. There's no multiverse edit/delete UI, no universe metadata edit UI, no template flag visibility, no move-archive surface.

**Critical UX gap:** `/forge/apply` still tells users to "Create one first in Settings → Worlds" (`apply/page.tsx:360-362`) — that copy is stale after F1-1.

**Critical router gap:** `DELETE /multiverses/{id}` always passes `force=True` (`:212`), so it cascades. The plan calls for a non-empty guard that returns 409 instead.

**Critical frontend gap:** `list_multiverses` returns only `{id, name, description, tags, universe_count, created_at}`. The frontend cannot show `system_name`, `is_template`, `knowledge_tree_type`, or `parent_multiverse_id` without backend changes.

**Path mismatch:** the plan's F3-3 wording targets `/forge/worlds` (single hierarchy surface), not a separate `/forge/multiverses` route. The audit confirms this is the intent.

### Plan-section update: F3-3

```
### F3-3 — Multiverse management — revised (effort M)

**Status (2026-07-23 audit):** Multiverse router exposes only 3 endpoints
(list, create, delete). The list endpoint returns a reduced shape that drops
system_name, is_template, knowledge_tree_type, parent_multiverse_id. There is
no update endpoint, no move-archive surface, no template-flag visibility.
Universe-metadata edit exists in the backend router but the frontend never
calls it. The /worlds hierarchy tab is the only management surface, and it
offers create-only for multiverses and create+delete for universes. Path
intent: a single /forge/worlds hierarchy surface (not /forge/multiverses).

**Goal (revised):** Complete CRUD for multiverse/universe management in the
/forge/worlds hierarchy tab. Safe multiverse deletion (no cascade). Edit
universe metadata. Surface template flags. Fix stale /forge/apply copy.

**Sub-tasks (revised, ~6.5-9.5 dev-days total):**

- **(0) Route and API inventory correction** (~0.5 day). Treat /forge/worlds
  as the target route. Update stale "Settings → Worlds" copy in /forge/apply.
  Resolve the /api/universes double-prefix issue from FORGE_INVENTORY.md §3.1
  before adding new callers.

- **(1) Data/API shape alignment** (~1 day). Expand the frontend-facing
  multiverse response to include system_name, is_template, knowledge_tree_type,
  parent_multiverse_id. Add a multiverse update request schema (name,
  description, optionally system_name). Add PUT/PATCH /multiverses/{mv_id}.
  Add universesApi.updateMultiverse wrapper.

- **(2) Safe multiverse deletion** (~0.5-1 day). Before deletion, count
  universes in the multiverse. If count > 0, return 409. Remove unconditional
  force=True for UI deletion. Tests: empty → 204, non-empty → 409, unknown → 404.

- **(3) /forge/worlds route migration** (~1-2 days, depends on F1-1). Move
  /worlds under /forge/worlds. Keep /worlds as redirect during migration.
  Update sidebar link. Update deep links from /forge/apply and other surfaces.

- **(4) Multiverse row edit/delete UI** (~1-1.5 days). Actions menu on each
  multiverse row: Edit, Delete. Edit form: name, description, optional system
  name. Delete behavior: show contained-universe count, confirmation, reject
  409 cleanly. Invalidate ["multiverses"] and ["universes", multiverseId].

- **(5) Universe metadata edit** (~1 day). Add Edit action to universe detail
  panel. Support name, description, genre (tone only after backend forwarding
  is corrected). Preserve existing delete and Play here. Refresh after save.

- **(6) Template visibility/filtering** (~0.5-1 day). Show Template badge for
  is_template. Add filter: all / playable / templates. Do not add template
  instantiation here.

- **(7) WorldContext and active-selection validation** (~0.5 day). Ensure
  deleting a selected multiverse clears or repairs the persisted WorldContext.
  If deleting a universe, clear the selected universe when it matches.

- **(8) Tests** (~1-1.5 days). Frontend: create, edit, delete (empty +
  non-empty refuse), edit universe metadata, template badge/filter, WorldContext
  cleared. Backend: multiverse update endpoint, non-empty delete → 409,
  empty delete → 204, response includes required metadata, universe update
  preserves multiverse ownership.

**Effort:** M (6.5-9.5 days). Plan's M estimate is right; the API gap
(Phase 1) is non-trivial but bounded. The route migration adds scope if F1-1
hasn't landed.
```

---

## 12. F1-3 — World-creation wizard (verified)

### Finding

Five creation paths exist with divergent UX, all reachable but never unified:

| Path | UI | Backend | What it creates |
|---|---|---|---|
| Blank form at `/worlds` | `worlds/page.tsx:290-440` | `universesApi.createMultiverse`/`createUniverse` | multiverse + universe only |
| QuickStartPanel | `QuickStartPanel.tsx:142-170` | `forgeApi.quickWorld` | multiverse + universe + LLM-generated entities + PC + maybe session |
| OnboardingWizard | `OnboardingWizard.tsx:13-67` | `forgeApi.demoWorld` | pre-curated "Millhaven" multiverse/universe + 5 entities + PC + session |
| Pack → new-world wizard | `apply/page.tsx:231-297` | `ingestApi.applyPackNewWorld` | multiverse + universe (proposals not auto-accepted) |
| Fork at `/snapshots` | `snapshots/page.tsx:197-210` (`window.prompt`) | `universesApi.forkUniverse` | deep clone of entities/facts/relationships |

**Shared primitive:** `QuickWorldBuilder` (`quick_world.py`) is the canonical "build a populated world from a seed" path. Used by both `demo-world` (curated JSON inline) and `quick-world` (LLM-driven). Blank form, pack→new-world, and fork paths bypass it.

**Why each path exists:**
- Demo is deterministic (no LLM needed) for the "0-friction" entry on the home page.
- Quick seed is LLM-driven for "blank page for your own idea."
- Pack→new-world is part of the Apply Pack UX (conflict-resolution on the existing-world side).
- Blank form predates any wizard.
- Fork is a `window.prompt` button in `/snapshots` — bare-bones but working.

**Test gap is severe:** zero coverage for any of the 4 creation endpoints and 4 mutation paths. The plan's F1-3 says "Backend: none" — but the broader wizard work would benefit from at least:
- `packages/ui/backend/tests/test_forge.py` covering `quick_world` and `demo_world`
- `packages/ui/backend/tests/test_universes.py` extended for `fork_universe`
- `packages/ui/backend/tests/test_pack_library.py` (new) for `apply_pack_new_world`

### Plan-section update: F1-3

```
### F1-3 — World-creation wizard — effort M — deps: F1-1

**Status (2026-07-23 audit):** Five creation paths exist with divergent UX,
all reachable but never unified. QuickWorldBuilder is the shared primitive
used by demo-world and quick-world; blank form, pack→new-world, and fork
bypass it. Zero test coverage for any creation endpoint. Path intent is
clear: one front door at /forge/worlds/new with five method cards.

**Goal (revised):** Ship the wizard at /forge/worlds/new with five methods.
Reuse existing forms as the embedded "step 2" body. Keep all existing entry
points (blank form, QuickStartPanel, OnboardingWizard) reachable as
back-compat.

**Sub-tasks (revised):**

- **(a) Shared form extraction** (~0.5 day). Move QuickStartPanel's form
  body into components/forge/worlds/QuickSeedForm.tsx. QuickStartPanel becomes
  a thin wrapper; Ingest Studio mount unchanged.

- **(b) Wizard page** (~1.5 days). New app/forge/worlds/new/page.tsx.
  Step 1 method picker (Blank / Quick seed / From pack / Fork / Demo).
  Step 2 embeds the right form. Step 3 confirm + land on /forge/worlds?universe=<id>.
  Reuse CreateMultiverseForm + CreateUniverseForm as the Blank form (single
  source of truth, hierarchy tab keeps a thin wrapper).

- **(c) Wizard state container** (~0.5 day). useState<Method> + AnimatePresence
  transitions matching /forge/apply.

- **(d) Entry points** (~0.5 day). "New world" Plus button on /forge/worlds
  hierarchy toolbar. Dashboard quick action (F1-2). Architect empty-state CTA.

- **(e) Tests** (~0.5 day). New app/forge/worlds/new/page.test.tsx covering
  method switch + blank submit + From pack router push + Quick seed
  navigation. Optional: test_forge.py covering quick_world and demo_world;
  test_universes.py extended for fork_universe; new test_pack_library.py
  for apply_pack_new_world.

**Effort:** S (a) + M (b) + S (c) + S (d) + S (e) = M (~3 days). Plan's M is
right. The plan's "Backend: none" underestimates the test gap; the four
endpoints have zero coverage and the wizard PR is a natural place to add
backend tests.

**Out of scope (per plan):** seed_universe (F1-5(b)), conflict resolution
(already in /forge/apply), EntityTemplate authoring (F3-2), canonizePack
collapse (F1-6).
```

---

## 13. Coverage gap roll-up after Tier 3 rounds 1-3

The Tier 3 explorations collectively surface **eight concrete test gaps** that span the plan's surface area. The honest read is that the plan's backend test surface is light. None of the following have any backend test:

- `templates.py` router (5 endpoints)
- `universes.py` multiverse operations (multiverse update, safe delete)
- `universes.py` fork_universe
- `universes.py` apply_pack_new_world (the 5 snapshot endpoints are also broken, but the wizard path is independent)
- `forge.py` quick_world and demo_world
- `lorebook.py` 4 dark endpoints
- `tone.py` 13 dark endpoints
- `random_tables.py` 2 dark endpoints (create, get-by-id)

For each F1.x / F2.x / F3.x item, the explorations added concrete test debt. The plan's existing test guidance ("frontend test for the wizard; backend: none") underestimates this. The recommended adjustment is to add **1 backend test file per F1.x / F2.x / F3.x item**, scoped to the new endpoints introduced by that item. Cumulative cost: ~5-8 test files, ~1 day total, but with significant long-term confidence.

---

## 14. Re-sequencing after Tier 3 rounds 1-3

The 13-item priority list (FORGE_EXPANSION.md §9) is correct. The new findings from this round adjust the **target surfaces** but not the order:

- **F3-2** (template authoring) belongs after F1-1 (creates the route) and after F2-1 (workbench). New sub-tasks (a) backend holes + (c) instantiate wiring are blocker-free.
- **F3-3** (multiverse management) belongs after F1-1 (route consolidation). Phase 1 (data/API shape alignment) is the most-felt gap; Phase 2 (safe deletion) is the safety-critical one; Phase 3 (route migration) depends on F1-1.
- **F1-3** (world-creation wizard) belongs after F1-1. (a) form extraction can land in parallel. The wizard is a consolidation that becomes natural once the other pieces are in place.

**Latest dependency map for Phase 1:**
- F1-1 → (F1-3, F1-5, F3-3)
- F1-1 → (F1-2, F1-4, F3-2)
- F1-4 → F2-3 (F1-4 lifecycle corrections are F2-3's blocker)
- F2-4(a) → F2-4 (contract repair first)
- F1-5(a) → F3-4.0/4.1 (ToneTab dedup is F3-4's prerequisite)

**Tier-3 round total: 9 explorations, ~25 dev-days of finding → ~22-25 dev-days of follow-up work planning.** The exploration was cheap; the work is bounded.

---

## 15. F1-2 — Forge overview dashboard (verified)

### Finding

The current `/forge` is an overloaded 1,941-line page (pack library + sources + assets + templates + random tables + ingest entry + pack detail tabs). The plan's stated goal is `/forge` becomes a fast, attention-first authoring front door. The current hub's only "overview" signal is a `review_pending` pack count chip (`forge/page.tsx:917-920`). There is no `StatsLine`, no aggregate dashboard, no jobs/health on the front door.

**Data contradictions/unreliable endpoints (the audit pulls at the plan's seams):**

- **`/api/jobs/health` drops 6/13 valid statuses** (`StatusCounts` only exposes `pending`, `running`, `failed`, `completed`, `partial`, `flagged_duplicate`, `blocked_provider`). The dropped statuses are `indexing`, `analyzing`, `failed_non_retryable`, `backing_off`, `cancelled`, `killed`. The dashboard MUST not interpret absence as zero. Derive the dashboard's active/failed/stale set from the full `/jobs` list, not from health alone.

- **No global pending-proposals endpoint.** The plan's "Compose pending-proposal count client-side from per-pack proposal summaries and story queue `total_pending`" is N+1: each pack needs a separate `/api/ingest/packs/{id}/proposals` call, and the story queue requires a `story_id` enumeration. Recommendation: relabel the card **`Packs awaiting review`** (count of packs with `status=review_pending`).

- **Dashboard links to packs/reviews are unreliable until F2-4/F1-4 fixes land.** `_job_to_dict` drops `pack_id`, `total_attempts`, `failed_sections`. The current `IngestionJobsList` "View Result" links to `/forge?pack=...` which defaults to Sources mode. The fix: `/forge/editor?pack=<id>` (per F2-4 expansion) — but **only safe after F2-4 contract repairs**.

- **No active-sessions endpoint.** Chat sessions have no lifecycle; `PlaySession` has `status=active` but is a separate record. Use "Recent sessions" or explicit "Active PlaySessions," not generic.

- **No coverage endpoint.** F2-1 workbench data is Architect-only. Show a "Coverage gaps" teaser/link to Architect — don't display a fake score.

- **No server-side "last visited" record.** WorldContext is browser-localstorage only. Highlight "Selected world" (from `WorldContext`); don't imply server-wide last visit.

- **Change-log lacks `universe_id`/`pack_id`** (`change_log.py:69-127`). Only supports global timeline or per-subject timeline. Don't try to build a per-universe activity timeline.

**User mental model (returning author):**
1. What's running? (jobs, optionally PlaySessions)
2. What's broken or blocked? (failed/stale jobs, queue lock, backend degraded)
3. What needs a human decision? (packs awaiting review)
4. What's missing? (coverage gaps — link to Architect)
5. What's new? (recent completed jobs, recent canon commits — label sources separately)
6. Where do I resume? (selected world + 3 recent worlds)

**Scope guidance:** the dashboard is **operational**, not analytical. No charts. Use stat tiles + tables/lists. Pair status colors with text/icons for accessibility.

### Plan-section update: F1-2

```
### F1-2 — Forge overview dashboard + wire jobs/health — effort M (3–4 dev-days core; M/S-M 4–6 days honest) — deps: F1-1

**Status (2026-07-23 audit):** The current /forge is an overloaded 1,941-line
page. The plan's "pending canon proposals" card is N+1 (no global endpoint).
`/api/jobs/health` drops 6/13 statuses. Dashboard links to packs/reviews are
unreliable until F2-4/F1-4 fix `_job_to_dict` and the by-ingest review path.
The dashboard is operational, not analytical — no charts, use stat tiles +
tables.

**Goal (revised):** `/forge` is a fast, attention-first authoring front door.
Show workspace world/pack/job state, make health and human review visible,
give one-click entry into every Forge workflow. Don't duplicate
`/forge/packs`, `/forge/ingest`, or `/forge/review`.

**Sub-tasks (revised):**

- **(1) Dashboard shell and final-route links** (~0.5-1 day). New
  `app/forge/page.tsx` after F1-1. Header + selected-world context + KPI card
  row + attention strip + jobs attention table + recent worlds/packs + quick
  actions. Preserve `?universe`/`?pack` deep-link semantics from F1-1.

- **(2) Typed data hooks and query keys** (~0.5 day). Add `jobsHealthApi.health()`,
  `JobsHealthResponse`. Query `universesApi.listUniverses()`,
  `ingestApi.listPacks()`, `ingestApi.listJobs()`, and health in parallel with
  independent loading/error boundaries. Poll jobs 5-10s, health 15-30s.

- **(3) World/pack cards** (~0.5-1 day). Highlight WorldContext's selected
  universe. "View all" links to `/forge/worlds` and `/forge/packs`.

- **(4) Jobs attention table** (~0.75-1 day). Derive complete live/failed/stale
  sets from the full `/jobs` list (NOT from health). Render top 3-5 active/
  failed/stale jobs with stage/progress/error. Add Re-run source / Cancel /
  Unlock actions (existing endpoints). Treat placeholders/non-UUID safely.

- **(5) Pipeline health chip** (~0.25-0.5 day). Map `/jobs/health` states:
  unreachable, watchdog disabled, running/healthy, stale jobs, failed/blocked
  counts. Include `generated_at`. Distinguish "healthy" from "watchdog disabled".
  Mount the same chip in `/forge/ingest`.

- **(6) Review card** (~0.5 day core; +1-2 days for true aggregate). Relabel
  plan's "pending canon proposals" as **Packs awaiting review** (count of
  packs with `review_pending`). Do NOT claim total proposals. If product
  requires true global count, add separate backend `GET /api/canon-review/summary`
  endpoint (+1-2 days and backend tests).

- **(7) Quick actions and resume** (~0.25 day). New world
  `/forge/worlds/new`; Upload `/forge/ingest`; Architect `/forge/architect`;
  Open selected/newest world; Demo secondary.

- **(8) Tests and accessibility** (~0.5-1 day). `app/forge/page.test.tsx`:
  cards, selected-world highlight, status mapping, health states, links/
  actions, empty/error partial failure. Add small `jobs_health` backend
  contract test. Status must use icon+text, keyboard focus, table/list fallback.

**Effort:** M (3-4 days) for the constrained core. M/S-M (4-6 days) honest
if the dashboard needs to deliver an honest all-status health chip, real
pending-proposal total, and robust job output links. The latter requires
F2-4(a) (job visibility contract) and F1-4 (by-ingest review) to land first.

**Soft dependencies:**
- F1-1 (hard; route consolidation)
- F2-4(a) (job visibility contract; for honest job output links)
- F1-4 (by-ingest review; for honest review card cross-references)

**Out of scope:** No chart. No coverage percentages (link to Architect).
No "last visited" UI claims (highlight selection instead). No active-
sessions dashboard (use recent sessions or explicit PlaySession labels).
```

---

## 16. F3-1 — Pack composition UX (verified)

### Finding

F3-1 is **not** a new build system. The composition verbs are all shipped today:
- **Merge** (`POST /api/ingest/packs/merge`, `pack_library.py:709-828`) — dedupes 10 collection types by normalized key, no preview, no conflict model, no `parent_pack_ids` set.
- **Clone** (`POST /api/ingest/packs/{id}/clone`, `pack_library.py:1079-1122`) — copies most fields, sets immediate parent, but loses `source_document_ids`, `intro_text`, `plot_threads`.
- **Slice** (`POST /api/ingest/packs/{id}/slice`, `pack_library.py:1142-1188`) — backend supports 10 collections; frontend exposes only 3 (entities, axioms, lore facts).
- **Export** (`GET /api/ingest/packs/{id}/export`) — emits `PackExportEnvelope` (no `schema_version`).
- **Import** (`POST /api/ingest/packs/import`) — requires `schema_version`. **An export-then-import round-trip is currently broken** — the envelope is incompatible.
- **Apply** (`POST /api/ingest/packs/{id}/apply/new-world`, `/apply/{universe_id}`) — separate from composition; in F1-6 scope.

**Multiple inline composition UIs exist:**
- `PackLibrary.tsx:113-177` batch bar (merge, export, clone, slice)
- `app/forge/page.tsx:372-498` merge modal (with name + strategy)
- `app/forge/editor/page.tsx` partial slice-only picker (only 3/10 collections)
- `app/forge/page.tsx:1489-1496` apply wizard link

**Correctness gaps found (in addition to the plan's scope):**
- **Merged packs have no `parent_pack_ids`** (`pack_library.py:799-828` omits them). Lineage is silently broken.
- **Export/import envelope mismatch** — `PackExportEnvelope` lacks `schema_version` (`knowledge_packs.py:764-768`); import requires it (`pack_library.py:979-994`).
- **Clone loses `source_document_ids`, `intro_text`, `plot_threads`** (`pack_library.py:1089-1118`).
- **Slice UI exposes 3/10 collections** — relationships, tables, agendas, topology, tone profiles, character profiles, generation templates are not selectable.
- **Zero backend tests** for merge/clone/slice/export/import/apply behaviors. Only `tests/test_pack_library_locking.py:45-74, 209-213` covers clone-while-locked.

**Plan intent (`FORGE_MODE_PLAN.md:572-597`):** merge dry-run preview + lineage display + optional two-pack diff. F3-1 is precision and lineage polish, not a new composition data architecture.

### Plan-section update: F3-1

```
### F3-1 — Pack composition UX — effort M — deps: Phase 1 canonical pack surface

**Status (2026-07-23 audit):** All composition verbs are shipped. F3-1 is
polish and correctness. Adjacent correctness gaps found: merged packs have
no lineage, export/import envelope mismatch (round-trip broken), clone
loses 3 fields, slice UI exposes only 3/10 collections, zero backend tests.

**Goal (revised):** Make composition predictable before persistence and make
derived pack lineage understandable after persistence.

**Sub-tasks (revised, ~4-6 dev-days core):**

- **(1) Canonicalize the frontend entry point** (~0.5 day). After Phase 1
  identifies `/forge/packs` as canonical, reuse one MergeModal from both
  pack-list selection and pack detail. Do not add preview behavior to both
  the legacy `PackLibrary.tsx` and the canonical page.

- **(2) Factor a pure backend composition function** (~1 day). Extract merge
  metadata and deduplication from `pack_library.py:709-828`. Return would-be
  metadata, per-collection input/output counts, duplicate groups and selected
  winner, source pack IDs, warnings for incompatible metadata.

- **(3) Add merge dry-run/preview** (~0.5-1 day). Add `dry_run: bool = False`
  to `MergePacksRequest`. `dry_run=true` performs validation and composition
  but does NOT call `mongodb_create_knowledge_pack`. Preview response must
  clearly distinguish preview data from a persisted KnowledgePack.

- **(4) Merge preview UX** (~1-1.5 days). Debounced/request-on-selection preview
  in MergeModal. Show each source pack, output counts, removed duplicate
  counts, winner rules. Show warnings before confirmation. Refresh preview
  on order/strategy change (first_wins is order-sensitive). Batch-bar Merge
  opens this modal rather than persisting immediately.

- **(5) Finish lineage semantics and display** (~0.5-1 day). Set merged pack
  `parent_pack_ids` to all direct source packs. Preserve current
  immediate-parent behavior for clone and slice. Replace the anonymous
  `lineage` badge at `forge/page.tsx:1450` with parent names and links.
  Handle archived/missing parents. A compact lineage drawer may show direct
  parents and direct children.

- **(6) Composition contract cleanup** (~0.5-1 day, required or split into a
  prerequisite bug-fix PR). Add `schema_version="1.0"` to `PackExportEnvelope`;
  prove exported files can be imported unchanged. Define and test which
  pack-level fields clone, slice, merge, and import preserve. Audit
  `intro_text`, `source_document_ids`, `plot_threads`, embedded profiles/system
  data, evidence artifacts. Decide whether slice should preserve source
  provenance and game-system linkage.

- **(7) Tests** (~1 day). Backend: dry-run writes nothing; dry-run and
  persisted composition have identical item/count decisions; dedup keys for
  every supported collection; first_wins ordering; longest_description
  behavior and intended collection scope; merged-parent lineage; clone/slice
  preservation contract; export → import round-trip. Frontend: batch Merge
  opens preview rather than immediately POSTing; preview refreshes on
  selection/order/strategy; confirmation persists once; lineage parent links
  render; slice controls expose only intentionally supported collections.

- **(8) Optional pack diff** (~1-2 days, cut first). Compare two fetched packs
  client-side by the same normalized keys used by merge. Show added/removed/
  changed. Keep read-only.

**Effort:** 4-6 dev-days core (M). 6-8 days if optional diff and full
contract cleanup are included.

**Out of scope:** No drag-and-drop composition canvas. No meta-packs. No
immutable PackVersion schema. No branch names/merge bases/rebase. No
snapshot-aware editing. No proposal review redesign. No world apply
conflict detection (that's F1-6 step 1).
```

---

## 17. GM P3.2 — Notes→canon review linkage (verified)

### Finding

The plan offers two options for P3.2:
- **(a) Document as-is** (S, recommended for now) — add a hint line under the scratchpad Ingest button ("Proposals land in Forge → Review").
- **(b) Thread story_id** (M) — proposal attribution becomes dual (recording story + ingest job).

**The audit's recommendation: option (a).** Reasoning:

- **Pipeline currently has no story context.** The scratchpad ingest call (`page.tsx:363-372`) builds a `Blob`/`File` and calls `ingestApi.uploadSource(file, { scan_type, analysis_layers, multiverse_id, title })` — no `story_id`. The backend upload endpoint (`ingest.py:719-731`) accepts `multiverse_id`, `title`, `scan_type`, `analysis_layers`, `new_setting_name`, `new_setting_system` — but **not `story_id`**. The pipeline (`ingestion_pipeline.py:391-418`) stores bytes, creates a Neo4j `Source` + Mongo `Document`, calls `IngestionPipeline.ingest_file(..., multiverse_id, ...)` — **no story_id** anywhere on the path.

- **Proposals are not created inline by the pipeline.** The pipeline calls `analyzer` and `_auto_canonize` (`ingestion_pipeline.py:570-590, 620-640`). `_auto_canonize` (`canonkeeper.py:842-949`) calls `bulk_enqueue_proposals` (`canonkeeper.py:576-624`) which writes `source='ingestion_job:<job UUID>'` and `status='pending_review'` (an invalid `ProposalStatus` enum value — F2-3's bug). The ingest path does NOT call `ProposedChangeCreate` directly, so adding `story_id` to the upload form doesn't propagate.

- **The story queue ignores proposals without `scene_id`.** `canon_review.py:162-165` only groups proposals into scene cards if they have non-null `scene_id`. Ingest proposals have no `scene_id`. So even if `story_id` were threaded, story queue would not display them unless `scene_id` were also wired.

- **Scene-runtime proposals are the existing pattern.** `PersistenceService` calls `ProposedChangeCreate(scene_id, story_id, turn_id, ...)`. The schema (`proposed_changes.py:68-76`) supports `scene_id` and `story_id`. So the schema is ready; the pipeline is what's missing.

- **Mapping ingest proposals to scenes is non-trivial.** Ingest runs offline; it doesn't know which scene/turn a recording will be at. The mapping would be a separate product decision (e.g., tie ingest to active session, or treat ingest as standalone).

- **Option (b) cost is more than 3 one-line changes.** Schema already supports `story_id`. Plumbing must traverse: `Notebook ingest → uploadSource → upload endpoint → _run_ingest_in_thread → IngestionPipeline.ingest_file → analyzer → _auto_canonize → bulk_enqueue_proposals`. Each hop needs the `story_id` param added. And, separately, the story queue needs proposals to carry `scene_id` (or a new "ingested without scene" grouping).

- **Risk: dual-queue duplication.** If `story_id` is threaded, ingest proposals appear in both the story queue AND the ingest queue. Users see the same proposal twice. The plan section doesn't address this.

### Plan-section update: P3.2

```
### P3.2 · Notes→canon review linkage — effort S — deps: P2.3

**Status (2026-07-23 audit):** Option (a) is the right call. Option (b)
requires more than 3 one-line changes: pipeline has no story context; ingest
proposals don't carry scene_id; story queue ignores proposals without scene_id
(`canon_review.py:162-165`). Risk: dual-queue duplication if both story_id
and source are populated.

**Goal (revised):** Make the scratchpad → ingest flow's destination obvious to
the user. Defer proposal attribution to a future product decision (separate
review or "tie ingest to active session").

**Implemented (option a):**
- Add a hint line under the Ingest button in the scratchpad toolbar
  (`page.tsx:379-387`): "Proposals land in Forge → Review".
- Optionally a `<Tooltip>` on the Ingest button with the same copy.
- Update the status bar (`:409-419`) to reference "Forge → Review" alongside
  the existing "Queued for ingestion" line.
- Frontend test: `page.test.tsx` asserts the hint text + tooltip renders.

**Effort:** S (1-2 hours, included in P3.3 PR).

**Out of scope (deferred):**
- Threading `story_id` through the ingest pipeline. Revisit when product
  decides whether tied ingest (recording-scoped) is wanted.
- A "scenario": if a future product decision is "ingest-proposals-appear-in-
  story-queue", the plumbing is: schema already supports it; pipeline
  needs `story_id` plumbing; analyzer needs to know `scene_id` (or story
  queue needs an "unscened" lane); ingest queue needs a "linked story"
  filter to avoid duplicate display.
- Until then, the hint line is honest.
```

---

## 18. Tier-3 round 4 — re-sequencing and final summary

**Latest priority list (after 4 rounds of exploration):**

| Priority | Item | Effort | Status |
|---|---|---|---|
| 1 | **F1-5(e)** fix 6 snapshot/seed BROKEN endpoints | 0.5 day | ✅ DONE 2026-07-24 |
| 2 | **F1-6 step 1** restore conflict detection in `apply_pack_existing_world` | 1 day | ✅ DONE 2026-07-24 |
| 3 | **F2-4(a)** job visibility contract repair | 1 day | ✅ DONE 2026-07-24 |
| 4 | **F1-4** 5 lifecycle corrections (enqueue, status, lineage, contract, commit) | 2-3 days | ✅ DONE 2026-07-24 |
| 5 | **F2-3** canon-review triage | 4-7 days | ✅ DONE 2026-07-24 (a-d, f; e deferred w/ G-9) |
| 6 | **F1-1** route consolidation | 1 week | ✅ DONE 2026-07-24 |
| 7 | **F3-4.0/4.1** ToneTab dedup + lift | 1.5 days | ✅ DONE 2026-07-24 (incl. F1-5(a)) |
| 8 | **F1-2** dashboard | 3-6 days | ✅ DONE 2026-07-24 |
| 9 | **F1-3** world-creation wizard | 3 days | ✅ DONE 2026-07-24 |
| 10 | **F1-5 (a, b, c) + F1-6 (collapse PackLibrary)** | 3 days | ✅ DONE 2026-07-24 |
| 11 | **F3-4.2-4.4** libraries, tags, lorebook in Forge | 5.5 days | ✅ DONE 2026-07-24 |
| 12 | **F2-1** workbench | 2-3 weeks | ✅ DONE 2026-07-24 (coverage API + panel) |
| 13 | **F2-2** ontology management | 2-3 weeks | ✅ DONE 2026-07-24 (CRUD API + /forge/ontology + explorer edges + NPC profiles) |
| 14 | **F3-2** template authoring UI | 4-6 days | ✅ DONE 2026-07-24 |
| 15 | **F3-3** multiverse management | 6.5-9.5 days | after F1-1 |
| 16 | **F3-1** pack composition UX | 4-6 days | after Phase 1 |
| 17 | **F3-1, F3-2, F3-3** remaining | 3 weeks | sequential after Phase 2 |
| 18 | **P3.1** audio/hybrid descope | 15 min | doc stub |
| 19 | **P3.2** hint line | 1-2 hours | in P3.3 PR |
| 20 | **P3.3** recording archive metadata | 1 day | P1.4 dependency met |

**GM plan now fully closed** (P3.1 descope + P3.2 hint + P3.3 archive metadata = small PR).

**Forge plan has 18 work items** with realistic effort estimates (~6-12 months solo, depending on depth). The 4-6 hidden correctness bugs (F1-5(e), F1-6 step 1, F2-4(a), F1-4 lifecycle, F3-1 export/import) are now in the priority list as P0/P1.

**Total Tier-3 exploration (4 rounds, 12 explorations):**
- ~33 dev-days of finding
- ~30-35 dev-days of follow-up work planning
- 18 priority items identified with realistic effort
- 12 new bug fixes surfaced (4 BROKEN endpoints, 6 dark endpoints via F1-5, F2-4 contract bugs, F2-3 reason-drop, F1-4 lifecycle, F3-1 export/import envelope)

The exploration found far more concrete bugs than the plan anticipated. Half of the priority list is now "fix the bug" rather than "build the feature".

### Addenda (peer agent corrections worth recording)

**F1-2 review card caveat (peer addendum):** Until F1-4's by-ingest lifecycle bugs are fixed (unreachable auto-canonize branch, invalid `pending_review` status, no job attribution causing unrelated pending proposals to be misattributed, no by-ingest commit path — see `FORGE_EXPANSION.md §6`), the dashboard must use the conservative "packs awaiting review" signal and avoid presenting by-ingest proposal totals as authoritative. The revised F1-2 plan section §15 already reflects this: "Do NOT claim total proposals."

**F1-2 endpoint inventory (peer addendum):** additional endpoints that the dashboard could surface but aren't named in the planned IA:
- `GET /api/ingest/sources` — recent sources ambient row (capped at 100 jobs before dedup)
- `GET /api/ingest/assets` — only if asset count is desired
- `GET /api/stories?universe_id=` + `/api/stories/{id}/scenes` — future per-universe "recent story" row
- `GET /api/play-sessions?universe_id=&status=` — distinct from `/api/chat` sessions
- `GET /api/databases` and `/api/performance` — drilldown, not dashboard KPIs
- `GET /api/health?deep=true` — already wired via `ConnectionStatus`

There is no generic `/events`, `/activity`, `/active-ingests`, `/active-sessions`, `/pending-proposals/summary`, `/coverage`, or `/seed-attempts` route. The only real-time transports are per-job SSE and per-chat WebSocket.

**F1-2 test gap (peer addendum):** Currently no Forge-specific frontend `*.test.tsx`/`*.test.ts` files exist under `packages/ui/frontend/src`. The F1-2 `app/forge/page.test.tsx` is genuinely new, not an extension of an existing pattern; it should mock React Query/API independently and cover partial query failures (some cards succeed, some fail). This is reflected in the §15 sub-task (8).
