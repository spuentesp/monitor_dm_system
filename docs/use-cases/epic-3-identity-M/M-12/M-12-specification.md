# M-12: Create Entity

**Actor:** User
**Trigger:** Manage → Entities → Create

**Flow:**
1. Select universe
2. Select entity type:
   - Character → M-13
   - Location → M-14
   - Faction → M-15
   - Object → M-17
   - Concept → M-18
   - Organization → M-15 (same as faction)
3. Route to type-specific flow

#### Implementation

**Layer 1 (Data Layer):**
```python
# Generic entity creation (used by all type-specific handlers)
neo4j_create_entity(universe_id, entity_type, params) -> UUID
```

**Entity Type Router:**
```python
ENTITY_HANDLERS = {
    EntityType.CHARACTER: create_character,    # M-13
    EntityType.LOCATION: create_location,      # M-14
    EntityType.FACTION: create_faction,        # M-15
    EntityType.OBJECT: create_object,          # M-17
    EntityType.CONCEPT: create_concept,        # M-18
    EntityType.ORGANIZATION: create_faction,   # Same as faction
}

async def create_entity(universe_id: UUID, entity_type: EntityType) -> UUID:
    handler = ENTITY_HANDLERS[entity_type]
    return await handler(universe_id)
```

**Layer 3 (CLI):**
```bash
monitor manage entity create --universe <UUID> --type character
# Or interactive: monitor manage entity create
```

---
