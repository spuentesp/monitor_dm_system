# CF-6: Generate Player Handouts

**Actor:** Human GM
**Trigger:** Co-Pilot → Handouts

**Purpose:** Create summaries and reference documents for players based on what their characters know.

**Flow:**

1. **Select Scope:**
   - Specific character (what they know)
   - Party (shared knowledge)
   - Story so far (campaign summary)
   - Location (travel guide)
   - NPC (relationship summary)

2. **Configure Handout:**
   - Perspective: In-character vs out-of-character
   - Detail level: Brief, standard, detailed
   - Include/exclude: Secrets, rumors, speculation
   - Format: Prose, bullet points, table

3. **Generate Handout:**
   - System gathers relevant facts, memories, scenes
   - Filters by character knowledge (what PC has witnessed)
   - Excludes GM-only information
   - Generates formatted output

4. **Review & Export:**
   - GM reviews and edits
   - Export as Markdown, PDF, or image
   - Optionally save to story documents

**Handout Types:**

| Type | Contents | Use Case |
|------|----------|----------|
| Session Recap | What happened last session | Remind players |
| Character Dossier | What PC knows about NPC | Investigation |
| Location Guide | Known facts about place | Exploration |
| Quest Log | Active plot threads from PC perspective | Tracking |
| Lore Summary | World knowledge PC has learned | Reference |
| Relationship Map | Known relationships between NPCs | Intrigue |

### Implementation

**Layer 1 (Data Layer):**
```python
# Gather character knowledge
neo4j_list_facts(entity_ids=[character_id], witnessed_by=character_id)
mongodb_list_memories(entity_id=character_id, importance_min=0.5)
mongodb_list_scenes(participant_ids=[character_id])
neo4j_list_relationships(entity_id=character_id, known=True)
```

**Layer 2 (Agents):**
- `ContextAssembly.get_character_knowledge(character_id)` — What PC knows
- `Narrator.generate_handout(knowledge, format, style)` — Create prose
- `Narrator.format_as_table(knowledge, columns)` — Create structured output

**Layer 3 (CLI):**
```bash
monitor copilot handout --character <UUID> --type recap
monitor copilot handout --party --type quest_log
monitor copilot handout --location <UUID> --format markdown
monitor copilot handout --npc <UUID> --perspective in_character
```

**Handout Schema:**
```python
@dataclass
class Handout:
    id: UUID
    story_id: UUID
    title: str
    handout_type: HandoutType
    perspective: Perspective  # in_character, out_of_character
    scope_entity_id: UUID | None  # Character, location, NPC

    content: str
    format: Format  # prose, bullets, table, mixed

    includes_secrets: bool
    includes_rumors: bool

    created_at: datetime
    exported_at: datetime | None

class HandoutType(Enum):
    SESSION_RECAP = "session_recap"
    CHARACTER_DOSSIER = "character_dossier"
    LOCATION_GUIDE = "location_guide"
    QUEST_LOG = "quest_log"
    LORE_SUMMARY = "lore_summary"
    RELATIONSHIP_MAP = "relationship_map"
    CUSTOM = "custom"
```

---
