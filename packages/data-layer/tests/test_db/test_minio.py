from contextlib import asynccontextmanager

import pytest

from monitor_data.db.minio import MinIOClient


@pytest.mark.asyncio
async def test_folder_backend_upload_download_and_delete(tmp_path):
    client = MinIOClient(
        backend="folder",
        local_path=str(tmp_path),
        bucket="monitor",
        fallback_to_local=False,
    )

    await client.upload("uploads/test.txt", b"hello world", content_type="text/plain")

    data = await client.download("uploads/test.txt")
    url = await client.presigned_url("uploads/test.txt")

    assert data == b"hello world"
    assert url.startswith("file://")

    await client.delete("uploads/test.txt")

    with pytest.raises(FileNotFoundError):
        await client.download("uploads/test.txt")


@pytest.mark.asyncio
async def test_remote_upload_falls_back_to_local_folder(monkeypatch, tmp_path):
    client = MinIOClient(
        backend="minio",
        endpoint_url="http://localhost:9000",
        local_path=str(tmp_path),
        bucket="monitor",
        fallback_to_local=True,
    )

    @asynccontextmanager
    async def fake_s3():
        class FakeClient:
            async def head_bucket(self, Bucket):
                return None

            async def put_object(self, **kwargs):
                raise RuntimeError("XMinioStorageFull")

            async def get_object(self, **kwargs):
                raise RuntimeError("remote storage unavailable")

            async def delete_object(self, **kwargs):
                return None

        yield FakeClient()

    monkeypatch.setattr(client, "_s3", fake_s3)

    await client.upload("uploads/fallback.txt", b"stored locally")

    data = await client.download("uploads/fallback.txt")
    url = await client.presigned_url("uploads/fallback.txt")

    assert data == b"stored locally"
    assert url.startswith("file://")
