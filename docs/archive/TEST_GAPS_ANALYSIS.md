# MONITOR Test Specifications - Critical Gap Analysis

> **Review of whether test specifications will guarantee the app works for its IDEAL STATE.**

---

## Executive Summary

**Conclusion:** The current test specifications are **FUNDAMENTALLY INCOMPLETE** and will **NOT** guarantee the app works for its intended use cases.

**Critical Gaps Identified:**
1. **AutoGM Core Features (P-18 to P-21)**: COMPLETELY MISSING - These are core to solo roleplay
2. **Co-Pilot Features (CF-1 to CF-6)**: COMPLETELY MISSING - These are core to GM assistance
3. **End-to-End User Workflows**: MISSING - Tests don't verify complete user experiences
4. **IDEAL STATE Validation**: MISSING - Tests don't verify the app delivers its core objectives

---

## What MONITOR Should Do (IDEAL STATE)

### Mode 1: World Architect

**Objective (O1): Persistent Fictional Worlds**
- Build worlds from documents and structured data
- Extract entities, facts, relationships automatically
- Apply knowledge packs to seed worlds
- World state is consistent and persistent

**What Tests Must Verify:**
1. Document ingestion extracts correct entities, facts, relationships
2. World state remains consistent across sessions
3. Knowledge packs apply correctly without conflicts
4. World evolves over time (O5) - facts persist, entities change

### Mode 2: Autonomous GM (Solo Roleplay)

**Objective (O2): Playable Narrative Experiences**
- Turn Loop (P-3): Display context → await input → parse → process → narrate → append → check end
- Resolve Action (P-4): Parse intent → calculate DC → roll dice → determine outcome → create ProposedChanges → narrate
- AutoGM Oracle (P-18): Answer world-truth questions with probability resolution (Yes/No, Yes but, No and)
- Procedural Scene Population (P-19): Auto-generate NPCs, loot, hazards for new locations using Random Tables
- Forced Narrative Pushback (P-20): GM authority to prevent player abuse (pause and prompt for roll)
- Downtime & Progression (P-21): XP spending, leveling up, skill training, persistent character changes

**What Tests Must Verify:**
1. **Complete Solo Session Flow**:
   - Start scene → player declares action → system resolves → narrates → append turn → continue until scene end
   - Resolution respects dice mechanics (critical_success, success, partial, failure, critical_failure)
   - Narrative is coherent and responsive to player choices
   - World state updates (ProposedChanges → CanonKeeper → Neo4j)

2. **AutoGM Oracle (P-18)**:
   - Questions about unknown environmental states trigger Oracle resolution
   - Oracle determines likelihood based on tension/narrative context
   - Oracle rolls percentile/probability dice and maps to Yes/No outcomes
   - Oracle result is canonized as Fact
   - Narrator respects the rolled oracle truth

3. **Procedural Scene Population (P-19)**:
   - New/unexplored locations trigger procedural generation
   - System pulls appropriate Random Tables (encounters, features, loot) based on location type
   - Generated entities are staged or canonized
   - Narrator describes procedurally generated elements

4. **Forced Narrative Pushback (P-20)**:
   - System detects forced narrative declarations (e.g., "I instantly kill the boss")
   - If stakes are high, system pauses and prompts for a roll
   - Player can accept pushback (convert to dice roll) or override with explicit GM mode command
   - Prevents trivialization of combat loops

5. **Downtime & Progression (P-21)**:
   - System detects completion of milestones or dedicated downtime scenes
   - Presents progression options (XP spending, leveling up, skill training)
   - Validates progression choices against Game System rules
   - Commits changes to canonical entity properties in Neo4j

### Mode 3: GM Assistant (Co-Pilot)

**Objective (O4): Assisted Human GMing**
- Record Session (CF-1): Capture human-led sessions in real-time, parse into turns, create proposals
- Generate Recap (CF-2): Summarize what happened (events, decisions, NPCs, threads)
- Detect Unresolved Threads (CF-3): Surface plot hooks, promises, dangling storylines
- Suggest Plot Hooks (CF-4): Generate contextual hooks based on world state
- Detect Contradictions (CF-5): Find conflicting facts (dead NPCs speaking, timeline violations)
- Generate Player Handouts (CF-6): Create summaries for players based on character knowledge

**What Tests Must Verify:**
1. **Complete Co-Pilot Session Flow**:
   - GM starts recording → system captures session → parses into turns → creates proposals
   - System generates recap with events, decisions, NPCs, threads
   - System detects unresolved threads and ranks by priority
   - GM reviews and accepts proposals → CanonKeeper commits changes

2. **Contradiction Detection (CF-5)**:
   - System finds direct contradictions ("X is dead" vs "X spoke to party")
   - System finds timeline violations (Event B before Event A when B depends on A)
   - System finds location conflicts (Entity in two places at same time)
   - System finds relationship conflicts ("X hates Y" vs "X is Y's ally")
   - System suggests resolution options (retcon older, retcon newer, mark as mystery, create explanation)

3. **Thread Detection (CF-3)**:
   - System identifies open questions (things players asked but weren't answered)
   - System identifies unfulfilled promises (NPCs promised something, not delivered)
   - System identifies dangling hooks (clues planted but not followed up)
   - System ranks by recency, importance, story relevance

4. **Handout Generation (CF-6)**:
   - System filters facts by character knowledge (what PC witnessed)
   - System excludes GM-only information
   - System generates formatted output (prose, bullet points, table)
   - Handouts are accurate and useful for players

---

## Current Test Specifications Gap Analysis

### ✅ What IS Covered:

| Epic | Coverage | Status |
|------|----------|--------|
| Epic 0: Data Layer (DL-1 to DL-26) | Contract, property-based tests | ✅ Covered |
| Epic 1: Play (P-1 to P-17) | Turn loop, resolve action, dice roll | ⚠️ Partially covered |
| Epic 2: Manage (M-1 to M-35) | Entity CRUD, hierarchy, scenes | ✅ Covered |
| Epic 3: Query (Q-1 to Q-11) | Semantic search, browse entities | ✅ Covered |
| Epic 4: Ingest (I-1 to I-13) | Upload, extract, curate | ✅ Covered |
| Epic 5: System (SYS-1 to SYS-12) | Lifecycle, config | ✅ Added |
| Epic 7: Story (ST-1 to ST-8) | Plot threads | ⚠️ Added but superficial |
| Epic 8: Rules (RS-1 to RS-7) | Game systems | ⚠️ Added but superficial |
| Epic 10: Packs (MP-1 to MP-9) | Knowledge packs | ✅ Covered |

### ❌ What is NOT Covered:

| Use Case | Critical for Mode | Missing Tests |
|----------|-------------------|---------------|
| **P-18: AutoGM Oracle** | Solo Roleplay (CRITICAL) | COMPLETELY MISSING |
| **P-19: Procedural Scene Population** | Solo Roleplay (CRITICAL) | COMPLETELY MISSING |
| **P-20: Forced Narrative Pushback** | Solo Roleplay (CRITICAL) | COMPLETELY MISSING |
| **P-21: Downtime & Progression** | Solo Roleplay (CRITICAL) | COMPLETELY MISSING |
| **CF-1: Record Session** | GM Assistant (CRITICAL) | COMPLETELY MISSING |
| **CF-2: Generate Recap** | GM Assistant (CRITICAL) | COMPLETELY MISSING |
| **CF-3: Detect Unresolved Threads** | GM Assistant (CRITICAL) | COMPLETELY MISSING |
| **CF-4: Suggest Plot Hooks** | GM Assistant (CRITICAL) | COMPLETELY MISSING |
| **CF-5: Detect Contradictions** | GM Assistant (CRITICAL) | COMPLETELY MISSING |
| **CF-6: Generate Player Handouts** | GM Assistant (CRITICAL) | COMPLETELY MISSING |

### ⚠️ Superficial Coverage:

| Use Case | Issue |
|----------|-------|
| Epic 1: Play (P-3, P-4) | Tests verify API contracts but NOT complete solo session workflow |
| Epic 7: Story (ST-1 to ST-8) | Tests verify plot thread CRUD but NOT narrative coherence |
| Epic 8: Rules (RS-1 to RS-7) | Tests verify game system CRUD but NOT rule enforcement during play |

---

## What Tests Are Missing to Guarantee App Works

### 1. End-to-End Workflow Tests (CRITICAL)

**Solo Roleplay Session:**
```
1. Player starts story
2. System starts scene at location
3. Player declares action: "I attack the goblin"
4. System parses action → determines it's combat
5. System calculates DC (15) → rolls dice (d20 + 5 = 18)
6. System determines outcome (success) → creates ProposedChanges (goblin HP -5)
7. System narrates: "You swing your sword and strike the goblin!"
8. System appends turn to MongoDB
9. Player continues... (repeat 10-20 times)
10. Scene ends
11. Player asks: "What did I learn?"
12. System generates recap
13. Player starts downtime
14. System offers progression (level up)
15. Player spends XP
16. System commits changes to Neo4j
17. Character stats permanently updated
```

**GM Assistant Session:**
```
1. GM starts recording session
2. GM types notes during play
3. System parses into turns and creates proposals
4. Session ends
5. GM asks: "What happened?"
6. System generates recap with events, decisions, NPCs, threads
7. GM asks: "What threads are unresolved?"
8. System detects and ranks threads (open questions, promises, hooks)
9. GM asks: "Any contradictions?"
10. System finds conflicts (dead NPC speaking, timeline violations)
11. GM reviews and accepts proposals
12. CanonKeeper commits changes
13. System updates canon
```

### 2. AutoGM Core Tests (CRITICAL)

**Oracle Resolution (P-18):**
```
Given: Scene with tension_score = 7 (high tension)
When: Player asks "Is the door locked?"
Then: Oracle determines likelihood (Unlikely due to high tension)
Then: Oracle rolls percentile (25)
Then: Oracle maps to outcome (No - door is not locked)
Then: Oracle result is canonized as Fact
Then: Narrator describes: "The door creaks open easily..."
```

**Procedural Scene Population (P-19):**
```
Given: New location "Dungeon Room 1" with no entities
When: Scene initialization detects unpopulated location
Then: System pulls Random Tables (encounters, features, loot)
Then: System rolls on tables → generates 1 goblin, 1 treasure chest, 1 trap
Then: System stages entities in scene
Then: Narrator describes: "You enter a dark room. A goblin guards a chest, but there's a tripwire..."
```

**Forced Narrative Pushback (P-20):**
```
Given: Active combat with boss monster (high stakes)
When: Player types "I instantly kill the boss with one hit"
Then: Resolver detects forced narrative declaration
Then: System pauses and prompts: "This requires a roll. Do you want to roll?"
Then: Player accepts pushback
Then: System converts to dice roll action
Then: System rolls and determines outcome
```

**Downtime & Progression (P-21):**
```
Given: Story arc reaches resolution
When: System detects milestone completion
Then: System presents progression options (XP: 5, available: level up, train skill)
Then: Player chooses "level up to level 2"
Then: System validates against game system rules (D&D 5e: requires XP = 300)
Then: System commits changes to Neo4j (character.level = 2, XP = 200)
Then: Character stats permanently updated
```

### 3. Co-Pilot Core Tests (CRITICAL)

**Contradiction Detection (CF-5):**
```
Given: Fact 1: "Gandalf is dead" (established at turn 10)
Given: Fact 2: "Gandalf spoke to the party" (established at turn 20)
When: GM runs contradiction detection
Then: System finds direct contradiction (dead vs alive)
Then: System shows both facts with sources (Fact 1 at turn 10, Fact 2 at turn 20)
Then: System suggests resolution options:
  - Retcon Fact 1 (Gandalf wasn't actually dead)
  - Retcon Fact 2 (It was a ghost/vision)
  - Mark as "apparent contradiction" (mystery)
Then: GM chooses resolution
Then: System applies resolution and updates canon
```

**Thread Detection (CF-3):**
```
Given: Story with 50 turns
When: GM asks for unresolved threads
Then: System analyzes turns and identifies:
  - Open questions: "Who killed the duke?" (asked at turn 15, never answered)
  - Unfulfilled promises: NPC promised reward at turn 20, never delivered
  - Dangling hooks: Clue planted at turn 30, never followed up
Then: System ranks by recency, importance, story relevance
Then: System displays prioritized list
```

### 4. Narrative Coherence Tests (CRITICAL)

**Coherence Across Sessions:**
```
Given: Session 1: Player defeats goblin, goblin escapes
When: Session 2 starts
Then: System remembers goblin escaped
Then: System includes goblin in context
Then: Narrator references goblin: "The goblin you fought before is lurking nearby..."
```

**World State Consistency:**
```
Given: Character with HP = 20/20
When: Character takes 5 damage
Then: System updates HP = 15/20
When: Character drinks healing potion (+5 HP)
Then: System updates HP = 20/20
When: Character takes 30 damage (fatal)
Then: System updates HP = -10/20
Then: System marks character as "dead" or "unconscious"
Then: Narrator describes death/unconsciousness
```

---

## Why Current Tests Won't Guarantee App Works

### Problem 1: Fragmented Testing

**Current approach:** Test each API endpoint in isolation
```python
def test_resolve_action():
    result = resolve_action(action="I attack", target="goblin")
    assert result.success_level in ["success", "failure"]
```

**What's missing:** Complete workflow validation
```python
def test_complete_solo_session():
    # Start scene
    scene_id = start_scene(location_id)
    # Player declares action
    turn_1 = user_action("I attack the goblin")
    # System resolves
    resolution = resolve_action(turn_1)
    # System narrates
    response = generate_narration(resolution)
    # System appends turn
    append_turn(scene_id, turn_1, response)
    # Player continues...
    # Verify: World state updated correctly
    # Verify: Narrative is coherent
    # Verify: Character stats persisted
```

### Problem 2: Missing Core Features

**AutoGM Core (P-18 to P-21):**
- P-18 (Oracle): COMPLETELY MISSING
- P-19 (Procedural): COMPLETELY MISSING
- P-20 (Pushback): COMPLETELY MISSING
- P-21 (Progression): COMPLETELY MISSING

**Co-Pilot Core (CF-1 to CF-6):**
- CF-1 (Record Session): COMPLETELY MISSING
- CF-2 (Recap): COMPLETELY MISSING
- CF-3 (Threads): COMPLETELY MISSING
- CF-4 (Hooks): COMPLETELY MISSING
- CF-5 (Contradictions): COMPLETELY MISSING
- CF-6 (Handouts): COMPLETELY MISSING

### Problem 3: No Narrative Coherence Validation

**What's missing:**
- Tests verify APIs return valid data
- Tests DON'T verify narrative makes sense
- Tests DON'T verify responses are responsive to player choices
- Tests DON'T verify world state remains consistent

**Example:**
```python
# Current test (missing)
def test_narrative_coherence():
    # Player defeats goblin
    result_1 = complete_turn("I attack the goblin with all my might")
    # Next turn, player asks about goblin
    result_2 = complete_turn("What happened to the goblin?")
    # Verify: Narrator remembers goblin was defeated
    # Verify: Narrative is coherent
    assert "goblin" in result_2.narrative.lower()
    assert "defeated" in result_2.narrative.lower() or "escaped" in result_2.narrative.lower()
```

### Problem 4: No World State Persistence Validation

**What's missing:**
- Tests verify data is written to databases
- Tests DON'T verify world state persists across sessions
- Tests DON'T verify world evolves over time (O5)

**Example:**
```python
# Current test (missing)
def test_world_state_persistence():
    # Session 1: Character gains XP
    scene_1_id = start_scene(...)
    complete_turn(scene_1_id, "I defeat the goblin")
    complete_turn(scene_1_id, "I search the room")
    end_scene(scene_1_id)

    # Session 2: Character should have XP
    scene_2_id = start_scene(...)
    character = get_character(character_id)
    # Verify: Character XP persisted
    assert character.xp > 0
    # Verify: Character learned about location
    assert "Dungeon Room 1" in character.known_locations
```

---

## What Needs to Happen Before Testing

### Step 1: Define IDEAL STATE Document

**Create docs/IDEAL_STATE.md:**
1. For each mode (World Architect, Autonomous GM, GM Assistant):
   - Describe what the ideal user experience looks like
   - Define the complete user workflow from start to finish
   - Identify all user interactions and expected system responses
2. For each core objective (O1-O5):
   - Define what success looks like
   - Define what tests must verify
3. For each critical feature (P-18 to P-21, CF-1 to CF-6):
   - Define the acceptance criteria
   - Define what tests must verify

### Step 2: Create End-to-End Test Scenarios

**Create docs/E2E_TEST_SCENARIOS.md:**
1. For each mode, create complete test scenarios:
   - Solo Roleplay: Start story → play 20 turns → end scene → downtime → progression
   - GM Assistant: Start recording → capture session → generate recap → detect threads → resolve proposals
   - World Architect: Upload document → extract entities → curate pack → apply to world
2. For each scenario, define:
   - The user actions (what user does)
   - The expected system responses (what system does)
   - The expected world state changes (what changes in world)
   - The verification criteria (what tests check)

### Step 3: Update Test Specifications

**Update docs/TEST_SPECIFICATIONS.md:**
1. Add comprehensive specifications for P-18 to P-21 (AutoGM Core)
2. Add comprehensive specifications for CF-1 to CF-6 (Co-Pilot Core)
3. Add end-to-end workflow tests
4. Add narrative coherence tests
5. Add world state persistence tests

### Step 4: Implement Tests

**Create integration/e2e tests:**
1. Implement end-to-end test scenarios
2. Implement AutoGM core tests
3. Implement Co-Pilot core tests
4. Implement narrative coherence tests
5. Implement world state persistence tests

---

## Conclusion

**Current Test Specifications Status:**
- ❌ Will NOT guarantee the app works for solo roleplay
- ❌ Will NOT guarantee the app works for GM assistance
- ❌ Missing 16 critical use cases (P-18 to P-21, CF-1 to CF-6)
- ❌ Missing end-to-end workflow tests
- ❌ Missing narrative coherence validation
- ❌ Missing world state persistence validation

**What Must Happen:**
1. ✅ Define IDEAL STATE document (what the app SHOULD do)
2. ✅ Create end-to-end test scenarios (complete user workflows)
3. ✅ Update test specifications (add missing use cases)
4. ✅ Implement comprehensive tests (validate IDEAL STATE)

**Next Steps:**
1. Create docs/IDEAL_STATE.md
2. Create docs/E2E_TEST_SCENARIOS.md
3. Update docs/TEST_SPECIFICATIONS.md with missing specifications
4. Implement tests to validate IDEAL STATE

---

**Document Version:** 1.0
**Last Updated:** May 19, 2026
**Status:** CRITICAL GAPS IDENTIFIED