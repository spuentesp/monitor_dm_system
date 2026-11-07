"""
RPG system specs package.

Import this package to ensure all built-in specs are loaded into SystemRegistry.
No longer imports .py files directly — instead calls the JSON seed loader which
produces GameSystemSpec objects for ALL systems in builtin_systems.json.

Every spec in that file is converted to a GameSystemSpec at startup via
``converters.builtin_to_game_system_spec()``. Game systems are third-party
content; the platform never ships per-system Python modules.
"""

from monitor_data.schemas.rpg_ontology.converters import seed_system_registry

seed_system_registry()

__all__ = []
