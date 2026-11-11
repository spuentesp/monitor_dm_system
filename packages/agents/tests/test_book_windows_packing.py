"""Window packing across headings and divisions, and what never gets sent (I-17, tasks 5 and 9)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from monitor_agents.book_decomposition import plan_windows, settings as settings_mod
from monitor_agents.book_decomposition.extractor import format_units
from monitor_agents.book_decomposition.windows import (
    build_windows,
    non_content_counts,
    plan_non_content,
    window_id,
)
from monitor_agents.book_decomposition.settings import OLD, DecompositionSettings
from monitor_data.schemas.book_graph import (
    BookNode,
    BookNodeKind,
    BookTree,
    DecompositionReport,
)


def _node(kind, node_id, *, parent=None, text="", seq=0) -> BookNode:
    return BookNode(
        id=node_id,
        doc_id="d",
        kind=kind,
        parent_id=parent,
        seq=seq,
        text=text,
        page_start=0,
        page_end=0,
    )


def _tree(nodes: list[BookNode]) -> BookTree:
    return BookTree(
        doc_id="d", title="T", decomposer_version="1", content_hash="x", nodes=nodes, report=DecompositionReport()
    )


def _paragraphs(parent: str, start: int, count: int, words: int = 4) -> list[BookNode]:
    nodes = []
    for i in range(count):
        node_id = f"{parent}-p{i}"
        text = " ".join(f"word{i}x{j}" for j in range(words))
        nodes.append(_node(BookNodeKind.PARAGRAPH, node_id, parent=parent, text=text, seq=start + i * 2))
        nodes.append(_node(BookNodeKind.SENTENCE, f"{node_id}s0", parent=node_id, text=text, seq=start + i * 2 + 1))
    return nodes


def _two_divisions() -> BookTree:
    """root → Chapter One (heading A, two paragraphs), Chapter Two (heading B, two paragraphs)."""
    nodes = [
        _node(BookNodeKind.BOOK, "root", text="Book"),
        _node(BookNodeKind.DIVISION, "d1", parent="root", text="Chapter One", seq=1),
        _node(BookNodeKind.HEADING, "h1", parent="d1", text="A", seq=2),
        *_paragraphs("d1", 3, 2),
        _node(BookNodeKind.DIVISION, "d2", parent="root", text="Chapter Two", seq=7),
        _node(BookNodeKind.HEADING, "h2", parent="d2", text="B", seq=8),
        *_paragraphs("d2", 9, 2),
    ]
    return _tree(nodes)


@pytest.mark.unit
def test_a_window_spans_headings_and_divisions_up_to_the_budget():
    windows = build_windows(_two_divisions(), max_words=100, settings=DecompositionSettings())
    assert len(windows) == 1
    divisions = {unit.node_id.split("-")[0] for unit in windows[0].units}
    assert divisions == {"d1", "d2"}
    paths = {unit.heading_path for unit in windows[0].units}
    assert ("Chapter One", "A") in paths
    assert ("Chapter Two", "B") in paths


@pytest.mark.unit
def test_the_word_budget_still_splits_a_long_run_of_paragraphs():
    nodes = [_node(BookNodeKind.BOOK, "root"), _node(BookNodeKind.DIVISION, "d1", parent="root", text="C")]
    nodes += _paragraphs("d1", 2, 6, words=4)  # 6 paragraphs of 4 words.
    windows = build_windows(_tree(nodes), max_words=9, settings=DecompositionSettings())
    assert [len(window.units) for window in windows] == [2, 2, 2]


@pytest.mark.unit
def test_headings_mode_restores_the_old_behaviour():
    """The old default (a new window at every heading) stays reachable for side-by-side runs."""
    nodes = [
        _node(BookNodeKind.BOOK, "root"),
        _node(BookNodeKind.DIVISION, "d1", parent="root", text="C"),
        _node(BookNodeKind.PARAGRAPH, "p0", parent="d1", text="one two three four five six"),
        _node(BookNodeKind.SENTENCE, "p0s0", parent="p0", text="one two three four five six", seq=2),
        _node(BookNodeKind.HEADING, "h", parent="d1", text="Sub", seq=3),
        _node(BookNodeKind.PARAGRAPH, "p1", parent="d1", text="seven eight nine ten"),
        _node(BookNodeKind.SENTENCE, "p1s0", parent="p1", text="seven eight nine ten", seq=5),
        _node(BookNodeKind.PARAGRAPH, "p2", parent="d1", text="a b c d"),
        _node(BookNodeKind.SENTENCE, "p2s0", parent="p2", text="a b c d", seq=7),
    ]
    tree = _tree(nodes)
    packed = build_windows(tree, max_words=50, break_at="budget", settings=DecompositionSettings())
    legacy = build_windows(tree, max_words=50, break_at="headings", settings=DecompositionSettings())
    assert len(packed) == 1  # Packed: the heading doesn't break anything.
    assert [len(window.units) for window in legacy] == [1, 2]  # Old: the heading starts a new window.


@pytest.mark.unit
def test_window_id_comes_only_from_the_unit_ids():
    """A run resumed under different settings still keys its saved outcomes the same way."""
    [packed] = build_windows(_two_divisions(), max_words=100, settings=DecompositionSettings())
    # The heading a unit carries can't change its window's identity.
    altered = tuple(replace(unit, heading_path=("Somewhere", "Else")) for unit in packed.units)
    assert window_id(packed.units) == window_id(altered)
    # A resumed run narrows the window to what is still pending and recomputes the id from that.
    pending = {unit.node_id for unit in packed.units[:2]}
    [planned] = plan_windows([packed], pending)
    assert {unit.node_id for unit in planned.units} == pending
    assert planned.id == window_id(planned.units)


@pytest.mark.unit
def test_format_units_shows_each_units_own_heading():
    [window] = build_windows(_two_divisions(), max_words=100, settings=DecompositionSettings())
    formatted = format_units(window)
    assert "[S1] (Chapter One > A)" in formatted
    assert "[S3] (Chapter Two > B)" in formatted


@pytest.mark.unit
def test_non_content_is_skipped_and_reported():
    nodes = [
        _node(BookNodeKind.BOOK, "root"),
        _node(BookNodeKind.PARAGRAPH, "fm", parent="root", text="Credits and legal text."),
        _node(BookNodeKind.SENTENCE, "fms", parent="fm", text="Credits and legal text.", seq=1),
        _node(BookNodeKind.DIVISION, "toc", parent="root", text="CONTENTS", seq=2),
        _node(BookNodeKind.PARAGRAPH, "tocp", parent="toc", text="Chapter One ... 3"),
        _node(BookNodeKind.SENTENCE, "tocps", parent="tocp", text="Chapter One ... 3", seq=4),
        _node(BookNodeKind.DIVISION, "d1", parent="root", text="Chapter One", seq=5),
        _node(BookNodeKind.PARAGRAPH, "p0", parent="d1", text="Roll two dice."),
        _node(BookNodeKind.SENTENCE, "p0s0", parent="p0", text="Roll two dice.", seq=7),
        _node(BookNodeKind.FURNITURE, "furn", parent="d1", text="Page 3", seq=8),
    ]
    tree = _tree(nodes)
    reasons = plan_non_content(tree, DecompositionSettings())
    assert reasons["fm"] == "front_matter"
    assert reasons["tocp"] == "non_content_division"
    assert reasons["furn"] == "furniture"
    assert non_content_counts(reasons) == {"front_matter": 1, "non_content_division": 1, "furniture": 1}

    windows = build_windows(tree, max_words=1000, settings=DecompositionSettings())
    sent = [unit.node_id for window in windows for unit in window.units]
    assert sent == ["p0s0"]  # Only real content goes to the model.

    off = DecompositionSettings(skip_non_content=False)
    reasons_off = plan_non_content(tree, off)
    assert set(reasons_off) == {"furn"}  # Furniture is marked by the decomposer itself, always skipped.
    windows_off = build_windows(tree, max_words=1000, settings=off)
    sent_off = [unit.node_id for window in windows_off for unit in window.units]
    assert sent_off == ["fms", "tocps", "p0s0"]


@pytest.mark.unit
def test_every_setting_reads_the_environment_with_its_old_value_reachable(monkeypatch):
    monkeypatch.setenv(settings_mod.WINDOW_WORDS, "600")
    monkeypatch.setenv(settings_mod.WINDOW_BREAK, "headings")
    monkeypatch.setenv(settings_mod.REVIEW_BATCH, "12")
    monkeypatch.setenv(settings_mod.GRAPH_BATCH, "30")
    monkeypatch.setenv(settings_mod.COVERAGE_BATCH, "8")
    monkeypatch.setenv(settings_mod.COVERAGE_SAMPLE, "1.0")
    monkeypatch.setenv(settings_mod.SKIP_NON_CONTENT, "0")
    monkeypatch.setenv(settings_mod.EXTRACT_MAX_TOKENS, "16384")
    current = DecompositionSettings.from_env()
    assert current.window_words == OLD.window_words == 600
    assert current.window_break == OLD.window_break == "headings"
    assert current.review_batch == OLD.review_batch == 12
    assert current.graph_batch == OLD.graph_batch == 30
    assert current.coverage_batch == OLD.coverage_batch == 8
    assert current.coverage_sample == OLD.coverage_sample == 1.0
    assert current.skip_non_content is OLD.skip_non_content is False
    assert current.extract_max_tokens == OLD.extract_max_tokens == 16384


@pytest.mark.unit
def test_new_defaults_are_the_documented_ones():
    fresh = DecompositionSettings()
    assert fresh.window_words == 3000
    assert fresh.window_break == "budget"
    assert 60 <= fresh.review_batch <= 80
    assert fresh.graph_batch == 150
    assert fresh.coverage_sample == 0.10
    assert fresh.extract_max_tokens == 32768
    assert fresh.skip_non_content is True


@pytest.mark.unit
def test_outcomes_saved_under_old_windows_settle_a_new_settings_run(tmp_path):
    """A run started before this phase resumes without repeating a finished window (task 5)."""
    from monitor_agents.book_decomposition import ExtractionLog, reconcile
    from monitor_agents.book_decomposition.pipeline import WindowOutcome

    tree = _two_divisions()
    old_windows = build_windows(tree, max_words=100, break_at="headings", settings=DecompositionSettings())
    finished = {unit.node_id for unit in old_windows[0].units}
    log = ExtractionLog(tmp_path / "log.jsonl")
    log.append(WindowOutcome(window_id=old_windows[0].id, cited=sorted(finished)))

    new_windows = build_windows(tree, max_words=100, settings=DecompositionSettings())
    expected = {unit.node_id for window in new_windows for unit in window.units}
    states = reconcile(expected, log.read())
    assert states.done == finished
    assert states.pending == expected - finished
    planned = plan_windows(new_windows, states.pending)
    # The new-settings run sends only what the old-settings run never finished.
    assert {unit.node_id for window in planned for unit in window.units} == states.pending
