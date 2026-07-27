# Q-8: Compare Entities

**Actor:** User
**Trigger:** Query → Compare

**Flow:**
1. Select two or more entities
2. Display side-by-side:
   - Properties
   - Stats (if characters)
   - Relationships to each other
   - Common facts

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entities(entity_ids) -> list[Entity]
neo4j_get_shared_facts(entity_ids) -> list[Fact]
neo4j_get_mutual_relationships(entity_ids) -> list[Relationship]
mongodb_get_character_sheets(entity_ids) -> list[CharacterSheet]
```

**Comparison Logic:**
```python
async def compare_entities(entity_ids: list[UUID]) -> Comparison:
    # 1. Get all entities
    entities = await neo4j_get_entities(entity_ids)

    # 2. Get shared facts
    shared_facts = await neo4j_get_shared_facts(entity_ids)

    # 3. Get mutual relationships
    mutual_rels = await neo4j_get_mutual_relationships(entity_ids)

    # 4. Get character sheets if applicable
    sheets = {}
    character_ids = [e.id for e in entities if e.entity_type == "character"]
    if character_ids:
        sheets = await mongodb_get_character_sheets(character_ids)

    return Comparison(
        entities=entities,
        shared_facts=shared_facts,
        mutual_relationships=mutual_rels,
        character_sheets=sheets
    )
```

**Layer 3 (CLI):**
```bash
monitor query compare <UUID1> <UUID2>
monitor query compare --names "Gandalf" "Saruman" --universe <UUID>
```

---
