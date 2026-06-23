"""Data classes for the Analyzer agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from monitor_data.schemas.base import IngestionStatus


@dataclass(slots=True)
class AnalysisRunResult:
    """Final analyzer outcome, including truthful reliability metadata."""

    pack_id: UUID
    status: IngestionStatus = IngestionStatus.COMPLETED
    total_batches: int = 0
    succeeded_batches: int = 0
    failed_batches: int = 0
    retried_batches: int = 0
    current_provider: Optional[str] = None
    current_model: Optional[str] = None
    last_error: Optional[str] = None

    @property
    def partial(self) -> bool:
        return self.failed_batches > 0


@dataclass(slots=True)
class LLMExecutionSummary:
    """Mutable per-analysis counters used to surface retry/partial state to MongoDB."""

    total_batches: int = 0
    succeeded_batches: int = 0
    failed_batches: int = 0
    retried_batches: int = 0
    current_provider: Optional[str] = None
    current_model: Optional[str] = None
    last_error: Optional[str] = None
    blocked_provider: bool = False

    def final_status(self) -> IngestionStatus:
        if self.blocked_provider and self.succeeded_batches == 0:
            return IngestionStatus.FAILED_NON_RETRYABLE
        if self.blocked_provider:
            return IngestionStatus.BLOCKED_PROVIDER
        if self.failed_batches > 0:
            return IngestionStatus.PARTIAL
        return IngestionStatus.COMPLETED

    def as_job_update(self) -> dict[str, Any]:
        return {
            "total_batches": self.total_batches,
            "succeeded_batches": self.succeeded_batches,
            "failed_batches": self.failed_batches,
            "retried_batches": self.retried_batches,
            "current_provider": self.current_provider,
            "current_model": self.current_model,
            "last_error": self.last_error,
            "partial": self.failed_batches > 0,
        }
