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
    get_gliner_client,
)
from monitor_data.tools._shared import call_sync as _call_sync
from monitor_data.tools.perception_tools import PerceptionBackend, RegexBackend, SpacyBackend

log = structlog.get_logger()

# =============================================================================
# SCHEMAS
# =============================================================================


_MAX_LABELS = 64
_MAX_LABEL_LEN = 64


def _bounded_labels(labels: list[str] | None) -> list[str]:
    """Server-side label allowlist bounds: cap count and per-label length."""
    labels = labels or _parse_entity_types()
    if len(labels) > _MAX_LABELS:
        raise ValueError(f"too many labels: {len(labels)} (max {_MAX_LABELS})")
    cleaned = [lbl.strip()[:_MAX_LABEL_LEN] for lbl in labels if lbl.strip()]
    return cleaned[:_MAX_LABELS]


def _bounded_threshold(threshold: float) -> float:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be within [0, 1], got {threshold}")
    return threshold


def _max_text_chars() -> int:
    # GLINER_MAX_LENGTH is a token budget; 4 chars/token is the usual estimate.
    return max(1, settings.gliner_max_length) * 4


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split an oversized text into model-sized windows at paragraph/sentence
    boundaries, so long inputs are processed instead of rejected."""
    if len(text) <= max_chars:
        return [text]
    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            # prefer a paragraph, then sentence, then space boundary
            for sep in ("\n\n", "\n", ". ", " "):
                cut = text.rfind(sep, start + max_chars // 2, end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        windows.append(text[start:end])
        start = end
    return [w for w in windows if w.strip()] or [text[:max_chars]]


def _bounded_text(text: str) -> str:
    if len(text) > _max_text_chars():
        raise ValueError(f"text too long: {len(text)} chars (max {_max_text_chars()})")
    return text


class EntityExtractionRequest:
    """Request for entity extraction from text (bounds enforced server-side)."""

    def __init__(
        self,
        text: str,
        labels: list[str] | None = None,
        threshold: float = 0.5,
    ):
        self.text = _bounded_text(text)
        self.labels = _bounded_labels(labels)
        self.threshold = _bounded_threshold(threshold)


class EntityExtractionResponse:
    """Response containing extracted entities."""

    def __init__(self, entities: list[Entity], text: str, backend: str = "", fallback: bool = False):
        self.entities = entities
        self.text = text
        self.count = len(entities)
        self.backend = backend
        self.fallback = fallback

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "backend": self.backend,
            "fallback": self.fallback,
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
    """Request for batch entity extraction from multiple texts (bounded)."""

    def __init__(
        self,
        texts: list[str],
        labels: list[str] | None = None,
        threshold: float = 0.5,
    ):
        max_batch = max(1, settings.gliner_batch_size)
        if len(texts) > max_batch:
            raise ValueError(f"batch too large: {len(texts)} texts (max {max_batch})")
        self.texts = [_bounded_text(t) for t in texts]
        self.labels = _bounded_labels(labels)
        self.threshold = _bounded_threshold(threshold)


class BatchEntityExtractionResponse:
    """Response containing extracted entities for multiple texts."""

    def __init__(self, results: list[list[Entity]], texts: list[str], backend: str = "", fallback: bool = False):
        self.results = results
        self.texts = texts
        self.count = len(texts)
        self.backend = backend
        self.fallback = fallback

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
            "backend": self.backend,
            "fallback": self.fallback,
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
_gliner_health: bool | None = None  # cached after first probe


def _gliner_ready() -> bool:
    """Probe the GLiNER service once, cache the result, log a warning on fallback."""
    global _gliner_health
    if _gliner_health is None:
        try:
            _gliner_health = bool(_call_sync(get_gliner_client().health_check()))
        except Exception:  # noqa: BLE001  # reason: any failure means "not ready"; we degrade to spaCy
            _gliner_health = False
        if not _gliner_health:
            log.warning(
                "gliner_unavailable_falling_back_to_spacy",
                configured_backend=settings.nlp_backend,
                gliner_url=settings.gliner_url,
            )
    return _gliner_health


def _active_backend() -> tuple[str, bool]:
    """Return (active_backend, fell_back). gliner only when configured AND healthy."""
    if settings.nlp_backend == "spacy":
        return "spacy", False
    if _gliner_ready():
        return "gliner", False
    return "spacy", True


def _reset_nlp_backend_cache() -> None:
    """Reset the cached GLiNER probe. Test helper."""
    global _gliner_health
    _gliner_health = None


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

    threshold = _bounded_threshold(threshold)
    labels = _bounded_labels(labels)
    max_chars = _max_text_chars()

    active, fell_back = _active_backend()
    entities: list[Entity] = []
    # Oversized texts are split into model-sized windows and processed
    # sequentially; entity offsets are shifted back to whole-text coordinates.
    for offset, window in _enumerate_windows(text, max_chars):
        if active == "spacy":
            backend = _get_spacy_backend()
            detected = _call_sync(backend.detect_entities(window))
            entities.extend(
                Entity(
                    text=d.text,
                    label=d.entity_type.value,
                    start=d.start + offset,
                    end=d.end + offset,
                    confidence=d.confidence,
                )
                for d in detected
            )
        else:
            request = EntityExtractionRequest(text=window, labels=labels, threshold=threshold)
            for e in _call_sync(extract_entities(request.text, labels=request.labels, threshold=request.threshold)):
                entities.append(
                    Entity(
                        text=e.text, label=e.label, start=e.start + offset, end=e.end + offset, confidence=e.confidence
                    )
                )
    response = EntityExtractionResponse(entities=entities, text=text, backend=active, fallback=fell_back)

    return response.to_dict()


def _enumerate_windows(text: str, max_chars: int) -> list[tuple[int, str]]:
    """[(offset, window)] covering ``text`` in model-sized pieces."""
    if len(text) <= max_chars:
        return [(0, text)]
    out: list[tuple[int, str]] = []
    start = 0
    for window in _split_text(text, max_chars):
        out.append((start, window))
        start += len(window)
    return out


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

    max_batch = max(1, settings.gliner_batch_size)
    threshold = _bounded_threshold(threshold)
    labels = _bounded_labels(labels)

    active, fell_back = _active_backend()
    all_results: list[list[Entity]] = []
    max_chars = _max_text_chars()
    # Oversized batches are processed in bounded chunks; oversized texts are
    # split into windows with offset-adjusted entities (per-text results stay
    # aligned with the input order).
    for i in range(0, len(texts), max_batch):
        chunk = texts[i : i + max_batch]
        chunk_results: list[list[Entity]] = []
        for t in chunk:
            per_text: list[Entity] = []
            for offset, window in _enumerate_windows(t, max_chars):
                if active == "spacy":
                    backend = _get_spacy_backend()
                    detected = _call_sync(backend.detect_entities(window))
                    per_text.extend(
                        Entity(
                            text=d.text,
                            label=d.entity_type.value,
                            start=d.start + offset,
                            end=d.end + offset,
                            confidence=d.confidence,
                        )
                        for d in detected
                    )
                else:
                    request = EntityExtractionRequest(text=window, labels=labels, threshold=threshold)
                    for e in _call_sync(
                        extract_entities(request.text, labels=request.labels, threshold=request.threshold)
                    ):
                        per_text.append(
                            Entity(
                                text=e.text,
                                label=e.label,
                                start=e.start + offset,
                                end=e.end + offset,
                                confidence=e.confidence,
                            )
                        )
            chunk_results.append(per_text)
        all_results.extend(chunk_results)
    results = all_results
    response = BatchEntityExtractionResponse(results=results, texts=texts, backend=active, fallback=fell_back)

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

    active, fell_back = _active_backend()
    if active == "spacy":
        try:
            backend = _get_spacy_backend()
            # Run a quick entity extraction as health check
            _call_sync(backend.detect_entities("health check test"))
            healthy = True
        except Exception:  # noqa: BLE001  # reason: falls back to unhealthy on failure (in nlp_health_check)
            healthy = False
    else:
        healthy = True  # _gliner_ready() already probed the service
    return {
        "healthy": healthy,
        "backend": active,
        "configured_backend": settings.nlp_backend,
        "fallback": fell_back,
    }


def nlp_active_backend() -> dict[str, Any]:
    """Report which NLP backend is configured vs. actually serving requests.

    Agents call this at extraction time to record provenance on knowledge
    packs (which backend + labels produced the entities).
    """
    active, fell_back = _active_backend()
    return {
        "configured_backend": settings.nlp_backend,
        "active_backend": active,
        "fallback": fell_back,
        "entity_types": _parse_entity_types(),
        "nlp_enabled": settings.nlp_enabled,
    }


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
