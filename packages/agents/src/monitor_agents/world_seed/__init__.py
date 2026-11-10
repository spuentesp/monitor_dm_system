"""WorldSeed — starting situations for the guided start (Phase 2).

LAYER: 2 (agents)

Given a universe, produce 2-4 concrete start options grounded in its
content; materialize the chosen option into canon state at the opening.
"""

from monitor_agents.world_seed.gather import gather_universe_material
from monitor_agents.world_seed.materialize import (
    materialize_chosen_start,
    prepare_starting_situation,
    resolve_chosen_start,
    situation_brief,
)
from monitor_agents.world_seed.models import (
    StartOption,
    StartOptionNPC,
    StartOptionThread,
    UniverseMaterial,
    WorldSeedResult,
)
from monitor_agents.world_seed.seed import WorldSeed, estimate_start_time

__all__ = [
    "StartOption",
    "StartOptionNPC",
    "StartOptionThread",
    "UniverseMaterial",
    "WorldSeed",
    "WorldSeedResult",
    "estimate_start_time",
    "gather_universe_material",
    "materialize_chosen_start",
    "prepare_starting_situation",
    "resolve_chosen_start",
    "situation_brief",
]
