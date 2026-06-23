# MONITOR — System Description

> **Multi-Ontology Narrative Intelligence Through Omniversal Representation**

---

## One-Sentence Pitch

A persistent narrative intelligence system that can build worlds, run solo RPGs, and assist human Game Masters by remembering everything that matters and reacting like a coherent storyteller.

---

## 1. What It Is

MONITOR is a **narrative intelligence system** that can create, understand, run, and assist tabletop role-playing games across one or multiple worlds.

It operates in three distinct modes:

| Mode | Description |
|------|-------------|
| **World Architect** | Builds and maintains fictional worlds and multiverses from structured and unstructured sources |
| **Autonomous Game Master** | Runs full solo RPG experiences with turn-by-turn narration and rules enforcement |
| **Game Master Assistant** | Supports human-led campaigns by recording, tracking, recalling, and analyzing sessions |

The system treats **worlds, characters, events, and stories as persistent entities that evolve over time**.

---

## 2. Core Objectives

What success looks like:

| ID | Objective | Description |
|----|-----------|-------------|
| **O1** | Persistent Fictional Worlds | Create and maintain consistent worlds that retain facts, history, entities, and causal continuity across sessions |
| **O2** | Playable Narrative Experiences | Deliver full solo RPG gameplay where the system narrates, adjudicates rules, and reacts meaningfully to player choices |
| **O3** | System-Agnostic Rules Handling | Support multiple RPG systems (dice, cards, custom mechanics) without hard-coding any single game |
| **O4** | Assisted Human GMing | Act as a reliable co-pilot for live or recorded sessions: remembering what happened, tracking consequences, and surfacing useful insights |
| **O5** | World Evolution Over Time | Allow worlds and characters to change permanently based on play, not reset between sessions |

---

## 3. Epics

### EPIC 1 — World & Multiverse Definition

**Goal:** Allow users to create, expand, and modify fictional worlds with structured consistency.

**Capabilities:**
- Define worlds, universes, and multiverses
- Store facts, locations, factions, rules of reality
- Track canonical vs optional or alternative truths

**Key Use Cases:**
- Ingest a setting book or PDF and extract:
  - Geography
  - Cultures
  - Magic/technology rules
- Manually add or edit world facts
- Fork timelines or alternate universes
- Ask factual questions about the world ("What gods exist in this region?")

---

### EPIC 2 — Knowledge & Memory Ingestion

**Goal:** Convert external information into usable world knowledge.

**Capabilities:**
- Ingest:
  - Written lore
  - Session summaries
  - Player notes
  - Transcripts or recordings
- Distinguish:
  - Facts
  - Rumors
  - Character beliefs
  - Player knowledge vs character knowledge

**Key Use Cases:**
- Upload campaign notes → world memory updates
- Record a live session → automatic event timeline
- Ask: "What did the party promise the Duke?"
- Detect contradictions or unresolved threads

---

### EPIC 3 — Character Creation & Identity Management

**Goal:** Support persistent player characters and NPCs across stories.

**Capabilities:**
- Create player characters tied to:
  - A world
  - A rule system
- Maintain:
  - Stats
  - Inventory
  - Relationships
  - Psychological traits
- Allow characters to reappear as NPCs in other stories

**Key Use Cases:**
- Create a solo character and start a campaign
- Import an existing character sheet
- Reuse a past PC as an NPC in a new story
- Ask: "How would this character realistically react?"

---

### EPIC 4 — Autonomous Narrative Game Master

**Goal:** Run a complete RPG session without a human GM.

**Capabilities:**
- Scene-based narration
- Turn-by-turn interaction
- Player choice → world reaction
- Maintain tone, genre, and pacing
- Track unresolved consequences

**Key Use Cases:**
- Play a solo campaign like an interactive novel
- Switch between:
  - Freeform roleplay
  - Structured turns
- Pause, rewind, or branch the story
- Ask the GM for clarification or summaries mid-session

---

### EPIC 5 — Rules & Randomization Engine

**Goal:** Apply RPG mechanics consistently and transparently.

**Capabilities:**
- Support:
  - Dice systems (d20, dice pools, percentiles)
  - Card-based systems
  - Custom probability rules
- Enforce:
  - Success/failure logic
  - Partial successes
  - Narrative consequences

**Key Use Cases:**
- Roll dice automatically when required
- Explain why an outcome happened
- Override or house-rule mechanics
- Ask: "What are my odds if I try this?"

---

### EPIC 6 — Session Tracking & Timeline Management

**Goal:** Treat gameplay as a sequence of meaningful events.

**Capabilities:**
- Record:
  - Scenes
  - Actions
  - Decisions
  - Outcomes
- Maintain:
  - World timelines
  - Character timelines
- Enable querying past events

**Key Use Cases:**
- Review last session summary
- Ask: "When did this NPC betray us?"
- Detect dangling plot threads
- Generate recaps for players

---

### EPIC 7 — Human GM Assistant Mode

**Goal:** Augment, not replace, a human Dungeon Master.

**Capabilities:**
- Listen to or ingest live sessions
- Track:
  - NPC names
  - Improvised lore
  - Player decisions
- Suggest:
  - Plot hooks
  - Consequences
  - Continuations

**Key Use Cases:**
- GM runs a live table; system records canon
- Ask mid-campaign:
  - "What threads have I not resolved?"
- Generate prep notes for next session
- Detect inconsistencies introduced accidentally

---

### EPIC 8 — Planning & Meta-Narrative Tools

**Goal:** Help design stories without breaking immersion.

**Capabilities:**
- Plan arcs without forcing outcomes
- Model factions, tensions, and goals
- Simulate "what if" scenarios

**Key Use Cases:**
- Ask: "What happens if the kingdom collapses?"
- Design a mystery with multiple valid solutions
- Balance player agency with narrative pressure

---

## 4. System Modes

These rows describe the **target product workflow surface**. In the current repo, the main live play surface is the web chat UI, and the wired CLI command set is smaller (`state`, `rules`, `mechanics`, `ingest`, `playtest`).

| Mode | Who Leads | System Role | Target Command Surface | Current Live Surface |
|------|-----------|-------------|------------------------|----------------------|
| **Solo Play** | Player | Full GM | `monitor play` | Web chat UI + `monitor playtest` |
| **Assisted GM** | Human GM | Memory + Analyst | `monitor copilot` | Web UI support flows |
| **World Design** | User | Architect | `monitor manage` | Web world-building flows + package APIs |
| **Post-Session Analysis** | User | Archivist | `monitor copilot`, `monitor query` | Query/use-case support remains mostly design-level |

### Additional Product Commands

| Command | Purpose | Use Cases |
|---------|---------|-----------|
| `monitor query` | Search and explore canon | Q-1 to Q-11 |
| `monitor ingest` | Upload and process documents | I-1 to I-13 |
| `monitor story` | Arc planning, faction modeling, what-if | ST-1 to ST-8 |
| `monitor rules` | Game system definition | RS-1 to RS-7 |

---

## 5. Non-Goals

The system does **NOT**:

- Force stories toward predefined endings
- Replace player agency
- Require a single RPG system
- Assume combat-only gameplay

---

## 6. Epic → Use Case Alignment

> Cross-reference to `docs/USE_CASES.md`

### Use Cases by Category

| Category | Range | Description |
|----------|-------|-------------|
| **DATA LAYER** | `DL-1` to `DL-26` | Canonical data access and MCP interfaces |
| **PLAY** | `P-1` to `P-21` | Core gameplay loop — narration, scenes, actions |
| **MANAGE** | `M-1` to `M-35` | World administration — CRUD for all entities |
| **QUERY** | `Q-1` to `Q-11` | Canon exploration — search, browse, ask |
| **INGEST** | `I-1` to `I-12` | Knowledge import — documents, extraction, curation |
| **SYSTEM** | `SYS-1` to `SYS-12` | App lifecycle, config, session |
| **CO-PILOT** | `CF-1` to `CF-8` | Human GM assistant features |
| **STORY** | `ST-1` to `ST-8` | Planning & meta-narrative tools |
| **RULES** | `RS-1` to `RS-7` | Game system definition — stats, skills, mechanics |
| **PACKS** | `MP-1` to `MP-9` | Multiverse Pack composition and reuse |
| **DOCS** | `DOC-1` | Documentation publishing & governance |

**Current catalog:** 165 use cases (see `docs/USE_CASES.md` for the live summary table)

### Epic Mapping

| Epic | Use Cases | Coverage |
|------|-----------|----------|
| **EPIC 0** — Data Layer Access | DL-1 to DL-14 (canonical data/MCP interfaces) | Defined |
| **EPIC 1** — World & Multiverse | M-1 to M-8 (hierarchy), M-23 to M-25 (axioms), M-30 (time) | Complete |
| **EPIC 2** — Knowledge Ingestion | I-1 to I-6 | Complete |
| **EPIC 3** — Character & Identity | M-12 to M-22 (entities, characters, memories) | Complete |
| **EPIC 4** — Autonomous GM | P-1 to P-8, P-11, P-12 (play loop) | Complete |
| **EPIC 5** — Rules & Randomization | P-4, P-9, P-10, **RS-1 to RS-4** (game systems) | Complete |
| **EPIC 6** — Session & Timeline | M-26 to M-30 (facts, scenes, time), Q-5 (timeline) | Complete |
| **EPIC 7** — Human GM Assistant | CF-1 to CF-5 (co-pilot features) | Complete |
| **EPIC 8** — Planning & Meta-Narrative | ST-1 to ST-5 (story planning) | Complete |
| **EPIC 9** — Documentation | DOC-1 | Defined |

### Use Case Summary

| Prefix | Name | Count | Epic |
|--------|------|-------|------|
| `DL-` | Data Layer | 14 | EPIC 0 |
| `P-` | Play | 12 | EPIC 4, 5 |
| `M-` | Manage | 30 | EPIC 1, 3, 6 |
| `Q-` | Query | 9 | EPIC 6 |
| `I-` | Ingest | 6 | EPIC 2 |
| `SYS-` | System | 10 | — |
| `CF-` | Co-Pilot | 5 | EPIC 7 |
| `ST-` | Story Planning | 5 | EPIC 8 |
| `RS-` | Rules | 4 | EPIC 5 |
| `DOC-` | Documentation | 1 | EPIC 9 |

**Total: 96 use cases**

---

## 7. Document Map

| Document | Purpose |
|----------|---------|
| `SYSTEM.md` | **This file** — Product vision and epics |
| `ARCHITECTURE.md` | Technical layer architecture |
| `STRUCTURE.md` | Repository folder definitions |
| `docs/USE_CASES.md` | Detailed use case specifications |
| `docs/AI_DOCS.md` | Quick reference for implementation |
| `packages/*/IMPLEMENTATION.md` | Layer-specific task lists |

---

## 8. Ideal State (System Modes)

### Mode 1: World Architect

### Purpose

Build and maintain fictional worlds from structured and unstructured sources. The system should automatically extract entities, facts, relationships from documents and organize them into coherent world knowledge.

### Ideal User Experience

```
User: I want to create a fantasy world for my D&D campaign.

System: Let's build your world. What's the name?
User: Eldoria
System: Great! Eldoria is created. You can upload documents or add manual facts.
User: (Uploads "Eldoria_Campaign_Setting.pdf")
System: Extracting content from 150 pages...
        Found 45 entities (characters, locations, factions)
        Found 120 facts (lore, history, rules)
        Found 80 relationships (alliances, rivalries)
        Ready to review!

User: Show me the factions.
System: (Lists factions with descriptions):
        - The Silver Alliance (good-aligned kingdom)
        - The Shadow Cabal (evil conspiracy)
        - The Free Traders Guild (merchant alliance)

User: Add a fact: The Silver Alliance is at war with the Shadow Cabal.
System: Fact added. This contradicts existing fact that they are uneasy allies.
        Would you like to resolve the contradiction?
User: Retcon the old fact.
System: Done. Silver Alliance and Shadow Cabal are now at war.

User: Create a character for the party.
System: What's the character's name and race?
User: Elara, High Elf Rogue
System: Elara created. Would you like to import from a character sheet?
User: No, let me add stats. STR 10, DEX 18, CON 12, INT 14, WIS 12, CHA 10.
System: Stats saved. Elara is ready for adventure!

User: Apply the "Forgotten Ruins" knowledge pack to this world.
System: Applying pack...
        Added 15 new locations (ruins, dungeons)
        Added 30 new entities (ancient guardians, traps)
        Added 20 new facts (lore about the ruins)
        Pack applied successfully!
```

### What the System Must Do

#### 1. Document Ingestion (I-1 to I-13)

**User Action:** Upload a PDF document
**System Action:**
1. Upload document to MinIO storage
2. Extract text from PDF
3. Chunk text into 500-token snippets with 50-token overlap
4. Generate embeddings for each snippet
5. Store embeddings in Qdrant
6. Extract entities (names, locations, factions, items)
7. Extract facts (lore, history, rules)
8. Extract relationships (alliances, rivalries, family ties)
9. Store extracted data in MongoDB (for review)
10. Present extracted data to user for curation

**Success Criteria:**
- All text extracted correctly
- Entities identified with ≥80% precision
- Facts identified with ≥70% precision
- Relationships identified with ≥60% precision
- User can review and curate extracted data
- User can accept/reject/approve extracted data

#### 2. Knowledge Pack Curation (I-12)

**User Action:** Curate extracted entities, facts, relationships into a knowledge pack
**System Action:**
1. User reviews extracted entities
2. User accepts/rejects/modifies entities
3. User reviews extracted facts
4. User accepts/rejects/modifies facts
5. User reviews extracted relationships
6. User accepts/rejects/modifies relationships
7. User creates knowledge pack
8. System stores pack with metadata (name, description, type)

**Success Criteria:**
- User can review all extracted data
- User can modify extracted data
- User can create packs from curated data
- Packs are reusable across worlds

#### 3. Knowledge Pack Application (MP-5 to MP-9)

**User Action:** Apply knowledge pack to world
**System Action:**
1. User selects world
2. User selects pack
3. System applies pack:
   - Create entities from archetypes
   - Create facts from lore_facts
   - Create relationships
   - Handle conflicts (duplicate entities, contradictory facts)
4. System presents conflict resolution options
5. User resolves conflicts
6. System commits changes to canon (via CanonKeeper)

**Success Criteria:**
- Pack applies successfully without errors
- Conflicts are detected and presented to user
- User can resolve conflicts (merge, skip, overwrite)
- Changes are committed to canon correctly
- World state is consistent after application

#### 4. World State Persistence (O1, O5)

**User Action:** Access world after session
**System Action:**
1. User opens world
2. System loads all entities, facts, relationships
3. System shows world state (entities, facts, timeline)
4. User can review history (what happened in previous sessions)
5. User can see current world state (who's alive, what factions exist, etc.)

**Success Criteria:**
- World state persists across sessions
- Facts remain consistent
- Entities evolve over time (stats change, relationships change)
- Timeline is preserved
- User can review history

---

### Mode 2: Autonomous Game Master (Solo Roleplay)

### Purpose

Run a complete RPG session without a human GM. The system should narrate, adjudicate rules, and react meaningfully to player choices. The system should act like a coherent storyteller who remembers everything and respects the rules.

### Ideal User Experience

```
User: I want to play a solo D&D campaign.

System: Let's set up your character.
User: Elara, High Elf Rogue, level 1.
System: Stats? AC? Hit points?
User: (Enters stats)
System: Character created. What's the starting adventure?
User: The party is hired to investigate disappearances in a village.
System: Scene starting...
        [You arrive in the village of Millhaven at dusk. The streets are empty,
         and an unnatural mist clings to the ground. A nervous innkeeper named
         Barnaby greets you.]

User: "What's going on with the mist?"
System: [Barnaby's eyes dart around nervously. "It started three nights ago.
         People started disappearing. Then the mist came. Nobody goes out
         after dark anymore. I'd suggest you find rooms quickly."]

User: "I'll search the village for clues."
System: [Rolling Investigation...]
        [Your investigation DC is 12.]
        [Rolling 1d20 + 5 (Investigation) = 17]
        [Success!]
        [You find fresh drag marks leading from the town square toward the old
         cemetery. The marks are only hours old.]

User: "I follow the tracks to the cemetery."
System: [Scene transitioning to cemetery...]
        [The cemetery is shrouded in mist. Crypts loom like silent sentinels.
         The drag marks lead to a newly-dug grave that's been disturbed.]

User: "Is there anything in the grave?"
System: [Oracle query: Is there anything in the grave?]
        [Tension: High (7). Likelihood: Likely.]
        [Rolling percentile... 42]
        [Yes, but...]
        [You peer into the grave. There's a body, but it's not what you expect.
         It's a villager, but their skin is pale and their eyes glow faintly blue.
         They're not dead... not yet.]

User: "I draw my sword and prepare for a fight."
System: [Combat initiated!]
        [Enemy: Possessed Villager (stats: AC 12, HP 15, attacks: claw +4)]
        [Roll initiative... You: 18, Enemy: 12]
        [You go first!]

User: "I attack with my rapier."
System: [Rolling attack... 1d20 + 6 = 22]
        [Hit!]
        [Rolling damage... 1d8 + 3 = 7]
        [The possessed villager staggers back. Your rapier glows with
         magical energy as it cuts through the mist.]

User: (Continues combat...)

[Several turns later...]

User: "I search the villager's body."
System: [You find a silver amulet with a strange blue gem. It pulses with
         an otherworldly energy.]
        [Item added: Amulet of Shadows]

User: "I return to the inn and ask Barnaby if he recognizes this amulet."
System: [Barnaby's face goes pale. "That... that belonged to the village
         elder, Magda. She disappeared first. We never found her body."]

User: (Session ends)
System: Session summary:
        - You investigated the village
        - You found drag marks leading to the cemetery
        - You fought and defeated a possessed villager
        - You found an amulet belonging to the missing elder
        - XP gained: 50
        - Unresolved threads: Where is Magda? What's causing the possessions?

User: Start downtime.
System: You have 50 XP. Available options:
        - Level up to level 2 (requires 300 XP)
        - Train a skill (+1 to a skill, costs 10 XP)
        - Learn a feat (requires 100 XP)
User: Train Investigation (+1 to Investigation, costs 10 XP).
System: Done! Your Investigation skill is now +6.
        Remaining XP: 40.
```

### What the System Must Do

#### 1. Turn Loop (P-3) - The Heart of the Game

**User Action:** Declares action ("I attack", "I pick the lock", "I climb")
**System Action:**
1. Display context (location, present entities, recent turns)
2. Await user input
3. Parse input type:
   - If starts with `/` → META_COMMAND
   - If starts with `"` or contains "say" → DIALOGUE
   - If contains `?` or starts with "what", "who", "where", "how" → QUESTION
   - Otherwise → ACTION
4. Process through appropriate handler:
   - ACTION → P-4 (Resolve Action)
   - DIALOGUE → P-5 (Handle Dialogue)
   - QUESTION → P-6 (Answer Question)
   - META_COMMAND → P-7 (Execute Command)
5. Generate response (via Narrator agent)
6. Append turns to MongoDB (user turn, GM turn)
7. Check: Should scene end?
8. If yes → P-8 (End Scene)
9. If no → Continue loop

**Success Criteria:**
- Turn loop executes smoothly (no crashes)
- Input parsing is accurate (≥95%)
- Response generation is coherent (≥80% user satisfaction)
- Turns are appended correctly to MongoDB
- Scene ends when appropriate
- Response time < 3s per turn

#### 2. Resolve Action (P-4) - Dice and Outcomes

**User Action:** Declares action ("I attack the goblin")
**System Action:**
1. Parse action intent
2. Identify target entities
3. Determine difficulty (DC)
4. Determine resolution type:
   - **Dice**: Combat, skill checks, saves
   - **Narrative**: Trivial actions (GM decides)
   - **Auto-success**: Guaranteed success (impossible to fail)
   - **Auto-fail**: Impossible actions (can't succeed)
5. If dice:
   - Roll dice according to formula
   - Calculate total
   - Determine success level:
     - critical_success: roll + 10 or nat 20
     - success: roll >= DC
     - partial: DC - 5 <= roll < DC
     - failure: DC - 10 <= roll < DC - 5
     - critical_failure: roll < DC - 10 or nat 1
6. Create ProposedChanges (state changes, damage, etc.)
7. Narrator describes outcome
8. Return to turn loop

**Success Criteria:**
- Difficulty calculation is correct (DC appropriate for action)
- Dice rolling is accurate (formula interpreted correctly)
- Success level determination is correct
- ProposedChanges are created for all state changes
- Narrative description is coherent and responsive
- Response time < 500ms (excluding narration)

#### 3. AutoGM Oracle (P-18) - Probability Resolution

**User Action:** Asks question about unknown environmental state ("Is the door locked?")
**System Action:**
1. Detect question about unknown fact
2. Determine tension_score (0-10, higher = more tension)
3. Determine likelihood based on tension/narrative context:
   - High tension → unlikely answers (system is hostile)
   - Low tension → likely answers (system is benign)
4. Roll percentile die (1d100)
5. Map to outcome:
   - 1-5: "No, and..." (bad outcome)
   - 6-45: "No" (answer is no)
   - 46-55: "No, but..." (answer is no but something good happens)
   - 56-95: "Yes" (answer is yes)
   - 96-100: "Yes, and..." (good outcome)
6. Canonize oracle result as Fact
7. Narrator describes outcome, respecting rolled truth

**Example:**
```
Question: "Is the door locked?"
Tension: 7 (high tension)
Likelihood: Unlikely (system is hostile)
Roll: 25
Outcome: "No" (door is not locked)
Narrator: [The door creaks open easily. It wasn't locked after all.]
Fact: "The door to the crypt is not locked." (canon_level=cards)
```

**Success Criteria:**
- Oracle questions are detected correctly
- Likelihood determination is based on tension/narrative
- Dice rolling is accurate
- Outcome mapping is correct
- Oracle result is canonized as Fact
- Narrator respects the rolled oracle truth
- Oracle resolves consistently (same question → same outcome)

#### 4. Procedural Scene Population (P-19) - Auto-Generate Content

**User Action:** Transitions to new/unexplored location
**System Action:**
1. Detect scene transition to new location
2. Check if location is unpopulated (no entities staged)
3. If unpopulated, trigger procedural generation:
   - Pull Random Tables for location type (encounters, features, loot)
   - Roll on each table
   - Generate entities based on rolls:
     - NPCs (from encounter table)
     - Hazards (from hazard table)
     - Loot (from loot table)
     - Features (from feature table)
   - Stage entities in scene (temporary or canonized)
4. Narrator describes procedurally generated elements in opening prompt

**Example:**
```
Location: "Dungeon Room 3" (type=cave)
Random Tables:
- Encounters: 1d6 goblins (rolled: 2)
- Hazards: 1d4 pits (rolled: 1)
- Loot: 1d3 treasure chests (rolled: 1)
- Features: 1d6 stalactites (rolled: 3)

Generated entities:
- 2 Goblins (temporarily staged in scene)
- 1 Pit trap (temporarily staged)
- 1 Treasure chest (canonized: becomes permanent world entity)
- 3 Stalactites (temporary)

Narrator: [You enter a dark cave. Two goblins are arguing over a treasure chest,
          while a third goblin stands guard. Stalactites hang from the ceiling,
          and there's a pit in the center of the room.]
```

**Success Criteria:**
- Scene transition triggers procedural generation
- Random tables are pulled correctly for location type
- Rolls are random and varied (not same every time)
- Generated entities are staged correctly
- Narrator describes procedurally generated elements
- Generation doesn't create contradictions (e.g., duplicate NPCs)

#### 5. Forced Narrative Pushback (P-20) - GM Authority

**User Action:** Declares forced narrative ("I instantly kill the boss with one hit")
**System Action:**
1. Parse action
2. Detect forced narrative declaration
3. Evaluate stakes:
   - Low stakes: trivial actions (allow forced narrative)
   - High stakes: combat, major plot points (require roll)
4. If stakes are high:
   - Pause turn
   - Prompt user: "This requires a roll. Do you want to roll?"
   - User options:
     - Accept pushback (convert to dice roll)
     - Override with explicit GM mode command ("/gm override")
5. If user accepts:
   - Convert action to dice roll
   - Calculate DC
   - Roll dice
   - Determine outcome
6. Narrate outcome based on roll

**Example:**
```
User: "I instantly kill the dragon with one arrow!"
System: [The dragon is a powerful creature. This requires a roll.]
        [Do you want to roll? (Y/N)]
User: Y
System: [Rolling attack... 1d20 + 7 = 15]
        [Dragon AC: 18]
        [Miss!]
        [Your arrow bounces off the dragon's scales. The dragon roars!]
```

**Success Criteria:**
- Forced narrative declarations are detected correctly
- Stakes are evaluated correctly
- High-stakes actions prompt for roll
- Low-stakes actions allow forced narrative
- User can override with explicit GM mode command
- Pushback prevents trivialization of combat

#### 6. Downtime & Progression (P-21) - Character Advancement

**User Action:** Completes milestone or enters downtime scene
**System Action:**
1. Detect milestone completion or downtime scene
2. Present progression options:
   - XP summary (how much XP gained)
   - Available upgrades (level up, train skill, learn feat)
   - Requirements (XP needed, prerequisites)
3. User selects progression option
4. Validate choice against game system rules:
   - Check if enough XP
   - Check if prerequisites met
   - Check if choice is legal per game system
5. If valid:
   - Commit changes to canonical entity properties in Neo4j
   - Update character stats
   - Reduce XP
   - Confirm to user
6. If invalid:
   - Explain why (not enough XP, prerequisites not met)

**Example:**
```
System: [Story arc complete!]
        [XP gained: 300]
        [Total XP: 500]
        [Current level: 1]
        [Available options:]
        - Level up to level 2 (requires 300 XP) ✓ Available
        - Train a skill (+1 to skill, costs 50 XP) ✓ Available
        - Learn a feat (requires 100 XP) ✓ Available

User: Level up to level 2.
System: [Leveling up to level 2...]
        [Gaining: +1 proficiency bonus, new class feature]
        [Remaining XP: 200]
        [Character updated in canon!]

User: Train Investigation (+1 to Investigation, costs 50 XP).
System: [Investigation skill increased from +5 to +6]
        [Remaining XP: 150]
        [Character updated in canon!]
```

**Success Criteria:**
- Milestone detection is accurate
- Progression options are presented correctly
- Validation against game system rules is correct
- Invalid choices are rejected with explanation
- Valid choices are committed to canon
- Character stats persist across sessions

---

### Mode 3: Game Master Assistant (Co-Pilot)

### Purpose

Augment, not replace, a human Dungeon Master. The system should capture sessions, generate recaps, detect unresolved threads, suggest plot hooks, detect contradictions, and generate handouts. The human GM remains in control.

### Ideal User Experience

```
GM: I'm running a D&D session tonight. I want the system to record it.

System: Start recording session?
GM: Yes. The story is "The Shadow Conspiracy".
System: Recording started. Enter GM notes as the session progresses.

[Session starts...]
GM: (typing notes) The party arrives at the village of Millhaven. They meet
    Barnaby, the nervous innkeeper.
System: [Parsed: Scene started. Location: Millhaven. Entity: Barnaby (innkeeper).
        Fact: Barnaby is nervous. Status: pending review]

[Later in session...]
GM: (typing notes) The party investigates disappearances. They find drag marks
    leading to the cemetery. They find a possessed villager.
System: [Parsed: Action: Investigate disappearances. Entity: Possessed Villager.
        Fact: Villagers are being possessed. Status: pending review]

[Session ends...]
GM: Stop recording.
System: Recording stopped. Session summary:
        - Scenes: 2 (Millhaven inn, Cemetery)
        - Turns: 25
        - Entities: 4 (Barnaby, Possessed Villager, Elara, Gandalf)
        - Facts proposed: 7
        - Ready for review.

GM: Generate a recap for my players.
System: Session Recap:
        **What Happened:**
        The party arrived in Millhaven at dusk and met Barnaby, the nervous
        innkeeper. Barnaby told them about disappearances and strange mist.

        **Key Events:**
        - Party investigates disappearances
        - Party finds drag marks leading to cemetery
        - Party fights and defeats a possessed villager
        - Party finds amulet belonging to missing elder Magda

        **Decisions Made:**
        - Party chose to investigate cemetery (risky choice)
        - Party chose to fight possessed villager (combat decision)

        **NPCs Encountered:**
        - Barnaby (innkeeper, nervous)
        - Possessed Villager (hostile, defeated)

        **Unresolved Questions:**
        - Where is Magda?
        - What's causing the possessions?
        - What's in the cemetery crypt?

GM: Show me unresolved threads.
System: Unresolved Threads (ranked by priority):
        1. **High Priority:** Where is Magda? (asked at turn 20, never answered)
        2. **Medium Priority:** What's causing the possessions? (central mystery)
        3. **Low Priority:** What's in the crypt? (foreshadowed but not explored)

GM: Suggest some plot hooks for next session.
System: Plot Hook Suggestions:
        1. **Immediate:** The possessed villager wakes up and reveals they were
           forced by a dark ritual. They know where Magda is.
        2. **Near-term:** The amulet pulses with energy and leads the party to a
           hidden cave where the possessions originate.
        3. **Long-term:** The Shadow Cabal is behind everything. They're
           kidnapping villagers for a ritual to summon a dark entity.

GM: Check for contradictions.
System: No contradictions found. Canon is consistent.

GM: Generate a handout for my players.
System: What type of handout?
        - Session recap
        - Character dossier (what PC knows)
        - Location guide (known facts about place)
        - Quest log (active plot threads)
GM: Character dossier for Elara.
System: Elara's Knowledge:
        **What Elara Knows:**
        - Barnaby is the innkeeper at Millhaven
        - Villagers are disappearing
        - Strange mist appears at night
        - Possessed villager fought and defeated
        - Amulet belonged to missing elder Magda
        - Drag marks led to cemetery

        **What Elara Doesn't Know:**
        - Where Magda is
        - What's causing the possessions
        - What the Shadow Cabal is planning

GM: Review and accept the proposed facts.
System: Proposed Facts:
        1. Barnaby is nervous (accept/reject/modify)
        2. Villagers are being possessed (accept/reject/modify)
        3. Amulet belonged to Magda (accept/reject/modify)
        ...

GM: (Reviews and accepts all facts)
System: Facts committed to canon via CanonKeeper.
        Canon updated successfully!

GM: Prepare for next session.
System: Next Session Prep:
        - Current threads: 3 unresolved
        - Active entities: 4 (Barnaby, Magda (missing), Shadow Cabal)
        - Recent events: Possessed villager defeated, amulet found
        - Suggested plot hooks: 3 (see above)
```

### What the System Must Do

#### 1. Record Session (CF-1) - Capture Human-Led Sessions

**User Action:** Starts recording session
**System Action:**
1. Initialize recording mode for story
2. Enter passive observation:
   - GM types notes into assistant chat
   - OR session is recorded/transcribed for later ingestion
3. Parse and categorize incoming material:
   - Action
   - Dialogue
   - Lore
   - Decision
   - Consequence
4. Create/update draft story/scene documents in MongoDB
5. For each significant event:
   - Append turns to draft scene transcript
   - Create ProposedChange items tagged with timestamp, participants, location
6. GM can annotate in real time ("this is important", "NPC name: Varys")
7. Session ends → scene drafts and pending proposals ready for review

**Success Criteria:**
- Recording starts and stops correctly
- Incoming material is parsed and categorized accurately (≥80%)
- Turns are appended to draft transcript
- ProposedChanges are created for significant events
- GM can annotate in real time
- Session can be reviewed after recording

#### 2. Generate Recap (CF-2) - Summarize What Happened

**User Action:** Requests recap of session
**System Action:**
1. Select session/scene to recap
2. Analyze:
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

**Success Criteria:**
- Recap covers all major events (≥90%)
- Recap is readable and useful for players
- Recap is accurate (doesn't hallucinate events)
- Recap includes decisions, NPCs, threads
- Recap can be exported

#### 3. Detect Unresolved Threads (CF-3) - Surface Plot Hooks

**User Action:** Asks for unresolved threads
**System Action:**
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

**Success Criteria:**
- All unresolved threads are detected
- Threads are categorized correctly (questions, promises, hooks)
- Threads are ranked by priority
- GM can manage threads (dismiss, resolve, annotate)
- Thread detection is accurate (≥80%)

#### 4. Suggest Plot Hooks (CF-4) - Generate Contextual Hooks

**User Action:** Asks for plot hooks
**System Action:**
1. Analyze current context:
   - Active story and recent events
   - Present location and NPCs
   - Unresolved threads (CF-3)
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

**Success Criteria:**
- Hooks are contextually appropriate (≥70%)
- Hooks connect to existing threads
- Hooks involve relevant entities
- GM can modify or dismiss hooks
- Hooks can be saved as plot_thread

#### 5. Detect Contradictions (CF-5) - Find Conflicting Facts

**User Action:** Runs contradiction detection
**System Action:**
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

**Success Criteria:**
- All contradictions are detected
- Contradictions are categorized correctly
- Sources are shown (where facts came from)
- Resolution options are provided
- GM can resolve contradictions
- Canon remains consistent after resolution

#### 6. Generate Player Handouts (CF-6) - Create Summaries for Players

**User Action:** Requests player handout
**System Action:**
1. **Select Scope:**
   - Specific character (what they know)
   - Party (shared knowledge)
   - Story so far (campaign summary)
   - Location (travel guide)
   - NPC (relationship summary)
2. **Configure Handout:**
   - Perspective: In-character vs out-of-character
   - Detail level: Brief, standard, detailed
   - Include/exclude: Secrets, rumors, speculation
   - Format: Prose, bullet points, table
3. **Generate Handout:**
   - System gathers relevant facts, memories, scenes
   - Filters by character knowledge (what PC witnessed)
   - Excludes GM-only information
   - Generates formatted output
4. **Review & Export:**
   - GM reviews and edits
   - Export as Markdown, PDF, or image
   - Optionally save to story documents

**Success Criteria:**
- Handout is filtered by character knowledge (what PC knows)
- GM-only information is excluded
- Handout is accurate and useful for players
- Handout can be exported in multiple formats
- GM can edit before export

---

### Cross-Cutting Concerns

### 1. Narrative Coherence

**Requirement:** Narrator must generate coherent, contextually appropriate responses that respect world state, character knowledge, and previous turns.

**What Must Happen:**
- Narrator has access to full context (entities, facts, events, recent turns)
- Narrator references previous events and character knowledge
- Narrator respects canon (doesn't contradict established facts)
- Narrator maintains tone and genre consistency
- Narrator is responsive to player choices (not generic)

**Example:**
```
Turn 1: Player defeats goblin
Turn 2: Player asks "What happened to the goblin?"
Narrator: "The goblin's body lies on the ground. You defeated it in combat."
(Not: "I don't see any goblin here.")
```

### 2. World State Consistency

**Requirement:** World state must remain consistent across sessions and modes. Facts, entities, and relationships must evolve logically.

**What Must Happen:**
- Facts persist across sessions
- Entities evolve over time (stats change, relationships change)
- Contradictions are detected and resolved
- Timeline is preserved (event A before event B)
- CanonKeeper ensures only canonical facts are written to Neo4j

**Example:**
```
Session 1: Character HP = 20/20 → takes 5 damage → HP = 15/20
Session 2: Character HP = 15/20 → heals 5 → HP = 20/20
(Not: Character HP = 20/20 in Session 2)
```

### 3. Performance

**Requirement:** System must respond quickly to maintain immersion.

**Performance Targets:**
- Turn loop (full cycle): < 3s
- Resolve action (excluding narration): < 500ms
- Semantic search: < 200ms
- Document processing (10MB PDF): < 30s
- Knowledge pack application (100 entities): < 30s

### 4. Reliability

**Requirement:** System must handle errors gracefully and not lose data.

**What Must Happen:**
- LLM API failures → fallback to rule-based resolution
- Database connection losses → auto-reconnect with retry
- Invalid inputs → graceful error messages (not crashes)
- Concurrent operations → no data corruption
- Turn data is persisted before generating response

### 5. Scalability

**Requirement:** System must support multiple concurrent users and large worlds.

**What Must Happen:**
- Multiple users can play simultaneously without interference
- Large worlds (1000+ entities) load in < 5s
- Large scenes (1000+ turns) load in < 10s
- Vector search remains fast with large embeddings (100K+)

---

### Success Criteria

### Mode 1: World Architect

- ✅ Document ingestion extracts entities, facts, relationships correctly
- ✅ Knowledge packs can be curated and applied without conflicts
- ✅ World state persists across sessions
- ✅ Contradictions are detected and can be resolved
- ✅ World evolves over time (O5)

### Mode 2: Autonomous GM (Solo Roleplay)

- ✅ Turn loop executes smoothly (no crashes)
- ✅ Actions resolve correctly (dice, narrative, auto)
- ✅ Narrative is coherent and responsive
- ✅ Oracle resolves questions consistently
- ✅ Procedural generation creates varied content
- ✅ Forced narrative pushback prevents abuse
- ✅ Character progression works correctly
- ✅ World state updates correctly

### Mode 3: GM Assistant (Co-Pilot)

- ✅ Sessions are captured and parsed correctly
- ✅ Recaps are accurate and useful
- ✅ Unresolved threads are detected and ranked
- ✅ Plot hooks are contextually appropriate
- ✅ Contradictions are detected and can be resolved
- ✅ Handouts are filtered by character knowledge

---
