# P-1: Start New Story — Contract Specifications

## Overview

**Purpose:** Create a new story in the system, including creating a Story node in Neo4j and a story outline document in MongoDB.

**Trigger:** User selects "Play → New Story"

**Flow:**
1. Select multiverse
2. Select universe
3. Prompt: Story title
4. Prompt: Story type (campaign, arc, episode, one-shot)
5. Prompt: Theme (optional)
6. Prompt: Premise (optional)
7. Select/create participating PCs
8. Create Story node in Neo4j
9. Create story_outline in MongoDB
10. → P-2 (Start first scene)

**Output:** story_id, ready for scene in the selected universe

---

## Layer 1: Data Layer Contracts

### Tool: `neo4j_get_universe`

**Purpose:** Validate that the universe exists before creating a story.

**Signature:**
```python
async def neo4j_get_universe(universe_id: str) -> Dict[str, Any]:
    pass
```

**Parameters:**
- `universe_id` (str): UUID of the universe to validate

**Returns:**
- `Dict[str, Any]`: Universe data containing:
  - `id` (str): Universe UUID
  - `name` (str): Universe name
  - `description` (str): Universe description
  - `multiverse_id` (str): Parent multiverse UUID

**Raises:**
- `UniverseNotFoundError`: If universe does not exist

**Example:**
```python
universe = await neo4j_get_universe("universe-123")
assert universe["id"] == "universe-123"
assert universe["name"] == "Forgotten Realms"
```

---

### Tool: `neo4j_create_story`

**Purpose:** Create a Story node in Neo4j.

**Signature:**
```python
async def neo4j_create_story(params: Dict[str, Any]) -> str:
    pass
```

**Parameters:**
- `params` (Dict[str, Any]): Story creation parameters:
  - `universe_id` (str, required): Universe UUID
  - `title` (str, required): Story title
  - `story_type` (str, required): Type of story ("campaign", "arc", "episode", "one-shot")
  - `theme` (str, optional): Story theme
  - `premise` (str, optional): Story premise
  - `status` (str, default="active"): Story status

**Returns:**
- `str`: story_id (UUID of newly created Story node)

**Raises:**
- `InvalidParameterError`: If required parameters are missing
- `UniverseNotFoundError`: If universe does not exist

**Example:**
```python
story_id = await neo4j_create_story({
    "universe_id": "universe-123",
    "title": "The Lost Mines of Phandelver",
    "story_type": "campaign",
    "theme": "Fantasy adventure",
    "premise": "A group of adventurers must rescue a dwarf from goblins.",
    "status": "active"
})
assert isinstance(story_id, str)
assert len(story_id) == 36  # UUID format
```

**Database Writes:**
```cypher
CREATE (s:Story {
    id: $story_id,
    universe_id: $universe_id,
    title: $title,
    story_type: $story_type,
    theme: $theme,
    premise: $premise,
    status: "active",
    created_at: datetime()
})
```

---

### Tool: `mongodb_create_story_outline`

**Purpose:** Create a story outline document in MongoDB.

**Signature:**
```python
async def mongodb_create_story_outline(params: Dict[str, Any]) -> str:
    pass
```

**Parameters:**
- `params` (Dict[str, Any]): Story outline parameters:
  - `story_id` (str, required): Story UUID (must match Neo4j Story node)
  - `beats` (list, default=[]): List of story beats/planning points
  - `pc_ids` (list, required): List of participating PC UUIDs

**Returns:**
- `str`: outline_id (UUID of newly created outline document)

**Raises:**
- `InvalidParameterError`: If required parameters are missing
- `StoryNotFoundError`: If story_id does not exist in Neo4j

**Example:**
```python
outline_id = await mongodb_create_story_outline({
    "story_id": "story-123",
    "beats": [
        {"order": 1, "title": "Introduction", "description": "Meet the party"},
        {"order": 2, "title": "Inciting Incident", "description": "Goblin ambush"}
    ],
    "pc_ids": ["pc-001", "pc-002", "pc-003"]
})
assert isinstance(outline_id, str)
```

**Database Writes:**
```javascript
{
  "_id": outline_id,
  "story_id": "story-123",
  "beats": [
    {"order": 1, "title": "Introduction", "description": "Meet the party"},
    {"order": 2, "title": "Inciting Incident", "description": "Goblin ambush"}
  ],
  "pc_ids": ["pc-001", "pc-002", "pc-003"],
  "created_at": ISODate("2025-01-19T00:00:00Z"),
  "updated_at": ISODate("2025-01-19T00:00:00Z")
}
```

---

## Layer 2: Agent Contracts

### Class: `StoryLoop`

**Purpose:** Manages the story lifecycle and creates the initial story and outline.

**Location:** `packages/agents/src/monitor_agents/loops/story_loop.py`

#### Method: `create_story`

**Signature:**
```python
async def create_story(
    self,
    universe_id: str,
    title: str,
    story_type: str,
    theme: Optional[str] = None,
    premise: Optional[str] = None,
    pc_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    pass
```

**Parameters:**
- `universe_id` (str, required): Universe UUID
- `title` (str, required): Story title
- `story_type` (str, required): Type of story ("campaign", "arc", "episode", "one-shot")
- `theme` (str, optional): Story theme
- `premise` (str, optional): Story premise
- `pc_ids` (List[str], optional): List of participating PC UUIDs (default: [])

**Returns:**
- `Dict[str, Any]`: Story creation result:
  - `story_id` (str): Story UUID
  - `outline_id` (str): Outline UUID
  - `status` (str): "success"

**Raises:**
- `UniverseNotFoundError`: If universe does not exist
- `InvalidParameterError`: If required parameters are missing or invalid
- `DatabaseError`: If database write fails

**Example:**
```python
result = await story_loop.create_story(
    universe_id="universe-123",
    title="The Lost Mines of Phandelver",
    story_type="campaign",
    theme="Fantasy adventure",
    premise="A group of adventurers must rescue a dwarf from goblins.",
    pc_ids=["pc-001", "pc-002", "pc-003"]
)
assert result["story_id"] == "story-123"
assert result["outline_id"] == "outline-456"
assert result["status"] == "success"
```

---

## Layer 3: CLI Contracts

### Command: `monitor play new`

**Purpose:** Start a new story from the CLI.

**Signature:**
```bash
monitor play new --universe <UUID> --title <TITLE> [OPTIONS]
```

**Parameters:**
- `--universe` (UUID, required): Universe UUID
- `--title` (string, required): Story title
- `--type` (string, optional): Story type (default: "campaign")
  - Options: "campaign", "arc", "episode", "one-shot"
- `--theme` (string, optional): Story theme
- `--premise` (string, optional): Story premise
- `--characters` (UUIDs, optional): Comma-separated list of PC UUIDs

**Returns:**
- CLI output with story_id and confirmation

**Exit Codes:**
- `0`: Success
- `1`: Error (invalid parameters, universe not found, database error)

**Example:**
```bash
$ monitor play new \
    --universe universe-123 \
    --title "The Lost Mines of Phandelver" \
    --type campaign \
    --theme "Fantasy adventure" \
    --premise "A group of adventurers must rescue a dwarf from goblins." \
    --characters pc-001,pc-002,pc-003

✅ Story created successfully
Story ID: story-123
Outline ID: outline-456
Ready to start scene → P-2
```

---

## Web API Contracts

### Endpoint: `POST /api/stories`

**Purpose:** Create a new story via web API.

**Location:** `packages/ui/backend/src/monitor_ui/routers/chat.py`

**Signature:**
```python
async def create_story(request: CreateStoryRequest) -> CreateStoryResponse:
    pass
```

**Request Body:**
```json
{
  "universe_id": "string (required)",
  "title": "string (required)",
  "story_type": "string (optional, default='campaign')",
  "theme": "string (optional)",
  "premise": "string (optional)",
  "pc_ids": ["string"] (optional)"
}
```

**Response Body (Success - 201):**
```json
{
  "story_id": "story-123",
  "outline_id": "outline-456",
  "status": "success",
  "created_at": "2025-01-19T00:00:00Z"
}
```

**Response Body (Error - 400):**
```json
{
  "error": "InvalidParameterError",
  "message": "Missing required parameter: title"
}
```

**Response Body (Error - 404):**
```json
{
  "error": "UniverseNotFoundError",
  "message": "Universe not found: universe-999"
}
```

---

## Sequence Diagram

```
User → Web UI / CLI
    │
    ├─→ StoryLoop.create_story()
    │       │
    │       ├─→ neo4j_get_universe(universe_id)  // Validate universe
    │       │       └─→ Returns universe data
    │       │
    │       ├─→ neo4j_create_story(params)  // Create Story node
    │       │       └─→ Returns story_id
    │       │
    │       ├─→ mongodb_create_story_outline(params)  // Create outline
    │       │       └─→ Returns outline_id
    │       │
    │       └─→ Returns {story_id, outline_id, status}
    │
    └─→ Display confirmation to user
```

---

## Database Schemas

### Neo4j: Story Node

**Label:** `:Story`

**Properties:**
- `id` (string, required, unique): Story UUID
- `universe_id` (string, required): Universe UUID (foreign key)
- `title` (string, required): Story title
- `story_type` (string, required): "campaign", "arc", "episode", or "one-shot"
- `theme` (string, optional): Story theme
- `premise` (string, optional): Story premise
- `status` (string, default="active"): "active", "paused", "completed"
- `created_at` (datetime, auto): Creation timestamp
- `updated_at` (datetime, auto): Last update timestamp

**Relationships:**
- `(:Story)-[:BELONGS_TO]->(:Universe)`: Story belongs to universe

**Example:**
```cypher
CREATE (s:Story {
    id: "story-123",
    universe_id: "universe-123",
    title: "The Lost Mines of Phandelver",
    story_type: "campaign",
    theme: "Fantasy adventure",
    premise: "A group of adventurers must rescue a dwarf from goblins.",
    status: "active",
    created_at: datetime(),
    updated_at: datetime()
})
CREATE (s)-[:BELONGS_TO]->(:Universe {id: "universe-123"})
```

---

### MongoDB: Story Outline Document

**Collection:** `story_outlines`

**Schema:**
```javascript
{
  "_id": string,           // Outline UUID (primary key)
  "story_id": string,      // Story UUID (foreign key to Neo4j)
  "beats": [               // List of story beats
    {
      "order": number,     // Beat order (1, 2, 3, ...)
      "title": string,     // Beat title
      "description": string // Beat description
    }
  ],
  "pc_ids": [string],      // List of participating PC UUIDs
  "created_at": datetime,  // Creation timestamp
  "updated_at": datetime   // Last update timestamp
}
```

**Indexes:**
- Index on `story_id` for lookups

**Example:**
```javascript
{
  "_id": "outline-456",
  "story_id": "story-123",
  "beats": [
    {"order": 1, "title": "Introduction", "description": "Meet the party"},
    {"order": 2, "title": "Inciting Incident", "description": "Goblin ambush"}
  ],
  "pc_ids": ["pc-001", "pc-002", "pc-003"],
  "created_at": ISODate("2025-01-19T00:00:00Z"),
  "updated_at": ISODate("2025-01-19T00:00:00Z")
}
```

---

## Error Handling

| Error | Condition | Response |
|-------|-----------|----------|
| `UniverseNotFoundError` | universe_id does not exist | 404 (API) / Exit code 1 (CLI) |
| `InvalidParameterError` | Missing required parameters | 400 (API) / Exit code 1 (CLI) |
| `DatabaseError` | Database write fails | 500 (API) / Exit code 1 (CLI) |

---

## Preconditions

1. **At least one multiverse exists:** System must have at least one multiverse configured
2. **At least one universe exists:** System must have at least one universe in the selected multiverse
3. **MongoDB connection:** Must be able to connect to MongoDB
4. **Neo4j connection:** Must be able to connect to Neo4j

---

## Postconditions

1. **Story node created:** Neo4j contains a `:Story` node with the specified parameters
2. **Outline document created:** MongoDB contains a `story_outlines` document linked to the story
3. **Story linked to universe:** Story node has a `:BELONGS_TO` relationship to the universe
4. **Ready for scene:** System is ready to proceed to P-2 (Start Scene)
5. **PCs linked:** Participating PCs are recorded in the outline document

---

## Dependencies

- **M-1:** Create Multiverse (multiverse must exist)
- **M-2:** Create Universe (universe must exist)
- **M-13:** Create Character (PCs must exist)

---

## Next Use Case

**P-2: Start Scene** - After story is created, the next step is to create the first scene.

---

**Last Updated:** 2025-01-19