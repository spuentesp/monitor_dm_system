"""Run a whole book through decomposition, resumably (I-17).

Tree, extraction and review each pick up from what's stored, so calling this again after a crash
or a pause only does what's missing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from monitor_data.schemas.book_graph import BookRecord, BookRecordType, BookTree
from monitor_data.schemas.ingestion_jobs import DecompositionProgress
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_data.tools.ingest_tools.book_tree import DECOMPOSER_VERSION, decompose_pdf
from monitor_data.tools.mongodb_tools.book_decomposition import mongodb_upsert_book_records
from monitor_data.tools.mongodb_tools.knowledge_packs import (
    mongodb_create_knowledge_pack,
    mongodb_get_knowledge_pack,
)

from monitor_agents.book_decomposition.extractor import WindowExtractor
from monitor_agents.book_decomposition.knowledge_graph import (
    GraphModel,
    build_domain_tree,
    build_graphs,
    graph_fingerprint,
)
from monitor_agents.book_decomposition.pack_mapper import build_pack, map_claims
from monitor_agents.book_decomposition.pacing import RunGuard, RunStopped
from monitor_agents.book_decomposition.pipeline import WindowOutcome
from monitor_agents.book_decomposition.review import (
    CoverageModel,
    ReviewModel,
    ReviewReport,
    coverage_fingerprint,
    review_claims,
    verification_fingerprint,
)
from monitor_agents.book_decomposition.runner import IngestStatus, run_until_settled
from monitor_agents.book_decomposition.store import (
    MongoCheckLog,
    MongoCoverageLog,
    MongoExtractionLog,
    MongoGraphLog,
    load_tree,
    save_domain_trees,
    save_graphs,
    save_review,
    save_tree,
)
from monitor_agents.book_decomposition.windows import build_windows

log = structlog.get_logger()


class DecomposeStatus(StrEnum):
    COMPLETE = "complete"
    COMPLETE_WITH_QUARANTINE = "complete_with_quarantine"
    PAUSED = "paused"


@dataclass
class DecomposeResult:
    status: DecomposeStatus
    progress: DecompositionProgress
    pack_id: UUID | None = None
    report: ReviewReport | None = field(default=None)


def _load_or_build_tree(pdf_bytes: bytes, doc_id: str, title: str) -> BookTree:
    """Reuse a stored tree unless the file or decomposer changed. Unchanged text keeps its IDs."""
    stored = load_tree(doc_id)
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()
    if stored is not None and stored.content_hash == content_hash and stored.decomposer_version == DECOMPOSER_VERSION:
        return stored
    tree = decompose_pdf(pdf_bytes, doc_id, title)
    save_tree(tree)
    return tree


async def decompose_book(
    pdf_bytes: bytes,
    *,
    doc_id: UUID,
    job_id: UUID,
    title: str,
    pack_type: KnowledgePackType,
    extractor: WindowExtractor,
    review_model: ReviewModel,
    guard: RunGuard,
    run_key: str,
    accept_run: Callable[[str], bool],
    coverage_model: CoverageModel | None = None,
    check_coverage: bool = False,
    concurrency: int = 4,
    on_progress: Callable[[DecompositionProgress], None] | None = None,
    graph_model: GraphModel | None = None,
    on_tree: Callable[[BookTree], Awaitable[None]] | None = None,
) -> DecomposeResult:
    """Decompose a book and create its review-pending pack. Safe to call repeatedly."""
    key = str(doc_id)
    tree = _load_or_build_tree(pdf_bytes, key, title)
    if on_tree is not None:
        await on_tree(tree)
    windows = build_windows(tree)
    expected = {unit.node_id for window in windows for unit in window.units}
    outcome_log = MongoExtractionLog(key)
    progress = DecompositionProgress(sentences_total=len(expected))

    def publish() -> None:
        if on_progress is not None:
            on_progress(progress)

    done: set[str] = set()

    def on_saved(outcome: WindowOutcome) -> None:
        done.update(outcome.cited, outcome.skipped)
        progress.sentences_done = len(done & expected)
        publish()

    with outcome_log.exclusive():
        extraction = await run_until_settled(
            windows,
            extractor,
            outcome_log,
            guard,
            run_key=run_key,
            accept_run=accept_run,
            concurrency=concurrency,
            on_saved=on_saved,
        )
        done = set(extraction.states.done)
        progress.sentences_done = len(done)
        progress.sentences_quarantined = len(extraction.states.quarantined)
        if extraction.status == IngestStatus.PAUSED:
            progress.pause_reason = extraction.pause_reason
            publish()
            return DecomposeResult(DecomposeStatus.PAUSED, progress)
        publish()

        outcomes = [o for o in outcome_log.read() if accept_run(o.run_key)]
        try:
            review = await review_claims(
                tree,
                outcomes,
                review_model,
                concurrency=concurrency,
                check_log=MongoCheckLog(key, verification_fingerprint()),
                check_coverage=check_coverage,
                coverage_model=coverage_model,
                coverage_log=MongoCoverageLog(key, coverage_fingerprint()),
            )
        except RunStopped as exc:
            progress.pause_reason = str(exc)
            publish()
            return DecomposeResult(DecomposeStatus.PAUSED, progress)
        save_review(key, review)
        domains = {claim.id: claim.domain for claim in review.claims}
        if graph_model is not None:
            try:
                graphs, domains = await build_graphs(
                    review.claims,
                    graph_model,
                    MongoGraphLog(key, graph_fingerprint()),
                    concurrency=concurrency,
                )
            except RunStopped as exc:
                progress.pause_reason = str(exc)
                publish()
                return DecomposeResult(DecomposeStatus.PAUSED, progress)
            save_graphs(key, graphs, domains)
        save_domain_trees(
            key,
            {domain: build_domain_tree(tree, review.claims, domains, domain) for domain in ("rules", "lore")},
        )

        mapped = map_claims(review.claims, tree)
        if mapped.held_back:
            mongodb_upsert_book_records(
                key,
                BookRecordType.REPORT,
                [BookRecord(key="held_back", data={"claims": mapped.held_back})],
            )
        # A fixed ID, so a crash just after creating the pack can't create a second one.
        pack_id = uuid5(NAMESPACE_URL, f"book-decomposition:{key}")
        if mongodb_get_knowledge_pack(pack_id) is None:
            mongodb_create_knowledge_pack(
                build_pack(
                    mapped,
                    pack_id=pack_id,
                    name=title,
                    pack_type=pack_type,
                    source_document_id=doc_id,
                    job_id=job_id,
                )
            )
    progress.claims_kept = len(review.claims)
    progress.claims_held_back = len(mapped.held_back)
    publish()
    status = DecomposeStatus.COMPLETE_WITH_QUARANTINE if extraction.states.quarantined else DecomposeStatus.COMPLETE
    return DecomposeResult(status, progress, pack_id, review.report)
