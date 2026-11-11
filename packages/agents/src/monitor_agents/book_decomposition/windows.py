"""Partition a book tree into extraction windows.

Every sentence and table belongs to exactly one window, and no window crosses a
non-content region (task 9). A window packs across headings and divisions up to a
word budget (`MONITOR_BOOK_WINDOW_WORDS`, default 3,000), so a whole chapter can
be one call; each unit keeps its own id and heading path, and the window shows
the model each unit's heading, so a claim still points at its sentence.
`MONITOR_BOOK_WINDOW_BREAK=headings` restores the old behaviour of starting a new
window at every heading and division.

Text from the previous passage is passed as read-only context so pronouns can be
resolved without that text being cited again.

The non-content filter is a pre-filter before an expensive model call, as
docs/architecture/DE_HEURISTIC_PRINCIPLE.md allows: it only drops furniture the
decomposer already marked, text before the first division (front matter), and
divisions whose own TOC title is contents/index/credits. It decides nothing
about game meaning, and `MONITOR_BOOK_SKIP_NON_CONTENT=0` turns it off.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import NAMESPACE_URL, uuid5

from monitor_data.schemas.book_graph import BookNode, BookNodeKind, BookTree

from monitor_agents.book_decomposition.settings import (
    BREAK_BUDGET,
    BREAK_HEADINGS,
    DecompositionSettings,
)

_CONTEXT_WORDS = 60

# Divisions whose own bookmark title says they hold no game content (task 9).
_NON_CONTENT_DIVISION_TITLES = frozenset(
    {
        "contents",
        "tableofcontents",
        "index",
        "credits",
        "acknowledgements",
        "acknowledgments",
        "abouttheauthor",
        "abouttheauthors",
    }
)


@dataclass(frozen=True)
class Unit:
    """The smallest citable piece of a book: a sentence, or a whole table."""

    node_id: str
    label: str
    kind: BookNodeKind
    text: str
    page: int
    # Where this unit sits: the division path plus the heading above it. A window
    # can span headings and divisions, so each unit carries its own.
    heading_path: tuple[str, ...] = ()


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
class _Entry:
    """One content node in a draft, with the heading that was above it there."""

    node: BookNode
    parent_id: str
    heading: str | None


@dataclass
class _Draft:
    entries: list[_Entry] = field(default_factory=list)
    words: int = 0


def window_id(units: Sequence[Unit]) -> str:
    """Identify a window by exactly which units it holds.

    Saved outcomes are keyed by this, so a run resumed under different window
    settings still matches: `reconcile` works per unit, and `plan_windows`
    recomputes the id of whatever units remain.
    """
    return str(uuid5(NAMESPACE_URL, "window:" + "|".join(unit.node_id for unit in units)))


def _heading_path(tree_by_id: dict[str, BookNode], division_id: str) -> tuple[str, ...]:
    path: list[str] = []
    current: BookNode | None = tree_by_id.get(division_id)
    while current is not None and current.kind == BookNodeKind.DIVISION:
        path.insert(0, current.text)
        current = tree_by_id.get(current.parent_id) if current.parent_id else None
    return tuple(path)


def _compact(text: str) -> str:
    return text.replace(" ", "").casefold()


def _unit_path(tree_by_id: dict[str, BookNode], parent_id: str, heading: str | None) -> tuple[str, ...]:
    """The division path plus the heading above this unit, as the model should see it."""
    path = list(_heading_path(tree_by_id, parent_id))
    # A heading repeating its division, possibly letter-spaced, adds nothing to the path.
    if heading and not (path and _compact(heading) == _compact(path[-1])):
        path.append(heading)
    return tuple(path)


def plan_non_content(tree: BookTree, settings: DecompositionSettings | None = None) -> dict[str, str]:
    """Map each node that never goes to the model to the reason it is held back.

    Furniture is always held back (the decomposer marked it: running headers,
    footers, page numbers). Front matter and contents/index/credits divisions are
    held back only when `settings.skip_non_content` is on.
    """
    s = settings or DecompositionSettings.from_env()
    by_id = {node.id: node for node in tree.nodes}
    has_divisions = any(node.kind == BookNodeKind.DIVISION for node in tree.nodes)
    reasons: dict[str, str] = {}
    for node in tree.nodes:
        if node.kind == BookNodeKind.FURNITURE:
            reasons[node.id] = "furniture"
    if not s.skip_non_content:
        return reasons

    def compact_title(text: str) -> str:
        return "".join(text.split()).casefold()

    non_content_divisions = {
        node.id
        for node in tree.nodes
        if node.kind == BookNodeKind.DIVISION and compact_title(node.text) in _NON_CONTENT_DIVISION_TITLES
    }

    def under_non_content(node: BookNode) -> bool:
        parent = by_id.get(node.parent_id or "")
        while parent is not None:
            if parent.id in non_content_divisions:
                return True
            parent = by_id.get(parent.parent_id or "") if parent.parent_id else None
        return False

    for node in tree.nodes:
        if node.id in reasons or node.kind not in (BookNodeKind.PARAGRAPH, BookNodeKind.TABLE, BookNodeKind.HEADING):
            continue
        parent = by_id.get(node.parent_id or "")
        if under_non_content(node):
            reasons[node.id] = "non_content_division"
        elif has_divisions and parent is not None and parent.kind == BookNodeKind.BOOK:
            # Text before the first bookmark: title page, contents, credits.
            reasons[node.id] = "front_matter"
    return reasons


def non_content_counts(reasons: dict[str, str]) -> dict[str, int]:
    """Counts per reason, for the run's report."""
    counts: dict[str, int] = {}
    for reason in reasons.values():
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def build_windows(
    tree: BookTree,
    max_words: int | None = None,
    *,
    break_at: str | None = None,
    settings: DecompositionSettings | None = None,
) -> list[Window]:
    """Build windows in reading order. An oversized paragraph or table gets its own window.

    With `break_at="budget"` (the default) a window packs across headings and
    divisions until the word budget is spent. With `break_at="headings"` a new
    window starts at every heading and every change of parent division — the
    behaviour before phase 5a, reachable for side-by-side runs.
    """
    s = settings or DecompositionSettings.from_env()
    words_budget = s.window_words if max_words is None else max_words
    mode = s.window_break if break_at is None else break_at
    if mode not in (BREAK_BUDGET, BREAK_HEADINGS):
        raise ValueError(f"break_at must be 'budget' or 'headings', got {mode!r}")

    by_id = {node.id: node for node in tree.nodes}
    sentences_of: dict[str, list[BookNode]] = {}
    for node in tree.nodes:
        if node.kind == BookNodeKind.SENTENCE and node.parent_id:
            sentences_of.setdefault(node.parent_id, []).append(node)
    skipped = plan_non_content(tree, s)

    drafts: list[_Draft] = []
    draft: _Draft | None = None
    heading: str | None = None
    current_parent: str | None = None

    for node in tree.nodes:
        if node.id in skipped:
            continue
        if node.kind not in (BookNodeKind.PARAGRAPH, BookNodeKind.TABLE, BookNodeKind.HEADING):
            continue
        if node.parent_id != current_parent:
            current_parent = node.parent_id
            heading = None  # A heading doesn't carry over into the next division.
            if mode == BREAK_HEADINGS:
                draft = None
        if node.kind == BookNodeKind.HEADING:
            heading = node.text
            if mode == BREAK_HEADINGS:
                draft = None
            continue
        words = len(node.text.split())
        if draft is None or draft.words + words > words_budget:
            draft = _Draft()
            drafts.append(draft)
        draft.entries.append(_Entry(node, node.parent_id or "", heading))
        draft.words += words

    windows: list[Window] = []
    previous_text = ""
    for draft in drafts:
        units: list[Unit] = []
        for entry in draft.entries:
            node = entry.node
            leaves = sentences_of.get(node.id, []) if node.kind == BookNodeKind.PARAGRAPH else [node]
            path = _unit_path(by_id, entry.parent_id, entry.heading)
            for leaf in leaves:
                prefix = "T" if leaf.kind == BookNodeKind.TABLE else "S"
                units.append(Unit(leaf.id, f"{prefix}{len(units) + 1}", leaf.kind, leaf.text, leaf.page_start, path))
        if not units:
            continue
        windows.append(
            Window(
                id=window_id(units),
                division_id=draft.entries[0].parent_id,
                heading_path=units[0].heading_path,
                context=" ".join(previous_text.split()[-_CONTEXT_WORDS:]),
                units=tuple(units),
            )
        )
        previous_text = " ".join(unit.text for unit in units)
    return windows
