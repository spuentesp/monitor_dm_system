# RS-1: Define Game System

**Actor:** User
**Trigger:** Manage → Rules → Create System

**Purpose:** Create a reusable game system definition (stats, skills, dice mechanics).

**Flow:**
1. Basic system info:
   - Name (e.g., "D&D 5e", "Fate Core", "Homebrew Fantasy")
   - Description
   - Core mechanic summary ("d20 + modifier vs DC")
2. Define attributes/stats:
   - Name, abbreviation, range (e.g., "Strength", "STR", 1-20)
   - How they're used (modifier = (stat - 10) / 2)
3. Define skills:
   - Name, linked attribute, trained/untrained bonus
   - Categories (combat, social, exploration)
4. Define dice mechanics:
   - Base resolution formula (e.g., "1d20 + skill + modifier")
   - Success thresholds (meet-or-beat, count successes, etc.)
   - Critical success/failure rules
5. Define resource types:
   - HP, Mana, Stress, Fate Points, etc.
   - Max, current, recovery rules
6. Save game system
7. System becomes available for universe/character creation

**Output:** Reusable game system definition

### Implementation

**Layer 1 (Data Layer):**
```python
# Store in MongoDB (complex, document-oriented)
mongodb_create_game_system(params) -> system_id
mongodb_get_game_system(system_id) -> GameSystem
mongodb_list_game_systems() -> list[GameSystemSummary]
mongodb_update_game_system(system_id, params)
mongodb_delete_game_system(system_id)
```

**Layer 2 (Agents):**
- `Orchestrator.create_game_system(params)` — Coordinate creation
- `Resolver.load_game_system(system_id)` — Load for resolution

**Layer 3 (CLI):**
```bash
monitor rules create                             # Interactive wizard
monitor rules create --name "D&D 5e" --template dnd5e
monitor rules list                               # Show all systems
monitor rules view <SYSTEM_ID>                   # View details
monitor rules edit <SYSTEM_ID>                   # Modify system
```

**Game System Schema:**
```python
@dataclass
class GameSystem:
    id: UUID
    name: str
    description: str
    version: str = "1.0"

    # Core resolution mechanic
    core_mechanic: CoreMechanic

    # Attributes (Strength, Dexterity, etc.)
    attributes: list[AttributeDef]

    # Skills (Athletics, Persuasion, etc.)
    skills: list[SkillDef]

    # Resources (HP, Mana, etc.)
    resources: list[ResourceDef]

    # Combat rules
    combat: CombatRules | None

    # Custom dice notation extensions
    custom_dice: dict[str, str] = {}  # {"advantage": "2d20kh1"}

@dataclass
class CoreMechanic:
    type: MechanicType  # d20, dice_pool, percentile, card, narrative
    formula: str        # "1d20 + {skill} + {modifier}"
    success_type: SuccessType  # meet_or_beat, count_successes, highest_wins

    success_threshold: str | None  # "DC" or fixed number
    critical_success: str | None   # "natural 20" or "double threshold"
    critical_failure: str | None   # "natural 1"
    partial_success: str | None    # "within 5 of DC"

@dataclass
class AttributeDef:
    name: str                # "Strength"
    abbreviation: str        # "STR"
    min_value: int = 1
    max_value: int = 20
    default_value: int = 10
    modifier_formula: str | None = "(value - 10) // 2"  # How to derive modifier

@dataclass
class SkillDef:
    name: str                # "Athletics"
    attribute: str           # "STR" - linked attribute
    category: str            # "physical", "mental", "social"
    trained_bonus: int = 0   # Bonus if trained
    description: str = ""

@dataclass
class ResourceDef:
    name: str                # "Hit Points"
    abbreviation: str        # "HP"
    max_formula: str         # "constitution * level + 10"
    recovery_rules: str      # "Long rest: full. Short rest: spend hit dice."
    depleted_effect: str     # "At 0: unconscious. Below 0: death saves."
```

---
