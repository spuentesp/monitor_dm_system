# P-9: Dice Roll

**Actor:** Resolver
**Trigger:** Action requires dice, or `/roll` command

**Flow:**
1. Parse dice notation (see Dice Module below)
2. Execute roll
3. Apply modifiers
4. Display: formula, individual dice, total
5. IF part of action resolution:
   - Compare to DC/target
   - Determine success level
   - Apply to P-4 outcome

**Dice Notation:**
```
[N]d[S][modifier][keep]

Examples:
  d20       → roll 1d20
  2d6       → roll 2d6, sum
  1d20+5    → roll 1d20, add 5
  4d6kh3    → roll 4d6, keep highest 3
  2d20kl1   → roll 2d20, keep lowest 1 (disadvantage)
  1d20adv   → roll 2d20, keep highest (advantage)
  1d20dis   → roll 2d20, keep lowest (disadvantage)
```

### Implementation

**Layer 1 (Data Layer):**
```python
# Pure utility - no database calls
# Dice module is a standalone utility

import re
import random
from dataclasses import dataclass

@dataclass
class DiceRoll:
    formula: str
    individual_rolls: list[int]
    kept_rolls: list[int]
    modifier: int
    total: int

DICE_PATTERN = re.compile(
    r'^(\d*)d(\d+)'                    # NdS
    r'((?:[+-]\d+)*)?'                 # modifiers (+5-2)
    r'(?:k([hl])(\d+))?'               # keep highest/lowest N
    r'(?:(adv|dis))?$',                # advantage/disadvantage shorthand
    re.IGNORECASE
)

def parse_dice(formula: str) -> dict:
    """Parse dice notation into components."""
    formula = formula.lower().strip()
    match = DICE_PATTERN.match(formula)
    if not match:
        raise ValueError(f"Invalid dice notation: {formula}")

    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    mod_str = match.group(3) or ""
    keep_type = match.group(4)  # 'h' or 'l'
    keep_count = int(match.group(5)) if match.group(5) else None
    adv_dis = match.group(6)  # 'adv' or 'dis'

    # Handle advantage/disadvantage shorthand
    if adv_dis == "adv":
        count, keep_type, keep_count = 2, 'h', 1
    elif adv_dis == "dis":
        count, keep_type, keep_count = 2, 'l', 1

    # Parse modifiers
    modifier = 0
    if mod_str:
        for mod in re.findall(r'[+-]\d+', mod_str):
            modifier += int(mod)

    return {
        "count": count,
        "sides": sides,
        "modifier": modifier,
        "keep_type": keep_type,
        "keep_count": keep_count
    }

def roll_dice(formula: str) -> DiceRoll:
    """Roll dice according to notation."""
    parsed = parse_dice(formula)

    # Roll individual dice
    individual = [random.randint(1, parsed["sides"]) for _ in range(parsed["count"])]

    # Apply keep rules
    if parsed["keep_type"] == 'h' and parsed["keep_count"]:
        kept = sorted(individual, reverse=True)[:parsed["keep_count"]]
    elif parsed["keep_type"] == 'l' and parsed["keep_count"]:
        kept = sorted(individual)[:parsed["keep_count"]]
    else:
        kept = individual

    total = sum(kept) + parsed["modifier"]

    return DiceRoll(
        formula=formula,
        individual_rolls=individual,
        kept_rolls=kept,
        modifier=parsed["modifier"],
        total=total
    )
```

**Layer 2 (Agents):**
- `Resolver.roll(formula, context)` - Wraps dice utility, logs roll if in scene

**Layer 3 (CLI):**
```bash
# Standalone roll
monitor roll 2d6+5

# In-game via meta command
> /roll 1d20+7
🎲 1d20+7 → [14] + 7 = 21
```

**Display Format:**
```python
def format_roll(roll: DiceRoll) -> str:
    """Format roll for CLI display."""
    if roll.individual_rolls != roll.kept_rolls:
        # Show dropped dice
        dropped = [r for r in roll.individual_rolls if r not in roll.kept_rolls]
        dice_str = f"[{', '.join(map(str, roll.kept_rolls))}] (dropped: {dropped})"
    else:
        dice_str = f"[{', '.join(map(str, roll.individual_rolls))}]"

    if roll.modifier != 0:
        mod_str = f" {'+' if roll.modifier > 0 else ''}{roll.modifier}"
    else:
        mod_str = ""

    return f"🎲 {roll.formula} → {dice_str}{mod_str} = {roll.total}"
```

---
