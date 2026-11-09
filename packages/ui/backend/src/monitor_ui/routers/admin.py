"""Backoffice operator console: user administration (admin-only).

All routes require an authenticated ADMIN principal (``require_admin``).
Operators can list/search users, inspect a user, ban/unban, and grant or
revoke admin. An operator cannot modify their own account through these
routes (no self-ban / self-demotion); secrets (password hashes, tokens)
are never returned.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from monitor_data.db.postgres import PostgresClient
from monitor_data.schemas.users import (
    AdminRoleRequest,
    BanRequest,
    UserAdminListResponse,
    UserAdminResponse,
)

from monitor_ui.auth import Principal, get_postgres, require_admin

router = APIRouter()


def _admin_view(row: dict[str, Any]) -> UserAdminResponse:
    return UserAdminResponse(
        id=row["id"],
        email=row["email"],
        username=row["username"],
        display_name=row.get("display_name", ""),
        is_admin=bool(row.get("is_admin", False)),
        is_banned=bool(row.get("is_banned", False)),
        banned_reason=row.get("banned_reason"),
        email_verified=bool(row.get("email_verified", False)),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _get_user_or_404(db: PostgresClient, user_id: UUID) -> dict[str, Any]:
    user = await db.user_get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.get("/users", response_model=UserAdminListResponse)
async def list_users(
    q: str | None = Query(default=None, max_length=100, description="Search email/username"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_admin),
    db: PostgresClient = Depends(get_postgres),
) -> UserAdminListResponse:
    """Paginated user directory for the operator console."""
    rows = await db.users_list_admin(q, limit, offset)
    total = await db.users_count_admin(q)
    return UserAdminListResponse(
        users=[_admin_view(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=UserAdminResponse)
async def get_user(
    user_id: UUID,
    principal: Principal = Depends(require_admin),
    db: PostgresClient = Depends(get_postgres),
) -> UserAdminResponse:
    return _admin_view(await _get_user_or_404(db, user_id))


@router.post("/users/{user_id}/ban", response_model=UserAdminResponse)
async def ban_user(
    user_id: UUID,
    body: BanRequest,
    principal: Principal = Depends(require_admin),
    db: PostgresClient = Depends(get_postgres),
) -> UserAdminResponse:
    """Suspend an account. Existing sessions/API tokens are rejected from now on."""
    if user_id == principal.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot ban yourself.")
    user = await _get_user_or_404(db, user_id)
    await db.user_set_banned(user_id, True, body.reason)
    user["is_banned"] = True
    user["banned_reason"] = body.reason
    return _admin_view(user)


@router.post("/users/{user_id}/unban", response_model=UserAdminResponse)
async def unban_user(
    user_id: UUID,
    principal: Principal = Depends(require_admin),
    db: PostgresClient = Depends(get_postgres),
) -> UserAdminResponse:
    user = await _get_user_or_404(db, user_id)
    await db.user_set_banned(user_id, False, None)
    user["is_banned"] = False
    user["banned_reason"] = None
    return _admin_view(user)


@router.post("/users/{user_id}/role", response_model=UserAdminResponse)
async def set_user_role(
    user_id: UUID,
    body: AdminRoleRequest,
    principal: Principal = Depends(require_admin),
    db: PostgresClient = Depends(get_postgres),
) -> UserAdminResponse:
    """Grant or revoke admin. Operators cannot demote themselves."""
    if user_id == principal.user_id and not body.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke your own admin role.",
        )
    user = await _get_user_or_404(db, user_id)
    await db.user_set_admin(user_id, body.is_admin)
    user["is_admin"] = body.is_admin
    return _admin_view(user)
