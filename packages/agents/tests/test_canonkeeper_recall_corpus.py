"""Tests for the G08 recall corpus and its scoring.

The corpus is data, so what matters is that it stays *usable*: every class
is populated, every violating case really contradicts the canon, and the
scoring function reports the numbers the harness gates on.

Run:
    uv run pytest packages/agents/tests/test_canonkeeper_recall_corpus.py -q
"""

from __future__ import annotations

from monitor_agents.canonkeeper.recall_corpus import (
    CLASS_TARGETS,
    CONSISTENT_CLASSES,
    DIRECT_CLASSES,
    FALSE_POSITIVE_CEILING,
    IMPLICATION_CLASSES,
    RECALL_CANON,
    RECALL_CASES,
    TIMELINE_CLASSES,
    VIOLATION_CLASSES,
    RecallCase,
    entity_names,
    evaluate,
    focused_context,
    render_context,
)


class TestCorpusShape:
    def test_every_class_is_populated(self) -> None:
        counts = {c.case_class: 0 for c in RECALL_CASES}
        for case in RECALL_CASES:
            counts[case.case_class] += 1

        for name in (*VIOLATION_CLASSES, *CONSISTENT_CLASSES):
            assert counts[name] >= 6, f"{name} has only {counts[name]} cases"

    def test_every_violation_class_has_a_target(self) -> None:
        for name in VIOLATION_CLASSES:
            assert name in CLASS_TARGETS

    def test_consistent_classes_have_no_target(self) -> None:
        """A floor on recall makes no sense for known-good material."""
        for name in CONSISTENT_CLASSES:
            assert name not in CLASS_TARGETS

    def test_targets_match_the_gap_plan(self) -> None:
        # Direct and timeline: ≥90%. Reasoning chains: ≥80%.
        for name in (*DIRECT_CLASSES, *TIMELINE_CLASSES):
            assert CLASS_TARGETS[name] >= 0.90
        for name in IMPLICATION_CLASSES:
            assert CLASS_TARGETS[name] >= 0.80

    def test_the_world_has_axioms_facts_and_timestamps(self) -> None:
        assert any(f.kind == "axiom" for f in RECALL_CANON)
        assert any(f.kind != "axiom" for f in RECALL_CANON)
        assert any(f.time_ref for f in RECALL_CANON)

    def test_statements_are_unique(self) -> None:
        statements = [c.statement for c in RECALL_CASES]
        assert len(statements) == len(set(statements))

    def test_the_falses_positive_ceiling_is_strict(self) -> None:
        assert 0 < FALSE_POSITIVE_CEILING <= 0.10


class TestRendering:
    def test_axioms_come_first(self) -> None:
        lines = render_context().splitlines()
        axiom_lines = [ln for ln in lines if ln.startswith("Axiom:")]
        assert axiom_lines
        assert lines.index(axiom_lines[-1]) < lines.index(
            next(ln for ln in lines if ln.startswith("Fact"))
        )

    def test_a_timestamp_is_shown_with_its_fact(self) -> None:
        assert "Fact (day 3, 10:00):" in render_context()

    def test_focused_context_keeps_the_axioms(self) -> None:
        scoped = focused_context("Mira Vale opened the sealed door.")
        assert "Axiom:" in scoped

    def test_focused_context_narrows_the_canon(self) -> None:
        statement = "Mira Vale has crossed into the Burnside district a dozen times."
        scoped = focused_context(statement)
        # The Burnside fact and Mira Vale's facts are in; the Kittiwake's are
        # not — they cannot bear on this candidate.
        assert "Burnside district" in scoped
        assert "Kittiwake" not in scoped

    def test_entity_names_are_found_in_a_statement(self) -> None:
        assert "Mira Vale" in entity_names("Mira Vale opened the door.")
        assert entity_names("A stranger arrived.") == set()


class TestEvaluate:
    def _cases(self) -> tuple[RecallCase, ...]:
        return (
            RecallCase("a", "direct_negation", True),
            RecallCase("b", "direct_negation", True),
            RecallCase("c", "consistent_restatement", False),
        )

    def test_recall_counts_a_detection_from_either_check(self) -> None:
        report = evaluate(self._cases(), direct_flags={"a"}, implication_flags={"b"})

        entry = report.classes["direct_negation"]
        assert entry.total == 2
        assert entry.detected == 2
        assert entry.direct_recall == 0.5
        assert entry.implication_recall == 0.5
        assert entry.recall == 1.0

    def test_a_miss_is_not_detected(self) -> None:
        report = evaluate(self._cases(), direct_flags=set(), implication_flags=set())

        entry = report.classes["direct_negation"]
        assert entry.detected == 0
        assert entry.recall == 0.0
        assert not entry.meets_target

    def test_a_flag_on_known_good_material_is_a_false_positive(self) -> None:
        report = evaluate(self._cases(), direct_flags={"c"}, implication_flags=set())

        assert report.classes["consistent_restatement"].false_positives == 1
        assert report.false_positive_rate == 1.0

    def test_the_report_gates_on_the_targets(self) -> None:
        cases = tuple(
            RecallCase(f"v{i}", "direct_negation", True) for i in range(10)
        ) + (RecallCase("g", "consistent_restatement", False),)

        full = evaluate(cases, direct_flags={f"v{i}" for i in range(10)}, implication_flags=set())
        assert full.meets_targets is True
        assert full.false_positive_rate == 0.0

        partial = evaluate(cases, direct_flags={f"v{i}" for i in range(5)}, implication_flags=set())
        assert partial.meets_targets is False

    def test_the_report_serializes(self) -> None:
        report = evaluate(self._cases(), direct_flags={"a"}, implication_flags=set())
        payload = report.to_dict()

        assert payload["meets_targets"] is False
        assert "direct_negation" in payload["classes"]
        assert payload["classes"]["direct_negation"]["recall"] == 0.5
