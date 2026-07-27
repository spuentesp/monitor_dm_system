"""
E2E Test 03 — Game System (RS-1..RS-4)

Tests the game-system CRUD operations in MongoDB and the dice resolution
utilities.

Use cases covered
-----------------
DL-20  Manage game systems in MongoDB
RS-1   Create a new game system (D20 rules)
RS-2   Retrieve and list game systems
RS-3   Dice resolution — skill check
RS-4   Dice resolution — combat attack roll with modifiers

The GM-loop resolution path (Resolver agent) is exercised in test_04_gm_loop.py.
This file focuses on the data-layer primitives.
"""

from __future__ import annotations

from typing import Any

import pytest

# =============================================================================
# RS-1 / DL-20: Game System CRUD
# =============================================================================


@pytest.mark.e2e
@pytest.mark.integration
class TestGameSystemCRUD:
    """RS-1 / RS-2 — Game system creation and retrieval."""

    def test_game_system_created_by_fixture(self, seeded_game_system: Any) -> None:
        """RS-1: seeded_game_system fixture creates a D20 game system."""
        assert seeded_game_system is not None
        assert seeded_game_system.id is not None
        assert (
            "D20" in seeded_game_system.name.upper()
            or "d20" in seeded_game_system.name.lower()
        )

    def test_get_game_system_by_id(self, seeded_game_system: Any) -> None:
        """RS-2: Retrieving the game system by ID returns correct data."""
        from monitor_data.tools.mongodb_tools import mongodb_get_game_system

        gs = mongodb_get_game_system(seeded_game_system.id)
        assert gs is not None
        assert gs.id == seeded_game_system.id
        assert len(gs.attributes) == 6  # STR, DEX, CON, INT, WIS, CHA
        assert len(gs.skills) == 9

    def test_list_game_systems_includes_seed(self, seeded_game_system: Any) -> None:
        """RS-2: Listing game systems includes the seeded D20 system."""
        from monitor_data.tools.mongodb_tools import mongodb_list_game_systems

        result = mongodb_list_game_systems()
        # Returns object with .systems or List — check both shapes
        if hasattr(result, "systems"):
            systems = result.systems
        else:
            systems = result
        ids = [s.id for s in systems]
        assert seeded_game_system.id in ids

    def test_game_system_has_core_mechanic(self, seeded_game_system: Any) -> None:
        """RS-1: Core mechanic is the D20 formula."""
        gs = seeded_game_system
        assert gs.core_mechanic is not None
        assert gs.core_mechanic.type.value == "d20"
        assert (
            "d20" in gs.core_mechanic.formula.lower()
            or "D20" in gs.core_mechanic.formula
        )

    def test_game_system_has_rules(self, seeded_game_system: Any) -> None:
        """RS-1: Game system includes combat and mechanic rules."""
        gs = seeded_game_system
        assert len(gs.rules) >= 1
        rule_names = [r.name for r in gs.rules]
        assert any(
            "Attack" in n or "Initiative" in n or "Armor" in n for n in rule_names
        )

    def test_game_system_attributes_correct(self, seeded_game_system: Any) -> None:
        """RS-1: All 6 D&D-like attributes are present with correct names."""
        gs = seeded_game_system
        attr_names = [a.name for a in gs.attributes]
        for attr in (
            "Strength",
            "Dexterity",
            "Constitution",
            "Intelligence",
            "Wisdom",
            "Charisma",
        ):
            assert attr in attr_names, f"{attr} missing from attribute definitions"

    def test_game_system_skills_linked_to_attributes(
        self, seeded_game_system: Any
    ) -> None:
        """RS-1: Skills have linked_attribute set and point to valid attributes."""
        gs = seeded_game_system
        attr_names = {a.name for a in gs.attributes}
        for skill in gs.skills:
            if skill.linked_attribute:
                assert skill.linked_attribute in attr_names, (
                    f"Skill {skill.name} links to unknown attribute {skill.linked_attribute}"
                )

    def test_create_second_game_system(self, e2e_databases: Any) -> None:
        """RS-1: Multiple game systems can co-exist in the DB."""
        from monitor_data.schemas.game_systems import (
            CoreMechanic,
            CoreMechanicType,
            GameSystemCreate,
            SuccessType,
        )
        from monitor_data.tools.mongodb_tools import (
            mongodb_create_game_system,
            mongodb_get_game_system,
        )

        gs2 = mongodb_create_game_system(
            GameSystemCreate(
                name="Narrative Homebrew",
                version="0.1",
                description="A pure narrative system with no dice.",
                core_mechanic=CoreMechanic(
                    type=CoreMechanicType.NARRATIVE,
                    formula="narrative description only",
                    success_type=SuccessType.HIGHEST_WINS,
                ),
                attributes=[],
                skills=[],
                rules=[],
                # [G-8] Provenance gate — direct creation needs hand_authored
                # since this e2e test doesn't ingest a source document.
                hand_authored=True,
            )
        )
        assert gs2 is not None
        retrieved = mongodb_get_game_system(gs2.id)
        assert retrieved.name == "Narrative Homebrew"


# =============================================================================
# RS-3 / RS-4: Dice Resolution
# =============================================================================


@pytest.mark.e2e
class TestDiceResolution:
    """
    RS-3 / RS-4 — Dice rolling and modifier calculation.

    These tests use the data-layer dice utilities directly.
    Agent-level resolution (Resolver.resolve_check) is exercised
    in test_04_gm_loop.py.
    """

    def test_roll_d20_in_range(self) -> None:
        """RS-3: A d20 roll always lands between 1 and 20."""
        from monitor_data.utils.dice import roll_dice

        for _ in range(50):
            result = roll_dice("1d20")
            assert 1 <= result.total <= 20, f"d20 out of range: {result.total}"

    def test_roll_d20_plus_modifier(self) -> None:
        """RS-3: Modifier is added correctly to the roll."""
        from monitor_data.utils.dice import roll_dice

        for _ in range(20):
            result = roll_dice("1d20+5")
            # d20 (1-20) + 5 = 6-25
            assert 6 <= result.total <= 25, f"d20+5 out of range: {result.total}"

    def test_roll_multiple_dice(self) -> None:
        """RS-4: Multi-die expressions work (e.g., 2d6 for damage)."""
        from monitor_data.utils.dice import roll_dice

        for _ in range(20):
            result = roll_dice("2d6")
            assert 2 <= result.total <= 12, f"2d6 out of range: {result.total}"
            assert len(result.rolls) == 2

    def test_roll_result_has_expression(self) -> None:
        """RS-3: DiceResult records the original expression."""
        from monitor_data.utils.dice import roll_dice

        result = roll_dice("1d20")
        assert result.expression == "1d20"

    def test_calculate_strength_modifier(self) -> None:
        """RS-3: Strength 16 → modifier +3 (D&D formula: floor((16-10)/2))."""
        from monitor_data.utils.dice import calculate_modifier

        # D&D-style modifier: floor((attr - 10) / 2)
        assert calculate_modifier(16, "(VALUE - 10) // 2") == 3
        assert calculate_modifier(10, "(VALUE - 10) // 2") == 0
        assert calculate_modifier(8, "(VALUE - 10) // 2") == -1

    def test_calculate_dexterity_modifier(self) -> None:
        """RS-3: Dexterity 14 → modifier +2."""
        from monitor_data.utils.dice import calculate_modifier

        assert calculate_modifier(14, "(VALUE - 10) // 2") == 2

    def test_skill_check_success(self) -> None:
        """RS-4: A skill check with high modifier passes a DC 10."""
        from monitor_data.utils.dice import calculate_modifier, roll_dice

        # STR 18 → modifier +4. Minimum total on d20+4 = 5, well above easy DC.
        modifier = calculate_modifier(18, "(VALUE - 10) // 2")
        assert modifier == 4

        # Run 10 checks — all should pass DC 10 with +4 on at least 60% of rolls
        passes = 0
        for _ in range(10):
            result = roll_dice("1d20")
            if result.total + modifier >= 10:
                passes += 1
        # At DC10 with +4 modifier, success chance is 70% (roll >= 6)
        # 10 samples might fail, keep threshold low
        assert passes >= 3

    def test_natural_20_critical_success(self) -> None:
        """RS-4: We can detect a natural 20 in dice results."""
        from monitor_data.utils.dice import roll_dice

        # Roll until we see a 20 (p=5%, expected 20 rolls)
        seen_20 = False
        for _ in range(200):
            result = roll_dice("1d20")
            if result.rolls[0] == 20:
                seen_20 = True
                break
        assert seen_20, "Should see at least one natural 20 in 200 rolls"

    def test_natural_1_critical_failure(self) -> None:
        """RS-4: We can detect a natural 1 in dice results."""
        from monitor_data.utils.dice import roll_dice

        seen_1 = False
        for _ in range(200):
            result = roll_dice("1d20")
            if result.rolls[0] == 1:
                seen_1 = True
                break
        assert seen_1, "Should see at least one natural 1 in 200 rolls"

    def test_to_dict_format(self) -> None:
        """RS-3: DiceResult.to_dict() returns serializable dict."""
        from monitor_data.utils.dice import roll_dice

        result = roll_dice("1d20+3")
        d = result.to_dict()
        assert "total" in d
        assert "rolls" in d
        assert "expression" in d
        assert isinstance(d["total"], int)
        assert isinstance(d["rolls"], list)
