import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from monitor_data.schemas.knowledge_packs import (
    KnowledgePackType,
    KnowledgePackStatus,
)
from monitor_ui.main import create_app

app = create_app()
client = TestClient(app)

@pytest.fixture
def mock_db():
    with patch("monitor_ui.routers.pack_library.mongodb_list_knowledge_packs") as mock_list, \
         patch("monitor_ui.routers.pack_library.mongodb_get_knowledge_pack") as mock_get, \
         patch("monitor_ui.routers.pack_library.mongodb_create_knowledge_pack") as mock_create, \
         patch("monitor_ui.routers.pack_library.mongodb_update_knowledge_pack") as mock_update, \
         patch("monitor_ui.routers.pack_library.mongodb_delete_knowledge_pack") as mock_delete, \
         patch("monitor_ui.routers.pack_library.mongodb_get_ingestion_job") as mock_job:
        yield mock_list, mock_get, mock_create, mock_update, mock_delete, mock_job

def test_list_packs(mock_db):
    mock_list, *_ = mock_db
    pack_id = uuid.uuid4()
    
    # We must mock the returned object which has a `.packs` attribute.
    result_mock = MagicMock()
    pack = MagicMock()
    pack.id = pack_id
    pack.name = "Test Pack"
    pack.description = "Test description"
    pack.status = KnowledgePackStatus.READY
    pack.tags = []
    
    result_mock.packs = [pack]
    mock_list.return_value = result_mock
    
    response = client.get("/api/ingest/packs")
    assert response.status_code == 200, response.json()
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(pack_id)

def test_get_pack(mock_db):
    _, mock_get, *_ = mock_db
    pack_id = uuid.uuid4()
    
    pack = MagicMock()
    pack.id = pack_id
    pack.name = "Test Pack"
    pack.description = "Test description"
    pack.status = KnowledgePackStatus.READY
    pack.tags = []
    
    mock_get.return_value = pack
    
    response = client.get(f"/api/ingest/packs/{pack_id}")
    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["id"] == str(pack_id)

def test_get_pack_not_found(mock_db):
    _, mock_get, *_ = mock_db
    pack_id = uuid.uuid4()
    mock_get.return_value = None
    
    response = client.get(f"/api/ingest/packs/{pack_id}")
    assert response.status_code == 404

def test_create_pack(mock_db):
    _, _, mock_create, *_ = mock_db
    pack_id = uuid.uuid4()
    
    pack = MagicMock()
    pack.id = pack_id
    pack.name = "New Pack"
    pack.description = "Desc"
    pack.pack_type = KnowledgePackType.CUSTOM
    pack.status = KnowledgePackStatus.READY
    pack.tags = []
    
    mock_create.return_value = pack
    
    response = client.post("/api/ingest/packs", json={"name": "New Pack", "description": "Desc"})
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["id"] == str(pack_id)
    assert data["name"] == "New Pack"

def test_delete_pack(mock_db):
    _, mock_get, _, _, mock_delete, _ = mock_db
    pack_id = uuid.uuid4()
    mock_delete.return_value = True
    
    response = client.delete(f"/api/ingest/packs/{pack_id}")
    assert response.status_code == 200, response.json()
    assert response.json()["action"] == "archived"

def test_delete_pack_not_found(mock_db):
    _, mock_get, _, _, mock_delete, _ = mock_db
    pack_id = uuid.uuid4()
    mock_delete.return_value = False
    
    response = client.delete(f"/api/ingest/packs/{pack_id}")
    assert response.status_code == 404

def test_update_pack(mock_db):
    _, mock_get, _, mock_update, _, _ = mock_db
    pack_id = uuid.uuid4()
    
    pack = MagicMock()
    pack.id = pack_id
    pack.name = "Old Name"
    pack.status = KnowledgePackStatus.READY
    pack.tags = []
    
    mock_get.return_value = pack
    
    updated_pack = MagicMock()
    updated_pack.id = pack_id
    updated_pack.name = "New Name"
    updated_pack.status = KnowledgePackStatus.READY
    updated_pack.tags = []
    
    mock_update.return_value = updated_pack
    
    response = client.put(f"/api/ingest/packs/{pack_id}", json={"name": "New Name"})
    assert response.status_code == 200, response.json()
    assert response.json()["name"] == "New Name"


def test_get_pack_entities(mock_db):
    _, mock_get, *_ = mock_db
    import uuid
    pack_id = uuid.uuid4()
    
    pack = MagicMock()
    pack.id = pack_id
    pack.name = "Test Pack"
    
    # Needs to mock entity retrieval, wait, those use mongodb_list_knowledge_pack_entities?
    # Actually, we should check which DB tools are used!
def test_put_pack(mock_db):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id)
    mock_update.return_value = MagicMock(id=pack_id)
    response = client.put(f'/api/ingest/packs/{pack_id}', json={'name': 'Updated Pack', 'description': 'Updated'})
    assert response.status_code == 200, response.json()

def test_post_promote_pack(mock_db):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, entity_archetypes=[], relationship_archetypes=[], lore_facts=[MagicMock()])
    mock_update.return_value = MagicMock(id=pack_id)
    response = client.post(f'/api/ingest/packs/{pack_id}/promote', json={'direction': 'to_axiom', 'source_index': 0})
    assert response.status_code == 200, response.json()

def test_patch_pack_entity(mock_db):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, entity_archetypes=[MagicMock(name='Entity1', type='Person', properties={})])
    mock_update.return_value = MagicMock(id=pack_id)
def test_patch_pack_relationship(mock_db):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, entity_relationships=[MagicMock(from_entity='A', to_entity='B', rel_type='KNOWS', properties={})])
    mock_update.return_value = MagicMock(id=pack_id)
    response = client.patch(f'/api/ingest/packs/{pack_id}/relationships/0', json={'from_entity': 'A', 'to_entity': 'C', 'rel_type': 'KNOWS', 'properties': {}})
    assert response.status_code == 200, response.json()

def test_post_pack_relationship(mock_db):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, entity_relationships=[])
    mock_update.return_value = MagicMock(id=pack_id)
    response = client.post(f'/api/ingest/packs/{pack_id}/relationships', json={'from_entity': 'A', 'to_entity': 'B', 'rel_type': 'KNOWS', 'properties': {}})
    assert response.status_code == 201, response.json()

def test_delete_pack_item(mock_db):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, entity_archetypes=[MagicMock()], relationship_archetypes=[MagicMock()])
    mock_update.return_value = MagicMock(id=pack_id)
    response = client.delete(f'/api/ingest/packs/{pack_id}/entities/0')
    assert response.status_code == 200, response.json()

def test_post_merge_packs(mock_db, monkeypatch):
    _, mock_get, mock_update, *_ = mock_db
    mock_get.return_value = MagicMock(id='00000000-0000-0000-0000-000000000000', entity_archetypes=[], relationship_archetypes=[], pack_type='game_system')
    mock_merge = MagicMock(return_value=MagicMock(id='11111111-1111-1111-1111-111111111111'))
    monkeypatch.setattr('monitor_ui.routers.pack_library.KnowledgePackService.merge_packs', mock_merge)
    response = client.post('/api/ingest/packs/merge', json={'pack_ids': ['00000000-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111'], 'name': 'Merged Pack', 'delete_originals': False})
    assert response.status_code == 201, response.json()

def test_post_pack(mock_db, monkeypatch):
    mock_create = MagicMock()
    mock_create.return_value = MagicMock(id='11111111-1111-1111-1111-111111111111')
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_create_knowledge_pack', mock_create)
    response = client.post('/api/ingest/packs', json={'name': 'New Pack', 'description': 'Test'})
    assert response.status_code == 201, response.json()

def test_delete_pack_unauthorized(monkeypatch):
    mock_delete = MagicMock(return_value=True)
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_delete_knowledge_pack', mock_delete)
    response = client.delete('/api/ingest/packs/00000000-0000-0000-0000-000000000000')
    assert response.status_code == 200, response.json()

def test_get_pack_export(mock_db):
    _, mock_get, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_pack = MagicMock(id=pack_id)
    mock_pack.model_dump.return_value = {'id': pack_id, 'name': 'Test', 'description': 'Desc', 'entity_archetypes': [], 'entity_relationships': [], 'pack_type': 'game_system', 'author_id': 'user', 'version': 1, 'status': 'draft', 'created_at': '2025-01-01T00:00:00Z', 'updated_at': '2025-01-01T00:00:00Z'}
    mock_get.return_value = mock_pack
    response = client.get(f'/api/ingest/packs/{pack_id}/export')
    assert response.status_code == 200, response.json()

def test_post_import_pack(monkeypatch):
    mock_create = MagicMock()
    mock_create.return_value = MagicMock(id='11111111-1111-1111-1111-111111111111')
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_create_knowledge_pack', mock_create)
    response = client.post('/api/ingest/packs/import', json={'pack': {'name': 'Imported', 'description': '', 'entity_archetypes': [], 'entity_relationships': [], 'pack_type': 'game_system', 'status': 'draft', 'version': 1}, 'exported_at': '2025-01-01T00:00:00Z', 'schema_version': '1.0'})
    assert response.status_code == 201, response.json()

def test_post_clone_pack(mock_db, monkeypatch):
    _, mock_get, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_pack = MagicMock(id=pack_id, name='Test', description='Desc', pack_type='game_system', game_system_id=None, game_system_data=None, system_name='test', tags=[], axioms=[], entity_archetypes=[], lore_facts=[], entity_relationships=[], random_tables=[], agendas=[], topologies=[], tone_profiles=[])
    mock_pack.model_dump.return_value = {'id': pack_id, 'name': 'Test', 'description': 'Desc', 'entity_archetypes': [], 'entity_relationships': [], 'pack_type': 'game_system', 'author_id': 'user', 'version': 1, 'status': 'draft', 'created_at': '2025-01-01T00:00:00Z', 'updated_at': '2025-01-01T00:00:00Z'}
    mock_get.return_value = mock_pack
    mock_create = MagicMock()
    mock_create.return_value = MagicMock(id='11111111-1111-1111-1111-111111111111')
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_create_knowledge_pack', mock_create)
    response = client.post(f'/api/ingest/packs/{pack_id}/clone', json={'name': 'Clone'})
    assert response.status_code == 201, response.json()

def test_post_slice_pack(mock_db, monkeypatch):
    _, mock_get, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_pack = MagicMock(id=pack_id, name='Test', description='Desc', pack_type='game_system', game_system_id=None, system_name='test', tags=[], axioms=[], entity_archetypes=[{'name': 'E1', 'entity_type': 'Person'}], lore_facts=[], entity_relationships=[], random_tables=[], agendas=[], topologies=[], tone_profiles=[])
    mock_pack.model_dump.return_value = {'id': pack_id, 'name': 'Test', 'description': 'Desc', 'entity_archetypes': [{'name': 'E1', 'entity_type': 'Person', 'properties': {}}], 'entity_relationships': [], 'pack_type': 'game_system', 'author_id': 'user', 'version': 1, 'status': 'draft', 'created_at': '2025-01-01T00:00:00Z', 'updated_at': '2025-01-01T00:00:00Z'}
    mock_get.return_value = mock_pack
    mock_create = MagicMock()
    mock_create.return_value = MagicMock(id='11111111-1111-1111-1111-111111111111')
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_create_knowledge_pack', mock_create)
    response = client.post(f'/api/ingest/packs/{pack_id}/slice', json={'entity_indices': [0], 'relationship_indices': [], 'name': 'Slice'})
    assert response.status_code == 201, response.json()

def test_post_apply_new_world(monkeypatch, mock_db):
    _, mock_get, *_ = mock_db
    mock_get.return_value = MagicMock(id='00000000-0000-0000-0000-000000000000', status='draft', game_system_id=None)
    mock_create_setting = MagicMock(return_value=('11111111-1111-1111-1111-111111111111', '11111111-1111-1111-1111-111111111111'))
    monkeypatch.setattr('monitor_ui.routers.pack_library._create_setting', mock_create_setting)
    mock_apply = AsyncMock(return_value={'proposals_created': 0, 'committed': 0, 'errors': []})
    monkeypatch.setattr('monitor_ui.routers.pack_library.CanonKeeper.apply_pack_to_universe', mock_apply)
    response = client.post('/api/ingest/packs/00000000-0000-0000-0000-000000000000/apply/new-world', json={'world_name': 'Test World'})
    assert response.status_code == 201, response.json()

def test_post_apply_universe(monkeypatch):
    mock_apply = AsyncMock(return_value={'proposals_created': 0, 'committed': 0, 'errors': []})
    monkeypatch.setattr('monitor_ui.routers.pack_library.KnowledgePackService.apply_pack_to_existing_world', mock_apply)
    response = client.post('/api/ingest/packs/00000000-0000-0000-0000-000000000000/apply/11111111-1111-1111-1111-111111111111', json={'mode': 'full'})
    assert response.status_code == 200, response.json()

def test_get_proposals(monkeypatch, mock_db):
    _, mock_get, *_ = mock_db
    mock_get.return_value = MagicMock()
    mock_list = MagicMock()
    mock_list.return_value = MagicMock(proposed_changes=[])
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_list_proposed_changes', mock_list)
    mock_mongo = MagicMock()
    mock_mongo.return_value.get_collection.return_value.count_documents = MagicMock(return_value=0)
    monkeypatch.setattr('monitor_data.db.mongodb.get_mongodb_client', mock_mongo)
    response = client.get('/api/ingest/packs/00000000-0000-0000-0000-000000000000/proposals')
    assert response.status_code == 200, response.json()

def test_patch_proposal(monkeypatch):
    mock_update = MagicMock()
    mock_update.proposal_id = '22222222-2222-2222-2222-222222222222'
    mock_update.status.value = 'accepted'
    mock_update.decision_metadata.decided_by = 'user'
    mock_update.decision_metadata.decided_at.isoformat.return_value = '2025-01-01T00:00:00Z'
    mock_update.decision_metadata.reason = 'OK'
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_update_proposed_change', MagicMock(return_value=mock_update))
    response = client.patch('/api/ingest/proposals/22222222-2222-2222-2222-222222222222', json={'action': 'accept'})
    assert response.status_code == 200, response.json()

def test_post_proposals_batch(monkeypatch):
    mock_update = MagicMock()
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_update_proposed_change', mock_update)
    response = client.post('/api/ingest/proposals/batch', json={'actions': [{'proposal_id': '22222222-2222-2222-2222-222222222222', 'action': 'accept', 'reason': 'OK'}]})
    assert response.status_code == 200, response.json()

def test_put_pack_full_lists(mock_db, monkeypatch):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, status=MagicMock(value='draft'))
    mock_update.return_value = MagicMock(id=pack_id)
    payload = {
        'axioms': [{'statement': 'A', 'domain': 'general'}],
        'entity_archetypes': [{'name': 'E', 'entity_type': 'person'}],
        'lore_facts': [{'statement': 'L'}],
        'entity_relationships': [{'from_entity': 'A', 'to_entity': 'B', 'rel_type': 'knows'}],
        'random_tables': [{'name': 'R', 'entries': []}],
        'agendas': [{'title': 'A', 'description': 'desc'}],
        'topologies': [{'from_location': 'A', 'to_location': 'B'}],
        'tone_profiles': [{'name': 'T', 'instruction': 'inst'}],
        'tags': ['tag1'],
        'plot_threads': [{'title': 'P', 'description': 'desc'}]
    }
    response = client.put(f'/api/ingest/packs/{pack_id}', json=payload)
    assert response.status_code == 200, response.json()

def test_assert_pack_not_building(mock_db, monkeypatch):
    _, mock_get, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, ingestion_job_id='job1')
    mock_job = MagicMock(status=MagicMock(value='running'))
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_get_ingestion_job', MagicMock(return_value=mock_job))
    response = client.put(f'/api/ingest/packs/{pack_id}', json={'name': 'fail'})
    assert response.status_code == 409

def test_post_promote_to_lore(mock_db):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, axioms=[MagicMock(statement='A')], lore_facts=[], status=MagicMock(value='draft'))
    mock_update.return_value = MagicMock(id=pack_id)
    response = client.post(f'/api/ingest/packs/{pack_id}/promote', json={'direction': 'to_lore', 'source_index': 0})
    assert response.status_code == 200

def test_patch_entity_archetype(mock_db):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_entity = MagicMock()
    mock_entity.model_dump.return_value = {'name': 'E', 'entity_type': 'person'}
    mock_get.return_value = MagicMock(id=pack_id, entity_archetypes=[mock_entity], status=MagicMock(value='draft'))
    mock_update.return_value = MagicMock(id=pack_id)
    response = client.patch(f'/api/ingest/packs/{pack_id}/entities/0', json={'name': 'E2'})
    assert response.status_code == 200

def test_patch_relationship(mock_db):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_rel = MagicMock()
    mock_rel.model_dump.return_value = {'from_entity': 'A', 'to_entity': 'B', 'rel_type': 'knows'}
    mock_get.return_value = MagicMock(id=pack_id, entity_relationships=[mock_rel], status=MagicMock(value='draft'))
    mock_update.return_value = MagicMock(id=pack_id)
    response = client.patch(f'/api/ingest/packs/{pack_id}/relationships/0', json={'rel_type': 'hates'})
    assert response.status_code == 200

def test_post_commit_pack(mock_db, monkeypatch):
    _, mock_get, mock_update, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, status=MagicMock(value='draft'))
    mock_update.return_value = MagicMock(id=pack_id)
    
    mock_keeper = AsyncMock()
    mock_keeper.commit_accepted.return_value = {'committed': 5, 'errors': []}
    monkeypatch.setattr('monitor_ui.routers.pack_library.CanonKeeper', MagicMock(return_value=mock_keeper))
    
    response = client.post(f'/api/ingest/packs/{pack_id}/commit')
    assert response.status_code == 200, response.json()



def test_put_pack_invalid_data(mock_db):
    _, mock_get, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, status=MagicMock(value='draft'))
    payload2 = {'axioms': [{}]} # missing statement
    response = client.put(f'/api/ingest/packs/{pack_id}', json=payload2)
    assert response.status_code == 422

def test_delete_pack_endpoint(mock_db):
    _, mock_get, _, mock_delete, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, status=MagicMock(value='draft'))
    response = client.delete(f'/api/ingest/packs/{pack_id}')
    assert response.status_code == 200

def test_post_new_pack_endpoint(mock_db, monkeypatch):
    mock_create = MagicMock(return_value=MagicMock(id='00000000-0000-0000-0000-000000000000'))
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_create_knowledge_pack', mock_create)
    response = client.post('/api/ingest/packs', json={'name': 'New Pack', 'description': 'Desc', 'pack_type': 'misc'})
    assert response.status_code == 201

def test_post_merge_packs_with_strategy(mock_db, monkeypatch):
    mock_create = MagicMock(return_value=MagicMock(id='00000000-0000-0000-0000-000000000000'))
    monkeypatch.setattr('monitor_ui.routers.pack_library.mongodb_create_knowledge_pack', mock_create)
    _, mock_get, *_ = mock_db
    mock_get.return_value = MagicMock(id='00000000-0000-0000-0000-000000000000', axioms=[MagicMock(statement='A')])
    
    mock_merge = MagicMock(return_value=MagicMock(id='00000000-0000-0000-0000-000000000000', name='Merged Pack', description='', intro_text='', pack_type=KnowledgePackType.MISC, status=KnowledgePackStatus.PENDING, tags=[], source_document_ids=[], ingestion_job_id=None, parent_pack_ids=[], created_at=datetime.now(), updated_at=datetime.now()))
    monkeypatch.setattr('monitor_ui.routers.pack_library.KnowledgePackService.merge_packs', mock_merge)
    
    response = client.post('/api/ingest/packs/merge', json={'pack_ids': ['00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000001'], 'name': 'Merged Pack', 'strategy': 'union'})
    assert response.status_code == 201

def test_all_uncovered_endpoints(mock_db, monkeypatch):
    _, mock_get, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_service = MagicMock()
    mock_service.promote_pack = AsyncMock()
    mock_service.clone_pack = AsyncMock()
    mock_service.slice_pack = AsyncMock()
    mock_service.apply_pack_to_new_world = AsyncMock()
    mock_service.apply_pack_to_existing_world = AsyncMock()
    monkeypatch.setattr('monitor_ui.routers.pack_library.KnowledgePackService', mock_service)
    
    mock_pack = MagicMock()
    mock_pack.entities = []
    mock_pack.relationships = []
    mock_get.return_value = mock_pack

    # promote
    client.post(f'/api/ingest/packs/{pack_id}/promote', json={'direction': 'to_axiom', 'source_index': 0})
    client.post(f'/api/ingest/packs/{pack_id}/promote', json={'direction': 'invalid', 'source_index': 0})
    
    # entities patch
    client.patch(f'/api/ingest/packs/{pack_id}/entities/0', json={'name': 'new'})
    
    # relationships patch
    client.patch(f'/api/ingest/packs/{pack_id}/relationships/0', json={'rel_type': 'new'})
    
    # relationships post
    client.post(f'/api/ingest/packs/{pack_id}/relationships', json={'from_entity': 'a', 'target': 'b', 'rel_type': 'rel', 'to_entity': 'b'})
    
    # entities delete
    client.delete(f'/api/ingest/packs/{pack_id}/entities/0')
    
    # export
    client.get(f'/api/ingest/packs/{pack_id}/export')
    
    # clone
    client.post(f'/api/ingest/packs/{pack_id}/clone', json={'new_name': 'cloned'})
    
    # slice
    client.post(f'/api/ingest/packs/{pack_id}/slice', json={'entity_names': ['A'], 'new_name': 'slice'})
    
    # apply/new-world
    client.post(f'/api/ingest/packs/{pack_id}/apply/new-world', json={'name': 'New World', 'universe_name': 'U'})
    
    # apply/universe
    client.post(f'/api/ingest/packs/{pack_id}/apply/00000000-0000-0000-0000-000000000000')
    
    # kgs
    client.get('/api/ingest/kgs')
    client.post('/api/ingest/kgs', json={'name': 'KG'})
    
    # proposals
    client.get(f'/api/ingest/packs/{pack_id}/proposals')
    client.patch('/api/ingest/proposals/00000000-0000-0000-0000-000000000000', json={'action': 'accept'})
    client.post('/api/ingest/proposals/batch', json={'proposal_ids': [], 'action': 'accept'})
    
    client.post('/api/ingest/packs/import', json={'data': {}})

def test_put_pack_invalid_exceptions(mock_db):
    _, mock_get, *_ = mock_db
    pack_id = '00000000-0000-0000-0000-000000000000'
    mock_get.return_value = MagicMock(id=pack_id, status=MagicMock(value='draft'))

    def check_422(payload):
        resp = client.put(f'/api/ingest/packs/{pack_id}', json=payload)
        assert resp.status_code == 422
        
    check_422({'status': 'invalid'})
    check_422({'entity_archetypes': [{}]})
    check_422({'lore_facts': [{}]})
    check_422({'entity_relationships': [{}]})
    check_422({'random_tables': [{}]})
    check_422({'agendas': [{}]})
    check_422({'topologies': [{}]})
    check_422({'tone_profiles': [{}]})
    check_422({'character_profiles': [{}]})
    check_422({'generation_templates': [{}]})
    check_422({'chunk_summaries': [{}]})
    check_422({'section_summaries': [{}]})
    check_422({'game_system_id': 'invalid'})
    check_422({'plot_threads': [{}]})
    check_422({'source_document_ids': ['invalid']})
    
    # 404
    mock_get.return_value = None
    resp = client.put(f'/api/ingest/packs/{pack_id}', json={'name': 'new'})
    assert resp.status_code == 404
