"""Auto-reconciler for interrupted character-knowledge corrections.

Accepting a knowledge correction writes several stores (MongoDB, Qdrant,
fact properties) and then records the verdict. A crash between those
writes leaves the proposal ``pending`` with a
``knowledge_retraction_checkpoint``: whatever already landed is kept, and
only completing the accept makes the stores agree again. Retrying the
accept has always completed it; this module performs that retry
automatically (``CorrectionReconciler`` sweeps on an interval).

The checkpoint proves the proposal already passed review gating
(ownership, the G08 override requirement, the stale-attribution check), so
reconciliation skips the gates and finishes the write + verdict like a
successful accept. A correction whose target moved under it (the memory
text changed after the accept started) cannot be completed blindly — it is
marked ``knowledge_reconciliation_error`` and left for a human instead of
being retried forever.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from monitor_data.schemas.base import ProposalStatus
from monitor_data.schemas.proposed_changes import (
    CanonOverrideRecord,
    DecisionMetadata,
    ProposedChangeUpdate,
)

log = structlog.get_logger(__name__)

DEFAULT_INTERVAL_SECONDS = 60.0


async def finish_interrupted_correction(doc: dict[str, Any]) -> None:
    """Complete one interrupted accept. Raises when it cannot be completed."""
    from monitor_agents.canonkeeper.agent import CanonKeeper
    from monitor_data.tools.mongodb_tools.canon_audit import mongodb_record_canon_override
    from monitor_data.tools.mongodb_tools.proposals import (
        mongodb_update_proposed_change,
        prepare_knowledge_memory_change,
    )

    proposal_id = str(doc["proposal_id"])
    content = doc.get("content") or {}
    correction = content.get("knowledge_correction") or {}
    memory_already_absent = False
    keeper = CanonKeeper()
    if correction.get("item_kind") == "memory" and correction.get("action") in ("retract", "correct"):
        memory_already_absent = await asyncio.to_thread(
            prepare_knowledge_memory_change, UUID(proposal_id), content
        )
    await keeper.apply_knowledge_correction(content, memory_already_absent=memory_already_absent)
    try:
        from monitor_data.db.redis import get_redis_client

        await asyncio.to_thread(get_redis_client().delete_prefix, "solo_play:")
    except Exception as exc:  # noqa: BLE001  # cache failure must not undo an applied correction
        log.warning("could not invalidate knowledge cache", proposal_id=proposal_id, error=str(exc))
    try:
        mongodb_update_proposed_change(
            UUID(proposal_id),
            ProposedChangeUpdate(
                status=ProposalStatus.ACCEPTED,
                knowledge_correction_applied=True,
                decision_metadata=DecisionMetadata(
                    decided_by="auto-reconciler",
                    decided_at=datetime.now(UTC),
                    reason="Completing a knowledge correction whose accept was interrupted",
                    override_reason=None,
                ),
            ),
        )
    except ValueError as exc:
        # A concurrent accept may have finished the verdict first — that is
        # success, not a stall.
        from monitor_data.tools.mongodb_tools.proposals import mongodb_get_proposed_change

        current = await asyncio.to_thread(mongodb_get_proposed_change, UUID(proposal_id))
        if current is not None and current.status == ProposalStatus.ACCEPTED:
            return
        raise exc

    flag_kinds = sorted(
        {
            str(flag.get("kind"))
            for flag in (doc.get("review_flags") or [])
            if isinstance(flag, dict) and flag.get("kind")
        }
    )
    if "direct_contradiction" in flag_kinds:
        try:
            mongodb_record_canon_override(
                CanonOverrideRecord(
                    proposal_id=UUID(proposal_id),
                    owner_id=str(doc.get("owner_id") or "unknown"),
                    reason=(
                        "Override accepted by the GM; completed by the auto-reconciler "
                        "after the accepting write was interrupted"
                    ),
                    flag_kinds=flag_kinds,
                    hard_mode=False,
                )
            )
        except Exception as exc:  # noqa: BLE001  # the audit write must not undo the acceptance
            log.warning("could not record the reconciled override", proposal_id=proposal_id, error=str(exc))


class CorrectionReconciler:
    """Async-cooperative loop that finishes interrupted knowledge corrections.

    Never raises out of a tick; errors are logged and retried next tick.
    """

    def __init__(self, *, interval_seconds: float = DEFAULT_INTERVAL_SECONDS, limit: int = 20) -> None:
        self._interval = interval_seconds
        self._limit = limit
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Spawn the background sweep loop."""
        if self.is_running():
            log.info("CorrectionReconciler already running")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="correction-reconciler")
        log.info("CorrectionReconciler started", interval_seconds=self._interval)

    async def stop(self, timeout: float = 5.0) -> None:
        """Stop the loop gracefully and wait up to ``timeout`` seconds."""
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except TimeoutError:
            self._task.cancel()
        finally:
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001  # the sweep must never kill the loop
                log.warning("CorrectionReconciler tick failed", error=str(exc))
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def tick(self) -> dict[str, list[str]]:
        """One sweep over interrupted corrections. Returns what happened."""
        from monitor_data.tools.mongodb_tools.proposals import (
            mongodb_find_interrupted_corrections,
            mongodb_mark_correction_stalled,
        )

        docs = await asyncio.to_thread(mongodb_find_interrupted_corrections, self._limit)
        reconciled: list[str] = []
        stalled: list[str] = []
        for doc in docs:
            proposal_id = str(doc.get("proposal_id") or "")
            try:
                await finish_interrupted_correction(doc)
            except ValueError as exc:
                stalled.append(proposal_id)
                log.error("knowledge correction stalled; needs a human", proposal_id=proposal_id, error=str(exc))
                await asyncio.to_thread(mongodb_mark_correction_stalled, UUID(proposal_id), str(exc))
                continue
            except Exception as exc:  # noqa: BLE001  # transient store failure; retry next tick
                log.warning("knowledge correction reconcile will retry", proposal_id=proposal_id, error=str(exc))
                continue
            reconciled.append(proposal_id)
            log.info("knowledge correction reconciled", proposal_id=proposal_id)
        return {"reconciled": reconciled, "stalled": stalled}
