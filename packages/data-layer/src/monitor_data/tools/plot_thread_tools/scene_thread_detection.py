"""
Plot thread detection from scene content (Temporal & Contradiction Gap).

LAYER: 1 (data-layer)

This module extracts plot threads (promises, threats, mysteries, etc.)
from scene content and updates thread status based on scene outcomes.

Key functionality:
  1. detect_plot_threads_from_scene — Extract threads from scene text
  2. update_thread_status_from_scene — Update thread status based on outcomes
  3. classify_thread_content — Determine thread category from content

Usage::

    from monitor_data.tools.plot_thread_tools.scene_thread_detection import (
        detect_plot_threads_from_scene,
        update_thread_status_from_scene,
    )

    # Detect threads from scene content
    threads = detect_plot_threads_from_scene(
        scene_text="The king promised to rebuild the city...",
        scene_id=uuid,
        universe_id=uuid,
    )

    # Update thread status based on scene outcomes
    updates = update_thread_status_from_scene(
        scene_id=uuid,
        scene_text="The king fulfilled his promise...",
        universe_id=uuid,
    )
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from monitor_data.schemas.plot_threads import (
    ExtractedPlotThread,
    PlotThreadCategory,
    PlotThreadDetectionResult,
    PlotThreadUrgency,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Pattern matching for plot thread detection
# =============================================================================

# Promise patterns: "promised to", "vowed to", "swore to", "committed to"
_PROMISE_PATTERNS = [
    r"\b(promises?|promised|vowed?|swore?|committed|pledged?|guaranteed?)\s+to\b",
    r"\b(shall\s+(not\s+)?)(\w+)\b",
    r"\b(must\s+(not\s+)?)(\w+)\b",
    r"\b(will\s+(not\s+)?)(\w+)\b",
]

# Threat patterns: "threatened to", "warned that", "lurking", "impending"
_THREAT_PATTERNS = [
    r"\b(threaten(s|ed)?|warn(s|ed)?)\s+(that|to)\b",
    r"\b(lurk(s|ing)?|looms?|impends?|imminent)\b",
    r"\b(danger|peril|threat|risk)\s+(of)\b",
    r"\b(invasion|attack|assault|siege)\s+(is\s+(not\s+)?)?(coming|approaching)\b",
]

# Mystery patterns: "mystery", "puzzle", "unknown", "unanswered", "secret"
_MYSTERY_PATTERNS = [
    r"\b(mystery|puzzle|enigma|riddle|secret)\b",
    r"\b(unknown|unanswered|unsolved|unclear)\b",
    r"\b(who|what|where|when|why|how)\s+(did|does|is|was|were)\b",
    r"\b(discover|investigate|uncover|solve|reveal)\s+(the)?\b",
]

# Consequence patterns: "as a result", "because of", "led to", "caused"
_CONSEQUENCE_PATTERNS = [
    r"\b(as\s+(a\s+)?result|because\s+of|due\s+to)\b",
    r"\b(led\s+to|caused?|resulted\s+in)\b",
    r"\b(consequence|aftermath|repercussion|effect)\b",
]

# Relationship patterns: "ally", "enemy", "friend", "rival", "tension"
_RELATIONSHIP_PATTERNS = [
    r"\b(all(y|ies)|friend(s|ship))\b",
    r"\b(enem(y|ies)|foe(s)?|rival(s)?|opponent(s)?)\b",
    r"\b(tension|conflict|dispute|feud|grudge)\b",
    r"\b(romance|love|hatred|betrayal|loyalty)\b",
]

# World event patterns: "war", "famine", "plague", "revolution", "disaster"
_WORLD_EVENT_PATTERNS = [
    r"\b(war|battle|conflict|invasion)\b",
    r"\b(famine|plague|drought|disaster|catastrophe)\b",
    r"\b(revolution|uprising|rebellion|coup)\b",
    r"\b(coronation|funeral|wedding|festival)\b",
]

# Resolution patterns: "resolved", "solved", "completed", "fulfilled"
_RESOLUTION_PATTERNS = [
    r"\b(resolved|solved|completed|fulfilled)\b",
    r"\b(answered|revealed|discovered|found)\b",
    r"\b(defeated|destroyed|vanquished)\b",
    r"\b(paid off|settled|concluded)\b",
]

# =============================================================================
# PUBLIC API
# =============================================================================


def detect_plot_threads_from_scene(
    scene_text: str,
    scene_id: UUID,
    universe_id: UUID,
    entity_names: Optional[List[str]] = None,
) -> PlotThreadDetectionResult:
    """
    Extract plot threads from scene content.

    Args:
        scene_text: Scene content to analyze.
        scene_id: Scene where threads were detected.
        universe_id: Universe containing the scene.
        entity_names: Entities mentioned in the scene.

    Returns:
        PlotThreadDetectionResult with detected threads.
    """
    result = PlotThreadDetectionResult()

    # Detect promises
    result.threads.extend(_detect_promises(scene_text, scene_id, entity_names))

    # Detect threats
    result.threads.extend(_detect_threats(scene_text, scene_id, entity_names))

    # Detect mysteries
    result.threads.extend(_detect_mysteries(scene_text, scene_id, entity_names))

    # Detect consequences
    result.threads.extend(_detect_consequences(scene_text, scene_id, entity_names))

    # Detect relationships
    result.threads.extend(_detect_relationships(scene_text, scene_id, entity_names))

    # Detect world events
    result.threads.extend(_detect_world_events(scene_text, scene_id, entity_names))

    result.compute_totals()
    return result


def update_thread_status_from_scene(
    scene_id: UUID,
    scene_text: str,
    universe_id: UUID,
    existing_threads: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Update plot thread status based on scene outcomes.

    Args:
        scene_id: Scene being analyzed.
        scene_text: Scene content.
        universe_id: Universe containing the scene.
        existing_threads: Existing plot threads to check for resolution.

    Returns:
        Dict with thread updates (resolved, advanced, abandoned).
    """
    existing_threads = existing_threads or []
    updates = {
        "scene_id": str(scene_id),
        "resolved_threads": [],
        "advanced_threads": [],
        "abandoned_threads": [],
        "new_threads": [],
    }

    # Check for thread resolutions in scene text
    for thread in existing_threads:
        thread_id = thread.get("thread_id")

        if not thread_id:
            continue

        # Check if this thread is resolved in the scene
        if _is_thread_resolved(scene_text, thread):
            updates["resolved_threads"].append(
                {
                    "thread_id": str(thread_id),
                    "title": thread.get("title"),
                    "resolution": "Resolved in scene",
                    "scene_id": str(scene_id),
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        # Check if this thread is advanced in the scene
        elif _is_thread_advanced(scene_text, thread):
            updates["advanced_threads"].append(
                {
                    "thread_id": str(thread_id),
                    "title": thread.get("title"),
                    "progress": "Advanced in scene",
                    "scene_id": str(scene_id),
                    "advanced_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        # Check if this thread is abandoned in the scene
        elif _is_thread_abandoned(scene_text, thread):
            updates["abandoned_threads"].append(
                {
                    "thread_id": str(thread_id),
                    "title": thread.get("title"),
                    "abandonment_reason": "Implied abandonment in scene",
                    "scene_id": str(scene_id),
                    "abandoned_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    return updates


def classify_thread_content(
    text: str,
    max_length: int = 2000,
) -> PlotThreadCategory:
    """
    Classify text into a plot thread category.

    Args:
        text: Text to classify.
        max_length: Maximum text length to analyze.

    Returns:
        PlotThreadCategory for the text.
    """
    text = text[:max_length].lower()

    # Check each category
    if _matches_patterns(text, _PROMISE_PATTERNS):
        return PlotThreadCategory.PROMISE
    if _matches_patterns(text, _THREAT_PATTERNS):
        return PlotThreadCategory.THREAT
    if _matches_patterns(text, _MYSTERY_PATTERNS):
        return PlotThreadCategory.MYSTERY
    if _matches_patterns(text, _CONSEQUENCE_PATTERNS):
        return PlotThreadCategory.CONSEQUENCE
    if _matches_patterns(text, _RELATIONSHIP_PATTERNS):
        return PlotThreadCategory.RELATIONSHIP
    if _matches_patterns(text, _WORLD_EVENT_PATTERNS):
        return PlotThreadCategory.WORLD_EVENT

    # Default to mystery if no clear category
    return PlotThreadCategory.MYSTERY


# =============================================================================
# Private detection functions
# =============================================================================


def _detect_promises(
    text: str,
    scene_id: UUID,
    entity_names: Optional[List[str]] = None,
) -> List[ExtractedPlotThread]:
    """Detect promise threads in text."""
    threads = []
    text_lower = text.lower()

    for pattern in _PROMISE_PATTERNS:
        matches = re.finditer(pattern, text_lower)
        for match in matches:
            # Extract the promise context (100 chars before and after)
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()

            # Determine urgency
            urgency = _determine_urgency(context)

            thread = ExtractedPlotThread(
                title=_extract_thread_title(context, "Promise"),
                description=context,
                category=PlotThreadCategory.PROMISE,
                urgency=urgency,
                entity_names=_extract_entity_names(context, entity_names),
                confidence=0.7,
            )
            threads.append(thread)

    return threads


def _detect_threats(
    text: str,
    scene_id: UUID,
    entity_names: Optional[List[str]] = None,
) -> List[ExtractedPlotThread]:
    """Detect threat threads in text."""
    threads = []
    text_lower = text.lower()

    for pattern in _THREAT_PATTERNS:
        matches = re.finditer(pattern, text_lower)
        for match in matches:
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()

            # Threats are usually urgent
            urgency = _determine_urgency(context, default=PlotThreadUrgency.HIGH)

            thread = ExtractedPlotThread(
                title=_extract_thread_title(context, "Threat"),
                description=context,
                category=PlotThreadCategory.THREAT,
                urgency=urgency,
                entity_names=_extract_entity_names(context, entity_names),
                confidence=0.7,
            )
            threads.append(thread)

    return threads


def _detect_mysteries(
    text: str,
    scene_id: UUID,
    entity_names: Optional[List[str]] = None,
) -> List[ExtractedPlotThread]:
    """Detect mystery threads in text."""
    threads = []
    text_lower = text.lower()

    for pattern in _MYSTERY_PATTERNS:
        matches = re.finditer(pattern, text_lower)
        for match in matches:
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()

            urgency = _determine_urgency(context)

            thread = ExtractedPlotThread(
                title=_extract_thread_title(context, "Mystery"),
                description=context,
                category=PlotThreadCategory.MYSTERY,
                urgency=urgency,
                entity_names=_extract_entity_names(context, entity_names),
                confidence=0.6,
            )
            threads.append(thread)

    return threads


def _detect_consequences(
    text: str,
    scene_id: UUID,
    entity_names: Optional[List[str]] = None,
) -> List[ExtractedPlotThread]:
    """Detect consequence threads in text."""
    threads = []
    text_lower = text.lower()

    for pattern in _CONSEQUENCE_PATTERNS:
        matches = re.finditer(pattern, text_lower)
        for match in matches:
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()

            urgency = _determine_urgency(context, default=PlotThreadUrgency.MEDIUM)

            thread = ExtractedPlotThread(
                title=_extract_thread_title(context, "Consequence"),
                description=context,
                category=PlotThreadCategory.CONSEQUENCE,
                urgency=urgency,
                entity_names=_extract_entity_names(context, entity_names),
                confidence=0.6,
            )
            threads.append(thread)

    return threads


def _detect_relationships(
    text: str,
    scene_id: UUID,
    entity_names: Optional[List[str]] = None,
) -> List[ExtractedPlotThread]:
    """Detect relationship threads in text."""
    threads = []
    text_lower = text.lower()

    for pattern in _RELATIONSHIP_PATTERNS:
        matches = re.finditer(pattern, text_lower)
        for match in matches:
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()

            urgency = _determine_urgency(context, default=PlotThreadUrgency.MEDIUM)

            thread = ExtractedPlotThread(
                title=_extract_thread_title(context, "Relationship"),
                description=context,
                category=PlotThreadCategory.RELATIONSHIP,
                urgency=urgency,
                entity_names=_extract_entity_names(context, entity_names),
                confidence=0.6,
            )
            threads.append(thread)

    return threads


def _detect_world_events(
    text: str,
    scene_id: UUID,
    entity_names: Optional[List[str]] = None,
) -> List[ExtractedPlotThread]:
    """Detect world event threads in text."""
    threads = []
    text_lower = text.lower()

    for pattern in _WORLD_EVENT_PATTERNS:
        matches = re.finditer(pattern, text_lower)
        for match in matches:
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()

            # World events are usually high urgency
            urgency = _determine_urgency(context, default=PlotThreadUrgency.HIGH)

            thread = ExtractedPlotThread(
                title=_extract_thread_title(context, "World Event"),
                description=context,
                category=PlotThreadCategory.WORLD_EVENT,
                urgency=urgency,
                entity_names=_extract_entity_names(context, entity_names),
                confidence=0.7,
            )
            threads.append(thread)

    return threads


# =============================================================================
# Private helper functions
# =============================================================================


def _matches_patterns(text: str, patterns: List[str]) -> bool:
    """Check if text matches any of the given patterns."""
    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False


def _extract_thread_title(context: str, category: str) -> str:
    """Extract a short title from context."""
    # Take the first 50 chars and clean up
    title = context[:50].strip()
    # Remove trailing punctuation
    title = re.sub(r"[.,!?;:]+$", "", title)
    # Add ellipsis if truncated
    if len(context) > 50:
        title += "..."
    return f"{category}: {title}"


def _extract_entity_names(
    context: str,
    known_entities: Optional[List[str]] = None,
) -> List[str]:
    """Extract entity names from context."""
    known_entities = known_entities or []
    context_lower = context.lower()
    return [entity for entity in known_entities if entity.lower() in context_lower]


def _determine_urgency(
    context: str,
    default: PlotThreadUrgency = PlotThreadUrgency.MEDIUM,
) -> PlotThreadUrgency:
    """Determine urgency based on context keywords."""
    context_lower = context.lower()

    high_urgency_keywords = [
        "immediate",
        "urgent",
        "critical",
        "emergency",
        "deadly",
        "imminent",
        "looming",
        "now",
        "today",
        "tonight",
    ]

    low_urgency_keywords = [
        "eventually",
        "someday",
        "one day",
        "in the future",
        "later",
    ]

    for keyword in high_urgency_keywords:
        if keyword in context_lower:
            return PlotThreadUrgency.HIGH

    for keyword in low_urgency_keywords:
        if keyword in context_lower:
            return PlotThreadUrgency.LOW

    return default


def _is_thread_resolved(scene_text: str, thread: Dict[str, Any]) -> bool:
    """Check if a thread is resolved in the scene."""
    thread_title = thread.get("title", "").lower()
    thread_description = thread.get("description", "").lower()
    scene_text_lower = scene_text.lower()

    # Check for resolution patterns
    for pattern in _RESOLUTION_PATTERNS:
        matches = re.finditer(pattern, scene_text_lower)
        for match in matches:
            # Check if the resolution context mentions this thread
            context = scene_text_lower[max(0, match.start() - 50) : match.end() + 50]
            if thread_title in context or any(
                word in context for word in thread_description.split()[:3]
            ):
                return True

    return False


def _is_thread_advanced(scene_text: str, thread: Dict[str, Any]) -> bool:
    """Check if a thread is advanced in the scene."""
    thread_title = thread.get("title", "").lower()
    thread_description = thread.get("description", "").lower()
    scene_text_lower = scene_text.lower()

    # Check if the thread title is mentioned (suggesting it's being addressed)
    if thread_title in scene_text_lower:
        return True

    # Check if key words from thread description appear in scene text
    # This allows for partial match (e.g., "councilor's murder" matching "murder continues")
    key_words = thread_description.split()[:5]  # First 5 words
    for word in key_words:
        # Skip common stop words
        word_clean = re.sub(r"[^\w]", "", word).lower()
        if len(word_clean) > 3 and word_clean in scene_text_lower:
            return True

    return False


def _is_thread_abandoned(scene_text: str, thread: Dict[str, Any]) -> bool:
    """Check if a thread is abandoned in the scene."""
    thread_title = thread.get("title", "").lower()
    scene_text_lower = scene_text.lower()

    abandonment_keywords = [
        "forgot",
        "ignored",
        "dismissed",
        "abandoned",
        "gave up",
        "not important",
        "never mind",
        "forget it",
    ]

    # Check if the thread is mentioned with abandonment keywords
    for keyword in abandonment_keywords:
        if keyword in scene_text_lower and thread_title in scene_text_lower:
            return True

    return False
