"""
Tests for LLMExecutionSummary: per-batch counters + per-section failure list.

The summary is what the analyzer writes back to the ingestion job doc, so
it's the only place downstream UIs learn about partial-extraction state.
"""

from monitor_data.schemas.base import IngestionStatus

from monitor_agents.analyzer._models import LLMExecutionSummary


class TestLLMExecutionSummary:
    def test_default_state_is_completed(self):
        s = LLMExecutionSummary()
        assert s.final_status() is IngestionStatus.COMPLETED
        assert s.total_batches == 0
        assert s.failed_sections == []

    def test_record_section_failure_appends(self):
        s = LLMExecutionSummary()
        s.record_section_failure(
            section_path="Chapter 3: Character",
            stage="game_rule_extraction",
            reason="ValidationError: rule_type='class' is invalid",
        )
        assert len(s.failed_sections) == 1
        entry = s.failed_sections[0]
        assert entry["section_path"] == "Chapter 3: Character"
        assert entry["stage"] == "game_rule_extraction"
        assert "ValidationError" in entry["reason"]

    def test_record_section_failure_caps_at_200(self):
        s = LLMExecutionSummary()
        for i in range(250):
            s.record_section_failure(
                section_path=f"section_{i}",
                stage="game_rule_extraction",
                reason="boom",
            )
        assert len(s.failed_sections) == 200

    def test_failed_sections_truncate_path_and_reason(self):
        s = LLMExecutionSummary()
        long_path = "x" * 500
        long_reason = "r" * 1000
        s.record_section_failure(
            section_path=long_path,
            stage="entity_extraction",
            reason=long_reason,
        )
        entry = s.failed_sections[0]
        assert len(entry["section_path"]) == 200
        assert len(entry["reason"]) == 500

    def test_final_status_partial_when_failed_batches(self):
        s = LLMExecutionSummary(total_batches=10, succeeded_batches=8, failed_batches=2)
        assert s.final_status() is IngestionStatus.PARTIAL

    def test_final_status_blocked_provider_short_circuit(self):
        s = LLMExecutionSummary(succeeded_batches=0, blocked_provider=True, total_batches=5, failed_batches=5)
        assert s.final_status() is IngestionStatus.FAILED_NON_RETRYABLE

    def test_as_job_update_includes_new_fields(self):
        s = LLMExecutionSummary(
            total_batches=10,
            succeeded_batches=8,
            failed_batches=2,
            retried_batches=3,
            total_attempts=13,
            current_provider="ollama",
            current_model="qwen2.5",
            last_error="boom",
        )
        s.record_section_failure(section_path="s1", stage="game_rule_extraction", reason="r")
        update = s.as_job_update()
        assert update["total_batches"] == 10
        assert update["total_attempts"] == 13
        assert update["failed_sections"] == [{"section_path": "s1", "stage": "game_rule_extraction", "reason": "r"}]
        assert update["partial"] is True
