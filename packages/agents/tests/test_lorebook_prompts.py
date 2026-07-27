"""
Tests for the lorebook DSPy prompt modules.

Covers:
- LorebookKeywordExtractor.forward: keyword extraction with mocked DSPy
- LorebookIngestionModule.forward: entry draft generation with mocked DSPy
- Fallback paths: invalid JSON, empty content, missing fields
- Signature structure: InputField/OutputField definitions

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_lorebook_prompts.py -v
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# Signature structure tests
# =============================================================================


class TestLorebookSignatures:
    def test_keyword_extraction_signature_has_input_field(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractionSignature

        sig = LorebookKeywordExtractionSignature
        assert "content" in sig.input_fields

    def test_keyword_extraction_signature_has_output_field(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractionSignature

        sig = LorebookKeywordExtractionSignature
        assert "keywords" in sig.output_fields

    def test_ingestion_signature_has_input_fields(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionSignature

        sig = LorebookIngestionSignature
        assert "chunk" in sig.input_fields
        assert "existing_keywords" in sig.input_fields
        assert "tags_str" in sig.input_fields

    def test_ingestion_signature_has_output_field(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionSignature

        sig = LorebookIngestionSignature
        assert "entry" in sig.output_fields


# =============================================================================
# LorebookKeywordExtractor — forward with mocked DSPy
# =============================================================================


class TestLorebookKeywordExtractor:
    def test_extracts_keywords_from_valid_json(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords='["dragon", "mithril", "smaug"]'))

        result = extractor.forward(content="The dragon Smaug hoards mithril.")

        assert result == ["dragon", "mithril", "smaug"]

    def test_lowercases_keywords(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords='["Dragon", "MITHRIL", "Smaug"]'))

        result = extractor.forward(content="The dragon Smaug hoards mithril.")

        assert all(k == k.lower() for k in result)

    def test_strips_whitespace(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords='[" dragon ", " mithril"]'))

        result = extractor.forward(content="The dragon hoards mithril.")

        assert result == ["dragon", "mithril"]

    def test_limits_to_8_keywords(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords=json.dumps([f"kw{i}" for i in range(15)])))

        result = extractor.forward(content="Some content")

        assert len(result) <= 8

    def test_falls_back_to_capitalized_words_on_invalid_json(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords="not valid json"))

        result = extractor.forward(content="The Dragon hoards Mithril in the Mountain.")

        # Should extract capitalized words as fallback
        assert "dragon" in result
        assert "mithril" in result
        assert "mountain" in result

    def test_falls_back_on_non_list_json(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords='{"not": "a list"}'))

        result = extractor.forward(content="The Dragon hoards Mithril.")

        # Should use fallback
        assert "dragon" in result

    def test_falls_back_on_list_with_non_strings(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords='["dragon", 42, null]'))

        result = extractor.forward(content="The Dragon hoards Mithril.")

        # Should use fallback since not all items are strings
        assert "dragon" in result

    def test_fallback_filters_common_words(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords="not json at all"))

        result = extractor.forward(content="The Dragon and the But for the His.")

        # Common words should be filtered out
        assert "the" not in result
        assert "and" not in result
        assert "but" not in result
        assert "for" not in result
        assert "his" not in result
        assert "dragon" in result

    def test_fallback_deduplicates(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords="not json"))

        result = extractor.forward(content="Dragon Dragon Dragon Mithril Mithril")

        # Should deduplicate
        assert result.count("dragon") == 1
        assert result.count("mithril") == 1

    def test_fallback_limits_to_8(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords="not json"))

        result = extractor.forward(content="Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota Kappa")

        assert len(result) <= 8

    def test_empty_content_returns_empty_list(self):
        from monitor_agents.indexer.lorebook import LorebookKeywordExtractor

        extractor = LorebookKeywordExtractor()
        extractor._extract = MagicMock(return_value=SimpleNamespace(keywords="not json"))

        result = extractor.forward(content="")

        assert result == []


# =============================================================================
# LorebookIngestionModule — forward with mocked DSPy
# =============================================================================


class TestLorebookIngestionModule:
    def test_generates_draft_from_valid_json(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionModule

        module = LorebookIngestionModule()
        entry_json = json.dumps(
            {
                "keywords": ["dragon", "smaug"],
                "content": "Smaug is a fire drake.",
                "priority": 70,
                "tags": ["combat", "fire"],
                "confidence": 0.9,
            }
        )
        module._propose = MagicMock(return_value=SimpleNamespace(entry=entry_json))

        result = module.forward(chunk="Smaug the dragon lives in the mountain.")

        assert result.keywords == ["dragon", "smaug"]
        assert result.content == "Smaug is a fire drake."
        assert result.priority == 70
        assert result.tags == ["combat", "fire"]
        assert result.confidence == 0.9

    def test_lowercases_keywords(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionModule

        module = LorebookIngestionModule()
        entry_json = json.dumps(
            {
                "keywords": ["Dragon", "SMAUG"],
                "content": "Test",
                "priority": 50,
                "tags": [],
                "confidence": 0.8,
            }
        )
        module._propose = MagicMock(return_value=SimpleNamespace(entry=entry_json))

        result = module.forward(chunk="Test chunk")

        assert all(k == k.lower() for k in result.keywords)

    def test_uses_priority_hint_as_default(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionModule

        module = LorebookIngestionModule()
        entry_json = json.dumps(
            {
                "keywords": ["test"],
                "content": "Test content",
                # No priority field
                "tags": [],
                "confidence": 0.7,
            }
        )
        module._propose = MagicMock(return_value=SimpleNamespace(entry=entry_json))

        result = module.forward(chunk="Test", priority_hint=42)

        assert result.priority == 42

    def test_uses_default_confidence_when_missing(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionModule

        module = LorebookIngestionModule()
        entry_json = json.dumps(
            {
                "keywords": ["test"],
                "content": "Test",
                "priority": 50,
                "tags": [],
                # No confidence field
            }
        )
        module._propose = MagicMock(return_value=SimpleNamespace(entry=entry_json))

        result = module.forward(chunk="Test")

        assert result.confidence == 0.5

    def test_falls_back_on_invalid_json(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionModule

        module = LorebookIngestionModule()
        module._propose = MagicMock(return_value=SimpleNamespace(entry="not valid json"))

        result = module.forward(chunk="Some chunk of lore text.", priority_hint=60, tags=["dungeon"])

        # Fallback: empty keywords, truncated content, low confidence
        assert result.keywords == []
        assert result.content == "Some chunk of lore text."[:500]
        assert result.priority == 60
        assert result.tags == ["dungeon"]
        assert result.confidence == 0.3

    def test_falls_back_on_missing_fields(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionModule

        module = LorebookIngestionModule()
        module._propose = MagicMock(return_value=SimpleNamespace(entry='{"incomplete": true}'))

        result = module.forward(chunk="Chunk text", priority_hint=55)

        assert result.keywords == []
        assert result.content == ""
        assert result.priority == 55
        assert result.confidence == 0.5

    def test_passes_existing_keywords_to_dspy(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionModule

        module = LorebookIngestionModule()
        entry_json = json.dumps(
            {
                "keywords": ["new"],
                "content": "Test",
                "priority": 50,
                "tags": [],
                "confidence": 0.8,
            }
        )
        module._propose = MagicMock(return_value=SimpleNamespace(entry=entry_json))

        module.forward(
            chunk="Test chunk",
            existing_keywords=["dragon", "smaug"],
            tags=["combat"],
        )

        # Verify DSPy was called with the right args
        call_kwargs = module._propose.call_args.kwargs
        assert call_kwargs["existing_keywords"] == "dragon, smaug"
        assert call_kwargs["tags_str"] == "combat"

    def test_handles_empty_existing_keywords(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionModule

        module = LorebookIngestionModule()
        entry_json = json.dumps(
            {
                "keywords": ["test"],
                "content": "Test",
                "priority": 50,
                "tags": [],
                "confidence": 0.8,
            }
        )
        module._propose = MagicMock(return_value=SimpleNamespace(entry=entry_json))

        module.forward(chunk="Test", existing_keywords=None, tags=None)

        call_kwargs = module._propose.call_args.kwargs
        assert call_kwargs["existing_keywords"] == ""
        assert call_kwargs["tags_str"] == ""

    def test_truncates_content_in_fallback(self):
        from monitor_agents.indexer.lorebook import LorebookIngestionModule

        module = LorebookIngestionModule()
        module._propose = MagicMock(return_value=SimpleNamespace(entry="not json"))

        long_chunk = "A" * 1000
        result = module.forward(chunk=long_chunk)

        assert len(result.content) <= 500
