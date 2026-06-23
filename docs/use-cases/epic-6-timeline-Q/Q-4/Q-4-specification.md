# Q-4: Explore Facts

**Actor:** User
**Trigger:** Query → Facts

**Flow:**
1. Select universe
2. Filter by:
   - Entity (facts involving X)
   - Authority (source, gm, player, system)
   - Canon level (canon, proposed, retconned)
   - Time range
3. Display facts with evidence links
4. Navigate to related entities

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_facts(
    universe_id,
    entity_id=None,
    authority=None,
    canon_level="canon",
    offset=0,
    limit=20
) -> list[Fact]
```

**Layer 3 (CLI):**
```bash
monitor query facts --universe <UUID>
monitor query facts --entity <UUID> --authority gm
```

---
