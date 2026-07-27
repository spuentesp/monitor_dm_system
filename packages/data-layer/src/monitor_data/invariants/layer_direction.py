r"""
Layer Direction Invariant (INV-3).

This invariant ensures that dependencies flow in the correct direction:
    Layer 3 (CLI) → Layer 2 (Agents) → Layer 1 (Data Layer)

No layer can import from a layer above it.

Formal Specification:
    LayerDirection ==
        ∧ ∀import \in imports :
            import.source_layer < import.target_layer
        ∧ CLI.imports ⊆ {Agents}
        ∧ Agents.imports ⊆ {DataLayer, External}
        ∧ DataLayer.imports ⊆ {External}

TLA+ Representation:
    VARIABLE import_graph: function mapping modules to their imports

    LayerDirectionInvariant ==
        /\ \A mod \in DOMAIN import_graph :
            \A imp \in import_graph[mod] :
                Layer(mod) > Layer(imp)
"""


# Layer definitions
class Layer:
    """Layer number constants (higher = closer to user)."""

    EXTERNAL = 0
    DATA_LAYER = 1
    AGENTS = 2
    CLI = 3
    UI = 3  # Same as CLI


LAYER_NAMES: dict[int, str] = {
    0: "External",
    1: "Data Layer",
    2: "Agents",
    3: "CLI/UI",
}

# Valid import paths between layers
VALID_IMPORTS: dict[str, frozenset[str]] = {
    # Data Layer can only import external libraries
    "monitor_data": frozenset(
        {
            "monitor_data",  # Internal imports within data-layer
            "pydantic",
            "datetime",
            "uuid",
            "enum",
            "typing",
            "logging",
            "mcp",
            "neo4j",
            "motor",
            "qdrant_client",
            "minio",
            "asyncpg",
            "aiosqlite",
            "structlog",
            "tenacity",
            "instructor",
            "logfire",
            # Add other allowed external imports
        }
    ),
    # Agents can import data-layer and external
    "monitor_agents": frozenset(
        {
            "monitor_agents",
            "monitor_data",
            "pydantic",
            "datetime",
            "uuid",
            "enum",
            "typing",
            "logging",
            "langgraph",
            "dspy",
            "structlog",
            "tenacity",
            "instructor",
            "logfire",
            # Other external libs agents use
        }
    ),
    # CLI can import agents and external
    "monitor_cli": frozenset(
        {
            "monitor_cli",
            "monitor_agents",
            "pydantic",
            "datetime",
            "uuid",
            "enum",
            "typing",
            "logging",
            "click",
            "typer",
            # Other external libs CLI uses
        }
    ),
    # UI Backend can import agents and external
    "monitor_ui": frozenset(
        {
            "monitor_ui",
            "monitor_agents",
            "monitor_data",  # UI sometimes needs direct data access for static files
            "pydantic",
            "fastapi",
            "uvicorn",
            "websockets",
            "jinja2",
            # Other external libs
        }
    ),
}

# Forbidden import patterns (skip-layer imports)
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    # CLI cannot import data-layer directly
    ("monitor_cli", "monitor_data"),
    # Agents cannot import CLI
    ("monitor_agents", "monitor_cli"),
    # Data Layer cannot import agents or CLI
    ("monitor_data", "monitor_agents"),
    ("monitor_data", "monitor_cli"),
    ("monitor_data", "monitor_ui"),
]


class LayerDirection:
    """
    Formal invariant checker for layer direction.

    This ensures:
    1. Dependencies flow downward (CLI → Agents → Data Layer)
    2. No skip-layer imports (CLI → Data Layer)
    3. No upward imports (Data Layer → Agents)
    """

    @staticmethod
    def get_layer(module_name: str) -> int:
        """
        Get the layer number for a module.

        Args:
            module_name: Full module name (e.g., 'monitor_data.db.neo4j')

        Returns:
            Layer number (0-3)
        """
        if module_name.startswith("monitor_data"):
            return Layer.DATA_LAYER
        elif module_name.startswith("monitor_agents"):
            return Layer.AGENTS
        elif module_name.startswith("monitor_cli"):
            return Layer.CLI
        elif module_name.startswith("monitor_ui"):
            return Layer.UI
        else:
            return Layer.EXTERNAL

    @staticmethod
    def is_valid_import(source_module: str, target_module: str) -> bool:
        """
        Check if import from source to target is valid.

        Args:
            source_module: Module doing the import
            target_module: Module being imported

        Returns:
            True if import direction is valid
        """
        source_layer = LayerDirection.get_layer(source_module)
        target_layer = LayerDirection.get_layer(target_module)

        # External imports are always valid
        if target_layer == Layer.EXTERNAL:
            return True

        # Same layer imports are always valid
        if source_layer == target_layer:
            return True

        # Must flow downward (higher number to lower number)
        return source_layer >= target_layer  # Upward import forbidden

    @staticmethod
    def check_import_legality(source_module: str, target_module: str) -> tuple[bool, str | None]:
        """
        Check if import is legal and return violation message if not.

        Args:
            source_module: Module doing the import
            target_module: Module being imported

        Returns:
            (is_legal, violation_message)
        """
        source_layer = LayerDirection.get_layer(source_module)
        target_layer = LayerDirection.get_layer(target_module)

        # Check for forbidden patterns
        for forbidden_source, forbidden_target in FORBIDDEN_PATTERNS:
            if source_module.startswith(forbidden_source) and target_module.startswith(forbidden_target):
                return False, (
                    f"FORBIDDEN: {source_module} cannot import {target_module}. "
                    f"Layer {LAYER_NAMES[source_layer]} cannot import Layer {LAYER_NAMES[target_layer]}."
                )

        # Check downward flow (must flow from higher layer to lower layer)
        if source_layer < target_layer:
            return False, (
                f"Layer violation: {source_module} (Layer {source_layer}: {LAYER_NAMES[source_layer]}) "
                f"cannot import {target_module} (Layer {target_layer}: {LAYER_NAMES[target_layer]}). "
                f"Dependencies must flow downward."
            )

        return True, None

    @staticmethod
    def assert_valid_import(source_module: str, target_module: str) -> None:
        """
        Assert that import is legal.

        Args:
            source_module: Module doing the import
            target_module: Module being imported

        Raises:
            ImportError: If import violates layer direction
        """
        is_legal, message = LayerDirection.check_import_legality(source_module, target_module)
        if not is_legal:
            raise ImportError(message)


def assert_layer_direction(source_module: str, target_module: str) -> None:
    """
    Convenience function to assert valid layer direction.

    Args:
        source_module: Module doing the import
        target_module: Module being imported

    Raises:
        ImportError: If import violates layer direction
    """
    LayerDirection.assert_valid_import(source_module, target_module)


def check_import_legality(source_module: str, target_module: str) -> tuple[bool, str | None]:
    """
    Convenience function to check import legality.

    Args:
        source_module: Module doing the import
        target_module: Module being imported

    Returns:
        (is_legal, violation_message)
    """
    return LayerDirection.check_import_legality(source_module, target_module)


# =============================================================================
# TLA+ SPECIFICATION
# =============================================================================
r"""
---------------- MODULE LayerDirection ----------------

CONSTANT
    - Modules: set of all module names
    - External: set of external library modules

VARIABLE
    - import_graph: function [Modules -> SUBSET Modules]
    - layer_map: function [Modules -> {0, 1, 2, 3}]

\* Layer 0 = External, 1 = Data Layer, 2 = Agents, 3 = CLI/UI

LayerValid(mod, imp) ==
    \/ layer_map[mod] = 0  \* External can import anything
    \/ layer_map[mod] = layer_map[imp]  \* Same layer imports allowed
    \/ layer_map[mod] > layer_map[imp]  \* Downward imports only

LayerDirectionInvariant ==
    \A mod \in Modules :
        \A imp \in import_graph[mod] :
            LayerValid(mod, imp)

TypeInvariant ==
    /\ import_graph : [Modules -> SUBSET Modules]
    /\ layer_map : [Modules -> {0, 1, 2, 3}]

Init ==
    /\ import_graph = [m \in Modules |-> {}]
    /\ layer_map = [m \in Modules |->
        CASE m \in {"monitor_data.*"} -> 1
          [] m \in {"monitor_agents.*"} -> 2
          [] m \in {"monitor_cli.*", "monitor_ui.*"} -> 3
          [] OTHER -> 0]

THEOREM TypeInvariant /\ Init => LayerDirectionInvariant

=============================================================
"""
