# P-4: Resolve Action — Contract Specification

## Use Case Overview

**P-4: Resolve Action** handles the outcome determination and narration for player actions that require resolution. It's called from P-3 (Turn Loop) when a player takes an action that has mechanical consequences (e.g., attacking, using skills, attempting challenges).

### Purpose

P-4 is responsible for:
- Determining how actions are resolved (dice vs. narrative vs. auto-success/auto-fail)
- Rolling dice when necessary
- Creating ProposedChanges for canon state changes
- Generating narration of action outcomes
- Returning results to P-3 to append to the scene turn log

### Flow

1. Parse action intent from player input
2. Identify target entity and difficulty (if applicable)
3. Determine resolution type (Dice/Narrative/Auto-Success/Auto-Fail)
4. If Dice resolution → call P-9 (Dice Roll)
5. Calculate outcome (CRITICAL_SUCCESS, SUCCESS, PARTIAL, FAILURE, CRITICAL_FAILURE)
6. Create ProposedChanges for canon state changes
7. Narrate outcome through Narrator
8. Return resolution results to P-3

---

## Layer 1: Data Layer Tool Contracts

### Tool 1: `neo4j_get_entity`

**Purpose:** Retrieve entity details from Neo4j (for target identification and entity state).

**Signature:**
```python
async def neo4j_get_entity(entity_id: str) -> Entity
```

**Parameters:**
- `entity_id` (str, required): Unique identifier of the entity to retrieve

**Returns:**
```python
Entity = {
    "id": str,              # Unique entity identifier
    "name": str,            # Entity name
    "type": str,            # "character", "location", "item", etc.
    "universe_id": str,     # Parent universe identifier
    "attributes": dict,     # Entity attributes (stats, tags, etc.)
    "relationships": list,  # Entity relationships
    "canon": dict,          # Canon facts about entity
    # Additional entity-specific fields...
}
```

**Error Handling:**
- Raises `EntityNotFoundError` when `entity_id` does not exist in Neo4j
- Raises `InvalidParameterError` when `entity_id` is empty or malformed

**Contract:**
- Returns a complete Entity object with all standard fields
- Entity includes current state (attributes) for resolution calculation
- Raises descriptive errors when entity cannot be found

---

### Tool 2: `dice_roll`

**Purpose:** Roll dice according to formula and return detailed roll information.

**Signature:**
```python
async def dice_roll(formula: str) -> DiceRoll
```

**Parameters:**
- `formula` (str, required): Dice notation (e.g., "1d20", "2d6+3", "4d6kh3")

**Returns:**
```python
DiceRoll = {
    "formula": str,         # Original dice formula (e.g., "1d20+5")
    "rolls": List[int],     # Individual die results (e.g., [17])
    "total": int,           # Sum of all rolls + modifiers (e.g., 22)
    "success": bool,        # Whether total met or exceeded target (if applicable)
    "details": dict,        # Additional roll metadata
}
```

**Supported Notations:**
- Standard: `NdS` (e.g., "1d20", "2d6")
- Modifiers: `+N`, `-N` (e.g., "1d20+5", "2d6-1")
- Keep Highest: `NdSkhX` (e.g., "4d6kh3")
- Keep Lowest: `NdSklX` (e.g., "4d6kl3")
- Advantage/Disadvantage: (handled by calling multiple 1d20 rolls)

**Error Handling:**
- Raises `InvalidDiceFormulaError` when `formula` is malformed
- Raises `InvalidParameterError` when `formula` is empty

**Contract:**
- Parses dice formula according to standard RPG notation
- Returns all individual die results for transparency
- Calculates total correctly including modifiers
- Supports standard D&D 5e dice mechanics

---

### Tool 3: `mongodb_create_resolution`

**Purpose:** Store resolution details in MongoDB for reference and canon audit.

**Signature:**
```python
async def mongodb_create_resolution(params: dict) -> str
```

**Parameters:**
```python
{
    "scene_id": str,          # (required) Scene identifier
    "turn_id": str,           # (required) Turn identifier (user turn)
    "action": str,            # (required) Player action text
    "formula": str,           # (required if Dice resolution) Dice formula used
    "rolls": List[int],       # (required if Dice resolution) Individual die results
    "total": int,             # (required if Dice resolution) Total roll result
    "outcome": str,           # (required) Outcome type (CRITICAL_SUCCESS, SUCCESS, PARTIAL, FAILURE, CRITICAL_FAILURE)
    "dc": int,                # (required if Dice resolution) Difficulty class
    "resolution_type": str,   # (required) Resolution type (DICE, NARRATIVE, AUTO_SUCCESS, AUTO_FAIL)
    "target_id": str,         # (optional) Target entity identifier
    "effect_id": str,         # (optional) Associated effect identifier
    "metadata": dict,         # (optional) Additional resolution metadata
}
```

**Returns:**
- `resolution_id` (str): Unique identifier of the created resolution document

**Error Handling:**
- Raises `ValidationError` when required parameters are missing
- Raises `InvalidParameterError` when parameters are malformed
- Raises `DatabaseError` when MongoDB write fails

**Contract:**
- Creates resolution document in `resolutions` collection
- Returns resolution_id as string (UUID format)
- Stores all resolution details for audit and canon reference
- Links resolution to scene and turn for traceability

---

### Tool 4: `mongodb_create_proposal`

**Purpose:** Create a proposal for canon state change (already tested in P-3, but used in P-4).

**Signature:**
```python
async def mongodb_create_proposal(scene_id: str, type: str, content: dict, status: str = "pending") -> str
```

**Parameters:**
```python
{
    "scene_id": str,          # (required) Scene identifier
    "type": str,              # (required) Proposal type: "state_change", "entity_create", "relationship_create"
    "content": dict,          # (required) Proposal content:
    {
        "entity_id": str,     # (required for state_change) Target entity identifier
        "tag": str,           # (required for state_change) Attribute tag to modify
        "action": str,        # (required for state_change) Action: "set", "increment", "decrement"
        "value": Any,         # (required for state_change) Value to set/change
    },
    "status": str,            # (optional) Proposal status: "pending", "approved", "rejected" (default: "pending")
}
```

**Returns:**
- `proposal_id` (str): Unique identifier of the created proposal

**Error Handling:**
- Raises `ValidationError` when required parameters are missing
- Raises `InvalidParameterError` when parameters are malformed
- Raises `DatabaseError` when MongoDB write fails

**Contract:**
- Creates proposal document in `proposed_changes` collection
- Returns proposal_id as string (UUID format)
- Stores proposal with pending status for CanonKeeper review
- Links proposal to scene for context

---

## Layer 2: Agent Contracts

### Agent 1: `Resolver.resolve_action`

**Purpose:** Determine action outcome and create resolution record.

**Signature:**
```python
async def resolve_action(
    scene_id: str,
    turn_id: str,
    action: str,
    actor_id: str,
    context: dict
) -> dict
```

**Parameters:**
```python
{
    "scene_id": str,          # (required) Scene identifier
    "turn_id": str,           # (required) Turn identifier (user turn)
    "action": str,            # (required) Player action text (e.g., "I attack the goblin")
    "actor_id": str,          # (required) Actor entity identifier
    "context": dict,          # (required) Assembled context:
    {
        "scene": dict,        # Scene details
        "location": dict,     # Location details
        "entities": list,     # Entities present
        "recent_turns": list, # Recent turn history
        "summary": str,       # Context summary
    }
}
```

**Returns:**
```python
{
    "resolution_id": str,     # Resolution identifier (UUID)
    "resolution_type": str,   # Resolution type: DICE, NARRATIVE, AUTO_SUCCESS, AUTO_FAIL
    "outcome": str,           # Outcome: CRITICAL_SUCCESS, SUCCESS, PARTIAL, FAILURE, CRITICAL_FAILURE
    "dice_result": dict,      # (if DICE) Dice roll result:
    {
        "formula": str,       # Dice formula used
        "rolls": list,        # Individual die results
        "total": int,         # Total result
        "dc": int,            # Difficulty class
    },
    "target_id": str,         # (if applicable) Target entity identifier
    "proposal_ids": list,     # List of proposal IDs for canon changes
    "narration_seed": str,    # Seed text for narration generation
}
```

**Error Handling:**
- Raises `ResolutionError` when resolution cannot be determined
- Raises `EntityNotFoundError` when target entity does not exist
- Raises `InvalidParameterError` when parameters are malformed

**Contract:**
- Determines resolution type based on action context and difficulty
- Calls dice_roll for DICE resolution type
- Calculates outcome based on roll result vs. DC
- Creates resolution record in MongoDB
- Creates proposals for canon state changes
- Returns complete resolution information for narration

---

### Agent 2: `Resolver.evaluate_difficulty`

**Purpose:** Determine difficulty class (DC) for an action.

**Signature:**
```python
async def evaluate_difficulty(
    action: str,
    target_id: str,
    context: dict
) -> int
```

**Parameters:**
```python
{
    "action": str,            # (required) Player action text
    "target_id": str,         # (optional) Target entity identifier
    "context": dict,          # (required) Assembled context
}
```

**Returns:**
- `dc` (int): Difficulty class (5-30 scale)

**Standard DC Scale:**
- **5**: Trivial (nearly automatic)
- **10**: Easy (most characters will succeed)
- **15**: Medium (challenging but doable)
- **20**: Hard (requires skill or luck)
- **25**: Very Hard (expert-level challenge)
- **30**: Nearly Impossible (only legendary feats)

**Error Handling:**
- Returns `0` when no DC applies (narrative resolution)

**Contract:**
- Analyzes action to determine required difficulty
- Considers target capabilities and environment factors
- Returns DC on standard 5-30 scale
- Returns 0 for narrative-only actions

---

### Agent 3: `Resolver.determine_effects`

**Purpose:** Determine canon state changes resulting from action outcome.

**Signature:**
```python
async def determine_effects(
    action: str,
    outcome: str,
    target_id: str,
    context: dict
) -> list
```

**Parameters:**
```python
{
    "action": str,            # (required) Player action text
    "outcome": str,           # (required) Outcome type
    "target_id": str,         # (optional) Target entity identifier
    "context": dict,          # (required) Assembled context
}
```

**Returns:**
```python
list of dicts, where each dict is:
{
    "type": str,              # "state_change", "entity_create", "relationship_create"
    "entity_id": str,         # Target entity identifier
    "tag": str,               # Attribute tag to modify
    "action": str,            # "set", "increment", "decrement"
    "value": Any,             # Value to set/change
}
```

**Contract:**
- Analyzes outcome to determine state changes
- Creates effect proposals for canon changes
- Returns list of effects sorted by priority
- Returns empty list for outcomes with no mechanical effects

---

### Agent 4: `Narrator.describe_action_result`

**Purpose:** Generate narration for action outcome.

**Signature:**
```python
async def describe_action_result(
    context: dict,
    action: str,
    outcome: str,
    resolution: dict
) -> str
```

**Parameters:**
```python
{
    "context": dict,          # (required) Assembled context (scene, location, entities, turns)
    "action": str,            # (required) Player action text
    "outcome": str,           # (required) Outcome type
    "resolution": dict,       # (required) Resolution result:
    {
        "resolution_id": str,
        "resolution_type": str,
        "outcome": str,
        "dice_result": dict,  # (if applicable)
        "target_id": str,     # (if applicable)
    }
}
```

**Returns:**
- `narration` (str): Narrated description of action outcome

**Contract:**
- Generates vivid, engaging narration of action result
- Incorporates outcome type (success/failure degree)
- References target and mechanical details if applicable
- Matches narrative tone to context and action
- Returns narrative text as string (100-500 words typical)

---

## Enums

### `ResolutionType`

**Purpose:** Enumeration of resolution types for actions.

**Values:**
```python
class ResolutionType(Enum):
    DICE = "DICE"                     # Roll dice to determine outcome
    NARRATIVE = "NARRATIVE"           # Story-driven outcome (no dice)
    AUTO_SUCCESS = "AUTO_SUCCESS"     # Automatic success (no roll needed)
    AUTO_FAIL = "AUTO_FAIL"           # Automatic failure (no roll needed)
```

**Usage:**
- `ResolutionType.DICE`: Use when outcome is uncertain and has mechanical consequences
- `ResolutionType.NARRATIVE`: Use when outcome is story-driven with no mechanical impact
- `ResolutionType.AUTO_SUCCESS`: Use when action always succeeds (e.g., opening unlocked door)
- `ResolutionType.AUTO_FAIL`: Use when action cannot succeed (e.g., attacking invulnerable entity)

---

### `Outcome`

**Purpose:** Enumeration of possible action outcomes.

**Values:**
```python
class Outcome(Enum):
    CRITICAL_SUCCESS = "CRITICAL_SUCCESS"  # Roll >= DC + 10, or maximum success
    SUCCESS = "SUCCESS"                    # Roll >= DC, or ordinary success
    PARTIAL = "PARTIAL"                    # Roll >= DC - 5, or mixed success
    FAILURE = "FAILURE"                    # Roll >= DC - 10, or ordinary failure
    CRITICAL_FAILURE = "CRITICAL_FAILURE"  # Roll < DC - 10, or maximum failure
```

**Usage:**
- `CRITICAL_SUCCESS`: Exceptional success with bonuses (e.g., double damage, extra effect)
- `SUCCESS`: Ordinary success with intended effect
- `PARTIAL`: Mixed success (intended effect achieved partially or with complications)
- `FAILURE`: Ordinary failure (no effect achieved)
- `CRITICAL_FAILURE`: Exceptional failure with penalties (e.g., damage to actor, setback)

---

## Helper Functions

### Function: `calculate_dc(action_difficulty: str) -> int`

**Purpose:** Calculate DC from action difficulty string.

**Signature:**
```python
def calculate_dc(action_difficulty: str) -> int
```

**Parameters:**
- `action_difficulty` (str, required): Difficulty description ("trivial", "easy", "medium", "hard", "very hard", "nearly impossible")

**Returns:**
- `dc` (int): Difficulty class (5-30 scale)

**Mapping:**
```python
{
    "trivial": 5,
    "easy": 10,
    "medium": 15,
    "hard": 20,
    "very hard": 25,
    "nearly impossible": 30,
}
```

**Error Handling:**
- Returns `15` (medium) for unknown difficulty strings

---

### Function: `map_outcome(total: int, dc: int) -> Outcome`

**Purpose:** Map roll result to outcome type.

**Signature:**
```python
def map_outcome(total: int, dc: int) -> Outcome
```

**Parameters:**
- `total` (int, required): Total dice roll result
- `dc` (int, required): Difficulty class

**Returns:**
- `Outcome`: Outcome type enum value

**Mapping:**
```python
if total >= dc + 10:
    return Outcome.CRITICAL_SUCCESS
elif total >= dc:
    return Outcome.SUCCESS
elif total >= dc - 5:
    return Outcome.PARTIAL
elif total >= dc - 10:
    return Outcome.FAILURE
else:
    return Outcome.CRITICAL_FAILURE
```

**Examples:**
- `map_outcome(25, 15)` → `CRITICAL_SUCCESS` (25 >= 15 + 10)
- `map_outcome(18, 15)` → `SUCCESS` (18 >= 15)
- `map_outcome(12, 15)` → `PARTIAL` (12 >= 15 - 5)
- `map_outcome(5, 15)` → `FAILURE` (5 >= 15 - 10)
- `map_outcome(3, 15)` → `CRITICAL_FAILURE` (3 < 15 - 10)

---

## Database Writes

### MongoDB: `resolutions` Collection

**Purpose:** Store resolution details for canon audit and reference.

**Document Structure:**
```python
{
    "_id": str,                  # Resolution identifier (UUID)
    "scene_id": str,             # Scene identifier
    "turn_id": str,              # Turn identifier (user turn)
    "action": str,               # Player action text
    "resolution_type": str,      # Resolution type (DICE, NARRATIVE, AUTO_SUCCESS, AUTO_FAIL)
    "formula": str,              # Dice formula (if DICE)
    "rolls": List[int],          # Individual die results (if DICE)
    "total": int,                # Total roll result (if DICE)
    "outcome": str,              # Outcome type
    "dc": int,                   # Difficulty class (if DICE)
    "target_id": str,            # Target entity identifier (if applicable)
    "effect_id": str,            # Associated effect identifier (if applicable)
    "metadata": dict,            # Additional resolution metadata
    "created_at": datetime,      # Timestamp
}
```

**Indexes:**
- Index on `scene_id` for scene-based queries
- Index on `turn_id` for turn-based queries
- Index on `target_id` for entity-based queries

---

### MongoDB: `proposed_changes` Collection

**Purpose:** Store proposals for canon state changes (same as P-3).

**Document Structure:**
```python
{
    "_id": str,                  # Proposal identifier (UUID)
    "scene_id": str,             # Scene identifier
    "type": str,                 # Proposal type: "state_change", "entity_create", "relationship_create"
    "content": dict,             # Proposal content:
    {
        "entity_id": str,        # Target entity identifier
        "tag": str,              # Attribute tag to modify
        "action": str,           # Action: "set", "increment", "decrement"
        "value": Any,            # Value to set/change
    },
    "status": str,               # Proposal status: "pending", "approved", "rejected"
    "resolution_ref": str,       # Reference to resolution that created this proposal
    "created_at": datetime,      # Timestamp
    "updated_at": datetime,      # Timestamp
}
```

**Usage in P-4:**
- Created for each canon state change resulting from action outcome
- Links to resolution for traceability
- Reviewed and committed by CanonKeeper

---

## Error Handling

### Error: `ResolutionError`

**Purpose:** Raised when resolution cannot be determined.

**Conditions:**
- When action cannot be parsed or understood
- When resolution type cannot be determined
- When required context is missing

**Message Format:**
```
ResolutionError: Could not resolve action: {action} - {reason}
```

---

### Error: `EntityNotFoundError`

**Purpose:** Raised when target entity does not exist.

**Conditions:**
- When `target_id` does not exist in Neo4j
- When entity reference is invalid

**Message Format:**
```
EntityNotFoundError: Entity not found: {entity_id}
```

---

### Error: `InvalidDiceFormulaError`

**Purpose:** Raised when dice formula is malformed.

**Conditions:**
- When `formula` cannot be parsed
- When formula contains invalid notation

**Message Format:**
```
InvalidDiceFormulaError: Invalid dice formula: {formula}
```

---

## Contract Testing

### Contract Test Coverage

**Data Layer Tool Contracts:**
- ✅ neo4j_get_entity: Returns Entity object with all required fields
- ✅ dice_roll: Returns DiceRoll with formula, rolls, total
- ✅ mongodb_create_resolution: Creates resolution and returns resolution_id
- ✅ mongodb_create_proposal: Creates proposal and returns proposal_id

**Agent Contracts:**
- ✅ Resolver.resolve_action: Returns complete resolution information
- ✅ Resolver.evaluate_difficulty: Returns DC on 5-30 scale
- ✅ Resolver.determine_effects: Returns list of effect proposals
- ✅ Narrator.describe_action_result: Returns narration text

**Helper Functions:**
- ✅ calculate_dc: Returns correct DC for difficulty strings
- ✅ map_outcome: Returns correct Outcome for roll vs DC

**Error Handling:**
- ✅ ResolutionError for unresolvable actions
- ✅ EntityNotFoundError for missing targets
- ✅ InvalidDiceFormulaError for malformed formulas

---

**Last Updated:** 2025-01-19