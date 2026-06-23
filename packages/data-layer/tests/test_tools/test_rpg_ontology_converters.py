"""
Tests for the RPG Ontology converter — builtin_systems.json → GameSystemSpec.

LAYER: data-layer
SCOPE: unit tests (no DB required)

Tests cover:
- All 7 systems load from builtin_systems.json without error
- Converter produces a valid GameSystemSpec for each system
- SystemRegistry is populated with all 7 systems at import time
- `make_entity_model()` generates correct field counts per system
- VtM non-ASCII condition names are handled (Rötschreck → roetschreck)
- Narrative Pure/Weighted long dice_notation strings are truncated correctly
- Factory models are isolated (no cross-system contamination)
- Derived modifier fields are correctly marked user_settable=False
- Field counts match expectations per system complexity
"""

import pytest

from monitor_data.schemas.rpg_ontology import SystemRegistry, make_entity_model
from monitor_data.schemas.rpg_ontology.converters import (
    load_all_builtin_specs,
    seed_system_registry,
    _slugify,
    _to_ascii,
    get_spec_for_system,
)
from monitor_data.schemas.rpg_ontology.meta import GameSystemSpec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_registry():
    """Clear and reseed the SystemRegistry before each test."""
    # Save original specs
    original_specs = load_all_builtin_specs()
    # Unregister everything
    registry = SystemRegistry()
    for sid in list(registry.list_systems()):
        registry.unregister(sid)
    # Re-register fresh
    for spec in original_specs:
        registry.register(spec)
    yield
    # Leave it clean


@pytest.fixture
def registry():
    return SystemRegistry()


@pytest.fixture
def all_specs():
    return load_all_builtin_specs()


# ---------------------------------------------------------------------------
# Converter correctness
# ---------------------------------------------------------------------------


class TestBuiltinToGameSystemSpec:
    @pytest.mark.parametrize(
        "system_name",
        [
            "D&D 5e",
            "Fate Core",
            "Powered by the Apocalypse",
            "Narrative Pure",
            "Narrative Weighted",
            "Death in Space",
            "Vampire: The Masquerade 5th Edition",
            "Mistlands Core",
        ],
    )
    def test_all_systems_convert_without_error(self, system_name):
        """Every system in builtin_systems.json produces a valid GameSystemSpec."""
        spec = get_spec_for_system(system_name)
        assert spec is not None, f"Converter returned None for {system_name!r}"
        assert isinstance(spec, GameSystemSpec)
        # Validate the spec round-trips cleanly
        reloaded = GameSystemSpec.model_validate(spec.model_dump())
        assert reloaded.system_id == spec.system_id
        assert reloaded.system_name == spec.system_name

    def test_slugify_produces_valid_system_ids(self, all_specs):
        """slugify produces snake_case ids that GameSystemSpec accepts."""
        for spec in all_specs:
            # Must pass the validator (lower-snake-case, starts with letter)
            reloaded = GameSystemSpec.model_validate(spec.model_dump())
            assert reloaded.system_id == spec.system_id

    def test_dnd5e_has_correct_field_counts(self):
        spec = get_spec_for_system("D&D 5e")
        assert spec is not None
        char = spec.get_entity_type("character")
        assert char is not None
        # 6 attributes + 1 name + 1 is_player_character + 6 modifiers + 18 skills
        # + 2 resources (HP, HD) + armor + initiative + proficiency
        # = 1 + 1 + 6 + 6 + 18 + 2 + 1 + 1 + 1 = 37+ fields minimum
        assert len(char.fields) >= 30, f"D&D 5e character has only {len(char.fields)} fields"

    def test_vtm_has_hunger_dice_field(self):
        spec = get_spec_for_system("Vampire")
        assert spec is not None
        char = spec.get_entity_type("character")
        hunger_field = next((f for f in char.fields if "hunger" in f.name), None)
        assert hunger_field is not None, "VtM should have a Hunger-related field"

    def test_dnd5e_modifier_fields_are_derived(self):
        spec = get_spec_for_system("D&D 5e")
        char = spec.get_entity_type("character")
        modifier_fields = [f for f in char.fields if f.name.endswith("_mod")]
        assert len(modifier_fields) >= 6, "Should have 6 attribute modifier fields"
        for f in modifier_fields:
            assert f.derived_formula is not None, f"{f.name} should be derived"
            assert not f.user_settable, f"{f.name} should not be user_settable"

    def test_narrative_pure_handles_empty_formula(self):
        spec = get_spec_for_system("Narrative Pure")
        assert spec is not None
        # dice_notation was too long, should be truncated to 50 chars
        assert len(spec.core_mechanic.dice_notation or "") <= 50

    def test_narrative_weighted_handles_long_formula(self):
        spec = get_spec_for_system("Narrative Weighted")
        assert spec is not None
        assert len(spec.core_mechanic.dice_notation or "") <= 50

    def test_vtm_non_ascii_condition_sluggified(self):
        spec = get_spec_for_system("Vampire")
        assert spec is not None
        char = spec.get_entity_type("character")
        # "Rötschreck" → NFKD → "Rotschreck" (diacritics stripped, not replaced)
        # _slugify lowercases and replaces spaces, so "Rotschreck" → "rotschreck"
        assert any("rotschreck" in f.name for f in char.fields), (
            "Rötschreck should be converted to snake_case ASCII 'rotschreck'"
        )

    def test_all_systems_have_character_and_item_entity_types(self, all_specs):
        for spec in all_specs:
            assert "character" in spec.entity_types, (
                f"{spec.system_name} missing 'character' entity type"
            )
            assert "item" in spec.entity_types, f"{spec.system_name} missing 'item' entity type"

    def test_system_ids_are_unique(self, all_specs):
        ids = [s.system_id for s in all_specs]
        assert len(ids) == len(set(ids)), "Duplicate system_ids found"

    def test_character_entity_has_name_field(self, all_specs):
        for spec in all_specs:
            char = spec.get_entity_type("character")
            assert any(f.name == "character_name" for f in char.fields), (
                f"{spec.system_name} character missing 'character_name' field"
            )


# ---------------------------------------------------------------------------
# SystemRegistry population
# ---------------------------------------------------------------------------


class TestSystemRegistryPopulation:
    def test_all_eight_systems_registered(self, registry):
        """SystemRegistry contains all 8 systems after import."""
        assert len(registry.list_systems()) == 8

    def test_get_by_system_id(self, registry):
        """Each system is retrievable by its canonical system_id."""
        # D&D 5e
        spec = registry.get("dandd_5e")
        assert spec is not None
        assert spec.system_name == "D&D 5e"
        # VtM 5e
        spec = registry.get("vampire_the_masquerade_5th_edition")
        assert spec is not None
        assert "Vampire" in spec.system_name
        # Death in Space
        spec = registry.get("death_in_space")
        assert spec is not None
        assert "Death in Space" in spec.system_name

    def test_registry_list_systems_returns_all_eight(self, registry):
        """list_systems() returns exactly the 8 registered system IDs."""
        systems = registry.list_systems()
        assert len(systems) == 8
        expected = {
            "dandd_5e",
            "fate_core",
            "powered_by_the_apocalypse",
            "narrative_pure",
            "narrative_weighted",
            "death_in_space",
            "vampire_the_masquerade_5th_edition",
            "mistlands_core",
        }
        assert set(systems) == expected

    def test_unregister_then_reregister(self, registry):
        """A system can be unregistered and re-registered without error."""
        spec = registry.get("death_in_space")
        assert spec is not None
        registry.unregister("death_in_space")
        assert registry.get("death_in_space") is None
        registry.register(spec)
        assert registry.get("death_in_space") is not None

    def test_seed_is_idempotent(self, registry):
        """seed_system_registry() can be called multiple times without error."""
        before = set(registry.list_systems())
        seed_system_registry()
        after = set(registry.list_systems())
        assert before == after


# ---------------------------------------------------------------------------
# Factory model generation
# ---------------------------------------------------------------------------


class TestFactoryModelGeneration:
    def test_make_entity_model_produces_model_per_system(self, registry):
        """make_entity_model generates a distinct model class for each system."""
        dnd = make_entity_model(registry.get("dandd_5e"), "character")
        vtm = make_entity_model(registry.get("vampire_the_masquerade_5th_edition"), "character")
        dis = make_entity_model(registry.get("death_in_space"), "character")

        assert dnd is not vtm
        assert dnd is not dis
        assert vtm is not dis

    def test_dnd5e_model_has_expected_fields(self, registry):
        """D&D 5e model exposes all expected character sheet fields."""
        model_cls = make_entity_model(registry.get("dandd_5e"), "character")
        field_names = set(model_cls.model_fields)

        # Core attribute fields
        for attr in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]:
            assert attr in field_names, f"D&D 5e model missing '{attr}' field"

        # Name field
        assert "character_name" in field_names

    def test_vtm_model_has_hunger_field(self, registry):
        """VtM 5e model exposes the Hunger dice pool field."""
        model_cls = make_entity_model(
            registry.get("vampire_the_masquerade_5th_edition"), "character"
        )
        field_names = set(model_cls.model_fields)
        assert any("hunger" in n for n in field_names), (
            f"VtM model missing hunger field; fields: {field_names}"
        )

    def test_model_caching_no_regeneration(self, registry):
        """Calling make_entity_model twice with same args returns the same class."""
        dnd1 = make_entity_model(registry.get("dandd_5e"), "character")
        dnd2 = make_entity_model(registry.get("dandd_5e"), "character")
        assert dnd1 is dnd2, "Model cache not working — same spec produced different classes"

    def test_field_count_reasonableness(self, registry):
        """Each system model has a reasonable number of fields for a character sheet."""
        # D&D 5e is the most complex (6 attrs + modifiers + 18 skills + resources)
        dnd_model = make_entity_model(registry.get("dandd_5e"), "character")
        assert len(dnd_model.model_fields) >= 30

        # Narrative Pure is the simplest (name + attributes only)
        narrative = make_entity_model(registry.get("narrative_pure"), "character")
        assert 3 <= len(narrative.model_fields) <= 20

    @pytest.mark.parametrize(
        "system_id",
        [
            "dandd_5e",
            "fate_core",
            "powered_by_the_apocalypse",
            "narrative_pure",
            "narrative_weighted",
            "death_in_space",
            "vampire_the_masquerade_5th_edition",
        ],
    )
    def test_all_systems_produce_valid_character_model(self, registry, system_id):
        """Every registered system produces a valid, instantiable character model."""
        spec = registry.get(system_id)
        assert spec is not None, f"Missing spec for {system_id}"
        model_cls = make_entity_model(spec, "character")
        assert model_cls is not None
        assert hasattr(model_cls, "model_validate")
        assert hasattr(model_cls, "model_fields")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_slugify(self):
        assert _slugify("D&D 5e") == "dandd_5e"
        assert (
            _slugify("Vampire: The Masquerade 5th Edition") == "vampire_the_masquerade_5th_edition"
        )
        assert _slugify("Powered by the Apocalypse") == "powered_by_the_apocalypse"
        assert _slugify("Death in Space") == "death_in_space"
        assert _slugify("Fate Core") == "fate_core"
        assert _slugify("7th Sea") == "sys_7th_sea"
        assert _slugify("A & B Game") == "a_and_b_game"

    def test_to_ascii(self):
        # NFKD + ignore strips combining marks (diacritics) → base chars remain
        assert _to_ascii("Rötschreck") == "Rotschreck"
        assert _to_ascii("Mörder") == "Morder"  # umlaut stripped
        assert _to_ascii("Strength") == "Strength"
        assert _to_ascii("Nervous") == "Nervous"
