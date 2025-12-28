"""
Pydantic schemas for MONITOR Data Layer.

These schemas define the data contracts for all operations.
They are used for:
- Request/response validation
- API documentation generation
- Type safety across the codebase

SCHEMA CATEGORIES:
- base:        Base models, enums (CanonLevel, Authority, etc)
- universe:    Universe, Multiverse schemas
- entities:    EntityArchetype, EntityInstance, entity types
- facts:       Fact, Event, canon_level, authority
- scenes:      Scene, Turn, ProposedChange, Resolution
- memories:    CharacterMemory, importance, valence
- sources:     Source, Document, Snippet
- queries:     Search requests, filters, pagination
- composite:   ContextPackage, CanonizationResult

See: docs/architecture/VALIDATION_SCHEMAS.md for full schema definitions
"""

from monitor_data.schemas.base import (
    CanonLevel,
    SourceCanonLevel,
    Authority,
    AxiomAuthority,
    EntityType,
    EntityClass,
    StoryType,
    StoryStatus,
    SceneStatus,
    ProposalStatus,
    ProposalType,
    Speaker,
    CanonicalMetadata,
    BaseResponse,
)
from monitor_data.schemas.universe import (
    UniverseCreate,
    UniverseUpdate,
    UniverseResponse,
    UniverseFilter,
    MultiverseCreate,
    MultiverseUpdate,
    MultiverseResponse,
)
from monitor_data.schemas.memories import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
    MemoryFilter,
    MemoryListResponse,
    MemorySearchQuery,
    MemorySearchResult,
    MemorySearchResponse,
)

# from monitor_data.schemas.entities import *
# from monitor_data.schemas.facts import *
# from monitor_data.schemas.scenes import *
# from monitor_data.schemas.sources import *
# from monitor_data.schemas.queries import *
# from monitor_data.schemas.composite import *

__all__ = [
    # Base enums and models
    "CanonLevel",
    "SourceCanonLevel",
    "Authority",
    "AxiomAuthority",
    "EntityType",
    "EntityClass",
    "StoryType",
    "StoryStatus",
    "SceneStatus",
    "ProposalStatus",
    "ProposalType",
    "Speaker",
    "CanonicalMetadata",
    "BaseResponse",
    # Universe schemas
    "UniverseCreate",
    "UniverseUpdate",
    "UniverseResponse",
    "UniverseFilter",
    "MultiverseCreate",
    "MultiverseUpdate",
    "MultiverseResponse",
    # Memory schemas (DL-7)
    "MemoryCreate",
    "MemoryUpdate",
    "MemoryResponse",
    "MemoryFilter",
    "MemoryListResponse",
    "MemorySearchQuery",
    "MemorySearchResult",
    "MemorySearchResponse",
]
