#!/usr/bin/env python3
"""Manual step-by-step ingestion pipeline test."""

import asyncio
import json
import logging
import os
import sys
import time

# Enable LLM logging
os.environ["MONITOR_LLM_LOG"] = "1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("test_pipeline")


async def step_1_test_pdf_extraction():
    """Extract text from the Death in Space PDF to verify pymupdf works."""
    log.info("=" * 60)
    log.info("STEP 1: PDF Text Extraction (pymupdf)")
    log.info("=" * 60)

    from monitor_data.tools.ingest_tools import ingest_pdf

    from monitor_data.db.minio import get_minio_client

    minio = get_minio_client()
    object_key = "uploads/0a876e75-1e6f-4c37-bd89-4c395c2a8580/20260407_023339_Death_in_Space_Core_Rules.pdf"

    pdf_bytes = None
    try:
        pdf_bytes = await minio.download(object_key)
        log.info("Downloaded PDF from MinIO: %s (%d bytes)", object_key, len(pdf_bytes))
    except Exception as e:
        log.error("Download failed: %s", e)

    if not pdf_bytes:
        log.error("Could not download PDF from MinIO!")
        return None

    # Now extract + chunk
    t0 = time.time()
    chunks = ingest_pdf(pdf_bytes, "Death in Space Core Rules")
    elapsed = time.time() - t0

    log.info("PDF extraction: %d chunks in %.1fs", len(chunks), elapsed)
    if chunks:
        log.info(
            "First chunk: page=%s, words=%d",
            chunks[0].page_number,
            len(chunks[0].text.split()),
        )
        log.info(
            "Last chunk:  page=%s, words=%d",
            chunks[-1].page_number,
            len(chunks[-1].text.split()),
        )

        # Show section distribution
        sections = {}
        for c in chunks:
            sp = c.metadata.get("section_path", "no-section")
            sections[sp] = sections.get(sp, 0) + 1
        log.info("Unique sections: %d", len(sections))

        # Show semantic categories
        categories = {}
        for c in chunks:
            cat = c.metadata.get("semantic_category", "uncategorized")
            categories[cat] = categories.get(cat, 0) + 1
        log.info("Semantic categories: %s", json.dumps(categories, indent=2))

    return chunks, pdf_bytes


async def step_2_test_embedding(chunks):
    """Embed chunks and upsert to Qdrant."""
    log.info("=" * 60)
    log.info("STEP 2: Embedding + Qdrant Upsert")
    log.info("=" * 60)

    from monitor_data.db.embeddings import embed_batch
    from qdrant_client.models import PointStruct

    # Test embedding with first 3 chunks
    test_texts = [c.text[:500] for c in chunks[:3]]
    log.info("Testing embedding with %d sample texts...", len(test_texts))
    t0 = time.time()
    try:
        vectors = await embed_batch(test_texts)
        elapsed = time.time() - t0
        log.info(
            "Embedding test OK: %d vectors, dim=%d, %.1fs",
            len(vectors),
            len(vectors[0]),
            elapsed,
        )
    except Exception as e:
        log.error("Embedding FAILED: %s", e)
        raise

    # Now embed ALL chunks
    log.info("Embedding all %d chunks...", len(chunks))
    batch_size = 64
    all_points = []
    t0 = time.time()

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]
        try:
            vecs = await embed_batch(texts)
            for j, (chunk, vec) in enumerate(zip(batch, vecs)):
                point = PointStruct(
                    id=str(chunk.chunk_id),
                    vector=vec,
                    payload=chunk.to_qdrant_payload(),
                )
                all_points.append(point)
            log.info(
                "  Embedded batch %d-%d (%d/%d)",
                i,
                i + len(batch),
                len(all_points),
                len(chunks),
            )
        except Exception as e:
            log.error("Embedding batch %d FAILED: %s", i, e)
            raise

    elapsed = time.time() - t0
    log.info("All %d chunks embedded in %.1fs", len(all_points), elapsed)

    # Upsert to Qdrant
    from monitor_data.db.qdrant import get_qdrant_client as get_qclient

    qclient = get_qclient()
    collection = "snippets"

    await qclient.ensure_collection(collection)
    qdrant = qclient.get_client()
    log.info("Qdrant collection '%s' ready", collection)

    # Upsert in batches
    for i in range(0, len(all_points), batch_size):
        batch = all_points[i : i + batch_size]
        await qdrant.upsert(collection_name=collection, points=batch)
    log.info("Upserted %d points to Qdrant '%s'", len(all_points), collection)

    return len(all_points)


async def step_3_test_llm_calls():
    """Test that LIGHT and HEAVY LLM providers actually work."""
    log.info("=" * 60)
    log.info("STEP 3: LLM Provider Smoke Test")
    log.info("=" * 60)

    import dspy
    from monitor_agents.dspy_runtime import get_dspy_lm
    from monitor_data.schemas.llm_config import ModelRole

    # Test LIGHT model
    log.info("Testing LIGHT model (used for classification/rules)...")
    t0 = time.time()
    try:
        lm = get_dspy_lm("analyzer", ModelRole.LIGHT)
        log.info("  LIGHT LM: %s", lm.model)
        with dspy.context(lm=lm):
            result = lm("Say 'hello world' and nothing else.")
            log.info("  LIGHT response: %s", str(result)[:200])
        elapsed = time.time() - t0
        log.info("  LIGHT model OK (%.1fs)", elapsed)
    except Exception as e:
        log.error("  LIGHT model FAILED: %s", e)
        import traceback

        traceback.print_exc()
        return False

    # Test HEAVY model
    log.info("Testing HEAVY model (used for extraction)...")
    t0 = time.time()
    try:
        lm = get_dspy_lm("analyzer", ModelRole.HEAVY)
        log.info("  HEAVY LM: %s", lm.model)
        with dspy.context(lm=lm):
            result = lm("Say 'hello world' and nothing else.")
            log.info("  HEAVY response: %s", str(result)[:200])
        elapsed = time.time() - t0
        log.info("  HEAVY model OK (%.1fs)", elapsed)
    except Exception as e:
        log.error("  HEAVY model FAILED: %s", e)
        import traceback

        traceback.print_exc()
        return False

    return True


async def main():
    log.info("MANUAL PIPELINE TEST — Death in Space Core Rules")
    log.info("=" * 60)

    # Step 1: Extract PDF
    result = await step_1_test_pdf_extraction()
    if result is None:
        log.error("ABORT: PDF extraction failed")
        return
    chunks, pdf_bytes = result

    # Step 2: Embed + Qdrant
    snippet_count = await step_2_test_embedding(chunks)

    # Step 3: Smoke test LLM providers
    llm_ok = await step_3_test_llm_calls()
    if not llm_ok:
        log.error("ABORT: LLM providers not working — fix before proceeding")
        return

    log.info("")
    log.info("=" * 60)
    log.info("STEPS 1-3 PASSED — ready for analysis pipeline")
    log.info("  Chunks: %d, Snippets in Qdrant: %d", len(chunks), snippet_count)
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
