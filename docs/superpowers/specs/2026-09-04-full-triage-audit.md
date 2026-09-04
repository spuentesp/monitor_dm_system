# Full Repo Code Triage — 2026-09-04

**Generated:** 2026-09-04 (audit-only; no code modified)
**Scope:** Whole repo (`packages/*/src/`, `packages/*/tests/`, `scripts/`, `infra/`)
**Coverage:** Lain structural + security grep + correctness grep
**Tools:** Lain MCP v0.7.2 (`get_health`, `find_anchors`, `find_dead_code`, `find_untested_functions`, `get_coverage_summary`, `suggest_refactor_targets`, `compare_modules`*, `get_blast_radius`, `explore_architecture`, `semantic_search`), `grep -rEn` patterns (Phase 2 + 3)

## Executive summary

*(Filled by Task 4.)*

## Findings

*(Filled by Task 4 after all phases complete.)*

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

*(Filled by Task 2.)*

## Phase 3 — Correctness findings

*(Filled by Task 3.)*

## Tool limitations

*(Filled by Task 4.)*

## Deferred / out-of-scope

*(Filled by Task 4.)*

## Out-of-scope findings

*(Filled by Task 4.)*
