#!/usr/bin/env python3
"""Deliberate, versioned re-index of every Qdrant collection with the pinned model.

WHY THIS EXISTS
---------------
Retrieval commits to ONE embedding model (see ``RetrievalConfig``). Every
vector in Qdrant must have been produced by that model — index-time and
query-time must match, or nearest-vector search returns garbage. When the
pinned model changes (e.g. repointing the ``llm_providers`` embedding row from
``gemini/gemini-embedding-001`` back to ``ollama/nomic-embed-text``), the old
vectors are stale and the ``RetrievalService`` model/dim guard will hard-fail
``ensure_collection`` on purpose. This script is the sanctioned way to rebuild:
it re-embeds every stored passage with the *current* pinned model and records
the model in ``system_config`` so the guard passes again.

The source text is read back from each point's ``text`` payload (the
``RetrievalService.index`` contract stores ``payload["text"]`` on every point),
so no upstream corpus is needed — this re-embeds exactly what is already stored.

DESTRUCTIVE: with ``--yes`` this DROPS and recreates each collection. Points
with no ``text`` payload cannot be re-embedded and are dropped — run
``--dry-run`` first to see how many that is.

PRECONDITIONS
-------------
* Qdrant reachable.
* The pinned embedding provider is live and matches the intended model. If you
  just repointed the DB row, run ``scripts/seed_ollama_embedding_provider.py``
  first, then this.

USAGE
-----
    # Report what would happen — no writes:
    uv run python scripts/reindex_embeddings.py --dry-run

    # Rebuild every collection with the pinned model:
    uv run python scripts/reindex_embeddings.py --yes

    # Only specific collections:
    uv run python scripts/reindex_embeddings.py --yes --collections snippets,knowledge
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, "packages/data-layer/src")


async def _scroll_all(client, collection: str, page: int = 256):
    """Yield every point in ``collection`` (payload only, no vectors)."""
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=collection,
            limit=page,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            yield p
        if offset is None:
            break


async def _reindex_one(service, qdrant, collection: str, *, dry_run: bool, batch_size: int) -> dict:
    from monitor_data.retrieval.contracts import Document

    client = qdrant.get_client()

    try:
        await client.get_collection(collection)
    except Exception:  # noqa: BLE001 — collection missing; nothing to reindex
        print(f"  [{collection}] does not exist — skipping")
        return {"collection": collection, "total": 0, "reindexed": 0, "dropped": 0, "skipped": True}

    docs: list[Document] = []
    no_text = 0
    total = 0
    async for point in _scroll_all(client, collection):
        total += 1
        payload = dict(getattr(point, "payload", None) or {})
        text = payload.pop("text", None)
        if not text or not str(text).strip():
            no_text += 1
            continue
        docs.append(Document(id=str(getattr(point, "id", "")), text=str(text), payload=payload))

    print(
        f"  [{collection}] {total} points; {len(docs)} re-embeddable, "
        f"{no_text} without a 'text' payload (would be dropped)"
    )

    if dry_run:
        return {"collection": collection, "total": total, "reindexed": 0, "dropped": no_text, "dry_run": True}

    # Drop + recreate at the pinned dimension (ensure_collection reads
    # COLLECTION_CONFIGS, whose size is settings.embedding_dimension — the same
    # dimension the RetrievalConfig pins to, so the guard stays consistent).
    await client.delete_collection(collection_name=collection)
    qdrant._collections_initialized.discard(collection)
    await qdrant.ensure_collection(collection)

    reindexed = 0
    for start in range(0, len(docs), batch_size):
        batch = docs[start : start + batch_size]
        # adopt=True: the collection's recorded meta still names the OLD model
        # (delete_collection drops the Qdrant collection, not the Postgres meta
        # row). Without adopt, the model/dim guard would raise on the very
        # first batch — exactly the model-swap this script exists to perform.
        await service.index(collection, batch, adopt=True)
        reindexed += len(batch)
        print(f"    [{collection}] re-indexed {reindexed}/{len(docs)}")

    return {"collection": collection, "total": total, "reindexed": reindexed, "dropped": no_text}


async def _run(collections: list[str], *, dry_run: bool, batch_size: int) -> int:
    from monitor_data.db.qdrant import COLLECTION_CONFIGS, QdrantClient
    from monitor_data.retrieval import default_retrieval_service

    targets = collections or list(COLLECTION_CONFIGS.keys())
    unknown = [c for c in targets if c not in COLLECTION_CONFIGS]
    if unknown:
        print(f"ERROR: unknown collection(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Valid collections: {', '.join(COLLECTION_CONFIGS)}", file=sys.stderr)
        return 2

    service = default_retrieval_service()
    model = await service.model()
    dimension = await service.dimension()

    print("Reindex plan")
    print("------------")
    print(f"  pinned embedding model : {model}")
    print(f"  vector dimension       : {dimension}")
    print(f"  collections            : {', '.join(targets)}")
    print(f"  mode                   : {'DRY RUN (no writes)' if dry_run else 'REBUILD (destructive)'}")
    print()

    qdrant = QdrantClient()
    results = []
    for collection in targets:
        results.append(
            await _reindex_one(
                service, qdrant, collection, dry_run=dry_run, batch_size=batch_size
            )
        )

    print()
    print("Summary")
    print("-------")
    for r in results:
        if r.get("skipped"):
            print(f"  {r['collection']}: skipped (missing)")
        elif dry_run:
            print(f"  {r['collection']}: {r['total']} points, {r['dropped']} would be dropped")
        else:
            print(f"  {r['collection']}: re-indexed {r['reindexed']}, dropped {r['dropped']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--collections",
        default="",
        help="Comma-separated collection names (default: all known collections).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only; make no writes.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required to actually drop+rebuild. Without it (and without --dry-run), refuses to run.",
    )
    parser.add_argument("--batch-size", type=int, default=128, help="Docs per embed/upsert batch.")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print(
            "Refusing to run: this drops and rebuilds collections. Pass --dry-run to preview, "
            "or --yes to confirm the destructive rebuild.",
            file=sys.stderr,
        )
        return 1

    collections = [c.strip() for c in args.collections.split(",") if c.strip()]
    return asyncio.run(_run(collections, dry_run=args.dry_run, batch_size=args.batch_size))


if __name__ == "__main__":
    raise SystemExit(main())
