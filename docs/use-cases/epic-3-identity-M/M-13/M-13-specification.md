# M-13: Create Character

**Actor:** User
**Trigger:** Create Entity → Character

**Flow:**
1. Prompt: Name
2. Prompt: Role (PC, NPC, antagonist, ally)
3. Prompt: Description
4. Select archetype (from EntityArchetype) or custom
5. IF PC or detailed NPC:
   - Create character_sheet:
     - Stats (STR, DEX, CON, INT, WIS, CHA or system-specific)
     - Resources (HP, MP, etc.)
     - Abilities
     - Equipment
6. Create EntityInstance in Neo4j
7. IF archetype: link DERIVES_FROM
8. Create character_sheet in MongoDB (if applicable)

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_archetypes(universe_id, type="character")  # Available archetypes
neo4j_create_entity(universe_id, "character", params) -> UUID
neo4j_create_relationship(entity_id, archetype_id, "DERIVES_FROM")
mongodb_create_character_sheet(entity_id, stats)
```

**Character Creation Flow:**
```python
async def create_character(universe_id: UUID) -> UUID:
    # 1. Collect basic info
    name = await prompt("Character name:")
    role = await prompt_choice("Role:", ["PC", "NPC", "antagonist", "ally"])
    description = await prompt("Description:")

    # 2. Select or skip archetype
    archetypes = await neo4j_list_archetypes(universe_id, type="character")
    archetype_id = await prompt_choice(
        "Base archetype (optional):",
        [a.name for a in archetypes] + ["Custom"]
    )

    # 3. Create entity in Neo4j
    entity_id = await neo4j_create_entity(universe_id, "character", {
        "name": name,
        "description": description,
        "properties": {
            "role": role,
            "archetype": archetype_id if archetype_id != "Custom" else None
        },
        "state_tags": ["alive"],
        "canon_level": "canon",
        "confidence": 1.0
    })

    # 4. Link to archetype if selected
    if archetype_id and archetype_id != "Custom":
        await neo4j_create_relationship(entity_id, archetype_id, "DERIVES_FROM")

    # 5. Create character sheet if PC or detailed NPC
    if role in ["PC", "NPC"]:
        stats = await prompt_character_stats()
        await mongodb_create_character_sheet(entity_id, {
            "entity_id": entity_id,
            "stats": stats,
            "resources": {
                "hp_max": calculate_hp(stats),
                "hp_current": calculate_hp(stats)
            },
            "created_at": datetime.utcnow()
        })

    return entity_id

async def prompt_character_stats() -> dict:
    """Prompt for D&D-style stats (customizable per system)."""
    stats = {}
    for stat in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        value = await prompt(f"{stat} (8-18):", validator=int_range(8, 18))
        stats[stat] = value
    return stats
```

**Database Writes:**

| Database | Node/Collection | Data |
|----------|-----------------|------|
| Neo4j | `:EntityInstance` | `{id, name, entity_type: "character", properties, state_tags}` |
| Neo4j | `[:DERIVES_FROM]` | Edge to archetype (if selected) |
| Neo4j | `[:HAS_ENTITY]` | Edge from Universe |
| MongoDB | `character_sheets` | `{entity_id, stats, resources}` |

**Layer 3 (CLI):**
```bash
monitor manage entity create --type character --universe <UUID> --name "Gandalf"
# Interactive mode walks through all prompts
```

---
