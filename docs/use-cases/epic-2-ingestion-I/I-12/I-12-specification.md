# I-12: Delete Ingest Job

**Actor:** User
**Trigger:** Ingest → Jobs → [Job] → Delete

**Purpose:** Remove a failed, duplicate, or stale ingest job record from the history.

**Flow:**
1. Job list shows status: pending / processing / done / failed
2. Select job(s) to delete
3. Confirm → job record removed; source file and derived pack are NOT deleted
4. Guard: cannot delete a job in `processing` state

**Output:** Job record removed; source and pack unaffected.

### Implementation
```python
mongodb_delete_ingest_job(job_id)  # hard delete; guard on status != "processing"
```

---
