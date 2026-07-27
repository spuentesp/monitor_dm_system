# M-2: Create Universe — API Contracts

> **Use Case:** Create a universe within a multiverse with genre, tone, and tech level
> **Priority:** 9 (Manage hierarchy)
> **Layer:** Layer 3 (CLI) + Layer 2 (Agents)

---

## Overview

M-2 creates a universe node within a multiverse. A universe represents a playable campaign setting with specific genre, tone, tech level, and description. Users can create a fresh universe or branch from an existing one.

**Flow:**
1. Trigger: User runs `monitor manage universe create` or selects Manage → Universe → Create
2. Select multiverse (display list, prompt for selection)
3. Prompt for universe name (e.g., "Forgotten Realms", "Age of Sigmar")
4. Choose basis: Fresh start OR Branch from existing universe
5. If branching → select source universe, confirm inheritance
6. Prompt for genre (e.g., Fantasy, Sci-Fi, Cyberpunk)
7. Prompt for tone (e.g., Dark, Heroic, Whimsical)
8. Prompt for tech level (e.g., Pre-Industrial, Modern, Future)
9. Prompt for description and baseline canon notes
10. Create Universe node in Neo4j
11. Link Universe to Multiverse
12. If branching → link to source universe with BRANCH_OF relationship
13. Confirm creation with universe ID

**Contract Scope:**
- CLI command for universe creation
- Agent for universe processing
- Data layer tools for Neo4j operations
- Validation of universe parameters (Pydantic models)
- Fresh start vs branching logic

---

## Data Layer Tool Contracts

### `neo4j_list_multiverses(omniverse_id: str) -> List[MultiverseSummary]`

Lists all multiverses in the omniverse for selection.

**Contract:**
- **Parameters:**
  - `omniverse_id: str` - Omniverse ID
- **Returns:** `List[MultiverseSummary]` - List of multiverse summary dicts
- **Behavior:**
  - Queries Neo4j for all Multiverse nodes linked to Omniverse
  - Returns list of multiverse summaries with:
    - `id: str` - Multiverse ID
    - `name: str` - Multiverse name
    - `system_name: str` - System/genre
    - `universe_count: int` - Number of universes in multiverse
  - Ordered by name

**Example:**
```python
result = await mcp_client.call_tool("neo4j_list_multiverses", {"omniverse_id": "omni123"})
assert isinstance(result, list)
assert len(result) >= 1
assert result[0]["id"] is not None
assert result[0]["name"] is not None
assert result[0]["system_name"] is not None
assert "universe_count" in result[0]
```

**Error Handling:**
- Invalid omniverse_id → raises `NotFoundError: Omniverse not found: omniverse_id`
- Neo4j connection error → raises `ConnectionError: Failed to list multiverses`

---

### `neo4j_create_universe(multiverse_id: str, params: dict, branch_from: str = None) -> str`

Creates a Universe node and links it to Multiverse (and optionally to source universe).

**Contract:**
- **Parameters:**
  - `multiverse_id: str` - Parent multiverse ID
  - `params: dict` - Universe properties:
    - `name: str` - Universe name (required, 1-200 chars)
    - `genre: str` - Genre (required, from Genre enum)
    - `tone: str` - Tone (required, from Tone enum)
    - `tech_level: str` - Tech level (required, from TechLevel enum)
    - `description: str` - Description and baseline canon notes (optional, max 5000 chars)
    - `canon_level: str` - Canon level (default: "canon")
  - `branch_from: str` - Source universe ID for branching (optional)
- **Returns:** `str` - Created universe ID (UUID)
- **Behavior:**
  - Creates Universe node in Neo4j with provided properties
  - Creates `(:Multiverse)-[:CONTAINS]->(:Universe)` relationship
  - If `branch_from` provided → creates `(:Universe)-[:BRANCH_OF]->(:Universe)` relationship
  - Auto-generates UUID for universe_id
  - Sets created_at timestamp
  - Returns universe_id

**Example:**
```python
# Fresh start universe
result = await mcp_client.call_tool("neo4j_create_universe", {
    "multiverse_id": "multi123",
    "params": {
        "name": "Forgotten Realms",
        "genre": "Fantasy",
        "tone": "Heroic",
        "tech_level": "Pre-Industrial",
        "description": "High fantasy world",
        "canon_level": "canon"
    },
    "branch_from": None
})
assert isinstance(result, str)
assert len(result) == 36  # UUID format

# Branch from existing universe
result = await mcp_client.call_tool("neo4j_create_universe", {
    "multiverse_id": "multi123",
    "params": {
        "name": "Forgotten Realms - alternate timeline",
        "genre": "Fantasy",
        "tone": "Dark",
        "tech_level": "Pre-Industrial",
        "description": "Alternate timeline where the gods are dead",
        "canon_level": "canon"
    },
    "branch_from": "universe456"
})
assert isinstance(result, str)
assert len(result) == 36
```

**Error Handling:**
- Invalid multiverse_id → raises `NotFoundError: Multiverse not found: multiverse_id`
- Invalid branch_from (if provided) → raises `NotFoundError: Source universe not found: universe_id`
- Invalid params → raises `ValidationError: Invalid universe parameters: <error>`
- Name too short/long → raises `ValidationError: Name must be 1-200 characters`
- Invalid genre → raises `ValidationError: Invalid genre. Must be one of: Fantasy, Sci-Fi, Cyberpunk, etc.`
- Invalid tone → raises `ValidationError: Invalid tone. Must be one of: Dark, Heroic, Whimsical, etc.`
- Invalid tech_level → raises `ValidationError: Invalid tech level. Must be one of: Pre-Industrial, Modern, Future, etc.`
- Neo4j connection error → raises `ConnectionError: Failed to create universe`

---

### `neo4j_list_universes(multiverse_id: str) -> List[UniverseSummary]`

Lists all universes in a multiverse (for branching selection).

**Contract:**
- **Parameters:**
  - `multiverse_id: str` - Multiverse ID
- **Returns:** `List[UniverseSummary]` - List of universe summary dicts
- **Behavior:**
  - Queries Neo4j for all Universe nodes linked to Multiverse
  - Returns list of universe summaries with:
    - `id: str` - Universe ID
    - `name: str` - Universe name
    - `genre: str` - Genre
    - `tone: str` - Tone
    - `tech_level: str` - Tech level
    - `entity_count: int` - Number of entities in universe
    - `story_count: int` - Number of stories in universe
  - Ordered by name

**Example:**
```python
result = await mcp_client.call_tool("neo4j_list_universes", {"multiverse_id": "multi123"})
assert isinstance(result, list)
assert len(result) >= 1
assert result[0]["id"] is not None
assert result[0]["name"] is not None
assert result[0]["genre"] is not None
assert result[0]["tone"] is not None
assert result[0]["tech_level"] is not None
assert "entity_count" in result[0]
assert "story_count" in result[0]
```

**Error Handling:**
- Invalid multiverse_id → raises `NotFoundError: Multiverse not found: multiverse_id`
- Neo4j connection error → raises `ConnectionError: Failed to list universes`

---

## Agent Contracts

### UniverseCreator

#### `create_universe(multiverse_id: str, name: str, genre: str, tone: str, tech_level: str, description: str = None, branch_from: str = None) -> str`

Creates a universe with the provided parameters.

**Contract:**
- **Parameters:**
  - `multiverse_id: str` - Parent multiverse ID
  - `name: str` - Universe name (1-200 chars)
  - `genre: str` - Genre (from Genre enum)
  - `tone: str` - Tone (from Tone enum)
  - `tech_level: str` - Tech level (from TechLevel enum)
  - `description: str` - Description (optional, max 5000 chars)
  - `branch_from: str` - Source universe ID for branching (optional)
- **Returns:** `str` - Created universe ID
- **Behavior:**
  - Validates parameters (name length, genre enum, tone enum, tech_level enum, description length)
  - Validates multiverse_id exists
  - Validates branch_from exists (if provided)
  - Creates universe in Neo4j (calls `neo4j_create_universe()`)
  - Displays confirmation message: "Universe created: <universe_id>"
  - If branching → displays: "Branched from <universe_name> (<branch_from>)"
  - Returns universe_id

**Example:**
```python
# Fresh start
result = await universe_creator.create_universe(
    multiverse_id="multi123",
    name="Forgotten Realms",
    genre="Fantasy",
    tone="Heroic",
    tech_level="Pre-Industrial",
    description="High fantasy world with magic and gods"
)
assert isinstance(result, str)
assert len(result) == 36  # UUID format

# Branch
result = await universe_creator.create_universe(
    multiverse_id="multi123",
    name="Forgotten Realms - alternate",
    genre="Fantasy",
    tone="Dark",
    tech_level="Pre-Industrial",
    description="Alternate timeline",
    branch_from="universe456"
)
assert isinstance(result, str)
```

**Error Handling:**
- Invalid name → raises `ValidationError: Name must be 1-200 characters`
- Invalid genre → raises `ValidationError: Invalid genre. Must be one of: Fantasy, Sci-Fi, Cyberpunk, etc.`
- Invalid tone → raises `ValidationError: Invalid tone. Must be one of: Dark, Heroic, Whimsical, etc.`
- Invalid tech_level → raises `ValidationError: Invalid tech level. Must be one of: Pre-Industrial, Modern, Future, etc.`
- Invalid description → raises `ValidationError: Description must be max 5000 characters`
- Multiverse not found → raises `NotFoundError: Multiverse not found`
- Source universe not found → raises `NotFoundError: Source universe not found`
- Neo4j error → raises `UniverseCreationError: Failed to create universe: <error>`

---

#### `validate_universe_params(name: str, genre: str, tone: str, tech_level: str, description: str = None) -> None`

Validates universe creation parameters.

**Contract:**
- **Parameters:**
  - `name: str` - Universe name
  - `genre: str` - Genre
  - `tone: str` - Tone
  - `tech_level: str` - Tech level
  - `description: str` - Description (optional)
- **Returns:** None
- **Behavior:**
  - Validates name is not empty and <= 200 chars
  - Validates genre is in Genre enum
  - Validates tone is in Tone enum
  - Validates tech_level is in TechLevel enum
  - Validates description is <= 5000 chars (if provided)
  - Raises ValidationError if any validation fails
  - Returns None if all validations pass

**Example:**
```python
# Valid params
universe_creator.validate_universe_params(
    name="Forgotten Realms",
    genre="Fantasy",
    tone="Heroic",
    tech_level="Pre-Industrial",
    description="High fantasy world"
)

# Invalid genre
with pytest.raises(ValidationError, match="Invalid genre"):
    universe_creator.validate_universe_params(
        name="Test",
        genre="InvalidGenre",  # Not in Genre enum
        tone="Heroic",
        tech_level="Pre-Industrial"
    )

# Invalid tone
with pytest.raises(ValidationError, match="Invalid tone"):
    universe_creator.validate_universe_params(
        name="Test",
        genre="Fantasy",
        tone="InvalidTone",  # Not in Tone enum
        tech_level="Pre-Industrial"
    )

# Invalid tech level
with pytest.raises(ValidationError, match="Invalid tech level"):
    universe_creator.validate_universe_params(
        name="Test",
        genre="Fantasy",
        tone="Heroic",
        tech_level="InvalidTechLevel"  # Not in TechLevel enum
    )
```

**Error Handling:**
- Invalid name → raises `ValidationError: Name must be 1-200 characters`
- Invalid genre → raises `ValidationError: Invalid genre. Must be one of: Fantasy, Sci-Fi, Cyberpunk, etc.`
- Invalid tone → raises `ValidationError: Invalid tone. Must be one of: Dark, Heroic, Whimsical, etc.`
- Invalid tech_level → raises `ValidationError: Invalid tech level. Must be one of: Pre-Industrial, Modern, Future, etc.`
- Invalid description → raises `ValidationError: Description must be max 5000 characters`

---

#### `select_multiverse(omniverse_id: str) -> str`

Prompts user to select a multiverse from the list.

**Contract:**
- **Parameters:**
  - `omniverse_id: str` - Omniverse ID
- **Returns:** `str` - Selected multiverse ID
- **Behavior:**
  - Lists all multiverses (calls `neo4j_list_multiverses()`)
  - Displays numbered list to user
  - Prompts user for selection
  - Validates selection is in range
  - Returns selected multiverse_id

**Example:**
```python
result = await universe_creator.select_multiverse(omniverse_id="omni123")
assert isinstance(result, str)
assert len(result) == 36  # UUID format
```

**Error Handling:**
- No multiverses available → raises `NotFoundError: No multiverses available. Create a multiverse first.`
- Invalid selection → prompts user to try again

---

#### `select_branch_universe(multiverse_id: str) -> str`

Prompts user to select a source universe for branching.

**Contract:**
- **Parameters:**
  - `multiverse_id: str` - Multiverse ID
- **Returns:** `str` - Selected universe ID for branching
- **Behavior:**
  - Lists all universes in multiverse (calls `neo4j_list_universes()`)
  - Displays numbered list to user
  - Prompts user for selection (or cancel)
  - Validates selection is in range
  - Returns selected universe_id
  - If user cancels → returns None

**Example:**
```python
result = await universe_creator.select_branch_universe(multiverse_id="multi123")
assert isinstance(result, str)
assert len(result) == 36  # UUID format

# User cancels
result = await universe_creator.select_branch_universe(multiverse_id="multi123")
assert result is None
```

**Error Handling:**
- No universes available → raises `NotFoundError: No universes available in this multiverse. Cannot branch.`
- Invalid selection → prompts user to try again

---

## CLI Contracts

### `monitor manage universe create` Command

CLI command to create a universe.

**Contract:**
- **Command:** `monitor manage universe create`
- **Options:**
  - `--multiverse <id>` - Multiverse ID (required if not interactive)
  - `--name <name>` - Universe name (required if not interactive)
  - `--genre <genre>` - Genre (required if not interactive)
  - `--tone <tone>` - Tone (required if not interactive)
  - `--tech <level>` - Tech level (required if not interactive)
  - `--description <desc>` - Description (optional)
  - `--branch <id>` - Branch from universe ID (optional)
- **Behavior:**
  - If all options provided → non-interactive creation
  - If options missing → interactive prompts for missing values
  - Prompts for multiverse selection (if not provided)
  - Prompts for fresh start vs branching
  - If branching → prompts for source universe selection
  - Validates all parameters
  - Creates universe
  - Displays confirmation message
- **Examples:**
  - `monitor manage universe create --multiverse multi123 --name "Forgotten Realms" --genre Fantasy --tone Heroic --tech Pre-Industrial` → Non-interactive fresh start
  - `monitor manage universe create` → Interactive prompts
  - `monitor manage universe create --multiverse multi123 --name "Alternate FR" --genre Fantasy --tone Dark --tech Pre-Industrial --branch universe456` → Non-interactive with branching

**Error Handling:**
- Missing required options (non-interactive) → displays error message
- Invalid parameters → displays validation error
- Multiverse not found → displays error message
- Source universe not found → displays error message
- Creation failed → displays error message with details

---

## Enums and Data Structures

### `Genre` Enum

```python
class Genre(str, Enum):
    FANTASY = "Fantasy"
    SCI_FI = "Sci-Fi"
    CYBERPUNK = "Cyberpunk"
    HORROR = "Horror"
    WESTERN = "Western"
    MODERN = "Modern"
    HISTORICAL = "Historical"
    POST_APOCALYPTIC = "Post-Apocalyptic"
    STEAMPUNK = "Steampunk"
    URBAN_FANTASY = "Urban Fantasy"
    SPACE_OPERA = "Space Opera"
    SUPERHERO = "Superhero"
```

---

### `Tone` Enum

```python
class Tone(str, Enum):
    DARK = "Dark"
    HEROIC = "Heroic"
    WHIMSICAL = "Whimsical"
    GRIMDARK = "Grimdark"
    OPTIMISTIC = "Optimistic"
    MYSTERIOUS = "Mysterious"
    CAMPY = "Campy"
    SERIOUS = "Serious"
    LIGHT_HEARTED = "Light-Hearted"
```

---

### `TechLevel` Enum

```python
class TechLevel(str, Enum):
    PRE_INDUSTRIAL = "Pre-Industrial"
    STEAM = "Steam"
    EARLY_MODERN = "Early Modern"
    MODERN = "Modern"
    NEAR_FUTURE = "Near Future"
    FAR_FUTURE = "Far Future"
    POST_APOCALYPTIC = "Post-Apocalyptic"
    ANCIENT = "Ancient"
    MEDIEVAL = "Medieval"
```

---

### `MultiverseSummary` Dict

```python
{
    "id": str,  # Multiverse ID
    "name": str,  # Multiverse name
    "system_name": str,  # System/genre
    "universe_count": int,  # Number of universes
    "created_at": str,  # ISO 8601 timestamp
}
```

---

### `UniverseSummary` Dict

```python
{
    "id": str,  # Universe ID
    "name": str,  # Universe name
    "genre": str,  # Genre (from Genre enum)
    "tone": str,  # Tone (from Tone enum)
    "tech_level": str,  # Tech level (from TechLevel enum)
    "entity_count": int,  # Number of entities
    "story_count": int,  # Number of stories
    "created_at": str,  # ISO 8601 timestamp
}
```

---

## Error Handling

### Exception Hierarchy

```python
class UniverseError(Exception):
    """Base exception for universe-related errors."""
    pass

class UniverseCreationError(UniverseError):
    """Raised when universe creation fails."""
    pass

class ValidationError(UniverseError):
    """Raised when parameters fail validation."""
    pass
```

### Error Scenarios

| Scenario | Error | User Message |
|----------|-------|--------------|
| Name too short/long | `ValidationError` | "Name must be 1-200 characters" |
| Invalid genre | `ValidationError` | "Invalid genre. Must be one of: Fantasy, Sci-Fi, Cyberpunk, etc." |
| Invalid tone | `ValidationError` | "Invalid tone. Must be one of: Dark, Heroic, Whimsical, etc." |
| Invalid tech level | `ValidationError` | "Invalid tech level. Must be one of: Pre-Industrial, Modern, Future, etc." |
| Description too long | `ValidationError` | "Description must be max 5000 characters" |
| Multiverse not found | `NotFoundError` | "Multiverse not found" |
| Source universe not found | `NotFoundError` | "Source universe not found" |
| Creation failed | `UniverseCreationError` | "Failed to create universe: <error>" |
| No multiverses available | `NotFoundError` | "No multiverses available. Create a multiverse first." |
| No universes available | `NotFoundError` | "No universes available in this multiverse. Cannot branch." |

---

## Database Operations

### Database Reads
- **Neo4j:** `neo4j_list_multiverses(omniverse_id)` - Query for multiverse nodes linked to omniverse
- **Neo4j:** `neo4j_list_universes(multiverse_id)` - Query for universe nodes linked to multiverse

### Database Writes
- **Neo4j:** `neo4j_create_universe(multiverse_id, params, branch_from)` - Create Universe node and link to Multiverse
  - **Condition:** User provides valid universe parameters
  - **Fields created:** id, name, genre, tone, tech_level, description, canon_level, created_at
  - **Relationships:** `(:Multiverse)-[:CONTAINS]->(:Universe)`
  - **Optional relationship:** `(:Universe)-[:BRANCH_OF]->(:Universe)` (if branching)

---

## Integration Points

### Dependencies
- **M-1:** Create Multiverse (multiverse must exist first)

### Layer Flow
```
Layer 3 (CLI):
  monitor manage universe create
  → UniverseCreator (Layer 2 Agent)
  → Data Layer Tools (Layer 1):
    - neo4j_list_multiverses
    - neo4j_list_universes
    - neo4j_create_universe
```

---

## Security Considerations

- No authentication required for universe creation
- No authorization checks (all authenticated users can create universes)
- Input validation: name, genre, tone, tech_level, description length validation
- Multiverse and source universe validation
- Branching creates a new universe that inherits from source but does not modify it

---

## Performance Requirements

- Multiverse list: < 100ms
- Universe list: < 100ms
- Universe creation: < 200ms
- Branch creation: < 200ms

---

## Testing Strategy

- Unit tests: validate_universe_params() with all valid and invalid inputs (genre, tone, tech_level enums)
- Unit tests: create_universe() with fresh start and branching
- Unit tests: select_multiverse() and select_branch_universe() with interactive prompts
- Unit tests: Genre, Tone, TechLevel enum validation
- Integration tests: create_universe() with mocked MCP tools (fresh and branch)
- Integration tests: select_multiverse() with mocked neo4j_list_multiverses
- Integration tests: select_branch_universe() with mocked neo4j_list_universes
- CLI tests: monitor manage universe create command with all options (fresh and branch)
- End-to-end tests: Full universe creation workflow (fresh and branch)

---

## Compliance Checklist

- ✅ Validates name length (1-200 chars)
- ✅ Validates genre enum
- ✅ Validates tone enum
- ✅ Validates tech_level enum
- ✅ Validates description length (max 5000 chars)
- ✅ Lists multiverses for selection
- ✅ Lists universes for branching selection
- ✅ Supports fresh start creation
- ✅ Supports branching from existing universe
- ✅ Creates Universe node in Neo4j
- ✅ Links Universe to Multiverse
- ✅ Links Universe to source universe (if branching)
- ✅ Returns universe ID
- ✅ Displays confirmation message
- ✅ Supports interactive and non-interactive modes
- ✅ Validates multiverse_id exists
- ✅ Validates branch_from exists (if provided)
- ✅ Handles creation errors gracefully