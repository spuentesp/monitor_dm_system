from unittest.mock import patch, MagicMock
from uuid import uuid4
from datetime import datetime
from fastapi.testclient import TestClient
from monitor_ui.main import app

client = TestClient(app)

class MockModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
            
    def model_dump(self, mode=None):
        return {k: v for k, v in self.__dict__.items()}

def test_get_game_systems():
    with patch("monitor_ui.routers.game_systems.mongodb_list_game_systems") as mock_list:
        sys_id = uuid4()
        m = MockModel(
            id=sys_id, 
            name="System 1", 
            description="desc",
            version="1",
            is_builtin=False,
            source_document_id=None,
            rules=[],
            attributes=[],
            skills=[],
            resources=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        mock_list.return_value = MagicMock(systems=[m], total=1, limit=50, offset=0)
        
        resp = client.get("/api/systems")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["systems"]) == 1
        assert data["systems"][0]["name"] == "System 1"

def test_get_game_systems_error():
    with patch("monitor_ui.routers.game_systems.mongodb_list_game_systems", side_effect=Exception("DB Error")):
        resp = client.get("/api/systems")
        assert resp.status_code == 503
