"""
MinIO MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose MinIO object storage operations via the MCP server.
All operations have authority: * (available to all agents).
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from minio.error import S3Error

from monitor_data.db.minio import get_minio_client
from monitor_data.schemas.assets import (
    MinioUpload,
    MinioUploadResponse,
    MinioGetObject,
    MinioGetObjectResponse,
    MinioDeleteObject,
    MinioDeleteObjectResponse,
    MinioListObjects,
    MinioListObjectsResponse,
    MinioObjectInfo,
    MinioGetPresignedUrl,
    MinioGetPresignedUrlResponse,
    MinioRef,
)


# =============================================================================
# UPLOAD OPERATIONS
# =============================================================================


def minio_upload(params: MinioUpload) -> MinioUploadResponse:
    """
    Upload a binary asset to MinIO.

    Authority: * (all agents)
    Use Case: DL-9

    Args:
        params: Upload parameters (bucket, key, content, content_type, metadata)

    Returns:
        MinioUploadResponse with upload information and minio_ref

    Raises:
        S3Error: If upload fails
        RuntimeError: If client not connected
    """
    client = get_minio_client()

    # Auto-generate key if not provided
    object_key = params.key
    if not object_key:
        # Generate UUID-based key
        object_key = str(uuid4())

    # Upload the object
    result = client.upload_object(
        bucket_name=params.bucket,
        object_key=object_key,
        content=params.content,
        content_type=params.content_type,
        metadata=params.metadata,
    )

    # Create minio_ref for MongoDB storage
    minio_ref = MinioRef(bucket=params.bucket, key=object_key)

    return MinioUploadResponse(
        bucket=result["bucket"],
        key=result["key"],
        etag=result["etag"],
        version_id=result.get("version_id"),
        size=len(params.content),
        minio_ref=minio_ref,
    )


# =============================================================================
# GET OPERATIONS
# =============================================================================


def minio_get_object(params: MinioGetObject) -> MinioGetObjectResponse:
    """
    Retrieve a binary asset from MinIO.

    Authority: * (all agents)
    Use Case: DL-9

    Args:
        params: Get parameters (bucket, key)

    Returns:
        MinioGetObjectResponse with content and metadata

    Raises:
        S3Error: If object not found or retrieval fails
        RuntimeError: If client not connected
    """
    client = get_minio_client()

    # Get the object
    result = client.get_object(bucket_name=params.bucket, object_key=params.key)

    # Create minio_ref
    minio_ref = MinioRef(bucket=params.bucket, key=params.key)

    return MinioGetObjectResponse(
        bucket=result["bucket"],
        key=result["key"],
        content=result["content"],
        content_type=result["content_type"],
        size=result["size"],
        metadata=result["metadata"],
        etag=result["etag"],
        last_modified=result["last_modified"],
        minio_ref=minio_ref,
    )


# =============================================================================
# DELETE OPERATIONS
# =============================================================================


def minio_delete_object(params: MinioDeleteObject) -> MinioDeleteObjectResponse:
    """
    Delete a binary asset from MinIO.

    Authority: * (all agents)
    Use Case: DL-9

    Args:
        params: Delete parameters (bucket, key)

    Returns:
        MinioDeleteObjectResponse confirming deletion

    Raises:
        S3Error: If deletion fails
        RuntimeError: If client not connected
    """
    client = get_minio_client()

    # Delete the object
    deleted = client.delete_object(bucket_name=params.bucket, object_key=params.key)

    return MinioDeleteObjectResponse(
        bucket=params.bucket, key=params.key, deleted=deleted
    )


# =============================================================================
# LIST OPERATIONS
# =============================================================================


def minio_list_objects(params: MinioListObjects) -> MinioListObjectsResponse:
    """
    List objects in a MinIO bucket with pagination.

    Authority: * (all agents)
    Use Case: DL-9

    Args:
        params: List parameters (bucket, prefix, limit, offset)

    Returns:
        MinioListObjectsResponse with paginated object list

    Raises:
        S3Error: If listing fails
        RuntimeError: If client not connected
    """
    client = get_minio_client()

    # List all objects matching the prefix
    all_objects = client.list_objects(
        bucket_name=params.bucket, prefix=params.prefix, recursive=True
    )

    # Apply pagination
    start_idx = params.offset
    end_idx = start_idx + params.limit
    paginated_objects = all_objects[start_idx:end_idx]

    # Convert to MinioObjectInfo
    object_infos = []
    for obj in paginated_objects:
        minio_ref = MinioRef(bucket=params.bucket, key=obj["key"])
        object_infos.append(
            MinioObjectInfo(
                bucket=obj["bucket"],
                key=obj["key"],
                size=obj["size"],
                etag=obj["etag"],
                last_modified=obj["last_modified"],
                is_dir=obj["is_dir"],
                minio_ref=minio_ref,
            )
        )

    # Determine if there are more objects
    has_more = len(all_objects) > end_idx

    return MinioListObjectsResponse(
        bucket=params.bucket,
        prefix=params.prefix,
        objects=object_infos,
        count=len(object_infos),
        offset=params.offset,
        limit=params.limit,
        has_more=has_more,
    )


# =============================================================================
# PRESIGNED URL OPERATIONS
# =============================================================================


def minio_get_presigned_url(
    params: MinioGetPresignedUrl,
) -> MinioGetPresignedUrlResponse:
    """
    Generate a presigned URL for temporary access to an object.

    Authority: * (all agents)
    Use Case: DL-9

    Args:
        params: Presigned URL parameters (bucket, key, expires_in)

    Returns:
        MinioGetPresignedUrlResponse with presigned URL

    Raises:
        S3Error: If URL generation fails
        RuntimeError: If client not connected
    """
    client = get_minio_client()

    # Generate presigned URL
    url = client.get_presigned_url(
        bucket_name=params.bucket,
        object_key=params.key,
        expires_in=params.expires_in,
    )

    # Create minio_ref
    minio_ref = MinioRef(bucket=params.bucket, key=params.key)

    return MinioGetPresignedUrlResponse(
        bucket=params.bucket,
        key=params.key,
        url=url,
        expires_in=params.expires_in,
        minio_ref=minio_ref,
    )
