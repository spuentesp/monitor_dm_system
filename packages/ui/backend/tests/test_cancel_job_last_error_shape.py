"""Regression test: cancelling a job must leave last_error in a shape that
survives a real read-back.

Live bug (found 2026-07-22 while investigating a separate crash): the
/cancel endpoint wrote last_error="Cancelled by user" (a bare string)
directly via pymongo, bypassing IngestionJobUpdate validation. Data-layer's
_hydrate_last_error explicitly raises ValueError on any non-dict last_error
read back from Mongo -- so every cancelled job became permanently unreadable
via mongodb_get_ingestion_job / `monitor ingest status` / the job list UI.
This matches bare-string last_error values observed on real job records
from earlier cancellations ("Cancelled by operator via ingest-jobs CLI").
"""

from __future__ import annotations

from monitor_data.schemas.ingestion_jobs import LastError


def test_cancel_last_error_payload_hydrates_via_lasterror_model():
    """The exact dict shape the /cancel endpoint now writes must construct a
    valid LastError -- i.e. it would survive _hydrate_last_error's
    isinstance(raw, dict) + LastError(**raw) round trip."""
    payload = {
        "category": "unknown",
        "message": "Cancelled by user",
        "failed_at": "2026-07-22T00:00:00+00:00",
        "detail": "Job cancelled via the /cancel endpoint.",
    }

    hydrated = LastError(**payload)

    assert hydrated.message == "Cancelled by user"
    assert hydrated.category.value == "unknown"
