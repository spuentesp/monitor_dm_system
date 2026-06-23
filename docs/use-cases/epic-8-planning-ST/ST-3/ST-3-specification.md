# ST-3: Simulate "What If" Scenarios

**Actor:** Human GM
**Trigger:** Story → What If

**Purpose:** Explore hypothetical outcomes without affecting canon.

**Flow:**
1. Define scenario:
   - Starting point (current state or past event)
   - Hypothetical change ("What if the king died?")
2. System creates sandbox copy of relevant state
3. Simulate forward:
   - Faction reactions
   - NPC responses
   - Cascade effects
   - Timeline of consequences
4. Present results:
   - Immediate effects (hours/days)
   - Short-term effects (weeks)
   - Long-term effects (months/years)
5. GM can:
   - Dismiss (just exploration)
   - Adopt as canon (make it happen)
   - Save as alternate timeline
   - Use for planning (incorporate elements)

**Output:** Simulated consequence chain (non-canonical unless adopted)

### Implementation

**Layer 1 (Data Layer):**
```python
# Read-only queries (simulation doesn't write to main DB)
neo4j_get_universe(universe_id)
neo4j_list_entities(universe_id)
neo4j_list_facts(universe_id)
neo4j_list_relationships(entity_ids)

# Only if adopted:
neo4j_create_event(adopted_event)
neo4j_create_fact(consequence)
```

**Layer 2 (Agents):**
- `ContextAssembly.snapshot_state(universe_id)` — Copy current state
- `Narrator.simulate_consequences(change, state, depth)` — LLM simulation
- `CanonKeeper.adopt_simulation(simulation_id)` — Make canonical

**Layer 3 (CLI):**
```bash
monitor story whatif --universe <UUID> --change "The king is assassinated"
monitor story whatif --story <UUID> --change "The party fails the heist"
monitor story whatif --adopt <SIMULATION_ID>  # Make it canon
```

**Simulation Prompt:**
```python
WHATIF_PROMPT = """
Given this world state, simulate the consequences of: {change}

Current state:
- Factions: {factions}
- Key NPCs: {npcs}
- Recent events: {recent_events}
- Active tensions: {tensions}

Simulate:
1. Immediate reactions (hours): Who does what?
2. Short-term effects (days/weeks): How does the situation evolve?
3. Long-term effects (months): What's the new equilibrium?

For each effect, identify:
- Who is affected
- What changes
- What new conflicts emerge
- What opportunities arise
"""
```

**Simulation Result:**
```python
@dataclass
class Simulation:
    id: UUID
    universe_id: UUID
    starting_point: str  # Description or event_id
    hypothetical_change: str

    immediate_effects: list[Effect]   # Hours
    shortterm_effects: list[Effect]   # Days/weeks
    longterm_effects: list[Effect]    # Months/years

    affected_entities: list[UUID]
    new_conflicts: list[str]
    opportunities: list[str]

    status: SimulationStatus  # sandbox, adopted, dismissed
```

---
