"""Tests for the demo PC bootstrap (R4): resources are derived from the bound
game system, never a hardcoded literal resource dict."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from monitor_ui.routers.forge import _DEMO_PC_ATTRIBUTES, _demo_pc_properties

_MISTLANDS_DOC = {
    "name": "Mistlands Core",
    "attributes": [
        {"name": "Grit", "abbreviation": "GRIT", "modifier_formula": "(VALUE - 10) / 2"},
        {"name": "Resolve", "abbreviation": "RESOLVE", "modifier_formula": "(VALUE - 10) / 2"},
    ],
    "resources": [
        {"name": "Health", "abbreviation": "HP", "calculation": "10 + Grit_modifier"},
        {"name": "Nerve", "abbreviation": "NV", "calculation": "6 + Resolve_modifier"},
    ],
}


def test_demo_pc_attributes_carry_no_literal_resources():
    # The bootstrap constant holds chosen attribute *values* only — no resources.
    assert "resources" not in _DEMO_PC_ATTRIBUTES
    assert _DEMO_PC_ATTRIBUTES["Grit"] == 12


def test_demo_pc_properties_without_system_has_no_resources():
    props = _demo_pc_properties(None)
    assert props == {"attributes": dict(_DEMO_PC_ATTRIBUTES)}
    assert "resources" not in props


def test_demo_pc_properties_derives_resources_from_system():
    sys_resp = MagicMock()
    sys_resp.model_dump.return_value = _MISTLANDS_DOC
    with patch(
        "monitor_data.tools.mongodb_tools.mongodb_get_game_system",
        return_value=sys_resp,
    ):
        props = _demo_pc_properties(uuid4())

    # Health = 10 + (Grit 12 -> +1) = 11, sourced from the system, not a literal.
    assert props["resources"]["Health"] == {"current": 11, "max": 11}
    assert props["resources"]["Nerve"] == {"current": 6, "max": 6}
    assert props["attributes"]["Grit"] == 12
