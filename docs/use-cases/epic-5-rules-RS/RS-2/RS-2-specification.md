# RS-2: Import Game System

**Actor:** User
**Trigger:** Manage → Rules → Import

**Purpose:** Import a game system from SRD, JSON, or community format.

**Flow:**
1. Select import source:
   - **Built-in template:** D&D 5e SRD, Fate Core, PbtA, OSR
   - **JSON file:** Custom export format
   - **URL:** Community repository
2. Preview imported system:
   - Show attributes, skills, mechanics
   - Highlight any conflicts with existing systems
3. Customize before saving:
   - Rename, adjust values, remove unwanted elements
4. Save as new game system
5. Optionally mark as "official" or "homebrew"

**Output:** Imported game system ready for use

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_import_game_system(source, format) -> GameSystem
mongodb_validate_game_system(system) -> ValidationResult
```

**Layer 2 (Agents):**
- `Indexer.parse_game_system(file_path, format)` — Parse import file
- `Orchestrator.preview_import(parsed)` — Show preview

**Layer 3 (CLI):**
```bash
monitor rules import --template dnd5e              # Built-in template
monitor rules import --file ./my-system.json       # From file
monitor rules import --url https://example.com/system.json
```

**Built-in Templates:**
```python
class BuiltinTemplate(Enum):
    DND_5E_SRD = "dnd5e"           # D&D 5th Edition SRD
    DND_3_5_SRD = "dnd35"          # D&D 3.5 SRD
    PATHFINDER_1E = "pf1e"         # Pathfinder 1e
    PATHFINDER_2E = "pf2e"         # Pathfinder 2e
    FATE_CORE = "fate"             # Fate Core
    FATE_ACCELERATED = "fae"       # Fate Accelerated
    PBTA_BASIC = "pbta"            # Powered by the Apocalypse
    BLADES_ITD = "bitd"            # Blades in the Dark
    OSR_BASIC = "osr"              # Basic OSR (B/X style)
    CYPHER = "cypher"              # Cypher System
    SAVAGE_WORLDS = "sw"           # Savage Worlds
    SIMPLE_D6 = "simple"           # Minimal d6 system (default)
```

**Import Format (JSON):**
```json
{
  "name": "My Custom System",
  "version": "1.0",
  "core_mechanic": {
    "type": "d20",
    "formula": "1d20 + {skill} + {modifier}",
    "success_type": "meet_or_beat"
  },
  "attributes": [
    {"name": "Might", "abbreviation": "MGT", "max_value": 10}
  ],
  "skills": [
    {"name": "Fighting", "attribute": "MGT", "category": "combat"}
  ],
  "resources": [
    {"name": "Health", "abbreviation": "HP", "max_formula": "might * 5"}
  ]
}
```

---
