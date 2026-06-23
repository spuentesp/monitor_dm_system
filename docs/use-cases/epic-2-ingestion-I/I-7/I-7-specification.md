# I-7: Source Library

**Actor:** User
**Trigger:** Ingest → Sources

**Purpose:** Browse and manage all uploaded source documents (PDFs, EPUBs, etc.) independently from the packs they produced. PDFs are stored externally to packs; this view is the authoritative library.

**Flow:**
1. List all uploaded sources — paginated, sortable by name / date / status
2. Each row: filename, type, status, size, upload date, number of packs produced
3. Click source → detail: full ingest history, scan type, layers run, jobs run, file preview
4. See which pack(s) were derived from this source
5. Link/unlink pack associations (see I-10)

**Output:** Browsable source library with provenance to derived packs.

### Implementation
- MinIO: retrieve file bytes for preview/download
- MongoDB: source metadata, job history
- `Source` type in `packages/ui/frontend/src/lib/types.ts`

---
