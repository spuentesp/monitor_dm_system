"""Refusal-split batch helper: halves and retries once, holds what still refuses (I-2, I-17).

Unit tests drive the helper with fakes; the last three tests prove the example
call sites in book_decomposition.review.verify_claims and
analyzer._batched_extract_all invoke the real helper with the real arguments.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
import structlog
from dspy.utils.exceptions import AdapterParseError
from monitor_agents.book_batching import BatchOutcome, HeldItem, run_batch_with_refusal_split
from monitor_agents.book_decomposition.extractor import WindowExtractionSignature
from monitor_agents.book_decomposition.review import Claim, verify_claims
from monitor_agents.llm_errors import LLMErrorClass, classify_llm_error
from monitor_agents.utils.analyzer_support import SectionDigest
from monitor_data.schemas.book_graph import (
    AtomKind,
    ClaimCheck,
    ClaimVerdict,
    ExtractedAtom,
    VerificationBatch,
)

LIVE_REFUSAL = "The request was rejected because it was considered high risk"


def _refusal() -> AdapterParseError:
    return AdapterParseError("ChatAdapter", WindowExtractionSignature, LIVE_REFUSAL)


class _Item:
    def __init__(self, id: str) -> None:
        self.id = id


class _ScriptedRun:
    """Records every call's ids and returns/raises what the script says."""

    def __init__(self, script: dict[tuple[str, ...], object]) -> None:
        self.script = script
        self.calls: list[tuple[str, ...]] = []

    async def __call__(self, items) -> object:
        ids = tuple(item.id for item in items)
        self.calls.append(ids)
        outcome = self.script[ids]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _items(*ids: str) -> list[_Item]:
    return [_Item(id_) for id_ in ids]


@pytest.mark.unit
async def test_success_first_try_returns_one_result_and_no_holds() -> None:
    run = _ScriptedRun({("a", "b"): "done"})
    outcome = await run_batch_with_refusal_split(_items("a", "b"), run, id_of=lambda i: i.id)
    assert outcome == BatchOutcome(results=["done"], held=[])
    assert run.calls == [("a", "b")]


@pytest.mark.unit
async def test_empty_batch_is_not_run() -> None:
    run = _ScriptedRun({})
    outcome = await run_batch_with_refusal_split([], run, id_of=lambda i: i.id)
    assert outcome == BatchOutcome(results=[], held=[])
    assert run.calls == []


@pytest.mark.unit
async def test_refusal_splits_in_half_and_retries_each_half_once() -> None:
    run = _ScriptedRun(
        {
            ("a", "b", "c", "d"): _refusal(),
            ("a", "b"): "left",
            ("c", "d"): "right",
        }
    )
    outcome = await run_batch_with_refusal_split(_items("a", "b", "c", "d"), run, id_of=lambda i: i.id)
    assert outcome.results == ["left", "right"]
    assert outcome.held == []
    assert run.calls == [("a", "b", "c", "d"), ("a", "b"), ("c", "d")]


@pytest.mark.unit
async def test_half_that_refuses_again_is_held_with_ids_and_reason() -> None:
    run = _ScriptedRun(
        {
            ("a", "b", "c", "d"): _refusal(),
            ("a", "b"): _refusal(),
            ("c", "d"): "right",
        }
    )
    outcome = await run_batch_with_refusal_split(_items("a", "b", "c", "d"), run, id_of=lambda i: i.id)
    assert outcome.results == ["right"]
    assert [held.id for held in outcome.held] == ["a", "b"]
    for held in outcome.held:
        assert isinstance(held, HeldItem)
        assert LIVE_REFUSAL in held.reason
        assert "AdapterParseError" in held.reason
    # Each half got exactly one attempt: no deeper recursion.
    assert run.calls == [("a", "b", "c", "d"), ("a", "b"), ("c", "d")]


@pytest.mark.unit
async def test_odd_batch_splits_into_one_and_two() -> None:
    run = _ScriptedRun(
        {
            ("a", "b", "c"): _refusal(),
            ("a",): "left",
            ("b", "c"): "right",
        }
    )
    outcome = await run_batch_with_refusal_split(_items("a", "b", "c"), run, id_of=lambda i: i.id)
    assert outcome.results == ["left", "right"]
    assert run.calls == [("a", "b", "c"), ("a",), ("b", "c")]


@pytest.mark.unit
async def test_single_item_refusal_is_held_without_an_unchanged_retry() -> None:
    run = _ScriptedRun({("a",): _refusal()})
    outcome = await run_batch_with_refusal_split(_items("a"), run, id_of=lambda i: i.id)
    assert outcome.results == []
    assert len(outcome.held) == 1
    assert outcome.held[0].id == "a"
    assert LIVE_REFUSAL in outcome.held[0].reason
    assert run.calls == [("a",)]


@pytest.mark.unit
async def test_both_halves_refusing_holds_every_item() -> None:
    run = _ScriptedRun(
        {
            ("a", "b", "c", "d"): _refusal(),
            ("a", "b"): _refusal(),
            ("c", "d"): _refusal(),
        }
    )
    outcome = await run_batch_with_refusal_split(_items("a", "b", "c", "d"), run, id_of=lambda i: i.id)
    assert outcome.results == []
    assert [held.id for held in outcome.held] == ["a", "b", "c", "d"]


@pytest.mark.unit
async def test_refusal_phrase_in_a_plain_exception_also_splits() -> None:
    """The helper classifies through the real classify_llm_error, both shapes."""
    run = _ScriptedRun(
        {
            ("a", "b"): RuntimeError(LIVE_REFUSAL),
            ("a",): "left",
            ("b",): "right",
        }
    )
    outcome = await run_batch_with_refusal_split(_items("a", "b"), run, id_of=lambda i: i.id)
    assert outcome.results == ["left", "right"]
    assert classify_llm_error(RuntimeError(LIVE_REFUSAL)).error_class == LLMErrorClass.CONTENT_REFUSED


@pytest.mark.unit
async def test_non_refusal_failure_propagates_without_splitting() -> None:
    run = _ScriptedRun({("a", "b"): RuntimeError("connection reset")})
    with pytest.raises(RuntimeError, match="connection reset"):
        await run_batch_with_refusal_split(_items("a", "b"), run, id_of=lambda i: i.id)
    assert run.calls == [("a", "b")]


# ---------------------------------------------------------------------------
# Example call site 1: book_decomposition.review.verify_claims
# ---------------------------------------------------------------------------


def _claim(n: int) -> Claim:
    atom = ExtractedAtom(kind=AtomKind.RULE, statement=f"Rule number {n} applies.", cites=["S1"])
    return Claim(
        id=f"claim-{n}",
        atom=atom,
        source_node_ids=("n1",),
        page=0,
        source_text="Rule number applies.",
        from_example_passage=False,
    )


class _RefusingAboveTwo:
    """Refuses any prompt with 3+ claims (the full batch), answers smaller ones."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def verify(self, prompt: str) -> VerificationBatch:
        self.prompts.append(prompt)
        labels = [match.group(0)[1:-1] for match in re.finditer(r"\[C\d+\]", prompt)]
        if len(labels) >= 3:
            raise _refusal()
        return VerificationBatch(checks=[ClaimCheck(label=label, verdict=ClaimVerdict.SUPPORTED) for label in labels])


@pytest.mark.unit
async def test_verify_claims_example_call_site_splits_and_keeps_both_halves() -> None:
    claims = [_claim(n) for n in range(1, 5)]
    model = _RefusingAboveTwo()

    checks = await verify_claims(claims, model, batch_size=4, concurrency=2)

    assert len(model.prompts) == 3  # full batch, then each half — refusal not retried as-is
    assert sorted(checks) == [f"claim-{n}" for n in range(1, 5)]


class _AlwaysRefusing:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def verify(self, prompt: str) -> VerificationBatch:
        self.prompts.append(prompt)
        raise _refusal()


@pytest.mark.unit
async def test_verify_claims_example_call_site_records_held_claims() -> None:
    claims = [_claim(n) for n in range(1, 5)]
    model = _AlwaysRefusing()

    with structlog.testing.capture_logs() as logs:
        checks = await verify_claims(claims, model, batch_size=4, concurrency=2)

    assert checks == {}
    assert len(model.prompts) == 3
    held_events = [entry for entry in logs if entry["event"] == "claim_verification_held"]
    assert sorted(entry["claim_id"] for entry in held_events) == [f"claim-{n}" for n in range(1, 5)]
    assert all(LIVE_REFUSAL in entry["reason"] for entry in held_events)


# ---------------------------------------------------------------------------
# Example call site 2: analyzer._batched_extract_all
# ---------------------------------------------------------------------------


def _section(path: str, text: str) -> SectionDigest:
    return SectionDigest(section_path=path, text=text, min_page=0, min_chunk_index=0)


@pytest.mark.unit
async def test_batched_extract_example_call_site_splits_and_collects_both_halves(monkeypatch, caplog) -> None:
    from monitor_agents.analyzer import Analyzer
    from monitor_agents.analyzer.analyzer import BatchedExtractionSignature

    analyzer = Analyzer()
    sections = [_section("Chapter > Alpha", "alpha body"), _section("Chapter > Beta", "beta body")]
    contexts: list[str] = []

    async def fake_call_module(module, *, stage=None, batch_id=None, **kwargs):
        context = kwargs["sections_context"]
        contexts.append(context)
        if "alpha body" in context and "beta body" in context:
            raise AdapterParseError("ChatAdapter", BatchedExtractionSignature, LIVE_REFUSAL)
        if "alpha body" in context:
            return SimpleNamespace(axioms=[SimpleNamespace(statement="left axiom")], entities=[], lore_facts=[])
        return SimpleNamespace(axioms=[SimpleNamespace(statement="right axiom")], entities=[], lore_facts=[])

    monkeypatch.setattr(analyzer, "_call_module", fake_call_module)

    axioms, entities, lore = await analyzer._batched_extract_all(sections, "Source", True, True, True)

    assert len(contexts) == 3
    assert "alpha body" in contexts[0] and "beta body" in contexts[0]
    assert "alpha body" in contexts[1] and "beta body" not in contexts[1]
    assert "beta body" in contexts[2] and "alpha body" not in contexts[2]
    assert [axiom.statement for axiom in axioms] == ["left axiom", "right axiom"]
    assert entities == []
    assert lore == []
    assert not [r for r in caplog.records if "held section" in r.getMessage()]


@pytest.mark.unit
async def test_batched_extract_example_call_site_holds_sections_that_still_refuse(monkeypatch, caplog) -> None:
    from monitor_agents.analyzer import Analyzer
    from monitor_agents.analyzer.analyzer import BatchedExtractionSignature

    analyzer = Analyzer()
    sections = [_section("Chapter > Alpha", "alpha body"), _section("Chapter > Beta", "beta body")]
    calls: list[list[str]] = []

    async def fake_call_module(module, *, stage=None, batch_id=None, **kwargs):
        context = kwargs["sections_context"]
        calls.append([s.section_path for s in sections if s.text in context])
        raise AdapterParseError("ChatAdapter", BatchedExtractionSignature, LIVE_REFUSAL)

    monkeypatch.setattr(analyzer, "_call_module", fake_call_module)

    axioms, entities, lore = await analyzer._batched_extract_all(sections, "Source", True, True, True)

    # Full batch, then each half exactly once; nothing else.
    assert calls == [
        ["Chapter > Alpha", "Chapter > Beta"],
        ["Chapter > Alpha"],
        ["Chapter > Beta"],
    ]
    assert axioms == [] and entities == [] and lore == []
    held_messages = [record.getMessage() for record in caplog.records if "held section" in record.getMessage()]
    assert len(held_messages) == 2
    assert any("Chapter > Alpha" in message for message in held_messages)
    assert any("Chapter > Beta" in message for message in held_messages)
