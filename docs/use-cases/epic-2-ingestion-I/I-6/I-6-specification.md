# I-6: Manage Binary Assets (MinIO)

**Actor:** User
**Trigger:** Ingest → Upload binary

**Flow:**
1. Upload binary (PDF/image/audio) to MinIO with metadata (source_id, universe_id).
2. Link binary to source document and entity references (if known).
3. Retrieve or stream binary by source/entity.
4. Delete/replace binary (soft delete, retain metadata).

**Output:** Binary stored with retrievable URL and metadata.

**Implementation**
- Data Layer: MinIO client operations; metadata references stored alongside sources/entities.
- Agents: Indexer handles uploads; CanonKeeper links evidence to binaries.
- CLI: `monitor ingest --binary <file> --universe <UUID>`.

---
