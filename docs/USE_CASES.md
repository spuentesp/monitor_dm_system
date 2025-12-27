# MONITOR Use Cases

> Complete use case catalog organized by functional category.
>
> For product vision, objectives, and epic definitions, see [`SYSTEM.md`](../SYSTEM.md).

---

## System Overview

**MONITOR** is a narrative intelligence system that operates in three modes:

| Mode | Description |
|------|-------------|
| **World Architect** | Build and maintain fictional worlds from structured/unstructured sources |
| **Autonomous GM** | Run full solo RPG experiences with turn-by-turn narration |
| **GM Assistant** | Support human-led campaigns by recording, tracking, and analyzing |

See [SYSTEM.md](../SYSTEM.md) for core objectives (O1-O5) and epics (EPIC 1-8).

---

## Use Case Categories

| Category | Code | Description | Count |
|----------|------|-------------|-------|
| **DATA LAYER** | `DL-` | Canonical data access and MCP interfaces | 14 |
| **PLAY** | `P-` | Core gameplay loop — narration, scenes, actions | 12 |
| **MANAGE** | `M-` | World administration — CRUD for all entities | 30 |
| **QUERY** | `Q-` | Canon exploration — search, browse, ask | 9 |
| **INGEST** | `I-` | Knowledge import — documents, extraction | 6 |
| **SYSTEM** | `SYS-` | App lifecycle, config, session | 10 |
| **CO-PILOT** | `CF-` | Human GM assistant features | 5 |
| **STORY** | `ST-` | Planning & meta-narrative tools | 5 |
| **RULES** | `RS-` | Game system definition — stats, skills, mechanics | 4 |
| **DOCS** | `DOC-` | Documentation publishing & governance | 1 |

**Total: 96 use cases**

## Testing Expectations

- Every use case implementation must add or update unit tests that cover success and failure paths.
- End-to-end or integration tests should exercise the full flow for cross-layer interactions (e.g., CLI → agents → data-layer) where applicable.
- Pull requests that change code without touching tests should be rejected by automation (see `scripts/require_tests_for_code_changes.py` and CI gate).
- Each change must reference at least one use-case ID (DL-, P-, M-, Q-, I-, SYS-, CF-, ST-, RS-, DOC-) in commits/PR body; CI enforces this.

---

# Epic 0: DATA LAYER ACCESS (Foundational)

> These use cases define the explicit data interfaces (tools + schemas) exposed by the data-layer and MCP server. They must be implemented and tested before any agent/CLI work. Each use case maps to MCP commands with authority and validation.

## DL-1: Manage Multiverse/Universes (Neo4j)
- CRUD for Multiverse/Universe nodes, hierarchy, tags.
- MCP: `neo4j_create_universe`, `neo4j_get_universe`, `neo4j_update_universe`, `neo4j_list_universes`, `neo4j_delete_universe`.

## DL-2: Manage Archetypes & Instances (Neo4j)
- CRUD for EntityArchetype/EntityInstance, state_tags, derivatives.
- MCP: `neo4j_create_entity`, `neo4j_get_entity`, `neo4j_update_entity`, `neo4j_list_entities`, `neo4j_delete_entity`.

## DL-3: Manage Facts & Events (Neo4j, provenance)
- CRUD for Facts/Events, relationships, provenance edges (SUPPORTED_BY).
- MCP: `neo4j_create_fact`, `neo4j_get_fact`, `neo4j_update_fact`, `neo4j_list_facts`, `neo4j_delete_fact`, `neo4j_create_event`.

## DL-4: Manage Stories, Scenes, Turns (Neo4j + MongoDB)
- CRUD for Story, Scene, Turn records; status transitions.
- MCP: `neo4j_create_story`, `neo4j_get_story`, `neo4j_update_story`; `mongodb_create_scene`, `mongodb_get_scene`, `mongodb_update_scene`, `mongodb_append_turn`, `mongodb_list_scenes`.

## DL-5: Manage Proposed Changes (MongoDB)
- Create/retrieve/update ProposedChange documents for canonization staging.
- MCP: `mongodb_create_proposed_change`, `mongodb_get_proposed_change`, `mongodb_list_proposed_changes`, `mongodb_update_proposed_change`.

## DL-6: Manage Story Outlines & Plot Threads (MongoDB + Neo4j)
- CRUD for story_outline documents and plot threads; link to stories and facts.
- MCP: `mongodb_create_story_outline`, `mongodb_get_story_outline`, `mongodb_update_story_outline`; `neo4j_create_plot_thread`, `neo4j_list_plot_threads`.

## DL-7: Manage Memories (MongoDB + Qdrant)
- CRUD for CharacterMemory; embedding operations.
- MCP: `mongodb_create_memory`, `mongodb_get_memory`, `mongodb_list_memories`, `mongodb_update_memory`; `qdrant_embed_memory`, `qdrant_search_memories`.

## DL-8: Manage Sources, Documents, Snippets, Ingest Proposals (MongoDB)
- CRUD for sources/documents/snippets and ingest proposals.
- MCP: `neo4j_create_source`; `mongodb_create_document`, `mongodb_get_document`, `mongodb_list_documents`, `mongodb_create_snippet`, `mongodb_list_snippets`, `mongodb_create_ingest_proposal`, `mongodb_list_ingest_proposals`, `mongodb_update_ingest_proposal`.

## DL-9: Manage Binary Assets (MinIO)
- Upload/download/delete/list binaries with metadata references.
- MCP: `minio_upload`, `minio_get_object`, `minio_delete_object`, `minio_list_objects`.

## DL-10: Vector Index Operations (Qdrant)
- Upsert/search/delete embeddings for scenes, memories, snippets.
- MCP: `qdrant_upsert`, `qdrant_search`, `qdrant_delete`.

## DL-11: Text Search Index Operations (OpenSearch)
- Index/search/delete text documents/snippets/facts.
- MCP: `opensearch_index_document`, `opensearch_search`, `opensearch_delete_document`.

## DL-12: MCP Server & Middleware (Auth/Validation/Health)
- Register tools, enforce authority and schema validation, expose health.
- MCP: health/status endpoints; middleware: `auth`, `validation`, tool registry introspection.

## DL-13: Manage Axioms (Neo4j)
- CRUD for Axiom nodes tied to universes; link to sources/snippets.
- MCP: `neo4j_create_axiom`, `neo4j_get_axiom`, `neo4j_update_axiom`, `neo4j_list_axioms`, `neo4j_delete_axiom`.

## DL-14: Manage Relationships & State Tags (Neo4j)
- Create/update/delete relationships between entities (membership, ownership, social, spatial, participation) and update state_tags.
- MCP: `neo4j_create_relationship`, `neo4j_update_relationship`, `neo4j_delete_relationship`, `neo4j_list_relationships`; `neo4j_update_state_tags`.

---

# Epic 1: PLAY (Core Gameplay)

> As a user, I want to play tabletop RPG sessions with an AI Game Master.

## P-1: Start New Story

**Actor:** User
**Trigger:** Play → New Story
**Preconditions:** At least one universe exists (or create during flow)

**Flow:**
1. Select universe (or create new → M-4)
2. Prompt: Story title
3. Prompt: Story type (campaign, arc, episode, one-shot)
4. Prompt: Theme (optional)
5. Prompt: Premise (optional)
6. Select/create participating PCs (→ M-13)
7. Create Story node in Neo4j
8. Create story_outline in MongoDB
9. → P-2 (Start first scene)

**Output:** story_id, ready for scene

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_get_universe(universe_id)           # Validate universe exists
neo4j_create_story(params) -> story_id    # Create Story node
mongodb_create_story_outline(params)      # Create outline document
```

**Layer 2 (Agents):**
- `Orchestrator.start_new_story(universe_id, params)` - Coordinates flow
- Validates universe, prompts user, creates story

**Layer 3 (CLI):**
```bash
monitor play new --universe <UUID> --title "Story Title"
# Or interactive: monitor play new
```

**Database Writes:**

| Database | Collection/Node | Data |
|----------|-----------------|------|
| Neo4j | `:Story` | `{id, universe_id, title, story_type, theme, premise, status: "active"}` |
| MongoDB | `story_outlines` | `{story_id, beats: [], pc_ids: [...]}` |

**Sequence:**
```
User → CLI → Orchestrator
                │
                ├─→ neo4j_get_universe() → validate
                ├─→ neo4j_create_story() → story_id
                ├─→ mongodb_create_story_outline()
                └─→ P-2 (Start Scene)
```

---

## P-2: Start Scene

**Actor:** User/Orchestrator
**Trigger:** New story started, or previous scene ended

**Flow:**
1. Prompt: Scene title (or auto-generate from context)
2. Prompt: Scene purpose (combat, exploration, social, rest, travel)
3. Select location (existing entity or create → M-14)
4. Confirm participating entities (PCs + relevant NPCs)
5. Create Scene document in MongoDB
6. Narrator generates opening description
7. Display scene opening
8. → P-3 (Turn loop)

**Output:** scene_id, scene opening narration

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_get_entity(location_id)             # Validate location
neo4j_list_entities(universe_id, type="character")  # Get available entities
mongodb_create_scene(params) -> scene_id  # Create scene document
mongodb_append_turn(scene_id, turn)       # Opening narration
qdrant_search(query, "scene_chunks")      # Get similar scenes for context
```

**Layer 2 (Agents):**
- `Orchestrator.start_scene(story_id, params)` - Creates scene, coordinates agents
- `ContextAssembly.get_scene_context(story_id)` - Assembles context for narrator
- `Narrator.generate_scene_opening(context)` - Generates opening text

**Layer 3 (CLI):**
```bash
# Automatic in story flow, or:
monitor play scene --story <UUID> --title "Tavern Encounter"
```

**Database Writes:**

| Database | Collection/Node | Data |
|----------|-----------------|------|
| MongoDB | `scenes` | `{id, story_id, title, purpose, status: "active", location_ref, participating_entities, turns: []}` |
| MongoDB | `scenes.turns` | Opening turn: `{speaker: "gm", text: "<opening>"}` |

**Sequence:**
```
Orchestrator
    │
    ├─→ mongodb_create_scene(story_id, params)
    ├─→ ContextAssembly.get_scene_context()
    │       ├─→ neo4j_get_entity(location)
    │       ├─→ neo4j_list_entities(participating)
    │       └─→ qdrant_search(similar scenes)
    ├─→ Narrator.generate_scene_opening(context)
    ├─→ mongodb_append_turn(opening)
    └─→ Display to user → P-3
```

---

## P-3: Turn Loop (Core Gameplay)

**Actor:** User
**Trigger:** Within active scene
**This is the heart of the game.**

```
LOOP:
  1. Display: location, present entities, recent context
  2. Prompt: await user input
  3. Parse input type:
     - Action → P-4
     - Dialogue → P-5
     - Question → P-6
     - Meta-command → P-7
  4. Process through appropriate handler
  5. Narrator generates response
  6. Append turns to MongoDB
  7. Check: should scene end?
  8. IF end → P-8
  9. ELSE → continue loop
```

### Implementation

**Layer 1 (Data Layer):**
```python
# Each turn iteration:
mongodb_get_scene(scene_id)               # Get current scene state
mongodb_get_turns(scene_id, limit=10)     # Recent context
mongodb_append_turn(scene_id, user_turn)  # User input
mongodb_append_turn(scene_id, gm_turn)    # GM response
mongodb_create_proposal(scene_id, ...)    # If canonical changes proposed
```

**Layer 2 (Agents):**
- `Orchestrator.run_turn_loop(scene_id)` - Main loop controller
- `ContextAssembly.get_scene_context(scene_id)` - Build context each turn
- `Narrator.handle_user_input(input, context)` - Parse and respond
- `Resolver.resolve_action(action, context)` - If action needs resolution

**Layer 3 (CLI):**
- Interactive REPL mode within scene
- Input is captured via prompt, output displayed to console

**State Machine:**
```python
class TurnState(Enum):
    AWAITING_INPUT = "awaiting_input"
    PROCESSING = "processing"
    RESOLVING = "resolving"
    RESPONDING = "responding"
    CHECKING_END = "checking_end"
```

**Database Writes Per Turn:**

| Database | Operation | Data |
|----------|-----------|------|
| MongoDB | `scenes.turns.append` | `{turn_id, speaker: "user", text: "...", timestamp}` |
| MongoDB | `scenes.turns.append` | `{turn_id, speaker: "gm", text: "...", resolution_ref?}` |
| MongoDB | `proposed_changes.insert` | If action implies state change |

**Turn Parsing Logic:**
```python
def parse_input(text: str) -> InputType:
    if text.startswith("/"):
        return InputType.META_COMMAND
    if text.startswith('"') or "say" in text.lower():
        return InputType.DIALOGUE
    if "?" in text or text.lower().startswith(("what", "who", "where", "how")):
        return InputType.QUESTION
    return InputType.ACTION
```

---

## P-4: Resolve Action

**Actor:** User
**Trigger:** User declares action ("I attack", "I pick the lock", "I climb")

**Flow:**
1. Parse action intent
2. Identify target entities, difficulty
3. Determine resolution type:
   - **Dice:** Roll required (combat, skill checks)
   - **Narrative:** GM decides (trivial actions)
   - **Deterministic:** Auto-success/fail (impossible/guaranteed)
4. IF dice:
   - Calculate difficulty (DC)
   - → P-9 (Dice roll)
   - Determine success level
5. Create ProposedChanges (state changes, damage, etc.)
6. Narrator describes outcome
7. Return to P-3

**Outcomes:** critical_success, success, partial, failure, critical_failure

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_get_entity(target_id)               # Get target entity state
dice_roll(formula) -> DiceRoll            # Roll dice (P-9)
mongodb_create_resolution(params)         # Store resolution result
mongodb_create_proposal(scene_id, ...)    # Propose state changes
```

**Layer 2 (Agents):**
- `Resolver.resolve_action(action, context)` - Main resolution logic
- `Resolver.evaluate_difficulty(action, context)` - Calculate DC
- `Resolver.determine_effects(action, result)` - Compute state changes
- `Narrator.describe_action_result(action, resolution)` - Narrate outcome

**Resolution Logic:**
```python
class ResolutionType(Enum):
    DICE = "dice"           # Requires roll
    NARRATIVE = "narrative" # GM decides
    AUTO_SUCCESS = "auto_success"
    AUTO_FAIL = "auto_fail"

def determine_resolution_type(action: str, context: Context) -> ResolutionType:
    # Combat actions always need dice
    if is_combat_action(action):
        return ResolutionType.DICE

    # Trivial actions auto-succeed
    if is_trivial(action, context):
        return ResolutionType.AUTO_SUCCESS

    # Impossible actions auto-fail
    if is_impossible(action, context):
        return ResolutionType.AUTO_FAIL

    # Skill checks need dice
    return ResolutionType.DICE

def calculate_dc(action: str, context: Context) -> int:
    """Standard D&D-style DCs: 5 trivial, 10 easy, 15 medium, 20 hard, 25 very hard, 30 nearly impossible"""
    base_dc = 10
    # Adjust based on circumstances
    return base_dc + modifiers
```

**Database Writes:**

| Database | Collection | Data |
|----------|------------|------|
| MongoDB | `resolutions` | `{id, scene_id, turn_id, action, formula, rolls, total, outcome, dc}` |
| MongoDB | `proposed_changes` | `{scene_id, type: "state_change", content: {entity_id, tag, action}}` |

**Outcome Mapping:**
```python
def determine_outcome(roll: int, dc: int) -> Outcome:
    diff = roll - dc
    if diff >= 10:
        return Outcome.CRITICAL_SUCCESS
    elif diff >= 0:
        return Outcome.SUCCESS
    elif diff >= -5:
        return Outcome.PARTIAL
    elif diff >= -10:
        return Outcome.FAILURE
    else:
        return Outcome.CRITICAL_FAILURE
```

---

## P-5: Handle Dialogue

**Actor:** User
**Trigger:** User speaks in-character or to NPC

**Flow:**
1. Identify speaker (PC) and target (NPC or narration)
2. IF targeting NPC:
   - Load NPC personality, memories, facts
   - Generate NPC response using context
   - Create memory for NPC (what was said)
   - May trigger: information exchange, relationship change, quest hook
3. IF narration (speaking aloud):
   - Record as turn
   - Other entities may react
4. Return to P-3

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_get_entity(npc_id)                  # Get NPC data
neo4j_list_facts(entity_id=npc_id)        # NPC's known facts
mongodb_get_memories(entity_id=npc_id)    # NPC's memories
qdrant_search_memories(npc_id, query)     # Semantic memory recall
mongodb_append_turn(scene_id, turn)       # Record dialogue
mongodb_create_memory(npc_id, memory)     # Store NPC memory of conversation
mongodb_create_proposal(...)              # If relationship change proposed
```

**Layer 2 (Agents):**
- `Narrator.handle_dialogue(speaker_id, target_id, text, context)` - Main handler
- `ContextAssembly.get_entity_context(npc_id)` - Assemble NPC context
- `MemoryManager.recall_memories(npc_id, query)` - Get relevant memories
- `MemoryManager.create_memory(npc_id, text, scene_id)` - Store new memory

**NPC Response Generation:**
```python
async def generate_npc_response(
    npc_id: UUID,
    player_said: str,
    context: Context
) -> str:
    # 1. Get NPC personality and state
    npc = await neo4j_get_entity(npc_id)

    # 2. Get NPC's memories of this player/topic
    memories = await qdrant_search_memories(npc_id, player_said, limit=5)

    # 3. Get relevant facts NPC knows
    facts = await neo4j_list_facts(entity_id=npc_id, limit=10)

    # 4. Build prompt with NPC personality, knowledge, memories
    prompt = build_npc_prompt(npc, memories, facts, player_said)

    # 5. Generate response via LLM
    response = await llm_generate(prompt)

    # 6. Create memory for NPC about this conversation
    await mongodb_create_memory({
        "entity_id": npc_id,
        "text": f"Player said: {player_said}. I responded: {response}",
        "scene_id": context.scene_id,
        "importance": 0.6
    })

    return response
```

**Database Writes:**

| Database | Collection | Data |
|----------|------------|------|
| MongoDB | `scenes.turns` | User dialogue turn |
| MongoDB | `scenes.turns` | NPC response turn (speaker: "entity", entity_id: npc_id) |
| MongoDB | `memories` | NPC's memory of conversation |

---

## P-6: Answer Question

**Actor:** User
**Trigger:** User asks about environment, entities, situation

**Examples:** "What do I see?", "Who is in the room?", "What do I know about orcs?"

**Flow:**
1. Parse question type:
   - **Perception:** What's observable (environment, entities)
   - **Knowledge:** What PC knows (facts, memories)
   - **Lore:** What exists in universe (axioms, canon)
2. Query appropriate sources:
   - Scene context (current location, entities)
   - Character memories (what they remember)
   - Canon facts (what's true)
3. Narrator describes based on PC's perspective
4. May reveal or withhold information based on checks
5. Return to P-3

### Implementation

**Layer 1 (Data Layer):**
```python
# By question type:

# Perception questions:
mongodb_get_scene(scene_id)               # Current scene state
neo4j_list_entities(location_id)          # Entities at location

# Knowledge questions:
mongodb_get_memories(entity_id=pc_id)     # PC's memories
qdrant_search_memories(pc_id, query)      # Semantic memory search
neo4j_list_facts(entity_id=pc_id)         # Facts involving PC

# Lore questions:
neo4j_list_axioms(universe_id)            # World rules
qdrant_search(query, "snippet_chunks")    # Search source materials
neo4j_list_facts(universe_id)             # Canon facts
```

**Layer 2 (Agents):**
- `Narrator.answer_question(question, context)` - Main handler
- `ContextAssembly.get_scene_context(scene_id)` - For perception
- `ContextAssembly.get_entity_context(pc_id)` - For knowledge
- `ContextAssembly.semantic_search(query, universe_id)` - For lore

**Question Classification:**
```python
class QuestionType(Enum):
    PERCEPTION = "perception"  # Observable environment
    KNOWLEDGE = "knowledge"    # What PC knows
    LORE = "lore"             # Universe facts/rules

def classify_question(text: str) -> QuestionType:
    text_lower = text.lower()

    # Perception indicators
    if any(word in text_lower for word in ["see", "hear", "smell", "look", "around", "room"]):
        return QuestionType.PERCEPTION

    # Knowledge indicators
    if any(word in text_lower for word in ["know", "remember", "recall", "heard about"]):
        return QuestionType.KNOWLEDGE

    # Lore/general questions
    return QuestionType.LORE

async def answer_question(question: str, context: Context) -> str:
    q_type = classify_question(question)

    match q_type:
        case QuestionType.PERCEPTION:
            # What's observable now
            scene = await mongodb_get_scene(context.scene_id)
            entities = await neo4j_list_entities(scene.location_ref)
            return generate_perception_response(scene, entities)

        case QuestionType.KNOWLEDGE:
            # What PC remembers/knows
            memories = await qdrant_search_memories(context.pc_id, question)
            facts = await neo4j_list_facts(entity_id=context.pc_id)
            return generate_knowledge_response(memories, facts)

        case QuestionType.LORE:
            # Universe facts
            results = await qdrant_search(question, "snippet_chunks")
            axioms = await neo4j_list_axioms(context.universe_id)
            return generate_lore_response(results, axioms)
```

**Information Gating:**
```python
# Some information may require checks to reveal
async def gate_information(info: str, pc: Entity, context: Context) -> str:
    # Check if perception requires roll
    if requires_perception_check(info):
        roll = await dice_roll("1d20")
        dc = get_perception_dc(info)
        if roll.total < dc:
            return "You don't notice anything unusual."

    return info
```

---

## P-7: Meta Commands

**Actor:** User
**Trigger:** Input starts with `/`

| Command | Description | Flow |
|---------|-------------|------|
| `/roll [dice]` | Roll dice manually | → P-9 |
| `/status` | Show scene status, participants, proposals | Display context |
| `/recap` | Summarize recent turns | Generate summary |
| `/end` | End current scene | → P-8 |
| `/pause` | Save and exit to menu | Save state, exit |
| `/undo` | Undo last turn (if not canonized) | Remove turn |
| `/entities` | List entities in scene | Display list |
| `/facts [entity]` | Show facts about entity | → Q-4 |
| `/help` | Show commands | Display help |
| `/character [name]` | View character sheet | → M-16 |

### Implementation

**Layer 1 (Data Layer):**
```python
# Command-specific tools:

# /status
mongodb_get_scene(scene_id)
mongodb_list_pending_proposals(scene_id)

# /recap
mongodb_get_turns(scene_id, limit=20)

# /undo
mongodb_undo_turn(scene_id)

# /entities
neo4j_list_entities(universe_id, filters)

# /facts
neo4j_list_facts(entity_id)

# /character
mongodb_get_character_sheet(entity_id)
neo4j_get_entity(entity_id)
```

**Layer 2 (Agents):**
- `Orchestrator.handle_meta_command(command, args, context)` - Router
- Individual handlers per command type

**Command Router:**
```python
META_COMMANDS = {
    "/roll": handle_roll,
    "/status": handle_status,
    "/recap": handle_recap,
    "/end": handle_end,
    "/pause": handle_pause,
    "/undo": handle_undo,
    "/entities": handle_entities,
    "/facts": handle_facts,
    "/help": handle_help,
    "/character": handle_character,
}

async def handle_meta_command(input_text: str, context: Context) -> MetaResult:
    parts = input_text.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handler = META_COMMANDS.get(command)
    if not handler:
        return MetaResult(error=f"Unknown command: {command}")

    return await handler(args, context)
```

**Command Handlers:**
```python
async def handle_status(args: str, context: Context) -> MetaResult:
    scene = await mongodb_get_scene(context.scene_id)
    proposals = await mongodb_list_pending_proposals(context.scene_id)

    return MetaResult(
        display=format_status(scene, proposals),
        continue_loop=True
    )

async def handle_recap(args: str, context: Context) -> MetaResult:
    turns = await mongodb_get_turns(context.scene_id, limit=20)
    summary = await llm_summarize(turns)

    return MetaResult(
        display=summary,
        continue_loop=True
    )

async def handle_undo(args: str, context: Context) -> MetaResult:
    # Check if scene is not yet canonized
    scene = await mongodb_get_scene(context.scene_id)
    if scene.status != "active":
        return MetaResult(error="Cannot undo after canonization")

    await mongodb_undo_turn(context.scene_id)
    return MetaResult(
        display="Last turn undone.",
        continue_loop=True
    )

async def handle_end(args: str, context: Context) -> MetaResult:
    # Trigger scene end flow
    return MetaResult(
        trigger_scene_end=True,
        continue_loop=False
    )

async def handle_pause(args: str, context: Context) -> MetaResult:
    # Save state and exit
    await mongodb_update_scene(context.scene_id, {"paused": True})
    return MetaResult(
        display="Game paused. Your progress is saved.",
        exit_to_menu=True
    )
```

**Layer 3 (CLI):**
```python
# Commands are handled in the REPL loop
class REPLSession:
    async def process_input(self, text: str):
        if text.startswith("/"):
            result = await self.orchestrator.handle_meta_command(text, self.context)
            self.display(result)
            if result.exit_to_menu:
                return False  # Exit REPL
            if result.trigger_scene_end:
                await self.end_scene()
        else:
            # Normal turn processing
            await self.process_turn(text)
        return True
```

---

## P-8: End Scene (Canonization)

**Actor:** Orchestrator/User
**Trigger:** Scene goal met, user `/end`, or narrative signal

**Flow:**
1. Narrator generates scene closing narration
2. Display closing
3. **Canonization gate:**
   - Fetch pending ProposedChanges for scene
   - For each proposal:
     - Evaluate: authority, confidence, contradictions
     - Accept → write to Neo4j (Fact/Event/Entity)
     - Reject → mark rejected with rationale
   - Link evidence (SUPPORTED_BY edges)
4. Update scene status = "completed"
5. Generate scene summary
6. Embed summary in Qdrant
7. Prompt: New scene (→ P-2), End session (→ SYS-3), or Continue story

### Implementation

**Layer 1 (Data Layer):**
```python
# Canonization tools (CanonKeeper only):
mongodb_list_pending_proposals(scene_id)  # Get pending proposals
neo4j_create_fact(params) -> fact_id      # Write accepted fact
neo4j_create_event(params) -> event_id    # Write accepted event
neo4j_create_entity(params) -> entity_id  # Write new entity
neo4j_set_state_tags(entity_id, changes)  # Update entity state
neo4j_link_evidence(canonical_id, refs)   # SUPPORTED_BY edges
mongodb_evaluate_proposal(id, decision)   # Mark accepted/rejected
mongodb_update_scene(scene_id, status)    # Complete scene
qdrant_embed_scene(scene_id, summary)     # Index for recall
```

**Layer 2 (Agents):**
- `Orchestrator.end_scene(scene_id)` - Coordinates closing flow
- `Narrator.generate_scene_closing(context)` - Closing narration
- `CanonKeeper.canonize_scene(scene_id)` - **Critical: only agent that writes to Neo4j**
- `Indexer.embed_scene_summary(scene_id, summary)` - Vectorize for recall

**Canonization Algorithm:**
```python
async def canonize_scene(scene_id: UUID) -> CanonizationResult:
    proposals = await mongodb_list_pending_proposals(scene_id)

    accepted = []
    rejected = []

    for proposal in proposals:
        decision = await evaluate_proposal(proposal)

        if decision.accept:
            # Write to Neo4j based on proposal type
            canonical_id = await write_to_canon(proposal)

            # Link evidence
            await neo4j_link_evidence(canonical_id, proposal.evidence)

            # Mark accepted
            await mongodb_evaluate_proposal(
                proposal.id,
                status="accepted",
                canonical_id=canonical_id
            )
            accepted.append(canonical_id)
        else:
            await mongodb_evaluate_proposal(
                proposal.id,
                status="rejected",
                rationale=decision.rationale
            )
            rejected.append(proposal.id)

    return CanonizationResult(accepted=accepted, rejected=rejected)

async def evaluate_proposal(proposal: ProposedChange) -> Decision:
    """Evaluate if proposal should be canonized."""

    # 1. Check authority weight
    authority_weight = {
        "source": 1.0,
        "gm": 0.9,
        "player": 0.7,
        "system": 0.5
    }[proposal.authority]

    # 2. Check for contradictions with existing facts
    contradictions = await neo4j_check_contradictions(proposal)
    if contradictions:
        return Decision(accept=False, rationale=f"Contradicts: {contradictions}")

    # 3. Check confidence threshold
    min_confidence = 0.5
    if proposal.confidence * authority_weight < min_confidence:
        return Decision(accept=False, rationale="Below confidence threshold")

    return Decision(accept=True)

async def write_to_canon(proposal: ProposedChange) -> UUID:
    """Write proposal to appropriate Neo4j node type."""
    match proposal.type:
        case "fact":
            return await neo4j_create_fact(proposal.content)
        case "event":
            return await neo4j_create_event(proposal.content)
        case "entity":
            return await neo4j_create_entity(proposal.content)
        case "state_change":
            await neo4j_set_state_tags(
                proposal.content["entity_id"],
                proposal.content["changes"]
            )
            # State changes also create a fact documenting the change
            return await neo4j_create_fact({
                "statement": f"Entity state changed",
                "involved_entity_ids": [proposal.content["entity_id"]]
            })
        case "relationship":
            return await neo4j_create_relationship(proposal.content)
```

**Database Writes:**

| Phase | Database | Operation | Data |
|-------|----------|-----------|------|
| 1 | MongoDB | Read | `proposed_changes WHERE scene_id AND status=pending` |
| 2 | Neo4j | Write | `(:Fact)`, `(:Event)`, `(:EntityInstance)`, relationships |
| 3 | Neo4j | Write | `(:Fact)-[:SUPPORTED_BY]->(:Turn)` edges |
| 4 | MongoDB | Update | `proposed_changes.status = accepted/rejected` |
| 5 | MongoDB | Update | `scenes.status = completed, canonical_outcomes = [...]` |
| 6 | Qdrant | Upsert | Scene summary embedding |

**Invariants:**
- Only CanonKeeper writes to Neo4j (except Orchestrator for Story creation)
- Every canonical fact/event MUST have evidence (SUPPORTED_BY edge)
- Rejected proposals keep their data for audit trail
- Scene status: `active` → `finalizing` → `completed`

---

## P-9: Dice Roll

**Actor:** Resolver
**Trigger:** Action requires dice, or `/roll` command

**Flow:**
1. Parse dice notation (see Dice Module below)
2. Execute roll
3. Apply modifiers
4. Display: formula, individual dice, total
5. IF part of action resolution:
   - Compare to DC/target
   - Determine success level
   - Apply to P-4 outcome

**Dice Notation:**
```
[N]d[S][modifier][keep]

Examples:
  d20       → roll 1d20
  2d6       → roll 2d6, sum
  1d20+5    → roll 1d20, add 5
  4d6kh3    → roll 4d6, keep highest 3
  2d20kl1   → roll 2d20, keep lowest 1 (disadvantage)
  1d20adv   → roll 2d20, keep highest (advantage)
  1d20dis   → roll 2d20, keep lowest (disadvantage)
```

### Implementation

**Layer 1 (Data Layer):**
```python
# Pure utility - no database calls
# Dice module is a standalone utility

import re
import random
from dataclasses import dataclass

@dataclass
class DiceRoll:
    formula: str
    individual_rolls: list[int]
    kept_rolls: list[int]
    modifier: int
    total: int

DICE_PATTERN = re.compile(
    r'^(\d*)d(\d+)'                    # NdS
    r'((?:[+-]\d+)*)?'                 # modifiers (+5-2)
    r'(?:k([hl])(\d+))?'               # keep highest/lowest N
    r'(?:(adv|dis))?$',                # advantage/disadvantage shorthand
    re.IGNORECASE
)

def parse_dice(formula: str) -> dict:
    """Parse dice notation into components."""
    formula = formula.lower().strip()
    match = DICE_PATTERN.match(formula)
    if not match:
        raise ValueError(f"Invalid dice notation: {formula}")

    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    mod_str = match.group(3) or ""
    keep_type = match.group(4)  # 'h' or 'l'
    keep_count = int(match.group(5)) if match.group(5) else None
    adv_dis = match.group(6)  # 'adv' or 'dis'

    # Handle advantage/disadvantage shorthand
    if adv_dis == "adv":
        count, keep_type, keep_count = 2, 'h', 1
    elif adv_dis == "dis":
        count, keep_type, keep_count = 2, 'l', 1

    # Parse modifiers
    modifier = 0
    if mod_str:
        for mod in re.findall(r'[+-]\d+', mod_str):
            modifier += int(mod)

    return {
        "count": count,
        "sides": sides,
        "modifier": modifier,
        "keep_type": keep_type,
        "keep_count": keep_count
    }

def roll_dice(formula: str) -> DiceRoll:
    """Roll dice according to notation."""
    parsed = parse_dice(formula)

    # Roll individual dice
    individual = [random.randint(1, parsed["sides"]) for _ in range(parsed["count"])]

    # Apply keep rules
    if parsed["keep_type"] == 'h' and parsed["keep_count"]:
        kept = sorted(individual, reverse=True)[:parsed["keep_count"]]
    elif parsed["keep_type"] == 'l' and parsed["keep_count"]:
        kept = sorted(individual)[:parsed["keep_count"]]
    else:
        kept = individual

    total = sum(kept) + parsed["modifier"]

    return DiceRoll(
        formula=formula,
        individual_rolls=individual,
        kept_rolls=kept,
        modifier=parsed["modifier"],
        total=total
    )
```

**Layer 2 (Agents):**
- `Resolver.roll(formula, context)` - Wraps dice utility, logs roll if in scene

**Layer 3 (CLI):**
```bash
# Standalone roll
monitor roll 2d6+5

# In-game via meta command
> /roll 1d20+7
🎲 1d20+7 → [14] + 7 = 21
```

**Display Format:**
```python
def format_roll(roll: DiceRoll) -> str:
    """Format roll for CLI display."""
    if roll.individual_rolls != roll.kept_rolls:
        # Show dropped dice
        dropped = [r for r in roll.individual_rolls if r not in roll.kept_rolls]
        dice_str = f"[{', '.join(map(str, roll.kept_rolls))}] (dropped: {dropped})"
    else:
        dice_str = f"[{', '.join(map(str, roll.individual_rolls))}]"

    if roll.modifier != 0:
        mod_str = f" {'+' if roll.modifier > 0 else ''}{roll.modifier}"
    else:
        mod_str = ""

    return f"🎲 {roll.formula} → {dice_str}{mod_str} = {roll.total}"
```

---

## P-10: Combat Mode

**Actor:** User
**Trigger:** Combat initiated

**Flow:**
1. Identify combatants (PCs, NPCs, enemies)
2. Roll initiative (or use fixed order)
3. **Combat loop:**
   ```
   FOR each round:
     FOR each combatant (initiative order):
       IF PC: await player action → P-4
       IF NPC: Narrator decides action → P-4
       Apply resolution
       Check: death, flee, surrender, incapacitated
     END FOR
     Check: combat end conditions
   END FOR
   ```
4. On combat end:
   - Summarize results
   - Update entity states (HP, conditions)
   - Create facts (who won, casualties)
5. Return to P-3 or P-8

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_list_entities(location_id, type="character")  # Get combatants
mongodb_get_character_sheets(entity_ids)            # Get stats/HP
mongodb_update_character_sheet(entity_id, changes)  # Update HP/conditions
mongodb_append_turn(scene_id, combat_turn)          # Log combat actions
mongodb_create_proposal(scene_id, ...)              # State changes (death, etc.)
```

**Layer 2 (Agents):**
- `Orchestrator.enter_combat_mode(scene_id, combatants)` - Initialize combat
- `Resolver.roll_initiative(combatants)` - Roll and order
- `Resolver.resolve_attack(attacker, target, action)` - Combat resolution
- `Narrator.describe_combat_action(action, resolution)` - Narrate results
- `Narrator.decide_npc_action(npc, context)` - AI-controlled enemies

**Combat State Machine:**
```python
@dataclass
class CombatState:
    scene_id: UUID
    round: int = 1
    turn_order: list[Combatant] = field(default_factory=list)
    current_index: int = 0
    status: CombatStatus = CombatStatus.ACTIVE

class CombatStatus(Enum):
    INITIALIZING = "initializing"
    ACTIVE = "active"
    ENDING = "ending"
    ENDED = "ended"

@dataclass
class Combatant:
    entity_id: UUID
    name: str
    initiative: int
    is_pc: bool
    hp_current: int
    hp_max: int
    conditions: list[str] = field(default_factory=list)
    is_active: bool = True  # False if dead/fled/incapacitated
```

**Initiative Roll:**
```python
async def roll_initiative(combatants: list[UUID]) -> list[Combatant]:
    """Roll initiative for all combatants and return sorted order."""
    results = []

    for entity_id in combatants:
        entity = await neo4j_get_entity(entity_id)
        sheet = await mongodb_get_character_sheet(entity_id)

        # Roll 1d20 + DEX modifier (or initiative bonus)
        dex_mod = calculate_modifier(sheet.stats.get("DEX", 10))
        init_roll = roll_dice(f"1d20+{dex_mod}")

        results.append(Combatant(
            entity_id=entity_id,
            name=entity.name,
            initiative=init_roll.total,
            is_pc=(entity.properties.get("role") == "PC"),
            hp_current=sheet.resources.get("hp_current", 10),
            hp_max=sheet.resources.get("hp_max", 10)
        ))

    # Sort by initiative (descending), ties broken by DEX
    return sorted(results, key=lambda c: c.initiative, reverse=True)
```

**Combat Loop:**
```python
async def run_combat_loop(combat: CombatState, context: Context):
    """Main combat loop."""
    while combat.status == CombatStatus.ACTIVE:
        combatant = combat.turn_order[combat.current_index]

        if not combatant.is_active:
            # Skip incapacitated combatants
            combat.current_index = (combat.current_index + 1) % len(combat.turn_order)
            continue

        # Display turn prompt
        display_combat_status(combat)

        if combatant.is_pc:
            # Wait for player input
            action = await prompt_player_action(combatant)
        else:
            # AI decides NPC action
            action = await narrator.decide_npc_action(combatant, combat, context)

        # Resolve action
        resolution = await resolver.resolve_combat_action(action, combat, context)

        # Apply effects
        await apply_combat_effects(resolution, combat)

        # Log turn
        await mongodb_append_turn(context.scene_id, {
            "speaker": "entity" if not combatant.is_pc else "user",
            "entity_id": combatant.entity_id,
            "text": format_combat_action(action, resolution),
            "resolution_ref": resolution.id
        })

        # Check end conditions
        if check_combat_end(combat):
            combat.status = CombatStatus.ENDING
            break

        # Next turn
        combat.current_index = (combat.current_index + 1) % len(combat.turn_order)
        if combat.current_index == 0:
            combat.round += 1

    # Combat ended
    await end_combat(combat, context)
```

**Combat Resolution:**
```python
async def resolve_combat_action(
    action: CombatAction,
    combat: CombatState,
    context: Context
) -> CombatResolution:
    """Resolve a combat action (attack, spell, etc.)."""
    match action.type:
        case "attack":
            # Roll to hit
            attack_roll = roll_dice(f"1d20+{action.attack_bonus}")
            target_ac = await get_target_ac(action.target_id)

            if attack_roll.total >= target_ac:
                # Hit - roll damage
                damage_roll = roll_dice(action.damage_formula)
                return CombatResolution(
                    action=action,
                    attack_roll=attack_roll,
                    hit=True,
                    damage=damage_roll.total,
                    effects=[DamageEffect(action.target_id, damage_roll.total)]
                )
            else:
                return CombatResolution(action=action, attack_roll=attack_roll, hit=False)

        case "spell":
            # Handle spell save or attack
            pass

        case "move":
            # Handle movement
            pass

        case "disengage":
            # Allow flee without opportunity attack
            pass
```

**Combat End Conditions:**
```python
def check_combat_end(combat: CombatState) -> bool:
    """Check if combat should end."""
    pcs = [c for c in combat.turn_order if c.is_pc and c.is_active]
    enemies = [c for c in combat.turn_order if not c.is_pc and c.is_active]

    # All PCs down
    if not pcs:
        return True

    # All enemies down
    if not enemies:
        return True

    return False

async def end_combat(combat: CombatState, context: Context):
    """Finalize combat and create proposals for state changes."""
    # Create proposals for deaths
    for combatant in combat.turn_order:
        if combatant.hp_current <= 0:
            await mongodb_create_proposal(context.scene_id, {
                "type": "state_change",
                "content": {
                    "entity_id": combatant.entity_id,
                    "changes": {"add": ["dead"], "remove": ["alive"]}
                },
                "evidence": [context.scene_id],
                "authority": "system"
            })

    # Update character sheets with final HP
    for combatant in combat.turn_order:
        await mongodb_update_character_sheet(combatant.entity_id, {
            "resources.hp_current": max(0, combatant.hp_current)
        })

    # Generate combat summary
    summary = await narrator.summarize_combat(combat)
    await mongodb_append_turn(context.scene_id, {
        "speaker": "gm",
        "text": f"**Combat Ended**\n{summary}"
    })
```

**Database Writes:**

| Database | Collection | Data |
|----------|------------|------|
| MongoDB | `scenes.turns` | Combat action turns with resolution refs |
| MongoDB | `resolutions` | Attack rolls, damage, saves |
| MongoDB | `character_sheets` | HP updates during combat |
| MongoDB | `proposed_changes` | State changes (death, conditions) |

---

## P-11: Conversation Mode

**Actor:** User
**Trigger:** Extended dialogue with NPC

**Flow:**
1. Enter focused dialogue with specific NPC
2. Load NPC context: personality, memories, goals, secrets
3. **Dialogue loop:**
   - User speaks
   - NPC responds (in character, using context)
   - Track conversation topics
   - May unlock: information, quests, relationship changes
4. Exit back to P-3

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_get_entity(npc_id)                  # NPC data
neo4j_list_facts(entity_id=npc_id)        # Facts NPC knows
neo4j_get_relationships(npc_id)           # NPC's relationships
mongodb_get_memories(entity_id=npc_id)    # NPC's memories
mongodb_get_character_sheet(npc_id)       # NPC's personality/goals
qdrant_search_memories(npc_id, query)     # Semantic memory search
mongodb_append_turn(scene_id, turn)       # Log dialogue
mongodb_create_memory(npc_id, memory)     # Store new NPC memory
mongodb_create_proposal(scene_id, ...)    # Relationship/info proposals
```

**Layer 2 (Agents):**
- `Orchestrator.enter_conversation_mode(scene_id, npc_id)` - Initialize
- `Narrator.generate_npc_response(npc_id, input, context)` - NPC dialogue
- `ContextAssembly.get_npc_full_context(npc_id)` - Deep NPC context
- `MemoryManager.update_npc_memory(npc_id, conversation)` - Memory updates

**Conversation State:**
```python
@dataclass
class ConversationState:
    scene_id: UUID
    npc_id: UUID
    npc_name: str
    topics_discussed: list[str] = field(default_factory=list)
    information_revealed: list[str] = field(default_factory=list)
    relationship_delta: int = 0  # -3 to +3 scale
    status: ConversationStatus = ConversationStatus.ACTIVE

class ConversationStatus(Enum):
    ACTIVE = "active"
    ENDING = "ending"
    ENDED = "ended"
```

**NPC Context Assembly:**
```python
async def get_npc_full_context(npc_id: UUID) -> NPCContext:
    """Assemble complete NPC context for conversation."""
    # Core entity data
    entity = await neo4j_get_entity(npc_id)
    sheet = await mongodb_get_character_sheet(npc_id)

    # Relationships
    relationships = await neo4j_get_relationships(npc_id)

    # Known facts
    facts = await neo4j_list_facts(entity_id=npc_id, limit=20)

    # Memories of player/current scene participants
    recent_memories = await mongodb_get_memories(
        entity_id=npc_id,
        sort_by="last_accessed",
        limit=10
    )

    return NPCContext(
        entity=entity,
        personality=sheet.properties.get("personality", {}),
        goals=sheet.properties.get("goals", []),
        secrets=sheet.properties.get("secrets", []),
        relationships=relationships,
        facts=facts,
        memories=recent_memories
    )

@dataclass
class NPCContext:
    entity: Entity
    personality: dict  # traits, quirks, speech patterns
    goals: list[str]   # what NPC wants
    secrets: list[str] # info NPC may reveal under conditions
    relationships: list[Relationship]
    facts: list[Fact]
    memories: list[Memory]
```

**Conversation Loop:**
```python
async def run_conversation_loop(
    conversation: ConversationState,
    context: Context
):
    """Main conversation loop with NPC."""
    # Get full NPC context once at start
    npc_context = await get_npc_full_context(conversation.npc_id)

    # Build system prompt for NPC persona
    npc_prompt = build_npc_persona_prompt(npc_context)

    while conversation.status == ConversationStatus.ACTIVE:
        # Display conversation prompt
        display_conversation_status(conversation)

        # Get player input
        user_input = await prompt_user(f"[To {conversation.npc_name}]> ")

        # Check for exit commands
        if user_input.lower() in ["/exit", "/leave", "/done"]:
            conversation.status = ConversationStatus.ENDING
            break

        # Search for relevant memories based on what player said
        relevant_memories = await qdrant_search_memories(
            conversation.npc_id,
            user_input,
            limit=3
        )

        # Generate NPC response
        response = await generate_npc_conversation_response(
            npc_prompt=npc_prompt,
            player_said=user_input,
            relevant_memories=relevant_memories,
            conversation_history=get_recent_turns(context.scene_id, limit=10)
        )

        # Check if NPC reveals information
        revealed = await check_information_reveal(
            npc_context.secrets,
            user_input,
            conversation
        )
        if revealed:
            conversation.information_revealed.append(revealed)

        # Track topic
        topic = extract_topic(user_input)
        if topic not in conversation.topics_discussed:
            conversation.topics_discussed.append(topic)

        # Log turns
        await mongodb_append_turn(context.scene_id, {
            "speaker": "user",
            "text": user_input
        })
        await mongodb_append_turn(context.scene_id, {
            "speaker": "entity",
            "entity_id": conversation.npc_id,
            "text": response
        })

    # Conversation ended - update NPC memory
    await end_conversation(conversation, context)

async def end_conversation(conversation: ConversationState, context: Context):
    """Finalize conversation and update NPC state."""
    # Create memory for NPC about the conversation
    summary = summarize_conversation(conversation)
    await mongodb_create_memory(conversation.npc_id, {
        "text": summary,
        "scene_id": context.scene_id,
        "importance": 0.7,
        "emotional_valence": conversation.relationship_delta * 0.2
    })

    # Create proposals for revealed information
    for info in conversation.information_revealed:
        await mongodb_create_proposal(context.scene_id, {
            "type": "fact",
            "content": {
                "statement": info,
                "authority": "player"  # Revealed through player action
            },
            "evidence": [context.scene_id],
            "confidence": 0.8
        })

    # Create proposal for relationship change if significant
    if abs(conversation.relationship_delta) >= 2:
        await mongodb_create_proposal(context.scene_id, {
            "type": "relationship",
            "content": {
                "from_entity": context.pc_id,
                "to_entity": conversation.npc_id,
                "type": "ALLY_OF" if conversation.relationship_delta > 0 else "ENEMY_OF"
            },
            "evidence": [context.scene_id],
            "authority": "system"
        })
```

**Information Reveal Logic:**
```python
async def check_information_reveal(
    secrets: list[str],
    player_input: str,
    conversation: ConversationState
) -> str | None:
    """Check if player input triggers secret reveal."""
    # Use LLM to evaluate if player has earned information
    for secret in secrets:
        # Check if topic relates to secret
        if not topic_matches(player_input, secret):
            continue

        # Check conversation conditions (trust, topics discussed, etc.)
        reveal_chance = calculate_reveal_chance(
            topics_discussed=conversation.topics_discussed,
            relationship_delta=conversation.relationship_delta
        )

        if random.random() < reveal_chance:
            return secret

    return None
```

**Database Writes:**

| Database | Collection | Data |
|----------|------------|------|
| MongoDB | `scenes.turns` | Player and NPC dialogue turns |
| MongoDB | `memories` | NPC memory of conversation |
| MongoDB | `proposed_changes` | Revealed facts, relationship changes |

---

## P-12: Continue Story

**Actor:** User
**Trigger:** Play → Continue

**Flow:**
1. List active stories (status = "active")
2. User selects story
3. Load story state:
   - Last scene (or scene list if between scenes)
   - Recent events summary
4. Display recap
5. Resume: P-3 (mid-scene) or P-2 (new scene)

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_list_stories(universe_id, status="active")   # Get active stories
neo4j_get_story(story_id)                          # Story details
mongodb_get_scenes(story_id, status="active")      # Active scenes
mongodb_get_scene(scene_id)                        # Scene details
mongodb_get_turns(scene_id, limit=10)              # Recent turns
qdrant_search(story_id, "scene_chunks")            # Story context
```

**Layer 2 (Agents):**
- `Orchestrator.list_continuable_stories(universe_id)` - Fetch active stories
- `Orchestrator.continue_story(story_id)` - Resume story
- `ContextAssembly.get_story_recap(story_id)` - Generate recap
- `Narrator.generate_continuation_prompt(context)` - Transition text

**Story State Resolution:**
```python
@dataclass
class StoryState:
    story_id: UUID
    title: str
    last_played: datetime
    active_scene: Scene | None
    scene_count: int
    resume_point: ResumePoint

class ResumePoint(Enum):
    MID_SCENE = "mid_scene"      # Active scene exists, continue turns
    BETWEEN_SCENES = "between"    # No active scene, start new scene
    PAUSED = "paused"            # Explicitly paused, show options

async def get_story_state(story_id: UUID) -> StoryState:
    """Determine where to resume a story."""
    story = await neo4j_get_story(story_id)
    scenes = await mongodb_get_scenes(story_id)

    active_scenes = [s for s in scenes if s.status == "active"]

    if active_scenes:
        return StoryState(
            story_id=story_id,
            title=story.title,
            last_played=story.updated_at,
            active_scene=active_scenes[0],
            scene_count=len(scenes),
            resume_point=ResumePoint.MID_SCENE
        )
    elif scenes and scenes[-1].status == "completed":
        return StoryState(
            story_id=story_id,
            title=story.title,
            last_played=story.updated_at,
            active_scene=None,
            scene_count=len(scenes),
            resume_point=ResumePoint.BETWEEN_SCENES
        )
    else:
        return StoryState(
            story_id=story_id,
            title=story.title,
            last_played=story.updated_at,
            active_scene=None,
            scene_count=len(scenes),
            resume_point=ResumePoint.PAUSED
        )
```

**Story Listing:**
```python
async def list_continuable_stories(universe_id: UUID | None = None) -> list[StorySummary]:
    """List all stories that can be continued."""
    filters = {"status": "active"}
    if universe_id:
        filters["universe_id"] = universe_id

    stories = await neo4j_list_stories(**filters)

    summaries = []
    for story in stories:
        state = await get_story_state(story.id)
        summaries.append(StorySummary(
            story_id=story.id,
            title=story.title,
            universe_name=story.universe.name,
            last_played=state.last_played,
            scene_count=state.scene_count,
            resume_point=state.resume_point
        ))

    # Sort by last played (most recent first)
    return sorted(summaries, key=lambda s: s.last_played, reverse=True)
```

**Recap Generation:**
```python
async def get_story_recap(story_id: UUID) -> str:
    """Generate a recap of recent story events."""
    # Get completed scenes (last 3)
    scenes = await mongodb_get_scenes(story_id, status="completed", limit=3)

    # Get recent events from Neo4j
    events = await neo4j_list_events(story_id, limit=10)

    # Get semantic context
    context_chunks = await qdrant_search(
        query=f"story:{story_id} recent events",
        collection="scene_chunks",
        limit=5
    )

    # Build recap with LLM
    recap = await llm_generate_recap(
        scenes=scenes,
        events=events,
        context=context_chunks
    )

    return recap
```

**Continue Flow:**
```python
async def continue_story(story_id: UUID) -> ContinueResult:
    """Resume a story from where it left off."""
    state = await get_story_state(story_id)

    # Generate recap
    recap = await get_story_recap(story_id)

    # Display recap
    display_recap(state.title, recap)

    match state.resume_point:
        case ResumePoint.MID_SCENE:
            # Resume existing scene
            scene = state.active_scene
            context = await build_scene_context(scene.scene_id)

            # Show recent turns
            recent_turns = await mongodb_get_turns(scene.scene_id, limit=5)
            display_recent_turns(recent_turns)

            # Enter turn loop
            return ContinueResult(
                action="enter_turn_loop",
                scene_id=scene.scene_id,
                context=context
            )

        case ResumePoint.BETWEEN_SCENES:
            # Prompt for new scene
            narrator_prompt = await narrator.generate_continuation_prompt(story_id)
            display(narrator_prompt)

            return ContinueResult(
                action="prompt_new_scene",
                story_id=story_id
            )

        case ResumePoint.PAUSED:
            # Show options
            return ContinueResult(
                action="show_resume_options",
                story_id=story_id,
                options=["Start new scene", "View story details", "End story"]
            )
```

**Layer 3 (CLI):**
```bash
# List continuable stories
monitor play continue

# Direct continue with story ID
monitor play continue --story <UUID>
```

**CLI Display:**
```python
def display_story_list(stories: list[StorySummary]):
    """Display list of continuable stories."""
    print("═══════════════════════════════════════════")
    print("  Continue Story")
    print("═══════════════════════════════════════════")
    print()

    for i, story in enumerate(stories, 1):
        status_icon = {
            ResumePoint.MID_SCENE: "▶",
            ResumePoint.BETWEEN_SCENES: "◯",
            ResumePoint.PAUSED: "⏸"
        }[story.resume_point]

        print(f"  [{i}] {status_icon} {story.title}")
        print(f"      Universe: {story.universe_name}")
        print(f"      Last played: {format_relative_time(story.last_played)}")
        print(f"      Scenes: {story.scene_count}")
        print()

def display_recap(title: str, recap: str):
    """Display story recap before resuming."""
    print()
    print(f"═══ {title} ═══")
    print()
    print("📜 Previously...")
    print()
    print(recap)
    print()
    print("─" * 40)
```

**Database Reads:**

| Database | Collection/Node | Query |
|----------|-----------------|-------|
| Neo4j | `:Story` | `WHERE status = "active"` |
| MongoDB | `scenes` | `WHERE story_id = ? ORDER BY created_at DESC` |
| MongoDB | `scenes.turns` | `WHERE scene_id = ? ORDER BY timestamp DESC LIMIT 10` |
| Qdrant | `scene_chunks` | Semantic search for story context |

---

# Epic 2: MANAGE (World Administration)

> As a user, I want to create, edit, and organize all narrative elements.

## Hierarchy Management

### M-1: Manage Omniverse

**Actor:** Admin
**Trigger:** Settings → Omniverse (rare)

**Flow:**
1. View omniverse info (usually just one)
2. Edit name, description
3. View multiverse list

**Note:** Usually auto-created. Most users won't touch this.

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_omniverse() -> Omniverse           # Get (or create) singleton
neo4j_update_omniverse(id, params)           # Update name/description
neo4j_list_multiverses(omniverse_id)         # List children
```

**Layer 3 (CLI):**
```bash
monitor manage omniverse        # View/edit omniverse
```

**Note:** Omniverse is auto-created on first run if none exists.

---

### M-2: Create Multiverse

**Actor:** User
**Trigger:** Manage → Multiverse → Create

**Flow:**
1. Prompt: Multiverse name (e.g., "D&D Worlds", "Marvel")
2. Prompt: System/setting (e.g., "D&D 5e", "FATE")
3. Prompt: Description
4. Create Multiverse node in Neo4j
5. Link to Omniverse

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_omniverse() -> Omniverse                    # Get parent
neo4j_create_multiverse(omniverse_id, params) -> UUID # Create node + edge
```

**Layer 3 (CLI):**
```bash
monitor manage multiverse create --name "D&D Worlds" --system "D&D 5e"
# Or interactive: monitor manage multiverse create
```

**Database Writes:**

| Database | Node/Edge | Data |
|----------|-----------|------|
| Neo4j | `:Multiverse` | `{id, name, system_name, description, created_at}` |
| Neo4j | `(:Omniverse)-[:CONTAINS]->(:Multiverse)` | Edge |

---

### M-3: List Multiverses

**Actor:** User
**Trigger:** Manage → Multiverses

**Output:** Table of multiverses with universe counts

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_multiverses(omniverse_id) -> list[MultiverseSummary]
# Returns: id, name, system_name, universe_count
```

**Cypher Query:**
```cypher
MATCH (m:Multiverse)<-[:CONTAINS]-(o:Omniverse {id: $omniverse_id})
OPTIONAL MATCH (m)-[:CONTAINS]->(u:Universe)
RETURN m.id, m.name, m.system_name, count(u) AS universe_count
ORDER BY m.name
```

---

### M-4: Create Universe

**Actor:** User
**Trigger:** Manage → Universes → Create

**Flow:**
1. Select multiverse (or create → M-2)
2. Prompt: Universe name
3. Prompt: Genre (fantasy, sci-fi, horror, modern, etc.)
4. Prompt: Tone (serious, humorous, dark, epic)
5. Prompt: Tech level (medieval, renaissance, industrial, modern, futuristic)
6. Prompt: Description
7. Create Universe node in Neo4j
8. Confirm creation

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_multiverses(omniverse_id)              # For selection
neo4j_create_universe(multiverse_id, params) -> UUID
```

**Layer 3 (CLI):**
```bash
monitor manage universe create --multiverse <UUID> --name "Middle-earth" --genre fantasy
# Interactive: monitor manage universe create
```

**Validation (Pydantic):**
```python
class CreateUniverseParams(BaseModel):
    multiverse_id: UUID
    name: str = Field(min_length=1, max_length=100)
    genre: Genre
    tone: Tone
    tech_level: TechLevel
    description: str = Field(max_length=2000)

class Genre(str, Enum):
    FANTASY = "fantasy"
    SCI_FI = "sci-fi"
    HORROR = "horror"
    MODERN = "modern"
    HISTORICAL = "historical"
    SUPERHERO = "superhero"
    POST_APOCALYPTIC = "post-apocalyptic"
    OTHER = "other"

class TechLevel(str, Enum):
    PRIMITIVE = "primitive"
    MEDIEVAL = "medieval"
    RENAISSANCE = "renaissance"
    INDUSTRIAL = "industrial"
    MODERN = "modern"
    NEAR_FUTURE = "near-future"
    FUTURISTIC = "futuristic"
    MIXED = "mixed"
```

**Database Writes:**

| Database | Node/Edge | Data |
|----------|-----------|------|
| Neo4j | `:Universe` | `{id, name, genre, tone, tech_level, description, canon_level: "canon", created_at}` |
| Neo4j | `(:Multiverse)-[:CONTAINS]->(:Universe)` | Edge |

---

### M-5: List Universes

**Actor:** User
**Trigger:** Manage → Universes

**Output:**
```
Universes
─────────────────────────────────────────
 # │ Name            │ Genre    │ Stories │ Entities
───┼─────────────────┼──────────┼─────────┼──────────
 1 │ Middle-earth    │ Fantasy  │ 3       │ 127
 2 │ Forgotten Realms│ Fantasy  │ 1       │ 456
```

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_universes(multiverse_id=None) -> list[UniverseSummary]
```

**Cypher Query:**
```cypher
MATCH (u:Universe)
WHERE u.canon_level <> 'retconned'
OPTIONAL MATCH (u)-[:HAS_STORY]->(s:Story)
OPTIONAL MATCH (u)-[:HAS_ENTITY]->(e:EntityInstance)
RETURN u.id, u.name, u.genre,
       count(DISTINCT s) AS story_count,
       count(DISTINCT e) AS entity_count
ORDER BY u.name
```

**Layer 3 (CLI):**
```bash
monitor manage universe list
monitor manage universe list --multiverse <UUID>
```

---

### M-6: View Universe

**Actor:** User
**Trigger:** Select universe from list

**Output:**
- Basic info (name, genre, tone, tech level)
- Entity counts by type
- Story list
- Source list
- Recent activity

**Actions:** Edit, Delete, Explore, Start Story

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_universe(universe_id) -> Universe
neo4j_get_universe_stats(universe_id) -> UniverseStats
neo4j_list_stories(universe_id, limit=5)
neo4j_list_sources(universe_id, limit=5)
```

**Cypher Query (Stats):**
```cypher
MATCH (u:Universe {id: $universe_id})
OPTIONAL MATCH (u)-[:HAS_ENTITY]->(e:EntityInstance)
WITH u, e.entity_type AS type, count(e) AS count
RETURN u, collect({type: type, count: count}) AS entity_counts
```

**Layer 3 (CLI):**
```bash
monitor manage universe view <UUID>
monitor manage universe view --name "Middle-earth"
```

---

### M-7: Edit Universe

**Actor:** User
**Trigger:** Universe → Edit

**Flow:**
1. Display current values
2. Edit: name, genre, tone, tech_level, description
3. Validate
4. Update Neo4j
5. Confirm

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_universe(universe_id) -> Universe  # Current state
neo4j_update_universe(universe_id, params)   # Apply changes
```

**Layer 3 (CLI):**
```bash
monitor manage universe edit <UUID> --name "New Name"
monitor manage universe edit <UUID>  # Interactive edit
```

---

### M-8: Delete Universe

**Actor:** User
**Trigger:** Universe → Delete

**Flow:**
1. Warning: "This will affect X stories, Y entities, Z facts"
2. Require confirmation (type name)
3. Soft delete: set canon_level = "retconned" on all nodes
4. Confirm deletion

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_universe_stats(universe_id) -> UniverseStats  # For warning
neo4j_soft_delete_universe(universe_id)                 # Soft delete
```

**Soft Delete Logic:**
```python
async def soft_delete_universe(universe_id: UUID) -> DeletionResult:
    """Soft delete a universe and all its contents."""
    # Get counts for confirmation
    stats = await neo4j_get_universe_stats(universe_id)

    # Mark all related nodes as retconned
    # Uses a transaction to ensure atomicity
    await neo4j_run_transaction("""
        MATCH (u:Universe {id: $universe_id})
        SET u.canon_level = 'retconned', u.deleted_at = datetime()

        WITH u
        OPTIONAL MATCH (u)-[:HAS_STORY]->(s:Story)
        SET s.canon_level = 'retconned', s.deleted_at = datetime()

        WITH u
        OPTIONAL MATCH (u)-[:HAS_ENTITY]->(e)
        SET e.canon_level = 'retconned', e.deleted_at = datetime()

        WITH u
        OPTIONAL MATCH (u)-[:HAS_AXIOM]->(a:Axiom)
        SET a.canon_level = 'retconned', a.deleted_at = datetime()
    """, {"universe_id": str(universe_id)})

    return DeletionResult(
        stories_affected=stats.story_count,
        entities_affected=stats.entity_count
    )
```

**Layer 3 (CLI):**
```bash
monitor manage universe delete <UUID>
# Requires confirmation: "Type 'Middle-earth' to confirm deletion"
```

**Important:** Soft delete preserves data. Use `--hard` flag for permanent deletion (admin only).

---

## Story Management

### M-9: List Stories

**Actor:** User
**Trigger:** Manage → Stories

**Filters:** universe, status, type
**Output:** Table with title, universe, status, scenes, last played

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_stories(universe_id=None, status=None, story_type=None) -> list[StorySummary]
```

**Layer 3 (CLI):**
```bash
monitor manage story list
monitor manage story list --universe <UUID> --status active
```

---

### M-10: View Story

**Actor:** User
**Trigger:** Select story from list

**Output:**
- Basic info (title, type, theme, premise)
- Scene list with summaries
- Participating characters
- Plot threads (open, resolved)
- Event timeline

**Actions:** Continue, Edit, Archive, Delete

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_story(story_id) -> Story
mongodb_get_scenes(story_id) -> list[SceneSummary]
neo4j_list_plot_threads(story_id) -> list[PlotThread]
neo4j_list_events(story_id, limit=10) -> list[Event]
```

**Layer 3 (CLI):**
```bash
monitor manage story view <UUID>
```

---

### M-11: Edit Story

**Actor:** User
**Trigger:** Story → Edit

**Editable:** title, theme, premise, status

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_story(story_id) -> Story
neo4j_update_story(story_id, params)
```

**Layer 3 (CLI):**
```bash
monitor manage story edit <UUID> --status completed
```

---

## Entity Management (Generic)

### M-12: Create Entity

**Actor:** User
**Trigger:** Manage → Entities → Create

**Flow:**
1. Select universe
2. Select entity type:
   - Character → M-13
   - Location → M-14
   - Faction → M-15
   - Object → M-17
   - Concept → M-18
   - Organization → M-15 (same as faction)
3. Route to type-specific flow

#### Implementation

**Layer 1 (Data Layer):**
```python
# Generic entity creation (used by all type-specific handlers)
neo4j_create_entity(universe_id, entity_type, params) -> UUID
```

**Entity Type Router:**
```python
ENTITY_HANDLERS = {
    EntityType.CHARACTER: create_character,    # M-13
    EntityType.LOCATION: create_location,      # M-14
    EntityType.FACTION: create_faction,        # M-15
    EntityType.OBJECT: create_object,          # M-17
    EntityType.CONCEPT: create_concept,        # M-18
    EntityType.ORGANIZATION: create_faction,   # Same as faction
}

async def create_entity(universe_id: UUID, entity_type: EntityType) -> UUID:
    handler = ENTITY_HANDLERS[entity_type]
    return await handler(universe_id)
```

**Layer 3 (CLI):**
```bash
monitor manage entity create --universe <UUID> --type character
# Or interactive: monitor manage entity create
```

---

### M-13: Create Character

**Actor:** User
**Trigger:** Create Entity → Character

**Flow:**
1. Prompt: Name
2. Prompt: Role (PC, NPC, antagonist, ally)
3. Prompt: Description
4. Select archetype (from EntityArchetype) or custom
5. IF PC or detailed NPC:
   - Create character_sheet:
     - Stats (STR, DEX, CON, INT, WIS, CHA or system-specific)
     - Resources (HP, MP, etc.)
     - Abilities
     - Equipment
6. Create EntityInstance in Neo4j
7. IF archetype: link DERIVES_FROM
8. Create character_sheet in MongoDB (if applicable)

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_archetypes(universe_id, type="character")  # Available archetypes
neo4j_create_entity(universe_id, "character", params) -> UUID
neo4j_create_relationship(entity_id, archetype_id, "DERIVES_FROM")
mongodb_create_character_sheet(entity_id, stats)
```

**Character Creation Flow:**
```python
async def create_character(universe_id: UUID) -> UUID:
    # 1. Collect basic info
    name = await prompt("Character name:")
    role = await prompt_choice("Role:", ["PC", "NPC", "antagonist", "ally"])
    description = await prompt("Description:")

    # 2. Select or skip archetype
    archetypes = await neo4j_list_archetypes(universe_id, type="character")
    archetype_id = await prompt_choice(
        "Base archetype (optional):",
        [a.name for a in archetypes] + ["Custom"]
    )

    # 3. Create entity in Neo4j
    entity_id = await neo4j_create_entity(universe_id, "character", {
        "name": name,
        "description": description,
        "properties": {
            "role": role,
            "archetype": archetype_id if archetype_id != "Custom" else None
        },
        "state_tags": ["alive"],
        "canon_level": "canon",
        "confidence": 1.0
    })

    # 4. Link to archetype if selected
    if archetype_id and archetype_id != "Custom":
        await neo4j_create_relationship(entity_id, archetype_id, "DERIVES_FROM")

    # 5. Create character sheet if PC or detailed NPC
    if role in ["PC", "NPC"]:
        stats = await prompt_character_stats()
        await mongodb_create_character_sheet(entity_id, {
            "entity_id": entity_id,
            "stats": stats,
            "resources": {
                "hp_max": calculate_hp(stats),
                "hp_current": calculate_hp(stats)
            },
            "created_at": datetime.utcnow()
        })

    return entity_id

async def prompt_character_stats() -> dict:
    """Prompt for D&D-style stats (customizable per system)."""
    stats = {}
    for stat in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        value = await prompt(f"{stat} (8-18):", validator=int_range(8, 18))
        stats[stat] = value
    return stats
```

**Database Writes:**

| Database | Node/Collection | Data |
|----------|-----------------|------|
| Neo4j | `:EntityInstance` | `{id, name, entity_type: "character", properties, state_tags}` |
| Neo4j | `[:DERIVES_FROM]` | Edge to archetype (if selected) |
| Neo4j | `[:HAS_ENTITY]` | Edge from Universe |
| MongoDB | `character_sheets` | `{entity_id, stats, resources}` |

**Layer 3 (CLI):**
```bash
monitor manage entity create --type character --universe <UUID> --name "Gandalf"
# Interactive mode walks through all prompts
```

---

### M-14: Create Location

**Actor:** User
**Trigger:** Create Entity → Location

**Flow:**
1. Prompt: Name
2. Prompt: Location type (city, building, region, planet, room, wilderness)
3. Prompt: Description
4. Prompt: Is exterior? (yes/no)
5. Select parent location (optional, for hierarchy)
6. Create EntityInstance in Neo4j
7. IF parent: create LOCATED_IN edge

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_entities(universe_id, type="location")  # For parent selection
neo4j_create_entity(universe_id, "location", params) -> UUID
neo4j_create_relationship(entity_id, parent_id, "LOCATED_IN")
```

**Layer 3 (CLI):**
```bash
monitor manage entity create --type location --universe <UUID> --name "Rivendell"
```

**Database Writes:**

| Database | Node/Edge | Data |
|----------|-----------|------|
| Neo4j | `:EntityInstance` | `{id, name, entity_type: "location", properties: {location_type, is_exterior}}` |
| Neo4j | `[:LOCATED_IN]` | Edge to parent location (if selected) |

---

### M-15: Create Faction/Organization

**Actor:** User
**Trigger:** Create Entity → Faction

**Flow:**
1. Prompt: Name
2. Prompt: Faction type (political, military, religious, guild, cult, company)
3. Prompt: Description
4. Prompt: Scope (local, regional, global)
5. Prompt: Leadership (link to existing character or create)
6. Create EntityInstance in Neo4j

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_entity(universe_id, "faction", params) -> UUID
neo4j_create_relationship(leader_id, faction_id, "MEMBER_OF", {role: "leader"})
```

**Layer 3 (CLI):**
```bash
monitor manage entity create --type faction --universe <UUID> --name "The Fellowship"
```

---

### M-16: View Entity

**Actor:** User
**Trigger:** Select entity from list

**Output:**
- Basic info (name, type, description)
- Properties (type-specific)
- State tags (current status)
- Relationships (allies, enemies, members, located_in)
- Facts involving entity
- IF character: character sheet, memories

**Actions:** Edit, Manage Relationships, View Memories (if character)

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entity(entity_id) -> Entity
neo4j_get_relationships(entity_id) -> list[Relationship]
neo4j_list_facts(entity_id=entity_id) -> list[Fact]
mongodb_get_character_sheet(entity_id)  # If character
mongodb_get_memories(entity_id, limit=10)  # If character
```

**Layer 3 (CLI):**
```bash
monitor manage entity view <UUID>
monitor manage entity view --name "Gandalf" --universe <UUID>
```

---

### M-17: Create Object

**Actor:** User
**Trigger:** Create Entity → Object

**Flow:**
1. Prompt: Name
2. Prompt: Object type (weapon, armor, artifact, tool, consumable, treasure)
3. Prompt: Description
4. Prompt: Is magical? Is unique?
5. Prompt: Owner (link to character, optional)
6. Create EntityInstance in Neo4j

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_entity(universe_id, "object", params) -> UUID
neo4j_create_relationship(owner_id, object_id, "OWNS")  # If owner set
```

---

### M-18: Create Concept

**Actor:** User
**Trigger:** Create Entity → Concept

**Flow:**
1. Prompt: Name (e.g., "The Force", "Magic System", "Divine Law")
2. Prompt: Concept type (belief, law, force, system)
3. Prompt: Description
4. Prompt: Is abstract?
5. Create EntityInstance in Neo4j

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_entity(universe_id, "concept", params) -> UUID
```

---

### M-19: Edit Entity

**Actor:** User
**Trigger:** Entity → Edit

**Flow:**
1. Display current values
2. Edit: name, description, properties, state_tags
3. Create ProposedChange (for canonization tracking)
4. Update Neo4j (or queue for CanonKeeper)

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entity(entity_id) -> Entity
neo4j_update_entity(entity_id, params)  # Direct update (GM authority)
# OR
mongodb_create_proposal(scene_id, {type: "entity_update", ...})  # Queue for canonization
```

**Layer 3 (CLI):**
```bash
monitor manage entity edit <UUID> --name "New Name"
monitor manage entity edit <UUID> --add-tag wounded --remove-tag healthy
```

---

### M-20: Delete Entity

**Actor:** User
**Trigger:** Entity → Delete

**Flow:**
1. Warning: affects X facts, Y relationships
2. Soft delete: canon_level = "retconned"

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entity_stats(entity_id) -> EntityStats  # Count impacts
neo4j_soft_delete_entity(entity_id)               # Set canon_level = "retconned"
```

---

### M-21: Manage Relationships

**Actor:** User
**Trigger:** Entity → Relationships

**Flow:**
1. Display current relationships:
   - ALLY_OF, ENEMY_OF
   - MEMBER_OF, LOCATED_IN
   - OWNS, DERIVES_FROM
2. Add relationship:
   - Select target entity
   - Select relationship type
   - Create edge in Neo4j
3. Remove relationship:
   - Mark edge as retconned

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_relationships(entity_id) -> list[Relationship]
neo4j_create_relationship(from_id, to_id, type, properties={})
neo4j_delete_relationship(relationship_id)  # Soft delete
```

**Relationship Types:**
```python
RELATIONSHIP_TYPES = [
    "ALLY_OF",      # Symmetric
    "ENEMY_OF",     # Symmetric
    "MEMBER_OF",    # Asymmetric (entity → group)
    "LOCATED_IN",   # Asymmetric (entity → location)
    "OWNS",         # Asymmetric (owner → object)
    "DERIVES_FROM", # Asymmetric (concrete → axiom)
]
```

**Layer 3 (CLI):**
```bash
monitor manage entity relationship add <FROM_UUID> <TO_UUID> --type ALLY_OF
monitor manage entity relationship remove <RELATIONSHIP_UUID>
```

---

### M-22: Manage Memories (Characters only)

**Actor:** User
**Trigger:** Character → Memories

**Flow:**
1. Display memories sorted by importance
2. View: text, emotional_valence, certainty, linked_fact
3. Add memory:
   - Text, importance, emotional_valence
   - Link to fact (optional)
4. Edit memory (for NPCs with uncertain recall)
5. Delete memory

#### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_memories(entity_id, sort_by="importance") -> list[Memory]
mongodb_create_memory(entity_id, params) -> memory_id
mongodb_update_memory(memory_id, params)
mongodb_delete_memory(memory_id)
qdrant_upsert_memory(memory_id, text, entity_id)  # Embed for recall
```

**Layer 3 (CLI):**
```bash
monitor manage entity memory list <ENTITY_UUID>
monitor manage entity memory add <ENTITY_UUID> --text "I met the hero in Rivendell"
```

---

## Axiom & Rule Management

### M-23: Create Axiom

**Actor:** User
**Trigger:** Manage → Axioms → Create

**Flow:**
1. Select universe
2. Prompt: Statement (e.g., "Magic exists", "FTL is impossible")
3. Prompt: Domain (physics, magic, society, biology)
4. Prompt: Confidence (0-100%)
5. Link to source (optional)
6. Create Axiom in Neo4j

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_axiom(universe_id, params) -> UUID
neo4j_link_evidence(axiom_id, source_id, "SUPPORTED_BY")
```

**Layer 3 (CLI):**
```bash
monitor manage axiom create --universe <UUID> --statement "Magic exists" --domain magic
```

**Note:** Axiom.authority can only be `source`, `gm`, or `system` (not `player`).

---

### M-24: List Axioms

**Actor:** User
**Trigger:** Manage → Axioms

**Output:** Table of axioms by domain

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_axioms(universe_id, domain=None) -> list[Axiom]
```

---

### M-25: Edit Axiom

**Actor:** User
**Trigger:** Axiom → Edit

**Editable:** statement, domain, confidence, canon_level

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_axiom(axiom_id) -> Axiom
neo4j_update_axiom(axiom_id, params)
```

---

## Fact & Event Management

### M-26: Create Fact (GM Override)

**Actor:** User (as GM)
**Trigger:** Manage → Facts → Create

**Flow:**
1. Select universe
2. Prompt: Statement
3. Prompt: Time reference (when is this true)
4. Prompt: Duration (ongoing, instant, temporary)
5. Link involved entities
6. Link evidence (source, scene)
7. Create Fact in Neo4j with authority = "gm"

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_fact(universe_id, params) -> UUID
neo4j_link_entities(fact_id, entity_ids, "INVOLVED_IN")
neo4j_link_evidence(fact_id, scene_id, "SUPPORTED_BY")
```

**Note:** This is a GM override path - bypasses normal canonization gate.

---

### M-27: View/Edit Fact

**Actor:** User
**Trigger:** Select fact

**Output:** Statement, entities, evidence, authority, confidence
**Actions:** Edit, Retcon (replace with new fact)

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_fact(fact_id) -> Fact
neo4j_update_fact(fact_id, params)
neo4j_retcon_fact(old_fact_id, new_fact_params) -> UUID  # Creates replacement
```

**Retcon Logic:**
```python
async def retcon_fact(old_fact_id: UUID, new_statement: str) -> UUID:
    """Replace a fact with a corrected version."""
    # Mark old as retconned
    await neo4j_update_fact(old_fact_id, {"canon_level": "retconned"})

    # Create new fact with reference to old
    new_fact_id = await neo4j_create_fact({
        "statement": new_statement,
        "replaces": old_fact_id,
        "authority": "gm",
        "canon_level": "canon"
    })

    return new_fact_id
```

---

## Scene Management

### M-28: List Scenes (in Story)

**Actor:** User
**Trigger:** Story → Scenes

**Output:** Table of scenes with title, status, turn count, summary

#### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_scenes(story_id) -> list[SceneSummary]
```

---

### M-29: View Scene

**Actor:** User
**Trigger:** Select scene

**Output:**
- Title, purpose, location
- Participants
- Turn transcript
- Proposals (accepted/rejected)
- Summary

#### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_scene(scene_id) -> Scene
mongodb_get_turns(scene_id) -> list[Turn]
mongodb_get_proposals(scene_id) -> list[ProposedChange]
neo4j_get_entity(location_ref) -> Entity  # Location details
```

---

### M-30: Manage World Time

**Actor:** User or Orchestrator
**Trigger:** Manage → Universe → Time, or automatic during play

**Purpose:** Track in-world time, calendars, and time-dependent events.

**Flow:**
1. Define or select calendar system:
   - Standard (Earth-like: days, weeks, months, years)
   - Custom (e.g., "28 days per month, 10 months per year")
   - Fantasy (e.g., "The Reckoning of Kings", custom month names)
2. Set current world date/time for universe
3. During play:
   - Time advances per scene (short rest = hours, long rest = days)
   - Travel advances time based on distance
   - Orchestrator prompts: "How much time passes?"
4. Time-dependent effects:
   - Deadlines ("The ritual completes in 3 days")
   - Aging (characters grow older)
   - Seasonal changes (winter arrives, harvest season)
   - Scheduled events (festivals, eclipses)
5. Query time-relative events ("What happened last month?")

**Output:** World clock, calendar display, time-relative event queries

#### Implementation

**Layer 1 (Data Layer):**
```python
# Calendar system definition
neo4j_create_calendar(universe_id, params) -> calendar_id
neo4j_get_calendar(universe_id) -> Calendar
neo4j_update_world_time(universe_id, new_time)

# Time-dependent facts and events
neo4j_create_event(params, scheduled_time=...)  # Future events
neo4j_list_events(universe_id, time_range=...)  # Query by time
neo4j_list_deadlines(universe_id, before=...)   # Upcoming deadlines
```

**Layer 2 (Agents):**
- `Orchestrator.advance_time(duration, reason)` — Move world clock forward
- `ContextAssembly.get_time_context(universe_id)` — Current date, upcoming events
- `Narrator.describe_time_passage(duration, events)` — Narrate what happens

**Layer 3 (CLI):**
```bash
monitor manage universe time --universe <UUID>              # View current time
monitor manage universe time --universe <UUID> --set "Day 15 of Harvest, Year 342"
monitor manage universe time --universe <UUID> --advance "3 days"
monitor manage universe calendar --universe <UUID>         # Define calendar
```

**Calendar Schema:**
```python
@dataclass
class Calendar:
    id: UUID
    universe_id: UUID
    name: str                          # "The Imperial Calendar"

    hours_per_day: int = 24
    days_per_week: int = 7
    weeks_per_month: int = 4
    months_per_year: int = 12

    day_names: list[str] | None        # ["Moonday", "Tirsday", ...]
    month_names: list[str] | None      # ["Deepwinter", "Thawing", ...]

    epoch_name: str = "Year"           # "Year", "Age", "Cycle"
    current_date: WorldDate

@dataclass
class WorldDate:
    year: int
    month: int
    day: int
    hour: int = 0

    def advance(self, days: int = 0, hours: int = 0) -> "WorldDate": ...
    def format(self, calendar: Calendar) -> str: ...

@dataclass
class Deadline:
    id: UUID
    description: str
    target_date: WorldDate
    entity_ids: list[UUID]             # Who/what is affected
    consequence: str                   # What happens if missed
    status: DeadlineStatus             # pending, met, missed
```

**Time Passage During Play:**
```python
class TimeDuration(Enum):
    MOMENT = "moment"        # Seconds to minutes
    SHORT_REST = "short"     # ~1 hour
    LONG_REST = "long"       # 8 hours / overnight
    DAY = "day"              # 24 hours
    TRAVEL_DAY = "travel"    # Day of travel
    WEEK = "week"
    MONTH = "month"
    SEASON = "season"        # ~3 months
    YEAR = "year"

async def advance_time(universe_id: UUID, duration: TimeDuration, reason: str):
    # 1. Calculate new world date
    calendar = await neo4j_get_calendar(universe_id)
    new_date = calendar.current_date.advance(duration)

    # 2. Check for triggered events
    triggered = await neo4j_list_events(universe_id,
        after=calendar.current_date, before=new_date)

    # 3. Check for missed deadlines
    missed = await neo4j_list_deadlines(universe_id, before=new_date, status="pending")

    # 4. Update world time
    await neo4j_update_world_time(universe_id, new_date)

    # 5. Generate narration if events occurred
    if triggered or missed:
        return await narrator.describe_time_passage(duration, triggered, missed)
```

---

---

# Epic 3: QUERY (Canon Exploration)

> As a user, I want to explore and ask questions about the canonical world.

## Q-1: Semantic Search

**Actor:** User
**Trigger:** Query → Search

**Flow:**
1. Prompt: Natural language query
2. Embed query → Qdrant search
3. Retrieve: entities, facts, scenes, snippets
4. Rank by relevance
5. Display results with context
6. Allow drill-down

**Examples:**
- "Where is the One Ring?"
- "What happened to Gandalf?"
- "Who are the enemies of the Fellowship?"

### Implementation

**Layer 1 (Data Layer):**
```python
qdrant_search(query, collection, universe_id, limit=10) -> list[SearchResult]
neo4j_get_entity(entity_id)           # Hydrate entity results
neo4j_get_fact(fact_id)               # Hydrate fact results
mongodb_get_scene(scene_id)           # Hydrate scene results
```

**Search Flow:**
```python
async def semantic_search(query: str, universe_id: UUID) -> SearchResults:
    # 1. Search across all collections
    entity_results = await qdrant_search(query, "entity_chunks", universe_id)
    scene_results = await qdrant_search(query, "scene_chunks", universe_id)
    snippet_results = await qdrant_search(query, "snippet_chunks", universe_id)

    # 2. Merge and rank by score
    all_results = merge_results(entity_results, scene_results, snippet_results)
    ranked = sorted(all_results, key=lambda r: r.score, reverse=True)[:10]

    # 3. Hydrate with full data
    hydrated = []
    for result in ranked:
        match result.type:
            case "entity":
                entity = await neo4j_get_entity(result.id)
                hydrated.append(EntityResult(entity, result.score))
            case "scene":
                scene = await mongodb_get_scene(result.id)
                hydrated.append(SceneResult(scene, result.score))
            case "snippet":
                snippet = await mongodb_get_snippet(result.id)
                hydrated.append(SnippetResult(snippet, result.score))

    return SearchResults(query=query, results=hydrated)
```

**Layer 3 (CLI):**
```bash
monitor query search "Where is the One Ring?"
monitor query search "What happened to Gandalf?" --universe <UUID>
```

---

## Q-2: Ask About Entity

**Actor:** User
**Trigger:** Query → Ask, or "Tell me about [X]"

**Flow:**
1. Identify entity by name or ID
2. Retrieve:
   - Entity properties
   - Related facts
   - Relationships
   - Memories (if character)
   - Recent events
3. Generate natural language summary
4. Display

**Examples:**
- "Tell me about Gandalf"
- "What do I know about Mordor?"
- "Who is Sauron?"

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_find_entity(name, universe_id) -> Entity | None
neo4j_get_entity(entity_id) -> Entity
neo4j_get_relationships(entity_id) -> list[Relationship]
neo4j_list_facts(entity_id=entity_id, limit=20) -> list[Fact]
neo4j_list_events(entity_id=entity_id, limit=10) -> list[Event]
mongodb_get_memories(entity_id, limit=10) -> list[Memory]
```

**Entity Summary Generation:**
```python
async def ask_about_entity(query: str, universe_id: UUID) -> str:
    # 1. Extract entity name from query
    entity_name = extract_entity_name(query)

    # 2. Find entity
    entity = await neo4j_find_entity(entity_name, universe_id)
    if not entity:
        return f"I don't know of any '{entity_name}' in this universe."

    # 3. Gather context
    relationships = await neo4j_get_relationships(entity.id)
    facts = await neo4j_list_facts(entity_id=entity.id, limit=20)
    events = await neo4j_list_events(entity_id=entity.id, limit=10)

    memories = []
    if entity.entity_type == "character":
        memories = await mongodb_get_memories(entity.id, limit=10)

    # 4. Generate summary with LLM
    summary = await llm_generate_entity_summary(
        entity=entity,
        relationships=relationships,
        facts=facts,
        events=events,
        memories=memories
    )

    return summary
```

**Layer 3 (CLI):**
```bash
monitor query ask "Tell me about Gandalf"
monitor query entity <UUID>
```

---

## Q-3: Browse Entities

**Actor:** User
**Trigger:** Query → Browse

**Flow:**
1. Select universe
2. Select entity type (or all)
3. Display paginated list
4. Filter: name, state, properties
5. Select for details → M-16

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_entities(universe_id, type=None, filters={}, offset=0, limit=20) -> list[Entity]
```

**Layer 3 (CLI):**
```bash
monitor query entities --universe <UUID>
monitor query entities --type character --filter "role=PC"
```

---

## Q-4: Explore Facts

**Actor:** User
**Trigger:** Query → Facts

**Flow:**
1. Select universe
2. Filter by:
   - Entity (facts involving X)
   - Authority (source, gm, player, system)
   - Canon level (canon, proposed, retconned)
   - Time range
3. Display facts with evidence links
4. Navigate to related entities

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_facts(
    universe_id,
    entity_id=None,
    authority=None,
    canon_level="canon",
    offset=0,
    limit=20
) -> list[Fact]
```

**Layer 3 (CLI):**
```bash
monitor query facts --universe <UUID>
monitor query facts --entity <UUID> --authority gm
```

---

## Q-5: View Timeline

**Actor:** User
**Trigger:** Query → Timeline

**Flow:**
1. Select scope (story or universe)
2. Display chronological events
3. Filter by: entity, event type, severity
4. Click event for details

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_events(
    story_id=None,
    universe_id=None,
    entity_id=None,
    order_by="time_ref"
) -> list[Event]
```

**Layer 3 (CLI):**
```bash
monitor query timeline --story <UUID>
monitor query timeline --universe <UUID> --entity <UUID>
```

---

## Q-6: Relationship Graph

**Actor:** User
**Trigger:** Query → Relationships

**Flow:**
1. Select starting entity
2. Display relationship graph (text or visual tree)
3. Navigate interactively
4. Show: ALLY_OF, ENEMY_OF, MEMBER_OF, LOCATED_IN, OWNS

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_relationship_graph(entity_id, depth=2) -> Graph
```

**Cypher Query:**
```cypher
MATCH (e:EntityInstance {id: $entity_id})-[r]-(related)
WHERE r.canon_level <> 'retconned'
RETURN e, r, related
```

**Layer 3 (CLI):**
```bash
monitor query graph <ENTITY_UUID>
monitor query graph <ENTITY_UUID> --depth 3
```

**Text Tree Display:**
```
Gandalf (character)
├── ALLY_OF
│   ├── Frodo Baggins
│   └── Aragorn
├── MEMBER_OF
│   └── The Fellowship
└── LOCATED_IN
    └── Middle-earth
```

---

## Q-7: Ask Question (Natural Language)

**Actor:** User
**Trigger:** Query → Ask (free-form)

**Flow:**
1. User asks natural language question
2. Parse intent:
   - Entity lookup
   - Fact search
   - Relationship query
   - Timeline query
3. Execute appropriate query
4. Generate natural language answer
5. Display with sources

**Examples:**
- "What happened in the last session?"
- "Who killed the dragon?"
- "Where did we find the artifact?"
- "What are the rules for magic in this world?"

### Implementation

**Layer 1 (Data Layer):**
```python
# Uses multiple tools based on intent
qdrant_search(query, collections, universe_id)
neo4j_list_facts(filters)
neo4j_list_entities(filters)
neo4j_list_axioms(filters)
mongodb_get_scenes(story_id)
```

**Layer 2 (Agents):**
- `ContextAssembly.answer_question(question, universe_id)` - Main handler

**Question Answering Flow:**
```python
async def answer_question(question: str, universe_id: UUID) -> Answer:
    # 1. Classify question intent
    intent = await classify_question_intent(question)

    # 2. Gather relevant context based on intent
    context = []

    if intent.needs_semantic_search:
        results = await qdrant_search(question, ["scene_chunks", "snippet_chunks"], universe_id)
        context.extend(results)

    if intent.entity_name:
        entity = await neo4j_find_entity(intent.entity_name, universe_id)
        if entity:
            facts = await neo4j_list_facts(entity_id=entity.id)
            context.extend(facts)

    if intent.is_rules_question:
        axioms = await neo4j_list_axioms(universe_id)
        context.extend(axioms)

    if intent.is_timeline_question:
        events = await neo4j_list_events(universe_id=universe_id, limit=20)
        context.extend(events)

    # 3. Generate answer with LLM
    answer = await llm_generate_answer(
        question=question,
        context=context
    )

    # 4. Include sources
    sources = extract_sources(context)

    return Answer(text=answer, sources=sources)
```

**Layer 3 (CLI):**
```bash
monitor query ask "What happened in the last session?"
monitor query ask "What are the rules for magic?"
```

---

## Q-8: Compare Entities

**Actor:** User
**Trigger:** Query → Compare

**Flow:**
1. Select two or more entities
2. Display side-by-side:
   - Properties
   - Stats (if characters)
   - Relationships to each other
   - Common facts

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entities(entity_ids) -> list[Entity]
neo4j_get_shared_facts(entity_ids) -> list[Fact]
neo4j_get_mutual_relationships(entity_ids) -> list[Relationship]
mongodb_get_character_sheets(entity_ids) -> list[CharacterSheet]
```

**Comparison Logic:**
```python
async def compare_entities(entity_ids: list[UUID]) -> Comparison:
    # 1. Get all entities
    entities = await neo4j_get_entities(entity_ids)

    # 2. Get shared facts
    shared_facts = await neo4j_get_shared_facts(entity_ids)

    # 3. Get mutual relationships
    mutual_rels = await neo4j_get_mutual_relationships(entity_ids)

    # 4. Get character sheets if applicable
    sheets = {}
    character_ids = [e.id for e in entities if e.entity_type == "character"]
    if character_ids:
        sheets = await mongodb_get_character_sheets(character_ids)

    return Comparison(
        entities=entities,
        shared_facts=shared_facts,
        mutual_relationships=mutual_rels,
        character_sheets=sheets
    )
```

**Layer 3 (CLI):**
```bash
monitor query compare <UUID1> <UUID2>
monitor query compare --names "Gandalf" "Saruman" --universe <UUID>
```

---

## Q-9: Keyword Search (OpenSearch)

**Actor:** User
**Trigger:** Query → Keyword search

**Flow:**
1. Enter keyword query with optional filters (universe, entity type, date range).
2. Search OpenSearch index for entities/facts/documents.
3. Return ranked results with snippets and links to canonical records.

**Output:** Ranked results with context snippets.

**Implementation**
- Data Layer: OpenSearch client query endpoints.
- Agents: ContextAssembly formats and enriches results.
- CLI: `monitor query --keyword "ancient dragon" --universe <UUID>`.

---

---

# Epic 4: INGEST (Knowledge Import)

> As a user, I want to import external documents to populate the canon.

## I-1: Upload Document

**Actor:** User
**Trigger:** Ingest → Upload

**Flow:**
1. Select file (PDF, EPUB, TXT, MD, DOCX)
2. Select target universe (or create)
3. Prompt: Source type (manual, rulebook, lore, homebrew, session_notes)
4. Prompt: Authority level (authoritative, canon, proposed)
5. Upload to MinIO
6. Create Source node in Neo4j
7. Create Document record in MongoDB
8. → I-2 (Extract)

### Implementation

**Layer 1 (Data Layer):**
```python
minio_upload(file_path, bucket="documents") -> minio_ref
neo4j_create_source(universe_id, params) -> source_id
mongodb_create_document(params) -> doc_id
```

**Upload Flow:**
```python
async def upload_document(
    file_path: Path,
    universe_id: UUID,
    source_type: SourceType,
    canon_level: SourceCanonLevel
) -> UploadResult:
    # 1. Upload to MinIO
    minio_ref = await minio_upload(file_path, bucket="documents")

    # 2. Create Source in Neo4j
    source_id = await neo4j_create_source(universe_id, {
        "title": file_path.stem,
        "source_type": source_type,
        "canon_level": canon_level,
        "provenance": "user_upload"
    })

    # 3. Create Document record in MongoDB
    doc_id = await mongodb_create_document({
        "source_id": source_id,
        "universe_id": universe_id,
        "minio_ref": minio_ref,
        "filename": file_path.name,
        "file_type": file_path.suffix,
        "extraction_status": "pending"
    })

    # 4. Queue extraction
    await queue_extraction(doc_id)

    return UploadResult(source_id=source_id, doc_id=doc_id)
```

**Layer 3 (CLI):**
```bash
monitor ingest upload ./phb.pdf --universe <UUID> --type rulebook --authority authoritative
```

---

## I-2: Extract Content

**Actor:** System (Indexer)
**Trigger:** After upload

**Flow:**
1. Extract text from document
2. Chunk into snippets (500 tokens, 50 overlap)
3. Store snippets in MongoDB
4. Embed snippets in Qdrant
5. → I-3 (Entity extraction)

### Implementation

**Layer 1 (Data Layer):**
```python
minio_download(minio_ref) -> bytes
mongodb_create_snippet(doc_id, params) -> snippet_id
qdrant_upsert(collection, vector, payload)
mongodb_update_document(doc_id, {"extraction_status": "complete"})
```

**Layer 2 (Agents):**
- `Indexer.extract_content(doc_id)` - Main extraction flow

**Extraction Flow:**
```python
async def extract_content(doc_id: UUID) -> ExtractionResult:
    # 1. Get document metadata
    doc = await mongodb_get_document(doc_id)

    # 2. Download file from MinIO
    content = await minio_download(doc.minio_ref)

    # 3. Extract text based on file type
    text = await extract_text(content, doc.file_type)

    # 4. Chunk text (500 tokens, 50 overlap)
    chunks = chunk_text(text, chunk_size=500, overlap=50)

    # 5. Store snippets and embed
    snippet_ids = []
    for i, chunk in enumerate(chunks):
        # Store in MongoDB
        snippet_id = await mongodb_create_snippet(doc_id, {
            "doc_id": doc_id,
            "source_id": doc.source_id,
            "text": chunk.text,
            "page": chunk.page,
            "section": chunk.section,
            "chunk_index": i
        })

        # Embed in Qdrant
        embedding = await embed_text(chunk.text)
        await qdrant_upsert("snippet_chunks", {
            "id": snippet_id,
            "vector": embedding,
            "payload": {
                "snippet_id": str(snippet_id),
                "doc_id": str(doc_id),
                "source_id": str(doc.source_id),
                "universe_id": str(doc.universe_id),
                "text": chunk.text
            }
        })
        snippet_ids.append(snippet_id)

    # 6. Update document status
    await mongodb_update_document(doc_id, {"extraction_status": "complete"})

    # 7. Queue entity extraction
    await queue_entity_extraction(doc_id, snippet_ids)

    return ExtractionResult(snippet_count=len(snippet_ids))
```

---

## I-3: Extract Entities

**Actor:** System (Indexer + LLM)
**Trigger:** After content extraction

**Flow:**
1. LLM processes snippets
2. Identifies:
   - Characters (named, archetypes)
   - Locations
   - Factions
   - Objects
   - Concepts/Rules
3. Creates ProposedChange for each
4. Links evidence to source snippets
5. Queue for review → I-4

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_snippets(doc_id) -> list[Snippet]
mongodb_create_ingest_proposal(params) -> proposal_id
```

**Layer 2 (Agents):**
- `Indexer.extract_entities(doc_id)` - Main entity extraction

**Entity Extraction Flow:**
```python
async def extract_entities(doc_id: UUID) -> list[IngestProposal]:
    doc = await mongodb_get_document(doc_id)
    snippets = await mongodb_get_snippets(doc_id)

    proposals = []

    # Process snippets in batches
    for batch in chunk_list(snippets, batch_size=10):
        batch_text = "\n\n".join([s.text for s in batch])

        # LLM extraction
        extracted = await llm_extract_entities(batch_text, doc.source_type)

        for entity in extracted.entities:
            proposal = await mongodb_create_ingest_proposal({
                "doc_id": doc_id,
                "source_id": doc.source_id,
                "universe_id": doc.universe_id,
                "type": entity.type,  # entity, axiom, fact
                "content": entity.to_dict(),
                "evidence": [s.id for s in batch],
                "confidence": entity.confidence,
                "status": "pending"
            })
            proposals.append(proposal)

    return proposals

async def llm_extract_entities(text: str, source_type: str) -> ExtractedEntities:
    """Use LLM to identify entities, rules, and facts from text."""
    prompt = f"""
    Extract entities, rules, and facts from this {source_type} text.

    Text:
    {text}

    Return JSON with:
    - entities: [{{name, type, description, properties}}]
    - axioms: [{{statement, domain}}]
    - facts: [{{statement}}]
    """
    return await llm_structured_output(prompt, ExtractedEntities)
```

---

## I-4: Review Proposals

**Actor:** User
**Trigger:** Ingest → Review

**Flow:**
1. List pending proposals (grouped by source)
2. For each:
   - Display proposed entity/fact
   - Show source snippet (evidence)
   - Show confidence score
3. Actions:
   - Accept → canonize to Neo4j
   - Edit → modify and accept
   - Reject → mark rejected
   - Skip → decide later

---

## I-5: Manage Sources

**Actor:** User
**Trigger:** Ingest → Sources

**Flow:**
1. List sources by universe
2. View: title, type, entity count, snippet count
3. Actions:
   - View details
   - Re-process (extract again)
   - Set authority level
   - Delete (soft)

---

## I-6: Manage Binary Assets (MinIO)

**Actor:** User
**Trigger:** Ingest → Upload binary

**Flow:**
1. Upload binary (PDF/image/audio) to MinIO with metadata (source_id, universe_id).
2. Link binary to source document and entity references (if known).
3. Retrieve or stream binary by source/entity.
4. Delete/replace binary (soft delete, retain metadata).

**Output:** Binary stored with retrievable URL and metadata.

**Implementation**
- Data Layer: MinIO client operations; metadata references stored alongside sources/entities.
- Agents: Indexer handles uploads; CanonKeeper links evidence to binaries.
- CLI: `monitor ingest --binary <file> --universe <UUID>`.

---

---

# Epic 5: SYSTEM (Configuration & Lifecycle)

> As a user, I want to configure and manage the application.

## SYS-1: Start Application

**Actor:** User
**Trigger:** Run `monitor` command

**Flow:**
1. Load configuration
2. Initialize database connections
3. Verify all services healthy
4. Display main menu

---

## SYS-2: Main Menu

**Actor:** User
**Trigger:** At main menu

**Menu:**
```
MONITOR - Auto-GM
═══════════════════

  [P] Play      - Start or continue story
  [M] Manage    - Universes, stories, entities
  [Q] Query     - Search and explore canon
  [I] Ingest    - Upload documents
  [S] Settings  - Configuration
  [X] Exit

>
```

---

## SYS-3: Exit Application

**Actor:** User
**Trigger:** Exit or Ctrl+C

**Flow:**
1. IF in active scene:
   - Prompt: Save progress?
   - Auto-save if configured
2. Close database connections
3. Exit cleanly

---

## SYS-4: Configure LLM

**Actor:** User
**Trigger:** Settings → LLM

**Settings:**
- Model: claude-sonnet-4, claude-opus-4
- Temperature: 0.0 - 1.0
- Max tokens
- API key

---

## SYS-5: Configure Databases

**Actor:** User
**Trigger:** Settings → Databases

**Flow:**
1. Display connection status for each DB
2. Test connections
3. Edit connection strings if needed

---

## SYS-6: User Preferences

**Actor:** User
**Trigger:** Settings → Preferences

**Settings:**
- Default universe
- Auto-save frequency
- Narrator verbosity (concise, normal, verbose)
- Dice display (show individual dice, show formula)
- Theme (dark, light)

---

## SYS-7: Export Data

**Actor:** User
**Trigger:** Settings → Export

**Flow:**
1. Select scope:
   - Everything
   - Universe
   - Story
2. Select format (JSON, Markdown)
3. Generate export
4. Save to file

---

## SYS-8: Import Data

**Actor:** User
**Trigger:** Settings → Import

**Flow:**
1. Select file
2. Validate format
3. Preview changes
4. Merge strategy: overwrite, append, skip conflicts
5. Execute import

---

## SYS-9: Verify Backup/Restore

**Actor:** Operator
**Trigger:** Scheduled verification or manual

**Flow:**
1. Restore snapshot to scratch environment.
2. Run integrity checks (Neo4j constraints, MongoDB indexes, Qdrant collections).
3. Run sample queries to validate data.
4. Report status and failures.

**Output:** Verification report with pass/fail.

---

## SYS-10: Retention and Archival

**Actor:** Operator
**Trigger:** Policy enforcement

**Flow:**
1. Define retention policies for narrative data (scenes, turns, embeddings).
2. Archive or prune per policy (move to cold storage, delete embeddings).
3. Update indices and references.
4. Log actions for audit.

**Output:** Policy-compliant storage footprint.

---

# Epic 6: CO-PILOT (Human GM Assistant)

> As a human Game Master, I want AI assistance during and after sessions without replacing my authority.

This epic supports **EPIC 7 — Human GM Assistant Mode** from [SYSTEM.md](../SYSTEM.md).

**Core Principle:** The system augments, never overrides. The human GM remains in control.

---

## CF-1: Record Live Session

**Actor:** Human GM
**Trigger:** Co-Pilot → Start Recording

**Purpose:** Capture session events in real-time for later canonization.

**Flow:**
1. GM starts recording mode
2. System enters passive observation:
   - GM narrates or types events as they happen
   - System parses and categorizes input (action, dialogue, lore, decision)
3. System creates draft scene document in MongoDB
4. For each significant event:
   - Create `ProposedChange` (pending review)
   - Tag with timestamp, participants, location
5. GM can annotate in real-time ("this is important", "NPC name: Varys")
6. Session ends → scene saved as draft
7. → CF-2 (Generate recap) or → I-4 (Review proposals)

**Input Modes:**
- Text: GM types events as they happen
- Voice: *(future)* Transcription of table audio
- Hybrid: Quick notes + post-session expansion

**Output:** Draft scene with pending proposals

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_scene(story_id, params, status="draft")  # Draft scene
mongodb_append_turn(scene_id, turn)                      # Each event
mongodb_create_proposal(scene_id, type, content)         # Pending changes
```

**Layer 2 (Agents):**
- `Orchestrator.start_recording_session(story_id)` — Initialize recording mode
- `Narrator.parse_gm_input(text, context)` — Categorize GM narration
- `Indexer.extract_entities_realtime(text)` — Detect new NPCs, locations

**Layer 3 (CLI):**
```bash
monitor copilot record --story <UUID>
# Interactive mode with live input
```

**State:**
```python
class RecordingState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    FINALIZING = "finalizing"
```

---

## CF-2: Generate Session Recap

**Actor:** Human GM or Player
**Trigger:** Co-Pilot → Recap (after session ends)

**Purpose:** Create human-readable summary of what happened.

**Flow:**
1. Select session/scene to recap
2. System analyzes:
   - All turns in scene
   - Accepted proposals
   - Key decisions and outcomes
3. Generate structured recap:
   - **Summary:** 2-3 paragraph overview
   - **Key Events:** Bulleted list
   - **Decisions Made:** Player choices and consequences
   - **NPCs Encountered:** Names and roles
   - **Threads Opened/Closed:** Plot progression
   - **Loot/Rewards:** If applicable
4. Display recap
5. Option: Export as Markdown, share with players

**Output:** Formatted session summary

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_scene(scene_id)                    # Get scene
mongodb_get_turns(scene_id)                    # All turns
mongodb_get_proposals(scene_id, status="accepted")  # What became canon
neo4j_list_events(scene_id)                    # Canonical events
```

**Layer 2 (Agents):**
- `ContextAssembly.get_full_scene_history(scene_id)` — Compile all data
- `Narrator.generate_recap(scene_history)` — LLM summarization

**Layer 3 (CLI):**
```bash
monitor copilot recap --scene <UUID>
monitor copilot recap --story <UUID> --last   # Most recent scene
monitor copilot recap --story <UUID> --all    # Full story recap
```

**LLM Prompt Structure:**
```python
RECAP_PROMPT = """
Summarize this RPG session for players. Include:
1. What happened (narrative summary)
2. Important decisions the party made
3. New information learned
4. Unresolved questions or hooks

Session data:
{scene_turns}

Tone: {story_tone}
"""
```

---

## CF-3: Detect Unresolved Threads

**Actor:** Human GM
**Trigger:** Co-Pilot → Threads (or automatic at session end)

**Purpose:** Surface plot hooks, promises, and dangling storylines the GM may have forgotten.

**Flow:**
1. Analyze story history:
   - All scenes in current story
   - All proposals and facts
   - NPC statements and promises
   - Player stated intentions
2. Identify unresolved items:
   - **Open Questions:** Things players asked but weren't answered
   - **Unfulfilled Promises:** NPCs promised something, not delivered
   - **Dangling Hooks:** Clues planted but not followed up
   - **Incomplete Quests:** Started but not finished
   - **Missing Payoffs:** Setups without resolution
3. Rank by:
   - Recency (older = more urgent)
   - Importance (player interest level)
   - Story relevance
4. Display prioritized list
5. GM can: dismiss, mark resolved, add notes

**Output:** Prioritized list of unresolved threads

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_list_scenes(story_id)                  # All scenes
mongodb_get_turns(scene_id) for each scene     # All dialogue
neo4j_list_facts(story_id, type="promise")     # Tracked promises
neo4j_list_plot_threads(story_id, status="open")  # Open threads
qdrant_search(query="unresolved", story_id)    # Semantic search
```

**Layer 2 (Agents):**
- `ContextAssembly.get_story_history(story_id)` — Full story context
- `CanonKeeper.analyze_threads(story_history)` — LLM analysis for threads

**Layer 3 (CLI):**
```bash
monitor copilot threads --story <UUID>
monitor copilot threads --story <UUID> --critical  # High priority only
```

**Thread Categories:**
```python
class ThreadType(Enum):
    OPEN_QUESTION = "open_question"      # "Who killed the duke?"
    PROMISE = "promise"                   # NPC said they would do X
    HOOK = "hook"                        # Clue planted
    QUEST = "quest"                      # Active objective
    FORESHADOWING = "foreshadowing"      # Setup without payoff
    RELATIONSHIP = "relationship"         # Unresolved NPC tension
```

---

## CF-4: Suggest Plot Hooks

**Actor:** Human GM
**Trigger:** Co-Pilot → Suggest (during prep or session)

**Purpose:** Generate contextually appropriate plot hooks based on world state.

**Flow:**
1. Analyze current context:
   - Active story and recent events
   - Present location and NPCs
   - Unresolved threads (→ CF-3)
   - Character goals and relationships
   - Faction tensions
2. Generate hook suggestions:
   - **Immediate:** Can happen right now
   - **Near-term:** Next session material
   - **Long-term:** Arc-level developments
3. For each hook, provide:
   - Description
   - Involved entities
   - Potential outcomes
   - Connection to existing threads
4. GM selects, modifies, or dismisses
5. Selected hooks optionally saved as plot_thread

**Output:** Contextual plot hook suggestions

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_entities(universe_id, type="faction")   # Active factions
neo4j_get_relationships(entity_id, depth=2)        # NPC networks
neo4j_list_facts(entity_id, type="goal")           # Character motivations
mongodb_get_scene(current_scene_id)                # Current situation
```

**Layer 2 (Agents):**
- `ContextAssembly.get_story_context(story_id)` — Current state
- `Narrator.generate_hooks(context, count=5)` — LLM generation
- `Orchestrator.save_plot_thread(hook)` — If GM accepts

**Layer 3 (CLI):**
```bash
monitor copilot suggest --story <UUID>
monitor copilot suggest --story <UUID> --type combat
monitor copilot suggest --story <UUID> --involving <ENTITY_ID>
```

**Hook Generation Prompt:**
```python
HOOK_PROMPT = """
Given this story context, suggest {count} plot hooks.

Current situation: {scene_summary}
Active factions: {factions}
Unresolved threads: {threads}
Character goals: {character_goals}

For each hook provide:
1. Brief description (1-2 sentences)
2. Why it's relevant now
3. Potential complications
4. Which threads it advances

Genre: {genre}
Tone: {tone}
"""
```

---

## CF-5: Detect Contradictions

**Actor:** Human GM
**Trigger:** Co-Pilot → Validate (manual) or automatic during canonization

**Purpose:** Find and flag contradictory facts introduced accidentally.

**Flow:**
1. Scope selection:
   - Current scene only
   - Current story
   - Entire universe
2. Analyze all canonical facts for conflicts:
   - **Direct contradictions:** "X is dead" vs "X spoke to party"
   - **Timeline violations:** Event B before Event A (but B depends on A)
   - **Location conflicts:** Entity in two places at same time
   - **Relationship conflicts:** "X hates Y" vs "X is Y's ally"
   - **Rule violations:** Actions that break established axioms
3. For each conflict:
   - Show both facts with sources
   - Suggest resolution options:
     - Retcon older fact
     - Retcon newer fact
     - Mark as "apparent contradiction" (mystery)
     - Create explanation fact
4. GM resolves each conflict
5. Update canon accordingly

**Output:** Conflict report with resolution options

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_facts(universe_id)                      # All facts
neo4j_list_events(universe_id)                     # All events
neo4j_get_entity(entity_id)                        # Entity states
neo4j_retcon_fact(fact_id)                         # Apply retcon
neo4j_create_fact(explanation)                     # Add explanation
```

**Layer 2 (Agents):**
- `CanonKeeper.validate_consistency(scope)` — Run validation
- `CanonKeeper.suggest_resolution(conflict)` — Generate options
- `CanonKeeper.apply_resolution(conflict, choice)` — Execute fix

**Layer 3 (CLI):**
```bash
monitor copilot validate --universe <UUID>
monitor copilot validate --story <UUID>
monitor copilot validate --scene <UUID>
```

**Conflict Detection Logic:**
```python
async def detect_contradictions(facts: list[Fact]) -> list[Conflict]:
    conflicts = []

    # 1. State contradictions (same entity, conflicting states)
    for entity_id in unique_entities(facts):
        entity_facts = [f for f in facts if f.subject_id == entity_id]
        conflicts.extend(find_state_conflicts(entity_facts))

    # 2. Timeline contradictions
    events = await neo4j_list_events(universe_id)
    conflicts.extend(validate_timeline(events))

    # 3. Location contradictions
    conflicts.extend(validate_locations(facts, events))

    # 4. Semantic contradictions (LLM-assisted)
    conflicts.extend(await llm_find_contradictions(facts))

    return conflicts
```

**Conflict Schema:**
```python
@dataclass
class Conflict:
    type: ConflictType
    fact_a: Fact
    fact_b: Fact
    description: str
    severity: Severity  # critical, major, minor
    suggested_resolutions: list[Resolution]
```

---

# Epic 7: STORY (Planning & Meta-Narrative)

> As a storyteller, I want to plan and design narratives without forcing outcomes.

This epic supports **EPIC 8 — Planning & Meta-Narrative Tools** from [SYSTEM.md](../SYSTEM.md).

**Core Principle:** Plan the situation, not the plot. Players determine outcomes.

---

## ST-1: Plan Story Arc

**Actor:** Human GM or Autonomous GM
**Trigger:** Story → Plan Arc

**Purpose:** Design multi-session story structure with flexible outcomes.

**Flow:**
1. Define arc parameters:
   - Title and theme
   - Target length (sessions/scenes)
   - Tone and genre
   - Central conflict
2. Identify key elements:
   - **Inciting Incident:** What kicks things off
   - **Rising Actions:** Escalating complications (not fixed sequence)
   - **Crisis Points:** Decision moments for players
   - **Possible Climaxes:** Multiple valid endings
   - **Fallout Options:** Consequences of each ending
3. Assign entities:
   - Protagonist(s)
   - Antagonist(s)
   - Supporting cast
   - Locations
4. Define success/failure conditions (flexible)
5. Create arc document with milestones (not rails)
6. Save as `story_outline` in MongoDB + `PlotThread` nodes in Neo4j

**Output:** Flexible arc structure with branching possibilities

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_story_outline(story_id, arc_params)
neo4j_create_plot_thread(story_id, thread_params)  # For each thread
neo4j_link_entities_to_arc(arc_id, entity_ids)
```

**Layer 2 (Agents):**
- `Orchestrator.plan_arc(story_id, params)` — Coordinate planning
- `Narrator.generate_arc_structure(params)` — LLM arc generation
- `CanonKeeper.validate_arc(arc)` — Check consistency with canon

**Layer 3 (CLI):**
```bash
monitor story plan --story <UUID>
monitor story plan --story <UUID> --template heist
monitor story plan --story <UUID> --template mystery
```

**Arc Templates:**
```python
class ArcTemplate(Enum):
    THREE_ACT = "three_act"           # Classic structure
    HEIST = "heist"                   # Plan, execute, escape
    MYSTERY = "mystery"               # Clues, suspects, revelation
    JOURNEY = "journey"               # Travel with encounters
    SIEGE = "siege"                   # Defense against threat
    POLITICAL = "political"           # Intrigue and alliances
    DUNGEON = "dungeon"               # Exploration and combat
    CUSTOM = "custom"                 # Freeform
```

**Arc Document Structure:**
```python
@dataclass
class StoryArc:
    id: UUID
    story_id: UUID
    title: str
    theme: str
    target_sessions: int

    inciting_incident: str
    rising_actions: list[str]          # Possible complications
    crisis_points: list[CrisisPoint]   # Decision moments
    possible_climaxes: list[Climax]    # Multiple endings

    protagonists: list[UUID]
    antagonists: list[UUID]
    key_locations: list[UUID]

    milestones: list[Milestone]        # Progress markers
    current_phase: str
```

---

## ST-2: Model Faction Goals

**Actor:** Human GM
**Trigger:** Story → Factions

**Purpose:** Define what factions want and how they'll pursue it, creating emergent conflict.

**Flow:**
1. Select or create factions involved in story
2. For each faction, define:
   - **Primary Goal:** What they ultimately want
   - **Secondary Goals:** Stepping stones
   - **Methods:** How they pursue goals (violence, diplomacy, subterfuge)
   - **Resources:** What they can deploy
   - **Constraints:** Lines they won't cross
   - **Relationships:** Allies, enemies, neutral
3. System identifies:
   - **Conflict Points:** Where goals clash
   - **Alliance Opportunities:** Where goals align
   - **Pressure Points:** What threatens each faction
4. Optionally simulate faction actions between sessions
5. Save faction states and update relationships

**Output:** Faction goal map with conflict/alliance analysis

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entity(faction_id)                       # Faction data
neo4j_list_facts(entity_id=faction_id, type="goal")  # Current goals
neo4j_create_fact(faction_id, type="goal", content)  # New goal
neo4j_create_relationship(faction_a, faction_b, type)  # Alliances/enmities
neo4j_update_entity(faction_id, properties)        # Update state
```

**Layer 2 (Agents):**
- `ContextAssembly.get_faction_context(faction_ids)` — Compile faction data
- `Narrator.analyze_faction_dynamics(factions)` — Find conflicts
- `Resolver.simulate_faction_turn(faction, context)` — Off-screen actions

**Layer 3 (CLI):**
```bash
monitor story factions --story <UUID>
monitor story factions --story <UUID> --add <FACTION_ID>
monitor story factions --story <UUID> --simulate
```

**Faction Goal Schema:**
```python
@dataclass
class FactionGoal:
    faction_id: UUID
    goal_type: GoalType  # survival, power, wealth, ideology, revenge, protection
    description: str
    priority: int        # 1-5
    methods: list[str]   # violence, diplomacy, subterfuge, commerce
    deadline: str | None # If time-sensitive

@dataclass
class FactionState:
    faction_id: UUID
    goals: list[FactionGoal]
    resources: dict[str, int]  # gold, soldiers, influence, etc.
    relationships: dict[UUID, RelationType]
    current_actions: list[str]  # What they're doing this "turn"
```

---

## ST-3: Simulate "What If" Scenarios

**Actor:** Human GM
**Trigger:** Story → What If

**Purpose:** Explore hypothetical outcomes without affecting canon.

**Flow:**
1. Define scenario:
   - Starting point (current state or past event)
   - Hypothetical change ("What if the king died?")
2. System creates sandbox copy of relevant state
3. Simulate forward:
   - Faction reactions
   - NPC responses
   - Cascade effects
   - Timeline of consequences
4. Present results:
   - Immediate effects (hours/days)
   - Short-term effects (weeks)
   - Long-term effects (months/years)
5. GM can:
   - Dismiss (just exploration)
   - Adopt as canon (make it happen)
   - Save as alternate timeline
   - Use for planning (incorporate elements)

**Output:** Simulated consequence chain (non-canonical unless adopted)

### Implementation

**Layer 1 (Data Layer):**
```python
# Read-only queries (simulation doesn't write to main DB)
neo4j_get_universe(universe_id)
neo4j_list_entities(universe_id)
neo4j_list_facts(universe_id)
neo4j_list_relationships(entity_ids)

# Only if adopted:
neo4j_create_event(adopted_event)
neo4j_create_fact(consequence)
```

**Layer 2 (Agents):**
- `ContextAssembly.snapshot_state(universe_id)` — Copy current state
- `Narrator.simulate_consequences(change, state, depth)` — LLM simulation
- `CanonKeeper.adopt_simulation(simulation_id)` — Make canonical

**Layer 3 (CLI):**
```bash
monitor story whatif --universe <UUID> --change "The king is assassinated"
monitor story whatif --story <UUID> --change "The party fails the heist"
monitor story whatif --adopt <SIMULATION_ID>  # Make it canon
```

**Simulation Prompt:**
```python
WHATIF_PROMPT = """
Given this world state, simulate the consequences of: {change}

Current state:
- Factions: {factions}
- Key NPCs: {npcs}
- Recent events: {recent_events}
- Active tensions: {tensions}

Simulate:
1. Immediate reactions (hours): Who does what?
2. Short-term effects (days/weeks): How does the situation evolve?
3. Long-term effects (months): What's the new equilibrium?

For each effect, identify:
- Who is affected
- What changes
- What new conflicts emerge
- What opportunities arise
"""
```

**Simulation Result:**
```python
@dataclass
class Simulation:
    id: UUID
    universe_id: UUID
    starting_point: str  # Description or event_id
    hypothetical_change: str

    immediate_effects: list[Effect]   # Hours
    shortterm_effects: list[Effect]   # Days/weeks
    longterm_effects: list[Effect]    # Months/years

    affected_entities: list[UUID]
    new_conflicts: list[str]
    opportunities: list[str]

    status: SimulationStatus  # sandbox, adopted, dismissed
```

---

## ST-4: Design Mystery Structure

**Actor:** Human GM
**Trigger:** Story → Mystery (or during arc planning)

**Purpose:** Create solvable mysteries with multiple valid investigation paths.

**Flow:**
1. Define the mystery:
   - **The Truth:** What actually happened (GM secret)
   - **The Question:** What players are trying to discover
   - **The Stakes:** Why it matters
2. Design clue structure:
   - **Core Clues:** Must-find clues that point to truth
   - **Bonus Clues:** Shortcuts or confirmations
   - **Red Herrings:** Misleading information (optional)
   - **Floating Clues:** Can be found in multiple locations
3. Place clues:
   - Assign to locations, NPCs, objects
   - Define discovery conditions (investigation, social, combat)
   - Ensure multiple paths to each core clue
4. Define suspects/theories:
   - Plausible alternatives
   - Evidence for/against each
5. Track player discoveries during play
6. Validate solvability (three-clue rule: any core clue findable 3 ways)

**Output:** Mystery structure with clue placement

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_story_outline(story_id, mystery_structure)
neo4j_create_fact(clue_fact, visibility="hidden")  # Hidden until found
neo4j_link_evidence(clue_id, location_id)          # Clue placement
neo4j_update_fact(clue_id, visibility="revealed")  # When discovered
```

**Layer 2 (Agents):**
- `Narrator.design_mystery(params)` — Generate structure
- `Narrator.validate_solvability(mystery)` — Check three-clue rule
- `ContextAssembly.track_discoveries(scene_id)` — What players found

**Layer 3 (CLI):**
```bash
monitor story mystery --story <UUID>
monitor story mystery --story <UUID> --validate
monitor story mystery --story <UUID> --status  # What players know
```

**Mystery Structure:**
```python
@dataclass
class Mystery:
    id: UUID
    story_id: UUID

    truth: str                        # What actually happened (GM only)
    question: str                     # What players seek to answer
    stakes: str                       # Why it matters

    core_clues: list[Clue]           # Required for solution
    bonus_clues: list[Clue]          # Helpful but optional
    red_herrings: list[Clue]         # Misleading
    floating_clues: list[Clue]       # Can appear anywhere

    suspects: list[Suspect]          # Alternative theories

    discovered_clues: list[UUID]     # Player progress
    current_theories: list[str]      # What players think

@dataclass
class Clue:
    id: UUID
    content: str                     # What the clue reveals
    locations: list[UUID]            # Where it can be found
    discovery_methods: list[str]     # How to find it (investigate, talk, search)
    points_to: str                   # What conclusion it supports
    is_discovered: bool
```

---

## ST-5: Balance Player Agency

**Actor:** Human GM or Autonomous GM
**Trigger:** Story → Balance (or automatic suggestion)

**Purpose:** Ensure story pressure without railroading.

**Flow:**
1. Analyze current story state:
   - Player goals and stated intentions
   - GM/story goals and direction
   - Divergence between them
2. Identify agency concerns:
   - **Railroading Risk:** Story forcing specific path
   - **Stagnation Risk:** No pressure, no direction
   - **Overwhelm Risk:** Too many options, paralysis
3. Suggest adjustments:
   - **Add Pressure:** Time limits, antagonist actions
   - **Add Options:** New paths, resources, allies
   - **Add Clarity:** Signpost important choices
   - **Reduce Complexity:** Resolve minor threads
4. GM reviews and applies suggestions
5. Update story outline with adjustments

**Output:** Agency analysis with balancing suggestions

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_story_outline(story_id)
mongodb_list_scenes(story_id)
neo4j_list_plot_threads(story_id)
neo4j_list_facts(story_id, type="player_intention")
```

**Layer 2 (Agents):**
- `ContextAssembly.analyze_story_flow(story_id)` — Compile state
- `Narrator.assess_agency(story_state)` — LLM analysis
- `Narrator.suggest_balance(assessment)` — Generate suggestions

**Layer 3 (CLI):**
```bash
monitor story balance --story <UUID>
monitor story balance --story <UUID> --apply <SUGGESTION_ID>
```

**Agency Assessment:**
```python
@dataclass
class AgencyAssessment:
    story_id: UUID

    player_goals: list[str]           # What players want
    story_direction: list[str]        # Where narrative is heading
    alignment_score: float            # 0-1, how aligned

    railroading_risk: Risk            # low, medium, high
    stagnation_risk: Risk
    overwhelm_risk: Risk

    suggestions: list[BalanceSuggestion]

@dataclass
class BalanceSuggestion:
    type: SuggestionType   # add_pressure, add_options, add_clarity, simplify
    description: str
    implementation: str    # How to do it
    affected_threads: list[UUID]
```

**Balancing Prompt:**
```python
BALANCE_PROMPT = """
Analyze this story for player agency balance.

Player stated intentions: {player_goals}
Current story direction: {story_threads}
Recent player choices: {recent_decisions}
Open options: {available_paths}

Assess:
1. Are players being pushed toward a specific outcome? (railroading)
2. Is there enough pressure to drive decisions? (stagnation)
3. Are there too many unresolved threads? (overwhelm)

For each concern, suggest specific adjustments that:
- Preserve player choice
- Maintain story momentum
- Keep complexity manageable
"""
```

---

# Epic 8: RULES (Game System Definition)

> As a user, I want to define and manage RPG rule systems so I can play any game, not just D&D.

This epic supports **Objective O3 — System-Agnostic Rules Handling** from [SYSTEM.md](../SYSTEM.md).

**Core Principle:** The system should not hard-code any single RPG. Rules are data, not code.

---

## RS-1: Define Game System

**Actor:** User
**Trigger:** Manage → Rules → Create System

**Purpose:** Create a reusable game system definition (stats, skills, dice mechanics).

**Flow:**
1. Basic system info:
   - Name (e.g., "D&D 5e", "Fate Core", "Homebrew Fantasy")
   - Description
   - Core mechanic summary ("d20 + modifier vs DC")
2. Define attributes/stats:
   - Name, abbreviation, range (e.g., "Strength", "STR", 1-20)
   - How they're used (modifier = (stat - 10) / 2)
3. Define skills:
   - Name, linked attribute, trained/untrained bonus
   - Categories (combat, social, exploration)
4. Define dice mechanics:
   - Base resolution formula (e.g., "1d20 + skill + modifier")
   - Success thresholds (meet-or-beat, count successes, etc.)
   - Critical success/failure rules
5. Define resource types:
   - HP, Mana, Stress, Fate Points, etc.
   - Max, current, recovery rules
6. Save game system
7. System becomes available for universe/character creation

**Output:** Reusable game system definition

### Implementation

**Layer 1 (Data Layer):**
```python
# Store in MongoDB (complex, document-oriented)
mongodb_create_game_system(params) -> system_id
mongodb_get_game_system(system_id) -> GameSystem
mongodb_list_game_systems() -> list[GameSystemSummary]
mongodb_update_game_system(system_id, params)
mongodb_delete_game_system(system_id)
```

**Layer 2 (Agents):**
- `Orchestrator.create_game_system(params)` — Coordinate creation
- `Resolver.load_game_system(system_id)` — Load for resolution

**Layer 3 (CLI):**
```bash
monitor rules create                             # Interactive wizard
monitor rules create --name "D&D 5e" --template dnd5e
monitor rules list                               # Show all systems
monitor rules view <SYSTEM_ID>                   # View details
monitor rules edit <SYSTEM_ID>                   # Modify system
```

**Game System Schema:**
```python
@dataclass
class GameSystem:
    id: UUID
    name: str
    description: str
    version: str = "1.0"

    # Core resolution mechanic
    core_mechanic: CoreMechanic

    # Attributes (Strength, Dexterity, etc.)
    attributes: list[AttributeDef]

    # Skills (Athletics, Persuasion, etc.)
    skills: list[SkillDef]

    # Resources (HP, Mana, etc.)
    resources: list[ResourceDef]

    # Combat rules
    combat: CombatRules | None

    # Custom dice notation extensions
    custom_dice: dict[str, str] = {}  # {"advantage": "2d20kh1"}

@dataclass
class CoreMechanic:
    type: MechanicType  # d20, dice_pool, percentile, card, narrative
    formula: str        # "1d20 + {skill} + {modifier}"
    success_type: SuccessType  # meet_or_beat, count_successes, highest_wins

    success_threshold: str | None  # "DC" or fixed number
    critical_success: str | None   # "natural 20" or "double threshold"
    critical_failure: str | None   # "natural 1"
    partial_success: str | None    # "within 5 of DC"

@dataclass
class AttributeDef:
    name: str                # "Strength"
    abbreviation: str        # "STR"
    min_value: int = 1
    max_value: int = 20
    default_value: int = 10
    modifier_formula: str | None = "(value - 10) // 2"  # How to derive modifier

@dataclass
class SkillDef:
    name: str                # "Athletics"
    attribute: str           # "STR" - linked attribute
    category: str            # "physical", "mental", "social"
    trained_bonus: int = 0   # Bonus if trained
    description: str = ""

@dataclass
class ResourceDef:
    name: str                # "Hit Points"
    abbreviation: str        # "HP"
    max_formula: str         # "constitution * level + 10"
    recovery_rules: str      # "Long rest: full. Short rest: spend hit dice."
    depleted_effect: str     # "At 0: unconscious. Below 0: death saves."
```

---

## RS-2: Import Game System

**Actor:** User
**Trigger:** Manage → Rules → Import

**Purpose:** Import a game system from SRD, JSON, or community format.

**Flow:**
1. Select import source:
   - **Built-in template:** D&D 5e SRD, Fate Core, PbtA, OSR
   - **JSON file:** Custom export format
   - **URL:** Community repository
2. Preview imported system:
   - Show attributes, skills, mechanics
   - Highlight any conflicts with existing systems
3. Customize before saving:
   - Rename, adjust values, remove unwanted elements
4. Save as new game system
5. Optionally mark as "official" or "homebrew"

**Output:** Imported game system ready for use

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_import_game_system(source, format) -> GameSystem
mongodb_validate_game_system(system) -> ValidationResult
```

**Layer 2 (Agents):**
- `Indexer.parse_game_system(file_path, format)` — Parse import file
- `Orchestrator.preview_import(parsed)` — Show preview

**Layer 3 (CLI):**
```bash
monitor rules import --template dnd5e              # Built-in template
monitor rules import --file ./my-system.json       # From file
monitor rules import --url https://example.com/system.json
```

**Built-in Templates:**
```python
class BuiltinTemplate(Enum):
    DND_5E_SRD = "dnd5e"           # D&D 5th Edition SRD
    DND_3_5_SRD = "dnd35"          # D&D 3.5 SRD
    PATHFINDER_1E = "pf1e"         # Pathfinder 1e
    PATHFINDER_2E = "pf2e"         # Pathfinder 2e
    FATE_CORE = "fate"             # Fate Core
    FATE_ACCELERATED = "fae"       # Fate Accelerated
    PBTA_BASIC = "pbta"            # Powered by the Apocalypse
    BLADES_ITD = "bitd"            # Blades in the Dark
    OSR_BASIC = "osr"              # Basic OSR (B/X style)
    CYPHER = "cypher"              # Cypher System
    SAVAGE_WORLDS = "sw"           # Savage Worlds
    SIMPLE_D6 = "simple"           # Minimal d6 system (default)
```

**Import Format (JSON):**
```json
{
  "name": "My Custom System",
  "version": "1.0",
  "core_mechanic": {
    "type": "d20",
    "formula": "1d20 + {skill} + {modifier}",
    "success_type": "meet_or_beat"
  },
  "attributes": [
    {"name": "Might", "abbreviation": "MGT", "max_value": 10}
  ],
  "skills": [
    {"name": "Fighting", "attribute": "MGT", "category": "combat"}
  ],
  "resources": [
    {"name": "Health", "abbreviation": "HP", "max_formula": "might * 5"}
  ]
}
```

---

## RS-3: Define Character Template

**Actor:** User
**Trigger:** Manage → Rules → Character Template (within a game system)

**Purpose:** Define what a character sheet looks like for this game system.

**Flow:**
1. Select game system
2. Define character sheet sections:
   - **Core:** Name, description, portrait
   - **Attributes:** Which from system, starting values
   - **Skills:** Which are available, how many trained
   - **Resources:** HP, mana, etc.
   - **Inventory:** Slots, encumbrance rules
   - **Special:** Classes, feats, spells, moves (system-specific)
3. Define character creation rules:
   - Point buy vs rolled stats
   - Starting equipment
   - Background/origin options
4. Define advancement:
   - XP thresholds or milestone
   - What improves per level (HP, skills, features)
5. Save template to game system

**Output:** Character template attached to game system

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_character_template(system_id, params) -> template_id
mongodb_get_character_template(system_id) -> CharacterTemplate
mongodb_update_character_template(system_id, params)
```

**Layer 2 (Agents):**
- `Orchestrator.create_character_template(system_id, params)` — Create template
- `Orchestrator.apply_template(entity_id, template_id)` — Create character from template

**Layer 3 (CLI):**
```bash
monitor rules template --system <SYSTEM_ID>            # View/edit template
monitor rules template --system <SYSTEM_ID> --wizard   # Interactive setup
```

**Character Template Schema:**
```python
@dataclass
class CharacterTemplate:
    id: UUID
    system_id: UUID

    # What sections appear on sheet
    sections: list[SheetSection]

    # Character creation rules
    creation: CreationRules

    # Advancement rules
    advancement: AdvancementRules

@dataclass
class SheetSection:
    name: str                    # "Attributes", "Skills", "Inventory"
    type: SectionType            # attributes, skills, resources, inventory, custom
    fields: list[FieldDef]       # What fields in this section
    display_order: int

@dataclass
class CreationRules:
    attribute_method: str        # "point_buy", "roll_4d6_drop_lowest", "standard_array"
    starting_attribute_points: int | None
    starting_skills: int         # How many trained skills
    starting_resources: dict[str, str]  # {"HP": "constitution + 10"}
    starting_equipment: list[str] | str  # Fixed list or "choose from class"
    starting_level: int = 1

@dataclass
class AdvancementRules:
    method: str                  # "xp", "milestone", "session"
    xp_thresholds: list[int] | None  # [0, 300, 900, 2700, ...]
    per_level: PerLevelGains

@dataclass
class PerLevelGains:
    hp_formula: str              # "1d10 + constitution_modifier"
    skill_points: int            # Additional skills per level
    features: str                # "Gain 1 feat every 4 levels"
    attribute_points: str        # "+2 to one attribute every 4 levels"
```

---

## RS-4: Override Mechanics (House Rules)

**Actor:** Human GM or User
**Trigger:** During play or Manage → Rules → Overrides

**Purpose:** Apply one-off or persistent rule modifications without changing the base system.

**Flow:**
1. Select scope:
   - **One-time:** Just this roll
   - **Scene:** For current scene only
   - **Story:** For entire story
   - **Universe:** Permanent house rule
2. Define override:
   - **Dice change:** "Roll 2d6 instead of 1d20 for social checks"
   - **Threshold change:** "DC 15 for this lock, not standard"
   - **Resource change:** "Healing potions restore 4d4, not 2d4"
   - **New rule:** "On natural 1, weapon breaks"
3. Apply override
4. Override is logged for transparency
5. Can be reverted or made permanent

**Output:** Active override applied to resolution

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_rule_override(scope, params) -> override_id
mongodb_list_rule_overrides(story_id) -> list[RuleOverride]
mongodb_delete_rule_override(override_id)
neo4j_create_axiom(universe_id, house_rule)  # For permanent rules
```

**Layer 2 (Agents):**
- `Resolver.apply_override(override)` — Use override in resolution
- `Resolver.get_effective_rules(context)` — Merge base + overrides
- `CanonKeeper.promote_override_to_axiom(override_id)` — Make permanent

**Layer 3 (CLI):**
```bash
monitor rules override --story <UUID> "Advantage on all stealth checks in darkness"
monitor rules override --scene <UUID> --temp "DC 20 for this check"
monitor rules override --list --story <UUID>   # Show active overrides
monitor rules override --remove <OVERRIDE_ID>
```

**Rule Override Schema:**
```python
@dataclass
class RuleOverride:
    id: UUID
    scope: OverrideScope          # one_time, scene, story, universe
    scope_id: UUID                # ID of scene/story/universe

    # What's being overridden
    target: OverrideTarget        # dice_formula, threshold, resource, custom
    original: str                 # What the base rule was
    override: str                 # What it's changed to

    reason: str                   # Why this override exists
    created_by: str               # "GM", "Player request", "House rule"
    created_at: datetime

    # Tracking
    times_used: int = 0
    active: bool = True

class OverrideScope(Enum):
    ONE_TIME = "one_time"         # Single use
    SCENE = "scene"               # Current scene
    STORY = "story"               # Entire story
    UNIVERSE = "universe"         # Permanent (becomes axiom)

class OverrideTarget(Enum):
    DICE_FORMULA = "dice"         # Change dice rolled
    THRESHOLD = "threshold"       # Change DC/target number
    RESOURCE = "resource"         # Change HP/damage/etc
    SKILL_CHECK = "skill"         # Change which skill applies
    CUSTOM = "custom"             # Freeform rule
```

**Override Resolution:**
```python
async def resolve_with_overrides(
    action: str,
    base_formula: str,
    context: Context
) -> Resolution:
    # 1. Get base rules from game system
    system = await mongodb_get_game_system(context.system_id)
    rules = system.core_mechanic

    # 2. Get applicable overrides (most specific wins)
    overrides = await mongodb_list_rule_overrides(
        story_id=context.story_id,
        scene_id=context.scene_id,
        active=True
    )

    # 3. Apply overrides in order (universe → story → scene → one_time)
    effective_rules = apply_overrides(rules, overrides)

    # 4. Resolve with effective rules
    result = await roll_dice(effective_rules.formula)

    # 5. Mark one-time overrides as used
    for o in overrides:
        if o.scope == OverrideScope.ONE_TIME:
            await mongodb_delete_rule_override(o.id)

    return result
```

---

# Dice Module Specification

## Notation

```
[count]d[sides][modifiers][keep]

Components:
  count    = number of dice (default 1)
  sides    = die type (4, 6, 8, 10, 12, 20, 100)
  modifier = +N or -N
  keep     = kh[N] (keep highest N) or kl[N] (keep lowest N)
```

## Examples

| Notation | Description |
|----------|-------------|
| `d20` | Roll 1d20 |
| `2d6` | Roll 2d6, sum |
| `1d20+5` | Roll 1d20, add 5 |
| `4d6kh3` | Roll 4d6, keep highest 3 (stat generation) |
| `2d20kh1` | Roll 2d20, keep highest (advantage) |
| `2d20kl1` | Roll 2d20, keep lowest (disadvantage) |
| `1d20adv` | Shorthand for advantage |
| `1d20dis` | Shorthand for disadvantage |
| `8d6` | Roll 8d6 (fireball damage) |
| `1d20+5+2` | Multiple modifiers |

## Implementation

```python
@dataclass
class DiceRoll:
    formula: str
    individual_rolls: list[int]
    kept_rolls: list[int]
    modifier: int
    total: int

def roll_dice(formula: str) -> DiceRoll:
    # 1. Parse formula
    # 2. Roll individual dice
    # 3. Apply keep rules
    # 4. Apply modifiers
    # 5. Return result
```

---

# Epic 9: Documentation (DOC)

> As a maintainer, I want documentation published and governed consistently.

## DOC-1: Publish Docs to Wiki

> Epic: Documentation (DOC)

**Actor:** Maintainer
**Trigger:** Release or documentation update

**Flow:**
1. Sync repo docs to GitHub wiki (flattened structure).
2. Set Home page to `WIKI_HOME`.
3. Validate navigation and key links.
4. Include AI setup and contributing guides.

**Output:** Updated wiki with working navigation.

**Implementation**
- Script: `scripts/sync_docs_to_wiki.sh`
- Optional CI: scheduled doc sync or manual run.

---

# Use Case Summary

## By Epic

| Epic | Use Cases | Priority |
|------|-----------|----------|
| DATA LAYER | DL-1 to DL-14 | Phase 0 (Foundational) |
| PLAY | P-1 to P-12 | Phase 1 (MVP) |
| MANAGE | M-1 to M-29 | Phase 1-2 |
| QUERY | Q-1 to Q-9 | Phase 2 |
| INGEST | I-1 to I-6 | Phase 3 |
| SYSTEM | SYS-1 to SYS-10 | Phase 1 |
| DOCS | DOC-1 | Phase 1 |

## MVP (Phase 1)

Core gameplay loop:
- SYS-1, SYS-2, SYS-3 (app lifecycle)
- M-4, M-5 (create/list universe)
- P-1, P-2, P-3, P-4, P-8 (story, scene, turn, action, canonize)
- P-9 (dice rolls)
- M-12, M-13 (create entities, characters)

## Phase 0

Data layer foundation:
- DL-1 to DL-14 (all data access MCP tools, auth/validation, indices)
- Tasks:
  - Create Pydantic schemas for all DL objects (universes, entities, axioms, facts/events, relationships/state tags, stories/scenes/turns, proposed changes, story outlines/plot threads, memories, sources/documents/snippets/ingest proposals, binaries, embeddings, search docs).
  - Implement DB clients (Neo4j, MongoDB, Qdrant, MinIO, OpenSearch) and health checks.
  - Implement MCP tools for each DL use case with auth/validation middleware.
  - Docker/dev setup: ensure infra/docker-compose is runnable; add sample .env for services.
  - Provide template/parent files agents can copy (one schema/tool pattern per store) to accelerate implementation.
  - Data-layer perspectives are detailed in `docs/DATA_LAYER_USE_CASES.md`.

## Phase 2

Management and query:
- M-* (all entity CRUD)
- Q-1 to Q-9 (search and exploration)
- P-10, P-11 (combat, conversation modes)

## Phase 3

Ingestion:
- I-1 to I-6 (full ingestion pipeline)

## Phase 4

Polish:
- Q-8, Q-9 (compare, keyword search)
- SYS-7, SYS-8, SYS-9, SYS-10 (export/import, backup verify, retention)
- Advanced gameplay features

---

# Layer Mapping

| Use Case | CLI (L3) | Agents (L2) | Data (L1) |
|----------|----------|-------------|-----------|
| P-3 Turn | repl/session | Orchestrator, Narrator, Resolver | all tools |
| P-4 Action | handlers | Resolver | mongodb, neo4j |
| P-8 Canonize | handlers | CanonKeeper, Indexer | neo4j, qdrant |
| P-9 Dice | handlers | Resolver | - |
| M-4 Create Universe | commands/manage | - | neo4j_tools |
| M-13 Create Character | commands/manage | - | neo4j, mongodb |
| Q-1 Search | commands/query | ContextAssembly | qdrant, neo4j |
| I-1 Upload | commands/ingest | Indexer | minio, mongodb, qdrant |

---

# References

- **Architecture:** `ARCHITECTURE.md`
- **Data Model:** `docs/ontology/ONTOLOGY.md`
- **Agents:** `docs/architecture/AGENT_ORCHESTRATION.md`
- **Loops:** `docs/architecture/CONVERSATIONAL_LOOPS.md`
- **Implementation:** `packages/*/IMPLEMENTATION.md`
