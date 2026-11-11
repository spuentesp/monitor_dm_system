"""Count the Analyzer's calls for a book without running a model (I-17).

LAYER: 2 (agents)
IMPORTS FROM: analyzer settings and batching helpers, data-layer book schema

Only the stages that the Phase 5a settings batch are counted exactly. The
Analyzer also runs stages that make one call per section (tables, agendas,
topologies, profiles); those are not batched yet, depend on what the
classifier selects at run time, and are therefore reported as "not modelled"
rather than guessed at. The job stores the real count, so the estimate and the
actual can be compared after a run.

A book's sections are approximated by its content divisions, which is close to
what the Analyzer's own chunking produces (129 sections against 154 divisions
on Death in Space).
"""

from __future__ import annotations

from dataclasses import dataclass

from monitor_data.schemas.book_graph import BookNodeKind, BookTree

from monitor_agents.analyzer import _settings
from monitor_agents.analyzer._batching import plan_word_batches
from monitor_agents.book_decomposition.windows import plan_non_content
from monitor_agents.analyzer._constants import (
    CLASSIFIER_BATCH_SIZE,
    MAX_SECTIONS_PER_LAYER,
    SYSTEM_SCHEMA_SECTION_LIMIT,
)


@dataclass(frozen=True, slots=True)
class AnalyzerEstimate:
    sections: int
    classification: int
    summaries: int
    batched_extraction: int
    character_sheet: int  # one call per focus section plus one synthesis, game systems only

    @property
    def total(self) -> int:
        return self.classification + self.summaries + self.batched_extraction + self.character_sheet

    def as_dict(self) -> dict[str, int]:
        return {
            "classification": self.classification,
            "summaries": self.summaries,
            "batched_extraction": self.batched_extraction,
            "character_sheet": self.character_sheet,
        }


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b) if a > 0 else 0


def section_word_counts(tree: BookTree) -> list[int]:
    """Words per content division, in reading order, capped at the Analyzer's section limit.

    Furniture and, with ``MONITOR_BOOK_SKIP_NON_CONTENT`` on, front matter and
    contents pages are left out, as they are for the decomposition.
    """
    not_content = plan_non_content(tree)
    words: dict[str, int] = {}
    order: list[str] = []
    for node in tree.nodes:
        if node.kind != BookNodeKind.PARAGRAPH or node.id in not_content or not node.parent_id:
            continue
        if node.parent_id not in words:
            order.append(node.parent_id)
            words[node.parent_id] = 0
        words[node.parent_id] += len(node.text.split())
    return [words[division] for division in order][:MAX_SECTIONS_PER_LAYER]


def estimate_analyzer_calls(
    tree: BookTree,
    *,
    batch_words: int | None = None,
    batch_sections: int | None = None,
    summary_batch: int | None = None,
    game_system: bool = True,
) -> AnalyzerEstimate:
    """Calls for the stages the Phase 5a settings batch. Defaults come from the environment."""
    counts = section_word_counts(tree)
    n = len(counts)
    max_words = batch_words if batch_words is not None else _settings.batch_words()
    max_sections = batch_sections if batch_sections is not None else _settings.batch_sections()
    per_summary = summary_batch if summary_batch is not None else _settings.summary_batch()

    batches = plan_word_batches(counts, words_of=lambda w: w, max_words=max_words, max_sections=max_sections)
    focus = min(n, SYSTEM_SCHEMA_SECTION_LIMIT)
    return AnalyzerEstimate(
        sections=n,
        classification=_ceil_div(n, CLASSIFIER_BATCH_SIZE),
        summaries=_ceil_div(n, per_summary),
        batched_extraction=len(batches),
        character_sheet=(focus + 1) if (game_system and focus) else 0,
    )
