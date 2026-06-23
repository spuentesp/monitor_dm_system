import pytest
from unittest.mock import AsyncMock, MagicMock
from monitor_agents.analyzer import Analyzer
from monitor_data.schemas.knowledge_packs import (
    ExtractedCharacterProfile,
    ExtractedGenerationTemplate,
    ExtractedToneProfile,
)
from monitor_data.schemas.game_systems import (
    CreationLogicStep,
    LogicStepType,
)
from monitor_agents.utils.analyzer_support import SectionDigest


@pytest.mark.asyncio
async def test_extract_creation_logic_success():
    analyzer = Analyzer()
    mock_result = MagicMock()
    mock_result.logic_steps = [
        CreationLogicStep(
            step_number=1,
            logic_type=LogicStepType.CHOICE,
            data_source="archetype:Clan",
            target_field="sheet.identity.clan",
            is_automated=False,
        ),
        CreationLogicStep(
            step_number=2,
            logic_type=LogicStepType.ROLL,
            data_source="4d6k3",
            target_field="sheet.attributes.strength",
            is_automated=True,
        ),
    ]
    analyzer._call_module = AsyncMock(return_value=mock_result)

    steps = [
        {
            "step_number": 1,
            "title": "Pick a Clan",
            "instructions": "Choose one from the list of clans.",
        },
        {
            "step_number": 2,
            "title": "Roll Stats",
            "instructions": "Roll 4d6 and keep the highest 3.",
        },
    ]
    results = await analyzer._extract_creation_logic(steps, "Archetypes: Brujah, Gangrel")

    assert len(results) == 2
    assert results[0].logic_type == LogicStepType.CHOICE
    assert results[1].target_field == "sheet.attributes.strength"


@pytest.mark.asyncio
async def test_extract_tone_profiles_success():
    analyzer = Analyzer()
    mock_result = MagicMock()
    mock_result.tone_profiles = [
        ExtractedToneProfile(
            name="Gothic Horror",
            description="Dark and oppressive atmosphere",
            instruction="Use visceral descriptions and emphasize shadows.",
            trigger_tags=["vampire", "night"],
            confidence=0.9,
        )
    ]
    analyzer._call_module = AsyncMock(return_value=mock_result)

    sections = [
        SectionDigest(
            section_path="Mood",
            text="It is a dark and stormy night.",
            min_page=1,
            min_chunk_index=1,
        )
    ]
    results = await analyzer._extract_tone_profiles(sections, "Test Source")

    assert len(results) == 1
    assert results[0].name == "Gothic Horror"
    analyzer._call_module.assert_called_once()


@pytest.mark.asyncio
async def test_extract_character_profiles_success():
    analyzer = Analyzer()
    mock_result = MagicMock()
    mock_result.character_profiles = [
        ExtractedCharacterProfile(
            name="The Brooding Prince",
            traits={"stoic": 0.9, "melancholy": 0.8},
            values=["Honor", "Legacy"],
            fears=["Failure"],
            desires=["Redemption"],
            speech_style="Formal and terse",
            mannerisms=["Fidgeting with signet ring"],
            is_template=False,
            confidence=0.95,
        )
    ]
    analyzer._call_module = AsyncMock(return_value=mock_result)

    sections = [
        SectionDigest(
            section_path="NPCs", text="Prince Valerius sits alone.", min_page=10, min_chunk_index=5
        )
    ]
    results = await analyzer._extract_character_profiles(sections, "Test Source")

    assert len(results) == 1
    assert results[0].name == "The Brooding Prince"
    assert results[0].traits["stoic"] == 0.9


@pytest.mark.asyncio
async def test_extract_generation_templates_success():
    analyzer = Analyzer()
    mock_result = MagicMock()
    mock_result.generation_templates = [
        ExtractedGenerationTemplate(
            name="Brujah Enforcer",
            archetype_name="Brujah",
            stat_block_name="Street Thug",
            profile_name="Angry Rebel",
            random_table_names=["Biker Gear", "Thug Names"],
            confidence=0.85,
        )
    ]
    analyzer._call_module = AsyncMock(return_value=mock_result)

    sections = [
        SectionDigest(
            section_path="ST Advice",
            text="Typical Brujah enforcers use thug stats.",
            min_page=100,
            min_chunk_index=1,
        )
    ]
    results = await analyzer._extract_generation_templates(
        sections, "Test Source", known_entities="Archetypes: Brujah"
    )

    assert len(results) == 1
    assert results[0].name == "Brujah Enforcer"
    assert "Biker Gear" in results[0].random_table_names


class TestExtractedCharacterProfile:
    def test_character_profile_creation(self):
        """ExtractedCharacterProfile should be created with required fields."""
        profile = ExtractedCharacterProfile(
            name="Test Character",
            traits={"brave": 0.9},
            values=["Honor"],
            fears=["Death"],
            desires=["Glory"],
            speech_style="Bold",
            mannerisms=["Strides confidently"],
            is_template=False,
            confidence=0.95,
        )
        assert profile.name == "Test Character"
        assert profile.traits["brave"] == 0.9

    def test_character_profile_defaults(self):
        """ExtractedCharacterProfile should have sensible defaults."""
        profile = ExtractedCharacterProfile(
            name="Simple NPC",
            traits={},
            values=[],
            fears=[],
            desires=[],
            speech_style="",
            mannerisms=[],
            is_template=True,
            confidence=0.5,
        )
        assert profile.is_template is True

    def test_character_profile_with_empty_traits(self):
        """ExtractedCharacterProfile should handle empty traits."""
        profile = ExtractedCharacterProfile(
            name="Empty NPC",
            traits={},
            values=[],
            fears=[],
            desires=[],
            speech_style="Neutral",
            mannerisms=[],
            is_template=False,
            confidence=0.5,
        )
        assert profile.traits == {}
        assert profile.confidence == 0.5


class TestExtractedToneProfile:
    def test_tone_profile_creation(self):
        """ExtractedToneProfile should be created with required fields."""
        tone = ExtractedToneProfile(
            name="Gothic",
            description="Dark atmosphere",
            instruction="Use shadows and dread.",
            trigger_tags=["night", "castle"],
            confidence=0.9,
        )
        assert tone.name == "Gothic"
        assert "night" in tone.trigger_tags

    def test_tone_profile_defaults(self):
        """ExtractedToneProfile should handle missing optional fields."""
        tone = ExtractedToneProfile(
            name="Minimal",
            description="Basic tone",
            instruction="Be basic.",
            trigger_tags=[],
            confidence=0.5,
        )
        assert tone.trigger_tags == []
        assert tone.confidence == 0.5


class TestExtractedGenerationTemplate:
    def test_generation_template_creation(self):
        """ExtractedGenerationTemplate should be created with required fields."""
        template = ExtractedGenerationTemplate(
            name="Warrior",
            archetype_name="Fighter",
            stat_block_name="Soldier",
            profile_name="Military",
            random_table_names=["Weapons", "Armor"],
            confidence=0.85,
        )
        assert template.name == "Warrior"
        assert "Weapons" in template.random_table_names

    def test_generation_template_empty_tables(self):
        """ExtractedGenerationTemplate should handle empty random tables."""
        template = ExtractedGenerationTemplate(
            name="Empty Template",
            archetype_name="None",
            stat_block_name="Basic",
            profile_name="Generic",
            random_table_names=[],
            confidence=0.5,
        )
        assert template.random_table_names == []
