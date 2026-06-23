# MP-2: Import Pack from File

**Actor:** User
**Trigger:** Packs → Import

**Purpose:** Load a shared pack file (exported via MP-3) into the pack library.

**Flow:**
1. Upload `.monitorpack` file (gzip-compressed JSON)
2. System validates schema version
3. Creates new KnowledgePack in MongoDB from file; generates a fresh `id`
4. Pack is NOT auto-applied — user reviews first
5. Source PDFs are not bundled; `source_ids` are preserved as metadata references

**Output:** New pack in `status: "ready"`, available in pack library.

### Implementation
```python
POST /packs/import  →  multipart file upload
# Validate schema_version; reject unknown versions
# Always generate new id — never trust imported IDs
```

---
