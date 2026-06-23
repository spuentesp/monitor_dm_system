# M-26: Create Fact (GM Override)

**Actor:** User (as GM)
**Trigger:** Manage → Facts → Create

**Flow:**
1. Select universe
2. Prompt: Statement
3. Prompt: Time reference (when is this true)
4. Prompt: Duration (ongoing, instant, temporary)
5. Link involved entities
6. Link evidence (source, scene)
7. Create Fact in Neo4j with authority = "gm"

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_fact(universe_id, params) -> UUID
neo4j_link_entities(fact_id, entity_ids, "INVOLVED_IN")
neo4j_link_evidence(fact_id, scene_id, "SUPPORTED_BY")
```

**Note:** This is a GM override path - bypasses normal canonization gate.

---
