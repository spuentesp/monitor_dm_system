from unittest.mock import patch, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from monitor_ui.main import app
import pytest

client = TestClient(app)

class MockModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

@pytest.fixture(autouse=True)
def mock_ensure_omniverse():
    with patch("monitor_ui.routers.graph.neo4j_ensure_omniverse") as mock:
        yield mock

def test_graph_world_entities():
    with patch("monitor_ui.routers.graph.neo4j_list_universes") as mock_list_univ, \
         patch("monitor_ui.routers.graph.neo4j_list_entities") as mock_list_ent, \
         patch("monitor_ui.routers.graph.neo4j_list_relationships") as mock_list_rels, \
         patch("monitor_ui.routers.graph.neo4j_list_multiverses") as mock_list_multi:
        
        m_id = uuid4()
        u_id = uuid4()
        mock_list_multi.return_value = [MockModel(id=m_id, name="M1", system_name="S1")]
        mock_list_univ.return_value = [MockModel(id=u_id, multiverse_id=m_id, name="U1", genre="sci-fi", canon_level=MockModel(value="core"))]
        e_id = uuid4()
        e_id2 = uuid4()
        mock_list_ent.return_value = MagicMock(entities=[
            MockModel(id=e_id, universe_id=u_id, name="E1", entity_type="Char", description="D", state_tags=["1","2","3","4"], is_archetype=False),
            MockModel(id=e_id2, universe_id=u_id, name="E2", entity_type="Char2", description="D2", state_tags=[], is_archetype=True)
        ])
        mock_list_rels.return_value = MagicMock(relationships=[
            MockModel(relationship_id="r1", from_entity_id=e_id, to_entity_id=e_id2, rel_type="KNOWS")
        ])
        
        # Test basic
        resp = client.get("/api/graph/world")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) > 0

        # Test filters
        resp2 = client.get(f"/api/graph/world?multiverse_id={m_id}&universe_id={u_id}&entity_types=Char,Char2&related_to={e_id}")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["nodes"]) > 0

def test_graph_universe_full():
    with patch("monitor_ui.routers.graph.neo4j_list_universes") as mock_list_univ, \
         patch("monitor_ui.routers.graph.neo4j_list_entities") as mock_list_ent, \
         patch("monitor_ui.routers.graph.neo4j_list_relationships") as mock_list_rels:
        
        mock_list_univ.return_value = [
            MockModel(
                id=uuid4(), 
                name="Test Universe", 
                genre="Fantasy", 
                canon_level=MockModel(value="core")
            )
        ]
        
        ent_id1 = uuid4()
        ent_id2 = uuid4()
        mock_list_ent.return_value = MagicMock(
            entities=[
                MockModel(id=ent_id1, name="E1", entity_type="Location", description="D1", state_tags=[], is_archetype=True),
                MockModel(id=ent_id2, name="E2", entity_type="Character", description="D2", state_tags=[], is_archetype=False),
            ]
        )
        
        mock_list_rels.return_value = MagicMock(
            relationships=[
                MockModel(relationship_id="r1", from_entity_id=ent_id1, to_entity_id=ent_id2, rel_type="IN_LOCATION")
            ]
        )
        
        resp = client.get(f"/api/graph/universes/{uuid4()}/graph?entity_types=Location,Character&rel_types=IN_LOCATION")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 3
        assert len(data["edges"]) == 3

def test_graph_entity_full():
    with patch("monitor_ui.routers.graph.neo4j_list_entities") as mock_list_ent, \
         patch("monitor_ui.routers.graph.neo4j_list_relationships") as mock_list_rels, \
         patch("monitor_ui.routers.graph.neo4j_get_entity") as mock_get_ent:
        
        ent_id1 = uuid4()
        ent_id2 = uuid4()
        
        mock_list_ent.return_value = MagicMock(
            entities=[
                MockModel(id=ent_id1, name="E1", entity_type="Location", description="D1", state_tags=[], is_archetype=True)
            ]
        )
        
        mock_list_rels.return_value = MagicMock(
            relationships=[
                MockModel(relationship_id="r1", from_entity_id=ent_id1, to_entity_id=ent_id2, rel_type="IN_LOCATION")
            ]
        )
        
        mock_get_ent.return_value = MockModel(id=ent_id2, name="E2", entity_type="Character", description="D2", state_tags=[], is_archetype=False)
        
        resp = client.get(f"/api/graph/universes/{uuid4()}/graph/entity/{ent_id1}?depth=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1

def test_graph_universe_exception():
    with patch("monitor_ui.routers.graph.neo4j_list_universes") as mock_list_univ:
        mock_list_univ.side_effect = Exception("DB error")
        resp = client.get(f"/api/graph/universes/{uuid4()}/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("error") == "DB error"

def test_graph_entity_exception():
    with patch("monitor_ui.routers.graph.neo4j_get_entity") as _, \
         patch("monitor_ui.routers.graph.neo4j_list_relationships") as _, \
         patch("monitor_ui.routers.graph.neo4j_list_entities") as mock_list_ent:
        mock_list_ent.side_effect = Exception("DB error")
        resp = client.get(f"/api/graph/universes/{uuid4()}/graph/entity/{uuid4()}")
        assert resp.status_code == 200
        data = resp.json()
        print("Entity Exception Data:", data)
        assert data.get("error") == "DB error"
