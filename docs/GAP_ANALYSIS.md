# MONITOR Gap Analysis: Path to Automatic Gamemaster

> Comprehensive review of use cases against the north star vision

---

## Executive Summary

**Current Coverage: ~75%**

The use cases provide solid foundational coverage for world management, narrative containers, and canonization. However, **critical gameplay mechanics are incomplete**, blocking the "Automatic Gamemaster" vision.

### Critical Blockers (Must Fix)

| Gap | Impact | Priority |
|-----|--------|----------|
| No Resolution Mechanics DL | Cannot run turns | P0 |
| No PC Action Agent | Cannot run solo play | P0 |
| No Scene Completion Detection | Cannot auto-progress | P0 |
| Character Sheet Ambiguity | Stats unclear | P1 |
| No NPC Action Loop | Combat broken | P1 |

---

## 1. Vision Alignment Check

### Objectives Coverage

| Objective | Coverage | Assessment |
|-----------|----------|------------|
| **O1: Persistent Worlds** | 95% | Excellent - Neo4j entities, facts, relationships all covered |
| **O2: Playable Experiences** | 60% | **GAP** - Resolution mechanics undefined |
| **O3: System-Agnostic Rules** | 85% | Good - RS-1 to RS-5 cover dice, cards, overrides |
| **O4: Assisted GMing** | 80% | Good - CF-1 to CF-7 cover recording, prep, handouts |
| **O5: World Evolution** | 90% | Good - Change log, snapshots, temporal tracking |

### Mode Coverage

| Mode | Coverage | Assessment |
|------|----------|------------|
| **Solo Play** | 55% | **GAP** - Missing turn resolution, PC agency |
| **World Design** | 95% | Excellent - M-1 to M-35 comprehensive |
| **Assisted GM** | 85% | Good - Some polish needed |
| **Query** | 90% | Good - Q-1 to Q-10 comprehensive |

---

## 2. Data Layer Gaps

### Missing DL Use Cases

#### DL-24: Manage Turn Resolutions (CRITICAL)

**Why it's missing:** The `resolutions` MongoDB collection is defined in ONTOLOGY.md (Section 3.4) but has no corresponding DL use case.

**What ONTOLOGY defines:**
```javascript
Collection: resolutions
- resolution_id, turn_id, scene_id
- action, resolution_type (dice/narrative/deterministic)
- mechanics (formula, roll, target, modifiers)
- success_level (critical_success/success/partial/failure/critical_failure)
- effects[] (type, description, target_id, magnitude)
```

**Required MCP Tools (Data Layer - CRUD only):**
```python
mongodb_create_resolution(turn_id, action, params) -> resolution_id
mongodb_get_resolution(resolution_id) -> Resolution
mongodb_list_resolutions(scene_id) -> list[Resolution]
mongodb_update_resolution(resolution_id, effects?, description?)
```

**Required Agents Layer Utilities (Business Logic):**
```python
# These are NOT MCP tools - they live in agents layer
roll_dice(formula) -> DiceResult
evaluate_success(roll, target, modifiers) -> SuccessLevel
calculate_effects(action, success_level, context) -> list[Effect]
resolve_action(action, character_id, context) -> Resolution  # Orchestration
```

**Impact:** Without this, P-4 (Player Action) and P-9 (Dice Rolls) have no data layer backing.

---

#### DL-25: Manage Combat State (HIGH)

**Why it's needed:** Combat is a core RPG mechanic requiring state tracking beyond basic turns.

**Required Collections:**
```javascript
// combat_encounters
{
  encounter_id: UUID,
  scene_id: UUID,
  status: enum["initiative", "active", "resolved"],

  participants: [
    {
      entity_id: UUID,
      initiative: int,
      initiative_card: string,  // For card-based
      position: {x, y},         // If tactical
      conditions: [string],     // poisoned, stunned, etc.
      resources: {hp: int, ...}
    }
  ],

  round: int,
  current_turn_entity: UUID,
  turn_order: [UUID],

  environment: {
    terrain: string,
    lighting: string,
    hazards: [string]
  }
}
```

**Required MCP Tools (Data Layer - CRUD only):**
```python
mongodb_create_combat(scene_id, participants) -> encounter_id
mongodb_get_combat(encounter_id) -> CombatEncounter
mongodb_update_combat(encounter_id, status?, round?, turn_order?)
mongodb_add_combat_participant(encounter_id, entity_id, ...)
mongodb_update_combat_participant(encounter_id, entity_id, ...)
mongodb_set_combat_outcome(encounter_id, outcome)
```

**Required Agents Layer (Business Logic):**
```python
# Combat flow orchestration lives in agents layer
advance_combat_turn(encounter_id) -> next_entity_id  # Orchestrator
roll_initiative(encounter_id, game_system_id)        # Resolver utility
check_combat_end(encounter_id) -> bool               # Resolver utility
```

---

#### DL-26: Manage Character Stats (CLARIFICATION NEEDED)

**Current ambiguity:** Character stats can be stored in:
- Neo4j `EntityInstance.stats` properties
- MongoDB `character_sheets` collection
- Both (with sync rules)

**Decision required:**
1. **Neo4j as truth:** Stats are properties on EntityInstance. Slower but canonical.
2. **MongoDB as working memory:** Stats cached in character_sheets during scenes. Sync at canonization.
3. **Hybrid:** Neo4j for permanent stats, MongoDB for temporary effects.

**Recommendation:** Option 3 (Hybrid)

**Data Layer MCP Tools (CRUD only):**
```python
# Neo4j: Permanent/base stats (via existing DL-2)
neo4j_get_entity(entity_id) -> Entity  # includes stats
neo4j_update_entity(entity_id, updates)  # CanonKeeper only

# MongoDB: Working state storage (DL-26)
mongodb_create_working_state(entity_id, scene_id, base_stats, resources)
mongodb_get_working_state(entity_id, scene_id) -> WorkingState
mongodb_update_working_state(state_id, current_stats?, resources?)
mongodb_add_temp_effect(state_id, effect)
mongodb_remove_temp_effect(state_id, effect_id)
mongodb_mark_canonized(state_id)
```

**Agents Layer (Business Logic):**
```python
# These are NOT MCP tools - they live in agents layer
init_working_state_from_neo4j(entity_id, scene_id)  # Orchestrator
get_effective_stat(state, stat_name) -> int          # Utility
canonize_working_state(state_id)                     # CanonKeeper
```

---

### Incomplete DL Use Cases

#### DL-7: Memories - Missing Recall Operation

Current DL-7 creates memories but doesn't specify retrieval:

```python
# ADD to DL-7
mongodb_query_memories(
    entity_id: UUID,
    filters: {
        memory_type: str,       # observation, deduction, emotion
        related_to: UUID,       # About what/whom
        time_range: tuple,      # When did it happen
        importance_min: float   # Threshold
    },
    limit: int
) -> list[Memory]

# For LLM context injection
mongodb_get_relevant_memories(
    entity_id: UUID,
    context: str,              # Current situation
    limit: int
) -> list[Memory]              # Semantically relevant
```

---

#### DL-15/16: Parties - Missing Scene-Time Updates

Current DL-15/16 cover creation but not mid-scene state changes:

```python
# ADD to DL-15
neo4j_update_party_status(party_id, new_status)  # traveling → combat
neo4j_update_party_location(party_id, location_id)
neo4j_set_active_pc(party_id, entity_id)

# ADD to DL-16
mongodb_update_party_formation(party_id, formation)
mongodb_split_party(party_id, split_config) -> split_id
mongodb_rejoin_party(split_id)
```

---

#### DL-23: Snapshots - Missing Restore Operation

Current DL-23 captures snapshots but doesn't specify restore.

**Data Layer MCP Tools (CRUD only):**
```python
# DL-23 already provides:
mongodb_create_snapshot(scope, scope_id, name, entities, facts, ...)
mongodb_get_snapshot(snapshot_id)
mongodb_list_snapshots(scope?, scope_id?)
mongodb_delete_snapshot(snapshot_id)
```

**Agents Layer (Restore Orchestration):**
```python
# Restore logic lives in agents layer (CanonKeeper)
async def restore_snapshot(
    snapshot_id: UUID,
    strategy: RestoreStrategy  # full, entities_only, selective
) -> RestoreResult:
    # 1. Begin transaction
    # 2. If full: Delete current state within scope
    # 3. Recreate entities from snapshot (via neo4j_create_entity)
    # 4. Recreate facts from snapshot (via neo4j_create_fact)
    # 5. Recreate relationships from snapshot
    # 6. Invalidate Qdrant indices for affected entities
    # 7. Log restore in change_log (via mongodb_log_change)
    # 8. Commit transaction
```

---

## 3. Loop/Agent Gaps

### Missing Agents for Autonomous Play

The current agent roster (Orchestrator, Narrator, Resolver, CanonKeeper, ContextAssembly, MemoryManager, Indexer) is **insufficient for fully autonomous solo play**.

#### Required: Player Character Agent (PC-Agent)

**Purpose:** Decide what the player character(s) do each turn in autonomous mode.

**Responsibilities:**
- Interpret character personality, goals, and situation
- Generate plausible PC actions
- Respect character knowledge limits (no metagaming)
- Handle party coordination (which PC acts when)

**Integration:**
```
Turn Loop (Autonomous Mode):
  S2: PC-Agent generates action (instead of user input)
      ↓
  S3: Resolver processes action
      ↓
  S4: Narrator generates response
```

**Use Case:** P-15: Autonomous PC Actions
```
Actor: System (PC-Agent)
Trigger: Turn begins in autonomous mode

Flow:
1. Load PC context (stats, personality, goals, situation)
2. Analyze current scene state
3. Generate candidate actions based on personality
4. Select action aligned with character goals
5. Submit to Resolver
6. (Optionally) Allow user override

Output: PC action declaration for turn
```

---

#### Required: Story Planner Agent

**Purpose:** Generate and maintain story structure for coherent campaigns.

**Responsibilities:**
- Generate story outline from premise
- Define story beats and checkpoints
- Create scene specifications
- Track narrative progress
- Detect story completion

**Integration:**
```
Story Loop:
  S1: Story Planner generates outline
      ↓
  S2: Scene Loop (each scene)
      ↓
  S3: Story Planner checks progress against outline
      ↓
  Decision: More scenes needed? → S2
            Story complete? → Finalize
```

**Use Case:** ST-8: Automatic Story Planning
```
Actor: System (Story Planner)
Trigger: New story created (P-1)

Flow:
1. Accept story premise/setup
2. Identify genre, tone, scope
3. Generate story outline:
   - Opening situation
   - Key plot points (3-7)
   - Possible endings
   - Required scenes per act
4. Create first scene specification
5. Track progress through outline

Output: Story outline + initial scene spec
```

---

#### Required: Scene Completion Detector

**Purpose:** Determine when a scene should end naturally.

**Current gap:** Document mentions "scene goal met" but never defines what that means.

**Responsibilities:**
- Evaluate scene objectives against current state
- Detect natural transition points
- Identify forced endings (PC death, TPK, escape)
- Suggest scene wrap-up when appropriate

**Integration with Scene Loop:**
```python
# At end of each turn (S6):
async def check_scene_completion(scene: Scene, context: Context) -> SceneStatus:
    # Check explicit objectives
    if scene.objectives:
        completed = evaluate_objectives(scene.objectives, context)
        if all(completed):
            return SceneStatus.OBJECTIVES_MET

    # Check implicit completion triggers
    triggers = [
        check_location_exit(context),      # Party left scene location
        check_time_passage(context),       # Significant time skip
        check_encounter_resolved(context), # Combat/social resolved
        check_narrative_closure(context),  # LLM-detected natural ending
    ]

    if any(triggers):
        return SceneStatus.NATURAL_END

    return SceneStatus.CONTINUE
```

---

#### Required: NPC Action Loop

**Purpose:** Handle NPC decision-making during encounters.

**Current gap:** Resolver handles "outcomes" but doesn't specify NPC agency.

**Responsibilities:**
- Determine NPC actions based on personality/goals
- Handle enemy tactics in combat
- Manage NPC social responses
- Track NPC state changes

**Integration:**
```
Combat Turn Order:
  PC Turn → PC-Agent (or user) decides
  NPC Turn → NPC-Agent decides based on AI

Social Encounter:
  PC speaks → NPC-Agent responds based on disposition
```

**Should extend:** Resolver agent with NPC decision-making capability

---

### Loop Specification Gaps

#### Scene Loop - Missing Details

**Current specification (from CONVERSATIONAL_LOOPS.md):**
```
S1: Load context
S2: User action
S3: Resolve outcome
S4: Mid-scene checkpoint
S5: Persist narrative
S6: Continue or end
```

**Missing specifications:**

1. **S2 in Autonomous Mode:** Who generates the action?
   - Add: PC-Agent generates if `story.mode == "autonomous"`

2. **S3 Combat Flow:** How do multiple combatants resolve?
   - Add: Initiative order → Round loop → Each combatant's turn

3. **S4 Trigger Conditions:** When is mid-scene commit triggered?
   - Add: `critical_events = ["character_death", "major_revelation", "location_change"]`

4. **S6 End Detection:** How is "end" determined?
   - Add: Scene Completion Detector integration

---

#### Turn Loop - Missing NPC Integration

**Current specification:**
```
User Input → Parse → Retrieve → Resolve → Narrate → Persist
```

**Required for combat/encounters:**
```
PC Action → Resolve PC
  ↓
NPC Reactions (for each NPC):
  → NPC-Agent decision
  → Resolve NPC
  → Narrate NPC action
  ↓
Environment Effects
  ↓
Round Summary
  ↓
Next Round or End Combat
```

---

## 4. Use Case Gaps

### Missing PLAY Use Cases

#### P-15: Autonomous PC Actions
See agent section above.

#### P-16: Combat Encounter Management

**Actor:** System (Orchestrator + Resolver)
**Trigger:** Combat begins (hostile action, ambush, etc.)

**Flow:**
1. Initialize combat encounter (create combat state)
2. Roll/draw initiative for all participants
3. Establish turn order
4. **Round Loop:**
   - For each participant in order:
     - If PC: Get action (user or PC-Agent)
     - If NPC: NPC-Agent decides action
     - Resolve action (Resolver)
     - Apply effects (damage, conditions)
     - Check for defeat/victory
   - Environmental effects
   - Round summary
5. Check combat end conditions
6. Resolve combat outcome
7. Canonize results

**Implementation:**
- Layer 1: DL-25 (Combat State)
- Layer 2: Resolver.combat_round(), NPC-Agent
- Layer 3: Combat REPL mode

---

#### P-17: Social Encounter Management

**Actor:** System (Orchestrator + Narrator)
**Trigger:** Significant NPC interaction begins

**Flow:**
1. Initialize social context (NPC disposition, PC reputation)
2. **Exchange Loop:**
   - PC statement/action
   - NPC reaction (based on personality, goals, relationship)
   - Disposition shift (based on interaction quality)
   - Check for resolution (persuaded, angered, deal made)
3. Social outcome determined
4. Update relationship facts
5. Canonize results

---

### Missing MANAGE Use Cases

#### M-36: Manage NPC Behaviors

**Purpose:** Define how NPCs make decisions during encounters.

**Flow:**
1. Select NPC or archetype
2. Define behavior patterns:
   - Combat tactics (aggressive, defensive, support)
   - Social disposition (friendly, hostile, neutral)
   - Goals and motivations
   - Knowledge and beliefs
3. Define reaction triggers
4. Save behavior profile

---

### Missing DATA LAYER Use Cases

As detailed above:
- DL-24: Manage Turn Resolutions
- DL-25: Manage Combat State
- DL-26: Manage Character Stats (clarification)

---

## 5. Architectural Concerns

### Concern 1: GM Authority vs. Proposal Flow

**Current design:** All changes go through proposals → CanonKeeper commits.

**Problem for autonomous play:** Every turn requires proposal evaluation, creating latency.

**Resolution options:**
1. **Batch more aggressively:** Only commit at scene end (current design, but slow feedback)
2. **Trust Resolver for mechanical changes:** HP changes, position moves don't need proposals
3. **Two-tier authority:**
   - Mechanical changes: Resolver commits directly
   - Narrative changes: Proposal flow

**Recommendation:** Option 3 - Define clear boundary:
```python
DIRECT_COMMIT = ["hp_change", "position_move", "condition_apply", "resource_spend"]
PROPOSAL_REQUIRED = ["fact_create", "relationship_change", "entity_state_change"]
```

---

### Concern 2: Turn Resolution Performance

**Current flow:**
```
Action → Context (Neo4j + MongoDB + Qdrant) → LLM → Proposals → Persist
```

**Latency estimate:** 2-5 seconds per turn (LLM + DB queries)

**For combat (10 participants × 5 rounds = 50 turns):** 100-250 seconds

**Optimization options:**
1. **Cache combat context:** Load once, update incrementally
2. **Parallel resolution:** Resolve non-conflicting actions simultaneously
3. **Batch narration:** Generate round summaries instead of per-action narration
4. **Deterministic fallback:** Use rule tables instead of LLM for simple resolutions

---

### Concern 3: Multi-Character Party Coordination

**Current assumption:** Single PC with clear action declaration.

**Reality:** Parties have 3-6 characters who may:
- Act simultaneously
- Coordinate tactics
- Have conflicting goals
- Split up

**Required specification:**
1. **Turn order in combat:** Initiative determines sequence
2. **Out-of-combat actions:** Sequential (one PC acts, then next) or parallel (all declare, then resolve)?
3. **Party splits:** How does scene loop handle simultaneous separate locations?

**Recommendation:** Add to P-13 (Party Management):
```python
class PartyActionMode(Enum):
    SEQUENTIAL = "sequential"      # One PC at a time (simpler)
    SIMULTANEOUS = "simultaneous"  # All declare, then resolve (more realistic)
    LEADER_ONLY = "leader_only"    # Active PC acts for party (fastest)
```

---

## 6. Recommended Action Plan

### Phase 0: Critical Blockers (Week 1)

1. **Draft DL-24: Turn Resolutions**
   - Define MongoDB schema
   - Define MCP tools
   - Add to DATA_LAYER_USE_CASES.md

2. **Clarify Character Stats (DL-26)**
   - Make decision: Neo4j vs MongoDB vs Hybrid
   - Document in ONTOLOGY.md
   - Update DL-2

3. **Extend P-4: Player Action**
   - Add resolution workflow details
   - Reference DL-24
   - Define mechanical vs narrative outcomes

### Phase 1: Combat Foundation (Week 2)

4. **Draft DL-25: Combat State**
   - Define encounter schema
   - Define combat tools

5. **Draft P-16: Combat Encounter Management**
   - Full combat loop specification
   - Initiative, rounds, turns

6. **Extend Resolver Agent**
   - Add NPC decision-making
   - Add combat resolution

### Phase 2: Autonomous Play (Week 3)

7. **Define PC-Agent specification**
   - Personality-driven action generation
   - Knowledge boundary enforcement

8. **Draft P-15: Autonomous PC Actions**
   - Integration with turn loop

9. **Define Scene Completion Detector**
   - Objective evaluation
   - Natural ending detection

### Phase 3: Story Planning (Week 4)

10. **Define Story Planner Agent**
    - Outline generation
    - Beat tracking

11. **Draft ST-8: Automatic Story Planning**
    - Story structure generation

12. **Update loop specifications**
    - Integrate new agents
    - Document autonomous mode

---

## 7. Summary: What's Blocking "Automatic Gamemaster"

| Capability | Status | Blocking? |
|------------|--------|-----------|
| World persistence | Complete | No |
| Entity management | Complete | No |
| Fact/event tracking | Complete | No |
| Scene/turn containers | Complete | No |
| Canonization flow | Complete | No |
| **Turn resolution mechanics** | **Missing** | **YES** |
| **Combat state management** | **Missing** | **YES** |
| **PC action generation** | **Missing** | **YES** |
| **Scene completion detection** | **Missing** | **YES** |
| **NPC decision-making** | **Incomplete** | **YES** |
| Story planning | Incomplete | Partially |
| Multi-character coordination | Incomplete | Partially |

**Bottom line:** The system can **store and query** a world excellently, but cannot **run** a game autonomously due to missing resolution mechanics and agent specifications.

---

## Appendix: Verification Checklist

### For Each Use Case, Verify:

- [ ] Has corresponding DL use case(s)
- [ ] Has defined agent responsibilities
- [ ] Has defined data flow
- [ ] Has defined CLI command(s)
- [ ] Has defined error handling
- [ ] References related use cases

### For Data Layer, Verify:

- [ ] Every ONTOLOGY collection has DL coverage
- [ ] Every DL has MCP tool definitions
- [ ] CRUD operations complete
- [ ] Query operations complete
- [ ] Authority rules defined

### For Loops, Verify:

- [ ] Entry conditions defined
- [ ] Exit conditions defined
- [ ] Agent assignments clear
- [ ] Data flow documented
- [ ] Error recovery specified
