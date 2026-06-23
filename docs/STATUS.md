# MONITOR — Status (single source of truth)

> **Last verified:** 2026-06-22, on this machine, by running the commands below.
> Supersedes `CLOSING_THE_GAP*.md`, `ACCURATE_IMPLEMENTATION_STATUS.md`,
> `TESTING_STATUS_REPORT.md`, `YAML_STATUS_UPDATE_SUMMARY.md` (now in `docs/archive/`).
> The forward plan lives in `FINAL_FABLE_PLAN.md` / `FINAL_FABLE_TASKS.md` at repo root.

## Test suite (hermetic — no network, no real keys)

| Suite | Result | Wall time |
|-------|--------|-----------|
| Full unit suite (`uv run pytest packages tests/api tests/contracts tests/behavior`) | **5,672 passed, 38 skipped, 0 failed** | ~3:47 |
| `packages/agents` | ~770+ passed | ~2:20 |
| `packages/data-layer` | ~1,640+ passed | ~1:00 |
| `packages/ui` | ~100+ passed | ~25s |
| `tests/` (contracts+behavior+property+api+root) | remainder, all green | — |
| Flake check | 3 consecutive identical green runs (2026-06-11 baseline) | — |

Hermeticity is enforced by the repo-root `conftest.py`: fake API keys,
unroutable DB/provider URLs, pytest-socket network block (unix sockets
allowed), 60s per-test timeout, `DB_SYNC_TIMEOUT=15` on the sync→async
bridge. Integration/E2E tests run only with `RUN_INTEGRATION=1` / `RUN_E2E=1`.

The 182 skips: integration/e2e-marked tests plus 6 `tests/unit/{CF,P}-*`
modules that test self-contained spec prototypes (no `monitor_*` imports) —
kept as design artifacts, skipped with rationale in each module.

## Quality gates

| Gate | State |
|------|-------|
| `uv run ruff check packages` | **clean** |
| `python scripts/check_layer_dependencies.py` | **passing** |
| `npx tsc --noEmit` (frontend) | **clean** |
| `mypy` strict | configured; informational in CI (backlog) |
| Mutation testing | **removed** (T-017 decision) — mutmut 3.5 is broken upstream and cosmic-ray hangs indefinitely on the async stack; claims formally removed |
| CI | `.github/workflows/ci.yml` (lint, layer, mypy-informational, unit, frontend) + `nightly-integration.yml` |

## Dev stack

`docker compose --env-file .env -f infra/docker-compose.yml up -d`
→ 9 containers, all healthy, zero restart loops (verified 2026-06-10).
Neo4j password is parameterized from `.env`; the previous data directory is
preserved at `infra/neo4j/data.bak-20260610`. GLiNER is opt-in
(`--profile gliner`); spaCy is the default NLP backend with a regex fallback.

## Mode completeness (code-verified surface, not a promise)

| Mode | Backend | Frontend | E2E proof |
|------|---------|----------|-----------|
| Autonomous GM (play loop, dice, oracle, combat, scene/story lifecycle) | Implemented | Play console wired | **smoke passing** (live narration, stat calls, state persisted — 2026-06-11; T-031 extras pending) |
| World Architect (ingest, packs, templates, tables, seed, fork, snapshots, graph) | Implemented | Forge/Worlds/Snapshots/Explorer pages | pending (T-029) |
| GM Co-Pilot (hooks, contradictions, session prep, handouts, canon review) | Implemented | GM page + CanonReviewPanel | pending (T-030) |

Frontend still exposes roughly a third of backend capability — six routers
have no UI at all (`tone`, `lorebook`, `search`, `performance`, `databases`,
`modes`): see `docs/BACKEND_VS_FRONTEND_AUDIT.md` and tasks T-033…T-039.

## Live smoke (T-027, 2026-06-11)

`uv run python scripts/live_gameplay_smoke.py --api-url http://localhost:8001/api`
plays a scripted session against the running stack: real GM narration
(in-fiction, system-aware stat calls), stories created in Neo4j, scenes and
sessions persisted in MongoDB, zero scene-loop failures. Three deep runtime
bugs were found and fixed by this smoke (datetime serialization in prompts,
lost GameSystemRuntime aliases, and an MCP serializer that corrupted every
List[Model] tool result). One residual fallback comes from an invalid
non-default LLM provider credential in `.env` (litellm AuthenticationError,
gracefully handled) — refresh GITHUB_MODELS_TOKEN or remove that provider row.

## Verified play pass (T-055, 2026-06-13)

Driven end-to-end against the dockerized stack (rebuilt `ui-backend`, all
DBs healthy) exercising the new on-ramp and audit trail:

- **Demo world** — `POST /api/forge/demo-world?start_playing=true` (the
  Onboarding Wizard's button, T-057) created/reused the curated **Millhaven**
  universe with no LLM and returned a bound session.
- **Roleplay loop** — three turns over `POST /api/chat/{id}/send` each returned
  fresh, in-fiction GM prose (952 / 678 / 797 chars; 20.8 s / 28.2 s / 18.0 s)
  that referenced the seeded NPCs and locations.
- **World Architect** — a `world_architect` session spawned a new canon NPC
  (Gareth the lamplighter); the turn reported `committed: 1`.
- **Q-10 audit trail (T-064)** — that commit appeared in `GET /api/change-log`
  as `created · entity · CanonKeeper · system` with reason
  "Auto-accepted: user-defined world element via World Architect", confirming
  CanonKeeper's `_commit_to_neo4j` audit hook fires on the architect path
  (which commits in-memory proposals, not via MongoDB).

Two bugs were found and fixed during this pass: the audit hook originally
only read `neo4j_id` from a persisted proposal doc (empty for architect/
quick-world commits) and dereferenced a `None` doc — both corrected so the
log captures every committed proposal regardless of origin.

## Use-case surface sweep (2026-06-14)

Live probe of every mounted API router against the dockerized stack (all 5
datastores `online` via `/api/health?deep=true`):

- **21/21 read surfaces → 200 with real data** — world/universe browse, entity
  graph, chat sessions, modes, **LLM providers + node assignments**, databases
  health (`/api/databases`), NPCs/systems/characters, semantic search, prompts,
  performance, tone, templates, play-sessions, random tables, knowledge packs,
  ingest jobs, Q-10 change log, aggregate health.
- **Write flows verified end-to-end:** PDF ingestion (upload → `completed` job
  in ~90 s → `ready` pack, 14 entities/1 axiom/2 lore); play loop (demo world →
  3 GM-narrated turns); World Architect canon commit surfaced in the change log.

The sweep caught and fixed one real regression: `GET /api/llm/providers` (and
`/assignments`) 500-ed with `UnboundLocalError: existing_rows` —
`_maybe_seed_from_env` wrapped the providers_list() read in `suppress(Exception)`
without a default, so a transient DB read failure left the variable unbound and
broke the entire Settings → LLM tab. Fixed (init `existing_rows = {}` first);
re-probe returns 200 with 9 provider rows + 2 assignments.

## Phase 8 — Vision Hardening progress

- **T-095 GM quality eval harness** — `scripts/eval_gm_playtest.py` scores a
  transcript with an LLM judge against a 5-point rubric → `docs/testing/`.
  Baseline (fresh demo, 6 GM turns): **5/5 all dimensions, avg 5.00** (judge is
  generous on a short happy-path; the instrument is the point — quality is now a
  tracked number for regression-checking later changes).

- **T-096 architect determinism** — deterministic fallback synthesizes the
  entity proposal when the LLM extraction whiffs on an explicit "create NPC
  named X". Live: **5/5** explicit creates now commit (was flaky).
- **T-094 co-pilot threads/hooks** — root cause of the empty CF-3 panel was a
  datetime-coercion bug in `neo4j_list_plot_threads` (raw neo4j DateTime →
  pydantic error → endpoint silently returned 0). Fixed; story bootstrap now
  seeds an opening thread. Hooks (already canon-grounded) went from generic
  "Welcome to Millhaven" to "What Lies Beneath the Canvas" once a thread
  existed to ground on. CF-5 contradictions already work (existing tests).
- **T-097 ingestion recall** — labelled 8-entity fixture PDF → **100% recall
  (8/8)**; all named characters/locations/factions extracted. *Caveats:* the
  analyzer also emits ~12 generic *type* entities (City, Militia, Region…)
  alongside the 8 named ones (precision noise, arguably intentional taxonomy);
  and one run hit an intermittent **`RuntimeError: Event loop is closed` at the
  embed stage** — a real reliability bug (tracked as a follow-up). *Decisions:*
  huge docs (>50 MB) are rejected with a clear message (not streamed); scanned
  PDFs fail loudly ("no extractable text") — OCR remains a future opt-in.

- **T-093 retrieval scoping** — the observed cross-universe "bleed" did *not*
  reproduce (0/5); the live scene/co-pilot path is already universe-isolated
  (it pulls no ingested snippets). Hardened the latent unscoped snippet-search
  API by universe + regression tests. (Likely-hallucination, not a live bug.)
  **2026-06-19 update:** `universe_id` now added to `MemoryCreate`,
  `MemoryFilter`, `MemoryEmbedRequest`, `MemorySearchRequest`, `MemoryResponse`
  schemas. Threaded through `persist_memories` in scene_loop/scene_support.
  Qdrant payload + filter include `universe_id`. 2 new universe-scoped unit
  tests + 51 contract tests updated. *Live two-universe regression pending.*
- **T-092 mechanical layer — engaged.** Two real bugs had kept the HP/combat
  HUD empty: (1) the resolver emits `resolution_type: "trivial"`, which isn't a
  valid `ResolutionType` enum value, so `ResolutionCreate` threw and the
  `except` did `return {}` — aborting `persist_turn_artifacts` *before*
  working-state ever persisted (every trivial-resolution turn); (2)
  `seed_actor_state` read stats only from the scene's entity list, but the
  bound PC's stats live in `actor_context`. Fixed both (safe enum coercion +
  actor_context fallback), and `demo-world` now bootstraps a pregen stat PC in
  auto-roll mode. **Live-verified:** a fresh demo now shows
  `working_state{ current_stats: Grit/Wits/Resolve, resources: Health/Nerve,
  conditions: [pressured], narrative_pressure: high }`. Narrative loop
  unaffected (3/3). *Carryover:* resources seed but don't yet decrement from
  prose combat (the resolver emits no resource deltas without game-system
  damage rules) — tracked as a follow-up.
  **2026-06-19 update:** `quick-world` with `start_playing` now bootstraps a
  demo PC via `_ensure_demo_pc` and binds it to the session with
  `play_mode=dice_game_system`. Chat router (REST + WS) persists
  `latest_working_state`/`latest_scene_checkpoint`/`latest_social_read`/
  `latest_relationship_snapshot` from turn metadata into the session document.
  3 forge API tests + 1 chat router working_state persistence test. *Live
  verification pending.*
- **T-098 embed reliability** — self-healing retry committed (83ff485c):
  `_upsert_points` resets the client and retries once on "Event loop is
  closed". 3 retry-path + 2 reset_client tests pass. *Live stress test pending.*

## Vision playtest (2026-06-14) — measured, not estimated

**Autonomous GM — 15-turn live playtest** (fresh Millhaven session, scripted
investigation → combat → climax → oracle):
- **15/15 turns succeeded**, 0 failures across the full arc.
- **Continuity held:** 14/15 turns echoed proper nouns from prior turns; 14/15
  referenced world canon (Barnaby, Magda, the Cabal, cemetery, fog, amulet).
  The GM sustained a coherent mystery across 15 turns — the "campaign coherence
  unproven" worry is materially reduced.
- Prose: avg **1,162 chars/turn**; resolver engaged (success levels alternated
  pending/success). Phase stayed `active_play`.
- **Latency: median 27 s, mean 25 s, max 39 s** — 8–13× the <3 s SYSTEM target.
  This is the headline gap, not correctness.
- **`working_state` was empty** the whole run: the demo session is pure
  narrative (no character sheet / `dice_game_system`), so HP/resource/combat
  state — and therefore the CombatPanel/HUD — never populate. The mechanical
  layer is built but not exercised by the default demo flow.

**GM Co-Pilot — live session** (gm_assistant recorder + every discrete tool):
all surfaces returned 200 with real output —
- CF-1 recorder reflections (881 / 1,294 chars, substantive),
- CF plot hooks (4; titles generic, e.g. "Welcome to Millhaven"),
- CF-5 contradictions (0 found, ~2.6 s — depth unverified),
- CF session-prep, CF handout (2,253-char in-character letter — strong),
- CF-3 story threads (**0** — thread tracking not populating for this story),
- CF-2 recap (works).
- **Caveat:** a Millhaven reflection referenced "the Ashfall Reaches" (a
  different test universe) — possible cross-universe retrieval-scoping bleed.

Read: both pillars' *plumbing is complete and runs*; the deltas to "vision" are
latency (GM), the unexercised mechanical/combat layer, and co-pilot output
quality + retrieval scoping — quality/perf work, not missing features.

## Measured performance (T-046, 2026-06-12, dev laptop + Gemini flash)

| Operation | Measured | SYSTEM.md target |
|-----------|----------|------------------|
| Full play turn (`POST /chat/{id}/send`, real LLM) | ~6.3 s | < 3 s |
| Semantic search (`/search/search`, incl. query embedding) | ~6.5 s first-call / cold | < 200 ms |
| Universe state (`/universes/.../state`) | ~0.35 s | — |
| Dice resolve (hermetic, no LLM) | < 50 ms | < 500 ms |

Turn and search times are dominated by remote LLM/embedding latency; the
targets assume a faster provider or local embedding cache. Recorded here as
honest baselines, not failures to hide.

## Demo

`uv run python scripts/demo_millhaven.py` (stack must be up) creates the
Millhaven sample world (5 entities, 4 lore facts, canonized) plus a
ready-to-play session, then prints the Play-page instructions. Verified
end-to-end 2026-06-12: the GM narrates in-world on the first message.

## Phase 8B — Session-review remediation (2026-06-14/15)

Tracked in `docs/SESSION_REVIEW_PLAN.md` (criteria: docs · tests · no
hardcoding · new data seeded). **All R-items landed + hermetically proven:**
R1–R3, R5 (seeding/indexes/regressions); **R4** (demo PC resources derived from
the bound system, not literals); **R6** (`condition` rule_type — 0 ValidationErrors
across 8 builtins); **R7** (vitest stood up, 19 frontend tests); **R8/T-091**
(extraction parallelization + Predict + prompt caching + real WebSocket narrator
streaming + resolver→LIGHT; fan-out edge bug fixed); **R9/T-098** (self-healing
qdrant upsert retry on a closed event loop); **R10** (state tags derived from track
threshold/depleted data, not a hardcoded HP≤0 vocabulary or alias table). Two
**live-only gates remain open** (no hermetic proof): R8 turn-latency numbers
(< 8 s median / < 3 s first-token, observed over WebSocket) and R9's 10-consecutive-
ingest soak — both need a build-free window with the stack up.

## SOLID/DRY refactoring (2026-06-05 → 2026-06-21)

All 10 tasks from the refactoring plan are complete and verified.

| # | Principle | What changed | Files |
|---|-----------|-------------|-------|
| 1 | DB efficiency | `verify_nodes_exist` batched into single `WHERE id IN $list` query | `neo4j_tools/_helpers.py` |
| 2 | DRY | `AuditMixin` for shared `id`/`created_at`/`updated_at` schema fields | `schemas/base.py`, `schemas/entities.py` |
| 3 | DRY | Shared document→response conversion helpers | `mongodb_tools/_conversion_helpers.py` |
| 4 | Error handling | `exc_info=True` + `logger.warning` on all JSON parse fallback paths | `base.py`, `narrator.py`, `canonkeeper.py`, `context_assembly.py` |
| 5 | SRP | `CommitDispatcherMixin` extracted from CanonKeeper god class | `commit_dispatcher.py` (new), `canonkeeper.py` |
| 6 | DIP | `AgentFactory` + `get_agent_factory()` singleton for loop node injection | `agent_factory.py` (new), `scene_loop.py`, `story_loop.py` |
| 7 | SRP | `derive_state_deltas` split into 3 focused sub-functions | `loops/scene_support.py` |
| 8 | OCP | `CommitHandlerRegistry` + `@commit_handler` decorator for extensible commit handlers | `handlers/registry.py`, `handlers/__init__.py` (new) |
| 9 | DRY | `_TONE_PROFILES` removed from `Narrator`; single source of truth via `BUILTIN_TONE_PROFILES` in `tone_resolver.py` | `narrator.py`, `utils/tone_resolver.py`, `tests/behavior/test_P_5_behavior.py` |
| 10 | Error handling | `call_tool` JSON parse failure now logs with `exc_info=True` | `base.py` |

**Verification:** CanonKeeper tests (35 passed), P-5 behavior + tone resolver tests (28 passed), all module imports clean, zero lint/type errors.

## Known deferrals

- **P-21 Autonomous PC Actions** — formally deferred (was the original P-15 YAML intent).
- **Mutation testing** — formally removed (mutmut broken upstream, cosmic-ray hangs on async stack).
- **OpenTelemetry export** — logfire runs local-only; OTLP env passthrough is T-044.
- **Coverage cold spots** — `mongodb_tools/snapshots.py` ~31%, `merge_candidates.py` ~19% (T-042).

## Reproduce these numbers

```bash
uv run pytest packages tests -q --tb=no            # full hermetic suite
uv run ruff check packages                         # lint
uv run python scripts/check_layer_dependencies.py  # layer boundaries
cd packages/ui/frontend && npx tsc --noEmit        # frontend types
docker ps --format '{{.Names}}: {{.Status}}'       # stack health
```
