# M-13: Create Character — API Contracts

> **Use Case:** Create a character entity with stats, resources, and character sheet
> **Priority:** 10 (Manage entities)
> **Layer:** Layer 3 (CLI) + Layer 2 (Agents)

---

## Overview

M-13 creates a character entity within a universe. Characters can be player characters (PCs), non-player characters (NPCs), antagonists, or allies. Each character can optionally derive from an archetype (EntityArchetype) and has a detailed character sheet with stats (STR, DEX, CON, INT, WIS, CHA), resources (HP, MP), abilities, and equipment.

**Flow:**
1. Trigger: User runs `monitor manage entity create --type character` or selects Manage → Entities → Create → Character
2. Select universe (if not provided)
3. Prompt for character name (e.g., "Gandalf", "Frodo")
4. Prompt for role (PC, NPC, antagonist, ally)
5. Prompt for description (appearance, personality, backstory)
6. Select archetype from EntityArchetype list OR choose custom
7. If archetype selected → link to archetype via DERIVES_FROM edge
8. If PC or detailed NPC → prompt for stats (STR, DEX, CON, INT, WIS, CHA)
9. If PC or detailed NPC → calculate and set resources (HP, MP)
10. If PC or detailed NPC → prompt for abilities and equipment
11. Create EntityInstance in Neo4j with entity_type="character"
12. Link character to universe via HAS_ENTITY edge
13. If archetype selected → link to archetype via DERIVES_FROM edge
14. If PC or detailed NPC → create character_sheet in MongoDB
15. Confirm creation with entity ID

**Contract Scope:**
- CLI command for character creation
- Agent for character processing
- Data layer tools for Neo4j and MongoDB operations
- Validation of character parameters (stats validation, role enum)
- Optional archetype derivation
- Character sheet creation for PCs and detailed NPCs

---

## Data Layer Tool Contracts

### `neo4j_list_archetypes(universe_id: str = None) -> List[ArchetypeSummary]`

Lists all character archetypes available for selection.

**Contract:**
- **Parameters:**
  - `universe_id: str` - Universe ID (optional, if None returns global archetypes)
- **Returns:** `List[ArchetypeSummary]` - List of archetype summary dicts
- **Behavior:**
  - Queries Neo4j for all EntityArchetype nodes
  - If universe_id provided → filters to archetypes in that universe
  - Returns list of archetype summaries with:
    - `id: str` - Archetype ID
    - `name: str` - Archetype name (e.g., "Wizard", "Warrior", "Rogue")
    - `description: str` - Archetype description
    - `entity_type: str` - "archetype"
  - Ordered by name

**Example:**
```python
result = await mcp_client.call_tool("neo4j_list_archetypes", {"universe_id": "universe123"})
assert isinstance(result, list)
assert len(result) >= 1
assert result[0]["id"] is not None
assert result[0]["name"] is not None
assert result[0]["entity_type"] == "archetype"
```

**Error Handling:**
- Invalid universe_id (if provided) → raises `NotFoundError: Universe not found: universe_id`
- Neo4j connection error → raises `ConnectionError: Failed to list archetypes`

---

### `neo4j_create_entity(universe_id: str, entity_type: str, params: dict) -> str`

Creates an EntityInstance node in Neo4j.

**Contract:**
- **Parameters:**
  - `universe_id: str` - Parent universe ID
  - `entity_type: str` - Entity type (e.g., "character", "location", "faction")
  - `params: dict` - Entity properties:
    - `name: str` - Entity name (required, 1-200 chars)
    - `description: str` - Description (optional, max 5000 chars)
    - `role: str` - Character role (optional, from CharacterRole enum: "PC", "NPC", "antagonist", "ally")
    - `properties: dict` - Type-specific properties (optional)
    - `state_tags: list` - State tags (optional, default: [])
    - `canon_level: str` - Canon level (default: "canon")
- **Returns:** `str` - Created entity ID (UUID)
- **Behavior:**
  - Creates EntityInstance node in Neo4j with provided properties
  - Creates `(:Universe)-[:HAS_ENTITY]->(:EntityInstance)` relationship
  - Auto-generates UUID for entity_id
  - Sets created_at timestamp
  - Returns entity_id

**Example:**
```python
result = await mcp_client.call_tool("neo4j_create_entity", {
    "universe_id": "universe123",
    "entity_type": "character",
    "params": {
        "name": "Gandalf",
        "description": "A wise and powerful wizard",
        "role": "ally",
        "properties": {},
        "state_tags": [],
        "canon_level": "canon"
    }
})
assert isinstance(result, str)
assert len(result) == 36  # UUID format
```

**Error Handling:**
- Invalid universe_id → raises `NotFoundError: Universe not found: universe_id`
- Invalid params → raises `ValidationError: Invalid entity parameters: <error>`
- Name too short/long → raises `ValidationError: Name must be 1-200 characters`
- Neo4j connection error → raises `ConnectionError: Failed to create entity`

---

### `neo4j_create_relationship(from_id: str, to_id: str, relationship_type: str, properties: dict = None) -> str`

Creates a relationship between two entities.

**Contract:**
- **Parameters:**
  - `from_id: str` - Source entity ID
  - `to_id: str` - Target entity ID
  - `relationship_type: str` - Relationship type (e.g., "DERIVES_FROM", "LOCATED_IN")
  - `properties: dict` - Relationship properties (optional)
- **Returns:** `str` - Created relationship ID
- **Behavior:**
  - Creates relationship in Neo4j between two nodes
  - Sets provided properties (if any)
  - Returns relationship ID

**Example:**
```python
# Link character to archetype
result = await mcp_client.call_tool("neo4j_create_relationship", {
    "from_id": "entity123",
    "to_id": "archetype456",
    "relationship_type": "DERIVES_FROM",
    "properties": {}
})
assert isinstance(result, str)

# Link character to universe
result = await mcp_client.call_tool("neo4j_create_relationship", {
    "from_id": "universe123",
    "to_id": "entity456",
    "relationship_type": "HAS_ENTITY",
    "properties": {}
})
assert isinstance(result, str)
```

**Error Handling:**
- Invalid from_id → raises `NotFoundError: Source entity not found: entity_id`
- Invalid to_id → raises `NotFoundError: Target entity not found: entity_id`
- Invalid relationship_type → raises `ValidationError: Invalid relationship type`
- Neo4j connection error → raises `ConnectionError: Failed to create relationship`

---

### `mongodb_create_character_sheet(entity_id: str, stats: dict, resources: dict, abilities: list = None, equipment: list = None) -> str`

Creates a character sheet in MongoDB for a character.

**Contract:**
- **Parameters:**
  - `entity_id: str` - Character entity ID (foreign key to Neo4j)
  - `stats: dict` - Character stats (e.g., D&D stats: STR, DEX, CON, INT, WIS, CHA)
  - `resources: dict` - Character resources (e.g., HP, MP)
  - `abilities: list` - Character abilities (optional)
  - `equipment: list` - Character equipment (optional)
- **Returns:** `str` - Created character sheet ID (MongoDB ObjectId as string)
- **Behavior:**
  - Creates document in MongoDB `character_sheets` collection
  - Links to Neo4j entity via entity_id field
  - Sets created_at timestamp
  - Returns character sheet ID

**Example:**
```python
result = await mcp_client.call_tool("mongodb_create_character_sheet", {
    "entity_id": "entity123",
    "stats": {
        "STR": 16,
        "DEX": 14,
        "CON": 14,
        "INT": 18,
        "WIS": 16,
        "CHA": 16
    },
    "resources": {
        "hp_max": 14,
        "hp_current": 14,
        "mp_max": 20,
        "mp_current": 20
    },
    "abilities": ["Fireball", "Lightning Bolt", "Teleport"],
    "equipment": ["Staff", "Robe of the Archmagi"]
})
assert isinstance(result, str)
# Returns MongoDB ObjectId as string
```

**Error Handling:**
- Invalid entity_id → raises `NotFoundError: Character entity not found: entity_id`
- Invalid stats → raises `ValidationError: Invalid stats: <error>`
- MongoDB connection error → raises `ConnectionError: Failed to create character sheet`

---

## Agent Contracts

### CharacterCreator

#### `create_character(universe_id: str, name: str, role: str, description: str = None, archetype_id: str = None, stats: dict = None, abilities: list = None, equipment: list = None) -> str`

Creates a character entity with the provided parameters.

**Contract:**
- **Parameters:**
  - `universe_id: str` - Parent universe ID
  - `name: str` - Character name (1-200 chars)
  - `role: str` - Character role (from CharacterRole enum: "PC", "NPC", "antagonist", "ally")
  - `description: str` - Description (optional, max 5000 chars)
  - `archetype_id: str` - Archetype ID for derivation (optional)
  - `stats: dict` - Character stats (optional, required for PC or detailed NPC)
  - `abilities: list` - Character abilities (optional)
  - `equipment: list` - Character equipment (optional)
- **Returns:** `str` - Created entity ID
- **Behavior:**
  - Validates parameters (name length, role enum, description length, stats validation)
  - Validates universe_id exists
  - Validates archetype_id exists (if provided)
  - Creates entity in Neo4j (calls `neo4j_create_entity()`)
  - Links character to universe via HAS_ENTITY edge (calls `neo4j_create_relationship()`)
  - If archetype_id provided → links to archetype via DERIVES_FROM edge (calls `neo4j_create_relationship()`)
  - If role is "PC" or stats provided → creates character sheet in MongoDB (calls `mongodb_create_character_sheet()`)
  - If stats not provided but role is "PC" or detailed NPC → prompts for stats (calls `prompt_character_stats()`)
  - Calculates HP from stats (calls `calculate_hp()`)
  - Displays confirmation message: "Character created: <entity_id>"
  - Returns entity_id

**Example:**
```python
# PC with archetype and stats
result = await character_creator.create_character(
    universe_id="universe123",
    name="Gandalf",
    role="ally",
    description="A wise and powerful wizard",
    archetype_id="archetype456",
    stats={
        "STR": 16,
        "DEX": 14,
        "CON": 14,
        "INT": 18,
        "WIS": 16,
        "CHA": 16
    },
    abilities=["Fireball", "Lightning Bolt", "Teleport"],
    equipment=["Staff", "Robe of the Archmagi"]
)
assert isinstance(result, str)
assert len(result) == 36  # UUID format

# NPC without archetype or detailed stats
result = await character_creator.create_character(
    universe_id="universe123",
    name="Villager",
    role="NPC",
    description="A simple villager"
)
assert isinstance(result, str)
```

**Error Handling:**
- Invalid name → raises `ValidationError: Name must be 1-200 characters`
- Invalid role → raises `ValidationError: Invalid role. Must be one of: PC, NPC, antagonist, ally`
- Invalid description → raises `ValidationError: Description must be max 5000 characters`
- Invalid stats → raises `ValidationError: Invalid stats: <error>`
- Universe not found → raises `NotFoundError: Universe not found`
- Archetype not found → raises `NotFoundError: Archetype not found`
- Neo4j error → raises `CharacterCreationError: Failed to create character: <error>`
- MongoDB error → raises `CharacterCreationError: Failed to create character sheet: <error>`

---

#### `validate_character_params(name: str, role: str, description: str = None, stats: dict = None) -> None`

Validates character creation parameters.

**Contract:**
- **Parameters:**
  - `name: str` - Character name
  - `role: str` - Character role
  - `description: str` - Description (optional)
  - `stats: dict` - Character stats (optional)
- **Returns:** None
- **Behavior:**
  - Validates name is not empty and <= 200 chars
  - Validates role is in CharacterRole enum
  - Validates description is <= 5000 chars (if provided)
  - Validates stats structure if provided (must have STR, DEX, CON, INT, WIS, CHA keys, values must be int 8-18)
  - Raises ValidationError if any validation fails
  - Returns None if all validations pass

**Example:**
```python
# Valid params
character_creator.validate_character_params(
    name="Gandalf",
    role="ally",
    description="A wise and powerful wizard",
    stats={
        "STR": 16,
        "DEX": 14,
        "CON": 14,
        "INT": 18,
        "WIS": 16,
        "CHA": 16
    }
)

# Invalid role
with pytest.raises(ValidationError, match="Invalid role"):
    character_creator.validate_character_params(
        name="Test",
        role="InvalidRole",  # Not in CharacterRole enum
        description="Test"
    )

# Invalid stats (missing key)
with pytest.raises(ValidationError, match="Invalid stats"):
    character_creator.validate_character_params(
        name="Test",
        role="PC",
        description="Test",
        stats={
            "STR": 16,
            "DEX": 14
            # Missing CON, INT, WIS, CHA
        }
    )

# Invalid stats (value out of range)
with pytest.raises(ValidationError, match="Invalid stats"):
    character_creator.validate_character_params(
        name="Test",
        role="PC",
        description="Test",
        stats={
            "STR": 7,  # Too low (min 8)
            "DEX": 14,
            "CON": 14,
            "INT": 18,
            "WIS": 16,
            "CHA": 16
        }
    )
```

**Error Handling:**
- Invalid name → raises `ValidationError: Name must be 1-200 characters`
- Invalid role → raises `ValidationError: Invalid role. Must be one of: PC, NPC, antagonist, ally`
- Invalid description → raises `ValidationError: Description must be max 5000 characters`
- Invalid stats structure → raises `ValidationError: Invalid stats: <error>`
- Invalid stats values → raises `ValidationError: Invalid stats: <error>`

---

#### `prompt_character_stats() -> dict`

Prompts user for D&D-style character stats (STR, DEX, CON, INT, WIS, CHA).

**Contract:**
- **Parameters:** None
- **Returns:** `dict` - Character stats with keys: "STR", "DEX", "CON", "INT", "WIS", "CHA"
- **Behavior:**
  - Prompts user for each stat (STR, DEX, CON, INT, WIS, CHA)
  - Validates each stat value is int 8-18
  - Returns stats dict

**Example:**
```python
result = await character_creator.prompt_character_stats()
assert isinstance(result, dict)
assert "STR" in result
assert "DEX" in result
assert "CON" in result
assert "INT" in result
assert "WIS" in result
assert "CHA" in result
assert all(8 <= v <= 18 for v in result.values())
```

**Error Handling:**
- Invalid input → prompts user to try again

---

#### `calculate_hp(stats: dict) -> int`

Calculates HP from character stats (D&D-style formula).

**Contract:**
- **Parameters:**
  - `stats: dict` - Character stats with "CON" key
- **Returns:** `int` - HP value
- **Behavior:**
  - Calculates HP based on CON modifier (D&D: 8 + CON_mod for level 1)
  - Returns HP value

**Example:**
```python
result = character_creator.calculate_hp({
    "STR": 16,
    "DEX": 14,
    "CON": 14,  # CON 14 → +2 modifier
    "INT": 18,
    "WIS": 16,
    "CHA": 16
})
# HP = 8 + (14 - 10) // 2 = 8 + 2 = 10
assert result == 10
```

**Error Handling:**
- Invalid stats (missing CON) → raises `ValidationError: Invalid stats: missing CON`
- Invalid stats (CON not int) → raises `ValidationError: Invalid stats: CON must be int`

---

#### `select_archetype(universe_id: str = None) -> str`

Prompts user to select an archetype from the list.

**Contract:**
- **Parameters:**
  - `universe_id: str` - Universe ID (optional, if None shows global archetypes)
- **Returns:** `str` - Selected archetype ID, or None if custom
- **Behavior:**
  - Lists all archetypes (calls `neo4j_list_archetypes()`)
  - Displays numbered list to user with "Custom" option
  - Prompts user for selection
  - Validates selection is in range
  - Returns selected archetype_id or None if custom selected

**Example:**
```python
result = await character_creator.select_archetype(universe_id="universe123")
assert isinstance(result, str) or result is None

# User selects custom
result = await character_creator.select_archetype(universe_id="universe123")
assert result is None
```

**Error Handling:**
- No archetypes available → allows custom creation only
- Invalid selection → prompts user to try again

---

## CLI Contracts

### `monitor manage entity create --type character` Command

CLI command to create a character.

**Contract:**
- **Command:** `monitor manage entity create --type character`
- **Options:**
  - `--universe <id>` - Universe ID (required if not interactive)
  - `--name <name>` - Character name (required if not interactive)
  - `--role <role>` - Character role (required if not interactive)
  - `--description <desc>` - Description (optional)
  - `--archetype <id>` - Archetype ID for derivation (optional)
  - `--stats <json>` - Stats as JSON (optional, for non-interactive)
  - `--interactive` - Interactive mode (default)
- **Behavior:**
  - If all options provided → non-interactive creation
  - If options missing → interactive prompts for missing values
  - Prompts for universe selection (if not provided)
  - Prompts for name, role, description
  - Prompts for archetype selection or custom
  - If role is "PC" → prompts for stats (if not provided)
  - If archetype selected → links to archetype
  - If role is "PC" or stats provided → creates character sheet
  - Displays confirmation message
- **Examples:**
  - `monitor manage entity create --type character --universe universe123 --name "Gandalf" --role ally --description "A wise wizard"` → Non-interactive NPC
  - `monitor manage entity create --type character` → Interactive prompts
  - `monitor manage entity create --type character --universe universe123 --name "Frodo" --role PC --archetype archetype456 --stats '{"STR": 10, "DEX": 14, "CON": 12, "INT": 10, "WIS": 14, "CHA": 14}'` → Non-interactive PC with archetype

**Error Handling:**
- Missing required options (non-interactive) → displays error message
- Invalid parameters → displays validation error
- Universe not found → displays error message
- Archetype not found → displays error message
- Creation failed → displays error message with details

---

## Enums and Data Structures

### `CharacterRole` Enum

```python
class CharacterRole(str, Enum):
    PC = "PC"              # Player Character
    NPC = "NPC"            # Non-Player Character
    ANTAGONIST = "antagonist"  # Antagonist character
    ALLY = "ally"          # Ally character
```

---

### `ArchetypeSummary` Dict

```python
{
    "id": str,  # Archetype ID
    "name": str,  # Archetype name (e.g., "Wizard", "Warrior")
    "description": str,  # Archetype description
    "entity_type": str,  # "archetype"
}
```

---

### `CharacterSheet` Dict

```python
{
    "entity_id": str,  # Foreign key to Neo4j EntityInstance
    "stats": {
        "STR": int,  # Strength
        "DEX": int,  # Dexterity
        "CON": int,  # Constitution
        "INT": int,  # Intelligence
        "WIS": int,  # Wisdom
        "CHA": int   # Charisma
    },
    "resources": {
        "hp_max": int,      # Max Hit Points
        "hp_current": int,  # Current Hit Points
        "mp_max": int,      # Max Magic Points (optional)
        "mp_current": int   # Current Magic Points (optional)
    },
    "abilities": list,  # List of ability names (optional)
    "equipment": list,  # List of equipment names (optional)
    "created_at": str   # ISO 8601 timestamp
}
```

---

## Error Handling

### Exception Hierarchy

```python
class CharacterError(Exception):
    """Base exception for character-related errors."""
    pass

class CharacterCreationError(CharacterError):
    """Raised when character creation fails."""
    pass

class ValidationError(CharacterError):
    """Raised when parameters fail validation."""
    pass
```

### Error Scenarios

| Scenario | Error | User Message |
|----------|-------|--------------|
| Name too short/long | `ValidationError` | "Name must be 1-200 characters" |
| Invalid role | `ValidationError` | "Invalid role. Must be one of: PC, NPC, antagonist, ally" |
| Description too long | `ValidationError` | "Description must be max 5000 characters" |
| Invalid stats structure | `ValidationError` | "Invalid stats: <error>" |
| Invalid stats value (too low) | `ValidationError` | "Invalid stats: <stat> must be 8-18" |
| Invalid stats value (too high) | `ValidationError` | "Invalid stats: <stat> must be 8-18" |
| Missing stat key | `ValidationError` | "Invalid stats: missing <stat> key" |
| Universe not found | `NotFoundError` | "Universe not found" |
| Archetype not found | `NotFoundError` | "Archetype not found" |
| Character creation failed | `CharacterCreationError` | "Failed to create character: <error>" |
| Character sheet creation failed | `CharacterCreationError` | "Failed to create character sheet: <error>" |

---

## Database Operations

### Database Reads
- **Neo4j:** `neo4j_list_archetypes(universe_id)` - Query for archetype nodes
- **MongoDB:** None (only writes)

### Database Writes
- **Neo4j:** `neo4j_create_entity(universe_id, entity_type, params)` - Create EntityInstance node
  - **Condition:** User provides valid character parameters
  - **Fields created:** id, name, entity_type="character", description, role, properties, state_tags, canon_level, created_at
  - **Relationship:** `(:Universe)-[:HAS_ENTITY]->(:EntityInstance)`
- **Neo4j:** `neo4j_create_relationship(from_id, to_id, relationship_type, properties)` - Create relationships
  - **Condition:** User selects archetype
  - **Relationship:** `(:EntityInstance)-[:DERIVES_FROM]->(:EntityArchetype)`
- **MongoDB:** `mongodb_create_character_sheet(entity_id, stats, resources, abilities, equipment)` - Create character sheet
  - **Condition:** Role is "PC" or user provides stats
  - **Fields created:** entity_id, stats, resources, abilities, equipment, created_at

---

## Integration Points

### Dependencies
- **M-2:** Create Universe (universe must exist first)

### Layer Flow
```
Layer 3 (CLI):
  monitor manage entity create --type character
  → CharacterCreator (Layer 2 Agent)
  → Data Layer Tools (Layer 1):
    - neo4j_list_archetypes
    - neo4j_create_entity
    - neo4j_create_relationship
    - mongodb_create_character_sheet
```

---

## Security Considerations

- No authentication required for character creation
- No authorization checks (all authenticated users can create characters)
- Input validation: name, role, description length validation
- Stats validation: structure (all 6 keys required), values (8-18 range)
- Universe validation
- Archetype validation (if provided)
- Character sheet created for PCs and detailed NPCs only

---

## Performance Requirements

- Archetype list: < 100ms
- Character creation (without character sheet): < 200ms
- Character creation (with character sheet): < 300ms
- HP calculation: < 1ms

---

## Testing Strategy

- Unit tests: validate_character_params() with all valid and invalid inputs (role enum, stats structure and values)
- Unit tests: create_character() with PC, NPC, antagonist, ally roles
- Unit tests: create_character() with archetype and without archetype
- Unit tests: prompt_character_stats() with interactive prompts
- Unit tests: calculate_hp() with various CON values
- Unit tests: select_archetype() with interactive selection
- Unit tests: CharacterRole enum validation
- Integration tests: create_character() with mocked MCP tools (PC with archetype, NPC without archetype)
- Integration tests: create_character() with character sheet creation
- CLI tests: monitor manage entity create --type character command with all options (PC, NPC, with archetype, without archetype)
- End-to-end tests: Full character creation workflow (PC with archetype and stats)

---

## Compliance Checklist

- ✅ Validates name length (1-200 chars)
- ✅ Validates role enum (PC, NPC, antagonist, ally)
- ✅ Validates description length (max 5000 chars)
- ✅ Validates stats structure (all 6 keys: STR, DEX, CON, INT, WIS, CHA)
- ✅ Validates stats values (8-18 range)
- ✅ Lists archetypes for selection
- ✅ Supports custom archetype creation
- ✅ Creates EntityInstance node in Neo4j
- ✅ Links character to universe via HAS_ENTITY edge
- ✅ Links character to archetype via DERIVES_FROM edge (if archetype selected)
- ✅ Creates character sheet in MongoDB (if PC or stats provided)
- ✅ Calculates HP from stats
- ✅ Prompts for stats (if not provided and role is PC or detailed NPC)
- ✅ Returns entity ID
- ✅ Displays confirmation message
- ✅ Supports interactive and non-interactive modes
- ✅ Validates universe_id exists
- ✅ Validates archetype_id exists (if provided)
- ✅ Handles creation errors gracefully