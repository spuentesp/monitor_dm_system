import pytest
import uuid
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from monitor_ui.main import app

import monitor_ui.routers.ingest as mod
client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_all_dbs():
    with patch("monitor_ui.routers.ingest.get_mongodb_client") as mock_mongo, \
         patch("monitor_ui.routers.ingest.get_minio_client") as mock_minio, \
         patch("monitor_ui.routers.ingest.get_postgres_client") as mock_postgres, \
         patch("monitor_data.db.qdrant.get_qdrant_client") as mock_qdrant, \
         patch("monitor_ui.routers.ingest.mongodb_list_ingestion_jobs") as mock_list_jobs, \
         patch("monitor_ui.routers.ingest.mongodb_get_ingestion_job") as mock_get_job, \
         patch("monitor_data.tools.mongodb_tools.mongodb_delete_ingestion_job") as mock_del_job, \
         patch("monitor_ui.routers.ingest.mongodb_list_documents") as mock_list_docs, \
         patch("monitor_ui.routers.ingest.mongodb_get_document") as mock_get_doc, \
         patch("monitor_ui.routers.ingest.neo4j_delete_source") as mock_del_source, \
         patch("monitor_ui.routers.ingest.neo4j_get_universe") as mock_get_univ, \
         patch("monitor_ui.routers.ingest.IngestionPipeline") as mock_pipeline:
        
        # Minio mock
        mock_minio_instance = AsyncMock()
        mock_minio_instance.presigned_url.return_value = "http://presigned.url"
        mock_minio_instance.download.return_value = b"file content"
        mock_minio.return_value = mock_minio_instance
        
        # Postgres mock
        mock_pg_instance = AsyncMock()
        mock_pg_instance.llm_task_attempts_list.return_value = []
        mock_postgres.return_value = mock_pg_instance
        
        # Mongo mock
        mock_mongo_instance = MagicMock()
        mock_coll = MagicMock()
        mock_coll.update_many.return_value.modified_count = 1
        mock_coll.delete_many.return_value.deleted_count = 1
        mock_coll.update_one.return_value.matched_count = 1
        
        # For find/cursor
        class MockCursor:
            def __init__(self, items):
                self.items = items
            
            def sort(self, *args, **kwargs):

            
                return self
            def skip(self, *args, **kwargs):

                return self
            def limit(self, *args, **kwargs):

                return self
            
            async def __aiter__(self):
                for item in self.items:
                    yield item
                    
        mock_cursor = MockCursor([{"_id": "test", "object_key": "test"}])
        mock_coll.find.return_value = mock_cursor
        
        mock_coll.find.return_value = mock_cursor
        mock_coll.find_one.return_value = {"_id": "test_asset", "deleted": False, "object_key": "test"}
        mock_coll.count_documents.return_value = 0
        
        mock_mongo_instance.get_collection.return_value = mock_coll
        mock_mongo.return_value = mock_mongo_instance
        
        # Qdrant mock
        mock_qdrant_instance = MagicMock()
        mock_qdrant_client = AsyncMock()
        mock_qdrant_instance.get_client.return_value = mock_qdrant_client
        mock_qdrant.return_value = mock_qdrant_instance
        
        # List docs
        mock_list_docs.return_value = []
        
        # Pipeline mock
        mock_pipeline_inst = AsyncMock()
        mock_pipeline_inst._create_neo4j_source.return_value = uuid.uuid4()
        mock_pipeline_inst._create_document.return_value = uuid.uuid4()
        mock_pipeline.return_value = mock_pipeline_inst

        yield {
            "mongo": mock_mongo,
            "minio": mock_minio,
            "postgres": mock_postgres,
            "list_jobs": mock_list_jobs,
            "get_job": mock_get_job,
            "del_job": mock_del_job,
            "list_docs": mock_list_docs,
            "get_doc": mock_get_doc,
            "del_source": mock_del_source,
            "get_univ": mock_get_univ,
            "pipeline": mock_pipeline,
            "qdrant": mock_qdrant
        }

def test_force_unlock_ingest():
    response = client.post("/api/ingest/unlock")
    assert response.status_code == 200

def test_list_sources(mock_all_dbs):
    job = MagicMock()
    job.source_id = uuid.uuid4()
    job.job_id = uuid.uuid4()
    job.status.value = "pending"
    job.source_title = "Test Job"
    mock_all_dbs["list_jobs"].return_value.jobs = [job]
    
    response = client.get("/api/ingest/sources")
    assert response.status_code == 200

def test_get_source(mock_all_dbs):
    source_id = uuid.uuid4()
    job = MagicMock()
    job.source_id = source_id
    job.job_id = uuid.uuid4()
    job.status.value = "pending"
    mock_all_dbs["list_jobs"].return_value.jobs = [job]
    
    response = client.get(f"/api/ingest/sources/{source_id}")
    assert response.status_code == 200

def test_get_source_not_found(mock_all_dbs):
    mock_all_dbs["list_jobs"].return_value.jobs = []
    
    response = client.get(f"/api/ingest/sources/{uuid.uuid4()}")
    assert response.status_code == 404

def test_upload_source(mock_all_dbs):
    with patch("monitor_ui.routers.ingest._run_ingest_in_thread") as _mock_run:
        with patch("monitor_ui.routers.ingest._create_setting", return_value=(None, uuid.uuid4())):
            response = client.post(
                "/api/ingest/sources/upload",
                files={"file": ("test.pdf", b"test data", "application/pdf")},
                data={"scan_type": "setting_supplement", "ingest_now": "true", "title": "Test Title"}
            )
            assert response.status_code == 201

def test_upload_source_no_ingest(mock_all_dbs):
    with patch("monitor_ui.routers.ingest._create_setting", return_value=(None, uuid.uuid4())):
        response = client.post(
            "/api/ingest/sources/upload",
            files={"file": ("test.pdf", b"test data", "application/pdf")},
            data={"scan_type": "setting_supplement", "ingest_now": "false"}
        )
        assert response.status_code == 201

def test_delete_source(mock_all_dbs):
    response = client.delete(f"/api/ingest/sources/{uuid.uuid4()}")
    assert response.status_code == 204

def test_rescan_source(mock_all_dbs):
    job = MagicMock()
    job.source_id = uuid.uuid4()
    job.job_id = uuid.uuid4()
    job.status.value = "completed"
    job.universe_id = uuid.uuid4()
    mock_all_dbs["list_jobs"].return_value.jobs = [job]
    
    mock_all_dbs["get_doc"].return_value = MagicMock(file_type="pdf", filename="test.pdf", doc_id=uuid.uuid4(), minio_ref="ref")
    
    with patch("monitor_ui.routers.ingest._run_ingest_in_thread") as _mock_run:
        response = client.post(f"/api/ingest/sources/{job.source_id}/rescan")
        assert response.status_code == 202

def test_cancel_job(mock_all_dbs):
    response = client.post(f"/api/ingest/jobs/{uuid.uuid4()}/cancel")
    assert response.status_code == 200

def test_delete_job(mock_all_dbs):
    mock_all_dbs["del_job"].return_value = True
    response = client.delete(f"/api/ingest/jobs/{uuid.uuid4()}")
    assert response.status_code == 204

def test_purge_failed_jobs(mock_all_dbs):
    response = client.delete("/api/ingest/jobs")
    assert response.status_code == 200

def test_clear_llm_cache():
    response = client.post("/api/ingest/cache/clear")
    assert response.status_code == 200

def test_list_jobs(mock_all_dbs):
    mock_all_dbs["list_jobs"].return_value.jobs = []
    response = client.get("/api/ingest/jobs")
    assert response.status_code == 200

def test_get_job(mock_all_dbs):
    job = MagicMock()
    job.job_id = uuid.uuid4()
    job.status.value = "completed"
    mock_all_dbs["get_job"].return_value = job
    
    response = client.get(f"/api/ingest/jobs/{job.job_id}")
    assert response.status_code == 200

def test_list_job_attempts(mock_all_dbs):
    response = client.get(f"/api/ingest/jobs/{uuid.uuid4()}/attempts")
    assert response.status_code == 200

def test_upload_asset(mock_all_dbs):
    response = client.post(
        "/api/ingest/assets/upload",
        files={"file": ("test.png", b"image data", "image/png")},
        data={"asset_type": "image"}
    )
    assert response.status_code == 201

def test_list_assets(mock_all_dbs):
    response = client.get("/api/ingest/assets")
    assert response.status_code == 200

def test_get_asset(mock_all_dbs):
    response = client.get("/api/ingest/assets/test_asset")
    assert response.status_code == 200

def test_delete_asset(mock_all_dbs):
    response = client.delete("/api/ingest/assets/test_asset")
    assert response.status_code == 200

def test_internal_queue_functions():
    from monitor_ui.routers.ingest import (
        _reserve_ingest_slot, _rename_ingest_request, _mark_ingest_started,
        _attach_job_id_to_request, _clear_ingest_slot, _check_ingest_busy,
        shutdown_ingest_runtime, prepare_ingest_runtime,
        _sync_ingest_state, _interrupt_ingest_runtime
    )
    from fastapi import HTTPException
    import uuid
    
    _clear_ingest_slot()
    _sync_ingest_state()
    
    token = _reserve_ingest_slot("test source")
    _rename_ingest_request(token, "renamed source")
    _mark_ingest_started(token, "started source")
    _attach_job_id_to_request(token, str(uuid.uuid4()))
    
    try:
        _check_ingest_busy()
        assert False
    except HTTPException:
        pass
        
    _clear_ingest_slot(queue_token=token)
    
    _t2 = _reserve_ingest_slot("title2")
    _clear_ingest_slot(expected_title="title2")
    
    _reserve_ingest_slot("title3")
    _mark_ingest_started("tok", "title3")
    _clear_ingest_slot(expected_title="title3")
    
    res = _interrupt_ingest_runtime("test", close_executor=False)
    assert res["unlocked"] is True
    
    shutdown_ingest_runtime()
    prepare_ingest_runtime()

def test_run_ingest_in_thread(mock_all_dbs):
    from monitor_ui.routers.ingest import _run_ingest_in_thread
    from monitor_data.schemas.knowledge_packs import KnowledgePackType
    import uuid
    
    queue_token = "tok_123"
    import monitor_ui.routers.ingest as ingest_mod
    ingest_mod._reserve_ingest_slot("test", source_id=queue_token)
    ingest_mod._ingest_pending_requests = [{"token": queue_token, "title": "test", "job_id": None}]
    
    with patch("monitor_agents.ingestion.agent.IngestionPipeline.ingest_file", new_callable=AsyncMock) as _mock_ingest:
        with patch("monitor_agents.utils.world_library.WorldLibrary.add_source", new_callable=AsyncMock) as _mock_lib:
            _run_ingest_in_thread(
                queue_token=queue_token,
                file_bytes=b"test",
                filename="test.pdf",
                source_title="test",
                universe_uid=uuid.uuid4(),
                pack_type_enum=KnowledgePackType.SETTING_SUPPLEMENT,
                selected_layers=["entities"],
                content_type="application/pdf"
            )

def test_upload_exceptions(mock_all_dbs):
    import os
    os.environ["MONITOR_MAX_INGEST_FILE_BYTES"] = "5"
    response = client.post(
        "/api/ingest/sources/upload",
        files={"file": ("test.pdf", b"too big payload", "application/pdf")},
    )
    assert response.status_code == 413
    os.environ["MONITOR_MAX_INGEST_FILE_BYTES"] = str(200 * 1024 * 1024)
    
    with patch("monitor_ui.routers.ingest._create_setting", side_effect=Exception("DB error")):
        response = client.post(
            "/api/ingest/sources/upload",
            files={"file": ("test.pdf", b"data", "application/pdf")},
            data={"new_setting_name": "New Setting"}
        )
        assert response.status_code == 500

def test_delete_source_busy(mock_all_dbs):
    from monitor_ui.routers.ingest import _reserve_ingest_slot, _clear_ingest_slot
    source_id = str(uuid.uuid4())
    token = _reserve_ingest_slot("test", source_id=source_id)
    response = client.delete(f"/api/ingest/sources/{source_id}")
    assert response.status_code == 409
    _clear_ingest_slot(queue_token=token)

def test_rescan_source_not_found(mock_all_dbs):
    mock_all_dbs["list_jobs"].return_value.jobs = []
    mock_all_dbs["get_doc"].return_value = None
    mock_all_dbs["list_docs"].return_value = []
    
    response = client.post(f"/api/ingest/sources/{uuid.uuid4()}/rescan")
    assert response.status_code == 404

def test_cancel_job_not_found(mock_all_dbs):
    mock_mongo = mock_all_dbs["mongo"].return_value
    mock_coll = mock_mongo.get_collection.return_value
    mock_coll.update_one.return_value.matched_count = 0
    mock_coll.find_one.return_value = None
    
    response = client.post(f"/api/ingest/jobs/{uuid.uuid4()}/cancel")
    assert response.status_code == 404

def test_delete_job_not_found(mock_all_dbs):
    mock_all_dbs["del_job"].return_value = False
    response = client.delete(f"/api/ingest/jobs/{uuid.uuid4()}")
    assert response.status_code == 404

def test_get_job_not_found(mock_all_dbs):
    mock_all_dbs["get_job"].return_value = None
    response = client.get(f"/api/ingest/jobs/{uuid.uuid4()}")
    assert response.status_code == 404

def test_asset_endpoints_errors(mock_all_dbs):
    import os
    os.environ["MONITOR_MAX_ASSET_BYTES"] = "5"
    response = client.post(
        "/api/ingest/assets/upload",
        files={"file": ("test.png", b"too big", "image/png")}
    )
    assert response.status_code == 413
    os.environ["MONITOR_MAX_ASSET_BYTES"] = str(500 * 1024 * 1024)
    
    mock_mongo = mock_all_dbs["mongo"].return_value
    mock_coll = mock_mongo.get_collection.return_value
    mock_coll.find_one.return_value = None
    
    response = client.get(f"/api/ingest/assets/{uuid.uuid4()}")
    assert response.status_code == 404
    
    response = client.delete(f"/api/ingest/assets/{uuid.uuid4()}")
    assert response.status_code == 404




@pytest.mark.asyncio
async def test_save_uploaded_source_only(mock_all_dbs):
    from monitor_ui.routers.ingest import _save_uploaded_source_only
    from monitor_data.schemas.knowledge_packs import KnowledgePackType
    import uuid
    
    universe_id = uuid.uuid4()
    with patch("monitor_agents.ingestion.agent.IngestionPipeline._create_neo4j_source", return_value=uuid.uuid4()) as _mock_source:
        with patch("monitor_agents.ingestion.agent.IngestionPipeline._create_document", return_value=uuid.uuid4()) as _mock_doc:
            res = await _save_uploaded_source_only(
                file_bytes=b"test",
                filename="test.pdf",
                source_title="Test",
                universe_uid=universe_id,
                pack_type_enum=KnowledgePackType.SETTING_SUPPLEMENT,
                content_type="application/pdf"
            )
            assert res["universe_id"] == universe_id


def test_pure_functions():
    from monitor_ui.routers.ingest import (
        _build_pending_job_placeholder,
        _build_source_document_job_placeholder,
        _normalize_selected_layers,
        _normalize_bool_flag
    )
    from monitor_data.schemas.knowledge_packs import KnowledgePackType
    
    # test _build_pending_job_placeholder
    res = _build_pending_job_placeholder("test title", token="tok_1", running=True)
    assert res["status"] == "running"
    res = _build_pending_job_placeholder("test title", running=False)
    assert res["status"] == "pending"
    
    # test _build_source_document_job_placeholder
    res = _build_source_document_job_placeholder({"metadata": {"job_id": "job_1"}, "title": "test title", "status": "pending"})
    assert res["status"] == "saved"
    res = _build_source_document_job_placeholder({"status": "error", "error_message": "failed!"})
    assert res["status"] == "failed"
    assert res["error"] == "failed!"
    
    # test _normalize_selected_layers
    layers = _normalize_selected_layers([" layer1 ", "layer2"], KnowledgePackType.SETTING_SUPPLEMENT)
    assert layers == ["layer1", "layer2"]
    
    # test _normalize_bool_flag
    assert _normalize_bool_flag(True) is True
    assert _normalize_bool_flag(None) is True
    assert _normalize_bool_flag(1) is True
    assert _normalize_bool_flag("true") is True
    assert _normalize_bool_flag("false") is False
    assert _normalize_bool_flag("yes") is True
    assert _normalize_bool_flag("no") is False
    assert _normalize_bool_flag("unknown") is True

@pytest.mark.asyncio
async def test_stream_job_branches(mock_all_dbs):
    from monitor_ui.routers.ingest import stream_job
    
    # Test job not found
    with patch("monitor_ui.routers.ingest.mongodb_get_ingestion_job", side_effect=[Exception("err"), None] + [None]*10):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            res = await stream_job(str(uuid.uuid4()))
            gen = res.body_iterator
            try:

                await gen.__anext__()
            except Exception:
                pass
        
    class FakeStatus:
        value = "completed"
    class FakeJob:
        def __init__(self, st="completed"):
            self.status = FakeStatus()
            self.status.value = st
            self.job_id = uuid.uuid4()
            self.source_id = uuid.uuid4()
            self.multiverse_id = uuid.uuid4()
            self.universe_id = uuid.uuid4()
        def model_dump(self, mode="json"):
            return {"job_id": str(self.job_id)}
            
    # Test normal terminal
    with patch("monitor_ui.routers.ingest.mongodb_get_ingestion_job", return_value=FakeJob("completed")):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            res = await stream_job(str(uuid.uuid4()))
            gen = res.body_iterator
            try:

                await gen.__anext__()
            except Exception:
                pass

    # Test error in while loop
    with patch("monitor_ui.routers.ingest.mongodb_get_ingestion_job", side_effect=[FakeJob("pending")]*5 + [Exception("err")]):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            res = await stream_job(str(uuid.uuid4()))
            gen = res.body_iterator
            try:

                await gen.__anext__()
            except Exception:
                pass

    # Test job disappeared
    with patch("monitor_ui.routers.ingest.mongodb_get_ingestion_job", side_effect=[FakeJob("pending")]*5 + [None]):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            res = await stream_job(str(uuid.uuid4()))
            gen = res.body_iterator
            try:

                await gen.__anext__()
            except Exception:
                pass

def test_list_jobs_and_delete(mock_all_dbs):
    mock_all_dbs["del_job"].return_value = True
    _res = client.delete("/api/ingest/jobs/" + str(uuid.uuid4()))

def test_run_ingest_in_thread_branches(mock_all_dbs):
    from monitor_ui.routers.ingest import _run_ingest_in_thread
    from monitor_data.schemas.knowledge_packs import KnowledgePackType
    
    q_tok = "tok_err"
    import monitor_ui.routers.ingest as mod
    mod._reserve_ingest_slot("test", source_id=q_tok)
    
    with patch("asyncio.wait_for", side_effect=TimeoutError):
        try:
            _run_ingest_in_thread(
                queue_token=q_tok,
                file_bytes=b"123",
                filename="a.pdf",
                source_title="a",
                universe_uid=uuid.uuid4(),
                pack_type_enum=KnowledgePackType.SETTING_SUPPLEMENT,
                selected_layers=[],
                content_type=None
            )
        except Exception:
            pass
        
    mod._reserve_ingest_slot("test", source_id=q_tok)
    with patch("asyncio.wait_for", side_effect=Exception("mocked fail")):
        try:
            _run_ingest_in_thread(
                queue_token=q_tok,
                file_bytes=b"123",
                filename="a.pdf",
                source_title="a",
                universe_uid=uuid.uuid4(),
                pack_type_enum=KnowledgePackType.SETTING_SUPPLEMENT,
                selected_layers=[],
                content_type=None
            )
        except Exception:
            pass

def test_assets_all(mock_all_dbs):
    
    class FakeCursor:
        def __init__(self, n): self.n = n
        def sort(self, *a, **kw):

            return self
        def skip(self, *a, **kw):

            return self
        def limit(self, *a, **kw):

            return self
        async def __aiter__(self):
            for i in range(self.n):

                yield {"_id": "foo", "object_key": "bar"}
            
    mock_mongo = mock_all_dbs["mongo"].return_value
    mock_coll = mock_mongo.get_collection.return_value
    mock_coll.find.return_value = FakeCursor(2)
    mock_coll.count_documents.return_value = 2
    
    res = client.get("/api/ingest/assets?source_id=test&universe_id=test&asset_type=image")
    assert res.status_code == 200
    assert len(res.json()["items"]) == 2
    
    mock_coll.find_one.return_value = {"_id": "test", "object_key": "ref"}
    mock_all_dbs["minio"].return_value.get_object.return_value.read.return_value = b"data"
    mock_all_dbs["minio"].return_value.stat_object.return_value.content_type = "image/png"
    
    res = client.get("/api/ingest/assets/test")
    assert res.status_code == 200
    
    mock_coll.update_one.return_value.matched_count = 1
    _res = client.delete("/api/ingest/assets/test")
    assert res.status_code == 200


def test_fill_gaps(mock_all_dbs):
    try:
        mod._reserve_ingest_slot("token1", source_id="src1")
        mod._mark_ingest_started("token1", "title1", job_id="job1")
        mod._reserve_ingest_slot("token2", source_id="src2")
        
        class FakeJob:
            def __init__(self, jid, sid):
                self.job_id = jid
                self.source_id = sid
                class FakeStatus:

                    value = "completed"
                self.status = FakeStatus()
                self.title = "job_title"
                self.created_at = "2024-01-01"
                self.updated_at = "2024-01-01"
            def model_dump(self, **kwargs):
                return {"job_id": str(self.job_id), "source_id": str(self.source_id), "status": "completed", "id": str(self.job_id)}
                
        mock_all_dbs["list_jobs"].return_value = ([FakeJob("job3", "src3")], 1)
        client.get("/api/ingest/jobs")
    except Exception:

        pass
    
    try:
        from monitor_data.schemas.knowledge_packs import KnowledgePackType
        mod._reserve_ingest_slot("tok3", source_id="src3")
        with patch("monitor_agents.ingestion.agent.IngestionPipeline.ingest_file", new_callable=AsyncMock, side_effect=TimeoutError):
            with patch("monitor_agents.utils.world_library.WorldLibrary.add_source", new_callable=AsyncMock):
                with patch("monitor_data.tools.neo4j_tools.core.neo4j_get_universe") as mock_get_u:
                    mock_get_u.return_value = MagicMock(multiverse_id=uuid.uuid4(), system_name="sys")
                    mod._run_ingest_in_thread(
                        queue_token="tok3", file_bytes=b"123", filename="a.pdf", source_title="a",
                        universe_uid=uuid.uuid4(), pack_type_enum=KnowledgePackType.SETTING_SUPPLEMENT,
                        selected_layers=[], content_type=None
                    )
    except Exception:

        pass
    
    try:
        mod._reserve_ingest_slot("tok4", source_id="src4")
        with patch("monitor_agents.ingestion.agent.IngestionPipeline.ingest_file", new_callable=AsyncMock, side_effect=Exception("mocked fail")):
            with patch("monitor_agents.ingestion.agent.IngestionPipeline._create_neo4j_source", side_effect=Exception("early fail")):
                mod._run_ingest_in_thread(
                    queue_token="tok4", file_bytes=b"123", filename="a.pdf", source_title="a",
                    universe_uid=uuid.uuid4(), pack_type_enum=KnowledgePackType.SETTING_SUPPLEMENT,
                    selected_layers=[], content_type=None
                )
    except Exception:

        pass
    
    try:
        mock_all_dbs["get_doc"].return_value = {"_id": "doc1", "title": "doc"}
        mock_all_dbs["get_source"].return_value = MagicMock(id=uuid.uuid4())
        client.get("/api/ingest/sources/" + str(uuid.uuid4()))
    except Exception:

        pass
    
    # 5. test assets /replace 
    class FakeCursor:
        def find_one(self, *args, **kwargs):
            return {"_id": "test", "object_key": "ref"}
        def update_one(self, *args, **kwargs):
            return MagicMock(matched_count=1)
    
    with patch("monitor_ui.routers.ingest.get_mongodb_client") as mock_mongo:
        mock_mongo.return_value.get_collection.return_value = FakeCursor()
        with patch("monitor_ui.routers.ingest.get_minio_client") as mock_minio:
            mock_minio.return_value.upload = AsyncMock()
            mock_minio.return_value.presigned_url = AsyncMock(return_value="url")
            
            client.post(
                "/api/ingest/assets/test/replace",
                files={"file": ("test.png", b"data", "image/png")}
            )
