"""
NLP / GLiNER MCP Tools for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

These tools expose Named Entity Recognition (NER) operations via the MCP server.
GLiNER provides zero-shot NER capabilities for extracting entities from text.
"""

from typing import Any

import structlog

from monitor_data.config import settings
from monitor_data.db.gliner import (
    Entity,
    extract_entities,
    extract_entities_batch,
    get_gliner_client,
)
from monitor_data.tools._shared import call_sync as _call_sync
from monitor_data.tools.perception_tools import PerceptionBackend, RegexBackend, SpacyBackend

log = structlog.get_logger()

# =============================================================================
# SCHEMAS
# =============================================================================


class EntityExtractionRequest:
    """Request for entity extraction from text."""

    def __init__(
        self,
        text: str,
        labels: list[str] | None = None,
        threshold: float = 0.5,
    ):
        self.text = text
        self.labels = labels or _parse_entity_types()
        self.threshold = threshold


class EntityExtractionResponse:
    """Response containing extracted entities."""

    def __init__(self, entities: list[Entity], text: str):
        self.entities = entities
        self.text = text
        self.count = len(entities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "entities": [
                e.to_dict()
                if hasattr(e, "to_dict")
                else {
                    "text": e.text,
                    "label": e.label,
                    "start": e.start,
                    "end": e.end,
                    "confidence": e.confidence,
                }
                for e in self.entities
            ],
            "count": self.count,
        }


class BatchEntityExtractionRequest:
    """Request for batch entity extraction from multiple texts."""

    def __init__(
        self,
        texts: list[str],
        labels: list[str] | None = None,
        threshold: float = 0.5,
    ):
        self.texts = texts
        self.labels = labels or _parse_entity_types()
        self.threshold = threshold


class BatchEntityExtractionResponse:
    """Response containing extracted entities for multiple texts."""

    def __init__(self, results: list[list[Entity]], texts: list[str]):
        self.results = results
        self.texts = texts
        self.count = len(texts)

    def to_dict(self) -> dict[str, Any]:
        def entity_to_dict(e: Any) -> dict[str, Any]:
            if hasattr(e, "to_dict"):
                return dict(e.to_dict())
            return {
                "text": e.text,
                "label": e.label,
                "start": e.start,
                "end": e.end,
                "confidence": e.confidence,
            }

        return {
            "texts": self.texts,
            "results": [[entity_to_dict(e) for e in entities] for entities in self.results],
            "count": self.count,
        }


class NLPHealthCheckResponse:
    """Response for NLP service health check."""

    def __init__(self, healthy: bool, backend: str = "gliner"):
        self.healthy = healthy
        self.backend = backend

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "backend": self.backend,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _parse_entity_types() -> list[str]:
    """Parse ENTITY_TYPES from settings into a list."""
    if not settings.entity_types:
        return []
    return [t.strip() for t in settings.entity_types.split(",") if t.strip()]


def _ensure_nlp_enabled() -> None:
    """Raise an error if NLP is not enabled."""
    if not settings.nlp_enabled:
        raise ValueError("NLP is not enabled. Set NLP_ENABLED=true in your environment configuration.")


# =============================================================================
# BACKEND DISPATCH
# =============================================================================


_spacy_backend: PerceptionBackend | None = None


def _get_spacy_backend() -> PerceptionBackend:
    """Lazily create a spaCy backend instance.

    Falls back to the dependency-free RegexBackend when spaCy or its model is
    unavailable (e.g. slim containers), so NLP tools degrade instead of crashing.
    """
    global _spacy_backend
    if _spacy_backend is None:
        try:
            _spacy_backend = SpacyBackend()
        except (ImportError, OSError) as exc:
            log.warning("spacy_backend_unavailable_falling_back_to_regex", error=str(exc))
            _spacy_backend = RegexBackend()
    return _spacy_backend


def _detected_to_entity(de: Any) -> Entity:
    """Convert a DetectedEntity (perception) to an Entity (gliner schema)."""
    return Entity(
        text=de.text,
        label=de.entity_type.value,
        start=de.start,
        end=de.end,
        confidence=de.confidence,
    )


# =============================================================================
# MCP TOOLS
# =============================================================================


def nlp_extract_entities(
    text: str,
    labels: list[str] | None = None,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """
    Extract named entities from text using GLiNER NER.

    Args:
        text: The input text to extract entities from
        labels: Optional list of entity types to detect (e.g., ["person", "location"])
                If not provided, uses ENTITY_TYPES from settings
        threshold: Confidence threshold for entity detection (0.0 to 1.0)

    Returns:
        Dict containing:
        - text: Original text
        - entities: List of extracted entities with text, label, score, start, end
        - count: Number of entities found

    Example:
        >>> result = nlp_extract_entities("John lives in New York.")
        >>> result['entities'][0]['text']  # 'John'
        >>> result['entities'][0]['label']  # 'person'
    """
    _ensure_nlp_enabled()

    if not text or not text.strip():
        return EntityExtractionResponse(entities=[], text=text).to_dict()

    if settings.nlp_backend == "spacy":
        backend = _get_spacy_backend()
        detected = _call_sync(backend.detect_entities(text))
        entities = [_detected_to_entity(d) for d in detected]
    else:
        request = EntityExtractionRequest(text=text, labels=labels, threshold=threshold)
        entities = _call_sync(extract_entities(request.text, labels=request.labels, threshold=request.threshold))
    response = EntityExtractionResponse(entities=entities, text=text)

    return response.to_dict()


def nlp_extract_entities_batch(
    texts: list[str],
    labels: list[str] | None = None,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """
    Extract named entities from multiple texts in batch.

    Args:
        texts: List of input texts to extract entities from
        labels: Optional list of entity types to detect
                If not provided, uses ENTITY_TYPES from settings
        threshold: Confidence threshold for entity detection (0.0 to 1.0)

    Returns:
        Dict containing:
        - texts: Original texts
        - results: List of entity lists, one per input text
        - count: Number of texts processed

    Example:
        >>> result = nlp_extract_entities_batch(["John lives in NYC", "Paris is beautiful"])
        >>> result['results'][0][0]['text']  # 'John'
        >>> result['results'][1][0]['text']  # 'Paris'
    """
    _ensure_nlp_enabled()

    if not texts:
        return BatchEntityExtractionResponse(results=[], texts=[]).to_dict()

    if settings.nlp_backend == "spacy":
        backend = _get_spacy_backend()
        all_results: list[list[Entity]] = []
        for t in texts:
            detected = _call_sync(backend.detect_entities(t))
            all_results.append([_detected_to_entity(d) for d in detected])
        results = all_results
    else:
        request = BatchEntityExtractionRequest(texts=texts, labels=labels, threshold=threshold)
        results = _call_sync(extract_entities_batch(request.texts, labels=request.labels, threshold=request.threshold))
    response = BatchEntityExtractionResponse(results=results, texts=texts)

    return response.to_dict()


def nlp_health_check() -> dict[str, Any]:
    """
    Check if the NLP service (GLiNER) is healthy and responsive.

    Returns:
        Dict containing:
        - healthy: Boolean indicating if service is responsive
        - backend: Name of the NLP backend (e.g., "gliner")

    Example:
        >>> result = nlp_health_check()
        >>> result['healthy']  # True if GLiNER is running
    """
    if not settings.nlp_enabled:
        return NLPHealthCheckResponse(healthy=False, backend=settings.nlp_backend).to_dict()

    if settings.nlp_backend == "spacy":
        try:
            backend = _get_spacy_backend()
            # Run a quick entity extraction as health check
            _call_sync(backend.detect_entities("health check test"))
            return NLPHealthCheckResponse(healthy=True, backend=settings.nlp_backend).to_dict()
        except Exception:
            return NLPHealthCheckResponse(healthy=False, backend=settings.nlp_backend).to_dict()

    try:
        gliner = get_gliner_client()
        healthy = _call_sync(gliner.health_check())
        return NLPHealthCheckResponse(healthy=healthy, backend=settings.nlp_backend).to_dict()
    except Exception:
        return NLPHealthCheckResponse(healthy=False, backend=settings.nlp_backend).to_dict()


def nlp_get_supported_entity_types() -> dict[str, Any]:
    """
    Get the list of supported entity types from configuration.

    Returns:
        Dict containing:
        - entity_types: List of configured entity types
        - count: Number of entity types

    Example:
        >>> result = nlp_get_supported_entity_types()
        >>> result['entity_types']  # ['person', 'location', 'organization', ...]
    """
    entity_types = _parse_entity_types()
    return {
        "entity_types": entity_types,
        "count": len(entity_types),
    }
