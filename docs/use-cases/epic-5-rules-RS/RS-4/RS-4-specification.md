# RS-4: Override Mechanics (House Rules)

**Actor:** Human GM or User
**Trigger:** During play or Manage → Rules → Overrides

**Purpose:** Apply one-off or persistent rule modifications without changing the base system.

**Flow:**
1. Select scope:
   - **One-time:** Just this roll
   - **Scene:** For current scene only
   - **Story:** For entire story
   - **Universe:** Permanent house rule
2. Define override:
   - **Dice change:** "Roll 2d6 instead of 1d20 for social checks"
   - **Threshold change:** "DC 15 for this lock, not standard"
   - **Resource change:** "Healing potions restore 4d4, not 2d4"
   - **New rule:** "On natural 1, weapon breaks"
3. Apply override
4. Override is logged for transparency
5. Can be reverted or made permanent

**Output:** Active override applied to resolution

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_rule_override(scope, params) -> override_id
mongodb_list_rule_overrides(story_id) -> list[RuleOverride]
mongodb_delete_rule_override(override_id)
neo4j_create_axiom(universe_id, house_rule)  # For permanent rules
```

**Layer 2 (Agents):**
- `Resolver.apply_override(override)` — Use override in resolution
- `Resolver.get_effective_rules(context)` — Merge base + overrides
- `CanonKeeper.promote_override_to_axiom(override_id)` — Make permanent

**Layer 3 (CLI):**
```bash
monitor rules override --story <UUID> "Advantage on all stealth checks in darkness"
monitor rules override --scene <UUID> --temp "DC 20 for this check"
monitor rules override --list --story <UUID>   # Show active overrides
monitor rules override --remove <OVERRIDE_ID>
```

**Rule Override Schema:**
```python
@dataclass
class RuleOverride:
    id: UUID
    scope: OverrideScope          # one_time, scene, story, universe
    scope_id: UUID                # ID of scene/story/universe

    # What's being overridden
    target: OverrideTarget        # dice_formula, threshold, resource, custom
    original: str                 # What the base rule was
    override: str                 # What it's changed to

    reason: str                   # Why this override exists
    created_by: str               # "GM", "Player request", "House rule"
    created_at: datetime

    # Tracking
    times_used: int = 0
    active: bool = True

class OverrideScope(Enum):
    ONE_TIME = "one_time"         # Single use
    SCENE = "scene"               # Current scene
    STORY = "story"               # Entire story
    UNIVERSE = "universe"         # Permanent (becomes axiom)

class OverrideTarget(Enum):
    DICE_FORMULA = "dice"         # Change dice rolled
    THRESHOLD = "threshold"       # Change DC/target number
    RESOURCE = "resource"         # Change HP/damage/etc
    SKILL_CHECK = "skill"         # Change which skill applies
    CUSTOM = "custom"             # Freeform rule
```

**Override Resolution:**
```python
async def resolve_with_overrides(
    action: str,
    base_formula: str,
    context: Context
) -> Resolution:
    # 1. Get base rules from game system
    system = await mongodb_get_game_system(context.system_id)
    rules = system.core_mechanic

    # 2. Get applicable overrides (most specific wins)
    overrides = await mongodb_list_rule_overrides(
        story_id=context.story_id,
        scene_id=context.scene_id,
        active=True
    )

    # 3. Apply overrides in order (universe → story → scene → one_time)
    effective_rules = apply_overrides(rules, overrides)

    # 4. Resolve with effective rules
    result = await roll_dice(effective_rules.formula)

    # 5. Mark one-time overrides as used
    for o in overrides:
        if o.scope == OverrideScope.ONE_TIME:
            await mongodb_delete_rule_override(o.id)

    return result
```

---
