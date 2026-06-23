# P-4: Resolve Action

**Actor:** User
**Trigger:** User declares action ("I attack", "I pick the lock", "I climb")

**Flow:**
1. Parse action intent
2. Identify target entities, difficulty
3. Determine resolution type:
   - **Dice:** Roll required (combat, skill checks)
   - **Narrative:** GM decides (trivial actions)
   - **Deterministic:** Auto-success/fail (impossible/guaranteed)
4. IF dice:
   - Calculate difficulty (DC)
   - → P-9 (Dice roll)
   - Determine success level
5. Create ProposedChanges (state changes, damage, etc.)
6. Narrator describes outcome
7. Return to P-3

**Outcomes:** critical_success, success, partial, failure, critical_failure

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_get_entity(target_id)               # Get target entity state
dice_roll(formula) -> DiceRoll            # Roll dice (P-9)
mongodb_create_resolution(params)         # Store resolution result
mongodb_create_proposal(scene_id, ...)    # Propose state changes
```

**Layer 2 (Agents):**
- `Resolver.resolve_action(action, context)` - Main resolution logic
- `Resolver.evaluate_difficulty(action, context)` - Calculate DC
- `Resolver.determine_effects(action, result)` - Compute state changes
- `Narrator.describe_action_result(action, resolution)` - Narrate outcome

**Resolution Logic:**
```python
class ResolutionType(Enum):
    DICE = "dice"           # Requires roll
    NARRATIVE = "narrative" # GM decides
    AUTO_SUCCESS = "auto_success"
    AUTO_FAIL = "auto_fail"

def determine_resolution_type(action: str, context: Context) -> ResolutionType:
    # Combat actions always need dice
    if is_combat_action(action):
        return ResolutionType.DICE

    # Trivial actions auto-succeed
    if is_trivial(action, context):
        return ResolutionType.AUTO_SUCCESS

    # Impossible actions auto-fail
    if is_impossible(action, context):
        return ResolutionType.AUTO_FAIL

    # Skill checks need dice
    return ResolutionType.DICE

def calculate_dc(action: str, context: Context) -> int:
    """Standard D&D-style DCs: 5 trivial, 10 easy, 15 medium, 20 hard, 25 very hard, 30 nearly impossible"""
    base_dc = 10
    # Adjust based on circumstances
    return base_dc + modifiers
```

**Database Writes:**

| Database | Collection | Data |
|----------|------------|------|
| MongoDB | `resolutions` | `{id, scene_id, turn_id, action, formula, rolls, total, outcome, dc}` |
| MongoDB | `proposed_changes` | `{scene_id, type: "state_change", content: {entity_id, tag, action}}` |

**Outcome Mapping:**
```python
def determine_outcome(roll: int, dc: int) -> Outcome:
    diff = roll - dc
    if diff >= 10:
        return Outcome.CRITICAL_SUCCESS
    elif diff >= 0:
        return Outcome.SUCCESS
    elif diff >= -5:
        return Outcome.PARTIAL
    elif diff >= -10:
        return Outcome.FAILURE
    else:
        return Outcome.CRITICAL_FAILURE
```

---
