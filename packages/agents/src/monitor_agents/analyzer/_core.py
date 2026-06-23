"""
Analyzer Agent — extracts structured knowledge from ingested source text.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts

The Analyzer sits between the Indexer and the CanonKeeper in the ingestion
pipeline:

    Indexer → text chunks in Qdrant
    Analyzer → KnowledgePack (MongoDB, status=ready)
                ProposedChanges (ready for CanonKeeper review)
    CanonKeeper → evaluates proposals → Neo4j nodes

Pipeline for a single source:
  1. Receive job_id + source metadata
  2. Run thematic Qdrant queries to retrieve representative chunks
  3. For each extraction category, call a DSPy reasoning module
  4. Parse structured output → typed lists (axioms, entities, lore, rules)
  5. Optionally detect & extract game system definition
  6. Write ProposedChanges for each extracted item (if universe_id provided)
  7. Create KnowledgePack (status=ready) with all extracted content
  8. Update IngestionJob progress throughout

Extraction categories:
  AXIOM           — Ontological world truths: "Magic exists", "Gods are real"
  ENTITY_ARCHETYPE — Type/template: "Wizard", "Dragon", "The Thieves' Guild"
  LORE_FACT       — Specific canon fact: "The Sundering happened 1000 years ago"
  GAME_RULE       — Mechanical procedure: "Spell slots", "AC = 10 + DEX mod"

Authority:
  - Qdrant: read-only (search for chunks)
  - MongoDB: read/write (IngestionJob progress, KnowledgePack, ProposedChanges)
  - Neo4j: NO access — all writes go through CanonKeeper via ProposedChanges
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, cast
from uuid import UUID

from qdrant_client.http.models import SearchRequest
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchText, MatchValue

from monitor_agents.analyzer._constants import (
    BATCH_SIZE as _BATCH_SIZE,
    CATEGORIES_AXIOMS as _CATEGORIES_AXIOMS,
    CATEGORIES_CHARACTER_SHEET as _CATEGORIES_CHARACTER_SHEET,
    CATEGORIES_CHARACTER_PROFILES as _CATEGORIES_CHARACTER_PROFILES,
    CATEGORIES_ENTITIES as _CATEGORIES_ENTITIES,
    CATEGORIES_GAME_DETECTION as _CATEGORIES_GAME_DETECTION,
    CATEGORIES_GENERATION_TEMPLATES as _CATEGORIES_GENERATION_TEMPLATES,
    CATEGORIES_LORE as _CATEGORIES_LORE,
    CATEGORIES_NPC as _CATEGORIES_NPC,
    CATEGORIES_RULES as _CATEGORIES_RULES,
    CATEGORIES_TABLES as _CATEGORIES_TABLES,
    CATEGORIES_TONE as _CATEGORIES_TONE,
    CLASSIFIER_BATCH_SIZE as _CLASSIFIER_BATCH_SIZE,
    DETECTION_SAMPLE_SIZE as _DETECTION_SAMPLE_SIZE,
    EXTRACTION_CONCURRENCY as _EXTRACTION_CONCURRENCY,
    FALLBACK_QUERIES_AXIOMS as _FALLBACK_QUERIES_AXIOMS,
    FALLBACK_QUERIES_CHARACTER_PROFILES as _FALLBACK_QUERIES_CHARACTER_PROFILES,
    FALLBACK_QUERIES_ENTITIES as _FALLBACK_QUERIES_ENTITIES,
    FALLBACK_QUERIES_GAME as _FALLBACK_QUERIES_GAME,
    FALLBACK_QUERIES_GENERATION_TEMPLATES as _FALLBACK_QUERIES_GENERATION_TEMPLATES,
    FALLBACK_QUERIES_LORE as _FALLBACK_QUERIES_LORE,
    FALLBACK_QUERIES_NPC as _FALLBACK_QUERIES_NPC,
    FALLBACK_QUERIES_TABLES as _FALLBACK_QUERIES_TABLES,
    FALLBACK_QUERIES_TONE as _FALLBACK_QUERIES_TONE,
    MAX_CATEGORY_CHUNKS as _MAX_CATEGORY_CHUNKS,
    MAX_REFERENCE_SECTIONS as _MAX_REFERENCE_SECTIONS,
    MAX_SECTION_WORDS as _MAX_SECTION_WORDS,
    MAX_SECTIONS_PER_LAYER as _MAX_SECTIONS_PER_LAYER,
    SYSTEM_SCHEMA_SECTION_LIMIT as _SYSTEM_SCHEMA_SECTION_LIMIT_FROM_CONSTANTS,
)
from monitor_agents.analyzer._enrichment import enrich_entities_from_evidence
from monitor_agents.analyzer._game_system_persistence import save_game_system
from monitor_agents.analyzer._mindscape_projection import project_mindscape_to_qdrant
from monitor_agents.analyzer._models import AnalysisRunResult, LLMExecutionSummary
from monitor_agents.base import BaseAgent
from monitor_agents.llm_errors import LLMErrorClass
from monitor_agents.llm_execution import (
    LLMExecutionContext,
    LLMAttemptRecord,
    LLMAttemptStatus,
    LLMTaskRunner,
)
from monitor_agents.prompts.analyzer import (
    AgendaExtractionModule,
    BatchedExtractionModule,
    CharacterProfileExtractionModule,
    CharacterSheetExtractionModule,
    CreationLogicSynthesizerModule,
    CreationProcedureExtractionModule,
    GameRuleExtractionModule,
    GameSystemDetectionModule,
    GenerationTemplateExtractionModule,
    NPCExtractionModule,
    PlotThreadExtractionModule,
    RandomTableExtractionModule,
    RelationshipInferenceModule,
    SectionClassifierModule,
    SectionSummaryModule,
    SourceMindscapeSynthesisModule,
    SourceProfileSynthesisModule,
    ToneExtractionModule,
    TopologyExtractionModule,
)
from monitor_data.db.embeddings import embed_text
from monitor_data.db.qdrant import get_qdrant_client
from monitor_data.schemas.agendas import ExtractedAgenda
from monitor_data.schemas.ingestion_jobs import IngestionJobUpdate, IngestionStage
from monitor_data.schemas.knowledge_packs import (
    ApplyKnowledgePackRequest,
    EmbeddedGameSystem,
    EmbeddedSourceProfile,
    ExtractedAxiom,
    ExtractedCharacterProfile,
    ExtractedEntityArchetype,
    ExtractedGenerationTemplate,
    ExtractedLoreFact,
    ExtractedPlotThread,
    ExtractedRandomTable,
    ExtractedRelationship,
    ExtractedToneProfile,
    ExtractedTopology,
    KnowledgePackCreate,
    KnowledgePackStatus,
    KnowledgePackType,
    KnowledgePackUpdate,
    SectionSummaryArtifact,
    SourceMindscapeArtifact,
)
from monitor_agents.utils.analyzer_support import (
    REFERENCE_SECTION_KEYWORDS as _REFERENCE_SECTION_KEYWORDS,
    REFERENCE_SECTION_RE as _REFERENCE_SECTION_RE,
    SectionDigest as _SectionDigest,
    append_section_chunk,
    build_alias_map,
    build_chunk_summary_artifacts,
    build_graph_snapshot,
    build_section_digests,
    build_section_summary_inputs,
    build_source_profile_seed,
    dedupe_named_items,
    dedupe_relationships,
    derive_hierarchy_relationships,
    format_mindscape_context,
    format_section_context,
    format_source_profile_context,
    heuristic_extract_character_sheet_sections,
    materialize_container_entities,
    materialize_social_entities_and_relationships,
    merge_entity_archetypes,
    merge_source_profiles,
    normalize_relationship_refs,
    parse_section_classifications,
    parse_source_profile,
    persist_mindscape_artifacts,
    prioritize_schema_sections,
    rank_sections_with_profile,
    summarize_source_profile,
    system_section_score,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_apply_knowledge_pack,
    mongodb_create_knowledge_pack,
    mongodb_update_ingestion_job,
    mongodb_update_knowledge_pack,
)
from monitor_data.schemas.game_systems import CreationLogicStep
from monitor_data.schemas.base import IngestionStatus

# Alias for backwards compat — some methods reference _SYSTEM_SCHEMA_SECTION_LIMIT
_SYSTEM_SCHEMA_SECTION_LIMIT = _SYSTEM_SCHEMA_SECTION_LIMIT_FROM_CONSTANTS

__all__ = ["Analyzer", "AnalysisRunResult"]

logger = logging.getLogger(__name__)


class _SectionBundle:
    """Typed container for the section retrieval phase of ``analyze_source``."""

    __slots__ = (
        "content_sections",
        "game_chunks",
        "rule_sections",
        "charsheet_sections",
        "reference_sections",
        "npc_sections",
        "table_sections",
        "tone_sections",
        "character_profile_sections",
        "generation_template_sections",
        "plot_thread_sections",
    )

    def __init__(
        self,
        *,
        content_sections: List[_SectionDigest],
        game_chunks: List[str],
        rule_sections: List[_SectionDigest],
        charsheet_sections: List[_SectionDigest],
        reference_sections: List[_SectionDigest],
        npc_sections: List[_SectionDigest],
        table_sections: List[_SectionDigest] = None,
        tone_sections: List[_SectionDigest] = None,
        character_profile_sections: List[_SectionDigest] = None,
        generation_template_sections: List[_SectionDigest] = None,
        plot_thread_sections: List[_SectionDigest] = None,
    ) -> None:
        self.content_sections = content_sections
        self.game_chunks = game_chunks
        self.rule_sections = rule_sections
        self.charsheet_sections = charsheet_sections
        self.reference_sections = reference_sections
        self.npc_sections = npc_sections
        self.table_sections = table_sections or []
        self.tone_sections = tone_sections or []
        self.character_profile_sections = character_profile_sections or []
        self.generation_template_sections = generation_template_sections or []
        self.plot_thread_sections = plot_thread_sections or []


class Analyzer(BaseAgent):
    """
    Extracts structured knowledge from a set of ingested text chunks.

    STATELESS — uses job_id for progress tracking, all results go to MongoDB.
    """

    def __init__(self, agent_id: str = "analyzer-1") -> None:
        super().__init__(agent_type="Analyzer", agent_id=agent_id)
        self._llm_runner = LLMTaskRunner(
            agent_name=self.agent_type, timeout_s=self._LLM_CALL_TIMEOUT
        )
        self._active_job_id: Optional[UUID] = None
        self._active_execution_summary: Optional[LLMExecutionSummary] = None
        self._game_detector = GameSystemDetectionModule()
        self._rule_extractor = GameRuleExtractionModule()
        self._charsheet_extractor = CharacterSheetExtractionModule()
        self._creation_proc_extractor = CreationProcedureExtractionModule()
        self._npc_extractor = NPCExtractionModule()
        self._table_extractor = RandomTableExtractionModule()
        self._agenda_extractor = AgendaExtractionModule()
        self._topology_extractor = TopologyExtractionModule()
        self._rel_inferer = RelationshipInferenceModule()
        self._section_classifier = SectionClassifierModule()
        self._source_profiler = SourceProfileSynthesisModule()
        self._batched_extractor = BatchedExtractionModule()
        self._tone_extractor = ToneExtractionModule()
        self._character_profile_extractor = CharacterProfileExtractionModule()
        self._generation_template_extractor = GenerationTemplateExtractionModule()
        self._creation_logic_synthesizer = CreationLogicSynthesizerModule()
        self._plot_thread_extractor = PlotThreadExtractionModule()

    async def run(self) -> None:
        pass  # driven externally by IngestionPipeline

    # ------------------------------------------------------------------
    # DSPy call wrapper — enforces a hard Python-level timeout so a single
    # blocked LLM request cannot stall the entire pipeline indefinitely.
    # litellm's request_timeout kwarg is unreliable for some providers
    # (GitHub Models / Azure backend), so we enforce the limit here via
    # asyncio.wait_for + asyncio.to_thread.
    # ------------------------------------------------------------------

    _LLM_CALL_TIMEOUT: float = float(os.environ.get("MONITOR_LLM_TIMEOUT", "120"))

    async def _call_module(
        self,
        module: Callable[..., Any],
        timeout: Optional[float] = None,
        *,
        stage: Optional[str] = None,
        batch_id: Optional[str] = None,
        job_id: Optional[UUID] = None,
        source_id: Optional[UUID] = None,
        summary: Optional[LLMExecutionSummary] = None,
        **kwargs: Any,
    ) -> Any:
        """Run a DSPy module through the shared retry/backoff execution layer."""
        active_summary = summary if summary is not None else self._active_execution_summary
        active_job_id = job_id if job_id is not None else self._active_job_id

        if active_summary is not None and active_summary.blocked_provider:
            raise RuntimeError(
                "LLM provider blocked for this job after a non-retryable failure; skipping remaining DSPy work"
            )

        effective_timeout = timeout if timeout is not None else self._LLM_CALL_TIMEOUT
        module_role = getattr(module, "_role", None) or self._default_model_role()
        context = LLMExecutionContext(
            job_id=active_job_id,
            source_id=source_id,
            stage=stage or type(module).__name__.replace("Module", "").lower(),
            batch_id=batch_id,
            node_name="analyzer",
            role=module_role,
        )
        async def _run() -> Any:
            return await self._llm_runner.run_blocking(
                module,
                kwargs=kwargs,
                context=context,
                timeout=effective_timeout,
                on_attempt=lambda attempt: self._record_llm_attempt(
                    active_job_id, active_summary, attempt
                ),
            )

        try:
            result = await _run()
        except Exception as exc:  # noqa: BLE001
            # DSPy AdapterParseError (the LM returned fields the JSON adapter
            # can't parse) is frequently transient with non-deterministic
            # providers like MiniMax — a single re-run usually returns valid
            # output. Without this, whole extraction batches were silently lost.
            msg = f"{type(exc).__name__}: {exc}".lower()
            if "adapterparseerror" in msg or "failed to parse" in msg:
                logger.warning(
                    "Module %s parse failure; retrying once: %s",
                    context.stage,
                    exc,
                )
                result = await _run()
            else:
                raise
        return result.value

    def _record_llm_attempt(
        self,
        job_id: Optional[UUID],
        summary: Optional[LLMExecutionSummary],
        attempt: LLMAttemptRecord,
    ) -> None:
        """Fold attempt telemetry into the active ingestion job state."""
        if summary is None:
            return

        if attempt.attempt_no == 1:
            summary.total_batches += 1
        else:
            summary.retried_batches += 1

        if attempt.provider_id:
            summary.current_provider = attempt.provider_id
        if attempt.model:
            summary.current_model = attempt.model
        if attempt.error_message:
            summary.last_error = attempt.error_message

        if attempt.status == LLMAttemptStatus.SUCCEEDED:
            summary.succeeded_batches += 1
        elif attempt.status in {
            LLMAttemptStatus.FAILED,
            LLMAttemptStatus.FAILED_NON_RETRYABLE,
            LLMAttemptStatus.CANCELLED,
        }:
            summary.failed_batches += 1
            # AUTH/QUOTA/MISCONFIGURATION are provider-level: every remaining
            # batch will fail the same way, so block the provider. A VALIDATION
            # error, however, is per-batch *content* (the model returned output
            # that didn't match the schema for THIS batch); other batches can and
            # do still succeed. Treating it as a provider block poisoned the whole
            # job (BLOCKED_PROVIDER) and skipped canonization of all good data.
            if attempt.error_class in {
                LLMErrorClass.AUTH.value,
                LLMErrorClass.QUOTA.value,
                LLMErrorClass.MISCONFIGURATION.value,
            }:
                summary.blocked_provider = True

        if job_id is None:
            return

        next_retry_at = None
        status = None
        warnings = None
        errors = None
        activity_log = None

        if attempt.status == LLMAttemptStatus.BACKING_OFF:
            status = IngestionStatus.BACKING_OFF
            if attempt.backoff_ms:
                next_retry_at = datetime.now(timezone.utc) + timedelta(
                    milliseconds=attempt.backoff_ms
                )
            activity_log = [self._format_attempt_message(attempt)]
            warnings = [attempt.error_message] if attempt.error_message else None
        elif attempt.status == LLMAttemptStatus.FAILED_NON_RETRYABLE:
            status = summary.final_status()
            activity_log = [self._format_attempt_message(attempt)]
            errors = [attempt.error_message] if attempt.error_message else None
        elif attempt.status == LLMAttemptStatus.FAILED:
            activity_log = [self._format_attempt_message(attempt)]
            warnings = [attempt.error_message] if attempt.error_message else None
        elif attempt.status == LLMAttemptStatus.CANCELLED:
            status = IngestionStatus.CANCELLED
            activity_log = [self._format_attempt_message(attempt)]
            warnings = [attempt.error_message] if attempt.error_message else None
        elif attempt.status == LLMAttemptStatus.SUCCEEDED:
            next_retry_at = None

        self._update_job(
            job_id,
            status=status,
            next_retry_at=next_retry_at,
            warnings=warnings,
            errors=errors,
            activity_log=activity_log,
            **summary.as_job_update(),
        )

    @staticmethod
    def _format_attempt_message(attempt: LLMAttemptRecord) -> str:
        """Convert an attempt record into a concise operator-visible timeline entry."""
        batch_label = f" {attempt.batch_id}" if attempt.batch_id else ""
        provider_label = "/".join(
            part
            for part in [
                attempt.provider_id or "unknown-provider",
                attempt.model or "unknown-model",
            ]
            if part
        )
        error_label = attempt.error_class or "unknown"

        if attempt.status == LLMAttemptStatus.BACKING_OFF:
            return (
                f"Retrying {attempt.stage}{batch_label} after {error_label} "
                f"(attempt {attempt.attempt_no}/{attempt.max_attempts}, provider={provider_label})"
            )
        if attempt.status == LLMAttemptStatus.FAILED_NON_RETRYABLE:
            return (
                f"Provider blocked during {attempt.stage}{batch_label}: {error_label} "
                f"({provider_label})"
            )
        if attempt.status == LLMAttemptStatus.CANCELLED:
            return f"LLM work cancelled during {attempt.stage}{batch_label} ({provider_label})"
        return (
            f"LLM batch failed during {attempt.stage}{batch_label}: {error_label} "
            f"({provider_label})"
        )

    async def analyze(
        self,
        job_id: UUID,
        source_name: str,
        source_document_ids: List[UUID],
        pack_name: str,
        pack_type: KnowledgePackType = KnowledgePackType.SETTING_SUPPLEMENT,
        universe_id: Optional[UUID] = None,
        multiverse_id: Optional[UUID] = None,
        analysis_layers: Optional[List[str]] = None,
        auto_apply: bool = False,
    ) -> AnalysisRunResult:
        """Backward-compatible alias for the primary analysis entry point."""
        return await self.analyze_source(
            job_id=job_id,
            source_name=source_name,
            source_document_ids=source_document_ids,
            pack_name=pack_name,
            pack_type=pack_type,
            universe_id=universe_id,
            multiverse_id=multiverse_id,
            analysis_layers=analysis_layers,
            auto_apply=auto_apply,
        )

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    async def analyze_source(
        self,
        job_id: UUID,
        source_name: str,
        source_document_ids: List[UUID],
        pack_name: str,
        pack_type: KnowledgePackType = KnowledgePackType.SETTING_SUPPLEMENT,
        universe_id: Optional[UUID] = None,
        multiverse_id: Optional[UUID] = None,
        analysis_layers: Optional[List[str]] = None,
        auto_apply: bool = False,
    ) -> AnalysisRunResult:
        """
        Full analysis pass over a source document's Qdrant chunks.

        Creates a KnowledgePack with all extracted axioms, entity archetypes,
        lore facts, and game rules.  Optionally auto-applies the pack to a
        multiverse (creating ProposedChanges for CanonKeeper to evaluate).

        Args:
            job_id:               IngestionJob to track progress.
            source_name:          Logical name used during indexing (e.g. "D&D 5e PHB").
            source_document_ids:  MongoDB document IDs of the source files.
            pack_name:            Display name for the resulting KnowledgePack.
            pack_type:            Type of source (rulebook, setting_supplement, etc.).
            universe_id:          Neo4j universe scope for proposals (optional).
            multiverse_id:        Neo4j multiverse for proposals (optional).
            auto_apply:           If True and multiverse_id set, auto-apply pack.

        Returns:
            pack_id: UUID of the created KnowledgePack.
        """
        selected_layers = {
            layer.strip().lower()
            for layer in (
                analysis_layers
                or [
                    "axioms",
                    "entities",
                    "lore",
                    "game_system",
                    "rules",
                    "tone",
                    "character_profiles",
                    "generation_templates",
                    "plot_threads",
                ]
            )
            if layer
        }
        include_axioms = "axioms" in selected_layers
        include_entities = "entities" in selected_layers
        include_lore = "lore" in selected_layers
        include_tone = "tone" in selected_layers
        include_character_profiles = "character_profiles" in selected_layers
        include_generation_templates = "generation_templates" in selected_layers
        include_plot_threads = "plot_threads" in selected_layers
        include_content = (
            include_axioms
            or include_entities
            or include_lore
            or include_tone
            or include_character_profiles
            or include_generation_templates
            or include_plot_threads
        )
        include_game_system = "game_system" in selected_layers or "rules" in selected_layers
        include_rules = "rules" in selected_layers

        execution_summary = LLMExecutionSummary()
        self._active_job_id = job_id
        self._active_execution_summary = execution_summary

        # --- Stage: ANALYZE starts ---
        self._update_job(
            job_id,
            status=IngestionStatus.RUNNING,
            current_stage=IngestionStage.ANALYZE,
            progress=0.0,
            activity_log=[f"Analyzer started for layers: {', '.join(sorted(selected_layers))}"],
        )

        # Create a DRAFT pack immediately so callers can track it
        pack = mongodb_create_knowledge_pack(
            KnowledgePackCreate(
                name=pack_name,
                pack_type=pack_type,
                system_name=None,  # set later if game system detected
                source_document_ids=source_document_ids,
                ingestion_job_id=job_id,
            )
        )
        # `KnowledgePackResponse` exposes the primary key as the `id` attribute
        # (with `pack_id` as a deserialization alias). Reading `.pack_id` here
        # raised AttributeError and crashed the analyzer with no job-side error
        # other than the bare exception name — found during T-082 live diagnosis.
        pack_id = pack.id

        # Link job → pack so the user can navigate from a completed job
        self._update_job(job_id, pack_id=pack_id)

        # Phase 1: Retrieve sections
        sections = await self._retrieve_all_sections(
            job_id,
            source_name,
            include_content=include_content,
            include_game_system=include_game_system,
            include_rules=include_rules,
        )

        # Phase 2: Classify & filter sections, synthesize profile + mindscape
        (
            filtered_sections,
            source_profile,
            source_profile_context,
        ) = await self._classify_and_build_profile(
            job_id,
            pack_id,
            source_name,
            sections,
            pack_type,
            include_axioms,
            include_entities,
            include_lore,
        )

        # Phase 3: Detect game system
        is_game_system, detected_system_name = await self._detect_game_system_phase(
            job_id,
            pack_id,
            source_name,
            sections.game_chunks,
            include_game_system,
            source_profile,
            source_profile_context,
        )

        # Phase 4: Batched extraction + entity enrichment + relationship inference
        axioms, entities, lore_facts, relationship_facts = await self._extract_and_enrich_entities(
            job_id,
            source_name,
            filtered_sections,
            source_profile_context,
            source_profile,
            include_axioms,
            include_entities,
            include_lore,
        )

        (
            game_rules,
            charsheet_data,
            creation_procedure_data,
            npc_data,
            random_tables,
            agendas,
            topologies,
            tone_profiles,
            character_profiles,
            generation_templates,
            plot_threads,
        ) = await self._extract_game_subsystems(
            job_id,
            source_name,
            sections,
            is_game_system,
            detected_system_name,
            include_rules,
            source_profile_context,
            known_entities=entities,
            include_tone=include_tone,
            include_character_profiles=include_character_profiles,
            include_generation_templates=include_generation_templates,
            include_plot_threads=include_plot_threads,
        )

        # Phase 6: Assemble game system + save pack + finalize
        return await self._assemble_and_finalize(
            job_id,
            pack_id,
            source_name,
            source_document_ids,
            axioms,
            entities,
            lore_facts,
            relationship_facts,
            game_rules,
            charsheet_data,
            creation_procedure_data,
            npc_data,
            random_tables,
            agendas,
            topologies,
            tone_profiles,
            character_profiles,
            generation_templates,
            plot_threads,
            is_game_system,
            detected_system_name,
            source_profile,
            pack_type,
            auto_apply,
            multiverse_id,
            universe_id,
            execution_summary,
        )

    # ------------------------------------------------------------------
    # Phase helpers (extracted from analyze_source)
    # ------------------------------------------------------------------

    async def _retrieve_all_sections(
        self,
        job_id: UUID,
        source_name: str,
        *,
        include_content: bool,
        include_game_system: bool,
        include_rules: bool,
    ) -> "_SectionBundle":
        """Phase 1: Retrieve source sections by semantic category (LLM-free)."""
        content_sections: List[_SectionDigest] = []
        game_chunks: List[str] = []
        rule_sections: List[_SectionDigest] = []
        charsheet_sections: List[_SectionDigest] = []
        reference_sections: List[_SectionDigest] = []
        npc_sections: List[_SectionDigest] = []
        table_sections: List[_SectionDigest] = []
        tone_sections: List[_SectionDigest] = []
        character_profile_sections: List[_SectionDigest] = []
        generation_template_sections: List[_SectionDigest] = []
        plot_thread_sections: List[_SectionDigest] = []

        if include_content:
            seen_paths: set[str] = set()
            for categories, fallback in [
                (_CATEGORIES_AXIOMS, _FALLBACK_QUERIES_AXIOMS),
                (_CATEGORIES_ENTITIES, _FALLBACK_QUERIES_ENTITIES),
                (_CATEGORIES_LORE, _FALLBACK_QUERIES_LORE),
                (_CATEGORIES_TONE, _FALLBACK_QUERIES_TONE),
                (_CATEGORIES_CHARACTER_PROFILES, _FALLBACK_QUERIES_CHARACTER_PROFILES),
                (_CATEGORIES_GENERATION_TEMPLATES, _FALLBACK_QUERIES_GENERATION_TEMPLATES),
            ]:
                batch = await self._retrieve_sections_by_category(
                    source_name,
                    categories,
                    "snippets",
                    fallback_queries=fallback,
                )
                for section in batch:
                    if section.section_path not in seen_paths:
                        seen_paths.add(section.section_path)
                        content_sections.append(section)

            # Assign specialized sections for targeted extraction passes
            tone_sections = [
                s
                for s in content_sections
                if s.semantic_category in _CATEGORIES_TONE or "tone" in s.section_path.lower()
            ]
            character_profile_sections = [
                s
                for s in content_sections
                if s.semantic_category in _CATEGORIES_CHARACTER_PROFILES
                or any(kw in s.section_path.lower() for kw in ["character", "profile", "npc"])
            ]
            generation_template_sections = [
                s
                for s in content_sections
                if s.semantic_category in _CATEGORIES_GENERATION_TEMPLATES
                or "generation" in s.section_path.lower()
            ]
            # Plot threads: narrative sections with story/promise/mystery keywords
            _plot_keywords = {
                "promise",
                "threat",
                "mystery",
                "plot",
                "quest",
                "foreshadow",
                "ominous",
                "danger",
                "looming",
                "prophecy",
                "cliffhanger",
                "unresolved",
                "consequence",
                "vendetta",
                "secret",
                "hidden",
            }
            plot_thread_sections = [
                s
                for s in content_sections
                if any(
                    kw in s.text.lower() or kw in s.section_path.lower() for kw in _plot_keywords
                )
            ]
            # If no narrative sections found, fall back to all content
            if not plot_thread_sections:
                plot_thread_sections = content_sections[:10]

            content_sections.sort(key=lambda s: (s.min_page, s.min_chunk_index))

        if include_game_system:
            _game_sections = await self._retrieve_sections_by_category(
                source_name,
                _CATEGORIES_GAME_DETECTION,
                "snippets",
                fallback_queries=_FALLBACK_QUERIES_GAME,
            )
            game_chunks = [s.text for s in _game_sections]
        if include_rules:
            rule_sections = await self._retrieve_sections_by_category(
                source_name,
                _CATEGORIES_RULES,
                "snippets",
                fallback_queries=_FALLBACK_QUERIES_GAME,
            )
        if include_game_system:
            charsheet_sections = await self._retrieve_sections_by_category(
                source_name,
                _CATEGORIES_CHARACTER_SHEET,
                "snippets",
                fallback_queries=_FALLBACK_QUERIES_GAME,
            )
            reference_sections = await self._retrieve_reference_sections(source_name, "snippets")
        if include_game_system or include_rules:
            npc_sections = await self._retrieve_sections_by_category(
                source_name,
                _CATEGORIES_NPC,
                "snippets",
                fallback_queries=_FALLBACK_QUERIES_NPC,
            )
            table_sections = await self._retrieve_sections_by_category(
                source_name,
                _CATEGORIES_TABLES,
                "snippets",
                fallback_queries=_FALLBACK_QUERIES_TABLES,
            )

        self._update_job(
            job_id,
            progress=0.1,
            activity_log=[
                f"Retrieved {len(content_sections)} content sections, "
                f"{len(rule_sections)} rule sections, "
                f"{len(charsheet_sections)} charsheet sections, "
                f"{len(reference_sections)} reference sections, "
                f"{len(table_sections)} table sections"
            ],
        )

        return _SectionBundle(
            content_sections=content_sections,
            game_chunks=game_chunks,
            rule_sections=rule_sections,
            charsheet_sections=charsheet_sections,
            reference_sections=reference_sections,
            npc_sections=npc_sections,
            table_sections=table_sections,
            tone_sections=tone_sections,
            character_profile_sections=character_profile_sections,
            generation_template_sections=generation_template_sections,
            plot_thread_sections=plot_thread_sections,
        )

    async def _classify_and_build_profile(
        self,
        job_id: UUID,
        pack_id: UUID,
        source_name: str,
        sections: "_SectionBundle",
        pack_type: KnowledgePackType,
        include_axioms: bool,
        include_entities: bool,
        include_lore: bool,
    ) -> Tuple[List[_SectionDigest], Optional[EmbeddedSourceProfile], str]:
        """Phase 2: Classify sections, synthesize source profile + mindscape context."""
        include_content = include_axioms or include_entities or include_lore
        filtered_sections: List[_SectionDigest] = []
        source_profile: Optional[EmbeddedSourceProfile] = None
        source_profile_context = ""

        if include_content and sections.content_sections:
            filtered_sections = await self._classify_and_filter_sections(
                sections.content_sections, source_name
            )
            self._update_job(
                job_id,
                progress=0.2,
                activity_log=[
                    f"Section classifier kept {len(filtered_sections)} of "
                    f"{len(sections.content_sections)} sections (filtered metadata/credits)"
                ],
            )

        # Synthesize and persist source profile
        profile_sections = (
            filtered_sections
            or sections.content_sections
            or sections.rule_sections
            or sections.charsheet_sections
        )
        if profile_sections or sections.reference_sections:
            source_profile = await self._synthesize_source_profile(
                source_name=source_name,
                sections=profile_sections,
                reference_sections=sections.reference_sections,
                source_kind=pack_type.value,
            )
            if source_profile is not None:
                mongodb_update_knowledge_pack(
                    pack_id,
                    KnowledgePackUpdate(
                        source_profile_data=source_profile,
                        system_name=source_profile.system_name,
                    ),
                )
                source_profile_context = format_source_profile_context(source_profile)
                mode_label = "generic fallback" if not source_profile_context else "profile-guided"
                self._update_job(
                    job_id,
                    progress=0.28,
                    activity_log=[f"{summarize_source_profile(source_profile)} ({mode_label})"],
                )
            else:
                self._update_job(
                    job_id,
                    progress=0.28,
                    activity_log=["Source profile unavailable; using generic extraction mode"],
                )

        # Mindscape synthesis
        mindscape_sections = filtered_sections or sections.content_sections
        if mindscape_sections:
            try:
                mindscape = await self.synthesize_mindscape(
                    sections=mindscape_sections,
                    source_name=source_name,
                    pack_id=pack_id,
                )
                mindscape_context = format_mindscape_context(mindscape)
                if mindscape_context:
                    source_profile_context = (
                        f"{source_profile_context}\n\n{mindscape_context}"
                        if source_profile_context
                        else mindscape_context
                    )
                self._update_job(
                    job_id,
                    progress=0.32,
                    activity_log=[
                        f"Mindscape synthesis complete: {len(mindscape.themes)} themes, "
                        f"{len(mindscape.taxonomy_hints)} taxonomy hints"
                    ],
                )
            except Exception as exc:
                logger.warning("Mindscape synthesis skipped for '%s': %s", source_name, exc)

        return filtered_sections, source_profile, source_profile_context

    async def _detect_game_system_phase(
        self,
        job_id: UUID,
        pack_id: UUID,
        source_name: str,
        game_chunks: List[str],
        include_game_system: bool,
        source_profile: Optional[EmbeddedSourceProfile],
        source_profile_context: str,
    ) -> Tuple[bool, Optional[str]]:
        """Phase 3: Detect game system from game_chunks."""
        is_game_system = False
        detected_system_name: Optional[str] = None

        if include_game_system:
            is_game_system, detected_system_name = await self._detect_game_system(
                game_chunks,
                source_name,
                source_profile_context=source_profile_context,
            )
            if (
                detected_system_name
                and source_profile is not None
                and not source_profile.system_name
            ):
                confidence_map = dict(source_profile.confidence_by_field)
                confidence_map.setdefault("system_name", 0.92)
                source_profile = source_profile.model_copy(
                    update={
                        "system_name": detected_system_name,
                        "confidence_by_field": confidence_map,
                    }
                )
                mongodb_update_knowledge_pack(
                    pack_id,
                    KnowledgePackUpdate(
                        source_profile_data=source_profile,
                        system_name=detected_system_name,
                    ),
                )
                source_profile_context = format_source_profile_context(source_profile)
        self._update_job(
            job_id,
            game_system_found=is_game_system,
            progress=0.35,
            activity_log=[
                f"Game system detection: {'detected ' + detected_system_name if is_game_system and detected_system_name else 'none'}"
            ],
        )

        return is_game_system, detected_system_name

    async def _extract_and_enrich_entities(
        self,
        job_id: UUID,
        source_name: str,
        filtered_sections: List[_SectionDigest],
        source_profile_context: str,
        source_profile: Optional[EmbeddedSourceProfile],
        include_axioms: bool,
        include_entities: bool,
        include_lore: bool,
    ) -> Tuple[
        List[ExtractedAxiom],
        List[ExtractedEntityArchetype],
        List[ExtractedLoreFact],
        List[ExtractedRelationship],
    ]:
        """Phase 4: Batched extraction, entity enrichment, container/social synthesis, relationship inference."""
        axioms: List[ExtractedAxiom] = []
        entities: List[ExtractedEntityArchetype] = []
        lore_facts: List[ExtractedLoreFact] = []
        include_content = include_axioms or include_entities or include_lore

        # Batched extraction
        if include_content and filtered_sections:
            axioms, entities, lore_facts = await self._batched_extract_all(
                filtered_sections,
                source_name,
                include_axioms,
                include_entities,
                include_lore,
                source_profile_context=source_profile_context,
                source_profile=source_profile,
            )
        self._update_job(
            job_id,
            axioms_extracted=len(axioms),
            entities_extracted=len(entities),
            world_template_found=bool(axioms),
            progress=0.55,
            activity_log=[
                f"Batched extraction complete: {len(axioms)} axioms, "
                f"{len(entities)} entities, {len(lore_facts)} lore facts"
            ],
        )

        # Entity evidence enrichment
        if include_entities and entities:
            entity_names = [e.name for e in entities if e.name]
            evidence = await self._retrieve_entity_evidence(source_name, entity_names)
            entities = self._enrich_entities_from_evidence(entities, evidence)
            self._update_job(
                job_id,
                progress=0.58,
                activity_log=[
                    f"Entity evidence enrichment: {len(evidence)} of {len(entity_names)} "
                    "entities gained cross-section evidence from Qdrant MatchText search"
                ],
            )

        entities, synthesized_count = self._materialize_container_entities(entities, source_name)
        if synthesized_count:
            self._update_job(
                job_id,
                progress=0.59,
                activity_log=[
                    f"Container synthesis complete: {synthesized_count} named container entities added"
                ],
            )

        entities, heuristic_relationships, social_synth_count = (
            self._materialize_social_entities_and_relationships(
                entities,
                source_name,
            )
        )
        if social_synth_count or heuristic_relationships:
            self._update_job(
                job_id,
                progress=0.62,
                activity_log=[
                    f"Institution synthesis complete: {social_synth_count} social entities and "
                    f"{len(heuristic_relationships)} relationship hints added"
                ],
            )

        # Hierarchy derivation + relationship inference
        hierarchy_relationships = (
            derive_hierarchy_relationships(entities) if include_entities else []
        )
        if hierarchy_relationships:
            self._update_job(
                job_id,
                progress=0.63,
                activity_log=[
                    f"Hierarchy derivation: {len(hierarchy_relationships)} structural edges "
                    "derived from parent_entity_name links"
                ],
            )

        llm_relationships = (
            await self._infer_relationships(
                entities,
                source_name,
                source_profile_context=source_profile_context,
            )
            if include_entities and entities
            else []
        )
        relationship_facts = self._dedupe_relationships(
            [*hierarchy_relationships, *heuristic_relationships, *llm_relationships]
        )
        _alias_map = build_alias_map(entities)
        relationship_facts = normalize_relationship_refs(relationship_facts, _alias_map)
        self._update_job(
            job_id,
            progress=0.65,
            activity_log=[
                f"Relationship inference complete: {len(relationship_facts)} relationship(s) inferred"
            ],
        )

        # Lore facts already extracted in batch step
        self._update_job(
            job_id,
            progress=0.7,
            activity_log=[f"Lore pass complete: {len(lore_facts)} lore facts extracted"],
        )

        return axioms, entities, lore_facts, relationship_facts

    async def _extract_game_subsystems(
        self,
        job_id: UUID,
        source_name: str,
        sections: "_SectionBundle",
        is_game_system: bool,
        detected_system_name: Optional[str],
        include_rules: bool,
        source_profile_context: str,
        known_entities: Optional[List[ExtractedEntityArchetype]] = None,
        include_tone: bool = True,
        include_character_profiles: bool = True,
        include_generation_templates: bool = True,
        include_plot_threads: bool = True,
    ) -> Tuple[
        List[Dict[str, Any]],
        Dict[str, Any],
        Dict[str, Any],
        Dict[str, Any],
        List[ExtractedRandomTable],
        List[ExtractedAgenda],
        List[ExtractedTopology],
        List[ExtractedToneProfile],
        List[ExtractedCharacterProfile],
        List[ExtractedGenerationTemplate],
        List[ExtractedPlotThread],
    ]:
        """Phase 5: Extract game rules, character sheet, creation procedure, NPC data, tables, agendas, topologies, tones, profiles, templates, and plot threads."""
        game_rules: List[Dict[str, Any]] = []
        charsheet_data: Dict[str, Any] = {}
        creation_procedure_data: Dict[str, Any] = {}
        npc_data: Dict[str, Any] = {}
        random_tables: List[ExtractedRandomTable] = []
        agendas: List[ExtractedAgenda] = []
        topologies: List[ExtractedTopology] = []
        tone_profiles: List[ExtractedToneProfile] = []
        character_profiles: List[ExtractedCharacterProfile] = []
        generation_templates: List[ExtractedGenerationTemplate] = []
        plot_threads: List[ExtractedPlotThread] = []
        combined_charsheet_sections: List[_SectionDigest] = []
        source_label = detected_system_name or source_name

        # Game rules
        if is_game_system and include_rules:
            fallback_rule_sections = sections.rule_sections or sections.charsheet_sections
            game_rules = await self._extract_game_rules(
                fallback_rule_sections,
                source_label,
                source_profile_context=source_profile_context,
            )
            rules_log = f"Rules pass complete: {len(game_rules)} rules extracted"
        elif include_rules:
            rules_log = "Rules pass skipped: no game system detected"
        else:
            rules_log = "Rules pass skipped: rules layer not selected"
        self._update_job(
            job_id,
            progress=0.8,
            activity_log=[rules_log],
        )

        # Random tables, agendas, and topology are useful for adventure/setting
        # sources even when no formal game system is detected.
        if include_rules:
            random_tables = await self._extract_random_tables(
                sections.table_sections,
                source_label,
            )
        self._update_job(
            job_id,
            progress=0.82,
            activity_log=[f"Random tables pass complete: {len(random_tables)} tables extracted"],
        )

        # Agendas & Clocks
        if include_rules:
            agendas = await self._extract_agendas(
                sections.content_sections,
                source_label,
            )
        self._update_job(
            job_id,
            progress=0.84,
            activity_log=[f"Agenda pass complete: {len(agendas)} agendas extracted"],
        )

        # Spatial Topology
        if include_rules:
            topologies = await self._extract_topologies(
                sections.content_sections,
                source_label,
            )
        self._update_job(
            job_id,
            progress=0.86,
            activity_log=[f"Topology pass complete: {len(topologies)} connections extracted"],
        )

        # Narrative Tone
        if include_tone:
            tone_profiles = await self._extract_tone_profiles(
                sections.tone_sections,
                source_label,
            )
        self._update_job(
            job_id,
            progress=0.87,
            activity_log=[f"Tone pass complete: {len(tone_profiles)} tone profiles extracted"],
        )

        # Character Profiles (Narrative/Psychology)
        if include_character_profiles:
            character_profiles = await self._extract_character_profiles(
                sections.character_profile_sections,
                source_label,
            )
        self._update_job(
            job_id,
            progress=0.88,
            activity_log=[
                f"Character profile pass complete: {len(character_profiles)} profiles extracted"
            ],
        )

        if not is_game_system:
            # Plot threads are valuable even without a game system
            if include_plot_threads:
                thread_sections = sections.plot_thread_sections or sections.content_sections
                plot_threads = await self._extract_plot_threads(
                    thread_sections,
                    source_label,
                )
            self._update_job(
                job_id,
                progress=0.895,
                activity_log=[f"Plot thread pass complete: {len(plot_threads)} threads extracted"],
            )
            return (
                game_rules,
                charsheet_data,
                creation_procedure_data,
                npc_data,
                random_tables,
                agendas,
                topologies,
                tone_profiles,
                character_profiles,
                generation_templates,
                plot_threads,
            )

        # Character sheet
        fallback_charsheet_sections = sections.charsheet_sections or sections.rule_sections
        seen_section_paths: set[str] = set()
        for section in [*fallback_charsheet_sections, *sections.reference_sections]:
            key = f"{section.section_path}|{section.min_page}|{section.min_chunk_index}"
            if key in seen_section_paths:
                continue
            seen_section_paths.add(key)
            combined_charsheet_sections.append(section)

        charsheet_data = await self._extract_character_sheet(
            combined_charsheet_sections,
            source_label,
            source_profile_context=source_profile_context,
        )
        attrs = len(charsheet_data.get("attributes", []))
        skills = len(charsheet_data.get("skills", []))
        res = len(charsheet_data.get("resources", []))
        powers = len(charsheet_data.get("powers", []))
        subsystems = len(charsheet_data.get("subsystems", []))
        self._update_job(
            job_id,
            activity_log=[
                f"Character sheet pass complete: {attrs} attributes, {skills} skills, "
                f"{res} resources, {powers} powers, {subsystems} subsystems"
            ],
        )

        # Creation procedure
        creation_procedure_data = await self._extract_creation_procedure(
            combined_charsheet_sections
            if charsheet_data
            else (sections.charsheet_sections or sections.rule_sections or []),
            source_label,
            source_profile_context=source_profile_context,
        )
        n_steps = len(creation_procedure_data.get("steps", []))
        n_bgs = len(creation_procedure_data.get("backgrounds", []))
        has_gen = bool(creation_procedure_data.get("ability_score_generation"))
        has_adv = bool(creation_procedure_data.get("advancement"))
        self._update_job(
            job_id,
            activity_log=[
                f"Creation procedure pass complete: {n_steps} steps, "
                f"{n_bgs} backgrounds, ability_gen={'yes' if has_gen else 'no'}, "
                f"advancement={'yes' if has_adv else 'no'}"
            ],
        )

        # Actionable Creation Logic Synthesis
        if include_rules and n_steps > 0:
            # Build context of known entities and tables for logic mapping
            entities_summary = (
                f"Archetypes: {', '.join([e.name for e in (known_entities or [])])}\n"
                f"Tables: {', '.join([t.name for t in random_tables])}\n"
                f"Attributes: {', '.join([a.get('name', '') for a in charsheet_data.get('attributes', [])])}"
            )

            creation_logic = await self._extract_creation_logic(
                creation_procedure_data.get("steps", []),
                entities_summary,
            )
            creation_procedure_data["logic"] = creation_logic
            self._update_job(
                job_id,
                progress=0.885,
                activity_log=[
                    f"Creation logic synthesis complete: {len(creation_logic)} actionable steps generated"
                ],
            )

        # NPC data
        fallback_npc_sections = sections.npc_sections or sections.rule_sections or []
        npc_data = await self._extract_npc_data(
            fallback_npc_sections,
            source_label,
            core_mechanic_hint=charsheet_data.get("core_mechanic", {}),
            source_profile_context=source_profile_context,
        )
        n_blocks = len(npc_data.get("stat_blocks", []))
        has_rules = bool(npc_data.get("creation_rules"))
        self._update_job(
            job_id,
            activity_log=[
                f"NPC pass complete: {n_blocks} stat blocks, "
                f"creation_rules={'yes' if has_rules else 'no'}"
            ],
        )

        # Generation Templates (depends on archetypes, stat blocks, and profiles)
        if include_generation_templates:
            # Build known entity roster for cross-referencing
            archetype_list = [e.name for e in (known_entities or [])]
            statblock_list = [s.get("name", "") for s in npc_data.get("stat_blocks", [])]
            profile_list = [p.name for p in character_profiles]

            known_entity_context = (
                f"Archetypes: {', '.join(archetype_list)}\n"
                f"Stat Blocks: {', '.join(statblock_list)}\n"
                f"Profiles: {', '.join(profile_list)}"
            )

            generation_templates = await self._extract_generation_templates(
                sections.generation_template_sections,
                source_label,
                known_entities=known_entity_context,
            )
        self._update_job(
            job_id,
            progress=0.89,
            activity_log=[
                f"Generation template pass complete: {len(generation_templates)} templates extracted"
            ],
        )

        # Plot Thread extraction (dangling promises, threats, mysteries)
        if include_plot_threads:
            thread_sections = sections.plot_thread_sections or sections.content_sections
            plot_threads = await self._extract_plot_threads(
                thread_sections,
                source_label,
            )
        self._update_job(
            job_id,
            progress=0.895,
            activity_log=[f"Plot thread pass complete: {len(plot_threads)} threads extracted"],
        )

        return (
            game_rules,
            charsheet_data,
            creation_procedure_data,
            npc_data,
            random_tables,
            agendas,
            topologies,
            tone_profiles,
            character_profiles,
            generation_templates,
            plot_threads,
        )

    async def _assemble_and_finalize(
        self,
        job_id: UUID,
        pack_id: UUID,
        source_name: str,
        source_document_ids: List[UUID],
        axioms: List[ExtractedAxiom],
        entities: List[ExtractedEntityArchetype],
        lore_facts: List[ExtractedLoreFact],
        relationship_facts: List[ExtractedRelationship],
        game_rules: List[Dict[str, Any]],
        charsheet_data: Dict[str, Any],
        creation_procedure_data: Dict[str, Any],
        npc_data: Dict[str, Any],
        random_tables: List[ExtractedRandomTable],
        agendas: List[ExtractedAgenda],
        topologies: List[ExtractedTopology],
        tone_profiles: List[ExtractedToneProfile],
        character_profiles: List[ExtractedCharacterProfile],
        generation_templates: List[ExtractedGenerationTemplate],
        plot_threads: List[ExtractedPlotThread],
        is_game_system: bool,
        detected_system_name: Optional[str],
        source_profile: Optional[EmbeddedSourceProfile],
        pack_type: KnowledgePackType,
        auto_apply: bool,
        multiverse_id: Optional[UUID],
        universe_id: Optional[UUID],
        execution_summary: LLMExecutionSummary,
    ) -> AnalysisRunResult:
        """Phase 6: Assemble game system, save pack, auto-apply, and finalize."""
        system_name: Optional[str] = None
        game_system_id: Optional[UUID] = None
        embedded_game_system = None

        if is_game_system and detected_system_name:
            system_name = detected_system_name
            source_doc_id = source_document_ids[0] if source_document_ids else None
            game_system_id, embedded_game_system = await self._save_game_system(
                detected_system_name,
                game_rules,
                source_name,
                charsheet_data=charsheet_data,
                creation_procedure_data=creation_procedure_data,
                npc_data=npc_data,
                random_tables=random_tables,
                agendas=agendas,
                topologies=topologies,
                character_profiles=character_profiles,
                generation_templates=generation_templates,
                resolution_mechanics=charsheet_data.get("resolution_mechanics"),
                source_document_id=source_doc_id,
            )

        # Update pack with all extracted content
        mongodb_update_knowledge_pack(
            pack_id,
            KnowledgePackUpdate(
                status=KnowledgePackStatus.READY,
                tags=[pack_type.value] + ([system_name] if system_name else []),
                axioms=axioms,
                entity_archetypes=entities,
                lore_facts=lore_facts,
                entity_relationships=relationship_facts,
                random_tables=random_tables,
                agendas=agendas,
                topologies=topologies,
                tone_profiles=tone_profiles,
                character_profiles=character_profiles,
                generation_templates=generation_templates,
                plot_threads=plot_threads,
                game_system_id=game_system_id,
                game_system_data=embedded_game_system,
                source_profile_data=source_profile,
                system_name=system_name,
            ),
        )

        # Finalize job stage
        self._update_job(
            job_id,
            current_stage=IngestionStage.PROPOSE,
            stages_completed=[
                IngestionStage.UPLOAD,
                IngestionStage.EXTRACT,
                IngestionStage.EMBED,
                IngestionStage.ANALYZE,
            ],
            progress=0.9,
            activity_log=["Knowledge pack assembled and ready for proposal/apply step"],
        )

        # Auto-apply if requested
        if auto_apply and multiverse_id is not None:
            try:
                mongodb_apply_knowledge_pack(
                    pack_id,
                    ApplyKnowledgePackRequest(
                        multiverse_id=multiverse_id,
                        universe_id=universe_id,
                        proposer=self.agent_id,
                    ),
                )
                proposals = len(axioms) + len(entities) + len(lore_facts) + len(relationship_facts)
                self._update_job(
                    job_id,
                    proposals_generated=proposals,
                    progress=0.95,
                    current_stage=IngestionStage.CANONIZE,
                    stages_completed=[
                        IngestionStage.UPLOAD,
                        IngestionStage.EXTRACT,
                        IngestionStage.EMBED,
                        IngestionStage.ANALYZE,
                        IngestionStage.PROPOSE,
                    ],
                    activity_log=[
                        f"Auto-apply complete: {proposals} proposals generated for CanonKeeper"
                    ],
                )
            except Exception as apply_exc:  # noqa: BLE001
                logger.warning(
                    "Auto-apply failed for pack %s (pack is still usable): %s", pack_id, apply_exc
                )
                self._update_job(
                    job_id,
                    progress=0.95,
                    warnings=[f"Auto-apply failed: {apply_exc}"],
                    activity_log=[f"Auto-apply failed (pack still usable): {apply_exc}"],
                )
        else:
            self._update_job(
                job_id,
                progress=0.95,
                activity_log=["Analysis complete; pack ready for review in the Packs tab"],
            )

        final_status = execution_summary.final_status()
        self._update_job(
            job_id,
            next_retry_at=None,
            **execution_summary.as_job_update(),
        )
        if final_status != IngestionStatus.COMPLETED:
            self._update_job(
                job_id,
                status=final_status,
                activity_log=[
                    f"Analysis finished with {execution_summary.failed_batches} failed LLM batch(es); status={final_status.value}"
                ],
                **execution_summary.as_job_update(),
            )

        result = AnalysisRunResult(
            pack_id=pack_id,
            status=final_status,
            total_batches=execution_summary.total_batches,
            succeeded_batches=execution_summary.succeeded_batches,
            failed_batches=execution_summary.failed_batches,
            retried_batches=execution_summary.retried_batches,
            current_provider=execution_summary.current_provider,
            current_model=execution_summary.current_model,
            last_error=execution_summary.last_error,
        )
        self._active_execution_summary = None
        self._active_job_id = None
        return result

    # ------------------------------------------------------------------
    # Chunk retrieval
    # ------------------------------------------------------------------

    async def _retrieve_sections_by_category(
        self,
        source_name: str,
        categories: List[str],
        collection: str = "snippets",
        fallback_queries: Optional[List[str]] = None,
    ) -> List[_SectionDigest]:
        """
        Retrieve Qdrant chunks grouped by section_path into coherent section digests.

        Returns one _SectionDigest per section — heading + combined body text trimmed
        to _MAX_SECTION_WORDS — preserving the narrative and structural context that
        flat batch retrieval loses.  Falls back to semantic search for documents
        ingested before section_path tagging was added.
        """
        from qdrant_client.models import MatchAny

        client = get_qdrant_client()
        await client.ensure_collection(collection)
        qdrant = client.get_client()

        # section_path → {"texts": [(page, idx, text)], "min_page": int, "min_chunk_index": int}
        sections: Dict[str, Dict[str, Any]] = {}
        seen_texts: set[str] = set()
        total_chunks = 0

        # --- Primary: category filter scroll ---
        try:
            cat_filter = Filter(
                must=[
                    FieldCondition(key="source_name", match=MatchValue(value=source_name)),
                    FieldCondition(key="semantic_category", match=MatchAny(any=categories)),
                ],
                must_not=[
                    FieldCondition(
                        key="artifact_type",
                        match=MatchAny(
                            any=["chunk_summary", "section_summary", "source_mindscape"]
                        ),
                    )
                ],
            )
            offset = None
            while total_chunks < _MAX_CATEGORY_CHUNKS:
                batch, offset = await qdrant.scroll(
                    collection_name=collection,
                    scroll_filter=cat_filter,
                    limit=64,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                if not batch:
                    break
                for pt in batch:
                    payload = pt.payload or {}
                    text = payload.get("text", "")
                    if not text or text in seen_texts:
                        continue
                    seen_texts.add(text)
                    total_chunks += 1
                    section_path = payload.get("section_path") or "General"
                    page = payload.get("page_number") or 0
                    idx = payload.get("chunk_index") or 0

                    append_section_chunk(
                        sections,
                        section_path=section_path,
                        page=page,
                        idx=idx,
                        text=text,
                        chunk_id=payload.get("chunk_id"),
                        semantic_category=payload.get("semantic_category"),
                    )
                if offset is None:
                    break
        except Exception as exc:
            logger.warning("Section retrieval failed for '%s' %s: %s", source_name, categories, exc)

        # --- Fallback: semantic search for untagged documents ---
        if not sections and fallback_queries:
            logger.info(
                "No category-tagged sections for '%s' %s; using fallback semantic search",
                source_name,
                categories,
            )
            for query in fallback_queries:
                try:
                    vector = await embed_text(query)
                    src_filter = Filter(
                        must=[
                            FieldCondition(key="source_name", match=MatchValue(value=source_name))
                        ],
                        must_not=[
                            FieldCondition(
                                key="artifact_type",
                                match=MatchAny(
                                    any=["chunk_summary", "section_summary", "source_mindscape"]
                                ),
                            )
                        ],
                    )
                    hits = await self._search_qdrant_points(
                        qdrant=qdrant,
                        collection=collection,
                        vector=vector,
                        query_filter=src_filter,
                        limit=16,
                    )
                    for scored in hits:
                        payload = scored.payload or {}
                        text = payload.get("text", "")
                        if not text or text in seen_texts:
                            continue
                        seen_texts.add(text)
                        section_path = payload.get("section_path") or "General"
                        page = payload.get("page_number") or 0
                        idx = payload.get("chunk_index") or 0
                        append_section_chunk(
                            sections,
                            section_path=section_path,
                            page=page,
                            idx=idx,
                            text=text,
                            chunk_id=payload.get("chunk_id"),
                            semantic_category=payload.get("semantic_category"),
                        )
                except Exception as exc:
                    logger.warning("Fallback section search failed for '%s': %s", query, exc)

        # --- Assemble section digests ---
        digests = build_section_digests(sections, max_words=_MAX_SECTION_WORDS)
        if len(digests) >= _MAX_SECTIONS_PER_LAYER:
            logger.warning(
                "Section cap (%d) reached for '%s' %s — some sections may be missing. "
                "Raise _MAX_SECTIONS_PER_LAYER if this source has many sub-sections.",
                _MAX_SECTIONS_PER_LAYER,
                source_name,
                categories,
            )
        return digests[:_MAX_SECTIONS_PER_LAYER]

    async def _retrieve_reference_sections(
        self,
        source_name: str,
        collection: str = "snippets",
    ) -> List[_SectionDigest]:
        """Retrieve table-of-contents, glossary, index, and chapter-map sections.

        TTRPG books often encode the system schema in appendices, glossaries,
        chapter lists, and indexed reference pages rather than in one neat
        "character sheet" chapter. This pass intentionally scans for those
        reference sections so the system-mapping prompts can enumerate
        attributes, skills, powers, and subsystems more completely.
        """
        client = get_qdrant_client()
        await client.ensure_collection(collection)
        qdrant = client.get_client()

        sections: Dict[str, Dict[str, Any]] = {}
        seen_texts: set[str] = set()
        total_chunks = 0

        try:
            src_filter = Filter(
                must=[FieldCondition(key="source_name", match=MatchValue(value=source_name))],
                must_not=[
                    FieldCondition(
                        key="artifact_type",
                        match=MatchAny(
                            any=["chunk_summary", "section_summary", "source_mindscape"]
                        ),
                    )
                ],
            )
            offset = None
            while total_chunks < _MAX_CATEGORY_CHUNKS:
                batch, offset = await qdrant.scroll(
                    collection_name=collection,
                    scroll_filter=src_filter,
                    limit=64,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                if not batch:
                    break

                for pt in batch:
                    payload = pt.payload or {}
                    text = payload.get("text", "")
                    if not text or text in seen_texts:
                        continue

                    section_path = payload.get("section_path") or "General"
                    heading_blob = f"{section_path}\n{text[:500]}".lower()
                    if not any(
                        keyword in heading_blob for keyword in _REFERENCE_SECTION_KEYWORDS
                    ) and not _REFERENCE_SECTION_RE.search(heading_blob):
                        continue

                    seen_texts.add(text)
                    total_chunks += 1
                    page = payload.get("page_number") or 0
                    idx = payload.get("chunk_index") or 0

                    append_section_chunk(
                        sections,
                        section_path=section_path,
                        page=page,
                        idx=idx,
                        text=text,
                        chunk_id=payload.get("chunk_id"),
                        semantic_category=payload.get("semantic_category"),
                    )

                if offset is None:
                    break
        except Exception as exc:
            logger.warning("Reference section retrieval failed for '%s': %s", source_name, exc)

        digests = build_section_digests(sections, max_words=_MAX_SECTION_WORDS)
        return digests[:_MAX_REFERENCE_SECTIONS]

    # ------------------------------------------------------------------
    # DSPy extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_section_context(section: _SectionDigest) -> str:
        """Format a section digest as a labelled heading + body for the DSPy prompt."""
        return format_section_context(section)

    # ------------------------------------------------------------------
    # Section classification — filter metadata before extraction
    # ------------------------------------------------------------------

    async def _classify_and_filter_sections(
        self,
        sections: List[_SectionDigest],
        source_name: str,
    ) -> List[_SectionDigest]:
        """
        Classify sections using a single LLM call and return only game_content sections.

        Sends section headings + short previews (not full text) to the classifier,
        which is cheap and fast.  Sections classified as metadata, index, or
        front_matter are filtered out.
        """
        if not sections:
            return []

        # Classify in batches of _CLASSIFIER_BATCH_SIZE so each call stays within
        # ~2.5K tokens and completes within MONITOR_LLM_TIMEOUT on slow providers.
        classifications: Dict[int, str] = {}  # 1-based global index → label

        n_batches = (len(sections) + _CLASSIFIER_BATCH_SIZE - 1) // _CLASSIFIER_BATCH_SIZE
        for batch_num, batch_start in enumerate(range(0, len(sections), _CLASSIFIER_BATCH_SIZE), 1):
            batch = sections[batch_start : batch_start + _CLASSIFIER_BATCH_SIZE]

            preview_lines = []
            for local_i, section in enumerate(batch, 1):
                heading = section.section_path or "General"
                preview = section.text[:120].replace("\n", " ")
                preview_lines.append(f"{local_i}. [{heading}] {preview}...")

            section_list = "\n".join(preview_lines)

            try:
                result = await self._call_module(
                    self._section_classifier,
                    stage="section_classification",
                    batch_id=f"{batch_num}/{n_batches}",
                    section_list=section_list,
                    source_name=source_name,
                )
                batch_classifications = parse_section_classifications(
                    result.classification_reasoning
                )
                for local_i, label in batch_classifications.items():
                    classifications[batch_start + local_i] = label
                logger.info(
                    "Section classifier batch %d/%d: classified %d sections",
                    batch_num,
                    n_batches,
                    len(batch_classifications),
                )
            except (asyncio.TimeoutError, Exception) as exc:
                logger.warning(
                    "Section classification failed for batch %d/%d of '%s': %s — keeping these sections",
                    batch_num,
                    n_batches,
                    source_name,
                    exc,
                )

        # Keep only game_content sections (default for unclassified = keep)
        filtered: List[_SectionDigest] = []
        for i, section in enumerate(sections, 1):
            classification = classifications.get(i, "game_content")
            if classification == "game_content":
                filtered.append(section)
            else:
                logger.info(
                    "Filtered section %d '%s' as %s",
                    i,
                    section.section_path,
                    classification,
                )

        return filtered

    # ------------------------------------------------------------------
    # Batched extraction — multiple sections per LLM call
    # ------------------------------------------------------------------

    async def _batched_extract_all(
        self,
        sections: List[_SectionDigest],
        source_name: str,
        include_axioms: bool,
        include_entities: bool,
        include_lore: bool,
        source_profile_context: str = "",
        source_profile: Optional[EmbeddedSourceProfile] = None,
    ) -> Tuple[List[ExtractedAxiom], List[ExtractedEntityArchetype], List[ExtractedLoreFact]]:
        """
        Extract axioms, entities, and lore facts from sections using parallel batched LLM calls.

        Groups sections into batches of _BATCH_SIZE and fires all calls concurrently,
        bounded by _EXTRACTION_CONCURRENCY to avoid rate-limiting.  Post-extraction
        name-based merge handles deduplication, while concurrency cuts total wall-clock
        time by ~_EXTRACTION_CONCURRENCY×.

        When a source_profile is supplied, sections are pre-ranked by profile relevance
        so the batches most likely to yield high-quality axioms, entities, and lore facts
        are processed first (and any early-exit / sampling logic benefits from the ordering).
        """
        all_axioms: List[ExtractedAxiom] = []
        all_entities: List[ExtractedEntityArchetype] = []
        all_lore: List[ExtractedLoreFact] = []

        if not sections:
            return all_axioms, all_entities, all_lore

        # Re-rank sections by profile signal density before batching.
        if source_profile is not None:
            sections = rank_sections_with_profile(sections, source_profile)

        # Build batches
        batches: List[List[_SectionDigest]] = [
            sections[i : i + _BATCH_SIZE] for i in range(0, len(sections), _BATCH_SIZE)
        ]

        n_batches = len(batches)
        logger.info(
            "Batched extraction: %d sections → %d batches of ≤%d (concurrency=%d)",
            len(sections),
            n_batches,
            _BATCH_SIZE,
            _EXTRACTION_CONCURRENCY,
        )

        # Semaphore caps concurrent LLM calls to avoid provider rate-limits.
        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _run_batch(batch_idx: int, batch: List[_SectionDigest]) -> Optional[Any]:
            section_texts = [self._format_section_context(s) for s in batch]
            sections_context = "\n\n---SECTION---\n\n".join(section_texts)
            async with sem:
                try:
                    result = await self._call_module(
                        self._batched_extractor,
                        stage="batched_extraction",
                        batch_id=f"{batch_idx + 1}/{n_batches}",
                        sections_context=sections_context,
                        source_name=source_name,
                        known_graph_context="",
                        source_profile_context=source_profile_context,
                    )
                    logger.info("Batch %d/%d complete", batch_idx + 1, n_batches)
                    return result
                except Exception as exc:
                    logger.warning(
                        "Batched extraction failed for batch %d/%d: %s",
                        batch_idx + 1,
                        n_batches,
                        exc,
                    )
                    return None

        # Fire all batches concurrently
        batch_results = list(
            await asyncio.gather(*[_run_batch(i, b) for i, b in enumerate(batches)])
        )

        # Collect typed results from all batches
        for result in batch_results:
            if result is None:
                continue
            if include_axioms:
                all_axioms.extend(result.axioms or [])
            if include_entities:
                all_entities.extend(result.entities or [])
            if include_lore:
                all_lore.extend(result.lore_facts or [])

        logger.info(
            "Parallel extraction complete: %d axioms, %d entities, %d lore (pre-merge)",
            len(all_axioms),
            len(all_entities),
            len(all_lore),
        )

        return all_axioms, merge_entity_archetypes(all_entities), all_lore

    def _materialize_container_entities(
        self,
        entities: List[ExtractedEntityArchetype],
        source_name: str,
    ) -> Tuple[List[ExtractedEntityArchetype], int]:
        """Create generic named parent/container entities from child hierarchy hints."""
        return materialize_container_entities(entities, source_name)

    def _materialize_social_entities_and_relationships(
        self,
        entities: List[ExtractedEntityArchetype],
        source_name: str,
    ) -> Tuple[List[ExtractedEntityArchetype], List[ExtractedRelationship], int]:
        """Create missing social/institutional entities and explicit membership links from traits."""
        return materialize_social_entities_and_relationships(entities, source_name)

    @staticmethod
    def _dedupe_relationships(
        relationships: List[ExtractedRelationship],
    ) -> List[ExtractedRelationship]:
        """Remove duplicate relationships while preserving the first-seen order."""
        return dedupe_relationships(relationships)

    @staticmethod
    def _build_graph_snapshot(
        entities: Dict[str, "ExtractedEntityArchetype"],
        relationships: List["ExtractedRelationship"],
        *,
        max_nodes: int = 40,
        max_edges: int = 30,
    ) -> str:
        """Build a compact Cypher-style snapshot of the known graph for context injection."""
        return build_graph_snapshot(
            entities,
            relationships,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    async def _synthesize_source_profile(
        self,
        source_name: str,
        sections: List[_SectionDigest],
        reference_sections: List[_SectionDigest],
        source_kind: str,
    ) -> Optional[EmbeddedSourceProfile]:
        """Synthesize a structured source profile before deep extraction begins."""
        if not sections and not reference_sections:
            return None

        seed_profile = build_source_profile_seed(
            source_name,
            sections,
            reference_sections,
            source_kind=source_kind,
        )

        representative_sections = "\n\n---SECTION---\n\n".join(
            self._format_section_context(section)
            for section in (sections[:6] or reference_sections[:6])
        )
        heading_paths = (
            "\n".join(
                f"- {section.section_path}"
                for section in [*reference_sections[:10], *sections[:12]]
                if section.section_path
            )
            or "- General"
        )
        reference_signals = (
            "\n\n---REFERENCE---\n\n".join(
                self._format_section_context(section) for section in reference_sections[:8]
            )
            or "None"
        )

        synthesized: Optional[EmbeddedSourceProfile] = None
        try:
            result = await self._call_module(
                self._source_profiler,
                stage="source_profile_synthesis",
                representative_sections=representative_sections or "None",
                heading_paths=heading_paths,
                reference_signals=reference_signals,
                source_name=source_name,
                draft_profile_context=seed_profile.model_dump_json(indent=2),
            )
            synthesized = parse_source_profile(getattr(result, "profile_json", ""))
        except Exception as exc:
            logger.warning("Source profile synthesis failed for '%s': %s", source_name, exc)

        profile = merge_source_profiles(seed_profile, synthesized)
        if not any(
            [
                profile.system_name,
                profile.taxonomy_containers,
                profile.lore_domains,
                (profile.coverage_summary or "").strip(),
            ]
        ):
            return None
        return profile

    async def synthesize_mindscape(
        self,
        *,
        sections: List[_SectionDigest],
        source_name: str,
        pack_id: UUID | str,
    ) -> SourceMindscapeArtifact:
        """
        Generate section summaries and a source-level semantic frame.
        Persists artifacts to the KnowledgePack and returns the SourceMindscapeArtifact.
        """
        section_summarizer = SectionSummaryModule()
        global_synthesizer = SourceMindscapeSynthesisModule()

        section_inputs = build_section_summary_inputs(
            [
                {
                    "heading_path": s.section_path.split(" > "),
                    "text": s.text,
                    "chunk_ids": getattr(s, "chunk_ids", []),
                    "semantic_category": getattr(s, "semantic_category", None),
                }
                for s in sections
            ]
        )
        chunk_summary_artifacts = build_chunk_summary_artifacts(sections)
        section_summary_artifacts: List[SectionSummaryArtifact] = []
        formatted_section_summaries: List[str] = []

        for inp in section_inputs:
            try:
                result = await self._call_module(
                    section_summarizer,
                    stage="section_summary",
                    heading_path=inp["heading_path"],
                    section_text=inp["section_text"],
                )
                summary_text = getattr(result, "summary", "") or ""
            except Exception as exc:
                logger.warning("Section summary failed for '%s': %s", inp["heading_path"], exc)
                summary_text = ""

            artifact = SectionSummaryArtifact(
                section_key=inp["heading_path"].replace(" > ", "_").lower(),
                heading_path=inp["heading_path"].split(" > "),
                chunk_ids=list(inp.get("chunk_ids", []) or []),
                summary=summary_text or inp.get("section_text", "")[:280],
                confidence=0.8 if summary_text else 0.55,
                semantic_category=inp.get("semantic_category"),
            )
            section_summary_artifacts.append(artifact)
            if summary_text:
                formatted_section_summaries.append(f"{inp['heading_path']}: {summary_text}")

        try:
            global_result = await self._call_module(
                global_synthesizer,
                stage="mindscape_synthesis",
                section_summaries="\n".join(formatted_section_summaries),
                source_name=source_name,
            )
            mindscape = SourceMindscapeArtifact(
                source_name=source_name,
                summary=getattr(global_result, "global_summary", "") or "",
                themes=getattr(global_result, "themes", []) or [],
                taxonomy_hints=getattr(global_result, "taxonomy_hints", []) or [],
                system_name=getattr(global_result, "system_name", None),
                confidence=0.85,
            )
        except Exception as exc:
            logger.warning("Mindscape synthesis failed for '%s': %s", source_name, exc)
            mindscape = SourceMindscapeArtifact(
                source_name=source_name,
                summary="",
                themes=[],
                taxonomy_hints=[],
                system_name=None,
                confidence=0.0,
            )

        persist_mindscape_artifacts(
            pack_id=str(pack_id),
            chunk_summaries=chunk_summary_artifacts,
            section_summaries=section_summary_artifacts,
            mindscape=mindscape,
            mongo_client=None,
        )

        try:
            await self._project_mindscape_to_qdrant(
                source_name=source_name,
                chunk_summaries=chunk_summary_artifacts,
                section_summaries=section_summary_artifacts,
                mindscape=mindscape,
            )
        except Exception as exc:
            logger.warning("Qdrant mindscape projection failed for '%s': %s", source_name, exc)

        return mindscape

    async def _project_mindscape_to_qdrant(
        self,
        *,
        source_name: str,
        chunk_summaries: List[Any],
        section_summaries: List[Any],
        mindscape: Optional[Any],
        collection: str = "snippets",
    ) -> None:
        """Delegate to standalone mindscape projection function."""
        await project_mindscape_to_qdrant(
            source_name=source_name,
            chunk_summaries=chunk_summaries,
            section_summaries=section_summaries,
            mindscape=mindscape,
            collection=collection,
        )

    async def _detect_game_system(
        self,
        chunks: List[str],
        source_name: str,
        source_profile_context: str = "",
    ) -> Tuple[bool, Optional[str]]:
        """Return (is_game_system, system_name) using a flat sample of chunks."""
        if not chunks:
            return False, None

        sample = self._chunks_to_prompt(chunks[:_DETECTION_SAMPLE_SIZE])
        try:
            result = await self._call_module(
                self._game_detector,
                stage="game_detection",
                source_chunks=sample,
                source_name=source_name,
                source_profile_context=source_profile_context,
            )
        except asyncio.TimeoutError:
            logger.warning("Game system detection timed out — assuming not a game system")
            return False, None
        reasoning = result.game_system_reasoning or ""

        is_game = "IS_GAME_SYSTEM:YES" in reasoning.upper()
        system_name: Optional[str] = None
        m = re.search(r"SYSTEM_NAME:([^\|]+)", reasoning, re.IGNORECASE)
        if m:
            system_name = m.group(1).strip()
            if system_name.lower() in ("unknown", "n/a", "none", ""):
                system_name = None

        return is_game, system_name

    async def _extract_tone_profiles(
        self,
        sections: List[_SectionDigest],
        source_name: str,
    ) -> List[ExtractedToneProfile]:
        """Extract narrative tone profiles."""
        if not sections:
            return []

        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _extract_one(section: _SectionDigest) -> List[ExtractedToneProfile]:
            context = self._format_section_context(section)
            async with sem:
                try:
                    result = await self._call_module(
                        self._tone_extractor,
                        stage="tone_extraction",
                        batch_id=section.section_path[:80],
                        section_context=context,
                        source_name=source_name,
                    )
                    return result.tone_profiles or []
                except Exception as exc:
                    logger.warning(
                        "Tone extraction failed for section '%s': %s",
                        section.section_path,
                        exc,
                    )
                    return []

        batches = await asyncio.gather(*[_extract_one(s) for s in sections])
        all_profiles: List[ExtractedToneProfile] = []
        for batch in batches:
            all_profiles.extend(batch)
        return dedupe_named_items(all_profiles)

    async def _extract_character_profiles(
        self,
        sections: List[_SectionDigest],
        source_name: str,
    ) -> List[ExtractedCharacterProfile]:
        """Extract character narrative profiles."""
        if not sections:
            return []

        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _extract_one(section: _SectionDigest) -> List[ExtractedCharacterProfile]:
            context = self._format_section_context(section)
            async with sem:
                try:
                    result = await self._call_module(
                        self._character_profile_extractor,
                        stage="character_profile_extraction",
                        batch_id=section.section_path[:80],
                        section_context=context,
                        source_name=source_name,
                    )
                    return result.character_profiles or []
                except Exception as exc:
                    logger.warning(
                        "Character profile extraction failed for section '%s': %s",
                        section.section_path,
                        exc,
                    )
                    return []

        batches = await asyncio.gather(*[_extract_one(s) for s in sections])
        all_profiles: List[ExtractedCharacterProfile] = []
        for batch in batches:
            all_profiles.extend(batch)
        return dedupe_named_items(all_profiles)

    async def _extract_generation_templates(
        self,
        sections: List[_SectionDigest],
        source_name: str,
        known_entities: str = "",
    ) -> List[ExtractedGenerationTemplate]:
        """Extract NPC generation recipes."""
        if not sections:
            return []

        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _extract_one(section: _SectionDigest) -> List[ExtractedGenerationTemplate]:
            context = self._format_section_context(section)
            async with sem:
                try:
                    result = await self._call_module(
                        self._generation_template_extractor,
                        stage="generation_template_extraction",
                        batch_id=section.section_path[:80],
                        section_context=context,
                        source_name=source_name,
                        known_entities=known_entities,
                    )
                    return result.generation_templates or []
                except Exception as exc:
                    logger.warning(
                        "Generation template extraction failed for section '%s': %s",
                        section.section_path,
                        exc,
                    )
                    return []

        batches = await asyncio.gather(*[_extract_one(s) for s in sections])
        all_templates: List[ExtractedGenerationTemplate] = []
        for batch in batches:
            all_templates.extend(batch)
        return dedupe_named_items(all_templates)

    async def _extract_plot_threads(
        self,
        sections: List[_SectionDigest],
        source_name: str,
    ) -> List[ExtractedPlotThread]:
        """Extract dangling plot threads (promises, threats, mysteries, etc.)."""
        if not sections:
            return []

        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _extract_one(section: _SectionDigest) -> List[ExtractedPlotThread]:
            context = self._format_section_context(section)
            async with sem:
                try:
                    result = await self._call_module(
                        self._plot_thread_extractor,
                        stage="plot_thread_extraction",
                        batch_id=section.section_path[:80],
                        section_context=context,
                        source_name=source_name,
                    )
                    return result.plot_threads or []
                except Exception as exc:
                    logger.warning(
                        "Plot thread extraction failed for section '%s': %s",
                        section.section_path,
                        exc,
                    )
                    return []

        batches = await asyncio.gather(*[_extract_one(s) for s in sections])
        all_threads: List[ExtractedPlotThread] = []
        for batch in batches:
            all_threads.extend(batch)
        # Dedupe by title (plot threads use 'title' not 'name')
        seen_titles: set[str] = set()
        unique: List[ExtractedPlotThread] = []
        for t in all_threads:
            key = t.title.strip().lower()
            if key and key not in seen_titles:
                seen_titles.add(key)
                unique.append(t)
        return unique

    async def _extract_game_rules(
        self,
        sections: List[_SectionDigest],
        system_name: str,
        source_profile_context: str = "",
    ) -> List[Dict[str, Any]]:
        """Extract game rules — parallel LLM calls bounded by _EXTRACTION_CONCURRENCY."""
        if not sections:
            return []

        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _extract_one(section: _SectionDigest) -> List[Dict[str, Any]]:
            context = self._format_section_context(section)
            async with sem:
                try:
                    result = await self._call_module(
                        self._rule_extractor,
                        stage="game_rule_extraction",
                        batch_id=section.section_path[:80],
                        section_context=context,
                        system_name=system_name,
                        source_profile_context=source_profile_context,
                    )
                    return result.rules or []
                except Exception as exc:
                    logger.warning(
                        "Rule extraction failed for section '%s': %s",
                        section.section_path,
                        exc,
                    )
                    return []

        batches = await asyncio.gather(*[_extract_one(s) for s in sections])
        rules: List[Dict[str, Any]] = []
        for batch in batches:
            rules.extend(batch)
        return rules

    @staticmethod
    def _system_section_score(section: _SectionDigest) -> int:
        """Heuristically rank sections that are likely to define the system schema."""
        return system_section_score(section)

    async def _extract_character_sheet(
        self,
        sections: List[_SectionDigest],
        system_name: str,
        source_profile_context: str = "",
    ) -> Dict[str, Any]:
        """Extract character sheet structure using focused per-section and synthesis passes."""
        if not sections:
            return {
                "attributes": [],
                "skills": [],
                "resources": [],
                "powers": [],
                "subsystems": [],
                "core_mechanic": {},
                "resolution_mechanics": [],
            }

        focus_sections = prioritize_schema_sections(
            sections,
            limit=max(_SYSTEM_SCHEMA_SECTION_LIMIT, 1),
        )

        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _extract_one(section: _SectionDigest) -> Dict[str, Any]:
            context = self._format_section_context(section)
            async with sem:
                try:
                    result = await self._call_module(
                        self._charsheet_extractor,
                        stage="character_sheet_extraction",
                        batch_id=section.section_path[:80],
                        section_context=context,
                        system_name=system_name,
                        source_profile_context=source_profile_context,
                    )
                    return {
                        "attributes": result.attributes or [],
                        "skills": result.skills or [],
                        "resources": result.resources or [],
                        "conditions": result.conditions or [],
                        "scenery_rules": result.scenery_rules or [],
                        "core_mechanic": result.core_mechanic,
                        "resolution_mechanics": result.resolution_mechanics or [],
                    }
                except Exception as exc:
                    logger.warning(
                        "Character sheet extraction failed for section '%s': %s",
                        section.section_path,
                        exc,
                    )
                    return {}

        parsed_results: List[Dict[str, Any]] = [
            heuristic_extract_character_sheet_sections(focus_sections, system_name)
        ]
        parsed_results.extend(await asyncio.gather(*[_extract_one(s) for s in focus_sections]))

        if len(focus_sections) > 1:
            combined_context = "\n\n---SECTION---\n\n".join(
                self._format_section_context(section)
                for section in focus_sections[:_SYSTEM_SCHEMA_SECTION_LIMIT]
            )
            try:
                synthesis_result = await self._call_module(
                    self._charsheet_extractor,
                    stage="character_sheet_synthesis",
                    batch_id="combined",
                    section_context=combined_context,
                    system_name=system_name,
                    source_profile_context=source_profile_context,
                )
                parsed_results.append(
                    {
                        "attributes": synthesis_result.attributes or [],
                        "skills": synthesis_result.skills or [],
                        "resources": synthesis_result.resources or [],
                        "conditions": synthesis_result.conditions or [],
                        "scenery_rules": synthesis_result.scenery_rules or [],
                        "core_mechanic": synthesis_result.core_mechanic,
                        "resolution_mechanics": synthesis_result.resolution_mechanics or [],
                    }
                )
            except Exception as exc:
                logger.warning(
                    "Character sheet synthesis pass failed for '%s': %s",
                    system_name,
                    exc,
                )

        all_attrs: List[Dict[str, Any]] = []
        all_skills: List[Dict[str, Any]] = []
        all_resources: List[Dict[str, Any]] = []
        all_powers: List[Dict[str, Any]] = []
        all_subsystems: List[Dict[str, Any]] = []
        all_resolutions: List[Dict[str, Any]] = []
        core_mechanic: Dict[str, Any] = {}

        for parsed in parsed_results:
            if not parsed:
                continue
            all_attrs.extend(parsed.get("attributes", []))
            all_skills.extend(parsed.get("skills", []))
            all_resources.extend(parsed.get("resources", []))
            all_powers.extend(parsed.get("powers", []))
            all_subsystems.extend(parsed.get("subsystems", []))
            all_resolutions.extend(parsed.get("resolution_mechanics", []))
            if not core_mechanic and parsed.get("core_mechanic"):
                core_mechanic = parsed["core_mechanic"]

        return {
            "attributes": dedupe_named_items(all_attrs),
            "skills": dedupe_named_items(all_skills),
            "resources": dedupe_named_items(all_resources),
            "powers": dedupe_named_items(all_powers),
            "subsystems": dedupe_named_items(all_subsystems),
            "core_mechanic": core_mechanic,
            "resolution_mechanics": all_resolutions,
        }

    # ------------------------------------------------------------------
    # Character creation procedure extraction
    # ------------------------------------------------------------------

    async def _extract_creation_procedure(
        self,
        sections: List[_SectionDigest],
        system_name: str,
        source_profile_context: str = "",
    ) -> Dict[str, Any]:
        """Extract character creation procedure (steps, ability gen, backgrounds, advancement)."""
        if not sections:
            return {}

        focus_sections = prioritize_schema_sections(
            sections,
            limit=max(_SYSTEM_SCHEMA_SECTION_LIMIT, 1),
        )

        combined_context = "\n\n---SECTION---\n\n".join(
            self._format_section_context(section)
            for section in focus_sections[:_SYSTEM_SCHEMA_SECTION_LIMIT]
        )

        try:
            result = await self._call_module(
                self._creation_proc_extractor,
                stage="creation_procedure_extraction",
                batch_id="combined",
                section_context=combined_context,
                system_name=system_name,
                source_profile_context=source_profile_context,
            )
            return {"steps": result.steps or []}
        except Exception as exc:
            logger.warning(
                "Creation procedure extraction failed for '%s': %s",
                system_name,
                exc,
            )
            return {}

    # ------------------------------------------------------------------
    # NPC extraction
    # ------------------------------------------------------------------

    async def _extract_creation_logic(
        self,
        steps: List[Dict[str, Any]],
        known_entities: str,
    ) -> List[CreationLogicStep]:
        """Synthesize actionable logic from text creation steps."""
        if not steps:
            return []

        # Convert steps to a readable prompt string
        steps_str = "\n".join(
            [
                f"STEP {s.get('step_number')}: {s.get('title')} - {s.get('instructions')}"
                for s in steps
            ]
        )

        try:
            result = await self._call_module(
                self._creation_logic_synthesizer,
                stage="creation_logic_synthesis",
                creation_steps=steps_str,
                known_entities=known_entities,
            )
            return result.logic_steps or []
        except Exception as exc:
            logger.warning("Creation logic synthesis failed: %s", exc)
            return []

    async def _extract_npc_data(
        self,
        sections: List[_SectionDigest],
        system_name: str,
        core_mechanic_hint: Optional[Dict[str, Any]] = None,
        source_profile_context: str = "",
    ) -> Dict[str, Any]:
        """Extract NPC stat blocks and NPC creation rules from bestiary/enemy sections."""
        if not sections:
            return {"stat_blocks": [], "creation_rules": None}

        focus_sections = prioritize_schema_sections(
            sections,
            limit=max(_SYSTEM_SCHEMA_SECTION_LIMIT, 1),
        )

        combined_context = "\n\n---SECTION---\n\n".join(
            self._format_section_context(section)
            for section in focus_sections[:_SYSTEM_SCHEMA_SECTION_LIMIT]
        )

        cm_hint = core_mechanic_hint or {}
        system_context = (
            f"Core mechanic type: {cm_hint.get('type', 'unknown')}, "
            f"success_type: {cm_hint.get('success_type', 'unknown')}"
        )

        try:
            result = await self._call_module(
                self._npc_extractor,
                stage="npc_extraction",
                batch_id="combined",
                system_name=system_name,
                system_context=system_context,
                source_profile_context=source_profile_context,
                text_chunks=combined_context,
            )
            return {
                "stat_blocks": result.stat_blocks or [],
                "creation_rules": result.creation_rules,
            }
        except Exception as exc:
            logger.warning(
                "NPC extraction failed for '%s': %s",
                system_name,
                exc,
            )
            return {"stat_blocks": [], "creation_rules": None}

    # ------------------------------------------------------------------
    # Random table extraction
    # ------------------------------------------------------------------

    async def _extract_random_tables(
        self,
        sections: List[_SectionDigest],
        source_name: str,
    ) -> List[ExtractedRandomTable]:
        """Extract structured random tables from identified table sections."""
        if not sections:
            return []

        # Table extraction can be very token-intensive if many tables exist.
        # We batch sections just like entities.
        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _run_batch(batch: List[_SectionDigest]) -> List[ExtractedRandomTable]:
            combined_context = "\n\n---SECTION---\n\n".join(
                self._format_section_context(section) for section in batch
            )
            async with sem:
                try:
                    result = await self._call_module(
                        self._table_extractor,
                        stage="random_table_extraction",
                        batch_id=f"{len(batch)}-sections",
                        section_context=combined_context,
                        source_name=source_name,
                    )
                    return result.random_tables or []
                except Exception as exc:
                    logger.warning(
                        "Random table extraction batch failed for '%s': %s",
                        source_name,
                        exc,
                    )
                    return []

        # Use same batch size as general extraction
        all_tables: List[ExtractedRandomTable] = []
        for i in range(0, len(sections), _BATCH_SIZE):
            batch = sections[i : i + _BATCH_SIZE]
            results = await _run_batch(batch)
            all_tables.extend(results)

        return dedupe_named_items(all_tables)

    async def _extract_agendas(
        self,
        sections: List[_SectionDigest],
        source_name: str,
    ) -> List[ExtractedAgenda]:
        """Extract faction agendas and clocks."""
        if not sections:
            return []

        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _run_batch(batch: List[_SectionDigest]) -> List[ExtractedAgenda]:
            combined_context = "\n\n---SECTION---\n\n".join(
                self._format_section_context(section) for section in batch
            )
            async with sem:
                try:
                    result = await self._call_module(
                        self._agenda_extractor,
                        stage="agenda_extraction",
                        batch_id=f"{len(batch)}-sections",
                        section_context=combined_context,
                        source_name=source_name,
                    )
                    return result.agendas or []
                except Exception as exc:
                    logger.warning("Agenda extraction failed for '%s': %s", source_name, exc)
                    return []

        all_agendas: List[ExtractedAgenda] = []
        for i in range(0, len(sections), _BATCH_SIZE):
            batch = sections[i : i + _BATCH_SIZE]
            results = await _run_batch(batch)
            all_agendas.extend(results)

        return dedupe_named_items(all_agendas)

    async def _extract_topologies(
        self,
        sections: List[_SectionDigest],
        source_name: str,
    ) -> List[ExtractedTopology]:
        """Extract spatial topology connections."""
        if not sections:
            return []

        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _run_batch(batch: List[_SectionDigest]) -> List[ExtractedTopology]:
            combined_context = "\n\n---SECTION---\n\n".join(
                self._format_section_context(section) for section in batch
            )
            async with sem:
                try:
                    result = await self._call_module(
                        self._topology_extractor,
                        stage="topology_extraction",
                        batch_id=f"{len(batch)}-sections",
                        section_context=combined_context,
                        source_name=source_name,
                    )
                    return result.topologies or []
                except Exception as exc:
                    logger.warning("Topology extraction failed for '%s': %s", source_name, exc)
                    return []

        all_topologies: List[ExtractedTopology] = []
        for i in range(0, len(sections), _BATCH_SIZE):
            batch = sections[i : i + _BATCH_SIZE]
            results = await _run_batch(batch)
            all_topologies.extend(results)

        # Deduplication for topologies (by from/to/type)
        seen = set()
        deduped = []
        for t in all_topologies:
            key = (
                t.from_location.lower().strip(),
                t.to_location.lower().strip(),
                t.connection_type.lower().strip(),
            )
            if key not in seen:
                seen.add(key)
                deduped.append(t)
        return deduped

    # ------------------------------------------------------------------
    # Entity evidence enrichment (using Qdrant MatchText full-text index)
    # ------------------------------------------------------------------

    async def _retrieve_entity_evidence(
        self,
        source_name: str,
        entity_names: List[str],
        collection: str = "snippets",
        snippets_per_entity: int = 4,
    ) -> Dict[str, List[str]]:
        """
        For each extracted entity name, retrieve chunks from Qdrant that literally
        mention that name using the MatchText full-text payload index.

        Runs lookups concurrently with bounded parallelism.

        Returns:
            Dict mapping entity_name → list of raw chunk texts (deduped).
        """
        client = get_qdrant_client()
        await client.ensure_collection(collection)
        qdrant = client.get_client()

        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _lookup(name: str) -> Tuple[str, List[str]]:
            async with sem:
                try:
                    text_filter = Filter(
                        must=[
                            FieldCondition(
                                key="source_name",
                                match=MatchValue(value=source_name),
                            ),
                            FieldCondition(
                                key="text",
                                match=MatchText(text=name.strip()),
                            ),
                        ]
                    )
                    batch, _ = await qdrant.scroll(
                        collection_name=collection,
                        scroll_filter=text_filter,
                        limit=snippets_per_entity,
                        with_payload=True,
                        with_vectors=False,
                    )
                    texts: List[str] = []
                    seen: set[str] = set()
                    for pt in batch:
                        txt = (pt.payload or {}).get("text", "")
                        if txt and txt not in seen:
                            seen.add(txt)
                            texts.append(txt)
                    return name, texts
                except Exception as exc:
                    logger.debug("Entity evidence lookup failed for '%s': %s", name, exc)
                    return name, []

        valid_names = [n for n in entity_names if n and n.strip()]
        results = await asyncio.gather(*[_lookup(n) for n in valid_names])

        evidence: Dict[str, List[str]] = {}
        for name, texts in results:
            if texts:
                evidence[name] = texts
        return evidence

    def _enrich_entities_from_evidence(
        self,
        entities: List[ExtractedEntityArchetype],
        evidence: Dict[str, List[str]],
    ) -> List[ExtractedEntityArchetype]:
        """Delegate to standalone enrichment function."""
        return enrich_entities_from_evidence(entities, evidence)

    # Max entities per relationship-inference batch.
    # At ~120 chars/entity line: 30 entities ≈ 3.6K chars ≈ ~900 tokens input
    # (plus prompt overhead) — well inside the HEAVY model's context window.
    _REL_BATCH_SIZE = 5

    def _build_entity_roster_line(self, e: "ExtractedEntityArchetype") -> str:
        """Format one entity as a compact roster line for relationship inference."""
        type_label = e.entity_type
        if e.sub_type:
            type_label += f"/{e.sub_type}"
        parent_note = f", parent={e.parent_entity_name}" if e.parent_entity_name else ""
        desc_snippet = ""
        if e.description:
            raw = e.description.strip().replace("\n", " ")
            desc_snippet = raw[:80] + ("…" if len(raw) > 80 else "")
        traits_snippet = ""
        if e.properties:
            items = list(e.properties.items())[:5]
            traits_snippet = " | " + ", ".join(f"{k}:{v}" for k, v in items)
        line = f"{e.name} ({type_label}{parent_note})"
        if desc_snippet:
            line += f": {desc_snippet}"
        if traits_snippet:
            line += traits_snippet
        return line

    async def _infer_relationships(
        self,
        entities: List[ExtractedEntityArchetype],
        source_name: str,
        source_profile_context: str = "",
    ) -> List[ExtractedRelationship]:
        """
        Post-extraction pass: infer entity-to-entity relationships.

        Batching strategy (three call types, all run concurrently):

        1. **Family batches** — one call per container *that has children*.
           Each call sees the container + its direct children.  Produces
           fine-grained hierarchy edges (subtype_of, part_of, instance_of).

        2. **Cross-family batch** — one call over all real containers + top
           factions/locations.  Produces inter-group edges (member_of,
           allied_with, enemy_of, controls, leads).

        3. **Orphan batches** — entities that have no parent AND no children,
           chunked at _REL_BATCH_SIZE.  Catches standalone characters and
           objects that relate to known groups.

        Keeping each batch ≤ _REL_BATCH_SIZE entities keeps token budgets
        predictable and prevents the single-call timeouts we saw before.
        """
        if not entities:
            return []

        # ── Classify entities ──────────────────────────────────────────────
        # "Real containers" = entities that appear as parent_entity_name for
        # at least one other entity.  More reliable than is_container flag.
        parent_names_in_use: set[str] = {
            e.parent_entity_name.lower().strip() for e in entities if e.parent_entity_name
        }
        children_by_parent: Dict[str, List[ExtractedEntityArchetype]] = {}
        for e in entities:
            if e.parent_entity_name:
                children_by_parent.setdefault(e.parent_entity_name, []).append(e)

        real_containers: List[ExtractedEntityArchetype] = []
        orphans: List[ExtractedEntityArchetype] = []
        for e in entities:
            name_key = e.name.lower().strip()
            if name_key in parent_names_in_use:
                real_containers.append(e)
            elif not e.parent_entity_name:
                orphans.append(e)
            # entities WITH a parent go into children_by_parent only

        # ── Build family batches ───────────────────────────────────────────
        batches: List[List[ExtractedEntityArchetype]] = []
        for container in real_containers:
            family = [container] + children_by_parent.get(container.name, [])
            batches.extend(
                family[start : start + self._REL_BATCH_SIZE]
                for start in range(0, len(family), self._REL_BATCH_SIZE)
            )

        # ── Cross-family batch — top-level entities only ───────────────────
        # Containers (taxonomy roots) + top-level factions/locations that are
        # not children of anything.  Include diverse entity_types so the LLM
        # has enough context to discover cross-group edges.
        cross_family = [
            e
            for e in real_containers + orphans
            if e.entity_type in ("faction", "location", "organization", "concept")
        ]
        batches.extend(
            cross_family[start : start + self._REL_BATCH_SIZE]
            for start in range(0, len(cross_family), self._REL_BATCH_SIZE)
        )

        # ── Orphan batches — standalone characters, objects, etc. ─────────
        batches.extend(
            orphans[start : start + self._REL_BATCH_SIZE]
            for start in range(0, len(orphans), self._REL_BATCH_SIZE)
        )

        # Remove duplicate / single-entity batches (no rels can be inferred
        # from a single entity).
        seen_ids: set[frozenset[str]] = set()
        deduped_batches: List[List[ExtractedEntityArchetype]] = []
        for batch in batches:
            if len(batch) < 2:
                continue
            key = frozenset(e.name for e in batch)
            if key not in seen_ids:
                seen_ids.add(key)
                deduped_batches.append(batch)
        batches = deduped_batches

        if not batches:
            return []

        logger.info(
            "Relationship inference: %d entities (%d containers, %d orphans) → %d batches",
            len(entities),
            len(real_containers),
            len(orphans),
            len(batches),
        )

        all_entities_by_key = {e.name.lower().strip(): e for e in entities}
        known_snapshot = self._build_graph_snapshot(all_entities_by_key, [])

        sem = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

        async def _run_batch(batch: List[ExtractedEntityArchetype]) -> List[ExtractedRelationship]:
            roster_lines = [self._build_entity_roster_line(e) for e in batch]
            entity_roster = "\n".join(roster_lines)
            full_roster = (
                f"# Known structure (do not re-emit these as REL lines):\n{known_snapshot}\n\n"
                f"# Entities to analyse:\n{entity_roster}"
                if known_snapshot
                else entity_roster
            )
            async with sem:
                try:
                    result = await self._call_module(
                        self._rel_inferer,
                        stage="relationship_inference",
                        batch_id=f"{len(batch)}-entities",
                        entity_roster=full_roster,
                        source_name=source_name,
                        source_profile_context=source_profile_context,
                    )
                    return result.relationships or []
                except Exception as exc:
                    logger.warning(
                        "Relationship inference batch failed for '%s': %s", source_name, exc
                    )
                    return []

        batch_results = await asyncio.gather(*[_run_batch(b) for b in batches])
        all_rels: List[ExtractedRelationship] = []
        for rels in batch_results:
            all_rels.extend(rels)
        return all_rels

    async def _save_game_system(
        self,
        system_name: str,
        game_rules: List[Dict[str, Any]],
        source_name: str,
        charsheet_data: Optional[Dict[str, Any]] = None,
        creation_procedure_data: Optional[Dict[str, Any]] = None,
        npc_data: Optional[Dict[str, Any]] = None,
        random_tables: Optional[List[ExtractedRandomTable]] = None,
        agendas: Optional[List[ExtractedAgenda]] = None,
        topologies: Optional[List[ExtractedTopology]] = None,
        character_profiles: Optional[List[ExtractedCharacterProfile]] = None,
        generation_templates: Optional[List[ExtractedGenerationTemplate]] = None,
        resolution_mechanics: Optional[List[Dict[str, Any]]] = None,
        source_document_id: Optional[UUID] = None,
    ) -> Tuple[Optional[UUID], EmbeddedGameSystem]:
        """Delegate to standalone game system persistence function."""
        return await save_game_system(
            system_name=system_name,
            game_rules=game_rules,
            source_name=source_name,
            charsheet_data=charsheet_data,
            creation_procedure_data=creation_procedure_data,
            npc_data=npc_data,
            random_tables=random_tables,
            agendas=agendas,
            topologies=topologies,
            character_profiles=character_profiles,
            generation_templates=generation_templates,
            resolution_mechanics=resolution_mechanics,
            source_document_id=source_document_id,
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    async def _search_qdrant_points(
        qdrant: Any,
        collection: str,
        vector: List[float],
        query_filter: Filter,
        limit: int,
    ) -> List[Any]:
        """Compatibility wrapper for mixed Qdrant client/server versions."""
        if hasattr(qdrant, "search"):
            return cast(
                List[Any],
                await qdrant.search(
                    collection_name=collection,
                    query_vector=vector,
                    limit=limit,
                    query_filter=query_filter,
                ),
            )

        search_api = getattr(getattr(qdrant, "http", None), "search_api", None)
        if search_api is not None and hasattr(search_api, "search_points"):
            response = await search_api.search_points(
                collection_name=collection,
                search_request=SearchRequest(
                    vector=vector,
                    limit=limit,
                    with_payload=True,
                    with_vector=False,
                    filter=query_filter,
                ),
            )
            return list(getattr(response, "result", []) or [])

        if hasattr(qdrant, "query_points"):
            response = await qdrant.query_points(
                collection_name=collection,
                query=vector,
                limit=limit,
                with_payload=True,
                with_vectors=False,
                query_filter=query_filter,
            )
            return list(getattr(response, "points", []) or getattr(response, "result", []) or [])

        raise AttributeError("No supported Qdrant search method found")

    @staticmethod
    def _chunks_to_prompt(chunks: List[str]) -> str:
        """Join text chunks with a separator for the DSPy prompt."""
        return "\n---\n".join(chunks)

    def _update_job(self, job_id: UUID, **kwargs: Any) -> None:
        """Update ingestion job progress fields (fire-and-forget; ignores errors)."""
        try:
            mongodb_update_ingestion_job(job_id, IngestionJobUpdate(**kwargs))
        except Exception as exc:  # noqa: BLE001
            # Log at WARNING for status transitions (critical state changes),
            # DEBUG for routine progress increments.
            if "status" in kwargs:
                logger.warning(
                    "Failed to update job %s status to %s: %s", job_id, kwargs["status"], exc
                )
            else:
                logger.debug("Job progress update failed for %s: %s", job_id, exc)
