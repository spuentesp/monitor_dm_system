# World Forge — Direct Manipulation & Generative Rules Plan

> **Status:** in progress
> **Author:** World Architect assessment follow-up
> **Scope:** Close the gap between MONITOR's strong *generative* world-building
> brain and its thin *direct-manipulation* surface, plus extend the Architect to
> generate **system rules**, not just lore.

## Context

The world-creation stack today:

- **Generation** is good: `WorldArchitect` (conversational, gap-steering) +
  `QuickWorldBuilder` (one-seed → playable world). Both auto-canonize via
  `CanonKeeper`.
- **Visualization** is good: React Flow graph in `explorer/page.tsx`,
  `worlds/page.tsx`, and the Architect mini-graph — colour-coded, ego-graph
  drill-down, filters, search.
- **Manipulation** is thin: read + delete + fork + snapshots only. The graph
  inspector advertises "inspect and **edit**" but is read-only. The data layer
  already has `neo4j_update_entity`, `neo4j_create_character_relationship`,
  `neo4j_create_entity`, and `neo4j_fork_universe` — they are simply **not wired
  into the graph UI**, and there is **no single-entity REST endpoint**.
- **Rules** are narrative only: the Architect extracts `axiom`s (prose truths)
  but never mechanical rules, even though `neo4j_create_resolution_mechanic` /
  `neo4j_create_ability_system` exist.

## Architectural rules honored

- Layers: `data-layer (1) → agents (2) → cli/ui (3)`; dependencies flow down only.
- **Only `CanonKeeper` writes Neo4j.** All graph mutations from the UI go through
  the backend → a `CanonKeeper`-authority path (the World Architect already
  auto-commits this way for user-deliberate edits).
- Every change references a use-case ID (`M-36`..`M-41`).
- Every change ships unit + integration tests; integration/e2e tests are marked
  and gated by `RUN_INTEGRATION=1` / `RUN_E2E=1`.
- `structlog`, never `print()`. `async` on agent methods that touch MCP tools.

## Path conventions

- `entities` router is mounted at `/api/entities` and defines `/entities/...`
  paths → public path is `/api/entities/entities/{id}` (doubled, like universes).
- `universes` router → `/api/universes/universes/...`.

---

## Gap 1 — Edit entities directly from the graph (`M-36`)

**Goal:** Click a node → edit name / description / tags / properties → save →
graph reflects canon.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 1.1 | `GET /entities/{id}` returning full entity (wrap `neo4j_get_entity`) | 3 (backend) | `routers/entities.py` |
| 1.2 | `PATCH /entities/{id}` (wrap `neo4j_update_entity`; tags via `neo4j_update_state_tags`) under CanonKeeper authority | 3 (backend) | `routers/entities.py` |
| 1.3 | `entitiesApi.getEntity` + `entitiesApi.updateEntity` | 3 (frontend) | `lib/api.ts` |
| 1.4 | Editable `InspectorPanel` (name/description/tags) with save + optimistic refetch | 3 (frontend) | `worlds/page.tsx`, `explorer/page.tsx` |
| 1.5 | Contract tests (mocked tools) | test | `tests/test_entities_crud.py` |
| 1.6 | Integration test (real Neo4j: create→update→read round-trip) | test | `tests/test_entities_crud_integration.py` |
| 1.7 | Frontend lib test for `updateEntity` payload shaping | test | `lib/entitiesApi.test.ts` |

**Done when:** editing a node persists to Neo4j and survives reload.

## Gap 2 — Create relationships inline on the graph (`M-37`)

**Goal:** Drag from a node handle to another node → pick a relation type → an edge
is persisted between the two entities.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 2.1 | Generalize `POST /entities/relationships` to any entity pair + rel type + properties; return created edge | 3 (backend) | `routers/entities.py` |
| 2.2 | `GET /entities/{id}/relationships` (list edges for inspector) | 3 (backend) | `routers/entities.py` |
| 2.3 | `entitiesApi.createRelationship` + `listRelationships` | 3 (frontend) | `lib/api.ts` |
| 2.4 | React Flow `onConnect` → rel-type modal → persist → add edge | 3 (frontend) | `explorer/page.tsx` |
| 2.5 | Contract + integration tests | test | `tests/test_relationships.py` (+ integration) |

## Gap 3 — Create nodes on the graph canvas (`M-38`)

**Goal:** "+ Add node" affordance on the canvas → type/name → entity created in the
selected universe and added to the graph.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 3.1 | `POST /entities/entities` single-entity create (wrap `neo4j_create_entity`, CanonKeeper authority) | 3 (backend) | `routers/entities.py` |
| 3.2 | `entitiesApi.createEntity` | 3 (frontend) | `lib/api.ts` |
| 3.3 | Add-node UI (mini-form / palette) on explorer canvas | 3 (frontend) | `explorer/page.tsx` |
| 3.4 | Contract + integration tests | test | `tests/test_entities_crud*.py` |

## Gap 4 — Universe split & merge (`M-39`, `M-40`)

Built on the proven `neo4j_fork_universe` template (deep-clone + `id_map` +
relationship remap + `alt_world_type`/`parent_universe_id`).

| # | Task | Layer | Files |
|---|------|-------|-------|
| 4.1 | `neo4j_split_universe(source, name, entity_ids)` → clone the selected subset + induced relationships into a new universe (`alt_world_type='split'`) | 1 (data) | `neo4j_tools/core.py` |
| 4.2 | `neo4j_merge_universes(source_ids, name, dedupe_by='name')` → union canon into a new universe, dedupe entities by name, remap relationships (`alt_world_type='merge'`) | 1 (data) | `neo4j_tools/core.py` |
| 4.3 | `POST /universes/{id}/split` and `POST /universes/merge` | 3 (backend) | `routers/universes.py` |
| 4.4 | `universesApi.splitUniverse` + `mergeUniverses` + UI (multiselect in explorer → split; tree multi-select → merge) | 3 (frontend) | `lib/api.ts`, `worlds`/`explorer` |
| 4.5 | Data-layer integration tests (real Neo4j round-trips) + backend contract tests | test | `data-layer tests/`, `backend tests/` |

## Gap 5 — Architect generates system rules (`M-41`)

**Goal:** The Architect can author *mechanical* rules (resolution mechanics,
ability systems), not just lore axioms.

| # | Task | Layer | Files |
|---|------|-------|-------|
| 5.1 | Add `resolution_mechanic` + `ability_system` to the DSPy extraction vocabulary | 2 (agents) | `prompts/world_architect.py` |
| 5.2 | Parse those proposal types in `_parse_proposals` | 2 (agents) | `world_architect.py` |
| 5.3 | Commit via `neo4j_create_resolution_mechanic` / `neo4j_create_ability_system` in `_commit_proposals` | 2 (agents) | `world_architect.py` |
| 5.4 | Agent unit tests (parse + commit, tools mocked) | test | `agents tests/` |

---

## Test strategy ("real usage")

- **Unit / contract:** FastAPI `TestClient` with the underlying `neo4j_*` tool
  `patch`ed (the established `test_universes.py` pattern). Fast, no DB.
- **Integration (`@pytest.mark.integration`, `RUN_INTEGRATION=1`):** hit a real
  Neo4j. Each test creates its own multiverse/universe, performs the real
  round-trip (create → edit → relate → split/merge → read back), and tears down.
- **Frontend:** Vitest lib tests for API payload shaping (the existing
  `*.test.ts` pattern under `lib/`), plus the Playwright e2e harness for the
  edit-on-graph flow where practical.

## Rollout order

1. **Gap 1** (edit) — unlocks "direct manipulation" with zero new data-layer work.
2. **Gap 2** (relate) — makes the graph feel like a tool.
3. **Gap 3** (create) — completes node CRUD on the canvas.
4. **Gap 4** (split/merge) — the headline multiverse capability.
5. **Gap 5** (rules) — deepens generation.
