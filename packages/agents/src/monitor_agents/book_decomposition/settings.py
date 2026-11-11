"""Named settings for every number the decomposition spends model calls on (I-17).

Each setting has an environment variable, a documented default (the value this
phase runs with), and an OLD value in `OLD` — the value before this phase — so a
side-by-side run of old and new settings only needs environment variables.

Read settings through `DecompositionSettings.from_env()`, which reads the
environment at call time so tests can override with monkeypatch.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

# Environment variables, and the defaults they fall back to.
WINDOW_WORDS = "MONITOR_BOOK_WINDOW_WORDS"
WINDOW_BREAK = "MONITOR_BOOK_WINDOW_BREAK"
EXTRACT_MAX_TOKENS = "MONITOR_BOOK_EXTRACT_MAX_TOKENS"
REVIEW_BATCH = "MONITOR_BOOK_REVIEW_BATCH"
GRAPH_BATCH = "MONITOR_BOOK_GRAPH_BATCH"
COVERAGE_BATCH = "MONITOR_BOOK_COVERAGE_BATCH"
COVERAGE_SAMPLE = "MONITOR_BOOK_COVERAGE_SAMPLE"
COVERAGE_MIN_PARAGRAPHS = "MONITOR_BOOK_COVERAGE_MIN_PARAGRAPHS"
SKIP_AUDIT_BATCH = "MONITOR_BOOK_SKIP_AUDIT_BATCH"
SKIP_NON_CONTENT = "MONITOR_BOOK_SKIP_NON_CONTENT"
# Estimate-only proxies: what a book will yield, before any model has run.
CLAIMS_PER_SENTENCE = "MONITOR_BOOK_CLAIMS_PER_SENTENCE"
SKIP_SHARE = "MONITOR_BOOK_SKIP_SHARE"
STACK_SHARE = "MONITOR_BOOK_STACK_SHARE"
PARAGRAPH_KEEP_SHARE = "MONITOR_BOOK_PARAGRAPH_KEEP_SHARE"
ZERO_DIVISION_SHARE = "MONITOR_BOOK_ZERO_DIVISION_SHARE"

BREAK_HEADINGS = "headings"  # Old behaviour: a new window at every heading and division.
BREAK_BUDGET = "budget"  # New behaviour: pack across headings and divisions up to the word budget.


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes")


def _choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    raw = (os.environ.get(name) or "").strip() or default
    if raw not in allowed:
        raise ValueError(f"{name} must be one of {allowed}, got {raw!r}")
    return raw


@dataclass(frozen=True)
class DecompositionSettings:
    """Every number a decomposition run is budgeted by. All env-overridable."""

    # Extraction windows (task 5).
    window_words: int = 3000  # OLD 600. Word budget for one extraction window.
    window_break: str = BREAK_BUDGET  # OLD "headings". Where a new window starts.
    extract_max_tokens: int = 32768  # OLD 16384. Output cap; a window that hits it is split.
    # Review batches (tasks 6, 8).
    review_batch: int = 70  # OLD 12. Claims per verification call; the brief asks for 60-80.
    graph_batch: int = 150  # OLD 30. Claims per graph call (task 7).
    coverage_batch: int = 25  # OLD 8. Paragraphs per coverage call.
    coverage_sample: float = 0.10  # OLD 1.0. Share of audited paragraphs actually checked (task 8).
    coverage_min_paragraphs: int = 64  # Below this many paragraphs, sampling saves nothing: check all.
    skip_audit_batch: int = 25  # OLD 25. Skipped sentences per second-look call.
    # What is never sent for extraction (task 9).
    skip_non_content: bool = True  # OLD False. Front matter and contents/index/credits divisions.
    # Estimate-only proxies (task 10): what the book will yield, guessed until measured.
    claims_per_sentence: float = 1.0  # Claims kept per extracted unit.
    skip_share: float = 0.35  # Share of units the extractor will skip.
    stack_share: float = 0.25  # Share of claims sent to a stacking call.
    paragraph_keep_share: float = 0.26  # Share of paragraphs that keep a claim (measured on Death in Space).
    zero_division_share: float = 0.05  # Share of paragraphs living in a division that yields no claim.

    @classmethod
    def from_env(cls) -> DecompositionSettings:
        """Read every setting from the environment, at call time."""
        return cls(
            window_words=_int(WINDOW_WORDS, cls.window_words),
            window_break=_choice(WINDOW_BREAK, cls.window_break, (BREAK_BUDGET, BREAK_HEADINGS)),
            extract_max_tokens=_int(EXTRACT_MAX_TOKENS, cls.extract_max_tokens),
            review_batch=_int(REVIEW_BATCH, cls.review_batch),
            graph_batch=_int(GRAPH_BATCH, cls.graph_batch),
            coverage_batch=_int(COVERAGE_BATCH, cls.coverage_batch),
            coverage_sample=_float(COVERAGE_SAMPLE, cls.coverage_sample),
            coverage_min_paragraphs=_int(COVERAGE_MIN_PARAGRAPHS, cls.coverage_min_paragraphs),
            skip_audit_batch=_int(SKIP_AUDIT_BATCH, cls.skip_audit_batch),
            skip_non_content=_bool(SKIP_NON_CONTENT, cls.skip_non_content),
            claims_per_sentence=_float(CLAIMS_PER_SENTENCE, cls.claims_per_sentence),
            skip_share=_float(SKIP_SHARE, cls.skip_share),
            stack_share=_float(STACK_SHARE, cls.stack_share),
            paragraph_keep_share=_float(PARAGRAPH_KEEP_SHARE, cls.paragraph_keep_share),
            zero_division_share=_float(ZERO_DIVISION_SHARE, cls.zero_division_share),
        )


# The values before phase 5a, so an old-vs-new comparison is only environment variables:
#   MONITOR_BOOK_WINDOW_WORDS=600 MONITOR_BOOK_WINDOW_BREAK=headings
#   MONITOR_BOOK_EXTRACT_MAX_TOKENS=16384 MONITOR_BOOK_REVIEW_BATCH=12
#   MONITOR_BOOK_GRAPH_BATCH=30 MONITOR_BOOK_COVERAGE_BATCH=8
#   MONITOR_BOOK_COVERAGE_SAMPLE=1.0 MONITOR_BOOK_SKIP_NON_CONTENT=0
# The estimate-only proxies stay at their defaults: they describe the book, not the run.
OLD = replace(
    DecompositionSettings(),
    window_words=600,
    window_break=BREAK_HEADINGS,
    extract_max_tokens=16384,
    review_batch=12,
    graph_batch=30,
    coverage_batch=8,
    coverage_sample=1.0,
    skip_non_content=False,
)
