"""
MONITOR Contract Testing Infrastructure.

This module provides Design-by-Contract (DbC) decorators and invariant checkers
for the MONITOR data layer.

Usage:
    from monitor_data.contracts import pre, post, invariant
    from monitor_data.invariants import CanonKeeperExclusivity

Tools used:
- deal: Runtime contract enforcement + Z3 verification
- pydantic: Schema validation as contract
"""

from monitor_data.contracts.fact_contracts import (
    FactInvariants,
    FactPostConditions,
    FactPreConditions,
)
from monitor_data.contracts.resolution_contracts import (
    ResolutionInvariants,
    ResolutionPostConditions,
    ResolutionPreConditions,
    dice_roll_properties,
    modifier_properties,
)
from monitor_data.contracts.scene_contracts import (
    SceneInvariants,
    ScenePostConditions,
    ScenePreConditions,
)
from monitor_data.invariants.canon_keeper import (
    CanonKeeperExclusivity,
    assert_canon_keeper_only,
)
from monitor_data.invariants.layer_direction import (
    LayerDirection,
    assert_layer_direction,
)
from monitor_data.invariants.scene_atomicity import (
    SceneAtomicity,
    assert_scene_atomic,
)

__all__ = [
    # Scene contracts
    "ScenePreConditions",
    "ScenePostConditions",
    "SceneInvariants",
    # Fact contracts
    "FactPreConditions",
    "FactPostConditions",
    "FactInvariants",
    # Resolution contracts
    "ResolutionPreConditions",
    "ResolutionPostConditions",
    "ResolutionInvariants",
    "dice_roll_properties",
    "modifier_properties",
    # Invariants
    "CanonKeeperExclusivity",
    "assert_canon_keeper_only",
    "SceneAtomicity",
    "assert_scene_atomic",
    "LayerDirection",
    "assert_layer_direction",
]
