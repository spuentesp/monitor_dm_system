"""
Fake MinIO / S3 client for unit tests.

Mirrors the async interface of monitor_data.db.minio.MinIOClient.
Stores objects in an in-memory dict.

Usage::

    from tests.mocks.db.minio import FakeMinIOClient

    client = FakeMinIOClient()
    await client.upload("document.pdf", b"file contents")
    data = await client.download("document.pdf")
"""

from __future__ import annotations

from typing import Any


class FakeMinIOClient:
    """In-memory MinIO/S3 client for unit tests.

    Stores objects as bytes keyed by object name.
    Supports upload, download, delete, and presigned URL generation.
    """

    def __init__(self, bucket: str = "monitor") -> None:
        self._bucket = bucket
        self._objects: dict[str, bytes] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    async def upload(
        self,
        object_name: str,
        data: bytes,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Upload an object. Returns the object name."""
        self._objects[object_name] = data
        self._metadata[object_name] = metadata or {}
        return object_name

    async def download(self, object_name: str) -> bytes:
        """Download an object. Raises KeyError if not found."""
        if object_name not in self._objects:
            raise KeyError(f"Object '{object_name}' not found")
        return self._objects[object_name]

    async def delete(self, object_name: str) -> None:
        """Delete an object."""
        self._objects.pop(object_name, None)
        self._metadata.pop(object_name, None)

    async def exists(self, object_name: str) -> bool:
        """Check if an object exists."""
        return object_name in self._objects

    async def list_objects(self, prefix: str = "") -> list[str]:
        """List objects with an optional prefix filter."""
        if not prefix:
            return list(self._objects.keys())
        return [name for name in self._objects if name.startswith(prefix)]

    async def get_metadata(self, object_name: str) -> dict[str, Any]:
        """Get object metadata."""
        return self._metadata.get(object_name, {})

    async def presigned_url(self, object_name: str, expires: int = 3600) -> str:
        """Generate a fake presigned URL."""
        return f"http://localhost:9000/{self._bucket}/{object_name}?expires={expires}"

    def seed_object(
        self, object_name: str, data: bytes, metadata: dict | None = None
    ) -> None:
        """Seed an object directly."""
        self._objects[object_name] = data
        self._metadata[object_name] = metadata or {}

    def reset(self) -> None:
        """Clear all objects."""
        self._objects.clear()
        self._metadata.clear()


def make_mock_minio_client() -> FakeMinIOClient:
    """Return a FakeMinIOClient."""
    return FakeMinIOClient()
