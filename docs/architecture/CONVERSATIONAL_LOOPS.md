# MONITOR Conversational Loops

*State machines for narrative interaction: how scenes, turns, and stories flow.*

---

## Core Principle

MONITOR operates through **nested loops** at different timescales:

0. **Main Loop** (session) - What do you want to do?
1. **Story Loop** (campaign) - Campaign/arc lifecycle
2. **Scene Loop** (interactive) - Interactive narrative unit
3. **Turn Loop** (exchange) - Individual user/GM exchanges

Each loop is a **state machine** with clear:
- Entry conditions
- State transitions
- Exit conditions
- Canonization checkpoints

---

## The Four Loops

### 0. Main Loop (Session/Menu)

**Timescale:** Continuous (user session)
**Purpose:** Session management and mode selection
**Canonization:** None (delegated to Story/Scene loops)

This is the **outermost loop** - the user's entry point to MONITOR.

```
Main States:
┌──────────────┐
│     Idle     │ ← Waiting for user intent
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Executing  │ ← Running selected mode
└──────┬───────┘
       │
       ▼
┌──────────────┐
│     Idle     │ ← Return to menu
└──────────────┘
```

**Main Loop Flow:**

```
START (User Session)
  │
  ├─→ Display Available Actions
  │     - Start new story
  │     - Continue existing story
  │     - Manage universe (view/edit entities)
  │     - Manage characters
  │     - Ingest documents (upload PDF/manual)
  │     - Query/retrieve (ask about canon)
  │     - System admin (backups, etc.)
  │
  ├─→ User Selects Mode
  │     ↓
  │   Decision Tree:
  │
  ├─→ MODE: Start New Story
  │     ├─→ Universe exists? If not → Ingest/Create flow
  │     ├─→ Create PC? If needed → Character creation
  │     ├─→ Define story outline
  │     └─→ [STORY LOOP] ◄─── runs until story complete
  │           ↓
  │         Return to Main Loop
  │
  ├─→ MODE: Continue Story
  │     ├─→ Load existing Story from Neo4j
  │     ├─→ Load last scene from MongoDB
  │     └─→ [STORY LOOP or SCENE LOOP] ◄─── resume
  │           ↓
  │         Return to Main Loop
  │
  ├─→ MODE: Ingest Documents
  │     ├─→ Upload PDF → MinIO
  │     ├─→ Extract + chunk → MongoDB
  │     ├─→ Embed → Qdrant
  │     ├─→ Propose universe/axioms → MongoDB
  │     ├─→ User review → accept/reject
  │     └─→ Canonize accepted → Neo4j
  │           ↓
  │         Return to Main Loop
  │
  ├─→ MODE: Query/Retrieve
  │     ├─→ User question
  │     ├─→ Query Neo4j (canonical facts)
  │     ├─→ Query Qdrant (semantic recall)
  │     ├─→ Query MongoDB (narrative details)
  │     └─→ Present results
  │           ↓
  │         Return to Main Loop
  │
  ├─→ MODE: Manage Universe
  │     ├─→ List entities/facts
  │     ├─→ Edit/create entities (manual)
  │     ├─→ View timeline
  │     └─→ Export/visualize
  │           ↓
  │         Return to Main Loop
  │
  ├─→ MODE: Manage Characters
  │     ├─→ List PCs/NPCs
  │     ├─→ Create new character
  │     ├─→ Edit character (stats/memories)
  │     └─→ View character history
  │           ↓
  │         Return to Main Loop
  │
  ├─→ User exits session
  │
END (Session closes)
```

**Main Loop States:**

| State | Description | Available Actions |
|-------|-------------|------------------|
| Idle | Waiting for user command | Start story, continue, ingest, query, manage, exit |
| Executing | Running selected mode | (mode-specific) |
| Suspended | Story paused mid-scene | Resume, abandon, save checkpoint |

**Data Persistence:**

When user exits mid-story:
- MongoDB: scene.status = "active" (preserved)
- MongoDB: turns preserved
- MongoDB: proposals = "pending" (preserved)
- Neo4j: last canonized state (consistent)

On resume:
- Load scene state from MongoDB
- Continue Scene Loop from last turn

**Critical Invariant:** Main Loop does NOT write canon. It delegates to Story/Scene loops.

---

### 1. Story Loop (Campaign)

**Timescale:** Days to months
**Purpose:** Campaign/arc continuity
**Canonization:** Story endpoints and major beats
**Parent:** Main Loop (launched from "Start/Continue Story" modes)

```
Story States:
┌─────────────┐
│   Created   │ ← Story defined, universe linked
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Active    │ ← Scenes running
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Completed  │ ← Final facts canonized
└─────────────┘
```

**Story Loop Flow:**

```
START
  │
  ├─→ Define Story (universe, theme, constraints)
  │     ↓
  │   MongoDB: story_outline
  │   Neo4j: Story node (canonical container)
  │
  ├─→ Create Initial Scene
  │     ↓
  │   MongoDB: scene (status=active)
  │   Neo4j: Scene node (optional, for ordering)
  │
  ├─→ [SCENE LOOP] ◄──────┐
  │     ↓                  │
  │   Scene ends           │
  │     ↓                  │
  │   Decision: Continue?  │
  │     ├─ Yes → Create next scene ─┘
  │     └─ No  ↓
  │
  ├─→ Finalize Story
  │     ↓
  │   MongoDB: story recap
  │   Neo4j: Story.status = "completed"
  │   Neo4j: final canonical facts/timeline
  │
END
```

**Data Written:**

| Phase | MongoDB | Neo4j | Qdrant |
|-------|---------|-------|--------|
| Start | story_outline | Story node | - |
| Active | scenes, notes | Scene nodes (optional) | - |
| End | recap | final facts, timeline closure | story summary |

---

### 2. Scene Loop (Interactive)

**Timescale:** Minutes to hours
**Purpose:** Interactive narrative unit with canonization boundary
**Canonization:** End of scene (batch commit)
**Parent:** Story Loop (nested within active story)

This is the **core interactive loop** where users engage with the narrative.

```
Scene States:
┌──────────────┐
│   Created    │ ← Context loaded
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Active    │ ← Turn loop running
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Finalizing  │ ← Canonization gate
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Completed   │ ← Canon written
└──────────────┘
```

**Scene Loop Flow (Detailed):**

```
S1: LOAD CONTEXT
  ├─→ Query Neo4j
  │     - Scene-linked entities + relations
  │     - Active facts/conditions (time_ref)
  │     - Location/setting state
  │
  ├─→ Query MongoDB
  │     - Previous turns in this scene
  │     - Character memories for participants
  │     - GM notes/constraints
  │
  ├─→ Query Qdrant (optional)
  │     - Similar past scenes
  │     - Relevant rule excerpts
  │     - Character memory recall
  │
  └─→ OUTPUT: Context package (IDs + texts)

    ↓

S2: USER ACTION / INPUT
  ├─→ Write MongoDB
  │     - Append Turn to scene_turns
  │     - speaker, text, timestamp
  │
  └─→ State: waiting for resolution

    ↓

S3: RESOLVE OUTCOME
  ├─→ Rules-based OR narrative randomizer
  │     - Success/partial/fail + effects
  │
  ├─→ Write MongoDB
  │     - ProposedChange records
  │     - Resolution record (if dice/rules)
  │     - Evidence citations
  │
  └─→ Proposals are STAGED, not canonical yet

    ↓

S4: CANONIZATION GATE (optional mid-scene)
  │
  ├─→ IF critical event OR explicit commit:
  │     ├─→ Evaluate proposals
  │     ├─→ Write Neo4j (accepted facts)
  │     ├─→ Mark proposals accepted/rejected
  │     └─→ Continue scene
  │
  └─→ ELSE: defer to scene end

    ↓

S5: PERSIST NARRATIVE
  ├─→ Write MongoDB
  │     - GM turn text (response)
  │     - Updated scene state
  │
  └─→ Write Qdrant
        - Embed new turn chunk
        - Update scene summary vector

    ↓

S6: CONTINUE OR END SCENE
  │
  ├─→ IF scene goals unmet: LOOP to S2
  │
  └─→ IF scene complete: FINALIZE

    ↓

FINALIZE (Canonization Checkpoint)
  ├─→ Review ALL proposed_changes
  │     - Accept/reject by policy
  │     - Batch canonical deltas
  │
  ├─→ Write Neo4j
  │     - Facts/Events (time_ref, participants)
  │     - Relations (state changes)
  │     - SUPPORTED_BY edges (→ Scene, Turns)
  │
  ├─→ Write MongoDB
  │     - Mark scene.status = "completed"
  │     - scene.canonical_outcomes = [fact_ids]
  │     - Final scene summary
  │
  └─→ Write Qdrant
        - Scene summary embedding
        - Key memory entries for participants

END SCENE
```

**Critical Invariants:**

1. **Turns never write to Neo4j directly**
   - Turns are narrative artifacts (MongoDB only)
   - Only canonization writes to graph

2. **Scene is atomic canonization unit**
   - Primary: batch commit at scene end
   - Optional: mid-scene checkpoints for critical events

3. **Proposals are explicit**
   - ProposedChange records are structured, not free text
   - Each has evidence pointers
   - Each has status (pending/accepted/rejected)

---

### 3. Turn Loop (Exchange)

**Timescale:** Seconds
**Purpose:** Individual user/GM exchange
**Canonization:** None (deferred to Scene)
**Parent:** Scene Loop (embedded in steps S2-S5)

The Turn Loop is the innermost loop, embedded inside the Scene Loop.

```
TURN FLOW:

User Input
  ↓
Parse Intent
  ↓
Retrieve Context (if needed)
  ↓
Generate Response
  ↓
Extract Proposals (if any)
  ↓
Persist Turn (MongoDB)
  ↓
Continue Scene
```

**Turn as Data:**

Turns are **append-only narrative logs**.

They do NOT:
- Modify canonical state
- Write to Neo4j
- Make decisions about truth

They MAY:
- Propose canonical changes (staged in MongoDB)
- Trigger mid-scene commit (if critical)
- Reference canonical entities/facts

---

## State Transition Rules

### Scene State Machine

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| Created | Load context | Active | Load Neo4j/MongoDB/Qdrant |
| Active | User turn | Active | Append turn, generate proposals |
| Active | Critical event | Active | Mid-scene canonization |
| Active | Scene goal met | Finalizing | Begin canonization |
| Active | Explicit end | Finalizing | Begin canonization |
| Finalizing | Canon written | Completed | Mark scene done, update indices |

### Turn State Machine

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| - | User input | Processing | Parse, retrieve context |
| Processing | Context loaded | Generating | LLM inference |
| Generating | Response ready | Proposing | Extract canonical deltas |
| Proposing | Proposals staged | Persisted | Write turn + proposals to MongoDB |

---

## Canonization Decision Points

### 1. Mid-Scene Checkpoint (Optional)

**Trigger conditions:**
- Character death
- Major discovery (new entity/location)
- Explicit user/GM "commit" command
- Turn count threshold (e.g., every 50 turns in long scene)

**Process:**
```
IF trigger:
  ├─→ Evaluate pending proposals
  ├─→ Accept high-confidence deltas
  ├─→ Write to Neo4j (Facts + SUPPORTED_BY)
  ├─→ Mark proposals as accepted
  └─→ Continue scene (stay in Active state)
```

### 2. End-of-Scene Canonization (Primary)

**Trigger conditions:**
- Scene goal achieved
- Location transition
- Explicit scene end
- Story beat complete

**Process:**
```
Scene Finalization:
  ├─→ Collect ALL pending proposals
  ├─→ Evaluate by policy (authority + confidence)
  ├─→ Batch write to Neo4j:
  │     - Facts/Events
  │     - Relations (new/updated)
  │     - State tags
  │     - SUPPORTED_BY edges
  │
  ├─→ Update MongoDB:
  │     - scene.status = "completed"
  │     - proposal.status = "accepted"|"rejected"
  │     - scene.canonical_outcomes = [fact_ids]
  │
  └─→ Update Qdrant:
        - Scene summary embedding
        - Character memory entries
```

---

## Loop Coordination

Loops are **nested and sequential** within a session:

```
┌─────────────────────────────────────────────────────┐
│        MAIN LOOP (session/menu)                     │
│                                                     │
│  User selects mode → Execute → Return               │
│                                                     │
│  ┌───────────────────────────────────────────────┐ │
│  │     STORY LOOP (campaign)                     │ │
│  │                                               │ │
│  │  ┌─────────────────────────────────────────┐ │ │
│  │  │   SCENE LOOP (interactive)              │ │ │
│  │  │                                         │ │ │
│  │  │  ┌───────────────────────────────────┐ │ │ │
│  │  │  │  TURN LOOP (exchange)             │ │ │ │
│  │  │  │                                   │ │ │ │
│  │  │  │  User → Resolve → Persist         │ │ │ │
│  │  │  └───────────────────────────────────┘ │ │ │
│  │  │                                         │ │ │
│  │  │  Context → Turns → Canonize (scene end) │ │ │
│  │  └─────────────────────────────────────────┘ │ │
│  │                                               │ │
│  │  Story → Scenes → Story End (canonize)        │ │
│  └───────────────────────────────────────────────┘ │
│                                                     │
│  Ingest | Query | Manage (non-story modes)          │
└─────────────────────────────────────────────────────┘
```

**Key principles:**
- **Main Loop** coordinates all modes (story, ingest, query, manage)
- **Inner loops do NOT canonize** - only Scene end and Story end write to Neo4j
- **Loops are resumable** - exit mid-story, resume from MongoDB state

---

## Data Flow Through Loops

### During Active Scene

```
User Input
  ↓
MongoDB: Turn (append)
  ↓
MongoDB: ProposedChange (stage)
  ↓
[Repeat turns...]
  ↓
Scene Ends
  ↓
Neo4j: Facts/Events (batch write)
  ↓
Qdrant: Embeddings (update)
```

**Critical: Neo4j writes are batched at checkpoints, not per-turn.**

---

## Error Handling & Recovery

### Scene Crash Recovery

**If scene loop crashes mid-scene:**

1. MongoDB has all turns (recoverable)
2. Proposals are staged (recoverable)
3. Neo4j has last checkpoint state (consistent)
4. On restart:
   - Resume scene from last turn
   - Re-evaluate proposals
   - User can choose: continue or finalize now

### Canonization Failure

**If Neo4j write fails during finalization:**

1. MongoDB scene state = "finalizing" (stuck)
2. Proposals remain "pending"
3. Recovery:
   - Retry canonization with same proposals
   - OR mark scene "failed" and manual review
   - Never lose narrative (MongoDB has full log)

### Partial Canonization

**If only some proposals succeed:**

1. Mark accepted proposals (MongoDB)
2. Mark failed proposals with error reason
3. Allow user to:
   - Retry failed proposals
   - Skip and mark rejected
   - Manual override

---

## Loop Performance Budgets

| Loop | Latency Target | Throughput Target | Canonization Cost |
|------|---------------|-------------------|------------------|
| Main | < 100ms (mode switch) | N/A | None (delegates) |
| Story | Hours-days | - | 1 closure write (cheap) |
| Scene | 5-30 min | - | 1 batch write (cheap) |
| Turn | < 2s | 1 turn/2s | None (deferred) |

**Key insights:**
- **Main Loop** is lightweight (just coordination)
- **Scene-level canonization** keeps Neo4j writes low-frequency and high-value
- **Turn latency** is user-facing (must be fast)

---

## Examples

### Example 1: Simple Combat Scene

```
Scene Start → Load Context
  Neo4j: PC stats, enemy stats, location
  MongoDB: No prior turns (new scene)

Turn 1: "I attack the orc"
  MongoDB: Turn (user input)
  Resolve: Roll → success
  MongoDB: ProposedChange (orc takes 8 damage)

Turn 2: "The orc retaliates"
  MongoDB: Turn (GM response)
  Resolve: Roll → partial
  MongoDB: ProposedChange (PC takes 3 damage)

Turn 3: "I finish him"
  MongoDB: Turn (user input)
  Resolve: Roll → success
  MongoDB: ProposedChange (orc dies)

Scene End → Canonization
  Neo4j:
    - Event: "Combat with orc"
    - Fact: "Orc died" (time_ref, participants)
    - State: PC.wounded = true
    - SUPPORTED_BY → Scene, Turns 1-3
  MongoDB:
    - scene.status = "completed"
    - proposals marked "accepted"
  Qdrant:
    - Scene summary: "combat victory, PC wounded"
```

### Example 2: Discovery Scene with Mid-Scene Commit

```
Scene Start → Load Context
  Neo4j: PC, current location
  MongoDB: No prior turns

Turn 1-10: Exploration dialogue
  MongoDB: Turns, no proposals

Turn 11: "You find a hidden door"
  MongoDB: Turn + ProposedChange (new location entity)
  TRIGGER: Critical discovery → mid-scene commit

Mid-Scene Canonization:
  Neo4j:
    - Entity: HiddenChamber
    - Relation: Location→HiddenChamber
    - SUPPORTED_BY → Turn 11
  MongoDB:
    - proposal.status = "accepted"
  Scene continues (status still "active")

Turn 12-20: Explore chamber
  MongoDB: Turns

Scene End → Final Canonization
  Neo4j:
    - Facts from turns 12-20
    - PC.location = HiddenChamber
    - SUPPORTED_BY → Scene, Turns 12-20
```

---

## Next Steps

To implement these loops, we need:

1. **Loop Controllers** (agent orchestration)
   - See [AGENT_ORCHESTRATION.md](AGENT_ORCHESTRATION.md)
   - Who runs each loop
   - How loops coordinate

2. **State Validators**
   - Ensure transitions are legal
   - Detect stuck states
   - Recovery procedures

3. **Canonization Policies** (detailed)
   - Authority resolution
   - Confidence thresholds
   - Conflict resolution

4. **Performance Monitoring**
   - Loop cycle times
   - Canonization batch sizes
   - Error rates

---

## References

- [DATABASE_INTEGRATION.md](DATABASE_INTEGRATION.md) - Data layer and canonization rules
- [AGENT_ORCHESTRATION.md](AGENT_ORCHESTRATION.md) - Who runs these loops
- [ONTOLOGY.md](../ontology/ONTOLOGY.md) - Canonical data model
