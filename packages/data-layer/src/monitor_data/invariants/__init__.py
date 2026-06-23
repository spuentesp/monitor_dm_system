"""
MONITOR Invariants Module.

This module provides invariant checkers for critical system constraints.
These are TLA+-style formal specifications encoded in Python.

Usage:
    from monitor_data.invariants import CanonKeeperExclusivity, SceneAtomicity

    # In middleware or tests
    CanonKeeperExclusivity.assert_write_allowed("neo4j_create_fact", "CanonKeeper")
    SceneAtomicity.assert_scene_boundary(scene_id, proposed_changes)
"""

from monitor_data.invariants.canon_keeper import (
    CanonKeeperExclusivity,
    assert_canon_keeper_only,
    is_canon_keeper_tool,
)
from monitor_data.invariants.scene_atomicity import (
    SceneAtomicity,
    assert_scene_atomic,
    get_atomic_boundary,
)
from monitor_data.invariants.layer_direction import (
    LayerDirection,
    assert_layer_direction,
    check_import_legality,
)
from monitor_data.invariants.turn_flow import (
    TurnFlow,
    TurnPhase,
)
from monitor_data.invariants.proposed_change_workflow import (
    ProposedChangeWorkflow,
    ProposedChangeStatus,
)

__all__ = [
    # INV-1: CanonKeeper Exclusivity
    "CanonKeeperExclusivity",
    "assert_canon_keeper_only",
    "is_canon_keeper_tool",
    # INV-2: Scene Atomicity
    "SceneAtomicity",
    "assert_scene_atomic",
    "get_atomic_boundary",
    # INV-3: Layer Direction
    "LayerDirection",
    "assert_layer_direction",
    "check_import_legality",
    # INV-4: Turn Flow
    "TurnFlow",
    "TurnPhase",
    # INV-6: Proposed Change Workflow
    "ProposedChangeWorkflow",
    "ProposedChangeStatus",
]
