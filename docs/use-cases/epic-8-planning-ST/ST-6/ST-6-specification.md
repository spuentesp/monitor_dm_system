# ST-6: Generate Random Encounters

**Actor:** Human GM or System (automatic during travel)
**Trigger:** Story → Encounters, or automatic during time passage

**Purpose:** Procedurally generate context-appropriate encounters using world state and random tables.

**Flow:**

1. **Trigger Encounter:**
   - Manual: GM requests encounter
   - Automatic: During travel, rest, or time passage
   - Roll chance based on location danger level

2. **Determine Parameters:**
   - Location type (wilderness, urban, dungeon)
   - Time of day
   - Party level/strength
   - Recent events (faction activity, weather)
   - Story context (active threats, nearby NPCs)

3. **Generate Encounter:**
   - Roll on appropriate random table (M-33)
   - Or use LLM generation with context
   - Adjust difficulty based on party

4. **Flesh Out Details:**
   - Generate NPC names/traits if needed
   - Determine NPC motivations
   - Set terrain/environmental factors
   - Create tactical situation

5. **Present Options:**
   - Combat encounter
   - Social encounter
   - Environmental challenge
   - Discovery/lore reveal
   - Nothing (false alarm)

### Implementation

**Layer 1 (Data Layer):**
```python
# Random tables
mongodb_roll_on_table(table_id) -> RollResult
mongodb_list_random_tables(universe_id, table_type="encounter")

# Context gathering
neo4j_list_entities(location_id, type="character", role="npc")
neo4j_list_facts(location_id, type="threat")
neo4j_get_entity(location_id)  # Location properties
```

**Layer 2 (Agents):**
- `Resolver.check_random_encounter(context)` — Roll for encounter
- `Narrator.generate_encounter(params, context)` — Create encounter details
- `Orchestrator.trigger_encounter(encounter)` — Start encounter scene

**Layer 3 (CLI):**
```bash
monitor story encounter --story <UUID>
monitor story encounter --story <UUID> --type combat
monitor story encounter --story <UUID> --difficulty hard
monitor story encounter --story <UUID> --table <TABLE_ID>

# In play REPL
> /encounter
> /encounter social
```

**Encounter Schema:**
```python
@dataclass
class Encounter:
    id: UUID
    story_id: UUID
    location_id: UUID

    encounter_type: EncounterType  # combat, social, environmental, discovery
    difficulty: Difficulty  # trivial, easy, medium, hard, deadly
    source: EncounterSource  # table_roll, llm_generated, manual

    title: str
    description: str

    participants: list[EncounterParticipant]
    terrain: TerrainDescription | None
    environmental_factors: list[str]

    motivations: dict[UUID, str]  # NPC motivations
    potential_outcomes: list[str]

    table_id: UUID | None  # If from random table
    roll_result: int | None

class EncounterType(Enum):
    COMBAT = "combat"
    SOCIAL = "social"
    ENVIRONMENTAL = "environmental"
    DISCOVERY = "discovery"
    PUZZLE = "puzzle"
    CHASE = "chase"
    MIXED = "mixed"

@dataclass
class EncounterParticipant:
    entity_id: UUID | None  # Existing entity or None for new
    name: str
    role: str  # enemy, neutral, ally, environmental
    template_id: UUID | None  # For spawning from template
    count: int  # Number of this type
```

**Encounter Generation Prompt:**
```python
ENCOUNTER_PROMPT = """
Generate a {encounter_type} encounter for this situation:

Location: {location_description}
Time: {time_of_day}
Weather: {weather}
Party: {party_summary}
Recent Events: {recent_events}
Active Threats: {active_threats}

Requirements:
- Difficulty: {difficulty}
- Should fit the narrative context
- Include clear motivations for NPCs
- Provide multiple resolution paths

Generate:
1. Encounter title and brief description
2. Participants and their goals
3. Environmental factors
4. 2-3 potential outcomes
"""
```

---
