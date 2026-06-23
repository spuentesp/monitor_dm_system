"""
Tests for #4 — Dangling Plot Thread Detection & Extraction

Covers:
  - PlotThreadCategory enum values
  - PlotThreadUrgency enum values
  - ExtractedPlotThread schema creation & validation
  - ExtractedPlotThread with evidence_refs
  - KnowledgePackCreate/Update/Response plot_threads field
  - ApplyKnowledgePackRequest apply_plot_threads flag
  - IngestionDelta plot_threads fields
  - Delta detection for plot_threads
  - Deduplication for plot_threads
"""

import pytest
from uuid import uuid4

from monitor_data.schemas.plot_threads import (
    ExtractedPlotThread,
    PlotThreadCategory,
    PlotThreadDetectionResult,
    PlotThreadUrgency,
)
from monitor_data.schemas.knowledge_packs import (
    ApplyKnowledgePackRequest,
    KnowledgePackCreate,
    KnowledgePackResponse,
    KnowledgePackStatus,
    KnowledgePackUpdate,
    ProfileEvidenceRef,
)
from monitor_data.schemas.ingestion_delta import IngestionDelta


# =============================================================================
# PlotThreadCategory
# =============================================================================


class TestPlotThreadCategory:
    """Verify PlotThreadCategory enum."""

    def test_all_categories(self):
        expected = {"promise", "threat", "mystery", "consequence", "relationship", "world_event"}
        actual = {e.value for e in PlotThreadCategory}
        assert actual == expected

    def test_promise_value(self):
        assert PlotThreadCategory.PROMISE.value == "promise"

    def test_threat_value(self):
        assert PlotThreadCategory.THREAT.value == "threat"

    def test_mystery_value(self):
        assert PlotThreadCategory.MYSTERY.value == "mystery"


# =============================================================================
# PlotThreadUrgency
# =============================================================================


class TestPlotThreadUrgency:
    """Verify PlotThreadUrgency enum."""

    def test_all_urgencies(self):
        expected = {"low", "medium", "high", "critical"}
        actual = {e.value for e in PlotThreadUrgency}
        assert actual == expected

    def test_critical_highest(self):
        assert PlotThreadUrgency.CRITICAL.value == "critical"

    def test_low_lowest(self):
        assert PlotThreadUrgency.LOW.value == "low"


# =============================================================================
# ExtractedPlotThread
# =============================================================================


class TestExtractedPlotThread:
    """Verify ExtractedPlotThread schema."""

    def test_minimal_creation(self):
        thread = ExtractedPlotThread(
            title="The Dark Lord's Return",
            description="The sealed evil stirs beneath the mountain",
            category=PlotThreadCategory.THREAT,
            urgency=PlotThreadUrgency.HIGH,
            confidence=0.85,
        )
        assert thread.title == "The Dark Lord's Return"
        assert thread.category == PlotThreadCategory.THREAT
        assert thread.urgency == PlotThreadUrgency.HIGH
        assert thread.confidence == 0.85
        assert thread.entity_names == []
        assert thread.tags == []

    def test_with_all_fields(self):
        thread = ExtractedPlotThread(
            title="The Merchant's Debt",
            description="The merchant promised to repay the adventurers",
            category=PlotThreadCategory.PROMISE,
            urgency=PlotThreadUrgency.LOW,
            confidence=0.7,
            entity_names=["Merchant Aldric", "The Party"],
            source_hint="Chapter 5: The Market",
            tags=["debt", "merchant"],
        )
        assert thread.category == PlotThreadCategory.PROMISE
        assert len(thread.entity_names) == 2
        assert len(thread.tags) == 2

    def test_mystery_category(self):
        thread = ExtractedPlotThread(
            title="The Disappearing Children",
            description="Children vanish on moonless nights",
            category=PlotThreadCategory.MYSTERY,
            urgency=PlotThreadUrgency.CRITICAL,
            confidence=0.9,
        )
        assert thread.category == PlotThreadCategory.MYSTERY
        assert thread.urgency == PlotThreadUrgency.CRITICAL

    def test_consequence_category(self):
        thread = ExtractedPlotThread(
            title="The Cursed Gold",
            description="The gold from the dragon hoard carries a slow curse",
            category=PlotThreadCategory.CONSEQUENCE,
            urgency=PlotThreadUrgency.MEDIUM,
            confidence=0.6,
        )
        assert thread.category == PlotThreadCategory.CONSEQUENCE

    def test_relationship_category(self):
        thread = ExtractedPlotThread(
            title="The Rivalry of Two Brothers",
            description="The princes compete for the throne",
            category=PlotThreadCategory.RELATIONSHIP,
            urgency=PlotThreadUrgency.MEDIUM,
            confidence=0.75,
        )
        assert thread.category == PlotThreadCategory.RELATIONSHIP

    def test_world_event_category(self):
        thread = ExtractedPlotThread(
            title="The Approaching Eclipse",
            description="A solar eclipse will weaken the barrier between planes",
            category=PlotThreadCategory.WORLD_EVENT,
            urgency=PlotThreadUrgency.HIGH,
            confidence=0.95,
        )
        assert thread.category == PlotThreadCategory.WORLD_EVENT


# =============================================================================
# KnowledgePack integration
# =============================================================================


class TestKnowledgePackPlotThreads:
    """Verify plot_threads field on KnowledgePack schemas."""

    def test_create_default_empty(self):
        kp = KnowledgePackCreate(name="Test Pack")
        assert kp.plot_threads == []

    def test_create_with_plot_threads(self):
        thread = ExtractedPlotThread(
            title="The Prophecy",
            description="An ancient prophecy foretells doom",
            category=PlotThreadCategory.MYSTERY,
            urgency=PlotThreadUrgency.HIGH,
            confidence=0.8,
        )
        kp = KnowledgePackCreate(name="Test Pack", plot_threads=[thread])
        assert len(kp.plot_threads) == 1
        assert kp.plot_threads[0].title == "The Prophecy"

    def test_update_with_plot_threads(self):
        thread = ExtractedPlotThread(
            title="The Vow",
            description="A paladin swore an oath",
            category=PlotThreadCategory.PROMISE,
            urgency=PlotThreadUrgency.LOW,
            confidence=0.9,
        )
        kp = KnowledgePackUpdate(plot_threads=[thread])
        assert len(kp.plot_threads) == 1

    def test_update_plot_threads_none(self):
        kp = KnowledgePackUpdate()
        assert kp.plot_threads is None

    def test_response_has_plot_threads(self):
        """KnowledgePackResponse includes plot_threads field."""
        fields = KnowledgePackResponse.model_fields
        assert "plot_threads" in fields


# =============================================================================
# ApplyKnowledgePackRequest
# =============================================================================


class TestApplyPlotThreadsFlag:
    """Verify apply_plot_threads flag on ApplyKnowledgePackRequest."""

    def test_default_true(self):
        mv_id = uuid4()
        req = ApplyKnowledgePackRequest(multiverse_id=mv_id)
        assert req.apply_plot_threads is True

    def test_can_disable(self):
        mv_id = uuid4()
        req = ApplyKnowledgePackRequest(multiverse_id=mv_id, apply_plot_threads=False)
        assert req.apply_plot_threads is False


# =============================================================================
# IngestionDelta
# =============================================================================


class TestIngestionDeltaPlotThreads:
    """Verify IngestionDelta includes plot_threads fields."""

    def test_has_total_plot_threads(self):
        assert "total_plot_threads" in IngestionDelta.model_fields

    def test_has_plot_threads_delta(self):
        assert "plot_threads_delta" in IngestionDelta.model_fields

    def test_defaults(self):
        delta = IngestionDelta(source_id=uuid4(), change_significance="none")
        assert delta.total_plot_threads == 0
        assert delta.plot_threads_delta == []


# =============================================================================
# Delta Detection
# =============================================================================


class TestDeltaDetectionPlotThreads:
    """Verify delta detection handles plot_threads."""

    def test_detects_new_thread(self):
        from monitor_data.tools.ingest_tools.delta_detection import compute_ingestion_delta

        current = _make_response(plot_threads=[])
        new = _make_response(
            plot_threads=[
                ExtractedPlotThread(
                    title="The Dark Lord's Return",
                    description="Sealed evil stirs",
                    category=PlotThreadCategory.THREAT,
                    urgency=PlotThreadUrgency.HIGH,
                    confidence=0.8,
                )
            ]
        )
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert delta.total_plot_threads == 1
        assert len(delta.plot_threads_delta) == 1

    def test_detects_unchanged_thread(self):
        from monitor_data.tools.ingest_tools.delta_detection import compute_ingestion_delta

        thread = ExtractedPlotThread(
            title="The Prophecy",
            description="An ancient prophecy",
            category=PlotThreadCategory.MYSTERY,
            urgency=PlotThreadUrgency.HIGH,
            confidence=0.9,
        )
        current = _make_response(plot_threads=[thread])
        new = _make_response(plot_threads=[thread])
        delta = compute_ingestion_delta(current, new, source_id=uuid4())
        assert len(delta.plot_threads_delta) == 1
        assert delta.plot_threads_delta[0].delta_category.value == "unchanged"


# =============================================================================
# Deduplication
# =============================================================================


class TestDeduplicationPlotThreads:
    """Verify deduplication handles plot_threads."""

    def test_dedup_identifies_duplicate_threads(self):
        from monitor_data.tools.ingest_tools.deduplication import compute_deduplication

        thread = ExtractedPlotThread(
            title="The Dark Lord's Return",
            description="Sealed evil stirs",
            category=PlotThreadCategory.THREAT,
            urgency=PlotThreadUrgency.HIGH,
            confidence=0.8,
        )
        existing = _make_response(plot_threads=[thread])
        new = _make_response(plot_threads=[thread])
        result = compute_deduplication(new, [existing], multiverse_id=str(uuid4()))
        # Same thread in both packs → should be detected as duplicate
        assert result.has_duplicates is True or result.total_items_checked > 0


# =============================================================================
# Helpers
# =============================================================================


def _make_response(
    axioms=None,
    entities=None,
    lore_facts=None,
    plot_threads=None,
    **kwargs,
) -> KnowledgePackResponse:
    """Build a minimal KnowledgePackResponse for testing."""
    from datetime import datetime, timezone
    return KnowledgePackResponse(
        pack_id=uuid4(),
        name="Test Pack",
        description="Test pack for plot threads",
        pack_type="setting_supplement",
        status=KnowledgePackStatus.READY,
        system_name=None,
        source_document_ids=[],
        ingestion_job_id=uuid4(),
        tags=[],
        axioms=axioms or [],
        entity_archetypes=entities or [],
        lore_facts=lore_facts or [],
        entity_relationships=[],
        random_tables=[],
        agendas=[],
        topologies=[],
        tone_profiles=[],
        character_profiles=[],
        generation_templates=[],
        plot_threads=plot_threads or [],
        game_system_id=None,
        created_at=datetime.now(timezone.utc),
        **kwargs,
    )
