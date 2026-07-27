# M-1: Create Multiverse — API Contracts

> **Use Case:** Create a multiverse/setting that serves as the canonical base for playable universes
> **Priority:** 8 (Manage hierarchy)
> **Layer:** Layer 3 (CLI) + Layer 2 (Agents)

---

## Overview

M-1 creates a multiverse/setting node that serves as the canonical base for one or more playable universes. A multiverse represents a setting/world layer (e.g., "The Witcher", "Middle-earth", "Marvel") that can contain multiple universes.

**Flow:**
1. Trigger: User runs `monitor manage multiverse create` or selects Manage → Multiverse → Create
2. Prompt for multiverse name (e.g., "D&D Worlds", "Marvel Cinematic Universe")
3. Prompt for default system/genre (e.g., "D&D 5e", "FATE")
4. Prompt for description and baseline canon notes
5. Optionally seed from ingested knowledge pack or source set (optional step)
6. Get omniverse ID (singleton parent)
7. Create Multiverse node in Neo4j
8. Link Multiverse to Omniverse
9. Confirm creation with multiverse ID

**Contract Scope:**
- CLI command for multiverse creation
- Agent for multiverse processing
- Data layer tools for Neo4j operations
- Validation of multiverse parameters
- Optional knowledge pack seeding

---

## Data Layer Tool Contracts

### `neo4j_get_omniverse() -> Omniverse`

Retrieves the singleton omniverse (creates if none exists).

**Contract:**
- **Parameters:** None
- **Returns:** `Omniverse` dict
- **Behavior:**
  - Queries Neo4j for omniverse node (singleton pattern)
  - If omniverse exists → returns omniverse dict
  - If omniverse does not exist → creates omniverse node and returns it
  - Omniverse is auto-created on first run if none exists

**Example:**
```python
# Omniverse exists
result = await mcp_client.call_tool("neo4j_get_omniverse", {})
assert result is not None
assert result["id"] is not None
assert result["name"] is not None

# Omniverse does not exist (auto-created)
result = await mcp_client.call_tool("neo4j_get_omniverse", {})
assert result is not None
assert result["id"] is not None
assert result["name"] == "Omniverse"  # Default name
```

**Error Handling:**
- Neo4j connection error → raises `ConnectionError: Failed to get or create omniverse`

---

### `neo4j_create_multiverse(omniverse_id: str, params: dict) -> str`

Creates a Multiverse node and links it to Omniverse.

**Contract:**
- **Parameters:**
  - `omniverse_id: str` - Parent omniverse ID
  - `params: dict` - Multiverse properties:
    - `name: str` - Multiverse name (required, 1-200 chars)
    - `system_name: str` - Default system/genre (required, 1-100 chars, e.g., "D&D 5e", "FATE")
    - `description: str` - Description and baseline canon notes (optional, max 5000 chars)
    - `canon_level: str` - Canon level (default: "canon")
- **Returns:** `str` - Created multiverse ID (UUID)
- **Behavior:**
  - Creates Multiverse node in Neo4j with provided properties
  - Creates `(:Omniverse)-[:CONTAINS]->(:Multiverse)` relationship
  - Auto-generates UUID for multiverse_id
  - Sets created_at timestamp
  - Returns multiverse_id

**Example:**
```python
result = await mcp_client.call_tool("neo4j_create_multiverse", {
    "omniverse_id": "omni123",
    "name": "D&D Worlds",
    "system_name": "D&D 5e",
    "description": "A collection of D&D campaigns",
    "canon_level": "canon"
})
assert isinstance(result, str)
assert len(result) == 36  # UUID format
```

**Error Handling:**
- Invalid omniverse_id → raises `NotFoundError: Omniverse not found: omniverse_id`
- Invalid params → raises `ValidationError: Invalid multiverse parameters: <error>`
- Name too short/long → raises `ValidationError: Name must be 1-200 characters`
- Neo4j connection error → raises `ConnectionError: Failed to create multiverse`

---

### `neo4j_list_multiverses(omniverse_id: str) -> List[MultiverseSummary]`

Lists all multiverses in the omniverse.

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

## Agent Contracts

### MultiverseCreator

#### `create_multiverse(name: str, system_name: str, description: str = None) -> str`

Creates a multiverse with the provided parameters.

**Contract:**
- **Parameters:**
  - `name: str` - Multiverse name (1-200 chars)
  - `system_name: str` - Default system/genre (1-100 chars)
  - `description: str` - Description (optional, max 5000 chars)
- **Returns:** `str` - Created multiverse ID
- **Behavior:**
  - Validates parameters (name length, system_name length, description length)
  - Gets omniverse ID (calls `neo4j_get_omniverse()`)
  - Creates multiverse in Neo4j (calls `neo4j_create_multiverse()`)
  - Displays confirmation message: "Multiverse created: <multiverse_id>"
  - Returns multiverse_id

**Example:**
```python
result = await multiverse_creator.create_multiverse(
    name="D&D Worlds",
    system_name="D&D 5e",
    description="A collection of D&D campaigns"
)
assert isinstance(result, str)
assert len(result) == 36  # UUID format
```

**Error Handling:**
- Invalid name → raises `ValidationError: Name must be 1-200 characters`
- Invalid system_name → raises `ValidationError: System name must be 1-100 characters`
- Invalid description → raises `ValidationError: Description must be max 5000 characters`
- Omniverse not found → raises `NotFoundError: Omniverse not found`
- Neo4j error → raises `MultiverseCreationError: Failed to create multiverse: <error>`

---

#### `validate_multiverse_params(name: str, system_name: str, description: str = None) -> None`

Validates multiverse creation parameters.

**Contract:**
- **Parameters:**
  - `name: str` - Multiverse name
  - `system_name: str` - System/genre
  - `description: str` - Description (optional)
- **Returns:** None
- **Behavior:**
  - Validates name is not empty and <= 200 chars
  - Validates system_name is not empty and <= 100 chars
  - Validates description is <= 5000 chars (if provided)
  - Raises ValidationError if any validation fails
  - Returns None if all validations pass

**Example:**
```python
# Valid params
multiverse_creator.validate_multiverse_params(
    name="D&D Worlds",
    system_name="D&D 5e",
    description="A collection"
)

# Invalid name (empty)
with pytest.raises(ValidationError):
    multiverse_creator.validate_multiverse_params(
        name="",
        system_name="D&D 5e"
    )

# Invalid name (too long)
with pytest.raises(ValidationError):
    multiverse_creator.validate_multiverse_params(
        name="x" * 201,
        system_name="D&D 5e"
    )
```

**Error Handling:**
- Invalid name → raises `ValidationError: Name must be 1-200 characters`
- Invalid system_name → raises `ValidationError: System name must be 1-100 characters`
- Invalid description → raises `ValidationError: Description must be max 5000 characters`

---

#### `seed_from_knowledge_pack(multiverse_id: str, pack_id: str) -> None`

Seeds multiverse from ingested knowledge pack (optional step).

**Contract:**
- **Parameters:**
  - `multiverse_id: str` - Multiverse ID to seed
  - `pack_id: str` - Knowledge pack ID to seed from
- **Returns:** None
- **Behavior:**
  - Queries MongoDB for knowledge pack by pack_id
  - Extracts entities, facts, and relationships from pack
  - Creates entities in Neo4j linked to multiverse
  - Creates facts in Neo4j with canon_level="canon"
  - Displays progress: "Seeded X entities, Y facts from knowledge pack"
  - Optional: called only if user chooses to seed from pack

**Example:**
```python
await multiverse_creator.seed_from_knowledge_pack(
    multiverse_id="multi123",
    pack_id="pack456"
)
# Displays: "Seeded 15 entities, 42 facts from knowledge pack"
```

**Error Handling:**
- Invalid pack_id → raises `NotFoundError: Knowledge pack not found: pack_id`
- Neo4j error → raises `SeedingError: Failed to seed multiverse: <error>`

---

## CLI Contracts

### `monitor manage multiverse create` Command

CLI command to create a multiverse.

**Contract:**
- **Command:** `monitor manage multiverse create`
- **Options:**
  - `--name <name>` - Multiverse name (required if not interactive)
  - `--system <system>` - System/genre (required if not interactive)
  - `--description <desc>` - Description (optional)
  - `--pack <id>` - Knowledge pack ID to seed from (optional)
- **Behavior:**
  - If all options provided → non-interactive creation
  - If options missing → interactive prompts for missing values
  - Validates all parameters
  - Creates multiverse
  - If `--pack` provided → seeds from knowledge pack
  - Displays confirmation message
- **Examples:**
  - `monitor manage multiverse create --name "D&D Worlds" --system "D&D 5e"` → Non-interactive
  - `monitor manage multiverse create` → Interactive prompts
  - `monitor manage multiverse create --name "Marvel" --system "Marvel RPG" --pack pack123` → With seeding

**Error Handling:**
- Missing required options (non-interactive) → displays error message
- Invalid parameters → displays validation error
- Creation failed → displays error message with details

---

## Enums and Data Structures

### `Omniverse` Dict

```python
{
    "id": str,  # Omniverse ID (UUID)
    "name": str,  # Omniverse name
    "description": str,  # Omniverse description
    "created_at": str,  # ISO 8601 timestamp
}
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

## Error Handling

### Exception Hierarchy

```python
class MultiverseError(Exception):
    """Base exception for multiverse-related errors."""
    pass

class MultiverseCreationError(MultiverseError):
    """Raised when multiverse creation fails."""
    pass

class ValidationError(MultiverseError):
    """Raised when parameters fail validation."""
    pass

class SeedingError(MultiverseError):
    """Raised when knowledge pack seeding fails."""
    pass
```

### Error Scenarios

| Scenario | Error | User Message |
|----------|-------|--------------|
| Name too short/long | `ValidationError` | "Name must be 1-200 characters" |
| System name too short/long | `ValidationError` | "System name must be 1-100 characters" |
| Description too long | `ValidationError` | "Description must be max 5000 characters" |
| Omniverse not found | `NotFoundError` | "Omniverse not found" |
| Creation failed | `MultiverseCreationError` | "Failed to create multiverse: <error>" |
| Seeding failed | `SeedingError` | "Failed to seed multiverse: <error>" |

---

## Database Operations

### Database Reads
- **Neo4j:** `neo4j_get_omniverse()` - Query for omniverse node (singleton)
- **Neo4j:** `neo4j_list_multiverses(omniverse_id)` - Query for multiverse nodes linked to omniverse
- **MongoDB:** `seed_from_knowledge_pack()` - Query knowledge pack by pack_id

### Database Writes
- **Neo4j:** `neo4j_create_multiverse(omniverse_id, params)` - Create Multiverse node and link to Omniverse
  - **Condition:** User provides valid multiverse parameters
  - **Fields created:** id, name, system_name, description, canon_level, created_at
  - **Relationship:** `(:Omniverse)-[:CONTAINS]->(:Multiverse)`
- **Neo4j:** `seed_from_knowledge_pack()` - Create entities and facts from knowledge pack (optional)
  - **Condition:** User chooses to seed from knowledge pack
  - **Entities created:** From pack, linked to multiverse
  - **Facts created:** From pack, with canon_level="canon"

---

## Integration Points

### Dependencies
- **None:** M-1 is a top-level use case (multiverse creation)

### Layer Flow
```
Layer 3 (CLI):
  monitor manage multiverse create
  → MultiverseCreator (Layer 2 Agent)
  → Data Layer Tools (Layer 1):
    - neo4j_get_omniverse
    - neo4j_create_multiverse
    - neo4j_list_multiverses
    - seed_from_knowledge_pack (optional)
```

---

## Security Considerations

- No authentication required for multiverse creation
- No authorization checks (all authenticated users can create multiverses)
- Input validation: name, system_name, description length validation
- Omniverse is singleton (user cannot create multiple omniverses)
- Knowledge pack seeding validates pack_id exists and belongs to user

---

## Performance Requirements

- Omniverse get/create: < 100ms
- Multiverse creation: < 200ms
- Knowledge pack seeding: < 5s (depends on pack size)

---

## Testing Strategy

- Unit tests: validate_multiverse_params() with all valid and invalid inputs
- Unit tests: create_multiverse() with all parameter combinations
- Unit tests: seed_from_knowledge_pack() with valid and invalid pack IDs
- Integration tests: create_multiverse() with mocked MCP tools
- Integration tests: seed_from_knowledge_pack() with mocked MongoDB and Neo4j
- CLI tests: monitor manage multiverse create command with all options
- End-to-end tests: Full multiverse creation workflow

---

## Compliance Checklist

- ✅ Validates name length (1-200 chars)
- ✅ Validates system_name length (1-100 chars)
- ✅ Validates description length (max 5000 chars)
- ✅ Gets or creates omniverse (singleton pattern)
- ✅ Creates Multiverse node in Neo4j
- ✅ Links Multiverse to Omniverse
- ✅ Returns multiverse ID
- ✅ Displays confirmation message
- ✅ Supports optional knowledge pack seeding
- ✅ Supports interactive and non-interactive modes
- ✅ Validates knowledge pack ID before seeding
- ✅ Handles creation errors gracefully