from unittest.mock import patch, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from monitor_ui.main import app

client = TestClient(app)

class MockModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
            
def test_forge_demo_world_full():
    with patch("monitor_data.tools.mongodb_tools.mongodb_list_game_systems") as mock_list_systems, \
         patch("monitor_data.tools.mongodb_tools.mongodb_get_game_system") as mock_get_system, \
         patch("monitor_data.tools.neo4j_tools.neo4j_ensure_omniverse") as mock_ensure, \
         patch("monitor_data.tools.neo4j_tools.neo4j_list_universes") as mock_list_univ, \
         patch("monitor_data.tools.neo4j_tools.neo4j_create_multiverse") as mock_create_mv, \
         patch("monitor_data.tools.neo4j_tools.neo4j_create_universe") as mock_create_univ, \
         patch("monitor_data.tools.neo4j_tools.entities.neo4j_list_entities") as mock_list_ent, \
         patch("monitor_data.tools.neo4j_tools.entities.neo4j_create_entity") as mock_create_ent, \
         patch("monitor_data.tools.neo4j_tools.stories.neo4j_list_stories") as mock_list_stories, \
         patch("monitor_data.tools.neo4j_tools.stories.neo4j_create_story") as mock_create_story, \
         patch("monitor_ui.routers.chat.create_session") as mock_create_session, \
         patch("anyio.to_thread.run_sync") as mock_run_sync:
        
        mock_ensure.return_value = {"omniverse_id": str(uuid4())}
        
        mock_systems = [MockModel(id=uuid4(), name="Mistlands Core", is_active=True)]
        mock_list_systems.return_value = MagicMock(systems=mock_systems)
        mock_get_system.return_value = MagicMock(model_dump=lambda mode: {})
        
        mock_list_univ.return_value = []
        mock_create_mv.return_value = MockModel(id=uuid4())
        mock_create_univ.return_value = MockModel(id=uuid4())
        
        mock_list_ent.return_value = MagicMock(entities=[])
        mock_create_ent.return_value = MockModel(id=uuid4())
        
        mock_list_stories.return_value = []
        mock_create_story.return_value = MockModel(id=uuid4())
        
        mock_create_session.return_value = MockModel(id=str(uuid4()))
        
        async def fake_run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)
        mock_run_sync.side_effect = fake_run_sync
        
        resp = client.post("/api/forge/demo-world", json={"world_name": "Test World", "game_system_id": str(uuid4()), "start_session": True})
        assert resp.status_code == 200
