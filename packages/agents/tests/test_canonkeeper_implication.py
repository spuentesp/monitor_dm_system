"""Tests for the G-9 implication-level contradiction check.

Covers:
- ``ImplicationContradictionModule.forward``: numbered-list parsing, the
  audit field (``implications``), NONE handling, alternative line formats
- ``CanonKeeper.implication_conflict_flags``: context assembly, flag shape
  (type/severity), chunking, fail-soft behaviour
- The Phase 1 setting stays off by default — the check must not change
  behaviour until its false-positive rate is measured.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.canonkeeper.verification import (
    BatchContradictionModule,
    ImplicationContradictionModule,
    ImplicationContradictionSignature,
)


@contextmanager
def _no_lm():
    """Neutralise the DSPy LM resolution — hermetic tests never call a model."""
    with patch("monitor_agents.dspy_runtime.dspy_context_for", return_value=nullcontext()):
        yield


def _stub_module(contradictions: str, implications: str = "") -> ImplicationContradictionModule:
    module = ImplicationContradictionModule()
    module.verify = MagicMock(return_value=SimpleNamespace(contradictions=contradictions, implications=implications))
    return module


class TestImplicationModuleParsing:
    def test_none_output_yields_no_flags(self):
        module = _stub_module("NONE", "NONE")
        with patch("monitor_agents.dspy_runtime.dspy_context_for", return_value=nullcontext()):
            assert module.forward(context="ctx", new_facts="1. thing") == {}

    def test_flagged_candidate_carries_its_reasoning_chain(self):
        module = _stub_module("1: implies the king is dead", "1: canon implies he died in battle")
        with patch("monitor_agents.dspy_runtime.dspy_context_for", return_value=nullcontext()):
            result = module.forward(context="ctx", new_facts="1. thing\n2. other")

        assert result == {
            1: {
                "explanation": "implies the king is dead",
                "implications": "canon implies he died in battle",
            }
        }

    def test_implications_for_unflagged_candidates_are_ignored(self):
        module = _stub_module("1: reason", "2: chain for something that was not flagged")
        with patch("monitor_agents.dspy_runtime.dspy_context_for", return_value=nullcontext()):
            result = module.forward(context="ctx", new_facts="1. thing\n2. other")

        assert set(result) == {1}
        assert result[1]["implications"] == ""

    def test_alternative_line_formats_are_accepted(self):
        module = _stub_module("2) dashed reason", "2) dashed chain")
        with patch("monitor_agents.dspy_runtime.dspy_context_for", return_value=nullcontext()):
            result = module.forward(context="ctx", new_facts="1. a\n2. b")

        assert result[2]["explanation"] == "dashed reason"
        assert result[2]["implications"] == "dashed chain"

    def test_parsing_is_shared_with_the_direct_batch_check(self):
        assert ImplicationContradictionModule._LINE_RE is BatchContradictionModule._LINE_RE

    def test_signature_states_the_grounding_rules(self):
        doc = ImplicationContradictionSignature.__doc__ or ""
        assert "IMPLICITLY" in doc
        assert "never reject" in doc.lower()


class TestImplicationConflictFlags:
    @pytest.mark.asyncio
    async def test_no_canon_context_yields_no_flags(self):
        keeper = CanonKeeper()
        keeper._fetch_canon_facts = AsyncMock(return_value=[])
        keeper._fetch_canon_axioms = AsyncMock(return_value=[])

        assert await keeper.implication_conflict_flags(uuid4(), ["some statement"]) == []

    @pytest.mark.asyncio
    async def test_empty_statements_yield_no_flags(self):
        keeper = CanonKeeper()
        keeper._fetch_canon_facts = AsyncMock(return_value=[{"statement": "fact"}])
        keeper._fetch_canon_axioms = AsyncMock(return_value=[])

        assert await keeper.implication_conflict_flags(uuid4(), []) == []
        assert await keeper.implication_conflict_flags(uuid4(), ["   "]) == []

    @pytest.mark.asyncio
    async def test_flags_carry_type_and_high_severity(self):
        keeper = CanonKeeper()
        keeper._fetch_canon_facts = AsyncMock(return_value=[{"statement": "The king died"}])
        keeper._fetch_canon_axioms = AsyncMock(return_value=[])

        stub = _stub_module(
            "1: the candidate denies the king's death",
            "1: canon implies he died in battle",
        )
        with (
            _no_lm(),
            patch(
                "monitor_agents.canonkeeper.verification.ImplicationContradictionModule",
                return_value=stub,
            ),
        ):
            flags = await keeper.implication_conflict_flags(uuid4(), ["The king lives"])

        assert len(flags) == 1
        flag = flags[0]
        assert flag["statement"] == "The king lives"
        assert flag["contradiction_type"] == "implication_conflict"
        assert flag["severity"] == "high"
        assert flag["implications"].startswith("canon implies")

    @pytest.mark.asyncio
    async def test_candidates_are_chunked(self):
        """The batched shape (one call per chunk of candidates)."""
        keeper = CanonKeeper()
        keeper._fetch_canon_facts = AsyncMock(return_value=[{"statement": "fact"}])
        keeper._fetch_canon_axioms = AsyncMock(return_value=[])

        stub = _stub_module("NONE", "NONE")
        with (
            _no_lm(),
            patch(
                "monitor_agents.canonkeeper.verification.ImplicationContradictionModule",
                return_value=stub,
            ),
            patch("monitor_data.config.settings.canonkeeper_implication_chunk_size", 2),
            patch(
                "monitor_data.config.settings.canonkeeper_per_candidate_checks", False
            ),
        ):
            await keeper.implication_conflict_flags(uuid4(), ["a", "b", "c"])

        assert stub.verify.call_count == 2

    @pytest.mark.asyncio
    async def test_the_per_candidate_shape_asks_once_per_candidate(self):
        """The measured shape (G08): one candidate per call."""
        keeper = CanonKeeper()
        keeper._fetch_canon_facts = AsyncMock(return_value=[{"statement": "fact"}])
        keeper._fetch_canon_axioms = AsyncMock(return_value=[])

        stub = _stub_module("NONE", "NONE")
        with (
            _no_lm(),
            patch(
                "monitor_agents.canonkeeper.verification.ImplicationContradictionModule",
                return_value=stub,
            ),
            patch(
                "monitor_data.config.settings.canonkeeper_per_candidate_checks", True
            ),
        ):
            await keeper.implication_conflict_flags(uuid4(), ["a", "b", "c"])

        assert stub.verify.call_count == 3
        # Each call carries exactly one candidate.
        assert stub.verify.call_args_list[0].kwargs["new_facts"] == "1. a"

    @pytest.mark.asyncio
    async def test_module_failure_degrades_to_no_flags(self):
        keeper = CanonKeeper()
        keeper._fetch_canon_facts = AsyncMock(return_value=[{"statement": "fact"}])
        keeper._fetch_canon_axioms = AsyncMock(return_value=[])

        stub = _stub_module("NONE")
        stub.verify.side_effect = Exception("LLM unavailable")
        with (
            _no_lm(),
            patch(
                "monitor_agents.canonkeeper.verification.ImplicationContradictionModule",
                return_value=stub,
            ),
        ):
            flags = await keeper.implication_conflict_flags(uuid4(), ["a"])

        assert flags == []


def test_implication_check_is_off_by_default():
    """Phase 1 measures first — the check must not change behaviour yet."""
    from monitor_data.config import Settings

    field = Settings.model_fields["canonkeeper_implication_check_enabled"]
    assert field.default is False
