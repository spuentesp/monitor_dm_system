"""
Asset (MinIO) Pydantic models for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, datetime, uuid)
CALLED BY: minio_tools.py

These schemas define request/response models for MinIO binary asset operations.
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# MINIO REFERENCE
# =============================================================================


class MinioRef(BaseModel):
    """
    Reference to a MinIO object.
    
    This is stored in MongoDB to link documents to their binary assets.
    """

    bucket: str = Field(..., description="MinIO bucket name")
    key: str = Field(..., description="Object key (path) in bucket")


# =============================================================================
# UPLOAD OPERATIONS
# =============================================================================


class MinioUpload(BaseModel):
    """
    Parameters for uploading a binary asset to MinIO.
    """

    bucket: str = Field(..., description="Bucket name")
    key: Optional[str] = Field(
        None, description="Object key (if None, auto-generates UUID-based key)"
    )
    content: bytes = Field(..., description="Binary content to upload")
    content_type: str = Field(
        default="application/octet-stream", description="MIME type of the content"
    )
    metadata: Optional[Dict[str, str]] = Field(
        None,
        description="Optional metadata (source_id, universe_id, uploader, etc.)",
    )


class MinioUploadResponse(BaseModel):
    """
    Response from uploading an object to MinIO.
    """

    bucket: str
    key: str
    etag: str
    version_id: Optional[str] = None
    size: int
    minio_ref: MinioRef = Field(
        ..., description="Reference object for storing in MongoDB"
    )


# =============================================================================
# GET OPERATIONS
# =============================================================================


class MinioGetObject(BaseModel):
    """
    Parameters for retrieving an object from MinIO.
    """

    bucket: str = Field(..., description="Bucket name")
    key: str = Field(..., description="Object key (path)")


class MinioGetObjectResponse(BaseModel):
    """
    Response from getting an object from MinIO.
    """

    bucket: str
    key: str
    content: bytes
    content_type: str
    size: int
    metadata: Dict[str, str]
    etag: str
    last_modified: datetime
    minio_ref: MinioRef


# =============================================================================
# DELETE OPERATIONS
# =============================================================================


class MinioDeleteObject(BaseModel):
    """
    Parameters for deleting an object from MinIO.
    """

    bucket: str = Field(..., description="Bucket name")
    key: str = Field(..., description="Object key (path)")


class MinioDeleteObjectResponse(BaseModel):
    """
    Response from deleting an object from MinIO.
    """

    bucket: str
    key: str
    deleted: bool


# =============================================================================
# LIST OPERATIONS
# =============================================================================


class MinioListObjects(BaseModel):
    """
    Parameters for listing objects in a bucket.
    """

    bucket: str = Field(..., description="Bucket name")
    prefix: Optional[str] = Field(None, description="Optional prefix filter")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class MinioObjectInfo(BaseModel):
    """
    Information about a single object in MinIO.
    """

    bucket: str
    key: str
    size: int
    etag: str
    last_modified: datetime
    is_dir: bool
    minio_ref: MinioRef


class MinioListObjectsResponse(BaseModel):
    """
    Response from listing objects in MinIO.
    """

    bucket: str
    prefix: Optional[str] = None
    objects: List[MinioObjectInfo]
    count: int
    offset: int
    limit: int
    has_more: bool = Field(
        ..., description="True if there are more objects beyond this page"
    )


# =============================================================================
# PRESIGNED URL OPERATIONS
# =============================================================================


class MinioGetPresignedUrl(BaseModel):
    """
    Parameters for generating a presigned URL.
    """

    bucket: str = Field(..., description="Bucket name")
    key: str = Field(..., description="Object key (path)")
    expires_in: int = Field(
        default=3600, ge=1, le=604800, description="Expiration time in seconds"
    )


class MinioGetPresignedUrlResponse(BaseModel):
    """
    Response from generating a presigned URL.
    """

    bucket: str
    key: str
    url: str
    expires_in: int
    minio_ref: MinioRef
