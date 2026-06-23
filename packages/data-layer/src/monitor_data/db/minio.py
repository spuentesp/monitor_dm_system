"""
MinIO / S3 / local-folder storage client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (aiobotocore, tenacity)
CALLED BY: ingestion and file retrieval workflows

Supports configurable storage backends:
- ``minio``  : local or remote MinIO using the S3 protocol
- ``s3``     : AWS S3 or any compatible object store with a custom endpoint
- ``folder`` : local filesystem storage for offline/dev fallback

The public API remains the same (`upload`, `download`, `delete`,
`presigned_url`) so the rest of the stack does not need to know which backend
is active.
"""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import aiobotocore.session
from tenacity import retry

from monitor_data.config import settings
from monitor_data.db._utils import DB_RETRY

logger = logging.getLogger(__name__)
_LOCAL_BACKENDS = {"folder", "local", "filesystem"}

# ---------------------------------------------------------------------------
# (Retry policy DB_RETRY imported from ._utils)
# ---------------------------------------------------------------------------


class MinIOClient:
    """
    Configurable object storage client for MONITOR.

    Despite the legacy class name, this client now supports MinIO, AWS S3 /
    S3-compatible backends, and a local folder backend for development or as a
    resilience fallback when remote storage is full or unavailable.
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
        secure: Optional[bool] = None,
        backend: Optional[str] = None,
        local_path: Optional[str] = None,
        fallback_to_local: Optional[bool] = None,
    ) -> None:
        self._backend: str = (backend or settings.storage_backend).strip().lower()
        self._bucket: str = bucket or settings.minio_bucket
        self._region: str = region or settings.minio_region
        self._access_key: str = access_key or settings.minio_access_key
        self._secret_key: str = secret_key or settings.minio_secret_key
        self._fallback_to_local: bool = (
            settings.storage_fallback_to_local if fallback_to_local is None else fallback_to_local
        )
        self._local_root = Path(local_path or settings.local_storage_path).expanduser().resolve()
        self._session = aiobotocore.session.get_session()

        scheme = "https" if (secure if secure is not None else settings.minio_secure) else "http"
        configured_endpoint = endpoint_url
        if configured_endpoint is None:
            configured_endpoint = settings.storage_endpoint
            if configured_endpoint is None and self._backend != "s3":
                configured_endpoint = settings.minio_endpoint

        if configured_endpoint and not configured_endpoint.startswith(("http://", "https://")):
            configured_endpoint = f"{scheme}://{configured_endpoint}"
        self._endpoint_url: Optional[str] = configured_endpoint

    def _uses_local_storage(self) -> bool:
        return self._backend in _LOCAL_BACKENDS

    def _local_bucket_root(self, bucket: Optional[str] = None) -> Path:
        target = bucket or self._bucket
        return (self._local_root / target).resolve()

    def _local_object_path(self, key: str, bucket: Optional[str] = None) -> Path:
        root = self._local_bucket_root(bucket)
        candidate = (root / Path(str(key).lstrip("/"))).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"Unsafe storage key outside local root: {key}")
        return candidate

    async def _write_local(
        self,
        key: str,
        data: bytes,
        bucket: Optional[str] = None,
    ) -> Path:
        path = self._local_object_path(key, bucket)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    # ------------------------------------------------------------------
    # Internal context manager to obtain an S3 client
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _s3(self) -> AsyncIterator[Any]:
        """Yield an aiobotocore S3 client scoped to a single operation."""
        client_kwargs = {
            "service_name": "s3",
            "aws_access_key_id": self._access_key,
            "aws_secret_access_key": self._secret_key,
            "region_name": self._region,
        }
        if self._endpoint_url:
            client_kwargs["endpoint_url"] = self._endpoint_url

        async with self._session.create_client(**client_kwargs) as client:
            yield client

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @retry(**DB_RETRY)
    async def verify_connectivity(self) -> bool:
        """Verify the configured object store is reachable."""
        if self._uses_local_storage():
            self._local_bucket_root().mkdir(parents=True, exist_ok=True)
            return True

        try:
            async with self._s3() as client:
                await client.list_buckets()
            return True
        except Exception as exc:
            if self._fallback_to_local:
                self._local_bucket_root().mkdir(parents=True, exist_ok=True)
                logger.warning(
                    "Remote object storage unavailable (%s); local folder fallback remains available at %s",
                    exc,
                    self._local_root,
                )
                return True
            return False

    # ------------------------------------------------------------------
    # Bucket management
    # ------------------------------------------------------------------

    @retry(**DB_RETRY)
    async def ensure_bucket(self, bucket: Optional[str] = None) -> None:
        """Create the bucket if it does not already exist (idempotent)."""
        if self._uses_local_storage():
            self._local_bucket_root(bucket).mkdir(parents=True, exist_ok=True)
            return

        target = bucket or self._bucket
        async with self._s3() as client:
            try:
                await client.head_bucket(Bucket=target)
            except Exception:
                await client.create_bucket(Bucket=target)

    # ------------------------------------------------------------------
    # Object operations
    # ------------------------------------------------------------------

    @retry(**DB_RETRY)
    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        bucket: Optional[str] = None,
    ) -> None:
        """Upload bytes to the configured object storage backend."""
        target = bucket or self._bucket

        if self._uses_local_storage():
            await self._write_local(key, data, target)
            return

        try:
            await self.ensure_bucket(target)
            async with self._s3() as client:
                await client.put_object(
                    Bucket=target,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
        except Exception as exc:
            if self._fallback_to_local:
                fallback_path = await self._write_local(key, data, target)
                logger.warning(
                    "Remote object upload failed (%s); stored '%s' in local fallback at %s",
                    exc,
                    key,
                    fallback_path,
                )
                return
            raise

    @retry(**DB_RETRY)
    async def download(self, key: str, bucket: Optional[str] = None) -> bytes:
        """Download an object and return its bytes."""
        target = bucket or self._bucket

        if self._uses_local_storage():
            return self._local_object_path(key, target).read_bytes()

        try:
            async with self._s3() as client:
                response = await client.get_object(Bucket=target, Key=key)
                async with response["Body"] as stream:
                    return bytes(await stream.read())
        except Exception as exc:
            local_path = self._local_object_path(key, target)
            if self._fallback_to_local and local_path.exists():
                logger.warning(
                    "Remote object download failed (%s); serving '%s' from local fallback at %s",
                    exc,
                    key,
                    local_path,
                )
                return local_path.read_bytes()
            raise

    @retry(**DB_RETRY)
    async def delete(self, key: str, bucket: Optional[str] = None) -> None:
        """Delete an object from remote or local storage."""
        target = bucket or self._bucket

        if self._uses_local_storage():
            path = self._local_object_path(key, target)
            if path.exists():
                path.unlink()
            return

        try:
            async with self._s3() as client:
                await client.delete_object(Bucket=target, Key=key)
        finally:
            if self._fallback_to_local:
                path = self._local_object_path(key, target)
                if path.exists():
                    path.unlink()

    @retry(**DB_RETRY)
    async def presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        bucket: Optional[str] = None,
    ) -> str:
        """Generate a presigned GET URL or local file URI."""
        target = bucket or self._bucket

        if self._uses_local_storage():
            return self._local_object_path(key, target).as_uri()

        try:
            async with self._s3() as client:
                url: str = await client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": target, "Key": key},
                    ExpiresIn=expires_in,
                )
            return url
        except Exception as exc:
            local_path = self._local_object_path(key, target)
            if self._fallback_to_local and local_path.exists():
                logger.warning(
                    "Presigned URL generation failed (%s); using local file URI for '%s'",
                    exc,
                    key,
                )
                return local_path.as_uri()
            raise


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_minio_client_instance: Optional[MinIOClient] = None


def get_minio_client() -> MinIOClient:
    """
    Return (and lazily initialise) the module-level MinIOClient singleton.

    Synchronous factory — aiobotocore creates per-operation clients internally
    so there is no persistent connection to establish at startup.
    """
    global _minio_client_instance
    if _minio_client_instance is None:
        _minio_client_instance = MinIOClient()
    return _minio_client_instance


def reset_minio_client() -> None:
    """Discard the singleton.  Used in tests for clean state."""
    global _minio_client_instance
    _minio_client_instance = None
