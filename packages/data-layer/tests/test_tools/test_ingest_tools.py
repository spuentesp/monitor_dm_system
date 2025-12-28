"""
Unit tests for MongoDB document, snippet, and ingest proposal operations.

Tests cover:
- mongodb_create_document
- mongodb_get_document
- mongodb_list_documents
- mongodb_create_snippet
- mongodb_list_snippets
- mongodb_create_ingest_proposal
- mongodb_list_ingest_proposals
- mongodb_update_ingest_proposal
"""

from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.documents import (
    DocumentCreate,
    DocumentFilter,
)
from monitor_data.schemas.snippets import (
    SnippetCreate,
    SnippetFilter,
)
from monitor_data.schemas.ingest_proposals import (
    IngestProposalCreate,
    IngestProposalUpdate,
    IngestProposalFilter,
)
from monitor_data.schemas.base import (
    DocumentStatus,
    IngestProposalStatus,
    IngestProposalType,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_document,
    mongodb_get_document,
    mongodb_list_documents,
    mongodb_create_snippet,
    mongodb_list_snippets,
    mongodb_create_ingest_proposal,
    mongodb_list_ingest_proposals,
    mongodb_update_ingest_proposal,
)


# =============================================================================
# TESTS: mongodb_create_document
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_document_success(
    mock_get_client: Mock,
    source_data: Dict[str, Any],
    universe_data: Dict[str, Any],
):
    """Test successful document creation."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    params = DocumentCreate(
        source_id=UUID(source_data["id"]),
        universe_id=UUID(universe_data["id"]),
        minio_ref="documents/test.pdf",
        title="Test Document",
        filename="test.pdf",
        file_type="pdf",
        metadata={"pages": 10},
    )

    result = mongodb_create_document(params)

    assert result.title == "Test Document"
    assert result.source_id == UUID(source_data["id"])
    assert result.minio_ref == "documents/test.pdf"
    assert result.extraction_status == DocumentStatus.PENDING
    assert mock_collection.insert_one.call_count == 1


def test_create_document_missing_required():
    """Test document creation with missing required fields."""
    with pytest.raises(Exception):  # Pydantic validation error
        DocumentCreate(
            source_id=uuid4(),
            # Missing required fields
        )


# =============================================================================
# TESTS: mongodb_get_document
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_document_success(
    mock_get_client: Mock,
    document_data: Dict[str, Any],
):
    """Test successful document retrieval."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = document_data
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    result = mongodb_get_document(UUID(document_data["doc_id"]))

    assert result is not None
    assert result.doc_id == UUID(document_data["doc_id"])
    assert result.title == document_data["title"]
    assert result.extraction_status == DocumentStatus(document_data["extraction_status"])


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_document_not_found(mock_get_client: Mock):
    """Test document retrieval when document doesn't exist."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = None
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    result = mongodb_get_document(uuid4())

    assert result is None


# =============================================================================
# TESTS: mongodb_list_documents
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_documents_no_filters(
    mock_get_client: Mock,
    document_data: Dict[str, Any],
):
    """Test listing documents without filters."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.count_documents.return_value = 1
    
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [document_data]
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    
    mock_collection.find.return_value = mock_cursor
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    filters = DocumentFilter()
    result = mongodb_list_documents(filters)

    assert result.total == 1
    assert len(result.documents) == 1
    assert result.documents[0].doc_id == UUID(document_data["doc_id"])


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_documents_with_source_filter(
    mock_get_client: Mock,
    document_data: Dict[str, Any],
    source_data: Dict[str, Any],
):
    """Test listing documents filtered by source_id."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.count_documents.return_value = 1
    
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [document_data]
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    
    mock_collection.find.return_value = mock_cursor
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    filters = DocumentFilter(source_id=UUID(source_data["id"]))
    result = mongodb_list_documents(filters)

    assert result.total == 1
    # Verify filter was applied
    call_args = mock_collection.find.call_args[0][0]
    assert call_args["source_id"] == source_data["id"]


# =============================================================================
# TESTS: mongodb_create_snippet
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_snippet_success(
    mock_get_client: Mock,
    document_data: Dict[str, Any],
    source_data: Dict[str, Any],
):
    """Test successful snippet creation."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    params = SnippetCreate(
        doc_id=UUID(document_data["doc_id"]),
        source_id=UUID(source_data["id"]),
        text="This is a test snippet.",
        page=1,
        section="Introduction",
        chunk_index=0,
        metadata={"char_count": 23},
    )

    result = mongodb_create_snippet(params)

    assert result.text == "This is a test snippet."
    assert result.doc_id == UUID(document_data["doc_id"])
    assert result.page == 1
    assert result.chunk_index == 0
    assert mock_collection.insert_one.call_count == 1


def test_create_snippet_missing_required():
    """Test snippet creation with missing required fields."""
    with pytest.raises(Exception):  # Pydantic validation error
        SnippetCreate(
            doc_id=uuid4(),
            # Missing source_id, text, chunk_index
        )


# =============================================================================
# TESTS: mongodb_list_snippets
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_snippets_by_document(
    mock_get_client: Mock,
    snippet_data: Dict[str, Any],
    document_data: Dict[str, Any],
):
    """Test listing snippets filtered by document_id."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.count_documents.return_value = 1
    
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [snippet_data]
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    
    mock_collection.find.return_value = mock_cursor
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    filters = SnippetFilter(doc_id=UUID(document_data["doc_id"]))
    result = mongodb_list_snippets(filters)

    assert result.total == 1
    assert len(result.snippets) == 1
    assert result.snippets[0].snippet_id == UUID(snippet_data["snippet_id"])


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_snippets_by_page(
    mock_get_client: Mock,
    snippet_data: Dict[str, Any],
):
    """Test listing snippets filtered by page number."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.count_documents.return_value = 1
    
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [snippet_data]
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    
    mock_collection.find.return_value = mock_cursor
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    filters = SnippetFilter(page=112)
    result = mongodb_list_snippets(filters)

    assert result.total == 1
    # Verify filter was applied
    call_args = mock_collection.find.call_args[0][0]
    assert call_args["page"] == 112


# =============================================================================
# TESTS: mongodb_create_ingest_proposal
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_ingest_proposal_success(
    mock_get_client: Mock,
    universe_data: Dict[str, Any],
    snippet_data: Dict[str, Any],
):
    """Test successful ingest proposal creation."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    params = IngestProposalCreate(
        proposal_type=IngestProposalType.ENTITY,
        universe_id=UUID(universe_data["id"]),
        content={"name": "Wizard", "description": "A spellcaster"},
        confidence=0.95,
        evidence_snippet_ids=[UUID(snippet_data["snippet_id"])],
        metadata={"model": "gpt-4"},
    )

    result = mongodb_create_ingest_proposal(params)

    assert result.proposal_type == IngestProposalType.ENTITY
    assert result.confidence == 0.95
    assert result.status == IngestProposalStatus.PENDING
    assert len(result.evidence_snippet_ids) == 1
    assert mock_collection.insert_one.call_count == 1


def test_create_ingest_proposal_missing_required():
    """Test ingest proposal creation with missing required fields."""
    with pytest.raises(Exception):  # Pydantic validation error
        IngestProposalCreate(
            proposal_type=IngestProposalType.FACT,
            # Missing universe_id, content, confidence
        )


# =============================================================================
# TESTS: mongodb_list_ingest_proposals
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_ingest_proposals_no_filters(
    mock_get_client: Mock,
    ingest_proposal_data: Dict[str, Any],
):
    """Test listing ingest proposals without filters."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.count_documents.return_value = 1
    
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [ingest_proposal_data]
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    
    mock_collection.find.return_value = mock_cursor
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    filters = IngestProposalFilter()
    result = mongodb_list_ingest_proposals(filters)

    assert result.total == 1
    assert len(result.proposals) == 1
    assert result.proposals[0].proposal_id == UUID(ingest_proposal_data["proposal_id"])


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_ingest_proposals_by_status(
    mock_get_client: Mock,
    ingest_proposal_data: Dict[str, Any],
):
    """Test listing ingest proposals filtered by status."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.count_documents.return_value = 1
    
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [ingest_proposal_data]
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    
    mock_collection.find.return_value = mock_cursor
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    filters = IngestProposalFilter(status=IngestProposalStatus.PENDING)
    result = mongodb_list_ingest_proposals(filters)

    assert result.total == 1
    # Verify filter was applied
    call_args = mock_collection.find.call_args[0][0]
    assert call_args["status"] == "pending"


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_ingest_proposals_by_type(
    mock_get_client: Mock,
    ingest_proposal_data: Dict[str, Any],
):
    """Test listing ingest proposals filtered by type."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.count_documents.return_value = 1
    
    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [ingest_proposal_data]
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    
    mock_collection.find.return_value = mock_cursor
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    filters = IngestProposalFilter(proposal_type=IngestProposalType.ENTITY)
    result = mongodb_list_ingest_proposals(filters)

    assert result.total == 1
    # Verify filter was applied
    call_args = mock_collection.find.call_args[0][0]
    assert call_args["proposal_type"] == "entity"


# =============================================================================
# TESTS: mongodb_update_ingest_proposal
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_ingest_proposal_accept(
    mock_get_client: Mock,
    ingest_proposal_data: Dict[str, Any],
):
    """Test accepting an ingest proposal."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    
    # Mock find_one for existence check
    mock_collection.find_one.side_effect = [
        ingest_proposal_data,  # First call: check exists
        {**ingest_proposal_data, "status": "accepted", "decision_reason": "Approved"},  # Second call: return updated
    ]
    
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    canonical_id = uuid4()
    params = IngestProposalUpdate(
        status=IngestProposalStatus.ACCEPTED,
        decision_reason="Approved",
        canonical_id=canonical_id,
    )

    result = mongodb_update_ingest_proposal(UUID(ingest_proposal_data["proposal_id"]), params)

    assert result.status == IngestProposalStatus.ACCEPTED
    assert result.decision_reason == "Approved"
    assert result.canonical_id == canonical_id
    assert mock_collection.update_one.call_count == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_ingest_proposal_reject(
    mock_get_client: Mock,
    ingest_proposal_data: Dict[str, Any],
):
    """Test rejecting an ingest proposal."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    
    # Mock find_one for existence check
    mock_collection.find_one.side_effect = [
        ingest_proposal_data,  # First call: check exists
        {**ingest_proposal_data, "status": "rejected", "decision_reason": "Duplicate"},  # Second call: return updated
    ]
    
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    params = IngestProposalUpdate(
        status=IngestProposalStatus.REJECTED,
        decision_reason="Duplicate",
    )

    result = mongodb_update_ingest_proposal(UUID(ingest_proposal_data["proposal_id"]), params)

    assert result.status == IngestProposalStatus.REJECTED
    assert result.decision_reason == "Duplicate"


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_ingest_proposal_not_found(mock_get_client: Mock):
    """Test updating non-existent ingest proposal."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = None
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    params = IngestProposalUpdate(status=IngestProposalStatus.ACCEPTED)

    with pytest.raises(ValueError, match="IngestProposal .* not found"):
        mongodb_update_ingest_proposal(uuid4(), params)


# =============================================================================
# INTEGRATION-STYLE TESTS
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_ingest_pipeline_flow(
    mock_get_client: Mock,
    source_data: Dict[str, Any],
    universe_data: Dict[str, Any],
):
    """Test the full ingestion pipeline flow: document → snippet → proposal."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_collection.return_value = mock_collection
    mock_get_client.return_value = mock_client

    # Step 1: Create document
    doc_params = DocumentCreate(
        source_id=UUID(source_data["id"]),
        universe_id=UUID(universe_data["id"]),
        minio_ref="documents/test.pdf",
        title="Test Source",
        filename="test.pdf",
        file_type="pdf",
    )
    doc = mongodb_create_document(doc_params)

    # Step 2: Create snippet
    snippet_params = SnippetCreate(
        doc_id=doc.doc_id,
        source_id=UUID(source_data["id"]),
        text="Extracted knowledge",
        chunk_index=0,
    )
    snippet = mongodb_create_snippet(snippet_params)

    # Step 3: Create ingest proposal
    proposal_params = IngestProposalCreate(
        proposal_type=IngestProposalType.FACT,
        universe_id=UUID(universe_data["id"]),
        content={"statement": "Magic exists"},
        confidence=0.9,
        evidence_snippet_ids=[snippet.snippet_id],
    )
    proposal = mongodb_create_ingest_proposal(proposal_params)

    # Verify the pipeline created all items
    assert doc.doc_id is not None
    assert snippet.snippet_id is not None
    assert proposal.proposal_id is not None
    assert proposal.evidence_snippet_ids[0] == snippet.snippet_id
    assert mock_collection.insert_one.call_count == 3  # document, snippet, proposal
