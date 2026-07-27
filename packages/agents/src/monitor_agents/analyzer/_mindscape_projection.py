"""
Mindscape projection — push summary artifacts into Qdrant payloads and vectors.

This is a standalone async function that takes pre-built summary artifacts and
persists them to Qdrant.  It doesn't depend on the Analyzer class.
"""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

import structlog
from monitor_data.db.qdrant import get_qdrant_client
from qdrant_client.models import PointStruct

logger = structlog.get_logger(__name__)


async def project_mindscape_to_qdrant(
    *,
    source_name: str,
    chunk_summaries: list[Any],
    section_summaries: list[Any],
    mindscape: Any | None,
    collection: str = "snippets",
) -> None:
    """Project summary artifacts into Qdrant payloads and summary vectors."""
    if not chunk_summaries and not section_summaries and not getattr(mindscape, "summary", ""):
        return

    client = get_qdrant_client()
    await client.ensure_collection(collection)
    qdrant = client.get_client()

    section_by_chunk: dict[str, Any] = {}
    for section in section_summaries:
        for chunk_id in getattr(section, "chunk_ids", []) or []:
            section_by_chunk[str(chunk_id)] = section

    common_payload = {
        "source_name": source_name,
        "source_mindscape_summary": getattr(mindscape, "summary", "") or "",
        "source_themes": list(getattr(mindscape, "themes", []) or []),
        "source_taxonomy_hints": list(getattr(mindscape, "taxonomy_hints", []) or []),
        "source_system_name": getattr(mindscape, "system_name", None),
    }

    for chunk_summary in chunk_summaries:
        related_section = section_by_chunk.get(str(getattr(chunk_summary, "chunk_id", "")))
        payload_patch = {
            **common_payload,
            "summary": getattr(chunk_summary, "summary", "") or "",
            "chunk_summary": getattr(chunk_summary, "summary", "") or "",
            "summary_confidence": float(getattr(chunk_summary, "confidence", 0.0) or 0.0),
            "summary_tags": list(getattr(chunk_summary, "tags", []) or []),
            "source_ref": getattr(chunk_summary, "source_ref", None),
            "section_summary": getattr(related_section, "summary", "") if related_section else "",
            "section_key": getattr(related_section, "section_key", None) if related_section else None,
            "semantic_category": getattr(related_section, "semantic_category", None) if related_section else None,
            "artifact_projection_version": "mindscape-v1",
        }
        await qdrant.set_payload(
            collection_name=collection,
            payload=payload_patch,
            points=[str(chunk_summary.chunk_id)],
        )

    payloads: list[dict[str, Any]] = []
    for chunk_summary in chunk_summaries:
        summary_text = (getattr(chunk_summary, "summary", "") or "").strip()
        if not summary_text:
            continue
        payloads.append(
            {
                **common_payload,
                "artifact_type": "chunk_summary",
                "text": summary_text,
                "summary": summary_text,
                "related_chunk_id": str(chunk_summary.chunk_id),
                "chunk_index": int(getattr(chunk_summary, "chunk_index", 0) or 0),
                "source_ref": getattr(chunk_summary, "source_ref", None),
                "summary_tags": list(getattr(chunk_summary, "tags", []) or []),
            }
        )

    for section_summary in section_summaries:
        summary_text = (getattr(section_summary, "summary", "") or "").strip()
        if not summary_text:
            continue
        payloads.append(
            {
                **common_payload,
                "artifact_type": "section_summary",
                "text": summary_text,
                "summary": summary_text,
                "section_key": getattr(section_summary, "section_key", None),
                "heading_path": list(getattr(section_summary, "heading_path", []) or []),
                "chunk_ids": list(getattr(section_summary, "chunk_ids", []) or []),
                "semantic_category": getattr(section_summary, "semantic_category", None),
            }
        )

    mindscape_summary = (getattr(mindscape, "summary", "") or "").strip()
    if mindscape_summary:
        payloads.append(
            {
                **common_payload,
                "artifact_type": "source_mindscape",
                "text": mindscape_summary,
                "summary": mindscape_summary,
            }
        )

    if not payloads:
        return

    from monitor_data.retrieval import default_retrieval_service

    vectors = await default_retrieval_service().embed_docs([payload["text"] for payload in payloads])
    points = [
        PointStruct(
            id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"{payload['artifact_type']}:{source_name}:{payload.get('related_chunk_id') or payload.get('section_key') or 'mindscape'}",
                )
            ),
            vector=vector,
            payload=payload,
        )
        for payload, vector in zip(payloads, vectors, strict=False)
    ]
    await qdrant.upsert(collection_name=collection, points=points)
