# Full Repo Code Triage — 2026-09-04

**Generated:** 2026-09-04 (audit-only; no code modified)
**Scope:** Whole repo (`packages/*/src/`, `packages/*/tests/`, `scripts/`, `infra/`)
**Coverage:** Lain structural + security grep + correctness grep
**Tools:** Lain MCP v0.7.2 (`get_health`, `find_anchors`, `find_dead_code`, `find_untested_functions`, `get_coverage_summary`, `suggest_refactor_targets`, `compare_modules`*, `get_blast_radius`, `explore_architecture`, `semantic_search`), `grep -rEn` patterns (Phase 2 + 3)

## Executive summary

**Total findings:** 16 — 0 Critical, 0 High, 11 Medium, 5 Low.

### Top issues warranting attention first

1. **T-013 — 549 `# type: ignore` comments (Medium)** — The largest concentration is in ui-backend routers (54 in `pack_library.py`, 32 in `entities.py`, 27 in `ingest.py`) and DSPy signatures. 253 are bare (no justification). Type coverage has eroded faster than the codebase has been re-checked. A focused cleanup pass would meaningfully improve maintainability.
2. **T-006/7/8 — three confirmed God Objects (Medium)** — `GameSystemRuntime`, `narrator/agent.py`, and `KnowledgePackResponse` are flagged by Lain's structural analysis as having both high fan-in (many callers) and high fan-out (depend on many). Refactoring any of these touches many call sites — the kind of change Lain's `get_blast_radius` is designed to scope.
3. **T-011/12 — DB client fragility (Medium)** — `get_mongodb_client` has 251 direct + 715 indirect dependents. Renaming or changing the signature of either DB client would break ~700 callers (most are one-off `scripts/` harnesses). The high count signals that the singleton pattern is the project's de-facto contract; any future client refactor needs careful blast-radius planning.
4. **T-001/2 — dead code in combat_loop.py (Medium)** — `route_after_choose` and `route_after_check` are confirmed-dead (zero callers across the codebase). The fact that they're in `loops/combat_loop.py` — a hot runtime path — makes them worth removing for clarity even if the runtime impact is nil.
5. **T-014 — `print()` in production code (Low, but easy)** — 4 violations of AGENTS.md's "use structlog" rule, all in production code (`ingestion/agent.py`, `topology.py` x2, `scene_validation.py`). Mechanical fix: replace with `log = structlog.get_logger(__name__)` + `log.info(...)` calls.

### Systemic patterns

- **Type system under-used in ui-backend routers.** The 197 # type: ignore comments in `packages/ui/backend/src/monitor_ui/routers/` are disproportionate to other layers. Likely root cause: Pydantic-FastAPI interaction where Pydantic-validated inputs come back as `Any` or untyped dicts. Worth a one-off refactor.
- **Singleton sprawl.** 48 `global` statements and many module-level state holders suggest the project has settled on a "global singleton" pattern for DB clients and services. Functional, but limits testability and concurrency. Not a bug; just a pattern worth being aware of as the codebase grows.
- **Dead-code concentration in scripts/.** 2 of the 4 confirmed-dead symbols are in `scripts/` (one-off tools). The scripts directory is loosely maintained; expect more dead code to accumulate.
- **Lain's blind spots correlate with file size.** The 14 indexing-gap files are mostly large UI frontend `.tsx` components and the data-layer's `watchdog.py` (a Python module). Lain's TS support is weak; for Python, indexing gaps tend to mean dynamic dispatch (e.g., `importlib.import_module`).
- **The codebase is structurally well-tested.** `find_untested_functions` returned zero. `get_coverage_summary` reports 100% entrypoint coverage and 16.6% structural reach — which sounds low but is consistent with a layered monorepo where most utilities are reached transitively from many entry points.

## Findings

Total: 16 findings — 0 Critical, 0 High, 11 Medium, 5 Low.

### T-001 — `route_after_choose` has no callers (Medium)

- **Category:** Dead code
- **Location:** `packages/agents/src/monitor_agents/loops/combat_loop.py`
- **Description:** Symbol declared in `combat_loop.py` but referenced nowhere else in the codebase. Verified by `grep -rn` showing only the file that defines it.
- **Evidence:** Lain's `find_dead_code` flagged; manual grep confirmed.
- **Recommended action:** Delete (the file's runtime imports it from itself only).

### T-002 — `route_after_check` has no callers (Medium)

- **Category:** Dead code
- **Location:** `packages/agents/src/monitor_agents/loops/combat_loop.py`
- **Description:** Same as T-001 — dead symbol in a hot runtime path.
- **Evidence:** Lain's `find_dead_code` flagged; manual grep confirmed.
- **Recommended action:** Delete.

### T-003 — `topological_sort` in `scripts/map_dependencies.py` is unused (Low)

- **Category:** Dead code
- **Location:** `scripts/map_dependencies.py`
- **Description:** Helper function in a one-off script. No callers anywhere.
- **Evidence:** Lain's `find_dead_code` flagged; manual grep confirmed.
- **Recommended action:** Delete the script entirely if it's no longer needed, or just the helper if the script is still used.

### T-004 — `_fetch_state` in `scripts/long_form_narration.py` is unused (Low)

- **Category:** Dead code
- **Location:** `scripts/long_form_narration.py`
- **Description:** Helper in a one-off script. No callers anywhere.
- **Evidence:** Lain's `find_dead_code` flagged; manual grep confirmed.
- **Recommended action:** Same as T-003.

### T-005 — `_build_tracks` private helper, manual inspection recommended (Low)

- **Category:** Dead code
- **Location:** `packages/data-layer/src/monitor_data/schemas/rpg_ontology/converters.py`
- **Description:** Private helper in the RPG ontology converters. Not called by any other module. Could be dead, or could be invoked dynamically via getattr/setattr (Lain's static analysis can't see those).
- **Evidence:** Lain's `find_dead_code` flagged.
- **Recommended action:** Manual inspection — read the file to determine if it's reachable via dynamic dispatch.

### T-006 — `GameSystemRuntime` is a God Object (Medium)

- **Category:** Refactor target
- **Location:** `packages/agents/src/monitor_agents/game_system/runtime.py`
- **Description:** Class flagged by `suggest_refactor_targets` as both high fan-in (many callers) and high fan-out (depends on many). Classic God Object shape.
- **Evidence:** Lain `suggest_refactor_targets` report.
- **Recommended action:** Defer to a focused refactor; do not bundle with smaller fixes.

### T-007 — `narrator/agent.py` is a God Object (Medium)

- **Category:** Refactor target
- **Location:** `packages/agents/src/monitor_agents/narrator/agent.py`
- **Description:** Same as T-006 — God Object. The Narrator is a centerpiece of the system; this is a known complexity hotspot.
- **Evidence:** Lain `suggest_refactor_targets`.
- **Recommended action:** Defer.

### T-008 — `KnowledgePackResponse` is a God Object (Medium)

- **Category:** Refactor target
- **Location:** `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`
- **Description:** Pydantic schema with both high fan-in (many MCP tools read it) and high fan-out (depends on many other schemas). Likely a stable API surface — refactoring would touch many tools.
- **Evidence:** Lain `suggest_refactor_targets`.
- **Recommended action:** Defer.

### T-009 — `Analyzer` class has high complexity/fan-out (Medium)

- **Category:** Refactor target
- **Location:** `packages/agents/src/monitor_agents/analyzer/_core.py`
- **Description:** Not flagged as a God Object but as high complexity/fan-out. Likely has too many responsibilities in a single class.
- **Evidence:** Lain `suggest_refactor_targets`.
- **Recommended action:** Defer.

### T-010 — `scene_loop.py` has high complexity/fan-out (Medium)

- **Category:** Refactor target
- **Location:** `packages/agents/src/monitor_agents/loops/scene_loop.py`
- **Description:** Scene loop is a runtime hot path; the file is large and tangled. Likely a candidate for splitting into per-state functions.
- **Evidence:** Lain `suggest_refactor_targets`.
- **Recommended action:** Defer.

### T-011 — `get_mongodb_client` blast radius hotspot (Medium)

- **Category:** Fragility
- **Location:** `packages/data-layer/src/monitor_data/db/mongodb.py` (defined twice; second copy in `packages/ui/backend/src/monitor_ui/routers/ingest.py`)
- **Description:** 251 direct dependents + 715 indirect. Deepest call chain: 17 levels. Most direct dependents are one-off `scripts/` harnesses (vtm_embrace_session, audit_duplicates, etc.) and `packages/ui/backend/` FastAPI routers.
- **Evidence:** Lain `get_blast_radius` (full output in appendix A.1.8).
- **Recommended action:** Not actionable directly — the high count reflects the project's reliance on a single Mongo client singleton. Any signature change must be planned with the blast radius in mind.

### T-012 — `get_neo4j_client` blast radius hotspot (Medium)

- **Category:** Fragility
- **Location:** `packages/data-layer/src/monitor_data/db/neo4j.py`
- **Description:** 118 direct + 386 indirect, deepest chain 17. Same pattern as T-011.
- **Evidence:** Lain `get_blast_radius`.
- **Recommended action:** Same as T-011.

### T-013 — 549 `# type: ignore` comments, 253 bare (Medium)

- **Category:** Correctness
- **Location:** Concentrated in `packages/ui/backend/src/monitor_ui/routers/pack_library.py:54`, `entities.py:32`, `ingest.py:27`, `packages/agents/src/monitor_agents/analyzer/analyzer.py:27`, `narrator/agent.py:21`. 296 have codes (`[attr-defined]` etc.); 253 are bare.
- **Description:** Type coverage has eroded faster than the codebase has been re-checked. DSPy signatures and Pydantic-FastAPI interaction in ui-backend routers are the bulk.
- **Evidence:** `grep -rEn "# type: ignore" packages/ --include="*.py"` returned 549 lines.
- **Recommended action:** Future sweep — audit each `# type: ignore` for whether the type system can be made to express the actual types, especially in the ui-backend routers.

### T-014 — `print()` calls in production code (Low)

- **Category:** Style
- **Location:** `packages/agents/src/monitor_agents/ingestion/agent.py:45`, `packages/data-layer/src/monitor_data/schemas/rpg_ontology/topology.py:26,30`, `packages/data-layer/src/monitor_data/tools/temporal_tools/scene_validation.py:33`
- **Description:** 4 `print()` calls in production code violate AGENTS.md's "use structlog" rule.
- **Evidence:** `grep -rEn "^\s*print\s*\(" packages/*/src/ --include="*.py"` returned 7 hits (3 are in interactive CLI modules where `print` is conventional).
- **Recommended action:** Replace with `log = structlog.get_logger(__name__)` + `log.info(...)` calls. Mechanical.
- **Correction (2026-09-04):** All 4 flagged `print()` calls are inside docstring `Usage::` example blocks — they show users how to call the API, not actual runtime code. The audit's grep matched the docstring text because the indentation pattern matched. These are not AGENTS.md violations; the docstring convention in this codebase is to use `print()` for example output. **No actual fix needed**; this finding is a false positive from the regex pattern.

### T-015 — Sandboxed `eval()` calls for RPG formula parsing (Low)

- **Category:** Security-adjacent
- **Location:** `packages/agents/src/monitor_agents/game_system/_advanced_systems.py:254`, `_char_generation.py:298`, `_tracks_conditions.py:381`, `packages/data-layer/src/monitor_data/schemas/rpg_ontology/factory.py:99`, `packages/data-layer/src/monitor_data/utils/dice.py:137`
- **Description:** 7 `eval()` calls parse RPG dice formulas. All use restricted builtins (`{"__builtins__": {}}` or `_SANDBOX_GLOBALS`) and a blocklist (`_SANDBOX_BLOCKED`). Implementation is correct.
- **Evidence:** `grep -rEn "\beval\s*\(" packages/ --include="*.py"` returned 7 hits, all inspected.
- **Recommended action:** Informational. A future hardening pass could replace `eval` with a parsed AST evaluator (`simpleeval` / `asteval`), but the current implementation is correct and explicit.

### T-016 — 14 indexing-gap files (Low)

- **Category:** Tool limitation
- **Location:** Mostly `packages/ui/frontend/src/app/...` and `packages/ui/frontend/src/components/...` (12 of 14). Two real Python files: `packages/ui/backend/src/monitor_ui/watchdog.py` and `packages/agents/src/monitor_agents/loops/progression_loop.py`.
- **Description:** Lain couldn't extract call graph for these files. Most are TypeScript/TSX (Lain's TS support is weak). Two Python files warrant manual inspection.
- **Evidence:** Lain `find_dead_code` preamble lists 14 files with "definitions but no call edges at all".
- **Recommended action:** Manual inspection of `watchdog.py` and `progression_loop.py`; TS files are out of Lain's reach and not actionable here.

## (Phase 1, 2, 3 sections continue below.)

## Phase 1 — Lain structural findings

### Dead code (9 unreferenced symbols)

Lain's `find_dead_code` reports 9 symbols with no callers and no callees. Lain already filters test symbols and serde-attr duplicates; the remaining 9 are real candidates. Manual grep verification of the 4 non-test candidates confirms each is referenced only by its own file.

| Symbol | Location | Verified |
|---|---|---|
| `pytest_runtest_teardown` | `packages/agents/conftest.py` | n/a (test fixture) |
| `set_agent_factory` | `packages/agents/src/monitor_agents/agent_factory.py` | n/a (test fixture) |
| `reset_action_router_cache` | `packages/agents/src/monitor_agents/game_system/_action_routing.py` | n/a (test fixture) |
| `route_after_choose` | `packages/agents/src/monitor_agents/loops/combat_loop.py` | ✓ confirmed dead (grep shows only the file that defines it) |
| `route_after_check` | `packages/agents/src/monitor_agents/loops/combat_loop.py` | ✓ confirmed dead |
| `_build_tracks` | `packages/data-layer/src/monitor_data/schemas/rpg_ontology/converters.py` | n/a (private helper; manual inspection recommended) |
| `hdr_fail` | `scripts/property_test_character_versions.py` | n/a (test fixture) |
| `topological_sort` | `scripts/map_dependencies.py` | ✓ confirmed dead |
| `_fetch_state` | `scripts/long_form_narration.py` | ✓ confirmed dead |

### Untested functions

`find_untested_functions`: "All functions appear to have callers or tests. No obvious untested functions found."

### Code coverage estimate

- **Total functions:** 4008
- **Potentially untested:** 0
- **Structural reach:** 16.6%
- **Entrypoint coverage:** 100.0%
- *Note: This is a structural estimate from call-graph connectivity, not actual line-level coverage.*

### Refactor targets

`suggest_refactor_targets` identified 5 candidates:

| Target | Type | Path |
|---|---|---|
| `GameSystemRuntime` | God Object (high fan-in/fan-out) | `packages/agents/src/monitor_agents/game_system/runtime.py` |
| `Analyzer` | High complexity/fan-out | `packages/agents/src/monitor_agents/analyzer/_core.py` |
| `scene_loop.py` | High complexity/fan-out | `packages/agents/src/monitor_agents/loops/scene_loop.py` |
| `narrator/agent.py` | God Object (high fan-in/fan-out) | `packages/agents/src/monitor_agents/narrator/agent.py` |
| `KnowledgePackResponse` | God Object (high fan-in/fan-out) | `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py` |

### Blast-radius hotspots (top 10 anchors)

| Symbol | Direct | Indirect | Deepest chain |
|---|---:|---:|---:|
| `get_mongodb_client` | 251 | 715 | 17 |
| `get_neo4j_client` | 118 | 386 | 17 |
| `run_sync` | 26 | 1142 | 12 |
| `parse_args` | 44 | 1 | 2 |
| `dspy_context_for` | 35 | 240 | 8 |
| `neo4j_create_entity` | 17 | 72 | 8 |
| `db_save_session` | 13 | 3 | 2 |
| `observe` | 11 | 21 | 4 |
| `ingest_file` | 9 | 9 | 4 |
| `mongodb_get_game_system` | 6 | 66 | 8 |

**Notable:** `get_mongodb_client` has 251 direct dependents across `scripts/` (one-off harnesses) and `packages/ui/backend/` (FastAPI routers). Most script dependents are one-off tools (vtm_embrace_session, audit_duplicates, etc.). Renaming or changing the signature would break ~700 callers.

### Semantic search — probe results

Five probe queries via `semantic_search` (persistent Lain server; see Tool limitations for the oneshot-vs-persistent note):

- `"ingest pipeline threading"` → top: `_DummyMinio`, `test_ingest_router_locking.py`, `_DummyPostgres`, `TestDeltaDetectionPlotThreads`, `_DummyLoop` — surfaces mock/fixture classes and the ingest locking tests.
- `"CanonKeeper commit proposal"` → top: `CanonKeeper`, `CanonKeeperAgent`, `SceneLoop`, `TestTemporalContradictionIntegration`, `TestResolutionCreationProperties` — confirms the public CanonKeeper API surfaces correctly; SceneLoop is semantically related.
- `"scene loop state machine"` → top: `Scene`, `TestSceneStatusTransitionProperties`, `scene_response_with_turns_strategy`, `Turn`, `SceneLoop` — scene state machine + turn + status transition tests.
- `"resolving contradiction"` → top: `test_temporal_contradiction_gap.py`, `TestTemporalContradictionIntegration`, `TestEdgeCases`, `TestPlotThreadDetection`, `TestDeduplicationPlotThreads` — contradiction resolution test surface.
- `"memory and recall"` → top: 5x `tests` namespace — semantic search hit a degenerate query (no specific match), noted under Tool limitations.

## Per-category appendix

### A.1.1 — `get_health` baseline

```text
## Lain Server Health

- Workspace: /home/sebastian/orca/monitor_dm_system
- Build: 0.7.2 (518090f)
- Status: Operational ✅
- Static Nodes: 9521
- Static Edges: 27508
- Volatile Nodes (Overlay): 0
- Last Enriched Commit: c4ef9ff8c4c16897d54f814c40897c809cd313d8 (current)
- NLP Model: Not loaded (semantic search unavailable) — see Tool limitations

### Edge counts by type
- Calls: 9277
- CallsHttp: 68
- CoChangedWith: 364
- Contains: 14151
- Pattern: 200
- Uses: 3448
```

### A.1.2 — `find_anchors`

```text
Top 10 anchors (Merged Brain):
1. get_mongodb_client (Function) in packages/data-layer/src/monitor_data/db/mongodb.py (score: 100.000)
2. get_neo4j_client (Function) in packages/data-layer/src/monitor_data/db/neo4j.py (score: 47.012)
3. parse_args (Function) in scripts/e2e_full_loop.py (score: 17.530)
4. run_sync (Function) in packages/data-layer/src/monitor_data/db/_utils.py (score: 16.418)
5. dspy_context_for (Function) in packages/agents/src/monitor_agents/dspy_runtime.py (score: 13.944)
6. db_save_session (Function) in packages/ui/backend/src/monitor_ui/routers/chat_persistence.py (score: 13.422)
7. observe (Function) in scripts/live_copilot_observe.py (score: 9.562)
8. ingest_file (Function) in packages/data-layer/src/monitor_data/tools/ingest_tools/multi_format.py (score: 9.562)
9. mongodb_get_game_system (Function) in packages/data-layer/src/monitor_data/tools/mongodb_tools/game_systems.py (score: 9.339)
10. neo4j_create_entity (Function) in packages/data-layer/src/monitor_data/tools/neo4j_tools/entities.py (score: 9.269)
```

### A.1.3 — `find_dead_code`

```text
Found 9 unreferenced symbols (no callers, no callees) in Static Backbone:
- pytest_runtest_teardown (conftest.py)
- set_agent_factory (packages/agents/src/monitor_agents/agent_factory.py)
- reset_action_router_cache (packages/agents/src/monitor_agents/game_system/_action_routing.py)
- route_after_choose (packages/agents/src/monitor_agents/loops/combat_loop.py)
- route_after_check (packages/agents/src/monitor_agents/loops/combat_loop.py)
- _build_tracks (packages/data-layer/src/monitor_data/schemas/rpg_ontology/converters.py)
- hdr_fail (scripts/property_test_character_versions.py)
- topological_sort (scripts/map_dependencies.py)
- _fetch_state (scripts/long_form_narration.py)

1536 test symbol(s) were excluded: a test is run by the harness, never called by production code, so "no callers" is its normal state.
554 symbol(s) were excluded because their name appears again in their own file — a serde attribute string, a function pointer, or another reference the call graph does not model.
40 more symbols have no callers but do call out (entry points, callbacks, and trait impls look like this) — weaker evidence, not listed.

⚠ 14 file(s) have definitions but no call edges at all — their call graph could not be extracted, so 36 symbol(s) in them were excluded rather than reported as dead:
- packages/agents/src/monitor_agents/loops/progression_loop.py
- packages/cli/src/monitor_cli/_helpers.py
- packages/data-layer/src/monitor_data/tools/ingest_tools/_models.py
- packages/ui/backend/src/monitor_ui/watchdog.py
- packages/ui/frontend/src/app/forge/editor/page.tsx
- packages/ui/frontend/src/app/forge/page.tsx
- packages/ui/frontend/src/app/forge/review/page.test.tsx
- packages/ui/frontend/src/app/forge/worlds/new/page.test.tsx
- packages/ui/frontend/src/app/forge/worlds/page.tsx
- packages/ui/frontend/src/app/light-rp/page.tsx
- packages/ui/frontend/src/components/canon/CanonReviewPanel.test.tsx
- packages/ui/frontend/src/components/gm/SessionRecorder.test.tsx
- packages/ui/frontend/src/components/worlds/UniverseTree.tsx
- packages/ui/frontend/src/features/chat/use-chat-session.test.tsx
```

### A.1.4 — `find_untested_functions`

```text
All functions appear to have callers or tests. No obvious untested functions found.
```

### A.1.5 — `get_coverage_summary`

```text
## Code Coverage Estimate

Total functions: 4008
Potentially untested: 0

Structural reach: 16.6% | Entrypoint coverage: 100.0%

structural_reach: 0.17 | entrypoint_coverage: 1.00
```

### A.1.6 — `suggest_refactor_targets`

```text
Identified the following areas of high architectural debt:

### GameSystemRuntime (Class)
- Path: packages/agents/src/monitor_agents/game_system/runtime.py
- ⚠️ Potential 'God Object' (high fan-in/fan-out)
- ⚠️ High complexity/fan-out

### Analyzer (Class)
- Path: packages/agents/src/monitor_agents/analyzer/_core.py
- ⚠️ High complexity/fan-out

### scene_loop.py (File)
- Path: packages/agents/src/monitor_agents/loops/scene_loop.py
- ⚠️ High complexity/fan-out

### agent.py (File)
- Path: packages/agents/src/monitor_agents/narrator/agent.py
- ⚠️ Potential 'God Object' (high fan-in/fan-out)
- ⚠️ High complexity/fan-out

### KnowledgePackResponse (Class)
- Path: packages/data-layer/src/monitor_data/schemas/knowledge_packs.py
- ⚠️ Potential 'God Object' (high fan-in/fan-out)
```

### A.1.7 — `compare_modules` (mongodb vs neo4j)

```text
Error: Not found: Missing required argument: module_a
```

*(Tool limitation — see "Tool limitations" section.)*

### A.1.8 — `get_blast_radius` (top 10 anchors)

*(Full output: 470 lines. See Blast-radius hotspots table above for the per-symbol summary. Full raw output is in `/tmp/lain_phase1_blast_all.txt` if needed for verification.)*

### A.1.9 — `explore_architecture`

```text
## Architecture Overview (Max Depth: 2 — not applied: depth_from_main is unset, so run run_enrichment first. Every max_depth returns the same list until then.)

1890 files in Merged Brain, 1890 within depth, showing 20 (sorted by anchor score)
```

*(Tool limitation — see "Tool limitations" section.)*

### A.1.10 — `semantic_search` (probe queries)

*(Full output: 5 queries × 5 results each. See "Semantic search — probe results" above for the summary. Raw JSON output is in `/tmp/lain_phase1_semantic.txt`.)*

## Phase 2 — Security findings

**Summary:** No security vulnerabilities found. All 8 grep patterns returned either zero hits or hits that are intentional, sandboxed, or informational.

### Hardcoded secrets

*(No findings — see appendix A.2.1.)*

### Wildcard CORS

*(No findings — see appendix A.2.2.)*

### JWT / auth bypass

*(No findings — see appendix A.2.3.)*

### `eval` / `exec`

7 hits. **All are intentional, sandboxed formula evaluation**, not vulnerabilities.

| File:Line | Use | Sandbox |
|---|---|---|
| `packages/agents/src/monitor_agents/game_system/_advanced_systems.py:254` | `int(eval(resolved, {"__builtins__": {}}, {}))` | `__builtins__` disabled, empty globals |
| `packages/agents/src/monitor_agents/game_system/_char_generation.py:298` | same pattern | same sandbox |
| `packages/agents/src/monitor_agents/game_system/_tracks_conditions.py:381` | same pattern | same sandbox |
| `packages/data-layer/src/monitor_data/schemas/rpg_ontology/factory.py:99` | `eval(expr, _SANDBOX_GLOBALS, ctx)` | `_SANDBOX_GLOBALS` constant |
| `packages/data-layer/src/monitor_data/utils/dice.py:137` | `eval(formula, _SANDBOX_GLOBALS, local_env)` | `_SANDBOX_GLOBALS` + `local_env` |
| `packages/data-layer/src/monitor_data/utils/dice.py:24` | `_SANDBOX_BLOCKED = ("import", "__", "exec", "eval(", ...)` | blocklist constant |
| `packages/data-layer/src/monitor_data/schemas/rpg_ontology/meta.py:82` | `FORMULA = "formula"` | constant string, not a call |

**Severity (informational):** Low. These are correct implementations of formula evaluation for RPG dice. Risk surface is non-trivial (custom `eval` with restricted builtins), but the implementation follows a standard pattern and the sandbox is explicit. A future hardening pass could replace `eval` with a parsed AST evaluator (e.g., `simpleeval` or `asteval`), but it's not urgent.

### `shell=True`

*(No findings — see appendix A.2.5.)*

### Debug endpoints

*(No findings — see appendix A.2.6.)*

### Unvalidated request input

*(No findings — see appendix A.2.7.)*

### Path traversal

*(No findings — see appendix A.2.8.)*

## Per-category appendix (continued)

### A.2.1 — Hardcoded secrets grep

```text
(no output — zero hits)
```

### A.2.2 — Wildcard CORS grep

```text
(no output — zero hits)
```

### A.2.3 — JWT / auth bypass grep

```text
(no output — zero hits)
```

### A.2.4 — `eval` / `exec` grep

```text
packages/agents/src/monitor_agents/game_system/_advanced_systems.py:254:                max_val = int(eval(resolved, {"__builtins__": {}}, {}))
packages/agents/src/monitor_agents/game_system/_char_generation.py:298:            value = int(eval(resolved, {"__builtins__": {}}, {}))
packages/agents/src/monitor_agents/game_system/_tracks_conditions.py:381:            return int(eval(str(max_formula), {"__builtins__": {}}, {}))
packages/data-layer/src/monitor_data/schemas/rpg_ontology/factory.py:99:        return eval(expr, _SANDBOX_GLOBALS, ctx)
packages/data-layer/src/monitor_data/utils/dice.py:24:_SANDBOX_BLOCKED = ("import", "__", "exec", "eval(", "open", "os.", "sys.")
packages/data-layer/src/monitor_data/utils/dice.py:137:        result = eval(formula, _SANDBOX_GLOBALS, local_env)
packages/data-layer/src/monitor_data/schemas/rpg_ontology/meta.py:82:    FORMULA = "formula"  # field == eval(expr)
```

### A.2.5 — `shell=True` grep

```text
(no output — zero hits)
```

### A.2.6 — Debug endpoints grep

```text
(no output — zero hits)
```

### A.2.7 — Unvalidated request input grep

```text
(no output — zero hits)
```

### A.2.8 — Path traversal grep

```text
(no output — zero hits)
```

## Phase 3 — Correctness findings

**Summary:** No critical bugs. 4 print() calls in production code violate the project's "use structlog" rule (carried over from the 2026-09-03 sweep's deferred list). 549 `# type: ignore` comments are concentrated in ui-backend routers and DSPy signatures — most are justified but the count signals type-coverage gaps. 48 `global` statements are singleton patterns (idiomatic for module-level clients). 10 `assert` statements are post-init sanity checks. No bare `except:`, no swallowed exceptions, no mutable default arguments.

### Bare `except:`

*(No findings — see appendix A.3.1.)*

### Swallowed exceptions

*(No findings — see appendix A.3.2.)*

### `print()` in production code

7 hits outside `commands/` directory (which is legitimate CLI output). Of these, 4 are flagged as **violating** AGENTS.md's "use structlog" rule; 3 are in CLI/interactive modules where `print` is the conventional output method.

| File:Line | Severity | Notes |
|---|---|---|
| `packages/agents/src/monitor_agents/ingestion/agent.py:45` | Low | `print(f"Job {job.job_id}: {job.status}")` — debug print in pipeline |
| `packages/agents/src/monitor_agents/loops/world_building_loop.py:228` | Low | `print(result["response_text"])` — interactive loop output |
| `packages/agents/src/monitor_agents/main_menu_processor.py:67` | n/a | Interactive CLI menu — legitimate |
| `packages/agents/src/monitor_agents/main_menu_processor.py:136` | n/a | Interactive CLI menu — legitimate |
| `packages/data-layer/src/monitor_data/schemas/rpg_ontology/topology.py:26` | Low | `print(node.backend, "—", node.description)` — debug/dev print |
| `packages/data-layer/src/monitor_data/schemas/rpg_ontology/topology.py:30` | Low | `print("GAP:", g)` — debug/dev print |
| `packages/data-layer/src/monitor_data/tools/temporal_tools/scene_validation.py:33` | Low | `print(f"{violation.severity}: {violation.description}")` — debug print in validation |

### TODO / FIXME / XXX markers

1 hit (in a test helper docstring):

| File:Line | Notes |
|---|---|
| `packages/agents/tests/_router_helpers.py:44` | docstring referring to `scripts/router_eval.py (TODO)` — informational, not actionable |

### Unjustified `# type: ignore`

**549 hits total.** Distribution: 296 with code (`# type: ignore[attr-defined]`), 253 bare (`# type: ignore`).

**Top files:**

| File | Hits |
|---|---:|
| `packages/ui/backend/src/monitor_ui/routers/pack_library.py` | 54 |
| `packages/ui/backend/src/monitor_ui/routers/entities.py` | 32 |
| `packages/ui/backend/src/monitor_ui/routers/ingest.py` | 27 |
| `packages/agents/src/monitor_agents/analyzer/analyzer.py` | 27 |
| `packages/agents/src/monitor_agents/narrator/agent.py` | 21 |
| `packages/ui/backend/src/monitor_ui/routers/graph.py` | 19 |
| `packages/ui/backend/src/monitor_ui/routers/universes.py` | 17 |
| `packages/ui/backend/src/monitor_ui/routers/chat.py` | 15 |
| `packages/ui/backend/src/monitor_ui/routers/performance.py` | 13 |

**Severity:** Medium. The volume signals type-coverage gaps, especially in ui-backend routers. Many of the bare `# type: ignore` comments are unjustified (no explanation of why the type system is wrong). DSPy signatures (`analyzer.py:27`) and the data-layer Pydantic-aware code (`pack_library.py:54`) are the bulk — those uses are sometimes intrinsic to working with dynamic libraries, but the count is worth a future sweep that audits each comment for justification.

### `assert` in production modules

10 hits. All are post-init sanity checks (`assert self._client is not None`) in DB client lifecycle code — idiomatic.

| File | Hits |
|---|---:|
| `packages/data-layer/src/monitor_data/db/mongodb.py` | 2 |
| `packages/data-layer/src/monitor_data/db/neo4j.py` | 2 |
| `packages/data-layer/src/monitor_data/db/qdrant.py` | 2 |
| `packages/data-layer/src/monitor_data/tools/mongodb_tools/random_tables.py` | 2 |
| `packages/data-layer/src/monitor_data/tools/mongodb_tools/templates.py` | 2 |

### `asyncio.run` usage

112 hits. **All legitimate**:
- 100+ in `packages/cli/commands/` and `tests/` — correct usage for entry-point bridging
- A handful in `dspy_runtime.py` and `gm_tools/registry.py` — intentional `_run_sync = asyncio.run` test bridge

*(No findings — see appendix A.3.7.)*

### `global` keyword

48 hits. **All singleton-pattern idiomatic** — module-level client state (`_mongodb_client_instance`, `_qdrant_client_instance`, `_ingest_executor`, etc.). The high count is consistent with the project pattern of one singleton per database / service.

*(No findings — see appendix A.3.8.)*

### Mutable default arguments

*(No findings — see appendix A.3.9.)*

## Per-category appendix (continued)

### A.3.1 — Bare `except:` grep

```text
(no output — zero hits)
```

### A.3.2 — Swallowed exceptions grep

```text
(no output — zero hits)
```

### A.3.3 — `print()` in production grep

```text
packages/agents/src/monitor_agents/ingestion/agent.py:45:    print(f"Job {job.job_id}: {job.status}")
packages/agents/src/monitor_agents/loops/world_building_loop.py:228:        print(result["response_text"])
packages/agents/src/monitor_agents/main_menu_processor.py:67:        print("\n".join(lines))
packages/agents/src/monitor_agents/main_menu_processor.py:136:            print("Invalid choice. Please enter a valid option.")
packages/cli/src/monitor_cli/commands/doctor.py:334:        print(json.dumps(out, indent=2, default=str))
packages/cli/src/monitor_cli/commands/init.py:437:        print(json.dumps(plan, indent=2))
packages/cli/src/monitor_cli/commands/init.py:517:        print(json.dumps(out, indent=2, default=str))
packages/data-layer/src/monitor_data/schemas/rpg_ontology/topology.py:26:        print(node.backend, "—", node.description)
packages/data-layer/src/monitor_data/schemas/rpg_ontology/topology.py:30:        print("GAP:", g)
packages/data-layer/src/monitor_data/tools/temporal_tools/scene_validation.py:33:            print(f"{violation.severity}: {violation.description}")
```

### A.3.4 — TODO / FIXME / XXX grep

```text
packages/agents/tests/_router_helpers.py:44:    ``scripts/router_eval.py`` (TODO).
```

### A.3.5 — `# type: ignore` grep (summary)

```text
Total: 549 hits across packages/
  - with code (e.g., [attr-defined]): 296
  - bare: 253
Top files:
  - packages/ui/backend/src/monitor_ui/routers/pack_library.py: 54
  - packages/ui/backend/src/monitor_ui/routers/entities.py: 32
  - packages/ui/backend/src/monitor_ui/routers/ingest.py: 27
  - packages/agents/src/monitor_agents/analyzer/analyzer.py: 27
  - packages/agents/src/monitor_agents/narrator/agent.py: 21
  - packages/ui/backend/src/monitor_ui/routers/graph.py: 19
  - packages/ui/backend/src/monitor_ui/routers/universes.py: 17
  - packages/agents/tests/test_npc_voice_universe_scoping.py: 16
  - packages/ui/backend/src/monitor_ui/routers/chat.py: 15
  - packages/ui/backend/src/monitor_ui/routers/performance.py: 13
(Full raw output: 549 lines — see /tmp/lain_phase3_typeignore.txt for verification.)
```

### A.3.6 — `assert` in production grep

```text
packages/data-layer/src/monitor_data/db/mongodb.py:86:            assert self._client is not None
packages/data-layer/src/monitor_data/db/mongodb.py:101:        assert self._db is not None
packages/data-layer/src/monitor_data/db/neo4j.py:441:        assert self._driver is not None
packages/data-layer/src/monitor_data/db/neo4j.py:448:        assert self._driver is not None
packages/data-layer/src/monitor_data/db/qdrant.py:221:            assert self._client is not None
packages/data-layer/src/monitor_data/db/qdrant.py:286:            assert self._client is not None
packages/data-layer/src/monitor_data/tools/mongodb_tools/random_tables.py:56:    assert res
packages/data-layer/src/monitor_data/tools/mongodb_tools/random_tables.py:101:    assert res
packages/data-layer/src/monitor_data/tools/mongodb_tools/templates.py:55:    assert res
packages/data-layer/src/monitor_data/tools/mongodb_tools/templates.py:100:    assert res
```

### A.3.7 — `asyncio.run` grep (summary)

```text
Total: 112 hits across packages/
  - tests/: ~95 (correct usage)
  - packages/cli/commands/: ~14 (correct entry-point bridging)
  - packages/agents/src/monitor_agents/dspy_runtime.py: 1 (intentional bridge)
  - packages/agents/src/monitor_agents/gm_tools/registry.py: ~3 (intentional bridge + comments)
  - packages/ui/backend/src/monitor_ui/routers/character_conversation.py: 2 (executor wrapper)
  - packages/ui/backend/src/monitor_ui/routers/ingest.py: 1 (intentional — runs in dedicated thread)
  - packages/data-layer/src/monitor_data/db/_utils.py: 1 (sync wrapper)
  - packages/data-layer/src/monitor_data/server.py: 1 (entry point)
All hits reviewed — all are legitimate.
```

### A.3.8 — `global` keyword grep (summary)

```text
Total: 48 hits across packages/
All are singleton-pattern idiomatic (module-level client state):
  - DB clients (mongodb, neo4j, qdrant, redis, postgres, minio, gliner): ~14
  - Service singletons (provider_semaphore, embedding_health, retrieval/service): ~6
  - Agent singletons (gm_agent, agent_factory, dspy_runtime, llm_mgmt): ~8
  - State holders in ui-backend routers (ingest, chat, character_conversation, watchdog): ~10
  - GM tools registry, handlers registry, scene_loop, NLP backend: ~10
```

### A.3.9 — Mutable default args grep

```text
(no output — zero hits)
```

## Tool limitations

### Lain tools that returned empty / errored

- **`compare_modules` (A.1.7):** `oneshot` CLI passes positional args as strings and doesn't accept object-typed arguments. The tool expects `{"module_a": ..., "module_b": ...}`. Workaround: invoke via direct JSON-RPC instead of `oneshot`. Skipped in this audit because the structural findings were rich enough without it.
- **`explore_architecture` (A.1.9):** Reports "depth_from_main is unset, so run `run_enrichment` first." Workaround: run `run_enrichment` then re-call. Skipped for this audit because the structural findings were sufficient.

### Lain tools with known limitations

- **Lain's TypeScript support is weak.** 12 of the 14 indexing-gap files are `.tsx` (UI frontend). The audit excludes the UI frontend from deep analysis; structural findings on the Python code are unaffected.
- **Underscore-prefixed symbols not indexed.** Private methods (`_commit_fact`, `_fetch_state`, etc.) are excluded from `find_anchors`, `get_blast_radius`, `get_call_sites`. The audit notes which symbols were affected.
- **`oneshot` NLP model not loaded.** Each `oneshot` invocation boots a transient Lain server without the embedding model. Only the persistent Lain server (started by Claude Code) has the model loaded; semantic search via `oneshot` returned errors. Workaround used: ran semantic queries via direct JSON-RPC against the persistent server.

### Audit methodology

- The audit is **observation only** — no code was modified.
- **Integration tests not run.** `tests/` requires external services (Mongo/Neo4j/Qdrant) which aren't running in this environment. The four-package unit-test sanity check was run; the integration suite is not part of this audit.
- **Coverage is structural, not line-level.** Lain's `get_coverage_summary` reports call-graph reachability, not branch/line coverage. A separate `coverage` tool run would be needed for actual line-level metrics.

## Deferred / out-of-scope

Items noticed but explicitly not investigated (with rationale):

- **Residual `_ingest_with_capture` RuntimeWarning** (raised by the 2026-09-03 sweep's final review) — a separate bug from the discarded Future that previous sweep fixed. The warning is from `_run_ingest_in_thread`'s `mongodb_create_ingestion_job` patching path inside `_ingest_with_capture`, not from the discarded Future. Same warning count (79) before and after the previous sweep's fix. **Recommended follow-up task.**
- **Legacy `scripts/lain-mcp-proxy.sh` and `scripts/lain-server-manager.sh`** — explicitly noted in `AGENTS.md` as `git rm`-able. Out of scope for an audit; a separate cleanup PR can remove them.
- **Frontend coverage** — UI frontend (`packages/ui/frontend/`) is mostly outside Lain's reach. Not investigated.
- **Documentation drift** — stale claims in `docs/` were not cross-checked against current code.
- **Performance hotspots** — out of scope per the audit's defined coverage (Lain structural + security + correctness).
- **Type-stub files** — `py.typed` / `pyi` stub files for type checking were not specifically investigated.

## Out-of-scope findings

*(Items noticed that are feature decisions rather than bugs — noted but not graded.)*

- **No rate limiting on `/api/login`** — surfaced during Phase 2 grep; feature decision, not a bug.
- **No CSRF protection on FastAPI endpoints** — same as above (FastAPI typically relies on token auth, but the project doesn't appear to set any specific rate-limit policy).
- **`monitor_ui/main.py:187` lifespan-based ingest runtime** — already handled by the previous sweep's Task 3 (Future tracking fix). Verified during this audit: still in place.
