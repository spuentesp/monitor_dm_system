"""
Unit tests for Neo4j axiom operations (DL-13).

Tests cover:
- neo4j_create_axiom (with and without provenance)
- neo4j_get_axiom (with provenance chain)
- neo4j_list_axioms (with filtering)
- neo4j_update_axiom
- neo4j_delete_axiom (soft-delete)
- Axiom lifecycle integration
"""

from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.axioms import (
    AxiomCreate,
    AxiomUpdate,
    AxiomFilter,
    AxiomDomain,
)
from monitor_data.schemas.base import CanonLevel, AxiomAuthority
from monitor_data.tools.neo4j_tools import (
    neo4j_create_axiom,
    neo4j_get_axiom,
    neo4j_list_axioms,
    neo4j_update_axiom,
    neo4j_delete_axiom,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def axiom_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample axiom data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "statement": "Magic requires verbal components",
        "domain": AxiomDomain.MAGIC.value,
        "confidence": 1.0,
        "canon_level": CanonLevel.CANON.value,
        "authority": AxiomAuthority.SYSTEM.value,
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def source_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample source data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "title": "Core Rulebook",
        "source_type": "rulebook",
        "canon_level": "authoritative",
    }


# =============================================================================
# TESTS: neo4j_create_axiom
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_axiom_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    axiom_data: Dict[str, Any],
):
    """Test creating an Axiom with valid parameters."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock axiom creation
    mock_neo4j_client.execute_write.return_value = [{"a": axiom_data}]

    params = AxiomCreate(
        universe_id=UUID(universe_data["id"]),
        statement="Magic requires verbal components",
        domain=AxiomDomain.MAGIC,
        confidence=1.0,
    )

    result = neo4j_create_axiom(params)

    assert result.statement == "Magic requires verbal components"
    assert result.domain == AxiomDomain.MAGIC
    assert result.confidence == 1.0
    assert result.canon_level == CanonLevel.CANON
    assert result.sources == []
    assert mock_neo4j_client.execute_read.call_count == 1
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_axiom_with_provenance(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    axiom_data: Dict[str, Any],
    source_data: Dict[str, Any],
):
    """Test creating an Axiom with source provenance."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],  # Universe verification
        [{"found_ids": [source_data["id"]]}],  # Source verification
    ]

    # Mock axiom creation
    mock_neo4j_client.execute_write.return_value = [{"a": axiom_data}]

    params = AxiomCreate(
        universe_id=UUID(universe_data["id"]),
        statement="Magic requires verbal components",
        domain=AxiomDomain.MAGIC,
        source_ids=[UUID(source_data["id"])],
    )

    result = neo4j_create_axiom(params)

    assert result.statement == "Magic requires verbal components"
    assert result.sources == []  # Sources not loaded in create response
    # Verify that execute_write was called twice (create + link)
    assert mock_neo4j_client.execute_write.call_count == 2


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_axiom_domain(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test creating axioms with each domain value."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    domains = [
        AxiomDomain.PHYSICS,
        AxiomDomain.MAGIC,
        AxiomDomain.SOCIETY,
        AxiomDomain.METAPHYSICS,
    ]

    for domain in domains:
        axiom_data = {
            "id": str(uuid4()),
            "universe_id": universe_data["id"],
            "statement": f"Test axiom for {domain.value}",
            "domain": domain.value,
            "confidence": 1.0,
            "canon_level": CanonLevel.CANON.value,
            "authority": AxiomAuthority.SYSTEM.value,
            "created_at": "2024-01-01T00:00:00",
        }
        mock_neo4j_client.execute_write.return_value = [{"a": axiom_data}]

        params = AxiomCreate(
            universe_id=UUID(universe_data["id"]),
            statement=f"Test axiom for {domain.value}",
            domain=domain,
        )

        result = neo4j_create_axiom(params)
        assert result.domain == domain


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_axiom_universe_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test creating an Axiom with nonexistent universe_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe not found
    mock_neo4j_client.execute_read.return_value = []

    params = AxiomCreate(
        universe_id=uuid4(),
        statement="Test axiom",
        domain=AxiomDomain.PHYSICS,
    )

    with pytest.raises(ValueError, match="Universe .* not found"):
        neo4j_create_axiom(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_axiom_source_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test creating an Axiom with nonexistent source_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists but source doesn't
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],  # Universe found
        [{"found_ids": []}],  # Source not found
    ]

    params = AxiomCreate(
        universe_id=UUID(universe_data["id"]),
        statement="Test axiom",
        domain=AxiomDomain.PHYSICS,
        source_ids=[uuid4()],
    )

    with pytest.raises(ValueError, match="Source IDs not found"):
        neo4j_create_axiom(params)


# =============================================================================
# TESTS: neo4j_get_axiom
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_axiom_with_provenance(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
    source_data: Dict[str, Any],
):
    """Test retrieving an Axiom with provenance chain."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom with sources
    mock_neo4j_client.execute_read.return_value = [
        {
            "a": axiom_data,
            "sources": [source_data],
        }
    ]

    result = neo4j_get_axiom(UUID(axiom_data["id"]), include_provenance=True)

    assert result is not None
    assert result.id == UUID(axiom_data["id"])
    assert result.statement == axiom_data["statement"]
    assert len(result.sources) == 1
    assert result.sources[0]["id"] == source_data["id"]


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_axiom_without_provenance(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
):
    """Test retrieving an Axiom without provenance."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom without sources
    mock_neo4j_client.execute_read.return_value = [
        {
            "a": axiom_data,
            "sources": [],
        }
    ]

    result = neo4j_get_axiom(UUID(axiom_data["id"]), include_provenance=False)

    assert result is not None
    assert result.id == UUID(axiom_data["id"])
    assert result.sources == []


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_axiom_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test retrieving a nonexistent Axiom."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom not found
    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_axiom(uuid4())

    assert result is None


# =============================================================================
# TESTS: neo4j_list_axioms
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_axioms_by_domain(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test listing axioms filtered by domain."""
    mock_get_client.return_value = mock_neo4j_client

    axiom1 = {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "statement": "Magic axiom",
        "domain": AxiomDomain.MAGIC.value,
        "confidence": 1.0,
        "canon_level": CanonLevel.CANON.value,
        "authority": AxiomAuthority.SYSTEM.value,
        "created_at": "2024-01-01T00:00:00",
    }

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],  # Count
        [{"a": axiom1}],  # List
    ]

    filters = AxiomFilter(
        universe_id=UUID(universe_data["id"]),
        domain=AxiomDomain.MAGIC,
    )

    result = neo4j_list_axioms(filters)

    assert result.total == 1
    assert len(result.axioms) == 1
    assert result.axioms[0].domain == AxiomDomain.MAGIC


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_axioms_by_confidence(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test listing axioms filtered by confidence range."""
    mock_get_client.return_value = mock_neo4j_client

    axiom1 = {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "statement": "High confidence axiom",
        "domain": AxiomDomain.PHYSICS.value,
        "confidence": 0.9,
        "canon_level": CanonLevel.CANON.value,
        "authority": AxiomAuthority.SYSTEM.value,
        "created_at": "2024-01-01T00:00:00",
    }

    # Mock count and list queries
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 1}],  # Count
        [{"a": axiom1}],  # List
    ]

    filters = AxiomFilter(
        confidence_min=0.8,
        confidence_max=1.0,
    )

    result = neo4j_list_axioms(filters)

    assert result.total == 1
    assert len(result.axioms) == 1
    assert result.axioms[0].confidence >= 0.8


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_axioms_empty(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test listing axioms when none exist."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock empty result
    mock_neo4j_client.execute_read.side_effect = [
        [{"total": 0}],  # Count
        [],  # List
    ]

    result = neo4j_list_axioms()

    assert result.total == 0
    assert len(result.axioms) == 0


# =============================================================================
# TESTS: neo4j_update_axiom
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_axiom(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
):
    """Test updating an Axiom."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom exists
    mock_neo4j_client.execute_read.return_value = [{"id": axiom_data["id"]}]

    # Mock updated axiom
    updated_axiom = axiom_data.copy()
    updated_axiom["statement"] = "Updated statement"
    updated_axiom["confidence"] = 0.8
    mock_neo4j_client.execute_write.return_value = [{"a": updated_axiom}]

    params = AxiomUpdate(
        statement="Updated statement",
        confidence=0.8,
    )

    result = neo4j_update_axiom(UUID(axiom_data["id"]), params)

    assert result.statement == "Updated statement"
    assert result.confidence == 0.8
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_axiom_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test updating a nonexistent Axiom."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom not found
    mock_neo4j_client.execute_read.return_value = []

    params = AxiomUpdate(statement="Test")

    with pytest.raises(ValueError, match="Axiom .* not found"):
        neo4j_update_axiom(uuid4(), params)


# =============================================================================
# TESTS: neo4j_delete_axiom
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_axiom_soft_delete(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
):
    """Test soft-deleting an Axiom (sets canon_level to retconned)."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom exists
    mock_neo4j_client.execute_read.return_value = [{"id": axiom_data["id"]}]

    # Mock soft-delete
    retconned_axiom = axiom_data.copy()
    retconned_axiom["canon_level"] = CanonLevel.RETCONNED.value
    mock_neo4j_client.execute_write.return_value = [{"a": retconned_axiom}]

    result = neo4j_delete_axiom(UUID(axiom_data["id"]))

    assert result["deleted"] is True
    assert result["method"] == "soft-delete"
    assert result["canon_level"] == "retconned"
    assert mock_neo4j_client.execute_write.call_count == 1


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_axiom_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test deleting a nonexistent Axiom."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom not found
    mock_neo4j_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="Axiom .* not found"):
        neo4j_delete_axiom(uuid4())


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_axiom_lifecycle(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test full axiom lifecycle: create → update → soft-delete."""
    mock_get_client.return_value = mock_neo4j_client

    axiom_id = uuid4()

    # Step 1: Create
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]
    created_axiom = {
        "id": str(axiom_id),
        "universe_id": universe_data["id"],
        "statement": "Original statement",
        "domain": AxiomDomain.PHYSICS.value,
        "confidence": 1.0,
        "canon_level": CanonLevel.CANON.value,
        "authority": AxiomAuthority.SYSTEM.value,
        "created_at": "2024-01-01T00:00:00",
    }
    mock_neo4j_client.execute_write.return_value = [{"a": created_axiom}]

    create_params = AxiomCreate(
        universe_id=UUID(universe_data["id"]),
        statement="Original statement",
        domain=AxiomDomain.PHYSICS,
    )
    result = neo4j_create_axiom(create_params)
    assert result.statement == "Original statement"

    # Step 2: Update
    mock_neo4j_client.execute_read.return_value = [{"id": str(axiom_id)}]
    updated_axiom = created_axiom.copy()
    updated_axiom["statement"] = "Updated statement"
    mock_neo4j_client.execute_write.return_value = [{"a": updated_axiom}]

    update_params = AxiomUpdate(statement="Updated statement")
    result = neo4j_update_axiom(axiom_id, update_params)
    assert result.statement == "Updated statement"

    # Step 3: Soft-delete
    mock_neo4j_client.execute_read.return_value = [{"id": str(axiom_id)}]
    retconned_axiom = updated_axiom.copy()
    retconned_axiom["canon_level"] = CanonLevel.RETCONNED.value
    mock_neo4j_client.execute_write.return_value = [{"a": retconned_axiom}]

    result = neo4j_delete_axiom(axiom_id)
    assert result["deleted"] is True
    assert result["canon_level"] == "retconned"
