"""Tests for the [G-2](b) analyzer-side module-intro extraction.

Covers:
  * ``_extract_module_intro`` gating: only ADVENTURE_MODULE packs call the
    LLM (rulebooks short-circuit cheaply).
  * Length floor: returned text must exceed 40 chars or it's treated as no
    intro.
  * LLM failure: extraction returns ``None`` and warns-and-continues — no
    exception leaks to the caller.
  * ``_format_first_n_sections`` shapes the section window correctly
    (page-ordered, bounded by ``n``, skips empty).

NOTE on async: tests use ``asyncio.run`` because this repo's pytest-asyncio
class-level marker + ``asyncio_mode=auto`` are not picking up class methods
consistently across all runner versions. Function-level ``async def``
without the class marker reproduces the same flake — running via asyncio.run
is hermetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from monitor_data.schemas.knowledge_packs import KnowledgePackType

from monitor_agents.analyzer._core import Analyzer


@dataclass
class _FakeDigest:
    """Minimal stand-in for SectionDigest used by the formatter helper."""

    section_path: str
    text: str
    min_page: int = 0
    min_chunk_index: int = 0


def _bundle(*section_texts: tuple[str, str]) -> SimpleNamespace:
    """Build a minimal ``_SectionBundle`` with the given (path, text) pairs."""
    digests = [
        _FakeDigest(section_path=p, text=t, min_page=i, min_chunk_index=i) for i, (p, t) in enumerate(section_texts)
    ]
    return SimpleNamespace(content_sections=digests)


VALID_INTRO = (
    "A pale sun rose over the wreck of the Iolarite, its blue-white glow "
    "picking out the names scratched into the hull — yours among them. "
    "The last thing you remember is the gravimetric shear and the smell "
    "of burning coolant."
)
SHORT_INTRO = "Too short."
RULEBOOK_FIRST_PAGES = [
    ("Chapter 1: System Overview", "D100-based percentile system. Roll under your skill."),
    (
        "Chapter 2: Skills",
        "Skills improve with use. Most characters start with a few basic skills.",
    ),
]


@pytest.mark.asyncio
class TestExtractModuleIntro:
    """``_extract_module_intro`` gating + floor + error tolerance."""

    def _make_analyzer(self) -> Analyzer:
        """Construct a bare Analyzer (no LLM calls during ``__init__``)."""
        return Analyzer(agent_id="test-analyzer")

    async def test_rulebook_pack_skips_llm_call(self) -> None:
        """RULEBOOK packs short-circuit to ``""`` without invoking the LLM."""
        analyzer = self._make_analyzer()
        analyzer._module_intro_extractor = MagicMock()  # would raise if called

        result = await analyzer._extract_module_intro(
            pack_type=KnowledgePackType.RULEBOOK,
            source_name="Generic Rulebook",
            sections=_bundle(*RULEBOOK_FIRST_PAGES),
        )

        assert result == ""
        analyzer._module_intro_extractor.assert_not_called()

    async def test_setting_supplement_skips_llm_call(self) -> None:
        """Non-adventure pack types also short-circuit."""
        analyzer = self._make_analyzer()
        analyzer._module_intro_extractor = MagicMock()

        result = await analyzer._extract_module_intro(
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
            source_name="Setting Supplement",
            sections=_bundle(*RULEBOOK_FIRST_PAGES),
        )
        assert result == ""

    async def test_adventure_module_calls_llm_and_returns_intro(self) -> None:
        """ADVENTURE_MODULE with substantive intro → LLM call returns the intro."""
        from contextlib import nullcontext

        analyzer = self._make_analyzer()
        analyzer._module_intro_extractor = MagicMock(return_value=SimpleNamespace(intro_text=VALID_INTRO))

        # Patch the dspy context manager to a nullcontext so pytest-socket
        # doesn't block the LLM-provider resolution. The point of this test
        # is the gating + length floor — the LLM call itself is mocked.
        with patch("monitor_agents.dspy_runtime.dspy_context_for", lambda *a, **kw: nullcontext()):
            result = await analyzer._extract_module_intro(
                pack_type=KnowledgePackType.ADVENTURE_MODULE,
                source_name="Dead Gods",
                sections=_bundle(*RULEBOOK_FIRST_PAGES),
            )

        assert result == VALID_INTRO
        analyzer._module_intro_extractor.assert_called_once()

    async def test_llm_returns_short_intro_is_treated_as_none(self) -> None:
        """LLM returning intro ≤40 chars → caller treats it as no intro."""
        from contextlib import nullcontext

        analyzer = self._make_analyzer()
        analyzer._module_intro_extractor = MagicMock(return_value=SimpleNamespace(intro_text=SHORT_INTRO))
        with patch("monitor_agents.dspy_runtime.dspy_context_for", lambda *a, **kw: nullcontext()):
            result = await analyzer._extract_module_intro(
                pack_type=KnowledgePackType.ADVENTURE_MODULE,
                source_name="Short Intro Module",
                sections=_bundle(*RULEBOOK_FIRST_PAGES),
            )

        assert result is None

    async def test_llm_returns_empty_string_is_treated_as_none(self) -> None:
        from contextlib import nullcontext

        analyzer = self._make_analyzer()
        analyzer._module_intro_extractor = MagicMock(return_value=SimpleNamespace(intro_text=""))
        with patch("monitor_agents.dspy_runtime.dspy_context_for", lambda *a, **kw: nullcontext()):
            result = await analyzer._extract_module_intro(
                pack_type=KnowledgePackType.ADVENTURE_MODULE,
                source_name="Empty Module",
                sections=_bundle(*RULEBOOK_FIRST_PAGES),
            )
        assert result is None

    async def test_llm_exception_warns_and_returns_none(self) -> None:
        """A failing DSPy call must NOT crash the analyzer — fall back to None."""
        from contextlib import nullcontext

        analyzer = self._make_analyzer()
        analyzer._module_intro_extractor = MagicMock(side_effect=RuntimeError("dspy exploded"))
        with patch("monitor_agents.dspy_runtime.dspy_context_for", lambda *a, **kw: nullcontext()):
            result = await analyzer._extract_module_intro(
                pack_type=KnowledgePackType.ADVENTURE_MODULE,
                source_name="Doomed Module",
                sections=_bundle(*RULEBOOK_FIRST_PAGES),
            )
        assert result is None

    async def test_empty_sections_returns_none(self) -> None:
        """No content sections → no LLM call, returns None."""
        analyzer = self._make_analyzer()
        analyzer._module_intro_extractor = MagicMock()

        result = await analyzer._extract_module_intro(
            pack_type=KnowledgePackType.ADVENTURE_MODULE,
            source_name="Empty Doc",
            sections=_bundle(),  # no sections
        )

        assert result is None
        analyzer._module_intro_extractor.assert_not_called()


class TestFormatFirstNSections:
    """``_format_first_n_sections`` shapes the LLM input correctly."""

    def test_returns_empty_for_empty_bundle(self) -> None:
        assert Analyzer._format_first_n_sections(_bundle(), n=6) == ""

    def test_includes_heading_and_text_for_each_section(self) -> None:
        bundle = _bundle(
            ("Chapter 1: Arrival", "You wake aboard the drifting hulk."),
            ("Chapter 2: First Contact", "The salvage crew finds you unconscious."),
        )
        out = Analyzer._format_first_n_sections(bundle, n=6)
        assert "## Chapter 1: Arrival" in out
        assert "drifting hulk" in out
        assert "## Chapter 2: First Contact" in out
        assert "salvage crew" in out
        # sections separated by the divider
        assert "---" in out

    def test_caps_at_n_sections(self) -> None:
        bundle = _bundle(*[(f"Chapter {i}", f"Body {i}") for i in range(1, 11)])
        out = Analyzer._format_first_n_sections(bundle, n=3)
        # Only first 3 sections present
        assert "## Chapter 1" in out
        assert "## Chapter 2" in out
        assert "## Chapter 3" in out
        assert "## Chapter 4" not in out
        assert "## Chapter 10" not in out

    def test_skips_sections_with_no_text(self) -> None:
        bundle = _bundle(
            ("Chapter 1: Arrival", "Real text."),
            ("Chapter 2: Empty", ""),
        )
        out = Analyzer._format_first_n_sections(bundle, n=6)
        assert "## Chapter 1" in out
        assert "## Chapter 2" not in out  # empty section skipped

    def test_text_truncated_per_section(self) -> None:
        long_body = "x" * 5000
        bundle = _bundle(("Chapter 1", long_body))
        out = Analyzer._format_first_n_sections(bundle, n=6)
        # Body is truncated to 4000 chars before being placed inside the section.
        assert "x" * 4000 in out
        # The 5001st x is NOT in the bundle because of the [..4000] slice per section.
        assert "x" * 4001 not in out.split("Chapter 1", 1)[1].split("---", 1)[0]
