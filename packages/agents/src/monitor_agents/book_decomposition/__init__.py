"""Exhaustive book → atoms extraction (prototype).

See docs/architecture/BOOK_DECOMPOSITION_PLAN.md.
"""

from monitor_agents.book_decomposition.estimate import CallEstimate, estimate_calls
from monitor_agents.book_decomposition.extractor import DspyWindowExtractor
from monitor_agents.book_decomposition.ledger import ExtractionLog, LogBusy, reconcile
from monitor_agents.book_decomposition.pacing import RunGuard, RunStopped
from monitor_agents.book_decomposition.pipeline import (
    CoverageReport,
    WindowOutcome,
    build_coverage_report,
    extract_windows,
    validate_extraction,
)
from monitor_agents.book_decomposition.runner import (
    IngestResult,
    IngestStatus,
    plan_windows,
    run_until_settled,
)
from monitor_agents.book_decomposition.settings import OLD, DecompositionSettings
from monitor_agents.book_decomposition.windows import Unit, Window, build_windows, non_content_counts, plan_non_content

__all__ = [
    "OLD",
    "CallEstimate",
    "CoverageReport",
    "DecompositionSettings",
    "DspyWindowExtractor",
    "ExtractionLog",
    "IngestResult",
    "IngestStatus",
    "LogBusy",
    "RunGuard",
    "RunStopped",
    "Unit",
    "Window",
    "WindowOutcome",
    "build_coverage_report",
    "build_windows",
    "estimate_calls",
    "non_content_counts",
    "plan_non_content",
    "plan_windows",
    "reconcile",
    "run_until_settled",
    "extract_windows",
    "validate_extraction",
]
