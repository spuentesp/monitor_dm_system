# Q-6: Relationship Graph

**Actor:** User
**Trigger:** Query → Relationships

**Flow:**
1. Select starting entity
2. Display relationship graph (text or visual tree)
3. Navigate interactively
4. Show: ALLY_OF, ENEMY_OF, MEMBER_OF, LOCATED_IN, OWNS

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_relationship_graph(entity_id, depth=2) -> Graph
```

**Cypher Query:**
```cypher
MATCH (e:EntityInstance {id: $entity_id})-[r]-(related)
WHERE r.canon_level <> 'retconned'
RETURN e, r, related
```

**Layer 3 (CLI):**
```bash
monitor query graph <ENTITY_UUID>
monitor query graph <ENTITY_UUID> --depth 3
```

**Text Tree Display:**
```
Gandalf (character)
├── ALLY_OF
│   ├── Frodo Baggins
│   └── Aragorn
├── MEMBER_OF
│   └── The Fellowship
└── LOCATED_IN
    └── Middle-earth
```

---
