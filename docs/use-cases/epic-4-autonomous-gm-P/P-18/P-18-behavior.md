# P-18: AutoGM Oracle & Probability Resolution - Behavior Definition

**Use Case ID:** P-18
**Last Updated:** 2026-05-19
**Status:** ✅ Defined

## Overview

The AutoGM Oracle provides probability-based resolution for questions about unknown environmental states in single-player mode. It uses a percentile die (1d100) to determine Yes/No outcomes, with modifiers for "Yes, and" or "No, but" on extreme rolls.

## Preconditions

1. **Active scene exists** in MongoDB
2. **User submits a question** about the world (e.g., "Is the door locked?")
3. **User is in single-player mode** (Autonomous GM)
4. **ContextAssembly** has prepared scene context
5. **LLM client** is available

## User Actions

1. User types a question into the terminal
   - Example: "Is the door locked?"
   - Example: "Is there a secret passage here?"
   - Example: "Does the guard have a key?"

## System Actions

### Action 1: Parse User Input

**Agent:** ContextAssembly
**Method:** `detect_oracle_query(input: str) -> bool`

- Analyze user input for question patterns
- Detect question words: "Is", "Are", "Do", "Does", "Has", "Have", "Will", "Can", "Could"
- Distinguish from action declarations
- Return `True` if oracle query detected

**Success Criteria:**
- Question detection accuracy: ≥95%
- False positive rate: ≤5%

**Error Cases:**
- Input parsing fails → Error message, ask user to rephrase

---

### Action 2: Determine Tension & Likelihood

**Agent:** SceneLoop (OracleAgent)
**Method:** `determine_likelihood(tension_score: int) -> LikelihoodLevel`

- Retrieve current scene's `tension_score` (0-10)
- Map tension_score to likelihood:
  - 0-2: Almost Certain (00-05 → No, 06-95 → Yes, 96-100 → Yes, and)
  - 3-4: Likely (00-25 → No, 26-95 → Yes, 96-100 → Yes, and)
  - 5-6: 50/50 (00-49 → No, 50-95 → Yes, 96-100 → Yes, and)
  - 7-8: Unlikely (00-49 → No, 50-95 → Yes, 96-100 → Yes, and)
  - 9-10: Impossible (00-95 → No, 96-100 → No, and)

**Success Criteria:**
- Tension retrieval accuracy: 100%
- Likelihood mapping correctness: 100%

**Error Cases:**
- Scene not found → Error, ask user to start a scene
- Tension_score not set → Default to 50/50 (tension=5)

---

### Action 3: Roll Percentile Die

**Agent:** SceneLoop (OracleAgent)
**Method:** `roll_percentile() -> int`

- Generate random number between 1-100
- Apply appropriate dice system (OpenLegend, D&D 5e, etc.)
- Return roll result

**Success Criteria:**
- Roll range: 1-100 (100% correct)
- Randomness: No predictable patterns

**Error Cases:**
- Random number generator fails → Error, attempt retry

---

### Action 4: Canonize Oracle Result

**Agent:** CanonKeeper
**Method:** `canonize_oracle_result(query: str, outcome: OracleOutcome) -> Fact`

- Create `Fact` entity in MongoDB:
  ```python
  FactCreate(
      entity_id=query_hash,
      fact_type=FactType.WORLD_PROPERTY,
      content=f"{query}: {outcome}",
      canon_level=CanonLevel.CARDS,  # Game world truth
      evidence_refs=["oracle:{roll}:{tension_score}"]
  )
  ```
- Submit to CanonKeeper for evaluation
- CanonKeeper evaluates consistency
- CanonKeeper commits to Neo4j

**Success Criteria:**
- Fact creation: 100% success
- Evidence tracking: 100% (every oracle result has evidence)
- CanonKeeper evaluation: ≤2 seconds

**Error Cases:**
- CanonKeeper unavailable → Cache result, retry later
- Inconsistency detected → Prompt user for resolution

---

### Action 5: Narrator Describes Outcome

**Agent:** NarratorAgent
**Method:** `describe_oracle_outcome(query: str, outcome: OracleOutcome, context: dict) -> str`

- Generate narrative description of oracle result
- **CRITICAL CONSTRAINT:** Narrator MUST respect oracle outcome
  - Cannot say "Yes" if oracle said "No"
  - Must include "Yes, and" or "No, but" if rolled
  - Should add flavor and detail consistent with outcome
- Incorporate scene context (entities, relationships)
- Return narrative text

**Success Criteria:**
- Oracle outcome respected: 100%
- "Yes, and"/"No, but" included: 100% when rolled
- Narrative quality: ≥4/5 user rating

**Error Cases:**
- Narrator fails → Return raw oracle outcome without narrative

---

### Action 6: Append Turns

**Agent:** SceneLoop
**Method:** `append_oracle_turns(scene_id: str, query: str, response: str) -> Turn[]`

- Create user turn:
  ```python
  TurnCreate(
      speaker_id=user_id,
      turn_type=TurnType.QUESTION,
      content=query,
      metadata={"oracle_query": True}
  )
  ```
- Create GM turn:
  ```python
  TurnCreate(
      speaker_id="system:oracle",
      turn_type=TurnType.ORACLE_RESPONSE,
      content=response,
      metadata={
          "oracle_result": outcome.value,
          "roll": roll_result,
          "likelihood": likelihood.value,
          "fact_canonized": fact_id
      }
  )
  ```
- Append both turns to scene
- Update scene's `updated_at`

**Success Criteria:**
- Turn creation: 100% success
- Metadata completeness: 100% (roll, likelihood, fact_id all present)
- Append success: 100%

**Error Cases:**
- Scene not found → Error, ask user to start a scene
- Turn append fails → Error, cache turn for retry

---

## Postconditions

1. **Oracle result canonized** as Fact in Neo4j
2. **User turn** appended with metadata `oracle_query: True`
3. **GM turn** appended with oracle outcome and metadata
4. **Scene state updated** with oracle result
5. **Player receives narrative** describing outcome

## Success Criteria

1. **Question detection accuracy:** ≥95%
2. **Tension retrieval accuracy:** 100%
3. **Oracle outcome canonization:** 100%
4. **Narrator respects oracle outcome:** 100%
5. **Evidence tracking:** 100% (every oracle has evidence_refs)
6. **End-to-end latency:** ≤5 seconds

## Error Cases

| Error | Detection | Handling |
|-------|-----------|----------|
| Input parsing fails | Parse returns error | Error message, ask to rephrase |
| Scene not found | Scene lookup returns None | Error, ask to start scene |
| Tension not set | tension_score is None | Default to 50/50 (tension=5) |
| RNG fails | Roll throws exception | Error, retry |
| CanonKeeper unavailable | Canon call times out | Cache result, retry later |
| Inconsistency detected | CanonKeeper returns conflict | Prompt user for resolution |
| Narrator fails | Narrator returns error | Return raw outcome |
| Turn append fails | Turn creation throws exception | Error, cache for retry |

## Test Scenarios

### Scenario 1: Simple Yes/No

**Given:**
- Scene with tension_score = 5 (50/50)
- User asks: "Is the door locked?"

**When:**
- Oracle query detected
- Roll result: 60 (within 50-95 → Yes)

**Then:**
- Fact canonized: "Is the door locked?: Yes"
- Narrator describes: "The door is indeed locked, a sturdy wooden barrier barring your path."
- User turn appended with metadata `oracle_query: True`
- GM turn appended with oracle_result="yes", roll=60, likelihood="fifty_fifty"

---

### Scenario 2: "No, and..." Extreme Roll

**Given:**
- Scene with tension_score = 9 (Impossible)
- User asks: "Can I pick the lock?"

**When:**
- Oracle query detected
- Roll result: 98 (within 96-100 → No, and)

**Then:**
- Fact canonized: "Can I pick the lock?: No, and"
- Narrator describes: "Not only can you not pick the lock, but your attempts have drawn the attention of a nearby guard who approaches with weapon drawn."
- User turn appended
- GM turn appended with oracle_result="no_and", roll=98, likelihood="impossible"

---

### Scenario 3: Known Fact (No Oracle Needed)

**Given:**
- Scene with known Fact: "The door is unlocked"
- User asks: "Is the door locked?"

**When:**
- Oracle query detected
- System checks for existing Fact
- Found existing Fact answering the question

**Then:**
- No oracle roll performed
- Narrator describes: "As you established earlier, the door is unlocked."
- User turn appended
- GM turn appended with metadata `fact_source: "existing"`, not oracle

**Note:** This is an optimization - oracle queries should check existing Facts first.

---

### Scenario 4: Context Adjustment for High Tension

**Given:**
- Scene with tension_score = 10 (Impossible)
- User asks: "Can I sneak past the dragon?"

**When:**
- Oracle query detected
- Roll result: 99 (No, and)

**Then:**
- Fact canonized: "Can I sneak past the dragon?: No, and"
- Narrator describes: "You barely take a step when the dragon's eyes snap open, fixing you with an ancient, predatory gaze. Not only have you failed to sneak past, but you've now attracted its full attention."
- User turn appended
- GM turn appended with oracle_result="no_and", roll=99, likelihood="impossible"

---

### Scenario 5: Consistency Check Across Multiple Oracles

**Given:**
- Scene with tension_score = 5 (50/50)
- User asks: "Is the room empty?"
- Oracle returns: Yes (roll=60)

**When:**
- User then asks: "Are there guards here?"

**Then:**
- System detects potential inconsistency
- Checks existing Facts
- Prompt user: "You established the room is empty. Are you asking if guards are outside or rethinking your previous oracle?"
- Allow user to clarify or roll new oracle

**Note:** Multiple oracle queries should be checked for consistency.

---

## Contradictions Check

### Check with P-19: Procedural Scene Population

| Aspect | P-18 | P-19 | Contradiction? | Resolution |
|--------|------|------|----------------|------------|
| **Trigger** | Questions | Movement | ✅ No | Different patterns |
| **Purpose** | Answer unknown facts | Generate content | ✅ No | Complementary |
| **Dice** | 1d100 (oracle) | Table rolls (1d6, 2d6) | ✅ No | Different dice |
| **Canonization** | Oracle facts | Entities | ✅ No | Different types |
| **Narrator** | Oracle response | Scene opening | ✅ No | Different contexts |
| **Turns** | QUESTION/ORACLE_RESPONSE | MOVEMENT/SCENE_START | ✅ No | Different types |

**Result:** ✅ NO CONTRADICTIONS

**Notes:**
- P-18 and P-19 can be used together: P-19 generates scene, then P-18 answers questions about it
- Both canonize at `canon_level=cards`, but different entity types
- Both use Narrator, but for different purposes

---

## Dependencies

### Use Case Dependencies

- **P-2: Turn Loop** - Provides turn structure and append mechanism
- **P-3: Scene Lifecycle** - Provides scene creation and context
- **P-4: Resolve Action** - Provides resolution type logic

### Layer Dependencies

- **Data-Layer:**
  - DL-1: Fact Schema (Fact entity, canon_level, evidence_refs)
  - DL-2: Turn Schema (Turn entity, turn_type, metadata)
  - DL-3: Scene Schema (Scene entity, tension_score)
  - DL-5: CanonKeeper (Fact evaluation and commitment)

- **Agents:**
  - ContextAssembly (detect_oracle_query)
  - OracleAgent (determine_likelihood, roll_percentile)
  - CanonKeeper (canonize_oracle_result)
  - NarratorAgent (describe_oracle_outcome)

### External Dependencies

- MongoDB (Fact, Turn, Scene storage)
- Neo4j (Canon fact storage)
- LLM (Narrator, OracleAgent)
- Dice system (percentile rolls)

---

## Implementation Notes

### Performance Considerations

1. **Caching:** Cache oracle results for repeated questions within same scene
2. **Async operations:** CanonKeeper evaluation is async, don't block on it
3. **Optimization:** Check existing Facts before rolling oracle

### Security Considerations

1. **Evidence tracking:** Every oracle result MUST have evidence_refs
2. **Canonization:** All oracle results go through CanonKeeper
3. **Consistency checks:** Detect contradictions between multiple oracle queries

### User Experience

1. **Clear feedback:** Player should see oracle roll and outcome
2. **Narrative integration:** Oracle outcomes should feel natural, not mechanical
3. **Tension awareness:** High tension should make oracle queries more dramatic

### Known Limitations

1. **Yes/No only:** Oracle only answers Yes/No questions, not open-ended queries
2. **Tension-based:** Oracle accuracy depends on accurate tension_score
3. **Fact conflicts:** Manual resolution required for contradictory oracle queries