# M-22: Manage Memories (Characters only)

**Actor:** User
**Trigger:** Character → Memories

**Flow:**
1. Display memories sorted by importance
2. View: text, emotional_valence, certainty, linked_fact
3. Add memory:
   - Text, importance, emotional_valence
   - Link to fact (optional)
4. Edit memory (for NPCs with uncertain recall)
5. Delete memory

#### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_memories(entity_id, sort_by="importance") -> list[Memory]
mongodb_create_memory(entity_id, params) -> memory_id
mongodb_update_memory(memory_id, params)
mongodb_delete_memory(memory_id)
qdrant_upsert_memory(memory_id, text, entity_id)  # Embed for recall
```

**Layer 3 (CLI):**
```bash
monitor manage entity memory list <ENTITY_UUID>
monitor manage entity memory add <ENTITY_UUID> --text "I met the hero in Rivendell"
```

---
