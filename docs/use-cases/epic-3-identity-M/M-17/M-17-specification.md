# M-17: Create Object

**Actor:** User
**Trigger:** Create Entity → Object

**Flow:**
1. Prompt: Name
2. Prompt: Object type (weapon, armor, artifact, tool, consumable, treasure)
3. Prompt: Description
4. Prompt: Is magical? Is unique?
5. Prompt: Owner (link to character, optional)
6. Create EntityInstance in Neo4j

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_entity(universe_id, "object", params) -> UUID
neo4j_create_relationship(owner_id, object_id, "OWNS")  # If owner set
```

---
