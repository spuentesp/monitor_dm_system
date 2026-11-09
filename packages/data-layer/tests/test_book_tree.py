"""Tests for lossless PDF decomposition (book decomposition prototype, I-17)."""

from pathlib import Path

import fitz
import pytest
from hypothesis import given
from hypothesis import strategies as st
from monitor_data.schemas.book_graph import BookNodeKind, BookTree
from monitor_data.tools.ingest_tools.book_tree import (
    _Block,
    _continues,
    _Line,
    sections_from_tree,
    alnum_count,
    decompose_pdf,
    join_lines,
    split_sentences,
)

FIXTURE = Path(__file__).parents[3] / "tests" / "fixtures" / "ingestion" / "tiny_rulebook.pdf"


def _pdf(pages: list[list[tuple[float, float, str]]], toc: list[list] | None = None) -> bytes:
    doc = fitz.open()
    for items in pages:
        page = doc.new_page()
        for x, y, text in items:
            page.insert_text((x, y), text)
    if toc:
        doc.set_toc(toc)
    return doc.tobytes()


def _texts(tree: BookTree, kind: BookNodeKind) -> list[str]:
    return [node.text for node in tree.nodes if node.kind == kind]


def _division_paragraphs(tree: BookTree) -> dict[str, list[str]]:
    by_id = {node.id: node for node in tree.nodes}
    result: dict[str, list[str]] = {}
    for node in tree.nodes:
        if node.kind == BookNodeKind.PARAGRAPH:
            result.setdefault(by_id[node.parent_id].text, []).append(node.text)
    return result


@pytest.mark.unit
def test_nested_toc_does_not_duplicate_child_text_into_parent():
    """The defect in extract_pdf_structure: a parent section repeats all its children."""
    data = _pdf(
        [[(72, 72, "Chapter"), (72, 110, "Intro sentence here.")], [(72, 72, "Child"), (72, 110, "Child body here.")]],
        [[1, "Chapter", 1], [2, "Child", 2]],
    )
    paragraphs = _division_paragraphs(decompose_pdf(data, "d", "T"))
    assert paragraphs["Chapter"] == ["Intro sentence here."]
    assert paragraphs["Child"] == ["Child body here."]


@pytest.mark.unit
def test_same_page_siblings_each_get_only_their_own_text():
    """The defect in extract_pdf_structure: same-page siblings both receive the whole page."""
    data = _pdf(
        [[(72, 72, "Beta"), (72, 110, "Beta body."), (72, 200, "Gamma"), (72, 240, "Gamma body.")]],
        [[1, "Beta", 1], [1, "Gamma", 1]],
    )
    paragraphs = _division_paragraphs(decompose_pdf(data, "d", "T"))
    assert paragraphs == {"Beta": ["Beta body."], "Gamma": ["Gamma body."]}


@pytest.mark.unit
def test_section_starting_mid_page_keeps_the_text_before_it_in_the_previous_section():
    data = _pdf(
        [
            [(72, 72, "First"), (72, 110, "Opening text.")],
            [(72, 110, "Tail of first section."), (72, 300, "Second"), (72, 340, "Second body.")],
        ],
        [[1, "First", 1], [1, "Second", 2]],
    )
    paragraphs = _division_paragraphs(decompose_pdf(data, "d", "T"))
    assert paragraphs["First"] == ["Opening text.", "Tail of first section."]
    assert paragraphs["Second"] == ["Second body."]


@pytest.mark.unit
def test_two_columns_are_read_column_by_column():
    data = _pdf(
        [[(320, 72, "Right top."), (320, 120, "Right bottom."), (72, 96, "Left top."), (72, 144, "Left bottom.")]]
    )
    assert _texts(decompose_pdf(data, "d", "T"), BookNodeKind.PARAGRAPH) == [
        "Left top.",
        "Left bottom.",
        "Right top.",
        "Right bottom.",
    ]


@pytest.mark.unit
def test_running_headers_become_furniture_and_are_still_accounted_for():
    pages = [[(72, 30, "VAMPIRE THE GAME"), (72, 200, f"Body text {i}.")] for i in range(6)]
    tree = decompose_pdf(_pdf(pages), "d", "T")
    assert len(_texts(tree, BookNodeKind.FURNITURE)) == 6
    assert len(_texts(tree, BookNodeKind.PARAGRAPH)) == 6
    assert tree.report.is_lossless


@pytest.mark.unit
def test_paragraph_continuing_across_a_page_is_merged_past_the_header():
    pages = [
        [(72, 30, "RUNNING HEAD"), (72, 200, "This sentence carries")],
        [(72, 30, "RUNNING HEAD"), (72, 200, "on across the page.")],
        [(72, 30, "RUNNING HEAD"), (72, 200, "Another paragraph.")],
    ]
    tree = decompose_pdf(_pdf(pages), "d", "T")
    merged = next(n for n in tree.nodes if n.kind == BookNodeKind.PARAGRAPH)
    assert merged.text == "This sentence carries on across the page."
    assert (merged.page_start, merged.page_end) == (0, 1)


@pytest.mark.unit
def test_page_without_text_is_reported_rather_than_ignored():
    tree = decompose_pdf(_pdf([[(72, 72, "Only page with words.")], []]), "d", "T")
    assert tree.report.pages_total == 2
    assert tree.report.pages_without_text == 1


@pytest.mark.unit
def test_bookmark_on_an_empty_page_still_creates_its_division():
    data = _pdf([[(72, 72, "Text one.")], [], [(72, 72, "Text two.")]], [[1, "A", 1], [1, "Empty", 2], [1, "C", 3]])
    tree = decompose_pdf(data, "d", "T")
    assert _texts(tree, BookNodeKind.DIVISION) == ["A", "Empty", "C"]
    assert _division_paragraphs(tree)["C"] == ["Text two."]


@pytest.mark.unit
def test_bookmark_listed_out_of_page_order_does_not_misplace_later_sections():
    """Seen on a real rulebook: a sidebar bookmark listed early stranded half the entries."""
    data = _pdf(
        [
            [(72, 72, "First"), (72, 110, "First body.")],
            [(72, 72, "Second"), (72, 110, "Second body.")],
            [(72, 72, "Sidebar"), (72, 110, "Sidebar body.")],
        ],
        [[1, "Sidebar", 3], [1, "First", 1], [1, "Second", 2]],
    )
    tree = decompose_pdf(data, "d", "T")
    assert tree.report.toc_entries_located == 3
    assert _division_paragraphs(tree) == {
        "First": ["First body."],
        "Second": ["Second body."],
        "Sidebar": ["Sidebar body."],
    }


@pytest.mark.unit
def test_letter_spaced_heading_matches_its_bookmark():
    """Seen on a real rulebook: display type extracts as 'T h e  J u i c e'."""
    data = _pdf(
        [[(72, 72, "Before."), (72, 200, "T h e J u i c e"), (72, 240, "Juice body.")]],
        [[1, "Start", 1], [1, "The Juice", 1]],
    )
    tree = decompose_pdf(data, "d", "T")
    assert _division_paragraphs(tree)["The Juice"] == ["Juice body."]
    assert "T h e J u i c e" in _texts(tree, BookNodeKind.HEADING)


@pytest.mark.unit
def test_unrecognized_letter_spaced_text_is_a_heading_not_a_paragraph():
    tree = decompose_pdf(_pdf([[(72, 72, "M e n t a t T r a i n i n g")]]), "d", "T")
    assert _texts(tree, BookNodeKind.PARAGRAPH) == []
    assert tree.report.is_lossless


@pytest.mark.unit
def test_prefix_title_match_requires_a_whole_word():
    data = _pdf(
        [[(72, 72, "Warfare is common."), (72, 200, "War broke out here.")]],
        [[1, "Start", 1], [1, "War", 1]],
    )
    assert _division_paragraphs(decompose_pdf(data, "d", "T"))["War"] == ["War broke out here."]


@pytest.mark.unit
def test_real_fixture_is_lossless_with_every_toc_entry_present():
    tree = decompose_pdf(FIXTURE.read_bytes(), "d", "Tiny")
    assert tree.report.is_lossless
    assert tree.report.alnum_extracted > 0
    assert _texts(tree, BookNodeKind.DIVISION) == [
        "Introduction",
        "Attributes",
        "Abilities",
        "Resolving Actions",
        "Character Creation Process",
    ]


@pytest.mark.unit
def test_node_ids_are_deterministic_and_never_shared_between_documents():
    data = FIXTURE.read_bytes()
    first = [n.id for n in decompose_pdf(data, "doc-a", "T").nodes]
    assert first == [n.id for n in decompose_pdf(data, "doc-a", "T").nodes]
    assert not set(first) & {n.id for n in decompose_pdf(data, "doc-b", "T").nodes}
    assert len(first) == len(set(first))


def _ids_by_text(tree: BookTree, kind: BookNodeKind) -> dict[str, str]:
    return {n.text: n.id for n in tree.nodes if n.kind == kind}


@pytest.mark.unit
def test_adding_a_paragraph_leaves_every_other_paragraph_id_unchanged():
    """The idempotency guarantee: a decomposer fix can't invalidate work on unchanged text."""
    original = _pdf([[(72, 72, "Alpha text here."), (72, 120, "Beta text here.")], [(72, 72, "Gamma text here.")]])
    with_extra = _pdf(
        [
            [(72, 40, "A brand new paragraph."), (72, 72, "Alpha text here."), (72, 120, "Beta text here.")],
            [(72, 72, "Gamma text here.")],
        ]
    )
    before = _ids_by_text(decompose_pdf(original, "d", "T"), BookNodeKind.PARAGRAPH)
    after = _ids_by_text(decompose_pdf(with_extra, "d", "T"), BookNodeKind.PARAGRAPH)
    assert len(before) == 3
    assert all(after[text] == node_id for text, node_id in before.items())
    before_s = _ids_by_text(decompose_pdf(original, "d", "T"), BookNodeKind.SENTENCE)
    after_s = _ids_by_text(decompose_pdf(with_extra, "d", "T"), BookNodeKind.SENTENCE)
    assert all(after_s[text] == node_id for text, node_id in before_s.items())


@pytest.mark.unit
def test_paragraph_id_survives_moving_to_a_different_section():
    flat = _pdf([[(72, 72, "Same text here.")]], [[1, "One", 1]])
    other = _pdf([[(72, 72, "Same text here.")]], [[1, "Another Section Entirely", 1]])
    first = _ids_by_text(decompose_pdf(flat, "d", "T"), BookNodeKind.PARAGRAPH)
    second = _ids_by_text(decompose_pdf(other, "d", "T"), BookNodeKind.PARAGRAPH)
    assert first == second


@pytest.mark.unit
def test_changed_text_gets_a_new_id():
    first = decompose_pdf(_pdf([[(72, 72, "Pool holds 6.")]]), "d", "T")
    second = decompose_pdf(_pdf([[(72, 72, "Pool holds 8.")]]), "d", "T")
    assert set(_ids_by_text(first, BookNodeKind.PARAGRAPH).values()).isdisjoint(
        _ids_by_text(second, BookNodeKind.PARAGRAPH).values()
    )


@pytest.mark.unit
def test_repeated_identical_text_gets_distinct_ids():
    tree = decompose_pdf(
        _pdf([[(72, 100, "Repeat this."), (72, 200, "Repeat this."), (72, 300, "Repeat this.")]]), "d", "T"
    )
    ids = [n.id for n in tree.nodes if n.kind == BookNodeKind.PARAGRAPH]
    assert len(ids) == 3
    assert len(set(ids)) == 3


@pytest.mark.unit
def test_every_non_root_node_has_a_parent_that_comes_before_it():
    tree = decompose_pdf(FIXTURE.read_bytes(), "d", "T")
    seen = {tree.nodes[0].id}
    for node in tree.nodes[1:]:
        assert node.parent_id in seen
        seen.add(node.id)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("One here. Two here.", ["One here.", "Two here."]),
        ("Wow! Really? Yes.", ["Wow!", "Really?", "Yes."]),
        ("Use a tool, e.g. Hammer here.", ["Use a tool, e.g. Hammer here."]),
        ("1. Choose your name.", ["1. Choose your name."]),
        ("Roll a 5. Then stop.", ["Roll a 5.", "Then stop."]),
        ('He said "Stop." Then left.', ['He said "Stop."', "Then left."]),
        ("No end mark", ["No end mark"]),
        ("", []),
    ],
)
def test_split_sentences(text, expected):
    assert split_sentences(text) == expected


@pytest.mark.unit
@given(st.text(alphabet="abAB12 .!?\"'()\n", max_size=200))
def test_split_sentences_never_loses_or_reorders_text(text):
    assert " ".join(split_sentences(text)) == " ".join(text.split())


@pytest.mark.unit
def test_join_lines_undoes_hyphenation_only_before_lowercase():
    assert join_lines(["The disci-", "plines of", "Cain"]) == "The disciplines of Cain"
    assert join_lines(["Well-", "Known"]) == "Well- Known"


@pytest.mark.unit
def test_join_lines_removes_soft_hyphens_at_line_ends_and_inside_lines():
    assert join_lines(["The stor\xad", "age room"]) == "The storage room"
    assert join_lines(["develop\xad ment plan"]) == "development plan"


@pytest.mark.unit
def test_alnum_count_ignores_whitespace_and_hyphens():
    assert alnum_count("dis-\n ciplines 7") == alnum_count("disciplines7")


@pytest.mark.unit
def test_paragraph_records_its_main_font_and_color():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Plain rules text ends here.", fontname="helv", color=(0, 0, 0))
    page.insert_text((72, 300), "An example passage ends here.", fontname="hebo", color=(1, 0, 0))
    tree = decompose_pdf(doc.tobytes(), "d", "T")
    styles = {n.text: n.style for n in tree.nodes if n.kind == BookNodeKind.PARAGRAPH}
    assert styles["Plain rules text ends here."] != styles["An example passage ends here."]
    assert all(styles.values())


@pytest.mark.unit
def test_recording_style_does_not_change_node_ids():
    def build(color: tuple[float, float, float]) -> list[str]:
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "Same words here.", color=color)
        return [n.id for n in decompose_pdf(doc.tobytes(), "d", "T").nodes]

    assert build((0, 0, 0)) == build((1, 0, 0))


def _block(text: str, y0: float, page: int = 0, x0: float = 72.0) -> _Block:
    return _Block(page, x0, y0, x0 + 200, y0 + 12, [_Line(text=text, x0=x0, size=9.0)])


@pytest.mark.unit
def test_sentence_broken_by_a_font_change_continues():
    # Dune page 171: an italic "Dune" opens a new block, in the middle of the sentence.
    assert _continues(_block("While it often happens in", 100), _block("Dune, rivals can retreat.", 110))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("before", "after"),
    [
        (_block("It often does in", 100), _block("Dune, enemies yield.", 400)),  # Far below.
        (_block("It often does in", 100), _block("Dune, enemies yield.", 110, page=1)),  # Next page.
        (_block("It often does in", 100), _block("Dune, enemies yield.", 110, x0=320)),  # Next column.
        (_block("Defeat is not always death", 100), _block("Enemies can yield.", 110)),  # Can end.
        (_block("Defeat is not always in.", 100), _block("Enemies can yield.", 110)),  # Ended.
    ],
)
def test_capitalized_block_that_does_not_continue_the_sentence(before, after):
    assert not _continues(before, after)


@pytest.mark.unit
def test_lowercase_block_continues_even_on_the_next_page():
    assert _continues(_block("It often does", 700), _block("and enemies yield.", 50, page=1))


def _sections(pages, toc=None):
    return sections_from_tree(decompose_pdf(_pdf(pages, toc), "d", "T"))


@pytest.mark.unit
def test_nested_bookmarks_do_not_repeat_child_text_in_the_parent():
    sections = _sections(
        [
            [(72, 100, "Chapter text stands alone here.")],
            [(72, 100, "Combat rules stand alone here.")],
        ],
        [[1, "Chapter", 1], [2, "Combat", 2]],
    )
    by_name = {section.heading_path[-1]: section for section in sections}
    assert by_name["Chapter"].text == "Chapter text stands alone here."
    assert by_name["Combat"].text == "Combat rules stand alone here."
    assert by_name["Combat"].heading_path == ["Chapter", "Combat"]
    assert (by_name["Chapter"].depth, by_name["Combat"].depth) == (0, 1)


@pytest.mark.unit
def test_same_page_bookmarks_each_get_only_their_own_text():
    sections = _sections(
        [
            [
                (72, 100, "First section"),
                (72, 130, "First body sentence."),
                (72, 400, "Second section"),
                (72, 430, "Second body sentence."),
            ]
        ],
        [[1, "First section", 1], [1, "Second section", 1]],
    )
    joined = " ".join(section.text for section in sections)
    assert joined.count("First body sentence.") == 1 and joined.count("Second body sentence.") == 1
    assert "Second body sentence." not in sections[0].text


@pytest.mark.unit
def test_bookmark_with_no_text_of_its_own_is_not_a_section():
    sections = _sections(
        [[(72, 100, "Child"), (72, 130, "Only the child has body text here.")]],
        [[1, "Parent", 1], [2, "Child", 1]],
    )
    assert [section.heading_path for section in sections] == [["Parent", "Child"]]


@pytest.mark.unit
def test_text_before_the_first_bookmark_keeps_its_own_section():
    sections = _sections(
        [[(72, 100, "A foreword sits before any bookmark.")], [(72, 100, "Chapter body text.")]],
        [[1, "Chapter", 2]],
    )
    assert sections[0].heading_path == ["(untitled)"]
    assert "foreword" in sections[0].text
    assert "foreword" not in sections[1].text


@pytest.mark.unit
def test_book_with_no_bookmarks_splits_at_its_headings():
    doc = fitz.open()
    page = doc.new_page()
    body = "Ordinary body text sets the main size of this page for the reader to follow."
    page.insert_text((72, 60), body, fontsize=10)
    page.insert_text((72, 120), "Combat Rules", fontsize=20)
    page.insert_text((72, 160), body.replace("Ordinary", "Combat"), fontsize=10)
    page.insert_text((72, 220), "Magic Rules", fontsize=20)
    page.insert_text((72, 260), body.replace("Ordinary", "Magic"), fontsize=10)
    sections = sections_from_tree(decompose_pdf(doc.tobytes(), "d", "T"))
    assert [section.heading_path for section in sections] == [["(untitled)"], ["Combat Rules"], ["Magic Rules"]]
    assert "Magic body" not in sections[1].text


@pytest.mark.unit
def test_running_headers_are_left_out_but_all_body_text_is_kept():
    pages = [[(72, 20, "The Running Header"), (72, 300, f"Body number {i} is here.")] for i in range(6)]
    sections = _sections(pages)
    joined = " ".join(section.text for section in sections)
    assert "Running Header" not in joined
    assert all(f"Body number {i}" in joined for i in range(6))


@pytest.mark.unit
def test_book_with_no_text_has_no_sections():
    doc = fitz.open()
    doc.new_page()
    assert sections_from_tree(decompose_pdf(doc.tobytes(), "d", "T")) == []


def _ruled_table_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Ordinary body text sits above the table on this page.", fontsize=10)
    rows = [("1", "Calm", "5"), ("2", "Tense", "6 or 7"), ("3", "Grim", "8-9")]
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            page.insert_text((80 + c * 120, 118 + r * 20), cell, fontsize=10)
    for r in range(len(rows) + 1):
        page.draw_line((72, 100 + r * 20), (432, 100 + r * 20))
    for c in range(4):
        page.draw_line((72 + c * 120, 100), (72 + c * 120, 160))
    return doc.tobytes()


@pytest.mark.unit
def test_ruled_table_becomes_one_table_with_its_rows_intact():
    tree = decompose_pdf(_ruled_table_pdf(), "d", "T")
    tables = [n.text for n in tree.nodes if n.kind == BookNodeKind.TABLE]
    assert tables == ["1 | Calm | 5\n2 | Tense | 6 or 7\n3 | Grim | 8-9"]
    assert tree.report.is_lossless
    assert "Ordinary body text" in " ".join(n.text for n in tree.nodes if n.kind == BookNodeKind.PARAGRAPH)


@pytest.mark.unit
def test_table_rows_stay_together_in_sections():
    sections = sections_from_tree(decompose_pdf(_ruled_table_pdf(), "d", "T"))
    assert "2 | Tense | 6 or 7" in sections[0].text


@pytest.mark.unit
def test_failed_table_detection_keeps_the_text(monkeypatch):
    def fail(self, *args, **kwargs):
        raise RuntimeError("bad page")

    monkeypatch.setattr(fitz.Page, "find_tables", fail)
    tree = decompose_pdf(_ruled_table_pdf(), "d", "T")
    assert tree.report.is_lossless
    assert "Tense" in " ".join(n.text for n in tree.nodes)
    assert not [n for n in tree.nodes if n.kind == BookNodeKind.TABLE and " | " in n.text]


@pytest.mark.unit
def test_title_set_into_a_paragraph_starts_its_section():
    pages = [[(72, 100, "An opening line here."), (72, 140, "As it happens The Spacing Guild rules travel here.")]]
    sections = _sections(pages, [[1, "Start", 1], [1, "The Spacing Guild", 1]])
    assert any(s.heading_path == ["The Spacing Guild"] and "rules travel" in s.text for s in sections)


@pytest.mark.unit
def test_one_word_title_is_not_matched_inside_a_sentence():
    pages = [[(72, 100, "You may move your asset to any zone here.")]]
    sections = _sections(pages, [[1, "Zone", 1]])
    assert sections and sections[0].heading_path == ["Zone"]  # Falls back to the page's top block.
    assert len(sections) == 1


def _drawn(items) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    for x_pos, y_pos, text, color in items:
        page.insert_text((x_pos, y_pos), text, color=color, fontsize=10)
    return doc.tobytes()


BLACK, WHITE = (0, 0, 0), (1, 1, 1)


@pytest.mark.unit
def test_text_drawn_twice_at_one_spot_is_kept_once_and_counted():
    text = "Siege engines are too large for one crew."
    tree = decompose_pdf(_drawn([(72, 100, text, BLACK), (72, 100, text, WHITE)]), "d", "T")
    assert _texts(tree, BookNodeKind.PARAGRAPH) == [text]
    assert tree.report.alnum_overprint_removed > 0
    assert tree.report.is_lossless


@pytest.mark.unit
def test_shadow_offset_by_a_point_or_two_is_also_kept_once():
    text = "Siege engines are too large here."
    tree = decompose_pdf(_drawn([(72, 100, text, BLACK), (73, 101, text, WHITE)]), "d", "T")
    assert _texts(tree, BookNodeKind.PARAGRAPH) == [text]


@pytest.mark.unit
def test_same_words_in_another_place_are_kept_both_times():
    text = "Roll the dice now."
    tree = decompose_pdf(_drawn([(72, 100, text, BLACK), (72, 300, text, BLACK), (330, 100, text, BLACK)]), "d", "T")
    assert " ".join(_texts(tree, BookNodeKind.PARAGRAPH)).count(text) == 3
    assert tree.report.alnum_overprint_removed == 0
    assert tree.report.is_lossless


@pytest.mark.unit
def test_lost_text_still_fails_the_lossless_check():
    tree = decompose_pdf(_drawn([(72, 100, "Roll the dice now.", BLACK)]), "d", "T")
    tree.report.alnum_extracted += 5
    assert not tree.report.is_lossless


@pytest.mark.unit
def test_ruled_box_around_prose_is_not_a_table():
    doc = fitz.open()
    page = doc.new_page()
    lines = ["Siege engines are machines too large", "for one crew and they turn a", "small fight into a large battle."]
    for i, line in enumerate(lines):
        page.insert_text((80, 118 + i * 14), line, fontsize=10)
    page.draw_rect(fitz.Rect(72, 100, 432, 170))
    page.draw_line((252, 100), (252, 170))
    tree = decompose_pdf(doc.tobytes(), "d", "T")
    assert not [n for n in tree.nodes if n.kind == BookNodeKind.TABLE]
    assert "small fight into a large battle." in " ".join(_texts(tree, BookNodeKind.PARAGRAPH))


@pytest.mark.unit
def test_shadow_that_starts_a_letter_later_is_kept_once():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "o help you create the array", fontsize=10)
    page.insert_text((77.5, 100), "help you create the array", fontsize=10, color=WHITE)
    tree = decompose_pdf(doc.tobytes(), "d", "T")
    assert " ".join(_texts(tree, BookNodeKind.PARAGRAPH)).count("help you create") == 1
    assert tree.report.is_lossless


def _drop_cap_pdf(letter: str, first_line: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 110), letter, fontsize=40)
    page.insert_text((104, 84), first_line, fontsize=10)
    page.insert_text((104, 97), "second line of the same paragraph runs on.", fontsize=10)
    page.insert_text((72, 123), "and a third line runs back under the letter.", fontsize=10)
    page.insert_text((72, 300), "Then the rest of the book carries on in plain text.", fontsize=10)
    return doc.tobytes()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("letter", "first_line", "expected"),
    [("T", "he best way to learn is", "The best way"), ("A", "character is more than", "A character is")],
)
def test_drop_cap_goes_back_on_its_paragraph(letter, first_line, expected):
    tree = decompose_pdf(_drop_cap_pdf(letter, first_line), "d", "T")
    paragraphs = _texts(tree, BookNodeKind.PARAGRAPH)
    assert any(text.startswith(expected) for text in paragraphs)
    assert letter not in [n.text.strip() for n in tree.nodes if n.kind == BookNodeKind.HEADING]
    assert tree.report.is_lossless


@pytest.mark.unit
def test_large_lone_number_is_not_a_heading():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Ordinary body text sits here on this page today.", fontsize=10)
    page.insert_text((72, 140), "4", fontsize=16)
    page.insert_text((72, 180), "More ordinary body text follows the number.", fontsize=10)
    tree = decompose_pdf(doc.tobytes(), "d", "T")
    assert "4" not in [n.text.strip() for n in tree.nodes if n.kind == BookNodeKind.HEADING]
    assert tree.report.is_lossless
