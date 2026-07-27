# I-8: Delete or Reingest Source

**Actor:** User
**Trigger:** Source Library → Source → Delete / Reingest

**Purpose:** Remove a source and all derived data, or re-run ingestion with different parameters.

**Flow (Delete):**
1. Warn: lists all packs derived from this source
2. Confirm → delete file from MinIO, source record, all ingest jobs
3. Derived packs are NOT automatically deleted (user chooses separately)

**Flow (Reingest):**
1. Choose new scan type and/or analysis layers
2. Choose target: produce into existing pack or new pack
3. Queue new ingest job; prior job archived (not deleted)

**Output:** Source deleted, or new ingest job queued.

### Implementation
```python
minio_delete(ref)
mongodb_delete_source(source_id, cascade_jobs=True)
# Reingest: reuse upload flow with existing source_id
```

---
