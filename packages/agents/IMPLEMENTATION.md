# Agents Layer Implementation

> Machine-optimized task list for implementing Layer 2.

---

## Prerequisites

```
REQUIRES: Layer 1 (data-layer) complete
READS: docs/architecture/AGENT_ORCHESTRATION.md, docs/architecture/CONVERSATIONAL_LOOPS.md
OUTPUTS: 7 agents + 4 loop controllers
```

---

## Phase 1: Project Setup

### T1.1: Initialize Package

```bash
cd packages/agents
uv init --name monitor-agents
```

**Files to create:**
```
src/monitor_agents/
├── __init__.py
├── base.py
├── orchestrator.py
├── context_assembly.py
├── narrator.py
├── resolver.py
├── canonkeeper.py
├── memory_manager.py
├── indexer.py
├── loops/
│   ├── __init__.py
│   ├── main_loop.py
│   ├── story_loop.py
│   ├── scene_loop.py
│   └── turn_loop.py
├── prompts/
│   ├── __init__.py
│   ├── narrator.py
│   ├── resolver.py
│   └── canonkeeper.py
└── utils/
    ├── __init__.py
    ├── context.py
    └── parsing.py
```

### T1.2: Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "monitor-data-layer",  # Layer 1
    "anthropic>=0.39",
    "structlog>=23.2",
    "tenacity>=8.2",
]
```

---

## Phase 2: Base Agent

### T2.1: BaseAgent Class

**File:** `src/monitor_agents/base.py`

```python
class BaseAgent:
    agent_type: str          # "Orchestrator", "Narrator", etc.
    agent_id: str            # Unique instance ID
    authority: list[str]     # Allowed tool categories

    async def call_tool(self, tool_name: str, params: dict) -> dict:
        """Call MCP tool with authority check."""

    async def call_llm(self, messages: list, **kwargs) -> str:
        """Call LLM with agent context."""

    def log(self, event: str, **kwargs):
        """Structured logging."""
```

**Methods:**

| Method | Description |
|--------|-------------|
| `__init__(agent_id, mcp_client, llm_client)` | Initialize agent |
| `call_tool(name, params)` | Call MCP tool |
| `call_llm(messages, system, temperature)` | Call Anthropic API |
| `get_context()` | Get agent context for MCP |

---

## Phase 3: Orchestrator Agent

### T3.1: Orchestrator Class

**File:** `src/monitor_agents/orchestrator.py`

**Authority:** MongoDB (loop state), Neo4j (CreateStory only)

**Use Cases:** SYS-1, SYS-2, P-1, P-12, P-2, P-3, P-8

```python
class Orchestrator(BaseAgent):
    agent_type = "Orchestrator"
    authority = ["mongodb_scene", "mongodb_story_outline", "neo4j_create_story"]
```

**Methods:**

| Method | Use Case | Description |
|--------|----------|-------------|
| `run_main_loop()` | SYS-2 | Main menu dispatcher |
| `start_new_story(universe_id, params)` | P-1 | Create story + first scene |
| `continue_story(story_id)` | P-12 | Resume existing story |
| `run_story_loop(story_id)` | - | Story-level loop |
| `run_scene_loop(scene_id)` | P-2, P-3 | Scene-level loop |
| `run_turn_loop(scene_id)` | P-3 | Turn-level loop |
| `end_scene(scene_id)` | P-8 | Trigger canonization |
| `handle_meta_command(cmd)` | P-7 | Process /commands |

### T3.2: State Machine

**States:**
```
MAIN_MENU → STORY_ACTIVE → SCENE_ACTIVE → TURN_WAITING
                                       ↓
                                  CANONIZING → SCENE_END
```

**Transitions:**

| From | Event | To | Action |
|------|-------|----|----|
| MAIN_MENU | start_story | STORY_ACTIVE | Create story |
| MAIN_MENU | continue_story | SCENE_ACTIVE | Load scene |
| STORY_ACTIVE | start_scene | SCENE_ACTIVE | Create scene |
| SCENE_ACTIVE | user_input | TURN_WAITING | Process turn |
| TURN_WAITING | turn_complete | SCENE_ACTIVE | Continue scene |
| SCENE_ACTIVE | end_scene | CANONIZING | Start canonization |
| CANONIZING | canon_complete | SCENE_END | Scene closed |
| SCENE_END | new_scene | SCENE_ACTIVE | Create new scene |
| SCENE_END | end_story | MAIN_MENU | Return to menu |

---

## Phase 4: ContextAssembly Agent

### T4.1: ContextAssembly Class

**File:** `src/monitor_agents/context_assembly.py`

**Authority:** READ-ONLY (all databases)

**Use Cases:** P-3, Q-1, Q-2

```python
class ContextAssembly(BaseAgent):
    agent_type = "ContextAssembly"
    authority = []  # Read-only, no writes
```

**Methods:**

| Method | Use Case | Description |
|--------|----------|-------------|
| `get_scene_context(scene_id)` | P-3 | Full scene context |
| `get_entity_context(entity_id)` | M-16, Q-2 | Entity + facts + relations |
| `semantic_search(query, universe_id)` | Q-1 | Qdrant search |
| `get_relevant_facts(entity_ids, time_range)` | P-3, Q-4 | Facts for entities |
| `get_character_memories(entity_id, query)` | P-5, P-11 | Character memories |
| `get_location_details(location_id)` | P-2 | Location info |

### T4.2: Context Building

**Scene Context Structure:**

```python
@dataclass
class SceneContext:
    scene: Scene
    story: Story
    universe: Universe
    location: EntityInstance | None
    participants: list[EntityInstance]
    recent_turns: list[Turn]        # Last N turns
    relevant_facts: list[Fact]      # Facts about participants
    active_threads: list[PlotThread]
    pending_proposals: list[ProposedChange]
```

---

## Phase 5: Narrator Agent

### T5.1: Narrator Class

**File:** `src/monitor_agents/narrator.py`

**Authority:** MongoDB (turns only)

**Use Cases:** P-3, P-4, P-5, P-11

```python
class Narrator(BaseAgent):
    agent_type = "Narrator"
    authority = ["mongodb_append_turn"]
```

**Methods:**

| Method | Use Case | Description |
|--------|----------|-------------|
| `generate_scene_opening(context)` | P-2 | Opening narration |
| `handle_user_input(input, context)` | P-3 | Process user turn |
| `generate_response(context, resolution)` | P-3 | GM response |
| `generate_npc_dialogue(npc, context, player_said)` | P-5, P-11 | NPC speech |
| `generate_scene_closing(context)` | P-8 | Closing narration |
| `describe_action_result(action, resolution)` | P-4 | Action outcome |

### T5.2: Prompts

**File:** `src/monitor_agents/prompts/narrator.py`

| Prompt | Purpose |
|--------|---------|
| `SYSTEM_PROMPT` | Base narrator personality |
| `SCENE_OPENING` | Generate scene start |
| `USER_INPUT_PARSE` | Parse user intent |
| `RESPONSE_GENERATION` | Generate narrative |
| `NPC_DIALOGUE` | NPC in-character |
| `SCENE_CLOSING` | Scene ending |

---

## Phase 6: Resolver Agent

### T6.1: Resolver Class

**File:** `src/monitor_agents/resolver.py`

**Authority:** MongoDB (resolutions, proposals)

**Use Cases:** P-4, P-9, P-10

```python
class Resolver(BaseAgent):
    agent_type = "Resolver"
    authority = ["mongodb_create_resolution", "mongodb_create_proposal"]
```

**Methods:**

| Method | Use Case | Description |
|--------|----------|-------------|
| `resolve_action(action, context)` | P-4 | Determine outcome |
| `roll_dice(formula)` | P-9 | Dice mechanics |
| `evaluate_difficulty(action, context)` | P-4 | DC calculation |
| `determine_effects(action, result)` | P-4 | State changes |
| `create_proposals(effects, context)` | P-4 | Propose changes |
| `resolve_combat_action(action, context)` | P-10 | Combat resolution |

### T6.2: Resolution Types

```python
class ResolutionType(Enum):
    DICE = "dice"           # Roll required
    NARRATIVE = "narrative" # GM decision
    DETERMINISTIC = "deterministic"  # Auto-success/fail
```

### T6.3: Prompts

**File:** `src/monitor_agents/prompts/resolver.py`

| Prompt | Purpose |
|--------|---------|
| `DETERMINE_RESOLUTION_TYPE` | Dice vs narrative |
| `CALCULATE_DIFFICULTY` | DC for action |
| `EVALUATE_OUTCOME` | Success level |
| `DETERMINE_EFFECTS` | State changes |

---

## Phase 7: CanonKeeper Agent

### T7.1: CanonKeeper Class

**File:** `src/monitor_agents/canonkeeper.py`

**Authority:** Neo4j (ALL WRITES), MongoDB (proposal status)

**Use Cases:** P-8, I-4

```python
class CanonKeeper(BaseAgent):
    agent_type = "CanonKeeper"
    authority = ["neo4j_*", "mongodb_update_proposal"]
```

**Methods:**

| Method | Use Case | Description |
|--------|----------|-------------|
| `canonize_scene(scene_id)` | P-8 | Process scene proposals |
| `evaluate_proposal(proposal)` | P-8, I-4 | Accept/reject logic |
| `check_contradictions(proposal, existing_facts)` | P-8 | Consistency check |
| `write_fact(proposal)` | P-8, M-26 | Create Neo4j fact |
| `write_event(proposal)` | P-8 | Create Neo4j event |
| `write_entity(proposal)` | I-4 | Create Neo4j entity |
| `link_evidence(canonical_id, evidence)` | P-8 | SUPPORTED_BY edges |
| `review_ingestion_proposals(source_id)` | I-4 | Batch review |

### T7.2: Evaluation Criteria

```python
@dataclass
class EvaluationResult:
    accept: bool
    confidence: float
    rationale: str
    contradictions: list[Fact]
```

**Criteria:**

| Factor | Weight | Description |
|--------|--------|-------------|
| Authority | 0.3 | Source authority level |
| Evidence | 0.3 | Evidence quality |
| Consistency | 0.3 | No contradictions |
| Confidence | 0.1 | Proposal confidence |

### T7.3: Prompts

**File:** `src/monitor_agents/prompts/canonkeeper.py`

| Prompt | Purpose |
|--------|---------|
| `EVALUATE_PROPOSAL` | Accept/reject decision |
| `CHECK_CONTRADICTION` | Find conflicts |
| `GENERATE_RATIONALE` | Explain decision |

---

## Phase 8: MemoryManager Agent

### T8.1: MemoryManager Class

**File:** `src/monitor_agents/memory_manager.py`

**Authority:** MongoDB (memories), Qdrant (memory embeddings)

**Use Cases:** P-5, P-11, M-22

```python
class MemoryManager(BaseAgent):
    agent_type = "MemoryManager"
    authority = ["mongodb_*_memory", "qdrant_embed_memory"]
```

**Methods:**

| Method | Use Case | Description |
|--------|----------|-------------|
| `create_memory(entity_id, text, scene_id, fact_id)` | P-5 | Store memory |
| `recall_memories(entity_id, query, limit)` | P-5, P-11 | Retrieve memories |
| `update_memory_access(memory_id)` | P-11 | Update access stats |
| `get_emotional_context(entity_id)` | P-11 | Emotional state |
| `consolidate_memories(entity_id)` | - | Merge similar |

### T8.2: Memory Scoring

```python
def calculate_relevance(memory, query_embedding):
    semantic = cosine_similarity(memory.embedding, query_embedding)
    recency = decay_factor(memory.last_accessed)
    importance = memory.importance
    return 0.4 * semantic + 0.3 * importance + 0.3 * recency
```

---

## Phase 9: Indexer Agent

### T9.1: Indexer Class

**File:** `src/monitor_agents/indexer.py`

**Authority:** MongoDB (documents, snippets), Qdrant (all), MinIO (read)

**Use Cases:** I-1, I-2, I-3, P-8

```python
class Indexer(BaseAgent):
    agent_type = "Indexer"
    authority = ["mongodb_document", "mongodb_snippet", "qdrant_*", "minio_read"]
```

**Methods:**

| Method | Use Case | Description |
|--------|----------|-------------|
| `process_document(doc_id)` | I-1, I-2 | Extract + chunk + embed |
| `embed_scene_summary(scene_id, summary)` | P-8 | Scene vector |
| `extract_entities(doc_id)` | I-3 | LLM entity extraction |
| `create_snippets(doc_id, text)` | I-2 | Chunk document |
| `embed_snippets(snippet_ids)` | I-2 | Vectorize snippets |
| `reindex_universe(universe_id)` | - | Full reindex |

### T9.2: Chunking Strategy

```python
def chunk_document(text: str, chunk_size: int = 500, overlap: int = 50):
    # 1. Split by sections/paragraphs
    # 2. Chunk to max size
    # 3. Add overlap between chunks
    # 4. Return list of chunks with metadata
```

---

## Phase 10: Loop Implementations

### T10.1: Main Loop

**File:** `src/monitor_agents/loops/main_loop.py`

```python
async def main_loop(orchestrator: Orchestrator):
    while True:
        choice = await display_menu()
        match choice:
            case "play_new": await orchestrator.start_new_story()
            case "play_continue": await orchestrator.continue_story()
            case "manage": await manage_menu()
            case "ingest": await ingest_menu()
            case "query": await query_menu()
            case "settings": await settings_menu()
            case "exit": break
```

### T10.2: Story Loop

**File:** `src/monitor_agents/loops/story_loop.py`

```python
async def story_loop(orchestrator: Orchestrator, story_id: str):
    while True:
        action = await get_story_action()
        match action:
            case "new_scene":
                scene_id = await orchestrator.create_scene(story_id)
                await scene_loop(orchestrator, scene_id)
            case "end_story":
                await orchestrator.end_story(story_id)
                break
```

### T10.3: Scene Loop

**File:** `src/monitor_agents/loops/scene_loop.py`

```python
async def scene_loop(orchestrator: Orchestrator, scene_id: str):
    context = await orchestrator.context.get_scene_context(scene_id)

    # Opening narration
    opening = await orchestrator.narrator.generate_scene_opening(context)
    display(opening)

    # Turn loop
    while not context.scene_should_end:
        await turn_loop(orchestrator, scene_id, context)
        context = await orchestrator.context.get_scene_context(scene_id)

    # Canonization
    await orchestrator.end_scene(scene_id)
```

### T10.4: Turn Loop

**File:** `src/monitor_agents/loops/turn_loop.py`

```python
async def turn_loop(orchestrator: Orchestrator, scene_id: str, context: SceneContext):
    # 1. Get user input
    user_input = await get_user_input()

    # 2. Check meta commands
    if user_input.startswith("/"):
        return await orchestrator.handle_meta_command(user_input, context)

    # 3. Parse intent
    intent = await orchestrator.narrator.parse_intent(user_input, context)

    # 4. Resolve if needed
    if intent.requires_resolution:
        resolution = await orchestrator.resolver.resolve_action(intent, context)
    else:
        resolution = None

    # 5. Generate response
    response = await orchestrator.narrator.generate_response(context, resolution)

    # 6. Store turn
    await orchestrator.call_tool("mongodb_append_turn", {
        "scene_id": scene_id,
        "speaker": "user",
        "text": user_input
    })
    await orchestrator.call_tool("mongodb_append_turn", {
        "scene_id": scene_id,
        "speaker": "gm",
        "text": response
    })

    # 7. Display
    display(response)
```

---

## Phase 11: Utilities

### T11.1: Context Utilities

**File:** `src/monitor_agents/utils/context.py`

| Function | Description |
|----------|-------------|
| `build_llm_context(scene_context)` | Format for LLM |
| `summarize_recent_turns(turns, max_tokens)` | Compress history |
| `extract_entity_mentions(text)` | Find entity refs |

### T11.2: Parsing Utilities

**File:** `src/monitor_agents/utils/parsing.py`

| Function | Description |
|----------|-------------|
| `parse_dice_formula(formula)` | Parse "1d20+5" |
| `parse_user_intent(text)` | Action/dialogue/question |
| `extract_proposals_from_narrative(text)` | Find state changes |

---

## Phase 12: Testing

### T12.1: Unit Tests

```
tests/
├── conftest.py
├── test_orchestrator.py
├── test_narrator.py
├── test_resolver.py
├── test_canonkeeper.py
├── test_memory_manager.py
├── test_indexer.py
├── test_context_assembly.py
└── test_loops/
    ├── test_main_loop.py
    ├── test_story_loop.py
    ├── test_scene_loop.py
    └── test_turn_loop.py
```

### T12.2: Integration Tests

- Full scene flow: start → turns → canonize
- Multi-agent coordination
- State machine transitions

---

## Completion Checklist

```
[ ] T1: Package setup
[ ] T2: BaseAgent class
[ ] T3: Orchestrator (state machine + methods)
[ ] T4: ContextAssembly
[ ] T5: Narrator (+ prompts)
[ ] T6: Resolver (+ prompts)
[ ] T7: CanonKeeper (+ prompts)
[ ] T8: MemoryManager
[ ] T9: Indexer
[ ] T10: Loop implementations (4)
[ ] T11: Utilities
[ ] T12: Tests
```

---

## Dependencies

```
INTERNAL: monitor-data-layer (Layer 1)
EXTERNAL: anthropic, structlog, tenacity
```

---

## Agent Authority Matrix

| Agent | Neo4j | MongoDB | Qdrant | MinIO |
|-------|-------|---------|--------|-------|
| Orchestrator | CreateStory only | scenes, outlines | - | - |
| ContextAssembly | READ | READ | READ | - |
| Narrator | - | turns | - | - |
| Resolver | - | resolutions, proposals | - | - |
| **CanonKeeper** | **ALL** | proposal status | - | - |
| MemoryManager | - | memories | memories | - |
| Indexer | - | docs, snippets | ALL | READ |
