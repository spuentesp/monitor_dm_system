# M-18: Create Concept

**Actor:** User
**Trigger:** Create Entity → Concept

**Flow:**
1. Prompt: Name (e.g., "The Force", "Magic System", "Divine Law")
2. Prompt: Concept type (belief, law, force, system)
3. Prompt: Description
4. Prompt: Is abstract?
5. Create EntityInstance in Neo4j

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_entity(universe_id, "concept", params) -> UUID
```

---
