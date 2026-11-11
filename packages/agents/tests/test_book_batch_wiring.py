"""Refusal-split and split-on-truncation wiring across every decomposition batch (I-17).

Every batch an extraction, review, graph or coverage call can be cut into is
driven through the shared helper `run_batch_with_refusal_split`, and each test
here proves the real helper is invoked with the expected arguments. A fake model
that truncates proves no partial reply is ever accepted as complete.
"""

from __future__ import annotations

import re

import pytest
from dspy.utils.exceptions import AdapterParseError
from monitor_agents.book_decomposition import extract_windows, knowledge_graph, review as review_mod
from monitor_agents.book_decomposition.calls import CallTally, tallying_extractor, tallying_graph, tallying_review
from monitor_agents.book_decomposition.extractor import (
    ExtractorResult,
    TruncatedOutput,
    WindowExtractionSignature,
)
from monitor_agents.book_decomposition.knowledge_graph import GraphBatch, build_graphs
from monitor_agents.book_decomposition.pipeline import ProvenancedAtom, WindowOutcome
from monitor_agents.book_decomposition.review import (
    Claim,
    ReviewReport,
    audit_coverage,
    audit_skipped_units,
    review_claims,
    stack_claims,
    verify_claims,
)
from monitor_agents.book_decomposition.review import _Working
from monitor_agents.book_decomposition.windows import build_windows
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookNode,
    BookNodeKind,
    BookTree,
    ClaimCheck,
    ClaimStatus,
    ClaimVerdict,
    CoverageAudit,
    DecompositionReport,
    ExtractedAtom,
    ReviewedClaim,
    SkipAudit,
    StackDecision,
    VerificationBatch,
    WindowExtraction,
)

LIVE_REFUSAL = "The request was rejected because it was considered high risk"


def _refusal() -> AdapterParseError:
    return AdapterParseError("ChatAdapter", WindowExtractionSignature, LIVE_REFUSAL)


def _tree(paragraphs: list[str]) -> BookTree:
    """One paragraph and one sentence per string, IDs p0/s0, p1/s1, ... (no divisions)."""
    nodes = [BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0)]
    for i, text in enumerate(paragraphs):
        nodes.append(
            BookNode(
                id=f"p{i}",
                doc_id="d",
                kind=BookNodeKind.PARAGRAPH,
                parent_id="root",
                seq=len(nodes),
                text=text,
                page_start=i,
                page_end=i,
            )
        )
        nodes.append(
            BookNode(
                id=f"s{i}",
                doc_id="d",
                kind=BookNodeKind.SENTENCE,
                parent_id=f"p{i}",
                seq=len(nodes),
                text=text,
                page_start=i,
                page_end=i,
            )
        )
    return BookTree(
        doc_id="d", title="T", decomposer_version="1", content_hash="x", nodes=nodes, report=DecompositionReport()
    )


def _eight_sentence_window():
    """One paragraph holding eight separate sentence nodes, packed into one window."""
    text = " ".join(f"Sentence {i} here." for i in range(8))
    nodes = [BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0)]
    nodes.append(
        BookNode(
            id="p0",
            doc_id="d",
            kind=BookNodeKind.PARAGRAPH,
            parent_id="root",
            seq=1,
            text=text,
            page_start=0,
            page_end=0,
        )
    )
    for i in range(8):
        nodes.append(
            BookNode(
                id=f"s{i}",
                doc_id="d",
                kind=BookNodeKind.SENTENCE,
                parent_id="p0",
                seq=len(nodes),
                text=f"Sentence {i} here.",
                page_start=0,
                page_end=0,
            )
        )
    tree = BookTree(
        doc_id="d", title="T", decomposer_version="1", content_hash="x", nodes=nodes, report=DecompositionReport()
    )
    [window] = build_windows(tree)
    assert len(window.units) == 8
    return window


class _RefusingExtractor:
    """Refuses any window above a size, like a provider that won't take the request."""

    def __init__(self, limit: int, error=None) -> None:
        self.limit = limit
        self.error = error or (lambda: RuntimeError(LIVE_REFUSAL))
        self.sizes: list[int] = []

    async def __call__(self, window) -> ExtractorResult:
        self.sizes.append(len(window.units))
        if len(window.units) > self.limit:
            raise self.error()
        atoms = [
            ExtractedAtom(kind=AtomKind.RULE, statement=f"Claim about {u.node_id}.", cites=[u.label])
            for u in window.units
        ]
        return ExtractorResult(WindowExtraction(atoms=atoms), 1, 1)


@pytest.mark.unit
async def test_extraction_refusal_halves_the_window_and_never_repeats_it():
    window = _eight_sentence_window()
    extractor = _RefusingExtractor(limit=2)
    [outcome] = await extract_windows([window], extractor)
    assert extractor.sizes == [8, 4, 4, 2, 2, 2, 2]  # Split, never the same 8 twice.
    assert outcome.uncovered == []
    assert {node for atom in outcome.atoms for node in atom.source_node_ids} == {unit.node_id for unit in window.units}


@pytest.mark.unit
async def test_extraction_truncation_splits_the_window_and_loses_no_sentence():
    window = _eight_sentence_window()
    extractor = _RefusingExtractor(limit=2, error=lambda: TruncatedOutput("cut off at the cap"))
    [outcome] = await extract_windows([window], extractor)
    assert outcome.uncovered == []
    assert extractor.sizes[0] == 8 and max(extractor.sizes[1:]) <= 4


@pytest.mark.unit
async def test_a_single_unit_refusal_is_recorded_without_an_unchanged_retry():
    window = _eight_sentence_window()
    single = window.restricted_to({window.units[0].label})
    extractor = _RefusingExtractor(limit=0)
    [outcome] = await extract_windows([single], extractor)
    assert extractor.sizes == [1]  # Never retried with the same single unit.
    assert outcome.uncovered == [single.units[0].node_id]
    assert LIVE_REFUSAL in outcome.errors[0]


# ---------------------------------------------------------------------------
# Verification: split on truncation, retry only the uncovered part (task: no loss)
# ---------------------------------------------------------------------------


class _HalvingVerify:
    """Answers fully, or refuses a too-big prompt; records every prompt's claim labels."""

    def __init__(self, refuse_above: int | None = None, omit_last: bool = False, half_first: bool = False) -> None:
        self.refuse_above = refuse_above
        self.omit_last = omit_last
        self.half_first = half_first
        self.prompts: list[list[str]] = []
        self.prompt_texts: list[str] = []
        self.calls = 0

    async def verify(self, prompt: str) -> VerificationBatch:
        labels = [match.group(0)[1:-1] for match in re.finditer(r"\[C\d+\]", prompt)]
        self.prompts.append(labels)
        self.prompt_texts.append(prompt)
        self.calls += 1
        if self.refuse_above is not None and len(labels) > self.refuse_above:
            raise _refusal()
        if self.half_first and len(labels) > 1 and len(self.prompt_texts) == 1:
            labels = labels[: len(labels) // 2]  # A reply that stops halfway.
        if self.omit_last and labels:
            labels = labels[:-1]
        return VerificationBatch(checks=[ClaimCheck(label=label, verdict=ClaimVerdict.SUPPORTED) for label in labels])

    async def stack(self, prompt: str) -> StackDecision:
        return StackDecision()

    async def audit_skips(self, prompt: str) -> SkipAudit:
        return SkipAudit()

    async def find_gaps(self, prompt: str) -> CoverageAudit:
        return CoverageAudit()


def _statements_in(prompt: str) -> list[str]:
    return re.findall(r"CLAIM: (.*?)\nHEADING", prompt)


def _claims(count: int) -> list[Claim]:
    claims = []
    for n in range(count):
        atom = ExtractedAtom(kind=AtomKind.RULE, statement=f"Rule number {n} applies.", cites=["S1"])
        claims.append(
            Claim(
                id=f"claim-{n}",
                atom=atom,
                source_node_ids=(f"s{n}",),
                page=n,
                source_text="Rule applies.",
                from_example_passage=False,
            )
        )
    return claims


@pytest.mark.unit
async def test_a_truncated_verification_batch_splits_and_every_claim_is_checked():
    claims = _claims(8)
    model = _HalvingVerify(refuse_above=4)
    held: list[dict[str, str]] = []
    checks = await verify_claims(claims, model, batch_size=8, held_sink=held)
    assert [len(prompt) for prompt in model.prompts] == [8, 4, 4]  # Halved, never repeated whole.
    assert sorted(checks) == sorted(claim.id for claim in claims)
    assert held == []


@pytest.mark.unit
async def test_only_the_uncovered_part_is_retried_after_a_partial_reply():
    claims = _claims(8)
    model = _HalvingVerify(half_first=True)
    held: list[dict[str, str]] = []
    checks = await verify_claims(claims, model, batch_size=8, held_sink=held)
    first_prompt, retry_prompt = model.prompt_texts
    assert len(_statements_in(first_prompt)) == 8
    # The retry carries only what the first reply left out, not the whole batch again.
    assert set(_statements_in(retry_prompt)) == set(_statements_in(first_prompt)[4:])
    assert sorted(checks) == sorted(claim.id for claim in claims)
    assert held == []


@pytest.mark.unit
async def test_a_claim_no_reply_ever_covers_is_held_with_a_reason():
    claims = _claims(4)
    model = _HalvingVerify(omit_last=True)
    held: list[dict[str, str]] = []
    checks = await verify_claims(claims, model, batch_size=4, held_sink=held)
    missing = sorted(set(claim.id for claim in claims) - set(checks))
    assert missing == ["claim-3"]
    assert held[0]["section_path"] == "claim-3"
    assert held[0]["stage"] == "verification"
    assert "did not include" in held[0]["reason"]


@pytest.mark.unit
async def test_refused_verification_claims_reach_the_held_sink_with_the_refusal():
    claims = _claims(4)
    held: list[dict[str, str]] = []
    checks = await verify_claims(claims, _HalvingVerify(refuse_above=0), batch_size=4, held_sink=held)
    assert checks == {}
    assert sorted(entry["section_path"] for entry in held) == [f"claim-{n}" for n in range(4)]
    assert all(LIVE_REFUSAL in entry["reason"] for entry in held)
    assert all(entry["stage"] == "verification" for entry in held)


# ---------------------------------------------------------------------------
# The remaining review batches: stacking, skip audit, coverage
# ---------------------------------------------------------------------------


class _RefusingReview:
    """Every stage answers, except the one under test."""

    def __init__(self, *, refuse_stack=False, refuse_audit=False, refuse_gaps=False) -> None:
        self.refuse_stack = refuse_stack
        self.refuse_audit = refuse_audit
        self.refuse_gaps = refuse_gaps
        self.stack_calls = 0
        self.audit_calls = 0
        self.gap_calls = 0

    async def verify(self, prompt: str) -> VerificationBatch:
        labels = [match.group(0)[1:-1] for match in re.finditer(r"\[C\d+\]", prompt)]
        return VerificationBatch(checks=[ClaimCheck(label=label, verdict=ClaimVerdict.SUPPORTED) for label in labels])

    async def stack(self, prompt: str) -> StackDecision:
        self.stack_calls += 1
        if self.refuse_stack:
            raise _refusal()
        return StackDecision()

    async def audit_skips(self, prompt: str) -> SkipAudit:
        self.audit_calls += 1
        if self.refuse_audit:
            raise _refusal()
        return SkipAudit()

    async def find_gaps(self, prompt: str) -> CoverageAudit:
        self.gap_calls += 1
        if self.refuse_gaps:
            raise _refusal()
        return CoverageAudit()


def _outcome_with_skips() -> WindowOutcome:
    return WindowOutcome(
        window_id="w",
        skipped={"s0": "flavor"},
        cited=[],
    )


@pytest.mark.unit
async def test_a_refused_stacking_cluster_holds_each_claim_with_the_reason():
    first, second = "The Momentum pool holds at most 6 points.", "The Momentum pool holds at most six points total."
    tree = _tree(["Momentum pool holds 6, or six.", "Momentum pool holds 6, or six."])
    model = _RefusingReview(refuse_stack=True)
    result = await review_claims(
        tree,
        [
            WindowOutcome(
                window_id="w",
                atoms=[
                    ProvenancedAtom(
                        atom=ExtractedAtom(kind=AtomKind.RULE, statement=first, cites=["S1"]),
                        source_node_ids=["s0"],
                        page=0,
                    ),
                    ProvenancedAtom(
                        atom=ExtractedAtom(kind=AtomKind.RULE, statement=second, cites=["S1"]),
                        source_node_ids=["s1"],
                        page=1,
                    ),
                ],
            )
        ],
        model,
    )
    held = [entry for entry in result.report.held if entry["stage"] == "stacking"]
    assert len(held) == 2  # The cluster refused, split, and each single claim refused again.
    assert all(LIVE_REFUSAL in entry["reason"] for entry in held)
    assert model.stack_calls == 3  # Whole cluster, then each half once — never the same pair twice.
    statuses = {entry.status for entry in result.ledger}
    assert ClaimStatus.NEEDS_HUMAN in statuses


@pytest.mark.unit
async def test_a_refused_skip_audit_holds_the_sentences_it_could_not_recheck():
    tree = _tree(["Some flavor text."])
    model = _RefusingReview(refuse_audit=True)
    held: list[dict[str, str]] = []
    outcomes = await audit_skipped_units(tree, [_outcome_with_skips()], model, held_sink=held)
    assert held and held[0]["section_path"] == "s0" and held[0]["stage"] == "skip_audit"
    assert LIVE_REFUSAL in held[0]["reason"]
    assert "s0" in [nid for item in outcomes for nid in item.uncovered]


@pytest.mark.unit
async def test_a_refused_coverage_batch_holds_the_paragraphs():
    tree = _tree(["Players may add traits."])
    model = _RefusingReview(refuse_gaps=True)
    report = ReviewReport()
    # working: one accepted claim covering paragraph p0.
    atom = ExtractedAtom(kind=AtomKind.RULE, statement="Players may add traits.", cites=["S1"])
    claim = Claim(
        id="c1",
        atom=atom,
        source_node_ids=("s0",),
        page=0,
        source_text="Players may add traits.",
        from_example_passage=False,
        paragraph_ids=("p0",),
    )
    working = {"c1": _Working(claim, claim.atom.statement, ClaimStatus.ACCEPTED)}
    held: list[dict[str, str]] = []
    await audit_coverage(tree, working, model, report, held_sink=held)
    assert held and held[0]["section_path"] == "p0" and held[0]["stage"] == "coverage"
    assert LIVE_REFUSAL in held[0]["reason"]
    assert report.coverage_check_failures >= 1


# ---------------------------------------------------------------------------
# Graph batches: refusal through the helper, truncation split inside run
# ---------------------------------------------------------------------------


def _graph_claims(count: int) -> list[ReviewedClaim]:
    return [
        ReviewedClaim(
            id=f"g{n}",
            kind=AtomKind.RULE,
            statement=f"Momentum is spent on action {n}.",
            source_node_ids=[f"s{n}"],
            pages=[n],
            merged_from=[],
            domain="rules",
        )
        for n in range(count)
    ]


class _GraphScript:
    """Refuses a prompt over a size, or truncates it; answers otherwise."""

    def __init__(self, refuse_above: int | None = None, truncate_above: int | None = None) -> None:
        self.refuse_above = refuse_above
        self.truncate_above = truncate_above
        self.calls: list[int] = []

    async def propose(self, claims: str) -> GraphBatch:
        labels = re.findall(r"\[C\d+\]", claims)
        self.calls.append(len(labels))
        if self.refuse_above is not None and len(labels) > self.refuse_above:
            raise _refusal()
        if self.truncate_above is not None and len(labels) > self.truncate_above:
            raise TruncatedOutput("cut off at the cap")
        relationships = []
        for line in claims.splitlines():
            match = re.match(r"\[(C\d+)\]", line)
            if match is None:
                continue
            # The object must be named in the claim it cites: use the statement's last word.
            last_word = line.rsplit(")", 1)[-1].strip().rstrip(".").split()[-1]
            relationships.append(
                {
                    "subject": "Momentum",
                    "predicate": "used_in",
                    "object": f"Action {last_word}",
                    "cites": [match.group(1)],
                }
            )
        return GraphBatch(
            claim_domains={label: "rules" for label in labels},
            relationships=relationships,
        )

    async def find_duplicates(self, names: str):
        from monitor_agents.book_decomposition.knowledge_graph import MergeAnswer

        return MergeAnswer()


class _GraphStore:
    def __init__(self) -> None:
        self.saved: dict[str, GraphBatch] = {}

    def read(self) -> dict[str, GraphBatch]:
        return dict(self.saved)

    def append(self, key: str, answer: GraphBatch) -> None:
        self.saved[key] = answer


@pytest.mark.unit
async def test_graph_refusal_holds_the_claims_and_counts_the_batch_as_failed():
    held: list[dict[str, str]] = []
    model = _GraphScript(refuse_above=1)
    graphs, domains = await build_graphs(_graph_claims(4), model, _GraphStore(), held_sink=held)
    assert model.calls[:3] == [4, 2, 2]  # Whole batch, then each half once.
    assert sorted(entry["section_path"] for entry in held) == [f"g{n}" for n in range(4)]
    assert all(entry["stage"] == "graph" and LIVE_REFUSAL in entry["reason"] for entry in held)
    assert graphs["rules"].report.batches_failed == 1
    assert set(domains) == {"g0", "g1", "g2", "g3"}


@pytest.mark.unit
async def test_graph_truncation_splits_and_a_rerun_reuses_the_saved_halves():
    store = _GraphStore()
    model = _GraphScript(truncate_above=2)
    graphs, domains = await build_graphs(_graph_claims(4), model, store)
    assert model.calls == [4, 2, 2]  # Truncated once, then the two halves.
    assert set(domains) == {"g0", "g1", "g2", "g3"}  # Both halves' answers kept.
    # Every relationship survived the split, each citing a claim from its own half.
    assert {edge.object for edge in graphs["rules"].edges} == {"action 0", "action 1", "action 2", "action 3"}
    assert graphs["rules"].report.batches_failed == 0

    again = _GraphScript(truncate_above=2)
    await build_graphs(_graph_claims(4), again, store)
    # Only the doomed whole-batch prompt runs again; both halves come from the store.
    assert again.calls == [4]


# ---------------------------------------------------------------------------
# The real helper is invoked with the expected arguments (prove the wiring)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_stack_claims_calls_the_real_helper_with_the_cluster_and_claim_ids(monkeypatch):
    recorded: list[tuple[list[str], str]] = []
    real = review_mod.run_batch_with_refusal_split

    async def spy(items, run, *, id_of):
        recorded.append(([item.id for item in items], id_of(items[0])))
        return await real(items, run, id_of=id_of)

    monkeypatch.setattr(review_mod, "run_batch_with_refusal_split", spy)
    first, second = "The Momentum pool holds at most 6 points.", "The Momentum pool holds at most six points total."
    working = {}
    for claim_id, statement in (("c1", first), ("c2", second)):
        claim = Claim(
            id=claim_id,
            atom=ExtractedAtom(kind=AtomKind.RULE, statement=statement, cites=["S1"]),
            source_node_ids=("s0",),
            page=0,
            source_text=statement,
            from_example_passage=False,
        )
        working[claim_id] = _Working(claim, statement, ClaimStatus.ACCEPTED)
    await stack_claims(working, _RefusingReview(), ReviewReport())
    assert recorded, "stack_claims never used the refusal-split helper"
    assert recorded[0][0] == ["c1", "c2"]
    assert recorded[0][1] in {"c1", "c2"}  # id_of maps each claim to its own id.


@pytest.mark.unit
async def test_coverage_calls_the_real_helper_with_paragraph_batches(monkeypatch):
    recorded: list[tuple[list[str], str]] = []
    real = review_mod.run_batch_with_refusal_split

    async def spy(items, run, *, id_of):
        recorded.append(([item[0].id for item in items], id_of(items[0])))
        return await real(items, run, id_of=id_of)

    monkeypatch.setattr(review_mod, "run_batch_with_refusal_split", spy)
    tree = _tree(["Players may add traits."])
    atom = ExtractedAtom(kind=AtomKind.RULE, statement="Players may add traits.", cites=["S1"])
    claim = Claim(
        id="c1",
        atom=atom,
        source_node_ids=("s0",),
        page=0,
        source_text="Players may add traits.",
        from_example_passage=False,
        paragraph_ids=("p0",),
    )
    working = {"c1": _Working(claim, claim.atom.statement, ClaimStatus.ACCEPTED)}
    await audit_coverage(tree, working, _RefusingReview(), ReviewReport())
    assert recorded and recorded[0][0] == ["p0"]
    assert recorded[0][1] == "p0"  # Held items are keyed by the paragraph id.


@pytest.mark.unit
async def test_skip_audit_calls_the_real_helper_with_sentence_batches(monkeypatch):
    recorded: list[tuple[list[str], str]] = []
    real = review_mod.run_batch_with_refusal_split

    async def spy(items, run, *, id_of):
        recorded.append(([item[0] for item in items], id_of(items[0])))
        return await real(items, run, id_of=id_of)

    monkeypatch.setattr(review_mod, "run_batch_with_refusal_split", spy)
    tree = _tree(["Some flavor text."])
    await audit_skipped_units(tree, [_outcome_with_skips()], _RefusingReview())
    assert recorded and recorded[0][0] == ["s0"]
    assert recorded[0][1] == "s0"


@pytest.mark.unit
async def test_graph_calls_the_real_helper_with_claim_batches(monkeypatch):
    recorded: list[tuple[list[str], str]] = []
    real = knowledge_graph.run_batch_with_refusal_split

    async def spy(items, run, *, id_of):
        recorded.append(([item.id for item in items], id_of(items[0])))
        return await real(items, run, id_of=id_of)

    monkeypatch.setattr(knowledge_graph, "run_batch_with_refusal_split", spy)
    await build_graphs(_graph_claims(3), _GraphScript(), _GraphStore())
    assert recorded and recorded[0][0] == ["g0", "g1", "g2"]
    assert recorded[0][1] == "g0"


# ---------------------------------------------------------------------------
# Call tally wrappers (task 10: the actual count beside the estimate)
# ---------------------------------------------------------------------------


class _CountingExtractor:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, window):
        self.calls += 1
        raise RuntimeError("provider down")


class _CountingReview:
    def __init__(self) -> None:
        self.calls = 0

    async def verify(self, prompt):
        self.calls += 1
        raise RuntimeError("provider down")

    async def stack(self, prompt):
        self.calls += 1
        raise RuntimeError("provider down")

    async def audit_skips(self, prompt):
        self.calls += 1
        raise RuntimeError("provider down")

    async def find_gaps(self, prompt):
        self.calls += 1
        raise RuntimeError("provider down")


class _CountingGraph:
    def __init__(self) -> None:
        self.calls = 0

    async def propose(self, claims):
        self.calls += 1
        raise RuntimeError("provider down")

    async def find_duplicates(self, names):
        self.calls += 1
        raise RuntimeError("provider down")


@pytest.mark.unit
async def test_tallying_wrappers_count_every_stage_even_when_the_call_fails():
    tally = CallTally()
    window = _eight_sentence_window()

    extractor = tallying_extractor(_CountingExtractor(), tally)
    with pytest.raises(RuntimeError):
        await extractor(window)
    assert tally.get("extraction") == 1

    review_model = tallying_review(_CountingReview(), tally)
    for method in ("verify", "stack", "audit_skips", "find_gaps"):
        with pytest.raises(RuntimeError):
            await getattr(review_model, method)("prompt")
    assert tally.get("verification") == 1
    assert tally.get("stacking") == 1
    assert tally.get("skip_audit") == 1
    assert tally.get("coverage") == 1

    graph_model = tallying_graph(_CountingGraph(), tally)
    with pytest.raises(RuntimeError):
        await graph_model.propose("claims")
    with pytest.raises(RuntimeError):
        await graph_model.find_duplicates("names")
    assert tally.get("graph") == 2
    assert tally.total == 7
    assert set(tally.as_dict()) == {
        "extraction",
        "verification",
        "skip_audit",
        "stacking",
        "coverage",
        "graph",
    }


@pytest.mark.unit
async def test_tallying_wrappers_pass_arguments_through_unchanged():
    tally = CallTally()
    seen = {}

    class _Echo:
        async def __call__(self, window):
            seen["window"] = window
            return "extractor-result"

        async def verify(self, prompt):
            seen["prompt"] = prompt
            return "verify-result"

    extractor = tallying_extractor(_Echo(), tally)
    window = _eight_sentence_window()
    assert await extractor(window) == "extractor-result"
    assert seen["window"] is window
    model = tallying_review(_Echo(), tally)
    assert await model.verify("the prompt") == "verify-result"
    assert seen["prompt"] == "the prompt"
