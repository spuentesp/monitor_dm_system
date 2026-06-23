"""
Tests for the RPG Ontology system — covering schema validation, Death in Space
typed character sheets, equipment, and the tool layer.

Tests are pure unit tests (no DB required): they verify the Pydantic models,
validator rules, and the GameSystemRegistry logic.

Death in Space rule tests verify:
  - Attribute range enforcement (-3 to +3)
  - HP = max(1, BODY + 6) invariant
  - Cosmic Rot power gating (1 power per 3 rot)
  - Weapon damage die typing
  - Armor protection range (0-3)
  - Ship HP ≤ max_hp
  - Discriminated registry lookup
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

# Import the schema under test (auto-registers at import time)
from monitor_data.schemas.rpg_ontology.base import (
    GameSystemRegistry,
)
from monitor_data.schemas.rpg_ontology.systems.death_in_space import (
    DEATH_IN_SPACE,
    SYSTEM_ID,
    DISArmor,
    DISArmorProtection,
    DISCharacterSheet,
    DISCosmicPower,
    DISOrigin,
    DISDamageDie,
    DISShipClass,
    DISShipSheet,
    DISSkill,
    DISWeapon,
    DISWeaponProperty,
)
from monitor_data.tools.rpg_tools import rpg_validate_sheet


# =============================================================================
# Helper factory
# =============================================================================


def valid_dis_sheet(**overrides) -> dict:
    """Return a valid Death in Space character sheet dict."""
    defaults = dict(
        entity_id=str(uuid4()),
        character_name="Zyx the Wanderer",
        body=1,
        dex=2,
        savvy=-1,
        tech=0,
        hp=7,  # max(1, 1 + 6)
        max_hp=7,
        cosmic_rot=0,
    )
    defaults.update(overrides)
    return defaults


# =============================================================================
# 1. GameSystemRegistry
# =============================================================================


class TestGameSystemRegistry:
    def test_death_in_space_is_auto_registered(self):
        reg = GameSystemRegistry()
        assert SYSTEM_ID in reg.list_systems()

    def test_get_definition_returns_correct_system(self):
        reg = GameSystemRegistry()
        defn = reg.get_definition(SYSTEM_ID)
        assert defn is not None
        assert defn.system_name == "Death in Space"
        assert defn.publisher == "MORK BORG Publishing"

    def test_get_sheet_class_returns_dis_class(self):
        reg = GameSystemRegistry()
        cls = reg.get_sheet_class(SYSTEM_ID)
        assert cls is DISCharacterSheet

    def test_parse_sheet_valid(self):
        reg = GameSystemRegistry()
        sheet = reg.parse_sheet(SYSTEM_ID, valid_dis_sheet())
        assert isinstance(sheet, DISCharacterSheet)

    def test_parse_sheet_unknown_system_raises(self):
        reg = GameSystemRegistry()
        with pytest.raises(ValueError, match="Unknown game system: 'nonexistent'"):
            reg.parse_sheet("nonexistent", {})

    def test_attribute_specs_have_correct_range(self):
        defn = GameSystemRegistry().get_definition(SYSTEM_ID)
        for attr in defn.attributes:
            assert attr.min_value == -3
            assert attr.max_value == 3

    def test_validate_attribute_value(self):
        defn = GameSystemRegistry().get_definition(SYSTEM_ID)
        assert defn.validate_attribute_value("BODY", 3) is True
        assert defn.validate_attribute_value("BODY", -3) is True
        assert defn.validate_attribute_value("BODY", 4) is False
        assert defn.validate_attribute_value("BODY", -4) is False

    def test_attribute_lookup_case_insensitive(self):
        defn = GameSystemRegistry().get_definition(SYSTEM_ID)
        assert defn.attribute_by_abbr("body") is not None
        assert defn.attribute_by_abbr("BODY") is not None
        assert defn.attribute_by_abbr("Body") is not None


# =============================================================================
# 2. DISCharacterSheet — attribute validation
# =============================================================================


class TestDISCharacterSheetAttributes:
    def test_valid_character_creates_successfully(self):
        data = valid_dis_sheet()
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.character_name == "Zyx the Wanderer"
        assert sheet.body == 1

    def test_body_max_boundary_accepted(self):
        data = valid_dis_sheet(body=3, max_hp=9, hp=9)
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.body == 3

    def test_body_min_boundary_accepted(self):
        data = valid_dis_sheet(body=-3, max_hp=3, hp=3)
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.body == -3

    def test_body_above_max_rejected(self):
        with pytest.raises(ValidationError, match="less than or equal to 3"):
            DISCharacterSheet.model_validate(valid_dis_sheet(body=4, max_hp=10, hp=10))

    def test_body_below_min_rejected(self):
        with pytest.raises(ValidationError, match="greater than or equal to -3"):
            DISCharacterSheet.model_validate(valid_dis_sheet(body=-4, max_hp=2, hp=2))

    def test_all_attributes_in_range(self):
        data = valid_dis_sheet(body=-3, dex=3, savvy=-2, tech=1, max_hp=3, hp=3)
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.stat_total == -3 + 3 + (-2) + 1  # = -1

    def test_stat_total_computed_correctly(self):
        data = valid_dis_sheet(body=1, dex=2, savvy=-1, tech=0, max_hp=7, hp=7)
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.stat_total == 2  # 1+2+(-1)+0


# =============================================================================
# 3. HP invariant (HP = max(1, BODY + 6))
# =============================================================================


class TestDISHPInvariant:
    @pytest.mark.parametrize(
        "body,expected_max_hp",
        [
            (3, 9),  # 3+6
            (1, 7),  # 1+6
            (0, 6),  # 0+6
            (-1, 5),  # -1+6
            (-3, 3),  # -3+6 = 3 (above min)
        ],
    )
    def test_valid_max_hp_accepted(self, body, expected_max_hp):
        data = valid_dis_sheet(body=body, max_hp=expected_max_hp, hp=1)
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.max_hp == expected_max_hp

    def test_incorrect_max_hp_rejected(self):
        # body=1 → expected max_hp=7, but we pass 8
        with pytest.raises(ValidationError, match="max_hp must be 7"):
            DISCharacterSheet.model_validate(valid_dis_sheet(body=1, max_hp=8, hp=7))

    def test_hp_exceeds_max_hp_rejected(self):
        with pytest.raises(ValidationError, match="cannot exceed max_hp"):
            DISCharacterSheet.model_validate(valid_dis_sheet(body=1, max_hp=7, hp=8))

    def test_hp_at_zero_is_incapacitated(self):
        data = valid_dis_sheet(hp=0)
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.is_incapacitated is True

    def test_hp_above_zero_is_not_incapacitated(self):
        data = valid_dis_sheet(hp=3)
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.is_incapacitated is False

    def test_minimum_max_hp_is_one_when_body_is_minus_five_equivalent(self):
        """This cannot happen in DIS (body≥-3 means max_hp≥3), but test the formula."""
        # body=-3 → max(1, -3+6) = max(1,3) = 3
        data = valid_dis_sheet(body=-3, max_hp=3, hp=1)
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.max_hp == 3


# =============================================================================
# 4. Cosmic Rot power gating
# =============================================================================


class TestDISCosmicRot:
    def test_no_powers_with_zero_rot(self):
        data = valid_dis_sheet(cosmic_rot=0, cosmic_powers=[])
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.cosmic_powers == []

    def test_one_power_allowed_at_rot_3(self):
        data = valid_dis_sheet(
            cosmic_rot=3,
            cosmic_powers=[DISCosmicPower.VOID_SENSE.value],
        )
        sheet = DISCharacterSheet.model_validate(data)
        assert len(sheet.cosmic_powers) == 1

    def test_two_powers_allowed_at_rot_6(self):
        data = valid_dis_sheet(
            cosmic_rot=6,
            cosmic_powers=[DISCosmicPower.VOID_SENSE.value, DISCosmicPower.DRIFT_STEP.value],
        )
        sheet = DISCharacterSheet.model_validate(data)
        assert len(sheet.cosmic_powers) == 2

    def test_three_powers_allowed_at_rot_9(self):
        data = valid_dis_sheet(
            cosmic_rot=9,
            cosmic_powers=[
                DISCosmicPower.VOID_SENSE.value,
                DISCosmicPower.DRIFT_STEP.value,
                DISCosmicPower.PSYCHIC_SCREAM.value,
            ],
        )
        sheet = DISCharacterSheet.model_validate(data)
        assert len(sheet.cosmic_powers) == 3

    def test_too_many_powers_for_rot_level_rejected(self):
        # rot=3 allows only 1 power
        with pytest.raises(ValidationError, match="allows at most 1 power"):
            DISCharacterSheet.model_validate(
                valid_dis_sheet(
                    cosmic_rot=3,
                    cosmic_powers=[
                        DISCosmicPower.VOID_SENSE.value,
                        DISCosmicPower.DRIFT_STEP.value,
                    ],
                )
            )

    def test_power_slots_available_computed(self):
        data = valid_dis_sheet(
            cosmic_rot=6,
            cosmic_powers=[DISCosmicPower.VOID_SENSE.value],
        )
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.power_slots_available() == 1  # 6//3=2 slots, 1 used

    def test_cosmic_rot_max_is_ten(self):
        with pytest.raises(ValidationError, match="less than or equal to 10"):
            DISCharacterSheet.model_validate(valid_dis_sheet(cosmic_rot=11))

    def test_fully_corrupted_flag(self):
        data = valid_dis_sheet(
            cosmic_rot=10,
            cosmic_powers=[
                DISCosmicPower.VOID_SENSE.value,
                DISCosmicPower.DRIFT_STEP.value,
                DISCosmicPower.PSYCHIC_SCREAM.value,
            ],
        )
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.is_fully_corrupted is True


# =============================================================================
# 5. Skills
# =============================================================================


class TestDISSkills:
    def test_valid_skills_accepted(self):
        data = valid_dis_sheet(skills=[DISSkill.SHARP.value, DISSkill.SNEAKY.value])
        sheet = DISCharacterSheet.model_validate(data)
        assert len(sheet.skills) == 2

    def test_duplicate_skills_rejected(self):
        with pytest.raises(ValidationError, match="duplicates"):
            DISCharacterSheet.model_validate(
                valid_dis_sheet(skills=[DISSkill.SHARP.value, DISSkill.SHARP.value])
            )

    def test_origin_accepted(self):
        data = valid_dis_sheet(origin=DISOrigin.CONTRACTOR.value)
        sheet = DISCharacterSheet.model_validate(data)
        assert sheet.origin == DISOrigin.CONTRACTOR


# =============================================================================
# 6. Weapons
# =============================================================================


class TestDISWeapon:
    def test_melee_weapon_no_range_required(self):
        weapon = DISWeapon(
            name="Combat Knife",
            damage_formula=DISDamageDie.D4,
            is_ranged=False,
        )
        assert weapon.damage_formula == DISDamageDie.D4
        assert weapon.range_m is None

    def test_ranged_weapon_requires_range(self):
        with pytest.raises(ValidationError, match="Ranged weapons must specify range_m"):
            DISWeapon(
                name="Scrapper's Pistol",
                damage_formula=DISDamageDie.D6,
                is_ranged=True,
                # missing range_m
            )

    def test_valid_ranged_weapon(self):
        weapon = DISWeapon(
            name="Scrapper's Pistol",
            damage_formula=DISDamageDie.D6,
            is_ranged=True,
            range_m=30,
        )
        assert weapon.range_m == 30

    def test_assault_rifle_is_d10(self):
        weapon = DISWeapon(
            name="Assault Rifle",
            damage_formula=DISDamageDie.D10,
            is_ranged=True,
            range_m=100,
            properties=[DISWeaponProperty.SLOW],
        )
        assert weapon.damage_formula == DISDamageDie.D10

    def test_energy_weapon(self):
        weapon = DISWeapon(
            name="Plasma Cutter",
            damage_formula=DISDamageDie.D6,
            is_ranged=True,
            range_m=15,
            properties=[DISWeaponProperty.ENERGY],
        )
        assert DISWeaponProperty.ENERGY in weapon.properties


# =============================================================================
# 7. Armor
# =============================================================================


class TestDISArmor:
    def test_light_armor(self):
        armor = DISArmor(
            name="Padded Jacket",
            protection=DISArmorProtection.LIGHT,
        )
        assert armor.protection == DISArmorProtection.LIGHT
        assert armor.protection == 1

    def test_heavy_armor(self):
        armor = DISArmor(
            name="Full Environmental Suit",
            protection=DISArmorProtection.HEAVY,
            blocks_cosmic_rot=True,
        )
        assert armor.protection == 3
        assert armor.blocks_cosmic_rot is True

    def test_protection_enum_values(self):
        assert DISArmorProtection.NONE == 0
        assert DISArmorProtection.LIGHT == 1
        assert DISArmorProtection.MEDIUM == 2
        assert DISArmorProtection.HEAVY == 3


# =============================================================================
# 8. Ships
# =============================================================================


class TestDISShipSheet:
    def test_valid_ship(self):
        ship = DISShipSheet(
            name="The Leaking Coffin",
            ship_class=DISShipClass.FREIGHTER,
            hull_points=8,
            max_hull_points=12,
            crew_capacity=4,
            drive_condition=6,
        )
        assert ship.hull_points == 8
        assert ship.max_hull_points == 12

    def test_hull_points_cannot_exceed_max(self):
        with pytest.raises(ValidationError, match="cannot exceed max_hull_points"):
            DISShipSheet(
                name="Ghost Ship",
                ship_class=DISShipClass.SHUTTLE,
                hull_points=10,
                max_hull_points=6,
                crew_capacity=2,
            )

    def test_drive_condition_range(self):
        with pytest.raises(ValidationError, match="less than or equal to 6"):
            DISShipSheet(
                name="Fast Ship",
                ship_class=DISShipClass.WARSHIP,
                hull_points=20,
                max_hull_points=20,
                crew_capacity=12,
                drive_condition=7,  # out of range 0-6
            )


# =============================================================================
# 9. rpg_validate_sheet tool
# =============================================================================


class TestRPGValidateSheet:
    def test_valid_sheet_returns_success(self):
        result = rpg_validate_sheet(SYSTEM_ID, valid_dis_sheet())
        assert result["valid"] is True
        assert result["errors"] == []

    def test_invalid_sheet_returns_errors(self):
        bad_data = valid_dis_sheet(body=99, max_hp=105, hp=105)
        result = rpg_validate_sheet(SYSTEM_ID, bad_data)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_unknown_system_returns_error(self):
        result = rpg_validate_sheet("nonexistent_system", {})
        assert result["valid"] is False
        assert "Unknown game system" in result["errors"][0]

    def test_wrong_max_hp_returns_error(self):
        bad_data = valid_dis_sheet(body=0, max_hp=99, hp=6)
        result = rpg_validate_sheet(SYSTEM_ID, bad_data)
        assert result["valid"] is False
        assert any("max_hp" in e for e in result["errors"])


# =============================================================================
# 10. DEATH_IN_SPACE system definition integrity
# =============================================================================


class TestDEATHINSPACEDefinition:
    def test_system_id_is_snake_case(self):
        import re

        assert re.match(r"^[a-z][a-z0-9_]*$", DEATH_IN_SPACE.system_id)

    def test_has_exactly_four_attributes(self):
        assert len(DEATH_IN_SPACE.attributes) == 4

    def test_attribute_abbreviations_are_uppercase(self):
        abbrs = [a.abbreviation for a in DEATH_IN_SPACE.attributes]
        assert abbrs == ["BODY", "DEX", "SAVVY", "TECH"]

    def test_has_hp_resource(self):
        res_names = [r.abbreviation for r in DEATH_IN_SPACE.resources]
        assert "HP" in res_names

    def test_has_cosmic_rot_resource(self):
        res_names = [r.abbreviation for r in DEATH_IN_SPACE.resources]
        assert "ROT" in res_names

    def test_schema_class_path_is_importable(self):
        """The schema_class string must resolve to DISCharacterSheet."""
        module_path, class_name = DEATH_IN_SPACE.schema_class.rsplit(".", 1)
        import importlib

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        assert cls is DISCharacterSheet

    def test_hp_max_formula_in_resource(self):
        hp_res = next(r for r in DEATH_IN_SPACE.resources if r.abbreviation == "HP")
        assert "BODY" in hp_res.max_formula
        assert "6" in hp_res.max_formula


# =============================================================================
# 11. Integration-style — full character creation flow
# =============================================================================


class TestDISFullCharacterCreation:
    """End-to-end character creation mirroring the Death in Space rulebook."""

    def test_create_zyx_the_wanderer(self):
        """Contractor origin, survivalist character."""
        sheet = DISCharacterSheet.model_validate(
            {
                "entity_id": str(uuid4()),
                "character_name": "Zyx the Wanderer",
                "body": 1,
                "dex": 2,
                "savvy": -1,
                "tech": 0,
                "hp": 7,
                "max_hp": 7,  # max(1, 1+6)
                "cosmic_rot": 0,
                "origin": DISOrigin.CONTRACTOR.value,
                "drive": "Find my lost crew",
                "skills": [DISSkill.TOUGH.value, DISSkill.MUSCLE.value],
                "credits": 50,
            }
        )
        assert sheet.character_name == "Zyx the Wanderer"
        assert sheet.stat_total == 2
        assert not sheet.is_incapacitated

    def test_create_void_cultist_with_cosmic_powers(self):
        """High rot character — unlocked 2 cosmic powers."""
        sheet = DISCharacterSheet.model_validate(
            {
                "entity_id": str(uuid4()),
                "character_name": "Brother Null",
                "body": -2,
                "dex": 0,
                "savvy": 3,
                "tech": -1,
                "hp": 1,  # max(1, -2+6)=4 → current hp=1
                "max_hp": 4,
                "cosmic_rot": 7,
                "cosmic_powers": [
                    DISCosmicPower.VOID_SENSE.value,
                    DISCosmicPower.DRIFT_STEP.value,
                ],
                "cosmic_marks": ["Empty eye sockets replaced with void crystals"],
                "origin": DISOrigin.CULTIST.value,
                "drive": "Bring the Final Void to all",
                "skills": [DISSkill.SNEAKY.value],
                "credits": 0,
            }
        )
        assert sheet.cosmic_rot == 7
        assert len(sheet.cosmic_powers) == 2
        assert sheet.power_slots_available() == 0  # 7//3=2, 2 used

    def test_minimum_viable_character(self):
        """Bare-minimum valid character (all zeros)."""
        sheet = DISCharacterSheet.model_validate(
            {
                "entity_id": str(uuid4()),
                "character_name": "Unknown Drifter",
                "body": 0,
                "dex": 0,
                "savvy": 0,
                "tech": 0,
                "hp": 6,
                "max_hp": 6,  # max(1, 0+6)
                "cosmic_rot": 0,
            }
        )
        assert sheet.max_hp == 6
        assert sheet.stat_total == 0
