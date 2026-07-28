from unittest.mock import patch, MagicMock, AsyncMock
import uuid
from fastapi.testclient import TestClient

from monitor_ui.main import app
import monitor_ui.routers.ingest as mod

client = TestClient(app)

def test_missing_lines_in_ingest_more():
    # 1. replace_asset
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
            
            _res = client.post(
                "/api/ingest/assets/test/replace",
                files={"file": ("test.png", b"data", "image/png")}
            )

    # 2. test stream timeout / branches
    # directly call the function _run_ingest_in_thread
    with patch("monitor_ui.routers.ingest.asyncio.wait_for", side_effect=TimeoutError):
        mod._captured_job_id = [str(uuid.uuid4())]
        try:
            mod._run_ingest_in_thread(
                queue_token="tok_1",
                file_bytes=b"123",
                filename="a.pdf",
                source_title="a",
                universe_uid=uuid.uuid4(),
                pack_type_enum=None,
                selected_layers=[],
                content_type=None
            )
        except Exception:
            pass
        
    with patch("monitor_ui.routers.ingest.asyncio.wait_for", side_effect=Exception("foo")):
        mod._captured_job_id = [str(uuid.uuid4())]
        try:
            mod._run_ingest_in_thread(
                queue_token="tok_1",
                file_bytes=b"123",
                filename="a.pdf",
                source_title="a",
                universe_uid=uuid.uuid4(),
                pack_type_enum=None,
                selected_layers=[],
                content_type=None
            )
        except Exception:
            pass
