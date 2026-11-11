"""The Analyzer estimate counts the batched stages from the settings and the book tree (I-17)."""

from __future__ import annotations

import pytest
from monitor_data.schemas.book_graph import BookNode, BookNodeKind, BookTree

from monitor_agents.analyzer.estimate import estimate_analyzer_calls, section_word_counts


def _node(kind: BookNodeKind, node_id: str, *, parent: str | None = None, text: str = "", seq: int = 0) -> BookNode:
    return BookNode(id=node_id, doc_id="doc", kind=kind, parent_id=parent, seq=seq, text=text, page_start=0, page_end=0)


def _tree(section_words: list[int]) -> BookTree:
    nodes = [_node(BookNodeKind.BOOK, "book", text="Book")]
    for index, words in enumerate(section_words):
        division = f"d{index}"
        nodes.append(_node(BookNodeKind.DIVISION, division, parent="book", text=f"Section {index}", seq=2 * index + 1))
        nodes.append(
            _node(
                BookNodeKind.PARAGRAPH, f"p{index}", parent=division, text=" ".join(["word"] * words), seq=2 * index + 2
            )
        )
    return BookTree.model_construct(
        doc_id="doc", title="Book", decomposer_version="t", content_hash="h", nodes=nodes, report=None
    )


@pytest.mark.unit
def test_old_settings_make_one_summary_per_section_and_two_sections_per_batch() -> None:
    tree = _tree([100] * 20)
    old = estimate_analyzer_calls(tree, batch_words=1_000_000, batch_sections=2, summary_batch=1)
    assert old.sections == 20
    assert old.summaries == 20
    assert old.batched_extraction == 10
    assert old.classification == 2  # 15 sections per classification call


@pytest.mark.unit
def test_new_settings_fill_batches_by_words_and_summaries_by_count() -> None:
    tree = _tree([100] * 20)
    new = estimate_analyzer_calls(tree, batch_words=3000, batch_sections=16, summary_batch=10)
    assert new.summaries == 2
    assert new.batched_extraction == 2  # 16 sections then 4
    assert new.total < estimate_analyzer_calls(tree, batch_words=1_000_000, batch_sections=2, summary_batch=1).total


@pytest.mark.unit
def test_a_section_longer_than_the_budget_travels_alone() -> None:
    tree = _tree([5000, 100, 100])
    estimate = estimate_analyzer_calls(tree, batch_words=3000, batch_sections=16, summary_batch=10)
    assert estimate.batched_extraction == 2  # the long section, then the two short ones


@pytest.mark.unit
def test_character_sheet_calls_follow_the_game_system_flag_and_the_section_limit() -> None:
    tree = _tree([50] * 40)
    assert estimate_analyzer_calls(tree).character_sheet == 31  # 30 focus sections plus one synthesis
    assert estimate_analyzer_calls(tree, game_system=False).character_sheet == 0


@pytest.mark.unit
def test_section_words_are_per_division_in_reading_order() -> None:
    assert section_word_counts(_tree([10, 20, 30])) == [10, 20, 30]


@pytest.mark.unit
def test_section_words_are_capped_at_the_analyzer_section_limit() -> None:
    from monitor_agents.analyzer._constants import MAX_SECTIONS_PER_LAYER

    assert len(section_word_counts(_tree([5] * (MAX_SECTIONS_PER_LAYER + 20)))) == MAX_SECTIONS_PER_LAYER
