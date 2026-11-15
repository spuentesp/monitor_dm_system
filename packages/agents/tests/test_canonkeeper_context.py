"""Tests for the CanonKeeper focused-context builder (G08 phase 2).

The builder decides which canon a candidate statement is checked against.
Its rules are explicit, so they are pinned here: direct hits, one hop out,
the timeline, and the fallback that keeps an unknown candidate checkable.

Run:
    uv run pytest packages/agents/tests/test_canonkeeper_context.py -q
"""

from __future__ import annotations

from monitor_agents.canonkeeper.context import (
    build_focused_context,
    mentioned_entity_names,
    render_context_lines,
    select_relevant_facts,
)


def _fact(statement: str, entity_ids: list[str] | None = None, time_ref: str | None = None):
    fact: dict[str, object] = {"statement": statement, "entity_ids": entity_ids or []}
    if time_ref:
        fact["time_ref"] = time_ref
    return fact


FACTS = [
    _fact("Mira Vale is a courier for the Grey Line.", ["e-mira", "e-greyline"]),
    _fact("Mira Vale has never crossed into the Burnside district.", ["e-mira", "e-burnside"]),
    _fact("Captain Rell commands the dredger Kittiwake.", ["e-rell", "e-kittiwake"]),
    _fact("The harbour council meets at dusk in the Customs House.", ["e-council", "e-customs"]),
    _fact("The council closed the Brass Market on the fourth day.", ["e-council"], "day 4, 19:00"),
]


class TestMentionedEntityNames:
    def test_a_named_entity_is_found(self) -> None:
        assert mentioned_entity_names("Mira Vale left.", ["Mira Vale", "Old Tam"]) == {"Mira Vale"}

    def test_matching_is_case_insensitive(self) -> None:
        assert mentioned_entity_names("mira vale left.", ["Mira Vale"]) == {"Mira Vale"}

    def test_an_unmentioned_entity_is_not_found(self) -> None:
        assert mentioned_entity_names("A stranger left.", ["Mira Vale"]) == set()

    def test_an_empty_statement_matches_nothing(self) -> None:
        assert mentioned_entity_names("", ["Mira Vale"]) == set()


class TestSelectRelevantFacts:
    def test_direct_hits_are_selected(self) -> None:
        selected = select_relevant_facts(
            "Mira Vale no longer works for the Grey Line.", FACTS, ["Mira Vale", "Grey Line"]
        )
        statements = [f["statement"] for f in selected]
        assert "Mira Vale is a courier for the Grey Line." in statements

    def test_unrelated_facts_are_left_out(self) -> None:
        selected = select_relevant_facts(
            "Mira Vale crossed into the Burnside district.", FACTS, ["Mira Vale"]
        )
        statements = [f["statement"] for f in selected]
        assert "Captain Rell commands the dredger Kittiwake." not in statements

    def test_one_hop_out_is_included(self) -> None:
        selected = select_relevant_facts(
            "Mira Vale left.", FACTS, ["Grey Line"]
        )
        statements = [f["statement"] for f in selected]
        # The Burnside fact is attached to Mira Vale, who the Grey Line fact
        # also touches — one hop out.
        assert "Mira Vale has never crossed into the Burnside district." in statements

    def test_a_dated_fact_is_kept(self) -> None:
        selected = select_relevant_facts(
            "The harbour council met at dawn.", FACTS, ["harbour council"]
        )
        statements = [f["statement"] for f in selected]
        assert "The council closed the Brass Market on the fourth day." in statements

    def test_an_unknown_candidate_keeps_the_whole_canon(self) -> None:
        selected = select_relevant_facts("A stranger arrived.", FACTS, ["Mira Vale"])
        assert len(selected) == len(FACTS)

    def test_no_entity_names_keeps_the_whole_canon(self) -> None:
        selected = select_relevant_facts("A stranger arrived.", FACTS, [])
        assert len(selected) == len(FACTS)


class TestRenderContextLines:
    def test_axioms_come_first(self) -> None:
        lines = render_context_lines(FACTS, [{"statement": "Silver marks are the only currency."}])
        assert lines[0].startswith("Axiom:")

    def test_a_timestamp_is_shown(self) -> None:
        lines = render_context_lines(FACTS)
        assert any(line.startswith("Fact (day 4, 19:00):") for line in lines)

    def test_a_fact_without_a_statement_is_skipped(self) -> None:
        lines = render_context_lines([{"statement": ""}, _fact("Real fact.")])
        assert lines == ["Fact: Real fact."]


class TestBuildFocusedContext:
    def test_the_context_carries_the_bearing_canon(self) -> None:
        context = build_focused_context(
            "Mira Vale no longer works for the Grey Line.",
            FACTS,
            [{"statement": "The Grey Line is a courier guild."}],
            ["Mira Vale", "Grey Line"],
        )
        assert "Axiom: The Grey Line is a courier guild." in context
        assert "Mira Vale is a courier for the Grey Line." in context
        assert "Captain Rell" not in context

    def test_an_empty_canon_gives_an_empty_context(self) -> None:
        assert build_focused_context("Anything.", [], [], []) == ""
