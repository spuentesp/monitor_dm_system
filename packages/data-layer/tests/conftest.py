"""
Pytest configuration and fixtures for MONITOR Data Layer tests.

This module provides:
- Mock database clients
- Test data factories
- Common fixtures
"""

import os
from typing import Generator, Dict, Any
from uuid import uuid4

import pytest
from unittest.mock import Mock

from monitor_data.db.neo4j import Neo4jClient
from monitor_data.schemas.base import Authority, CanonLevel


# =============================================================================
# TEST CONFIGURATION
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set up test environment variables."""
    os.environ["NEO4J_URI"] = "bolt://localhost:7687"
    os.environ["NEO4J_USER"] = "neo4j"
    os.environ["NEO4J_PASSWORD"] = "test_password"


# =============================================================================
# MOCK CLIENTS
# =============================================================================


@pytest.fixture
def mock_neo4j_client() -> Generator[Mock, None, None]:
    """
    Provide a mock Neo4j client for testing.

    Returns:
        Mock Neo4jClient with common methods stubbed
    """
    mock_client = Mock(spec=Neo4jClient)
    mock_client.execute_read = Mock(return_value=[])
    mock_client.execute_write = Mock(return_value=[])
    mock_client.verify_connectivity = Mock(return_value=True)
    mock_client.connect = Mock()
    mock_client.close = Mock()

    yield mock_client


# =============================================================================
# TEST DATA FACTORIES
# =============================================================================


@pytest.fixture
def omniverse_data() -> Dict[str, Any]:
    """Provide sample omniverse data."""
    return {
        "id": str(uuid4()),
        "name": "Test Omniverse",
        "description": "Test omniverse for unit tests",
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def multiverse_data(omniverse_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample multiverse data."""
    return {
        "id": str(uuid4()),
        "omniverse_id": omniverse_data["id"],
        "name": "Test Multiverse",
        "system_name": "Test System",
        "description": "Test multiverse for unit tests",
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def universe_data(multiverse_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample universe data."""
    return {
        "id": str(uuid4()),
        "multiverse_id": multiverse_data["id"],
        "name": "Test Universe",
        "description": "A test universe for unit tests",
        "genre": "fantasy",
        "tone": "heroic",
        "tech_level": "medieval",
        "canon_level": CanonLevel.CANON.value,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def universe_node(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Provide a universe node as returned by Neo4j.

    This simulates the structure returned by execute_read/execute_write.
    """
    return {"u": universe_data}


@pytest.fixture
def story_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample story data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "title": "Test Story",
        "story_type": "campaign",
        "theme": "Adventure",
        "premise": "A test adventure",
        "status": "planned",
        "start_time_ref": None,
        "end_time_ref": None,
        "created_at": "2024-01-01T00:00:00",
        "completed_at": None,
    }


@pytest.fixture
def pc_entity_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample PC entity data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "name": "Test PC",
        "entity_type": "character",
        "is_archetype": False,
        "description": "A test player character",
        "properties": {"role": "PC"},
        "state_tags": ["alive"],
        "canon_level": "canon",
        "confidence": 1.0,
        "authority": "player",
        "created_at": "2024-01-01T00:00:00",
    }


# =============================================================================
# UTILITY FIXTURES
# =============================================================================


@pytest.fixture
def valid_uuid() -> str:
    """Provide a valid UUID string."""
    return str(uuid4())


@pytest.fixture
def invalid_uuid() -> str:
    """Provide an invalid UUID string."""
    return "not-a-valid-uuid"
