# M-16: View Entity

**Actor:** User
**Trigger:** Select entity from list

**Output:**
- Basic info (name, type, description)
- Properties (type-specific)
- State tags (current status)
- Relationships (allies, enemies, members, located_in)
- Facts involving entity
- IF character: character sheet, memories

**Actions:** Edit, Manage Relationships, View Memories (if character)

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entity(entity_id) -> Entity
neo4j_get_relationships(entity_id) -> list[Relationship]
neo4j_list_facts(entity_id=entity_id) -> list[Fact]
mongodb_get_character_sheet(entity_id)  # If character
mongodb_get_memories(entity_id, limit=10)  # If character
```

**Layer 3 (CLI):**
```bash
monitor manage entity view <UUID>
monitor manage entity view --name "Gandalf" --universe <UUID>
```

---
