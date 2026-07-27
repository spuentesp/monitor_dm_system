import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from monitor_ui.main import app
from monitor_data.db.postgres import PostgresClient

client = TestClient(app)

@pytest.fixture
def mock_postgres():
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client") as mock_get_pg:
        mock_pg = MagicMock(spec=PostgresClient)
        mock_get_pg.return_value = mock_pg
        yield mock_pg

def test_list_providers(mock_postgres):
    mock_postgres.providers_list.return_value = [
        {
            "id": "p1",
            "name": "Test Provider",
            "provider": "openai",
            "model": "gpt-4",
            "api_key": "test_key",
            "base_url": None,
            "status": "connected",
            "latency_ms": 100,
            "is_default": True,
            "role": "standard"
        }
    ]
    
    with patch("monitor_ui.routers.llm_mgmt._seeded", True):
        response = client.get("/api/llm/providers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "p1"
        assert data[0]["api_key_masked"] == "••••••••"

def test_add_provider(mock_postgres):
    mock_postgres.providers_list.return_value = []
    
    response = client.post("/api/llm/providers", json={
        "name": "New Provider",
        "provider": "anthropic",
        "model": "claude-3",
        "api_key": "new_key",
        "base_url": "https://test",
        "is_default": False,
        "role": "heavy"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Provider"
    assert data["provider"] == "anthropic"
    assert "id" in data
    mock_postgres.provider_upsert.assert_called_once()

def test_update_provider(mock_postgres):
    mock_postgres.provider_get.return_value = {
        "id": "p1",
        "name": "Old Provider",
        "provider": "openai",
        "model": "gpt-4",
        "api_key": "old_key",
        "is_default": False
    }
    
    response = client.put("/api/llm/providers/p1", json={
        "name": "Updated Provider",
        "is_default": True
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Provider"
    assert data["is_default"] is True
    mock_postgres.provider_upsert.assert_called_once()
    mock_postgres.provider_set_default.assert_called_once_with("p1")

def test_update_provider_not_found(mock_postgres):
    mock_postgres.provider_get.return_value = None
    response = client.put("/api/llm/providers/p1", json={"name": "Updated"})
    assert response.status_code == 404

def test_delete_provider(mock_postgres):
    response = client.delete("/api/llm/providers/p1")
    assert response.status_code == 204
    mock_postgres.provider_delete.assert_called_once_with("p1")

def test_duplicate_provider(mock_postgres):
    mock_postgres.provider_get.return_value = {
        "id": "p1",
        "name": "Original",
        "provider": "openai",
        "model": "gpt-4",
        "role": "standard"
    }
    
    response = client.post("/api/llm/providers/p1/duplicate", json={
        "name": "Copy",
        "role": "heavy"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Copy"
    assert data["role"] == "heavy"
    mock_postgres.provider_upsert.assert_called_once()

def test_duplicate_provider_not_found(mock_postgres):
    mock_postgres.provider_get.return_value = None
    response = client.post("/api/llm/providers/p1/duplicate")
    assert response.status_code == 404

def test_list_node_assignments(mock_postgres):
    mock_postgres.node_assignments_list.return_value = [
        {
            "node_name": "test_node",
            "provider_id": "p1",
            "param_overrides": {},
            "notes": "Test"
        }
    ]
    response = client.get("/api/llm/assignments")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["node_name"] == "test_node"

def test_upsert_node_assignment(mock_postgres):
    mock_postgres.node_assignment_get.return_value = {
        "node_name": "test_node",
        "provider_id": "p1",
        "param_overrides": {},
        "notes": "Notes"
    }
    
    response = client.put("/api/llm/assignments/test_node", json={
        "provider_id": "p1",
        "notes": "Notes"
    })
    assert response.status_code == 200
    mock_postgres.node_assignment_set.assert_called_once()

def test_upsert_node_assignment_not_found_after(mock_postgres):
    mock_postgres.node_assignment_get.return_value = None
    response = client.put("/api/llm/assignments/test_node", json={"provider_id": "p1"})
    assert response.status_code == 404

def test_delete_node_assignment(mock_postgres):
    response = client.delete("/api/llm/assignments/test_node")
    assert response.status_code == 204
    mock_postgres.node_assignment_delete.assert_called_once_with("test_node")

@pytest.mark.asyncio
async def test_test_provider_anthropic(mock_postgres):
    mock_postgres.provider_get.return_value = {
        "id": "p1",
        "provider": "anthropic",
        "model": "claude-3",
        "api_key": "test_key",
        "base_url": None
    }
    
    class MockResponse:
        def raise_for_status(self): pass
        def json(self): return {"content": [{"text": "ok"}]}
    
    with patch("httpx.AsyncClient.post", return_value=MockResponse()):
        response = client.post("/api/llm/providers/p1/test")
        assert response.status_code == 200
        assert response.json()["ok"] is True
        mock_postgres.provider_upsert.assert_called_once()

def test_test_provider_not_found(mock_postgres):
    mock_postgres.provider_get.return_value = None
    response = client.post("/api/llm/providers/p1/test")
    assert response.status_code == 404
