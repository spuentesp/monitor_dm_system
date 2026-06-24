# P-4: Resolve Action — Behavior Specification

> Verifies that actual implementation matches the behavior defined in P-4-specification.md

## Scenario 1: Action Resolution

**Given** a player has declared an action during a scene
**When** the system processes the action through the resolution flow
**Then** the action is parsed and resolved appropriately

### AC-1: Action Parsing
- [x] Action text is parsed for intent
- [x] Target entities are identified
- [x] Difficulty is calculated

### AC-2: Resolution Type Determination
- [x] Dice resolution for combat actions
- [x] Narrative resolution for trivial actions
- [x] Auto-success for trivial/easy actions
- [x] Auto-fail for impossible actions

### AC-3: Dice Rolling
- [x] Dice formula is parsed correctly
- [x] Rolls are executed with randomness
- [x] Total is calculated including modifiers
- [x] Individual die results are returned

### AC-4: Outcome Determination
- [x] CRITICAL_SUCCESS when roll exceeds DC by 10+
- [x] SUCCESS when roll meets or exceeds DC
- [x] PARTIAL when roll is 1-5 below DC
- [x] FAILURE when roll is 6-10 below DC
- [x] CRITICAL_FAILURE when roll is 10+ below DC

### AC-5: Resolution Storage
- [x] Resolution is stored in MongoDB resolutions collection
- [x] Resolution includes scene_id, turn_id, action, formula, rolls, total, outcome, dc

### AC-6: Proposal Creation
- [x] ProposedChanges are created for canon state changes
- [x] Proposals are linked to scene and action

## Scenario 2: Dice Resolution Flow

**Given** an action requiring dice resolution
**When** the player rolls for the action
**Then** dice are rolled and outcome is determined

### Acceptance Criteria
- AC-7: Dice are rolled according to formula (e.g., "1d20+5")
- AC-8: Individual die results are recorded
- AC-9: Total is calculated correctly
- AC-10: Outcome is determined based on roll vs DC

## Scenario 3: Narrative Resolution Flow

**Given** a trivial action
**When** the system evaluates the action
**Then** no dice are rolled and auto-success is returned

### Acceptance Criteria
- AC-11: Trivial actions return AUTO_SUCCESS
- AC-12: Resolution is stored without dice details

## Scenario 4: Outcome Narration

**Given** an action has been resolved
**When** the resolution is complete
**Then** the Narrator generates appropriate narration

### Acceptance Criteria
- AC-13: Outcome is narrated to player
- AC-14: Narration reflects success level
- AC-15: State changes are described in narration