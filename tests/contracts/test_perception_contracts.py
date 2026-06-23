"""
Contract tests for Perception schemas (Phase 1 fast-path routing).

Covers:
- DetectedEntityType enum: 7 entity types detected
- DetectionBackend enum: regex, spacy, gliner
- IntentType enum: 8 intent types
- DetectedEntity: single detection
- PerceptionInput: input to perception layer
- PerceptionOutput: full pipeline result

Use Cases: SYS-2 (Perception fast-path), Phase 1
"""

from __future__ import annotations

import pytest
from typing import List, Dict

from monitor_data.schemas.perception import (
    DetectedEntityType,
    DetectionBackend,
    IntentType,
    DetectedEntity,
    PerceptionInput,
    PerceptionOutput,
)


# =============================================================================
# Enums
# =============================================================================


class TestDetectedEntityTypeEnum:
    def test_all_values(self):
        assert DetectedEntityType.CHARACTER.value == "character"
        assert DetectedEntityType.LOCATION.value == "location"
        assert DetectedEntityType.OBJECT.value == "object"
        assert DetectedEntityType.FACTION.value == "faction"
        assert DetectedEntityType.SPELL.value == "spell"
        assert DetectedEntityType.ACTION.value == "action"
        assert DetectedEntityType.CONCEPT.value == "concept"


class TestDetectionBackendEnum:
    def test_all_values(self):
        assert DetectionBackend.REGEX.value == "regex"
        assert DetectionBackend.SPACY.value == "spacy"
        assert DetectionBackend.GLINER.value == "gliner"


class TestIntentTypeEnum:
    def test_all_values(self):
        assert IntentType.COMBAT.value == "combat"
        assert IntentType.EXPLORATION.value == "exploration"
        assert IntentType.DIALOGUE.value == "dialogue"
        assert IntentType.INVESTIGATION.value == "investigation"
        assert IntentType.SOCIAL.value == "social"
        assert IntentType.OOC.value == "ooc"
        assert IntentType.NARRATION.value == "narration"
        assert IntentType.UNKNOWN.value == "unknown"


# =============================================================================
# DetectedEntity
# =============================================================================


class TestDetectedEntity:
    def test_minimal(self):
        e = DetectedEntity(
            text="Gandalf",
            entity_type=DetectedEntityType.CHARACTER,
            start=0,
            end=7,
        )
        assert e.text == "Gandalf"
        assert e.start == 0
        assert e.end == 7
        assert e.confidence == 1.0  # default for regex
        assert e.is_known is None  # default

    def test_with_confidence(self):
        e = DetectedEntity(
            text="Rivendell",
            entity_type=DetectedEntityType.LOCATION,
            start=10,
            end=19,
            confidence=0.85,
        )
        assert e.confidence == 0.85

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            DetectedEntity(
                text="X", entity_type=DetectedEntityType.OBJECT, start=0, end=1,
                confidence=1.5,
            )
        with pytest.raises(Exception):
            DetectedEntity(
                text="X", entity_type=DetectedEntityType.OBJECT, start=0, end=1,
                confidence=-0.1,
            )

    def test_with_metadata(self):
        e = DetectedEntity(
            text="Mithrandir",
            entity_type=DetectedEntityType.CHARACTER,
            start=5,
            end=15,
            is_known=True,
            metadata={"source": "capitalized_pattern", "alias": "Gandalf"},
        )
        assert e.is_known is True
        assert e.metadata["alias"] == "Gandalf"


# =============================================================================
# PerceptionInput
# =============================================================================


class TestPerceptionInput:
    def test_minimal(self):
        inp = PerceptionInput(text="I attack the orc.")
        assert inp.text == "I attack the orc."
        assert inp.known_entities is None
        assert inp.session_id is None

    def test_with_known_entities(self):
        inp = PerceptionInput(
            text="Gandalf casts a spell.",
            known_entities=["Gandalf", "Frodo"],
            session_id="sess-1",
        )
        assert "Gandalf" in inp.known_entities
        assert inp.session_id == "sess-1"

    def test_empty_text_fails(self):
        with pytest.raises(Exception):
            PerceptionInput(text="")


# =============================================================================
# PerceptionOutput
# =============================================================================


class TestPerceptionOutput:
    def test_empty(self):
        out = PerceptionOutput()
        assert out.entities == []
        assert out.intent == IntentType.UNKNOWN
        assert out.intent_confidence == 0.0
        assert out.novel_entities == []
        assert out.processing_time_ms == 0.0
        assert out.backend == DetectionBackend.REGEX

    def test_with_entities(self):
        entities = [
            DetectedEntity(
                text="Gandalf", entity_type=DetectedEntityType.CHARACTER, start=0, end=7
            ),
            DetectedEntity(
                text="sword", entity_type=DetectedEntityType.OBJECT, start=20, end=25
            ),
        ]
        out = PerceptionOutput(
            entities=entities,
            intent=IntentType.COMBAT,
            intent_confidence=0.92,
            processing_time_ms=15.4,
        )
        assert len(out.entities) == 2
        assert out.intent == IntentType.COMBAT
        assert out.intent_confidence == 0.92

    def test_novel_entities(self):
        known = DetectedEntity(
            text="Frodo", entity_type=DetectedEntityType.CHARACTER, start=0, end=5, is_known=True
        )
        novel = DetectedEntity(
            text="Smeagol",
            entity_type=DetectedEntityType.CHARACTER,
            start=20,
            end=27,
            is_known=False,
        )
        out = PerceptionOutput(
            entities=[known, novel],
            novel_entities=[novel],
        )
        assert len(out.novel_entities) == 1
        assert out.novel_entities[0].is_known is False

    def test_backend_selection(self):
        out = PerceptionOutput(backend=DetectionBackend.SPACY)
        assert out.backend == DetectionBackend.SPACY

    def test_intent_confidence_bounds(self):
        with pytest.raises(Exception):
            PerceptionOutput(intent_confidence=2.0)
        with pytest.raises(Exception):
            PerceptionOutput(intent_confidence=-0.5)
