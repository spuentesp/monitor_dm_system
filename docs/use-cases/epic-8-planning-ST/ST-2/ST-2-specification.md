# ST-2: Model Faction Goals

**Actor:** Human GM
**Trigger:** Story → Factions

**Purpose:** Define what factions want and how they'll pursue it, creating emergent conflict.

**Flow:**
1. Select or create factions involved in story
2. For each faction, define:
   - **Primary Goal:** What they ultimately want
   - **Secondary Goals:** Stepping stones
   - **Methods:** How they pursue goals (violence, diplomacy, subterfuge)
   - **Resources:** What they can deploy
   - **Constraints:** Lines they won't cross
   - **Relationships:** Allies, enemies, neutral
3. System identifies:
   - **Conflict Points:** Where goals clash
   - **Alliance Opportunities:** Where goals align
   - **Pressure Points:** What threatens each faction
4. Optionally simulate faction actions between sessions
5. Save faction states and update relationships

**Output:** Faction goal map with conflict/alliance analysis

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entity(faction_id)                       # Faction data
neo4j_list_facts(entity_id=faction_id, type="goal")  # Current goals
neo4j_create_fact(faction_id, type="goal", content)  # New goal
neo4j_create_relationship(faction_a, faction_b, type)  # Alliances/enmities
neo4j_update_entity(faction_id, properties)        # Update state
```

**Layer 2 (Agents):**
- `ContextAssembly.get_faction_context(faction_ids)` — Compile faction data
- `Narrator.analyze_faction_dynamics(factions)` — Find conflicts
- `Resolver.simulate_faction_turn(faction, context)` — Off-screen actions

**Layer 3 (CLI):**
```bash
monitor story factions --story <UUID>
monitor story factions --story <UUID> --add <FACTION_ID>
monitor story factions --story <UUID> --simulate
```

**Faction Goal Schema:**
```python
@dataclass
class FactionGoal:
    faction_id: UUID
    goal_type: GoalType  # survival, power, wealth, ideology, revenge, protection
    description: str
    priority: int        # 1-5
    methods: list[str]   # violence, diplomacy, subterfuge, commerce
    deadline: str | None # If time-sensitive

@dataclass
class FactionState:
    faction_id: UUID
    goals: list[FactionGoal]
    resources: dict[str, int]  # gold, soldiers, influence, etc.
    relationships: dict[UUID, RelationType]
    current_actions: list[str]  # What they're doing this "turn"
```

---
