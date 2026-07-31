# MONITOR — Folder Structure

> Folder-structure reference for the monorepo. Linked from [AGENTS.md](AGENTS.md).
> Reflects the actual tree; regenerate this file when top-level layout changes.

---

## Root Level

```text
<repo-root>/
├── AGENTS.md             # Agent instructions (architecture rules, build/test/lint commands)
├── CLAUDE.md             # Agent guidance incl. CanonKeeper forbidden patterns
├── README.md             # Project overview for humans
├── CONTRIBUTING.md       # Contribution workflow
├── CHANGELOG.md          # Release notes
├── STRUCTURE.md          # THIS FILE
├── LICENSE
├── pyproject.toml        # uv workspace root (4 packages) + shared tool config
├── uv.lock               # Locked Python dependencies
├── pytest.ini            # Pytest markers (unit / integration / e2e)
├── conftest.py           # Root pytest fixtures
├── package.json          # npm scripts proxying to packages/ui/frontend
├── Makefile              # Common dev tasks
├── dev.sh / tmux-dev.sh  # Start infra + backend + frontend
├── env.example           # Environment template (never commit `.env`)
├── codecov.yml           # Coverage config
├── cosmic-ray*.toml      # Mutation-testing configs (one per agent/loop)
│
├── packages/             # The three layers + UI (uv workspace members)
├── tests/                # Cross-package integration/e2e suites
├── docs/                 # Canonical documentation
├── infra/                # Docker Compose for the database cluster
├── scripts/              # Dev/ops utilities (~100 files)
├── specs/                # TLA+ specifications
├── conductor/            # Planning scratch space
│
├── .github/workflows/    # CI
├── .vscode/              # Editor + MCP (Lain) config
├── .run/                 # IDE run configurations
└── .claude/              # Claude Code settings
```

Runtime/local artifacts not shown: `node_modules/`, `.venv/`, `__pycache__/`,
`.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `.hypothesis/`, `.coverage`,
`test_logs/` (log dumps from live runs), `session*.sqlite`, `coverage_full.json`,
`test_adv*.py` (ad-hoc scratch scripts at root).

---

## packages/ — The Layers

Dependency flow is strictly downward: **cli → agents → data-layer**. The UI
backend (FastAPI) sits alongside the CLI as another interface over agents.
See [docs/2_architecture/the_three_layers.md](docs/2_architecture/the_three_layers.md).

### packages/data-layer (Layer 1, `monitor_data`)

DB clients, MCP tools, schemas. Imports external libs only — never agents or CLI.

```text
packages/data-layer/
├── pyproject.toml, README.md, tests/
└── src/monitor_data/
    ├── db/               # Neo4j, MongoDB, Qdrant, Postgres clients
    ├── tools/            # MCP tools, auto-registered by server.py
    │   ├── neo4j_tools/, mongodb_tools/, ingest_tools/,
    │   ├── plot_thread_tools/, temporal_tools/
    │   ├── qdrant_tools.py, rpg_tools.py, nlp_tools.py, lain_tools.py, ...
    │   └── _shared.py
    ├── schemas/          # Pydantic v2 models (facts, entities, CanonLevel, ...)
    ├── middleware/       # Authority checks for write tools (auth.py)
    ├── retrieval/        # Retrieval service
    ├── llm/              # LLM provider clients/config + image_providers.py
    ├── contracts/        # Cross-layer data contracts
    ├── invariants/       # Invariant checks
    ├── initialization/   # Bootstrap/seed logic
    ├── data/, defaults/  # Bundled data and default configs
    └── utils/
```

### packages/agents (Layer 2, `monitor_agents`)

LLM calls, loops, AI logic. Talks to the data-layer via MCP tools only.
All agents inherit `BaseAgent` (`base.py`); only CanonKeeper may write to Neo4j.

```text
packages/agents/
├── pyproject.toml, README.md, tests/
└── src/monitor_agents/
    ├── base.py                # BaseAgent
    ├── canonkeeper.py         # CanonKeeper (sole Neo4j writer) + canonkeeper_support.py
    ├── narrator.py, gm_agent.py, npc_voice.py, resolver.py, oracle.py, ...
    ├── context_assembly.py, turn_context.py, token_budget.py
    ├── ingestion_pipeline.py, indexer.py
    ├── loops/                 # LangGraph loops: scene_loop.py, story_loop.py,
    │                          #   combat_loop.py, conversation_loop.py,
    │                          #   character_creation_loop.py, session_zero_loop.py,
    │                          #   progression_loop.py, ingestion_loop.py,
    │                          #   world_building_loop.py, session_bootstrap.py
    ├── services/              # Persistence and retrieval services
    ├── analyzer/, classifiers/, parsers/
    ├── game_system/           # Game-system (ruleset) support
    ├── gm_tools/, tools/, handlers/, players/, utils/
    └── llm_registry.py, llm_execution.py, dspy_runtime.py
```

### packages/cli (Layer 3, `monitor_cli`)

Commands, REPL, terminal UI. Imports agents only — never the data-layer.

```text
packages/cli/
├── pyproject.toml, README.md, IMPLEMENTATION.md, tests/
└── src/monitor_cli/
    ├── main.py             # Entry point
    ├── commands/           # play.py, manage.py, ingest.py, rules.py, state.py,
    │                       #   universe.py, mechanics.py, playtest.py, ingest_jobs.py, ...
    ├── repl/               # Interactive REPL
    └── ui/                 # Terminal UI helpers
```

### packages/ui — Web interface

```text
packages/ui/
├── backend/                # FastAPI app (monitor_ui)
│   ├── pyproject.toml, Dockerfile, tests/
│   └── src/monitor_ui/
│       ├── main.py, config.py, watchdog.py
│       └── routers/        # REST/WebSocket routers; chat_ws.py drives SceneLoop
│                           #   (chat*, ingest*, entities*, universes, stories,
│                           #    canon_review, forge, pack_library, gm_tools,
│                           #    image_gen, ...)
└── frontend/               # Next.js + TypeScript + Tailwind
    ├── package.json, next.config.ts, playwright.config.ts, vitest.config.ts, Dockerfile
    ├── src/                # app/, components/, features/, hooks/, lib/
    │                       #   two-tier hub routes: / (Lobby), /light-rp (Light RP),
    │                       #   /forge + /gm (Workbench), /config (Configuration)
    └── e2e/                # Playwright tests
```

---

## tests/ — Cross-Package Suites

Per-package unit tests live in `packages/*/tests/`; this tree holds the
integration/e2e layers. Markers: `unit` (default), `integration`
(`RUN_INTEGRATION=1`), `e2e` (`RUN_E2E=1`). `FakeMCPClient` and
`FakeLLMClient` live in `tests/conftest.py`.

```text
tests/
├── conftest.py           # Shared fakes and fixtures
├── unit/                 # Cross-cutting unit tests
├── api/                  # FastAPI router tests (chat, entities, forge, universes, ...)
├── behavior/             # Use-case behavior tests (test_P_*, test_M_*, test_CF_*, ...)
├── contracts/            # Schema/contract tests between layers
├── property/             # Hypothesis property tests
├── e2e/                  # End-to-end runs (logs/ internals not documented here)
├── fixtures/, mocks/     # Test data and mock implementations
└── test_*.py             # Top-level integration tests (chat router, ingestion gaps, ...)
```

---

## docs/ — Canonical Documentation

Entry point: [docs/_index.md](docs/_index.md). Status: [docs/STATUS.md](docs/STATUS.md).

```text
docs/
├── _index.md, STATUS.md
├── 1_product/            # Vision, modes, epics, ideal state
├── 2_architecture/       # The three layers, per-layer docs, MCP transport,
│                         #   ProposedChange pattern, data-model workflow
├── 3_loops_and_systems/  # One doc per loop (scene, story, combat, conversation,
│                         #   ingestion, progression, session zero, character creation, ...)
├── 4_ontology/           # Entity types, fact canon levels, graph relationships
├── 5_infrastructure/     # Database cluster, observability, Lain MCP proxy
├── 6_reference/          # gameplay_examples/ — worked session walkthroughs
├── architecture/         # Current design/audit docs (GM-as-authority, retrieval
│                         #   service, gap remediation, ingestion pipeline audit, ...)
├── use-cases/            # Use-case catalog, split per epic
│   ├── _schema.yml
│   └── epic-*/           # epic-0-data-layer-DL .. epic-11-system-SYS
├── USE_CASES.md          # Use-case index
├── testing/              # Test harness docs, replays, live GM-vs-player runs
├── contributing/         # e.g. badges
└── blog/                 # Blog drafts (post-01 .. post-09; drafts, not reference docs)
```

---

## infra/ — Database Cluster

```text
infra/
├── docker-compose.yml            # Base services
├── docker-compose.override.yml   # Local overrides
├── .env.example, README.md
├── neo4j/      # data/, import/, logs/, plugins/
├── mongodb/
├── postgres/
├── qdrant/
└── minio/
```

Start with:
`docker compose --env-file .env -f infra/docker-compose.yml up -d`
(or just `./dev.sh`, which brings up infra + backend + frontend).

---

## scripts/ — Dev/Ops Utilities (~100 files)

One-line summary: everything that isn't shipped code lives here — guard
scripts (`check_layer_dependencies.py`, `require_tests_for_code_changes.py`,
`require_use_case_reference.py`, `check_env_drift.sh`), live/e2e playtest and
replay harnesses (`e2e_full_loop*.py`, `run_e2e_replays.py`, `live_*`,
`*_replay.py`), analysis/reporting (`analyze_*.py`, `weekly_health_report.sh`),
seeding/migration (`seed_*.py`, `migrate_*.py`, `reindex_embeddings.py`),
GitHub/project sync (`sync_*.sh`, `check_issue_dependencies.py`), Lain/infra
helpers (`lain-mcp-proxy.sh`, `setup-lain-mcp.sh`, `doctor.sh`), demos, and the
`monitor` executable helper. See `scripts/README.md`.

---

## specs/ — TLA+ Specifications

```text
specs/
├── turn_flow.tla
├── scene_atomicity.tla
├── proposed_change_workflow.tla
├── canon_keeper.tla
└── layer_direction.tla
```

Formal models of core invariants (turn flow, scene atomicity, the
ProposedChange workflow, CanonKeeper authority, layer dependency direction).

---

## conductor/

Planning scratch space (`conductor/plan.md`) — working notes, not canonical
docs. Canonical documentation belongs in `docs/`.
