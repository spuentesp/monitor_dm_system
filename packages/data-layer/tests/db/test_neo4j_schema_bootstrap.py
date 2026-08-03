"""Tests that the Neo4j schema bootstrap creates the right constraints.

Sub-plan 1 of docs/superpowers/plans/2026-08-02-monitordm-coverage-and-shape.md.
"""
from __future__ import annotations

from monitor_data.db.neo4j import _SCHEMA_BOOTSTRAP_QUERIES


def test_bootstrap_creates_entity_label_constraint():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "CONSTRAINT" in body.upper()
    assert "Entity" in body


def test_bootstrap_includes_knowledge_tree_label():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "KnowledgeTree" in body


def test_bootstrap_includes_world_label_for_multiverse_hierarchy():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "World" in body


def test_bootstrap_includes_region_label():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "Region" in body


def test_bootstrap_includes_place_label():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "Place" in body


def test_bootstrap_includes_group_label():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "Group" in body


def test_bootstrap_includes_structure_label():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "Structure" in body


def test_bootstrap_includes_compound_index_on_entity_sub_type():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    # A useful query is "find all group entities in this universe" —
    # a compound index on (universe_id, group_type) makes that fast.
    assert "group_type" in body


def test_bootstrap_includes_compound_index_on_entity_place_type():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "place_type" in body
