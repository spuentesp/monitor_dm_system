"""Backoffice operator console: user administration (admin-only).

All routes require an authenticated ADMIN principal (``require_admin``).
Operators can list/search users, inspect a user, ban/unban, and grant or
revoke admin. An operator cannot modify their own account through these
routes (no self-ban / self-demotion); secrets (password hashes, tokens)
are never returned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from monitor_data.db.postgres import PostgresClient
from monitor_data.schemas.users import (
    AdminRoleRequest,
    BanRequest,
    UserAdminListResponse,
    UserAdminResponse,
)

from monitor_ui.auth import LOCAL_USER_ID, Principal, get_postgres, require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


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


# ---------------------------------------------------------------------------
# Usage + quota administration (multi-tenancy)
# ---------------------------------------------------------------------------


class UsageLimitUpdate(BaseModel):
    """Per-user quota override. ``None`` columns fall back to the env defaults."""

    daily_token_cap: int | None = None
    daily_call_cap: int | None = None
    exempt: bool = False


class UsageView(BaseModel):
    user_id: str
    username: str = ""
    email: str = ""
    tokens: int = 0
    calls: int = 0
    daily_token_cap: int | None = None
    daily_call_cap: int | None = None
    exempt: bool = False


class UsageSummary(BaseModel):
    day: str
    users: list[UsageView]


@router.get("/usage", response_model=UsageSummary)
async def list_usage(
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_admin),
    db: PostgresClient = Depends(get_postgres),
) -> UsageSummary:
    """Per-user usage for the current UTC day (admin view)."""
    rows = await db.usage_admin_summary(limit)
    return UsageSummary(
        day=datetime.now(UTC).date().isoformat(),
        users=[UsageView(**{**r, **(await _usage_extra(db, str(r["user_id"])))}) for r in rows],
    )


@router.get("/usage/{user_id}", response_model=UsageView)
async def get_usage(
    user_id: UUID,
    principal: Principal = Depends(require_admin),
    db: PostgresClient = Depends(get_postgres),
) -> UsageView:
    """One user's usage today plus their quota override."""
    user = await _get_user_or_404(db, user_id)
    usage = await db.usage_get(user_id)
    limits = await db.usage_limit_get(user_id) or {}
    return UsageView(
        user_id=str(user_id),
        username=user.get("username", ""),
        email=user.get("email", ""),
        tokens=int(usage.get("tokens", 0)),
        calls=int(usage.get("calls", 0)),
        daily_token_cap=limits.get("daily_token_cap"),
        daily_call_cap=limits.get("daily_call_cap"),
        exempt=bool(limits.get("exempt", False)),
    )


@router.put("/usage/{user_id}/limits", response_model=UsageView)
async def set_usage_limits(
    user_id: UUID,
    body: UsageLimitUpdate,
    principal: Principal = Depends(require_admin),
    db: PostgresClient = Depends(get_postgres),
) -> UsageView:
    """Set or clear a user's quota overrides (admin-changeable caps)."""
    await _get_user_or_404(db, user_id)
    row = await db.usage_limit_set(
        user_id,
        daily_token_cap=body.daily_token_cap,
        daily_call_cap=body.daily_call_cap,
        exempt=body.exempt,
    )
    usage = await db.usage_get(user_id)
    user = await _get_user_or_404(db, user_id)
    return UsageView(
        user_id=str(user_id),
        username=user.get("username", ""),
        email=user.get("email", ""),
        tokens=int(usage.get("tokens", 0)),
        calls=int(usage.get("calls", 0)),
        daily_token_cap=row.get("daily_token_cap"),
        daily_call_cap=row.get("daily_call_cap"),
        exempt=bool(row.get("exempt", False)),
    )


async def _usage_extra(db: PostgresClient, user_id: str) -> dict[str, Any]:
    """Quota-override columns for one user in the summary listing."""
    limits = await db.usage_limit_get(UUID(user_id)) or {}
    return {
        "daily_token_cap": limits.get("daily_token_cap"),
        "daily_call_cap": limits.get("daily_call_cap"),
        "exempt": bool(limits.get("exempt", False)),
    }


# ---------------------------------------------------------------------------
# Ownership backfill (pre-auth rows)
# ---------------------------------------------------------------------------


class OwnershipBackfillRequest(BaseModel):
    """Which owner the unowned rows should belong to."""

    owner_id: UUID | None = None


class OwnershipBackfillResponse(BaseModel):
    """How many rows were claimed."""

    owner_id: UUID
    worlds: int = 0
    multiverses: int = 0


@router.post("/ownership/backfill", response_model=OwnershipBackfillResponse)
async def backfill_ownership(
    body: OwnershipBackfillRequest | None = None,
    principal: Principal = Depends(require_admin),
    db: PostgresClient = Depends(get_postgres),
) -> OwnershipBackfillResponse:
    """Give the pre-auth rows (no owner) an owner, idempotently.

    Rows created before the ownership registry existed carry no owner, so
    only the local account can reach them. This claims them permanently.
    Running it twice is a no-op the second time, and rows that already
    have an owner are never touched.

    The target owner defaults to the local account — the account the
    unowned rows were reachable as.
    """
    owner_id = (body.owner_id if body else None) or LOCAL_USER_ID
    user = await db.user_get_by_id(owner_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    claimed = await db.ownership_backfill(owner_id)
    return OwnershipBackfillResponse(
        owner_id=owner_id,
        worlds=claimed.get("worlds", 0),
        multiverses=claimed.get("multiverses", 0),
    )
