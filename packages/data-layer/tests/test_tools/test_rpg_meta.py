"""
Tests for the general RPG meta-schema engine.

Tests cover:
  - meta.py — FieldSpec, ValidatorSpec, EntityTypeSpec, GameSystemSpec, SystemRegistry
  - factory.py — make_entity_model, validate_entity_data, clear_model_cache
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
    ItemTypeSpec,
    OntologyMechanicType,
    RelationCardinality,
    RelationSpec,
    SystemRegistry,
    ValidatorSpec,
    ValidatorType,
)

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


class TestItemEntityModel:
    """Factory-generated item model with typed weapon/armor sub-types."""

    @pytest.fixture(autouse=True)
    def model(self):
        clear_model_cache("item_factory_test")
        self.spec = GameSystemSpec(
            system_id="item_factory_test",
            system_name="Item Factory Test",
            core_mechanic=CoreMechanicSpec(
                mechanic_type=OntologyMechanicType.D20_OVER,
                success_condition="roll ≥ DC",
            ),
            entity_types={
                "item": EntityTypeSpec(
                    type_key="item",
                    display_name="Item",
                    fields=[
                        FieldSpec(name="item_name", display_name="Name", field_type=FieldType.STR),
                        FieldSpec(
                            name="item_type",
                            display_name="Item Type",
                            field_type=FieldType.ENUM,
                            enum_values=["weapon", "armor", "misc"],
                        ),
                        FieldSpec(
                            name="weight_kg",
                            display_name="Weight (kg)",
                            field_type=FieldType.FLOAT,
                            min_value=0.0,
                            required=False,
                        ),
                    ],
                    item_types={
                        "weapon": ItemTypeSpec(
                            type_key="weapon",
                            display_name="Weapon",
                            extra_fields=[
                                FieldSpec(
                                    name="damage_die",
                                    display_name="Damage Die",
                                    field_type=FieldType.STR,
                                    default_value="1d6",
                                ),
                            ],
                        ),
                    },
                )
            },
        )
        yield
        clear_model_cache("item_factory_test")

    def test_create_weapon(self):
        ItemModel = make_entity_model(self.spec, "item")
        item = ItemModel(item_name="Short Sword", item_type="weapon")
        assert item.item_name == "Short Sword"

    def test_invalid_item_type_rejected(self):
        ItemModel = make_entity_model(self.spec, "item")
        with pytest.raises(ValidationError):
            ItemModel(item_name="X", item_type="spell")

    def test_negative_weight_rejected(self):
        ItemModel = make_entity_model(self.spec, "item")
        with pytest.raises(ValidationError):
            ItemModel(item_name="X", item_type="misc", weight_kg=-1.0)


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
