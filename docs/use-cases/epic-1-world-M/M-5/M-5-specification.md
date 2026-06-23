# M-5: List Universes

**Actor:** User
**Trigger:** Manage → Universes

**Output:**
```
Universes
─────────────────────────────────────────
 # │ Name            │ Genre    │ Stories │ Entities
───┼─────────────────┼──────────┼─────────┼──────────
 1 │ Middle-earth    │ Fantasy  │ 3       │ 127
 2 │ Forgotten Realms│ Fantasy  │ 1       │ 456
```

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_universes(multiverse_id=None) -> list[UniverseSummary]
```

**Cypher Query:**
```cypher
MATCH (u:Universe)
WHERE u.canon_level <> 'retconned'
OPTIONAL MATCH (u)-[:HAS_STORY]->(s:Story)
OPTIONAL MATCH (u)-[:HAS_ENTITY]->(e:EntityInstance)
RETURN u.id, u.name, u.genre,
       count(DISTINCT s) AS story_count,
       count(DISTINCT e) AS entity_count
ORDER BY u.name
```

**Layer 3 (CLI):**
```bash
monitor manage universe list
monitor manage universe list --multiverse <UUID>
```

---
