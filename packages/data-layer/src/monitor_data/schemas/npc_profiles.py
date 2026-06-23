"""
Pydantic schemas for NPC Profile operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime)
CALLED BY: mongodb_tools.py

NPCProfile is the character's psychological backbone — separate from:
  - character_memories (what the NPC remembers — subjective, episodic)
  - character_sheets   (mechanical stats — HP, STR, spell slots)
  - EntityInstance     (canonical identity in Neo4j)

An NPCProfile contains what a good GM keeps on a notecard:
  - Personality traits, values, fears, desires
  - Speech patterns, catchphrases, mannerisms
  - Emotional tendencies (how quickly they anger, trust, etc.)
  - Preferences (what they love/hate)
  - Behavioral triggers (hidden reactions to specific topics)
  - GM-only secrets (the NPC IS the assassin, etc.)

This profile is the primary input for NPC dialogue sessions (npc_dialogues).
The detail_level on EntityInstance tracks how much of this has been filled in.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# SUB-MODELS
# =============================================================================


class EmotionalTendency(BaseModel):
    """A character's baseline tendency for a specific emotion.

    Combined with intensity: slow to anger (volatility=0.1) vs hot-headed (0.9).
    """

    emotion: str = Field(
        max_length=50,
        description="Emotion name: anger, joy, fear, disgust, trust, sadness, surprise",
    )
    baseline: float = Field(
        ge=-1.0,
        le=1.0,
        description="Resting level: -1=repressed, 0=neutral, +1=expressive",
    )
    volatility: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How quickly this emotion surges (0=stoic, 1=volatile)",
    )


class CharacterPreference(BaseModel):
    """Something a character likes, loves, or hates."""

    category: str = Field(
        max_length=50,
        description="Category: food, people, places, activities, ideas, objects",
    )
    item: str = Field(max_length=200, description="The specific thing")
    valence: float = Field(
        ge=-1.0,
        le=1.0,
        description="-1.0=despise, 0=neutral, +1.0=love",
    )
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Why they feel this way (backstory note)",
    )


class BehavioralTrigger(BaseModel):
    """A topic, person, or situation that triggers a specific behavioral reaction.

    Used by the NPC dialogue engine to override default behavior.
    Example: {'condition': 'asked about the thieves guild', 'reaction': 'becomes evasive and nervous'}
    """

    condition: str = Field(
        max_length=500,
        description="When this is triggered (topic, action, presence of entity, etc.)",
    )
    reaction: str = Field(
        max_length=500,
        description="How the NPC reacts (emotion, action, dialogue shift)",
    )
    intensity: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="How strongly this trigger fires",
    )
    is_hidden: bool = Field(
        default=True,
        description="If True, never hint at this trigger in narration — GM-only",
    )


# =============================================================================
# NPC PROFILE CRUD SCHEMAS
# =============================================================================


class NPCProfileCreate(BaseModel):
    """Request to create an NPCProfile document.

    One profile per entity (EntityInstance). If a profile already exists,
    use NPCProfileUpdate to enrich it as the player interacts with the NPC.
    """

    entity_id: UUID = Field(description="References Neo4j EntityInstance")
    # Personality dimensions (Big Five or custom labels — system agnostic)
    traits: Dict[str, float] = Field(
        default_factory=dict,
        description="Trait-name to score map (e.g., {'openness': 0.8, 'conscientiousness': 0.3})",
    )
    values: List[str] = Field(
        default_factory=list,
        description="Core values (e.g., ['honor', 'family', 'freedom'])",
    )
    fears: List[str] = Field(
        default_factory=list,
        description="What this character fears (e.g., ['betrayal', 'death', 'chaos'])",
    )
    desires: List[str] = Field(
        default_factory=list,
        description="What this character wants (e.g., ['recognition', 'revenge', 'peace'])",
    )
    # Voice and mannerism
    speech_style: Optional[str] = Field(
        None,
        max_length=200,
        description="How they speak (e.g., 'formal and verbose', 'terse military clipped')",
    )
    catchphrases: List[str] = Field(
        default_factory=list,
        description="Phrases this character uses frequently",
    )
    mannerisms: List[str] = Field(
        default_factory=list,
        description="Physical/behavioral tics (e.g., 'tugs ear when lying', 'never makes eye contact')",
    )
    # Emotional model
    emotional_tendencies: List[EmotionalTendency] = Field(default_factory=list)
    preferences: List[CharacterPreference] = Field(default_factory=list)
    # Behavioral triggers (hidden reactions)
    triggers: List[BehavioralTrigger] = Field(default_factory=list)
    # GM-only secrets (never exposed to player, only used in system reasoning)
    secrets: List[str] = Field(
        default_factory=list,
        description="GM-only facts about this NPC (hidden motivations, true identity, etc.)",
    )
    gm_notes: Optional[str] = Field(
        None,
        max_length=5000,
        description="Free-form GM notes about this NPC",
    )
    # Current emotional state (updated during play)
    current_emotional_state: Optional[str] = Field(
        None,
        max_length=200,
        description="NPC's current dominant emotion at this moment in the story",
    )
    relationship_states: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-entity social stance snapshots keyed by target entity_id. "
            "Used to remember trust/hostility drift across conversations."
        ),
    )


class NPCProfileUpdate(BaseModel):
    """Request to update/enrich an NPCProfile.

    All fields optional — only provided values overwrite existing ones.
    Lists are fully replaced (not merged) unless noted.
    """

    traits: Optional[Dict[str, float]] = None
    values: Optional[List[str]] = None
    fears: Optional[List[str]] = None
    desires: Optional[List[str]] = None
    speech_style: Optional[str] = Field(None, max_length=200)
    catchphrases: Optional[List[str]] = None
    mannerisms: Optional[List[str]] = None
    emotional_tendencies: Optional[List[EmotionalTendency]] = None
    preferences: Optional[List[CharacterPreference]] = None
    triggers: Optional[List[BehavioralTrigger]] = None
    secrets: Optional[List[str]] = None
    gm_notes: Optional[str] = Field(None, max_length=5000)
    current_emotional_state: Optional[str] = Field(None, max_length=200)
    relationship_states: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="Partial or full relationship-state map keyed by target entity_id",
    )
    # Single-item append helpers (for in-session updates)
    add_preference: Optional[CharacterPreference] = Field(
        None, description="Append a single preference (convenience field)"
    )
    add_trigger: Optional[BehavioralTrigger] = Field(
        None, description="Append a single trigger (convenience field)"
    )
    add_secret: Optional[str] = Field(
        None, max_length=500, description="Append a single secret (convenience field)"
    )


class NPCProfileResponse(BaseModel):
    """Response with NPCProfile data."""

    profile_id: UUID
    entity_id: UUID
    traits: Dict[str, float]
    values: List[str]
    fears: List[str]
    desires: List[str]
    speech_style: Optional[str] = None
    catchphrases: List[str]
    mannerisms: List[str]
    emotional_tendencies: List[EmotionalTendency]
    preferences: List[CharacterPreference]
    triggers: List[BehavioralTrigger]
    secrets: List[str]
    gm_notes: Optional[str] = None
    current_emotional_state: Optional[str] = None
    relationship_states: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
