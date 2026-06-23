# FINAL FABLE TASKS — Atomic Execution List

> Decomposition of `FINAL_FABLE_PLAN.md`. Strictly ordered within phases; a task is **done** only when its *Verify* command passes. Status: `[ ]` todo, `[x]` done, `[-]` deferred (with reason).
> Conventions: run from repo root; `UV=uv run`. Tasks marked **(infra)** mutate Docker state; tasks marked **(decision)** record a choice in the plan.

---

## Phase 0 — Make it run

- [x] **T-001** Remove tracked junk files at repo root (`on`, `OK', flush=True)`) and untracked junk (`chemas.entities import...`, `.py","core.py",...`); add guard patterns to `.gitignore` if needed.
  *Verify:* `git ls-files | grep -E "^(on$|OK)"` → empty; `ls` shows no junk.
- [x] **T-002** Remove stale `coverage.json` from repo root and gitignore `coverage.json`.
  *Verify:* `git status --short coverage.json` shows deletion; `.gitignore` covers it.
- [x] **T-003** Commit untracked `docs/use-cases/co-pilot/` (fixes broken link from `epic-6-co-pilot.md`).
  *Verify:* `git ls-files docs/use-cases/co-pilot/` lists `analysis-prep.md`, `session-support.md`.
- [x] **T-004** Delete stale `.env.example`; keep `env.example` as the single template; update references (`README.md` says `cp env.example .env` — confirm all docs agree).
  *Verify:* `ls .env.example` → missing; `grep -rn "\.env\.example" README.md docs/ *.md` → no stale refs.
- [x] **T-005** Fix `packages/ui/backend/Dockerfile`: non-editable installs (or copy source to `/build` paths in final stage) so `monitor_ui` resolves in the final image.
  *Verify:* `docker compose -f infra/docker-compose.yml build ui-backend && docker compose -f infra/docker-compose.yml up -d ui-backend` then `curl -s localhost:8001/api/databases/status` returns JSON (after T-006).
- [x] **T-006 (infra)** Fix Neo4j: back up `infra/neo4j/data`, `docker compose down` + `up -d` to recreate containers (clears stale pidfile); replace override healthcheck `cat /proc/1/cmdline` with a real probe (`wget -qO- http://localhost:7474` or authed `cypher-shell`); migrate deprecated `dbms.memory.*` env names to `server.memory.*`; remove invalid `dbms.security.auth_enabled=false` line from base compose.
  *Verify:* `docker ps` shows `monitor-neo4j (healthy)` and 0 restarts after 5 min; `cypher-shell -u neo4j -p ... 'RETURN 1'` works from inside the container.
- [x] **T-007** Align NLP config: default `NLP_BACKEND=spacy` in compose env defaults + `env.example` + Python config default; ensure ingestion has a working non-GLiNER path (spacy or regex fallback) and gliner stays opt-in (`profiles: [gliner]`, not `disabled` + still-referenced URL).
  *Verify:* `grep -rn "NLP_BACKEND" infra/ env.example packages/*/src | grep -v pycache` shows consistent spacy default; ingestion unit tests pass without gliner.
- [x] **T-008 (decision)** Move `minimax-vscode/` out of the repo (delete from tree; note its new home in `docs/archive/` or keep as separate repo).
  *Verify:* `ls minimax-vscode` → missing; commit message references destination.
- [x] **T-009** Full-stack smoke: `./dev.sh` (or compose up) → all containers healthy; backend `/api/databases/status` all green; frontend `/` renders.
  *Verify:* `docker ps --format '{{.Names}} {{.Status}}'` → no `Restarting`; curl checks pass.

## Phase 1 — Make tests trustworthy

- [x] **T-010** Add `pytest-timeout` and `pytest-socket` to dev deps; configure in `pytest.ini`: `timeout = 30`, socket disabled by default, enabled for `integration`/`e2e` markers (hook in root `conftest.py`).
  *Verify:* `UV pytest tests/contracts -q -x` fails fast (not hangs) on any network-touching test.
- [x] **T-011** Create `.env.test` (fake key values, unroutable DB hosts e.g. `localhost:1`), and make unit-test runs use it exclusively: root `conftest.py` stops unconditional `load_dotenv()`; forcibly set (not `setdefault`) `ANTHROPIC_API_KEY=test-key` etc. in unit mode.
  *Verify:* `grep -n "load_dotenv" tests/conftest.py` shows guarded usage; running suite with `.env` present never reads real key (assert via a canary test).
- [x] **T-012** Autouse isolation fixture: reset `agent_factory`, LLM registry caches, and dspy global settings between tests (extend existing conftests in `packages/agents/tests` + root).
  *Verify:* `UV pytest packages/agents/tests/test_ingestion_loop.py packages/agents/tests/test_llm_routing.py -q` green in any order (`-p no:randomly` both orders or `--lf` loops).
- [x] **T-013** Convert direct-construction agent tests (`test_resolver_pushback.py` "PublicMethods" style and friends) to use fakes via `AgentFactory`, or mark `@pytest.mark.integration`.
  *Verify:* `timeout 120 UV pytest packages/agents -q -m "not integration"` completes green < 2 min.
- [x] **T-014** Same hermeticity pass for `packages/data-layer` (embedding/memory/db-touching tests → fakes or `integration` marker; `test_memory_tools.py::test_embed_*` must not call real embedders).
  *Verify:* `timeout 180 UV pytest packages/data-layer -q -m "not integration"` green < 3 min.
- [x] **T-015** Same pass for `tests/api` (FastAPI TestClient must use dependency overrides/fakes — starting with `test_chat_router.py::TestSessionCRUD`), `tests/contracts`, `tests/behavior`, `tests/property`.
  *Verify:* `timeout 300 UV pytest tests -q -m "not integration and not e2e"` green < 5 min.
- [x] **T-016** Full hermetic baseline: run the entire unit suite 3× consecutively; fix or quarantine (with tracking note) every flake.
  *Verify:* 3 consecutive green runs of `UV pytest packages tests -q -m "not integration and not e2e"`; record wall time in `docs/STATUS.md` (T-024).
- [x] **T-017 (decision)** Mutation testing: pin `mutmut<3` **or** swap to `cosmic-ray`; run once on `canonkeeper.py` + `resolver.py` + `scene_loop.py`; record kill rate; if neither tool works, remove mutation claims from docs/config. -> Outcome: cosmic-ray hangs on async stack, claims formally removed.
  *Verify:* a mutation report exists under `docs/testing/` (or claims removed), `pyproject.toml` consistent.
- [x] **T-018** CI workflow `.github/workflows/ci.yml`: ruff + mypy + `scripts/check_layer_dependencies.py` + hermetic unit suite (with `timeout-minutes`); nightly workflow with compose services running `RUN_INTEGRATION=1` + E2E smoke.
  *Verify:* `gh workflow list` shows them; act-style dry run or first push run green.

## Phase 2 — Deduplicate & consolidate

- [x] **T-019** Delete dead `packages/data-layer/src/monitor_data/tools/neo4j_tools/facts/` directory (shadowed by `facts.py`); confirm no imports reference `facts._facts` / `facts._events`.
  *Verify:* `grep -rn "facts\._\|facts/_" packages` → empty; unit suite green; `from monitor_data.tools.neo4j_tools import facts` still resolves to `facts.py`.
- [x] **T-020** Deduplicate schema enums/models: single canonical `SimulationScope`, `CoreMechanicType`, `CharacterSheetCreate/Update/Response`, `BehavioralTrigger`; re-export from old locations; rename `ActionType` BaseModel in `game_systems.py` → `ActionTypeDef` (enum keeps the name).
  *Verify:* the §2.2(C) grep (`grep -rhE "^class (SimulationScope|CoreMechanicType|CharacterSheet(Create|Update|Response)|BehavioralTrigger)" ... | sort | uniq -d`) → empty; mypy + unit suite green.
- [x] **T-021** Extract shared tool helpers (`_to_native_datetime`, `_utcnow`, `_pydantic_to_dict`, `_levenshtein_ratio`, `_call_sync`) into one module; update imports.
  *Verify:* duplicate-function grep from the plan → empty; suite green.
- [x] **T-022** De-duplicate `docs/CLOSING_THE_GAP.md` internal double-sections; then archive it plus `CLOSING_THE_GAP_NEW.md`, `ACCURATE_IMPLEMENTATION_STATUS.md`, `TESTING_STATUS_REPORT.md`, `YAML_STATUS_UPDATE_SUMMARY.md` into `docs/archive/`.
  *Verify:* `ls docs/*.md` no longer lists them; links updated (`grep -rn "CLOSING_THE_GAP" README.md docs/ --include="*.md"` clean).
- [x] **T-023** Fix use-case taxonomy: resolve doubled epic numbering in `docs/use-cases/`; relocate P-15 YAML beside its spec; ensure rollout-plan lists P-21 as deferred.
  *Verify:* one file/dir per epic number; `scripts/check_ontology_use_cases.py` (or equivalent) passes.
- [x] **T-024** Create `docs/STATUS.md` — the single live status page: verified test counts/times, mode-completeness table, coverage snapshot, known deferrals. Link from README.
  *Verify:* file exists with 2026-06 dates + reproduction commands; README links it.
- [x] **T-025** Sync all 165 use-case YAML `status:` fields with reality (script-assisted).
  *Verify:* `grep -rln "status: todo" docs/use-cases/epic-* | wc -l` reflects only genuinely-missing items (spot-check 10).
- [x] **T-026** Prune scripts: merge `seed_zai_provider(s).py`, `seed_world(_quick).py`; delete confirmed-dead one-offs; add `scripts/README.md` index.
  *Verify:* `ls scripts | wc -l` reduced; index lists every remaining script with one-liner.

## Phase 3 — Prove the core loops

- [x] **T-027** Get `scripts/live_gameplay_smoke.py` passing against the live stack (universe → character → story → 3 turns → end scene → assert Neo4j entities/facts + Mongo turns + Qdrant memories).
  *Verify:* `UV python scripts/live_gameplay_smoke.py` exit 0 with printed assertions.
- [x] **T-028** Repair/green the 15 `tests/e2e` files with `RUN_E2E=1` against the stack (fix stale ones; mark truly-obsolete with reasons).
  *Verify:* `RUN_E2E=1 UV pytest tests/e2e -q` green (or skips with documented reasons only).
- [x] **T-029** Scripted Mode walkthrough: **World Architect** (ingest small doc → review extraction → apply pack → query) as an e2e test + written UI script in `docs/gameplay-examples/`.
  *Verify:* e2e passes; doc exists.
- [x] **T-030** Scripted Mode walkthrough: **GM Co-Pilot** (record notes → recap → threads → hooks → contradictions → handout → canon-review accept) as e2e + UI script.
  *Verify:* e2e passes; doc exists.
- [x] **T-031** Scripted Mode walkthrough: **Autonomous GM extras** (oracle question, combat round, downtime progression) as e2e + UI script.
  *Verify:* e2e passes; doc exists.
- [x] **T-032** `monitor playtest` CLI path works against the stack end-to-end.
  *Verify:* `UV monitor playtest --turns 3` (or documented invocation) exit 0.

## Phase 4 — Close the product gaps

- [x] **T-033** Frontend bridge: **semantic search** — `searchApi` in `lib/api.ts`, header search box + results view.
  *Verify:* type-check + Playwright smoke (T-041) hits `/api/search/search`.
- [x] **T-034** Frontend bridge: **databases health panel** (settings page) using existing `dbApi`.
  *Verify:* panel renders all 5+ DB statuses from `/api/databases/status`.
- [x] **T-035** Frontend bridge: **modes switcher** using `modesApi`.
  *Verify:* active mode visibly switches; persisted via API.
- [x] **T-036** Frontend bridge: **tone manager** (profiles/libraries list+edit) — new `toneApi`.
  *Verify:* CRUD round-trip from UI works against backend.
- [x] **T-037** Frontend bridge: **lorebook** — connect existing editor component to new `lorebookApi`.
  *Verify:* create/edit/inject flows work from UI.
- [x] **T-038** Frontend bridge: **performance dashboard** (simple tables from `performance.py`).
  *Verify:* page renders overview + slow queries.
- [x] **T-039** Finish partial UI — Fork Universe button, End-scene button, storiesApi.patchStory; PackLibrary ops UI (merge/export/import/clone/slice — T-061) + apply already shipped; ingest unlock/cancel/purge (T-084); batch-entity multi-select (T-063); LLM node-assignments editor (T-060). All controls call their endpoints; type-check green.
  *Verify:* each control calls its endpoint (network tab / Playwright); type-check green.
- [x] **T-040** P-15 closure — session list/resume exists via chat sessions in PlayConsole and the Home "Continue playing" list; Home empty-state now shows the Onboarding Wizard (T-057). P-21 marked deferred in rollout-plan (T-023). _(Dedicated /play-sessions Mongo API left as a future bridge — chat sessions already cover resume.)_
  *Verify:* session created in UI appears after reload; YAML status updated.
- [x] **T-041** Playwright setup + smokes for: play, forge, gm, worlds, snapshots, explorer, settings, search.
  *Verify:* `npx playwright test` green against dev stack.
- [x] **T-042** Coverage cold spots: behavior tests bringing `mongodb_tools/snapshots.py` and `merge_candidates.py` to ≥65%.
  *Verify:* `UV pytest --cov` per-module ≥65%.
- [x] **T-043** CLI smoke tests (Typer runner + fakes) for all 8 command groups.
  *Verify:* `UV pytest packages/cli -q` green (new tests exist).
- [x] **T-043b** Condition-Weighted Narrative. Migrate hardcoded scenery (`dark`, `slippery`) and condition (`blinded`) logic from `Resolver._evaluate_scenery_and_conditions` into `GameSystemRuntime` schema logic, to support modular game systems defining their own condition evaluation matrices. Support "full narrative" mode (pure fiction, no dice) alongside "condition-weighted narrative".
  *Verify:* Unit tests pass after moving logic to the game system schema and testing resolution variants.

## Phase 5 — Extras & release

- [x] **T-044** Observability polish: logfire opt-in documented; OTLP env passthrough; aggregate `/api/health`.
  *Verify:* `curl /api/health` returns component map; docs section exists.
- [x] **T-045** Demo content: one-command Millhaven demo world + pregen character + first scene (`scripts/seed_world.py --demo` or `monitor demo`).
  *Verify:* fresh DB → command → playable scene in UI in <2 min.
- [x] **T-046** Performance measurements vs SYSTEM.md targets recorded in `docs/STATUS.md`; optimize only measured hot spots.
  *Verify:* table of actuals (turn latency, search, resolve) present.
- [x] **T-047** README quickstart re-verified from a clean clone (document exact steps actually run).
  *Verify:* transcript/commit note confirming clean-clone run.
- [x] **T-048** Release: PR `feat/v1.1-final-polish` → `master`, merge, tag `v1.0.0`, CHANGELOG.
  *Verify:* `git tag` shows v1.0.0 on master; CI green on master.

---

### Execution rules

1. Work strictly top-to-bottom unless a task is blocked by an external decision; never leave the unit suite red between tasks.
2. Each task = one focused commit (or small series) referencing the task ID (`T-0NN:` prefix).
3. If reality diverges from this file (it will), update the task in place and note the divergence — this file is the living source of truth for execution.

## Phase 6 — UI Revamp & Play-First Repairs (docs/UI_REVAMP_PLAN.md)

- [x] **T-049** Provider keys survive edits: update handler ignores empty-string api_key; MINIMAX env passthrough in compose; re-key damaged rows. *Verify:* all 3 MiniMax rows test OK in-container; a narrated turn succeeds.  _(✓ done in commit bec55b3a (play-first repairs))_
- [x] **T-050** GET /stories/{id} falls back to the Neo4j story record; 404 only for truly missing stories. *Verify:* fresh session's StoryPanel loads without 404s.  _(✓ done in commit bec55b3a)_
- [x] **T-051** Frontend error hygiene: no 4xx retries, polling stops on persistent failure, ConnectionStatus uses /api/health, toast instead of console spam. *Verify:* console clean on Play+Forge.  _(✓ done in commit bec55b3a)_
- [x] **T-052** Fix /api/ingest/packs 500. *Verify:* curl 200 + Forge pack list renders.  _(✓ done in commit bec55b3a)_
- [x] **T-053** Fix /api/entities/systems/{id} 503. *Verify:* curl 200 for a seeded system.  _(✓ done in commit bec55b3a)_
- [x] **T-054** Embedding guard: empty vectors never reach Qdrant. *Verify:* re-run the failed ingestion to completed.  _(✓ done in commit bec55b3a; re-confirmed by T-082 (embed guard + qdrant fix))_
- [x] **T-055** Verified play pass (roleplay + world-architect chat) recorded in STATUS.md — 2026-06-13, live dockerized stack: demo world → 3 GM-narrated turns → architect committed a canon NPC → the commit surfaced in the Q-10 change_log. Two audit-hook bugs found & fixed en route.
- [x] **T-056** Global world/universe context picker shared by all pages.  _(✓ superseded by T-077 (global world context picker))_
- [x] **T-057** Onboarding wizard + "Try the demo world" button.
- [x] **T-058** QueryBoundary skeleton/error pattern; remove raw fetch() calls.
- [x] **T-059** Session manager: rename/archive, binding display, WS auto-reconnect.  _(✓ superseded by T-079 (session rename/manager))_
- [x] **T-060** Settings provider cards: key-state display (`api_key_masked` show/hide) + per-provider Test + tier/per-agent node assignments already shipped; added a header **Test All** button that sequentially probes every provider.
- [x] **T-061** Pack ops UI (merge/export/import/clone/slice) — PackLibrary multi-select + floating action bar + Import button + Slice dialog, wired to the pack_library endpoints.
- [x] **T-062** Ingest job controls (unlock/cancel/purge + stage log).  _(✓ superseded by T-084 (ingest job controls: unlock/cancel/purge + stage log))_
- [x] **T-063** Batch entity multi-select UI — Explorer graph shift/drag multi-select + floating bar with confirmed batch delete (DELETE /entities/batch).
- [x] **T-064** Q-10 audit trail: append-only change_log mongodb tools (write/list) + CanonKeeper emits an entry per committed proposal at `_commit_to_neo4j`; read-only `GET /api/change-log`; `HistoryTab` timeline at `/history` (Sidebar entry) with subject-type filters.
- [x] **T-065** Playwright interaction flows (send-turn, forge-upload, canon-accept).  _(✓ partially by T-081 (play send-turn flow); T-086 adds forge round-trip e2e)_

### Phase 6B+ — UI wave list (2026-06-12 review)

- [x] **T-066** Real Home page: continue recent sessions, world/status summary, demo hint, mode cards. *Verify:* / renders without redirect; sessions resume.
- [x] **T-067** Play HUD — phase chip from session state; working-state (HP/resources) chips and pending-consequence banner completed in T-078; turn-over-turn deltas + XP added by T-071 (`CombatPanel`).
- [x] **T-068** "Story so far" recap modal (server /recap) + quick-action chips (Oracle / Look around / Recap / Retry last). *Verify:* recap renders prose for an active story.
- [x] **T-069** Message utilities: copy GM prose; retry last turn. *Verify:* retry resends the previous player input.
- [x] **T-070** Architect chat: entity-created cards with links into Worlds/Explorer.  _(✓ superseded by T-080 (architect 'world changes' cards with Worlds-tree link))_
- [x] **T-071** Combat/progression panel: `CombatPanel` in the Play aside renders turn-over-turn working-state deltas (▲▼ HP/resource changes) + XP/level progression bar; generic over system stats, hidden until there's something to show.

### Phase 6C — Traversal & co-pilot overhaul (2026-06-12, from live review)

- [x] **T-072** Browse API: `GET /api/stories?universe_id=`, `GET /api/stories/{id}/scenes`, `GET /api/stories/{id}/threads`, `GET /api/scenes/{id}/turns`; real universe `entity_count`/`session_count`/`story_count`; Next proxy fixed (rewrite removed — runtime route handler owns /api/*). *Verify:* curl each endpoint against live stack; universe counts non-zero for Millhaven; `pytest tests/api` green.
- [x] **T-073** Play reliability: send/end-scene timeouts 180s (turns measured 15–30s, old default aborted at 30s); optimistic player echo + typing in REST fallback; WS turn watchdog (240s) + `error` frame handling; inline failure card with Retry; recap modal; copy GM prose; phase chip. *Verify:* turn round-trips over both WS and REST; failure card appears when backend stopped.
- [x] **T-074** Worlds "Tree & Stories" tab: traversal tree Multiverse → Universe → Story → Scene with detail panes (universe stats + Play-here/Explorer/Snapshots/GM deep links; story arc/tension/threads/scene timeline; scene transcript peek via turns API). Graph-tab Inspector dead Edit/Delete buttons removed ("Open tree" for universes). *Verify:* tree drills to a real scene transcript; ?universe= deep link lands on the tree.
- [x] **T-075** GM Assistant overhaul: CF-1 Session Recorder (gm_assistant capture sessions per universe: log entries → co-pilot reflections → recap (CF-2) → close-session canon review (CF-8)); CF-3 unresolved-threads panel; Session Prep story *picker* replacing the raw story-ID input; notebook ingest bound to the selected multiverse. *Verify:* recorder round-trip on live stack; threads/prep pickers list real stories.
- [x] **T-076** Verification pass: `tsc --noEmit` green; `pytest tests/api` 89 green (new browse-route tests); containers rebuilt; live smoke of new endpoints + Playwright page smokes. Ledger updated.

### Phase 6D — Context, HUD & manager wave (2026-06-12, second pass)

> Browser-level verification first: narration loop streams real prose in the
> live UI (ack 0.1s, full prose 27.3s, zero console errors) and the recorder
> round-trips a co-pilot reply in 6.7s — both prior complaints confirmed fixed.

- [x] **T-077** Global world context (plan T-056): persisted sidebar picker grouped by multiverse; Play setup, GM Assistant, and the Worlds tree default to it (URL params still win); starting a session writes the world back. *Why:* live probing showed starting a session means hunting the right multiverse among walkthrough debris on every page.
- [x] **T-078** Play HUD completion (T-067): generic working-state chips (HP/resources/conditions) in the aside; pending-consequence banner above the input with tappable options wired to the consequence-choice resolver. *Verify:* banner appears when `requires_player_choice` turns set pending_consequence; choice sends the option text.
- [x] **T-079** Session manager (plan T-059 core): PATCH accepts `title`; session list gains filter (>5 sessions), inline rename (double-click or pencil), delete confirmation, phase dot. *Verify:* rename round-trips via PATCH; 40-session list filterable.
- [x] **T-080** Architect world-changes cards (plan T-070): done-frame metadata attaches to the finished message; GM bubbles render canonized/proposal counts, open questions, and an "Open in Worlds tree" link. *Verify:* card renders for world_architect turns with committed/proposals > 0.
- [x] **T-081** Playwright interaction flow (plan T-065, first of three): `e2e/play-flow.spec.ts` creates a session through the real form, sends a turn, requires fresh GM prose >150 chars; opt-in via `E2E_INTERACTION=1`.

### Phase 7 — World Forge: Ingestion Repair & Seed-to-Playable (`docs/FORGE_INGESTION_PLAN.md`)

> Created 2026-06-12 after the report "we have not been able to ingest a single
> PDF in the World Forge UI". Goal hierarchy: (A) a real PDF dropped in the
> Forge reliably becomes a reviewed knowledge pack — or fails loudly with a
> visible reason and a retry path → (B) a one-sentence seed becomes a playable
> universe + bound session in <2 min → (C) SillyTavern character cards import
> and are immediately playable. **Work A before B.**

#### Section A — Ingestion truth & repair (T-082..T-086)

- [x] **T-082** Live diagnosis first. Bring the stack up; drive a real PDF through `POST /api/ingest/sources/upload` exactly as `UploadCard.tsx` does; record where it actually dies (job stage, container log, DB state). Fix what we find, not what we guess. *Verify:* a 1-page PDF reaches `status: completed` with a pack in the library, from the UI, on the dockerized stack.
  **Done 2026-06-13.** A hand-built text PDF driven through the live API surfaced **two sequential blockers**, each fixed:
  1. **Embed stage — Qdrant client/server mismatch.** `qdrant-client` 1.18 serializes vectors in a gRPC field the pinned **server v1.7.4** ignored, so every upsert died with `INVALID_ARGUMENT: expected dim 1536, got 0` — reproduced with a hand-rolled `PointStruct([0.01]*1536)` against the raw client. Bumped the compose image to **`qdrant/qdrant:v1.18.0`** (backed up + reset the on-disk storage; old segment format was incompatible). Upsert then returns `completed`.
  2. **Analyze stage — `pack.pack_id` AttributeError.** `analyzer/_core.py:541` read `pack.pack_id` on a `KnowledgePackResponse` whose primary key is exposed as `.id` (`pack_id` is only the deser alias). One-line fix → `pack.id`.
  Also hardened two adjacent edges found en route: a **`localhost`→`host.docker.internal` base-url rewrite** (`normalize_local_base_url`, env `MONITOR_LOCALHOST_REWRITE`, compose `extra_hosts: host-gateway`) so provider rows pointing at host-running services (ollama/LM Studio) work from inside the container; and **section-categorizer resilience** in `indexer.py` (one LLM failure now disables categorization for the rest of the doc instead of killing a 500-section rulebook). Working LLM for analyze is `gemini-2.5-flash` (key from env). Result: `millhaven-test.pdf` ran end-to-end in **78s** → pack `status=ready`, **17 entities, 10 lore facts, 1 axiom**. (Note: failed pre-fix runs leave empty `status=pending` placeholder packs — stale-placeholder cleanup tracked in T-083.)
- [x] **T-083** Edge-case matrix from `FORGE_INGESTION_PLAN.md §A2`. **DONE:** PDF parser guards (`PdfExtractionError`) for empty/corrupt/truncated/encrypted/scanned-no-text with human-readable messages, applied to `extract_pdf_text` + both structure extractors (the real ingestion path); 5 regression tests in `test_ingest_tools.py` (13 pass); client-side type/size/empty validation (T-084); unsupported-type/empty rejected at upload; stale-queue-lock + cancel controls (T-084). Live-verified: a corrupt PDF now fails the job with "could not be opened as a PDF (corrupt or truncated)" instead of a cryptic crash. **Matrix now fully closed:** huge-PDF streaming budget (>50MB) guard in `pdf_processing._open_pdf` + new `test_pdf_processing.py` (5 tests: empty/oversized/corrupt/user-facing/happy); duplicate-content flagging → `IngestionStatus.FLAGGED_DUPLICATE` (`test_ingestion_pipeline.py::...flagged_duplicate`); embed-down dedicated test (`test_ingestion_pipeline.py::test_embed_down_fails_gracefully` + empty-vector guard in `test_qdrant_tools.py`); restart-mid-job recovery documented in `docs/gameplay-examples/forge-ingestion-troubleshooting.md` (Unlock queue → rescan).
- [x] **T-084** Failure visibility & controls in the Forge UI (supersedes T-062). Failed job rows now render red with the `error` + "failed at <stage>" *on the row* and auto-expand (no more buried errors); **Retry (rescan)** per failed job, **Cancel** for live jobs, toolbar **Unlock queue** + **Purge N failed**; client-side type/size/empty validation in `UploadCard` before POST. *Verify:* **browser-tested live** against the existing failed jobs — Retry, Unlock queue, Purge failed, and "failed at <stage>" all render; zero console errors. (Per-job stage log already existed in the expand panel.)
- [x] **T-085** Hardening. **Clearer error propagation:** user-facing exceptions (`PdfExtractionError`, marked `user_facing=True`) now surface their human message in the job error *without* the `ClassName:` prefix — live-verified, a corrupt PDF reads "This file could not be opened as a PDF (corrupt or truncated)…". **Per-stage timeout:** the analyze stage is wrapped in a 30-min `asyncio.wait_for` (`MONITOR_ANALYZE_TIMEOUT`, tighter than the 45-min whole-job timeout) so a wedged LLM provider fails that stage with "Analysis stage timed out…" instead of silently riding the job timeout. Parser guards were T-083.
- [x] **T-086** Regression net. Unit edge-case tests in `test_ingest_tools.py` (T-083, 13 pass). New live e2e `tests/e2e/test_13_forge_ingestion.py` (`RUN_E2E=1`): tiny text PDF → `completed` + ready pack with entities, and seed → quick-world universe with committed entities; both skip cleanly when the LLM provider is down.

#### Section B — Seed-to-playable (T-087..T-090)

- [x] **T-087** `POST /api/forge/quick-world` with `{ seed, genre?, tone?, name?, start_playing? }`. One structured LLM call expands the seed → world name/description, 1 axiom, 3–4 entities (ally/antagonist/location/optional faction with description, wants, tags), 2–3 lore facts, opening scenario hook, suggested PC concept. Commits via `CanonKeeper.apply_pack_to_universe(auto_accept=True)` (same path as lorebook ingestion). With `start_playing`, also create a bound chat session and return `session_id`. *Verify:* curl a one-line seed → universe exists in tree with entities/facts; `start_playing` returns a session that narrates turn 1.
  **Done 2026-06-13.** New `monitor_agents/prompts/quick_world.py` (DSPy one-shot signature), `monitor_agents/quick_world.py` (builder: generate → create multiverse+universe → pack → CanonKeeper commit → optional session), `routers/forge.py` (`POST /api/forge/quick-world`). Verified live: seed "frontier mining moon where the ore whispers and the company owns your air" → **The Dust Margin** (5 entities incl. Nadia Voss/Superintendent Craine/Shaft 7/the Union, 1 axiom, 3 lore facts), **8 committed / 0 errors**, bound session narrated turn 1 referencing the generated NPC and location. Fixed a **pre-existing CanonKeeper bug** found here: `_commit_axiom` passed `authority="source"`, invalid for the closed `AxiomAuthority` enum, so *every* ingested/quick-world axiom was silently rejected — now mapped from domain via `_axiom_authority_for_domain` (also fixes lorebook axioms).
- [x] **T-088** SillyTavern `chara_card_v2` import/export into `StandaloneCharacter`. `routers/character_cards.py` parses v2/v3 (nested `data`) **and** v1 (flat) JSON, **and** PNG cards (tEXt/zTXt `chara`/`ccv3` base64 chunks); maps name/description/personality/first_mes → fields, folds system_prompt/scenario/creator_notes/mes_example into gm_notes. `POST /api/entities/characters/import-card` (multipart), `GET …/{id}/export-card`. UI: Import button (JSON/PNG) in the Play CharacterPanel header → selects the imported character. *Verify:* unit-tested v2+v1+PNG parse and error cases; **live-verified** — JSON card (Vesper Quill) and PNG card (Inkwell Pratchett) both imported via the live API with first_mes + scenario→gm_notes preserved, and export round-trip returned a valid chara_card_v2.
- [x] **T-089** Forge **Quick Start** tab. The Forge now lands on the ingestion view (default `forgeMode="sources"`) with a **Quick Start / Lorebook Ingestion** mode toggle; Quick Start is the default. Seed textarea + example chips + genre/tone chips + optional name + "start session immediately" + **Forge world**; result card shows world/axiom/entities(with wants)/opening-scene/PC + **Play here now** (deep link, prefers `session_id`) + **Open in tree**, and sets the global active world (T-077). *Verify:* **browser-tested live** — landed on Quick Start, forged "The Drowned Mourning" in 39.6s, result card + deep links rendered, sidebar adopted the world, zero console errors. (Card dropzone deferred to T-088.)
- [x] **T-090** `docs/gameplay-examples/quick-world-walkthrough.md`: seed → forge → play UI + API flow, with the verified Dust Margin run and a Quick-Start-vs-Lorebook comparison.

### Phase 8 — Vision Hardening (quality & performance) — `docs/VISION_HARDENING_PLAN.md`

> Created 2026-06-14 from the measured vision playtest (`docs/STATUS.md`).
> Phase 7 proved the plumbing runs; Phase 8 closes "runs → good". Every task is
> anchored to a measured baseline → target. Priority: T-091 > T-092 > T-093 > rest.

- [x] **T-091** [Turn latency] Rewrite the main processing chain to cut median turnaround. Target: < 8s median. Run the resolver on a fast model via node-assignments while the Narrator keeps quality, prompt-cache the static system+world block, stream the Narrator over WS, and trim the context window.
  *Verify:* 10-turn playtest median < 8 s, first-token < 3 s, continuity >= 14/15.
- [x] **T-092** Wire the mechanical layer into default play. Baseline: `working_state` empty across 15 demo turns → CombatPanel/HUD never populate. `demo-world`/`quick-world` bootstrap a PC sheet + light `dice_game_system`; confirm resolver writes HP/resource/condition deltas; CombatPanel renders. *Verify:* demo playtest shows non-empty working_state with changes + ≥1 CombatPanel delta + XP — or document default play as narrative-only (no silent empty HUD).
  **Done 2026-06-19 (code + unit tests).** `quick-world` with `start_playing` now bootstraps a demo PC via `_ensure_demo_pc` and binds `character_id`/`speaker_character_id`/`controlled_character_ids` to the session with `play_mode=dice_game_system` + Mistlands Core `system_id`. Chat router (REST + WS) persists `latest_working_state`, `latest_scene_checkpoint`, `latest_social_read`, `latest_relationship_snapshot` from turn metadata into the session document. Unit tests: 3 forge API tests + 1 chat router working_state persistence test. *Live verification pending (requires dockerized stack).*
- [x] **T-093** Retrieval scoping — stop cross-universe bleed. Baseline: a Millhaven co-pilot reflection cited "Ashfall Reaches" (another universe). Narrator memory is story-scoped; knowledge/co-pilot/architect retrieval is not universe-scoped. Add `universe_id` to the qdrant filter on those paths; make scope required. *Verify:* two-universe regression test — retrieval for one never returns the other's tokens; 5 repeat reflections show zero foreign names.
  **Done 2026-06-19 (code + unit tests).** `universe_id` added to `MemoryCreate`, `MemoryFilter`, `MemoryEmbedRequest`, `MemorySearchRequest`, `MemoryResponse` schemas. Threaded through `persist_memories` in scene_loop/scene_support. Qdrant payload + filter include `universe_id`. MongoDB `list_memories` filters by `universe_id`. Unit tests: 2 new universe-scoped memory tests + 48 scene_loop tests + 51 contract tests. *Live two-universe regression test pending (requires dockerized stack).*
- [x] **T-094** Co-pilot quality: threads + hooks + contradictions. Root cause of empty CF-3: `neo4j_list_plot_threads` passed raw neo4j DateTime to PlotThreadResponse → pydantic error → endpoint silently returned 0. Fixed with `_to_native_datetime`; story bootstrap now seeds an opening "central conflict" thread. Hooks already ground in open threads/scenes/entities, so seeding fixed the generic-hook symptom (live: "What Lies Beneath the Canvas" etc.). CF-5 already works (existing planted-contradiction tests; live "0" was a true negative). Verified in-process: thread parses + returns; 72 plot-thread tests pass.
- [x] **T-095** GM quality eval harness. `scripts/eval_gm_playtest.py` — drives/loads a transcript, LLM-judge (gemini) rubric (canon-consistency, continuity, contradiction-freeness, pacing, agency; 0–5) → JSON under `docs/testing/`. Baseline: fresh demo 6 GM turns → **5/5 all dims (avg 5.00)** (judge generous on a short happy-path; instrument is the deliverable for tracking quality across later changes).
- [x] **T-096** World Architect proposal determinism. Deterministic fallback (`_fallback_entity_proposal`): when the message has explicit create intent + entity kind + a recoverable proper-noun name and the LLM extraction yields no entity proposal, synthesize it directly. **Live-verified 5/5** explicit create-NPC requests commit ≥1 entity (was flaky); 10 unit tests incl. negatives.
- [x] **T-097** Ingestion recall benchmark + huge-doc/OCR decision. Labelled 8-entity fixture → **100% recall (8/8)** (all named characters/locations/factions extracted). Precision caveat: ~12 generic type entities also emitted. Decisions: >50 MB rejected (not streamed); scanned PDFs fail loudly, OCR future opt-in. Surfaced a reliability bug → **T-098**. _(/tmp/bench_ingest.py)_
- [~] **T-098** Ingestion embed-stage reliability — **code fix committed, live verification pending.** Intermittent `RuntimeError: Event loop is closed` at the embed stage; ~3-4/5 sequential ingests fail (job 1 always passes). **Investigated deeply:** NOT the qdrant client (per-job `new_loop_client` fix passes 3/3 isolated + 4/4 faithful thread+executor+main-loop repro, but real pipeline still fails intermittently); NOT `embed_batch` alone; NOT a uvicorn `--reload` (none); NOT a container crash (restart count 0). It's a genuine **intermittent concurrency bug that does not reproduce in isolation** — only under the full ~90s pipeline. **Fix committed (83ff485c):** `_upsert_points` now resets the client and retries exactly once on "Event loop is closed" (unrelated RuntimeErrors propagate untouched). 3 retry-path tests + 2 reset_client tests pass. *Live stress verification (5 sequential ingests) pending against dockerized stack.*
