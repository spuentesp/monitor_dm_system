import pytest
from monitor_data.invariants.canon_keeper import (
    CANON_KEEPER_WRITE_TOOLS,
    SHARED_NEO4J_WRITE_TOOLS,
    CanonKeeperExclusivity,
)
from monitor_data.tools import neo4j_tools

pytestmark = pytest.mark.unit

def test_canon_keeper_write_tools_parity():
    # Get all exported tools from neo4j_tools that start with neo4j_
    exported = [n for n in dir(neo4j_tools) if not n.startswith('_') and n.startswith('neo4j_')]
    write_verbs = ("create", "update", "delete", "set", "link", "add", "remove", "merge", "split", "fork", "ensure", "tick", "batch", "save")
    
    # Filter for functions that look like write operations
    actual_write_tools = set(n for n in exported if any(v in n for v in write_verbs) and n not in ["neo4j_get_scene_relevant_entities"])

    # Ensure every tool classified as a write tool is in one of the registries
    missing_from_registries = actual_write_tools - CANON_KEEPER_WRITE_TOOLS - SHARED_NEO4J_WRITE_TOOLS
    assert not missing_from_registries, f"Missing write tools from registries: {missing_from_registries}"

    # Ensure every tool in the registries is actually exported
    all_registry_tools = CANON_KEEPER_WRITE_TOOLS | SHARED_NEO4J_WRITE_TOOLS
    missing_from_exports = all_registry_tools - set(exported)
    assert not missing_from_exports, f"Registry contains tools not exported from neo4j_tools: {missing_from_exports}"

def test_canon_keeper_shared_isolation():
    # Ensure no overlap between exclusive and shared
    overlap = CANON_KEEPER_WRITE_TOOLS & SHARED_NEO4J_WRITE_TOOLS
    assert not overlap, f"Tools cannot be both exclusive and shared: {overlap}"

def test_canon_keeper_authorization():
    # Exclusive tools
    if CANON_KEEPER_WRITE_TOOLS:
        tool = next(iter(CANON_KEEPER_WRITE_TOOLS))
        assert CanonKeeperExclusivity.is_authorized_writer(tool, "CanonKeeper") is True
        assert CanonKeeperExclusivity.is_authorized_writer(tool, "Narrator") is False
        assert CanonKeeperExclusivity.is_authorized_writer(tool, "IngestionPipeline") is False

    # Shared tools
    if SHARED_NEO4J_WRITE_TOOLS:
        tool = next(iter(SHARED_NEO4J_WRITE_TOOLS))
        assert CanonKeeperExclusivity.is_authorized_writer(tool, "CanonKeeper") is True
        assert CanonKeeperExclusivity.is_authorized_writer(tool, "IngestionPipeline") is True
        assert CanonKeeperExclusivity.is_authorized_writer(tool, "Narrator") is False

    # Non-write tools
    assert CanonKeeperExclusivity.is_authorized_writer("neo4j_get_entity", "Narrator") is True
