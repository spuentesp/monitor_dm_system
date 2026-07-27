"""
Tests for monitor_data.tools.perception_tools — fast entity detection.

All tests run against the regex backend (zero dependencies).
No external model or database is required.

Note
----
Intent classification used to live here; it was later removed entirely —
the GMAgent LLM emits ``intent_type`` directly now.
"""

from __future__ import annotations

import pytest

from monitor_data.schemas.perception import (
    DetectedEntity,
    DetectedEntityType,
    DetectionBackend,
    PerceptionInput,
    PerceptionOutput,
)
from monitor_data.tools.perception_tools import (
    PerceptionPipeline,
    RegexBackend,
    RegexPerceptionBackend,
    _classify_entity_type,
    _deduplicate_overlaps,
)

# ============================================================================
# REGEX BACKEND — ENTITY DETECTION
# ============================================================================


class TestRegexEntityDetection:
    """Test RegexPerceptionBackend.detect_entities()."""

    def setup_method(self) -> None:
        self.backend = RegexPerceptionBackend()

    def test_detects_quoted_entity(self) -> None:
        entities = self.backend.detect_entities('I walk into the "Red Dragon Inn"')
        names = [e.text for e in entities]
        assert "Red Dragon Inn" in names

    def test_detects_capitalized_multiword(self) -> None:
        entities = self.backend.detect_entities("I approach the Dark Lord")
        names = [e.text for e in entities]
        assert "Dark Lord" in names

    def test_detects_spells(self) -> None:
        entities = self.backend.detect_entities("I cast Fireball at the goblin")
        spells = [e for e in entities if e.entity_type == DetectedEntityType.SPELL]
        assert len(spells) >= 1
        assert spells[0].text == "Fireball"

    def test_spell_lightning_bolt(self) -> None:
        entities = self.backend.detect_entities("I cast Lightning Bolt")
        spells = [e for e in entities if e.entity_type == DetectedEntityType.SPELL]
        assert any(s.text == "Lightning Bolt" for s in spells)

    def test_detects_multiple_entities(self) -> None:
        entities = self.backend.detect_entities('I attack the "Shadow King" with my Flame Sword in the Dark Tower')
        names = [e.text for e in entities]
        assert "Shadow King" in names
        assert len(entities) >= 2  # at least Shadow King + something else

    def test_skips_common_words(self) -> None:
        entities = self.backend.detect_entities("I go to the store")
        names = [e.text for e in entities]
        assert "I" not in names

    def test_empty_input(self) -> None:
        entities = self.backend.detect_entities("")
        assert entities == []

    def test_entity_has_correct_fields(self) -> None:
        entities = self.backend.detect_entities('I see "Gandalf"')
        assert len(entities) >= 1
        e = entities[0]
        assert e.text == "Gandalf"
        assert e.start >= 0
        assert e.end > e.start
        assert 0.0 <= e.confidence <= 1.0
        assert isinstance(e.entity_type, DetectedEntityType)

    def test_quoted_entity_higher_confidence(self) -> None:
        entities = self.backend.detect_entities('I see "Gandalf"')
        quoted = [e for e in entities if e.text == "Gandalf"]
        assert len(quoted) >= 1
        assert quoted[0].confidence >= 0.9

    def test_detects_entity_with_location_hint(self) -> None:
        entities = self.backend.detect_entities("We enter the Shadowfell Forest")
        locations = [e for e in entities if e.entity_type == DetectedEntityType.LOCATION]
        assert len(locations) >= 1

    def test_detects_entity_with_object_hint(self) -> None:
        entities = self.backend.detect_entities("I equip my Dragonslayer Sword")
        objects = [e for e in entities if e.entity_type == DetectedEntityType.OBJECT]
        assert any("Sword" in e.text or "Dragonslayer" in e.text for e in objects) or len(objects) >= 1


# ============================================================================
# ENTITY TYPE CLASSIFICATION
# ============================================================================


class TestEntityTypeClassification:
    """Test _classify_entity_type() heuristic."""

    def test_character_hint(self) -> None:
        result = _classify_entity_type("Gandalf", "the wizard Gandalf")
        assert result == DetectedEntityType.CHARACTER

    def test_location_hint(self) -> None:
        result = _classify_entity_type("Moria", "the city of Moria")
        assert result == DetectedEntityType.LOCATION

    def test_object_hint(self) -> None:
        result = _classify_entity_type("Sting", "the sword Sting")
        assert result == DetectedEntityType.OBJECT

    def test_faction_hint(self) -> None:
        result = _classify_entity_type("Night Watch", "the Night Watch guild")
        assert result == DetectedEntityType.FACTION

    def test_spell_pattern(self) -> None:
        result = _classify_entity_type("Fireball", "I cast Fireball")
        assert result == DetectedEntityType.SPELL

    def test_default_character_for_proper_noun(self) -> None:
        result = _classify_entity_type("Zephyr", "I see Zephyr")
        assert result == DetectedEntityType.CHARACTER


# ============================================================================
# OVERLAP DEDUPLICATION
# ============================================================================


class TestDeduplication:
    """Test _deduplicate_overlaps()."""

    def test_no_overlaps(self) -> None:
        entities = [
            DetectedEntity(text="A", entity_type=DetectedEntityType.CHARACTER, start=0, end=1, confidence=0.8),
            DetectedEntity(text="B", entity_type=DetectedEntityType.LOCATION, start=5, end=6, confidence=0.8),
        ]
        result = _deduplicate_overlaps(entities)
        assert len(result) == 2

    def test_overlapping_keeps_higher_confidence(self) -> None:
        entities = [
            DetectedEntity(
                text="Dragon",
                entity_type=DetectedEntityType.CHARACTER,
                start=0,
                end=6,
                confidence=0.7,
            ),
            DetectedEntity(
                text="Dragon",
                entity_type=DetectedEntityType.CHARACTER,
                start=0,
                end=6,
                confidence=0.95,
            ),
        ]
        result = _deduplicate_overlaps(entities)
        assert len(result) == 1
        assert result[0].confidence == 0.95

    def test_empty_list(self) -> None:
        assert _deduplicate_overlaps([]) == []


# ============================================================================
# PERCEPTION PIPELINE (async)
# ============================================================================


class TestPerceptionPipeline:
    """Test PerceptionPipeline full async flow (entity detection only)."""

    @pytest.mark.asyncio
    async def test_pipeline_detect(self) -> None:
        pipe = PerceptionPipeline()
        result = await pipe.detect("I attack the Dragon with my Flame Sword")

        assert isinstance(result, PerceptionOutput)
        assert result.backend == DetectionBackend.REGEX
        assert len(result.entities) >= 1
        assert result.processing_time_ms >= 0
        assert result.processing_time_ms < 100  # should be fast

    @pytest.mark.asyncio
    async def test_pipeline_novelty_detection(self) -> None:
        pipe = PerceptionPipeline(known_entities=["dragon"])
        result = await pipe.detect("I attack the Dragon with my Flame Sword")

        # Dragon is known, Flame Sword is not
        novel_names = [e.text for e in result.novel_entities]
        assert not any("Dragon" in n for n in novel_names) or len(result.novel_entities) < len(result.entities)

    @pytest.mark.asyncio
    async def test_pipeline_no_known_entities(self) -> None:
        pipe = PerceptionPipeline()
        result = await pipe.detect("I attack the Dragon")
        assert len(result.novel_entities) == len(result.entities)

    @pytest.mark.asyncio
    async def test_pipeline_with_structured_input(self) -> None:
        pipe = PerceptionPipeline()
        inp = PerceptionInput(
            text="I talk to the Merchant",
            known_entities=["merchant"],
        )
        result = await pipe.detect_with_input(inp)

        assert isinstance(result, PerceptionOutput)
        known_entities = [e for e in result.entities if e.is_known is True]
        assert len(known_entities) >= 1

    @pytest.mark.asyncio
    async def test_pipeline_invalid_backend(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            PerceptionPipeline(backend="nonexistent")

    @pytest.mark.asyncio
    async def test_pipeline_backend_name_property(self) -> None:
        pipe = PerceptionPipeline()
        assert pipe.backend_name == DetectionBackend.REGEX

    @pytest.mark.asyncio
    async def test_pipeline_has_no_intent_field(self) -> None:
        """PerceptionOutput no longer carries intent (moved to agents layer)."""
        pipe = PerceptionPipeline()
        result = await pipe.detect("I attack the Dragon")
        assert not hasattr(result, "intent") or "intent" not in result.model_dump()


# ============================================================================
# REGEX BACKEND (async wrapper)
# ============================================================================


class TestRegexBackendAsync:
    """Test RegexBackend async wrapper."""

    @pytest.mark.asyncio
    async def test_async_detect(self) -> None:
        backend = RegexBackend()
        entities = await backend.detect_entities("I attack the Dragon")
        assert len(entities) >= 1


# ============================================================================
# PERFORMANCE BUDGET
# ============================================================================


class TestPerformanceBudget:
    """Verify that regex perception stays within time budget."""

    @pytest.mark.asyncio
    async def test_regex_under_50ms(self) -> None:
        pipe = PerceptionPipeline()
        result = await pipe.detect(
            "I attack the Shadow King with my Flame Sword in the Dark Tower "
            "while casting Fireball at the guards of the Night Watch guild"
        )
        assert result.processing_time_ms < 50, f"Regex backend took {result.processing_time_ms:.1f}ms (budget: 50ms)"

    @pytest.mark.asyncio
    async def test_batch_100_inputs_under_500ms(self) -> None:
        import time

        pipe = PerceptionPipeline()
        inputs = [
            "I attack the Dragon with my Flame Sword",
            "I search the room for hidden doors",
            "I tell the guard that I am a traveler",
            "(( wait, I meant to go left ))",
            "I examine the ancient tome in the library",
        ] * 20

        t0 = time.perf_counter()
        for text in inputs:
            await pipe.detect(text)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 500, f"100 inputs took {elapsed_ms:.1f}ms (budget: 500ms)"
