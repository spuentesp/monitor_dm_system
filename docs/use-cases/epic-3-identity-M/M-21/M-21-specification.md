# M-21: Manage Relationships

**Actor:** User
**Trigger:** Entity → Relationships

**Flow:**
1. Display current relationships:
   - ALLY_OF, ENEMY_OF
   - MEMBER_OF, LOCATED_IN
   - OWNS, DERIVES_FROM
2. Add relationship:
   - Select target entity
   - Select relationship type
   - Create edge in Neo4j
3. Remove relationship:
   - Mark edge as retconned

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_relationships(entity_id) -> list[Relationship]
neo4j_create_relationship(from_id, to_id, type, properties={})
neo4j_delete_relationship(relationship_id)  # Soft delete
```

**Relationship Types:**
```python
RELATIONSHIP_TYPES = [
    "ALLY_OF",      # Symmetric
    "ENEMY_OF",     # Symmetric
    "MEMBER_OF",    # Asymmetric (entity → group)
    "LOCATED_IN",   # Asymmetric (entity → location)
    "OWNS",         # Asymmetric (owner → object)
    "DERIVES_FROM", # Asymmetric (concrete → axiom)
]
```

**Layer 3 (CLI):**
```bash
monitor manage entity relationship add <FROM_UUID> <TO_UUID> --type ALLY_OF
monitor manage entity relationship remove <RELATIONSHIP_UUID>
```

---
