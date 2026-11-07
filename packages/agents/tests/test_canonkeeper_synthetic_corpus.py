"""Tests for the hermetic contradiction-measurement corpus (G-9).

The corpus is the evidence base for the contradiction checks now that the
seeded mechanical universes are out of scope (product boundary, 2026-11-07).
These tests pin the *deterministic* half — which needs no model at all — so a
change to the rules that starts flagging legitimate transitions fails here.
"""

from __future__ import annotations

from monitor_agents.canonkeeper.synthetic_corpus import (
    SYNTHETIC_BAD_TRANSITIONS,
    SYNTHETIC_CANON,
    SYNTHETIC_CONSISTENT,
    SYNTHETIC_CONTRADICTING,
    SYNTHETIC_GOOD_TRANSITIONS,
    replay_transitions,
    synthetic_context,
)


def test_the_deterministic_rules_raise_nothing_on_legitimate_transitions():
    """The false-positive rate of the deterministic rules, measured."""
    violations = replay_transitions(SYNTHETIC_GOOD_TRANSITIONS)

    assert violations == [], f"unexpected violations: {violations}"


def test_the_deterministic_rules_catch_every_known_impossible_transition():
    violations = replay_transitions(SYNTHETIC_BAD_TRANSITIONS)

    assert len(violations) == len(SYNTHETIC_BAD_TRANSITIONS)
    # Each bad case is reached by the rule it was written for — including
    # mutual exclusion, which is masked if a terminal tag is also present.
    assert {v["rule"] for v in violations} == {
        "terminal_tag_agency",
        "terminal_tag_removal",
        "mutual_exclusion",
    }


def test_the_corpus_is_well_formed():
    assert len(SYNTHETIC_CANON) >= 10
    assert len(SYNTHETIC_CONSISTENT) >= 10
    assert len(SYNTHETIC_CONTRADICTING) >= 5

    # A probe cannot be both consistent and contradicting.
    consistent_lower = {s.lower() for s in SYNTHETIC_CONSISTENT}
    contradicting_lower = {s.lower() for s in SYNTHETIC_CONTRADICTING}
    assert not consistent_lower & contradicting_lower


def test_every_contradicting_probe_is_anchored_in_the_canon():
    """A probe that touches no canon entity is noise, not a contradiction."""
    canon_anchors = {
        word.strip(".,").lower()
        for statement in SYNTHETIC_CANON
        for word in statement.split()
        if word[:1].isupper() and len(word.strip(".,")) >= 3
    }
    assert canon_anchors, "the canon has no proper-noun anchors"

    for statement in SYNTHETIC_CONTRADICTING:
        assert any(anchor in statement.lower() for anchor in canon_anchors), (
            f"probe is not anchored in the canon: {statement}"
        )


def test_the_context_renders_the_canon_as_fact_lines():
    context = synthetic_context()

    assert context.count("\n") == len(SYNTHETIC_CANON) - 1
    assert all(line.startswith("Fact: ") for line in context.splitlines())
