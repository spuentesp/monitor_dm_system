"""
Tests for NPC/Scene Generator schemas and agent.

LAYER: data-layer (unit tests)
"""

from monitor_data.schemas.npc_scene_generator import (
    SceneBehavioralTrigger,
    GeneratedNPCProfile,
    ScenePrompt,
    NPCSceneGeneratorOutput,
)
from monitor_data.schemas.agendas import ExtractedAgenda
from monitor_data.schemas.knowledge_packs import ExtractedRandomTable, ExtractedTableEntry


class TestBehavioralTrigger:
    def test_minimal_trigger(self):
        bt = SceneBehavioralTrigger(trigger_topic="merchants", reaction="Flinches", gm_note=None)
        assert bt.trigger_topic == "merchants"
        assert bt.reaction == "Flinches"

    def test_trigger_with_gm_note(self):
        bt = SceneBehavioralTrigger(
            trigger_topic="betrayal", reaction="Cold fury", gm_note="NPC was betrayed in backstory"
        )
        assert bt.gm_note == "NPC was betrayed in backstory"

    def test_trigger_with_empty_gm_note(self):
        """SceneBehavioralTrigger with None gm_note is handled correctly."""
        bt = SceneBehavioralTrigger(trigger_topic="betrayal", reaction="Cold fury", gm_note=None)
        assert bt.gm_note is None
        assert bt.trigger_topic == "betrayal"
        assert bt.reaction == "Cold fury"


class TestGeneratedNPCProfile:
    def test_minimal_npc(self):
        npc = GeneratedNPCProfile(
            name="Zara",
            role="fortune teller",
            personality_summary="Paranoid",
            current_goal="Find the merchant",
        )
        assert npc.name == "Zara"
        assert npc.agenda_title is None
        assert npc.behavior_triggers == []
        assert npc.suggested_dialogue_hooks == []

    def test_full_npc(self):
        bt = SceneBehavioralTrigger(trigger_topic="tea", reaction="Flinches")
        npc = GeneratedNPCProfile(
            name="Zara",
            role="fortune teller",
            personality_summary="Paranoid and vengeful",
            current_goal="Find the merchant who cursed her",
            agenda_title="The Cursed Tea Conspiracy",
            behavior_triggers=[bt],
            suggested_dialogue_hooks=[
                "I sense betrayal in your future",
                "Ask about the tea. I dare you.",
            ],
            suggested_scene_invitations=[
                "A fortune teller blocks the path, demanding to read your palms"
            ],
            tags=["npc", "gothic"],
        )
        assert npc.behavior_triggers[0].trigger_topic == "tea"
        assert len(npc.suggested_dialogue_hooks) == 2

    def test_npc_from_agenda(self):
        """NPC can be derived from an ExtractedAgenda."""
        agenda = ExtractedAgenda(
            title="The Cursed Tea Conspiracy",
            description="Zara seeks revenge on the merchant who sold her cursed tea",
            agenda_type="faction_goal",
            suggested_segments=8,
        )
        # Simulate conversion - extract name from description
        npc_name = "Zara"  # In real use, would extract from description
        npc = GeneratedNPCProfile(
            name=npc_name,
            role="fortune teller",
            personality_summary="Shaped by vengeance",
            current_goal=agenda.description,
            agenda_title=agenda.title,
        )
        assert npc.name == "Zara"
        assert npc.agenda_title == "The Cursed Tea Conspiracy"

    def test_npc_with_all_optional_fields(self):
        """NPC with all optional fields populated."""
        bt1 = SceneBehavioralTrigger(
            trigger_topic="merchants", reaction="Flinches", gm_note="Betrayed by merchant"
        )
        bt2 = SceneBehavioralTrigger(
            trigger_topic="tea", reaction="Cold fury", gm_note="Cursed tea incident"
        )
        npc = GeneratedNPCProfile(
            name="Zara",
            role="fortune teller",
            personality_summary="Paranoid and vengeful",
            current_goal="Find the merchant who cursed her",
            agenda_title="The Cursed Tea Conspiracy",
            behavior_triggers=[bt1, bt2],
            suggested_dialogue_hooks=[
                "I sense betrayal in your future",
                "Ask about the tea. I dare you.",
                "The cards tell me you're hiding something",
            ],
            suggested_scene_invitations=[
                "A fortune teller blocks the path, demanding to read your palms",
                "Find Zara in her dimly lit tent, surrounded by strange herbs",
            ],
            tags=["npc", "gothic", "fortune_teller", "vengeful"],
        )
        assert len(npc.behavior_triggers) == 2
        assert len(npc.suggested_dialogue_hooks) == 3
        assert len(npc.suggested_scene_invitations) == 2
        assert len(npc.tags) == 4
        assert npc.behavior_triggers[0].trigger_topic == "merchants"
        assert npc.behavior_triggers[1].trigger_topic == "tea"


class TestScenePrompt:
    def test_minimal_scene(self):
        scene = ScenePrompt(
            title="Ambush in the Sewers",
            setup="Party is ambushed by RatCatchers",
        )
        assert scene.npcs_involved == []
        assert scene.random_table_rolls == []

    def test_full_scene(self):
        scene = ScenePrompt(
            title="Ambush in the Sewers",
            setup="The party is exploring the aqueducts when a gang springs an ambush",
            npcs_involved=["Zara"],
            random_table_rolls=[
                {
                    "table": "Sewer Encounters",
                    "roll": "14",
                    "result": "2d4 RatCatchers with smoke bombs",
                }
            ],
            agenda_clocks_active=["The Cursed Tea Conspiracy"],
            suggested_conflict="The RatCatchers are clearing tunnels for a larger purpose",
            tags=["encounter", "urban"],
        )
        assert scene.npcs_involved == ["Zara"]
        assert scene.random_table_rolls[0]["table"] == "Sewer Encounters"

    def test_scene_from_random_table(self):
        """Scene can be generated from an ExtractedRandomTable."""
        table = ExtractedRandomTable(
            name="Sewer Encounters",
            description="Random threats in the city sewers",
            dice_formula="1d20",
            table_type="encounter",
            entries=[
                ExtractedTableEntry(min_roll=1, max_roll=5, value="1d6 Giant Rats"),
                ExtractedTableEntry(min_roll=6, max_roll=10, value="1 Otyugh"),
                ExtractedTableEntry(min_roll=11, max_roll=15, value="2d4 RatCatchers"),
                ExtractedTableEntry(
                    min_roll=16,
                    max_roll=20,
                    value="Roll on 'Major Boss' table",
                    subtable_name="Major Boss",
                ),
            ],
        )
        # Simulate picking entry 3 (RatCatchers)
        entry = table.entries[2]
        scene = ScenePrompt(
            title=f"Encounter: {entry.value}",
            setup=f"Roll on {table.name} produced {entry.value}",
            random_table_rolls=[{"table": table.name, "roll": "14", "result": entry.value}],
            tags=["encounter", table.table_type],
        )
        assert "RatCatchers" in scene.title
        assert scene.tags == ["encounter", "encounter"]

    def test_scene_with_all_optional_fields(self):
        """Scene with all optional fields populated."""
        scene = ScenePrompt(
            title="The Betrayal at Midnight",
            setup="The party meets Zara at midnight, where she reveals the merchant's treachery",
            npcs_involved=["Zara", "The Merchant"],
            random_table_rolls=[
                {
                    "table": "Urban Encounters",
                    "roll": "7",
                    "result": "Mysterious stranger approaches",
                },
                {"table": "Weather", "roll": "12", "result": "Overcast with distant thunder"},
            ],
            agenda_clocks_active=["The Cursed Tea Conspiracy", "Merchant's Revenge"],
            suggested_conflict="Zara wants the party to help her exact revenge, but the merchant offers them gold to eliminate her instead",
            tags=["encounter", "social", "betrayal", "night", "urban"],
        )
        assert len(scene.npcs_involved) == 2
        assert len(scene.random_table_rolls) == 2
        assert len(scene.agenda_clocks_active) == 2
        assert scene.suggested_conflict is not None
        assert "Zara" in scene.suggested_conflict
        assert len(scene.tags) == 5


class TestNPCSceneGeneratorOutput:
    def test_empty_output(self):
        output = NPCSceneGeneratorOutput()
        assert output.npcs == []
        assert output.scenes == []

    def test_output_with_npcs_and_scenes(self):
        npc = GeneratedNPCProfile(
            name="Zara",
            role="fortune teller",
            personality_summary="Paranoid",
            current_goal="Seek revenge",
        )
        scene = ScenePrompt(title="Ambush", setup="Party is ambushed")
        output = NPCSceneGeneratorOutput(
            npcs=[npc], scenes=[scene], generated_from_pack_id="test-pack-123"
        )
        assert len(output.npcs) == 1
        assert len(output.scenes) == 1
        assert output.generated_from_pack_id == "test-pack-123"

    def test_output_multiple_npcs_and_scenes(self):
        npcs = [
            GeneratedNPCProfile(
                name=f"NPC{i}", role="role", personality_summary="summary", current_goal="goal"
            )
            for i in range(5)
        ]
        scenes = [ScenePrompt(title=f"Scene{i}", setup=f"Setup {i}") for i in range(3)]
        output = NPCSceneGeneratorOutput(npcs=npcs, scenes=scenes)
        assert len(output.npcs) == 5
        assert len(output.scenes) == 3

    def test_output_without_generated_from_pack_id(self):
        """Output can be created without a pack_id (optional field)."""
        npc = GeneratedNPCProfile(
            name="Zara",
            role="fortune teller",
            personality_summary="Paranoid",
            current_goal="Seek revenge",
        )
        scene = ScenePrompt(title="Ambush", setup="Party is ambushed")
        output = NPCSceneGeneratorOutput(npcs=[npc], scenes=[scene])
        assert output.generated_from_pack_id is None
        assert len(output.npcs) == 1
        assert len(output.scenes) == 1

    def test_output_json_serialization(self):
        """NPCSceneGeneratorOutput can be serialized to JSON."""
        npc = GeneratedNPCProfile(
            name="Zara",
            role="fortune teller",
            personality_summary="Paranoid",
            current_goal="Seek revenge",
            agenda_title="The Cursed Tea Conspiracy",
        )
        scene = ScenePrompt(
            title="The Betrayal",
            setup="Zara reveals the merchant's treachery",
            npcs_involved=["Zara"],
            suggested_conflict="Zara vs The Merchant",
        )
        output = NPCSceneGeneratorOutput(
            npcs=[npc], scenes=[scene], generated_from_pack_id="test-pack-123"
        )
        # Test that model_dump() works (Pydantic v2)
        data = output.model_dump()
        assert "npcs" in data
        assert "scenes" in data
        assert "generated_from_pack_id" in data
        assert data["generated_from_pack_id"] == "test-pack-123"
        assert len(data["npcs"]) == 1
        assert len(data["scenes"]) == 1
