# SYS-9: Verify Backup/Restore

**Actor:** Operator
**Trigger:** Scheduled verification or manual

**Flow:**
1. Restore snapshot to scratch environment.
2. Run integrity checks (Neo4j constraints, MongoDB indexes, Qdrant collections).
3. Run sample queries to validate data.
4. Report status and failures.

**Output:** Verification report with pass/fail.

---
