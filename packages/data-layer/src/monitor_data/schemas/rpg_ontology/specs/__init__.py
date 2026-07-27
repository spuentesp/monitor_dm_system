"""
RPG system specs package.

Import this package to ensure all built-in specs are loaded into SystemRegistry.
No longer imports .py files directly — instead calls the JSON seed loader which
produces GameSystemSpec objects for ALL systems in builtin_systems.json.

Death in Space and all other systems are now loaded from:
    packages/data-layer/src/monitor_data/data/builtin_systems.json

Each spec in that file is converted to a GameSystemSpec at startup via
``converters.builtin_to_game_system_spec()``.
"""

from monitor_data.schemas.rpg_ontology.converters import seed_system_registry

seed_system_registry()

__all__ = []
