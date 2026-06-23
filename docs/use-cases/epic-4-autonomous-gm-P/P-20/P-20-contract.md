# P-20: Forced Narrative Pushback - Contract Specifications

## Overview

Forced Narrative Pushback provides GM authority in single-player mode by pushing back against player abuse of forced narrative declarations (e.g., "I instantly kill the boss"). When the Resolver detects a forced narrative that involves a contested or high-stakes action, the Orchestrator pauses the turn and asks the player to confirm a roll or modifies the action into an attempt, ensuring stakes are preserved.

---

## Layer 1: Data Layer Contracts

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
        metadata: Optional metadata (forced_narrative, pushback, override, etc.)
    
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
    turn_type=TurnType.ACTION,
    content="I instantly kill the boss",
    scene_id="scene_456",
    metadata={
        "forced_narrative_detected": True,
        "pushback_triggered": True,
        "overridden": False,
        "stakes_level": "HIGH"
    }
)

# GM turn
gm_turn = mongodb_create_turn(
    speaker_id="system:pushback",
    turn_type=TurnType.NARRATION,
    content="You strike true, dealing a mighty blow to the boss!",
    scene_id="scene_456",
    metadata={
        "pushback_used": True,
        "overridden": False,
        "dice_roll_used": 18
    }
)
```

---

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
override_count = scene.metadata.get("override_count", 0)
```

---

### MongoDB: UpdateScene

**Purpose:** Update a scene's metadata (e.g., override_count) in MongoDB.

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
# Increment override_count
scene = mongodb_get_scene("scene_456")
override_count = scene.metadata.get("override_count", 0) + 1
updated_scene = mongodb_update_scene(
    "scene_456",
    {"metadata.override_count": override_count}
)
```

---

### MongoDB: OverrideLogCreate

**Purpose:** Create an override log entry in MongoDB.

**Signature:**
```python
def mongodb_create_override_log(
    scene_id: str,
    original_action: str,
    override_command: str,
    reason: str,
    stakes_level: str,
    timestamp: Optional[datetime] = None
) -> OverrideLog:
    """
    Create an override log entry in MongoDB.
    
    Args:
        scene_id: ID of the scene
        original_action: Original forced narrative action
        override_command: User's override command (e.g., "/gm-mode I ...")
        reason: Reason for override
        stakes_level: Stakes level (LOW, MEDIUM, HIGH)
        timestamp: Timestamp of override (defaults to now)
    
    Returns:
        OverrideLog: Created OverrideLog entry with assigned log_id
    
    Raises:
        ValidationError: If required fields are missing or invalid
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene
- `original_action` (str): Original forced narrative action
- `override_command` (str): User's override command
- `reason` (str): Reason for override
- `stakes_level` (str): Stakes level (LOW, MEDIUM, HIGH)
- `timestamp` (Optional[datetime]): Timestamp of override (defaults to now)

**Returns:**
- `OverrideLog`: Created OverrideLog entry with assigned log_id

**Raises:**
- `ValidationError`: If required fields are missing or invalid
- `DatabaseError`: If database operation fails

**Example:**
```python
from datetime import datetime
override_log = mongodb_create_override_log(
    scene_id="scene_456",
    original_action="I instantly kill the boss",
    override_command="/gm-mode I instantly kill the boss",
    reason="Player override of forced narrative pushback",
    stakes_level="HIGH",
    timestamp=datetime.now()
)
assert override_log.log_id is not None
```

---

## Layer 2: Agent Contracts

### Resolver.detect_forced_narrative

**Purpose:** Detect if user input contains forced narrative patterns.

**Signature:**
```python
def detect_forced_narrative(input: str) -> bool:
    """
    Detect if user input contains forced narrative patterns.
    
    Analyze user input for forced narrative patterns:
    - Instantaneous outcomes: "instantly", "immediately", "effortlessly"
    - Guaranteed success: "will succeed", "cannot fail", "guaranteed"
    - Magnitude violations: "kill the boss instantly", "destroy the entire room"
    - Declarative outcomes: "I kill the goblin" (no attempt language)
    
    Distinguish from normal actions:
    - Normal: "I attack the goblin" (attempt)
    - Forced: "I kill the goblin" (declarative)
    
    Args:
        input: User input string
    
    Returns:
        bool: True if forced narrative detected, False otherwise
    
    Raises:
        ParseError: If input parsing fails
    """
    pass
```

**Parameters:**
- `input` (str): User input string

**Returns:**
- `bool`: True if forced narrative detected, False otherwise

**Raises:**
- `ParseError`: If input parsing fails

**Example:**
```python
is_forced = detect_forced_narrative("I instantly kill the boss")
assert is_forced == True

is_forced = detect_forced_narrative("I attack the boss")
assert is_forced == False

is_forced = detect_forced_narrative("I pick the lock effortlessly")
assert is_forced == True
```

---

### Resolver.determine_stakes

**Purpose:** Determine the stakes level of an action.

**Signature:**
```python
def determine_stakes(
    action: str,
    context: Dict[str, Any]
) -> StakesLevel:
    """
    Determine the stakes level of an action.
    
    Analyze action and context to determine stakes:
    - Low stakes: Trivial actions, social interactions, environmental interactions
    - Medium stakes: Skill checks, minor challenges
    - High stakes: Combat, major plot points, significant challenges
    
    Args:
        action: User action string
        context: Scene context (entities, relationships, current state)
    
    Returns:
        StakesLevel: Stakes level (LOW, MEDIUM, or HIGH)
    
    Raises:
        StakesEvaluationError: If stakes evaluation fails
    """
    pass
```

**Parameters:**
- `action` (str): User action string
- `context` (Dict[str, Any]): Scene context (entities, relationships, current state)

**Returns:**
- `StakesLevel`: Stakes level (from enum: LOW, MEDIUM, or HIGH)

**Raises:**
- `StakesEvaluationError`: If stakes evaluation fails

**Example:**
```python
stakes = determine_stakes("I instantly kill the boss", {"entities": ["boss_npc"]})
assert stakes == StakesLevel.HIGH

stakes = determine_stakes("I open the door effortlessly", {})
assert stakes == StakesLevel.LOW

stakes = determine_stakes("I pick the lock effortlessly", {})
assert stakes == StakesLevel.MEDIUM
```

---

### SceneLoop.should_trigger_pushback

**Purpose:** Determine if pushback should be triggered based on stakes level.

**Signature:**
```python
def should_trigger_pushback(stakes: StakesLevel) -> bool:
    """
    Determine if pushback should be triggered based on stakes level.
    
    Compare stakes against pushback threshold:
    - HIGH stakes: Trigger mandatory pushback
    - MEDIUM stakes: Optional pushback (return False for mandatory)
    - LOW stakes: No pushback
    
    Args:
        stakes: Stakes level from determine_stakes()
    
    Returns:
        bool: True if pushback should be triggered, False otherwise
    
    Raises:
        ValueError: If stakes is invalid
    """
    pass
```

**Parameters:**
- `stakes` (StakesLevel): Stakes level from determine_stakes()

**Returns:**
- `bool`: True if pushback should be triggered, False otherwise

**Raises:**
- `ValueError`: If stakes is invalid

**Example:**
```python
should_pushback = should_trigger_pushback(StakesLevel.HIGH)
assert should_pushback == True

should_pushback = should_trigger_pushback(StakesLevel.MEDIUM)
assert should_pushback == False

should_pushback = should_trigger_pushback(StakesLevel.LOW)
assert should_pushback == False
```

---

### SceneLoop.generate_pushback_prompt

**Purpose:** Generate a pushback prompt explaining why pushback was triggered.

**Signature:**
```python
def generate_pushback_prompt(
    action: str,
    stakes: StakesLevel
) -> str:
    """
    Generate a pushback prompt explaining why pushback was triggered.
    
    Construct pushback prompt including:
    - Original action
    - Why pushback triggered
    - Options to accept or override
    - Warning about override logging
    
    Args:
        action: Original forced narrative action
        stakes: Stakes level that triggered pushback
    
    Returns:
        str: Pushback prompt
    
    Raises:
        PromptGenerationError: If prompt generation fails
    """
    pass
```

**Parameters:**
- `action` (str): Original forced narrative action
- `stakes` (StakesLevel): Stakes level that triggered pushback

**Returns:**
- `str`: Pushback prompt

**Raises:**
- `PromptGenerationError`: If prompt generation fails

**Example:**
```python
prompt = generate_pushback_prompt("I instantly kill the boss", StakesLevel.HIGH)
assert "PUSHBACK REQUIRED" in prompt
assert "I instantly kill the boss" in prompt
assert "high stakes" in prompt.lower()
assert "/gm-mode" in prompt
```

---

### SceneLoop.await_pushback_response

**Purpose:** Await and parse user's response to pushback prompt.

**Signature:**
```python
def await_pushback_response(
    user_input: str
) -> PushbackResponse:
    """
    Await and parse user's response to pushback prompt.
    
    Parse user response:
    - Override: starts with "/gm-mode"
    - Accept: action converted to attempt (dice roll)
    - Invalid: doesn't match patterns
    
    Args:
        user_input: User's response to pushback prompt
    
    Returns:
        PushbackResponse: Response type (ACCEPT, OVERRIDE, or INVALID)
    
    Raises:
        ValueError: If user_input is None or empty
    """
    pass
```

**Parameters:**
- `user_input` (str): User's response to pushback prompt

**Returns:**
- `PushbackResponse`: Response type (from enum: ACCEPT, OVERRIDE, or INVALID)

**Raises:**
- `ValueError`: If user_input is None or empty

**Example:**
```python
# Override
response = await_pushback_response("/gm-mode I instantly kill the boss")
assert response == PushbackResponse.OVERRIDE

# Accept
response = await_pushback_response("I attack the boss")
assert response == PushbackResponse.ACCEPT

# Invalid
response = await_pushback_response("What do you mean?")
assert response == PushbackResponse.INVALID
```

---

### Resolver.convert_to_dice_roll

**Purpose:** Convert forced narrative action to dice roll attempt.

**Signature:**
```python
def convert_to_dice_roll(action: str) -> str:
    """
    Convert forced narrative action to dice roll attempt.
    
    Parse forced narrative to extract intent:
    - "I instantly kill the boss" → "I attack the boss"
    - "I pick the lock effortlessly" → "I pick the lock"
    - "I cast a spell that destroys the entire room" → "I cast a spell"
    
    Convert to attempt language:
    - Add attempt verbs: "attack", "attempt to", "try to"
    - Remove instantaneous modifiers: "instantly", "effortlessly"
    
    Args:
        action: Forced narrative action
    
    Returns:
        str: Converted action as dice roll attempt
    
    Raises:
        ConversionError: If conversion fails
    """
    pass
```

**Parameters:**
- `action` (str): Forced narrative action

**Returns:**
- `str`: Converted action as dice roll attempt

**Raises:**
- `ConversionError`: If conversion fails

**Example:**
```python
converted = convert_to_dice_roll("I instantly kill the boss")
assert converted == "I attack the boss"

converted = convert_to_dice_roll("I pick the lock effortlessly")
assert converted == "I pick the lock"

converted = convert_to_dice_roll("I cast a spell that destroys the entire room")
assert "I cast a spell" in converted
```

---

### SceneLoop.log_override

**Purpose:** Log override event in MongoDB.

**Signature:**
```python
def log_override(
    scene_id: str,
    original_action: str,
    override_command: str,
    stakes_level: str
) -> None:
    """
    Log override event in MongoDB.
    
    Create override log entry and increment scene's override_count.
    Warn if override_count > 3.
    
    Args:
        scene_id: ID of the scene
        original_action: Original forced narrative action
        override_command: User's override command
        stakes_level: Stakes level (LOW, MEDIUM, HIGH)
    
    Raises:
        DatabaseError: If log creation or scene update fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene
- `original_action` (str): Original forced narrative action
- `override_command` (str): User's override command
- `stakes_level` (str): Stakes level (LOW, MEDIUM, HIGH)

**Returns:**
- None

**Raises:**
- `DatabaseError`: If log creation or scene update fails

**Example:**
```python
log_override(
    scene_id="scene_456",
    original_action="I instantly kill the boss",
    override_command="/gm-mode I instantly kill the boss",
    stakes_level="HIGH"
)
# Override logged in MongoDB
# Scene's override_count incremented
# Warning displayed if override_count > 3
```

---

### NarratorAgent.describe_outcome

**Purpose:** Generate narrative description of action outcome.

**Signature:**
```python
async def describe_outcome(
    action: str,
    outcome: ResolutionOutcome,
    pushback_used: bool
) -> str:
    """
    Generate narrative description of action outcome.
    
    Generate narrative description:
    - If pushback accepted and dice roll succeeded: Describe success with effort
    - If pushback accepted and dice roll failed: Describe failure with consequences
    - If overridden: Describe as declared
    
    Incorporate pushback context:
    - If pushback used: "After a tense roll..."
    - If overridden: "As you commanded..."
    
    Args:
        action: User action
        outcome: Resolution outcome from dice roll
        pushback_used: Whether pushback was used
    
    Returns:
        str: Narrative description
    
    Raises:
        NarratorError: If narrator fails to generate description
    """
    pass
```

**Parameters:**
- `action` (str): User action
- `outcome` (ResolutionOutcome): Resolution outcome from dice roll
- `pushback_used` (bool): Whether pushback was used

**Returns:**
- `str`: Narrative description

**Raises:**
- `NarratorError`: If narrator fails to generate description

**Example:**
```python
# Success with pushback
narrative = await describe_outcome(
    "I attack the boss",
    ResolutionOutcome.SUCCESS,
    pushback_used=True
)
assert "strike true" in narrative.lower()

# Failure with pushback
narrative = await describe_outcome(
    "I attack the boss",
    ResolutionOutcome.FAILURE,
    pushback_used=True
)
assert "misses" in narrative.lower() or "fail" in narrative.lower()

# Override
narrative = await describe_outcome(
    "I instantly kill the boss",
    ResolutionOutcome.SUCCESS,
    pushback_used=False
)
assert "instantly" in narrative.lower()
```

---

### SceneLoop.append_pushback_turns

**Purpose:** Create and append user and GM turns for pushback scenario.

**Signature:**
```python
async def append_pushback_turns(
    scene_id: str,
    user_action: str,
    response: str,
    user_id: str,
    forced_narrative: bool,
    pushback_used: bool,
    overridden: bool,
    stakes_level: Optional[str] = None,
    dice_roll_result: Optional[int] = None
) -> Tuple[Turn, Turn]:
    """
    Create and append user and GM turns for pushback scenario.
    
    Create user turn (ACTION).
    Create GM turn (NARRATION).
    Append both turns to scene.
    
    Args:
        scene_id: ID of the scene
        user_action: User's action
        response: GM's narrative response
        user_id: ID of the user
        forced_narrative: Whether forced narrative was detected
        pushback_used: Whether pushback was triggered
        overridden: Whether user overrode pushback
        stakes_level: Stakes level (if pushback used)
        dice_roll_result: Dice roll result (if pushback accepted)
    
    Returns:
        Tuple[Turn, Turn]: Tuple of (user_turn, gm_turn)
    
    Raises:
        DatabaseError: If turn creation or append fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene
- `user_action` (str): User's action
- `response` (str): GM's narrative response
- `user_id` (str): ID of the user
- `forced_narrative` (bool): Whether forced narrative was detected
- `pushback_used` (bool): Whether pushback was triggered
- `overridden` (bool): Whether user overrode pushback
- `stakes_level` (Optional[str]): Stakes level (if pushback used)
- `dice_roll_result` (Optional[int]): Dice roll result (if pushback accepted)

**Returns:**
- `Tuple[Turn, Turn]`: Tuple of (user_turn, gm_turn)

**Raises:**
- `DatabaseError`: If turn creation or append fails

**Example:**
```python
user_turn, gm_turn = await append_pushback_turns(
    scene_id="scene_456",
    user_action="I attack the boss",
    response="You strike true, dealing a mighty blow to the boss!",
    user_id="user_123",
    forced_narrative=True,
    pushback_used=True,
    overridden=False,
    stakes_level="HIGH",
    dice_roll_result=18
)
assert user_turn.turn_type == TurnType.ACTION
assert gm_turn.turn_type == TurnType.NARRATION
assert user_turn.metadata["forced_narrative_detected"] == True
assert gm_turn.metadata["pushback_used"] == True
```

---

## Layer 3: CLI Contracts

### Command: `/gm-mode`

**Purpose:** Override forced narrative pushback and execute action as declared.

**Signature:**
```bash
monitor-cli --gm-mode <action>
```

**Parameters:**
- `--gm-mode` (flag): Enable GM override mode
- `<action>` (str): Action to execute (required)

**Returns:**
- Exit code: 0 on success, non-zero on error
- Output:
  - Action executed as declared
  - Override logged
  - Warning if override_count > 3

**Example:**
```bash
$ monitor-cli --gm-mode "I instantly kill the boss"
⚠️ GM MODE OVERRIDE
Action: "I instantly kill the boss"
Override logged: Yes
Narrator: "With supernatural speed, you strike the boss down in an instant."
```

---

## Integration Tests

### Test 1: Combat - High Stakes Pushback

**Setup:**
```python
# Create test scene
scene = create_test_scene(world_id="world_123")

# Mock dependencies
mock_resolver = Mock()
mock_scene_loop = Mock()
mock_narrator = AsyncMock()
```

**Execute:**
```python
# Detect forced narrative
is_forced = detect_forced_narrative("I instantly kill the boss")
assert is_forced == True

# Determine stakes
stakes = determine_stakes("I instantly kill the boss", {"entities": ["boss_npc"]})
assert stakes == StakesLevel.HIGH

# Check if pushback should trigger
should_pushback = should_trigger_pushback(stakes)
assert should_pushback == True

# Generate pushback prompt
prompt = generate_pushback_prompt("I instantly kill the boss", StakesLevel.HIGH)
assert "PUSHBACK REQUIRED" in prompt

# User accepts pushback
response = await_pushback_response("I attack the boss")
assert response == PushbackResponse.ACCEPT

# Convert to dice roll
converted = convert_to_dice_roll("I instantly kill the boss")
assert converted == "I attack the boss"

# Resolve action with dice roll (mock roll to 18)
with patch('monitor_agents.resolver.roll_dice', return_value=18):
    outcome = resolve_action(converted, context)
    assert outcome == ResolutionOutcome.SUCCESS

# Generate narrative
narrative = await describe_outcome(converted, outcome, pushback_used=True)
assert narrative is not None

# Append turns
user_turn, gm_turn = await append_pushback_turns(
    scene_id=scene.scene_id,
    user_action="I attack the boss",
    response=narrative,
    user_id="user_123",
    forced_narrative=True,
    pushback_used=True,
    overridden=False,
    stakes_level="HIGH",
    dice_roll_result=18
)
```

**Assert:**
```python
# Verify all steps succeeded
assert user_turn.turn_type == TurnType.ACTION
assert gm_turn.turn_type == TurnType.NARRATION
assert user_turn.metadata["forced_narrative_detected"] == True
assert user_turn.metadata["pushback_triggered"] == True
assert user_turn.metadata["overridden"] == False
assert gm_turn.metadata["pushback_used"] == True
assert gm_turn.metadata["dice_roll_used"] == 18
```

---

### Test 2: Override with /gm-mode

**Setup:**
```python
# Create test scene
scene = create_test_scene(world_id="world_123")
```

**Execute:**
```python
# Detect forced narrative
is_forced = detect_forced_narrative("I instantly kill the boss")
assert is_forced == True

# Determine stakes
stakes = determine_stakes("I instantly kill the boss", {"entities": ["boss_npc"]})
assert stakes == StakesLevel.HIGH

# Generate pushback prompt
prompt = generate_pushback_prompt("I instantly kill the boss", StakesLevel.HIGH)
assert "/gm-mode" in prompt

# User overrides
response = await_pushback_response("/gm-mode I instantly kill the boss")
assert response == PushbackResponse.OVERRIDE

# Log override
log_override(
    scene_id=scene.scene_id,
    original_action="I instantly kill the boss",
    override_command="/gm-mode I instantly kill the boss",
    stakes_level="HIGH"
)

# Generate narrative (override context)
narrative = await describe_outcome("I instantly kill the boss", ResolutionOutcome.SUCCESS, pushback_used=False)
assert "instantly" in narrative.lower()

# Append turns
user_turn, gm_turn = await append_pushback_turns(
    scene_id=scene.scene_id,
    user_action="I instantly kill the boss",
    response=narrative,
    user_id="user_123",
    forced_narrative=True,
    pushback_used=True,
    overridden=True,
    stakes_level="HIGH"
)
```

**Assert:**
```python
# Verify override was logged
assert user_turn.metadata["overridden"] == True
assert gm_turn.metadata["overridden"] == True
# Check override_count was incremented
updated_scene = mongodb_get_scene(scene.scene_id)
assert updated_scene.metadata.get("override_count", 0) == 1
```

---

### Test 3: Low Stakes - No Pushback

**Setup:**
```python
# Create test scene
scene = create_test_scene(world_id="world_123")
```

**Execute:**
```python
# Detect forced narrative
is_forced = detect_forced_narrative("I open the door effortlessly")
assert is_forced == True

# Determine stakes
stakes = determine_stakes("I open the door effortlessly", {})
assert stakes == StakesLevel.LOW

# Check if pushback should trigger
should_pushback = should_trigger_pushback(stakes)
assert should_pushback == False

# No pushback triggered, action proceeds as declared
```

**Assert:**
```python
# Verify pushback was NOT triggered
assert should_pushback == False
```

---

### Test 4: Medium Stakes - Optional Pushback

**Setup:**
```python
# Create test scene
scene = create_test_scene(world_id="world_123")
```

**Execute:**
```python
# Detect forced narrative
is_forced = detect_forced_narrative("I pick the lock effortlessly")
assert is_forced == True

# Determine stakes
stakes = determine_stakes("I pick the lock effortlessly", {})
assert stakes == StakesLevel.MEDIUM

# Check if pushback should trigger
should_pushback = should_trigger_pushback(stakes)
assert should_pushback == False  # Optional, not mandatory

# System may suggest pushback but doesn't require it
```

**Assert:**
```python
# Verify pushback is optional
assert should_pushback == False
```

---

### Test 5: Multiple Overrides Warning

**Setup:**
```python
# Create test scene with override_count = 3
scene = create_test_scene(world_id="world_123")
mongodb_update_scene(scene.scene_id, {"metadata.override_count": 3})
```

**Execute:**
```python
# Detect forced narrative
is_forced = detect_forced_narrative("I instantly defeat the dragon")
assert is_forced == True

# User overrides
response = await_pushback_response("/gm-mode I instantly defeat the dragon")
assert response == PushbackResponse.OVERRIDE

# Log override (should trigger warning)
log_override(
    scene_id=scene.scene_id,
    original_action="I instantly defeat the dragon",
    override_command="/gm-mode I instantly defeat the dragon",
    stakes_level="HIGH"
)

# Check if warning was displayed
# (In real implementation, this would capture console output)
```

**Assert:**
```python
# Verify override_count was incremented to 4
updated_scene = mongodb_get_scene(scene.scene_id)
assert updated_scene.metadata.get("override_count", 0) == 4
# Warning should be displayed (verify in console output)
```

---

## Validation Checklist

- [ ] All function signatures match behavior specifications
- [ ] All parameters are typed correctly
- [ ] All return types are documented
- [ ] All error cases are specified
- [ ] All examples are valid
- [ ] Integration tests pass
- [ ] Override logging is enforced (every override logged)
- [ ] Override tracking is accurate (override_count updated)
- [ ] Override warnings displayed when override_count > 3
- [ ] Stakes evaluation is 100% accurate for high stakes
- [ ] Pushback only triggers for high stakes (mandatory)
- [ ] Pushback is optional for medium stakes
- [ ] Pushback is skipped for low stakes
- [ ] Turn metadata includes all required fields (forced_narrative, pushback, override, stakes_level, dice_roll)
- [ ] Conversion to dice roll preserves intent
- [ ] Narrator respects pushback context

---

## Related Documentation

- [P-20-behaviors.md](../behaviors/P-20-behaviors.md) - Behavior definition
- [USE_CASE_BEHAVIORS_INDEX.md](../USE_CASE_BEHAVIORS_INDEX.md) - Use case index
- [TEST_GAPS_ANALYSIS.md](../../TEST_GAPS_ANALYSIS.md) - Test gap analysis
- [TESTING_INDEX.md](../../TESTING_INDEX.md) - Testing master index

---

**Last Updated:** 2026-05-19
**Status:** ✅ Contract specifications complete