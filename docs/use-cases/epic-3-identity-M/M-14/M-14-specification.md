# M-14: Create Location

**Actor:** User
**Trigger:** Create Entity → Location

**Flow:**
1. Prompt: Name
2. Prompt: Location type (city, building, region, planet, room, wilderness)
3. Prompt: Description
4. Prompt: Is exterior? (yes/no)
5. Select parent location (optional, for hierarchy)
6. Create EntityInstance in Neo4j
7. IF parent: create LOCATED_IN edge

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_entities(universe_id, type="location")  # For parent selection
neo4j_create_entity(universe_id, "location", params) -> UUID
neo4j_create_relationship(entity_id, parent_id, "LOCATED_IN")
```

**Layer 3 (CLI):**
```bash
monitor manage entity create --type location --universe <UUID> --name "Rivendell"
```

**Database Writes:**

| Database | Node/Edge | Data |
|----------|-----------|------|
| Neo4j | `:EntityInstance` | `{id, name, entity_type: "location", properties: {location_type, is_exterior}}` |
| Neo4j | `[:LOCATED_IN]` | Edge to parent location (if selected) |

---
