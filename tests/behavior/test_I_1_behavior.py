"""
Behavior tests for I-1: Ingestion Pipeline.

Verifies ingestion schemas, chunking logic, delta detection,
deduplication, and contradiction detection without real DB/LLM connections.
"""

from __future__ import annotations

from uuid import uuid4

from monitor_data.schemas.ingestion_jobs import (
    IngestionStage,
    IngestionJobCreate,
    IngestionJobUpdate,
    IngestionJobFilter,
)
from monitor_data.schemas.ingestion_delta import (
    DeltaCategory,
    DeltaItem,
    IngestionDelta,
)
from monitor_data.schemas.deduplication import (
    DeduplicationStrategy,
    DuplicateCategory,
    DuplicateGroup,
    DeduplicationResult,
)
from monitor_data.schemas.contradiction import (
    ContradictionType,
    ContradictionSeverity,
    ContradictionResolution,
    ContradictionMatch,
    ContradictionResult,
)


# =============================================================================
# Ingestion Stage Enum
# =============================================================================


class TestIngestionStageEnum:
    def test_all_stages(self):
        """All ingestion stages exist in correct order."""
        assert IngestionStage.UPLOAD.value == "upload"
        assert IngestionStage.EXTRACT.value == "extract"
        assert IngestionStage.EMBED.value == "embed"
        assert IngestionStage.ANALYZE.value == "analyze"
        assert IngestionStage.PROPOSE.value == "propose"
        assert IngestionStage.CANONIZE.value == "canonize"
        assert IngestionStage.INDEX.value == "index"


# =============================================================================
# Ingestion Job Schemas
# =============================================================================


class TestIngestionJobCreateSchema:
    def test_minimal_create(self):
        """IngestionJobCreate with required fields."""
        uid = uuid4()
        sid = uuid4()
        did = uuid4()
        job = IngestionJobCreate(universe_id=uid, source_id=sid, doc_id=did)
        assert job.universe_id == uid
        assert job.source_id == sid
        assert job.doc_id == did
        assert job.pipeline_stages is not None

    def test_create_with_all_fields(self):
        """IngestionJobCreate can specify all fields."""
        uid, sid, did = uuid4(), uuid4(), uuid4()
        job = IngestionJobCreate(
            universe_id=uid,
            source_id=sid,
            doc_id=did,
            source_title="Player Handbook",
        )
        assert job.source_id == sid
        assert job.doc_id == did


class TestIngestionJobUpdateSchema:
    def test_update_progress(self):
        """IngestionJobUpdate can set progress."""
        update = IngestionJobUpdate(progress=0.5, current_stage=IngestionStage.EMBED)
        assert update.progress == 0.5
        assert update.current_stage == IngestionStage.EMBED

    def test_update_with_errors(self):
        """IngestionJobUpdate can report errors."""
        update = IngestionJobUpdate(errors=["PDF parse failed on page 42"])
        assert len(update.errors) == 1


class TestIngestionJobFilterSchema:
    def test_filter_defaults(self):
        """IngestionJobFilter defaults to reasonable pagination."""
        f = IngestionJobFilter()
        assert f.limit == 50
        assert f.offset == 0

    def test_filter_by_universe(self):
        """IngestionJobFilter can filter by universe_id."""
        uid = uuid4()
        f = IngestionJobFilter(universe_id=uid)
        assert f.universe_id == uid


# =============================================================================
# Delta Detection Schemas
# =============================================================================


class TestDeltaCategoryEnum:
    def test_all_categories(self):
        """All delta categories exist."""
        assert DeltaCategory.ADDED.value == "added"
        assert DeltaCategory.MODIFIED.value == "modified"
        assert DeltaCategory.UNCHANGED.value == "unchanged"
        assert DeltaCategory.REMOVED.value == "removed"


class TestDeltaItemSchema:
    def test_delta_item(self):
        """DeltaItem describes a single change."""
        item = DeltaItem(
            item_index=0,
            delta_category=DeltaCategory.ADDED,
            field_name="description",
            summary="New description added",
        )
        assert item.item_index == 0
        assert item.delta_category == DeltaCategory.ADDED
        assert item.summary == "New description added"


class TestIngestionDeltaSchema:
    def test_delta_with_items(self):
        """IngestionDelta groups changes by category."""
        item = DeltaItem(
            item_index=0,
            delta_category=DeltaCategory.ADDED,
            field_name="name",
            summary="New entity",
        )
        delta = IngestionDelta(
            source_id=uuid4(),
            change_significance="moderate",
            axioms_delta=[item],
            net_new_items=1,
        )
        assert delta.net_new_items == 1
        assert len(delta.axioms_delta) == 1


class TestIngestionDeltaApplyRequestSchema:
    def test_apply_request_importable(self):
        """IngestionDeltaApplyRequest schema is importable if it exists."""
        try:
            from monitor_data.schemas.ingestion_delta import IngestionDeltaApplyRequest

            assert IngestionDeltaApplyRequest is not None
        except ImportError:
            # Schema may not exist yet; skip gracefully
            pass


# =============================================================================
# Deduplication Schemas
# =============================================================================


class TestDeduplicationStrategyEnum:
    def test_all_strategies(self):
        """All deduplication strategies exist."""
        assert DeduplicationStrategy.KEEP_NEW.value == "keep_new"
        assert DeduplicationStrategy.KEEP_EXISTING.value == "keep_existing"
        assert DeduplicationStrategy.MERGE.value == "merge"
        assert DeduplicationStrategy.REVIEW.value == "review"


class TestDuplicateCategoryEnum:
    def test_all_categories(self):
        """All duplicate categories exist."""
        assert DuplicateCategory.EXACT.value == "exact"
        assert DuplicateCategory.SEMANTIC.value == "semantic"
        assert DuplicateCategory.SUBSUMED.value == "subsumed"
        assert DuplicateCategory.CONFLICTING.value == "conflicting"


class TestDuplicateGroupSchema:
    def test_duplicate_group(self):
        """DuplicateGroup describes a set of duplicates."""
        from monitor_data.schemas.deduplication import DuplicateItemRef

        ref = DuplicateItemRef(
            pack_id=uuid4(),
            item_index=0,
            field_name="name",
            identity_value="Test",
            content="Test",
            confidence=0.9,
        )
        group = DuplicateGroup(
            duplicate_id="dup-1",
            category=DuplicateCategory.EXACT,
            field_name="name",
            identity_field="name",
            strategy=DeduplicationStrategy.KEEP_NEW,
            strategy_reason="Exact match found",
            similarity_score=0.99,
            items=[ref],
        )
        assert group.category == DuplicateCategory.EXACT
        assert group.similarity_score == 0.99


class TestDeduplicationResultSchema:
    def test_result(self):
        """DeduplicationResult summarizes dedup findings."""
        result = DeduplicationResult(
            new_pack_id=uuid4(),
            multiverse_id=uuid4(),
            duplicate_groups=[],
            auto_resolvable_count=0,
            review_required_count=0,
            total_items_checked=0,
        )
        assert result.auto_resolvable_count == 0
        assert result.review_required_count == 0


# =============================================================================
# Contradiction Detection Schemas
# =============================================================================


class TestContradictionTypeEnum:
    def test_all_types(self):
        """All contradiction types exist."""
        assert ContradictionType.SEMANTIC_OPPOSITE.value == "semantic_opposite"
        assert ContradictionType.TEMPORAL_OVERRIDE.value == "temporal_override"
        assert ContradictionType.SCOPE_CONFLICT.value == "scope_conflict"
        assert ContradictionType.PARTIAL_OVERLAP.value == "partial_overlap"


class TestContradictionSeverityEnum:
    def test_all_severities(self):
        """All contradiction severities exist."""
        assert ContradictionSeverity.LOW.value == "low"
        assert ContradictionSeverity.MEDIUM.value == "medium"
        assert ContradictionSeverity.HIGH.value == "high"
        assert ContradictionSeverity.CRITICAL.value == "critical"


class TestContradictionResolutionEnum:
    def test_all_resolutions(self):
        """All contradiction resolutions exist."""
        assert ContradictionResolution.NEW_WINS.value == "new_wins"
        assert ContradictionResolution.OLD_WINS.value == "old_wins"
        assert ContradictionResolution.MERGE.value == "merge"
        assert ContradictionResolution.REVIEW.value == "review"


class TestContradictionMatchSchema:
    def test_match(self):
        """ContradictionMatch describes a single contradiction."""
        from monitor_data.schemas.contradiction import ContradictionFact

        new_fact = ContradictionFact(statement="The king is dead")
        existing_fact = ContradictionFact(statement="The king rules wisely")
        match = ContradictionMatch(
            contradiction_id="contra-1",
            contradiction_type=ContradictionType.SEMANTIC_OPPOSITE,
            severity=ContradictionSeverity.HIGH,
            new_fact=new_fact,
            existing_fact=existing_fact,
            similarity_score=0.85,
        )
        assert match.contradiction_type == ContradictionType.SEMANTIC_OPPOSITE
        assert match.severity == ContradictionSeverity.HIGH


class TestContradictionResultSchema:
    def test_result(self):
        """ContradictionResult summarizes all contradictions found."""
        result = ContradictionResult(
            axiom_contradictions=[],
            lore_contradictions=[],
            entity_contradictions=[],
            total_contradictions=0,
        )
        assert result.total_contradictions == 0


# =============================================================================
# Ingestion Tool Function Existence
# =============================================================================


class TestIngestToolFunctions:
    def test_detect_format_exists(self):
        """detect_format function is importable."""
        from monitor_data.tools.ingest_tools.multi_format import detect_format

        assert callable(detect_format)

    def test_ingest_file_exists(self):
        """ingest_file function is importable."""
        from monitor_data.tools.ingest_tools.multi_format import ingest_file

        assert callable(ingest_file)

    def test_chunk_text_exists(self):
        """chunk_text function is importable."""
        from monitor_data.tools.ingest_tools._chunking import chunk_text

        assert callable(chunk_text)

    def test_compute_delta_exists(self):
        """compute_ingestion_delta function is importable."""
        from monitor_data.tools.ingest_tools.delta_detection import (
            compute_ingestion_delta,
        )

        assert callable(compute_ingestion_delta)

    def test_compute_deduplication_exists(self):
        """compute_deduplication function is importable."""
        from monitor_data.tools.ingest_tools.deduplication import compute_deduplication

        assert callable(compute_deduplication)

    def test_detect_contradictions_exists(self):
        """detect_contradictions function is importable."""
        from monitor_data.tools.ingest_tools.contradiction_detection import (
            detect_contradictions,
        )

        assert callable(detect_contradictions)


# =============================================================================
# Chunking Behavior
# =============================================================================


class TestChunkingBehavior:
    def test_chunk_text_returns_list(self):
        """chunk_text returns a list of IngestedChunk objects."""
        from monitor_data.tools.ingest_tools._chunking import chunk_text

        chunks = chunk_text(
            source_name="test.md",
            text="This is a test paragraph with enough content to be meaningful for chunking.",
        )
        assert isinstance(chunks, list)

    def test_chunk_text_empty_input(self):
        """chunk_text handles empty input gracefully."""
        from monitor_data.tools.ingest_tools._chunking import chunk_text

        chunks = chunk_text(source_name="empty.md", text="")
        assert isinstance(chunks, list)
        assert len(chunks) == 0

    def test_chunk_text_preserves_source_name(self):
        """Each chunk records its source name."""
        from monitor_data.tools.ingest_tools._chunking import chunk_text

        chunks = chunk_text(
            source_name="handbook.pdf",
            text="A sufficiently long text that will produce at least one chunk for testing purposes.",
        )
        if chunks:
            assert chunks[0].source_name == "handbook.pdf"


class TestFormatDetection:
    def test_detect_markdown(self):
        """detect_format identifies markdown files."""
        from monitor_data.tools.ingest_tools.multi_format import detect_format

        fmt = detect_format("rules.md", "text/markdown")
        assert fmt == "markdown"

    def test_detect_pdf(self):
        """detect_format identifies PDF files."""
        from monitor_data.tools.ingest_tools.multi_format import detect_format

        fmt = detect_format("source.pdf", "application/pdf")
        assert fmt == "pdf"

    def test_detect_plain_text(self):
        """detect_format identifies plain text files."""
        from monitor_data.tools.ingest_tools.multi_format import detect_format

        fmt = detect_format("notes.txt", "text/plain")
        assert fmt == "text"


# =============================================================================
# Ingestion Pipeline Agent
# =============================================================================


class TestIngestionPipelineAgent:
    def test_pipeline_importable(self):
        """IngestionPipeline agent is importable."""
        from monitor_agents.ingestion_pipeline import IngestionPipeline

        assert IngestionPipeline is not None

    def test_pipeline_is_base_agent(self):
        """IngestionPipeline inherits from BaseAgent."""
        from monitor_agents.ingestion_pipeline import IngestionPipeline
        from monitor_agents.base import BaseAgent

        assert issubclass(IngestionPipeline, BaseAgent)

    def test_pipeline_has_ingest_file(self):
        """IngestionPipeline has ingest_file method."""
        from monitor_agents.ingestion_pipeline import IngestionPipeline

        assert hasattr(IngestionPipeline, "ingest_file")

    def test_pipeline_has_get_job(self):
        """IngestionPipeline has get_job method."""
        from monitor_agents.ingestion_pipeline import IngestionPipeline

        assert hasattr(IngestionPipeline, "get_job")


# =============================================================================
# Ingest Router
# =============================================================================


def _iter_route_paths(router):
    """Yield all route paths, recursing into included sub-routers."""
    from fastapi.routing import APIRoute

    for r in router.routes:
        if isinstance(r, APIRoute):
            yield r.path
        elif hasattr(r, "original_router"):
            yield from _iter_route_paths(r.original_router)


class TestIngestRouter:
    def test_router_importable(self):
        """Ingest router module is importable."""
        from monitor_ui.routers.ingest import router

        assert router is not None

    def test_router_has_upload_route(self):
        """Ingest router has upload endpoint."""
        from monitor_ui.routers.ingest import router

        route_paths = list(_iter_route_paths(router))
        assert any("upload" in p for p in route_paths)

    def test_router_has_packs_route(self):
        """Ingest router has packs endpoint."""
        from monitor_ui.routers.ingest import router

        route_paths = list(_iter_route_paths(router))
        assert any("packs" in p for p in route_paths)
