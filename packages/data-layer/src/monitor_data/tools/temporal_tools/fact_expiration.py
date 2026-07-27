"""
Fact expiration and validity checking (Temporal & Contradiction Gap).

LAYER: 1 (data-layer)

This module provides utilities for checking whether facts are valid at
specific points in time, and for managing the lifecycle of facts with
temporal constraints.

Key functionality:
  1. check_fact_validity — Determine if a fact is valid at a given time
  2. batch_check_fact_validity — Check multiple facts for validity
  3. expire_facts — Tombstone facts that are no longer valid
  4. get_active_facts — Retrieve only facts that are currently valid

Usage::

    from monitor_data.tools.temporal_tools.fact_expiration import (
        check_fact_validity,
        batch_check_fact_validity,
    )

    # Check a single fact
    validity = check_fact_validity(
        fact={"id": uuid, "statement": "...", "time_ref": ..., "duration": 86400},
        check_time=datetime.now(timezone.utc),
    )
    if validity.status == FactValidityStatus.EXPIRED:
        # Fact is no longer true

    # Check multiple facts
    batch = batch_check_fact_validity(
        facts=[...],
        check_time=datetime.now(timezone.utc),
        universe_id=uuid,
    )
    # batch.facts_to_expire contains IDs of facts to tombstone
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from monitor_data.schemas.temporal_validation import (
    FactExpirationBatch,
    FactValidity,
    FactValidityStatus,
)

logger = logging.getLogger(__name__)

# Threshold for "expiring soon" warnings
_EXPIRING_SOON_THRESHOLD = timedelta(hours=24)


# =============================================================================
# PUBLIC API
# =============================================================================


def check_fact_validity(
    fact: dict[str, Any],
    check_time: datetime,
) -> FactValidity:
    """
    Determine if a fact is valid at a specific point in time.

    Args:
        fact: Fact dict with 'id', 'statement', 'time_ref', 'duration'.
        check_time: The time at which to check validity.

    Returns:
        FactValidity with status and timing information.
    """
    fact_id = fact.get("id")
    if not fact_id:
        raise ValueError("Fact must have an 'id' field")

    statement = fact.get("statement", "")
    time_ref = fact.get("time_ref")
    duration = fact.get("duration")

    # Check if fact is timeless (no temporal constraints)
    is_timeless = time_ref is None and duration is None
    if is_timeless:
        return FactValidity(
            fact_id=UUID(str(fact_id)),
            statement=statement,
            time_ref=time_ref,
            duration=duration,
            expires_at=None,
            status=FactValidityStatus.ALWAYS_VALID,
            check_time=check_time,
            is_timeless=True,
            is_expiring_soon=False,
            time_until_expiry=None,
            time_until_start=None,
        )

    # Calculate expiration time
    expires_at: datetime | None = None
    if time_ref and duration:
        expires_at = time_ref + timedelta(seconds=duration)

    # Determine validity status
    status = _determine_validity_status(
        time_ref=time_ref,
        duration=duration,
        expires_at=expires_at,
        check_time=check_time,
    )

    # Calculate timing deltas
    time_until_expiry: timedelta | None = None
    time_until_start: timedelta | None = None
    is_expiring_soon = False

    if expires_at and status == FactValidityStatus.VALID:
        time_until_expiry = expires_at - check_time
        is_expiring_soon = time_until_expiry > timedelta(0) and time_until_expiry <= _EXPIRING_SOON_THRESHOLD

    if time_ref and status == FactValidityStatus.NOT_YET_STARTED:
        time_until_start = time_ref - check_time

    return FactValidity(
        fact_id=UUID(str(fact_id)),
        statement=statement,
        time_ref=time_ref,
        duration=duration,
        expires_at=expires_at,
        status=status,
        check_time=check_time,
        is_timeless=False,
        is_expiring_soon=is_expiring_soon,
        time_until_expiry=time_until_expiry,
        time_until_start=time_until_start,
    )


def batch_check_fact_validity(
    facts: Sequence[dict[str, Any]],
    check_time: datetime,
    universe_id: UUID,
) -> FactExpirationBatch:
    """
    Check multiple facts for validity at a specific point in time.

    Args:
        facts: Sequence of fact dicts with 'id', 'statement', 'time_ref', 'duration'.
        check_time: The time at which to check validity.
        universe_id: The universe containing these facts.

    Returns:
        FactExpirationBatch with categorized facts and expiration recommendations.
    """
    batch = FactExpirationBatch(
        universe_id=universe_id,
        check_time=check_time,
    )

    for fact in facts:
        validity = check_fact_validity(fact, check_time)

        if validity.status == FactValidityStatus.VALID:
            batch.valid_facts.append(validity)
        elif validity.status == FactValidityStatus.EXPIRED:
            batch.expired_facts.append(validity)
        elif validity.status == FactValidityStatus.NOT_YET_STARTED:
            batch.not_yet_started_facts.append(validity)
        elif validity.status == FactValidityStatus.ALWAYS_VALID:
            batch.always_valid_facts.append(validity)
        else:
            # Unknown status - treat as valid for safety
            logger.warning(f"Unknown validity status for fact {validity.fact_id}")
            batch.valid_facts.append(validity)

    batch.compute_totals()
    return batch


def get_active_facts(
    facts: Sequence[dict[str, Any]],
    check_time: datetime,
) -> list[dict[str, Any]]:
    """
    Filter to only facts that are currently valid.

    Args:
        facts: Sequence of fact dicts.
        check_time: The time at which to check validity.

    Returns:
        List of fact dicts that are valid at check_time.
    """
    active_facts = []

    for fact in facts:
        validity = check_fact_validity(fact, check_time)
        if validity.status in (FactValidityStatus.VALID, FactValidityStatus.ALWAYS_VALID):
            active_facts.append(fact)

    return active_facts


# =============================================================================
# PRIVATE HELPERS
# =============================================================================


def _determine_validity_status(
    time_ref: datetime | None,
    duration: int | None,
    expires_at: datetime | None,
    check_time: datetime,
) -> FactValidityStatus:
    """
    Determine the validity status based on temporal parameters.
    """
    # No time constraints
    if time_ref is None and duration is None:
        return FactValidityStatus.ALWAYS_VALID

    # Has time_ref but no duration - valid starting from time_ref
    if time_ref is not None and duration is None:
        if check_time < time_ref:
            return FactValidityStatus.NOT_YET_STARTED
        else:
            return FactValidityStatus.VALID

    # Has duration but no time_ref - valid for duration from creation
    if time_ref is None and duration is not None:
        # This is a weird case - duration without start time
        # Assume it's valid from now until duration expires
        # But we don't have a start time, so we can't calculate
        # Treat as always valid for safety
        logger.warning("Fact has duration but no time_ref - treating as always valid")
        return FactValidityStatus.ALWAYS_VALID

    # Has both time_ref and duration
    if time_ref and check_time < time_ref:
        return FactValidityStatus.NOT_YET_STARTED
    elif expires_at and check_time >= expires_at:
        return FactValidityStatus.EXPIRED
    else:
        return FactValidityStatus.VALID
