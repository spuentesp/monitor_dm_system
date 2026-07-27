# M-31: Entity Templates

**Actor:** User (GM/World Designer)
**Trigger:** Manage → Templates, or during entity creation

**Purpose:** Create reusable entity templates for efficient world-building and consistent entity generation.

**Flow:**

1. **Create Template:**
   - Base on existing entity OR create from scratch
   - Define fixed properties (type, base description)
   - Define variable properties (name patterns, stat ranges)
   - Define randomization rules

2. **Configure Template:**
   - Property overrides
   - Naming patterns ("$ADJECTIVE Guard", "Orc #$N")
   - Stat generation rules ("3d6 for STR", "roll on table")
   - Equipment loadout options
   - State tag defaults

3. **Use Template:**
   - Instantiate single entity
   - Bulk generate N entities
   - Quick-spawn during scene (`/spawn "Orc" 3`)

4. **Template Inheritance:**
   - Templates can derive from other templates
   - Override specific properties
   - Chain: "Elite Orc" → "Orc Warrior" → "Orc" → "Humanoid"

#### Implementation

**Layer 1 (Data Layer):**
```python
# Template CRUD (MongoDB)
mongodb_create_entity_template(universe_id, params) -> template_id
mongodb_get_entity_template(template_id) -> EntityTemplate
mongodb_list_entity_templates(universe_id, entity_type=None) -> list[TemplateSummary]
mongodb_update_entity_template(template_id, params)
mongodb_delete_entity_template(template_id)

# Template instantiation
mongodb_instantiate_template(template_id, overrides={}) -> entity_params
mongodb_bulk_instantiate_template(template_id, count, overrides={}) -> list[entity_params]

# Actual entity creation
neo4j_create_entity(universe_id, entity_type, params)
```

**Layer 2 (Agents):**
- `Orchestrator.create_template_from_entity(entity_id)` — Generate template from existing
- `Orchestrator.instantiate_template(template_id, overrides)` — Create entity from template
- `Orchestrator.bulk_spawn(template_id, count, location_id)` — Mass creation
- `Narrator.generate_template_variation(template, seed)` — Add unique flavor

**Layer 3 (CLI):**
```bash
# Template management
monitor manage template create --from-entity <UUID> --name "Generic Guard"
monitor manage template list --universe <UUID>
monitor manage template view <TEMPLATE_ID>
monitor manage template edit <TEMPLATE_ID>

# Template instantiation
monitor manage entity create --template "Generic Guard" --name "Bob"
monitor manage entity spawn --template "Orc Warrior" --count 5 --location <UUID>

# Quick spawn during play (meta command)
> /spawn "Orc Warrior" 3
```

**Template Schema:**
```python
@dataclass
class EntityTemplate:
    id: UUID
    universe_id: UUID
    name: str
    description: str

    entity_type: EntityType
    base_properties: dict

    variable_properties: list[VariableProperty]
    naming_pattern: NamingPattern
    stat_generation: StatGeneration | None

    default_state_tags: list[str]
    equipment_options: list[EquipmentOption] | None

    parent_template_id: UUID | None  # Inheritance

    usage_count: int
    created_at: datetime
    updated_at: datetime

class GenerationType(Enum):
    FIXED = "fixed"        # Always the same
    CHOICE = "choice"      # Random from list
    RANGE = "range"        # Random number in range
    PATTERN = "pattern"    # Text pattern
    TABLE = "table"        # Roll on random table
    LLM = "llm"            # Generate with AI
```

**Database Writes:**

| Database | Collection | Data |
|----------|------------|------|
| MongoDB | `entity_templates` | Template definitions |
| Neo4j | `:EntityInstance` | Instantiated entities |
| Neo4j | `[:INSTANTIATED_FROM]` | Optional link to template |

---
