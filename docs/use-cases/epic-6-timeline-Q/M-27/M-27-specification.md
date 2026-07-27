# M-27: View/Edit Fact

**Actor:** User
**Trigger:** Select fact

**Output:** Statement, entities, evidence, authority, confidence
**Actions:** Edit, Retcon (replace with new fact)

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_fact(fact_id) -> Fact
neo4j_update_fact(fact_id, params)
neo4j_retcon_fact(old_fact_id, new_fact_params) -> UUID  # Creates replacement
```

**Retcon Logic:**
```python
async def retcon_fact(old_fact_id: UUID, new_statement: str) -> UUID:
    """Replace a fact with a corrected version."""
    # Mark old as retconned
    await neo4j_update_fact(old_fact_id, {"canon_level": "retconned"})

    # Create new fact with reference to old
    new_fact_id = await neo4j_create_fact({
        "statement": new_statement,
        "replaces": old_fact_id,
        "authority": "gm",
        "canon_level": "canon"
    })

    return new_fact_id
```

---
