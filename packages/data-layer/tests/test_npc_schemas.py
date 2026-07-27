"""Tests for NPC schemas in game_systems.py."""

from monitor_data.schemas.game_systems import (
    CoreMechanic,
    CoreMechanicType,
    GameSystemCreate,
    NPCAttack,
    NPCCreationRules,
    NPCStatBlock,
    NPCTier,
    SuccessType,
)


class TestNPCSchemas:
    """Tests for NPC-related Pydantic schemas."""

    def test_npc_tier_enum(self):
        assert NPCTier.MINION == "minion"
        assert NPCTier.BOSS == "boss"
        assert NPCTier.VILLAIN == "villain"
        assert NPCTier.BRUTE == "brute"

    def test_npc_attack_model(self):
        atk = NPCAttack(name="Claw", damage="2d6")
        assert atk.name == "Claw"
        assert atk.damage == "2d6"

    def test_npc_stat_block_model(self):
        block = NPCStatBlock(
            name="Deathclaw",
            tier=NPCTier.BOSS,
            hp=18,
            defense="4",
            attacks=[
                NPCAttack(name="Claw", damage="8+4CD"),
                NPCAttack(name="Bite", damage="10+5CD"),
            ],
            special_abilities=["Terrifying", "Thick Hide 2"],
            source_ref="p.372",
        )
        assert block.name == "Deathclaw"
        assert block.tier == NPCTier.BOSS
        assert block.hp == 18
        assert len(block.attacks) == 2
        assert block.special_abilities == ["Terrifying", "Thick Hide 2"]

    def test_npc_stat_block_defaults(self):
        block = NPCStatBlock(name="Peasant", tier=NPCTier.MINION)
        assert block.hp is None
        assert block.defense is None
        assert block.attacks == []
        assert block.special_abilities == []
        assert block.source_ref is None

    def test_npc_creation_rules_model(self):
        rules = NPCCreationRules(
            types_available=["Brute", "Villain"],
            simplified_stat_method="1 Strength per Brute",
            scaling_notes="Brute: goons. Villain: full stat block.",
        )
        assert len(rules.types_available) == 2
        assert "Brute" in rules.types_available

    def test_game_system_create_with_npc_fields(self):
        """GameSystemCreate should accept NPC fields."""
        gs = GameSystemCreate(
            name="Test System",
            description="A test system",
            core_mechanic=CoreMechanic(
                type=CoreMechanicType.D20,
                formula="1d20 + modifier",
                success_type=SuccessType.MEET_OR_BEAT,
            ),
            npc_stat_blocks=[
                NPCStatBlock(
                    name="Goblin",
                    tier=NPCTier.MINION,
                    hp=7,
                    defense="15",
                    attacks=[NPCAttack(name="Scimitar", damage="1d6+2")],
                )
            ],
            npc_creation_rules=NPCCreationRules(
                types_available=["Minion", "Standard", "Elite"],
                simplified_stat_method="Use CR tables",
            ),
        )
        assert len(gs.npc_stat_blocks) == 1
        assert gs.npc_creation_rules is not None

    def test_game_system_create_without_npc_fields(self):
        """GameSystemCreate should work without NPC fields (backwards compat)."""
        gs = GameSystemCreate(
            name="Simple System",
            description="A simple system",
            core_mechanic=CoreMechanic(
                type=CoreMechanicType.NARRATIVE,
                formula="Narrative resolution",
                success_type=SuccessType.HIGHEST_WINS,
            ),
        )
        assert gs.npc_stat_blocks == []
        assert gs.npc_creation_rules is None


class TestCoreMechanicSchemas:
    """Tests for CoreMechanic schema."""

    def test_core_mechanic_d20(self):
        """CoreMechanic should support D20 type."""
        cm = CoreMechanic(
            type=CoreMechanicType.D20,
            formula="1d20 + modifier",
            success_type=SuccessType.MEET_OR_BEAT,
        )
        assert cm.type == CoreMechanicType.D20
        assert cm.formula == "1d20 + modifier"

    def test_core_mechanic_narrative(self):
        """CoreMechanic should support narrative type."""
        cm = CoreMechanic(
            type=CoreMechanicType.NARRATIVE,
            formula="GM discretion",
            success_type=SuccessType.HIGHEST_WINS,
        )
        assert cm.type == CoreMechanicType.NARRATIVE

    def test_core_mechanic_type_enum_values(self):
        """CoreMechanicType should have expected values."""
        assert CoreMechanicType.D20 == "d20"
        assert CoreMechanicType.NARRATIVE == "narrative"
        assert CoreMechanicType.DICE_POOL == "dice_pool"
        assert CoreMechanicType.PERCENTILE == "percentile"

    def test_success_type_enum_values(self):
        """SuccessType should have expected values."""
        assert SuccessType.MEET_OR_BEAT == "meet_or_beat"
        assert SuccessType.HIGHEST_WINS == "highest_wins"
        assert SuccessType.COUNT_SUCCESSES == "count_successes"
        assert SuccessType.DEGREES_OF_SUCCESS == "degrees_of_success"


class TestNPCAttackSchema:
    """Tests for NPCAttack schema."""

    def test_npc_attack_minimal(self):
        """NPCAttack should work with just name and damage."""
        atk = NPCAttack(name="Punch", damage="1d3")
        assert atk.name == "Punch"
        assert atk.damage == "1d3"

    def test_npc_attack_name_max_length(self):
        """NPCAttack name should have max length validation."""
        long_name = "A" * 200
        # Should not raise validation error at limit
        atk = NPCAttack(name=long_name, damage="1d6")
        assert len(atk.name) == 200
