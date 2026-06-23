# P-19: Procedural Scene Population - Contract Specifications

## Overview

Procedural Scene Population automatically generates content for new scenes using Random Tables. When the user moves to a new location, the system retrieves appropriate tables, rolls on them, generates entities, stages them in the scene, and canonizes permanent elements.

---

## Layer 1: Data Layer Contracts

### MongoDB: GetScene

**Purpose:** Retrieve a scene by its ID from MongoDB.

**Signature:**
```python
def mongodb_get_scene(scene_id: str) -> Optional[Scene]:
    """
    Retrieve a scene by its ID from MongoDB.
    
    Args:
        scene_id: ID of the scene to retrieve
    
    Returns:
        Optional[Scene]: Scene entity if found, None otherwise
    
    Raises:
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene to retrieve

**Returns:**
- `Optional[Scene]`: Scene entity if found, None otherwise

**Raises:**
- `DatabaseError`: If database operation fails

**Example:**
```python
scene = mongodb_get_scene("scene_456")
if scene is None:
    raise ValueError("Scene not found")
current_location = scene.current_location
```

---

### MongoDB: UpdateScene

**Purpose:** Update a scene's metadata (e.g., current_location, entity_registry) in MongoDB.

**Signature:**
```python
def mongodb_update_scene(
    scene_id: str,
    updates: Dict[str, Any]
) -> Scene:
    """
    Update a scene's metadata in MongoDB.
    
    Args:
        scene_id: ID of the scene to update
        updates: Dictionary of fields to update
    
    Returns:
        Scene: Updated Scene entity
    
    Raises:
        ValidationError: If update fields are invalid
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene to update
- `updates` (Dict[str, Any]): Dictionary of fields to update

**Returns:**
- `Scene`: Updated Scene entity

**Raises:**
- `ValidationError`: If update fields are invalid
- `DatabaseError`: If database operation fails

**Example:**
```python
updated_scene = mongodb_update_scene(
    "scene_456",
    {
        "current_location": "cave_entrance",
        "entity_registry": ["entity_1", "entity_2", "entity_3"]
    }
)
```

---

### MongoDB: ListTurns

**Purpose:** Query scene's turn history for previous mentions of location.

**Signature:**
```python
def mongodb_list_turns(
    scene_id: str,
    filters: Optional[Dict[str, Any]] = None
) -> List[Turn]:
    """
    Query scene's turn history.
    
    Args:
        scene_id: ID of the scene
        filters: Optional filters (e.g., {"turn_type": "MOVEMENT"})
    
    Returns:
        List[Turn]: List of turns matching filters
    
    Raises:
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene
- `filters` (Optional[Dict[str, Any]]): Optional filters

**Returns:**
- `List[Turn]`: List of turns matching filters

**Raises:**
- `DatabaseError`: If database operation fails

**Example:**
```python
turns = mongodb_list_turns("scene_456")
location_mentioned = False
for turn in turns:
    if "market" in turn.content.lower():
        location_mentioned = True
        break
```

---

### MongoDB: QueryRandomTables

**Purpose:** Query RandomTables collection for tables matching location type.

**Signature:**
```python
def mongodb_query_random_tables(
    location_type: str,
    world_id: str,
    is_active: bool = True
) -> List[RandomTable]:
    """
    Query RandomTables collection for tables matching location type.
    
    Args:
        location_type: Type of location (e.g., "cave", "forest", "city")
        world_id: ID of the current world
        is_active: Filter to active tables only (default: True)
    
    Returns:
        List[RandomTable]: List of tables matching criteria
    
    Raises:
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `location_type` (str): Type of location (e.g., "cave", "forest", "city")
- `world_id` (str): ID of the current world
- `is_active` (bool): Filter to active tables only (default: True)

**Returns:**
- `List[RandomTable]`: List of tables matching criteria

**Raises:**
- `DatabaseError`: If database operation fails

**Example:**
```python
tables = mongodb_query_random_tables(
    location_type="cave",
    world_id="world_123"
)
assert len(tables) > 0
```

---

### MongoDB: GetRandomTable

**Purpose:** Retrieve a specific RandomTable by table_id (for subtable resolution).

**Signature:**
```python
def mongodb_get_random_table(table_id: str) -> Optional[RandomTable]:
    """
    Retrieve a specific RandomTable by table_id.
    
    Args:
        table_id: ID of the table to retrieve
    
    Returns:
        Optional[RandomTable]: RandomTable if found, None otherwise
    
    Raises:
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `table_id` (str): ID of the table to retrieve

**Returns:**
- `Optional[RandomTable]`: RandomTable if found, None otherwise

**Raises:**
- `DatabaseError`: If database operation fails

**Example:**
```python
subtable = mongodb_get_random_table("goblin_chief_loot")
if subtable is None:
    logger.warning(f"Subtable not found: goblin_chief_loot")
```

---

### MongoDB: TurnCreate

**Purpose:** Create a new Turn entity in MongoDB.

**Signature:**
```python
def mongodb_create_turn(
    speaker_id: str,
    turn_type: TurnType,
    content: str,
    scene_id: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Turn:
    """
    Create a new Turn entity in MongoDB.
    
    Args:
        speaker_id: ID of the speaker
        turn_type: Type of turn
        content: Text content of the turn
        scene_id: ID of the scene
        metadata: Optional metadata
    
    Returns:
        Turn: Created Turn entity with assigned turn_id
    
    Raises:
        ValidationError: If required fields are missing or invalid
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `speaker_id` (str): ID of the speaker
- `turn_type` (TurnType): Type of turn (from enum)
- `content` (str): Text content of the turn
- `scene_id` (str): ID of the scene
- `metadata` (Optional[Dict[str, Any]]): Optional metadata

**Returns:**
- `Turn`: Created Turn entity with assigned turn_id

**Raises:**
- `ValidationError`: If required fields are missing or invalid
- `DatabaseError`: If database operation fails

**Example:**
```python
# User turn
user_turn = mongodb_create_turn(
    speaker_id="user_123",
    turn_type=TurnType.MOVEMENT,
    content="I go into the cave",
    scene_id="scene_456",
    metadata={"scene_transition": True, "target_location": "cave"}
)

# GM turn
gm_turn = mongodb_create_turn(
    speaker_id="system:procedural",
    turn_type=TurnType.SCENE_START,
    content="The cave interior is dimly lit...",
    scene_id="scene_456",
    metadata={
        "procedural_generation": True,
        "tables_used": ["table_1", "table_2"],
        "entities_generated": ["entity_1", "entity_2"],
        "entities_canonized": ["entity_2"]
    }
)
```

---

### Neo4j: CanonKeeper - Evaluate Entity

**Purpose:** CanonKeeper evaluates an entity for consistency before committing to Neo4j.

**Signature:**
```python
async def canonkeeper_evaluate_entity(entity: Entity) -> CanonEvaluationResult:
    """
    Evaluate an entity for consistency before committing to Neo4j.
    
    Args:
        entity: Entity to evaluate
    
    Returns:
        CanonEvaluationResult: Evaluation result with verdict and explanations
    
    Raises:
        CanonKeeperError: If CanonKeeper is unavailable
    """
    pass
```

**Parameters:**
- `entity` (Entity): Entity to evaluate

**Returns:**
- `CanonEvaluationResult`: Evaluation result with verdict and explanations
  - `verdict` (CanonVerdict): ACCEPT, REJECT, DEFER, or NEEDS_REVIEW
  - `explanation` (str): Explanation for the verdict
  - `conflicts` (List[str]): List of conflicting entities (if any)

**Raises:**
- `CanonKeeperError`: If CanonKeeper is unavailable

**Example:**
```python
evaluation = await canonkeeper_evaluate_entity(entity)
if evaluation.verdict == CanonVerdict.ACCEPT:
    # Entity is consistent, can commit
    pass
elif evaluation.verdict == CanonVerdict.REJECT:
    # Entity conflicts with canon
    logger.warning(f"Entity rejected: {evaluation.explanation}")
```

---

### Neo4j: CanonKeeper - Commit Entity

**Purpose:** CanonKeeper commits an entity to Neo4j as canonical truth.

**Signature:**
```python
async def canonkeeper_commit_entity(entity: Entity) -> str:
    """
    Commit an entity to Neo4j as canonical truth.
    
    Args:
        entity: Entity to commit
    
    Returns:
        str: Neo4j node ID of the committed entity
    
    Raises:
        CanonKeeperError: If CanonKeeper is unavailable
        ConsistencyError: If entity conflicts with existing canon
    """
    pass
```

**Parameters:**
- `entity` (Entity): Entity to commit

**Returns:**
- `str`: Neo4j node ID of the committed entity

**Raises:**
- `CanonKeeperError`: If CanonKeeper is unavailable
- `ConsistencyError`: If entity conflicts with existing canon

**Example:**
```python
neo4j_id = await canonkeeper_commit_entity(entity)
logger.info(f"Entity committed to Neo4j with ID: {neo4j_id}")
```

---

### MCP Tool: Create Entity

**Purpose:** Create a new Entity entity via MCP tool.

**Signature:**
```python
async def mcp_create_entity(
    entity_type: EntityType,
    name: str,
    description: str,
    properties: Dict[str, Any],
    world_id: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Entity:
    """
    Create a new Entity entity via MCP tool.
    
    Args:
        entity_type: Type of entity (e.g., EntityType.NPC, EntityType.ITEM)
        name: Name of the entity
        description: Description of the entity
        properties: Entity properties (e.g., {"hp": 10, "attack": 5})
        world_id: ID of the world
        metadata: Optional metadata
    
    Returns:
        Entity: Created Entity with assigned entity_id
    
    Raises:
        ValidationError: If required fields are missing or invalid
        MCPCallError: If MCP tool call fails
    """
    pass
```

**Parameters:**
- `entity_type` (EntityType): Type of entity (from enum)
- `name` (str): Name of the entity
- `description` (str): Description of the entity
- `properties` (Dict[str, Any]): Entity properties
- `world_id` (str): ID of the world
- `metadata` (Optional[Dict[str, Any]]): Optional metadata

**Returns:**
- `Entity`: Created Entity with assigned entity_id

**Raises:**
- `ValidationError`: If required fields are missing or invalid
- `MCPCallError`: If MCP tool call fails

**Example:**
```python
entity = await mcp_create_entity(
    entity_type=EntityType.NPC,
    name="Goblin",
    description="A green-skinned creature with pointed ears and sharp teeth.",
    properties={"hp": 10, "attack": 5, "defense": 3},
    world_id="world_123",
    metadata={"temporary": True}
)
assert entity.entity_id is not None
```

---

## Layer 2: Agent Contracts

### SceneLoop.detect_scene_transition

**Purpose:** Detect if user input is a scene transition (movement) and extract target location.

**Signature:**
```python
def detect_scene_transition(input: str) -> TransitionEvent:
    """
    Detect if user input is a scene transition (movement).
    
    Parse user input for movement keywords:
    - Directional: "go north", "move south", "head east"
    - Entry: "enter", "into", "walk into"
    - Exit: "leave", "exit", "walk out of"
    
    Args:
        input: User input string
    
    Returns:
        TransitionEvent: Transition event with source_location, target_location, is_new
    
    Raises:
        ParseError: If input parsing fails
    """
    pass
```

**Parameters:**
- `input` (str): User input string

**Returns:**
- `TransitionEvent`: Transition event with:
  - `source_location` (str): Current location
  - `target_location` (str): Target location extracted from input
  - `is_new` (bool): Whether location is new (to be determined by is_location_new)

**Raises:**
- `ParseError`: If input parsing fails

**Example:**
```python
event = detect_scene_transition("I go into the cave")
assert event.target_location == "cave"
```

---

### SceneLoop.is_location_new

**Purpose:** Determine if a location has been previously visited in the scene.

**Signature:**
```python
def is_location_new(scene_id: str, location: str) -> bool:
    """
    Determine if a location has been previously visited in the scene.
    
    Query scene's turn history for previous mentions of location.
    Search for location in Turn.content and Turn.metadata.
    
    Args:
        scene_id: ID of the scene
        location: Location name to search for
    
    Returns:
        bool: True if location has never been mentioned before
    
    Raises:
        DatabaseError: If turn history query fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene
- `location` (str): Location name to search for

**Returns:**
- `bool`: True if location has never been mentioned before

**Raises:**
- `DatabaseError`: If turn history query fails

**Example:**
```python
is_new = is_location_new("scene_456", "cave")
if is_new:
    # Trigger procedural generation
    pass
```

---

### SceneLoop.retrieve_random_tables

**Purpose:** Retrieve random tables for a given location type.

**Signature:**
```python
def retrieve_random_tables(
    location: str,
    world_id: str
) -> List[RandomTable]:
    """
    Retrieve random tables for a given location type.
    
    Query RandomTables collection for tables matching location type.
    Filter by location_type, world_id, is_active.
    
    Args:
        location: Target location (e.g., "cave", "forest", "city")
        world_id: ID of the current world
    
    Returns:
        List[RandomTable]: List of tables for location type
    
    Raises:
        DatabaseError: If table query fails
    """
    pass
```

**Parameters:**
- `location` (str): Target location
- `world_id` (str): ID of the current world

**Returns:**
- `List[RandomTable]`: List of tables for location type

**Raises:**
- `DatabaseError`: If table query fails

**Example:**
```python
tables = retrieve_random_tables("cave", "world_123")
assert len(tables) > 0
```

---

### SceneLoop.roll_on_table

**Purpose:** Roll on a random table and select entries based on dice results.

**Signature:**
```python
def roll_on_table(
    table: RandomTable,
    subtables: Optional[Dict[str, RandomTable]] = None
) -> List[TableEntry]:
    """
    Roll on a random table and select entries based on dice results.
    
    For each table, roll dice per table definition:
    - Parse dice_formula (e.g., "1d6", "2d6+2", "d20")
    - Execute dice roll
    - Map roll result to TableEntry via roll_range
    - Retrieve TableEntry details (entry_id, content, entity_type, quantity, subtable_ref)
    - If subtable_ref present, recurse into subtable
    
    Args:
        table: RandomTable to roll on
        subtables: Optional dictionary of pre-loaded subtables
    
    Returns:
        List[TableEntry]: List of selected table entries
    
    Raises:
        DiceParseError: If dice_formula is invalid
        DiceRollError: If dice roll fails
    """
    pass
```

**Parameters:**
- `table` (RandomTable): RandomTable to roll on
- `subtables` (Optional[Dict[str, RandomTable]]): Optional dictionary of pre-loaded subtables

**Returns:**
- `List[TableEntry]`: List of selected table entries

**Raises:**
- `DiceParseError`: If dice_formula is invalid
- `DiceRollError`: If dice roll fails

**Example:**
```python
entries = roll_on_table(table)
for entry in entries:
    print(f"{entry.content} (entity_type: {entry.entity_type})")
```

---

### SceneLoop.stage_entities

**Purpose:** Stage generated entities in the scene, canonizing permanent ones.

**Signature:**
```python
async def stage_entities(
    scene_id: str,
    entities: Entity[],
    is_permanent: bool[]
) -> None:
    """
    Stage generated entities in the scene, canonizing permanent ones.
    
    Determine canonization rules:
    - Permanent: Features, loot, named NPCs → Canonize to Neo4j
    - Temporary: One-off hazards, unnamed NPCs → Stage in scene only
    
    For permanent entities:
    - Create ProposedChange for canonization
    - Submit to CanonKeeper
    - CanonKeeper evaluates and commits to Neo4j
    
    For temporary entities:
    - Add to scene's staged_entities array
    - Mark with temporary: true
    
    Update scene's entity_registry with all entities.
    
    Args:
        scene_id: ID of the scene
        entities: List of entities to stage
        is_permanent: List of booleans indicating which entities are permanent
    
    Raises:
        DatabaseError: If scene update fails
        CanonKeeperError: If canonization fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene
- `entities` (Entity[]): List of entities to stage
- `is_permanent` (bool[]): List of booleans indicating which entities are permanent

**Returns:**
- None

**Raises:**
- `DatabaseError`: If scene update fails
- `CanonKeeperError`: If canonization fails

**Example:**
```python
entities = [goblin, sword, stalactites]
is_permanent = [False, True, True]
await stage_entities("scene_456", entities, is_permanent)
# Goblins staged as temporary, sword and stalactites canonized
```

---

### ContextAssembly.generate_scene_opening_prompt

**Purpose:** Generate a prompt for the Narrator to describe the scene opening.

**Signature:**
```python
def generate_scene_opening_prompt(
    scene: Scene,
    entities: Entity[],
    previous_turns: List[Turn]
) -> str:
    """
    Generate a prompt for the Narrator to describe the scene opening.
    
    Compile scene context:
    - Location description
    - Generated entities (permanent and temporary)
    - Previous turn context
    - World tone and themes
    
    Construct narrator prompt.
    
    Args:
        scene: Scene entity
        entities: List of generated entities
        previous_turns: List of previous turns for context
    
    Returns:
        str: Narrator prompt
    
    Raises:
        PromptGenerationError: If prompt generation fails
    """
    pass
```

**Parameters:**
- `scene` (Scene): Scene entity
- `entities` (Entity[]): List of generated entities
- `previous_turns` (List[Turn]): List of previous turns for context

**Returns:**
- `str`: Narrator prompt

**Raises:**
- `PromptGenerationError`: If prompt generation fails

**Example:**
```python
prompt = generate_scene_opening_prompt(scene, entities, turns)
assert "cave" in prompt.lower()
assert "goblin" in prompt.lower()
```

---

### SceneLoop.append_procedural_turns

**Purpose:** Create and append user and GM turns for scene transition.

**Signature:**
```python
async def append_procedural_turns(
    scene_id: str,
    movement: str,
    description: str,
    user_id: str,
    location: str,
    tables_used: List[str],
    entities_generated: List[str],
    entities_canonized: List[str]
) -> Tuple[Turn, Turn]:
    """
    Create and append user and GM turns for scene transition.
    
    Create user turn (MOVEMENT).
    Create GM turn (SCENE_START).
    Append both turns to scene.
    Update scene's current_location.
    
    Args:
        scene_id: ID of the scene
        movement: User's movement input
        description: GM's narrative description
        user_id: ID of the user
        location: Target location
        tables_used: List of table IDs used
        entities_generated: List of entity IDs generated
        entities_canonized: List of entity IDs canonized
    
    Returns:
        Tuple[Turn, Turn]: Tuple of (user_turn, gm_turn)
    
    Raises:
        DatabaseError: If turn creation or append fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene
- `movement` (str): User's movement input
- `description` (str): GM's narrative description
- `user_id` (str): ID of the user
- `location` (str): Target location
- `tables_used` (List[str]): List of table IDs used
- `entities_generated` (List[str]): List of entity IDs generated
- `entities_canonized` (List[str]): List of entity IDs canonized

**Returns:**
- `Tuple[Turn, Turn]`: Tuple of (user_turn, gm_turn)

**Raises:**
- `DatabaseError`: If turn creation or append fails

**Example:**
```python
user_turn, gm_turn = await append_procedural_turns(
    scene_id="scene_456",
    movement="I go into the cave",
    description="The cave interior is dimly lit...",
    user_id="user_123",
    location="cave",
    tables_used=["table_1", "table_2"],
    entities_generated=["entity_1", "entity_2", "entity_3"],
    entities_canonized=["entity_2", "entity_3"]
)
assert user_turn.turn_type == TurnType.MOVEMENT
assert gm_turn.turn_type == TurnType.SCENE_START
```

---

## Layer 3: CLI Contracts

**No specific CLI command.** Procedural Scene Population is an automated system triggered by movement actions. The user performs normal movement commands ("I go north", "I enter the cave"), and the system automatically detects scene transitions and generates content for new locations.

---

## Integration Tests

### Test 1: Cave with Goblins and Treasure

**Setup:**
```python
# Create test scene
scene = create_test_scene(current_location="forest_edge", world_id="world_123")

# Create random tables for cave
table_encounters = create_random_table(
    table_type="encounters",
    location_type="cave",
    world_id="world_123",
    dice_formula="1d6",
    entries=[
        {"roll_range": "1-2", "content": "nothing", "entity_type": None},
        {"roll_range": "3-4", "content": "3 goblins", "entity_type": EntityType.NPC, "quantity": 3},
        {"roll_range": "5-6", "content": "1 ogre", "entity_type": EntityType.NPC, "quantity": 1}
    ]
)

table_loot = create_random_table(
    table_type="loot",
    location_type="cave",
    world_id="world_123",
    dice_formula="1d6",
    entries=[
        {"roll_range": "1-3", "content": "50 gold", "entity_type": EntityType.ITEM},
        {"roll_range": "4-6", "content": "ancient sword", "entity_type": EntityType.ITEM}
    ]
)

table_features = create_random_table(
    table_type="features",
    location_type="cave",
    world_id="world_123",
    dice_formula="1d6",
    entries=[
        {"roll_range": "1-3", "content": "stalactites", "entity_type": EntityType.FEATURE},
        {"roll_range": "4-6", "content": "underground lake", "entity_type": EntityType.FEATURE}
    ]
)
```

**Execute:**
```python
# Detect scene transition
event = detect_scene_transition("I go into the cave")
assert event.target_location == "cave"

# Check if location is new
is_new = is_location_new(scene.scene_id, "cave")
assert is_new == True

# Retrieve random tables
tables = retrieve_random_tables("cave", scene.world_id)
assert len(tables) == 3

# Roll on tables with mocked dice
with patch('monitor_agents.scene_loop.roll_dice', side_effect=[4, 5, 2]):
    entries_encounters = roll_on_table(table_encounters)
    entries_loot = roll_on_table(table_loot)
    entries_features = roll_on_table(table_features)

assert len(entries_encounters) == 1
assert "goblins" in entries_encounters[0].content.lower()
assert len(entries_loot) == 1
assert "sword" in entries_loot[0].content.lower()
assert len(entries_features) == 1
assert "stalactites" in entries_features[0].content.lower()

# Generate entities
entities = []
is_permanent = []

for entry in entries_encounters + entries_loot + entries_features:
    if entry.entity_type:
        entity = await mcp_create_entity(
            entity_type=entry.entity_type,
            name=extract_name(entry.content),
            description=entry.content,
            properties=extract_properties(entry.content),
            world_id=scene.world_id,
            metadata={"temporary": entry.entity_type == EntityType.NPC and not is_named(entry.content)}
        )
        entities.append(entity)
        is_permanent.append(entry.entity_type != EntityType.NPC or is_named(entry.content))

# Stage entities
await stage_entities(scene.scene_id, entities, is_permanent)

# Generate narrator prompt
prompt = generate_scene_opening_prompt(scene, entities, [])
assert "cave" in prompt.lower()
assert len(entities) == 3

# Generate narrative description
description = await narrator_generate(prompt)
assert description is not None

# Append turns
user_turn, gm_turn = await append_procedural_turns(
    scene_id=scene.scene_id,
    movement="I go into the cave",
    description=description,
    user_id="user_123",
    location="cave",
    tables_used=[table_encounters.table_id, table_loot.table_id, table_features.table_id],
    entities_generated=[e.entity_id for e in entities],
    entities_canonized=[entities[1].entity_id, entities[2].entity_id]  # sword and stalactites
)
```

**Assert:**
```python
# Verify all steps succeeded
assert user_turn.turn_type == TurnType.MOVEMENT
assert gm_turn.turn_type == TurnType.SCENE_START
assert gm_turn.metadata["procedural_generation"] == True
assert len(gm_turn.metadata["entities_generated"]) == 3
assert len(gm_turn.metadata["entities_canonized"]) == 2
```

---

### Test 2: Already Visited Location (No Procedural Generation)

**Setup:**
```python
# Create test scene with previous visit
scene = create_test_scene(current_location="town_square", world_id="world_123")

# Create previous turn mentioning market
mongodb_create_turn(
    speaker_id="user_123",
    turn_type=TurnType.MOVEMENT,
    content="I go to the market",
    scene_id=scene.scene_id,
    metadata={"target_location": "market"}
)
```

**Execute:**
```python
# Detect scene transition
event = detect_scene_transition("I go to the market")
assert event.target_location == "market"

# Check if location is new
is_new = is_location_new(scene.scene_id, "market")
assert is_new == False

# No procedural generation should be triggered
```

**Assert:**
```python
# Verify procedural generation was skipped
assert is_new == False
```

---

### Test 3: No Tables Found (Fallback)

**Setup:**
```python
# Create test scene
scene = create_test_scene(current_location="forest_edge", world_id="world_123")

# No random tables for forest
```

**Execute:**
```python
# Detect scene transition
event = detect_scene_transition("I go into the forest")
assert event.target_location == "forest"

# Check if location is new
is_new = is_location_new(scene.scene_id, "forest")
assert is_new == True

# Retrieve random tables
tables = retrieve_random_tables("forest", scene.world_id)
assert len(tables) == 0

# Warning logged, skip procedural generation
```

**Assert:**
```python
# Verify graceful degradation
assert len(tables) == 0
# Warning should be logged
```

---

### Test 4: Canonization Rules (Permanent vs Temporary)

**Setup:**
```python
# Create test scene
scene = create_test_scene(current_location="dungeon_entrance", world_id="world_123")

# Create random tables with named and unnamed NPCs
table_encounters = create_random_table(
    table_type="encounters",
    location_type="dungeon",
    world_id="world_123",
    dice_formula="1d6",
    entries=[
        {"roll_range": "1-3", "content": "skeleton", "entity_type": EntityType.NPC},
        {"roll_range": "4-6", "content": "named skeleton Grak", "entity_type": EntityType.NPC}
    ]
)

table_loot = create_random_table(
    table_type="loot",
    location_type="dungeon",
    world_id="world_123",
    dice_formula="1d6",
    entries=[
        {"roll_range": "1-2", "content": "10 gold", "entity_type": EntityType.ITEM},
        {"roll_range": "3-6", "content": "enchanted ring", "entity_type": EntityType.ITEM}
    ]
)

table_features = create_random_table(
    table_type="features",
    location_type="dungeon",
    world_id="world_123",
    dice_formula="1d6",
    entries=[
        {"roll_range": "1-3", "content": "torch sconce", "entity_type": EntityType.FEATURE},
        {"roll_range": "4-6", "content": "ancient fresco", "entity_type": EntityType.FEATURE}
    ]
)
```

**Execute:**
```python
# Roll on tables with mocked dice (all max rolls for named NPCs)
with patch('monitor_agents.scene_loop.roll_dice', side_effect=[6, 5, 5]):
    entries_encounters = roll_on_table(table_encounters)
    entries_loot = roll_on_table(table_loot)
    entries_features = roll_on_table(table_features)

# Generate entities
entities = []
is_permanent = []

for entry in entries_encounters + entries_loot + entries_features:
    if entry.entity_type:
        is_named_npc = entry.entity_type == EntityType.NPC and is_named(entry.content)
        is_permanent.append(entry.entity_type != EntityType.NPC or is_named_npc)
        
        entity = await mcp_create_entity(
            entity_type=entry.entity_type,
            name=extract_name(entry.content),
            description=entry.content,
            properties=extract_properties(entry.content),
            world_id=scene.world_id,
            metadata={"temporary": not is_permanent[-1]}
        )
        entities.append(entity)

# Stage entities
await stage_entities(scene.scene_id, entities, is_permanent)
```

**Assert:**
```python
# Verify canonization rules
assert is_permanent == [True, True, True]  # Grak, ring, fresco are permanent
assert entities[0].metadata.get("temporary") == False
assert entities[1].metadata.get("temporary") == False
assert entities[2].metadata.get("temporary") == False
```

---

### Test 5: Subtable References (Nested Generation)

**Setup:**
```python
# Create test scene
scene = create_test_scene(current_location="forest_edge", world_id="world_123")

# Create main table for goblin lair
table_goblin_lair = create_random_table(
    table_type="encounters",
    location_type="goblin_lair",
    world_id="world_123",
    dice_formula="1d6",
    entries=[
        {"roll_range": "1-4", "content": "2 goblins", "entity_type": EntityType.NPC},
        {"roll_range": "5-6", "content": "goblin chief", "entity_type": EntityType.NPC, "subtable_ref": "goblin_chief_loot"}
    ]
)

# Create subtable for goblin chief loot
table_goblin_chief_loot = create_random_table(
    table_type="loot",
    location_type="goblin_lair",
    world_id="world_123",
    dice_formula="1d6",
    entries=[
        {"roll_range": "1-2", "content": "100 gold", "entity_type": EntityType.ITEM},
        {"roll_range": "3-6", "content": "magic amulet", "entity_type": EntityType.ITEM}
    ]
)
```

**Execute:**
```python
# Roll on main table with mocked dice (max roll for goblin chief)
with patch('monitor_agents.scene_loop.roll_dice', return_value=6):
    entries = roll_on_table(
        table_goblin_lair,
        subtables={"goblin_chief_loot": table_goblin_chief_loot}
    )

# Verify subtable was resolved
assert len(entries) == 2  # goblin chief + loot from subtable
assert entries[0].content == "goblin chief"
assert entries[1].content == "magic amulet"
```

**Assert:**
```python
# Verify nested generation worked
assert len(entries) == 2
```

---

## Validation Checklist

- [ ] All function signatures match behavior specifications
- [ ] All parameters are typed correctly
- [ ] All return types are documented
- [ ] All error cases are specified
- [ ] All examples are valid
- [ ] Integration tests pass
- [ ] Canonization rules are enforced (permanent vs temporary)
- [ ] CanonKeeper evaluation is async
- [ ] Subtable recursion depth is limited
- [ ] Turn metadata includes all required fields (tables, entities, canonization)
- [ ] Scene entity_registry is updated
- [ ] Graceful degradation when tables are missing
- [ ] Dice formulas are validated before rolling
- [ ] Roll ranges are validated and handle out-of-range cases

---

## Related Documentation

- [P-19-behaviors.md](../behaviors/P-19-behaviors.md) - Behavior definition
- [USE_CASE_BEHAVIORS_INDEX.md](../USE_CASE_BEHAVIORS_INDEX.md) - Use case index
- [TEST_GAPS_ANALYSIS.md](../../TEST_GAPS_ANALYSIS.md) - Test gap analysis
- [TESTING_INDEX.md](../../TESTING_INDEX.md) - Testing master index

---

**Last Updated:** 2026-05-19
**Status:** ✅ Contract specifications complete