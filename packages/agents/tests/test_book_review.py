"""Tests for claim review: nothing gets lost, examples are kept apart (prototype, I-17)."""

import asyncio
import json

import pytest
from dspy.utils import DummyLM
from monitor_agents.book_decomposition.pipeline import ProvenancedAtom, WindowOutcome
from monitor_agents.book_decomposition.pacing import RunStopped
from monitor_agents.book_decomposition.review import (
    CheckLog,
    CoverageLog,
    DspyReviewModel,
    ReviewResult,
    build_claims,
    check_ledger,
    cluster_claims,
    example_continuations,
    format_for_stacking,
    format_for_verification,
    quantity_clusters,
    sample_character_names,
    restrict_to_pages,
    review_claims,
    terms_not_fully_compared,
)
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookNode,
    BookNodeKind,
    BookTree,
    ClaimCheck,
    ClaimStack,
    ClaimStatus,
    ClaimVerdict,
    CoverageAudit,
    CoverageGap,
    DecompositionReport,
    ExtractedAtom,
    LedgerEntry,
    SkipAudit,
    StackDecision,
    StackRelation,
    VerificationBatch,
)


def _tree(paragraphs: list[str]) -> BookTree:
    """One paragraph and one sentence per string, with IDs p0/s0, p1/s1, ..."""
    nodes = [BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0)]
    for i, text in enumerate(paragraphs):
        nodes.append(BookNode(id=f"p{i}", doc_id="d", kind=BookNodeKind.PARAGRAPH, parent_id="root", seq=len(nodes), text=text, page_start=i, page_end=i))
        nodes.append(BookNode(id=f"s{i}", doc_id="d", kind=BookNodeKind.SENTENCE, parent_id=f"p{i}", seq=len(nodes), text=text, page_start=i, page_end=i))
    return BookTree(doc_id="d", title="T", decomposer_version="1", content_hash="x", nodes=nodes, report=DecompositionReport())


def _item(statement: str, source: int, kind: AtomKind = AtomKind.RULE, **fields: str) -> ProvenancedAtom:
    atom = ExtractedAtom(kind=kind, statement=statement, cites=["S1"], **fields)
    return ProvenancedAtom(atom=atom, source_node_ids=[f"s{source}"], page=source)


def _outcome(*items: ProvenancedAtom, skipped: dict[str, str] | None = None) -> WindowOutcome:
    return WindowOutcome(window_id="w", atoms=list(items), skipped=skipped or {})


class _Model:
    """Scripted review model. `verdicts` maps claim text to a verdict; default is supported."""

    def __init__(self, verdicts=None, stacks=None, rescued=None, fail_verify=False, fail_stack=False, fail_audit=False, gaps=(), fail_gaps=False):
        self.gaps = list(gaps)
        self.fail_gaps = fail_gaps
        self.coverage_prompts = []
        self.verdicts = verdicts or {}
        self.stacks = stacks or (lambda _: [])
        self.rescued = rescued or []
        self.fail_verify = fail_verify
        self.fail_stack = fail_stack
        self.fail_audit = fail_audit

    async def verify(self, prompt: str) -> VerificationBatch:
        if self.fail_verify:
            raise RuntimeError("provider down")
        checks = []
        for block in prompt.split("\n\n"):
            label = block.split("]")[0].strip("[")
            claim = block.split("CLAIM: ")[1].split("\nHEADING")[0]
            verdict, *rest = self.verdicts.get(claim, (ClaimVerdict.SUPPORTED,))
            checks.append(ClaimCheck(label=label, verdict=verdict, corrected_statement=rest[0] if rest else None, reason="because"))
        return VerificationBatch(checks=checks)

    async def stack(self, prompt: str) -> StackDecision:
        if self.fail_stack:
            raise RuntimeError("provider down")
        return StackDecision(stacks=self.stacks(prompt))

    async def audit_skips(self, prompt: str) -> SkipAudit:
        if self.fail_audit:
            raise RuntimeError("provider down")
        return SkipAudit(atoms=self.rescued)

    async def find_gaps(self, prompt: str) -> CoverageAudit:
        self.coverage_prompts.append(prompt)
        if self.fail_gaps:
            raise RuntimeError("provider down")
        return CoverageAudit(gaps=self.gaps)


def _status(result: ReviewResult, statement: str) -> ClaimStatus:
    return next(e.status for e in result.ledger if e.original_statement == statement)


DUPLICATES = ("The Momentum pool holds at most 6 points.", "The Momentum pool holds at most six points total.")


def _same_stack(prompt: str) -> list[ClaimStack]:
    return [ClaimStack(labels=["C1", "C2"], relation=StackRelation.SAME, canonical_statement="The Momentum pool holds at most 6 points.")]


@pytest.mark.unit
async def test_supported_claim_is_accepted_with_its_citation():
    tree = _tree(["Roll two dice."])
    result = await review_claims(tree, [_outcome(_item("Players roll two dice.", 0))], _Model())
    assert result.claims[0].statement == "Players roll two dice."
    assert result.claims[0].source_node_ids == ["s0"]
    assert result.report.ledger_problems == []


@pytest.mark.unit
async def test_correction_replaces_the_statement_and_keeps_the_original_in_the_ledger():
    tree = _tree(["Add traits, but the gamemaster may refuse them."])
    original = "Players may add as many traits as they like."
    fixed = "Players may add traits, subject to gamemaster veto."
    model = _Model({original: (ClaimVerdict.CORRECTED, fixed)})
    result = await review_claims(tree, [_outcome(_item(original, 0))], model)
    assert result.claims[0].statement == fixed
    assert _status(result, original) == ClaimStatus.CORRECTED
    assert result.ledger[0].original_statement == original


@pytest.mark.unit
async def test_a_correction_with_no_new_text_goes_to_a_person():
    tree = _tree(["Source."])
    model = _Model({"A claim here.": (ClaimVerdict.CORRECTED,)})
    result = await review_claims(tree, [_outcome(_item("A claim here.", 0))], model)
    assert _status(result, "A claim here.") == ClaimStatus.NEEDS_HUMAN
    assert result.claims == []


@pytest.mark.unit
async def test_examples_stay_out_of_canon_but_are_kept_and_not_orphaned():
    tree = _tree(["Example: Mira rolls and gets Intoxicated."])
    claim = "Mira is Intoxicated."
    result = await review_claims(tree, [_outcome(_item(claim, 0))], _Model({claim: (ClaimVerdict.EXAMPLE,)}))
    assert result.claims == []
    assert _status(result, claim) == ClaimStatus.EXAMPLE
    assert result.report.orphaned_sentences == []


@pytest.mark.unit
def test_claims_from_example_paragraphs_are_flagged_for_the_verifier():
    tree = _tree(["Example: Mira rolls.", "Players roll."])
    claims = build_claims(tree, [_outcome(_item("Mira rolls.", 0), _item("Players roll.", 1))])
    assert [c.from_example_passage for c in claims] == [True, False]


@pytest.mark.unit
async def test_rejecting_a_sentences_only_claim_reports_that_sentence_as_orphaned():
    """The safeguard against missing things: a bad deletion can't go unnoticed."""
    tree = _tree(["Important rule text.", "Other rule text."])
    bad, good = "Filler claim here.", "Other rule claim."
    result = await review_claims(
        tree, [_outcome(_item(bad, 0), _item(good, 1))], _Model({bad: (ClaimVerdict.FILLER,)})
    )
    assert _status(result, bad) == ClaimStatus.REJECTED
    assert result.report.orphaned_sentences == ["s0"]


@pytest.mark.unit
async def test_rejected_claim_with_another_claim_on_its_sentence_is_not_orphaned():
    tree = _tree(["Rule text."])
    bad, good = "Filler claim here.", "Good claim here."
    result = await review_claims(
        tree, [_outcome(_item(bad, 0), _item(good, 0))], _Model({bad: (ClaimVerdict.FILLER,)})
    )
    assert result.report.orphaned_sentences == []


@pytest.mark.unit
async def test_verification_failure_sends_claims_to_a_person_and_never_approves_them():
    tree = _tree(["Rule text."])
    result = await review_claims(tree, [_outcome(_item("A claim.", 0))], _Model(fail_verify=True))
    assert result.claims == []
    assert _status(result, "A claim.") == ClaimStatus.NEEDS_HUMAN
    assert result.report.claims_unchecked == 1


@pytest.mark.unit
async def test_duplicates_merge_and_the_survivor_inherits_every_citation():
    tree = _tree(["Momentum pool holds 6 points, or at most six.", "Later: Momentum pool holds 6 points, or at most six."])
    result = await review_claims(
        tree,
        [_outcome(_item(DUPLICATES[0], 0), _item(DUPLICATES[1], 1))],
        _Model(stacks=_same_stack),
    )
    assert len(result.claims) == 1
    assert result.claims[0].source_node_ids == ["s0", "s1"]
    assert result.claims[0].pages == [0, 1]
    assert _status(result, DUPLICATES[1]) == ClaimStatus.MERGED
    assert result.report.ledger_problems == []
    assert result.report.orphaned_sentences == []


@pytest.mark.unit
async def test_contradiction_the_source_settles_rejects_the_misreading():
    tree = _tree(["Momentum pool max is 6, not 8.", "Momentum pool max is 6, not 8, repeated."])
    wrong, right = "The Momentum pool holds at most 8 points.", "The Momentum pool holds at most 6 points."

    def stacks(_):
        return [ClaimStack(labels=["C1", "C2"], relation=StackRelation.CONTRADICTION, settled_by_source=True, wrong_labels=["C1"], canonical_statement=right, reason="source says 6")]

    result = await review_claims(tree, [_outcome(_item(wrong, 0), _item(right, 1))], _Model(stacks=stacks))
    assert _status(result, wrong) == ClaimStatus.REJECTED
    assert [c.statement for c in result.claims] == [right]
    assert result.report.contradictions_settled == 1
    assert result.report.orphaned_sentences == ["s0"]


@pytest.mark.unit
async def test_contradiction_the_source_cannot_settle_goes_to_a_person():
    tree = _tree(["Momentum pool max is 6.", "Momentum pool max is 8."])
    first, second = "The Momentum pool holds at most 6 points.", "The Momentum pool holds at most 8 points."

    def stacks(_):
        return [ClaimStack(labels=["C1", "C2"], relation=StackRelation.CONTRADICTION, reason="the book disagrees with itself")]

    result = await review_claims(tree, [_outcome(_item(first, 0), _item(second, 1))], _Model(stacks=stacks))
    assert result.claims == []
    assert {e.status for e in result.ledger} == {ClaimStatus.NEEDS_HUMAN}
    assert result.report.contradictions_for_human == 1
    assert result.report.orphaned_sentences == []


@pytest.mark.unit
async def test_settled_contradiction_without_a_stated_answer_goes_to_a_person():
    tree = _tree(["Momentum pool max is 6.", "Momentum pool max is 8."])
    first, second = "The Momentum pool holds at most 6 points.", "The Momentum pool holds at most 8 points."

    def stacks(_):
        return [ClaimStack(labels=["C1", "C2"], relation=StackRelation.CONTRADICTION, settled_by_source=True, wrong_labels=["C1"])]

    result = await review_claims(tree, [_outcome(_item(first, 0), _item(second, 1))], _Model(stacks=stacks))
    assert {e.status for e in result.ledger} == {ClaimStatus.NEEDS_HUMAN}


@pytest.mark.unit
async def test_stacking_failure_sends_those_claims_to_a_person_instead_of_approving_them():
    """A contradiction may have gone unseen, so "supported" alone isn't enough."""
    tree = _tree(["Momentum pool holds 6 points, or at most six.", "Momentum pool holds 6 points, or at most six.", "Three."])
    other = "Spice extends human life."
    result = await review_claims(
        tree,
        [_outcome(_item(DUPLICATES[0], 0), _item(DUPLICATES[1], 1), _item(other, 2))],
        _Model(fail_stack=True),
    )
    assert [c.statement for c in result.claims] == [other]
    assert _status(result, DUPLICATES[0]) == ClaimStatus.NEEDS_HUMAN
    assert _status(result, DUPLICATES[1]) == ClaimStatus.NEEDS_HUMAN
    assert result.report.stacking_failures == 1
    assert result.report.orphaned_sentences == []
    assert result.report.ledger_problems == []


@pytest.mark.unit
async def test_stack_with_invented_labels_changes_nothing():
    tree = _tree(["Momentum pool holds 6 points, or at most six.", "Momentum pool holds 6 points, or at most six."])

    def stacks(_):
        return [ClaimStack(labels=["C1", "C99"], relation=StackRelation.SAME, canonical_statement="X")]

    result = await review_claims(tree, [_outcome(_item(DUPLICATES[0], 0), _item(DUPLICATES[1], 1))], _Model(stacks=stacks))
    assert len(result.claims) == 2


@pytest.mark.unit
async def test_skip_audit_rescues_a_missed_claim_with_its_citation():
    tree = _tree(["At most three Determination.", "Filler."])
    rescued = ExtractedAtom(kind=AtomKind.RULE, statement="A character has at most three Determination.", cites=["S1"])
    outcome = _outcome(_item("Filler claim.", 1), skipped={"s0": "flavor"})
    result = await review_claims(tree, [outcome], _Model(rescued=[rescued]))
    assert result.report.rescued_from_skips == 1
    claim = next(c for c in result.claims if "Determination" in c.statement)
    assert claim.source_node_ids == ["s0"]


@pytest.mark.unit
async def test_skip_audit_failure_is_reported_and_doesnt_stop_review():
    tree = _tree(["Skipped.", "Kept."])
    outcome = _outcome(_item("Kept claim.", 1), skipped={"s0": "flavor"})
    result = await review_claims(tree, [outcome], _Model(fail_audit=True))
    assert result.report.skip_audit_failures == 1
    assert len(result.claims) == 1
    assert result.report.sentences_not_rechecked == ["s0"]


@pytest.mark.unit
async def test_a_successful_skip_audit_leaves_nothing_to_recheck():
    tree = _tree(["Skipped.", "Kept."])
    outcome = _outcome(_item("Kept claim.", 1), skipped={"s0": "flavor"})
    result = await review_claims(tree, [outcome], _Model())
    assert result.report.sentences_not_rechecked == []


@pytest.mark.unit
async def test_sentences_extraction_never_finished_are_reported():
    tree = _tree(["Lost.", "Finished later.", "Kept."])
    failed = WindowOutcome(window_id="a", uncovered=["s0", "s1"])
    retried = WindowOutcome(window_id="b", atoms=[_item("Kept claim.", 2)], cited=["s2"], skipped={"s1": "flavor"})
    result = await review_claims(tree, [failed, retried], _Model())
    assert result.report.sentences_never_extracted == ["s0"]


CONFLICTS = [
    ("The Momentum pool holds at most 6 points.", "A group can never save more than 8 Momentum."),
    ("A character starts each adventure with one Determination.", "Each hero starts with three Determination points."),
]


@pytest.mark.unit
@pytest.mark.parametrize(("first", "second"), CONFLICTS)
def test_differently_worded_numbers_for_one_term_become_candidates(first, second):
    claims = build_claims(_tree(["a", "b"]), [_outcome(_item(first, 0), _item(second, 1))])
    assert len(cluster_claims(claims)) == 2  # The wording alone wouldn't bring them together.
    assert [{c.atom.statement for c in group} for group in quantity_clusters(claims)] == [{first, second}]


@pytest.mark.unit
def test_quantity_clusters_ignore_claims_without_a_number_or_a_shared_term():
    items = [
        _item("Spending Momentum is optional for the Fremen.", 0),
        _item("A pool holds 6 Momentum.", 1),
        _item("A pool holds 8 Water.", 2),
    ]
    assert quantity_clusters(build_claims(_tree(["a", "b", "c"]), [_outcome(*items)])) == []


@pytest.mark.unit
async def test_differently_worded_contradiction_reaches_the_model_and_goes_to_a_person():
    first, second = CONFLICTS[0]
    seen: list[str] = []

    def stacks(prompt):
        seen.append(prompt)
        return [ClaimStack(labels=["C1", "C2"], relation=StackRelation.CONTRADICTION, reason="6 or 8")]

    result = await review_claims(_tree(["The Momentum pool holds 6 points, or 8.", "A group saves 6 or 8 Momentum."]), [_outcome(_item(first, 0), _item(second, 1))], _Model(stacks=stacks))
    assert len(seen) == 1
    assert {e.status for e in result.ledger} == {ClaimStatus.NEEDS_HUMAN}


@pytest.mark.unit
async def test_a_claim_settled_in_one_cluster_is_not_reopened_by_another():
    """A claim can sit in two clusters, and it must still end with one outcome."""
    rejected, kept, other = (
        "The Momentum pool holds at most 8 points.",
        "The Momentum pool holds at most 6 points.",
        "A group can never save more than 6 Momentum.",
    )

    def stacks(prompt):
        if other not in prompt:
            return [ClaimStack(labels=["C1", "C2"], relation=StackRelation.CONTRADICTION, settled_by_source=True, wrong_labels=["C1"], canonical_statement=kept)]
        return [ClaimStack(labels=["C1", "C2", "C3"], relation=StackRelation.SAME, canonical_statement=kept)]

    items = [_item(rejected, 0), _item(kept, 1), _item(other, 2)]
    result = await review_claims(_tree(["The Momentum pool holds 6 points, or 8."] * 3), [_outcome(*items)], _Model(stacks=stacks))
    assert _status(result, rejected) == ClaimStatus.REJECTED
    assert result.report.ledger_problems == []
    assert [c.statement for c in result.claims] == [kept]


@pytest.mark.unit
def test_clustering_groups_rewordings_and_conflicting_numbers_but_not_unrelated_claims():
    tree = _tree(["The Momentum pool holds 6 points, or 8."] * 4)
    items = [
        _item("The Momentum pool holds at most 6 points.", 0),
        _item("The Momentum pool holds at most 8 points.", 1),
        _item("A pool of Momentum holds points.", 2),
        _item("Spice extends human life.", 3),
    ]
    clusters = cluster_claims(build_claims(tree, [_outcome(*items)]))
    assert sorted(len(c) for c in clusters) == [1, 3]


@pytest.mark.unit
def test_entities_with_the_same_name_cluster_even_with_different_wording():
    tree = _tree(["a", "b"])
    items = [
        _item("Momentum is a resource.", 0, AtomKind.ENTITY, name="Momentum"),
        _item("Spent after passing tests.", 1, AtomKind.ENTITY, name="momentum"),
    ]
    assert len(cluster_claims(build_claims(tree, [_outcome(*items)]))) == 1


@pytest.mark.unit
def test_clusters_are_capped_so_one_call_stays_small():
    count = 30
    tree = _tree(["x"] * count)
    items = [_item(f"The Momentum pool holds points variant {'a' * (i + 1)}.", i) for i in range(count)]
    clusters = cluster_claims(build_claims(tree, [_outcome(*items)]), max_cluster=12)
    assert max(len(c) for c in clusters) <= 12
    assert sum(len(c) for c in clusters) == count


@pytest.mark.unit
@pytest.mark.parametrize(
    ("result", "fragment"),
    [
        (ReviewResult(), "no ledger entry"),
        (
            ReviewResult(ledger=[LedgerEntry(claim_id="x", kind=AtomKind.RULE, original_statement="s", status=ClaimStatus.MERGED, canonical_id="gone")]),
            "merged into a missing claim",
        ),
        (
            ReviewResult(ledger=[LedgerEntry(claim_id="x", kind=AtomKind.RULE, original_statement="s", status=ClaimStatus.ACCEPTED)]),
            "isn't in the output",
        ),
    ],
)
def test_ledger_check_catches_lost_claims(result, fragment):
    assert any(fragment in problem for problem in check_ledger(result, {"x"}))


@pytest.mark.unit
async def test_dspy_review_model_parses_a_real_adapter_response():
    answer = VerificationBatch(checks=[ClaimCheck(label="C1", verdict=ClaimVerdict.SUPPORTED)])
    lm = DummyLM([{"result": json.dumps(answer.model_dump(mode="json"))}])
    result = await DspyReviewModel(lm).verify("[C1] CLAIM: x\nSOURCE: y")
    assert result.checks[0].verdict == ClaimVerdict.SUPPORTED


class _CountingModel(_Model):
    def __init__(self, stop_after=None, **kwargs):
        super().__init__(**kwargs)
        self.verified: list[str] = []
        self.stop_after = stop_after

    async def verify(self, prompt: str) -> VerificationBatch:
        if self.stop_after is not None and len(self.verified) >= self.stop_after:
            raise RunStopped("quota")
        answer = await super().verify(prompt)
        self.verified.extend(b.split("CLAIM: ")[1].split("\nHEADING")[0] for b in prompt.split("\n\n"))
        return answer


def _spread_items(count: int) -> list[ProvenancedAtom]:
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa".split()
    return [_item(f"Claim about {words[i]}.", i) for i in range(count)]


@pytest.mark.unit
async def test_a_second_review_pays_for_no_finished_check_and_reports_them(tmp_path):
    log = CheckLog(tmp_path / "checks.jsonl")
    items = _spread_items(3)
    tree = _tree(["x"] * 3)
    await review_claims(tree, [_outcome(*items)], _CountingModel(), check_log=log)
    again = _CountingModel()
    result = await review_claims(tree, [_outcome(*items)], again, check_log=log)
    assert again.verified == []
    assert result.report.checks_reused == 3
    assert len(result.claims) == 3


@pytest.mark.unit
async def test_new_claims_shifting_the_batches_only_pay_for_the_new_claims(tmp_path):
    """This is what DSPy's whole-batch cache can't do."""
    log = CheckLog(tmp_path / "checks.jsonl")
    items = _spread_items(16)
    tree = _tree(["x"] * 16)
    await review_claims(tree, [_outcome(*items[1:])], _CountingModel(), check_log=log)
    again = _CountingModel()
    await review_claims(tree, [_outcome(*items)], again, check_log=log)
    assert again.verified == [items[0].atom.statement]


@pytest.mark.unit
async def test_stopping_mid_review_keeps_the_checks_already_done(tmp_path):
    log = CheckLog(tmp_path / "checks.jsonl")
    items = _spread_items(16)
    tree = _tree(["x"] * 16)
    with pytest.raises(RunStopped):
        await review_claims(tree, [_outcome(*items)], _CountingModel(stop_after=1), check_log=log, concurrency=1)
    assert len(log.read()) == 12
    finish = _CountingModel()
    result = await review_claims(tree, [_outcome(*items)], finish, check_log=log)
    assert len(finish.verified) == 4
    assert len(result.claims) == 16


@pytest.mark.unit
async def test_an_invalid_check_is_never_saved(tmp_path):
    log = CheckLog(tmp_path / "checks.jsonl")
    model = _CountingModel(verdicts={"A claim here.": (ClaimVerdict.CORRECTED,)})
    await review_claims(_tree(["x"]), [_outcome(_item("A claim here.", 0))], model, check_log=log)
    assert log.read() == {}


@pytest.mark.unit
async def test_a_torn_check_line_is_ignored_and_that_check_redone(tmp_path):
    log = CheckLog(tmp_path / "checks.jsonl")
    items = _spread_items(2)
    tree = _tree(["x"] * 2)
    await review_claims(tree, [_outcome(*items)], _CountingModel(), check_log=log)
    lines = log.path.read_text().splitlines()
    log.path.write_text(lines[0] + "\n" + lines[1][:20])
    again = _CountingModel()
    await review_claims(tree, [_outcome(*items)], again, check_log=log)
    assert len(again.verified) == 1


def _numeric_claims(count: int):
    tree = _tree(["x"] * count)
    words = [f"word{chr(97 + i)}" for i in range(count)]
    items = [_item(f"The Momentum {w} {w}x {w}y holds {i} points.", i) for i, w in enumerate(words)]
    return build_claims(tree, [_outcome(*items)])


@pytest.mark.unit
def test_a_common_terms_clusters_stay_capped_cover_everything_and_overlap():
    claims = _numeric_claims(26)
    clusters = quantity_clusters(claims, max_cluster=12)
    assert max(len(c) for c in clusters) <= 12
    assert {c.id for group in clusters for c in group} == {c.id for c in claims}
    assert {c.id for c in clusters[0]} & {c.id for c in clusters[1]}


@pytest.mark.unit
def test_similar_claims_of_a_common_term_land_in_one_cluster_however_far_apart():
    first = "The Momentum reserve for the Spacing Guild holds at most 6 points."
    second = "The Momentum reserve for the Spacing Guild holds at most 9 points."
    fillers = [f"The Momentum topic{chr(97 + i)} holds {i} points." for i in range(20)]
    statements = [first, *fillers, second]
    tree = _tree(["The Momentum reserve for the Spacing Guild holds 6, 7, 8 or 9 points."] * len(statements))
    claims = build_claims(tree, [_outcome(*[_item(s, i) for i, s in enumerate(statements)])])
    clusters = quantity_clusters(claims, max_cluster=12)
    assert any({first, second} <= {c.atom.statement for c in group} for group in clusters)


@pytest.mark.unit
def test_a_term_that_fits_in_one_cluster_is_fully_compared_and_a_larger_one_is_reported():
    assert terms_not_fully_compared(_numeric_claims(12), max_cluster=12) == []
    assert terms_not_fully_compared(_numeric_claims(13), max_cluster=12) == ["momentum"]


@pytest.mark.unit
async def test_review_report_names_terms_not_fully_compared():
    count = 13
    tree = _tree([f"The Momentum pool holds {i} points." for i in range(count)])
    words = [f"word{chr(97 + i)}" for i in range(count)]
    items = [_item(f"The Momentum {w} holds {i} points.", i) for i, w in enumerate(words)]
    result = await review_claims(tree, [_outcome(*items)], _Model())
    assert result.report.terms_not_fully_compared == ["momentum"]


@pytest.mark.unit
async def test_reviewing_some_pages_keeps_only_their_claims_and_sentences():
    tree = _tree(["a", "b", "c"])  # Pages are 0-indexed in the tree, 1-indexed for the reader.
    outcome = WindowOutcome(
        window_id="w",
        atoms=[_item("On first page.", 0), _item("On second page.", 1)],
        cited=["s0", "s1"],
        skipped={"s2": "flavor"},
        uncovered=["s1"],
    )
    [kept] = restrict_to_pages(tree, [outcome], 2, 2)
    assert [a.atom.statement for a in kept.atoms] == ["On second page."]
    assert (kept.cited, kept.skipped, kept.uncovered) == (["s1"], {}, ["s1"])
    assert len(outcome.atoms) == 2  # The original isn't changed.
    result = await review_claims(tree, [kept], _Model())
    assert [c.statement for c in result.claims] == ["On second page."]


EXAMPLE_STYLE = "Oblique|5"
BODY_STYLE = "Book|2"


def _styled_tree(rows: list[tuple[BookNodeKind, str, str | None]]) -> BookTree:
    """Rows of (kind, text, style), with paragraph IDs p0, p1, ... by row."""
    nodes = [BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0)]
    for i, (kind, text, style) in enumerate(rows):
        nodes.append(BookNode(id=f"p{i}", doc_id="d", kind=kind, parent_id="root", seq=len(nodes), text=text, page_start=i, page_end=i, style=style))
        nodes.append(BookNode(id=f"s{i}", doc_id="d", kind=BookNodeKind.SENTENCE, parent_id=f"p{i}", seq=len(nodes), text=text, page_start=i, page_end=i))
    return BookTree(doc_id="d", title="T", decomposer_version="3", content_hash="x", nodes=nodes, report=DecompositionReport())


PARA = BookNodeKind.PARAGRAPH
BODY = "A long ordinary paragraph of rules that sets the main style of this book."


@pytest.mark.unit
def test_unlabeled_paragraph_continuing_an_example_is_found():
    tree = _styled_tree([
        (PARA, BODY, BODY_STYLE),
        (PARA, "Example: Mira walks in.", EXAMPLE_STYLE),
        (PARA, "Mira attends the party.", EXAMPLE_STYLE),
        (PARA, "She whispers a hint.", EXAMPLE_STYLE),
        (PARA, BODY, BODY_STYLE),
        (PARA, "Example: Tobin moves.", EXAMPLE_STYLE),
    ])
    assert example_continuations(tree) == {"p2", "p3"}


@pytest.mark.unit
def test_quote_in_the_example_style_outside_a_run_is_not_an_example():
    tree = _styled_tree([
        (PARA, BODY, BODY_STYLE),
        (PARA, "Faith can be bought.", EXAMPLE_STYLE),
        (PARA, "Example: Mira walks in.", EXAMPLE_STYLE),
        (PARA, "Example: Tobin moves.", EXAMPLE_STYLE),
    ])
    assert example_continuations(tree) == set()


@pytest.mark.unit
def test_heading_ends_an_example_run():
    tree = _styled_tree([
        (PARA, BODY, BODY_STYLE),
        (PARA, "Example: Mira walks in.", EXAMPLE_STYLE),
        (PARA, "Example: Tobin moves.", EXAMPLE_STYLE),
        (BookNodeKind.HEADING, "Next Rule", "Heading|1"),
        (PARA, "Same style, new section.", EXAMPLE_STYLE),
    ])
    assert example_continuations(tree) == set()


@pytest.mark.unit
def test_label_in_body_style_never_marks_the_following_rules():
    tree = _styled_tree([
        (PARA, "Example: of how this works, read on through the book's main text.", BODY_STYLE),
        (PARA, "Example: another one written in the book's ordinary running text.", BODY_STYLE),
        (PARA, BODY, BODY_STYLE),
    ])
    assert example_continuations(tree) == set()


@pytest.mark.unit
def test_one_labeled_paragraph_does_not_make_a_style_mean_example():
    tree = _styled_tree([
        (PARA, BODY, BODY_STYLE),
        (PARA, "Example: Mira walks in.", EXAMPLE_STYLE),
        (PARA, "A sidebar in this style.", EXAMPLE_STYLE),
    ])
    assert example_continuations(tree) == set()


@pytest.mark.unit
def test_tree_without_style_information_finds_nothing():
    tree = _tree(["Example: Mira walks in.", "Mira attends the party."])
    assert example_continuations(tree) == set()


def _run_tree() -> BookTree:
    return _styled_tree([
        (PARA, BODY, BODY_STYLE),
        (PARA, "Example: Mira walks in.", EXAMPLE_STYLE),
        (PARA, "Mira attends the party.", EXAMPLE_STYLE),
        (PARA, "Example: Tobin moves.", EXAMPLE_STYLE),
    ])


@pytest.mark.unit
def test_layout_flag_reaches_the_verifier_prompt():
    claims = build_claims(_run_tree(), [_outcome(_item("Convivial is a trait.", 2))])
    assert claims[0].from_example_passage and claims[0].example_by_layout
    prompt = format_for_verification(claims)
    assert "from_example_passage=true" in prompt
    assert "continues a worked example" in prompt


@pytest.mark.unit
def test_labeled_and_ordinary_claims_get_no_layout_note():
    outcome = _outcome(_item("Mira walks.", 1), _item("Rules exist.", 0))
    assert "continues a worked example" not in format_for_verification(build_claims(_run_tree(), [outcome]))


@pytest.mark.unit
async def test_check_made_before_layout_flag_is_not_reused(tmp_path):
    log = CheckLog(tmp_path / "checks.jsonl")
    tree = _run_tree()
    outcome = _outcome(_item("Convivial is a trait.", 2), _item("Rules exist.", 0))
    plain, flagged = sorted(build_claims(tree, [outcome]), key=lambda c: c.example_by_layout)
    stale = ClaimCheck(label="C1", verdict=ClaimVerdict.SUPPORTED)
    log.append({plain.id: stale, flagged.id: stale})

    model = _Model(verdicts={"Convivial is a trait.": (ClaimVerdict.EXAMPLE,)})
    result = await review_claims(tree, [outcome], model, check_log=log)

    assert result.report.checks_reused == 1
    assert _status(result, "Convivial is a trait.") == ClaimStatus.EXAMPLE
    assert len(log.read()) == 3  # The stale check stays on file, beside the new one.


@pytest.mark.unit
async def test_verifier_can_keep_a_general_rule_found_in_a_run():
    model = _Model()  # Flagged, but the verifier says it's supported.
    outcome = _outcome(_item("The gamemaster receives Threat per player.", 2))
    tree = _styled_tree([
        (PARA, BODY, BODY_STYLE),
        (PARA, "Example: Mira walks in.", EXAMPLE_STYLE),
        (PARA, "The gamemaster receives Threat per player.", EXAMPLE_STYLE),
        (PARA, "Example: Tobin moves.", EXAMPLE_STYLE),
    ])
    result = await review_claims(tree, [outcome], model)
    assert _status(result, "The gamemaster receives Threat per player.") == ClaimStatus.ACCEPTED


@pytest.mark.unit
async def test_approved_claim_with_a_number_outside_its_source_goes_to_a_person():
    tree = _tree(["Roll two dice."])
    result = await review_claims(tree, [_outcome(_item("Players roll 5 dice.", 0))], _Model())
    assert _status(result, "Players roll 5 dice.") == ClaimStatus.NEEDS_HUMAN
    assert result.claims == []


@pytest.mark.unit
async def test_correction_that_invents_a_number_goes_to_a_person():
    tree = _tree(["Roll two dice."])
    model = _Model(verdicts={"Players roll dice.": (ClaimVerdict.CORRECTED, "Players roll 9 dice.")})
    result = await review_claims(tree, [_outcome(_item("Players roll dice.", 0))], model)
    assert _status(result, "Players roll dice.") == ClaimStatus.NEEDS_HUMAN


@pytest.mark.unit
async def test_correction_that_fixes_a_bad_number_is_kept():
    tree = _tree(["Roll two dice."])
    model = _Model(verdicts={"Players roll 5 dice.": (ClaimVerdict.CORRECTED, "Players roll 2 dice.")})
    result = await review_claims(tree, [_outcome(_item("Players roll 5 dice.", 0))], model)
    assert result.claims[0].statement == "Players roll 2 dice."





def _list_tree() -> BookTree:
    nodes = [BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0)]
    rows = [
        (BookNodeKind.HEADING, "h", "CHALLENGING (DIFFICULTY 2)"),
        (PARA, "p1", "Overcoming a complex lock"),
    ]
    for kind, node_id, text in rows:
        nodes.append(BookNode(id=node_id, doc_id="d", kind=kind, parent_id="root", seq=len(nodes), text=text, page_start=0, page_end=0))
    nodes.append(BookNode(id="s1", doc_id="d", kind=BookNodeKind.SENTENCE, parent_id="p1", seq=len(nodes), text="Overcoming a complex lock", page_start=0, page_end=0))
    return BookTree(doc_id="d", title="T", decomposer_version="3", content_hash="x", nodes=nodes, report=DecompositionReport())


@pytest.mark.unit
async def test_number_stated_by_the_heading_above_a_list_counts_as_in_the_source():
    statement = "Overcoming a complex lock is a Difficulty 2 skill test."
    outcome = _outcome(ProvenancedAtom(atom=ExtractedAtom(kind=AtomKind.RULE, statement=statement, cites=["S1"]), source_node_ids=["s1"], page=0))
    result = await review_claims(_list_tree(), [outcome], _Model())
    assert _status(result, statement) == ClaimStatus.ACCEPTED


@pytest.mark.unit
def test_verifier_and_stacker_see_the_heading_above_a_list():
    statement = "Overcoming a complex lock is a Difficulty 2 skill test."
    outcome = _outcome(ProvenancedAtom(atom=ExtractedAtom(kind=AtomKind.RULE, statement=statement, cites=["S1"]), source_node_ids=["s1"], page=0))
    claims = build_claims(_list_tree(), [outcome])
    assert "CHALLENGING (DIFFICULTY 2)" in format_for_verification(claims)
    assert "CHALLENGING (DIFFICULTY 2)" in format_for_stacking(claims, {claims[0].id: statement})


@pytest.mark.unit
def test_verifier_is_not_told_about_a_missing_number():
    claims = build_claims(_tree(["Roll two dice."]), [_outcome(_item("Players roll 5 dice.", 0))])
    assert "CHECK:" not in format_for_verification(claims)


@pytest.mark.unit
async def test_correction_that_grows_too_much_goes_to_a_person():
    original = "Roll two dice."
    long = "Roll two dice " + " ".join(["and"] * 30) + "."
    model = _Model(verdicts={original: (ClaimVerdict.CORRECTED, long)})
    result = await review_claims(_tree(["Roll two dice."]), [_outcome(_item(original, 0))], model)
    assert _status(result, original) == ClaimStatus.NEEDS_HUMAN


@pytest.mark.unit
async def test_name_given_earlier_in_the_section_is_not_a_false_alarm():
    tree = _styled_tree([(PARA, "Momentum is a pool.", None), (PARA, "Players spend it freely.", None)])
    statement = "Players spend Momentum freely."
    outcome = _outcome(_item(statement, 1))
    result = await review_claims(tree, [outcome], _Model())
    assert _status(result, statement) == ClaimStatus.ACCEPTED


@pytest.mark.unit
async def test_name_found_nowhere_in_the_section_goes_to_a_person():
    tree = _styled_tree([(PARA, "A pool exists.", None), (PARA, "Players spend it freely.", None)])
    statement = "Players spend Determination freely."
    result = await review_claims(tree, [_outcome(_item(statement, 1))], _Model())
    assert _status(result, statement) == ClaimStatus.NEEDS_HUMAN


@pytest.mark.unit
@pytest.mark.parametrize("verdict", [ClaimVerdict.FILLER, ClaimVerdict.UNSUPPORTED])
async def test_rejecting_a_claim_close_to_its_source_goes_to_a_person(verdict):
    statement = "A round ends after every hero has acted."
    tree = _tree(["After every hero has acted, the round ends."])
    result = await review_claims(tree, [_outcome(_item(statement, 0))], _Model(verdicts={statement: (verdict,)}))
    assert _status(result, statement) == ClaimStatus.NEEDS_HUMAN
    assert verdict.value in next(e.reason for e in result.ledger)


@pytest.mark.unit
async def test_rejecting_a_claim_unlike_its_source_still_rejects():
    statement = "A tool used to start a fight cannot change its target number."
    tree = _tree(["Tobin also wears a light cloak, but it won't help in the sky."])
    model = _Model(verdicts={statement: (ClaimVerdict.UNSUPPORTED,)})
    result = await review_claims(tree, [_outcome(_item(statement, 0))], model)
    assert _status(result, statement) == ClaimStatus.REJECTED


VETO = "Players may add traits, but the gamemaster may veto them."


@pytest.mark.unit
async def test_claims_from_one_paragraph_are_linked_to_each_other():
    first, second, other = "Players may add traits.", "The gamemaster may veto traits.", "Roll two dice."
    outcome = _outcome(_item(first, 0), _item(second, 0), _item(other, 1))
    result = await review_claims(_tree([VETO, "Roll two dice."]), [outcome], _Model())
    by_text = {claim.statement: claim for claim in result.claims}
    assert by_text[first].linked_claim_ids == [by_text[second].id]
    assert by_text[second].linked_claim_ids == [by_text[first].id]
    assert by_text[other].linked_claim_ids == []
    assert by_text[first].paragraph_ids == ["p0"]


@pytest.mark.unit
async def test_a_removed_claim_is_not_linked():
    first, second = "Players may add traits.", "The gamemaster may veto traits."
    model = _Model(verdicts={second: (ClaimVerdict.EXAMPLE,)})
    result = await review_claims(_tree([VETO]), [_outcome(_item(first, 0), _item(second, 0))], model)
    assert result.claims[0].linked_claim_ids == []


@pytest.mark.unit
async def test_verified_gap_is_reported_with_its_paragraph():
    gap = CoverageGap(label="P1", missing="The gamemaster may veto traits.", quote="the gamemaster may veto them")
    result = await review_claims(_tree([VETO]), [_outcome(_item("Players may add traits.", 0))], _Model(gaps=[gap]))
    assert [(g.paragraph_id, g.missing) for g in result.report.paragraph_gaps] == [("p0", gap.missing)]
    assert result.report.paragraphs_audited == 1


@pytest.mark.unit
async def test_gap_whose_quote_is_invented_is_dropped_and_counted():
    gap = CoverageGap(label="P1", missing="Dragons exist.", quote="dragons breathe fire")
    result = await review_claims(_tree([VETO]), [_outcome(_item("Players may add traits.", 0))], _Model(gaps=[gap]))
    assert result.report.paragraph_gaps == []
    assert result.report.coverage_gaps_unverified == 1


@pytest.mark.unit
async def test_gap_with_an_unknown_label_is_dropped_and_counted():
    gap = CoverageGap(label="P9", missing="Veto.", quote="the gamemaster may veto them")
    result = await review_claims(_tree([VETO]), [_outcome(_item("Players may add traits.", 0))], _Model(gaps=[gap]))
    assert result.report.coverage_gaps_unverified == 1


@pytest.mark.unit
async def test_failed_coverage_check_is_counted_and_changes_no_claim():
    statement = "Players may add traits."
    result = await review_claims(_tree([VETO]), [_outcome(_item(statement, 0))], _Model(fail_gaps=True))
    assert result.report.coverage_check_failures == 1
    assert _status(result, statement) == ClaimStatus.ACCEPTED


@pytest.mark.unit
async def test_coverage_check_reads_all_of_a_paragraphs_claims_together():
    first, second = "Players may add traits.", "The gamemaster may veto traits."
    model = _Model()
    await review_claims(_tree([VETO]), [_outcome(_item(first, 0), _item(second, 0))], model)
    assert first in model.coverage_prompts[0] and second in model.coverage_prompts[0]


@pytest.mark.unit
async def test_rejected_claim_does_not_count_as_coverage():
    kept, gone = "Players may add traits.", "Dragons breathe fire across mountains."
    model = _Model(verdicts={gone: (ClaimVerdict.UNSUPPORTED,)})
    await review_claims(_tree([VETO]), [_outcome(_item(kept, 0), _item(gone, 0))], model)
    assert gone not in model.coverage_prompts[0]


@pytest.mark.unit
async def test_worked_example_paragraph_is_not_audited():
    tree = _tree(["Example: Mira walks in."])
    model = _Model()
    await review_claims(tree, [_outcome(_item("Mira walks in.", 0))], model)
    assert model.coverage_prompts == []


@pytest.mark.unit
async def test_verified_gap_becomes_a_verified_claim_linked_to_its_paragraph():
    kept = "Players may add traits."
    gap = CoverageGap(label="P1", missing="The gamemaster may veto traits.", quote="the gamemaster may veto them")
    result = await review_claims(_tree([VETO]), [_outcome(_item(kept, 0))], _Model(gaps=[gap]))
    assert result.report.claims_from_gaps == 1
    assert _status(result, gap.missing) == ClaimStatus.ACCEPTED
    by_text = {claim.statement: claim for claim in result.claims}
    assert by_text[gap.missing].linked_claim_ids == [by_text[kept].id]
    assert by_text[gap.missing].source_node_ids == ["s0"]
    assert result.report.ledger_problems == []


@pytest.mark.unit
async def test_verifier_can_reject_a_gap_claim():
    bad = "Dragons guard all treasure forever."
    gap = CoverageGap(label="P1", missing=bad, quote="the gamemaster may veto them")
    model = _Model(gaps=[gap], verdicts={bad: (ClaimVerdict.UNSUPPORTED,)})
    result = await review_claims(_tree([VETO]), [_outcome(_item("Players may add traits.", 0))], model)
    assert _status(result, bad) == ClaimStatus.REJECTED
    assert bad not in [claim.statement for claim in result.claims]


@pytest.mark.unit
async def test_separate_coverage_model_is_used_when_given():
    gap = CoverageGap(label="P1", missing="The gamemaster may veto traits.", quote="the gamemaster may veto them")
    main, judge = _Model(), _Model(gaps=[gap])
    result = await review_claims(_tree([VETO]), [_outcome(_item("Players may add traits.", 0))], main, coverage_model=judge)
    assert main.coverage_prompts == [] and len(judge.coverage_prompts) == 1
    assert result.report.claims_from_gaps == 1


@pytest.mark.unit
async def test_saved_paragraph_check_is_reused_and_its_gap_still_becomes_a_claim(tmp_path):
    log = CoverageLog(tmp_path / "coverage.jsonl")
    gap = CoverageGap(label="P1", missing="The gamemaster may veto traits.", quote="the gamemaster may veto them")
    outcome = _outcome(_item("Players may add traits.", 0))
    await review_claims(_tree([VETO]), [outcome], _Model(gaps=[gap]), coverage_log=log)
    second = _Model()
    result = await review_claims(_tree([VETO]), [outcome], second, coverage_log=log)
    assert second.coverage_prompts == []
    assert result.report.coverage_reused == 1
    assert _status(result, gap.missing) == ClaimStatus.ACCEPTED


@pytest.mark.unit
async def test_paragraph_with_changed_claims_is_checked_again(tmp_path):
    log = CoverageLog(tmp_path / "coverage.jsonl")
    await review_claims(_tree([VETO]), [_outcome(_item("Players may add traits.", 0))], _Model(), coverage_log=log)
    second = _Model()
    await review_claims(_tree([VETO]), [_outcome(_item("The gamemaster may veto traits.", 0))], second, coverage_log=log)
    assert len(second.coverage_prompts) == 1


@pytest.mark.unit
async def test_coverage_log_ignores_a_torn_line(tmp_path):
    path = tmp_path / "coverage.jsonl"
    log = CoverageLog(path)
    await review_claims(_tree([VETO]), [_outcome(_item("Players may add traits.", 0))], _Model(), coverage_log=log)
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"key": "torn')
    assert len(log.read()) == 1


@pytest.mark.unit
async def test_merge_that_gathers_separate_rules_into_a_list_is_refused():
    first, second = "Hiding a lantern requires a test with Difficulty 2.", "Lifting a gate requires a test with Difficulty 2."
    bundled = "Certain actions require a skill test at Difficulty 2, including hiding a lantern, lifting a gate, starting a fire and putting out a fire."
    def stacks(_):
        return [ClaimStack(labels=["C1", "C2"], relation=StackRelation.SAME, canonical_statement=bundled)]
    source = "Hiding a lantern, lifting a gate, starting a fire and putting out a fire require a test with Difficulty 2."
    result = await review_claims(_tree([source, source]), [_outcome(_item(first, 0), _item(second, 1))], _Model(stacks=stacks))
    assert _status(result, first) == ClaimStatus.ACCEPTED and _status(result, second) == ClaimStatus.ACCEPTED
    assert result.report.merges_refused == 1
    assert bundled not in [claim.statement for claim in result.claims]


@pytest.mark.unit
async def test_stopping_the_run_still_saves_paragraph_checks_in_progress(tmp_path):
    log = CoverageLog(tmp_path / "coverage.jsonl")
    release = asyncio.Event()

    class Stopping(_Model):
        async def find_gaps(self, prompt):
            if "Second paragraph" in prompt:
                release.set()
                raise RunStopped("limit")
            await release.wait()
            await asyncio.sleep(0)
            return CoverageAudit(gaps=[])

    tree = _tree(["First paragraph holds rules.", "Second paragraph holds rules."])
    outcome = _outcome(_item("First paragraph holds rules.", 0), _item("Second paragraph holds rules.", 1))
    with pytest.raises(RunStopped):
        await review_claims(tree, [outcome], Stopping(), coverage_log=log, coverage_batch_size=1)
    assert len(log.read()) == 1


SIDEBAR_STYLE = "Book|white"


@pytest.mark.unit
def test_example_resumes_after_a_boxed_sidebar_on_the_next_page():
    tree = _styled_tree([
        (PARA, BODY, BODY_STYLE),
        (PARA, "Example: Mira walks in.", EXAMPLE_STYLE),
        (PARA, "Example: Tobin moves.", EXAMPLE_STYLE),
        (BookNodeKind.HEADING, "Overview", None),
        (PARA, "A sidebar with its own steps.", SIDEBAR_STYLE),
        (PARA, "Tobin also wears a cloak.", EXAMPLE_STYLE),
    ])
    resumed = next(n for n in tree.nodes if n.id == "p5")
    resumed.page_start = resumed.page_end = 3  # The page after the labeled example.
    assert "p5" in example_continuations(tree)


@pytest.mark.unit
def test_body_text_ends_an_example_even_after_a_sidebar():
    tree = _styled_tree([
        (PARA, BODY, BODY_STYLE),
        (PARA, "Example: Mira walks in.", EXAMPLE_STYLE),
        (PARA, "Example: Tobin moves.", EXAMPLE_STYLE),
        (PARA, "A sidebar with its own steps.", SIDEBAR_STYLE),
        (PARA, BODY, BODY_STYLE),
        (PARA, "A quote in the example style.", EXAMPLE_STYLE),
    ])
    assert "p5" not in example_continuations(tree)


def _names_tree() -> BookTree:
    rows = [(PARA, BODY, BODY_STYLE)]
    rows += [(PARA, f"Example: Mira rolls and Momentum is spent {i}.", EXAMPLE_STYLE) for i in range(4)]
    rows += [(PARA, "Players spend Momentum and the momentum pool grows.", BODY_STYLE)]
    return _styled_tree(rows)


@pytest.mark.unit
def test_sample_names_come_from_examples_and_exclude_ordinary_words():
    tree = _names_tree()
    names = sample_character_names(tree, example_continuations(tree))
    assert "Mira" in names
    assert "Momentum" not in names  # Also written in lowercase.


@pytest.mark.unit
async def test_kept_claim_naming_a_sample_character_goes_to_a_person():
    tree = _names_tree()
    statement = "Mira holds several useful assets."
    outcome = _outcome(_item(statement, 0))
    result = await review_claims(tree, [outcome], _Model(), check_coverage=False)
    assert _status(result, statement) == ClaimStatus.NEEDS_HUMAN
    assert "Mira" in next(e.reason for e in result.ledger)


@pytest.mark.unit
async def test_claim_that_describes_the_book_is_rejected():
    statement = "This section provides guidance on common actions."
    result = await review_claims(_tree([statement]), [_outcome(_item(statement, 0))], _Model())
    assert _status(result, statement) == ClaimStatus.REJECTED


@pytest.mark.unit
async def test_gap_that_describes_the_book_is_not_made_into_a_claim():
    gap = CoverageGap(label="P1", missing="This section provides guidance.", quote="the gamemaster may veto them")
    result = await review_claims(_tree([VETO]), [_outcome(_item("Players may add traits.", 0))], _Model(gaps=[gap]))
    assert result.report.claims_from_gaps == 0


@pytest.mark.unit
async def test_rules_and_other_kinds_get_their_domain():
    outcome = _outcome(_item("Roll two dice.", 0), _item("The Guild is old.", 1, AtomKind.FACT))
    result = await review_claims(_tree(["Roll two dice.", "The Guild is old."]), [outcome], _Model())
    assert {c.statement: c.domain for c in result.claims} == {"Roll two dice.": "rules", "The Guild is old.": "lore"}
