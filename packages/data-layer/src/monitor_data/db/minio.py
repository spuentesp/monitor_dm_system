"""
MinIO client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (minio)
CALLED BY: minio_tools.py

This client provides a wrapper around the MinIO client with
bucket management and object storage operations.
"""

import os
import threading
from typing import Any, Dict, List, Optional
from io import BytesIO

from minio import Minio
from minio.error import S3Error


class MinIOClient:
    """
    MinIO database client for binary asset storage.

    This client provides S3-compatible object storage operations.
    All operations are available to any agent (authority: *).
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        secure: Optional[bool] = None,
    ):
        """
        Initialize MinIO client.

        Args:
            endpoint: MinIO endpoint (default: from MINIO_ENDPOINT env var)
            access_key: MinIO access key (default: from MINIO_ACCESS_KEY env var)
            secret_key: MinIO secret key (required, from MINIO_SECRET_KEY env var)
            secure: Use HTTPS (default: from MINIO_SECURE env var, defaults to False)

        Raises:
            ValueError: If secret_key is not provided and MINIO_SECRET_KEY env var is not set
        """
        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY", "monitor")
        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY")
        self.secure = (
            secure
            if secure is not None
            else os.getenv("MINIO_SECURE", "false").lower() == "true"
        )

        if not self.secret_key:
            raise ValueError(
                "MinIO secret key is required. "
                "Provide it via the 'secret_key' parameter or set the MINIO_SECRET_KEY environment variable."
            )

        self._client: Optional[Minio] = None

    def connect(self) -> None:
        """Establish connection to MinIO."""
        if self._client is None:
            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )

    def close(self) -> None:
        """Close the MinIO connection."""
        # MinIO client doesn't need explicit cleanup
        self._client = None

    def __enter__(self) -> "MinIOClient":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def ensure_bucket(self, bucket_name: str) -> None:
        """
        Ensure bucket exists, create if it doesn't.

        Args:
            bucket_name: Name of the bucket

        Raises:
            RuntimeError: If not connected
            S3Error: If bucket creation fails
        """
        if not self._client:
            raise RuntimeError("MinIO client not connected. Call connect() first.")

        try:
            if not self._client.bucket_exists(bucket_name):
                self._client.make_bucket(bucket_name)
        except S3Error as e:
            raise RuntimeError(f"Failed to ensure bucket '{bucket_name}': {e}")

    def upload_object(
        self,
        bucket_name: str,
        object_key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Upload an object to MinIO.

        Args:
            bucket_name: Name of the bucket
            object_key: Object key (path)
            content: Binary content to upload
            content_type: MIME type of the content
            metadata: Optional metadata dictionary

        Returns:
            Dictionary with upload information (etag, bucket, key, version_id)

        Raises:
            RuntimeError: If not connected
            S3Error: If upload fails
        """
        if not self._client:
            raise RuntimeError("MinIO client not connected. Call connect() first.")

        # Ensure bucket exists
        self.ensure_bucket(bucket_name)

        # Upload the object
        content_stream = BytesIO(content)
        result = self._client.put_object(
            bucket_name,
            object_key,
            content_stream,
            length=len(content),
            content_type=content_type,
            metadata=metadata or {},
        )

        return {
            "bucket": bucket_name,
            "key": object_key,
            "etag": result.etag,
            "version_id": result.version_id,
        }

    def get_object(
        self, bucket_name: str, object_key: str
    ) -> Dict[str, Any]:
        """
        Get an object from MinIO.

        Args:
            bucket_name: Name of the bucket
            object_key: Object key (path)

        Returns:
            Dictionary with content, metadata, content_type, size

        Raises:
            RuntimeError: If not connected
            S3Error: If object not found or retrieval fails
        """
        if not self._client:
            raise RuntimeError("MinIO client not connected. Call connect() first.")

        try:
            # Get the object
            response = self._client.get_object(bucket_name, object_key)
            content = response.read()
            
            # Get object metadata
            stat = self._client.stat_object(bucket_name, object_key)
            
            return {
                "bucket": bucket_name,
                "key": object_key,
                "content": content,
                "content_type": stat.content_type,
                "size": stat.size,
                "metadata": stat.metadata,
                "etag": stat.etag,
                "last_modified": stat.last_modified,
            }
        finally:
            if response:
                response.close()
                response.release_conn()

    def delete_object(self, bucket_name: str, object_key: str) -> bool:
        """
        Delete an object from MinIO.

        Args:
            bucket_name: Name of the bucket
            object_key: Object key (path)

        Returns:
            True if deleted successfully

        Raises:
            RuntimeError: If not connected
            S3Error: If deletion fails
        """
        if not self._client:
            raise RuntimeError("MinIO client not connected. Call connect() first.")

        self._client.remove_object(bucket_name, object_key)
        return True

    def list_objects(
        self,
        bucket_name: str,
        prefix: Optional[str] = None,
        recursive: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        List objects in a bucket.

        Args:
            bucket_name: Name of the bucket
            prefix: Optional prefix filter
            recursive: List recursively (default: True)

        Returns:
            List of object dictionaries with key, size, etag, last_modified

        Raises:
            RuntimeError: If not connected
            S3Error: If listing fails
        """
        if not self._client:
            raise RuntimeError("MinIO client not connected. Call connect() first.")

        objects = []
        for obj in self._client.list_objects(
            bucket_name, prefix=prefix, recursive=recursive
        ):
            objects.append(
                {
                    "bucket": bucket_name,
                    "key": obj.object_name,
                    "size": obj.size,
                    "etag": obj.etag,
                    "last_modified": obj.last_modified,
                    "is_dir": obj.is_dir,
                }
            )

        return objects

    def get_presigned_url(
        self, bucket_name: str, object_key: str, expires_in: int = 3600
    ) -> str:
        """
        Generate a presigned URL for temporary access to an object.

        Args:
            bucket_name: Name of the bucket
            object_key: Object key (path)
            expires_in: URL expiration time in seconds (default: 3600 = 1 hour)

        Returns:
            Presigned URL string

        Raises:
            RuntimeError: If not connected
            S3Error: If URL generation fails
        """
        if not self._client:
            raise RuntimeError("MinIO client not connected. Call connect() first.")

        from datetime import timedelta

        url = self._client.presigned_get_object(
            bucket_name, object_key, expires=timedelta(seconds=expires_in)
        )
        return url

    def verify_connectivity(self) -> bool:
        """
        Verify connection to MinIO.

        Returns:
            True if connected and can list buckets, False otherwise
        """
        try:
            if not self._client:
                return False
            # Try to list buckets as a connectivity check
            list(self._client.list_buckets())
            return True
        except Exception:
            return False


# Global client instance (can be initialized once at startup)
_client: Optional[MinIOClient] = None
_client_lock = threading.Lock()


def get_minio_client() -> MinIOClient:
    """
    Get or create the global MinIO client instance (thread-safe).

    Returns:
        MinIOClient instance

    Note:
        This returns a singleton client. Call connect() before using.
        Uses double-checked locking for thread-safe initialization.
    """
    global _client
    # First check without lock for performance
    if _client is None:
        # Acquire lock for initialization
        with _client_lock:
            # Second check with lock to prevent race condition
            if _client is None:
                _client = MinIOClient()
                _client.connect()
    return _client
