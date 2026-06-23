# FINAL FABLE PLAN — Everything Needed to Finish MONITOR

> **Created:** 2026-06-10, by direct code/infra verification (not doc claims).
> **Goal:** Take MONITOR from its current **non-functional** state to a complete, working, polished realization of the product vision in `SYSTEM.md` — all three modes (World Architect, Autonomous GM, GM Co-Pilot) usable end-to-end, with trustworthy tests, clean code, and honest docs.
> **Companion file:** `FINAL_FABLE_TASKS.md` — the same plan decomposed into atomic, individually verifiable tasks.

---

## 1. The Vision (what "finished" means)

MONITOR is a persistent narrative-intelligence system for tabletop RPGs. "Finished" means:

| Mode | Definition of Done |
|------|--------------------|
| **World Architect** | Create world → ingest documents → review/curate extractions → apply knowledge packs → query/browse/fork/snapshot the world. All from the web UI. |
| **Autonomous GM** | Create character → start story → play turn-by-turn (actions, dialogue, questions, meta-commands) with dice resolution, oracle, procedural population, on-the-fly canonization, scene/story completion, downtime progression. All from the web UI chat + `monitor playtest` CLI. |
| **GM Co-Pilot** | Record a session → recap → unresolved threads → plot hooks → contradictions → handouts → canon review queue (accept/reject proposals). All from the GM page. |
| **Engineering** | `./dev.sh` brings up a working stack; the full unit suite runs **green in minutes, hermetically, on any machine with no API keys**; one honest E2E proves the core loop against real services; CI enforces all of it; no duplicated code; docs match reality. |

---

## 2. Verified Current State (ground truth, 2026-06-10)

Everything below was verified by running commands against this checkout — not copied from existing status docs (which are optimistic and themselves duplicated).

### 2.1 What actually works

- All four Python packages import cleanly (`monitor_data`, `monitor_agents`, `monitor_cli`, `monitor_ui`).
- The FastAPI app constructs with **227 routes** across 20 registered routers (33 router modules).
- The frontend (Next 15 / React 19, 16 app routes, ~21K LOC TS/TSX) **type-checks with zero errors**.
- data-layer: **782 unit tests pass** before the suite hits the first network-bound test.
- agents: **534+ tests pass** before resolver tests stall the suite.
- Large real surface: ~52K LOC data-layer, ~35K agents, ~16K UI backend, ~3K CLI. SceneLoop/StoryLoop/CanonKeeper/Resolver/loops all substantially implemented. TLA+ specs exist for core protocols.
- Test seams exist: `AgentFactory` + `reset_agent_factory()`, `FakeMCPClient`, `FakeLLMClient`.

### 2.2 Why the project is non-functional today

**(A) The Docker dev stack is broken — two containers crash-loop:**

1. `monitor-ui-backend` (19 restarts): `ModuleNotFoundError: No module named 'monitor_ui'`.
   **Root cause:** `packages/ui/backend/Dockerfile` does `pip install -e` (editable) in the **builder** stage at `/build/packages/...`, then the final stage copies source to `/app/packages/...`. The venv's editable path entries still point at `/build/...`, which doesn't exist in the final image.
2. `monitor-neo4j` (18 restarts): `Neo4j is already running (pid:7)`.
   **Root cause:** after the first unclean exit, the stale pidfile survives inside the same container fs; `restart: unless-stopped` restarts the *same* container forever. The override healthcheck (`cat /proc/1/cmdline`) always succeeds, so orchestration can't see the failure. The base compose also carries deprecated memory settings and an invalid `dbms.security.auth_enabled=false` list entry.
3. Config drift: `gliner` is stubbed out (busybox, `profiles: [disabled]`) but `ui-backend` env still defaults `NLP_BACKEND=gliner` with `GLINER_URL` pointing at the disabled service.

**(B) The test suite is not hermetic — this is the "full tests crash":**

- `tests/conftest.py` calls `load_dotenv()` and `monitor_data.config.Settings` reads `env_file=(".env.test", ".env")` → unit tests inherit the **real** `ANTHROPIC_API_KEY` and real DB URIs from `.env`.
- Many "unit" tests construct real agents (`Resolver()`, etc.) whose calls go `LLMRegistry(get_postgres_client())` → real Postgres → real LLM with tenacity exponential-backoff retries.
- Measured: `packages/agents` killed at 69% after 4+ min (docs claim 768 passed in ~10s); `packages/data-layer` hangs at 47% on `test_memory_tools.py::test_embed_memory` (real embedding call); `tests/api` hangs on its **third test** (`test_chat_router.py::TestSessionCRUD::test_create_session_minimal` → live chat router → crash-looping Neo4j).
- So the "6,149 collected / 99.95% pass" story in the docs is unreproducible: the suite **hangs indefinitely** on any machine where services are down/half-up — which is exactly the current machine state.
- Plus 4 known **ordering flakes**: 2 in `test_ingestion_loop.py` (pass in isolation — verified) and the 2 documented P-7 flakes; global state (dspy/LLM singletons) leaks between tests.
- Mutation testing is dead in the water: mutmut 3.5's StatsCollector crashes on numpy double-import (framework bug, documented in `CLOSING_THE_GAP.md` §12.4).

**(C) Duplicated code (verified):**

| Duplication | Locations |
|---|---|
| Entire facts/events tool family ×2 | `neo4j_tools/facts.py` (live, 40KB) **and** `neo4j_tools/facts/` dir (`_facts.py`, `_events.py`, `_shared.py`) — the dir has no `__init__.py`; `facts.py` shadows it, so the dir is dead code that still gets counted/maintained |
| `SimulationScope` ×2 | `schemas/base.py:157` and `schemas/facts.py:36` |
| `CoreMechanicType` ×2 | `schemas/rpg_ontology/meta.py:90` and `schemas/game_systems.py:30` |
| `CharacterSheetCreate/Update/Response` ×2 | `schemas/character_sheets.py` and `schemas/rpg_ontology/base.py` |
| `BehavioralTrigger` ×2 | `schemas/npc_profiles.py:80` and `schemas/npc_scene_generator.py:14` |
| `ActionType` name collision | `schemas/game_systems.py:314` (BaseModel) vs `schemas/resolutions.py:26` (Enum) — same name, different kind |
| Helper functions ×2–3 | `_to_native_datetime` ×3, `_utcnow`, `_pydantic_to_dict`, `_levenshtein_ratio`, `_call_sync` ×2 across tools |
| Env templates ×2 | `env.example` (canonical, full) vs `.env.example` (stale subset missing ~20 keys) |
| Seed scripts | `seed_zai_provider.py` vs `seed_zai_providers.py`; `seed_world.py` vs `seed_world_quick.py` (59 scripts total) |
| Status docs ×5+ | `CLOSING_THE_GAP.md` (which itself contains **two** §4–§9 blocks — a botched merge), `CLOSING_THE_GAP_NEW.md`, `ACCURATE_IMPLEMENTATION_STATUS.md`, `TESTING_STATUS_REPORT.md`, `YAML_STATUS_UPDATE_SUMMARY.md` |
| Use-case taxonomy | `docs/use-cases/` has conflicting epic numbering (`epic-5-rules-RS` + `epic-5-system.md`; `epic-6-co-pilot.md` + `epic-6-timeline-Q`; epics 7/8 doubled), P-15 YAML lives under `epic-1-world-M`, P-15 YAML contradicts P-15 spec markdown |

**(D) Repo hygiene problems (verified):**

- Garbage files **tracked in git** at repo root: `on` (less-help output), `OK', flush=True)` — plus untracked junk `chemas.entities import ...` and `.py","core.py",...` (shell-redirect accidents). Master's tip is literally "chore: remove garbage files", but the branch re-introduced them.
- `coverage.json` (875KB, stale) at root.
- `minimax-vscode/` — an entire unrelated VS Code extension living in this repo.
- Branch `feat/v1.1-final-polish` is **85 commits ahead of master, 0 behind**; master is stale.
- Broken doc link: `epic-6-co-pilot.md` → `docs/use-cases/co-pilot/analysis-prep.md` exists **but is untracked** (never committed).
- `.env` (real secrets) present; tests read it (see B).

**(E) Product gaps (from `BACKEND_VS_FRONTEND_AUDIT.md`, spot-verified):**

- Frontend exposes ~35–40% of backend capability. **Six routers have zero UI:** `tone`, `lorebook`, `search`, `performance`, `databases`, `modes`.
- Partially exposed: pack ops (merge/export/import/clone/slice/apply), ingest unlock/cancel/purge, LLM node-assignments, batch entity ops, universe fork button, end-story button, story DM-override patch.
- P-15 "Start Play Session" backend exists; YAML/spec conflict resolved on paper (P-21 = deferred Autonomous PC) but YAML statuses across all 165 use cases are wildly stale (144 "todo" vs ~87% implemented).
- Coverage cold spots: `mongodb_tools/snapshots.py` ~31%, `merge_candidates.py` ~19%.
- No CLI tests at all. No Playwright/browser tests. E2E suite (15 files) requires `RUN_E2E=1` + working stack — currently impossible since the stack is down.
- Observability: logfire is local-only; no OTLP export config; CI has no coverage/timeout gates.

---

## 3. The Plan

Ordered phases; each phase leaves the repo strictly better and verifiable. (Atomic decomposition in `FINAL_FABLE_TASKS.md`.)

### Phase 0 — Make it run (infra + hygiene blockers)

**0.1 Fix `ui-backend` Docker image.** Replace editable installs with regular installs (`pip install /build/packages/...`) or copy sources to identical paths; rebuild; verify `docker compose up ui-backend` serves `GET /api/databases/status`.

**0.2 Fix Neo4j service.** Recreate the container (`compose down && up` — data volume persists); restore a *real* healthcheck that works with auth enabled (HTTP probe on 7474 or `cypher-shell` with credentials); migrate deprecated `dbms.memory.*` → `server.memory.*` env names; delete the invalid `dbms.security.auth_enabled` line; keep dev-friendly heap sizes in the override only.

**0.3 Resolve NLP backend drift.** Single source of truth: `NLP_BACKEND=spacy` default everywhere (compose, env.example, config defaults); gliner stays available behind an opt-in profile with documented requirements; ingestion must degrade gracefully (regex fallback) when no NLP service is reachable.

**0.4 Repo hygiene.** `git rm` the tracked junk (`on`, `OK', flush=True)`), delete untracked junk, gitignore + remove `coverage.json`, commit `docs/use-cases/co-pilot/` (fixes broken link), delete `.env.example` in favor of `env.example` (or vice versa — keep exactly one, update README), decide `minimax-vscode/` out of the repo (move to its own repo; keep a pointer in docs).

**0.5 `./dev.sh` smoke.** After 0.1–0.4: full stack starts; backend `/api/databases/status` reports all DBs healthy; frontend loads; document the verified quickstart in README.

### Phase 1 — Make tests trustworthy (the crash fix)

**1.1 Hermetic-by-default unit tests.**
- Root conftest: stop `load_dotenv()` for unit runs; force a dedicated `.env.test` (fake keys, unroutable hosts) via `MONITOR_ENV_FILE` or monkeypatched `Settings`; **override**, don't `setdefault`, the dangerous vars (`ANTHROPIC_API_KEY=test-key`, etc.).
- Add `pytest-timeout` (per-test default ~20s, suite-level guard) and `pytest-socket` (network blocked unless `integration`/`e2e` marker) as dev deps wired in `pytest.ini`.
- Tests that genuinely need services get `@pytest.mark.integration` and are skipped by default (mechanism already exists).

**1.2 Fakes by default for agent construction in tests.** Use the existing `AgentFactory` seam: an autouse fixture installs a factory producing agents wired to `FakeLLMClient`/`FakeMCPClient`; direct-construction tests (e.g. `test_resolver_pushback.py`) are converted or marked integration. Reset `agent_factory`, dspy settings, and LLM registry caches between tests (autouse) — this also kills the 4 ordering flakes.

**1.3 Re-triage the suite.** With timeouts + socket-block on: run everything; every test now either passes fast, or fails loudly and gets fixed/marked. Target: **full unit suite green in < 5 minutes on a cold machine with no `.env`**. Publish the real counts in one place (see 2.4).

**1.4 Mutation testing decision.** Pin a working tool: mutmut 2.x or `cosmic-ray` on the 3 critical modules (`canonkeeper.py`, `scene_loop.py`, `resolver.py`); record kill-rate; otherwise formally drop the mutation gate from docs (no zombie claims).

**1.5 CI.** GitHub Actions workflow: ruff + mypy + layer-dependency check + hermetic unit suite (with timeout) on every PR; nightly job with dockerized services for `RUN_INTEGRATION=1` + the honest E2E (Phase 3). Coverage uploaded, gate at 50%/module to start, ratcheted later.

### Phase 2 — Deduplicate & consolidate

**2.1 Kill the dead facts package.** Delete `neo4j_tools/facts/` (dir), keep `facts.py`; verify imports/`__init__` exports and tool registration are unchanged (the dir is shadowed today, so behavior must not change — prove with the suite).

**2.2 Single-source the duplicated schemas.** For each pair (`SimulationScope`, `CoreMechanicType`, `CharacterSheet*`, `BehavioralTrigger`): keep one canonical definition, re-export from the legacy location if needed, delete the copy; rename one side of the `ActionType` model/enum collision (e.g. enum stays `ActionType`, model becomes `ActionTypeDef`). Run the suite + mypy to prove no semantic drift.

**2.3 Shared helpers module.** Move `_to_native_datetime`, `_utcnow`, `_pydantic_to_dict`, `_levenshtein_ratio`, `_call_sync` into `monitor_data/tools/_shared.py` (or `utils/`) and import everywhere.

**2.4 One status doc to rule them all.** Replace `CLOSING_THE_GAP.md` (de-duplicate its internal double sections), `CLOSING_THE_GAP_NEW.md`, `ACCURATE_IMPLEMENTATION_STATUS.md`, `TESTING_STATUS_REPORT.md`, `YAML_STATUS_UPDATE_SUMMARY.md` with a single `docs/STATUS.md` (generated numbers + date + verification commands); move the old ones to `docs/archive/`.

**2.5 Use-case taxonomy cleanup.** Renumber/rename the doubled epic files; move P-15 YAML next to its spec; sync all 165 YAML `status:` fields with reality (scripted via `scripts/analyze_use_case_coverage.py` where possible).

**2.6 Scripts pruning.** Merge `seed_zai_provider(s).py`, `seed_world(_quick).py`; delete one-off dead scripts; add a `scripts/README.md` index.

### Phase 3 — Prove the core loops (honest E2E)

**3.1 The honest smoke.** With the stack from Phase 0: scripted run (`scripts/live_gameplay_smoke.py` exists — make it pass): create universe → create character → start story → 3 turns (action/dialogue/question) → end scene → assert Neo4j has the entities/facts, Mongo has turns/scenes, Qdrant has memories. Wire as `RUN_E2E=1` job and as a `monitor playtest` invocation.

**3.2 Mode walkthroughs.** One scripted E2E per mode: Architect (ingest a small doc → review → apply pack), GM Assistant (record notes → recap → threads → hooks → contradiction → handout → canon review accept), Solo Play (the 3.1 smoke + oracle + combat + downtime). Defects found here become tasks; the walkthroughs become regression tests.

**3.3 Fix the e2e suite.** Get the 15 existing `tests/e2e` files passing against the running stack, or mark/repair the stale ones.

### Phase 4 — Close the product gaps

**4.1 Frontend bridges for the six dark routers.** Minimum viable UI: semantic **search** bar (header) + results page; **databases** health panel (settings); **modes** switcher (header/settings); **tone** manager (settings tab); **lorebook** editor wiring (component exists, connect API); **performance** dashboard (simple tables). Each = API client functions + page/panel + one Playwright smoke.

**4.2 Finish partially-wired UI.** Pack ops (merge/export/import/clone/slice/apply buttons in PackLibrary), ingest unlock/cancel/purge, batch entity multi-select, "Fork Universe" button, "End Story" button, LLM node-assignment editor, story DM-override.

**4.3 P-15/P-21 closure.** Finish play-sessions UX (list/resume in UI), keep P-21 (Autonomous PC) formally deferred with a YAML status that says so.

**4.4 Coverage cold spots.** Bring `snapshots.py` and `merge_candidates.py` to ≥65% with behavior tests (restore-path and merge-path edge cases).

**4.5 CLI tests.** Smoke tests for each `monitor` command group using Typer's runner with fakes (no network).

**4.6 Modular Rule Systems (Condition-Weighted Narrative).** Extract hardcoded scenery (`dark`, `slippery`) and condition (`blinded`, `pressured`) keywords from the Resolver into the dynamic `GameSystemRuntime` schema. Support "full narrative" (pure fiction) and "condition-weighted narrative" (dynamic bonuses/penalties based on character stats and location features), allowing any game system to define its own evaluation logic without code changes.

### Phase 5 — Extras & polish ("perfect version")

**5.1 Playwright suite.** One spec per major page (play, forge, gm, worlds, snapshots, explorer, settings) against the dev stack; runs in nightly CI.
**5.2 Observability.** Document logfire opt-in; add OTLP env passthrough so any OTel backend works; `/api/health` aggregating DB + LLM-provider reachability.
**5.3 Demo content.** `monitor demo` / `scripts/seed_world.py --demo`: one command creates the "Millhaven" sample world + pregen character + first scene, so a fresh install demos the SYSTEM.md script in <2 minutes.
**5.4 Performance pass.** Measure SYSTEM.md targets (turn <3s with fast LLM, search <200ms, resolve <500ms); record actuals in `docs/STATUS.md`; optimize only verified hot spots.
**5.5 Release.** Squash-free PR `feat/v1.1-final-polish` → `master` (85 commits), tag `v1.0.0`, README quickstart re-verified from a clean clone, CHANGELOG.

---

## 4. Acceptance Criteria (Definition of Done for the whole plan)

1. `docker compose --env-file .env -f infra/docker-compose.yml up -d` → **all containers healthy, zero restart loops** (verified via `docker ps` after 5 min).
2. `uv run pytest packages tests -m "not integration and not e2e" -q` → **green in <5 min** on a machine with **no `.env` and no network** (socket-blocked), zero flakes across 3 consecutive runs.
3. `RUN_E2E=1` honest smoke passes against the live stack: world → character → story → 3 turns → scene end → state verified in Neo4j/Mongo/Qdrant.
4. The three mode walkthroughs (§3.2) each complete from the web UI by hand, following a written script, without touching a terminal.
5. Zero duplicated definitions from §2.2(C) table; `ruff`, `mypy`, layer-check all green; CI enforces them.
6. One status doc; YAML statuses match code; README quickstart works from a clean clone.
7. `master` == release; tagged `v1.0.0`.

## 5. Decisions taken in this plan (flag if you disagree)

- **spaCy (with regex fallback) is the default NLP backend**; GLiNER is opt-in (its image is unavailable upstream).
- **mutmut is replaced or pinned**, not debugged (upstream bug).
- **P-21 Autonomous PC stays deferred** — it's a new feature, not a gap.
- **`minimax-vscode/` leaves the repo.**
- **logfire stays** as the tracing layer (OTel-compatible) instead of adding a parallel OpenTelemetry SDK setup.
- Existing UI stack (Next 15/React 19/React Query/React Flow) is kept; no rewrites.

## 6. Risk register

| Risk | Mitigation |
|------|-----------|
| Hermeticity refactor surfaces hidden failures across ~6k tests | Phase 1.3 triage budget; fix-or-mark policy; land in small commits |
| Neo4j data volume incompatible after container recreate | Volume is bind-mounted (`infra/neo4j/data`); back it up before recreate |
| Frontend bridge work balloons | Each bridge is "API client + minimal panel + smoke" only; no redesigns |
| LLM-dependent E2E is non-deterministic | Smoke asserts *structure* (entities exist, turns persisted), never prose content |
| Single-dev bandwidth | Tasks file is strictly ordered; every task leaves the repo green |
