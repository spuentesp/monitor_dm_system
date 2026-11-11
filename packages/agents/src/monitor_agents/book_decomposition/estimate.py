"""Estimate the model calls a decomposition will make, with no model call (I-17, task 10).

Everything here is counted from the book's own tree and the current settings:
windows are exact, and the rest are the book's yield (claims, skips, paragraphs)
times the batch size each stage sends. The yield numbers are named settings with
documented defaults (`MONITOR_BOOK_CLAIMS_PER_SENTENCE` and friends) — they are
proxies until a real run measures them, and `scripts/estimate_book_calls.py`
prints this estimate beside the old-defaults one.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

from monitor_data.schemas.book_graph import BookNodeKind, BookTree

from monitor_agents.book_decomposition.review import DEFAULT_MAX_CLUSTER
from monitor_agents.book_decomposition.settings import DecompositionSettings
from monitor_agents.book_decomposition.windows import Window, build_windows, plan_non_content

_GRAPH_MERGE_CALLS = 2  # One find_duplicates per domain, rules and lore.


def _ceil_div(count: int, batch: int) -> int:
    if count <= 0 or batch <= 0:
        return 0
    return math.ceil(count / batch)


@dataclass(frozen=True)
class CallEstimate:
    """Calls per stage, in the same stage names the run's tally uses."""

    extraction: int = 0
    verification: int = 0
    skip_audit: int = 0
    stacking: int = 0
    coverage: int = 0
    graph: int = 0

    @property
    def total(self) -> int:
        return self.extraction + self.verification + self.skip_audit + self.stacking + self.coverage + self.graph

    def as_dict(self) -> dict[str, int]:
        return {
            "extraction": self.extraction,
            "verification": self.verification,
            "skip_audit": self.skip_audit,
            "stacking": self.stacking,
            "coverage": self.coverage,
            "graph": self.graph,
        }


def _graph_enabled() -> bool:
    return os.environ.get("MONITOR_BOOK_GRAPH", "0") == "1"


def _coverage_enabled() -> bool:
    return os.environ.get("MONITOR_BOOK_COVERAGE", "0") == "1"


def estimate_calls(
    tree: BookTree,
    *,
    windows: list[Window] | None = None,
    settings: DecompositionSettings | None = None,
    graph_enabled: bool | None = None,
    coverage_enabled: bool | None = None,
) -> CallEstimate:
    """Count the calls this book will take under `settings`, without running a model.

    `windows` can be passed in when the caller already built them with the same
    settings, so the extraction count is the very list the run will use.
    """
    s = settings or DecompositionSettings.from_env()
    if graph_enabled is None:
        graph_enabled = _graph_enabled()
    if coverage_enabled is None:
        coverage_enabled = _coverage_enabled()
    if windows is None:
        windows = build_windows(tree, settings=s)

    extraction = len(windows)
    units = sum(len(window.units) for window in windows)
    claims = round(units * s.claims_per_sentence)
    verification = _ceil_div(claims, s.review_batch)
    skipped = round(units * s.skip_share)
    skip_audit = _ceil_div(skipped, s.skip_audit_batch)
    stacking = _ceil_div(round(claims * s.stack_share), DEFAULT_MAX_CLUSTER)

    skipped_nodes = plan_non_content(tree, s)
    paragraphs = sum(node.kind == BookNodeKind.PARAGRAPH and node.id not in skipped_nodes for node in tree.nodes)
    auditable = round(paragraphs * s.paragraph_keep_share)
    sampled = auditable if auditable < s.coverage_min_paragraphs else round(auditable * s.coverage_sample)
    zero_claim = round(paragraphs * s.zero_division_share)
    coverage = _ceil_div(sampled + zero_claim, s.coverage_batch) if coverage_enabled else 0

    graph = 0
    if graph_enabled and claims:
        graph = _ceil_div(claims, s.graph_batch) + _GRAPH_MERGE_CALLS

    return CallEstimate(
        extraction=extraction,
        verification=verification,
        skip_audit=skip_audit,
        stacking=stacking,
        coverage=coverage,
        graph=graph,
    )
