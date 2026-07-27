"""
Base Pydantic models and enums for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, datetime, uuid, enum)
CALLED BY: All other schema modules

These are the foundation models used across all schemas in the data layer.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field

logger = logging.getLogger(__name__)


# =============================================================================
# SHARED RESPONSE MIXINS
# =============================================================================


class AuditMixin(BaseModel):
    """Shared timestamp + id fields for response schemas.

    DRY: Avoids duplicating id/created_at/updated_at across 20+ schemas.
    """

    id: UUID
    created_at: datetime
    updated_at: datetime | None = None


# =============================================================================
# HELPERS
# =============================================================================


def _clamp_string(value: Any, *, limit: int) -> Any:
    """Trim overlong extracted text instead of failing the whole ingest."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if len(value) > limit:
        logger.debug("Truncating extracted text from %d to %d characters", len(value), limit)
        return value[:limit]
    return value


def _make_clamped(limit: int) -> Any[[int], int]:
    """Return a BeforeValidator function that clamps a string to *limit* chars."""

    def _validator(value: Any) -> Any:
        return _clamp_string(value, limit=limit)

    return _validator


def _make_clamped_coerce(limit: int) -> Any[[int], int]:
    """Return a BeforeValidator that clamps and converts None to empty string."""

    def _validator(value: Any) -> Any:
        if value is None:
            return ""
        return _clamp_string(value, limit=limit) or ""

    return _validator


Trimmed50 = Annotated[str, BeforeValidator(_make_clamped(50))]
Trimmed100 = Annotated[str, BeforeValidator(_make_clamped(100))]
Trimmed200 = Annotated[str, BeforeValidator(_make_clamped(200))]
Trimmed300 = Annotated[str, BeforeValidator(_make_clamped(300))]
Trimmed500 = Annotated[str, BeforeValidator(_make_clamped(500))]
Trimmed1000 = Annotated[str, BeforeValidator(_make_clamped(1000))]

TrimmedCoerce200 = Annotated[str, BeforeValidator(_make_clamped_coerce(200))]
TrimmedCoerce500 = Annotated[str, BeforeValidator(_make_clamped_coerce(500))]
TrimmedCoerce1000 = Annotated[str, BeforeValidator(_make_clamped_coerce(1000))]


# =============================================================================
# ENUMS
# =============================================================================


class CanonLevel(StrEnum):
    """How established a fact is in the shared world truth."""

    PROPOSED = "proposed"  # Candidate for canon, not yet accepted
    CANON = "canon"  # Accepted world truth
    RUMOR = "rumor"  # Unverified information (IC)
    CHARACTER_BELIEF = "character_belief"  # What an NPC believes to be true
    PLAYER_KNOWLEDGE = "player_knowledge"  # Meta-knowledge not known to characters
    RETCONNED = "retconned"  # Explicitly replaced or invalidated fact
    SUPERSEDED = "superseded"  # Replaced by a more recent fact version


class KnowledgeScope(StrEnum):
    """Who holds this information."""

    WORLD = "world"  # Known to almost everyone
    CHARACTER = "character"  # Private knowledge of a specific character
    PLAYER = "player"  # Known to players but not their characters (meta)
    FACTION = "faction"  # Secret known only to an organization
    RUMOR = "rumor"  # Fragmented information circulating socially


class AxiomAuthority(StrEnum):
    """Source of truth for an axiom."""

    PHYSICS = "physics"  # Hard rule of reality (magic is physics here)
    SOCIETY = "society"  # Fundamental social truth
    METAPHYSICS = "metaphysics"  # Divine/Cosmic truth
    GENRE = "genre"  # Rule of the narrative style


class Authority(StrEnum):
    """Authority level of a change.

    DETERMINES: Which changes can overwrite others.
    A change from a SOURCE can only be overridden by GM or SYSTEM.
    A change from GM can only be overridden by SYSTEM or higher GM declaration.
    """

    SOURCE = "source"  # Extracted from rulebooks/material
    GM = "gm"  # Declared by the gamemaster
    SYSTEM = "system"  # Fixed rule enforced by the software
    PLAYER = "player"  # Proposed by player, needs GM approval


class EntityType(StrEnum):
    """Entity classification."""

    CHARACTER = "character"
    FACTION = "faction"
    LOCATION = "location"
    OBJECT = "object"
    CONCEPT = "concept"
    ORGANIZATION = "organization"


class EntityClass(StrEnum):
    """Axiomatic vs Concrete entity classification."""

    AXIOMATICA = "EntityArchetype"  # Templates: Elf, Wizard, Sword
    CONCRETA = "EntityInstance"  # Individuals: Legolas, Gandalf, Narsil


class SimulationScope(StrEnum):
    """Impact of an event or fact."""

    LOCAL = "local"  # Affects individuals
    REGIONAL = "regional"  # Affects a location
    GLOBAL = "global"  # Affects the whole world
    COSMIC = "cosmic"  # Affects the multiverse


class IngestionStatus(StrEnum):
    """Life cycle of an ingestion job."""

    PENDING = "pending"
    RUNNING = "running"
    INDEXING = "indexing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    FAILED_NON_RETRYABLE = "failed_non_retryable"
    BLOCKED_PROVIDER = "blocked_provider"
    BACKING_OFF = "backing_off"
    CANCELLED = "cancelled"
    KILLED = "killed"
    FLAGGED_DUPLICATE = "flagged_duplicate"


class SourceCanonLevel(StrEnum):
    """Canonization status for Source nodes only.

    Sources use 'authoritative' instead of 'retconned' because
    source documents themselves aren't revised—only facts derived
    from them can be retconned.
    """

    PROPOSED = "proposed"
    CANON = "canon"
    AUTHORITATIVE = "authoritative"


class StoryType(StrEnum):
    """Narrative scope of a story."""

    CAMPAIGN = "campaign"  # Full campaign arc
    ARC = "arc"  # Story arc within a campaign
    EPISODE = "episode"  # Single episode/session
    ONE_SHOT = "one_shot"  # Standalone one-shot adventure


class StoryStatus(StrEnum):
    """Lifecycle status of a story.

    Lifecycle: PLANNED -> ACTIVE -> COMPLETED -> ARCHIVED.
    ABANDONED is an off-ramp from any non-terminal state.
    """

    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    ARCHIVED = "archived"


def transition_story_status(current: StoryStatus, target: StoryStatus) -> bool:
    """Validate a status transition.

    Returns True if ``current`` may legally transition to ``target``.

    Allowed transitions:
        PLANNED  -> ACTIVE, ABANDONED
        ACTIVE   -> COMPLETED, ABANDONED
        COMPLETED -> ARCHIVED
        ABANDONED -> ARCHIVED
    """
    if not isinstance(current, StoryStatus) or not isinstance(target, StoryStatus):
        return False
    if current == target:
        return False
    allowed = {
        StoryStatus.PLANNED: {StoryStatus.ACTIVE, StoryStatus.ABANDONED},
        StoryStatus.ACTIVE: {StoryStatus.COMPLETED, StoryStatus.ABANDONED},
        StoryStatus.COMPLETED: {StoryStatus.ARCHIVED},
        StoryStatus.ABANDONED: {StoryStatus.ARCHIVED},
    }
    return target in allowed.get(current, set())


class SceneStatus(StrEnum):
    """Lifecycle status of a scene."""

    ACTIVE = "active"
    FINALIZING = "finalizing"
    COMPLETED = "completed"


class ProposalStatus(StrEnum):
    """Evaluation status of a proposed change."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProposalType(StrEnum):
    """Category of a proposed change."""

    FACT = "fact"  # New or modified fact
    ENTITY = "entity"  # New or modified entity
    RELATIONSHIP = "relationship"  # New or modified relationship
    STATE_CHANGE = "state_change"  # Entity state tag change
    EVENT = "event"  # New or modified event
    MECHANIC = "mechanic"  # Rules/mechanic change


class PromotionIntent(StrEnum):
    """Entity-promotion signal tagged inline by the Narrator (see
    NarratorSignature's [Name](entity:anchor|flavor) convention).

    Distinct from ProposalType (what kind of change this is) — this is
    specifically about whether an ENTITY proposal deserves permanent
    Neo4j placement. See docs/2_architecture/data_model_workflow.md.
    """

    ANCHOR = "anchor"  # Structural weight — auto-promote at scene end
    FLAVOR = "flavor"  # Disposable — promoted only past the interaction threshold


class Speaker(StrEnum):
    """Who is speaking in a turn."""

    USER = "user"  # The human player
    GM = "gm"  # The Game Master / narrator
    ENTITY = "entity"  # An NPC or other in-world entity


class PartyStatus(StrEnum):
    """Adventuring party status."""

    TRAVELING = "traveling"
    CAMPING = "camping"
    IN_SCENE = "in_scene"
    COMBAT = "combat"
    SPLIT = "split"
    RESTING = "resting"


class CombatStatus(StrEnum):
    """Combat encounter lifecycle."""

    INITIALIZING = "initializing"
    INITIATIVE = "initiative"
    ACTIVE = "active"
    PAUSED = "paused"
    RESOLVED = "resolved"


class CombatSide(StrEnum):
    """Which side a combatant belongs to."""

    PC = "pc"
    ALLY = "ally"
    ENEMY = "enemy"
    NEUTRAL = "neutral"


class DetailLevel(StrEnum):
    """How detailed/elaborated an entity profile is."""

    STUB = "stub"  # Name + type only
    SKETCHED = "sketched"  # Basic description + a few traits
    DETAILED = "detailed"  # Full backstory, relationships, motivations
    ELABORATED = "elaborated"  # Richly developed through play


class AltWorldType(StrEnum):
    """Classification for alternate universe branches."""

    MAIN = "main"  # Primary/canonical timeline
    FORK = "fork"  # Divergent timeline
    WHAT_IF = "what_if"  # Hypothetical scenario
    DREAM = "dream"  # Dream/vision world
    SIMULATION = "simulation"  # Simulated reality
    SPLIT = "split"  # Splinter universe
    MERGE = "merge"  # Merged universe


class TemporalMode(StrEnum):
    """Temporal framing for a scene."""

    PRESENT = "present"  # Current timeline
    FLASHBACK = "flashback"  # Past event
    FLASH_FORWARD = "flash_forward"  # Future glimpse
    DREAM = "dream"  # Dream/vision sequence


class EmotionalRelationType(StrEnum):
    """Emotional relationship types — how a character FEELS about another.

    Directional: A LOVES B does not imply B LOVES A.
    These are separate Neo4j edge types from structural relationships.
    """

    LOVES = "LOVES"
    HATES = "HATES"
    FEARS = "FEARS"
    TRUSTS = "TRUSTS"
    DISTRUSTS = "DISTRUSTS"
    ADMIRES = "ADMIRES"
    ENVIES = "ENVIES"
    LOYAL_TO = "LOYAL_TO"
    INDEBTED_TO = "INDEBTED_TO"
    RIVALS = "RIVALS"
    PROTECTIVE_OF = "PROTECTIVE_OF"
    MENTORS = "MENTORS"
    GRIEVES = "GRIEVES"


class DialogueStatus(StrEnum):
    """Lifecycle status of an NPC dialogue."""

    ACTIVE = "active"
    ENDING = "ending"
    ENDED = "ended"


class NarrativeStyle(StrEnum):
    """Prose style for generated narratives."""

    LITERARY = "literary"  # Third-person prose fiction
    DRAMATIC = "dramatic"  # Screenplay / stage directions
    SUMMARY = "summary"  # Bullet-point factual recap
    LOG = "log"  # Raw chronological event list with roll outcomes


class ExtractionStatus(StrEnum):
    """Life cycle of knowledge extraction from a source."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionStatus(StrEnum):
    """Lifecycle status of a play session."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class KnowledgeTreeType(StrEnum):
    """Mutability mode for a multiverse knowledge tree."""

    STATIC = "static"  # Locked setting data (from sourcebook)
    DYNAMIC = "dynamic"  # Changes during play
    TEMPLATE = "template"  # Reusable blueprint (not playable directly)


class SourcePriority(StrEnum):
    """Priority/precedence level of a source document."""

    CORE = "core"  # Core rulebook
    SUPPLEMENT = "supplement"  # Official supplement
    ADVENTURE = "adventure"  # Adventure module
    FAN = "fan"  # Fan/homebrew content
    CUSTOM = "custom"  # Custom GM content


class HistoricalEventScope(StrEnum):
    """Geographic/narrative scope of a lore event."""

    COSMIC = "cosmic"  # Affects the multiverse
    GLOBAL = "global"  # Affects the whole world
    REGIONAL = "regional"  # Affects a region
    LOCAL = "local"  # Affects a city or smaller
    PERSONAL = "personal"  # Affects individual(s)


class LoreEventStatus(StrEnum):
    """Resolution status of a setting lore event."""

    CLOSED = "closed"  # Fully resolved in the setting
    OPEN = "open"  # Ongoing or future in the timeline


class SourceType(StrEnum):
    """Type of source document."""

    MANUAL = "manual"  # Human-curated / manually created
    RULEBOOK = "rulebook"  # RPG rulebook / core rules
    LORE = "lore"  # Setting / lore book
    SESSION = "session"  # Session transcript / notes
    SUPPLEMENT = "supplement"  # Official supplement
    ADVENTURE = "adventure"  # Adventure module


class NarrativeSourceType(StrEnum):
    """What was narrated in a generated narrative."""

    SESSION = "session"  # Covers an entire play session
    SCENE = "scene"  # Covers a single scene
    STORY = "story"  # Covers the whole story arc


class BeatStatus(StrEnum):
    """Lifecycle status of a story outline beat."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class PlotThreadType(StrEnum):
    """Category of a narrative plot thread."""

    MAIN = "main"
    SUBPLOT = "subplot"
    CHARACTER = "character"
    BACKGROUND = "background"
    MYSTERY = "mystery"


class PlotThreadStatus(StrEnum):
    """Lifecycle status of a plot thread."""

    OPEN = "open"
    ACTIVE = "active"
    ADVANCED = "advanced"
    RESOLVED = "resolved"
    CLOSED = "closed"
    ABANDONED = "abandoned"


class StoryStructureType(StrEnum):
    """Overall structural shape of a story."""

    LINEAR = "linear"
    BRANCHING = "branching"
    EPISODIC = "episodic"
    MYSTERY = "mystery"


class ArcTemplate(StrEnum):
    """Predefined story arc template."""

    THREE_ACT = "three_act"
    FIVE_ACT = "five_act"
    HEROES_JOURNEY = "heroes_journey"
    MYSTERY = "mystery"
    CUSTOM = "custom"


class ThreadPriority(StrEnum):
    """Priority of a plot thread relative to others."""

    MAIN = "main"
    SECONDARY = "secondary"
    MINOR = "minor"
    TERTIARY = "tertiary"


class ThreadUrgency(StrEnum):
    """Urgency level of a plot thread."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClueVisibility(StrEnum):
    """How visible a clue is to players."""

    HIDDEN = "hidden"
    DISCOVERABLE = "discoverable"
    DISCOVERED = "discovered"
    REVEALED = "revealed"


class PayoffStatus(StrEnum):
    """Whether a plot thread's payoff has been delivered."""

    SETUP_ONLY = "setup_only"
    FORESHADOWED = "foreshadowed"
    PAYOFF_DELIVERED = "payoff_delivered"


# =============================================================================
# BASE MODELS
# =============================================================================


class CanonicalMetadata(BaseModel):
    """Common metadata fields for canonical (Neo4j-backed) entities.

    Attached to every canonical node to track provenance and confidence.
    """

    canon_level: CanonLevel = Field(
        default=CanonLevel.CANON,
        description="How established this fact is in the shared world truth",
    )
    authority: Authority = Field(
        default=Authority.SYSTEM,
        description="Who asserted this data",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0)",
    )
    created_at: datetime | None = Field(None, description="When this was created")
    updated_at: datetime | None = Field(None, description="When this was last modified")


class BaseResponse(BaseModel):
    """Minimal base for all response schemas.

    Every API response inherits from this to ensure consistent shape.
    Concrete response schemas add their own fields on top.
    """

    model_config = {"from_attributes": True}


# =============================================================================
# EVIDENCE TRACKING
# Compact evidence pointers used by extracted items and profiles.
# Every canonical fact MUST have evidence_refs (per CLAUDE.md).
# =============================================================================


class ProfileEvidenceRef(BaseModel):
    """Compact evidence pointer backing an extracted or inferred field."""

    ref: Trimmed300 = Field(max_length=300, description="Human-readable page/section/message reference")
    section_path: Trimmed300 | None = Field(None, max_length=300)
    page_hint: int | None = Field(None, ge=1)
    note: Trimmed300 | None = Field(None, max_length=300)
