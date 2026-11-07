"""Lossless, deterministic PDF → book tree decomposition (prototype).

Unlike `extract_pdf_structure`, which copies whole page ranges into each TOC entry (so a
parent repeats its children and same-page siblings share text), this assigns every text
block to exactly one division by its position in reading order. Nothing is selected or
sampled: text is only ever classified, and `DecompositionReport` proves nothing was lost.

Structural heuristics here (fonts, margins, punctuation) describe page layout rather than
game meaning, so they fall outside docs/architecture/DE_HEURISTIC_PRINCIPLE.md.

See docs/architecture/BOOK_DECOMPOSITION_PLAN.md.
"""

from __future__ import annotations

import hashlib
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import fitz
import structlog

from monitor_data.schemas.book_graph import (
    BookNode,
    BookNodeKind,
    BookTree,
    DecompositionReport,
)
from monitor_data.tools.ingest_tools._models import SectionBlock
from monitor_data.tools.ingest_tools.pdf_processing import _open_pdf

DECOMPOSER_VERSION = "7"
_OVERPRINT_TOLERANCE = 3.0
_DROP_CAP_SIZE_RATIO = 2.5
_DROP_CAP_REACH = 40.0
_DROP_CAP_SLACK = 4.0
_DROP_CAP_RISE = 0.3  # How far above the letter its first line may start, as a share of its height.
_SPACED_CAPITALS = frozenset("AI")  # Letters that are words on their own.
_MIN_OVERPRINT_TAIL = 12
_TABLE_MIN_MULTI_CELL_SHARE = 0.5
_MIN_MIDDLE_TITLE_WORDS = 2
_TABLE_ROW_TOLERANCE = 3.0
_TABLE_MAX_WORDS_PER_ROW = 24
_TABLE_CELL_SEPARATOR = " | "
_UNTITLED_SECTION = "(untitled)"
_SECTION_CONTENT = (BookNodeKind.PARAGRAPH, BookNodeKind.TABLE, BookNodeKind.HEADING)
_NEXT_LINE_GAP = 1.5
_CANNOT_END_SENTENCE = frozenset(
    "a an the of in on at to for from by with and or but as that which who whose than if when "
    "while your their his her its is are was were be can may will not into over under through "
    "use uses".split()
)

_TERMINAL = (".", "!", "?", ":", ";", '"', "”", "’", ")", "]")
_ABBREVIATIONS = frozenset(
    {"e.g.", "i.e.", "etc.", "vs.", "cf.", "mr.", "mrs.", "ms.", "dr.", "st.", "p.", "pp."}
    | {"vol.", "no.", "fig.", "ed.", "approx.", "sr.", "jr."}
)
_SENTENCE_END = re.compile(r"[.!?]+[\"”’')\]]*\s+")
_OPENERS = "\"“‘'([¿¡"
_SOFT_HYPHEN = "\xad"
_MARGIN_FRACTION = 0.08
log = structlog.get_logger()
_COLUMN_GAP_FRACTION = 0.2
_FULL_WIDTH_FRACTION = 0.6
_INDENT_POINTS = 6.0
_HEADING_FONT_RATIO = 1.15
_HEADING_MAX_WORDS = 15
_FURNITURE_MIN_PAGES = 3
_FURNITURE_PAGE_FRACTION = 0.05


def alnum_count(text: str) -> int:
    """Count letters and digits. Unaffected by whitespace and dehyphenation."""
    return sum(ch.isalnum() for ch in text)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences so that `" ".join(result)` equals the normalized text."""
    normalized = " ".join(text.split())
    if not normalized:
        return []
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(normalized + " "):
        end = match.end()
        following = normalized[end : end + 1]
        if not following:
            break
        if not (following.isupper() or following.isdigit() or following in _OPENERS):
            continue
        last_word = normalized[start : match.start() + 1].rsplit(" ", 1)[-1].lower()
        is_initial = len(last_word) == 2 and last_word[0].isalpha()
        is_list_marker = normalized[start:end].strip() == last_word and last_word[:-1].isdigit()
        if last_word in _ABBREVIATIONS or is_initial or is_list_marker:
            continue
        sentences.append(normalized[start:end].strip())
        start = end
    sentences.append(normalized[start:].strip())
    return sentences


def join_lines(lines: list[str]) -> str:
    """Join PDF lines into text, undoing end-of-line hyphenation."""
    joined = ""
    for raw in lines:
        line = " ".join(raw.split())
        if not line:
            continue
        if joined.endswith(_SOFT_HYPHEN):
            joined = joined[:-1] + line
        elif joined.endswith("-") and line[0].islower():
            joined = joined[:-1] + line
        else:
            joined = f"{joined} {line}" if joined else line
    return " ".join(joined.replace(_SOFT_HYPHEN + " ", "").replace(_SOFT_HYPHEN, "").split())


@dataclass
class _Line:
    text: str
    x0: float
    size: float
    style: str = ""
    y0: float = 0.0


@dataclass
class _Block:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    lines: list[_Line]
    kind: BookNodeKind = BookNodeKind.PARAGRAPH
    toc_index: int | None = None
    last_page: int | None = None  # Set when a paragraph continues onto a later page.

    @property
    def text(self) -> str:
        if self.kind == BookNodeKind.TABLE:
            return "\n".join(" ".join(line.text.split()) for line in self.lines)
        return join_lines([line.text for line in self.lines])

    @property
    def max_size(self) -> float:
        return max(line.size for line in self.lines)

    @property
    def style(self) -> str | None:
        """The font and color of most of this block's words."""
        words: Counter[str] = Counter()
        for line in self.lines:
            words[line.style] += len(line.text.split())
        return words.most_common(1)[0][0] or None


@dataclass
class _Builder:
    doc_id: str
    nodes: list[BookNode] = field(default_factory=list)
    seen: Counter[str] = field(default_factory=Counter)

    def add(
        self,
        kind: BookNodeKind,
        parent: str | None,
        text: str,
        page_start: int,
        page_end: int,
        style: str | None = None,
    ) -> str:
        node_id = self._content_id(kind, parent, text)
        self.nodes.append(
            BookNode(
                id=node_id,
                doc_id=self.doc_id,
                kind=kind,
                parent_id=parent,
                seq=len(self.nodes),
                text=text,
                page_start=page_start,
                page_end=page_end,
                style=style,
            )
        )
        return node_id

    def _content_id(self, kind: BookNodeKind, parent: str | None, text: str) -> str:
        """Derive an ID from content, so reprocessing a book reuses the same IDs.

        A paragraph's ID doesn't depend on its position or section, so fixing the decomposer
        only changes the IDs of text that actually changed. Sentences are scoped to their
        paragraph. Identical text is told apart by the order it occurs in.
        """
        scope = parent if kind == BookNodeKind.SENTENCE else ""
        digest = hashlib.sha256(" ".join(text.split()).encode()).hexdigest()
        key = f"{self.doc_id}:{kind.value}:{scope}:{digest}"
        occurrence = self.seen[key]
        self.seen[key] += 1
        if kind == BookNodeKind.BOOK:
            return str(uuid5(NAMESPACE_URL, f"{self.doc_id}:book"))
        return str(uuid5(NAMESPACE_URL, f"{key}:{occurrence}"))


def _line_style(spans: list[dict[str, Any]]) -> str:
    """Name the font and color of most of a line's characters."""
    characters: Counter[str] = Counter()
    for span in spans:
        characters[f"{span['font']}|{span['color']}"] += len(span["text"].strip())
    return characters.most_common(1)[0][0]


def _block_from(page: int, bbox: tuple[float, float, float, float], lines: list[_Line]) -> _Block:
    return _Block(page, bbox[0], bbox[1], bbox[2], bbox[3], lines)


def _is_overprint(key: str, x1: float, y0: float, seen: list[tuple[str, float, float]]) -> bool:
    """True when the same words already sit at this spot, as when a PDF draws a text shadow.

    Lines are compared at their right edge, because a bullet or drop cap can move the left one.
    A drop cap can also make the shadow start a letter later, so a long tail of a kept line counts.
    """
    return any(
        (key == other or (len(key) >= _MIN_OVERPRINT_TAIL and other.endswith(key)))
        and abs(x1 - other_x1) <= _OVERPRINT_TOLERANCE
        and abs(y0 - other_y0) <= _OVERPRINT_TOLERANCE
        for other, other_x1, other_y0 in seen
    )


def _read_page_blocks(page: fitz.Page, page_num: int) -> tuple[list[_Block], int, int]:
    """Read text blocks, splitting a block where an indented line starts a new paragraph.

    Returns the blocks, the image count, and how many overprinted characters were left out.
    """
    blocks: list[_Block] = []
    images = 0
    overprint = 0
    seen: list[tuple[str, float, float]] = []
    for raw in page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]:
        if raw.get("type", 0) != 0:
            images += 1
            continue
        lines = [
            _Line(
                text="".join(span["text"] for span in line["spans"]),
                x0=line["bbox"][0],
                size=max(span["size"] for span in line["spans"]),
                style=_line_style(line["spans"]),
                y0=line["bbox"][1],
            )
            for line in raw["lines"]
            if line["spans"]
        ]
        kept = []
        for line, raw_line in zip(lines, (r for r in raw["lines"] if r["spans"]), strict=True):
            if not line.text.strip():
                continue
            key = _compact_key(line.text)
            x1, y0 = raw_line["bbox"][2], raw_line["bbox"][1]
            if key and _is_overprint(key, x1, y0, seen):
                overprint += alnum_count(line.text)
                continue
            seen.append((key, x1, y0))
            kept.append(line)
        lines = kept
        if not lines:
            continue
        left = min(line.x0 for line in lines)
        current: list[_Line] = []
        for line in lines:
            starts_new = current and line.x0 > left + _INDENT_POINTS and current[-1].text.rstrip().endswith(_TERMINAL)
            if starts_new:
                blocks.append(_block_from(page_num, raw["bbox"], current))
                current = []
            current.append(line)
        blocks.append(_block_from(page_num, raw["bbox"], current))
    return blocks, images, overprint


def _table_rows(blocks: list[_Block]) -> list[_Line]:
    """Rebuild table rows from their cells, which a PDF stores as separate text blocks."""
    cells = sorted((line for block in blocks for line in block.lines), key=lambda line: line.y0)
    rows: list[list[_Line]] = []
    for cell in cells:
        if rows and abs(cell.y0 - rows[-1][0].y0) <= _TABLE_ROW_TOLERANCE:
            rows[-1].append(cell)
        else:
            rows.append([cell])
    joined = []
    for row in rows:
        row.sort(key=lambda line: line.x0)
        text = _TABLE_CELL_SEPARATOR.join(cell.text.strip() for cell in row)
        joined.append(_Line(text=text, x0=row[0].x0, size=row[0].size, style=row[0].style, y0=row[0].y0))
    return joined


def _merge_table_blocks(page: fitz.Page, blocks: list[_Block]) -> list[_Block]:
    """Merge the blocks inside each ruled table into one table block, keeping all their text.

    Prose laid out in a grid can look like a table, so a region with long rows stays as it was.
    """
    try:
        found = page.find_tables().tables
    except Exception as exc:  # noqa: BLE001  # reason: PyMuPDF's detection can fail on odd pages; the text is kept as paragraphs either way
        log.warning("book_table_detection_failed", page=page.number, error=str(exc)[:200])
        return blocks
    merged = list(blocks)
    for table in found:
        if table.row_count < 2 or table.col_count < 2:
            continue
        x0, y0, x1, y1 = table.bbox
        inside = [
            block for block in merged if x0 <= (block.x0 + block.x1) / 2 <= x1 and y0 <= (block.y0 + block.y1) / 2 <= y1
        ]
        if not inside:
            continue
        rows = _table_rows(inside)
        multi_cell = sum(_TABLE_CELL_SEPARATOR in row.text for row in rows)
        too_long = max(len(row.text.split()) for row in rows) > _TABLE_MAX_WORDS_PER_ROW
        # A ruled box around prose is not a table, however short its lines are.
        if too_long or multi_cell < len(rows) * _TABLE_MIN_MULTI_CELL_SHARE:
            continue
        first = inside[0]
        table_block = _Block(first.page, x0, y0, x1, y1, rows, kind=BookNodeKind.TABLE)
        merged = [table_block if block is first else block for block in merged if block is first or block not in inside]
    return merged


def order_blocks(blocks: list[_Block], page_width: float) -> list[_Block]:
    """Put blocks in reading order: full-width bands split the page into column runs."""
    ordered: list[_Block] = []
    band: list[_Block] = []

    def flush_band() -> None:
        columns: list[float] = []
        keyed: list[tuple[int, float, _Block]] = []
        for block in sorted(band, key=lambda b: b.x0):
            if not columns or block.x0 - columns[-1] > page_width * _COLUMN_GAP_FRACTION:
                columns.append(block.x0)
            keyed.append((len(columns) - 1, block.y0, block))
        ordered.extend(item[2] for item in sorted(keyed, key=lambda k: (k[0], k[1])))
        band.clear()

    for block in sorted(blocks, key=lambda b: b.y0):
        if block.x1 - block.x0 >= page_width * _FULL_WIDTH_FRACTION:
            flush_band()
            ordered.append(block)
        else:
            band.append(block)
    flush_band()
    return ordered


def _furniture_key(block: _Block) -> str:
    return re.sub(r"\d+", "#", " ".join(block.text.split()).casefold())


def _mark_furniture(pages: list[list[_Block]], heights: list[float]) -> None:
    """Mark text repeated in the page margins, plus bare page numbers there."""
    in_margin: list[tuple[_Block, str]] = []
    seen_on: dict[str, set[int]] = {}
    for blocks, height in zip(pages, heights, strict=True):
        for block in blocks:
            margin = height * _MARGIN_FRACTION
            if block.y1 <= margin or block.y0 >= height - margin:
                key = _furniture_key(block)
                in_margin.append((block, key))
                seen_on.setdefault(key, set()).add(block.page)
    threshold = max(_FURNITURE_MIN_PAGES, int(len(pages) * _FURNITURE_PAGE_FRACTION))
    for block, key in in_margin:
        if key == "#" or len(seen_on[key]) >= threshold:
            block.kind = BookNodeKind.FURNITURE


def _words_key(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.casefold()).strip()


def _compact_key(text: str) -> str:
    """Compare with spaces removed, so letter-spaced 'T h e  E n d' matches 'The End'."""
    return re.sub(r"[\W_]+", "", text.casefold())


def _locate_toc_entries(toc: list[list[Any]], reading: list[_Block]) -> int:
    """Attach TOC entries to blocks on their own pages. Returns how many titles were found.

    Bookmark order often isn't page order (sidebars get listed out of sequence), so each
    entry is searched on its own page, with no shared cursor through the book.
    """
    by_page: dict[int, list[_Block]] = {}
    for block in reading:
        if block.kind != BookNodeKind.FURNITURE:
            by_page.setdefault(block.page, []).append(block)

    located = 0
    unlocated: list[int] = []
    for index, entry in enumerate(toc):
        match = _find_title_block(entry[1], by_page.get(entry[2] - 1, []))
        if match is None:
            unlocated.append(index)
            continue
        located += 1
        match.toc_index = index
        if _compact_key(match.text) == _compact_key(entry[1]):
            match.kind = BookNodeKind.HEADING
    # Title not on the page: start the division at the top of it, if that block is free.
    for index in unlocated:
        blocks = by_page.get(toc[index][2] - 1, [])
        if blocks and blocks[0].toc_index is None:
            blocks[0].toc_index = index
    return located


def _find_title_block(title: str, blocks: list[_Block]) -> _Block | None:
    """Find a TOC title among a page's blocks, preferring an exact match over a prefix."""
    compact = _compact_key(title)
    words = _words_key(title)
    if not compact:
        return None
    free = [block for block in blocks if block.toc_index is None]
    for block in free:
        if compact in (_compact_key(block.text), _compact_key(block.lines[0].text)):
            return block
    for block in free:
        if _words_key(block.text).startswith(words + " "):
            return block
    # A title set into its text. One word could just be a word, so it takes at least two.
    if len(words.split()) >= _MIN_MIDDLE_TITLE_WORDS:
        for block in free:
            if f" {words} " in f" {_words_key(block.text)} ":
                return block
    return None


def _body_font_size(reading: list[_Block]) -> float:
    sizes = [line.size for block in reading for line in block.lines for _ in range(max(1, len(line.text)))]
    return statistics.median(sizes) if sizes else 0.0


def _attach_drop_caps(reading: list[_Block], body_size: float) -> list[_Block]:
    """Put a large decorated first letter back on its paragraph, which starts just to its right.

    The paragraph then reads "The best" instead of a heading "T" and a paragraph "he best". The
    letter joins without a space when that makes a word used elsewhere in the book, so "A" and
    "character" become "A character".
    """
    if not body_size:
        return reading
    words = {word for block in reading for word in re.findall(r"[a-z]+", block.text.casefold())}
    attached: set[int] = set()
    for cap in reading:
        letter = cap.text.strip()
        if len(letter) != 1 or not letter.isalpha() or cap.max_size < body_size * _DROP_CAP_SIZE_RATIO:
            continue
        candidates = [
            block
            for block in reading
            if block.page == cap.page
            and block.kind == BookNodeKind.PARAGRAPH
            and block.text[:1].islower()
            # Lower lines often run under the letter, so only the first line sits beside it.
            and cap.x1 - _DROP_CAP_SLACK <= block.lines[0].x0 <= cap.x1 + _DROP_CAP_REACH
            and cap.y0 - (cap.y1 - cap.y0) * _DROP_CAP_RISE <= block.lines[0].y0 <= cap.y1
        ]
        if not candidates:
            continue
        target = min(candidates, key=lambda block: block.y0)
        first = target.lines[0]
        rest = first.text.lstrip()
        joined = letter.casefold() + (rest.split()[0].casefold() if rest.split() else "")
        joined_word = re.match(r"[a-z]+", joined)
        glue = " " if letter in _SPACED_CAPITALS and not (joined_word and joined_word.group(0) in words) else ""
        first.text = letter + glue + rest
        attached.add(id(cap))
    return [block for block in reading if id(block) not in attached]


def _classify_block(block: _Block, body_size: float) -> None:
    if block.kind != BookNodeKind.PARAGRAPH:
        return
    text = block.text
    words = text.split()
    single_letters = sum(len(word) == 1 for word in words)
    if len(words) >= 4 and single_letters >= len(words) * 0.5:
        block.kind = BookNodeKind.HEADING  # Letter-spaced display type.
        return
    if (
        body_size
        and block.max_size >= body_size * _HEADING_FONT_RATIO
        and len(words) <= _HEADING_MAX_WORDS
        and not text.endswith((".", "!", "?"))
        and any(ch.isalpha() for ch in text)  # A large lone number is a value, as in a stat block.
    ):
        block.kind = BookNodeKind.HEADING
        return
    lines = block.lines
    if len(lines) >= 3:
        short = sum(len(line.text.split()) <= 6 for line in lines)
        numeric = sum(any(ch.isdigit() for ch in line.text) for line in lines)
        if short >= len(lines) * 0.6 and numeric >= len(lines) * 0.5:
            block.kind = BookNodeKind.TABLE


def decompose_pdf(pdf_bytes: bytes, doc_id: str, title: str) -> BookTree:
    """Decompose a PDF into a tree where every piece of its text appears exactly once."""
    doc = _open_pdf(pdf_bytes)
    try:
        toc = doc.get_toc(simple=False)
        pages: list[list[_Block]] = []
        heights: list[float] = []
        images = 0
        no_text = 0
        extracted = 0
        overprint = 0
        for page_num in range(doc.page_count):
            page = doc[page_num]
            raw_text = page.get_text("text", flags=fitz.TEXTFLAGS_TEXT)
            extracted += alnum_count(raw_text)
            no_text += not raw_text.strip()
            blocks, page_images, page_overprint = _read_page_blocks(page, page_num)
            overprint += page_overprint
            blocks = _merge_table_blocks(page, blocks)
            images += page_images
            pages.append(order_blocks(blocks, page.rect.width))
            heights.append(page.rect.height)
        page_total = doc.page_count
    finally:
        doc.close()

    _mark_furniture(pages, heights)
    reading = [block for blocks in pages for block in blocks]
    located = _locate_toc_entries(toc, reading)
    body_size = _body_font_size(reading)
    for block in reading:
        _classify_block(block, body_size)
    reading = _attach_drop_caps(reading, body_size)

    builder = _Builder(doc_id)
    root = builder.add(BookNodeKind.BOOK, None, title, 0, max(page_total - 1, 0))
    _build_tree(builder, root, toc, reading)
    report = _build_report(builder, len(toc), located, page_total, no_text, images)
    report.alnum_extracted = extracted
    report.alnum_overprint_removed = overprint
    return BookTree(
        doc_id=doc_id,
        title=title,
        decomposer_version=DECOMPOSER_VERSION,
        content_hash=hashlib.sha256(pdf_bytes).hexdigest(),
        nodes=builder.nodes,
        report=report,
    )


def _build_tree(builder: _Builder, root: str, toc: list[list[Any]], reading: list[_Block]) -> None:
    """Add every division, then every block in reading order under its division.

    Parents come from TOC nesting and text placement comes from page position, so a
    bookmark listed out of page order can't drag the text around it to the wrong place.
    """
    division_ids: list[str] = []
    stack: list[tuple[int, str]] = [(0, root)]  # (TOC level, node ID); level 0 is the book.
    for level, entry_title, page_1indexed, *_ in toc:
        while stack[-1][0] >= level:
            stack.pop()
        page = page_1indexed - 1
        node = builder.add(BookNodeKind.DIVISION, stack[-1][1], entry_title, page, page)
        division_ids.append(node)
        stack.append((level, node))

    current = root
    open_paragraph: _Block | None = None
    paragraph_parent = root

    def flush() -> None:
        nonlocal open_paragraph
        if open_paragraph is not None:
            _add_paragraph(builder, paragraph_parent, open_paragraph)
            open_paragraph = None

    for block in reading:
        if block.toc_index is not None:
            flush()
            current = division_ids[block.toc_index]
        if block.kind == BookNodeKind.FURNITURE:
            # Furniture can interrupt a paragraph across pages without ending it.
            builder.add(block.kind, current, block.text, block.page, block.page)
        elif block.kind != BookNodeKind.PARAGRAPH:
            flush()
            builder.add(block.kind, current, block.text, block.page, block.page)
        elif open_paragraph is not None and _continues(open_paragraph, block):
            open_paragraph.lines = open_paragraph.lines + block.lines
            open_paragraph.last_page = block.page
            open_paragraph.y1 = block.y1
        else:
            flush()
            paragraph_parent = current
            open_paragraph = _Block(block.page, block.x0, block.y0, block.x1, block.y1, list(block.lines))
    flush()


def _continues(previous: _Block, following: _Block) -> bool:
    """True when a paragraph clearly carries on across a block or page break.

    A word in another font, such as an italic "Dune" or a bold game term, can start a new block in
    the middle of a sentence. It begins with a capital, so the next line must also sit directly
    below, and the sentence must have stopped on a word that can't end one.
    """
    before = previous.text
    after = following.text
    if not after or before.endswith(_TERMINAL):
        return False
    if after[0].islower():
        return True
    last_word = before.split()[-1].casefold() if before.split() else ""
    return (
        last_word in _CANNOT_END_SENTENCE
        and following.page == (previous.last_page or previous.page)
        and -previous.max_size <= following.y0 - previous.y1 <= previous.max_size * _NEXT_LINE_GAP
        and following.x0 < previous.x1
        and previous.x0 < following.x1
    )


def _add_paragraph(builder: _Builder, parent: str, block: _Block) -> None:
    text = block.text
    last_page = block.page if block.last_page is None else block.last_page
    paragraph = builder.add(BookNodeKind.PARAGRAPH, parent, text, block.page, last_page, style=block.style)
    for sentence in split_sentences(text):
        builder.add(BookNodeKind.SENTENCE, paragraph, sentence, block.page, last_page)


def _build_report(
    builder: _Builder,
    toc_entries: int,
    located: int,
    page_total: int,
    no_text: int,
    images: int,
) -> DecompositionReport:
    leaf_kinds = {
        BookNodeKind.PARAGRAPH,
        BookNodeKind.TABLE,
        BookNodeKind.HEADING,
        BookNodeKind.FURNITURE,
    }
    nodes = builder.nodes
    paragraphs = [n for n in nodes if n.kind == BookNodeKind.PARAGRAPH]
    sentences = [n for n in nodes if n.kind == BookNodeKind.SENTENCE]
    return DecompositionReport(
        pages_total=page_total,
        pages_without_text=no_text,
        image_blocks=images,
        toc_entries=toc_entries,
        toc_entries_located=located,
        node_counts=dict(Counter(n.kind.value for n in nodes)),
        words_total=sum(len(n.text.split()) for n in nodes if n.kind in leaf_kinds),
        fragment_paragraphs=sum(len(n.text.split()) <= 3 for n in paragraphs),
        alnum_in_leaves=sum(alnum_count(n.text) for n in nodes if n.kind in leaf_kinds),
        alnum_in_paragraphs=sum(alnum_count(n.text) for n in paragraphs),
        alnum_in_sentences=sum(alnum_count(n.text) for n in sentences),
    )


def sections_from_tree(tree: BookTree) -> list[SectionBlock]:
    """Convert a tree to sections, so each piece of the book's text is in exactly one of them.

    Each bookmark with text of its own becomes one section, holding only that text. Text before
    the first bookmark gets its own section. A book with no bookmarks splits at its headings.
    Running headers and page numbers are left out.
    """
    by_id = {node.id: node for node in tree.nodes}
    has_divisions = any(node.kind == BookNodeKind.DIVISION for node in tree.nodes)
    groups: dict[str, list[BookNode]] = {}
    order: list[str] = []
    paths: dict[str, list[str]] = {}
    current = ""
    for node in tree.nodes:
        if node.kind not in _SECTION_CONTENT:
            continue
        parent = by_id.get(node.parent_id or "")
        if parent is not None and parent.kind == BookNodeKind.DIVISION:
            key = parent.id
            paths[key] = _division_path(parent, by_id)
        elif has_divisions or (node.kind != BookNodeKind.HEADING and not current):
            key = current = current or _UNTITLED_SECTION
            paths[key] = [_UNTITLED_SECTION]
        elif node.kind == BookNodeKind.HEADING:
            key = current = node.id
            paths[key] = [" ".join(node.text.split())]
        else:
            key = current
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(node)
    sections = []
    for key in order:
        nodes = groups[key]
        sections.append(
            SectionBlock(
                heading_path=paths[key],
                depth=len(paths[key]) - 1,
                page_start=min(node.page_start for node in nodes),
                page_end=max(node.page_end for node in nodes),
                text="\n\n".join(node.text for node in nodes),
            )
        )
    return sections


def _division_path(division: BookNode, by_id: dict[str, BookNode]) -> list[str]:
    path = []
    node: BookNode | None = division
    while node is not None and node.kind == BookNodeKind.DIVISION:
        path.append(" ".join(node.text.split()))
        node = by_id.get(node.parent_id or "")
    return list(reversed(path))
