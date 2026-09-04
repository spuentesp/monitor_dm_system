# MONITOR — Agent Instructions

> Narrative AI system for tabletop RPGs. Three-layer Python monorepo.

## Architecture (read first)

| Layer | Package | Imports | Role |
|-------|---------|---------|------|
| 3 CLI | `monitor-cli` | agents only | Commands, REPL, terminal UI |
| 2 Agents | `monitor-agents` | data-layer only | LLM calls, loops, AI logic |
| 1 Data-layer | `monitor-data-layer` | external libs only | DB clients, MCP tools, schemas |

**Dependencies flow downward. Never import upward or skip layers.**

See [docs/2_architecture/the_three_layers.md](docs/2_architecture/the_three_layers.md) for full rules, and [docs/_index.md](docs/_index.md) for the documentation map.

## CanonKeeper Authority

**Only CanonKeeper can write to Neo4j.** All other agents create `ProposedChange` documents in MongoDB. CanonKeeper evaluates and commits. See [CLAUDE.md](CLAUDE.md) for the forbidden-pattern examples.

## Build & Run

```bash
uv sync                                    # install all packages
cp env.example .env                        # configure (edit values)
docker compose --env-file .env -f infra/docker-compose.yml up -d   # start DBs
./dev.sh                                   # infra + backend + frontend
```

## Test

```bash
uv run pytest packages -q                  # all
uv run pytest packages/data-layer -v       # by layer
uv run pytest packages/agents -v
uv run pytest tests/ -q                    # integration/e2e (tests/ root)
```

Markers: `@pytest.mark.unit` (default), `@pytest.mark.integration` (needs `RUN_INTEGRATION=1`), `@pytest.mark.e2e` (needs `RUN_E2E=1`).

Fixtures: `FakeMCPClient` and `FakeLLMClient` in [tests/conftest.py](tests/conftest.py).

## Lint & Format

```bash
uv run ruff check packages                 # lint
uv run ruff format packages                # format
uv run mypy packages/*/src --cache-dir /tmp/mypy-cache  # type-check
python scripts/check_layer_dependencies.py # boundary enforcement
```

Config: line-length 100, target Python 3.11, mypy strict.

## Key Conventions

### Imports

```python
# ✅ CLI → agents
from monitor_agents.loops import SceneLoop

# ✅ Agents → data-layer
from monitor_data.schemas.facts import FactCreate

# ❌ CLI → data-layer (FORBIDDEN)
from monitor_data.db.neo4j import Neo4jClient  # WRONG
```

### Agents (Layer 2)

All agents inherit `BaseAgent` ([base.py](packages/agents/src/monitor_agents/base.py)). They call data-layer via MCP tools, never directly. DSPy modules are co-located with their respective agents in dedicated package directories (e.g., `extraction/`, `canonkeeper/`). Loops are LangGraph graphs in `loops/`.

### MCP Tools (Layer 1)

Tools live in `packages/data-layer/src/monitor_data/tools/`. Auto-registered by `server.py`. Each tool group has its own module (`neo4j_tools/`, `mongodb_tools/`, `qdrant_tools.py`, `ingest_tools/`). Write tools require authority checks in `middleware/auth.py`.

### Schemas (Layer 1)

Pydantic v2 models in `packages/data-layer/src/monitor_data/schemas/`. Base enums in `base.py`. Entity types: Archetype vs Instance. Facts have CanonLevel.

### UI Backend

FastAPI app at `packages/ui/backend/src/monitor_ui/`. Routers in `routers/`. The chat router drives `SceneLoop` via WebSocket.

## Documentation Map

The documentation for MONITOR has been restructured for agent-friendliness.

**Start Here:** [docs/_index.md](docs/_index.md)

Quick Links:
- Product & Epics: [docs/1_product/_index.md](docs/1_product/_index.md)
- Architecture & Layers: [docs/2_architecture/_index.md](docs/2_architecture/_index.md)
- Loops & Systems: [docs/3_loops_and_systems/_index.md](docs/3_loops_and_systems/_index.md)
- Ontology & Models: [docs/4_ontology/_index.md](docs/4_ontology/_index.md)
- Infrastructure: [docs/5_infrastructure/_index.md](docs/5_infrastructure/_index.md)
- Folder Structure: [STRUCTURE.md](STRUCTURE.md)
- Use-case catalog: [docs/USE_CASES.md](docs/USE_CASES.md)
- Contributing workflow: [CONTRIBUTING.md](CONTRIBUTING.md)

## Common Mistakes

- Importing data-layer from CLI → route through an agent instead
- Writing to Neo4j outside CanonKeeper → use `ProposedChange` in MongoDB
- Skipping `check_layer_dependencies.py` before committing → run it
- Forgetting `async` on agent methods that call MCP tools → all MCP calls are async
- Using `print()` for logging → use `structlog` (`import structlog; log = structlog.get_logger()`)

## MCP Tools (Lain)

Lain is configured as an MCP server in [`.claude/settings.json`](.claude/settings.json)
on stdio (no HTTP proxy — Lain 0.6+ dropped the combined stdio+http mode):

```json
{
  "mcpServers": {
    "lain": {
      "command": "lain",
      "args": [
        "mcp",
        "--workspace", "/home/sebastian/orca/monitor_dm_system",
        "--embedding-model", "/home/sebastian/orca/monitor_dm_system/.lain/models"
      ]
    }
  }
}
```

Lain binary: `~/.local/lain/lain` (v0.7.2, MCP protocol 2025-11-25).
Installed via the [official installer](https://raw.githubusercontent.com/spuentesp/lain/main/install.sh)
from [spuentesp/lain](https://github.com/spuentesp/lain/releases/tag/v0.7.2).
ONNX model: `BGE-small-en-v1.5` at `/home/sebastian/orca/monitor_dm_system/.lain/models/model.onnx`
(see [setup recipe](https://github.com/spuentesp/lain#optional-semantic-search)).

`LAIN_EMBEDDING_MODEL` is exported in `~/.bashrc` for ad-hoc CLI usage. The MCP
config pins the model path explicitly so it does not depend on the env var.

Use Lain for:
- Blast radius analysis (`get_blast_radius`)
- Dependency traces (`trace_dependency`, `get_call_chain`)
- Dead code detection (`find_dead_code`)
- Semantic search (`semantic_search`) — requires the ONNX model above
- Architectural exploration (`explore_architecture`, `find_anchors`)
- Build/test integration (`run_build`, `run_tests`, `run_clippy`)

Health checks (no HTTP listener in stdio mode):
```bash
# Binary + version
~/.local/lain/lain --version
# Installation sanity (binary, hooks, registered MCP server)
~/.local/lain/lain doctor
# Spinning the MCP server against this workspace: start a tool-calling session
# in this agent and call get_health, or use the oneshot helper:
~/.local/lain/lain oneshot get_health --workspace /home/sebastian/orca/monitor_dm_system
```

The legacy `scripts/lain-mcp-proxy.sh` and `scripts/lain-server-manager.sh`
pattern is no longer used; you can `git rm` them if you want a clean tree.

## File Locations Quick Reference

| To modify... | Edit files in... | Layer |
|--------------|------------------|-------|
| Neo4j client | \`packages/data-layer/src/monitor_data/db/neo4j.py\` | 1 |
| MongoDB client | \`packages/data-layer/src/monitor_data/db/mongodb.py\` | 1 |
| Neo4j MCP tools | \`packages/data-layer/src/monitor_data/tools/neo4j_tools/\` | 1 |
| ContextAssembly agent | \`packages/agents/src/monitor_agents/context_assembly.py\` | 2 |
| Narrator agent | \`packages/agents/src/monitor_agents/narrator.py\` | 2 |
| CanonKeeper agent | \`packages/agents/src/monitor_agents/canonkeeper.py\` | 2 |
| Scene loop | \`packages/agents/src/monitor_agents/loops/scene_loop.py\` | 2 |
| Play command | \`packages/cli/src/monitor_cli/commands/play.py\` | 3 |
| Image provider adapters | \`packages/data-layer/src/monitor_data/llm/image_providers.py\` | 1 |
| Image generation endpoints | \`packages/ui/backend/src/monitor_ui/routers/image_gen.py\` | UI |
| Configuration page (\`/config\`) | \`packages/ui/frontend/src/app/config/page.tsx\` | UI |

