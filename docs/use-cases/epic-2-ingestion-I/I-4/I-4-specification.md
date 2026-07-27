# I-4: Review Proposals

**Actor:** User
**Trigger:** Ingest → Review

**Flow:**
1. List pending proposals (grouped by source)
2. For each:
   - Display proposed entity/fact
   - Show source snippet (evidence)
   - Show confidence score
3. Actions:
   - Accept → canonize to Neo4j
   - Edit → modify and accept
   - Reject → mark rejected
   - Skip → decide later

---
