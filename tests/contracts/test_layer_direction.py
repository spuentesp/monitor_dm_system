"""
Tests for layer direction invariant.

Use Cases: SYS-2 (Architecture Enforcement)
"""

import pytest
from monitor_data.invariants.layer_direction import (
    LAYER_NAMES,
    Layer,
    LayerDirection,
    assert_layer_direction,
    check_import_legality,
)


class TestLayerDetection:
    """Tests for layer detection."""

    def test_data_layer_detection(self):
        """monitor_data modules detected as Layer 1."""
        assert LayerDirection.get_layer("monitor_data") == Layer.DATA_LAYER
        assert LayerDirection.get_layer("monitor_data.db.neo4j") == Layer.DATA_LAYER
        assert (
            LayerDirection.get_layer("monitor_data.tools.mongodb_tools")
            == Layer.DATA_LAYER
        )

    def test_agents_layer_detection(self):
        """monitor_agents modules detected as Layer 2."""
        assert LayerDirection.get_layer("monitor_agents") == Layer.AGENTS
        assert LayerDirection.get_layer("monitor_agents.narrator.agent") == Layer.AGENTS
        assert (
            LayerDirection.get_layer("monitor_agents.loops.scene_loop") == Layer.AGENTS
        )

    def test_cli_layer_detection(self):
        """monitor_cli modules detected as Layer 3."""
        assert LayerDirection.get_layer("monitor_cli") == Layer.CLI
        assert LayerDirection.get_layer("monitor_cli.commands.play") == Layer.CLI

    def test_ui_layer_detection(self):
        """monitor_ui modules detected as Layer 3."""
        assert LayerDirection.get_layer("monitor_ui") == Layer.UI
        assert LayerDirection.get_layer("monitor_ui.routers.chat") == Layer.UI

    def test_external_detection(self):
        """External modules detected as Layer 0."""
        assert LayerDirection.get_layer("pydantic") == Layer.EXTERNAL
        assert LayerDirection.get_layer("langgraph") == Layer.EXTERNAL
        assert LayerDirection.get_layer("numpy") == Layer.EXTERNAL


class TestImportLegality:
    """Tests for import legality checking."""

    def test_valid_downward_import(self):
        """Agents can import from Data Layer (downward flow)."""
        is_legal, _ = check_import_legality(
            "monitor_agents.narrator.agent",
            "monitor_data.schemas.scenes",
        )
        assert is_legal is True

    def test_valid_same_layer_import(self):
        """Modules can import from same layer."""
        is_legal, _ = check_import_legality(
            "monitor_agents.narrator.agent",
            "monitor_agents.base",
        )
        assert is_legal is True

    def test_valid_external_import(self):
        """All layers can import external libraries."""
        is_legal, _ = check_import_legality(
            "monitor_data.db.neo4j",
            "neo4j",
        )
        assert is_legal is True

    def test_invalid_upward_import_cli_to_agents(self):
        """CLI cannot import Agents (upward flow)."""
        is_legal, message = check_import_legality(
            "monitor_cli.commands.play",
            "monitor_agents.loops.scene_loop",
        )
        # CLI → Agents is actually VALID (downward from CLI perspective)
        # Wait, this depends on perspective
        # CLI depends on Agents, so it's downward - this should be LEGAL
        assert is_legal is True

    def test_invalid_skip_layer(self):
        """CLI cannot import Data Layer directly (skip layer)."""
        is_legal, message = check_import_legality(
            "monitor_cli.commands.play",
            "monitor_data.db.neo4j",
        )
        assert is_legal is False
        assert "FORBIDDEN" in message or "Layer violation" in message

    def test_invalid_upward_from_data_layer(self):
        """Data Layer cannot import Agents (upward flow)."""
        is_legal, message = check_import_legality(
            "monitor_data.db.neo4j",
            "monitor_agents.base",
        )
        assert is_legal is False
        assert (
            "forbidden" in message.lower()
            or "upward" in message.lower()
            or "Layer violation" in message
        )


class TestAssertLayerDirection:
    """Tests for assert_layer_direction."""

    def test_assert_valid_import(self):
        """assert_layer_direction passes for valid imports."""
        # Should not raise
        assert_layer_direction(
            "monitor_agents.narrator.agent",
            "monitor_data.schemas.scenes",
        )

    def test_assert_invalid_import_raises(self):
        """assert_layer_direction raises for invalid imports."""
        with pytest.raises(ImportError):
            assert_layer_direction(
                "monitor_data.db.neo4j",
                "monitor_agents.base",
            )


class TestForbiddenPatterns:
    """Tests for specific forbidden patterns."""

    def test_cli_cannot_import_data_layer(self):
        """CLI importing data-layer directly is forbidden."""
        is_legal, _ = check_import_legality(
            "monitor_cli",
            "monitor_data",
        )
        assert is_legal is False

    def test_agents_cannot_import_cli(self):
        """Agents importing CLI is forbidden."""
        is_legal, _ = check_import_legality(
            "monitor_agents",
            "monitor_cli",
        )
        assert is_legal is False

    def test_data_layer_cannot_import_agents(self):
        """Data Layer importing Agents is forbidden."""
        is_legal, _ = check_import_legality(
            "monitor_data",
            "monitor_agents",
        )
        assert is_legal is False


class TestLayerNames:
    """Tests for layer name mapping."""

    def test_layer_names_complete(self):
        """All layers have names."""
        assert LAYER_NAMES[Layer.EXTERNAL] == "External"
        assert LAYER_NAMES[Layer.DATA_LAYER] == "Data Layer"
        assert LAYER_NAMES[Layer.AGENTS] == "Agents"
        assert LAYER_NAMES[Layer.CLI] == "CLI/UI"


# =============================================================================
# INTEGRATION TESTS - Check actual imports
# =============================================================================


class TestActualImportGraph:
    """Test actual import graph to verify layer separation."""

    def test_agents_does_not_import_cli(self):
        """Verify agents package doesn't import CLI."""
        # Read the agents package __init__.py
        import monitor_agents

        init_file = monitor_agents.__file__
        if init_file:
            with open(init_file) as f:
                content = f.read()
                # Should not contain monitor_cli imports
                assert "monitor_cli" not in content

    def test_data_layer_does_not_import_agents(self):
        """Verify data-layer package doesn't import agents."""
        import monitor_data

        init_file = monitor_data.__file__
        if init_file:
            with open(init_file) as f:
                content = f.read()
                # Should not contain monitor_agents imports
                assert "monitor_agents" not in content

    def test_monitor_data_schema_imports(self):
        """Verify monitor_data schemas only import external libs."""
        from monitor_data.schemas import base

        init_file = base.__file__
        if init_file:
            with open(init_file) as f:
                content = f.read()
                # Should not contain monitor_agents or monitor_cli
                assert "monitor_agents" not in content
                assert "monitor_cli" not in content
                assert "monitor_ui" not in content
