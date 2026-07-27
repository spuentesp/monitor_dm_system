import pytest
import uuid
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from monitor_ui.main import app

client = TestClient(app)

@pytest.fixture
def mock_db():
    with patch("monitor_ui.routers.ingest.mongodb_list_ingestion_jobs") as mock_jobs, \
         patch("monitor_ui.routers.ingest.mongodb_list_documents") as mock_docs, \
         patch("monitor_ui.routers.ingest.get_mongodb_client") as mock_client:
        yield mock_jobs, mock_docs, mock_client

def test_force_unlock_ingest(mock_db):
    _, _, mock_client = mock_db
    mock_coll = MagicMock()
    mock_coll.update_many.return_value.modified_count = 1
    mock_client.return_value.get_collection.return_value = mock_coll
    
    response = client.post("/api/ingest/unlock")
    assert response.status_code == 200
    assert response.json()["unlocked"] is True
    assert response.json()["recovered_jobs"] == 1

def test_list_sources(mock_db):
    mock_jobs, mock_docs, _ = mock_db
    job = MagicMock()
    job.source_id = uuid.uuid4()
    job.job_id = uuid.uuid4()
    job.status.value = "pending"
    job.source_title = "Test Job"
    mock_jobs.return_value.jobs = [job]
    mock_docs.return_value = []
    
    response = client.get("/api/ingest/sources")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(job.source_id)

def test_get_source(mock_db):
    mock_jobs, mock_docs, _ = mock_db
    job = MagicMock()
    source_id = uuid.uuid4()
    job.source_id = source_id
    job.job_id = uuid.uuid4()
    job.status.value = "pending"
    mock_jobs.return_value.jobs = [job]
    
    response = client.get(f"/api/ingest/sources/{source_id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(source_id)

def test_get_source_not_found(mock_db):
    mock_jobs, mock_docs, _ = mock_db
    mock_jobs.return_value.jobs = []
    mock_docs.return_value = []
    
    response = client.get(f"/api/ingest/sources/{uuid.uuid4()}")
    assert response.status_code == 404
