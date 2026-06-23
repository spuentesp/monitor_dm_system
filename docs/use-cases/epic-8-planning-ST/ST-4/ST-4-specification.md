# ST-4: Design Mystery Structure

**Actor:** Human GM
**Trigger:** Story → Mystery (or during arc planning)

**Purpose:** Create solvable mysteries with multiple valid investigation paths.

**Flow:**
1. Define the mystery:
   - **The Truth:** What actually happened (GM secret)
   - **The Question:** What players are trying to discover
   - **The Stakes:** Why it matters
2. Design clue structure:
   - **Core Clues:** Must-find clues that point to truth
   - **Bonus Clues:** Shortcuts or confirmations
   - **Red Herrings:** Misleading information (optional)
   - **Floating Clues:** Can be found in multiple locations
3. Place clues:
   - Assign to locations, NPCs, objects
   - Define discovery conditions (investigation, social, combat)
   - Ensure multiple paths to each core clue
4. Define suspects/theories:
   - Plausible alternatives
   - Evidence for/against each
5. Track player discoveries during play
6. Validate solvability (three-clue rule: any core clue findable 3 ways)

**Output:** Mystery structure with clue placement

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_story_outline(story_id, mystery_structure)
neo4j_create_fact(clue_fact, visibility="hidden")  # Hidden until found
neo4j_link_evidence(clue_id, location_id)          # Clue placement
neo4j_update_fact(clue_id, visibility="revealed")  # When discovered
```

**Layer 2 (Agents):**
- `Narrator.design_mystery(params)` — Generate structure
- `Narrator.validate_solvability(mystery)` — Check three-clue rule
- `ContextAssembly.track_discoveries(scene_id)` — What players found

**Layer 3 (CLI):**
```bash
monitor story mystery --story <UUID>
monitor story mystery --story <UUID> --validate
monitor story mystery --story <UUID> --status  # What players know
```

**Mystery Structure:**
```python
@dataclass
class Mystery:
    id: UUID
    story_id: UUID

    truth: str                        # What actually happened (GM only)
    question: str                     # What players seek to answer
    stakes: str                       # Why it matters

    core_clues: list[Clue]           # Required for solution
    bonus_clues: list[Clue]          # Helpful but optional
    red_herrings: list[Clue]         # Misleading
    floating_clues: list[Clue]       # Can appear anywhere

    suspects: list[Suspect]          # Alternative theories

    discovered_clues: list[UUID]     # Player progress
    current_theories: list[str]      # What players think

@dataclass
class Clue:
    id: UUID
    content: str                     # What the clue reveals
    locations: list[UUID]            # Where it can be found
    discovery_methods: list[str]     # How to find it (investigate, talk, search)
    points_to: str                   # What conclusion it supports
    is_discovered: bool
```

---
