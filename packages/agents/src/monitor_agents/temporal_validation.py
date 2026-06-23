"""
Temporal validation integration for CanonKeeper (Temporal & Contradiction Gap).

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts
CALLED BY: canonkeeper.py, scene_loop.py

This module integrates temporal and contradiction validation into the
CanonKeeper's proposal evaluation workflow for scene revisions.

Key functionality:
  1. validate_scene_revision — Run temporal and contradiction checks before committing
  2. check_proposal_contradictions — Check if proposed changes contradict existing canon
  3. handle_fact_replacement — Create new facts with `replaces` field when needed

Usage::

    from monitor_agents.temporal_validation import validate_scene_revision

    validation_result = await validate_scene_revision(
        scene_id=scene_id,
        universe_id=universe_id,
        story_id=story_id,
        scene_time_ref=datetime(1000, 1, 1),
        scene_text="The knights rode into battle...",
        proposals=proposals,
        canonkeeper=canonkeeper,
    )

    if not validation_result["is_valid"]:
        # Block revision until violations are resolved
        return validation_result
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import UUID

if TYPE_CHECKING:
    from monitor_agents.canonkeeper import CanonKeeper

from monitor_data.schemas.contradiction import (
    ContradictionResult,
)
from monitor_data.schemas.temporal_validation import (
    TemporalValidationRequest,
    TemporalValidationResult,
)
from monitor_data.tools.ingest_tools.contradiction_detection import (
    detect_contradictions,
)
from monitor_data.tools.temporal_tools import (
    validate_scene_temporal,
)

logger = logging.getLogger(__name__)


# =============================================================================
# PUBLIC API
# =============================================================================


async def validate_scene_revision(
    scene_id: UUID,
    universe_id: UUID,
    story_id: UUID,
    scene_time_ref: datetime,
    scene_text: str,
    proposals: List[Dict[str, Any]],
    canonkeeper: Any,
    entity_ids: Optional[List[UUID]] = None,
    location_ref: Optional[UUID] = None,
) -> Dict[str, Any]:
    """
    Validate a scene revision for temporal consistency and contradictions.

    This is called before committing scene revisions to ensure:
    1. Scene timeline respects canonical chronology
    2. No contradictions with existing canon
    3. Fact validity is respected

    Args:
        scene_id: The scene being revised.
        universe_id: The universe containing the scene.
        story_id: The story containing the scene.
        scene_time_ref: Scene timestamp.
        scene_text: Scene content for analysis.
        proposals: List of proposed changes from this revision.
        canonkeeper: CanonKeeper instance for fetching canon.
        entity_ids: Entities present in scene.
        location_ref: Scene location.

    Returns:
        Dict with validation results and recommendations.
    """
    result = {
        "scene_id": scene_id,
        "is_valid": True,
        "can_proceed": True,
        "temporal_result": None,
        "contradiction_result": None,
        "violations": [],
        "warnings": [],
        "recommendations": [],
    }

    # Fetch existing canon for validation
    canon_facts = await _fetch_canon_facts(universe_id, canonkeeper)
    canon_events = await _fetch_canon_events(universe_id, canonkeeper)
    canon_axioms = await _fetch_canon_axioms(universe_id, canonkeeper)

    # 1. Temporal validation
    temporal_request = TemporalValidationRequest(
        scene_id=scene_id,
        universe_id=universe_id,
        story_id=story_id,
        scene_time_ref=scene_time_ref,
        scene_text=scene_text,
        entity_ids=entity_ids or [],
        location_ref=location_ref,
        validate_against_facts=True,
        validate_against_events=True,
    )

    temporal_result = validate_scene_temporal(
        request=temporal_request,
        canon_events=canon_events,
        canon_facts=canon_facts,
    )
    result["temporal_result"] = temporal_result.model_dump(mode="json")

    if not temporal_result.is_valid:
        result["is_valid"] = False
        for violation in temporal_result.violations:
            result["violations"].append(
                {
                    "type": "temporal",
                    "severity": violation.severity.value,
                    "description": violation.description,
                }
            )

    if not temporal_result.can_proceed:
        result["can_proceed"] = False

    # 2. Contradiction detection (only if proposals create facts/axioms)
    if _has_proposals_needing_contradiction_check(proposals):
        # Build a mock KnowledgePack from proposals for contradiction checking
        from monitor_data.schemas.knowledge_packs import (
            KnowledgePackResponse,
            KnowledgePackStatus,
        )

        # Extract items from proposals
        new_axioms = _extract_axioms_from_proposals(proposals)
        new_lore_facts = _extract_lore_facts_from_proposals(proposals)
        new_entities = _extract_entities_from_proposals(proposals)

        mock_pack = KnowledgePackResponse(
            pack_id=UUID(),
            name=f"Scene Revision {scene_id}",
            description="Proposed changes from scene revision",
            pack_type="scene_revision",
            status=KnowledgePackStatus.READY,
            system_name=None,
            source_document_ids=[],
            ingestion_job_id=UUID(),
            tags=[],
            axioms=new_axioms,
            entity_archetypes=new_entities,
            lore_facts=new_lore_facts,
            entity_relationships=[],
            random_tables=[],
            agendas=[],
            topologies=[],
            tone_profiles=[],
            character_profiles=[],
            generation_templates=[],
            plot_threads=[],
            game_system_id=None,
            created_at=datetime.now(timezone.utc),
        )

        contradiction_result = detect_contradictions(
            new_pack=mock_pack,
            canon_axioms=[axiom.model_dump() for axiom in canon_axioms],
            canon_facts=canon_facts,
            multiverse_id=await _get_multiverse_id(universe_id, canonkeeper),
            universe_id=universe_id,
        )
        result["contradiction_result"] = contradiction_result.model_dump(mode="json")

        # Check for critical contradictions
        if contradiction_result.critical_severity_count > 0:
            result["is_valid"] = False
            result["can_proceed"] = False
            for match in contradiction_result.all_matches:
                if match.severity.value in ("critical", "high"):
                    result["violations"].append(
                        {
                            "type": "contradiction",
                            "severity": match.severity.value,
                            "description": match.explanation,
                            "recommended_resolution": match.recommended_resolution.value,
                        }
                    )

        # Add warnings for medium/low severity contradictions
        for match in contradiction_result.all_matches:
            if match.severity.value in ("medium", "low"):
                result["warnings"].append(
                    {
                        "type": "contradiction",
                        "severity": match.severity.value,
                        "description": match.explanation,
                        "recommended_resolution": match.recommended_resolution.value,
                    }
                )

    # 3. Generate recommendations
    result["recommendations"] = _generate_recommendations(
        temporal_result,
        result.get("contradiction_result"),
    )

    return result


async def check_proposal_contradictions(
    proposals: List[Dict[str, Any]],
    universe_id: UUID,
    canonkeeper: "CanonKeeper",
) -> ContradictionResult:
    """
    Check if proposed changes contradict existing canon.

    This is called by CanonKeeper during proposal evaluation to catch
    contradictions before they're committed.

    Args:
        proposals: List of proposed changes.
        universe_id: The universe containing the canon.
        canonkeeper: CanonKeeper instance for fetching canon.

    Returns:
        ContradictionResult with detected contradictions.
    """
    # Fetch existing canon
    canon_facts = await _fetch_canon_facts(universe_id, canonkeeper)
    canon_axioms = await _fetch_canon_axioms(universe_id, canonkeeper)

    # Build mock pack from proposals
    new_axioms = _extract_axioms_from_proposals(proposals)
    new_lore_facts = _extract_lore_facts_from_proposals(proposals)

    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackResponse,
        KnowledgePackStatus,
    )

    mock_pack = KnowledgePackResponse(
        pack_id=UUID(),
        name="Proposed Changes",
        description="Proposed changes to check for contradictions",
        pack_type="proposal_check",
        status=KnowledgePackStatus.READY,
        system_name=None,
        source_document_ids=[],
        ingestion_job_id=UUID(),
        tags=[],
        axioms=new_axioms,
        entity_archetypes=_extract_entities_from_proposals(proposals),
        lore_facts=new_lore_facts,
        entity_relationships=[],
        random_tables=[],
        agendas=[],
        topologies=[],
        tone_profiles=[],
        character_profiles=[],
        generation_templates=[],
        plot_threads=[],
        game_system_id=None,
        created_at=datetime.now(timezone.utc),
    )

    return detect_contradictions(
        new_pack=mock_pack,
        canon_axioms=[axiom.model_dump() for axiom in canon_axioms],
        canon_facts=canon_facts,
        multiverse_id=await _get_multiverse_id(universe_id, canonkeeper),
        universe_id=universe_id,
    )


def handle_fact_replacement(
    old_fact_id: UUID,
    new_fact_data: Dict[str, Any],
    scene_id: Optional[UUID] = None,
    reason: str = "Scene revision updated fact",
) -> Dict[str, Any]:
    """
    Prepare data for a fact replacement using the `replaces` field.

    This enables fact versioning and tombstoning in the Neo4j canon.
    The actual Neo4j write is done by CanonKeeper.

    Args:
        old_fact_id: The fact being replaced.
        new_fact_data: Data for the new fact.
        scene_id: Scene causing the replacement.
        reason: Why the replacement is occurring.

    Returns:
        Dict with new_fact_id and replacement tracking info.
    """
    # Add the `replaces` field to the new fact
    new_fact_data["replaces"] = str(old_fact_id)

    # The new fact will be created by CanonKeeper through the normal flow
    # This function just prepares the data and tracks the replacement

    return {
        "old_fact_id": str(old_fact_id),
        "new_fact_id": str(new_fact_data.get("id")) if new_fact_data.get("id") else None,
        "scene_id": str(scene_id) if scene_id else None,
        "reason": reason,
        "replacement_time": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# PRIVATE HELPERS
# =============================================================================


async def _fetch_canon_facts(
    universe_id: UUID,
    canonkeeper: "CanonKeeper",
) -> List[Dict[str, Any]]:
    """Fetch all canonical facts for a universe."""
    try:
        raw = await canonkeeper.call_tool(
            "neo4j_list_facts",
            {"filters": {"universe_id": str(universe_id), "canon_level": "canon"}},
        )
        if isinstance(raw, str):
            import json

            return json.loads(raw)
        if isinstance(raw, list):
            return raw
        return []
    except Exception as e:
        logger.error(f"Error fetching canon facts: {e}")
        return []


async def _fetch_canon_events(
    universe_id: UUID,
    canonkeeper: "CanonKeeper",
) -> List[Dict[str, Any]]:
    """Fetch all canonical events for a universe."""
    try:
        raw = await canonkeeper.call_tool(
            "neo4j_list_events",
            {"filters": {"universe_id": str(universe_id)}},
        )
        if isinstance(raw, str):
            import json

            return json.loads(raw)
        if isinstance(raw, list):
            return raw
        return []
    except Exception as e:
        logger.error(f"Error fetching canon events: {e}")
        return []


async def _fetch_canon_axioms(
    universe_id: UUID,
    canonkeeper: "CanonKeeper",
) -> List[Any]:
    """Fetch all canonical axioms for a universe."""
    try:
        raw = await canonkeeper.call_tool(
            "neo4j_list_axioms",
            {"filters": {"universe_id": str(universe_id), "canon_level": "canon"}},
        )
        if isinstance(raw, str):
            import json

            return json.loads(raw)
        if isinstance(raw, list):
            return raw
        return []
    except Exception as e:
        logger.error(f"Error fetching canon axioms: {e}")
        return []


async def _get_multiverse_id(
    universe_id: UUID,
    canonkeeper: "CanonKeeper",
) -> Optional[UUID]:
    """Get the multiverse ID for a universe."""
    try:
        universe = await canonkeeper.get_universe(universe_id)
        if universe:
            multiverse_id = universe.get("multiverse_id")
            if multiverse_id:
                return UUID(str(multiverse_id))
    except Exception as e:
        logger.error(f"Error getting multiverse ID: {e}")
    return None


def _has_proposals_needing_contradiction_check(
    proposals: List[Dict[str, Any]],
) -> bool:
    """Check if any proposals create facts/axioms that need contradiction checking."""
    for proposal in proposals:
        proposal_type = proposal.get("proposal_type", "")
        if proposal_type in (
            "create_axiom",
            "create_lore_fact",
            "create_entity_archetype",
        ):
            return True
    return False


def _extract_axioms_from_proposals(
    proposals: List[Dict[str, Any]],
) -> List[Any]:
    """Extract ExtractedAxiom objects from proposals."""
    from monitor_data.schemas.knowledge_packs import ExtractedAxiom

    axioms = []
    for proposal in proposals:
        if proposal.get("proposal_type") == "create_axiom":
            content = proposal.get("content", {})
            try:
                axiom = ExtractedAxiom(
                    statement=content.get("statement", ""),
                    domain=content.get("domain", ""),
                    source_ref=content.get("source_ref"),
                    confidence=content.get("confidence", 0.8),
                )
                axioms.append(axiom)
            except Exception as e:
                logger.warning(f"Failed to extract axiom from proposal: {e}")
    return axioms


def _extract_lore_facts_from_proposals(
    proposals: List[Dict[str, Any]],
) -> List[Any]:
    """Extract ExtractedLoreFact objects from proposals."""
    from monitor_data.schemas.knowledge_packs import ExtractedLoreFact

    facts = []
    for proposal in proposals:
        if proposal.get("proposal_type") == "create_lore_fact":
            content = proposal.get("content", {})
            try:
                fact = ExtractedLoreFact(
                    statement=content.get("statement", ""),
                    source_ref=content.get("source_ref"),
                    confidence=content.get("confidence", 0.8),
                )
                facts.append(fact)
            except Exception as e:
                logger.warning(f"Failed to extract lore fact from proposal: {e}")
    return facts


def _extract_entities_from_proposals(
    proposals: List[Dict[str, Any]],
) -> List[Any]:
    """Extract ExtractedEntityArchetype objects from proposals."""
    from monitor_data.schemas.knowledge_packs import ExtractedEntityArchetype

    entities = []
    for proposal in proposals:
        if proposal.get("proposal_type") == "create_entity_archetype":
            content = proposal.get("content", {})
            try:
                entity = ExtractedEntityArchetype(
                    name=content.get("name", ""),
                    entity_type=content.get("entity_type", ""),
                    description=content.get("description", ""),
                    source_ref=content.get("source_ref"),
                )
                entities.append(entity)
            except Exception as e:
                logger.warning(f"Failed to extract entity from proposal: {e}")
    return entities


def _generate_recommendations(
    temporal_result: Optional[TemporalValidationResult],
    contradiction_result: Optional[Dict[str, Any]],
) -> List[str]:
    """Generate recommendations based on validation results."""
    recommendations = []

    if temporal_result and not temporal_result.can_proceed:
        recommendations.append(
            "Scene timeline has critical violations. "
            "Adjust scene_time_ref or remove references to future events."
        )

    if temporal_result and temporal_result.warning_count > 0:
        recommendations.append(
            f"Scene has {temporal_result.warning_count} temporal warnings. "
            "Review anachronisms and fact validity."
        )

    if contradiction_result:
        total = contradiction_result.get("total_contradictions", 0)
        if total > 0:
            high_count = contradiction_result.get("high_severity_count", 0)
            critical_count = contradiction_result.get("critical_severity_count", 0)

            if critical_count > 0:
                recommendations.append(
                    f"{critical_count} critical contradiction(s) found. Resolve before committing."
                )
            elif high_count > 0:
                recommendations.append(
                    f"{high_count} high-severity contradiction(s) found. "
                    "Strongly recommend review before committing."
                )
            else:
                recommendations.append(f"{total} contradiction(s) found. Review recommended.")

    return recommendations
