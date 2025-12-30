"""
Unit tests for Neo4j axiom operations.

Tests cover:
- neo4j_create_axiom
- neo4j_get_axiom
- neo4j_list_axioms
- neo4j_update_axiom
- neo4j_delete_axiom
"""

from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.axioms import (
    AxiomCreate,
    AxiomUpdate,
    AxiomFilter,
)
from monitor_data.schemas.base import CanonLevel, AxiomAuthority, AxiomDomain
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
        "canon_level": CanonLevel.CANON.value,
        "confidence": 1.0,
        "authority": AxiomAuthority.GM.value,
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def source_data() -> Dict[str, Any]:
    """Provide sample source data."""
    return {
        "id": str(uuid4()),
        "title": "Player's Handbook",
    }


# =============================================================================
# TESTS: neo4j_create_axiom
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_axiom")
def test_create_axiom_success(
    mock_get_axiom: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    axiom_data: Dict[str, Any],
):
    """Test successful axiom creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists check
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock axiom creation
    mock_neo4j_client.execute_write.return_value = [{"a": axiom_data}]

    # Mock get_axiom response
    from monitor_data.schemas.axioms import AxiomResponse

    expected_response = AxiomResponse(
        id=UUID(axiom_data["id"]),
        universe_id=UUID(axiom_data["universe_id"]),
        statement=axiom_data["statement"],
        domain=AxiomDomain.MAGIC,
        canon_level=CanonLevel.CANON,
        confidence=axiom_data["confidence"],
        authority=AxiomAuthority.GM,
        created_at=datetime.fromisoformat(axiom_data["created_at"]),
        source_ids=[],
        snippet_ids=[],
    )
    mock_get_axiom.return_value = expected_response

    # Create axiom
    params = AxiomCreate(
        universe_id=UUID(universe_data["id"]),
        statement="Magic requires verbal components",
        domain=AxiomDomain.MAGIC,
        canon_level=CanonLevel.CANON,
        confidence=1.0,
        authority=AxiomAuthority.GM,
    )

    result = neo4j_create_axiom(params)

    assert result.statement == "Magic requires verbal components"
    assert result.domain == AxiomDomain.MAGIC
    assert result.confidence == 1.0
    mock_neo4j_client.execute_write.assert_called()


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_axiom_invalid_universe(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test axiom creation with non-existent universe."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe doesn't exist
    mock_neo4j_client.execute_read.return_value = []

    params = AxiomCreate(
        universe_id=uuid4(),
        statement="Magic requires verbal components",
        domain=AxiomDomain.MAGIC,
    )

    with pytest.raises(ValueError, match="Universe .* not found"):
        neo4j_create_axiom(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_axiom")
def test_create_axiom_with_provenance(
    mock_get_axiom: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    axiom_data: Dict[str, Any],
    source_data: Dict[str, Any],
):
    """Test axiom creation with provenance (sources)."""
    mock_get_client.return_value = mock_neo4j_client

    source_id = UUID(source_data["id"])

    # Mock universe and source exist checks
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],  # Universe exists
        [{"id": source_data["id"]}],  # Source exists
    ]

    # Mock axiom creation
    mock_neo4j_client.execute_write.return_value = [{"a": axiom_data}]

    # Mock get_axiom response with source
    from monitor_data.schemas.axioms import AxiomResponse

    expected_response = AxiomResponse(
        id=UUID(axiom_data["id"]),
        universe_id=UUID(axiom_data["universe_id"]),
        statement=axiom_data["statement"],
        domain=AxiomDomain.MAGIC,
        canon_level=CanonLevel.CANON,
        confidence=axiom_data["confidence"],
        authority=AxiomAuthority.GM,
        created_at=datetime.fromisoformat(axiom_data["created_at"]),
        source_ids=[source_id],
        snippet_ids=["snippet_123"],
    )
    mock_get_axiom.return_value = expected_response

    # Create axiom with provenance
    params = AxiomCreate(
        universe_id=UUID(universe_data["id"]),
        statement="Magic requires verbal components",
        domain=AxiomDomain.MAGIC,
        source_ids=[source_id],
        snippet_ids=["snippet_123"],
    )

    result = neo4j_create_axiom(params)

    assert result.source_ids == [source_id]
    assert result.snippet_ids == ["snippet_123"]
    # Verify SUPPORTED_BY edge was created
    assert mock_neo4j_client.execute_write.call_count >= 2


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_axiom")
def test_create_axiom_invalid_source(
    mock_get_axiom: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test axiom creation with non-existent source."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists but source doesn't
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": universe_data["id"]}],  # Universe exists
        [],  # Source doesn't exist
    ]

    params = AxiomCreate(
        universe_id=UUID(universe_data["id"]),
        statement="Magic requires verbal components",
        domain=AxiomDomain.MAGIC,
        source_ids=[uuid4()],
    )

    with pytest.raises(ValueError, match="Source .* not found"):
        neo4j_create_axiom(params)


@pytest.mark.parametrize(
    "domain",
    [
        AxiomDomain.PHYSICS,
        AxiomDomain.MAGIC,
        AxiomDomain.SOCIETY,
        AxiomDomain.METAPHYSICS,
    ],
)
@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_axiom")
def test_create_axiom_all_domains(
    mock_get_axiom: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
    axiom_data: Dict[str, Any],
    domain: AxiomDomain,
):
    """Test axiom creation with each domain value."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock universe exists
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]

    # Mock axiom creation
    axiom_data_copy = axiom_data.copy()
    axiom_data_copy["domain"] = domain.value
    mock_neo4j_client.execute_write.return_value = [{"a": axiom_data_copy}]

    # Mock get_axiom response
    from monitor_data.schemas.axioms import AxiomResponse

    expected_response = AxiomResponse(
        id=UUID(axiom_data["id"]),
        universe_id=UUID(axiom_data["universe_id"]),
        statement=axiom_data["statement"],
        domain=domain,
        canon_level=CanonLevel.CANON,
        confidence=axiom_data["confidence"],
        authority=AxiomAuthority.GM,
        created_at=datetime.fromisoformat(axiom_data["created_at"]),
        source_ids=[],
        snippet_ids=[],
    )
    mock_get_axiom.return_value = expected_response

    # Create axiom with specific domain
    params = AxiomCreate(
        universe_id=UUID(universe_data["id"]),
        statement=f"Test axiom for {domain.value}",
        domain=domain,
    )

    result = neo4j_create_axiom(params)

    assert result.domain == domain


# =============================================================================
# TESTS: neo4j_get_axiom
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_axiom_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
    source_data: Dict[str, Any],
):
    """Test successful axiom retrieval with provenance."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom with source
    mock_neo4j_client.execute_read.return_value = [
        {
            "a": axiom_data,
            "source_ids": [source_data["id"]],
        }
    ]

    result = neo4j_get_axiom(UUID(axiom_data["id"]))

    assert result is not None
    assert result.id == UUID(axiom_data["id"])
    assert result.statement == axiom_data["statement"]
    assert result.domain == AxiomDomain.MAGIC
    assert result.source_ids == [UUID(source_data["id"])]


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_axiom_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test axiom retrieval when axiom doesn't exist."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom not found
    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_axiom(uuid4())

    assert result is None


# =============================================================================
# TESTS: neo4j_list_axioms
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_axioms_no_filters(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
):
    """Test listing axioms without filters."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock multiple axioms
    axiom_data_2 = axiom_data.copy()
    axiom_data_2["id"] = str(uuid4())
    axiom_data_2["domain"] = AxiomDomain.PHYSICS.value

    mock_neo4j_client.execute_read.return_value = [
        {"a": axiom_data, "source_ids": []},
        {"a": axiom_data_2, "source_ids": []},
    ]

    result = neo4j_list_axioms()

    assert len(result) == 2
    assert result[0].domain == AxiomDomain.MAGIC
    assert result[1].domain == AxiomDomain.PHYSICS


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_axioms_filter_by_domain(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
):
    """Test listing axioms filtered by domain."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom with MAGIC domain
    mock_neo4j_client.execute_read.return_value = [
        {"a": axiom_data, "source_ids": []}
    ]

    filters = AxiomFilter(domain=AxiomDomain.MAGIC)
    result = neo4j_list_axioms(filters)

    assert len(result) == 1
    assert result[0].domain == AxiomDomain.MAGIC
    # Verify query includes domain filter
    call_args = mock_neo4j_client.execute_read.call_args
    assert "a.domain = $domain" in call_args[0][0]


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_axioms_filter_by_universe(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
    universe_data: Dict[str, Any],
):
    """Test listing axioms filtered by universe_id."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom for specific universe
    mock_neo4j_client.execute_read.return_value = [
        {"a": axiom_data, "source_ids": []}
    ]

    filters = AxiomFilter(universe_id=UUID(universe_data["id"]))
    result = neo4j_list_axioms(filters)

    assert len(result) == 1
    assert result[0].universe_id == UUID(universe_data["id"])
    # Verify query includes universe_id filter
    call_args = mock_neo4j_client.execute_read.call_args
    assert "a.universe_id = $universe_id" in call_args[0][0]


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_axioms_filter_by_confidence(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
):
    """Test listing axioms filtered by confidence range."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock high confidence axiom
    mock_neo4j_client.execute_read.return_value = [
        {"a": axiom_data, "source_ids": []}
    ]

    filters = AxiomFilter(confidence_min=0.8, confidence_max=1.0)
    result = neo4j_list_axioms(filters)

    assert len(result) == 1
    assert result[0].confidence >= 0.8
    # Verify query includes confidence filters
    call_args = mock_neo4j_client.execute_read.call_args
    assert "a.confidence >= $confidence_min" in call_args[0][0]
    assert "a.confidence <= $confidence_max" in call_args[0][0]


# =============================================================================
# TESTS: neo4j_update_axiom
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_axiom")
def test_update_axiom_success(
    mock_get_axiom: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
):
    """Test successful axiom update."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom exists
    mock_neo4j_client.execute_read.return_value = [{"id": axiom_data["id"]}]

    # Mock update
    updated_data = axiom_data.copy()
    updated_data["statement"] = "Magic requires verbal and somatic components"
    updated_data["confidence"] = 0.9
    mock_neo4j_client.execute_write.return_value = [{"a": updated_data}]

    # Mock get_axiom response
    from monitor_data.schemas.axioms import AxiomResponse

    expected_response = AxiomResponse(
        id=UUID(updated_data["id"]),
        universe_id=UUID(updated_data["universe_id"]),
        statement=updated_data["statement"],
        domain=AxiomDomain.MAGIC,
        canon_level=CanonLevel.CANON,
        confidence=updated_data["confidence"],
        authority=AxiomAuthority.GM,
        created_at=datetime.fromisoformat(updated_data["created_at"]),
        source_ids=[],
        snippet_ids=[],
    )
    mock_get_axiom.return_value = expected_response

    # Update axiom
    params = AxiomUpdate(
        statement="Magic requires verbal and somatic components",
        confidence=0.9,
    )

    result = neo4j_update_axiom(UUID(axiom_data["id"]), params)

    assert result.statement == "Magic requires verbal and somatic components"
    assert result.confidence == 0.9
    mock_neo4j_client.execute_write.assert_called()


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_axiom_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test update axiom when axiom doesn't exist."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom not found
    mock_neo4j_client.execute_read.return_value = []

    params = AxiomUpdate(statement="Updated statement")

    with pytest.raises(ValueError, match="Axiom .* not found"):
        neo4j_update_axiom(uuid4(), params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_axiom")
def test_update_axiom_no_changes(
    mock_get_axiom: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
):
    """Test update axiom with no changes."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom exists
    mock_neo4j_client.execute_read.return_value = [{"id": axiom_data["id"]}]

    # Mock get_axiom response (no update performed)
    from monitor_data.schemas.axioms import AxiomResponse

    expected_response = AxiomResponse(
        id=UUID(axiom_data["id"]),
        universe_id=UUID(axiom_data["universe_id"]),
        statement=axiom_data["statement"],
        domain=AxiomDomain.MAGIC,
        canon_level=CanonLevel.CANON,
        confidence=axiom_data["confidence"],
        authority=AxiomAuthority.GM,
        created_at=datetime.fromisoformat(axiom_data["created_at"]),
        source_ids=[],
        snippet_ids=[],
    )
    mock_get_axiom.return_value = expected_response

    # Update with empty params
    params = AxiomUpdate()

    result = neo4j_update_axiom(UUID(axiom_data["id"]), params)

    assert result.statement == axiom_data["statement"]
    # No write should be performed for empty update
    mock_neo4j_client.execute_write.assert_not_called()


# =============================================================================
# TESTS: neo4j_delete_axiom
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_axiom_soft_delete(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
):
    """Test axiom soft-delete (retconning)."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom exists
    mock_neo4j_client.execute_read.return_value = [{"id": axiom_data["id"]}]

    # Mock retcon update
    retconned_data = axiom_data.copy()
    retconned_data["canon_level"] = CanonLevel.RETCONNED.value
    mock_neo4j_client.execute_write.return_value = [{"a": retconned_data}]

    result = neo4j_delete_axiom(UUID(axiom_data["id"]), force=False)

    assert result["axiom_id"] == axiom_data["id"]
    assert result["deleted"] is True
    assert result["soft_delete"] is True
    # Verify SET canon_level was called
    call_args = mock_neo4j_client.execute_write.call_args
    assert "SET a.canon_level" in call_args[0][0]


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_axiom_hard_delete(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    axiom_data: Dict[str, Any],
):
    """Test axiom hard delete (permanent removal)."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom exists
    mock_neo4j_client.execute_read.return_value = [{"id": axiom_data["id"]}]

    # Mock delete
    mock_neo4j_client.execute_write.return_value = []

    result = neo4j_delete_axiom(UUID(axiom_data["id"]), force=True)

    assert result["axiom_id"] == axiom_data["id"]
    assert result["deleted"] is True
    assert result["soft_delete"] is False
    # Verify DETACH DELETE was called
    call_args = mock_neo4j_client.execute_write.call_args
    assert "DETACH DELETE" in call_args[0][0]


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_axiom_not_found(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test delete axiom when axiom doesn't exist."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock axiom not found
    mock_neo4j_client.execute_read.return_value = []

    with pytest.raises(ValueError, match="Axiom .* not found"):
        neo4j_delete_axiom(uuid4())


# =============================================================================
# INTEGRATION TEST: Axiom Lifecycle
# =============================================================================


@pytest.mark.integration
@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
@patch("monitor_data.tools.neo4j_tools.neo4j_get_axiom")
def test_axiom_lifecycle_integration(
    mock_get_axiom: Mock,
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    universe_data: Dict[str, Any],
):
    """Test complete axiom lifecycle: create → update → soft-delete."""
    mock_get_client.return_value = mock_neo4j_client

    # Step 1: Create axiom
    axiom_id = uuid4()
    axiom_data = {
        "id": str(axiom_id),
        "universe_id": universe_data["id"],
        "statement": "Magic exists",
        "domain": AxiomDomain.MAGIC.value,
        "canon_level": CanonLevel.CANON.value,
        "confidence": 1.0,
        "authority": AxiomAuthority.SYSTEM.value,
        "created_at": "2024-01-01T00:00:00",
    }

    # Mock create
    mock_neo4j_client.execute_read.return_value = [{"id": universe_data["id"]}]
    mock_neo4j_client.execute_write.return_value = [{"a": axiom_data}]

    from monitor_data.schemas.axioms import AxiomResponse

    created_response = AxiomResponse(
        id=axiom_id,
        universe_id=UUID(universe_data["id"]),
        statement="Magic exists",
        domain=AxiomDomain.MAGIC,
        canon_level=CanonLevel.CANON,
        confidence=1.0,
        authority=AxiomAuthority.SYSTEM,
        created_at=datetime.fromisoformat(axiom_data["created_at"]),
        source_ids=[],
        snippet_ids=[],
    )
    mock_get_axiom.return_value = created_response

    create_params = AxiomCreate(
        universe_id=UUID(universe_data["id"]),
        statement="Magic exists",
        domain=AxiomDomain.MAGIC,
    )
    created = neo4j_create_axiom(create_params)
    assert created.statement == "Magic exists"

    # Step 2: Update axiom
    mock_neo4j_client.execute_read.return_value = [{"id": str(axiom_id)}]
    updated_data = axiom_data.copy()
    updated_data["statement"] = "Magic exists with limitations"
    updated_response = AxiomResponse(
        id=axiom_id,
        universe_id=UUID(universe_data["id"]),
        statement="Magic exists with limitations",
        domain=AxiomDomain.MAGIC,
        canon_level=CanonLevel.CANON,
        confidence=1.0,
        authority=AxiomAuthority.SYSTEM,
        created_at=datetime.fromisoformat(axiom_data["created_at"]),
        source_ids=[],
        snippet_ids=[],
    )
    mock_get_axiom.return_value = updated_response

    update_params = AxiomUpdate(statement="Magic exists with limitations")
    updated = neo4j_update_axiom(axiom_id, update_params)
    assert updated.statement == "Magic exists with limitations"

    # Step 3: Soft-delete (retcon)
    mock_neo4j_client.execute_read.return_value = [{"id": str(axiom_id)}]
    retconned_data = updated_data.copy()
    retconned_data["canon_level"] = CanonLevel.RETCONNED.value
    mock_neo4j_client.execute_write.return_value = [{"a": retconned_data}]

    delete_result = neo4j_delete_axiom(axiom_id, force=False)
    assert delete_result["soft_delete"] is True
