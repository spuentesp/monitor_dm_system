# RS-8: Bind Rules Source to World / Session

**Actor:** User
**Trigger:** World setup, Pack apply flow, or Play session bootstrap

**Purpose:** Explicitly bind a playable world/session to the authoritative tabletop rules source, whether that source is a reusable **generic library system** or a **pack-embedded/internal system** carried by a knowledge pack.

**Flow:**
1. User selects a world, pack, or generic system during setup
2. MONITOR resolves the rules source as one of:
   - `generic_library` → `game_systems.system_id`
   - `pack_embedded` → `KnowledgePack.game_system_data` / `pack_id`
   - `narrative_only` → no structured mechanics bound
3. The world/session stores:
   - source type
   - source id
   - human-readable system name
   - optional `game_system_id` when a reusable library system is also present
4. Play bootstrap and character creation use that bound source without guessing or silently switching systems

**Output:** Stable, provenance-aware rules binding for runtime play.

### Implementation
- World/session metadata stores `default_system_source_type`, `default_system_source_id`, `default_system_name`
- Chat/play bootstrap resolves pack-embedded systems before falling back to generic-library lookup
- Depends on I-11 and DL-20

---

# Dice Module Specification

## Notation

```
[count]d[sides][modifiers][keep]

Components:
  count    = number of dice (default 1)
  sides    = die type (4, 6, 8, 10, 12, 20, 100)
  modifier = +N or -N
  keep     = kh[N] (keep highest N) or kl[N] (keep lowest N)
```

## Examples

| Notation | Description |
|----------|-------------|
| `d20` | Roll 1d20 |
| `2d6` | Roll 2d6, sum |
| `1d20+5` | Roll 1d20, add 5 |
| `4d6kh3` | Roll 4d6, keep highest 3 (stat generation) |
| `2d20kh1` | Roll 2d20, keep highest (advantage) |
| `2d20kl1` | Roll 2d20, keep lowest (disadvantage) |
| `1d20adv` | Shorthand for advantage |
| `1d20dis` | Shorthand for disadvantage |
| `8d6` | Roll 8d6 (fireball damage) |
| `1d20+5+2` | Multiple modifiers |

## Implementation

```python
@dataclass
class DiceRoll:
    formula: str
    individual_rolls: list[int]
    kept_rolls: list[int]
    modifier: int
    total: int

def roll_dice(formula: str) -> DiceRoll:
    # 1. Parse formula
    # 2. Roll individual dice
    # 3. Apply keep rules
    # 4. Apply modifiers
    # 5. Return result
```

---
