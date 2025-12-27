# MONITOR Use Cases

> **Complete use case catalog for the MONITOR application.**

---

## Overview

MONITOR use cases are organized into **8 categories**:

| Category | Prefix | Description |
|----------|--------|-------------|
| Session | `S-` | App startup, main menu, session management |
| Universe | `U-` | Universe/world CRUD and exploration |
| Story | `ST-` | Story/campaign management |
| Character | `C-` | PC/NPC creation and management |
| Gameplay | `G-` | Core roleplay loop |
| Ingestion | `I-` | Document upload and processing |
| Query | `Q-` | Canon exploration and search |
| Config | `CF-` | Settings and configuration |

---

## Category 1: Session Management (S-)

### S-1: Start Application

**Actor:** User
**Trigger:** User runs `monitor` command
**Flow:**
1. CLI initializes
2. Check database connections
3. Display main menu
4. Wait for user selection

**Main Menu Options:**
- Play (new or continue)
- Manage (universes, stories, characters)
- Ingest (upload documents)
- Query (explore canon)
- Settings
- Exit

---

### S-2: Main Menu Navigation

**Actor:** User
**Trigger:** User is at main menu
**Flow:**
1. Display menu options
2. User selects option
3. Route to appropriate sub-flow
4. On sub-flow completion, return to main menu

**Menu Structure:**
```
MONITOR Main Menu
├── Play
│   ├── New Story
│   ├── Continue Story
│   └── Quick Session (one-shot)
├── Manage
│   ├── Universes
│   ├── Stories
│   ├── Characters
│   └── Entities
├── Ingest
│   ├── Upload Document
│   ├── Review Proposals
│   └── Manage Sources
├── Query
│   ├── Search Canon
│   ├── Browse Entities
│   ├── Timeline View
│   └── Fact Explorer
├── Settings
│   ├── LLM Configuration
│   ├── Database Connections
│   └── Preferences
└── Exit
```

---

### S-3: Exit Application

**Actor:** User
**Trigger:** User selects Exit or Ctrl+C
**Flow:**
1. Prompt: "Save current session?" (if in story)
2. Finalize any pending operations
3. Close database connections
4. Exit cleanly

---

## Category 2: Universe Management (U-)

### U-1: List Universes

**Actor:** User
**Trigger:** Manage → Universes → List
**Flow:**
1. Query Neo4j for all Universe nodes
2. Display table: name, genre, story count, entity count
3. Allow selection for details

**Output:**
```
Universes
─────────────────────────────────────────────
 # │ Name            │ Genre    │ Stories │ Entities
───┼─────────────────┼──────────┼─────────┼──────────
 1 │ Middle-earth    │ Fantasy  │ 3       │ 127
 2 │ Star Wars       │ Sci-Fi   │ 1       │ 89
 3 │ Forgotten Realms│ Fantasy  │ 0       │ 456
```

---

### U-2: Create Universe

**Actor:** User
**Trigger:** Manage → Universes → Create
**Flow:**
1. Prompt: Universe name
2. Prompt: Genre (fantasy, sci-fi, horror, etc.)
3. Prompt: Tone (serious, humorous, dark, etc.)
4. Prompt: Tech level (medieval, modern, futuristic)
5. Prompt: Description (optional)
6. Create Universe node in Neo4j
7. Optionally: Create Multiverse container
8. Confirm creation

**Validation:**
- Name must be unique within Multiverse
- Genre from predefined list or custom

---

### U-3: View Universe Details

**Actor:** User
**Trigger:** Select universe from list
**Flow:**
1. Query Neo4j for Universe and related nodes
2. Display:
   - Basic info (name, genre, tone)
   - Statistics (entity count by type, fact count)
   - Stories in this universe
   - Recent activity
3. Offer actions: Edit, Delete, Explore, Start Story

---

### U-4: Edit Universe

**Actor:** User
**Trigger:** Universe details → Edit
**Flow:**
1. Display current values
2. Allow editing: name, genre, tone, description
3. Validate changes
4. Update Neo4j
5. Confirm update

---

### U-5: Delete Universe

**Actor:** User
**Trigger:** Universe details → Delete
**Flow:**
1. Warning: "This will delete X entities, Y facts, Z stories"
2. Require confirmation (type universe name)
3. Mark all related nodes as retconned (soft delete)
4. Confirm deletion

**Note:** We never hard-delete. All nodes are marked `canon_level: "retconned"`.

---

### U-6: Explore Universe

**Actor:** User
**Trigger:** Universe details → Explore
**Flow:**
1. Display universe map/overview
2. Show entity categories with counts
3. Allow drilling into:
   - Characters (PCs, NPCs)
   - Locations (hierarchy)
   - Factions/Organizations
   - Objects (artifacts, items)
   - Concepts (magic systems, etc.)
4. Search within universe

---

## Category 3: Story Management (ST-)

### ST-1: List Stories

**Actor:** User
**Trigger:** Manage → Stories or Play → Continue
**Flow:**
1. Query Neo4j for Story nodes
2. Display table: title, universe, status, last played, scene count
3. Filter by: universe, status (active, completed, abandoned)

---

### ST-2: Create New Story

**Actor:** User
**Trigger:** Play → New Story
**Flow:**
1. Select universe (or create new)
2. Prompt: Story title
3. Prompt: Story type (campaign, arc, one-shot)
4. Prompt: Theme (optional)
5. Prompt: Premise (optional)
6. Select/create participating PCs
7. Create Story node in Neo4j
8. Create story_outline in MongoDB
9. Transition to first scene (G-1)

---

### ST-3: Continue Story

**Actor:** User
**Trigger:** Play → Continue → Select story
**Flow:**
1. List stories with status = "active"
2. User selects story
3. Load last scene state from MongoDB
4. Display recap of recent events
5. Resume scene loop (G-2) or start new scene (G-1)

---

### ST-4: View Story Details

**Actor:** User
**Trigger:** Select story from list
**Flow:**
1. Query Neo4j + MongoDB for story data
2. Display:
   - Basic info (title, universe, type, status)
   - Scene list with summaries
   - Participating characters
   - Plot threads (open, resolved)
   - Timeline of major events
3. Offer actions: Continue, Edit, Archive, Delete

---

### ST-5: Edit Story

**Actor:** User
**Trigger:** Story details → Edit
**Flow:**
1. Display current values
2. Allow editing: title, theme, premise, status
3. Update Neo4j + MongoDB
4. Confirm update

---

### ST-6: Archive Story

**Actor:** User
**Trigger:** Story details → Archive
**Flow:**
1. Change status to "completed" or "abandoned"
2. Generate final summary
3. Optionally export

---

### ST-7: Delete Story

**Actor:** User
**Trigger:** Story details → Delete
**Flow:**
1. Warning: "This will delete X scenes, Y facts"
2. Require confirmation
3. Soft delete (mark retconned)
4. Confirm deletion

---

## Category 4: Character Management (C-)

### C-1: List Characters

**Actor:** User
**Trigger:** Manage → Characters
**Flow:**
1. Query Neo4j for EntityConcreta where entity_type = "character"
2. Display table: name, role (PC/NPC), universe, status
3. Filter by: universe, role, state (alive, dead)

---

### C-2: Create Character (PC)

**Actor:** User
**Trigger:** Manage → Characters → Create PC
**Flow:**
1. Select universe
2. Prompt: Character name
3. Prompt: Select archetype (from EntityAxiomatica) or custom
4. Prompt: Description
5. Prompt: Role (protagonist, party member)
6. Create character_sheet (character sheet):
   - Stats (system-specific)
   - Resources (HP, etc.)
   - Abilities
   - Equipment
7. Create EntityConcreta in Neo4j
8. Create character_sheet document in MongoDB
9. Optionally link to EntityAxiomatica (DERIVA_DE)

---

### C-3: Create Character (NPC)

**Actor:** User or System
**Trigger:** Manage → Characters → Create NPC, or during gameplay
**Flow:**
1. Similar to PC creation but simplified
2. NPCs may be created on-the-fly during gameplay
3. System can propose NPCs from narrative
4. GM confirms/edits before canonization

---

### C-4: View Character Details

**Actor:** User
**Trigger:** Select character from list
**Flow:**
1. Query Neo4j for entity + related facts
2. Query MongoDB for character_sheet + memories
3. Display:
   - Basic info (name, description, archetype)
   - Current state (state_tags)
   - Stats/resources (from character_sheet)
   - Relationships (allies, enemies, memberships)
   - Recent facts involving character
   - Memories (what they remember)
4. Offer actions: Edit, View Memories, View Relationships

---

### C-5: Edit Character

**Actor:** User
**Trigger:** Character details → Edit
**Flow:**
1. For PCs: Full edit of character_sheet + properties
2. For NPCs: Edit properties, state_tags
3. Create ProposedChange for significant edits
4. On save: CanonKeeper evaluates (or GM override)

---

### C-6: Manage Character Relationships

**Actor:** User
**Trigger:** Character details → Relationships
**Flow:**
1. Display current relationships (ALLY_OF, ENEMY_OF, MEMBER_OF, etc.)
2. Add relationship:
   - Select target entity
   - Select relationship type
   - Create edge in Neo4j
3. Remove relationship:
   - Mark edge as retconned

---

### C-7: View Character Memories

**Actor:** User
**Trigger:** Character details → Memories
**Flow:**
1. Query MongoDB for character_memories
2. Display memories sorted by importance
3. Show: text, emotional valence, linked fact
4. Allow editing memory (for NPCs with uncertain memories)

---

## Category 5: Gameplay (G-)

### G-1: Start New Scene

**Actor:** User/Orchestrator
**Trigger:** New story or scene transition
**Flow:**
1. Prompt: Scene title (or auto-generate)
2. Prompt: Scene purpose (combat, exploration, social, etc.)
3. Select location (existing or create)
4. Select participating entities
5. Create Scene document in MongoDB
6. Narrator generates scene description
7. Enter turn loop (G-2)

---

### G-2: Turn Loop (Core Gameplay)

**Actor:** User
**Trigger:** Within active scene
**Flow:**
```
LOOP:
  1. Display current context (location, present entities, recent turns)
  2. Await user input
  3. Parse intent:
     - Action ("I attack the orc")
     - Dialogue ("I say: Hello there")
     - Question ("What do I see?")
     - Meta-command (/end scene, /status, /roll)
  4. IF action requiring resolution:
     - Resolver.resolve(action, context)
     - Create ProposedChanges
  5. Narrator.generate_response(context, resolution)
  6. Append turns to MongoDB
  7. Check scene end conditions
  8. IF scene should end: → G-3
  9. ELSE: continue loop
```

---

### G-3: End Scene (Canonization)

**Actor:** Orchestrator/User
**Trigger:** Scene goal met, user command, or narrative signal
**Flow:**
1. Signal scene ending to user
2. Narrator generates scene closing
3. CanonKeeper.canonize_scene():
   - Fetch pending ProposedChanges
   - Evaluate each (authority, confidence, contradictions)
   - Accept → write to Neo4j
   - Reject → mark rejected with rationale
4. Update scene status to "completed"
5. Generate scene summary
6. Indexer embeds summary in Qdrant
7. Prompt: Start new scene or end session?

---

### G-4: In-Scene Actions

**Actor:** User
**Trigger:** User input during scene
**Sub-cases:**

#### G-4a: Physical Action
"I attack the orc" / "I pick the lock" / "I climb the wall"
- Resolver determines difficulty
- Roll dice (if applicable)
- Determine outcome
- Create ProposedChange (state changes)
- Narrator describes result

#### G-4b: Dialogue
"I say: We should work together"
- Narrator generates NPC response (if applicable)
- May trigger social mechanics
- Create memory for NPC (what was said)

#### G-4c: Observation
"What do I see?" / "I examine the door"
- ContextAssembly retrieves relevant facts
- Narrator describes based on canon
- May reveal hidden information

#### G-4d: Movement
"I go to the tavern" / "I enter the cave"
- Check if location exists
- Update character location (state_tag)
- Narrator describes new location
- May trigger new encounters

---

### G-5: Meta Commands (During Gameplay)

**Actor:** User
**Trigger:** Commands starting with `/`

| Command | Description |
|---------|-------------|
| `/status` | Show current scene status, participants, proposals |
| `/roll [dice]` | Roll dice (e.g., `/roll 1d20+5`) |
| `/end scene` | Signal scene end → G-3 |
| `/pause` | Save and exit to main menu |
| `/undo` | Undo last turn (if not canonized) |
| `/recap` | Show recent turns summary |
| `/entities` | List entities in scene |
| `/facts [entity]` | Show facts about entity |
| `/help` | Show available commands |

---

### G-6: Conversation Mode

**Actor:** User
**Trigger:** Engaging NPC in dialogue
**Flow:**
1. Enter focused dialogue with NPC
2. NPC uses personality, memories, facts to respond
3. Track conversation context
4. May trigger:
   - Information exchange
   - Relationship changes
   - Quest hooks
5. Exit to normal turn mode

---

### G-7: Combat Mode (Optional)

**Actor:** User
**Trigger:** Combat initiated
**Flow:**
1. Determine initiative order
2. Combat turn structure:
   - Current combatant acts
   - Resolve action
   - Check conditions (death, flee, surrender)
3. Track: HP, conditions, positioning
4. Exit when combat ends
5. Canonize combat results

---

## Category 6: Ingestion (I-)

### I-1: Upload Document

**Actor:** User
**Trigger:** Ingest → Upload
**Flow:**
1. Select file (PDF, EPUB, TXT, MD)
2. Select target universe (or create)
3. Prompt: Source type (manual, rulebook, lore, homebrew)
4. Upload to MinIO
5. Create Source node in Neo4j
6. Create Document record in MongoDB
7. Extract text → create Snippets
8. Embed snippets in Qdrant
9. Queue for entity extraction

---

### I-2: Extract Entities from Document

**Actor:** System
**Trigger:** After document upload
**Flow:**
1. LLM processes snippets
2. Identifies potential entities:
   - Characters (races, classes, named NPCs)
   - Locations
   - Objects (items, artifacts)
   - Concepts (magic systems, rules)
   - Factions
3. Creates ProposedChange for each
4. Links evidence to source snippets
5. Queue for user review

---

### I-3: Review Proposals

**Actor:** User
**Trigger:** Ingest → Review Proposals
**Flow:**
1. List pending proposals grouped by source
2. For each proposal:
   - Show extracted entity
   - Show source snippet (evidence)
   - Show confidence score
3. User actions:
   - Accept (→ canonize)
   - Edit and accept
   - Reject
   - Skip (decide later)
4. CanonKeeper processes accepted proposals

---

### I-4: Manage Sources

**Actor:** User
**Trigger:** Ingest → Manage Sources
**Flow:**
1. List uploaded sources
2. View: title, type, entity count, snippet count
3. Actions:
   - View details
   - Re-process (extract again)
   - Delete (soft delete)
   - Set authority level

---

## Category 7: Query & Exploration (Q-)

### Q-1: Search Canon

**Actor:** User
**Trigger:** Query → Search
**Flow:**
1. Prompt: Search query (natural language)
2. Qdrant semantic search
3. Retrieve matching entities, facts, scenes
4. Display ranked results
5. Allow drilling into results

---

### Q-2: Browse Entities

**Actor:** User
**Trigger:** Query → Browse Entities
**Flow:**
1. Select universe
2. Select entity type filter
3. Display entity list with key info
4. Select entity for details (C-4)

---

### Q-3: Timeline View

**Actor:** User
**Trigger:** Query → Timeline
**Flow:**
1. Select story or universe
2. Display chronological event timeline
3. Filter by: entity, event type, time range
4. Click event for details

---

### Q-4: Fact Explorer

**Actor:** User
**Trigger:** Query → Facts
**Flow:**
1. Select universe
2. Display facts with filters:
   - By entity
   - By canon_level
   - By authority
   - By time
3. Show fact with evidence links
4. Navigate to related entities

---

### Q-5: Relationship Graph

**Actor:** User
**Trigger:** Query → Relationships
**Flow:**
1. Select starting entity
2. Display relationship graph (visual or text)
3. Show: allies, enemies, members, locations
4. Navigate graph interactively

---

## Category 8: Configuration (CF-)

### CF-1: LLM Settings

**Actor:** User
**Trigger:** Settings → LLM
**Flow:**
1. Display current settings:
   - Model (claude-sonnet, claude-opus)
   - Temperature
   - Max tokens
2. Allow editing
3. Test connection
4. Save to config

---

### CF-2: Database Connections

**Actor:** User
**Trigger:** Settings → Databases
**Flow:**
1. Display connection status for each DB
2. Test connections
3. Edit connection strings
4. Reinitialize connections

---

### CF-3: User Preferences

**Actor:** User
**Trigger:** Settings → Preferences
**Flow:**
1. Display preferences:
   - Default universe
   - Auto-save frequency
   - Narrator verbosity
   - Dice display
2. Edit and save

---

### CF-4: Export Data

**Actor:** User
**Trigger:** Settings → Export
**Flow:**
1. Select export scope:
   - Entire database
   - Single universe
   - Single story
2. Select format (JSON, Markdown)
3. Generate export
4. Save to file

---

### CF-5: Import Data

**Actor:** User
**Trigger:** Settings → Import
**Flow:**
1. Select import file
2. Validate format
3. Preview import
4. Merge strategy (overwrite, append, skip conflicts)
5. Execute import
6. Report results

---

## Use Case Matrix

| ID | Name | Layer 3 (CLI) | Layer 2 (Agents) | Layer 1 (Data) |
|----|------|---------------|------------------|----------------|
| S-1 | Start App | `main.py` | - | Connection check |
| S-2 | Main Menu | `main.py` | - | - |
| U-1 | List Universes | `commands/manage.py` | - | `neo4j_tools` |
| U-2 | Create Universe | `commands/manage.py` | - | `neo4j_tools` |
| ST-2 | Create Story | `commands/play.py` | Orchestrator | `neo4j_tools`, `mongodb_tools` |
| C-2 | Create PC | `commands/manage.py` | - | `neo4j_tools`, `mongodb_tools` |
| G-2 | Turn Loop | `repl/session.py` | Orchestrator, Narrator, Resolver | All tools |
| G-3 | End Scene | `repl/session.py` | CanonKeeper, Indexer | `neo4j_tools`, `qdrant_tools` |
| I-1 | Upload Doc | `commands/ingest.py` | Indexer | `minio`, `mongodb_tools`, `qdrant_tools` |
| Q-1 | Search | `commands/query.py` | ContextAssembly | `qdrant_tools`, `neo4j_tools` |

---

## Implementation Priority

### Phase 1: Core Loop (MVP)
- S-1, S-2 (basic menu)
- U-2 (create universe)
- ST-2 (create story)
- G-1, G-2, G-3 (scene loop)
- G-4a, G-4b (actions, dialogue)

### Phase 2: Management
- U-1, U-3, U-4 (universe CRUD)
- ST-1, ST-3, ST-4 (story CRUD)
- C-1, C-2, C-4 (character CRUD)
- G-5 (meta commands)

### Phase 3: Ingestion
- I-1, I-2, I-3, I-4 (full ingestion pipeline)

### Phase 4: Query & Polish
- Q-1 through Q-5 (exploration)
- CF-1 through CF-5 (configuration)
- G-6, G-7 (advanced gameplay)

---

## References

- **Architecture:** `ARCHITECTURE.md`
- **Data Model:** `docs/ontology/ONTOLOGY.md`
- **Agent Roles:** `docs/architecture/AGENT_ORCHESTRATION.md`
- **Loops:** `docs/architecture/CONVERSATIONAL_LOOPS.md`
