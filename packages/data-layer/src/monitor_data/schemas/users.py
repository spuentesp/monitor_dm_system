"""User identity, browser session, and API-token contracts.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, datetime, uuid)
CALLED BY: UI backend authentication and ownership services
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def normalize_login(value: str) -> str:
    return value.strip().casefold()


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=1024)
    display_name: str = Field(default="", max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_login(value)
        local, separator, domain = normalized.partition("@")
        if not separator or not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("Enter a valid email address")
        return normalized


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    display_name: str = ""
    is_admin: bool = False
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    login: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("login")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_login(value)


class AuthSessionResponse(BaseModel):
    user: UserResponse
    expires_at: datetime


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expires_at: datetime | None = None


class ApiTokenCreatedResponse(BaseModel):
    id: UUID
    name: str
    token: str
    token_prefix: str
    created_at: datetime
    expires_at: datetime | None = None


class ApiTokenMetadataResponse(BaseModel):
    id: UUID
    name: str
    token_prefix: str
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class AuthModeResponse(BaseModel):
    auth_disabled: bool
    user: UserResponse


class UserAdminResponse(BaseModel):
    """Operator-console view of a user account. Never includes secrets."""

    id: UUID
    email: str
    username: str
    display_name: str = ""
    is_admin: bool = False
    is_banned: bool = False
    banned_reason: str | None = None
    email_verified: bool = False
    created_at: datetime
    updated_at: datetime


class UserAdminListResponse(BaseModel):
    users: list[UserAdminResponse]
    total: int
    limit: int
    offset: int


class BanRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AdminRoleRequest(BaseModel):
    is_admin: bool
