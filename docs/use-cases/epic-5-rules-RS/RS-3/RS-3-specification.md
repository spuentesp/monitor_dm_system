# RS-3: Define Character Template

**Actor:** User
**Trigger:** Manage → Rules → Character Template (within a game system)

**Purpose:** Define what a character sheet looks like for this game system.

**Flow:**
1. Select game system
2. Define character sheet sections:
   - **Core:** Name, description, portrait
   - **Attributes:** Which from system, starting values
   - **Skills:** Which are available, how many trained
   - **Resources:** HP, mana, etc.
   - **Inventory:** Slots, encumbrance rules
   - **Special:** Classes, feats, spells, moves (system-specific)
3. Define character creation rules:
   - Point buy vs rolled stats
   - Starting equipment
   - Background/origin options
4. Define advancement:
   - XP thresholds or milestone
   - What improves per level (HP, skills, features)
5. Save template to game system

**Output:** Character template attached to game system

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_character_template(system_id, params) -> template_id
mongodb_get_character_template(system_id) -> CharacterTemplate
mongodb_update_character_template(system_id, params)
```

**Layer 2 (Agents):**
- `Orchestrator.create_character_template(system_id, params)` — Create template
- `Orchestrator.apply_template(entity_id, template_id)` — Create character from template

**Layer 3 (CLI):**
```bash
monitor rules template --system <SYSTEM_ID>            # View/edit template
monitor rules template --system <SYSTEM_ID> --wizard   # Interactive setup
```

**Character Template Schema:**
```python
@dataclass
class CharacterTemplate:
    id: UUID
    system_id: UUID

    # What sections appear on sheet
    sections: list[SheetSection]

    # Character creation rules
    creation: CreationRules

    # Advancement rules
    advancement: AdvancementRules

@dataclass
class SheetSection:
    name: str                    # "Attributes", "Skills", "Inventory"
    type: SectionType            # attributes, skills, resources, inventory, custom
    fields: list[FieldDef]       # What fields in this section
    display_order: int

@dataclass
class CreationRules:
    attribute_method: str        # "point_buy", "roll_4d6_drop_lowest", "standard_array"
    starting_attribute_points: int | None
    starting_skills: int         # How many trained skills
    starting_resources: dict[str, str]  # {"HP": "constitution + 10"}
    starting_equipment: list[str] | str  # Fixed list or "choose from class"
    starting_level: int = 1

@dataclass
class AdvancementRules:
    method: str                  # "xp", "milestone", "session"
    xp_thresholds: list[int] | None  # [0, 300, 900, 2700, ...]
    per_level: PerLevelGains

@dataclass
class PerLevelGains:
    hp_formula: str              # "1d10 + constitution_modifier"
    skill_points: int            # Additional skills per level
    features: str                # "Gain 1 feat every 4 levels"
    attribute_points: str        # "+2 to one attribute every 4 levels"
```

---
