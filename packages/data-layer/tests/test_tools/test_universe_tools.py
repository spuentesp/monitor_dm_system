"""
Unit tests for Universe CRUD operations.

Tests the neo4j_tools universe operations with mocked Neo4j client.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from monitor_data.schemas.base import CanonLevel, Authority, ErrorResponse
from monitor_data.schemas.universe import (
    UniverseCreate,
    UniverseUpdate,
    UniverseResponse,
    ListUniversesRequest,
    ListUniversesResponse,
)
from monitor_data.tools import neo4j_tools


# ============================================================================
# Fixtures
# ============================================================================


class MockNeo4jClient:
    """Mock Neo4j client for testing."""
    
    def __init__(self):
        self.data = {}
        self.connected = False
    
    def connect(self):
        self.connected = True
    
    def close(self):
        self.connected = False
    
    def execute_read(self, query: str, params: dict):
        """Mock read execution."""
        # Normalize query for easier matching
        normalized_query = " ".join(query.split())
        
        # Handle multiverse verification
        if "MATCH (m:Multiverse" in normalized_query:
            multiverse_id = params.get("multiverse_id")
            if multiverse_id and multiverse_id in self.data.get("multiverses", {}):
                return [{"m": self.data["multiverses"][multiverse_id]}]
            return []
        
        # Handle universe retrieval
        if "MATCH (u:Universe" in normalized_query and "RETURN u" in normalized_query and "SKIP" not in normalized_query:
            universe_id = params.get("universe_id")
            if universe_id and universe_id in self.data.get("universes", {}):
                return [{"u": self.data["universes"][universe_id]}]
            return []
        
        # Handle list universes count
        if "count(u) as total" in normalized_query:
            universes = self.data.get("universes", {})
            # Apply filters
            multiverse_id = params.get("multiverse_id")
            canon_level = params.get("canon_level")
            
            filtered = []
            for u in universes.values():
                if multiverse_id and u["multiverse_id"] != multiverse_id:
                    continue
                if canon_level and u["canon_level"] != canon_level:
                    continue
                filtered.append(u)
            
            return [{"total": len(filtered)}]
        
        # Handle list universes query - needs to come AFTER count check
        if "MATCH (u:Universe)" in normalized_query and "RETURN u" in normalized_query and ("ORDER BY" in normalized_query or "SKIP" in normalized_query):
            universes = self.data.get("universes", {})
            multiverse_id = params.get("multiverse_id")
            canon_level = params.get("canon_level")
            limit = params.get("limit", 50)
            offset = params.get("offset", 0)
            
            filtered = []
            for u in universes.values():
                if multiverse_id and u["multiverse_id"] != multiverse_id:
                    continue
                if canon_level and u["canon_level"] != canon_level:
                    continue
                filtered.append({"u": u})
            
            # Sort by created_at desc (handle both string and datetime)
            try:
                filtered.sort(key=lambda x: x["u"]["created_at"], reverse=True)
            except:
                pass
            
            return filtered[offset:offset + limit]
        
        # Handle dependent check
        if "dependents" in normalized_query:
            universe_id = params.get("universe_id")
            if universe_id in self.data.get("universes", {}):
                # Simulate no dependents for simplicity
                return [{"dependents": 0}]
            return []
        
        return []
    
    def execute_write(self, query: str, params: dict):
        """Mock write execution."""
        # Handle universe creation
        if "CREATE (u:Universe" in query:
            if "universes" not in self.data:
                self.data["universes"] = {}
            
            universe_id = params["id"]
            self.data["universes"][universe_id] = {
                "id": universe_id,
                "multiverse_id": params["multiverse_id"],
                "name": params["name"],
                "description": params["description"],
                "genre": params.get("genre", ""),
                "tone": params.get("tone", ""),
                "tech_level": params.get("tech_level", ""),
                "canon_level": params["canon_level"],
                "authority": params["authority"],
                "created_at": params["created_at"],
            }
            return [{"u": self.data["universes"][universe_id]}]
        
        # Handle universe update
        if "SET" in query:
            universe_id = params.get("universe_id")
            if universe_id and universe_id in self.data.get("universes", {}):
                universe = self.data["universes"][universe_id]
                
                if "name" in params:
                    universe["name"] = params["name"]
                if "description" in params:
                    universe["description"] = params["description"]
                if "genre" in params:
                    universe["genre"] = params["genre"]
                if "tone" in params:
                    universe["tone"] = params["tone"]
                if "tech_level" in params:
                    universe["tech_level"] = params["tech_level"]
                
                return [{"u": universe}]
            return []
        
        # Handle universe deletion
        if "DELETE" in query:
            universe_id = params.get("universe_id")
            if universe_id and universe_id in self.data.get("universes", {}):
                del self.data["universes"][universe_id]
                return [{"deleted": 1}]
            return [{"deleted": 0}]
        
        return []


@pytest.fixture
def mock_client():
    """Fixture providing a mock Neo4j client."""
    client = MockNeo4jClient()
    
    # Add a test multiverse
    multiverse_id = str(uuid4())
    client.data["multiverses"] = {
        multiverse_id: {
            "id": multiverse_id,
            "omniverse_id": str(uuid4()),
            "name": "Test Multiverse",
            "system_name": "Test System",
            "description": "A test multiverse",
            "created_at": datetime.utcnow().isoformat(),
        }
    }
    
    # Patch the get_neo4j_client function
    original_get_client = neo4j_tools.get_neo4j_client
    neo4j_tools.get_neo4j_client = lambda: client
    neo4j_tools._neo4j_client = client
    
    yield client, multiverse_id
    
    # Restore original
    neo4j_tools.get_neo4j_client = original_get_client
    neo4j_tools._neo4j_client = None


# ============================================================================
# Test Create Universe
# ============================================================================


@pytest.mark.unit
def test_create_universe_success(mock_client):
    """Test successful universe creation."""
    client, multiverse_id = mock_client
    
    data = UniverseCreate(
        multiverse_id=multiverse_id,
        name="Test Universe",
        description="A test universe",
        genre="fantasy",
        tone="heroic",
        tech_level="medieval",
        authority=Authority.GM,
    )
    
    result = neo4j_tools.neo4j_create_universe("CanonKeeper", data)
    
    assert isinstance(result, UniverseResponse)
    assert result.name == "Test Universe"
    assert result.description == "A test universe"
    assert result.genre == "fantasy"
    assert result.tone == "heroic"
    assert result.tech_level == "medieval"
    assert result.canon_level == CanonLevel.CANON
    assert result.authority == Authority.GM


@pytest.mark.unit
def test_create_universe_invalid_multiverse(mock_client):
    """Test universe creation with invalid multiverse_id."""
    client, _ = mock_client
    
    fake_multiverse_id = uuid4()
    data = UniverseCreate(
        multiverse_id=fake_multiverse_id,
        name="Test Universe",
        description="A test universe",
    )
    
    result = neo4j_tools.neo4j_create_universe("CanonKeeper", data)
    
    assert isinstance(result, ErrorResponse)
    assert result.code == "NOT_FOUND"
    assert str(fake_multiverse_id) in result.error


@pytest.mark.unit
def test_create_universe_unauthorized(mock_client):
    """Test universe creation with unauthorized agent."""
    client, multiverse_id = mock_client
    
    data = UniverseCreate(
        multiverse_id=multiverse_id,
        name="Test Universe",
        description="A test universe",
    )
    
    result = neo4j_tools.neo4j_create_universe("Narrator", data)
    
    assert isinstance(result, ErrorResponse)
    assert result.code == "UNAUTHORIZED"


# ============================================================================
# Test Get Universe
# ============================================================================


@pytest.mark.unit
def test_get_universe_exists(mock_client):
    """Test retrieving an existing universe."""
    client, multiverse_id = mock_client
    
    # Create a universe first
    data = UniverseCreate(
        multiverse_id=multiverse_id,
        name="Test Universe",
        description="A test universe",
    )
    
    create_result = neo4j_tools.neo4j_create_universe("CanonKeeper", data)
    assert isinstance(create_result, UniverseResponse)
    
    # Now retrieve it
    result = neo4j_tools.neo4j_get_universe("Narrator", create_result.id)
    
    assert isinstance(result, UniverseResponse)
    assert result.id == create_result.id
    assert result.name == "Test Universe"


@pytest.mark.unit
def test_get_universe_not_found(mock_client):
    """Test retrieving a non-existent universe."""
    client, _ = mock_client
    
    fake_id = uuid4()
    result = neo4j_tools.neo4j_get_universe("Narrator", fake_id)
    
    assert isinstance(result, ErrorResponse)
    assert result.code == "NOT_FOUND"


# ============================================================================
# Test Update Universe
# ============================================================================


@pytest.mark.unit
def test_update_universe_success(mock_client):
    """Test successful universe update."""
    client, multiverse_id = mock_client
    
    # Create a universe first
    data = UniverseCreate(
        multiverse_id=multiverse_id,
        name="Test Universe",
        description="A test universe",
    )
    
    create_result = neo4j_tools.neo4j_create_universe("CanonKeeper", data)
    assert isinstance(create_result, UniverseResponse)
    
    # Update it
    update_data = UniverseUpdate(
        name="Updated Universe",
        genre="sci-fi",
    )
    
    result = neo4j_tools.neo4j_update_universe("CanonKeeper", create_result.id, update_data)
    
    assert isinstance(result, UniverseResponse)
    assert result.name == "Updated Universe"
    assert result.genre == "sci-fi"
    assert result.description == "A test universe"  # Unchanged


@pytest.mark.unit
def test_update_universe_not_found(mock_client):
    """Test updating a non-existent universe."""
    client, _ = mock_client
    
    fake_id = uuid4()
    update_data = UniverseUpdate(name="Updated Universe")
    
    result = neo4j_tools.neo4j_update_universe("CanonKeeper", fake_id, update_data)
    
    assert isinstance(result, ErrorResponse)
    assert result.code == "NOT_FOUND"


@pytest.mark.unit
def test_update_universe_unauthorized(mock_client):
    """Test updating universe with unauthorized agent."""
    client, multiverse_id = mock_client
    
    # Create a universe first
    data = UniverseCreate(
        multiverse_id=multiverse_id,
        name="Test Universe",
        description="A test universe",
    )
    
    create_result = neo4j_tools.neo4j_create_universe("CanonKeeper", data)
    assert isinstance(create_result, UniverseResponse)
    
    # Try to update with wrong agent
    update_data = UniverseUpdate(name="Updated Universe")
    result = neo4j_tools.neo4j_update_universe("Narrator", create_result.id, update_data)
    
    assert isinstance(result, ErrorResponse)
    assert result.code == "UNAUTHORIZED"


# ============================================================================
# Test List Universes
# ============================================================================


@pytest.mark.unit
def test_list_universes_all(mock_client):
    """Test listing all universes."""
    client, multiverse_id = mock_client
    
    # Create multiple universes
    for i in range(3):
        data = UniverseCreate(
            multiverse_id=multiverse_id,
            name=f"Universe {i}",
            description=f"Test universe {i}",
        )
        neo4j_tools.neo4j_create_universe("CanonKeeper", data)
    
    # List all
    result = neo4j_tools.neo4j_list_universes("Narrator", ListUniversesRequest())
    
    assert isinstance(result, ListUniversesResponse)
    assert result.total == 3
    assert len(result.universes) == 3


@pytest.mark.unit
def test_list_universes_filtered(mock_client):
    """Test listing universes with filters."""
    client, multiverse_id = mock_client
    
    # Create universes
    for i in range(3):
        data = UniverseCreate(
            multiverse_id=multiverse_id,
            name=f"Universe {i}",
            description=f"Test universe {i}",
        )
        neo4j_tools.neo4j_create_universe("CanonKeeper", data)
    
    # List with filter
    request = ListUniversesRequest(multiverse_id=multiverse_id)
    result = neo4j_tools.neo4j_list_universes("Narrator", request)
    
    assert isinstance(result, ListUniversesResponse)
    assert result.total == 3


@pytest.mark.unit
def test_list_universes_pagination(mock_client):
    """Test listing universes with pagination."""
    client, multiverse_id = mock_client
    
    # Create multiple universes
    for i in range(5):
        data = UniverseCreate(
            multiverse_id=multiverse_id,
            name=f"Universe {i}",
            description=f"Test universe {i}",
        )
        neo4j_tools.neo4j_create_universe("CanonKeeper", data)
    
    # List with pagination
    request = ListUniversesRequest(limit=2, offset=0)
    result = neo4j_tools.neo4j_list_universes("Narrator", request)
    
    assert isinstance(result, ListUniversesResponse)
    assert result.total == 5
    assert len(result.universes) == 2


# ============================================================================
# Test Delete Universe
# ============================================================================


@pytest.mark.unit
def test_delete_universe_success(mock_client):
    """Test successful universe deletion."""
    client, multiverse_id = mock_client
    
    # Create a universe
    data = UniverseCreate(
        multiverse_id=multiverse_id,
        name="Test Universe",
        description="A test universe",
    )
    
    create_result = neo4j_tools.neo4j_create_universe("CanonKeeper", data)
    assert isinstance(create_result, UniverseResponse)
    
    # Delete it
    result = neo4j_tools.neo4j_delete_universe("CanonKeeper", create_result.id)
    
    assert isinstance(result, dict)
    assert result["success"] is True


@pytest.mark.unit
def test_delete_universe_not_found(mock_client):
    """Test deleting a non-existent universe."""
    client, _ = mock_client
    
    fake_id = uuid4()
    result = neo4j_tools.neo4j_delete_universe("CanonKeeper", fake_id)
    
    assert isinstance(result, ErrorResponse)
    assert result.code == "NOT_FOUND"


@pytest.mark.unit
def test_delete_universe_unauthorized(mock_client):
    """Test deleting universe with unauthorized agent."""
    client, multiverse_id = mock_client
    
    # Create a universe
    data = UniverseCreate(
        multiverse_id=multiverse_id,
        name="Test Universe",
        description="A test universe",
    )
    
    create_result = neo4j_tools.neo4j_create_universe("CanonKeeper", data)
    assert isinstance(create_result, UniverseResponse)
    
    # Try to delete with wrong agent
    result = neo4j_tools.neo4j_delete_universe("Narrator", create_result.id)
    
    assert isinstance(result, ErrorResponse)
    assert result.code == "UNAUTHORIZED"


# ============================================================================
# Test Integration - Full Lifecycle
# ============================================================================


@pytest.mark.integration
def test_universe_lifecycle(mock_client):
    """Test full universe lifecycle: create → read → update → delete."""
    client, multiverse_id = mock_client
    
    # 1. Create
    create_data = UniverseCreate(
        multiverse_id=multiverse_id,
        name="Lifecycle Test Universe",
        description="Testing full lifecycle",
        genre="fantasy",
    )
    
    created = neo4j_tools.neo4j_create_universe("CanonKeeper", create_data)
    assert isinstance(created, UniverseResponse)
    assert created.name == "Lifecycle Test Universe"
    
    # 2. Read
    retrieved = neo4j_tools.neo4j_get_universe("Narrator", created.id)
    assert isinstance(retrieved, UniverseResponse)
    assert retrieved.id == created.id
    
    # 3. Update
    update_data = UniverseUpdate(
        name="Updated Lifecycle Universe",
        tone="dark",
    )
    
    updated = neo4j_tools.neo4j_update_universe("CanonKeeper", created.id, update_data)
    assert isinstance(updated, UniverseResponse)
    assert updated.name == "Updated Lifecycle Universe"
    assert updated.tone == "dark"
    assert updated.genre == "fantasy"  # Unchanged
    
    # 4. Delete
    deleted = neo4j_tools.neo4j_delete_universe("CanonKeeper", created.id, force=False)
    assert isinstance(deleted, dict)
    assert deleted["success"] is True
    
    # 5. Verify deletion
    not_found = neo4j_tools.neo4j_get_universe("Narrator", created.id)
    assert isinstance(not_found, ErrorResponse)
    assert not_found.code == "NOT_FOUND"
