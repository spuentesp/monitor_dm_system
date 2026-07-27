#!/usr/bin/env python3
"""
Ingestion-pipeline hygiene audit — INGESTION_PIPELINE_AUDIT.md Findings 3 & 7.

Two independent, read-only-by-default reports:

1. **game_systems provenance audit** (Finding 3): enumerate every
   ``game_systems`` document that has neither ``source_document_id`` nor
   ``hand_authored=True`` set — i.e. content that looks ingested/legitimate
   but has no traceable origin at all. This is the exact class of problem
   that let the ungrounded "Vampire: The Masquerade 5th Edition" document
   (``a227676a-...``) sit undetected for months.

2. **documents/MinIO dedup audit** (Finding 7): group ``documents`` records
   by ``(filename, file_size_bytes)`` — a cheap content-identity proxy
   without hashing every object. For each group with more than one record,
   report which one would be KEPT (``extraction_status=completed`` with the
   highest ``snippet_count``, else the most recent) and which would be
   DELETED. Also flags obvious test/probe-fixture uploads by filename
   pattern, regardless of duplication.

Usage::

    python scripts/audit_ingestion_documents.py                    # both reports, read-only
    python scripts/audit_ingestion_documents.py --provenance-only
    python scripts/audit_ingestion_documents.py --dedup-only
    python scripts/audit_ingestion_documents.py --apply-dedup      # ACTUALLY delete
                                                                     # dup/test-fixture
                                                                     # documents + their
                                                                     # MinIO objects

``--apply-dedup`` is the only destructive path in this script, and it always
prints the dry-run report first and asks for a typed confirmation before
touching MinIO or MongoDB — this is a one-time cleanup tool, not something
meant to run unattended.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import defaultdict
from typing import Any

from monitor_data.db.minio import get_minio_client
from monitor_data.db.mongodb import get_mongodb_client

# Filenames that are clearly automated test/probe fixtures, never meant to
# persist (INGESTION_PIPELINE_AUDIT.md Finding 7 evidence: probe1-probe5,
# t1, t2, corrupt.pdf, corrupt2.pdf, harrowfen, ashfall, ashfall_compact,
# millhaven-test).
_TEST_FIXTURE_PATTERNS = [
    re.compile(r"^probe\d*", re.IGNORECASE),
    re.compile(r"^t\d\.", re.IGNORECASE),
    re.compile(r"^corrupt\d*", re.IGNORECASE),
    re.compile(r"harrowfen", re.IGNORECASE),
    re.compile(r"ashfall", re.IGNORECASE),
    re.compile(r"millhaven[-_]?test", re.IGNORECASE),
]


def _is_test_fixture_filename(filename: str) -> bool:
    return any(p.search(filename) for p in _TEST_FIXTURE_PATTERNS)


# ============================================================================
# Finding 3: game_systems provenance audit
# ============================================================================


def audit_provenance() -> list[dict[str, Any]]:
    """Return every game_systems doc lacking BOTH source_document_id and
    hand_authored=True — i.e. content with no traceable origin."""
    mongodb = get_mongodb_client()
    systems = mongodb.get_collection("game_systems")

    gaps: list[dict[str, Any]] = []
    for doc in systems.find({}):
        if doc.get("is_builtin"):
            continue  # seed-data builtins are their own, separate story
        if doc.get("source_document_id"):
            continue
        if doc.get("hand_authored"):
            continue
        gaps.append(
            {
                "system_id": doc.get("system_id"),
                "name": doc.get("name"),
                "created_at": doc.get("created_at"),
                "needs_review": doc.get("needs_review", False),
            }
        )
    return gaps


def print_provenance_report(gaps: list[dict[str, Any]]) -> None:
    print("\n=== Finding 3: game_systems provenance audit ===")
    if not gaps:
        print("No provenance gaps found — every non-builtin system has a "
              "source_document_id or is marked hand_authored.")
        return
    print(f"{len(gaps)} system(s) with NO traceable origin (not ingested, not hand-authored):")
    for g in gaps:
        flag = " [needs_review]" if g["needs_review"] else ""
        print(f"  - {g['system_id']} | {g['name']!r} | created {g['created_at']}{flag}")
    print(
        "\nThese documents cannot be distinguished from a properly-ingested "
        "system without this audit. Recommended: either re-ingest from a "
        "real source, or explicitly mark them via the update endpoint with "
        "hand_authored=true if the content is intentionally hand-curated."
    )


# ============================================================================
# Finding 7: documents/MinIO dedup audit
# ============================================================================


def _completed_rank(doc: dict[str, Any]) -> tuple:
    """Sort key: prefer completed status, then higher snippet_count, then newer."""
    status = doc.get("extraction_status")
    is_completed = 1 if status == "completed" else 0
    snippet_count = doc.get("snippet_count") or 0
    created_at = doc.get("created_at")
    return (is_completed, snippet_count, created_at)


def audit_dedup() -> dict[str, Any]:
    """Group documents by (filename, file_size_bytes); report keep/delete sets."""
    mongodb = get_mongodb_client()
    documents = mongodb.get_collection("documents")

    groups: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    all_docs = list(documents.find({}))
    for doc in all_docs:
        key = (doc.get("filename", ""), doc.get("file_size_bytes"))
        groups[key].append(doc)

    duplicate_groups: list[dict[str, Any]] = []
    to_delete: list[dict[str, Any]] = []
    test_fixtures: list[dict[str, Any]] = []

    for (filename, size), docs in groups.items():
        is_test_fixture = _is_test_fixture_filename(filename)
        if is_test_fixture:
            test_fixtures.extend(docs)
            continue
        if len(docs) <= 1:
            continue
        ranked = sorted(docs, key=_completed_rank, reverse=True)
        keep, rest = ranked[0], ranked[1:]
        duplicate_groups.append(
            {"filename": filename, "size": size, "keep": keep, "delete": rest}
        )
        to_delete.extend(rest)

    return {
        "total_documents": len(all_docs),
        "duplicate_groups": duplicate_groups,
        "test_fixtures": test_fixtures,
        "to_delete": to_delete + test_fixtures,
    }


def print_dedup_report(report: dict[str, Any]) -> None:
    print("\n=== Finding 7: documents/MinIO dedup audit ===")
    print(f"Total documents scanned: {report['total_documents']}")

    print(f"\nDuplicate content groups: {len(report['duplicate_groups'])}")
    for group in report["duplicate_groups"]:
        keep = group["keep"]
        print(f"  '{group['filename']}' ({group['size']} bytes):")
        print(
            f"    KEEP   doc_id={keep.get('doc_id')} "
            f"status={keep.get('extraction_status')} snippets={keep.get('snippet_count')}"
        )
        for d in group["delete"]:
            print(
                f"    DELETE doc_id={d.get('doc_id')} "
                f"status={d.get('extraction_status')} snippets={d.get('snippet_count')} "
                f"minio_ref={d.get('minio_ref')}"
            )

    print(f"\nTest/probe-fixture uploads (delete outright): {len(report['test_fixtures'])}")
    for d in report["test_fixtures"]:
        print(f"  DELETE doc_id={d.get('doc_id')} filename={d.get('filename')!r}")

    print(f"\nTotal records that would be deleted: {len(report['to_delete'])}")


async def apply_dedup(to_delete: list[dict[str, Any]]) -> None:
    """Delete the given document records + their MinIO objects.

    Must go through MinIOClient — MinIO stores each object in its own
    erasure-coded on-disk directory, not a plain file; raw filesystem
    deletion corrupts the bucket (confirmed while investigating this
    finding: fitz.open() on the raw upload path fails with FileDataError).
    """
    mongodb = get_mongodb_client()
    documents = mongodb.get_collection("documents")
    minio = get_minio_client()

    deleted, errors = 0, 0
    for doc in to_delete:
        doc_id = doc.get("doc_id")
        minio_ref = doc.get("minio_ref")
        try:
            if minio_ref:
                await minio.delete(key=minio_ref)
            documents.delete_one({"doc_id": doc_id})
            deleted += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR deleting doc_id={doc_id}: {exc}")
            errors += 1
    print(f"\nApplied: {deleted} deleted, {errors} errors.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provenance-only", action="store_true")
    parser.add_argument("--dedup-only", action="store_true")
    parser.add_argument(
        "--apply-dedup",
        action="store_true",
        help="Actually delete duplicate/test-fixture documents + MinIO objects "
        "(after a typed confirmation prompt).",
    )
    args = parser.parse_args()

    run_provenance = not args.dedup_only
    run_dedup = not args.provenance_only

    if run_provenance:
        print_provenance_report(audit_provenance())

    if run_dedup:
        report = audit_dedup()
        print_dedup_report(report)

        if args.apply_dedup and report["to_delete"]:
            confirm = input(
                f"\nType 'DELETE {len(report['to_delete'])}' to permanently remove "
                "these documents and their MinIO objects: "
            )
            if confirm.strip() == f"DELETE {len(report['to_delete'])}":
                asyncio.run(apply_dedup(report["to_delete"]))
            else:
                print("Confirmation did not match — no changes made.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
