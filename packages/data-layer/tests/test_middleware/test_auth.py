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
    check_authority,
    get_allowed_agents,
    require_authority,
    AuthorizationError,
    AUTHORITY_MATRIX,
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
    assert check_authority("neo4j_get_universe", "Orchestrator") is True


def test_check_authority_unknown_tool_allows_all():
    """Unknown tools default to open access."""
    assert check_authority("unknown_tool", "Narrator") is True
    assert check_authority("unknown_tool", "AnyAgent") is True


def test_check_authority_orchestrator_can_create_story():
    """Orchestrator can create stories (shared permission)."""
    assert check_authority("neo4j_create_story", "Orchestrator") is True
    assert check_authority("neo4j_create_story", "CanonKeeper") is True


def test_check_authority_narrator_cannot_create_story():
    """Narrator cannot create stories."""
    assert check_authority("neo4j_create_story", "Narrator") is False


def test_check_authority_qdrant_operations_allow_all():
    """All agents can use Qdrant operations."""
    assert check_authority("qdrant_upsert", "CanonKeeper") is True
    assert check_authority("qdrant_upsert", "Narrator") is True
    assert check_authority("qdrant_upsert", "Orchestrator") is True
    assert check_authority("qdrant_search", "CanonKeeper") is True
    assert check_authority("qdrant_search", "Narrator") is True
    assert check_authority("qdrant_delete", "CanonKeeper") is True
    assert check_authority("qdrant_delete", "Narrator") is True


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
    """Get allowed agents for tool with multiple allowed agents."""
    allowed = get_allowed_agents("neo4j_create_story")
    assert "CanonKeeper" in allowed
    assert "Orchestrator" in allowed


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
        assert (
            check_authority(op, "CanonKeeper") is True
        ), f"CanonKeeper should be able to {op}"


def test_narrator_can_only_read():
    """Narrator can only read, not write."""
    assert check_authority("neo4j_get_universe", "Narrator") is True
    assert check_authority("neo4j_list_universes", "Narrator") is True
    assert check_authority("neo4j_create_universe", "Narrator") is False
    assert check_authority("neo4j_update_universe", "Narrator") is False
    assert check_authority("neo4j_delete_universe", "Narrator") is False


def test_multiple_agents_workflow():
    """Test realistic multi-agent workflow."""
    # Orchestrator can create stories
    assert check_authority("neo4j_create_story", "Orchestrator") is True

    # Narrator can append turns
    assert check_authority("mongodb_append_turn", "Narrator") is True

    # CanonKeeper can canonize changes
    assert check_authority("neo4j_create_fact", "CanonKeeper") is True

    # Everyone can read
    assert check_authority("neo4j_get_universe", "Narrator") is True
    assert check_authority("neo4j_get_universe", "Orchestrator") is True
    assert check_authority("neo4j_get_universe", "CanonKeeper") is True
