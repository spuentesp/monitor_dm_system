# MONITOR — Claude Code Instructions

> **Primary config**: See `AGENTS.md` for architecture, layer rules, and conventions.
> This file contains Claude Code-specific instructions only.

## Quick Start (Read Order)

1. `docs/_index.md` — Documentation map (START HERE)
2. `AGENTS.md` — Agent instructions (layer rules, commands, conventions)
3. `docs/2_architecture/the_three_layers.md` — Layer architecture and rules
4. `STRUCTURE.md` — Folder structure definitions
5. `docs/USE_CASES.md` — All use cases (DL-, P-, M-, etc.)

## Key Constraints (From AGENTS.md)

- **Three layers**: data-layer → agents → cli (dependencies flow downward ONLY)
- **CanonKeeper writes Neo4j**: All other agents use `ProposedChange` in MongoDB
- **Use case IDs mandatory**: Reference `DL-20`, `P-6`, `ST-2` etc. in commits/PRs
- **Tests required**: Every code change needs tests (unit + integration/e2e)
- **Evidence for canon facts**: Every canonical fact MUST have `evidence_refs`
- **Async MCP calls**: All agent methods calling MCP tools must be `async`
- **Logging**: Use `structlog`, never `print()`

## Forbidden Patterns (From AGENTS.md)

```python
# ❌ FORBIDDEN: CLI importing data-layer directly
from monitor_data.db import Neo4jClient  # WRONG!

# ✅ CORRECT: CLI imports agents, agents import data-layer
from monitor_agents.loops import SceneLoop  # RIGHT!
```

## Common Mistakes (From AGENTS.md)

- Importing data-layer from CLI → route through an agent instead
- Writing to Neo4j outside CanonKeeper → use `ProposedChange` in MongoDB
- Skipping `check_layer_dependencies.py` before committing → run it
- Forgetting `async` on agent methods that call MCP tools → all MCP calls are async
- Using `print()` for logging → use `structlog` (`import structlog; log = structlog.get_logger()`)

## MCP Tools (Lain)

Lain is a persistent code-intelligence MCP server configured for this workspace.
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

## Claude Code-Specific

### File Locations Quick Reference

| To modify... | Edit files in... | Layer |
|--------------|------------------|-------|
| Neo4j client | `packages/data-layer/src/monitor_data/db/neo4j.py` | 1 |
| MongoDB client | `packages/data-layer/src/monitor_data/db/mongodb.py` | 1 |
| Neo4j MCP tools | `packages/data-layer/src/monitor_data/tools/neo4j_tools/` | 1 |
| Retrieval (embeddings + RAG) | `packages/data-layer/src/monitor_data/retrieval/service.py` | 1 |
| ContextAssembly agent | `packages/agents/src/monitor_agents/context_assembly.py` | 2 |
| GM agent (authority, ReAct + tools) | `packages/agents/src/monitor_agents/gm_agent.py` | 2 |
| GM tools registry | `packages/agents/src/monitor_agents/gm_tools/registry.py` | 2 |
| Resolver (thin state machine) | `packages/agents/src/monitor_agents/resolver.py` | 2 |
| Narrator (refines GM draft) | `packages/agents/src/monitor_agents/narrator.py` | 2 |
| CanonKeeper agent | `packages/agents/src/monitor_agents/canonkeeper.py` | 2 |
| Scene loop | `packages/agents/src/monitor_agents/loops/scene_loop.py` | 2 |
| Play command | `packages/cli/src/monitor_cli/commands/play.py` | 3 |

### Full Documentation Map

| Topic | Read... |
|-------|---------|
| Documentation map | `docs/_index.md` |
| Product vision & epics | `docs/1_product/` |
| Use cases (DL-, P-, M-, …) | `docs/USE_CASES.md` |
| Architecture overview | `docs/2_architecture/` |
| **Narration / GM pipeline** | `docs/architecture/GM_AS_AUTHORITY.md` |
| Retrieval (embeddings + RAG) | `docs/architecture/RETRIEVAL_SERVICE.md` |
| De-heuristic principle | `docs/architecture/DE_HEURISTIC_PRINCIPLE.md` |
| Loops (scene, story, …) | `docs/3_loops_and_systems/` |
| Data model / ontology | `docs/4_ontology/` |
| Testing (LLM-vs-LLM + full-stack) | `docs/testing/REPLAYS.md` |

---

**Note**: `AGENTS.md` is the primary agent config. This file provides Claude Code-specific context and quick references.