## Agent Communication Patterns

### 1. Request-Response (Synchronous)

**Used by:** LangGraph loop nodes calling agents

```
SceneLoop.load_context → ContextAssembly: "Load context for scene X"
                        ← ContextAssembly: context_package

SceneLoop.narrate → Narrator: "Generate response for turn Y"
                   ← Narrator: narrative_text + proposals
```

### 2. Event Publishing (Asynchronous)

**Used by:** Background updates (Indexer)

```
Event: Turn created
  ↓
Indexer (subscribes) → embed turn → update Qdrant
```

### 3. Shared State (Data-Mediated)

**Used by:** All agents reading/writing databases

```
Narrator writes: MongoDB.turns.append(turn)
              ↓
SceneLoop reads: MongoDB.turns (to check scene state)
```

**Critical:** Shared state via databases, not hidden agent calls.

---

## Loop Ownership

| Loop | Implementation | Agents Called |
|------|---------------|---------------|
| SceneLoop | `loops/scene_loop.py` (LangGraph StateGraph) | ContextAssembly, Resolver, Narrator, CanonKeeper |
| StoryLoop | `loops/story_loop.py` (LangGraph StateGraph + scene-completion helpers) | CanonKeeper (finalize), SimulacrumAgent (world ticks) |
| ConversationLoop | `loops/conversation_loop.py` (LangGraph StateGraph) | NPCVoice |
| WorldBuildingLoop | `loops/world_building_loop.py` (LangGraph StateGraph) | WorldArchitect, CanonKeeper (auto-accept) |
| Ingestion | `ingestion_pipeline.py` (sequential) | Indexer, Analyzer |
| Canonization | CanonKeeper (exclusive authority) | — |

**Key insights:**
- **LangGraph StateGraph** replaces the monolithic Orchestrator
- Each loop is a compiled graph with typed `Pydantic` state
- **MongoDBSaver** provides checkpointing for SceneLoop and StoryLoop
- All agents are stateless workers — loop state lives in the graph checkpoint

---

## Coordination Example: Full Scene Execution

```
USER: "I attack the orc"
  ↓
[SceneLoop: load_context node]
  ↓
ContextAssembly.retrieve_turn_context(scene_id, user_input)
  ← context_package (entities, facts, memories, prior turns)
  ↓
MongoDB: Turn.append(scene_id, user_input)
  ↓
[SceneLoop: resolve node]
  ↓
Resolver.resolve_action(user_input, context)
  ← resolution (success, roll=18, orc takes 8 damage)
  ← proposals ([state_change: orc.hp -= 8])
  ↓
MongoDB: ProposedChange.save_batch(proposals)
  ↓
[SceneLoop: narrate node]
  ↓
Narrator.narrate_turn(context, user_input, resolution)
  ← "Your blade strikes true! The orc staggers, wounded."
  ↓
MongoDB: Turn.append(scene_id, gm_response)
  ↓
Event: Turn created → Indexer (background)
  ↓
[SceneLoop: routing — scene_complete?]
  ↓
scene_complete? → No → END (await next invoke)

---

USER: "I finish him"
  ↓
[... same flow ...]
  ↓
Resolver → success, orc dies
         → proposals ([state_change: orc.alive = false])
  ↓
[SceneLoop: narrate node — death detected]
  ↓
Narrator.narrate_turn(context, user_input, resolution)
  ← "The orc crumples to the ground. Silence."
  ↓
MongoDB: ProposedChange.save_batch([orc death proposal])
  ↓
[SceneLoop: routing — scene_complete? → Yes (combat done)]
  ↓
[SceneLoop: canonize node]
  ↓
CanonKeeper.finalize_scene(scene_id)
  ↓
CanonKeeper: evaluate all pending proposals
           → accept [orc died, PC took 3 damage, searched room]
           → write to Neo4j
  ↓
Neo4j: Fact(orc died, time_ref, participants)
       Edge: Fact -[:SUPPORTED_BY]→ Turn
  ↓
MongoDB: Proposal.status = "accepted"
         Scene.status = "completed"
  ↓
END SCENE
```

---

## Agent Scaling & Deployment

### Single-Machine Mode

All agents run as **threads/coroutines** in one process:
- LangGraph loops = compiled state graphs
- Agents = async functions called by loop nodes
- Coordination = function calls + shared DB connections

### Distributed Mode

Agents run as **separate services**:
- Loop controllers = coordinator services
- Agents = microservices (REST or gRPC)
- Coordination = message queue (RabbitMQ, Redis) + shared DBs

**Critical:** Data model stays the same. Only deployment changes.

---

## Agent Failure Handling

| Agent | Failure Impact | Recovery |
|-------|---------------|----------|
| ContextAssembly | No context loaded | Retry or use cached context |
| Narrator | No GM response | Retry with same context |
| Resolver | No outcome | Retry or fallback (narrative mode) |
| CanonKeeper | **Canon not written** | Proposals remain pending, retry on restart |
| Indexer | Indices stale | Non-critical, retry background |
| Analyzer | Knowledge not extracted | Non-critical, re-run analysis |
| IngestionPipeline | Ingest incomplete | IngestionJob tracks stage; resume from last checkpoint |
| WorldArchitect | World element not committed | Retry on next user turn |
| NPCVoice | NPC doesn't respond | Retry with same context |
| LangGraph loop | Loop stops | MongoDBSaver checkpoint; restart from last state |

**Most critical:** CanonKeeper failure. All other agents can retry safely.

---

## Security & Authority Enforcement

### Write Authority Matrix

| Agent | Neo4j | MongoDB | Qdrant | MinIO | PostgreSQL |
|-------|-------|---------|--------|-------|------------|
| ContextAssembly | ❌ | ❌ | ❌ | ❌ | ❌ |
| Narrator | ❌ | ✅ (turns) | ❌ | ❌ | ❌ |
| Resolver | ❌ | ✅ (resolutions, proposals) | ❌ | ❌ | ❌ |
| **CanonKeeper** | **✅** | ✅ (proposal status, verdicts) | ❌ | ❌ | ❌ |
| Indexer | ❌ | ❌ | **✅** (snippets, memories) | ❌ | ❌ |
| Analyzer | ❌ | ✅ (knowledge packs, jobs) | ❌ (read-only) | ❌ | ❌ |
| IngestionPipeline | ✅ (Source node only) | ✅ (documents, jobs) | ❌ | ✅ (upload) | ❌ |
| WorldArchitect | via CanonKeeper | ❌ | ❌ | ❌ | ❌ |
| NPCVoice | ❌ | ✅ (conversations) | ❌ | ❌ | ❌ |
| GameSystemRuntime | ❌ | ❌ | ❌ | ❌ | ❌ |

**Enforcement:** `AUTHORITY_MATRIX` in `packages/data-layer/src/monitor_data/middleware/auth.py` (225+ tool→agent mappings). Every MCP tool call is gated by `check_authority(tool_name, agent_type)`.

---

## Implementation Status

The orchestration architecture described in this document is implemented:

1. **Agent Interfaces** — All 9 agents + GameSystemRuntime implemented with typed Pydantic schemas
2. **LangGraph Loops** — 4 loop state machines replace the planned Orchestrator; SceneLoop and StoryLoop checkpointed via MongoDBSaver
3. **CanonKeeper Policy Engine** — DSPy reasoning + PolicyCheck modules, authority matrix enforcement in middleware
4. **Communication** — Synchronous function calls within loops; shared DB state between agents
5. **Testing** — Agent unit tests, loop state tests, canonization gate tests (see `packages/agents/tests/`)

---

## References

- [CONVERSATIONAL_LOOPS.md](CONVERSATIONAL_LOOPS.md) - Loop state machines
- [DATABASE_INTEGRATION.md](DATABASE_INTEGRATION.md) - Data layer and canonization
- [ONTOLOGY.md](../ontology/ONTOLOGY.md) - Canonical data model
