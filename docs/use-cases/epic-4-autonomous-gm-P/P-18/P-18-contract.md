# P-18: AutoGM Oracle & Probability Resolution - Contract Specifications

## Overview

The AutoGM Oracle provides probability-based resolution for questions about unknown environmental states in single-player mode. It uses a percentile die (1d100) to determine Yes/No outcomes, with modifiers for "Yes, and" or "No, but" on extreme rolls.

---

## Layer 1: Data Layer Contracts

### MongoDB: FactCreate

**Purpose:** Create a new Fact entity in MongoDB to store oracle results.

**Signature:**
```python
def mongodb_create_fact(
    entity_id: str,
    fact_type: FactType,
    content: str,
    canon_level: CanonLevel,
    evidence_refs: List[str],
    metadata: Optional[Dict[str, Any]] = None
) -> Fact:
    """
    Create a new Fact entity in MongoDB.
    
    Args:
        entity_id: Unique identifier for the fact (hash of query for oracle results)
        fact_type: Type of fact (e.g., FactType.WORLD_PROPERTY)
        content: Text content of the fact (e.g., "Is the door locked?: Yes")
        canon_level: Canonicality level (e.g., CanonLevel.CARDS for game world truth)
        evidence_refs: List of evidence references (e.g., ["oracle:60:5"])
        metadata: Optional additional metadata
    
    Returns:
        Fact: Created Fact entity with assigned fact_id
    
    Raises:
        ValidationError: If required fields are missing or invalid
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `entity_id` (str): Unique identifier for the fact
- `fact_type` (FactType): Type of fact (from enum: WORLD_PROPERTY, RELATIONSHIP, etc.)
- `content` (str): Text content of the fact
- `canon_level` (CanonLevel): Canonicality level (from enum: CARDS, GAME, WORLD)
- `evidence_refs` (List[str]): List of evidence references
- `metadata` (Optional[Dict[str, Any]]): Optional additional metadata

**Returns:**
- `Fact`: Created Fact entity with assigned fact_id

**Raises:**
- `ValidationError`: If required fields are missing or invalid
- `DatabaseError`: If database operation fails

**Example:**
```python
fact = mongodb_create_fact(
    entity_id="hash(is_door_locked)",
    fact_type=FactType.WORLD_PROPERTY,
    content="Is the door locked?: Yes",
    canon_level=CanonLevel.CARDS,
    evidence_refs=["oracle:60:5"],
    metadata={"oracle_query": True, "roll": 60, "tension_score": 5}
)
assert fact.fact_id is not None
assert fact.content == "Is the door locked?: Yes"
```

---

### MongoDB: TurnCreate

**Purpose:** Create a new Turn entity in MongoDB to track user questions and oracle responses.

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
        speaker_id: ID of the speaker (user_id for player, "system:oracle" for GM)
        turn_type: Type of turn (e.g., TurnType.QUESTION, TurnType.ORACLE_RESPONSE)
        content: Text content of the turn
        scene_id: ID of the scene this turn belongs to
        metadata: Optional metadata (e.g., oracle_query=True for user questions)
    
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
- `turn_type` (TurnType): Type of turn (from enum: QUESTION, ORACLE_RESPONSE, MOVEMENT, etc.)
- `content` (str): Text content of the turn
- `scene_id` (str): ID of the scene this turn belongs to
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
    turn_type=TurnType.QUESTION,
    content="Is the door locked?",
    scene_id="scene_456",
    metadata={"oracle_query": True}
)

# GM turn
gm_turn = mongodb_create_turn(
    speaker_id="system:oracle",
    turn_type=TurnType.ORACLE_RESPONSE,
    content="The door is indeed locked, a sturdy wooden barrier barring your path.",
    scene_id="scene_456",
    metadata={
        "oracle_result": "yes",
        "roll": 60,
        "likelihood": "fifty_fifty",
        "fact_canonized": fact_id
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
tension_score = scene.tension_score
```

---

### MongoDB: UpdateScene

**Purpose:** Update a scene's metadata (e.g., updated_at timestamp) in MongoDB.

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
        updates: Dictionary of fields to update (e.g., {"updated_at": datetime.now()})
    
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
from datetime import datetime
updated_scene = mongodb_update_scene(
    "scene_456",
    {"updated_at": datetime.now()}
)
```

---

### Neo4j: CanonKeeper - Evaluate Fact

**Purpose:** CanonKeeper evaluates a fact for consistency before committing to Neo4j.

**Signature:**
```python
async def canonkeeper_evaluate_fact(fact: Fact) -> CanonEvaluationResult:
    """
    Evaluate a fact for consistency before committing to Neo4j.
    
    Args:
        fact: Fact entity to evaluate
    
    Returns:
        CanonEvaluationResult: Evaluation result with verdict and explanations
    
    Raises:
        CanonKeeperError: If CanonKeeper is unavailable
    """
    pass
```

**Parameters:**
- `fact` (Fact): Fact entity to evaluate

**Returns:**
- `CanonEvaluationResult`: Evaluation result with verdict and explanations
  - `verdict` (CanonVerdict): ACCEPT, REJECT, DEFER, or NEEDS_REVIEW
  - `explanation` (str): Explanation for the verdict
  - `conflicts` (List[str]): List of conflicting facts (if any)

**Raises:**
- `CanonKeeperError`: If CanonKeeper is unavailable

**Example:**
```python
evaluation = await canonkeeper_evaluate_fact(fact)
if evaluation.verdict == CanonVerdict.ACCEPT:
    # Fact is consistent, can commit
    pass
elif evaluation.verdict == CanonVerdict.REJECT:
    # Fact conflicts with canon
    print(f"Fact rejected: {evaluation.explanation}")
```

---

### Neo4j: CanonKeeper - Commit Fact

**Purpose:** CanonKeeper commits a fact to Neo4j as canonical truth.

**Signature:**
```python
async def canonkeeper_commit_fact(fact: Fact) -> str:
    """
    Commit a fact to Neo4j as canonical truth.
    
    Args:
        fact: Fact entity to commit
    
    Returns:
        str: Neo4j node ID of the committed fact
    
    Raises:
        CanonKeeperError: If CanonKeeper is unavailable
        ConsistencyError: If fact conflicts with existing canon
    """
    pass
```

**Parameters:**
- `fact` (Fact): Fact entity to commit

**Returns:**
- `str`: Neo4j node ID of the committed fact

**Raises:**
- `CanonKeeperError`: If CanonKeeper is unavailable
- `ConsistencyError`: If fact conflicts with existing canon

**Example:**
```python
neo4j_id = await canonkeeper_commit_fact(fact)
print(f"Fact committed to Neo4j with ID: {neo4j_id}")
```

---

## Layer 2: Agent Contracts

### ContextAssembly.detect_oracle_query

**Purpose:** Detect if user input is an oracle query (question) vs. an action declaration.

**Signature:**
```python
def detect_oracle_query(input: str) -> bool:
    """
    Detect if user input is an oracle query (question) vs. an action declaration.
    
    Args:
        input: User input string
    
    Returns:
        bool: True if oracle query detected, False otherwise
    
    Raises:
        ParseError: If input parsing fails
    """
    pass
```

**Parameters:**
- `input` (str): User input string

**Returns:**
- `bool`: True if oracle query detected, False otherwise

**Raises:**
- `ParseError`: If input parsing fails

**Example:**
```python
is_oracle = detect_oracle_query("Is the door locked?")
assert is_oracle == True

is_oracle = detect_oracle_query("I kick the door open")
assert is_oracle == False
```

---

### OracleAgent.determine_likelihood

**Purpose:** Determine likelihood level based on scene tension score.

**Signature:**
```python
def determine_likelihood(tension_score: int) -> LikelihoodLevel:
    """
    Determine likelihood level based on scene tension score.
    
    Args:
        tension_score: Scene tension score (0-10)
    
    Returns:
        LikelihoodLevel: Likelihood level for oracle roll
    
    Raises:
        ValidationError: If tension_score is out of range (not 0-10)
    """
    pass
```

**Parameters:**
- `tension_score` (int): Scene tension score (0-10)

**Returns:**
- `LikelihoodLevel`: Likelihood level for oracle roll (from enum)
  - `ALMOST_CERTAIN`: 0-2
  - `LIKELY`: 3-4
  - `FIFTY_FIFTY`: 5-6
  - `UNLIKELY`: 7-8
  - `IMPOSSIBLE`: 9-10

**Raises:**
- `ValidationError`: If tension_score is out of range (not 0-10)

**Example:**
```python
likelihood = determine_likelihood(5)
assert likelihood == LikelihoodLevel.FIFTY_FIFTY

likelihood = determine_likelihood(9)
assert likelihood == LikelihoodLevel.IMPOSSIBLE
```

---

### OracleAgent.roll_percentile

**Purpose:** Roll a percentile die (1d100) to determine oracle outcome.

**Signature:**
```python
def roll_percentile() -> int:
    """
    Roll a percentile die (1d100) to determine oracle outcome.
    
    Returns:
        int: Roll result between 1 and 100 (inclusive)
    
    Raises:
        RandomNumberError: If random number generator fails
    """
    pass
```

**Parameters:**
- None

**Returns:**
- `int`: Roll result between 1 and 100 (inclusive)

**Raises:**
- `RandomNumberError`: If random number generator fails

**Example:**
```python
roll = roll_percentile()
assert 1 <= roll <= 100
```

---

### OracleAgent.determine_outcome

**Purpose:** Determine oracle outcome based on roll result and likelihood level.

**Signature:**
```python
def determine_outcome(
    roll: int,
    likelihood: LikelihoodLevel
) -> OracleOutcome:
    """
    Determine oracle outcome based on roll result and likelihood level.
    
    Args:
        roll: Percentile roll result (1-100)
        likelihood: Likelihood level from determine_likelihood()
    
    Returns:
        OracleOutcome: Oracle outcome (from enum)
        - YES: Basic yes
        - NO: Basic no
        - YES_AND: Yes with extra benefit (roll 96-100)
        - NO_BUT: No with mitigating factor (roll 96-100 for unlikely/impossible)
        - NO_AND: No with additional complication (roll 00-05 for almost_certain/likely)
    
    Raises:
        ValidationError: If roll is out of range (not 1-100)
    """
    pass
```

**Parameters:**
- `roll` (int): Percentile roll result (1-100)
- `likelihood` (LikelihoodLevel): Likelihood level from determine_likelihood()

**Returns:**
- `OracleOutcome`: Oracle outcome (from enum)
  - `YES`: Basic yes
  - `NO`: Basic no
  - `YES_AND`: Yes with extra benefit (roll 96-100)
  - `NO_BUT`: No with mitigating factor (roll 96-100 for unlikely/impossible)
  - `NO_AND`: No with additional complication (roll 00-05 for almost_certain/likely)

**Raises:**
- `ValidationError`: If roll is out of range (not 1-100)

**Example:**
```python
# Roll 60 with 50/50 likelihood → Yes
outcome = determine_outcome(60, LikelihoodLevel.FIFTY_FIFTY)
assert outcome == OracleOutcome.YES

# Roll 98 with Impossible likelihood → No, and
outcome = determine_outcome(98, LikelihoodLevel.IMPOSSIBLE)
assert outcome == OracleOutcome.NO_AND
```

---

### NarratorAgent.describe_oracle_outcome

**Purpose:** Generate narrative description of oracle outcome.

**Signature:**
```python
async def describe_oracle_outcome(
    query: str,
    outcome: OracleOutcome,
    context: dict
) -> str:
    """
    Generate narrative description of oracle outcome.
    
    CRITICAL CONSTRAINT: Narrator MUST respect oracle outcome.
    - Cannot say "Yes" if oracle said "No"
    - Must include "Yes, and" or "No, but" if rolled
    - Should add flavor and detail consistent with outcome
    
    Args:
        query: User's oracle query (e.g., "Is the door locked?")
        outcome: Oracle outcome from determine_outcome()
        context: Scene context (entities, relationships, location, etc.)
    
    Returns:
        str: Narrative description of oracle outcome
    
    Raises:
        NarratorError: If narrator fails to generate description
    """
    pass
```

**Parameters:**
- `query` (str): User's oracle query
- `outcome` (OracleOutcome): Oracle outcome from determine_outcome()
- `context` (dict): Scene context (entities, relationships, location, etc.)

**Returns:**
- `str`: Narrative description of oracle outcome

**Raises:**
- `NarratorError`: If narrator fails to generate description

**Example:**
```python
narrative = await describe_oracle_outcome(
    "Is the door locked?",
    OracleOutcome.YES,
    {"location": "Blackwood Manor", "entities": ["door"]}
)
assert "locked" in narrative.lower()
```

---

### SceneLoop.append_oracle_turns

**Purpose:** Create and append user and GM turns to the scene.

**Signature:**
```python
async def append_oracle_turns(
    scene_id: str,
    user_query: str,
    gm_response: str,
    user_id: str,
    oracle_result: str,
    roll: int,
    likelihood: str,
    fact_id: Optional[str] = None
) -> Tuple[Turn, Turn]:
    """
    Create and append user and GM turns to the scene.
    
    Args:
        scene_id: ID of the scene
        user_query: User's oracle query
        gm_response: GM's narrative response
        user_id: ID of the user
        oracle_result: Oracle outcome (e.g., "yes", "no", "yes_and", etc.)
        roll: Percentile roll result
        likelihood: Likelihood level
        fact_id: Optional fact ID if canonized
    
    Returns:
        Tuple[Turn, Turn]: Tuple of (user_turn, gm_turn)
    
    Raises:
        DatabaseError: If turn creation or append fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene
- `user_query` (str): User's oracle query
- `gm_response` (str): GM's narrative response
- `user_id` (str): ID of the user
- `oracle_result` (str): Oracle outcome (e.g., "yes", "no", "yes_and", etc.)
- `roll` (int): Percentile roll result
- `likelihood` (str): Likelihood level
- `fact_id` (Optional[str]): Optional fact ID if canonized

**Returns:**
- `Tuple[Turn, Turn]`: Tuple of (user_turn, gm_turn)

**Raises:**
- `DatabaseError`: If turn creation or append fails

**Example:**
```python
user_turn, gm_turn = await append_oracle_turns(
    scene_id="scene_456",
    user_query="Is the door locked?",
    gm_response="The door is indeed locked...",
    user_id="user_123",
    oracle_result="yes",
    roll=60,
    likelihood="fifty_fifty",
    fact_id="fact_789"
)
assert user_turn.turn_type == TurnType.QUESTION
assert gm_turn.turn_type == TurnType.ORACLE_RESPONSE
```

---

## Layer 3: CLI Contracts

### Command: `oracle`

**Purpose:** Submit an oracle query for probability-based resolution.

**Signature:**
```bash
monitor-cli oracle --query <query_text> [--scene <scene_id>]
```

**Parameters:**
- `--query` (str): Oracle query (required)
- `--scene` (str): Scene ID (optional, defaults to active scene)

**Returns:**
- Exit code: 0 on success, non-zero on error
- Output:
  - Oracle roll result
  - Oracle outcome
  - Narrative description
  - Fact canonization status

**Example:**
```bash
$ monitor-cli oracle --query "Is the door locked?"
🎲 Roll: 60
✅ Oracle Outcome: Yes
📝 Narrative: The door is indeed locked, a sturdy wooden barrier barring your path.
💾 Fact Canonized: Yes (fact_789)
```

---

## Integration Tests

### Test 1: Simple Yes/No Oracle

**Setup:**
```python
# Create test scene with tension=5 (50/50)
scene = create_test_scene(tension_score=5)

# Mock dependencies
mock_mcp_client = Mock()
mock_llm_client = AsyncMock()
```

**Execute:**
```python
# Detect oracle query
is_oracle = detect_oracle_query("Is the door locked?")
assert is_oracle == True

# Determine likelihood
likelihood = determine_likelihood(scene.tension_score)
assert likelihood == LikelihoodLevel.FIFTY_FIFTY

# Mock roll to 60 (within 50-95 → Yes)
with patch('monitor_agents.oracle.roll_percentile', return_value=60):
    roll = roll_percentile()
    outcome = determine_outcome(roll, likelihood)
    assert outcome == OracleOutcome.YES

# Canonize result
fact = mongodb_create_fact(
    entity_id=hash_query("Is the door locked?"),
    fact_type=FactType.WORLD_PROPERTY,
    content="Is the door locked?: Yes",
    canon_level=CanonLevel.CARDS,
    evidence_refs=["oracle:60:5"]
)

# Commit to Neo4j
neo4j_id = await canonkeeper_commit_fact(fact)
assert neo4j_id is not None

# Generate narrative
narrative = await describe_oracle_outcome(
    "Is the door locked?",
    OracleOutcome.YES,
    {"location": "Blackwood Manor"}
)
assert "locked" in narrative.lower()

# Append turns
user_turn, gm_turn = await append_oracle_turns(
    scene_id=scene.scene_id,
    user_query="Is the door locked?",
    gm_response=narrative,
    user_id="user_123",
    oracle_result="yes",
    roll=60,
    likelihood="fifty_fifty",
    fact_id=fact.fact_id
)
assert user_turn.turn_type == TurnType.QUESTION
assert gm_turn.turn_type == TurnType.ORACLE_RESPONSE
```

**Assert:**
```python
# Verify all steps succeeded
assert fact.fact_id is not None
assert narrative is not None
assert user_turn.turn_id is not None
assert gm_turn.turn_id is not None
```

---

### Test 2: "No, and..." Extreme Roll

**Setup:**
```python
# Create test scene with tension=9 (Impossible)
scene = create_test_scene(tension_score=9)
```

**Execute:**
```python
# Detect oracle query
is_oracle = detect_oracle_query("Can I pick the lock?")
assert is_oracle == True

# Determine likelihood
likelihood = determine_likelihood(scene.tension_score)
assert likelihood == LikelihoodLevel.IMPOSSIBLE

# Mock roll to 98 (within 96-100 → No, and)
with patch('monitor_agents.oracle.roll_percentile', return_value=98):
    roll = roll_percentile()
    outcome = determine_outcome(roll, likelihood)
    assert outcome == OracleOutcome.NO_AND

# Canonize result
fact = mongodb_create_fact(
    entity_id=hash_query("Can I pick the lock?"),
    fact_type=FactType.WORLD_PROPERTY,
    content="Can I pick the lock?: No, and",
    canon_level=CanonLevel.CARDS,
    evidence_refs=["oracle:98:9"]
)

# Commit to Neo4j
neo4j_id = await canonkeeper_commit_fact(fact)
assert neo4j_id is not None

# Generate narrative
narrative = await describe_oracle_outcome(
    "Can I pick the lock?",
    OracleOutcome.NO_AND,
    {"location": "Blackwood Manor", "entities": ["guard"]}
)
assert "not" in narrative.lower()
# Narrative should include additional complication

# Append turns
user_turn, gm_turn = await append_oracle_turns(
    scene_id=scene.scene_id,
    user_query="Can I pick the lock?",
    gm_response=narrative,
    user_id="user_123",
    oracle_result="no_and",
    roll=98,
    likelihood="impossible",
    fact_id=fact.fact_id
)
```

**Assert:**
```python
# Verify "No, and" outcome
assert oracle_result == "no_and"
assert narrative includes additional complication
```

---

### Test 3: Known Fact Optimization

**Setup:**
```python
# Create test scene with known fact
scene = create_test_scene(tension_score=5)
existing_fact = mongodb_create_fact(
    entity_id=hash_query("Is the door locked?"),
    fact_type=FactType.WORLD_PROPERTY,
    content="The door is unlocked",
    canon_level=CanonLevel.CARDS,
    evidence_refs=["scene_start"]
)
```

**Execute:**
```python
# Detect oracle query
is_oracle = detect_oracle_query("Is the door locked?")
assert is_oracle == True

# Check for existing fact (optimization)
existing_facts = mongodb_list_facts(content__icontains="door locked")
if existing_facts:
    # Skip oracle roll, use existing fact
    narrative = await describe_oracle_outcome(
        "Is the door locked?",
        existing_fact,
        context={"fact_source": "existing"}
    )
    # No oracle roll performed
```

**Assert:**
```python
# Verify oracle was skipped
assert existing_facts is not None
assert narrative includes "established earlier"
```

---

### Test 4: Consistency Check Across Multiple Oracles

**Setup:**
```python
# Create test scene with tension=5 (50/50)
scene = create_test_scene(tension_score=5)

# First oracle establishes room is empty
fact1 = mongodb_create_fact(
    entity_id=hash_query("Is the room empty?"),
    fact_type=FactType.WORLD_PROPERTY,
    content="Is the room empty?: Yes",
    canon_level=CanonLevel.CARDS,
    evidence_refs=["oracle:60:5"]
)
```

**Execute:**
```python
# Second oracle asks about guards
is_oracle = detect_oracle_query("Are there guards here?")
assert is_oracle == True

# Check for consistency with existing facts
existing_facts = mongodb_list_facts(scene_id=scene.scene_id)
for fact in existing_facts:
    if "empty" in fact.content.lower():
        # Potential inconsistency detected
        # Prompt user to clarify
        print("You established the room is empty. Are you asking if guards are outside or rethinking your previous oracle?")
```

**Assert:**
```python
# Verify consistency check was performed
assert existing_facts is not None
assert consistency_prompt_was_shown
```

---

### Test 5: Error Handling - Scene Not Found

**Setup:**
```python
# No active scene
scene_id = "nonexistent_scene"
```

**Execute:**
```python
try:
    scene = mongodb_get_scene(scene_id)
    if scene is None:
        raise ValueError("Scene not found")
except ValueError as e:
    # Handle error
    print(f"Error: {e}")
    print("Please start a scene first.")
```

**Assert:**
```python
# Verify error was handled correctly
assert scene is None
assert error_message_shown
```

---

## Validation Checklist

- [ ] All function signatures match behavior specifications
- [ ] All parameters are typed correctly
- [ ] All return types are documented
- [ ] All error cases are specified
- [ ] All examples are valid
- [ ] Integration tests pass
- [ ] Evidence tracking is enforced (every oracle has evidence_refs)
- [ ] CanonKeeper evaluation is async
- [ ] Narrator respects oracle outcome constraint
- [ ] Turn metadata includes all required fields (roll, likelihood, fact_id)
- [ ] Scene updated_at is updated after oracle

---

## Related Documentation

- [P-18-behaviors.md](../behaviors/P-18-behaviors.md) - Behavior definition
- [USE_CASE_BEHAVIORS_INDEX.md](../USE_CASE_BEHAVIORS_INDEX.md) - Use case index
- [TEST_GAPS_ANALYSIS.md](../../TEST_GAPS_ANALYSIS.md) - Test gap analysis
- [TESTING_INDEX.md](../../TESTING_INDEX.md) - Testing master index

---

**Last Updated:** 2026-05-19
**Status:** ✅ Contract specifications complete