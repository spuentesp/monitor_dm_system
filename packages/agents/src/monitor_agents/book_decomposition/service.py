"""Run a whole book through decomposition, resumably (I-17).

Tree, extraction and review each pick up from what's stored, so calling this again after a crash
or a pause only does what's missing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

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

from monitor_agents.book_decomposition.calls import CallTally, tallying_extractor, tallying_graph, tallying_review
from monitor_agents.book_decomposition.estimate import CallEstimate, estimate_calls
from monitor_agents.book_decomposition.extractor import WindowExtractor
from monitor_agents.book_decomposition.held_claims import (
    accepted_claims,
    build_trees,
    load_decisions,
    open_count,
    pack_id_for,
)
from monitor_agents.book_decomposition.knowledge_graph import (
    GraphModel,
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
from monitor_agents.book_decomposition.settings import DecompositionSettings
from monitor_agents.book_decomposition.store import (
    MongoCheckLog,
    MongoCoverageLog,
    MongoExtractionLog,
    MongoGraphLog,
    load_tree,
    save_domain_trees,
    save_graphs,
    save_non_content_report,
    save_review,
    save_tree,
)
from monitor_agents.book_decomposition.windows import build_windows, non_content_counts, plan_non_content

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
    # Every batch that was refused or never completed: section_path, stage, reason.
    held: list[dict[str, str]] = field(default_factory=list)
    # Model calls actually made, by stage, beside the estimate made before the run.
    calls: dict[str, int] = field(default_factory=dict)
    estimate: dict[str, int] | None = None
    # What never went to the model because the tree marks it as non-content (task 9).
    skipped_non_content: dict[str, int] = field(default_factory=dict)


def _extraction_held(outcomes: list[WindowOutcome], quarantined: set[str]) -> list[dict[str, str]]:
    """Quarantined units, each with the content failure that kept it from finishing."""
    reasons: dict[str, str] = {}
    for outcome in outcomes:
        if not outcome.errors:
            continue
        for unit_id in outcome.uncovered:
            if unit_id in quarantined and unit_id not in reasons:
                reasons[unit_id] = outcome.errors[-1]
    return [
        {
            "section_path": unit_id,
            "stage": "extraction",
            "reason": reasons.get(unit_id, "Content failure repeated; the unit was quarantined"),
        }
        for unit_id in sorted(quarantined)
    ]


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
    on_estimate: Callable[[CallEstimate], None] | None = None,
) -> DecomposeResult:
    """Decompose a book and create its review-pending pack. Safe to call repeatedly."""
    key = str(doc_id)
    settings = DecompositionSettings.from_env()
    tree = _load_or_build_tree(pdf_bytes, key, title)
    if on_tree is not None:
        await on_tree(tree)
    windows = build_windows(tree, settings=settings)
    estimate = estimate_calls(tree, windows=windows, settings=settings)
    if on_estimate is not None:
        on_estimate(estimate)
    skipped_reasons = plan_non_content(tree, settings)
    skipped_counts = non_content_counts(skipped_reasons)
    if skipped_counts:
        save_non_content_report(key, skipped_counts, skipped_reasons)
        log.info("book_non_content_skipped", doc_id=key, counts=skipped_counts)
    expected = {unit.node_id for window in windows for unit in window.units}
    outcome_log = MongoExtractionLog(key)
    progress = DecompositionProgress(sentences_total=len(expected))
    tally = CallTally()

    def publish() -> None:
        if on_progress is not None:
            on_progress(progress)

    def result(
        status: DecomposeStatus,
        *,
        pack_id: UUID | None = None,
        report: ReviewReport | None = None,
        held: list[dict[str, str]] | None = None,
    ) -> DecomposeResult:
        return DecomposeResult(
            status,
            progress,
            pack_id,
            report,
            held=[
                *_extraction_held([o for o in outcome_log.read() if accept_run(o.run_key)], _quarantined),
                *(held or []),
            ],
            calls=tally.as_dict(),
            estimate=estimate.as_dict(),
            skipped_non_content=skipped_counts,
        )

    done: set[str] = set()

    def on_saved(outcome: WindowOutcome) -> None:
        done.update(outcome.cited, outcome.skipped)
        progress.sentences_done = len(done & expected)
        publish()

    _quarantined: set[str] = set()
    with outcome_log.exclusive():
        extraction = await run_until_settled(
            windows,
            tallying_extractor(extractor, tally),
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
        _quarantined = set(extraction.states.quarantined)
        if extraction.status == IngestStatus.PAUSED:
            progress.pause_reason = extraction.pause_reason
            publish()
            return result(DecomposeStatus.PAUSED)
        publish()

        outcomes = [o for o in outcome_log.read() if accept_run(o.run_key)]
        try:
            review = await review_claims(
                tree,
                outcomes,
                tallying_review(review_model, tally),
                concurrency=concurrency,
                check_log=MongoCheckLog(key, verification_fingerprint()),
                check_coverage=check_coverage,
                coverage_model=tallying_review(coverage_model, tally) if coverage_model is not None else None,
                coverage_log=MongoCoverageLog(key, coverage_fingerprint()),
            )
        except RunStopped as exc:
            progress.pause_reason = str(exc)
            publish()
            return result(DecomposeStatus.PAUSED)
        save_review(key, review)
        held = [dict(entry) for entry in review.report.held]
        domains = {claim.id: claim.domain for claim in review.claims}
        if graph_model is not None:
            try:
                graphs, domains = await build_graphs(
                    review.claims,
                    tallying_graph(graph_model, tally),
                    MongoGraphLog(key, graph_fingerprint()),
                    concurrency=concurrency,
                    held_sink=held,
                )
            except RunStopped as exc:
                progress.pause_reason = str(exc)
                publish()
                return result(DecomposeStatus.PAUSED)
            save_graphs(key, graphs, domains)
        decisions = load_decisions(key)
        claims = [*review.claims, *accepted_claims(review.ledger, decisions, tree)]
        save_domain_trees(key, build_trees(tree, claims, domains))
        mapped = map_claims(claims, tree)
        if mapped.held_back:
            mongodb_upsert_book_records(
                key,
                BookRecordType.REPORT,
                [BookRecord(key="held_back", data={"claims": mapped.held_back})],
            )
        pack_id = pack_id_for(key)
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
    progress.claims_for_review = open_count(review.ledger, decisions)
    publish()
    status = DecomposeStatus.COMPLETE_WITH_QUARANTINE if extraction.states.quarantined else DecomposeStatus.COMPLETE
    return result(status, pack_id=pack_id, report=review.report, held=held)
