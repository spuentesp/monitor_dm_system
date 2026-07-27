"""Tests for system-driven derived-resource calculation.

Resources like Health derive from the game system's ``calculation`` formulas
(e.g. ``10 + Grit_modifier``) via the system's ``modifier_formula`` — never a
hardcoded curve. This is what lets the demo PC's HP be sourced from data.
"""

from monitor_agents.game_system import GameSystemRuntime

MISTLANDS_LIKE = {
    "name": "Mistlands-like",
    "attributes": [
        {"name": "Grit", "abbreviation": "GRIT", "modifier_formula": "(VALUE - 10) / 2"},
        {"name": "Resolve", "abbreviation": "RESOLVE", "modifier_formula": "(VALUE - 10) / 2"},
    ],
    "resources": [
        {"name": "Health", "abbreviation": "HP", "calculation": "10 + Grit_modifier"},
        {"name": "Nerve", "abbreviation": "NV", "calculation": "6 + Resolve_modifier"},
    ],
}


def test_derive_resources_resolves_modifier_tokens():
    gsr = GameSystemRuntime(MISTLANDS_LIKE)
    derived = gsr.derive_resources({"GRIT": 12, "RESOLVE": 11})
    # Grit 12 -> mod +1 -> Health 11; Resolve 11 -> mod 0 -> Nerve 6.
    assert derived == {"Health": 11, "Nerve": 6}


def test_derive_resources_scales_with_attribute():
    gsr = GameSystemRuntime(MISTLANDS_LIKE)
    assert gsr.derive_resources({"GRIT": 14, "RESOLVE": 10}) == {"Health": 12, "Nerve": 6}
    assert gsr.derive_resources({"GRIT": 8, "RESOLVE": 8}) == {"Health": 9, "Nerve": 5}


def test_derive_resources_no_hardcoded_fallback_when_no_formula():
    gsr = GameSystemRuntime({"name": "Empty", "attributes": [], "resources": [{"name": "Mana", "abbreviation": "MP"}]})
    # No calculation formula and no rule -> not invented from a literal.
    assert gsr.derive_resources({"INT": 10}) == {}
