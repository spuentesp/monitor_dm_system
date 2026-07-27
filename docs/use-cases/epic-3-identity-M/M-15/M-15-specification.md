# M-15: Create Faction/Organization

**Actor:** User
**Trigger:** Create Entity → Faction

**Flow:**
1. Prompt: Name
2. Prompt: Faction type (political, military, religious, guild, cult, company)
3. Prompt: Description
4. Prompt: Scope (local, regional, global)
5. Prompt: Leadership (link to existing character or create)
6. Create EntityInstance in Neo4j

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_entity(universe_id, "faction", params) -> UUID
neo4j_create_relationship(leader_id, faction_id, "MEMBER_OF", {role: "leader"})
```

**Layer 3 (CLI):**
```bash
monitor manage entity create --type faction --universe <UUID> --name "The Fellowship"
```

---
