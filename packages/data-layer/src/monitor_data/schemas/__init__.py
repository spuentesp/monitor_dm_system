"""
Pydantic schemas for MONITOR Data Layer.

These schemas define the data contracts for all operations.
They are used for:
- Request/response validation
- API documentation generation
- Type safety across the codebase

SCHEMA CATEGORIES:
- base:        Common schemas and enums
- universe:    Multiverse, Universe
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
    Authority,
    BaseCreateSchema,
    BaseNodeSchema,
    BaseResponseSchema,
    BaseUpdateSchema,
    CanonLevel,
    ErrorResponse,
)
from monitor_data.schemas.universe import (
    ListUniversesRequest,
    ListUniversesResponse,
    MultiverseCreate,
    MultiverseResponse,
    MultiverseUpdate,
    UniverseCreate,
    UniverseResponse,
    UniverseUpdate,
)

__all__ = [
    # Base schemas
    "Authority",
    "BaseCreateSchema",
    "BaseNodeSchema",
    "BaseResponseSchema",
    "BaseUpdateSchema",
    "CanonLevel",
    "ErrorResponse",
    # Universe schemas
    "ListUniversesRequest",
    "ListUniversesResponse",
    "MultiverseCreate",
    "MultiverseResponse",
    "MultiverseUpdate",
    "UniverseCreate",
    "UniverseResponse",
    "UniverseUpdate",
]

# from monitor_data.schemas.entities import *
# from monitor_data.schemas.facts import *
# from monitor_data.schemas.scenes import *
# from monitor_data.schemas.memories import *
# from monitor_data.schemas.sources import *
# from monitor_data.schemas.queries import *
# from monitor_data.schemas.composite import *
