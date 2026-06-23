# I-2: Extract Content

**Actor:** System (Indexer)
**Trigger:** After upload

**Flow:**
1. Extract text from document
2. Chunk into snippets (500 tokens, 50 overlap)
3. Store snippets in MongoDB
4. Embed snippets in Qdrant
5. → I-3 (Entity extraction)

### Implementation

**Layer 1 (Data Layer):**
```python
minio_download(minio_ref) -> bytes
mongodb_create_snippet(doc_id, params) -> snippet_id
qdrant_upsert(collection, vector, payload)
mongodb_update_document(doc_id, {"extraction_status": "complete"})
```

**Layer 2 (Agents):**
- `Indexer.extract_content(doc_id)` - Main extraction flow

**Extraction Flow:**
```python
async def extract_content(doc_id: UUID) -> ExtractionResult:
    # 1. Get document metadata
    doc = await mongodb_get_document(doc_id)

    # 2. Download file from MinIO
    content = await minio_download(doc.minio_ref)

    # 3. Extract text based on file type
    text = await extract_text(content, doc.file_type)

    # 4. Chunk text (500 tokens, 50 overlap)
    chunks = chunk_text(text, chunk_size=500, overlap=50)

    # 5. Store snippets and embed
    snippet_ids = []
    for i, chunk in enumerate(chunks):
        # Store in MongoDB
        snippet_id = await mongodb_create_snippet(doc_id, {
            "doc_id": doc_id,
            "source_id": doc.source_id,
            "text": chunk.text,
            "page": chunk.page,
            "section": chunk.section,
            "chunk_index": i
        })

        # Embed in Qdrant
        embedding = await embed_text(chunk.text)
        await qdrant_upsert("snippet_chunks", {
            "id": snippet_id,
            "vector": embedding,
            "payload": {
                "snippet_id": str(snippet_id),
                "doc_id": str(doc_id),
                "source_id": str(doc.source_id),
                "universe_id": str(doc.universe_id),
                "text": chunk.text
            }
        })
        snippet_ids.append(snippet_id)

    # 6. Update document status
    await mongodb_update_document(doc_id, {"extraction_status": "complete"})

    # 7. Queue entity extraction
    await queue_entity_extraction(doc_id, snippet_ids)

    return ExtractionResult(snippet_count=len(snippet_ids))
```

---
