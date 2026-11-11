"""Estimate model calls per stage without a model, and the script that prints it (I-17, task 10)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from monitor_agents.book_decomposition.calls import STAGES
from monitor_agents.book_decomposition.estimate import CallEstimate, estimate_calls
from monitor_agents.book_decomposition.settings import OLD, DecompositionSettings
from monitor_agents.book_decomposition.windows import build_windows
from monitor_data.schemas.book_graph import (
    BookNode,
    BookNodeKind,
    BookTree,
    DecompositionReport,
)

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "ingestion" / "tiny_rulebook.pdf"


def _tree(paragraphs: int) -> BookTree:
    """One division, `paragraphs` paragraphs of two words, one sentence each."""
    nodes = [
        BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0),
        BookNode(
            id="div",
            doc_id="d",
            kind=BookNodeKind.DIVISION,
            parent_id="root",
            seq=1,
            text="C",
            page_start=0,
            page_end=0,
        ),
    ]
    for i in range(paragraphs):
        text = f"word{i}a word{i}b"
        nodes.append(
            BookNode(
                id=f"p{i}",
                doc_id="d",
                kind=BookNodeKind.PARAGRAPH,
                parent_id="div",
                seq=len(nodes),
                text=text,
                page_start=0,
                page_end=0,
            )
        )
        nodes.append(
            BookNode(
                id=f"s{i}",
                doc_id="d",
                kind=BookNodeKind.SENTENCE,
                parent_id=f"p{i}",
                seq=len(nodes),
                text=text,
                page_start=0,
                page_end=0,
            )
        )
    return BookTree(
        doc_id="d", title="T", decomposer_version="1", content_hash="x", nodes=nodes, report=DecompositionReport()
    )


_EXPLICIT = DecompositionSettings(
    window_words=10_000,
    review_batch=4,
    graph_batch=5,
    coverage_batch=2,
    coverage_sample=0.5,
    coverage_min_paragraphs=0,
    skip_audit_batch=3,
    claims_per_sentence=1.0,
    skip_share=0.5,
    stack_share=0.5,
    paragraph_keep_share=1.0,
    zero_division_share=0.0,
)


@pytest.mark.unit
def test_estimate_counts_every_stage_from_the_tree_alone():
    tree = _tree(10)
    estimate = estimate_calls(tree, settings=_EXPLICIT, graph_enabled=True, coverage_enabled=True)
    # 1 window of 10 units; 10 claims at 4 per call = 3; 5 skipped at 3 per call = 2;
    # 5 stacked claims at 12 per call = 1; 5 sampled paragraphs at 2 per call = 3;
    # 10 claims at 5 per call = 2 plus 2 merge calls.
    assert estimate == CallEstimate(extraction=1, verification=3, skip_audit=2, stacking=1, coverage=3, graph=4)
    assert estimate.total == 14
    assert set(estimate.as_dict()) == set(STAGES)


@pytest.mark.unit
def test_estimate_uses_the_verbatim_windows_the_run_would_use():
    tree = _tree(10)
    windows = build_windows(tree, settings=_EXPLICIT)
    estimate = estimate_calls(tree, windows=windows, settings=_EXPLICIT, graph_enabled=False, coverage_enabled=False)
    assert estimate.extraction == len(windows)


@pytest.mark.unit
def test_old_defaults_estimate_more_calls_than_the_new_ones():
    tree = _tree(100)  # Enough claims that the batch sizes show.
    new = estimate_calls(tree, settings=DecompositionSettings(), graph_enabled=False, coverage_enabled=False)
    old = estimate_calls(tree, settings=OLD, graph_enabled=False, coverage_enabled=False)
    assert old.verification == 9  # ceil(100 claims / 12 per call, the old batch.
    assert new.verification == 2  # ceil(100 claims / 64 per call, the new default.
    assert old.total > new.total


@pytest.mark.unit
def test_environment_overrides_change_the_estimate(monkeypatch):
    tree = _tree(10)
    base = estimate_calls(tree, settings=_EXPLICIT, graph_enabled=False, coverage_enabled=False)
    monkeypatch.setenv("MONITOR_BOOK_REVIEW_BATCH", "5")
    monkeypatch.setenv("MONITOR_BOOK_GRAPH_BATCH", "3")
    changed = estimate_calls(
        tree, settings=DecompositionSettings.from_env(), graph_enabled=True, coverage_enabled=False
    )
    assert changed.verification != base.verification
    assert changed.graph >= 1 + 2  # ceil(units / 3) plus the two merge calls.


@pytest.mark.unit
def test_graph_and_coverage_follow_their_flags():
    tree = _tree(10)
    off = estimate_calls(tree, settings=_EXPLICIT, graph_enabled=False, coverage_enabled=False)
    on = estimate_calls(tree, settings=_EXPLICIT, graph_enabled=True, coverage_enabled=True)
    assert off.graph == 0 and off.coverage == 0
    assert on.graph > 0 and on.coverage > 0


@pytest.mark.unit
def test_script_prints_current_and_old_estimates_without_a_model():
    env = dict(os.environ)
    env.pop("MONITOR_BOOK_GRAPH", None)
    env.pop("MONITOR_BOOK_COVERAGE", None)
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "estimate_book_calls.py"), str(FIXTURE)],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert "Current settings: total=" in done.stdout
    assert "OLD defaults (before phase 5a): total=" in done.stdout
    assert "extraction" in done.stdout and "verification" in done.stdout
    assert "window_words=600" in done.stdout  # The old comparison really used the old numbers.
    assert "Difference (old - new):" in done.stdout
