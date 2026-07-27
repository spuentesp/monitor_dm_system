# M-25: Edit Axiom

**Actor:** User
**Trigger:** Axiom → Edit

**Editable:** statement, domain, confidence, canon_level

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_axiom(axiom_id) -> Axiom
neo4j_update_axiom(axiom_id, params)
```

---
