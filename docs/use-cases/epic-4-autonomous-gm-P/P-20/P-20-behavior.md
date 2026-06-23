# P-20: Forced Narrative Pushback - Behavior Definition

**Use Case ID:** P-20
**Last Updated:** 2026-05-19
**Status:** ✅ Defined

## Overview

Forced Narrative Pushback provides GM authority in single-player mode by pushing back against player abuse of forced narrative declarations (e.g., "I instantly kill the boss"). When the Resolver detects a forced narrative that involves a contested or high-stakes action, the Orchestrator pauses the turn and asks the player to confirm a roll or modifies the action into an attempt, ensuring stakes are preserved.

## Preconditions

1. **Active scene exists** in MongoDB
2. **User is in single-player mode** (Autonomous GM)
3. **Resolver is available** (P-4 implemented)
4. **SceneLoop is available** (P-3 implemented)
5. **User declares action** with forced narrative

## User Actions

1. User declares action with forced narrative
   - Example: "I instantly kill the boss"
   - Example: "I pick the lock effortlessly"
   - Example: "I cast a spell that destroys the entire room"

2. System detects forced narrative and pauses

3. System prompts for roll or override

4. User accepts pushback OR overrides with explicit command

## System Actions

### Action 1: Parse User Input for Forced Narrative

**Agent:** Resolver (P-4)
**Method:** `detect_forced_narrative(input: str) -> bool`

- Analyze user input for forced narrative patterns:
  - **Instantaneous outcomes:** "instantly", "immediately", "effortlessly", "without effort"
  - **Guaranteed success:** "will succeed", "cannot fail", "guaranteed", "certain"
  - **Magnitude violations:** "kill the boss instantly", "destroy the entire room", "solve all problems"
  - **Declarative outcomes:** "I kill the goblin", "I pick the lock" (no attempt language)
- Distinguish from normal actions:
  - Normal: "I attack the goblin" (attempt)
  - Forced: "I kill the goblin" (declarative)
- Return `True` if forced narrative detected

**Success Criteria:**
- Forced narrative detection: ≥95% precision
- False positive rate: ≤5%

**Error Cases:**
- Input parsing fails → Treat as normal action (no pushback)

---

### Action 2: Determine Current Stakes

**Agent:** Resolver (P-4)
**Method:** `determine_stakes(action: str, context: dict) -> StakesLevel`

- Analyze action and context to determine stakes:
  - **Low stakes (No pushback):**
    - Trivial actions: "I open the door", "I walk across the room"
    - Social interactions: "I talk to the merchant", "I ask for directions"
    - Environmental interactions: "I pick up the rock", "I look around"
  - **Medium stakes (Optional pushback):**
    - Skill checks: "I pick the lock", "I climb the wall"
    - Minor challenges: "I sneak past the guard", "I find a hidden passage"
  - **High stakes (Mandatory pushback):**
    - Combat: "I kill the boss", "I defeat the dragon"
    - Major plot points: "I solve the mystery", "I find the treasure"
    - Significant challenges: "I escape the collapsing castle", "I survive the trap"
- Map to stakes level:
  ```python
  if is_combat_action(action):
      return StakesLevel.HIGH
  if is_major_plot_point(action, context):
      return StakesLevel.HIGH
  if is_trivial(action):
      return StakesLevel.LOW
  return StakesLevel.MEDIUM
  ```

**Success Criteria:**
- Stakes evaluation: 100% accuracy
- High stakes detection: 100% (no false negatives)

**Error Cases:**
- Unknown stakes → Default to MEDIUM (conservative)

---

### Action 3: Evaluate Stakes Against Pushback Threshold

**Agent:** SceneLoop
**Method:** `should_trigger_pushback(stakes: StakesLevel) -> bool`

- Compare stakes against pushback threshold:
  ```python
  PUSHBACK_THRESHOLD = StakesLevel.HIGH  # Only high stakes trigger mandatory pushback

  if stakes >= PUSHBACK_THRESHOLD:
      return True  # Trigger pushback
  elif stakes == StakesLevel.MEDIUM:
      return False  # Optional pushback (player choice)
  else:
      return False  # No pushback
  ```
- For HIGH stakes, pushback is **mandatory**
- For MEDIUM stakes, pushback is **optional** (system may suggest)

**Success Criteria:**
- Threshold evaluation: 100% accuracy
- No false negatives (all high stakes trigger pushback)

---

### Action 4: Generate Pushback Prompt

**Agent:** SceneLoop
**Method:** `generate_pushback_prompt(action: str, stakes: StakesLevel) -> str`

- Construct pushback prompt explaining why:
  ```python
  prompt = f"""
  ⚠️ PUSHBACK REQUIRED ⚠️

  You declared: "{action}"

  This action involves high stakes (combat/major plot). The GM recommends resolving it with a dice roll to ensure fair and dramatic gameplay.

  Do you want to:
  1. Convert to dice roll: "I [attempt action]" (e.g., "I attack the boss")
  2. Override and proceed: "/gm-mode I [action]" (e.g., "/gm-mode I instantly kill the boss")

  Note: Overriding is logged and should be used sparingly.
  """
  ```
- Prompt includes:
  - Original action
  - Why pushback triggered
  - Options to accept or override
  - Warning about override logging

**Success Criteria:**
- Prompt clarity: 100% (players understand why)
- Options clarity: 100% (players know how to respond)

**Error Cases:**
- Prompt generation fails → Use fallback: "This action requires a dice roll. Proceed with a dice roll or use /gm-mode to override."

---

### Action 5: Awaiting User Response

**Agent:** SceneLoop
**Method:** `await_pushback_response(scene_id: str) -> PushbackResponse`

- Pause turn loop and await user input
- Parse user response:
  ```python
  if user_input.startswith("/gm-mode"):
      return PushbackResponse.OVERRIDE
  elif is_attempt_action(user_input):  # "I attack the boss"
      return PushbackResponse.ACCEPT
  else:
      return PushbackResponse.INVALID
  ```
- Validate response:
  - Accept: Action converted to attempt (dice roll)
  - Override: Explicit /gm-mode command
  - Invalid: Ask user to rephrase

**Success Criteria:**
- Response parsing: 100% accuracy
- Validation: 100% (invalid responses rejected)

**Error Cases:**
- Invalid response → Ask user to rephrase with examples

---

### Action 6: Convert to Dice Roll (If Accepted)

**Agent:** Resolver (P-4)
**Method:** `convert_to_dice_roll(action: str) -> str`

- If user accepts pushback:
  - Parse forced narrative to extract intent:
    - "I instantly kill the boss" → "I attack the boss"
    - "I pick the lock effortlessly" → "I pick the lock"
    - "I cast a spell that destroys the entire room" → "I cast a spell"
  - Convert to attempt language:
    - Add attempt verbs: "attack", "attempt to", "try to"
    - Remove instantaneous modifiers: "instantly", "effortlessly"
  - Return converted action

**Success Criteria:**
- Conversion accuracy: ≥95%
- Intent preservation: 100%

**Error Cases:**
- Conversion fails → Use original action as dice roll

---

### Action 7: Log Override (If Overridden)

**Agent:** SceneLoop
**Method:** `log_override(scene_id: str, action: str, reason: str) -> void`

- If user overrides with /gm-mode:
  - Create override log:
    ```python
    OverrideLogCreate(
        scene_id=scene_id,
        original_action=action,
        override_command=user_input,
        reason="Player override of forced narrative pushback",
        timestamp=datetime.now(),
        stakes_level=stakes
    )
    ```
  - Store in MongoDB (overridden_actions collection)
  - Increment scene's override_count
  - Warn if override_count > 3: "You've overridden 3 times. Consider using dice rolls for better gameplay."

**Success Criteria:**
- Override logging: 100% success
- Override tracking: 100% (every override logged)

**Error Cases:**
- Log creation fails → Continue with action, log error

---

### Action 8: Narrator Describes Outcome

**Agent:** NarratorAgent
**Method:** `describe_outcome(action: str, outcome: ResolutionOutcome, pushback_used: bool) -> str`

- Generate narrative description:
  - If pushback accepted and dice roll succeeded:
    - Describe success with effort and drama
    - Example: "You strike true, dealing a mighty blow to the boss!"
  - If pushback accepted and dice roll failed:
    - Describe failure with consequences
    - Example: "Your attack misses! The boss counterattacks."
  - If overridden:
    - Describe as declared
    - Example: "With supernatural speed, you strike the boss down in an instant."
- Incorporate pushback context:
  - If pushback used: "After a tense roll..."
  - If overridden: "As you commanded..."

**Success Criteria:**
- Narrative consistency: 100% (matches outcome)
- Pushback context included: 100%

**Error Cases:**
- Narrator fails → Return raw outcome without narration

---

### Action 9: Append Turns

**Agent:** SceneLoop
**Method:** `append_pushback_turns(scene_id: str, user_action: str, response: str, pushback_used: bool, overridden: bool) -> Turn[]`

- Create user turn:
  ```python
  TurnCreate(
      speaker_id=user_id,
      turn_type=TurnType.ACTION,
      content=user_action,
      metadata={
          "forced_narrative_detected": forced_narrative,
          "pushback_triggered": pushback_used,
          "overridden": overridden,
          "stakes_level": stakes.value if pushback_used else None
      }
  )
  ```
- Create GM turn:
  ```python
  TurnCreate(
      speaker_id="system:pushback" if pushback_used else "system:narrator",
      turn_type=TurnType.NARRATION,
      content=response,
      metadata={
          "pushback_used": pushback_used,
          "overridden": overridden,
          "dice_roll_used": dice_roll_result if pushback_accepted else None
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

1. **If accepted:** Action resolved via dice roll, not forced narrative
2. **If overridden:** Forced narrative allowed, override logged
3. **Turn appended** with correct metadata
4. **Override logged** in MongoDB (if overridden)
5. **Narrator describes** appropriate outcome

## Success Criteria

1. **Forced narrative detection:** ≥95% precision
2. **Stakes evaluation:** 100% accuracy
3. **Pushback only triggers for high-stakes:** 100% specificity
4. **Player can accept or override:** 100% success
5. **Override logged:** 100% (every override logged)
6. **Conversion to dice roll:** ≥95% accuracy
7. **End-to-end latency:** ≤3 seconds

## Error Cases

| Error | Detection | Handling |
|-------|-----------|----------|
| Resolver failure | Parse returns error | Error message, allow action |
| CanonKeeper failure | Canon call times out | Error message, allow action with warning |
| Narrator failure | Narrator returns error | Return raw outcome without narration |
| Unknown stakes | Stakes evaluation fails | Default to MEDIUM stakes |
| Invalid user response | Response doesn't match patterns | Ask user to rephrase with examples |
| Override log fails | Log creation throws exception | Continue with action, log error |

## Test Scenarios

### Scenario 1: Combat - High Stakes Pushback

**Given:**
- Scene with combat in progress
- Boss NPC present
- User declares: "I instantly kill the boss"

**When:**
- Forced narrative detected (instantaneous + combat)
- Stakes evaluated: HIGH (combat)
- Pushback triggered
- User accepts: "I attack the boss"
- Dice roll: 18 (success)

**Then:**
- Forced narrative detected: True
- Stakes level: HIGH
- Pushback triggered: True
- Action converted: "I attack the boss"
- Dice roll executed: 18
- Outcome: SUCCESS
- Narrator describes: "You strike true, dealing a mighty blow to the boss!"
- User turn appended with metadata: `forced_narrative_detected: True`, `pushback_triggered: True`, `overridden: False`
- GM turn appended with metadata: `pushback_used: True`, `dice_roll_used: 18`

---

### Scenario 2: Override with /gm-mode

**Given:**
- Scene with combat in progress
- Boss NPC present
- User declares: "I instantly kill the boss"

**When:**
- Forced narrative detected
- Stakes evaluated: HIGH
- Pushback triggered
- User overrides: "/gm-mode I instantly kill the boss"

**Then:**
- Forced narrative detected: True
- Stakes level: HIGH
- Pushback triggered: True
- Override logged in MongoDB
- Narrator describes: "With supernatural speed, you strike the boss down in an instant."
- User turn appended with metadata: `forced_narrative_detected: True`, `pushback_triggered: True`, `overridden: True`
- GM turn appended with metadata: `pushback_used: True`, `overridden: True`
- Scene's override_count incremented

---

### Scenario 3: Low Stakes - No Pushback

**Given:**
- Scene with trivial interaction
- User declares: "I open the door effortlessly"

**When:**
- Forced narrative detected (effortlessly)
- Stakes evaluated: LOW (trivial action)
- Pushback threshold check: LOW < HIGH
- Pushback NOT triggered

**Then:**
- Forced narrative detected: True
- Stakes level: LOW
- Pushback triggered: False
- Action proceeds as declared
- Narrator describes: "The door opens easily at your touch."
- User turn appended with metadata: `forced_narrative_detected: True`, `pushback_triggered: False`

**Note:** Low stakes actions don't trigger pushback.

---

### Scenario 4: Medium Stakes - Optional Pushback

**Given:**
- Scene with skill check
- User declares: "I pick the lock effortlessly"

**When:**
- Forced narrative detected (effortlessly)
- Stakes evaluated: MEDIUM (skill check)
- Pushback threshold check: MEDIUM < HIGH
- Pushback NOT mandatory, but suggested

**Then:**
- Forced narrative detected: True
- Stakes level: MEDIUM
- Pushback triggered: False (optional)
- System may suggest: "Would you like to roll for this lock pick?"
- If user ignores suggestion: Action proceeds as declared
- If user accepts suggestion: Action converted to dice roll

**Note:** Medium stakes actions may suggest pushback but don't require it.

---

### Scenario 5: Multiple Overrides Warning

**Given:**
- Scene with override_count = 3
- User declares: "I instantly defeat the dragon"

**When:**
- Forced narrative detected
- Stakes evaluated: HIGH
- Pushback triggered
- User overrides: "/gm-mode I instantly defeat the dragon"

**Then:**
- Override logged
- override_count incremented to 4
- Warning displayed: "You've overridden 4 times. Consider using dice rolls for better gameplay."
- Narrator describes as declared
- Turn appended with metadata showing override

**Note:** System warns about excessive overrides.

---

## Contradictions Check

### Check with P-18: Oracle

| Aspect | P-20 | P-18 | Contradiction? | Resolution |
|--------|------|------|----------------|------------|
| **Trigger** | Forced narrative | Questions | ✅ No | Different patterns |
| **Purpose** | Prevent abuse | Answer facts | ✅ No | Different purposes |
| **Dice** | Action dice rolls | Oracle 1d100 | ✅ No | Different dice |
| **Canonization** | None | Oracle facts | ✅ No | P-20 doesn't canonize |
| **Narrator** | Outcome description | Oracle response | ✅ No | Different contexts |
| **Turns** | ACTION/NARRATION | QUESTION/ORACLE_RESPONSE | ✅ No | Different types |

**Result:** ✅ NO CONTRADICTIONS

### Check with P-19: Procedural Generation

| Aspect | P-20 | P-19 | Contradiction? | Resolution |
|--------|------|------|----------------|------------|
| **Trigger** | Forced narrative | Movement | ✅ No | Different patterns |
| **Purpose** | Prevent abuse | Generate content | ✅ No | Different purposes |
| **Dice** | Action dice rolls | Table rolls | ✅ No | Different dice |
| **Canonization** | None | Entities | ✅ No | P-20 doesn't canonize |
| **Narrator** | Outcome description | Scene opening | ✅ No | Different contexts |
| **Turns** | ACTION/NARRATION | MOVEMENT/SCENE_START | ✅ No | Different types |

**Result:** ✅ NO CONTRADICTIONS

---

## Dependencies

### Use Case Dependencies

- **P-2: Turn Loop** - Provides turn structure and append mechanism
- **P-3: Scene Lifecycle** - Provides scene creation and turn loop
- **P-4: Resolve Action** - Provides action resolution and dice rolling

### Layer Dependencies

- **Data-Layer:**
  - DL-2: Turn Schema (Turn entity, turn_type, metadata)
  - DL-4: ProposedChange Schema (state modifications)

- **Agents:**
  - Resolver (detect_forced_narrative, determine_stakes, convert_to_dice_roll)
  - SceneLoop (should_trigger_pushback, generate_pushback_prompt, await_pushback_response, log_override)
  - NarratorAgent (describe_outcome)

### External Dependencies

- MongoDB (Turn, OverrideLog storage)
- LLM (Narrator)
- Dice system (action rolls)

---

## Implementation Notes

### Performance Considerations

1. **Caching:** Cache stakes evaluation for similar actions
2. **Async operations:** Override logging is async, don't block on it
3. **Optimization:** Skip pushback for known trivial actions

### Security Considerations

1. **Override logging:** Every override MUST be logged for audit trail
2. **Override warnings:** Warn users about excessive overrides
3. **Stakes accuracy:** Ensure high stakes are never missed

### User Experience

1. **Clear explanations:** Players should understand why pushback was triggered
2. **Easy responses:** Accept or override should be simple commands
3. **Fast response:** Pushback handling should be ≤2 seconds

### Known Limitations

1. **Binary stakes:** Low/Medium/High may be too coarse
2. **No adaptive thresholds:** Threshold doesn't adjust to player skill level
3. **Override spam:** Players could override repeatedly (though warned)