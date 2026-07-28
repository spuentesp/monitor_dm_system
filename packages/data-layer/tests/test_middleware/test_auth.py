"""
Unit tests for authority enforcement middleware.

Tests cover:
- check_authority
- get_allowed_agents
- require_authority
- AuthorizationError
- AUTHORITY_MATRIX
"""

import pytest

from monitor_data.middleware.auth import (
    AUTHORITY_MATRIX,
    AuthorizationError,
    check_authority,
    get_allowed_agents,
    require_authority,
)

# =============================================================================
# TESTS: check_authority
# =============================================================================


def test_check_authority_canonkeeper_can_create():
    """CanonKeeper can create universes."""
    assert check_authority("neo4j_create_universe", "CanonKeeper") is True


def test_check_authority_narrator_cannot_create():
    """Narrator cannot create universes."""
    assert check_authority("neo4j_create_universe", "Narrator") is False


def test_check_authority_anyone_can_read():
    """Any agent can read universes."""
    assert check_authority("neo4j_get_universe", "Narrator") is True
    assert check_authority("neo4j_get_universe", "CanonKeeper") is True
    assert check_authority("neo4j_get_universe", "Resolver") is True


def test_check_authority_unknown_tool_allows_all():
    """Unknown tools default to open access."""
    assert check_authority("unknown_tool", "Narrator") is True
    assert check_authority("unknown_tool", "AnyAgent") is True


def test_check_authority_only_canonkeeper_can_create_story():
    """Only CanonKeeper can create stories (Neo4j write = CanonKeeper only)."""
    assert check_authority("neo4j_create_story", "CanonKeeper") is True
    assert check_authority("neo4j_create_story", "Narrator") is False
    assert check_authority("neo4j_create_story", "Resolver") is False


def test_check_authority_narrator_cannot_create_story():
    """Narrator cannot create stories."""
    assert check_authority("neo4j_create_story", "Narrator") is False


# =============================================================================
# TESTS: get_allowed_agents
# =============================================================================


def test_get_allowed_agents_write_operation():
    """Get allowed agents for write operation."""
    allowed = get_allowed_agents("neo4j_create_universe")
    assert allowed == ["CanonKeeper"]


def test_get_allowed_agents_read_operation():
    """Get allowed agents for read operation."""
    allowed = get_allowed_agents("neo4j_get_universe")
    assert allowed == ["*"]


def test_get_allowed_agents_unknown_tool():
    """Get allowed agents for unknown tool defaults to all."""
    allowed = get_allowed_agents("unknown_tool")
    assert allowed == ["*"]


def test_get_allowed_agents_shared_permission():
    """Get allowed agents for tool with single exclusive agent."""
    allowed = get_allowed_agents("neo4j_create_story")
    assert "CanonKeeper" in allowed
    assert "Orchestrator" not in allowed


# =============================================================================
# TESTS: require_authority
# =============================================================================


def test_require_authority_authorized():
    """require_authority passes for authorized agent."""
    # Should not raise
    require_authority("neo4j_create_universe", "CanonKeeper")


def test_require_authority_unauthorized():
    """require_authority raises for unauthorized agent."""
    with pytest.raises(AuthorizationError) as exc_info:
        require_authority("neo4j_create_universe", "Narrator")

    assert "Narrator" in str(exc_info.value)
    assert "neo4j_create_universe" in str(exc_info.value)
    assert "CanonKeeper" in str(exc_info.value)


def test_require_authority_read_always_passes():
    """require_authority passes for any agent on read operations."""
    require_authority("neo4j_get_universe", "Narrator")
    require_authority("neo4j_get_universe", "AnyAgent")


# =============================================================================
# TESTS: AuthorizationError
# =============================================================================


def test_authorization_error_message():
    """AuthorizationError has correct message."""
    error = AuthorizationError("neo4j_create_universe", "Narrator", ["CanonKeeper"])

    assert error.tool_name == "neo4j_create_universe"
    assert error.agent_type == "Narrator"
    assert error.allowed_agents == ["CanonKeeper"]
    assert "Narrator" in str(error)
    assert "neo4j_create_universe" in str(error)
    assert "CanonKeeper" in str(error)


# =============================================================================
# TESTS: AUTHORITY_MATRIX completeness
# =============================================================================


def test_authority_matrix_has_universe_operations():
    """AUTHORITY_MATRIX includes all universe operations."""
    assert "neo4j_create_universe" in AUTHORITY_MATRIX
    assert "neo4j_get_universe" in AUTHORITY_MATRIX
    assert "neo4j_list_universes" in AUTHORITY_MATRIX
    assert "neo4j_update_universe" in AUTHORITY_MATRIX
    assert "neo4j_delete_universe" in AUTHORITY_MATRIX


def test_authority_matrix_universe_write_requires_canonkeeper():
    """All universe write operations require CanonKeeper."""
    write_ops = [
        "neo4j_create_universe",
        "neo4j_update_universe",
        "neo4j_delete_universe",
    ]

    for op in write_ops:
        allowed = AUTHORITY_MATRIX[op]
        assert allowed == ["CanonKeeper"], f"{op} should only allow CanonKeeper"


def test_authority_matrix_universe_read_allows_all():
    """All universe read operations allow all agents."""
    read_ops = [
        "neo4j_get_universe",
        "neo4j_list_universes",
    ]

    for op in read_ops:
        allowed = AUTHORITY_MATRIX[op]
        assert allowed == ["*"], f"{op} should allow all agents"


def test_runtime_artifact_writes_require_canonkeeper():
    """Accepted pack artifacts are activated through CanonKeeper."""
    write_ops = [
        "mongodb_create_random_table",
        "mongodb_create_entity_template",
        "mongodb_create_tone_profile",
    ]

    for op in write_ops:
        assert check_authority(op, "CanonKeeper") is True
        assert check_authority(op, "Narrator") is False


# =============================================================================
# TESTS: Integration scenarios
# =============================================================================


def test_canonkeeper_can_do_everything():
    """CanonKeeper can perform all universe operations."""
    operations = [
        "neo4j_create_universe",
        "neo4j_get_universe",
        "neo4j_list_universes",
        "neo4j_update_universe",
        "neo4j_delete_universe",
    ]

    for op in operations:
        assert check_authority(op, "CanonKeeper") is True, f"CanonKeeper should be able to {op}"


def test_narrator_can_only_read():
    """Narrator can only read, not write."""
    assert check_authority("neo4j_get_universe", "Narrator") is True
    assert check_authority("neo4j_list_universes", "Narrator") is True
    assert check_authority("neo4j_create_universe", "Narrator") is False
    assert check_authority("neo4j_update_universe", "Narrator") is False
    assert check_authority("neo4j_delete_universe", "Narrator") is False


def test_multiple_agents_workflow():
    """Test realistic multi-agent workflow."""
    # CanonKeeper creates stories (exclusive Neo4j writer)
    assert check_authority("neo4j_create_story", "CanonKeeper") is True
    assert check_authority("neo4j_create_story", "Narrator") is False

    # Narrator can append turns
    assert check_authority("mongodb_append_turn", "Narrator") is True

    # CanonKeeper can canonize changes
    assert check_authority("neo4j_create_fact", "CanonKeeper") is True

    # Everyone can read
    assert check_authority("neo4j_get_universe", "Narrator") is True
    assert check_authority("neo4j_get_universe", "Resolver") is True
    assert check_authority("neo4j_get_universe", "CanonKeeper") is True


# =============================================================================
# TESTS: AUTHORITY_MATRIX ↔ neo4j_tools parity
# =============================================================================


def test_authority_matrix_matches_actual_neo4j_tools():
    """Every neo4j_* tool exported from neo4j_tools must be in AUTHORITY_MATRIX
    (writes restricted, reads open), and every neo4j_* matrix entry must
    reference a real tool.
    """
    from monitor_data.tools import neo4j_tools

    exported = sorted(
        n for n in dir(neo4j_tools)
        if not n.startswith("_") and n.startswith("neo4j_")
    )
    neo4j_matrix_entries = [t for t in AUTHORITY_MATRIX if t.startswith("neo4j_")]

    missing_from_matrix = [t for t in exported if t not in AUTHORITY_MATRIX]
    assert not missing_from_matrix, (
        f"Tools exported from neo4j_tools but missing from AUTHORITY_MATRIX: "
        f"{missing_from_matrix}"
    )

    stale_matrix_entries = [t for t in neo4j_matrix_entries if t not in set(exported)]
    assert not stale_matrix_entries, (
        f"AUTHORITY_MATRIX has neo4j entries with no matching exported tool: "
        f"{stale_matrix_entries}"
    )


def test_authority_matrix_writes_require_canonkeeper():
    """Every neo4j write verb (create/update/delete/save/set/link/merge/split/
    batch/ensure/tick/fork/add/remove) registered in the matrix must require
    CanonKeeper (with explicit sharing for create_source, delete_source,
    fork_universe, link_to_archetype, create_character_relationship,
    tick_agendas).
    """
    write_verbs = (
        "create", "update", "delete", "save", "merge", "split",
        "batch", "ensure", "tick", "fork", "add", "remove",
    )
    # Tools with names ending in _set or _state_tags don't match canonical
    # write-verb patterns; we still verify they require CanonKeeper separately
    # via state_tags check below.
    shared_with_others = {
        "neo4j_create_source",
        "neo4j_delete_source",
        "neo4j_fork_universe",
        "neo4j_link_to_archetype",
        "neo4j_create_character_relationship",
        "neo4j_tick_agendas",
    }

    for tool_name, allowed in AUTHORITY_MATRIX.items():
        if not tool_name.startswith("neo4j_"):
            continue
        is_write = any(f"_{v}_" in tool_name or tool_name.endswith(f"_{v}") for v in write_verbs)
        if not is_write:
            continue
        if tool_name in shared_with_others:
            assert "CanonKeeper" in allowed, f"{tool_name} must allow CanonKeeper"
        else:
            assert allowed == ["CanonKeeper"], (
                f"{tool_name} should only allow CanonKeeper, got {allowed}"
            )

    # _state_tags writes are CanonKeeper-only
    for tag_tool in ("neo4j_set_state_tags", "neo4j_update_state_tags"):
        if tag_tool in AUTHORITY_MATRIX:
            assert AUTHORITY_MATRIX[tag_tool] == ["CanonKeeper"], (
                f"{tag_tool} should only allow CanonKeeper"
            )
