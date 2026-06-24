# MONITOR

*Multi-Ontology Narrative Intelligence Through Omniversal Representation*

**An Auto-GM system for tabletop RPGs and narrative games, built on a data-first, canonization-driven architecture.**

---

## What MONITOR Is

MONITOR is a **narrative intelligence system for tabletop RPGs**. It combines a canonical graph, narrative memory, semantic retrieval, and loop-based agents so worlds and sessions stay coherent over time.

### Current Runtime Reality (June 2026)

- **Interactive play:** the web chat flow in `packages/ui/backend/src/monitor_ui/routers/chat.py`
- **Wired CLI commands:** `monitor play`, `monitor manage`, `monitor universe`, `monitor ingest`, `monitor state`, `monitor rules`, `monitor mechanics`, and `monitor playtest`
- **Live data-layer MCP families:** `neo4j_*`, `mongodb_*`, `qdrant_*`, and `ingest_*`

### Core Principles

1. **Data-first** — persistent state lives in databases, not prompt memory
2. **Canonization-driven** — proposals become canon only after explicit evaluation
3. **Layered** — `cli → agents → data-layer`
4. **Provenance-aware** — canonical facts keep evidence links to sources or scenes

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    USER SURFACES                         │
│   Web UI (FastAPI + Next.js)  |  CLI (`monitor ...`)    │
└────────────────────────┬─────────────────────────────────┘
                         │ dispatches to
┌────────────────────────▼─────────────────────────────────┐
│               AGENTS + LANGGRAPH LOOPS                   │
│ SceneLoop | StoryLoop | TurnLoop | ConversationLoop      │
│ WorldBuildingLoop | Narrator | Resolver | CanonKeeper    │
└────────────────────────┬─────────────────────────────────┘
                         │ data-layer tools
┌────────────────────────▼─────────────────────────────────┐
│                    DATA LAYER API                        │
│  - Authority enforcement (CanonKeeper owns scene canon)  │
│  - Schema validation (Pydantic models)                   │
│  - Live MCP families: `neo4j_*`, `mongodb_*`,            │
│    `qdrant_*`, and `ingest_*`                            │
└─┬────────┬────────┬────────┬──────────┬──────────────────┘
  │        │        │        │          │
  ▼        ▼        ▼        ▼          ▼
 Neo4j   MongoDB   Qdrant  PostgreSQL  MinIO
                     (+ OpenSearch is provisioned in infra and remains optional)
```

---

## Quick Start (verified 2026-06-12)

### 1. Install workspace + create env files

```bash
uv sync                       # installs all four packages (uv workspace)
cp env.example .env           # fill in secrets / provider keys
cp env.example infra/.env
```

### 2. Start the stack

```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d
# or ./dev.sh for the infra + local backend/frontend combo
```

All nine containers report healthy; `curl localhost:8001/api/health?deep=true`
aggregates component status.

### 3. Seed the demo and play

```bash
uv run python scripts/demo_millhaven.py   # Millhaven world + ready session
# open http://localhost:3000/play and pick "The Millhaven Disappearances"

uv run monitor playtest live --turns 3     # scripted live session via CLI
```

### 4. Run the test suite (hermetic — no keys, no network)

```bash
uv run pytest packages tests -q            # ~5,900 tests, < 6 minutes
RUN_E2E=1 RUN_INTEGRATION=1 uv run pytest tests/e2e -q --timeout=300  # full-stack e2e
```

> `docs/USE_CASES.md` describes the broader target command surface (`play`, `manage`, `query`, and more). `packages/cli/src/monitor_cli/main.py` is the source of truth for what is currently wired up in the repo.
>
> **Current runtime reality:** the primary interactive play surface is the web chat UI, and `monitor playtest` is the wired CLI path for end-to-end autonomous-GM validation.

### Environment variables

- Copy `env.example` to `.env` and reuse the same values in `infra/.env` for Docker-based local runs.
- To publish the values to GitHub Actions secrets/variables, run `scripts/push_env_to_github.sh env.example` (or pass your `.env`) — requires authenticated `gh` CLI.
- To audit drift between `env.example` and GitHub Actions, run `scripts/check_env_drift.sh env.example`; it reports missing/extra keys without printing values.

### GitHub automation quick wins

- PR auto-labeling and test reminder: runs in CI via `.github/workflows/auto-label.yml`, or manually with `scripts/auto_label_and_comment.sh <pr#>`.
- Weekly health snapshot: `scripts/weekly_health_report.sh --days 7 [--discussion <category>|--issue <number>]` to print or post merged PRs, stale issues, and failing runs.
- Rerun failed workflows: `scripts/rerun_failed_workflow.sh --pr <number> [--comment]` (or `--branch <name>`) to restart the latest failed run.

---

## Documentation Map

Use the canonical docs below instead of hunting through overlapping summaries:

| Canon doc | Purpose |
|-----------|---------|
| [`docs/_index.md`](docs/_index.md) | **Documentation Map** — entry point for architecture, product, loops, and ontology |
| [`STRUCTURE.md`](STRUCTURE.md) | Repo layout and folder ownership |
| [`docs/USE_CASES.md`](docs/USE_CASES.md) | Use-case catalog and workflow targets |
| [`infra/README.md`](infra/README.md) | Local infrastructure setup and maintenance |

For subsystem detail, see [`docs/2_architecture/`](docs/2_architecture/) and [`docs/4_ontology/`](docs/4_ontology/).

---

## Contributing

Before changing code or docs:

1. Read `docs/_index.md` and `STRUCTURE.md`
2. Respect layer boundaries (`cli → agents → data-layer`)
3. Add or update tests for behavior changes
4. Reference the relevant use-case ID in your PR or commit message

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`AGENT_SETUP.md`](AGENT_SETUP.md) for contributor workflow details.

---

## License

MIT License. See [`LICENSE`](LICENSE) for details.

