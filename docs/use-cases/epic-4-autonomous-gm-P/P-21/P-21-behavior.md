# P-21: Downtime & Character Progression - Behavior Definition

**Use Case ID:** P-21
**Last Updated:** 2026-05-19
**Status:** ✅ Defined

## Overview

Downtime & Character Progression introduces a macro-loop phase for downtime activities and character advancement. When a story arc reaches 'resolution' or a scene is designated as 'rest/downtime', the system offers progression options (spending XP, leveling up, training skills) based on the active GameSystemRuntime. It applies persistent changes to the character's base stats in Neo4j (via CanonKeeper).

## Preconditions

1. **Active story or scene exists** in MongoDB
2. **Character entity exists** in Neo4j
3. **Game system is active** (DL-20)
4. **Downtime trigger detected:**
   - Story arc_label = 'resolution' OR
   - Scene designated as 'rest/downtime'
5. **Character has XP** to spend

## User Actions

1. System detects downtime trigger
2. System presents progression options
3. Player selects progression choices
4. System validates and applies changes

## System Actions

### Action 1: Detect Downtime Trigger

**Agent:** StoryLoop / SceneLoop
**Method:** `detect_downtime_trigger(story: Story, scene: Scene) -> bool`

- Check story arc status:
  ```python
  if story.arc_label == 'resolution':
      return True
  ```
- Check scene designation:
  ```python
  if scene.tags and 'rest' in scene.tags or 'downtime' in scene.tags:
      return True
  ```
- Check for explicit downtime command:
  ```python
  if user_input.startswith("/downtime"):
      return True
  ```
- Return `True` if any trigger is active

**Success Criteria:**
- Downtime detection accuracy: 100%
- No false negatives (all downtimes detected)

**Error Cases:**
- Story/scene not found → Error, ask user to start story

---

### Action 2: Query Character Entity

**Agent:** ProgressionLoop
**Method:** `query_character_progression(character_id: str) -> CharacterProgression`

- Retrieve character entity from Neo4j:
  ```python
  character = neo4j_get_entity(character_id)
  ```
- Extract progression data:
  ```python
  progression = CharacterProgression(
      character_id=character.entity_id,
      name=character.name,
      level=character.properties.get('level', 1),
      xp=character.properties.get('xp', 0),
      xp_to_next_level=character.properties.get('xp_to_next_level', 100),
      attributes=character.properties.get('attributes', {}),
      skills=character.properties.get('skills', []),
      available_upgrades=[]
  )
  ```
- Return progression data

**Success Criteria:**
- Character retrieval: 100% success
- Data extraction: 100% accuracy

**Error Cases:**
- Character not found → Error, ask user to create character
- Properties missing → Use defaults (level=1, xp=0)

---

### Action 3: Query Game System Rules

**Agent:** ProgressionLoop
**Method:** `query_progression_rules(system_id: str, level: int) -> ProgressionRules`

- Retrieve game system from MongoDB:
  ```python
  game_system = mongodb_get_game_system(system_id)
  ```
- Extract progression rules:
  ```python
  rules = ProgressionRules(
      system_id=system_id,
      system_name=game_system.name,
      core_mechanic=game_system.core_mechanic,
      level_up_xp=game_system.progression.level_up_xp,  # e.g., 1000 XP per level
      attribute_costs=game_system.progression.attribute_costs,  # e.g., {"strength": 50, "dexterity": 50}
      skill_costs=game_system.progression.skill_costs,  # e.g., {"stealth": 25, "perception": 25}
      level_benefits=game_system.progression.level_benefits,  # What each level grants
      max_attributes=game_system.progression.max_attributes,
      max_skills=game_system.progression.max_skills
  )
  ```
- Return rules

**Success Criteria:**
- Game system retrieval: 100% success
- Rule extraction: 100% accuracy

**Error Cases:**
- Game system not found → Error, ask user to select game system
- Rules missing → Use defaults (1000 XP per level)

---

### Action 4: Calculate Available Upgrades

**Agent:** ProgressionLoop
**Method:** `calculate_upgrades(progression: CharacterProgression, rules: ProgressionRules) -> List[UpgradeOption]`

- Determine what upgrades are affordable:
  ```python
  available_upgrades = []

  # Level up
  if progression.xp >= rules.level_up_xp:
      available_upgrades.append(UpgradeOption(
          type='level_up',
          cost=rules.level_up_xp,
          description=f'Level up to {progression.level + 1}',
          benefits=rules.level_benefits.get(progression.level + 1, [])
      ))

  # Attributes
  for attr, cost in rules.attribute_costs.items():
      if progression.xp >= cost:
          current_value = progression.attributes.get(attr, 10)
          max_value = rules.max_attributes.get(attr, 20)
          if current_value < max_value:
              available_upgrades.append(UpgradeOption(
                  type='attribute',
                  attribute=attr,
                  cost=cost,
                  description=f'Increase {attr} from {current_value} to {current_value + 1}',
                  new_value=current_value + 1
              ))

  # Skills
  for skill, cost in rules.skill_costs.items():
      if progression.xp >= cost:
          current_level = progression.skills.get(skill, 0)
          max_level = rules.max_skills.get(skill, 5)
          if current_level < max_level:
              available_upgrades.append(UpgradeOption(
                  type='skill',
                  skill=skill,
                  cost=cost,
                  description=f'Train {skill} from {current_level} to {current_level + 1}',
                  new_level=current_level + 1
              ))
  ```
- Return list of affordable upgrades

**Success Criteria:**
- Upgrade calculation: 100% accuracy
- Affordability check: 100%

**Error Cases:**
- Rules incomplete → Use defaults
- Calculation error → Return empty list, log error

---

### Action 5: Present Progression UI or Prompt

**Agent:** ProgressionLoop
**Method:** `present_progression_ui(progression: CharacterProgression, upgrades: List[UpgradeOption]) -> str`

- Construct prompt or UI:
  ```python
  prompt = f"""
  🔔 DOWNTIME & PROGRESSION 🔔

  Character: {progression.name}
  Level: {progression.level}
  XP: {progression.xp} / {progression.xp_to_next_level}

  Available Upgrades:
  """

  for i, upgrade in enumerate(upgrades, 1):
      prompt += f"{i}. {upgrade.description} (Cost: {upgrade.cost} XP)\n"

  prompt += "\nSelect upgrades by number (comma-separated), or 'done' to skip.\n"
  ```
- Display to user
- Awaiting user selection

**Success Criteria:**
- UI clarity: 100% (players understand options)
- All options displayed: 100%

**Error Cases:**
- No upgrades available → Prompt: "No upgrades available with current XP."

---

### Action 6: Parse User Selection

**Agent:** ProgressionLoop
**Method:** `parse_selection(input: str, upgrades: List[UpgradeOption]) -> List[UpgradeOption]`

- Parse user input:
  ```python
  if input.lower() == 'done':
      return []

  selected_indices = [int(x.strip()) for x in input.split(',')]
  selected_upgrades = []

  for index in selected_indices:
      if 1 <= index <= len(upgrades):
          selected_upgrades.append(upgrades[index - 1])
  ```
- Validate selection:
  - Total cost ≤ available XP
  - No duplicate upgrades
- Return selected upgrades

**Success Criteria:**
- Selection parsing: 100% accuracy
- Validation: 100%

**Error Cases:**
- Invalid input → Ask user to rephrase
- Duplicate selection → Remove duplicates
- Insufficient XP → Ask user to select different upgrades

---

### Action 7: Validate Against Game System Rules

**Agent:** ProgressionLoop
**Method:** `validate_selection(upgrades: List[UpgradeOption], rules: ProgressionRules, progression: CharacterProgression) -> ValidationResult`

- Check each upgrade against rules:
  ```python
  validation = ValidationResult(valid=True, errors=[])

  total_cost = sum(u.cost for u in upgrades)
  if total_cost > progression.xp:
      validation.valid = False
      validation.errors.append(f"Total cost ({total_cost}) exceeds available XP ({progression.xp})")

  for upgrade in upgrades:
      if upgrade.type == 'attribute':
          current_value = progression.attributes.get(upgrade.attribute, 10)
          max_value = rules.max_attributes.get(upgrade.attribute, 20)
          if current_value >= max_value:
              validation.valid = False
              validation.errors.append(f"{upgrade.attribute} already at max ({max_value})")

      if upgrade.type == 'skill':
          current_level = progression.skills.get(upgrade.skill, 0)
          max_level = rules.max_skills.get(upgrade.skill, 5)
          if current_level >= max_level:
              validation.valid = False
              validation.errors.append(f"{upgrade.skill} already at max ({max_level})")
  ```
- Return validation result

**Success Criteria:**
- Rule validation: 100% accuracy
- Error detection: 100%

**Error Cases:**
- Validation fails → Display errors, ask user to reselect

---

### Action 8: Create ProposedChanges for CanonKeeper

**Agent:** ProgressionLoop
**Method:** `create_proposed_changes(character_id: str, upgrades: List[UpgradeOption]) -> ProposedChange[]`

- Create ProposedChange for each upgrade:
  ```python
  proposed_changes = []

  for upgrade in upgrades:
      if upgrade.type == 'level_up':
          proposed_changes.append(ProposedChange(
              entity_id=character_id,
              change_type='level_up',
              changes={'level': upgrade.new_level},
              reason=f"Character progression during downtime",
              evidence_refs=[{"source": "progression", "upgrade_type": "level_up"}]
          ))

      if upgrade.type == 'attribute':
          proposed_changes.append(ProposedChange(
              entity_id=character_id,
              change_type='attribute_increase',
              changes={f'attributes.{upgrade.attribute}': upgrade.new_value},
              reason=f"Character progression during downtime",
              evidence_refs=[{"source": "progression", "upgrade_type": "attribute", "attribute": upgrade.attribute}]
          ))

      if upgrade.type == 'skill':
          proposed_changes.append(ProposedChange(
              entity_id=character_id,
              change_type='skill_training',
              changes={f'skills.{upgrade.skill}': upgrade.new_level},
              reason=f"Character progression during downtime",
              evidence_refs=[{"source": "progression", "upgrade_type": "skill", "skill": upgrade.skill}]
          ))
  ```
- Submit to CanonKeeper for evaluation

**Success Criteria:**
- ProposedChanges creation: 100% success
- Evidence tracking: 100%

**Error Cases:**
- CanonKeeper unavailable → Cache changes, retry later

---

### Action 9: CanonKeeper Evaluates and Commits

**Agent:** CanonKeeper
**Method:** `evaluate_and_commit(proposed_changes: ProposedChange[]) -> CanonResult`

- CanonKeeper evaluates each ProposedChange:
  - Check consistency with existing facts
  - Validate against game system rules
  - Check for contradictions
- CanonKeeper commits changes to Neo4j:
  ```python
  for change in proposed_changes:
      neo4j_update_entity(
          entity_id=change.entity_id,
          properties=change.changes
      )
  ```
- Deduct XP from character:
  ```python
  total_xp_spent = sum(u.cost for u in upgrades)
  neo4j_update_entity(
      entity_id=character_id,
      properties={'xp': progression.xp - total_xp_spent}
  )
  ```
- Return canon result

**Success Criteria:**
- Evaluation: 100% success
- Commitment: 100% success
- XP deduction: 100% accuracy

**Error Cases:**
- CanonKeeper rejection → Return error with reason
- Commitment fails → Log error, retry later

---

### Action 10: Narrator Describes Progression

**Agent:** NarratorAgent
**Method:** `describe_progression(upgrades: List[UpgradeOption], character_name: str) -> str`

- Generate narrative description:
  ```python
  prompt = f"""
  Describe the character's progression during downtime.

  Character: {character_name}
  Upgrades: {[u.description for u in upgrades]}

  Write a brief narrative describing the training, reflection, or
  events that led to these improvements. Keep it to 1-2 sentences.
  """
  ```
- Return narrative

**Success Criteria:**
- Narrative quality: ≥4/5 rating
- All upgrades mentioned: 100%

**Error Cases:**
- Narrator fails → Return list of upgrades as text

---

### Action 11: Append Turns

**Agent:** ProgressionLoop
**Method:** `append_progression_turns(scene_id: str, user_selection: str, response: str, upgrades: List[UpgradeOption]) -> Turn[]`

- Create user turn:
  ```python
  TurnCreate(
      speaker_id=user_id,
      turn_type=TurnType.PROGRESSION,
      content=user_selection,
      metadata={
          "downtime_triggered": True,
          "upgrades_selected": [u.type for u in upgrades],
          "xp_spent": sum(u.cost for u in upgrades)
      }
  )
  ```
- Create GM turn:
  ```python
  TurnCreate(
      speaker_id="system:progression",
      turn_type=TurnType.NARRATION,
      content=response,
      metadata={
          "progression_applied": True,
          "upgrades_applied": [u.description for u in upgrades],
          "canonized": True
      }
  )
  ```
- Append both turns to scene

**Success Criteria:**
- Turn creation: 100% success
- Metadata completeness: 100%

**Error Cases:**
- Turn append fails → Error, cache for retry

---

## Postconditions

1. **Character stats updated** in Neo4j
2. **XP deducted** from character
3. **Progression logged** in turns
4. **Narrator describes** progression

## Success Criteria

1. **Downtime detection:** 100% accuracy
2. **Character retrieval:** 100% success
3. **Game system rules retrieved:** 100% success
4. **Upgrade calculation:** 100% accuracy
5. **UI clarity:** 100%
6. **Selection parsing:** 100% accuracy
7. **Rule validation:** 100% accuracy
8. **Canonization:** 100% success
9. **XP deduction:** 100% accuracy
10. **End-to-end latency:** ≤5 seconds

## Error Cases

| Error | Detection | Handling |
|-------|-----------|----------|
| Story/scene not found | Query returns None | Error, ask user to start story |
| Character not found | Query returns None | Error, ask user to create character |
| Game system not found | Query returns None | Error, ask user to select system |
| No upgrades available | Upgrades list empty | Prompt: "No upgrades available" |
| Invalid user selection | Parse fails | Ask user to rephrase |
| Insufficient XP | Validation fails | Ask user to select different upgrades |
| CanonKeeper rejection | CanonKeeper returns conflict | Display error, allow reselection |
| Commitment fails | Neo4j update throws exception | Log error, retry later |
| Narrator fails | Narrator returns error | Return list of upgrades as text |

## Test Scenarios

### Scenario 1: Level Up

**Given:**
- Character: "Aragorn"
- Level: 1, XP: 1000
- Game system: D&D 5e
- Level up cost: 1000 XP

**When:**
- Downtime detected (story arc resolution)
- Upgrades calculated: Level up available
- User selects: "1" (level up)
- Validation passes
- CanonKeeper commits

**Then:**
- Character level updated to 2
- XP reduced to 0
- Narrator describes: "Aragorn reflects on his recent battles, gaining new insights and experience that bring him to new heights of skill."
- User turn appended with metadata: `upgrades_selected: ["level_up"]`, `xp_spent: 1000`
- GM turn appended with metadata: `progression_applied: True`, `upgrades_applied: ["Level up to 2"]`

---

### Scenario 2: Multiple Upgrades

**Given:**
- Character: "Gimli"
- Level: 1, XP: 150
- Game system: D&D 5e
- Attribute costs: {"strength": 50, "constitution": 50}
- Current attributes: {"strength": 14, "constitution": 14}

**When:**
- Downtime detected
- Upgrades calculated: Strength +1 (50 XP), Constitution +1 (50 XP)
- User selects: "1,2" (both attributes)
- Validation passes (total cost: 100 XP ≤ 150 XP)
- CanonKeeper commits

**Then:**
- Strength updated to 15
- Constitution updated to 15
- XP reduced to 50
- Narrator describes: "Gimli spends his downtime training, strengthening both his body and his resolve."
- User turn appended with metadata: `upgrades_selected: ["attribute", "attribute"]`, `xp_spent: 100`
- GM turn appended with metadata: `progression_applied: True`, `upgrades_applied: ["Increase strength from 14 to 15", "Increase constitution from 14 to 15"]`

---

### Scenario 3: No Upgrades Available

**Given:**
- Character: "Legolas"
- Level: 5, XP: 10
- Game system: D&D 5e
- All attributes at max (20)
- All skills at max (5)

**When:**
- Downtime detected
- Upgrades calculated: None (insufficient XP, maxed stats)
- System prompts: "No upgrades available with current XP."

**Then:**
- No upgrades selected
- No XP spent
- Narrator describes: "Legolas rests and reflects on his journey, though he has reached the pinnacle of his abilities for now."
- User turn appended with metadata: `upgrades_selected: []`, `xp_spent: 0`
- GM turn appended with metadata: `progression_applied: False`

---

### Scenario 4: Insufficient XP for Selection

**Given:**
- Character: "Boromir"
- Level: 1, XP: 75
- Game system: D&D 5e
- Attribute costs: {"strength": 50, "charisma": 50}

**When:**
- Downtime detected
- Upgrades calculated: Strength +1 (50 XP), Charisma +1 (50 XP)
- User selects: "1,2" (both attributes)
- Validation fails (total cost: 100 XP > 75 XP)
- System prompts: "Total cost (100) exceeds available XP (75). Please select different upgrades."
- User reselects: "1" (only Strength)

**Then:**
- Strength updated to new value
- Charisma unchanged
- XP reduced to 25
- Narrator describes progression
- Turn metadata shows single upgrade

**Note:** System prevents overspending.

---

### Scenario 5: Skill Training

**Given:**
- Character: "Frodo"
- Level: 1, XP: 50
- Game system: D&D 5e
- Skill costs: {"stealth": 25, "perception": 25}
- Current skills: {"stealth": 0, "perception": 0}

**When:**
- Downtime detected
- Upgrades calculated: Stealth +1 (25 XP), Perception +1 (25 XP)
- User selects: "1,2" (both skills)
- Validation passes (total cost: 50 XP ≤ 50 XP)
- CanonKeeper commits

**Then:**
- Stealth updated to 1
- Perception updated to 1
- XP reduced to 0
- Narrator describes: "Frodo practices moving silently and observing his surroundings, honing his skills for the journey ahead."
- User turn appended with metadata: `upgrades_selected: ["skill", "skill"]`, `xp_spent: 50`
- GM turn appended with metadata: `progression_applied: True`, `upgrades_applied: ["Train stealth from 0 to 1", "Train perception from 0 to 1"]`

---

## Contradictions Check

### Check with P-18: Oracle

| Aspect | P-21 | P-18 | Contradiction? | Resolution |
|--------|------|------|----------------|------------|
| **Trigger** | Downtime | Questions | ✅ No | Different patterns |
| **Purpose** | Character advancement | Answer facts | ✅ No | Different purposes |
| **Dice** | None (direct progression) | Oracle 1d100 | ✅ No | No dice in P-21 |
| **Canonization** | Entity properties | Oracle facts | ✅ No | Different types |
| **Narrator** | Progression description | Oracle response | ✅ No | Different contexts |
| **Turns** | PROGRESSION/NARRATION | QUESTION/ORACLE_RESPONSE | ✅ No | Different types |

**Result:** ✅ NO CONTRADICTIONS

### Check with P-19: Procedural Generation

| Aspect | P-21 | P-19 | Contradiction? | Resolution |
|--------|------|------|----------------|------------|
| **Trigger** | Downtime | Movement | ✅ No | Different patterns |
| **Purpose** | Character advancement | Generate content | ✅ No | Different purposes |
| **Dice** | None | Table rolls | ✅ No | No dice in P-21 |
| **Canonization** | Entity properties | Entities | ✅ No | Different types |
| **Narrator** | Progression description | Scene opening | ✅ No | Different contexts |
| **Turns** | PROGRESSION/NARRATION | MOVEMENT/SCENE_START | ✅ No | Different types |

**Result:** ✅ NO CONTRADICTIONS

### Check with P-20: Forced Narrative Pushback

| Aspect | P-21 | P-20 | Contradiction? | Resolution |
|--------|------|------|----------------|------------|
| **Trigger** | Downtime | Forced narrative | ✅ No | Different patterns |
| **Purpose** | Character advancement | Prevent abuse | ✅ No | Different purposes |
| **Dice** | None | Action dice rolls | ✅ No | No dice in P-21 |
| **Canonization** | Entity properties | None | ✅ No | P-20 doesn't canonize |
| **Narrator** | Progression description | Outcome description | ✅ No | Different contexts |
| **Turns** | PROGRESSION/NARRATION | ACTION/NARRATION | ✅ No | Different types |

**Result:** ✅ NO CONTRADICTIONS

---

## Dependencies

### Use Case Dependencies

- **DL-20: Game Systems** - Provides progression rules and costs
- **DL-2: Entity Schemas** - Provides character entity structure
- **P-2: Turn Loop** - Provides turn structure and append mechanism
- **P-3: Scene Lifecycle** - Provides scene creation and downtime detection

### Layer Dependencies

- **Data-Layer:**
  - DL-2: Entity Schema (Entity entity, properties, state_tags)
  - DL-4: ProposedChange Schema (canonization workflow)
  - DL-5: CanonKeeper (Entity evaluation and commitment)
  - DL-20: Game Systems (progression rules, costs)

- **Agents:**
  - ProgressionLoop (detect_downtime_trigger, calculate_upgrades, validate_selection)
  - CanonKeeper (evaluate_and_commit)
  - NarratorAgent (describe_progression)

### External Dependencies

- Neo4j (Entity storage and updates)
- MongoDB (Game systems storage, Turn storage)
- LLM (Narrator)

---

## Implementation Notes

### Performance Considerations

1. **Caching:** Cache game system rules for repeated queries
2. **Async operations:** CanonKeeper evaluation is async, don't block on it
3. **Batch updates:** Update all character properties in single Neo4j call

### Security Considerations

1. **CanonKeeper authority:** All character updates must go through CanonKeeper
2. **Rule validation:** All progression choices must be validated against game system rules
3. **Evidence tracking:** Every progression change must have evidence_refs

### User Experience

1. **Clear UI:** Players should understand what upgrades are available
2. **Validation feedback:** Players should see why a selection is invalid
3. **Narrative integration:** Progression should feel like character development, not just numbers

### Known Limitations

1. **Binary progression:** Either full upgrade or nothing (no partial upgrades)
2. **No respecialization:** Can't undo or change past upgrades
3. **System-dependent:** Different game systems have different progression rules