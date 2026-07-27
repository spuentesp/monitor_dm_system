# M-20: Delete Entity

**Actor:** User
**Trigger:** Entity → Delete

**Flow:**
1. Warning: affects X facts, Y relationships
2. Soft delete: canon_level = "retconned"

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_entity_stats(entity_id) -> EntityStats  # Count impacts
neo4j_soft_delete_entity(entity_id)               # Set canon_level = "retconned"
```

---
