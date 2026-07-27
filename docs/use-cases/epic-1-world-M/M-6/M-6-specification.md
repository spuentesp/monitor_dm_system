# M-6: View Universe

**Actor:** User
**Trigger:** Select universe from list

**Output:**
- Basic info (name, genre, tone, tech level)
- Entity counts by type
- Story list
- Source list
- Recent activity

**Actions:** Edit, Delete, Explore, Start Story

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_universe(universe_id) -> Universe
neo4j_get_universe_stats(universe_id) -> UniverseStats
neo4j_list_stories(universe_id, limit=5)
neo4j_list_sources(universe_id, limit=5)
```

**Cypher Query (Stats):**
```cypher
MATCH (u:Universe {id: $universe_id})
OPTIONAL MATCH (u)-[:HAS_ENTITY]->(e:EntityInstance)
WITH u, e.entity_type AS type, count(e) AS count
RETURN u, collect({type: type, count: count}) AS entity_counts
```

**Layer 3 (CLI):**
```bash
monitor manage universe view <UUID>
monitor manage universe view --name "Middle-earth"
```

---
