"""Read-only API for the append-only ChangeLog audit trail (Q-10).

Surfaces what CanonKeeper has committed to canon so a GM can audit the
history of canonical changes. The log is written by CanonKeeper; this
router never mutates it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from monitor_data.schemas.change_log import (
    ChangeLogFilter,
    ChangeLogListResponse,
    ChangeSubjectType,
    ChangeType,
)
from monitor_data.tools.mongodb_tools import mongodb_list_change_log

router = APIRouter()


@router.get("/change-log", response_model=ChangeLogListResponse)
async def list_change_log(
    subject_type: Optional[ChangeSubjectType] = None,
    subject_id: Optional[UUID] = None,
    change_type: Optional[ChangeType] = None,
    author: Optional[str] = None,
    transaction_id: Optional[UUID] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> ChangeLogListResponse:
    """Query the append-only canonical change log (newest first by default)."""
    try:
        return mongodb_list_change_log(
            ChangeLogFilter(
                subject_type=subject_type,
                subject_id=subject_id,
                change_type=change_type,
                author=author,
                transaction_id=transaction_id,
                since=since,
                until=until,
                limit=limit,
                offset=offset,
                sort_order=sort_order,
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Could not read change log: {exc}") from exc
