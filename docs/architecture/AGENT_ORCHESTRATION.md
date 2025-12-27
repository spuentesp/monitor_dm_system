# MONITOR Agent Orchestration

*Multi-agent coordination for narrative intelligence: roles, responsibilities, and communication patterns.*

---

## Core Principle

MONITOR is **not a monolithic AI**.

It is a **coordinated system of specialized agents**, each with:
- Clear responsibilities
- Bounded authority
- Explicit communication protocols
- Access to shared memory systems

**There is no "one agent does everything."** Complexity is distributed.

---

## Agent Design Philosophy

### 1. Specialization over Generalization

Each agent is expert in **one thing**:
- Context assembly
- Narrative generation
- Rules resolution
- Continuity checking
- Memory management

**Anti-pattern:** "Universal GM agent that does everything"

### 2. Stateless Agents, Stateful Data

Agents are **computation units**.

State lives in the databases:
- Neo4j (canonical truth)
- MongoDB (narrative + proposals)
- Qdrant (semantic index)

Agents can be restarted, replaced, or scaled without data loss.

### 3. Explicit Communication

Agents communicate via:
- **Shared data stores** (primary)
- **Message passing** (coordination)
- **Event bus** (optional, for loose coupling)

No "hidden" agent-to-agent calls. All coordination is observable.

### 4. Authority Boundaries

Each agent has explicit **write authority**:
- What it can read
- What it can propose
- What it can canonize

**The canonization gate is the only place authority is enforced.**

---

## The Agent Roster

MONITOR uses **7 core agent types**:

```
┌──────────────────────────────────────────────────────┐
│                  User Interface                      │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│           Orchestrator (Loop Controller)             │
│  - Manages Story/Scene/Turn loops                    │
│  - Coordinates agent calls                           │
│  - Enforces state transitions                        │
└───┬──────┬──────┬──────┬──────┬──────┬─────────────┘
    │      │      │      │      │      │
    ▼      ▼      ▼      ▼      ▼      ▼
┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐
│Context ││Narrator││Resolver││ Canon  ││Memory  ││Indexer │
│Assembly││        ││        ││Keeper  ││Manager ││        │
└────────┘└────────┘└────────┘└────────┘└────────┘└────────┘
    │         │         │         │         │         │
    └─────────┴─────────┴─────────┴─────────┴─────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │   Memory Systems (5 stores)   │
        │  Neo4j │ MongoDB │ Qdrant     │
        │  OpenSearch │ MinIO           │
        └───────────────────────────────┘
```

---

## Agent Specifications

### 1. Orchestrator (Loop Controller)

**Responsibility:** Manage conversational loops and state transitions

**Authority:**
- Read: all databases (for state inspection)
- Write: MongoDB (loop state only)
- Limited Neo4j: **CreateStory only** (story container setup)
- Canonize: no (delegates to CanonKeeper)

**What it does:**
- Runs Main/Story/Scene/Turn loops
- Manages session modes (start story, continue, ingest, query, manage)
- Enforces state machine transitions
- Coordinates agent calls in correct order
- Detects stuck states and recovery
- Triggers canonization checkpoints

**What it does NOT do:**
- Generate narrative content
- Make canon decisions
- Resolve rules/dice
- Assemble context

**Communication:**
```
Orchestrator receives:
  - User input (from UI)
  - Scene state changes (from MongoDB)
  - Agent completion signals

Orchestrator sends:
  - Context assembly requests → ContextAssembly
  - Narrative generation requests → Narrator
  - Resolution requests → Resolver
  - Canonization requests → CanonKeeper
  - Memory updates → MemoryManager
```

**Example orchestration (Main Loop):**
```python
def run_main_loop():
    while True:
        mode = display_menu_and_get_choice()

        if mode == "start_story":
            # Check prerequisites
            universe_id = ensure_universe_exists()
            pc_id = ensure_pc_exists()

            # Create story
            story_id = create_story(universe_id, pc_id)

            # Launch Story Loop
            run_story_loop(story_id)

        elif mode == "continue_story":
            story_id = select_story()
            run_story_loop(story_id)

        elif mode == "ingest":
            run_ingest_pipeline()

        elif mode == "query":
            run_query_mode()

        elif mode == "manage":
            run_management_console()

        elif mode == "exit":
            break
```

**Example orchestration (Scene Loop):**
```python
def run_scene_loop(scene_id):
    # S1: Load context
    context = ContextAssembly.load(scene_id)

    while scene.status == "active":
        # S2: User action
        user_input = await_user_input()
        Turn.append(scene_id, user_input)

        # S3: Resolve outcome
        resolution = Resolver.resolve(user_input, context)
        proposals = extract_proposals(resolution)
        ProposedChange.save_batch(proposals)

        # S4: Check mid-scene commit
        if is_critical(proposals):
            CanonKeeper.commit_mid_scene(scene_id, proposals)

        # S5: Persist narrative
        gm_response = Narrator.generate(context, resolution)
        Turn.append(scene_id, gm_response)
        Indexer.embed_turn(gm_response)

        # S6: Continue or end?
        if scene_goal_met(context):
            scene.status = "finalizing"
            break

    # Finalize: canonization
    CanonKeeper.finalize_scene(scene_id)
```

---

### 2. ContextAssembly Agent

**Responsibility:** Retrieve and package relevant context for narrative generation

**Authority:**
- Read: all databases
- Write: none (read-only agent)
- Canonize: no

**What it does:**
- Query Neo4j for canonical state (entities, facts, relations)
- Query MongoDB for narrative context (prior turns, memories)
- Query Qdrant for semantic recall (similar scenes, memories)
- Compose context package with IDs + texts
- Apply filtering by universe/story/scene scope

**What it does NOT do:**
- Generate narrative
- Decide what's relevant (uses heuristics/retrieval)
- Modify data

**Context Package Structure:**
```javascript
{
  canonical: {
    entities: [Entity],       // from Neo4j
    facts: [Fact],            // from Neo4j
    relations: [Relation]     // from Neo4j
  },
  narrative: {
    prior_turns: [Turn],      // from MongoDB
    scene_summary: "...",     // from MongoDB
    gm_notes: "..."           // from MongoDB
  },
  recalled: {
    similar_scenes: [Scene],  // from Qdrant
    character_memories: [Memory],  // from Qdrant → MongoDB
    rule_excerpts: [Snippet]  // from Qdrant → MongoDB
  },
  metadata: {
    universe_id: "...",
    story_id: "...",
    scene_id: "...",
    timestamp: "..."
  }
}
```

**Retrieval strategies:**
- **Canonical:** Graph traversal from scene entities (1-2 hops)
- **Narrative:** Temporal window (last N turns, last M scenes)
- **Recalled:** Vector similarity (top-K with metadata filters)

---

### 3. Narrator Agent

**Responsibility:** Generate narrative content (GM responses, descriptions)

**Authority:**
- Read: context package (provided by ContextAssembly)
- Write: MongoDB (turn text only)
- Canonize: no

**What it does:**
- Generate GM dialogue/responses
- Create scene descriptions
- Narrate NPC actions
- Maintain tone/style consistency
- Extract implicit proposals (optional)

**What it does NOT do:**
- Decide canonical truth
- Resolve rules/dice
- Modify graph state
- Assemble context (receives it)

**Input:**
- Context package (from ContextAssembly)
- User action (from Turn)
- Resolution outcome (from Resolver, if applicable)

**Output:**
- Narrative text (GM turn)
- Optional: ProposedChanges (extracted from narrative)

**Example:**
```python
def generate(context, user_action, resolution):
    prompt = compose_prompt(
        canonical=context.canonical,
        narrative=context.narrative,
        user_action=user_action,
        resolution=resolution
    )

    response = llm.generate(prompt)

    # Optional: extract proposals from narrative
    proposals = extract_canonical_deltas(response)

    return {
        "text": response,
        "proposals": proposals
    }
```

---

### 4. Resolver Agent

**Responsibility:** Resolve rules, dice, randomization for outcomes

**Authority:**
- Read: rule system (MongoDB), context
- Write: MongoDB (resolution records, proposals)
- Canonize: no (proposes outcomes)

**What it does:**
- Apply game rules (if rules-based)
- Roll dice / randomize outcomes
- Determine success/failure/partial
- Generate structured outcome (not narrative)
- Create evidence-linked proposals

**What it does NOT do:**
- Generate narrative text (that's Narrator)
- Decide canonical truth (that's CanonKeeper)
- Modify graph directly

**Input:**
- User action (intent)
- Context (character stats, environmental factors)
- Rule system schema

**Output:**
- Resolution record (success/fail, rolls, mechanics)
- ProposedChanges (structured deltas)

**Example:**
```python
def resolve_action(action, context, rules):
    # Interpret action
    intent = parse_intent(action)  # e.g., "attack orc"

    # Apply rules
    if rules.type == "dice":
        roll = dice.roll(rules.formula)
        success = roll >= rules.difficulty
    elif rules.type == "narrative":
        success = randomizer.choose(["success", "partial", "fail"])

    # Generate outcome structure
    outcome = {
        "action": intent,
        "success": success,
        "mechanics": {"roll": roll, "target": rules.difficulty},
        "effects": determine_effects(intent, success)
    }

    # Create proposals
    proposals = []
    for effect in outcome.effects:
        proposals.append(ProposedChange(
            type="state_change",
            content=effect,
            evidence=[f"roll:{roll}", f"action:{intent}"]
        ))

    return outcome, proposals
```

---

### 5. CanonKeeper Agent

**Responsibility:** Enforce canonization policy and write to Neo4j

**Authority:**
- Read: all databases
- Write: **Neo4j (only agent with Neo4j write access)**
- Write: MongoDB (proposal status updates)
- Canonize: **yes (exclusive authority)**

**What it does:**
- Evaluate ProposedChanges by policy
- Accept/reject proposals (authority + confidence checks)
- Batch write to Neo4j (Facts, Relations, State)
- Create SUPPORTED_BY provenance edges
- Detect contradictions
- Enforce temporal consistency
- Handle retcons

**What it does NOT do:**
- Generate proposals (receives them)
- Generate narrative
- Resolve actions

**Canonization Policy Evaluation:**
```python
def evaluate_proposal(proposal):
    # Check authority
    if proposal.authority == "source":
        confidence = 1.0
    elif proposal.authority == "gm":
        confidence = 1.0
    elif proposal.authority == "player":
        confidence = 0.8  # via resolution
    elif proposal.authority == "system":
        confidence = 0.5  # inferred

    # Check evidence
    if not proposal.evidence:
        confidence *= 0.5  # penalize unsupported

    # Check contradictions
    if contradicts_canon(proposal):
        if proposal.authority == "gm":
            # GM override: allow retcon
            mark_contradicted_facts_retconned()
        else:
            return "rejected", "contradicts canon"

    # Decide
    if confidence >= THRESHOLD:
        return "accepted", confidence
    else:
        return "pending", confidence  # needs review
```

**Canonization execution:**
```python
def finalize_scene(scene_id):
    proposals = ProposedChange.get_pending(scene_id)

    accepted = []
    rejected = []

    for proposal in proposals:
        status, reason = evaluate_proposal(proposal)

        if status == "accepted":
            # Write to Neo4j
            fact = create_fact(proposal)
            neo4j.create(fact)

            # Create evidence edges
            for evidence_id in proposal.evidence:
                neo4j.create_edge(fact, "SUPPORTED_BY", evidence_id)

            accepted.append(proposal.id)
        else:
            rejected.append((proposal.id, reason))

    # Update MongoDB
    ProposedChange.mark_accepted(accepted)
    ProposedChange.mark_rejected(rejected)

    # Update scene
    Scene.update(scene_id, {
        "status": "completed",
        "canonical_outcomes": [f.id for f in accepted]
    })
```

---

### 6. MemoryManager Agent

**Responsibility:** Manage character memories and subjective recall

**Authority:**
- Read: all databases
- Write: MongoDB (character_memory)
- Write: Qdrant (memory embeddings)
- Canonize: no

**What it does:**
- Create/update character memory entries
- Link memories to canonical facts (optional)
- Manage memory decay/importance
- Retrieve memories for context
- Distinguish objective (Neo4j) vs subjective (MongoDB)

**What it does NOT do:**
- Modify canonical state
- Generate narrative
- Resolve actions

**Memory Entry Structure:**
```javascript
{
  memory_id: "uuid",
  entity_id: "uuid",  // whose memory
  text: "I remember you saved my life",
  linked_fact_id: "uuid",  // optional: canonical anchor
  emotional_valence: 0.8,  // positive
  importance: 0.9,
  created_at: timestamp,
  last_accessed: timestamp,
  access_count: 5
}
```

**Memory vs Canon:**
- **Canon (Neo4j):** "Entity A saved Entity B at time T"
- **Memory (MongoDB):** "I remember you saved me, I'm grateful"

Memories can contradict canon (misremembering is valid).

---

### 7. Indexer Agent (Background)

**Responsibility:** Keep semantic indices up-to-date

**Authority:**
- Read: MongoDB
- Write: Qdrant, OpenSearch
- Canonize: no

**What it does:**
- Embed new content (turns, scenes, memories)
- Update vector indices (Qdrant)
- Update text indices (OpenSearch)
- Runs asynchronously (background job)
- Handles batch updates

**What it does NOT do:**
- Participate in loops
- Make decisions
- Modify source data

**Triggering:**
- Scene finalization → embed scene summary
- Turn creation → embed turn (optional, batched)
- Memory creation → embed memory
- Document ingestion → embed snippets

---

## Agent Communication Patterns

### 1. Request-Response (Synchronous)

**Used by:** Orchestrator calling other agents

```
Orchestrator → ContextAssembly: "Load context for scene X"
              ← ContextAssembly: context_package

Orchestrator → Narrator: "Generate response for turn Y"
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
Orchestrator reads: MongoDB.turns (to check scene state)
```

**Critical:** Shared state via databases, not hidden agent calls.

---

## Loop Ownership

| Loop | Owner | Delegates To |
|------|-------|-------------|
| Main Loop | Orchestrator | Story Loop, Ingest Pipeline, Query Handler, Management |
| Story Loop | Orchestrator | Scene Loop (recursive) |
| Scene Loop | Orchestrator | ContextAssembly, Narrator, Resolver, CanonKeeper |
| Turn Loop | Orchestrator | Narrator, Resolver |
| Canonization | CanonKeeper | (exclusive authority) |

**Key insights:**
- **Orchestrator** is the only agent that manages loops
- **Main Loop** routes to different system modes
- All other agents are stateless workers

---

## Coordination Example: Full Scene Execution

```
USER: "I attack the orc"
  ↓
[Orchestrator: S2 - User Action]
  ↓
MongoDB: Turn.append(scene_id, user_input)
  ↓
[Orchestrator: S3 - Resolve]
  ↓
Orchestrator → ContextAssembly.load(scene_id)
             ← context_package
  ↓
Orchestrator → Resolver.resolve(user_input, context)
             ← resolution (success, roll=18, orc takes 8 damage)
             ← proposals ([state_change: orc.hp -= 8])
  ↓
MongoDB: ProposedChange.save_batch(proposals)
  ↓
[Orchestrator: S4 - Check mid-scene commit]
  ↓
Orchestrator: is_critical? → No (not death, just damage)
  ↓
[Orchestrator: S5 - Persist Narrative]
  ↓
Orchestrator → Narrator.generate(context, user_input, resolution)
             ← "Your blade strikes true! The orc staggers, wounded."
  ↓
MongoDB: Turn.append(scene_id, gm_response)
  ↓
Event: Turn created → Indexer (background)
  ↓
[Orchestrator: S6 - Continue?]
  ↓
Orchestrator: scene_goal_met? → No
  ↓
[Loop back to S2, wait for next user input]

---

USER: "I finish him"
  ↓
[... same flow ...]
  ↓
Resolver → success, orc dies
         → proposals ([state_change: orc.alive = false])
  ↓
Orchestrator: is_critical? → Yes (death = critical)
  ↓
[Orchestrator: S4 - Mid-Scene Commit]
  ↓
Orchestrator → CanonKeeper.commit_mid_scene(scene_id, [orc death proposal])
             ← accepted, fact_id created
  ↓
Neo4j: Fact(orc died, time_ref, participants)
       Edge: Fact -[:SUPPORTED_BY]→ Turn
  ↓
MongoDB: Proposal.status = "accepted"
  ↓
[Continue scene...]

---

USER: "I search the room"
  ↓
[... more turns ...]
  ↓
Orchestrator: scene_goal_met? → Yes (combat done, loot checked)
  ↓
[Orchestrator: Scene Finalize]
  ↓
Orchestrator → CanonKeeper.finalize_scene(scene_id)
  ↓
CanonKeeper: evaluate remaining proposals
           → accept [PC took 3 damage, searched room]
           → write to Neo4j
           → mark scene completed
  ↓
MongoDB: Scene.status = "completed"
  ↓
Orchestrator → Indexer.embed_scene_summary(scene_id)
  ↓
END SCENE
```

---

## Agent Scaling & Deployment

### Single-Machine Mode

All agents run as **threads/coroutines** in one process:
- Orchestrator = main event loop
- Workers = async functions
- Coordination = function calls + shared DB connections

### Distributed Mode

Agents run as **separate services**:
- Orchestrator = coordinator service
- Workers = microservices (REST or gRPC)
- Coordination = message queue (RabbitMQ, Redis) + shared DBs

**Critical:** Data model stays the same. Only deployment changes.

---

## Agent Failure Handling

| Agent | Failure Impact | Recovery |
|-------|---------------|----------|
| Orchestrator | Loop stops | Restart from last MongoDB state |
| ContextAssembly | No context loaded | Retry or use cached context |
| Narrator | No GM response | Retry with same context |
| Resolver | No outcome | Retry or fallback (narrative mode) |
| CanonKeeper | **Canon not written** | Proposals remain pending, retry on restart |
| MemoryManager | Memories not saved | Non-critical, retry background |
| Indexer | Indices stale | Non-critical, retry background |

**Most critical:** CanonKeeper failure. All other agents can retry safely.

---

## Security & Authority Enforcement

### Write Authority Matrix

| Agent | Neo4j | MongoDB | Qdrant | MinIO |
|-------|-------|---------|--------|-------|
| Orchestrator | ⚠️ Limited (CreateStory only) | ✅ (loop state) | ❌ | ❌ |
| ContextAssembly | ❌ | ❌ | ❌ | ❌ |
| Narrator | ❌ | ✅ (turns) | ❌ | ❌ |
| Resolver | ❌ | ✅ (resolutions, proposals) | ❌ | ❌ |
| **CanonKeeper** | **✅** | ✅ (proposal status) | ❌ | ❌ |
| MemoryManager | ❌ | ✅ (memories) | ✅ | ❌ |
| Indexer | ❌ | ❌ | ✅ | ❌ |

**Enforcement:** Database credentials scoped per agent role.

---

## Next Steps

To implement agent orchestration:

1. **Agent Interfaces** (API contracts)
   - Define function signatures
   - Input/output schemas
   - Error codes

2. **Orchestrator State Machine**
   - Implement loop controllers
   - State transition validation
   - Recovery logic

3. **CanonKeeper Policy Engine**
   - Authority resolution rules
   - Confidence thresholds
   - Contradiction detection

4. **Communication Infrastructure**
   - Synchronous (function calls / REST)
   - Asynchronous (events / message queue)
   - Monitoring & tracing

5. **Testing Strategy**
   - Agent unit tests (isolated)
   - Integration tests (full scene loop)
   - Chaos testing (agent failures)

---

## References

- [CONVERSATIONAL_LOOPS.md](CONVERSATIONAL_LOOPS.md) - Loop state machines
- [DATABASE_INTEGRATION.md](DATABASE_INTEGRATION.md) - Data layer and canonization
- [ONTOLOGY.md](../ontology/ONTOLOGY.md) - Canonical data model
