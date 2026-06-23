# MONITOR Validation Schemas

*Pydantic models for data validation across the MONITOR system.*

> **Note (April 2026):** This document predates the ingestion revamp. The following schemas are implemented in code but not yet documented here:
> - **Game system mechanics:** `TrackDefinition`, `ThresholdEffect`, `TieredAbilitySystem`, `AbilityTier`, `AdvantageDefinition`, `ResolutionMechanic`, `SuccessDegree`, `DamageModel`, `DamageType`, `ConditionDefinition`, `ActionEconomy`, `ActionType`, `AdvancementModel`, `AdvancementCurrency`, `AdvancementTarget`, `RecoveryModel`, `RecoveryEvent` — see `packages/data-layer/src/monitor_data/schemas/game_systems.py`
> - **Ingestion artifacts:** `ChunkSummaryArtifact`, `SectionSummaryArtifact`, `SourceMindscapeArtifact`, `SectionBlock` — see `knowledge_packs.py` and `ingest_tools.py`
> - **Ingestion structure:** `SectionCategorizationSignature`, `SectionSummarySignature`, `SourceMindscapeSynthesisSignature` — see `packages/agents/src/monitor_agents/prompts/analyzer.py`
>
> For the authoritative schema definitions, trust the Pydantic models in code.

---

## Overview

This document defines **Pydantic models** for all data structures in MONITOR. These schemas:

1. **Validate** API requests and responses
2. **Type-check** data at runtime
3. **Document** data structures with examples
4. **Generate** OpenAPI/JSON Schema for MCP tools

**Key principle:** All data crossing layer boundaries must be validated.

---

## 1. Base Models

### 1.1 Common Enums

```python
from enum import Enum
from typing import Literal

class CanonLevel(str, Enum):
    """Canonization status for most canonical nodes."""
    PROPOSED = "proposed"
    CANON = "canon"
    RETCONNED = "retconned"

class SourceCanonLevel(str, Enum):
    """Canonization status for Source nodes only.

    Sources use 'authoritative' instead of 'retconned' because
    source documents themselves aren't revised—only facts derived
    from them can be retconned.
    """
    PROPOSED = "proposed"
    CANON = "canon"
    AUTHORITATIVE = "authoritative"

class Authority(str, Enum):
    """Who asserted this data (full set for Facts, Events, Entities)."""
    SOURCE = "source"
    GM = "gm"
    PLAYER = "player"
    SYSTEM = "system"

class AxiomAuthority(str, Enum):
    """Authority for Axiom nodes only (excludes 'player').

    World rules (physics, magic systems) cannot be created by player
    actions—only by GM declaration or authoritative sources.
    """
    SOURCE = "source"
    GM = "gm"
    SYSTEM = "system"

class EntityType(str, Enum):
    """Entity classification."""
    CHARACTER = "character"
    FACTION = "faction"
    LOCATION = "location"
    OBJECT = "object"
    CONCEPT = "concept"
    ORGANIZATION = "organization"

class EntityClass(str, Enum):
    """Axiomatic vs Concrete."""
    AXIOMATICA = "EntityArchetype"
    CONCRETA = "EntityInstance"

class StoryType(str, Enum):
    """Story type."""
    CAMPAIGN = "campaign"
    ARC = "arc"
    EPISODE = "episode"
    ONE_SHOT = "one_shot"

class SceneStatus(str, Enum):
    """Scene workflow status."""
    ACTIVE = "active"
    FINALIZING = "finalizing"
    COMPLETED = "completed"

class ProposalStatus(str, Enum):
    """Proposed change status."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class ProposalType(str, Enum):
    """Type of proposed change."""
    FACT = "fact"
    ENTITY = "entity"
    RELATIONSHIP = "relationship"
    STATE_CHANGE = "state_change"
    EVENT = "event"

class Speaker(str, Enum):
    """Who is speaking in a turn."""
    USER = "user"
    GM = "gm"
    ENTITY = "entity"
```

---

### 1.2 Base Canonization Metadata

```python
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from uuid import UUID

class CanonicalMetadata(BaseModel):
    """Base metadata for all canonical nodes."""
    canon_level: CanonLevel
    confidence: float = Field(ge=0.0, le=1.0)
    authority: Authority
    created_at: datetime

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError('confidence must be between 0.0 and 1.0')
        return v
```

---

