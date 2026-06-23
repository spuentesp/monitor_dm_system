# MP-9: Delete / Archive Pack

**Actor:** User
**Trigger:** Packs → [Pack] → Archive / Delete

**Purpose:** Soft-archive a pack (hidden but reversible) or permanently delete it. Applied canon is never rolled back.

**Flow (Archive):**
1. Pack `status` set to `"archived"`
2. Hidden from default list view; toggle to show archived
3. Fully reversible

**Flow (Delete):**
1. Warn: list worlds this pack has been applied to (from `apply_history`)
2. Confirm → hard delete from MongoDB
3. Source PDFs unaffected (external)
4. Applied canon is NOT rolled back
5. Guard: cannot delete while a `PackApplySession` for this pack is in `"resolving"` state

**Output:** Pack archived or deleted; all applied canon untouched.

### Implementation
```python
PATCH /packs/{id}   →  {status: "archived"}       # soft archive
DELETE /packs/{id}  →  hard delete; guard on active apply session
```

---
