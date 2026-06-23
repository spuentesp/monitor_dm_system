# P-2: Start Scene — Contract Specifications

## Overview

**Purpose:** Create a new scene in the system, including creating a scene document in MongoDB and generating opening narration.

**Trigger:** User selects "Play → New Scene" (or automatic after P-1)

**Flow:**
1. Prompt: Scene title
2. Prompt: Scene purpose/goal
3. Select location
4. Confirm entities present
5. Create Scene document in MongoDB
6. Narrator generates opening narration
7. Display opening narration
8. → P-3 (Turn Loop)

**Output:** scene_id, opening narration displayed

---

## Layer 1: Data Layer Contracts

### Tool: `neo4j_get_entity`

**Purpose:** Validate that the location entity exists before creating a scene.

**Signature:**
```python
async def neo4j_get_entity(entity_id: str) -> Dict[str, Any]:
    pass
```

**Parameters:**
- `entity_id` (str): UUID of the entity to retrieve

**Returns:**
- `Dict[str, Any]`: Entity data containing:
  - `id` (str): Entity UUID
  - `name` (str): Entity name
  - `type` (str): Entity type ("location", "character", "item", etc.)
  - `description` (str): Entity description
  - `universe_id` (str): Parent universe UUID

**Raises:**
- `EntityNotFoundError`: If entity does not exist

**Example:**
```python
location = await neo4j_get_entity("location-123")
assert location["id"] == "location-123"
assert location["name"] == "Phandalin"
assert location["type"] == "location"
```

---

### Tool: `neo4j_list_entities`

**Purpose:** List entities of a specific type in the universe (e.g., characters present in location).

**Signature:**
```python
async def neo4j_list_entities(
    universe_id: str,
    type: Optional[str] = None,
    location_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    pass
```

**Parameters:**
- `universe_id` (str): Universe UUID
- `type` (str, optional): Filter by entity type (e.g., "character")
- `location_id` (str, optional): Filter by location (entities present at location)

**Returns:**
- `List[Dict[str, Any]]`: List of entities, each containing:
  - `id` (str): Entity UUID
  - `name` (str): Entity name
  - `type` (str): Entity type
  - `description` (str): Entity description

**Example:**
```python
characters = await neo4j_list_entities(
    universe_id="universe-123",
    type="character",
    location_id="location-123"
)
assert len(characters) >= 1
assert characters[0]["type"] == "character"
```

---

### Tool: `mongodb_create_scene`

**Purpose:** Create a scene document in MongoDB.

**Signature:**
```python
async def mongodb_create_scene(params: Dict[str, Any]) -> str:
    pass
```

**Parameters:**
- `params` (Dict[str, Any]): Scene creation parameters:
  - `story_id` (str, required): Story UUID
  - `title` (str, required): Scene title
  - `purpose` (str, optional): Scene purpose/goal
  - `location_id` (str, required): Location UUID
  - `entity_ids` (list, default=[]): List of entity UUIDs present
  - `status` (str, default="active"): Scene status

**Returns:**
- `str`: scene_id (UUID of newly created scene document)

**Raises:**
- `InvalidParameterError`: If required parameters are missing
- `StoryNotFoundError`: If story_id does not exist

**Example:**
```python
scene_id = await mongodb_create_scene({
    "story_id": "story-123",
    "title": "Goblin Ambush",
    "purpose": "Introduce the party to goblin threat",
    "location_id": "location-123",
    "entity_ids": ["char-001", "char-002", "char-003", "goblin-001"],
    "status": "active"
})
assert isinstance(scene_id, str)
assert len(scene_id) == 36  # UUID format
```

**Database Writes:**
```javascript
{
  "_id": scene_id,
  "story_id": "story-123",
  "title": "Goblin Ambush",
  "purpose": "Introduce the party to goblin threat",
  "location_id": "location-123",
  "entity_ids": ["char-001", "char-002", "char-003", "goblin-001"],
  "status": "active",
  "created_at": ISODate("2025-01-19T00:00:00Z"),
  "updated_at": ISODate("2025-01-19T00:00:00Z")
}
```

---

### Tool: `mongodb_append_turn`

**Purpose:** Append a turn to the scene's turns array.

**Signature:**
```python
async def mongodb_append_turn(scene_id: str, turn: Dict[str, Any]) -> str:
    pass
```

**Parameters:**
- `scene_id` (str): Scene UUID
- `turn` (Dict[str, Any]): Turn data:
  - `order` (int, required): Turn order number
  - `type` (str, required): Turn type ("narrative", "player_action", "gm_action")
  - `content` (str, required): Turn content (narration or action description)
  - `actor` (str, optional): Actor ID (for player_action or gm_action)
  - `timestamp` (datetime, auto): Turn timestamp

**Returns:**
- `str`: turn_id (UUID of newly created turn)

**Raises:**
- `SceneNotFoundError`: If scene_id does not exist

**Example:**
```python
turn_id = await mongodb_append_turn("scene-456", {
    "order": 1,
    "type": "narrative",
    "content": "You are traveling down the Triboar Trail...",
    "actor": "narrator"
})
assert isinstance(turn_id, str)
```

**Database Writes:**
```javascript
// Update scenes collection
{
  "_id": "scene-456",
  // ... other scene fields
  "turns": [
    {
      "_id": turn_id,
      "order": 1,
      "type": "narrative",
      "content": "You are traveling down the Triboar Trail...",
      "actor": "narrator",
      "timestamp": ISODate("2025-01-19T00:00:00Z")
    }
  ]
}
```

---

### Tool: `qdrant_search`

**Purpose:** Search for relevant context (e.g., scene chunks) using semantic search.

**Signature:**
```python
async def qdrant_search(
    query: str,
    collection_name: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    pass
```

**Parameters:**
- `query` (str): Search query text
- `collection_name` (str): Qdrant collection name (e.g., "scene_chunks")
- `limit` (int, default=10): Maximum number of results

**Returns:**
- `List[Dict[str, Any]]`: List of search results, each containing:
  - `id` (str): Result UUID
  - `score` (float): Relevance score (0.0 to 1.0)
  - `payload` (Dict[str, Any]): Result payload containing:
    - `content` (str): Result content
    - `source` (str): Source reference
    - `metadata` (Dict[str, Any]): Additional metadata

**Example:**
```python
results = await qdrant_search(
    query="goblin ambush forest trail",
    collection_name="scene_chunks",
    limit=5
)
assert len(results) <= 5
if results:
    assert results[0]["score"] >= 0.0
    assert results[0]["score"] <= 1.0
```

---

## Layer 2: Agent Contracts

### Class: `Narrator`

**Purpose:** Generates narrative descriptions for scenes, actions, and other events.

**Location:** `packages/agents/src/monitor_agents/narrator.py`

#### Method: `generate_opening_narration`

**Signature:**
```python
async def generate_opening_narration(
    self,
    scene_id: str,
    location_id: str,
    entity_ids: List[str],
    purpose: Optional[str] = None
) -> str:
    pass
```

**Parameters:**
- `scene_id` (str, required): Scene UUID
- `location_id` (str, required): Location UUID
- `entity_ids` (List[str], required): List of entity UUIDs present
- `purpose` (str, optional): Scene purpose/goal

**Returns:**
- `str`: Opening narration text

**Raises:**
- `SceneNotFoundError`: If scene_id does not exist
- `LLMGenerationError`: If LLM fails to generate narration

**Example:**
```python
narration = await narrator.generate_opening_narration(
    scene_id="scene-456",
    location_id="location-123",
    entity_ids=["char-001", "char-002", "char-003"],
    purpose="Introduce the party to goblin threat"
)
assert isinstance(narration, str)
assert len(narration) > 0
```

---

### Class: `SceneLoop`

**Purpose:** Manages the scene lifecycle and transitions.

**Location:** `packages/agents/src/monitor_agents/loops/scene_loop.py`

#### Method: `create_scene`

**Signature:**
```python
async def create_scene(
    self,
    story_id: str,
    title: str,
    location_id: str,
    entity_ids: List[str],
    purpose: Optional[str] = None
) -> Dict[str, Any]:
    pass
```

**Parameters:**
- `story_id` (str, required): Story UUID
- `title` (str, required): Scene title
- `location_id` (str, required): Location UUID
- `entity_ids` (List[str], required): List of entity UUIDs present
- `purpose` (str, optional): Scene purpose/goal

**Returns:**
- `Dict[str, Any]`: Scene creation result:
  - `scene_id` (str): Scene UUID
  - `turn_id` (str): Opening turn UUID
  - `narration` (str): Opening narration text
  - `status` (str): "success"

**Raises:**
- `StoryNotFoundError`: If story_id does not exist
- `LocationNotFoundError`: If location_id does not exist
- `InvalidParameterError`: If required parameters are missing
- `DatabaseError`: If database write fails

**Example:**
```python
result = await scene_loop.create_scene(
    story_id="story-123",
    title="Goblin Ambush",
    location_id="location-123",
    entity_ids=["char-001", "char-002", "char-003", "goblin-001"],
    purpose="Introduce the party to goblin threat"
)
assert result["scene_id"] == "scene-456"
assert result["turn_id"] == "turn-789"
assert result["status"] == "success"
assert len(result["narration"]) > 0
```

---

## Layer 3: CLI Contracts

### Command: `monitor play scene`

**Purpose:** Start a new scene from the CLI.

**Signature:**
```bash
monitor play scene --story <UUID> --location <UUID> [OPTIONS]
```

**Parameters:**
- `--story` (UUID, required): Story UUID
- `--location` (UUID, required): Location UUID
- `--title` (string, optional): Scene title (if not provided, prompts user)
- `--purpose` (string, optional): Scene purpose/goal
- `--entities` (UUIDs, optional): Comma-separated list of entity UUIDs

**Returns:**
- CLI output with scene_id and opening narration

**Exit Codes:**
- `0`: Success
- `1`: Error (invalid parameters, story not found, location not found, database error)

**Example:**
```bash
$ monitor play scene \
    --story story-123 \
    --location location-123 \
    --title "Goblin Ambush" \
    --purpose "Introduce the party to goblin threat" \
    --entities char-001,char-002,char-003

✅ Scene created successfully
Scene ID: scene-456

Opening Narration:
You are traveling down the Triboar Trail when suddenly...

Ready for turn loop → P-3
```

---

## Web API Contracts

### Endpoint: `POST /api/scenes`

**Purpose:** Create a new scene via web API.

**Location:** `packages/ui/backend/src/monitor_ui/routers/chat.py`

**Signature:**
```python
async def create_scene(request: CreateSceneRequest) -> CreateSceneResponse:
    pass
```

**Request Body:**
```json
{
  "story_id": "string (required)",
  "title": "string (required)",
  "purpose": "string (optional)",
  "location_id": "string (required)",
  "entity_ids": ["string"] (optional)"
}
```

**Response Body (Success - 201):**
```json
{
  "scene_id": "scene-456",
  "turn_id": "turn-789",
  "narration": "You are traveling down the Triboar Trail...",
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
  "error": "StoryNotFoundError",
  "message": "Story not found: story-999"
}
```

---

## Sequence Diagram

```
User → Web UI / CLI
    │
    ├─→ SceneLoop.create_scene()
    │       │
    │       ├─→ neo4j_get_entity(location_id)  // Validate location
    │       │       └─→ Returns location data
    │       │
    │       ├─→ neo4j_list_entities(universe_id, type="character")  // Get available characters
    │       │       └─→ Returns list of characters
    │       │
    │       ├─→ qdrant_search(query, "scene_chunks")  // Search for context
    │       │       └─→ Returns relevant context
    │       │
    │       ├─→ mongodb_create_scene(params)  // Create scene document
    │       │       └─→ Returns scene_id
    │       │
    │       ├─→ Narrator.generate_opening_narration()  // Generate opening
    │       │       ├─→ Search context with Qdrant
    │       │       ├─→ Call LLM
    │       │       └─→ Returns narration text
    │       │
    │       ├─→ mongodb_append_turn(scene_id, turn)  // Append opening turn
    │       │       └─→ Returns turn_id
    │       │
    │       └─→ Returns {scene_id, turn_id, narration, status}
    │
    └─→ Display opening narration to user
```

---

## Database Schemas

### MongoDB: Scene Document

**Collection:** `scenes`

**Schema:**
```javascript
{
  "_id": string,              // Scene UUID (primary key)
  "story_id": string,         // Story UUID (foreign key)
  "title": string,            // Scene title
  "purpose": string,          // Scene purpose/goal (optional)
  "location_id": string,      // Location UUID (foreign key to Neo4j)
  "entity_ids": [string],     // List of entity UUIDs present
  "status": string,           // "active", "paused", "completed" (default: "active")
  "turns": [                  // Array of turn documents
    {
      "_id": string,          // Turn UUID
      "order": number,        // Turn order number
      "type": string,         // "narrative", "player_action", "gm_action"
      "content": string,      // Turn content
      "actor": string,        // Actor ID (optional)
      "timestamp": datetime   // Turn timestamp
    }
  ],
  "created_at": datetime,     // Creation timestamp
  "updated_at": datetime      // Last update timestamp
}
```

**Indexes:**
- Index on `story_id` for story queries
- Index on `location_id` for location queries

**Example:**
```javascript
{
  "_id": "scene-456",
  "story_id": "story-123",
  "title": "Goblin Ambush",
  "purpose": "Introduce the party to goblin threat",
  "location_id": "location-123",
  "entity_ids": ["char-001", "char-002", "char-003", "goblin-001"],
  "status": "active",
  "turns": [
    {
      "_id": "turn-789",
      "order": 1,
      "type": "narrative",
      "content": "You are traveling down the Triboar Trail...",
      "actor": "narrator",
      "timestamp": ISODate("2025-01-19T00:00:00Z")
    }
  ],
  "created_at": ISODate("2025-01-19T00:00:00Z"),
  "updated_at": ISODate("2025-01-19T00:00:00Z")
}
```

---

## Error Handling

| Error | Condition | Response |
|-------|-----------|----------|
| `StoryNotFoundError` | story_id does not exist | 404 (API) / Exit code 1 (CLI) |
| `LocationNotFoundError` | location_id does not exist | 404 (API) / Exit code 1 (CLI) |
| `InvalidParameterError` | Missing required parameters | 400 (API) / Exit code 1 (CLI) |
| `DatabaseError` | Database write fails | 500 (API) / Exit code 1 (CLI) |
| `LLMGenerationError` | LLM fails to generate narration | 500 (API) / Exit code 1 (CLI) |

---

## Preconditions

1. **Story exists:** A story must exist (created by P-1)
2. **Location exists:** The location must exist in the Neo4j database
3. **MongoDB connection:** Must be able to connect to MongoDB
4. **Neo4j connection:** Must be able to connect to Neo4j
5. **Qdrant connection:** Must be able to connect to Qdrant (for context search)
6. **LLM available:** LLM service must be available for narration generation

---

## Postconditions

1. **Scene document created:** MongoDB contains a scene document linked to the story
2. **Opening turn appended:** Scene document contains opening narration turn
3. **Narration generated:** Opening narration text is generated and displayed
4. **Ready for turn loop:** System is ready to proceed to P-3 (Turn Loop)
5. **Entities recorded:** Participating entities are recorded in the scene document

---

## Dependencies

- **P-1:** Start New Story (story must exist)
- **M-2:** Create Universe (universe must exist)
- **M-4:** Create Location (location must exist)
- **M-13:** Create Character (characters must exist)

---

## Next Use Case

**P-3: Turn Loop** - After scene is created and opening narration displayed, the next step is to start the turn loop.

---

**Last Updated:** 2025-01-19