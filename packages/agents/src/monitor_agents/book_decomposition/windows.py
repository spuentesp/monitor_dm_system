"""Partition a book tree into extraction windows.

Every sentence and table belongs to exactly one window, and no window crosses a division
or heading. Text from the previous passage is passed as read-only context so pronouns can
be resolved without that text being cited again.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import NAMESPACE_URL, uuid5

from monitor_data.schemas.book_graph import BookNode, BookNodeKind, BookTree

DEFAULT_MAX_WORDS = 600
_CONTEXT_WORDS = 60


@dataclass(frozen=True)
class Unit:
    """The smallest citable piece of a book: a sentence, or a whole table."""

    node_id: str
    label: str
    kind: BookNodeKind
    text: str
    page: int


@dataclass(frozen=True)
class Window:
    """A passage sent to the model in one call."""

    id: str
    division_id: str
    heading_path: tuple[str, ...]
    context: str
    units: tuple[Unit, ...]

    def restricted_to(self, labels: set[str]) -> Window:
        """Return this window limited to the given units, for retrying only what's missing."""
        kept = tuple(unit for unit in self.units if unit.label in labels)
        return Window(self.id, self.division_id, self.heading_path, self.context, kept)


@dataclass
class _Draft:
    division_id: str
    heading: str | None
    nodes: list[BookNode] = field(default_factory=list)
    words: int = 0


def window_id(units: Sequence[Unit]) -> str:
    """Identify a window by exactly which units it holds."""
    return str(uuid5(NAMESPACE_URL, "window:" + "|".join(unit.node_id for unit in units)))


def _heading_path(tree_by_id: dict[str, BookNode], division_id: str) -> tuple[str, ...]:
    path: list[str] = []
    current: BookNode | None = tree_by_id[division_id]
    while current is not None and current.kind == BookNodeKind.DIVISION:
        path.insert(0, current.text)
        current = tree_by_id.get(current.parent_id) if current.parent_id else None
    return tuple(path)


def build_windows(tree: BookTree, max_words: int = DEFAULT_MAX_WORDS) -> list[Window]:
    """Build windows in reading order. An oversized paragraph or table gets its own window."""
    by_id = {node.id: node for node in tree.nodes}
    sentences_of: dict[str, list[BookNode]] = {}
    for node in tree.nodes:
        if node.kind == BookNodeKind.SENTENCE and node.parent_id:
            sentences_of.setdefault(node.parent_id, []).append(node)

    drafts: list[_Draft] = []
    draft: _Draft | None = None
    heading: str | None = None
    current_parent: str | None = None

    for node in tree.nodes:
        if node.kind not in (BookNodeKind.PARAGRAPH, BookNodeKind.TABLE, BookNodeKind.HEADING):
            continue
        if node.parent_id != current_parent:
            current_parent = node.parent_id
            heading = None
            draft = None
        if node.kind == BookNodeKind.HEADING:
            heading = node.text
            draft = None
            continue
        words = len(node.text.split())
        if draft is None or draft.words + words > max_words:
            draft = _Draft(current_parent or "", heading)
            drafts.append(draft)
        draft.nodes.append(node)
        draft.words += words

    windows: list[Window] = []
    previous_text = ""
    for draft in drafts:
        units: list[Unit] = []
        for node in draft.nodes:
            leaves = sentences_of.get(node.id, []) if node.kind == BookNodeKind.PARAGRAPH else [node]
            for leaf in leaves:
                prefix = "T" if leaf.kind == BookNodeKind.TABLE else "S"
                units.append(Unit(leaf.id, f"{prefix}{len(units) + 1}", leaf.kind, leaf.text, leaf.page_start))
        if not units:
            continue
        path = _heading_path(by_id, draft.division_id)
        # A heading repeating its division, possibly letter-spaced, adds nothing to the path.
        repeats_division = path and (draft.heading or "").replace(" ", "").casefold() == (
            path[-1].replace(" ", "").casefold()
        )
        if draft.heading and not repeats_division:
            path = (*path, draft.heading)
        windows.append(
            Window(
                id=window_id(units),
                division_id=draft.division_id,
                heading_path=path,
                context=" ".join(previous_text.split()[-_CONTEXT_WORDS:]),
                units=tuple(units),
            )
        )
        previous_text = " ".join(unit.text for unit in units)
    return windows
