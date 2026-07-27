"""
Pydantic schemas for the Perception Layer — fast entity detection.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, enum)
CALLED BY: perception_tools.py

These schemas define the data contracts for the perception pipeline:
a lightweight entity detector that runs BEFORE the agent loop to
pre-filter context, route inputs, and flag novel entities.

Note
----
Intent classification used to live here too, but it required keyword
tables that couldn't tell ``I swing`` from ``I swing the conversation``.
It was later demoted to a semantic classifier and finally removed: the
GMAgent LLM now emits ``intent_type`` directly. :class:`IntentType` is the
enum in :mod:`monitor_agents.gm_awareness`.

Design note
-----------
The perception layer is intentionally disconnected from the rest of
MONITOR.  It does NOT register MCP tools or talk to Neo4j.  It is a
pure-inference module that can be used standalone or integrated later
as a pre-processing step in the scene loop.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# =============================================================================
# ENUMS
# =============================================================================


class DetectedEntityType(StrEnum):
    """Entity types the perception layer can detect."""

    CHARACTER = "character"
    LOCATION = "location"
    OBJECT = "object"
    FACTION = "faction"
    SPELL = "spell"
    ACTION = "action"
    CONCEPT = "concept"


class DetectionBackend(StrEnum):
    """Available perception backends.

    - ``regex``: Pure Python regex + heuristics (zero dependencies).
    - ``spacy``: spaCy NER pipeline (requires ``spacy`` + model).
    - ``gliner``: GLiNER zero-shot NER (requires ``gliner`` package).
    """

    REGEX = "regex"
    SPACY = "spacy"
    GLINER = "gliner"


# =============================================================================
# DETECTED ENTITY
# =============================================================================


class DetectedEntity(BaseModel):
    """A single entity detected by the perception layer."""

    text: str = Field(..., description="Raw text span that matched")
    entity_type: DetectedEntityType = Field(..., description="Classification of the entity")
    start: int = Field(..., description="Start character offset in input")
    end: int = Field(..., description="End character offset in input")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Detection confidence (1.0 for regex, <1.0 for ML)",
    )
    is_known: bool | None = Field(
        default=None,
        description="Whether this entity is already in the knowledge graph",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Extra info (e.g. {'source': 'capitalized_pattern'})",
    )


# =============================================================================
# PERCEPTION INPUT / OUTPUT
# =============================================================================


class PerceptionInput(BaseModel):
    """Input to the perception layer."""

    text: str = Field(..., min_length=1, description="Raw player / GM input")
    known_entities: list[str] | None = Field(
        default=None,
        description="Entity names already in the knowledge graph (for novelty detection)",
    )
    session_id: str | None = Field(default=None, description="Session ID for caching")


class PerceptionOutput(BaseModel):
    """Full output of the perception pipeline (entity detection only)."""

    entities: list[DetectedEntity] = Field(default_factory=list, description="All detected entities")
    novel_entities: list[DetectedEntity] = Field(
        default_factory=list,
        description="Entities NOT found in known_entities",
    )
    processing_time_ms: float = Field(default=0.0, description="Processing time in milliseconds")
    backend: DetectionBackend = Field(default=DetectionBackend.REGEX, description="Which backend was used")
