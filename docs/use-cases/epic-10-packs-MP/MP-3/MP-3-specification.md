# MP-3: Export Pack to File

**Actor:** User
**Trigger:** Packs → [Pack] → Export

**Purpose:** Serialize a pack to a portable `.monitorpack` file for sharing or backup. Source PDFs are not embedded.

**Flow:**
1. Select pack
2. Choose: include lineage metadata? (yes/no)
3. Download `.monitorpack` (gzip-compressed JSON)

**File format:**
```json
{
  "schema_version": "1.0",
  "exported_at": "2026-04-05T00:00:00Z",
  "pack": { "...full KnowledgePack document..." }
}
```

**Output:** `.monitorpack` file download.

### Implementation
```python
GET /packs/{id}/export  →  file stream (Content-Disposition: attachment)
```

---
