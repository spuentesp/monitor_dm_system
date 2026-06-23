# MONITOR — Implementation Roadmap

> **This is the working document.** Ordered by what unblocks what.
> Details for each task are in `docs/IMPLEMENTATION_PLAN.md`.

---

## Reading This Document

Each milestone has:
- **Why now** — what it unblocks
- **Tasks** — specific files to create or change
- **Done when** — the concrete test that says you're done

You cannot start a milestone until the previous one is complete.
Exceptions are called out explicitly.

---

## Current State (Snapshot)

| Area | Status |
|------|--------|
| DB clients | Exist, all **synchronous** (blocking) |
| Embeddings | Exist, all **zero vectors** (placeholder) |
| BaseAgent LLM | Client **commented out** |
| Loops | **Not implemented** (commented stubs) |
| Prompts | **Not implemented** (commented stubs) |
| MinIO client | **Does not exist** |
| Config | Scattered `os.getenv()` — no central module |

---

## Milestone 0 — Solid Foundation
### *"The data layer works correctly and async"*

**Why first:** Every agent, every loop, every test depends on being able to read and write
databases without blocking the event loop. This is a correctness issue, not an optimization.
Nothing else is worth building on top of sync DB clients.

**Tasks:**

| # | File | Change |
|---|------|--------|
| 0.1 | `data-layer/pyproject.toml` | Add `pydantic-settings>=2.2`, replace `pymongo` → `motor>=3.3`, replace `minio` → `aiobotocore>=2.7`, add `tenacity>=8.2` |
| 0.2 | `monitor_data/config.py` | **Create.** `pydantic-settings` `Settings` class — single source for all env vars |
| 0.3 | `monitor_data/db/mongodb.py` | Rewrite: `MongoClient` → `AsyncIOMotorClient`, all methods `async` |
| 0.4 | `monitor_data/db/neo4j.py` | Rewrite: `GraphDatabase` → `AsyncGraphDatabase`, `threading.Lock` → `asyncio.Lock` |
| 0.5 | `monitor_data/db/qdrant.py` | Rewrite: `QdrantClient` → `AsyncQdrantClient`, `threading.Lock` → `asyncio.Lock` |
| 0.6 | `monitor_data/db/minio.py` | **Create.** Async `aiobotocore` wrapper (file does not exist yet) |
| 0.7 | `monitor_data/db/*.py` | Add `@retry(tenacity)` on all `execute_read`, `execute_write`, collection ops |
| 0.8 | `monitor_data/tools/**/*.py` | Add `await` to all DB client calls (they're all sync calls right now) |
| 0.9 | `monitor_data/health.py` | Update `verify_connectivity` calls to `await` |

**Done when:**
```bash
cd packages/data-layer && pytest tests/test_db/ -v
# All DB client tests pass against real containers (testcontainers)
```
And the MCP server starts without errors: `monitor-data`

---

## Milestone 1 — Agents Can Think
### *"BaseAgent can make LLM calls and return typed results"*

**Why now:** The Anthropic client is commented out in `base.py`. No agent can do anything
intelligent until this is wired. `instructor` goes here too — once the client is active,
all structured outputs (CanonVerdict, ResolverOutcome) need enforcement from day one.

**Tasks:**

| # | File | Change |
|---|------|--------|
| 1.1 | `agents/pyproject.toml` | Add `instructor>=1.0`, `tenacity>=8.2`, `anyio>=4.0` |
| 1.2 | `monitor_agents/base.py` | Uncomment + implement: `Anthropic` client wrapped with `instructor`, `call_structured()` method with `@retry` |
| 1.3 | `monitor_data/schemas/canon_verdict.py` | **Create.** `CanonVerdict(proposal_id, accepted, reasoning, confidence, rejection_reason)` |
| 1.4 | `monitor_data/schemas/resolver_outcome.py` | **Create.** `ResolverOutcome(success, roll, modifier, details, effects, proposals)` |
| 1.5 | `monitor_data/schemas/narrator_response.py` | **Create.** `NarratorResponse(text, implied_state_changes)` |
| 1.6 | `monitor_agents/resolver.py` | Replace `json.loads()` chain for outcome generation with `call_structured(ResolverOutcome, ...)` |

**Done when:**
```python
# Quick smoke test
agent = BaseAgent("test", "t1")
result = await agent.call_structured(CanonVerdict, [...messages...])
assert isinstance(result, CanonVerdict)
```

---

## Milestone 2 — Semantic Memory Works
### *"Qdrant returns meaningful search results"*

**Why now:** The `embed_text()` method returns `[0.0] * 1536`. Every semantic search
in the game (recall similar scenes, find relevant memories, retrieve lore snippets)
is completely broken. This must be fixed before any context assembly or ingestion work.

Can be done **in parallel with Milestone 1** — no dependency between them.

**Tasks:**

| # | File | Change |
|---|------|--------|
| 2.1 | `data-layer/pyproject.toml` | Add `openai>=1.0` |
| 2.2 | `monitor_data/db/qdrant.py` | Replace placeholder `embed_text()` with real `AsyncOpenAI` call to `text-embedding-3-small` |
| 2.3 | `monitor_data/config.py` | Ensure `openai_api_key` and `embedding_model` are in `Settings` (from M0.2) |

**Done when:**
```python
qdrant = get_qdrant_client()
vec = await qdrant.embed_text("The orc chieftain raises his axe")
assert len(vec) == 1536
assert vec[0] != 0.0  # real embedding, not placeholder
```

---

## Milestone 3 — DSPy Prompt Modules
### *"Agents have declared, typed interfaces"*

**Why now:** The `prompts/` directory is entirely commented-out stubs. Before implementing
any agent beyond `Resolver`, the prompt layer needs to exist. DSPy Signatures replace
the manual string templates with typed, inspectable, eventually-optimizable interfaces.
LangGraph nodes (Milestone 4) call DSPy modules — so prompts come before loops.

**Requires:** Milestone 1 complete (working LLM client).

**Tasks:**

| # | File | Change |
|---|------|--------|
| 3.1 | `agents/pyproject.toml` | Add `dspy-ai>=2.5` |
| 3.2 | `monitor_agents/dspy_config.py` | **Create.** `configure_dspy()` — sets global `dspy.LM` from `settings` |
| 3.3 | `monitor_agents/prompts/narrator.py` | **Create.** `NarrateScene` Signature + `NarratorModule(dspy.Module)` |
| 3.4 | `monitor_agents/prompts/canonkeeper.py` | **Create.** `EvaluateProposal` Signature + `CanonKeeperModule(dspy.Module)` |
| 3.5 | `monitor_agents/prompts/context_assembly.py` | **Create.** `SummarizeContext` Signature + `ContextSummaryModule(dspy.Module)` |
| 3.6 | `monitor_agents/narrator.py` | **Create.** `Narrator(BaseAgent)` — uses `NarratorModule`, writes turn to MongoDB |
| 3.7 | `monitor_agents/canonkeeper.py` | **Create.** `CanonKeeper(BaseAgent)` — uses `CanonKeeperModule` + `instructor` for final `CanonVerdict` |
| 3.8 | `monitor_agents/context_assembly.py` | **Create.** `ContextAssembly(BaseAgent)` — queries Neo4j + MongoDB + Qdrant, uses `ContextSummaryModule` |

**Done when:**
```python
configure_dspy()
narrator = Narrator()
result = await narrator.generate(context_package, user_action="I attack the orc", resolution="success, 14 damage")
assert len(result.text) > 100
```

---

## Milestone 4 — Scene Loop Runs
### *"A complete scene executes start to finish"*

**Why now:** The Scene Loop is the core unit of play — everything else (Story Loop, Main Loop)
is scaffolding around it. Getting one scene working end-to-end is the first moment the system
is actually playable. Build this loop before the others.

LangGraph makes the state machine explicit and gives you MongoDB checkpointing for free.

**Requires:** Milestones 0, 1, 2, 3 complete.

**Tasks:**

| # | File | Change |
|---|------|--------|
| 4.1 | `agents/pyproject.toml` | Add `langgraph>=0.2`, `langgraph-checkpoint-mongodb>=0.1` |
| 4.2 | `monitor_agents/loops/scene_loop.py` | **Create.** `SceneState` TypedDict + `build_scene_graph()` returning compiled `StateGraph` |
| 4.3 | `monitor_agents/loops/scene_loop.py` | Implement nodes: `load_context_node`, `resolve_node`, `check_critical_node`, `narrate_node`, `mid_commit_node`, `finalize_node` |
| 4.4 | `monitor_agents/loops/scene_loop.py` | Implement edges: `should_continue()`, `should_mid_commit()` routing functions |
| 4.5 | `monitor_agents/loops/__init__.py` | Uncomment `SceneLoop`, export `build_scene_graph`, `get_checkpointer` |

**Graph shape:**
```
load_context → await_input → resolve → check_critical
                   ↑                         ↓              ↓
                   └── narrate ←── mid_commit   narrate
                         ↓
                   [continue or finalize] → END
```

**Done when:**
```bash
# Start infra
cd infra && docker compose up -d

# Run scene integration test
cd packages/agents && pytest tests/test_scene_loop.py -v
# Scene with 3 turns completes, CanonKeeper writes Facts to Neo4j
```

---

## Milestone 5 — Full Game Loop
### *"monitor play works"*

**Why now:** Once the Scene Loop works, wiring the remaining loops is straightforward.
Story Loop manages scene sequences. Main Loop routes to modes. Turn Loop is a thin
wrapper already handled inside the Scene Loop.

**Requires:** Milestone 4 complete.

**Tasks:**

| # | File | Change |
|---|------|--------|
| 5.1 | `monitor_agents/loops/turn_loop.py` | **Create.** `TurnState` + thin graph (resolve → narrate → persist). Mostly delegates to Scene Loop nodes. |
| 5.2 | `monitor_agents/loops/story_loop.py` | **Create.** `StoryState` + graph: manages scene creation, scene sequencing, story completion |
| 5.3 | `monitor_agents/loops/main_loop.py` | **Create.** `MainState` + router graph: dispatches to `story_loop`, `ingest`, `query`, `manage` sub-graphs |
| 5.4 | `monitor_agents/loops/__init__.py` | Uncomment all, export `build_main_graph()` |
| 5.5 | `monitor_agents/orchestrator.py` | **Create.** `Orchestrator(BaseAgent)` — entry point, compiles and runs `main_loop` graph |
| 5.6 | `cli/src/monitor_cli/commands/play.py` | Wire `monitor play` → `Orchestrator.run()` |

**Done when:**
```bash
monitor play
# Interactive REPL starts, user can start a story, play a scene, see Neo4j updated
```

---

## Milestone 6 — Knowledge Ingestion
### *"monitor ingest processes documents"*

**Why now:** EPIC 2 (Knowledge Ingestion) unlocks the full value proposition — being able
to ingest rulebooks, session notes, and lore PDFs. Can be developed in parallel with
Milestone 5 once Milestone 2 (real embeddings) is complete.

**Requires:** Milestone 2 complete (real embeddings). Milestones 3-5 not required.

**Tasks:**

| # | File | Change |
|---|------|--------|
| 6.1 | `data-layer/pyproject.toml` | Add `pymupdf>=1.24`, `tiktoken>=0.7` |
| 6.2 | `monitor_data/tools/ingest_tools.py` | **Create.** `extract_text_from_pdf()`, `chunk_text()`, `ingest_document()` MCP tool |
| 6.3 | `monitor_data/server.py` | Register ingest tools |
| 6.4 | `monitor_agents/indexer.py` | **Create.** `Indexer(BaseAgent)` — background agent, subscribes to document events, embeds and upserts to Qdrant |
| 6.5 | `cli/src/monitor_cli/commands/ingest.py` | Wire `monitor ingest <file>` → `ingest_document` MCP tool |

**Done when:**
```bash
monitor ingest path/to/rulebook.pdf --universe my-world
# Outputs: "Indexed 847 chunks into Qdrant collection 'snippets'"
# ContextAssembly can now recall rule excerpts during scenes
```

---

## Ongoing — Observability and Testing
### *"Do these alongside every milestone, not at the end"*

These are not a separate phase. Each milestone should ship with tests.

**Testing (start at Milestone 0):**

| # | File | When |
|---|------|------|
| T.1 | `data-layer/tests/conftest.py` | M0: Add `testcontainers` fixtures for Neo4j + MongoDB + Qdrant |
| T.2 | `data-layer/tests/test_db/` | M0: Integration tests for each async DB client |
| T.3 | `agents/tests/conftest.py` | M1: `pytest-mock` fixtures, mock `call_tool` for agent unit tests |
| T.4 | `agents/tests/test_resolver.py` | M1: Unit tests for `Resolver.resolve_check()` |
| T.5 | `agents/tests/test_scene_loop.py` | M4: Integration test for full scene execution |

**Observability (start at Milestone 1):**

| # | File | When |
|---|------|------|
| O.1 | `agents/pyproject.toml` | M1: Add `logfire[anthropic]>=0.30` |
| O.2 | `monitor_agents/telemetry.py` | M1: `configure_telemetry()` — `logfire.configure()` + `instrument_anthropic()` |
| O.3 | `monitor_agents/base.py` | M1: Add `logfire.span()` around `call_structured()` and `call_tool()` |
| O.4 | `monitor_agents/loops/scene_loop.py` | M4: Add `logfire.span()` around each LangGraph node |

---

## Summary View

```
NOW ──────────────────────────────────────────────────────► LATER

M0              M1              M2
Async DBs  →   LLM calls   ┐   Real          M3
+ Config        + instructor│   embeddings →  DSPy modules →  M4: Scene Loop
+ tenacity       + schemas  │   (parallel     Narrator            + LangGraph
                            │    to M1)       CanonKeeper     M5: Full Loop
                            │                 Context ─────►  M6: Ingest
                            │
                            └── T.1-T.3 tests + O.1-O.3 observability (always alongside)
```

**Recommended working order for a single session:**
1. Finish M0 entirely (async DBs — these are rote but critical)
2. M1 + M2 in parallel (LLM client and real embeddings are independent)
3. M3 (DSPy) only after M1
4. M4 (LangGraph Scene Loop) only after M3
5. M5 + M6 in parallel after M4

---

## Reference

| Topic | Document |
|-------|---------|
| File-by-file implementation details | `docs/IMPLEMENTATION_PLAN.md` |
| Library rationale and verdicts | `docs/archive/LIBRARY_PLAN.md` |
| Architecture layer rules | `ARCHITECTURE.md` |
| Agent roles and authority | `docs/architecture/AGENT_ORCHESTRATION.md` |
| Loop state machines | `docs/architecture/CONVERSATIONAL_LOOPS.md` |
