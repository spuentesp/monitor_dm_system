# ruff: noqa: F401
"""
RPG Ontology — formal typed schema system for MONITOR.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, uuid, datetime, enum)

Architecture
------------
Two layers:

1. **Meta / factory** (new, general):
   - ``meta.py``     — pure-data spec types (GameSystemSpec, FieldSpec, …)
   - ``factory.py``  — runtime Pydantic model generation via create_model()
   - ``specs/``      — built-in system specs (death_in_space, …)

2. **Base / static** (legacy, kept for backward compatibility):
   - ``base.py``     — abstract base classes (BaseCharacterSheet, …)
   - ``systems/``    — per-system Python subclasses (being phased out)

Usage (new approach — preferred)
---------------------------------
::

    from monitor_data.schemas.rpg_ontology import (
        GameSystemSpec, SystemRegistry,
        make_entity_model, validate_entity_data,
        DEATH_IN_SPACE,
    )

    registry = SystemRegistry()
    spec = registry.get("death_in_space")
    CharacterModel = make_entity_model(spec, "character")

    sheet = CharacterModel(
        character_name="Zyx", body=1, dex=2, savvy=-1, tech=0,
        hp=7, cosmic_rot=0, credits=10, debt=0,
    )
"""

# ── New general meta-schema exports ──────────────────────────────────────────
# Load all built-in specs (auto-registers them with SystemRegistry)
import monitor_data.schemas.rpg_ontology.specs
from monitor_data.schemas.rpg_ontology.base import (
    AttributeSpec as LegacyAttributeSpec,
)

# ── Legacy static exports (backward compatibility) ────────────────────────────
from monitor_data.schemas.rpg_ontology.base import (
    BaseArmor,
    BaseCharacterSheet,
    BaseEquipmentItem,
    BaseGameSystem,
    BaseWeapon,
    EquipmentItemCreate,
    EquipmentItemResponse,
    GameSystemRegistry,
    ItemType,
    ResourceSpec,
    TypedCharacterSheetCreate,
    TypedCharacterSheetResponse,
    TypedCharacterSheetUpdate,
)
from monitor_data.schemas.rpg_ontology.factory import (
    clear_model_cache,
    make_all_models,
    make_entity_model,
    validate_entity_data,
)
from monitor_data.schemas.rpg_ontology.meta import (
    CoreMechanicSpec,
    DataEdgeSpec,
    EntityTypeSpec,
    FieldSpec,
    FieldType,
    GameSystemSpec,
    ItemTypeSpec,
    OntologyMechanicType,
    RelationCardinality,
    RelationSpec,
    StorageBackend,
    SystemRegistry,
    ValidatorSpec,
    ValidatorType,
)

# Convenience re-export for Death in Space
from monitor_data.schemas.rpg_ontology.specs.death_in_space import DEATH_IN_SPACE

# Data topology — all 6 backends, cross-store edges, gap report
from monitor_data.schemas.rpg_ontology.topology import (
    MONITOR_TOPOLOGY,
    DataTopology,
    IndexedBy,
    StorageNode,
    gap_report,
)
from monitor_data.schemas.rpg_ontology.topology import (
    CollectionSpec as TopologyCollectionSpec,
)

__all__ = [
    # Meta / factory (new)
    "FieldSpec",
    "FieldType",
    "ValidatorSpec",
    "ValidatorType",
    "ItemTypeSpec",
    "EntityTypeSpec",
    "RelationSpec",
    "RelationCardinality",
    "CoreMechanicSpec",
    "OntologyMechanicType",
    "DataEdgeSpec",
    "StorageBackend",
    "GameSystemSpec",
    "SystemRegistry",
    "make_entity_model",
    "make_all_models",
    "validate_entity_data",
    "clear_model_cache",
    "DEATH_IN_SPACE",
    # Topology
    "DataTopology",
    "StorageNode",
    "TopologyCollectionSpec",
    "IndexedBy",
    "MONITOR_TOPOLOGY",
    "gap_report",
    # Legacy (base.py)
    "BaseGameSystem",
    "BaseCharacterSheet",
    "BaseEquipmentItem",
    "BaseWeapon",
    "BaseArmor",
    "LegacyAttributeSpec",
    "ResourceSpec",
    "ItemType",
    "GameSystemRegistry",
    "TypedCharacterSheetCreate",
    "TypedCharacterSheetUpdate",
    "TypedCharacterSheetResponse",
    "EquipmentItemCreate",
    "EquipmentItemResponse",
]
