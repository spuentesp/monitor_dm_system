"""MongoDB backends for book decomposition progress (I-17).

These match the file logs in `ledger.py` and `review.py`, so the extraction loop and the review
work the same on either one.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import structlog
from monitor_data.schemas.book_graph import (
    BookNode,
    BookRecord,
    BookRecordType,
    BookTree,
    ClaimCheck,
    DecompositionReport,
    ParagraphGap,
)
from monitor_data.tools.mongodb_tools.book_decomposition import (
    mongodb_acquire_book_lease,
    mongodb_list_book_records,
    mongodb_release_book_lease,
    mongodb_upsert_book_records,
)
from pydantic import ValidationError

from monitor_agents.book_decomposition.ledger import LogBusy
from monitor_agents.book_decomposition.pipeline import WindowOutcome
from monitor_agents.book_decomposition.review import ReviewResult

log = structlog.get_logger()

LEASE_SECONDS = 300.0
_TREE_META_KEY = "meta"


class MongoExtractionLog:
    """Window outcomes in MongoDB. A retried window's new outcome is kept beside the old one."""

    def __init__(
        self,
        doc_id: str,
        *,
        lease_seconds: float = LEASE_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.doc_id = doc_id
        self._lease_seconds = lease_seconds
        self._clock = clock
        self._owner = uuid.uuid4().hex

    def append(self, outcome: WindowOutcome) -> None:
        data = outcome.model_dump(mode="json")
        key = hashlib.sha256(outcome.model_dump_json().encode()).hexdigest()[:32]
        mongodb_upsert_book_records(
            self.doc_id, BookRecordType.OUTCOME, [BookRecord(key=key, data=data)]
        )

    def read(self) -> list[WindowOutcome]:
        return [
            WindowOutcome.model_validate(record.data)
            for record in mongodb_list_book_records(self.doc_id, BookRecordType.OUTCOME)
        ]

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Hold the document's lease, renewing it until the work ends or the process dies."""
        if not mongodb_acquire_book_lease(
            self.doc_id, self._owner, self._lease_seconds, now=self._clock()
        ):
            raise LogBusy(f"Another run is working on document {self.doc_id}")
        stop = threading.Event()

        def renew() -> None:
            while not stop.wait(self._lease_seconds / 3):
                try:
                    mongodb_acquire_book_lease(
                        self.doc_id, self._owner, self._lease_seconds, now=self._clock()
                    )
                except Exception as exc:  # noqa: BLE001  # reason: the next renewal retries; a lost lease only risks repeated work, since writes are idempotent
                    log.warning("book_lease_renew_failed", error=str(exc)[:200])

        renewer = threading.Thread(target=renew, daemon=True)
        renewer.start()
        try:
            yield
        finally:
            stop.set()
            renewer.join(timeout=5)
            mongodb_release_book_lease(self.doc_id, self._owner)


class _MongoKeyedLog:
    """Shared by the check and coverage logs: records scoped to one prompt's fingerprint."""

    record_type: BookRecordType

    def __init__(self, doc_id: str, fingerprint: str) -> None:
        self.doc_id = doc_id
        self.prefix = f"{fingerprint}:"

    def _read_rows(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (record.key.removeprefix(self.prefix), record.data)
            for record in mongodb_list_book_records(self.doc_id, self.record_type)
            if record.key.startswith(self.prefix)
        ]

    def _write(self, rows: dict[str, dict[str, Any]]) -> None:
        if rows:
            mongodb_upsert_book_records(
                self.doc_id,
                self.record_type,
                [BookRecord(key=self.prefix + key, data=data) for key, data in rows.items()],
            )


class MongoCheckLog(_MongoKeyedLog):
    """Finished verifier checks, per claim."""

    record_type = BookRecordType.CHECK

    def read(self) -> dict[str, ClaimCheck]:
        return {key: ClaimCheck.model_validate(data) for key, data in self._read_rows()}

    def append(self, checks: dict[str, ClaimCheck]) -> None:
        self._write({key: check.model_dump(mode="json") for key, check in checks.items()})


class MongoCoverageLog(_MongoKeyedLog):
    """Finished paragraph coverage checks, per paragraph and its claims."""

    record_type = BookRecordType.COVERAGE

    def read(self) -> dict[str, list[ParagraphGap]]:
        saved: dict[str, list[ParagraphGap]] = {}
        for key, data in self._read_rows():
            try:
                saved[key] = [ParagraphGap.model_validate(gap) for gap in data["gaps"]]
            except (KeyError, TypeError, ValidationError):
                log.warning("coverage_record_invalid", doc_id=self.doc_id, key=key)
        return saved

    def append(self, finished: dict[str, list[ParagraphGap]]) -> None:
        self._write(
            {
                key: {"gaps": [gap.model_dump(mode="json") for gap in gaps]}
                for key, gaps in finished.items()
            }
        )


def save_tree(tree: BookTree) -> None:
    """Store a tree's nodes and details, so a resumed run needn't parse the PDF again."""
    mongodb_upsert_book_records(
        tree.doc_id,
        BookRecordType.NODE,
        [BookRecord(key=node.id, data=node.model_dump(mode="json")) for node in tree.nodes],
    )
    meta = tree.model_dump(mode="json", exclude={"nodes"})
    mongodb_upsert_book_records(
        tree.doc_id, BookRecordType.TREE_META, [BookRecord(key=_TREE_META_KEY, data=meta)]
    )


def load_tree(doc_id: str) -> BookTree | None:
    """Load a stored tree, or None if there isn't a complete one.

    Details are written last, so their presence means every node was saved.
    """
    metas = mongodb_list_book_records(doc_id, BookRecordType.TREE_META)
    if not metas:
        return None
    nodes = [
        BookNode.model_validate(record.data)
        for record in mongodb_list_book_records(doc_id, BookRecordType.NODE)
    ]
    nodes.sort(key=lambda node: node.seq)
    data = metas[0].data
    return BookTree(
        doc_id=data["doc_id"],
        title=data["title"],
        decomposer_version=data["decomposer_version"],
        content_hash=data["content_hash"],
        nodes=nodes,
        report=DecompositionReport.model_validate(data["report"]),
    )


def save_review(doc_id: str, result: ReviewResult) -> None:
    """Store a finished review: kept claims, every claim's outcome, and the report."""
    mongodb_upsert_book_records(
        doc_id,
        BookRecordType.CLAIM,
        [BookRecord(key=claim.id, data=claim.model_dump(mode="json")) for claim in result.claims],
    )
    mongodb_upsert_book_records(
        doc_id,
        BookRecordType.LEDGER,
        [
            BookRecord(key=entry.claim_id, data=entry.model_dump(mode="json"))
            for entry in result.ledger
        ],
    )
    mongodb_upsert_book_records(
        doc_id,
        BookRecordType.REPORT,
        [BookRecord(key="review", data=result.report.model_dump(mode="json"))],
    )
