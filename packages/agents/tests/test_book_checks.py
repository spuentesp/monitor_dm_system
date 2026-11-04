"""Tests for the code checks on claims: wording doubts that never approve a claim (I-17)."""

import pytest
from monitor_agents.book_decomposition.checks import (
    closely_matches,
    combines_rules,
    check_names,
    check_numbers,
    is_overstuffed,
    quote_is_in,
    unresolved_flags,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("statement", "source", "missing"),
    [
        ("Roll 2 dice.", "Roll two dice.", []),
        ("Roll two dice.", "Roll 2 dice.", []),
        ("Roll 5 dice.", "Roll 2 dice.", ["5"]),
        ("One possible trait is Dark.", "A trait could be Dark.", []),
        ("Roll 1 die.", "Roll a die.", ["1"]),
        ("At most 12 points.", "Hold 120 points.", ["12"]),
    ],
)
def test_check_numbers(statement, source, missing):
    assert [item.detail for item in check_numbers(statement, source)] == missing


@pytest.mark.unit
def test_name_outside_source_and_heading_is_flagged():
    assert [f.detail for f in check_names("Spend it on Momentum now.", "Spend it now.")] == ["Momentum"]
    assert not check_names("Spend it on Momentum now.", "Spend it now.", "Momentum Rules")
    assert not check_names("Spend it on Momentum now.", "Spend momentum now.")


@pytest.mark.unit
def test_unresolved_flags_never_include_conditions():
    assert unresolved_flags("Knights ride.", "Knights ride, unless wounded.", "") == []


@pytest.mark.unit
def test_number_must_be_in_the_source_even_if_the_section_has_it():
    flags = unresolved_flags("Roll 5 dice.", "Roll some dice.", "Roll some dice. Hold 5 points.")
    assert [item.detail for item in flags] == ["5"]


@pytest.mark.unit
def test_restoring_a_short_condition_is_not_overstuffed():
    assert not is_overstuffed(
        "Players may add as many props to a scene as they like.",
        "Players may add as many props to a scene as they like, but the referee can refuse "
        "any that seem out of place.",
    )


@pytest.mark.unit
def test_packing_in_separate_rules_is_overstuffed():
    assert is_overstuffed("A trait can be tested.", "A trait can be tested " + "and more " * 15)


@pytest.mark.unit
def test_closely_matches_ignores_common_words_and_needs_shared_meaning():
    assert closely_matches("A round ends once all have acted.", "Once all have acted, the round ends.")
    assert not closely_matches("Assets adjust conflict Difficulty.", "Tobin has a personal shield.")
    assert not closely_matches("A the of.", "Anything at all.")


@pytest.mark.unit
def test_quote_is_found_regardless_of_case_and_spacing():
    assert quote_is_in("May  ADD traits", "Players may add\ntraits here.")
    assert not quote_is_in("may remove traits", "Players may add traits here.")
    assert not quote_is_in("  ", "Players may add traits here.")


@pytest.mark.unit
def test_merging_wordings_is_not_combining_but_listing_rules_is():
    member = "The Momentum pool holds at most 6 points."
    assert not combines_rules(member, "The Momentum pool holds at most 6 points in total.")
    assert combines_rules(member, member + " Targeting, moving, creating and removing all need a test with Difficulty 2 too.")
