"""
Test the ExtractionStatus -> UI status mapping in ingest_shared.

INGESTION_PIPELINE_AUDIT follow-up: failed docs were rendering as
"indexed" because _STATUS_MAP was missing ExtractionStatus.FAILED.
"""

from monitor_data.schemas.base import ExtractionStatus

from monitor_ui.routers.ingest_shared import _STATUS_MAP


class TestStatusMap:
    def test_failed_maps_to_failed(self):
        assert _STATUS_MAP[ExtractionStatus.FAILED.value] == "failed"

    def test_completed_maps_to_indexed(self):
        assert _STATUS_MAP[ExtractionStatus.COMPLETED.value] == "indexed"

    def test_pending_maps_to_saved(self):
        assert _STATUS_MAP[ExtractionStatus.PENDING.value] == "saved"

    def test_extracting_maps_to_processing(self):
        assert _STATUS_MAP[ExtractionStatus.EXTRACTING.value] == "processing"

    def test_all_canonical_statuses_mapped(self):
        # Every member of ExtractionStatus must have an explicit entry;
        # otherwise a new enum value silently falls into the default.
        for member in ExtractionStatus:
            assert member.value in _STATUS_MAP, member
