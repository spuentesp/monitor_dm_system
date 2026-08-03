"""Tests that Qdrant collections expose payload indexes for the new sub_type vocabulary.

Sub-plan 1 of docs/superpowers/plans/2026-08-02-monitordm-coverage-and-shape.md.
"""
from __future__ import annotations

from monitor_data.db.qdrant import PAYLOAD_INDEX_CONFIGS


def test_entities_collection_indexes_sub_type():
    indexed = PAYLOAD_INDEX_CONFIGS["entities"]
    assert "sub_type" in indexed


def test_entities_collection_indexes_group_type():
    indexed = PAYLOAD_INDEX_CONFIGS["entities"]
    assert "group_type" in indexed


def test_entities_collection_indexes_place_type():
    indexed = PAYLOAD_INDEX_CONFIGS["entities"]
    assert "place_type" in indexed


def test_knowledge_collection_indexes_sub_type():
    indexed = PAYLOAD_INDEX_CONFIGS["knowledge"]
    assert "sub_type" in indexed


def test_group_type_is_keyword_schema():
    """The Qdrant schema is keyword for filtering by exact value."""
    from qdrant_client.http import models
    assert PAYLOAD_INDEX_CONFIGS["entities"]["group_type"] == models.PayloadSchemaType.KEYWORD


def test_place_type_is_keyword_schema():
    from qdrant_client.http import models
    assert PAYLOAD_INDEX_CONFIGS["entities"]["place_type"] == models.PayloadSchemaType.KEYWORD
