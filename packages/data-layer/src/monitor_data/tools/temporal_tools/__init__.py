"""
Temporal validation and fact expiration tools (Temporal & Contradiction Gap).

LAYER: 1 (data-layer)

This package provides utilities for:
  - Checking temporal consistency of scenes against canon
  - Managing fact validity and expiration
  - Detecting temporal violations and paradoxes

Public modules:
  - fact_expiration: Check if facts are valid at specific times
  - scene_validation: Validate scene timeline consistency
"""

from monitor_data.tools.temporal_tools.fact_expiration import (
    batch_check_fact_validity,
    check_fact_validity,
    exclude_superseded_facts,
    get_active_facts,
    get_current_facts,
    order_facts_by_time,
)
from monitor_data.tools.temporal_tools.scene_validation import (
    validate_scene_temporal,
)

__all__ = [
    "batch_check_fact_validity",
    "check_fact_validity",
    "exclude_superseded_facts",
    "get_active_facts",
    "get_current_facts",
    "order_facts_by_time",
    "validate_scene_temporal",
]
