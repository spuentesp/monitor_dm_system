"""Tests for the DiceEngineRegistry (sub-plan 4)."""
from __future__ import annotations

from monitor_agents.dice import (
    DiceEngineRegistry,
    GenericDiceEngine,
    VtMV20Engine,
    default_dice_registry,
)


def test_default_registry_has_generic_and_vtm_v20():
    """The default registry must have at least the generic engine
    (fallback) and the VtM V20 engine (the one we ship out of the
    box) registered on import."""
    assert default_dice_registry.has("generic")
    assert default_dice_registry.has("vtm_v20")


def test_get_returns_registered_engine():
    engine = default_dice_registry.get("vtm_v20")
    assert isinstance(engine, VtMV20Engine)


def test_get_falls_back_to_generic_for_unknown_engine():
    engine = default_dice_registry.get("lancer")  # not registered
    # Should fall back to generic.
    assert engine.name == "generic"


def test_register_overwrites():
    reg = DiceEngineRegistry()
    e1 = GenericDiceEngine()
    e2 = GenericDiceEngine()
    reg.register(e1)
    reg.register(e2)
    assert reg.get("generic") is e2


def test_default_registry_lookup_methods():
    """Lookups by name and by has() work as expected."""
    engine = default_dice_registry.get("generic")
    assert engine.name == "generic"
    assert default_dice_registry.has("vtm_v20")
    assert not default_dice_registry.has("dnd5e_never_registered")
