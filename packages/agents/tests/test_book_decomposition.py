"""Tests for exhaustive window extraction (book decomposition prototype, I-17)."""

import json
from pathlib import Path
from types import SimpleNamespace

import dspy
import pytest
from dspy.utils import DummyLM
from dspy.utils.exceptions import AdapterParseError
from monitor_agents.book_decomposition import (
    DspyWindowExtractor,
    Unit,
    Window,
    WindowOutcome,
    build_coverage_report,
    build_windows,
    extract_windows,
    reconcile,
    validate_extraction,
)
from monitor_agents.book_decomposition.extractor import (
    ExtractorResult,
    MeteredLM,
    TruncatedOutput,
    WindowExtractionSignature,
    build_lm,
    failed_call_usage,
    prompt_fingerprint,
)
from monitor_agents.book_decomposition.review import (
    ClaimStackingSignature,
    ClaimVerificationSignature,
    SkipAuditSignature,
)
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookNode,
    BookNodeKind,
    BookTree,
    DecompositionReport,
    ExtractedAtom,
    SkipReason,
    UnitSkip,
    WindowExtraction,
)
from monitor_data.tools.ingest_tools.book_tree import decompose_pdf

FIXTURE = Path(__file__).parents[3] / "tests" / "fixtures" / "ingestion" / "tiny_rulebook.pdf"


@pytest.fixture
def tree() -> BookTree:
    return decompose_pdf(FIXTURE.read_bytes(), "doc", "Tiny")


def _synthetic_tree(paragraph_sentences: list[list[str]]) -> BookTree:
    nodes = [BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0)]
    nodes.append(
        BookNode(id="div", doc_id="d", kind=BookNodeKind.DIVISION, parent_id="root", seq=1, text="Chapter", page_start=0, page_end=0)
    )
    for p_index, sentences in enumerate(paragraph_sentences):
        paragraph = f"p{p_index}"
        nodes.append(
            BookNode(id=paragraph, doc_id="d", kind=BookNodeKind.PARAGRAPH, parent_id="div", seq=len(nodes), text=" ".join(sentences), page_start=0, page_end=0)
        )
        for s_index, sentence in enumerate(sentences):
            nodes.append(
                BookNode(id=f"{paragraph}s{s_index}", doc_id="d", kind=BookNodeKind.SENTENCE, parent_id=paragraph, seq=len(nodes), text=sentence, page_start=0, page_end=0)
            )
    return BookTree(doc_id="d", title="T", decomposer_version="1", content_hash="x", nodes=nodes, report=DecompositionReport())


def _atom(*cites: str, kind: AtomKind = AtomKind.AXIOM, **fields: str) -> ExtractedAtom:
    return ExtractedAtom(kind=kind, statement="A claim.", cites=list(cites), **fields)


def _complete(window: Window) -> WindowExtraction:
    return WindowExtraction(atoms=[_atom(unit.label) for unit in window.units])


class _Scripted:
    """An extractor that plays back a list of answers or exceptions, recording its calls."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[Window] = []

    async def __call__(self, window: Window) -> ExtractorResult:
        self.calls.append(window)
        answer = self.answers.pop(0) if self.answers else _complete
        if isinstance(answer, Exception):
            raise answer
        extraction = answer(window) if callable(answer) else answer
        return ExtractorResult(extraction, input_tokens=10, output_tokens=5)


@pytest.mark.unit
def test_every_sentence_lands_in_exactly_one_window(tree):
    windows = build_windows(tree, max_words=20)
    unit_ids = [unit.node_id for window in windows for unit in window.units]
    expected = [n.id for n in tree.nodes if n.kind in (BookNodeKind.SENTENCE, BookNodeKind.TABLE)]
    assert sorted(unit_ids) == sorted(expected)
    assert unit_ids == expected  # Reading order is kept as well.


@pytest.mark.unit
def test_windows_do_not_cross_divisions(tree):
    by_id = {n.id: n for n in tree.nodes}
    for window in build_windows(tree):
        parents = {by_id[by_id[u.node_id].parent_id].parent_id for u in window.units}
        assert parents == {window.division_id}


@pytest.mark.unit
def test_word_budget_splits_at_paragraphs_and_keeps_an_oversized_paragraph_whole():
    long_paragraph = [f"Sentence number {i} here." for i in range(10)]
    tree = _synthetic_tree([["Short one."], long_paragraph, ["Short two."]])
    windows = build_windows(tree, max_words=8)
    assert [len(w.units) for w in windows] == [1, 10, 1]


@pytest.mark.unit
def test_context_comes_from_the_previous_window_and_is_not_a_unit():
    tree = _synthetic_tree([["First passage text."], ["Second passage text."]])
    first, second = build_windows(tree, max_words=3)
    assert first.context == ""
    assert second.context == "First passage text."
    assert all("First" not in unit.text for unit in second.units)


@pytest.mark.unit
def test_validate_accepts_a_fully_accounted_window(tree):
    window = build_windows(tree)[0]
    labels = [u.label for u in window.units]
    extraction = WindowExtraction(
        atoms=[_atom(*labels[:-1])],
        skips=[UnitSkip(label=labels[-1], reason=SkipReason.FLAVOR)],
    )
    outcome = validate_extraction(window, extraction)
    assert outcome.uncovered == []
    assert outcome.atoms[0].source_node_ids == [u.node_id for u in window.units[:-1]]
    assert outcome.skipped == {window.units[-1].node_id: "flavor"}


@pytest.mark.unit
def test_validate_reports_units_the_model_ignored(tree):
    window = build_windows(tree)[0]
    outcome = validate_extraction(window, WindowExtraction())
    assert outcome.uncovered == [u.node_id for u in window.units]


@pytest.mark.unit
def test_validate_drops_atoms_citing_units_that_do_not_exist(tree):
    window = build_windows(tree)[0]
    real = window.units[0].label
    outcome = validate_extraction(window, WindowExtraction(atoms=[_atom(real, "S999"), _atom()]))
    assert outcome.atoms == []
    assert outcome.dropped_atoms == 2
    assert window.units[0].node_id in outcome.uncovered


@pytest.mark.unit
@pytest.mark.parametrize(
    "atom",
    [
        _atom("S1", kind=AtomKind.ENTITY),
        _atom("S1", kind=AtomKind.RELATIONSHIP, subject="A", predicate="rules"),
        ExtractedAtom(kind=AtomKind.AXIOM, statement="   ", cites=["S1"]),
    ],
)
def test_validate_drops_malformed_atoms(tree, atom):
    outcome = validate_extraction(build_windows(tree)[0], WindowExtraction(atoms=[atom]))
    assert outcome.atoms == []
    assert outcome.dropped_atoms == 1


@pytest.mark.unit
def test_a_citation_beats_a_skip_for_the_same_unit(tree):
    window = build_windows(tree)[0]
    label = window.units[0].label
    extraction = WindowExtraction(atoms=[_atom(label)], skips=[UnitSkip(label=label, reason=SkipReason.FLAVOR)])
    outcome = validate_extraction(window, extraction)
    assert outcome.skipped == {}
    assert outcome.cited == [window.units[0].node_id]


@pytest.mark.unit
async def test_retry_sends_only_the_units_still_missing(tree):
    window = build_windows(tree)[0]
    first = window.units[0].label
    extractor = _Scripted(WindowExtraction(atoms=[_atom(first)]))
    [outcome] = await extract_windows([window], extractor)
    assert outcome.uncovered == []
    assert outcome.attempts == 2
    assert [u.label for u in extractor.calls[1].units] == [u.label for u in window.units[1:]]
    assert len(outcome.atoms) == len(window.units)


@pytest.mark.unit
async def test_failures_are_reported_as_uncovered_instead_of_hidden(tree):
    windows = build_windows(tree)
    extractor = _Scripted(RuntimeError("provider down"), RuntimeError("provider down"))
    outcomes = await extract_windows(windows[:1], extractor)
    report = build_coverage_report(windows[:1], outcomes)
    assert report.units_uncovered == len(windows[0].units)
    assert report.windows_incomplete == 1
    assert report.coverage == 0.0
    assert "provider down" in outcomes[0].errors[0]


def _parse_error() -> AdapterParseError:
    return AdapterParseError("ChatAdapter", WindowExtractionSignature, "truncated output")


class _FailsAboveSize:
    """Fails to parse any window larger than a limit, like output hitting a token cap."""

    def __init__(self, limit: int):
        self.limit = limit
        self.sizes: list[int] = []

    async def __call__(self, window: Window) -> ExtractorResult:
        self.sizes.append(len(window.units))
        if len(window.units) > self.limit:
            raise _parse_error()
        return ExtractorResult(_complete(window))


@pytest.mark.unit
async def test_unparseable_output_splits_the_window_instead_of_repeating_the_request():
    tree = _synthetic_tree([[f"Sentence {i} here." for i in range(8)]])
    [window] = build_windows(tree)
    extractor = _FailsAboveSize(limit=2)
    [outcome] = await extract_windows([window], extractor)
    assert outcome.uncovered == []
    assert extractor.sizes[:3] == [8, 4, 4]
    assert max(extractor.sizes[3:]) <= 2
    assert {n for atom in outcome.atoms for n in atom.source_node_ids} == {
        unit.node_id for unit in window.units
    }


@pytest.mark.unit
async def test_a_unit_that_never_parses_is_reported_and_its_neighbors_still_extract():
    tree = _synthetic_tree([["First one.", "Second one.", "Third one."]])
    [window] = build_windows(tree)
    bad = window.units[1]

    async def extractor(part: Window) -> ExtractorResult:
        if bad in part.units:
            raise _parse_error()
        return ExtractorResult(_complete(part))

    [outcome] = await extract_windows([window], extractor)
    assert outcome.uncovered == [bad.node_id]
    assert len(outcome.atoms) == 2


@pytest.mark.unit
def test_minimax_routes_through_anthropic_format_with_its_own_key(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
    lm = build_lm("minimax/MiniMax-M3")
    assert lm.model == "anthropic/MiniMax-M3"
    assert lm.kwargs["api_key"] == "minimax-key"
    assert lm.kwargs["api_base"] == "https://api.minimax.io/anthropic"


@pytest.mark.unit
def test_minimax_without_a_key_refuses_to_fall_back_to_anthropic(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    with pytest.raises(RuntimeError, match="MINIMAX_API_KEY"):
        build_lm("minimax/MiniMax-M3")


@pytest.mark.unit
def test_letter_spaced_heading_repeating_its_division_is_left_out_of_the_path():
    tree = _synthetic_tree([["Some text."]])
    tree.nodes.insert(
        2,
        BookNode(id="h", doc_id="d", kind=BookNodeKind.HEADING, parent_id="div", seq=2, text="C h a p t e r", page_start=0, page_end=0),
    )
    assert build_windows(tree)[0].heading_path == ("Chapter",)


@pytest.mark.unit
def test_prompt_fingerprint_changes_when_the_prompt_changes(monkeypatch):
    before = prompt_fingerprint()
    assert before == prompt_fingerprint()
    monkeypatch.setattr(
        "monitor_agents.book_decomposition.extractor.WindowExtractionSignature",
        SimpleNamespace(instructions="A different prompt."),
    )
    assert prompt_fingerprint() != before


@pytest.mark.unit
async def test_transient_failure_recovers_on_retry(tree):
    window = build_windows(tree)[0]
    [outcome] = await extract_windows([window], _Scripted(RuntimeError("timeout")))
    assert outcome.uncovered == []
    assert outcome.errors == ["RuntimeError: timeout"]


@pytest.mark.unit
async def test_coverage_counts_against_expected_units_not_what_the_model_returned(tree):
    windows = build_windows(tree)
    outcomes = await extract_windows(windows[:1], _Scripted())
    report = build_coverage_report(windows, outcomes)
    assert report.units_total == sum(len(w.units) for w in windows)
    assert report.units_uncovered == report.units_total - len(windows[0].units)
    assert report.coverage < 1.0


@pytest.mark.unit
async def test_coverage_counts_a_unit_in_several_atoms_once_and_totals_usage(tree):
    window = build_windows(tree)[0]
    labels = [u.label for u in window.units]
    extraction = WindowExtraction(atoms=[_atom(*labels), _atom(*labels)])
    outcomes = await extract_windows([window], _Scripted(extraction))
    report = build_coverage_report([window], outcomes)
    assert report.units_cited == len(labels)
    assert report.atoms_by_kind == {"axiom": 2}
    assert (report.input_tokens, report.output_tokens) == (10, 5)


@pytest.mark.unit
async def test_dspy_extractor_parses_a_real_adapter_response(tree):
    window = build_windows(tree)[0]
    answer = WindowExtraction(atoms=[_atom(u.label) for u in window.units])
    lm = DummyLM([{"result": json.dumps(answer.model_dump(mode="json"))}])
    result = await DspyWindowExtractor(lm=lm)(window)
    assert validate_extraction(window, result.extraction).uncovered == []


def _lm_response(content, finish_reason="stop", completion_tokens=100, *, cache_hit=False):
    import litellm

    response = litellm.ModelResponse(
        choices=[{"message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        usage={"prompt_tokens": 10, "completion_tokens": completion_tokens, "total_tokens": 10 + completion_tokens},
    )
    if cache_hit:
        response.cache_hit = True
        response.usage = {}
    return response


def _scripted_lm(monkeypatch, responses):
    """A real metered LM with only the network call replaced."""
    script = list(responses)

    def forward(self, **_):
        # Not next(iterator): StopIteration can't cross asyncio.to_thread, and the test would hang.
        if not script:
            raise AssertionError("The LM was called more times than scripted")
        return script.pop(0)

    monkeypatch.setattr(dspy.LM, "forward", forward)
    return MeteredLM("anthropic/fake", cache=False)


def _answer(label="S1"):
    extraction = WindowExtraction(atoms=[ExtractedAtom(kind=AtomKind.RULE, statement="A claim.", cites=[label])])
    return f"[[ ## result ## ]]\n{extraction.model_dump_json()}\n\n[[ ## completed ## ]]"


_ONE_UNIT = Window(id="w", division_id="d", heading_path=("C",), context="", units=(Unit("n", "S1", BookNodeKind.SENTENCE, "Text.", 0),))


@pytest.mark.unit
async def test_extractor_reports_tokens_from_the_response(monkeypatch):
    lm = _scripted_lm(monkeypatch, [_lm_response(_answer())])
    result = await DspyWindowExtractor(lm=lm)(_ONE_UNIT)
    assert (result.input_tokens, result.output_tokens) == (10, 100)
    assert result.extraction.atoms[0].statement == "A claim."


@pytest.mark.unit
async def test_a_cut_off_answer_fails_even_when_it_parses_and_keeps_its_cost(monkeypatch):
    """DSPy can repair cut-off JSON, which would silently lose claims."""
    lm = _scripted_lm(monkeypatch, [_lm_response(_answer(), "length", 16384)])
    with pytest.raises(TruncatedOutput) as caught:
        await DspyWindowExtractor(lm=lm)(_ONE_UNIT)
    assert failed_call_usage(caught.value) == (10, 16384)


@pytest.mark.unit
async def test_an_answer_of_only_reasoning_counts_every_hidden_retry(monkeypatch):
    """Real failure on Dune: no text at all, after the whole token limit went to reasoning."""
    lm = _scripted_lm(monkeypatch, [_lm_response(None, "length", 16384), _lm_response(None, "length", 16384)])
    with pytest.raises(AdapterParseError) as caught:
        await DspyWindowExtractor(lm=lm)(_ONE_UNIT)
    assert failed_call_usage(caught.value) == (20, 32768)


@pytest.mark.unit
async def test_cached_cut_off_answer_costs_nothing_but_still_fails(monkeypatch):
    lm = _scripted_lm(monkeypatch, [_lm_response(_answer(), "length", cache_hit=True)])
    with pytest.raises(TruncatedOutput) as caught:
        await DspyWindowExtractor(lm=lm)(_ONE_UNIT)
    assert failed_call_usage(caught.value) == (0, 0)


@pytest.mark.unit
async def test_a_registry_lm_is_metered_too(monkeypatch):
    monkeypatch.setattr(dspy.LM, "forward", lambda self, **_: _lm_response(_answer(), "length", 16384))
    plain = dspy.LM("anthropic/fake", cache=False)
    with pytest.raises(TruncatedOutput):
        await DspyWindowExtractor(lm=plain)(_ONE_UNIT)


@pytest.mark.unit
def test_failed_call_usage_defaults_to_zero():
    assert failed_call_usage(RuntimeError("x")) == (0, 0)
    assert failed_call_usage(None) == (0, 0)


@pytest.mark.unit
def test_batch_lms_leave_retries_to_the_run_guard(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    assert build_lm("minimax/MiniMax-M3").num_retries == 0
    assert build_lm("gemini/gemini-2.5-flash").num_retries == 0


@pytest.mark.unit
def test_reasoning_effort_is_sent_only_when_asked(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    assert "reasoning_effort" not in build_lm("minimax/MiniMax-M3").kwargs
    kwargs = build_lm("minimax/MiniMax-M3", "low").kwargs
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["allowed_openai_params"] == ["reasoning_effort"]


@pytest.mark.unit
def test_truncated_output_counts_toward_quarantine():
    outcome = WindowOutcome(window_id="w", uncovered=["n"], errors=["TruncatedOutput: cut off"])
    assert reconcile(["n"], [outcome] * 3).quarantined == {"n"}


@pytest.mark.unit
@pytest.mark.parametrize("word", ["veto", "gamemaster", "traits"])
def test_prompts_do_not_contain_the_cases_the_first_real_test_checks(word):
    """Dune Chapter 5's dropped veto is the test, so the prompts can't quote the answer."""
    for signature in (WindowExtractionSignature, ClaimVerificationSignature, ClaimStackingSignature, SkipAuditSignature):
        assert word not in signature.instructions.casefold()
