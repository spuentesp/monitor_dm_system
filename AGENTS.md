# MONITOR — Agent Instructions

> Narrative AI system for tabletop RPGs. Three-layer Python monorepo.

## Architecture (read first)

| Layer | Package | Imports | Role |
|-------|---------|---------|------|
| 3 CLI | `monitor-cli` | agents only | Commands, REPL, terminal UI |
| 2 Agents | `monitor-agents` | data-layer only | LLM calls, loops, AI logic |
| 1 Data-layer | `monitor-data-layer` | external libs only | DB clients, MCP tools, schemas |

**Dependencies flow downward. Never import upward or skip layers.**

See [ARCHITECTURE.md](ARCHITECTURE.md) for full rules and diagrams.

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

All agents inherit `BaseAgent` ([base.py](packages/agents/src/monitor_agents/base.py)). They call data-layer via MCP tools, never directly. DSPy modules live in `prompts/`. Loops are LangGraph graphs in `loops/`.

### MCP Tools (Layer 1)

Tools live in `packages/data-layer/src/monitor_data/tools/`. Auto-registered by `server.py`. Each tool group has its own module (`neo4j_tools/`, `mongodb_tools/`, `qdrant_tools.py`, `ingest_tools/`). Write tools require authority checks in `middleware/auth.py`.

### Schemas (Layer 1)

Pydantic v2 models in `packages/data-layer/src/monitor_data/schemas/`. Base enums in `base.py`. Entity types: Archetype vs Instance. Facts have CanonLevel.

### UI Backend

FastAPI app at `packages/ui/backend/src/monitor_ui/`. Routers in `routers/`. The chat router drives `SceneLoop` via WebSocket.

## Documentation Map

| Topic | Source |
|-------|--------|
| Product vision & epics | [SYSTEM.md](SYSTEM.md) |
| Folder structure | [STRUCTURE.md](STRUCTURE.md) |
| Layer rules & diagrams | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Use-case catalog | [docs/USE_CASES.md](docs/USE_CASES.md) |
| Quick implementation ref | [docs/AI_DOCS.md](docs/AI_DOCS.md) |
| MCP transport | [docs/architecture/MCP_TRANSPORT.md](docs/architecture/MCP_TRANSPORT.md) |
| Agent orchestration | [docs/architecture/AGENT_ORCHESTRATION.md](docs/architecture/AGENT_ORCHESTRATION.md) |
| Data model | [docs/ontology/ONTOLOGY.md](docs/ontology/ONTOLOGY.md) |
| Contributing workflow | [CONTRIBUTING.md](CONTRIBUTING.md) |
| DB integration | [docs/architecture/DATABASE_INTEGRATION.md](docs/architecture/DATABASE_INTEGRATION.md) |

## Common Mistakes

- Importing data-layer from CLI → route through an agent instead
- Writing to Neo4j outside CanonKeeper → use `ProposedChange` in MongoDB
- Skipping `check_layer_dependencies.py` before committing → run it
- Forgetting `async` on agent methods that call MCP tools → all MCP calls are async
- Using `print()` for logging → use `structlog` (`import structlog; log = structlog.get_logger()`)

## MCP Tools (Lain)

Lain is configured as an MCP server in `.vscode/settings.json` via a proxy script:
```json
{
  "mcp": {
    "servers": {
      "lain": {
        "type": "stdio",
        "command": "scripts/lain-mcp-proxy.sh",
        "env": {
          "LAIN_PORT": "9999"
        }
      }
    }
  }
}
```

The proxy wraps the Lain binary and exposes it as an MCP server. The proxy
starts the underlying Lain HTTP server (if not already running) and bridges
stdio MCP traffic to HTTP. This allows the Lain process to be shared between
the MCP transport and curl-based health checks.

Lain binary: `~/.local/lain/lain` (v0.1.5 with MCP protocol 2025-11-25)
ONNX model: `<workspace>/.lain/models/model.onnx`

Use Lain for:
- Blast radius analysis (`get_blast_radius`)
- Dependency traces (`trace_dependency`, `get_call_chain`)
- Dead code detection (`find_dead_code`)
- Semantic search (`semantic_search`)
- Architectural exploration (`explore_architecture`, `find_anchors`)
- Build/test integration (`run_build`, `run_tests`, `run_clippy`)

Health check:
```bash
curl -s -X POST http://localhost:9999/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_health","arguments":{}},"id":1}'
```

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

