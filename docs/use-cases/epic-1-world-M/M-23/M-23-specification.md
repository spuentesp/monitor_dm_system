# M-23: Create Axiom

**Actor:** User
**Trigger:** Manage → Axioms → Create

**Flow:**
1. Select universe
2. Prompt: Statement (e.g., "Magic exists", "FTL is impossible")
3. Prompt: Domain (physics, magic, society, biology)
4. Prompt: Confidence (0-100%)
5. Link to source (optional)
6. Create Axiom in Neo4j

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_axiom(universe_id, params) -> UUID
neo4j_link_evidence(axiom_id, source_id, "SUPPORTED_BY")
```

**Layer 3 (CLI):**
```bash
monitor manage axiom create --universe <UUID> --statement "Magic exists" --domain magic
```

**Note:** Axiom.authority can only be `source`, `gm`, or `system` (not `player`).

---
