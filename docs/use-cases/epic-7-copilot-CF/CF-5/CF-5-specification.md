# CF-5: Detect Contradictions

**Actor:** Human GM
**Trigger:** Co-Pilot → Validate (manual) or automatic during canonization

**Purpose:** Find and flag contradictory facts introduced accidentally.

**Flow:**
1. Scope selection:
   - Current scene only
   - Current story
   - Entire universe
2. Analyze all canonical facts for conflicts:
   - **Direct contradictions:** "X is dead" vs "X spoke to party"
   - **Timeline violations:** Event B before Event A (but B depends on A)
   - **Location conflicts:** Entity in two places at same time
   - **Relationship conflicts:** "X hates Y" vs "X is Y's ally"
   - **Rule violations:** Actions that break established axioms
3. For each conflict:
   - Show both facts with sources
   - Suggest resolution options:
     - Retcon older fact
     - Retcon newer fact
     - Mark as "apparent contradiction" (mystery)
     - Create explanation fact
4. GM resolves each conflict
5. Update canon accordingly

**Output:** Conflict report with resolution options

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_facts(universe_id)                      # All facts
neo4j_list_events(universe_id)                     # All events
neo4j_get_entity(entity_id)                        # Entity states
neo4j_retcon_fact(fact_id)                         # Apply retcon
neo4j_create_fact(explanation)                     # Add explanation
```

**Layer 2 (Agents):**
- `CanonKeeper.validate_consistency(scope)` — Run validation
- `CanonKeeper.suggest_resolution(conflict)` — Generate options
- `CanonKeeper.apply_resolution(conflict, choice)` — Execute fix

**Layer 3 (CLI):**
```bash
monitor copilot validate --universe <UUID>
monitor copilot validate --story <UUID>
monitor copilot validate --scene <UUID>
```

**Conflict Detection Logic:**
```python
async def detect_contradictions(facts: list[Fact]) -> list[Conflict]:
    conflicts = []

    # 1. State contradictions (same entity, conflicting states)
    for entity_id in unique_entities(facts):
        entity_facts = [f for f in facts if f.subject_id == entity_id]
        conflicts.extend(find_state_conflicts(entity_facts))

    # 2. Timeline contradictions
    events = await neo4j_list_events(universe_id)
    conflicts.extend(validate_timeline(events))

    # 3. Location contradictions
    conflicts.extend(validate_locations(facts, events))

    # 4. Semantic contradictions (LLM-assisted)
    conflicts.extend(await llm_find_contradictions(facts))

    return conflicts
```

**Conflict Schema:**
```python
@dataclass
class Conflict:
    type: ConflictType
    fact_a: Fact
    fact_b: Fact
    description: str
    severity: Severity  # critical, major, minor
    suggested_resolutions: list[Resolution]
```

---
