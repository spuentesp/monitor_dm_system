# ST-1: Plan Story Arc

**Actor:** Human GM or Autonomous GM
**Trigger:** Story → Plan Arc

**Purpose:** Design multi-session story structure with flexible outcomes.

**Flow:**
1. Define arc parameters:
   - Title and theme
   - Target length (sessions/scenes)
   - Tone and genre
   - Central conflict
2. Identify key elements:
   - **Inciting Incident:** What kicks things off
   - **Rising Actions:** Escalating complications (not fixed sequence)
   - **Crisis Points:** Decision moments for players
   - **Possible Climaxes:** Multiple valid endings
   - **Fallout Options:** Consequences of each ending
3. Assign entities:
   - Protagonist(s)
   - Antagonist(s)
   - Supporting cast
   - Locations
4. Define success/failure conditions (flexible)
5. Create arc document with milestones (not rails)
6. Save as `story_outline` in MongoDB + `PlotThread` nodes in Neo4j

**Output:** Flexible arc structure with branching possibilities

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_story_outline(story_id, arc_params)
neo4j_create_plot_thread(story_id, thread_params)  # For each thread
neo4j_link_entities_to_arc(arc_id, entity_ids)
```

**Layer 2 (Agents):**
- `Orchestrator.plan_arc(story_id, params)` — Coordinate planning
- `Narrator.generate_arc_structure(params)` — LLM arc generation
- `CanonKeeper.validate_arc(arc)` — Check consistency with canon

**Layer 3 (CLI):**
```bash
monitor story plan --story <UUID>
monitor story plan --story <UUID> --template heist
monitor story plan --story <UUID> --template mystery
```

**Arc Templates:**
```python
class ArcTemplate(Enum):
    THREE_ACT = "three_act"           # Classic structure
    HEIST = "heist"                   # Plan, execute, escape
    MYSTERY = "mystery"               # Clues, suspects, revelation
    JOURNEY = "journey"               # Travel with encounters
    SIEGE = "siege"                   # Defense against threat
    POLITICAL = "political"           # Intrigue and alliances
    DUNGEON = "dungeon"               # Exploration and combat
    CUSTOM = "custom"                 # Freeform
```

**Arc Document Structure:**
```python
@dataclass
class StoryArc:
    id: UUID
    story_id: UUID
    title: str
    theme: str
    target_sessions: int

    inciting_incident: str
    rising_actions: list[str]          # Possible complications
    crisis_points: list[CrisisPoint]   # Decision moments
    possible_climaxes: list[Climax]    # Multiple endings

    protagonists: list[UUID]
    antagonists: list[UUID]
    key_locations: list[UUID]

    milestones: list[Milestone]        # Progress markers
    current_phase: str
```

---
