# P-3: Turn Loop — Contract Specifications

## Overview

**Purpose:** The heart of the game - manage the continuous loop of user input, action resolution, and narrative response within a scene.

**Trigger:** Within an active scene (after P-2 or continuing from previous turn)

**Flow (Continuous Loop):**
```
LOOP:
  1. Display context: location, present entities, recent turns
  2. Await user input
  3. Parse input type (action, dialogue, question, meta-command)
  4. Route to appropriate handler (P-4, P-5, P-6, P-7)
  5. Process through handler (resolve action, generate response, etc.)
  6. Narrator generates response narration
  7. Append user turn to MongoDB
  8. Append GM turn to MongoDB
  9. Create ProposedChanges if canonical changes needed
  10. Check if scene should end
  11. IF end → P-8 (End Scene)
  12. ELSE → continue loop (go to step 1)
```

**Output:** Continuous gameplay loop until scene ends

---

## Layer 1: Data Layer Contracts

### Tool: `mongodb_get_scene`

**Purpose:** Retrieve the current scene state from MongoDB.

**Signature:**
```python
async def mongodb_get_scene(scene_id: str) -> Dict[str, Any]:
    pass
```

**Parameters:**
- `scene_id` (str): Scene UUID

**Returns:**
- `Dict[str, Any]`: Scene data containing:
  - `_id` (str): Scene UUID
  - `story_id` (str): Story UUID
  - `title` (str): Scene title
  - `location_id` (str): Location UUID
  - `entity_ids` (List[str]): List of entity UUIDs present
  - `status` (str): Scene status ("active", "paused", "completed")
  - `turns` (List[Dict[str, Any]]): Array of turn documents
  - `created_at` (datetime): Creation timestamp
  - `updated_at` (datetime): Last update timestamp

**Raises:**
- `SceneNotFoundError`: If scene_id does not exist

**Example:**
```python
scene = await mongodb_get_scene("scene-456")
assert scene["_id"] == "scene-456"
assert scene["title"] == "Goblin Ambush"
assert scene["status"] == "active"
assert len(scene["turns"]) >= 1
```

---

### Tool: `mongodb_get_turns`

**Purpose:** Retrieve recent turns from a scene for context.

**Signature:**
```python
async def mongodb_get_turns(
    scene_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    pass
```

**Parameters:**
- `scene_id` (str): Scene UUID
- `limit` (int, default=10): Maximum number of recent turns to retrieve

**Returns:**
- `List[Dict[str, Any]]`: List of turn documents, sorted by order (most recent last), each containing:
  - `_id` (str): Turn UUID
  - `order` (int): Turn order number
  - `type` (str): Turn type ("narrative", "player_action", "gm_action")
  - `content` (str): Turn content
  - `actor` (str, optional): Actor ID (for player_action or gm_action)
  - `timestamp` (datetime): Turn timestamp

**Example:**
```python
turns = await mongodb_get_turns("scene-456", limit=10)
assert isinstance(turns, list)
assert len(turns) <= 10
assert turns[0]["order"] == 1  # First turn
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
  - `order` (int, required): Turn order number (auto-incremented)
  - `type` (str, required): Turn type ("narrative", "player_action", "gm_action")
  - `content` (str, required): Turn content (narration or action description)
  - `actor` (str, optional): Actor ID (for player_action or gm_action)
  - `resolution_ref` (str, optional): Reference to resolution document (for action turns)

**Returns:**
- `str`: turn_id (UUID of newly created turn)

**Raises:**
- `SceneNotFoundError`: If scene_id does not exist

**Example:**
```python
turn_id = await mongodb_append_turn("scene-456", {
    "order": 2,
    "type": "player_action",
    "content": "I attack the goblin with my sword",
    "actor": "char-001"
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
      "_id": "turn-789",
      "order": 1,
      "type": "narrative",
      "content": "You are traveling down the Triboar Trail...",
      "actor": "narrator",
      "timestamp": ISODate("2025-01-19T00:00:00Z")
    },
    {
      "_id": "turn-790",
      "order": 2,
      "type": "player_action",
      "content": "I attack the goblin with my sword",
      "actor": "char-001",
      "timestamp": ISODate("2025-01-19T00:00:05Z")
    }
  ]
}
```

---

### Tool: `mongodb_create_proposal`

**Purpose:** Create a proposal for canonical changes (if action implies state change).

**Signature:**
```python
async def mongodb_create_proposal(params: Dict[str, Any]) -> str:
    pass
```

**Parameters:**
- `params` (Dict[str, Any]): Proposal parameters:
  - `scene_id` (str, required): Scene UUID
  - `type` (str, required): Proposal type ("state_change", "fact_addition", "fact_removal")
  - `content` (Dict[str, Any], required): Proposal content:
    - `entity_id` (str): Entity UUID
    - `tag` (str): Entity tag/property
    - `action` (str): Action to perform ("set", "increment", "decrement")
    - `value` (Any): New value (for "set" action)
  - `status` (str, default="pending"): Proposal status

**Returns:**
- `str`: proposal_id (UUID of newly created proposal)

**Example:**
```python
proposal_id = await mongodb_create_proposal({
    "scene_id": "scene-456",
    "type": "state_change",
    "content": {
        "entity_id": "goblin-001",
        "tag": "health",
        "action": "decrement",
        "value": 10
    },
    "status": "pending"
})
assert isinstance(proposal_id, str)
```

**Database Writes:**
```javascript
{
  "_id": proposal_id,
  "scene_id": "scene-456",
  "type": "state_change",
  "content": {
    "entity_id": "goblin-001",
    "tag": "health",
    "action": "decrement",
    "value": 10
  },
  "status": "pending",
  "created_at": ISODate("2025-01-19T00:00:00Z")
}
```

---

## Layer 2: Agent Contracts

### Class: `TurnState`

**Purpose:** Enum representing the current state of the turn loop.

**Location:** `packages/agents/src/monitor_agents/loops/scene_loop.py`

**Values:**
```python
class TurnState(Enum):
    AWAITING_INPUT = "awaiting_input"  # Waiting for user input
    PROCESSING = "processing"           # Processing user input
    RESOLVING = "resolving"             # Resolving action (dice, checks)
    RESPONDING = "responding"           # Generating narrative response
    CHECKING_END = "checking_end"       # Checking if scene should end
```

---

### Class: `SceneLoop`

**Purpose:** Main scene-level controller for live play. Manages the turn loop.

**Location:** `packages/agents/src/monitor_agents/loops/scene_loop.py`

#### Method: `run`

**Signature:**
```python
async def run(
    self,
    scene_id: str
) -> AsyncIterator[Dict[str, Any]]:
    pass
```

**Parameters:**
- `scene_id` (str): Scene UUID

**Yields:**
- `Dict[str, Any]`: Turn result containing:
  - `turn_id` (str): Turn UUID
  - `state` (TurnState): Current turn state
  - `content` (str): Turn content (for display)
  - `is_last_turn` (bool): Whether this is the last turn before scene ends

**Raises:**
- `SceneNotFoundError`: If scene_id does not exist
- `InvalidStateError`: If scene is not in active status

**Example:**
```python
scene_loop = SceneLoop(mcp_client=fake_mcp_client, llm_client=fake_llm_client)

async for turn_result in scene_loop.run("scene-456"):
    print(f"Turn: {turn_result['content']}")
    if turn_result['is_last_turn']:
        break
```

#### Method: `process_turn`

**Signature:**
```python
async def process_turn(
    self,
    scene_id: str,
    user_input: str
) -> Dict[str, Any]:
    pass
```

**Parameters:**
- `scene_id` (str): Scene UUID
- `user_input` (str): User's input text

**Returns:**
- `Dict[str, Any]`: Turn processing result:
  - `user_turn_id` (str): User turn UUID
  - `gm_turn_id` (str): GM response turn UUID
  - `proposal_ids` (List[str]): List of proposal UUIDs (if any)
  - `input_type` (str): Parsed input type ("action", "dialogue", "question", "meta_command")
  - `content` (str): Narrative response content
  - `scene_ended` (bool): Whether scene should end after this turn

**Raises:**
- `SceneNotFoundError`: If scene_id does not exist
- `InvalidInputError`: If user_input is invalid or malformed

**Example:**
```python
result = await scene_loop.process_turn(
    scene_id="scene-456",
    user_input="I attack the goblin with my sword"
)
assert result["input_type"] == "action"
assert result["scene_ended"] == False
assert "user_turn_id" in result
assert "gm_turn_id" in result
```

---

### Class: `ContextAssembly`

**Purpose:** Builds turn context for narrative generation and action resolution.

**Location:** `packages/agents/src/monitor_agents/context_assembly.py`

#### Method: `assemble`

**Signature:**
```python
async def assemble(
    self,
    scene_id: str,
    limit: int = 10
) -> Dict[str, Any]:
    pass
```

**Parameters:**
- `scene_id` (str): Scene UUID
- `limit` (int, default=10): Maximum number of recent turns to include

**Returns:**
- `Dict[str, Any]`: Assembled context containing:
  - `scene` (Dict[str, Any]): Scene data
  - `location` (Dict[str, Any]): Location data (from Neo4j)
  - `entities` (List[Dict[str, Any]]): List of entities present
  - `recent_turns` (List[Dict[str, Any]]): Recent turns
  - `summary` (str): Text summary of context

**Raises:**
- `SceneNotFoundError`: If scene_id does not exist

**Example:**
```python
context = await context_assembly.assemble("scene-456", limit=10)
assert "scene" in context
assert "location" in context
assert "entities" in context
assert "recent_turns" in context
assert "summary" in context
```

---

### Class: `Narrator`

**Purpose:** Generates narrative descriptions for turns.

**Location:** `packages/agents/src/monitor_agents/narrator.py`

#### Method: `generate`

**Signature:**
```python
async def generate(
    self,
    context: Dict[str, Any],
    action: Optional[str] = None,
    input_type: Optional[str] = None
) -> str:
    pass
```

**Parameters:**
- `context` (Dict[str, Any], required): Context from ContextAssembly
- `action` (str, optional): Action being taken (for action responses)
- `input_type` (str, optional): Input type ("action", "dialogue", "question", "meta_command")

**Returns:**
- `str`: Narrative text

**Raises:**
- `LLMGenerationError`: If LLM fails to generate narration

**Example:**
```python
narration = await narrator.generate(
    context=context,
    action="I attack the goblin with my sword",
    input_type="action"
)
assert isinstance(narration, str)
assert len(narration) > 0
```

---

## Input Parsing Logic

### Function: `parse_input`

**Purpose:** Parse user input to determine input type.

**Signature:**
```python
def parse_input(text: str) -> InputType:
    pass
```

**Returns:**
- `InputType`: Enum value ("meta_command", "dialogue", "question", "action")

**Logic:**
```python
class InputType(Enum):
    META_COMMAND = "meta_command"
    DIALOGUE = "dialogue"
    QUESTION = "question"
    ACTION = "action"

def parse_input(text: str) -> InputType:
    if text.startswith("/"):
        return InputType.META_COMMAND
    if text.startswith('"') or "say" in text.lower():
        return InputType.DIALOGUE
    if "?" in text or text.lower().startswith(("what", "who", "where", "how", "why")):
        return InputType.QUESTION
    return InputType.ACTION
```

**Examples:**
```python
assert parse_input("/save") == InputType.META_COMMAND
assert parse_input('"Hello there!"') == InputType.DIALOGUE
assert parse_input("say: Hello") == InputType.DIALOGUE
assert parse_input("What do the goblins look like?") == InputType.QUESTION
assert parse_input("I attack the goblin") == InputType.ACTION
```

---

## Sequence Diagram

```
User → Web UI / CLI
    │
    ├─→ SceneLoop.run(scene_id)
    │       │
    │       ├─→ mongodb_get_scene(scene_id)  // Get scene state
    │       │       └─→ Returns scene data
    │       │
    │       ├─→ mongodb_get_turns(scene_id, limit=10)  // Get recent context
    │       │       └─→ Returns recent turns
    │       │
    │       ├─→ ContextAssembly.assemble()  // Build context
    │       │       ├─→ Get location data
    │       │       ├─→ Get entity data
    │       │       └─→ Returns context
    │       │
    │       ├─→ Display context to user
    │       │
    │       ├─→ Await user input
    │       │       ← User provides input
    │       │
    │       ├─→ parse_input(user_input)  // Parse input type
    │       │       └─→ Returns InputType
    │       │
    │       ├─→ SceneLoop.process_turn(user_input)
    │       │       │
    │       │       ├─→ Route to handler (P-4, P-5, P-6, P-7)
    │       │       │       └─→ e.g., Resolver.resolve_action()
    │       │       │
    │       │       ├─→ Narrator.generate(context, action, input_type)
    │       │       │       ├─→ Search context with Qdrant
    │       │       │       ├─→ Call LLM
    │       │       │       └─→ Returns narration
    │       │       │
    │       │       ├─→ mongodb_append_turn(scene_id, user_turn)  // Append user turn
    │       │       │       └─→ Returns user_turn_id
    │       │       │
    │       │       ├─→ mongodb_append_turn(scene_id, gm_turn)  // Append GM turn
    │       │       │       └─→ Returns gm_turn_id
    │       │       │
    │       │       ├─→ mongodb_create_proposal(...)  // If canonical changes needed
    │       │       │       └─→ Returns proposal_id
    │       │       │
    │       │       └─→ Returns {user_turn_id, gm_turn_id, proposal_ids, content, scene_ended}
    │       │
    │       ├─→ Display GM response to user
    │       │
    │       ├─→ Check if scene should end
    │       │
    │       └─→ IF scene_ended → P-8 (End Scene)
    │       ELSE → Continue loop
    │
    └─→ Display continuous gameplay
```

---

## Database Schemas

### MongoDB: Scene Document (Turns Array)

**Collection:** `scenes`

**Turns Array Schema:**
```javascript
{
  "_id": string,              // Scene UUID (primary key)
  // ... other scene fields
  "turns": [                  // Array of turn documents
    {
      "_id": string,          // Turn UUID
      "order": number,        // Turn order number (1, 2, 3, ...)
      "type": string,         // "narrative", "player_action", "gm_action"
      "content": string,      // Turn content
      "actor": string,        // Actor ID (optional)
      "resolution_ref": string, // Reference to resolution document (optional)
      "timestamp": datetime   // Turn timestamp
    }
  ]
}
```

**Example:**
```javascript
{
  "_id": "scene-456",
  "turns": [
    {
      "_id": "turn-789",
      "order": 1,
      "type": "narrative",
      "content": "You are traveling down the Triboar Trail...",
      "actor": "narrator",
      "timestamp": ISODate("2025-01-19T00:00:00Z")
    },
    {
      "_id": "turn-790",
      "order": 2,
      "type": "player_action",
      "content": "I attack the goblin with my sword",
      "actor": "char-001",
      "resolution_ref": "resolution-123",
      "timestamp": ISODate("2025-01-19T00:00:05Z")
    },
    {
      "_id": "turn-791",
      "order": 3,
      "type": "gm_action",
      "content": "Your sword strikes true! The goblin takes 8 damage and collapses...",
      "actor": "gm",
      "timestamp": ISODate("2025-01-19T00:00:10Z")
    }
  ]
}
```

---

### MongoDB: Proposed Changes Document

**Collection:** `proposed_changes`

**Schema:**
```javascript
{
  "_id": string,           // Proposal UUID (primary key)
  "scene_id": string,      // Scene UUID (foreign key)
  "type": string,          // "state_change", "fact_addition", "fact_removal"
  "content": {
    "entity_id": string,   // Entity UUID
    "tag": string,         // Entity tag/property
    "action": string,      // "set", "increment", "decrement"
    "value": any           // New value (for "set" action)
  },
  "status": string,        // "pending", "approved", "rejected"
  "created_at": datetime   // Creation timestamp
}
```

**Example:**
```javascript
{
  "_id": "proposal-456",
  "scene_id": "scene-456",
  "type": "state_change",
  "content": {
    "entity_id": "goblin-001",
    "tag": "health",
    "action": "decrement",
    "value": 8
  },
  "status": "pending",
  "created_at": ISODate("2025-01-19T00:00:10Z")
}
```

---

## Error Handling

| Error | Condition | Response |
|-------|-----------|----------|
| `SceneNotFoundError` | scene_id does not exist | 404 (API) / Error message |
| `InvalidStateError` | Scene is not in active status | 400 (API) / Error message |
| `InvalidInputError` | User input is invalid or malformed | 400 (API) / Error message |
| `LLMGenerationError` | LLM fails to generate narration | 500 (API) / Retry |
| `DatabaseError` | Database operation fails | 500 (API) / Retry |

---

## Preconditions

1. **Scene exists:** A scene must exist (created by P-2)
2. **Scene is active:** Scene must have status "active"
3. **MongoDB connection:** Must be able to connect to MongoDB
4. **Neo4j connection:** Must be able to connect to Neo4j (for entity data)
5. **Qdrant connection:** Must be able to connect to Qdrant (for context search)
6. **LLM available:** LLM service must be available for narration generation

---

## Postconditions

1. **User turn appended:** User turn is appended to scene's turns array
2. **GM turn appended:** GM response turn is appended to scene's turns array
3. **Proposals created:** ProposedChanges are created for canonical state changes
4. **Context preserved:** All turns are preserved in MongoDB
5. **Scene state updated:** Scene's updated_at timestamp is updated

---

## Dependencies

- **P-2:** Start Scene (scene must exist and be active)
- **P-4:** Resolve Action (for action inputs)
- **P-5:** Handle Dialogue (for dialogue inputs)
- **P-6:** Answer Question (for question inputs)
- **P-7:** Handle Meta-Command (for meta-commands)
- **P-8:** End Scene (when scene ends)
- **M-2:** Create Universe (universe must exist)
- **M-4:** Create Location (location must exist)
- **M-13:** Create Character (characters must exist)

---

## Next Use Cases

- **P-4: Resolve Action** - If user input is an action
- **P-5: Handle Dialogue** - If user input is dialogue
- **P-6: Answer Question** - If user input is a question
- **P-7: Handle Meta-Command** - If user input is a meta-command
- **P-8: End Scene** - When scene should end

---

**Last Updated:** 2025-01-19