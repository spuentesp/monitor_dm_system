# M-24: List Axioms

**Actor:** User
**Trigger:** Manage → Axioms

**Output:** Table of axioms by domain

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_axioms(universe_id, domain=None) -> list[Axiom]
```

---
