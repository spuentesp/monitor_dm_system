# P-19: Procedural Scene Population - Behavior Definition

**Use Case ID:** P-19
**Last Updated:** 2026-05-19
**Status:** ✅ Defined

## Overview

Procedural Scene Population automatically generates content for new scenes using Random Tables. When the user moves to a new location, the system retrieves appropriate tables, rolls on them, generates entities, stages them in the scene, and canonizes permanent elements.

## Preconditions

1. **Active scene exists** in MongoDB
2. **User performs movement action** ("I go north", "I enter the cave")
3. **Target location is new** (not previously visited)
4. **Random Tables collection exists** in MongoDB (DL-21)
5. **Table definitions exist** for location type
6. **ContextAssembly** has prepared scene context

## User Actions

1. User performs movement action
   - Example: "I go north"
   - Example: "I enter the cave"
   - Example: "I head into the forest"

## System Actions

### Action 1: Detect Scene Transition

**Agent:** SceneLoop
**Method:** `detect_scene_transition(input: str) -> TransitionEvent`

- Parse user input for movement keywords:
  - Directional: "go north", "move south", "head east"
  - Entry: "enter", "into", "walk into"
  - Exit: "leave", "exit", "walk out of"
- Extract target location from input
- Determine if location is new (check Scene.turns for previous visits)
- Create TransitionEvent with:
  - `source_location`: current location
  - `target_location`: extracted location
  - `is_new`: boolean (check visitation history)

**Success Criteria:**
- Transition detection accuracy: ≥95%
- Location extraction accuracy: ≥90%
- New location detection: 100% accuracy

**Error Cases:**
- Input parsing fails → Ask user to clarify location
- Ambiguous location detected → Prompt user: "Which [location]?"

---

### Action 2: Check Location Visitation

**Agent:** SceneLoop
**Method:** `is_location_new(scene_id: str, location: str) -> bool`

- Query scene's turn history for previous mentions of location
- Search for location in Turn.content and Turn.metadata
- Check if location was previously entered or described
- Return `True` if never mentioned before

**Success Criteria:**
- New location detection: 100% accuracy
- False positive rate: ≤2%

**Error Cases:**
- Scene not found → Error, ask user to start scene
- Turn history corrupt → Assume location is new (conservative)

---

### Action 3: Retrieve Random Tables

**Agent:** SceneLoop
**Method:** `retrieve_random_tables(location: str) -> RandomTable[]`

- Query RandomTables collection for tables matching location type
- Filter by:
  - `location_type`: Matches target location (cave, forest, city, dungeon)
  - `world_id`: Matches current world
  - `is_active`: true
- Retrieve all tables for location type:
  - `encounters`: Entities to encounter
  - `features`: Environmental features
  - `loot`: Treasure items
  - `hazards`: Environmental hazards
- Return array of RandomTable documents

**Success Criteria:**
- Table retrieval: 100% success
- Correct location filtering: 100%
- All relevant tables returned: 100%

**Error Cases:**
- No tables found for location → Log warning, skip procedural generation
- Tables collection empty → Log warning, skip procedural generation
- Multiple tables for same type → Use all (roll on each)

---

### Action 4: Roll on Each Table

**Agent:** SceneLoop
**Method:** `roll_on_table(table: RandomTable) -> TableEntry[]`

- For each table, roll dice per table definition:
  - Parse `dice_formula` (e.g., "1d6", "2d6+2", "d20")
  - Execute dice roll
  - Map roll result to TableEntry via `roll_range` (e.g., "1-2", "3-5", "6")
- Retrieve TableEntry details:
  - `entry_id`: Unique identifier
  - `content`: Text description of entry
  - `entity_type`: If entry represents entity (NPC, item, hazard)
  - `quantity`: Number of entities to generate
  - `subtable_ref`: Reference to subtable (e.g., "goblin_loot")
- If `subtable_ref` present, recurse into subtable
- Return array of selected TableEntries

**Success Criteria:**
- Dice roll accuracy: 100%
- Roll range mapping: 100%
- Subtable resolution: 100%

**Error Cases:**
- Invalid dice_formula → Use default 1d6
- Roll out of range → Use nearest valid entry
- Subtable not found → Log error, skip subtable

---

### Action 5: Generate Entities

**Agent:** SceneLoop (via MCP tools)
**Method:** `generate_entities(table_entries: TableEntry[]) -> Entity[]`

- For each TableEntry with `entity_type`:
  - Parse entity data from entry content
  - Create EntityCreate:
    ```python
    EntityCreate(
        entity_type=entity_type,
        name=extract_name(entry.content),
        description=entry.content,
        properties=extract_properties(entry.content),
        world_id=world_id
    )
    ```
  - Call `create_entity` MCP tool
  - Receive Entity back with entity_id
- Store entities for staging

**Success Criteria:**
- Entity creation: 100% success
- Property extraction: ≥90% accuracy
- Entity_id assignment: 100%

**Error Cases:**
- Entity creation fails → Log error, skip entity
- Property extraction fails → Create with minimal properties

---

### Action 6: Stage Entities in Scene

**Agent:** SceneLoop
**Method:** `stage_entities(scene_id: str, entities: Entity[], is_permanent: bool[]) -> void`

- For each entity, determine canonization rules:
  - **Permanent:** Features, loot, named NPCs → Canonize to Neo4j
  - **Temporary:** One-off hazards, unnamed NPCs → Stage in scene only
- For permanent entities:
  - Create ProposedChange for canonization
  - Submit to CanonKeeper
  - CanonKeeper evaluates and commits to Neo4j
- For temporary entities:
  - Add to scene's `staged_entities` array
  - Mark with `temporary: true`
- Update scene's `entity_registry` with all entities

**Success Criteria:**
- Permanent entity canonization: 100%
- Temporary entity staging: 100%
- Registry update: 100%

**Error Cases:**
- CanonKeeper unavailable → Stage as temporary, log warning
- Canonization rejected → Stage as temporary, log reason

---

### Action 7: Generate Prompt for Narrator

**Agent:** ContextAssembly
**Method:** `generate_scene_opening_prompt(scene: Scene, entities: Entity[]) -> str`

- Compile scene context:
  - Location description
  - Generated entities (permanent and temporary)
  - Previous turn context
  - World tone and themes
- Construct narrator prompt:
  ```
  The player has entered [location]. Describe the scene opening.
  Include the following generated elements:
  - [Entity 1]: [description]
  - [Entity 2]: [description]
  
  Maintain consistency with previous events.
  Keep the tone [world_tone].
  ```
- Return prompt

**Success Criteria:**
- Prompt completeness: 100% (all entities included)
- Context integration: 100% (previous events included)

**Error Cases:**
- Prompt generation fails → Use fallback: "The player enters [location]."

---

### Action 8: Append Turns

**Agent:** SceneLoop
**Method:** `append_procedural_turns(scene_id: str, movement: str, description: str) -> Turn[]`

- Create user turn:
  ```python
  TurnCreate(
      speaker_id=user_id,
      turn_type=TurnType.MOVEMENT,
      content=movement,
      metadata={"scene_transition": True, "target_location": location}
  )
  ```
- Narrator generates scene opening from prompt
- Create GM turn:
  ```python
  TurnCreate(
      speaker_id="system:procedural",
      turn_type=TurnType.SCENE_START,
      content=description,
      metadata={
          "procedural_generation": True,
          "tables_used": [table_ids],
          "entities_generated": [entity_ids],
          "entities_canonized": permanent_entity_ids
      }
  )
  ```
- Append both turns to scene
- Update scene's `current_location`

**Success Criteria:**
- Turn creation: 100% success
- Metadata completeness: 100% (tables, entities, canonization all tracked)
- Append success: 100%

**Error Cases:**
- Narrator fails → Return list of generated entities as text
- Turn append fails → Error, cache for retry

---

## Postconditions

1. **Scene populated** with entities from random tables
2. **Permanent entities canonized** in Neo4j
3. **Temporary entities staged** in scene
4. **User turn appended** with movement action
5. **GM turn appended** with scene opening
6. **Scene current_location updated** to new location

## Success Criteria

1. **Transition detection accuracy:** ≥95%
2. **New location detection:** 100% accuracy
3. **Table retrieval:** 100% success
4. **Dice roll accuracy:** 100%
5. **Entity creation:** 100% success
6. **Canonization rules followed:** 100% (permanent vs temporary)
7. **Narrator integration:** 100% (all generated entities described)
8. **End-to-end latency:** ≤5 seconds

## Error Cases

| Error | Detection | Handling |
|-------|-----------|----------|
| Input parsing fails | Parse returns error | Ask user to clarify location |
| Ambiguous location | Multiple location matches | Prompt user to clarify |
| Scene not found | Scene lookup returns None | Error, ask to start scene |
| No tables found | Tables query returns empty | Log warning, skip procedural generation |
| Invalid dice_formula | Dice parse exception | Use default 1d6 |
| Roll out of range | Roll value has no matching entry | Use nearest valid entry |
| Subtable not found | Subtable query returns empty | Log error, skip subtable |
| Entity creation fails | Entity MCP tool returns error | Log error, skip entity |
| CanonKeeper unavailable | Canon call times out | Stage as temporary, log warning |
| Canonization rejected | CanonKeeper returns conflict | Stage as temporary, log reason |
| Narrator fails | Narrator returns error | Return list of entities as text |

## Test Scenarios

### Scenario 1: Cave with Goblins and Treasure

**Given:**
- Scene with current_location="forest_edge"
- RandomTables for "cave" exists:
  - encounters: {1-2: nothing, 3-4: "3 goblins", 5-6: "1 ogre"}
  - loot: {1-3: "50 gold", 4-6: "ancient sword"}
  - features: {1-3: "stalactites", 4-6: "underground lake"}

**When:**
- User enters: "I go into the cave"
- Scene transition detected
- Roll encounters: 4 → "3 goblins"
- Roll loot: 5 → "ancient sword"
- Roll features: 2 → "stalactites"

**Then:**
- 3 goblin entities created (temporary, unnamed)
- Ancient sword entity created (permanent, loot)
- Stalactites entity created (permanent, feature)
- CanonKeeper canonizes sword and stalactites
- Goblins staged as temporary in scene
- Narrator describes: "The cave interior is dimly lit, sharp stalactites hanging from the ceiling like stone daggers. Three goblins huddle around a small campfire, and in the corner you glimpse the gleam of an ancient sword."
- User turn appended with metadata `scene_transition: True`, `target_location: cave`
- GM turn appended with metadata `procedural_generation: True`, `entities_generated: [goblin_ids, sword_id, stalactites_id]`

---

### Scenario 2: Already Visited Location (No Procedural Generation)

**Given:**
- Scene with current_location="town_square"
- Turn history shows previous visit to "market"

**When:**
- User enters: "I go to the market"

**Then:**
- Scene transition detected
- is_location_new returns False
- No procedural generation triggered
- Narrator describes: "You return to the bustling market, vendors hawking their wares as before."
- User turn appended
- GM turn appended WITHOUT `procedural_generation` metadata

**Note:** Only new locations trigger procedural generation.

---

### Scenario 3: No Tables Found (Fallback)

**Given:**
- Scene with current_location="forest_edge"
- RandomTables collection has no entries for "forest"

**When:**
- User enters: "I go into the forest"

**Then:**
- Scene transition detected
- retrieve_random_tables returns empty array
- Warning logged: "No tables found for location type: forest"
- No procedural generation performed
- Narrator describes: "You enter the forest, trees stretching endlessly around you."
- User turn appended
- GM turn appended WITHOUT `procedural_generation` metadata

**Note:** Graceful degradation when tables are missing.

---

### Scenario 4: Canonization Rules (Permanent vs Temporary)

**Given:**
- RandomTables for "dungeon" exists:
  - encounters: {1-3: "skeleton", 4-6: "named skeleton Grak"}
  - loot: {1-2: "10 gold", 3-6: "enchanted ring"}
  - features: {1-3: "torch sconce", 4-6: "ancient fresco"}

**When:**
- User enters: "I go into the dungeon"
- Roll encounters: 6 → "named skeleton Grak"
- Roll loot: 5 → "enchanted ring"
- Roll features: 5 → "ancient fresco"

**Then:**
- Skeleton Grak entity created (PERMANENT: named NPC)
- Enchanted ring entity created (PERMANENT: loot)
- Ancient fresco entity created (PERMANENT: feature)
- All three canonized by CanonKeeper
- All committed to Neo4j with canon_level=cards
- Narrator describes all three in scene opening
- GM turn metadata shows `entities_canonized: [grak_id, ring_id, fresco_id]`

**Contrast with unnamed skeleton:**
- If roll=2 → "skeleton"
- Skeleton entity created (TEMPORARY: unnamed NPC)
- Not canonized, staged in scene only
- Marked with `temporary: true`

---

### Scenario 5: Subtable References (Nested Generation)

**Given:**
- RandomTables for "goblin_lair" exists:
  - encounters: {1-4: "2 goblins", 5-6: "goblin chief"}
  - loot: {1-3: "rusty dagger", 4-6: "shiny gem"}
- Subtable "goblin_chief_loot" exists:
  - loot: {1-2: "100 gold", 3-6: "magic amulet"}

**When:**
- User enters: "I go into the goblin lair"
- Roll encounters: 6 → "goblin chief"
- Roll loot: 5 → "shiny gem"
- Chief entry has subtable_ref="goblin_chief_loot"
- System recurses into subtable
- Roll on subtable: 5 → "magic amulet"

**Then:**
- Goblin chief entity created (permanent, named NPC)
- Shiny gem entity created (permanent, loot)
- Magic amulet entity created (permanent, loot)
- All three canonized
- Narrator describes: "The goblin chief stands before you, a shiny gem clutched in one hand and a glowing magic amulet around his neck."
- GM turn metadata shows `tables_used: [goblin_lair_id, goblin_chief_loot_id]`

**Note:** Subtables allow nested procedural generation.

---

## Contradictions Check

### Check with P-18: Oracle

| Aspect | P-19 | P-18 | Contradiction? | Resolution |
|--------|------|------|----------------|------------|
| **Trigger** | Movement | Questions | ✅ No | Different patterns |
| **Purpose** | Generate content | Answer facts | ✅ No | Complementary |
| **Dice** | Table rolls (1d6, 2d6) | 1d100 (oracle) | ✅ No | Different dice |
| **Canonization** | Entities | Oracle facts | ✅ No | Different types |
| **Narrator** | Scene opening | Oracle response | ✅ No | Different contexts |
| **Turns** | MOVEMENT/SCENE_START | QUESTION/ORACLE_RESPONSE | ✅ No | Different types |

**Result:** ✅ NO CONTRADICTIONS

**Notes:**
- P-19 and P-18 can be used together: P-19 generates scene, then P-18 answers questions about it
- Both canonize at `canon_level=cards`, but different entity types
- Both use Narrator, but for different purposes

---

## Dependencies

### Use Case Dependencies

- **P-2: Turn Loop** - Provides turn structure and append mechanism
- **P-3: Scene Lifecycle** - Provides scene creation and current_location tracking
- **P-4: Resolve Action** - Provides action parsing
- **DL-21: Random Tables** - Provides table storage and retrieval

### Layer Dependencies

- **Data-Layer:**
  - DL-1: Entity Schema (Entity entity, entity_type, properties)
  - DL-2: Turn Schema (Turn entity, turn_type, metadata)
  - DL-3: Scene Schema (Scene entity, current_location, entity_registry)
  - DL-4: ProposedChange Schema (canonization workflow)
  - DL-5: CanonKeeper (Entity evaluation and commitment)
  - DL-21: Random Tables (RandomTable collection, TableEntry structure)

- **Agents:**
  - SceneLoop (detect_scene_transition, retrieve_random_tables, roll_on_table)
  - ContextAssembly (generate_scene_opening_prompt)
  - CanonKeeper (canonize_permanent_entities)
  - NarratorAgent (describe_procedural_scene)

### External Dependencies

- MongoDB (RandomTables, Turn, Scene storage)
- Neo4j (Canon entity storage)
- LLM (Narrator)
- Dice system (table rolls)

---

## Implementation Notes

### Performance Considerations

1. **Caching:** Cache RandomTables for location types
2. **Async operations:** CanonKeeper evaluation is async, don't block on it
3. **Batch entity creation:** Create all entities in parallel

### Security Considerations

1. **Canonization rules:** Permanent vs temporary must be strictly enforced
2. **Table filtering:** Only retrieve tables for active world
3. **Subtable recursion:** Limit recursion depth to prevent infinite loops

### User Experience

1. **Natural descriptions:** Procedural content should feel hand-crafted, not random
2. **Consistency:** Generated entities should be consistent with world tone
3. **Discovery:** Players should feel like they're discovering, not rolling dice

### Known Limitations

1. **Depends on tables:** Requires pre-authored Random Tables for each location type
2. **Binary new/old:** Doesn't handle "partially explored" locations well
3. **No adaptation:** Doesn't adapt generated content to player level or party composition