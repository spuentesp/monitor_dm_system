# M-3: List Multiverses

**Actor:** User
**Trigger:** Manage → Multiverses

**Output:** Table of multiverses with universe counts

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_multiverses(omniverse_id) -> list[MultiverseSummary]
# Returns: id, name, system_name, universe_count
```

**Cypher Query:**
```cypher
MATCH (m:Multiverse)<-[:CONTAINS]-(o:Omniverse {id: $omniverse_id})
OPTIONAL MATCH (m)-[:CONTAINS]->(u:Universe)
RETURN m.id, m.name, m.system_name, count(u) AS universe_count
ORDER BY m.name
```

---
