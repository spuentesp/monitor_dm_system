# I-1: Upload Document

**Actor:** User
**Trigger:** Ingest → Upload

**Flow:**
1. Select file (PDF, EPUB, TXT, MD, DOCX)
2. Select target universe (or create)
3. Prompt: Source type (manual, rulebook, lore, homebrew, session_notes)
4. Prompt: Authority level (authoritative, canon, proposed)
5. Upload to MinIO
6. Create Source node in Neo4j
7. Create Document record in MongoDB
8. → I-2 (Extract)

### Implementation

**Layer 1 (Data Layer):**
```python
minio_upload(file_path, bucket="documents") -> minio_ref
neo4j_create_source(universe_id, params) -> source_id
mongodb_create_document(params) -> doc_id
```

**Upload Flow:**
```python
async def upload_document(
    file_path: Path,
    universe_id: UUID,
    source_type: SourceType,
    canon_level: SourceCanonLevel
) -> UploadResult:
    # 1. Upload to MinIO
    minio_ref = await minio_upload(file_path, bucket="documents")

    # 2. Create Source in Neo4j
    source_id = await neo4j_create_source(universe_id, {
        "title": file_path.stem,
        "source_type": source_type,
        "canon_level": canon_level,
        "provenance": "user_upload"
    })

    # 3. Create Document record in MongoDB
    doc_id = await mongodb_create_document({
        "source_id": source_id,
        "universe_id": universe_id,
        "minio_ref": minio_ref,
        "filename": file_path.name,
        "file_type": file_path.suffix,
        "extraction_status": "pending"
    })

    # 4. Queue extraction
    await queue_extraction(doc_id)

    return UploadResult(source_id=source_id, doc_id=doc_id)
```

**Layer 3 (CLI):**
```bash
monitor ingest upload ./phb.pdf --universe <UUID> --type rulebook --authority authoritative
```

---
