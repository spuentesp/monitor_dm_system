# M-19: Edit Entity

**Actor:** User
**Trigger:** Entity → Edit

**Flow:**
1. Display current values
2. Edit: name, description, properties, state_tags
3. Create ProposedChange (for canonization tracking)
4. Update Neo4j (or queue for CanonKeeper)

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entity(entity_id) -> Entity
neo4j_update_entity(entity_id, params)  # Direct update (GM authority)
# OR
mongodb_create_proposal(scene_id, {type: "entity_update", ...})  # Queue for canonization
```

**Layer 3 (CLI):**
```bash
monitor manage entity edit <UUID> --name "New Name"
monitor manage entity edit <UUID> --add-tag wounded --remove-tag healthy
```

---
