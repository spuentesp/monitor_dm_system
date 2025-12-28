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


# =============================================================================
# SOURCE, DOCUMENT, SNIPPET, INGEST PROPOSAL DATA FACTORIES
# =============================================================================


@pytest.fixture
def source_data(universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample source data."""
    return {
        "id": str(uuid4()),
        "universe_id": universe_data["id"],
        "title": "Player's Handbook",
        "source_type": "rulebook",
        "edition": "5th Edition",
        "provenance": "ISBN: 978-0786965601",
        "doc_id": None,
        "canon_level": "canon",
        "metadata": {"author": "Wizards of the Coast", "year": 2014},
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def document_data(source_data: Dict[str, Any], universe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample document data."""
    return {
        "doc_id": str(uuid4()),
        "source_id": source_data["id"],
        "universe_id": universe_data["id"],
        "minio_ref": "documents/test-phb.pdf",
        "title": "Player's Handbook PDF",
        "filename": "phb-5e.pdf",
        "file_type": "pdf",
        "extraction_status": "pending",
        "metadata": {"size": 1024000, "pages": 320},
        "created_at": "2024-01-01T00:00:00",
        "extracted_at": None,
    }


@pytest.fixture
def snippet_data(document_data: Dict[str, Any], source_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample snippet data."""
    return {
        "snippet_id": str(uuid4()),
        "doc_id": document_data["doc_id"],
        "source_id": source_data["id"],
        "text": "Wizards are masters of arcane magic...",
        "page": 112,
        "section": "Chapter 3: Classes",
        "chunk_index": 0,
        "metadata": {"char_count": 1500},
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def ingest_proposal_data(universe_data: Dict[str, Any], snippet_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample ingest proposal data."""
    return {
        "proposal_id": str(uuid4()),
        "proposal_type": "entity",
        "universe_id": universe_data["id"],
        "content": {
            "name": "Wizard",
            "entity_type": "character",
            "description": "A spellcaster who draws on arcane magic",
        },
        "confidence": 0.95,
        "evidence_snippet_ids": [snippet_data["snippet_id"]],
        "status": "pending",
        "decision_reason": None,
        "canonical_id": None,
        "metadata": {"extraction_model": "gpt-4"},
        "created_at": "2024-01-01T00:00:00",
        "updated_at": None,
    }


@pytest.fixture
def mock_mongodb_client() -> Generator[Mock, None, None]:
    """
    Provide a mock MongoDB client for testing.

    Returns:
        Mock MongoDBClientClass with common methods stubbed
    """
    from monitor_data.db.mongodb import MongoDBClientClass
    
    mock_client = Mock(spec=MongoDBClientClass)
    mock_collection = Mock()
    
    mock_client.get_collection = Mock(return_value=mock_collection)
    mock_client.verify_connectivity = Mock(return_value=True)
    mock_client.connect = Mock()
    mock_client.close = Mock()
    
    yield mock_client
