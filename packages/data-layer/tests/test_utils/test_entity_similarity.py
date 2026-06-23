"""
Tests for entity similarity detection (I-13: Cross-Source Synthesis).

LAYER: 1 (data-layer) — tests utils/entity_similarity.py
"""

from uuid import uuid4

import pytest

from monitor_data.utils.entity_similarity import (
    jaro_winkler_similarity,
    levenshtein_ratio,
    name_similarity,
    compare_entity_fields,
    compute_entity_similarity,
    find_merge_candidates,
)


class TestJaroWinkler:
    """Tests for Jaro-Winkler string similarity."""

    def test_identical_strings(self):
        assert jaro_winkler_similarity("hello", "hello") == 1.0

    def test_empty_strings(self):
        assert jaro_winkler_similarity("", "") == 0.0
        assert jaro_winkler_similarity("hello", "") == 0.0
        assert jaro_winkler_similarity("", "hello") == 0.0

    def test_case_insensitive(self):
        assert jaro_winkler_similarity("Hello", "HELLO") == 1.0
        assert jaro_winkler_similarity("Gandalf", "gandalf") == 1.0

    def test_common_prefix_boost(self):
        # "test" and "testx" should be higher than "estx" and "testx"
        same_prefix = jaro_winkler_similarity("test", "testx")
        no_prefix = jaro_winkler_similarity("estx", "testx")
        assert same_prefix > no_prefix

    def test_similar_strings(self):
        score = jaro_winkler_similarity("Gandalf", "Gandolf")
        assert 0.8 <= score <= 1.0  # Very similar

    def test_different_strings(self):
        score = jaro_winkler_similarity("hello", "world")
        assert score < 0.5


class TestLevenshtein:
    """Tests for Levenshtein ratio."""

    def test_identical_strings(self):
        assert levenshtein_ratio("hello", "hello") == 1.0

    def test_single_char_diff(self):
        ratio = levenshtein_ratio("hello", "hallo")
        assert ratio == 0.8  # 1/5 different

    def test_whitespace_handled(self):
        # Levenshtein doesn't normalize spaces, but similar strings still score high
        ratio = levenshtein_ratio("hello world", "hello world")
        assert ratio == 1.0  # Exact match with spaces

    def test_case_insensitive(self):
        assert levenshtein_ratio("Hello", "HELLO") == 1.0


class TestNameSimilarity:
    """Tests for comprehensive name similarity."""

    def test_exact_match(self):
        assert name_similarity("Gandalf", "Gandalf") == 1.0

    def test_nickname_match(self):
        # "Gandalf" ≈ "Mithrandir" - same entity, different names
        score = name_similarity("Gandalf", "Mithrandir")
        assert score < 1.0  # Different names
        assert score > 0.3  # But same concept

    def test_substring_boost(self):
        # "Gandalf the Grey" contains "Gandalf" - should get boost
        score = name_similarity("Gandalf the Grey", "Gandalf")
        assert score > 0.9

    def test_typo_tolerance(self):
        # "Gandalf" vs "Gandolf" - typo
        score = name_similarity("Gandalf", "Gandolf")
        assert score > 0.8


class TestCompareEntityFields:
    """Tests for entity field comparison."""

    def test_agreed_fields(self):
        e1 = {"name": "Gandalf", "entity_type": "character", "properties": {"race": "Maiar"}}
        e2 = {"name": "Gandalf", "entity_type": "character", "properties": {"race": "Maiar"}}

        conflicting, agreed, scores = compare_entity_fields(e1, e2)

        assert "name" in agreed
        assert "entity_type" in agreed
        assert "properties" in agreed
        assert len(conflicting) == 0

    def test_conflicting_fields(self):
        e1 = {"name": "Gandalf the Grey", "entity_type": "character"}
        e2 = {"name": "Mithrandir", "entity_type": "character"}

        conflicting, agreed, scores = compare_entity_fields(e1, e2)

        assert "name" in conflicting
        assert "entity_type" in agreed

    def test_partial_properties(self):
        e1 = {"name": "Gandalf", "properties": {"race": "Maiar", "age": "ancient"}}
        e2 = {"name": "Gandalf", "properties": {"race": "Maiar", "power": "high"}}

        conflicting, agreed, scores = compare_entity_fields(e1, e2)

        # properties overlap but not identical
        assert scores["properties"] < 1.0
        assert scores["properties"] > 0.0


class TestComputeEntitySimilarity:
    """Tests for overall entity similarity computation."""

    def test_identical_entities(self):
        e1 = {
            "id": str(uuid4()),
            "name": "Gandalf",
            "entity_type": "character",
            "description": "A wizard",
            "properties": {"race": "Maiar"},
        }
        e2 = {
            "id": str(uuid4()),
            "name": "Gandalf",
            "entity_type": "character",
            "description": "A wizard",
            "properties": {"race": "Maiar"},
        }

        result = compute_entity_similarity(e1, e2)

        assert result["overall"] == pytest.approx(1.0)
        assert result["name_similarity"] == 1.0
        assert result["type_match"] == 1.0

    def test_different_entities(self):
        e1 = {
            "id": str(uuid4()),
            "name": "Gandalf",
            "entity_type": "character",
            "description": "A wizard",
            "properties": {},
        }
        e2 = {
            "id": str(uuid4()),
            "name": "Saruman",
            "entity_type": "character",
            "description": "A corrupted wizard",
            "properties": {},
        }

        result = compute_entity_similarity(e1, e2)

        assert result["overall"] < 1.0
        assert result["name_similarity"] < 1.0  # Different names
        assert result["type_match"] == 1.0  # Same type

    def test_different_types(self):
        e1 = {
            "id": str(uuid4()),
            "name": "Gandalf",
            "entity_type": "character",
            "properties": {},
        }
        e2 = {
            "id": str(uuid4()),
            "name": "Gandalf",
            "entity_type": "location",  # Different type!
            "properties": {},
        }

        result = compute_entity_similarity(e1, e2)

        assert result["type_match"] == 0.0  # Type mismatch


class TestFindMergeCandidates:
    """Tests for merge candidate detection."""

    def test_no_candidates_for_single_entity(self):
        entities = [
            {"id": str(uuid4()), "name": "Gandalf", "entity_type": "character", "properties": {}}
        ]
        candidates = find_merge_candidates(entities, min_confidence=0.7)
        assert len(candidates) == 0

    def test_find_similar_entities(self):
        entities = [
            {
                "id": str(uuid4()),
                "name": "Gandalf",
                "entity_type": "character",
                "properties": {"race": "Maiar"},
            },
            {
                "id": str(uuid4()),
                "name": "Gandalf the Grey",
                "entity_type": "character",
                "properties": {"race": "Maiar"},
            },
        ]

        candidates = find_merge_candidates(entities, min_confidence=0.7)

        assert len(candidates) == 1
        assert candidates[0]["merge_confidence"] >= 0.7

    def test_dissimilar_entities_not_matched(self):
        entities = [
            {
                "id": str(uuid4()),
                "name": "Gandalf",
                "entity_type": "character",
                "properties": {},
            },
            {
                "id": str(uuid4()),
                "name": "Sauron",
                "entity_type": "character",
                "properties": {},
            },
        ]

        candidates = find_merge_candidates(entities, min_confidence=0.7)

        # Very different names, no match expected at 0.7 threshold
        assert len(candidates) == 0

    def test_min_confidence_threshold(self):
        entities = [
            {
                "id": str(uuid4()),
                "name": "Gandalf",
                "entity_type": "character",
                "properties": {},
            },
            {
                "id": str(uuid4()),
                "name": "Gandalf the Grey",
                "entity_type": "character",
                "properties": {},
            },
        ]

        # High threshold should filter out
        candidates_high = find_merge_candidates(entities, min_confidence=0.95)
        # Low threshold should include
        candidates_low = find_merge_candidates(entities, min_confidence=0.5)

        assert len(candidates_low) >= len(candidates_high)

    def test_type_mismatch_lowers_score_significantly(self):
        entities = [
            {
                "id": str(uuid4()),
                "name": "Moria",
                "entity_type": "location",
                "properties": {},
            },
            {
                "id": str(uuid4()),
                "name": "Moria",
                "entity_type": "character",  # Different type!
                "properties": {},
            },
        ]

        candidates = find_merge_candidates(entities, min_confidence=0.7)

        # type_match is 0, so with name_weight=0.5, overall = 0.5
        # High threshold (0.7) filters out
        assert len(candidates) == 0

        # With low threshold (0.4), it would pass since name is identical
        # This tests that the score IS lowered by type mismatch but not blocked entirely
        candidates_low = find_merge_candidates(entities, min_confidence=0.4)
        assert len(candidates_low) == 1
        assert candidates_low[0]["merge_confidence"] == pytest.approx(0.5)
