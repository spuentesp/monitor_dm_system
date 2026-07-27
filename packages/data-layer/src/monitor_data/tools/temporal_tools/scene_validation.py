"""
Scene temporal validation (Temporal & Contradiction Gap).

LAYER: 1 (data-layer)

This module validates that scene timelines respect canonical chronology
and detects temporal inconsistencies such as:
  - Future references: Scene mentions events that haven't happened yet
  - Temporal paradoxes: Circular or impossible timeline
  - Anachronisms: Technology/knowledge not available at scene time
  - Fact validity: Scene uses facts that are expired or not yet valid

Usage::

    from monitor_data.tools.temporal_tools.scene_validation import validate_scene_temporal

    result = validate_scene_temporal(
        request=TemporalValidationRequest(
            scene_id=uuid,
            universe_id=uuid,
            story_id=uuid,
            scene_time_ref=datetime(1000, 1, 1),
            scene_text="The knights rode into battle...",
            entity_ids=[entity_id1, entity_id2],
        ),
        canon_events=[...],
        canon_facts=[...],
    )

    if not result.is_valid:
        # Handle temporal violations
        for violation in result.violations:
            print(f"{violation.severity}: {violation.description}")
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from monitor_data.schemas.temporal_validation import (
    FactValidityStatus,
    TemporalSeverity,
    TemporalValidationRequest,
    TemporalValidationResult,
    TemporalViolation,
    TemporalViolationType,
)
from monitor_data.tools.temporal_tools.fact_expiration import (
    check_fact_validity,
)

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Patterns for detecting temporal references in text
# -----------------------------------------------------------------------------

# Future reference patterns (e.g., "In the next year", "Tomorrow will be")
_FUTURE_REFERENCE_PATTERNS = [
    r"\b(in the (next|coming)\s+(year|month|week|day|hour))\b",
    r"\b(tomorrow)\b",
    r"\b(next\s+(year|month|week|day|hour))\b",
    r"\b(in the future)\b",
    r"\b(soon)\b",
    r"\b(eventually)\b",
    r"\b(later)\b",
]

# Past reference patterns (e.g., "Yesterday was", "In the past")
_PAST_REFERENCE_PATTERNS = [
    r"\b(in the (past|last)\s+(year|month|week|day|hour))\b",
    r"\b(yesterday)\b",
    r"\b(last\s+(year|month|week|day|hour))\b",
    r"\b(previously)\b",
    r"\b(formerly)\b",
    r"\b(before)\b",
]

# Technology/knowledge anachronism patterns (extend as needed)
_ANACHRONISM_KEYWORDS = [
    # Time period → forbidden keywords
    ("medieval", ["gunpowder", "steam", "electricity", "telephone", "computer", "internet"]),
    ("ancient", ["gunpowder", "steam", "electricity", "clockwork", "compass"]),
    ("renaissance", ["electricity", "telephone", "computer", "internet"]),
    ("modern", ["magic", "wizard", "spell"]),
]

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def validate_scene_temporal(
    request: TemporalValidationRequest,
    canon_events: Sequence[dict[str, Any]] | None = None,
    canon_facts: Sequence[dict[str, Any]] | None = None,
) -> TemporalValidationResult:
    """
    Validate temporal consistency of a scene against canonical chronology.

    Args:
        request: TemporalRequest with scene details.
        canon_events: Existing event dicts from Neo4j (must have 'id', 'title', 'start_time').
        canon_facts: Existing fact dicts from Neo4j/MongoDB (must have 'id', 'statement', 'time_ref', 'duration').

    Returns:
        TemporalResult with detected violations and validity assessment.
    """
    canon_events = canon_events or []
    canon_facts = canon_facts or []

    violations: list[TemporalViolation] = []

    # 1. Check for future references in scene text (always check - text patterns are independent)
    violations.extend(_check_future_references(request, canon_events))

    # 2. Check for anachronisms
    violations.extend(_check_anachronisms(request))

    # 3. Check fact validity
    if request.validate_against_facts:
        violations.extend(_check_fact_validity(request, canon_facts))

    # 4. Check for temporal paradoxes (circular references)
    if request.validate_against_events:
        violations.extend(_check_temporal_paradoxes(request, canon_events))

    # Build result
    result = TemporalValidationResult(
        scene_id=request.scene_id,
        universe_id=request.universe_id,
        scene_time_ref=request.scene_time_ref,
        violations=violations,
    )
    result.compute_totals()
    return result


# -----------------------------------------------------------------------------
# Validation checks
# -----------------------------------------------------------------------------


def _check_future_references(
    request: TemporalValidationRequest,
    canon_events: Sequence[dict[str, Any]],
) -> list[TemporalViolation]:
    """
    Check if scene references events that haven't happened yet at scene_time.
    """
    violations: list[TemporalViolation] = []

    # First, check text for future reference patterns
    text_lower = request.scene_text.lower()
    for pattern in _FUTURE_REFERENCE_PATTERNS:
        if re.search(pattern, text_lower):
            # Found a future reference - check if it's legitimate
            # (e.g., foreshadowing is okay, but stating facts about future is not)
            severity = _classify_future_reference_severity(pattern, request.scene_text)
            violations.append(
                TemporalViolation(
                    violation_id=f"future_ref:{request.scene_id}:{hash(pattern) % 10000}",
                    violation_type=TemporalViolationType.FUTURE_REFERENCE,
                    severity=severity,
                    description=f"Scene contains future reference pattern: {pattern}",
                    scene_id=request.scene_id,
                    scene_time_ref=request.scene_time_ref,
                    context={"pattern": pattern, "excerpt": request.scene_text[:200]},
                )
            )

    # Second, check if scene references specific future events
    for event in canon_events:
        event_start = event.get("start_time")
        if event_start and event_start > request.scene_time_ref:
            # Event happens after scene - check if scene references it
            event_title = event.get("title", "").lower()
            if event_title and event_title in request.scene_text.lower():
                violations.append(
                    TemporalViolation(
                        violation_id=f"future_event:{request.scene_id}:{event.get('id')}",
                        violation_type=TemporalViolationType.FUTURE_REFERENCE,
                        severity=TemporalSeverity.ERROR,
                        description=(
                            f"Scene references event that hasn't happened yet: "
                            f"'{event.get('title')}' occurs at {event_start}"
                        ),
                        scene_id=request.scene_id,
                        event_id=UUID(str(event.get("id"))) if event.get("id") else None,
                        scene_time_ref=request.scene_time_ref,
                        canon_time_ref=event_start,
                        context={"event_title": event.get("title")},
                    )
                )

    return violations


def _check_anachronisms(
    request: TemporalValidationRequest,
) -> list[TemporalViolation]:
    """
    Check for anachronistic technology or knowledge at scene time.
    """
    violations: list[TemporalViolation] = []

    text_lower = request.scene_text.lower()

    # Determine approximate time period from scene_time_ref
    # This is a simple heuristic - could be enhanced with more sophisticated logic
    year = request.scene_time_ref.year if request.scene_time_ref else None

    # Simple time period classification
    if year and year < 1000:
        period = "ancient"
    elif year and year < 1500:
        period = "medieval"
    elif year and year < 1800:
        period = "renaissance"
    elif year and year >= 2000:
        period = "modern"
    else:
        # Unknown period - skip anachronism check
        return []

    violations.extend(
        TemporalViolation(
            violation_id=f"anachronism:{request.scene_id}:{keyword}",
            violation_type=TemporalViolationType.ANACHRONISM,
            severity=TemporalSeverity.WARNING,
            description=(
                f"Possible anachronism: '{keyword}' in {period} setting (scene time: {request.scene_time_ref.year})"
            ),
            scene_id=request.scene_id,
            scene_time_ref=request.scene_time_ref,
            context={
                "keyword": keyword,
                "period": period,
                "excerpt": request.scene_text[:200],
            },
        )
        for check_period, forbidden_keywords in _ANACHRONISM_KEYWORDS
        if check_period == period
        for keyword in forbidden_keywords
        if keyword in text_lower
    )

    return violations


def _check_fact_validity(
    request: TemporalValidationRequest,
    canon_facts: Sequence[dict[str, Any]],
) -> list[TemporalViolation]:
    """
    Check if scene uses facts that are expired or not yet valid at scene time.
    """
    violations: list[TemporalViolation] = []

    for fact in canon_facts:
        validity = check_fact_validity(fact, request.scene_time_ref)

        # Check if fact statement appears in scene text
        fact_statement = fact.get("statement", "").lower()
        if fact_statement and fact_statement in request.scene_text.lower():
            if validity.status == FactValidityStatus.EXPIRED:
                violations.append(
                    TemporalViolation(
                        violation_id=f"expired_fact:{request.scene_id}:{fact.get('id')}",
                        violation_type=TemporalViolationType.EXPIRED_FACT,
                        severity=TemporalSeverity.WARNING,
                        description=(
                            f"Scene references expired fact: '{fact.get('statement')}' "
                            f"(expired at {validity.expires_at})"
                        ),
                        scene_id=request.scene_id,
                        fact_id=UUID(str(fact.get("id"))) if fact.get("id") else None,
                        scene_time_ref=request.scene_time_ref,
                        context={
                            "fact_statement": fact.get("statement"),
                            "expires_at": validity.expires_at.isoformat() if validity.expires_at else None,
                        },
                    )
                )
            elif validity.status == FactValidityStatus.NOT_YET_STARTED:
                violations.append(
                    TemporalViolation(
                        violation_id=f"premature_fact:{request.scene_id}:{fact.get('id')}",
                        violation_type=TemporalViolationType.PREMATURE_FACT,
                        severity=TemporalSeverity.WARNING,
                        description=(
                            f"Scene references fact that isn't valid yet: '{fact.get('statement')}' "
                            f"(becomes valid at {validity.time_ref})"
                        ),
                        scene_id=request.scene_id,
                        fact_id=UUID(str(fact.get("id"))) if fact.get("id") else None,
                        scene_time_ref=request.scene_time_ref,
                        context={
                            "fact_statement": fact.get("statement"),
                            "valid_from": validity.time_ref.isoformat() if validity.time_ref else None,
                        },
                    )
                )

    return violations


def _check_temporal_paradoxes(
    request: TemporalValidationRequest,
    canon_events: Sequence[dict[str, Any]],
) -> list[TemporalViolation]:
    """
    Check for temporal paradoxes or circular references.

    This is a basic check that can be enhanced with more sophisticated
    timeline analysis.
    """
    violations: list[TemporalViolation] = []

    # Check for events that are caused by this scene (if scene is in past)
    scene_time = request.scene_time_ref

    for event in canon_events:
        event_causes = event.get("causes", [])
        if request.scene_id in event_causes:
            # This event is caused by this scene
            event_start = event.get("start_time")
            if event_start and event_start < scene_time:
                # Event happens before scene, but is caused by scene - paradox!
                violations.append(
                    TemporalViolation(
                        violation_id=f"paradox:{request.scene_id}:{event.get('id')}",
                        violation_type=TemporalViolationType.TEMPORAL_PARADOX,
                        severity=TemporalSeverity.ERROR,
                        description=(
                            f"Temporal paradox: Scene causes event '{event.get('title')}' "
                            f"that occurs before the scene ({event_start} < {scene_time})"
                        ),
                        scene_id=request.scene_id,
                        event_id=UUID(str(event.get("id"))) if event.get("id") else None,
                        scene_time_ref=scene_time,
                        canon_time_ref=event_start,
                        context={
                            "event_title": event.get("title"),
                            "causes": event_causes,
                        },
                    )
                )

    return violations


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _classify_future_reference_severity(
    pattern: str,
    scene_text: str,
) -> TemporalSeverity:
    """
    Classify the severity of a future reference based on context.

    Foreshadowing (e.g., "Little did they know...") is less severe than
    stating facts about the future (e.g., "Tomorrow, the king will die").
    """
    text_lower = scene_text.lower()

    # Foreshadowing patterns - less severe
    foreshadowing_indicators = [
        "little did",
        "unknown to",
        "unbeknownst to",
        "would later",
        "was about to",
        "soon",
        "in the coming days",
    ]

    for indicator in foreshadowing_indicators:
        if indicator in text_lower:
            return TemporalSeverity.INFO

    # Statement of future fact - more severe
    if "will" in text_lower and "tomorrow" in text_lower:
        return TemporalSeverity.WARNING

    # Default to info level
    return TemporalSeverity.INFO
