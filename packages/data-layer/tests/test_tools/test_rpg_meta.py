"""
Tests for the general RPG meta-schema engine.

Tests cover:
  - meta.py — FieldSpec, ValidatorSpec, EntityTypeSpec, GameSystemSpec, SystemRegistry
  - factory.py — make_entity_model, validate_entity_data, clear_model_cache
  - specs/death_in_space.py — DEATH_IN_SPACE spec integrity and DIS game rules
"""

import pytest
from pydantic import ValidationError

from monitor_data.schemas.rpg_ontology.factory import (
    clear_model_cache,
    make_all_models,
    make_entity_model,
    validate_entity_data,
)
from monitor_data.schemas.rpg_ontology.meta import (
    CoreMechanicSpec,
    EntityTypeSpec,
    FieldSpec,
    FieldType,
    GameSystemSpec,
    OntologyMechanicType,
    RelationCardinality,
    RelationSpec,
    StorageBackend,
    SystemRegistry,
    ValidatorSpec,
    ValidatorType,
)
from monitor_data.schemas.rpg_ontology.specs.death_in_space import DEATH_IN_SPACE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_spec(system_id: str = "test_sys") -> GameSystemSpec:
    """Build a minimal GameSystemSpec for testing."""
    return GameSystemSpec(
        system_id=system_id,
        system_name="Test System",
        core_mechanic=CoreMechanicSpec(
            mechanic_type=OntologyMechanicType.D20_OVER,
            success_condition="roll ≥ DC",
        ),
        entity_types={
            "actor": EntityTypeSpec(
                type_key="actor",
                display_name="Actor",
                fields=[
                    FieldSpec(
                        name="actor_name",
                        display_name="Name",
                        field_type=FieldType.STR,
                    ),
                    FieldSpec(
                        name="level",
                        display_name="Level",
                        field_type=FieldType.INT,
                        min_value=1,
                        max_value=20,
                        default_value=1,
                    ),
                ],
            )
        },
    )


# ===========================================================================
# FieldSpec
# ===========================================================================


class TestFieldSpec:
    def test_snake_case_name_required(self):
        with pytest.raises(ValidationError, match="snake_case"):
            FieldSpec(name="Bad Name", display_name="X", field_type=FieldType.STR)

    def test_enum_type_requires_enum_values(self):
        with pytest.raises(ValidationError, match="no enum_values"):
            FieldSpec(name="x", display_name="X", field_type=FieldType.ENUM)

    def test_enum_with_values_ok(self):
        f = FieldSpec(
            name="rank",
            display_name="Rank",
            field_type=FieldType.ENUM,
            enum_values=["private", "sergeant", "captain"],
        )
        assert f.enum_values == ["private", "sergeant", "captain"]

    def test_derived_formula_auto_disables_user_settable(self):
        f = FieldSpec(
            name="max_hp",
            display_name="Max HP",
            field_type=FieldType.INT,
            derived_formula="level * 4",
            user_settable=True,  # should be overridden
        )
        assert f.user_settable is False

    def test_required_false_makes_optional(self):
        f = FieldSpec(
            name="nickname",
            display_name="Nickname",
            field_type=FieldType.STR,
            required=False,
        )
        assert f.required is False


# ===========================================================================
# GameSystemSpec
# ===========================================================================


class TestGameSystemSpec:
    def test_system_id_slug_enforced(self):
        with pytest.raises(ValidationError, match="lower-snake-case"):
            _minimal_spec(system_id="My System")

    def test_valid_spec_round_trips(self):
        spec = _minimal_spec()
        data = spec.model_dump()
        spec2 = GameSystemSpec.model_validate(data)
        assert spec2.system_id == spec.system_id

    def test_relation_unknown_from_type_rejected(self):
        with pytest.raises(ValidationError, match="unknown from_type"):
            spec = _minimal_spec()
            # Add a relation referencing a non-existent type
            spec2 = spec.model_copy(deep=True)
            spec2.relations.append(
                RelationSpec(
                    relation_id="bad_rel",
                    display_name="Bad",
                    from_type="nonexistent",
                    to_type="actor",
                    cardinality=RelationCardinality.ONE_TO_MANY,
                )
            )
            GameSystemSpec.model_validate(spec2.model_dump())

    def test_list_storage_backends(self):
        spec = _minimal_spec()
        # Minimal spec has no storage backends set
        assert spec.list_storage_backends() == []

    def test_get_entity_type(self):
        spec = _minimal_spec()
        et = spec.get_entity_type("actor")
        assert et is not None
        assert et.type_key == "actor"

    def test_get_fields_for(self):
        spec = _minimal_spec()
        fields = spec.get_fields_for("actor")
        names = [f.name for f in fields]
        assert "actor_name" in names
        assert "level" in names


# ===========================================================================
# SystemRegistry
# ===========================================================================


class TestSystemRegistry:
    def setup_method(self):
        # Use a fresh spec per test so we don't pollute the singleton
        self.registry = SystemRegistry()
        self.spec = _minimal_spec("reg_test_sys")

    def teardown_method(self):
        self.registry.unregister("reg_test_sys")
        clear_model_cache("reg_test_sys")

    def test_register_and_get(self):
        self.registry.register(self.spec)
        got = self.registry.get("reg_test_sys")
        assert got is not None
        assert got.system_id == "reg_test_sys"

    def test_get_missing_returns_none(self):
        assert self.registry.get("does_not_exist") is None

    def test_list_systems_includes_registered(self):
        self.registry.register(self.spec)
        assert "reg_test_sys" in self.registry.list_systems()

    def test_unregister(self):
        self.registry.register(self.spec)
        self.registry.unregister("reg_test_sys")
        assert self.registry.get("reg_test_sys") is None

    def test_load_from_dict(self):
        data = self.spec.model_dump()
        loaded = self.registry.load_from_dict(data)
        assert loaded.system_id == "reg_test_sys"

    def test_singleton_behaviour(self):
        r1 = SystemRegistry()
        r2 = SystemRegistry()
        assert r1 is r2


# ===========================================================================
# Factory — make_entity_model
# ===========================================================================


class TestMakeEntityModel:
    def setup_method(self):
        clear_model_cache("factory_test")
        self.spec = GameSystemSpec(
            system_id="factory_test",
            system_name="Factory Test",
            core_mechanic=CoreMechanicSpec(
                mechanic_type=OntologyMechanicType.D20_OVER,
                success_condition="roll ≥ DC",
            ),
            entity_types={
                "hero": EntityTypeSpec(
                    type_key="hero",
                    display_name="Hero",
                    fields=[
                        FieldSpec(name="hero_name", display_name="Name", field_type=FieldType.STR),
                        FieldSpec(
                            name="strength",
                            display_name="STR",
                            field_type=FieldType.INT,
                            min_value=1,
                            max_value=20,
                            default_value=10,
                        ),
                        FieldSpec(
                            name="modifier",
                            display_name="Modifier",
                            field_type=FieldType.INT,
                            derived_formula="(strength - 10) // 2",
                            user_settable=False,
                        ),
                        FieldSpec(
                            name="level",
                            display_name="Level",
                            field_type=FieldType.INT,
                            min_value=1,
                            max_value=20,
                            default_value=1,
                        ),
                        FieldSpec(
                            name="abilities",
                            display_name="Abilities",
                            field_type=FieldType.LIST_STR,
                            default_value=[],
                            required=False,
                        ),
                    ],
                    validators=[
                        ValidatorSpec(
                            rule_id="abilities_gated_by_level",
                            validator_type=ValidatorType.COUNT_GATE,
                            field="abilities",
                            other_field="level",
                            divisor=5,
                            description="abilities ≤ floor(level/5)",
                            error_message="Too many abilities for current level",
                        ),
                    ],
                )
            },
        )

    def teardown_method(self):
        clear_model_cache("factory_test")

    def test_generates_model(self):
        Model = make_entity_model(self.spec, "hero")
        assert Model.__name__ == "DynamicModel_factory_test_hero"

    def test_cached_on_second_call(self):
        M1 = make_entity_model(self.spec, "hero")
        M2 = make_entity_model(self.spec, "hero")
        assert M1 is M2

    def test_force_rebuild(self):
        M1 = make_entity_model(self.spec, "hero")
        M2 = make_entity_model(self.spec, "hero", force_rebuild=True)
        assert M1 is not M2

    def test_unknown_type_key_raises(self):
        with pytest.raises(KeyError, match="nonexistent"):
            make_entity_model(self.spec, "nonexistent")

    def test_valid_instance_created(self):
        Model = make_entity_model(self.spec, "hero")
        hero = Model(hero_name="Aldric", strength=16, level=1)
        assert hero.hero_name == "Aldric"
        assert hero.strength == 16

    def test_derived_modifier_computed(self):
        Model = make_entity_model(self.spec, "hero")
        hero = Model(hero_name="Aldric", strength=16, level=1)
        assert hero.modifier == 3  # (16-10)//2 = 3

    def test_field_min_max_enforced(self):
        Model = make_entity_model(self.spec, "hero")
        with pytest.raises(ValidationError):
            Model(hero_name="X", strength=25, level=1)  # strength > 20

    def test_count_gate_validator(self):
        Model = make_entity_model(self.spec, "hero")
        # level=5 → floor(5/5)=1 ability allowed
        hero = Model(hero_name="X", strength=10, level=5, abilities=["Charge"])
        assert len(hero.abilities) == 1

        # 2 abilities at level 5 is too many
        with pytest.raises((ValidationError, ValueError)):
            Model(hero_name="X", strength=10, level=5, abilities=["Charge", "Parry"])

    def test_make_all_models(self):
        models = make_all_models(self.spec)
        assert "hero" in models

    def test_validate_entity_data(self):
        result = validate_entity_data(self.spec, "hero", {"hero_name": "X", "strength": 12, "level": 1})
        assert result.hero_name == "X"


# ===========================================================================
# Death in Space spec
# ===========================================================================


class TestDeathInSpaceSpec:
    def test_spec_is_registered(self):
        registry = SystemRegistry()
        spec = registry.get("death_in_space")
        assert spec is not None
        assert spec.system_name == "Death in Space"

    def test_entity_types(self):
        assert "character" in DEATH_IN_SPACE.entity_types
        assert "item" in DEATH_IN_SPACE.entity_types

    def test_core_mechanic_is_d20_under(self):
        assert DEATH_IN_SPACE.core_mechanic.mechanic_type == OntologyMechanicType.D20_UNDER

    def test_character_fields_include_four_attributes(self):
        char = DEATH_IN_SPACE.entity_types["character"]
        field_names = [f.name for f in char.fields]
        for attr in ["body", "dex", "savvy", "tech"]:
            assert attr in field_names, f"Missing attribute: {attr}"

    def test_max_hp_is_derived(self):
        char = DEATH_IN_SPACE.entity_types["character"]
        max_hp_field = next(f for f in char.fields if f.name == "max_hp")
        assert max_hp_field.derived_formula == "max(1, body + 6)"
        assert max_hp_field.user_settable is False

    def test_data_edges_reference_existing_backends(self):
        for edge in DEATH_IN_SPACE.data_edges:
            assert isinstance(edge.from_backend, StorageBackend)
            assert isinstance(edge.to_backend, StorageBackend)

    def test_spec_round_trips_json(self):
        data = DEATH_IN_SPACE.model_dump()
        spec2 = GameSystemSpec.model_validate(data)
        assert spec2.system_id == "death_in_space"
        assert len(spec2.entity_types) == len(DEATH_IN_SPACE.entity_types)


# ===========================================================================
# Death in Space — character model (factory-generated)
# ===========================================================================


class TestDISCharacterModel:
    @pytest.fixture(autouse=True)
    def model(self):
        clear_model_cache("death_in_space")
        self.CharacterModel = make_entity_model(DEATH_IN_SPACE, "character")
        yield
        clear_model_cache("death_in_space")

    def _make(self, **kwargs):
        defaults = {
            "character_name": "Zyx",
            "body": 0,
            "dex": 0,
            "savvy": 0,
            "tech": 0,
            "hp": 6,
            "cosmic_rot": 0,
            "credits": 0,
            "debt": 0,
        }
        defaults.update(kwargs)
        return self.CharacterModel(**defaults)

    def test_create_basic(self):
        sheet = self._make(character_name="Zyx")
        assert sheet.character_name == "Zyx"

    def test_max_hp_derived_body_zero(self):
        sheet = self._make(body=0, hp=6)
        assert sheet.max_hp == 6  # max(1, 0+6)

    def test_max_hp_derived_body_plus_three(self):
        sheet = self._make(body=3, hp=9)
        assert sheet.max_hp == 9  # max(1, 3+6)

    def test_max_hp_derived_body_minus_three(self):
        sheet = self._make(body=-3, hp=1)
        assert sheet.max_hp == 3  # max(1, -3+6) still = 3

    def test_max_hp_floor_is_one_regardless(self):
        # Minimum possible: BODY=-3 → max(1, -3+6)=3, not <1
        sheet = self._make(body=-3, hp=1)
        assert sheet.max_hp >= 1

    def test_body_range_enforced(self):
        with pytest.raises(ValidationError):
            self._make(body=4)
        with pytest.raises(ValidationError):
            self._make(body=-4)

    def test_dex_range_enforced(self):
        with pytest.raises(ValidationError):
            self._make(dex=5)

    def test_cosmic_rot_range_enforced(self):
        with pytest.raises(ValidationError):
            self._make(cosmic_rot=11)
        with pytest.raises(ValidationError):
            self._make(cosmic_rot=-1)

    def test_cosmic_rot_zero_no_powers(self):
        sheet = self._make(cosmic_rot=0, cosmic_powers=[])
        assert sheet.cosmic_rot == 0

    def test_cosmic_powers_gated_rot_three(self):
        """floor(3/3)=1 power allowed at rot=3."""
        sheet = self._make(cosmic_rot=3, cosmic_powers=["Void Sense"])
        assert len(sheet.cosmic_powers) == 1

    def test_cosmic_powers_too_many_for_rot(self):
        """2 powers requires rot ≥ 6."""
        with pytest.raises((ValidationError, ValueError)):
            self._make(cosmic_rot=3, cosmic_powers=["Void Sense", "Drift Step"])

    def test_cosmic_powers_six_rot_two_allowed(self):
        """floor(6/3)=2 powers allowed at rot=6."""
        sheet = self._make(cosmic_rot=6, cosmic_powers=["Void Sense", "Drift Step"])
        assert len(sheet.cosmic_powers) == 2

    def test_cosmic_powers_nine_rot_three_allowed(self):
        """floor(9/3)=3 powers allowed at rot=9."""
        sheet = self._make(
            cosmic_rot=9,
            cosmic_powers=["Void Sense", "Drift Step", "Radiation Skin"],
        )
        assert len(sheet.cosmic_powers) == 3

    def test_invalid_origin_rejected(self):
        with pytest.raises(ValidationError):
            self._make(origin="astronaut")

    def test_valid_origin_accepted(self):
        sheet = self._make(origin="soldier")
        assert sheet.origin == "soldier"

    def test_invalid_skill_rejected(self):
        with pytest.raises(ValidationError):
            self._make(skills=["Hacking"])

    def test_valid_skill_accepted(self):
        sheet = self._make(skills=["Pilot", "Tinker"])
        assert "Pilot" in sheet.skills

    def test_credits_non_negative(self):
        with pytest.raises(ValidationError):
            self._make(credits=-5)

    def test_hp_non_negative(self):
        with pytest.raises(ValidationError):
            self._make(hp=-1)

    def test_default_is_player_character(self):
        sheet = self._make()
        assert sheet.is_player_character is True


# ===========================================================================
# Death in Space — item model (factory-generated)
# ===========================================================================


class TestDISItemModel:
    @pytest.fixture(autouse=True)
    def model(self):
        clear_model_cache("death_in_space")
        self.ItemModel = make_entity_model(DEATH_IN_SPACE, "item")
        yield
        clear_model_cache("death_in_space")

    def test_create_weapon(self):
        item = self.ItemModel(item_name="Combat Knife", item_type="weapon")
        assert item.item_name == "Combat Knife"

    def test_invalid_item_type_rejected(self):
        with pytest.raises(ValidationError):
            self.ItemModel(item_name="X", item_type="spell")

    def test_negative_weight_rejected(self):
        with pytest.raises(ValidationError):
            self.ItemModel(item_name="X", item_type="misc", weight_kg=-1.0)


# ===========================================================================
# Formula evaluator safety
# ===========================================================================


class TestFormulaEval:
    def test_import_in_formula_rejected(self):
        from monitor_data.schemas.rpg_ontology.factory import _eval_formula

        with pytest.raises(ValueError, match="Unsafe"):
            _eval_formula("__import__('os').getcwd()", {})

    def test_exec_in_formula_rejected(self):
        from monitor_data.schemas.rpg_ontology.factory import _eval_formula

        with pytest.raises(ValueError, match="Unsafe"):
            _eval_formula("exec('import os')", {})

    def test_basic_arithmetic(self):
        from monitor_data.schemas.rpg_ontology.factory import _eval_formula

        assert _eval_formula("max(1, body + 6)", {"body": -3}) == 3
        assert _eval_formula("(strength - 10) // 2", {"strength": 16}) == 3
