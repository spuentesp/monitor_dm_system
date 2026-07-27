"""Data classes for the Analyzer agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
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
    total_attempts: int = 0
    current_provider: str | None = None
    current_model: str | None = None
    last_error: str | None = None
    failed_sections: list[dict[str, str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.failed_sections is None:
            self.failed_sections = []

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
    # Total LLM attempts (each retry of a batch increments this; total_batches
    # counts logical batches only). Capped at len(failed_sections) growth.
    total_attempts: int = 0
    current_provider: str | None = None
    current_model: str | None = None
    last_error: str | None = None
    blocked_provider: bool = False
    # Per-section failure list. Each entry: {section_path, stage, reason}.
    # Capped at 200 entries so a runaway book doesn't bloat the job doc.
    failed_sections: list[dict[str, str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.failed_sections is None:
            self.failed_sections = []

    def record_section_failure(self, *, section_path: str, stage: str, reason: str, cap: int = 200) -> None:
        if len(self.failed_sections) >= cap:
            return
        self.failed_sections.append({"section_path": section_path[:200], "stage": stage, "reason": reason[:500]})

    def final_status(self) -> IngestionStatus:
        if self.blocked_provider and self.succeeded_batches == 0:
            return IngestionStatus.FAILED_NON_RETRYABLE
        if self.blocked_provider:
            return IngestionStatus.BLOCKED_PROVIDER
        if self.failed_batches > 0:
            return IngestionStatus.PARTIAL
        return IngestionStatus.COMPLETED

    def as_job_update(self) -> dict[str, Any]:
        # NOTE: this dict is splatted directly into IngestionJobUpdate(**kwargs)
        # at every call site (analyzer/_core.py _record_llm_attempt, and the
        # pipeline's final success-path update). IngestionJobUpdate.last_error
        # is a structured LastError model, not the plain message string this
        # summary tracks -- passing self.last_error here raises a pydantic
        # ValidationError (fatal at the one unguarded call site; silently
        # swallowed everywhere else via _update_job's try/except, which is why
        # this went unnoticed until it crashed a real ingest at progress=0.95).
        # The message itself is already surfaced via `warnings`/`activity_log`
        # in _record_llm_attempt, so it is intentionally NOT included here.
        return {
            "total_batches": self.total_batches,
            "succeeded_batches": self.succeeded_batches,
            "failed_batches": self.failed_batches,
            "retried_batches": self.retried_batches,
            "total_attempts": self.total_attempts,
            "current_provider": self.current_provider,
            "current_model": self.current_model,
            "partial": self.failed_batches > 0,
            "failed_sections": list(self.failed_sections),
        }
