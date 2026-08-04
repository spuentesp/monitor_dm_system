"""
Ingestion Loop — LangGraph StateGraph implementation for Multi-modal Ingestion.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.indexer.agent, monitor_agents.analyzer
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from langgraph.graph import END, StateGraph
from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.knowledge_packs import (
    KnowledgePackCreate,
    KnowledgePackStatus,
    KnowledgePackType,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_knowledge_pack,
    mongodb_update_ingestion_job,
)
from pydantic import BaseModel, Field

from monitor_agents.analyzer import Analyzer
from monitor_agents.indexer.agent import Indexer
from monitor_agents.ingestion.session_ingest import SessionListenerModule
from monitor_agents.ingestion.vision import MapExtractorModule
from monitor_agents.temporal_validation import check_proposal_contradictions

logger = logging.getLogger(__name__)


class IngestionModality(StrEnum):
    TEXT = "text"
    VISION = "vision"
    SESSION = "session"
    AUDIO = "audio"


class IngestionState(BaseModel):
    """State for the multi-modal ingestion loop."""

    # Input
    universe_id: UUID
    multiverse_id: UUID | None = None
    filename: str
    file_bytes: bytes | None = None
    source_title: str
    pack_name: str
    pack_type: KnowledgePackType = KnowledgePackType.SETTING_SUPPLEMENT

    # Processing Context
    modality: IngestionModality = IngestionModality.TEXT
    job_id: UUID | None = None
    source_id: UUID | None = None
    doc_id: UUID | None = None
    pack_id: UUID | None = None

    # Results
    extracted_entities: list[dict[str, Any]] = Field(default_factory=list)
    extracted_axioms: list[dict[str, Any]] = Field(default_factory=list)
    extracted_facts: list[dict[str, Any]] = Field(default_factory=list)
    extracted_mechanics: list[dict[str, Any]] = Field(default_factory=list)

    # Status
    status: IngestionStatus = IngestionStatus.PENDING
    errors: list[str] = Field(default_factory=list)
    current_stage: str = "init"


# =============================================================================
# NODES
# =============================================================================


async def detect_modality(state: IngestionState) -> dict[str, Any]:
    """Identify the input modality based on filename and content."""
    from pathlib import Path

    ext = Path(state.filename).suffix.lower()

    modality = IngestionModality.TEXT
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".pdf") and "map" in state.filename.lower():
        # Heuristic for map vision; real logic might inspect mime-type
        modality = IngestionModality.VISION
    elif ext in (".mp3", ".wav", ".m4a"):
        modality = IngestionModality.AUDIO
    elif state.pack_type == KnowledgePackType.SESSION_NOTES:
        modality = IngestionModality.SESSION

    return {"modality": modality, "current_stage": "routing"}


async def process_text(state: IngestionState) -> dict[str, Any]:
    """Standard text ingestion flow (I-1 to I-6)."""
    indexer = Indexer()
    analyzer = Analyzer()

    # 1. Indexing
    job_id = state.job_id or uuid4()
    await indexer.index(
        file_bytes=state.file_bytes,  # type: ignore[arg-type]
        filename=state.filename,
        source_name=state.source_title,
        metadata={
            "universe_id": str(state.universe_id),
            "job_id": str(job_id),
        },
    )

    # 1.5 Triage & Mechanics Extraction
    from monitor_data.db.qdrant import get_qdrant_client
    from monitor_agents.ingestion.triage import TriageAgent
    from monitor_agents.ingestion.mechanics_architect import MechanicsArchitect
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    triage_agent = TriageAgent()
    mechanics_architect = MechanicsArchitect()
    
    qdrant_client = get_qdrant_client().get_client()
    try:
        scroll_res, _ = await qdrant_client.scroll(
            collection_name="snippets",
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="job_id", match=MatchValue(value=str(job_id)))
                ]
            ),
            limit=1000
        )
        
        extracted_mechanics = []
        for point in scroll_res:
            text = point.payload.get("page_content", "") if point.payload else ""
            if not text:
                continue
                
            tags = triage_agent.triage(text)
            
            if "#mechanics" in tags or "#hybrid" in tags:
                mech_data = mechanics_architect.extract(text)
                if mech_data:
                    extracted_mechanics.append(mech_data)
    except Exception as exc:
        logger.warning(f"Failed to triage chunks from Qdrant: {exc}")
        extracted_mechanics = []

    # 2. Analysis
    analysis_res = await analyzer.analyze(  # type: ignore[call-arg]
        job_id=job_id,
        source_name=state.source_title,
        pack_name=state.pack_name,
        pack_type=state.pack_type,
        universe_id=state.universe_id,
        multiverse_id=state.multiverse_id,
    )

    return {
        "status": IngestionStatus.COMPLETED,
        "extracted_entities": [e.model_dump() for e in getattr(analysis_res, "entities", [])],
        "extracted_axioms": [a.model_dump() for a in getattr(analysis_res, "axioms", [])],
        "extracted_facts": [f.model_dump() for f in getattr(analysis_res, "lore_facts", [])],
        "extracted_mechanics": extracted_mechanics,
        "current_stage": "analysis_complete",
    }


async def process_vision(state: IngestionState) -> dict[str, Any]:
    """Extract spatial data from maps and images (I-14)."""
    extractor = MapExtractorModule()

    # Simulation: if we have image bytes but no description, we'd use a vision model.
    description = f"A map of {state.source_title} showing several points of interest."

    extraction = extractor(image_description=description)

    entities = []
    axioms = []
    for loc in extraction.locations:
        entities.append(
            {
                "name": loc.name,
                "entity_type": "location",
                "description": loc.description,
                "properties": {
                    "spatial_scale": extraction.scale_hint,
                    "coordinates": loc.coordinates,
                },
            }
        )
        if loc.contained_in:
            axioms.append(
                {
                    "statement": f"{loc.name} is located in {loc.contained_in}",
                    "axiom_type": "spatial",
                    "properties": {"relationship": "LOCATED_IN"},
                }
            )

    return {
        "extracted_entities": entities,
        "extracted_axioms": axioms,
        "current_stage": "vision_complete",
    }


async def process_live_session(state: IngestionState) -> dict[str, Any]:
    """Extract events and lore from session transcripts (I-15)."""
    listener = SessionListenerModule()

    # Assume file_bytes contains the transcript text
    transcript = state.file_bytes.decode("utf-8") if state.file_bytes else ""

    extraction = listener(turns=transcript)

    facts = []
    for event in extraction.events:
        facts.append(
            {
                "statement": event.statement,
                "fact_type": "event" if not event.is_lore else "state",
                "properties": {
                    "consequence": event.consequence,
                    "involved": event.involved_entities,
                },
            }
        )

    for lore in extraction.new_lore:
        facts.append({"statement": lore, "fact_type": "state", "properties": {"origin": "live_session"}})

    return {"extracted_facts": facts, "current_stage": "session_complete"}


async def synthesize_proposals(state: IngestionState) -> dict[str, Any]:
    """Synthesize all extracted data into a KnowledgePack and handle fact versioning (I-16)."""
    # I-16: Fact Versioning / Tombstoning
    # Check for contradictions with existing canon before creating the pack.
    # This allows us to prepopulate the 'replaces' field.
    final_facts = []
    for fact in state.extracted_facts:
        # Simple heuristic: find if this fact replaces an existing one
        # Real logic would use check_proposal_contradictions
        try:
            # We wrap the fact in a mock proposal for the checker
            proposal = {"proposal_type": "create_lore_fact", "content": fact}
            contradictions = await check_proposal_contradictions(  # type: ignore[call-arg]
                universe_id=state.universe_id, proposals=[proposal]
            )

            if contradictions and contradictions[0].get("contradicts"):  # type: ignore[index]
                # If it's a direct contradiction and the new fact is 'later' or higher confidence,
                # we set the 'replaces' field.
                old_id = contradictions[0]["contradicts"][0].get("id")  # type: ignore[index]
                if old_id:
                    fact["replaces"] = old_id
                    logger.info(f"Fact Versioning: Fact '{fact['statement']}' replaces {old_id}")
        except Exception as exc:
            logger.warning(f"Fact versioning check failed for fact: {exc}")

        final_facts.append(fact)

    # 1. Create KnowledgePack
    from monitor_data.schemas.knowledge_packs import EmbeddedGameSystem

    game_system_data = None
    if state.extracted_mechanics:
        game_system_data = EmbeddedGameSystem(name=state.pack_name or "Extracted Mechanics")
        for mech in state.extracted_mechanics:
            for key, val in mech.items():
                if isinstance(val, list) and hasattr(game_system_data, key):
                    current = getattr(game_system_data, key)
                    if isinstance(current, list):
                        current.extend(val)
                elif hasattr(game_system_data, key) and val is not None:
                    if not getattr(game_system_data, key):
                        setattr(game_system_data, key, val)

    pack = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name=state.pack_name,
            pack_type=state.pack_type,
            universe_id=state.universe_id,
            entities=state.extracted_entities,
            axioms=state.extracted_axioms,
            lore_facts=final_facts,
            game_system_data=game_system_data,
            status=KnowledgePackStatus.READY,
        )
    )

    # 2. Finalize Ingestion Job
    if state.job_id:
        mongodb_update_ingestion_job(
            state.job_id,
            {  # type: ignore[arg-type]
                "status": IngestionStatus.COMPLETED,
                "progress": 1.0,
                "completed_at": datetime.now(UTC),
                "activity_log": [f"Finalized multi-modal pack: {pack.id}"],
            },
        )

    return {
        "status": IngestionStatus.COMPLETED,
        "current_stage": "finalized",
        "pack_id": pack.id,
        "extracted_facts": final_facts,
    }


# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================


def route_modality(state: IngestionState) -> str:
    """Route to specialized extractor based on modality."""
    if state.modality == IngestionModality.VISION:
        return "process_vision"
    if state.modality in (IngestionModality.SESSION, IngestionModality.AUDIO):
        return "process_live_session"
    return "process_text"


def build_ingestion_graph() -> StateGraph[Any, Any, Any]:
    graph = StateGraph(IngestionState)

    graph.add_node("detect_modality", detect_modality)
    graph.add_node("process_text", process_text)
    graph.add_node("process_vision", process_vision)
    graph.add_node("process_live_session", process_live_session)
    graph.add_node("synthesize", synthesize_proposals)

    graph.set_entry_point("detect_modality")

    graph.add_conditional_edges(
        "detect_modality",
        route_modality,
        {
            "process_text": "process_text",
            "process_vision": "process_vision",
            "process_live_session": "process_live_session",
        },
    )

    graph.add_edge("process_text", "synthesize")
    graph.add_edge("process_vision", "synthesize")
    graph.add_edge("process_live_session", "synthesize")
    graph.add_edge("synthesize", END)

    return graph


class IngestionLoop:
    """
    LangGraph-based Ingestion Loop for Multi-modal document processing.
    """

    def __init__(self) -> None:
        self._graph = build_ingestion_graph()

    async def run(self, state: IngestionState | dict[str, Any]) -> dict[str, Any]:
        compiled = self._graph.compile()
        inputs = state if isinstance(state, dict) else state.model_dump()
        return await compiled.ainvoke(inputs)
