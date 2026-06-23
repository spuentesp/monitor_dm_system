# P-21: Downtime & Character Progression - Contract Specifications

## Overview

Downtime & Character Progression introduces a macro-loop phase for downtime activities and character advancement. When a story arc reaches 'resolution' or a scene is designated as 'rest/downtime', the system offers progression options (spending XP, leveling up, training skills) based on the active GameSystemRuntime. It applies persistent changes to the character's base stats in Neo4j (via CanonKeeper).

---

## Layer 1: Data Layer Contracts

### MongoDB: GetGameSystem

**Purpose:** Retrieve a game system from MongoDB by its ID.

**Signature:**
```python
def mongodb_get_game_system(system_id: str) -> Optional[GameSystem]:
    """
    Retrieve a game system from MongoDB by its ID.
    
    Args:
        system_id: ID of the game system to retrieve
    
    Returns:
        Optional[GameSystem]: GameSystem entity if found, None otherwise
    
    Raises:
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `system_id` (str): ID of the game system to retrieve

**Returns:**
- `Optional[GameSystem]`: GameSystem entity if found, None otherwise

**Raises:**
- `DatabaseError`: If database operation fails

**Example:**
```python
game_system = mongodb_get_game_system("dnd5e")
if game_system is None:
    raise ValueError("Game system not found")
level_up_xp = game_system.progression.level_up_xp
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
        metadata: Optional metadata (downtime_triggered, upgrades_selected, xp_spent, etc.)
    
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
# User turn (PROGRESSION)
user_turn = mongodb_create_turn(
    speaker_id="user_123",
    turn_type=TurnType.PROGRESSION,
    content="1",
    scene_id="scene_456",
    metadata={
        "downtime_triggered": True,
        "upgrades_selected": ["level_up"],
        "xp_spent": 1000
    }
)

# GM turn (NARRATION)
gm_turn = mongodb_create_turn(
    speaker_id="system:progression",
    turn_type=TurnType.NARRATION,
    content="Aragorn reflects on his recent battles, gaining new insights.",
    scene_id="scene_456",
    metadata={
        "progression_applied": True,
        "upgrades_applied": ["Level up to 2"],
        "canonized": True
    }
)
```

---

### Neo4j: GetEntity

**Purpose:** Retrieve an entity from Neo4j by its ID.

**Signature:**
```python
def neo4j_get_entity(entity_id: str) -> Optional[Entity]:
    """
    Retrieve an entity from Neo4j by its ID.
    
    Args:
        entity_id: ID of the entity to retrieve
    
    Returns:
        Optional[Entity]: Entity if found, None otherwise
    
    Raises:
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `entity_id` (str): ID of the entity to retrieve

**Returns:**
- `Optional[Entity]`: Entity if found, None otherwise

**Raises:**
- `DatabaseError`: If database operation fails

**Example:**
```python
character = neo4j_get_entity("char_123")
if character is None:
    raise ValueError("Character not found")
level = character.properties.get('level', 1)
xp = character.properties.get('xp', 0)
```

---

### Neo4j: UpdateEntity

**Purpose:** Update an entity's properties in Neo4j.

**Signature:**
```python
def neo4j_update_entity(
    entity_id: str,
    properties: Dict[str, Any]
) -> Entity:
    """
    Update an entity's properties in Neo4j.
    
    Args:
        entity_id: ID of the entity to update
        properties: Dictionary of properties to update (can be nested)
    
    Returns:
        Entity: Updated Entity
    
    Raises:
        ValidationError: If properties are invalid
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `entity_id` (str): ID of the entity to update
- `properties` (Dict[str, Any]): Dictionary of properties to update (can be nested)

**Returns:**
- `Entity`: Updated Entity

**Raises:**
- `ValidationError`: If properties are invalid
- `DatabaseError`: If database operation fails

**Example:**
```python
# Update character level and XP
updated_character = neo4j_update_entity(
    "char_123",
    {
        "level": 2,
        "xp": 0
    }
)

# Update attribute
updated_character = neo4j_update_entity(
    "char_123",
    {"attributes.strength": 15}
)

# Update skill
updated_character = neo4j_update_entity(
    "char_123",
    {"skills.stealth": 1}
)
```

---

### MongoDB: ProposedChangeCreate

**Purpose:** Create a ProposedChange document in MongoDB.

**Signature:**
```python
def mongodb_create_proposed_change(
    entity_id: str,
    change_type: str,
    changes: Dict[str, Any],
    reason: str,
    evidence_refs: List[Dict[str, Any]],
    status: str = "pending"
) -> ProposedChange:
    """
    Create a ProposedChange document in MongoDB.
    
    Args:
        entity_id: ID of the entity to change
        change_type: Type of change (e.g., 'level_up', 'attribute_increase', 'skill_training')
        changes: Dictionary of changes to apply
        reason: Reason for the change
        evidence_refs: List of evidence references
        status: Status of the proposal (default: 'pending')
    
    Returns:
        ProposedChange: Created ProposedChange document with assigned proposal_id
    
    Raises:
        ValidationError: If required fields are missing or invalid
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `entity_id` (str): ID of the entity to change
- `change_type` (str): Type of change (e.g., 'level_up', 'attribute_increase', 'skill_training')
- `changes` (Dict[str, Any]): Dictionary of changes to apply
- `reason` (str): Reason for the change
- `evidence_refs` (List[Dict[str, Any]]): List of evidence references
- `status` (str): Status of the proposal (default: 'pending')

**Returns:**
- `ProposedChange`: Created ProposedChange document with assigned proposal_id

**Raises:**
- `ValidationError`: If required fields are missing or invalid
- `DatabaseError`: If database operation fails

**Example:**
```python
# Level up proposal
proposal = mongodb_create_proposed_change(
    entity_id="char_123",
    change_type="level_up",
    changes={"level": 2},
    reason="Character progression during downtime",
    evidence_refs=[{"source": "progression", "upgrade_type": "level_up"}]
)

# Attribute increase proposal
proposal = mongodb_create_proposed_change(
    entity_id="char_123",
    change_type="attribute_increase",
    changes={"attributes.strength": 15},
    reason="Character progression during downtime",
    evidence_refs=[{"source": "progression", "upgrade_type": "attribute", "attribute": "strength"}]
)

# Skill training proposal
proposal = mongodb_create_proposed_change(
    entity_id="char_123",
    change_type="skill_training",
    changes={"skills.stealth": 1},
    reason="Character progression during downtime",
    evidence_refs=[{"source": "progression", "upgrade_type": "skill", "skill": "stealth"}]
)
```

---

## Layer 2: Agent Contracts

### ProgressionLoop.detect_downtime_trigger

**Purpose:** Detect if downtime should be triggered based on story/scene state.

**Signature:**
```python
def detect_downtime_trigger(
    story: Optional[Story],
    scene: Optional[Scene]
) -> bool:
    """
    Detect if downtime should be triggered based on story/scene state.
    
    Check for downtime triggers:
    - Story arc_label = 'resolution'
    - Scene tags contain 'rest' or 'downtime'
    - Explicit downtime command (not covered here, checked elsewhere)
    
    Args:
        story: Current story (may be None)
        scene: Current scene (may be None)
    
    Returns:
        bool: True if downtime should be triggered, False otherwise
    
    Raises:
        ValueError: If both story and scene are None
    """
    pass
```

**Parameters:**
- `story` (Optional[Story]): Current story (may be None)
- `scene` (Optional[Scene]): Current scene (may be None)

**Returns:**
- `bool`: True if downtime should be triggered, False otherwise

**Raises:**
- `ValueError`: If both story and scene are None

**Example:**
```python
# Story arc resolution
story = Story(arc_label="resolution")
scene = Scene(tags=[])
triggered = detect_downtime_trigger(story, scene)
assert triggered == True

# Scene tagged as rest
story = Story(arc_label="exploration")
scene = Scene(tags=["rest"])
triggered = detect_downtime_trigger(story, scene)
assert triggered == True

# No downtime trigger
story = Story(arc_label="exploration")
scene = Scene(tags=[])
triggered = detect_downtime_trigger(story, scene)
assert triggered == False
```

---

### ProgressionLoop.query_character_progression

**Purpose:** Retrieve and extract progression data for a character.

**Signature:**
```python
def query_character_progression(character_id: str) -> CharacterProgression:
    """
    Retrieve and extract progression data for a character.
    
    Retrieve character entity from Neo4j and extract progression data.
    Use defaults if properties are missing.
    
    Args:
        character_id: ID of the character
    
    Returns:
        CharacterProgression: Progression data for the character
    
    Raises:
        EntityNotFoundError: If character not found in Neo4j
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `character_id` (str): ID of the character

**Returns:**
- `CharacterProgression`: Progression data for the character

**Raises:**
- `EntityNotFoundError`: If character not found in Neo4j
- `DatabaseError`: If database operation fails

**Example:**
```python
progression = query_character_progression("char_123")
assert progression.character_id == "char_123"
assert progression.name == "Aragorn"
assert progression.level == 1
assert progression.xp >= 0
assert progression.attributes.get("strength", 10) >= 10
assert progression.skills.get("stealth", 0) >= 0
```

---

### ProgressionLoop.query_progression_rules

**Purpose:** Retrieve and extract progression rules from a game system.

**Signature:**
```python
def query_progression_rules(
    system_id: str,
    level: int
) -> ProgressionRules:
    """
    Retrieve and extract progression rules from a game system.
    
    Retrieve game system from MongoDB and extract progression rules.
    Use defaults if rules are missing.
    
    Args:
        system_id: ID of the game system
        level: Current character level (to retrieve level-specific benefits)
    
    Returns:
        ProgressionRules: Progression rules from the game system
    
    Raises:
        GameSystemNotFoundError: If game system not found in MongoDB
        DatabaseError: If database operation fails
    """
    pass
```

**Parameters:**
- `system_id` (str): ID of the game system
- `level` (int): Current character level (to retrieve level-specific benefits)

**Returns:**
- `ProgressionRules`: Progression rules from the game system

**Raises:**
- `GameSystemNotFoundError`: If game system not found in MongoDB
- `DatabaseError`: If database operation fails

**Example:**
```python
rules = query_progression_rules("dnd5e", 1)
assert rules.system_id == "dnd5e"
assert rules.system_name == "D&D 5e"
assert rules.level_up_xp == 1000
assert rules.attribute_costs.get("strength", 0) > 0
assert rules.skill_costs.get("stealth", 0) > 0
assert rules.max_attributes.get("strength", 20) >= 10
assert rules.max_skills.get("stealth", 5) >= 0
```

---

### ProgressionLoop.calculate_upgrades

**Purpose:** Calculate available upgrades based on character progression and game system rules.

**Signature:**
```python
def calculate_upgrades(
    progression: CharacterProgression,
    rules: ProgressionRules
) -> List[UpgradeOption]:
    """
    Calculate available upgrades based on character progression and game system rules.
    
    Determine what upgrades are affordable:
    - Level up (if XP >= level_up_xp)
    - Attributes (if XP >= cost and below max)
    - Skills (if XP >= cost and below max)
    
    Args:
        progression: Character progression data
        rules: Game system progression rules
    
    Returns:
        List[UpgradeOption]: List of affordable upgrades
    
    Raises:
        CalculationError: If calculation fails
    """
    pass
```

**Parameters:**
- `progression` (CharacterProgression): Character progression data
- `rules` (ProgressionRules): Game system progression rules

**Returns:**
- `List[UpgradeOption]`: List of affordable upgrades

**Raises:**
- `CalculationError`: If calculation fails

**Example:**
```python
progression = CharacterProgression(
    character_id="char_123",
    name="Aragorn",
    level=1,
    xp=1000,
    xp_to_next_level=1000,
    attributes={"strength": 14},
    skills=[]
)

rules = ProgressionRules(
    system_id="dnd5e",
    level_up_xp=1000,
    attribute_costs={"strength": 50},
    skill_costs={"stealth": 25},
    max_attributes={"strength": 20},
    max_skills={"stealth": 5}
)

upgrades = calculate_upgrades(progression, rules)
assert len(upgrades) >= 2  # Level up + Strength
assert any(u.type == "level_up" for u in upgrades)
assert any(u.type == "attribute" and u.attribute == "strength" for u in upgrades)
```

---

### ProgressionLoop.present_progression_ui

**Purpose:** Generate a UI prompt displaying progression options to the user.

**Signature:**
```python
def present_progression_ui(
    progression: CharacterProgression,
    upgrades: List[UpgradeOption]
) -> str:
    """
    Generate a UI prompt displaying progression options to the user.
    
    Construct prompt or UI with:
    - Character name, level, XP
    - List of available upgrades with costs
    - Instructions for selection
    
    Args:
        progression: Character progression data
        upgrades: List of available upgrades
    
    Returns:
        str: UI prompt string
    
    Raises:
        UIRenderError: If UI rendering fails
    """
    pass
```

**Parameters:**
- `progression` (CharacterProgression): Character progression data
- `upgrades` (List[UpgradeOption]): List of available upgrades

**Returns:**
- `str`: UI prompt string

**Raises:**
- `UIRenderError`: If UI rendering fails

**Example:**
```python
prompt = present_progression_ui(progression, upgrades)
assert "DOWNTIME & PROGRESSION" in prompt
assert "Aragorn" in prompt
assert "XP:" in prompt
assert "Available Upgrades:" in prompt
assert "Select upgrades" in prompt
```

---

### ProgressionLoop.parse_selection

**Purpose:** Parse user's upgrade selection from input.

**Signature:**
```python
def parse_selection(
    input: str,
    upgrades: List[UpgradeOption]
) -> List[UpgradeOption]:
    """
    Parse user's upgrade selection from input.
    
    Parse user input:
    - 'done' -> empty list
    - Comma-separated numbers -> selected upgrades
    
    Validate selection:
    - Total cost ≤ available XP
    - No duplicate upgrades
    
    Args:
        input: User input string
        upgrades: List of available upgrades
    
    Returns:
        List[UpgradeOption]: List of selected upgrades
    
    Raises:
        ParseError: If input parsing fails
        ValueError: If selection is invalid
    """
    pass
```

**Parameters:**
- `input` (str): User input string
- `upgrades` (List[UpgradeOption]): List of available upgrades

**Returns:**
- `List[UpgradeOption]`: List of selected upgrades

**Raises:**
- `ParseError`: If input parsing fails
- `ValueError`: If selection is invalid

**Example:**
```python
# Single selection
selected = parse_selection("1", upgrades)
assert len(selected) == 1

# Multiple selections
selected = parse_selection("1,2", upgrades)
assert len(selected) == 2

# Done
selected = parse_selection("done", upgrades)
assert len(selected) == 0

# Invalid input
try:
    selected = parse_selection("invalid", upgrades)
except ParseError:
    pass  # Expected
```

---

### ProgressionLoop.validate_selection

**Purpose:** Validate user's upgrade selection against game system rules.

**Signature:**
```python
def validate_selection(
    upgrades: List[UpgradeOption],
    rules: ProgressionRules,
    progression: CharacterProgression
) -> ValidationResult:
    """
    Validate user's upgrade selection against game system rules.
    
    Check each upgrade against rules:
    - Total cost ≤ available XP
    - Attributes below max
    - Skills below max
    
    Args:
        upgrades: List of selected upgrades
        rules: Game system progression rules
        progression: Character progression data
    
    Returns:
        ValidationResult: Validation result with errors if invalid
    
    Raises:
        ValidationError: If validation fails
    """
    pass
```

**Parameters:**
- `upgrades` (List[UpgradeOption]): List of selected upgrades
- `rules` (ProgressionRules): Game system progression rules
- `progression` (CharacterProgression): Character progression data

**Returns:**
- `ValidationResult`: Validation result with errors if invalid

**Raises:**
- `ValidationError`: If validation fails

**Example:**
```python
# Valid selection
validation = validate_selection(
    [upgrades[0]],
    rules,
    progression
)
assert validation.valid == True
assert len(validation.errors) == 0

# Insufficient XP
validation = validate_selection(
    [upgrades[0], upgrades[1], upgrades[2]],  # Too many
    rules,
    progression
)
assert validation.valid == False
assert any("exceeds available XP" in e for e in validation.errors)
```

---

### ProgressionLoop.create_proposed_changes

**Purpose:** Create ProposedChange documents for CanonKeeper evaluation.

**Signature:**
```python
def create_proposed_changes(
    character_id: str,
    upgrades: List[UpgradeOption]
) -> List[ProposedChange]:
    """
    Create ProposedChange documents for CanonKeeper evaluation.
    
    Create ProposedChange for each upgrade:
    - level_up -> change_type='level_up'
    - attribute -> change_type='attribute_increase'
    - skill -> change_type='skill_training'
    
    Each change includes:
    - entity_id
    - change_type
    - changes (properties to update)
    - reason
    - evidence_refs
    
    Args:
        character_id: ID of the character
        upgrades: List of selected upgrades
    
    Returns:
        List[ProposedChange]: List of proposed changes
    
    Raises:
    """
    pass
```

**Parameters:**
- `character_id` (str): ID of the character
- `upgrades` (List[UpgradeOption]): List of selected upgrades

**Returns:**
- `List[ProposedChange]`: List of proposed changes

**Raises:**

**Example:**
```python
proposals = create_proposed_changes("char_123", upgrades)
assert len(proposals) == len(upgrades)
for i, proposal in enumerate(proposals):
    assert proposal.entity_id == "char_123"
    assert proposal.change_type in ["level_up", "attribute_increase", "skill_training"]
    assert "Character progression during downtime" in proposal.reason
    assert len(proposal.evidence_refs) > 0
```

---

### CanonKeeper.evaluate_and_commit

**Purpose:** Evaluate and commit proposed changes to Neo4j.

**Signature:**
```python
async def evaluate_and_commit(
    proposed_changes: List[ProposedChange]
) -> CanonResult:
    """
    Evaluate and commit proposed changes to Neo4j.
    
    CanonKeeper evaluates each ProposedChange:
    - Check consistency with existing facts
    - Validate against game system rules
    - Check for contradictions
    
    CanonKeeper commits changes to Neo4j if valid.
    
    Args:
        proposed_changes: List of proposed changes
    
    Returns:
        CanonResult: Result of evaluation and commitment
    
    Raises:
        CanonConflictError: If CanonKeeper rejects changes
        DatabaseError: If commitment fails
    """
    pass
```

**Parameters:**
- `proposed_changes` (List[ProposedChange]): List of proposed changes

**Returns:**
- `CanonResult`: Result of evaluation and commitment

**Raises:**
- `CanonConflictError`: If CanonKeeper rejects changes
- `DatabaseError`: If commitment fails

**Example:**
```python
result = await evaluate_and_commit(proposals)
assert result.success == True
assert len(result.conflicts) == 0
```

---

### ProgressionLoop.deduct_xp

**Purpose:** Deduct spent XP from character in Neo4j.

**Signature:**
```python
def deduct_xp(
    character_id: str,
    xp_spent: int,
    current_xp: int
) -> Entity:
    """
    Deduct spent XP from character in Neo4j.
    
    Update character's XP property by subtracting spent XP.
    
    Args:
        character_id: ID of the character
        xp_spent: Amount of XP spent
        current_xp: Current XP amount (for validation)
    
    Returns:
        Entity: Updated character entity
    
    Raises:
        ValueError: If xp_spent > current_xp
        DatabaseError: If update fails
    """
    pass
```

**Parameters:**
- `character_id` (str): ID of the character
- `xp_spent` (int): Amount of XP spent
- `current_xp` (int): Current XP amount (for validation)

**Returns:**
- `Entity`: Updated character entity

**Raises:**
- `ValueError`: If xp_spent > current_xp
- `DatabaseError`: If update fails

**Example:**
```python
updated_character = deduct_xp("char_123", 1000, 1000)
assert updated_character.properties.get("xp") == 0
```

---

### NarratorAgent.describe_progression

**Purpose:** Generate narrative description of character progression.

**Signature:**
```python
async def describe_progression(
    upgrades: List[UpgradeOption],
    character_name: str
) -> str:
    """
    Generate narrative description of character progression.
    
    Generate narrative description of the training, reflection,
    or events that led to the improvements. Keep to 1-2 sentences.
    
    Args:
        upgrades: List of applied upgrades
        character_name: Name of the character
    
    Returns:
        str: Narrative description
    
    Raises:
        NarratorError: If narrator fails to generate description
    """
    pass
```

**Parameters:**
- `upgrades` (List[UpgradeOption]): List of applied upgrades
- `character_name` (str): Name of the character

**Returns:**
- `str`: Narrative description

**Raises:**
- `NarratorError`: If narrator fails to generate description

**Example:**
```python
narrative = await describe_progression(
    [UpgradeOption(type="level_up", description="Level up to 2")],
    "Aragorn"
)
assert "Aragorn" in narrative
assert len(narrative) > 0
```

---

### ProgressionLoop.append_progression_turns

**Purpose:** Create and append user and GM turns for progression scenario.

**Signature:**
```python
async def append_progression_turns(
    scene_id: str,
    user_selection: str,
    response: str,
    user_id: str,
    upgrades: List[UpgradeOption]
) -> Tuple[Turn, Turn]:
    """
    Create and append user and GM turns for progression scenario.
    
    Create user turn (PROGRESSION).
    Create GM turn (NARRATION).
    Append both turns to scene.
    
    Args:
        scene_id: ID of the scene
        user_selection: User's selection (e.g., "1,2")
        response: GM's narrative response
        user_id: ID of the user
        upgrades: List of applied upgrades
    
    Returns:
        Tuple[Turn, Turn]: Tuple of (user_turn, gm_turn)
    
    Raises:
        DatabaseError: If turn creation or append fails
    """
    pass
```

**Parameters:**
- `scene_id` (str): ID of the scene
- `user_selection` (str): User's selection (e.g., "1,2")
- `response` (str): GM's narrative response
- `user_id` (str): ID of the user
- `upgrades` (List[UpgradeOption]): List of applied upgrades

**Returns:**
- `Tuple[Turn, Turn]`: Tuple of (user_turn, gm_turn)

**Raises:**
- `DatabaseError`: If turn creation or append fails

**Example:**
```python
user_turn, gm_turn = await append_progression_turns(
    scene_id="scene_456",
    user_selection="1",
    response="Aragorn reflects on his recent battles...",
    user_id="user_123",
    upgrades=[upgrades[0]]
)
assert user_turn.turn_type == TurnType.PROGRESSION
assert gm_turn.turn_type == TurnType.NARRATION
assert user_turn.metadata.get("downtime_triggered") == True
assert gm_turn.metadata.get("progression_applied") == True
```

---

## Layer 3: CLI Contracts

### Command: `/downtime`

**Purpose:** Manually trigger downtime progression (optional override).

**Signature:**
```bash
monitor-cli --downtime [options]
```

**Parameters:**
- `--downtime` (flag): Trigger downtime progression
- `--character-id` (str, optional): Character ID (default: current character)
- `--scene-id` (str, optional): Scene ID (default: current scene)

**Returns:**
- Exit code: 0 on success, non-zero on error
- Output:
  - Progression UI
  - Applied upgrades
  - Updated character stats

**Example:**
```bash
$ monitor-cli --downtime --character-id char_123
🔔 DOWNTIME & PROGRESSION 🔔

Character: Aragorn
Level: 1
XP: 1000 / 1000

Available Upgrades:
1. Level up to 2 (Cost: 1000 XP)

Select upgrades by number (comma-separated), or 'done' to skip.
```

---

## Integration Tests

### Test 1: Level Up

**Setup:**
```python
# Create test character
character = create_test_character(
    name="Aragorn",
    level=1,
    xp=1000,
    xp_to_next_level=1000
)

# Create test scene
scene = create_test_scene(
    story=Story(arc_label="resolution"),
    scene=Scene(tags=[])
)

# Create test game system
game_system = create_test_game_system(
    name="D&D 5e",
    level_up_xp=1000
)
```

**Execute:**
```python
# Detect downtime trigger
triggered = detect_downtime_trigger(scene.story, scene.scene)
assert triggered == True

# Query character progression
progression = query_character_progression(character.character_id)
assert progression.character_id == character.character_id
assert progression.level == 1
assert progression.xp == 1000

# Query progression rules
rules = query_progression_rules(game_system.system_id, progression.level)
assert rules.level_up_xp == 1000

# Calculate upgrades
upgrades = calculate_upgrades(progression, rules)
assert len(upgrades) >= 1
assert any(u.type == "level_up" for u in upgrades)

# Present UI
ui = present_progression_ui(progression, upgrades)
assert "Aragorn" in ui
assert "1000 XP" in ui

# Parse selection
selected = parse_selection("1", upgrades)
assert len(selected) == 1
assert selected[0].type == "level_up"

# Validate selection
validation = validate_selection(selected, rules, progression)
assert validation.valid == True

# Create proposed changes
proposals = create_proposed_changes(character.character_id, selected)
assert len(proposals) == 1
assert proposals[0].change_type == "level_up"

# Evaluate and commit
result = await evaluate_and_commit(proposals)
assert result.success == True

# Verify character updated
updated_character = neo4j_get_entity(character.character_id)
assert updated_character.properties.get("level") == 2

# Deduct XP
updated_character = deduct_xp(
    character.character_id,
    1000,
    1000
)
assert updated_character.properties.get("xp") == 0

# Generate narrative
narrative = await describe_progression(selected, "Aragorn")
assert "Aragorn" in narrative

# Append turns
user_turn, gm_turn = await append_progression_turns(
    scene.scene.scene_id,
    "1",
    narrative,
    "user_123",
    selected
)
```

**Assert:**
```python
# Verify all steps succeeded
assert user_turn.turn_type == TurnType.PROGRESSION
assert gm_turn.turn_type == TurnType.NARRATION
assert user_turn.metadata.get("downtime_triggered") == True
assert user_turn.metadata.get("upgrades_selected") == ["level_up"]
assert user_turn.metadata.get("xp_spent") == 1000
assert gm_turn.metadata.get("progression_applied") == True
```

---

### Test 2: Multiple Upgrades

**Setup:**
```python
# Create test character
character = create_test_character(
    name="Gimli",
    level=1,
    xp=150,
    attributes={"strength": 14, "constitution": 14}
)

# Create test scene
scene = create_test_scene(
    story=Story(arc_label="resolution"),
    scene=Scene(tags=["rest"])
)

# Create test game system
game_system = create_test_game_system(
    name="D&D 5e",
    attribute_costs={"strength": 50, "constitution": 50},
    max_attributes={"strength": 20, "constitution": 20}
)
```

**Execute:**
```python
# Detect downtime trigger
triggered = detect_downtime_trigger(scene.story, scene.scene)
assert triggered == True

# Query character progression
progression = query_character_progression(character.character_id)

# Query progression rules
rules = query_progression_rules(game_system.system_id, progression.level)

# Calculate upgrades
upgrades = calculate_upgrades(progression, rules)
assert len(upgrades) >= 2  # Strength + Constitution

# Parse selection
selected = parse_selection("1,2", upgrades)
assert len(selected) == 2

# Validate selection (total cost: 100 XP ≤ 150 XP)
validation = validate_selection(selected, rules, progression)
assert validation.valid == True

# Create proposed changes
proposals = create_proposed_changes(character.character_id, selected)
assert len(proposals) == 2

# Evaluate and commit
result = await evaluate_and_commit(proposals)
assert result.success == True

# Verify character updated
updated_character = neo4j_get_entity(character.character_id)
assert updated_character.properties.get("attributes", {}).get("strength") == 15
assert updated_character.properties.get("attributes", {}).get("constitution") == 15

# Deduct XP
updated_character = deduct_xp(
    character.character_id,
    100,
    150
)
assert updated_character.properties.get("xp") == 50
```

**Assert:**
```python
# Verify both attributes updated
assert updated_character.properties.get("attributes", {}).get("strength") == 15
assert updated_character.properties.get("attributes", {}).get("constitution") == 15
assert updated_character.properties.get("xp") == 50
```

---

### Test 3: No Upgrades Available

**Setup:**
```python
# Create test character
character = create_test_character(
    name="Legolas",
    level=5,
    xp=10,
    attributes={"strength": 20, "dexterity": 20},
    skills={"stealth": 5, "perception": 5}
)

# Create test scene
scene = create_test_scene(
    story=Story(arc_label="resolution"),
    scene=Scene(tags=[])
)

# Create test game system
game_system = create_test_game_system(
    name="D&D 5e",
    level_up_xp=1000,
    attribute_costs={"strength": 50},
    max_attributes={"strength": 20},
    skill_costs={"stealth": 25},
    max_skills={"stealth": 5}
)
```

**Execute:**
```python
# Detect downtime trigger
triggered = detect_downtime_trigger(scene.story, scene.scene)
assert triggered == True

# Query character progression
progression = query_character_progression(character.character_id)

# Query progression rules
rules = query_progression_rules(game_system.system_id, progression.level)

# Calculate upgrades
upgrades = calculate_upgrades(progression, rules)
assert len(upgrades) == 0  # No upgrades available

# Present UI (should show "No upgrades available")
ui = present_progression_ui(progression, upgrades)
assert "No upgrades available" in ui
```

**Assert:**
```python
# Verify no upgrades available
assert len(upgrades) == 0
assert "No upgrades available" in ui
```

---

### Test 4: Insufficient XP for Selection

**Setup:**
```python
# Create test character
character = create_test_character(
    name="Boromir",
    level=1,
    xp=75
)

# Create test scene
scene = create_test_scene(
    story=Story(arc_label="resolution"),
    scene=Scene(tags=[])
)

# Create test game system
game_system = create_test_game_system(
    name="D&D 5e",
    attribute_costs={"strength": 50, "charisma": 50}
)
```

**Execute:**
```python
# Detect downtime trigger
triggered = detect_downtime_trigger(scene.story, scene.scene)
assert triggered == True

# Query character progression
progression = query_character_progression(character.character_id)

# Query progression rules
rules = query_progression_rules(game_system.system_id, progression.level)

# Calculate upgrades
upgrades = calculate_upgrades(progression, rules)
assert len(upgrades) >= 2  # Strength + Charisma

# Parse selection (both)
selected = parse_selection("1,2", upgrades)
assert len(selected) == 2

# Validate selection (should fail: 100 XP > 75 XP)
validation = validate_selection(selected, rules, progression)
assert validation.valid == False
assert any("exceeds available XP" in e for e in validation.errors)

# Reselect (only one)
selected = parse_selection("1", upgrades)
assert len(selected) == 1

# Validate selection (should pass: 50 XP ≤ 75 XP)
validation = validate_selection(selected, rules, progression)
assert validation.valid == True
```

**Assert:**
```python
# Verify validation prevents overspending
assert validation.valid == True
total_cost = sum(u.cost for u in selected)
assert total_cost <= progression.xp
```

---

### Test 5: Skill Training

**Setup:**
```python
# Create test character
character = create_test_character(
    name="Frodo",
    level=1,
    xp=50,
    skills={"stealth": 0, "perception": 0}
)

# Create test scene
scene = create_test_scene(
    story=Story(arc_label="resolution"),
    scene=Scene(tags=[])
)

# Create test game system
game_system = create_test_game_system(
    name="D&D 5e",
    skill_costs={"stealth": 25, "perception": 25},
    max_skills={"stealth": 5, "perception": 5}
)
```

**Execute:**
```python
# Detect downtime trigger
triggered = detect_downtime_trigger(scene.story, scene.scene)
assert triggered == True

# Query character progression
progression = query_character_progression(character.character_id)

# Query progression rules
rules = query_progression_rules(game_system.system_id, progression.level)

# Calculate upgrades
upgrades = calculate_upgrades(progression, rules)
assert len(upgrades) >= 2  # Stealth + Perception

# Parse selection
selected = parse_selection("1,2", upgrades)
assert len(selected) == 2

# Validate selection (50 XP ≤ 50 XP)
validation = validate_selection(selected, rules, progression)
assert validation.valid == True

# Create proposed changes
proposals = create_proposed_changes(character.character_id, selected)
assert len(proposals) == 2
assert all(p.change_type == "skill_training" for p in proposals)

# Evaluate and commit
result = await evaluate_and_commit(proposals)
assert result.success == True

# Verify character updated
updated_character = neo4j_get_entity(character.character_id)
assert updated_character.properties.get("skills", {}).get("stealth") == 1
assert updated_character.properties.get("skills", {}).get("perception") == 1

# Deduct XP
updated_character = deduct_xp(
    character.character_id,
    50,
    50
)
assert updated_character.properties.get("xp") == 0
```

**Assert:**
```python
# Verify both skills updated
assert updated_character.properties.get("skills", {}).get("stealth") == 1
assert updated_character.properties.get("skills", {}).get("perception") == 1
assert updated_character.properties.get("xp") == 0
```

---

## Validation Checklist

- [ ] All function signatures match behavior specifications
- [ ] All parameters are typed correctly
- [ ] All return types are documented
- [ ] All error cases are specified
- [ ] All examples are valid
- [ ] Integration tests pass
- [ ] Downtime detection accuracy: 100%
- [ ] Character retrieval: 100% success
- [ ] Game system retrieval: 100% success
- [ ] Upgrade calculation: 100% accuracy
- [ ] UI clarity: 100%
- [ ] Selection parsing: 100% accuracy
- [ ] Rule validation: 100% accuracy
- [ ] Canonization: 100% success (only via CanonKeeper)
- [ ] XP deduction: 100% accuracy
- [ ] Turn metadata completeness: 100%
- [ ] Evidence tracking: 100%

---

## Related Documentation

- [P-21-behaviors.md](../behaviors/P-21-behaviors.md) - Behavior definition
- [USE_CASE_BEHAVIORS_INDEX.md](../USE_CASE_BEHAVIORS_INDEX.md) - Use case index
- [TEST_GAPS_ANALYSIS.md](../../TEST_GAPS_ANALYSIS.md) - Test gap analysis
- [TESTING_INDEX.md](../../TESTING_INDEX.md) - Testing master index

---

**Last Updated:** 2026-05-19
**Status:** ✅ Contract specifications complete