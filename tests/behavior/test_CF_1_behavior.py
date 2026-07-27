"""
Behavior tests for CF-1 to CF-3: Co-pilot Basics (GM Assistant).

Verifies GM assistant agent schemas, Oracle resolution,
and GM tools router without real DB/LLM connections.
"""

from __future__ import annotations

from uuid import uuid4

# =============================================================================
# PlotHookAgent (CF-4)
# =============================================================================


class TestPlotHookAgentImport:
    def test_agent_importable(self):
        """PlotHookAgent is importable."""
        from monitor_agents.plot_hooks import PlotHookAgent

        assert PlotHookAgent is not None

    def test_agent_is_base_agent(self):
        """PlotHookAgent inherits from BaseAgent."""
        from monitor_agents.base import BaseAgent
        from monitor_agents.plot_hooks import PlotHookAgent

        assert issubclass(PlotHookAgent, BaseAgent)

    def test_agent_has_suggest_hooks(self):
        """PlotHookAgent has suggest_hooks method."""
        from monitor_agents.plot_hooks import PlotHookAgent

        assert hasattr(PlotHookAgent, "suggest_hooks")

    def test_agent_has_detect_contradictions(self):
        """PlotHookAgent has detect_contradictions method."""
        from monitor_agents.plot_hooks import PlotHookAgent

        assert hasattr(PlotHookAgent, "detect_contradictions")

    def test_agent_has_generate_session_prep(self):
        """PlotHookAgent has generate_session_prep method."""
        from monitor_agents.plot_hooks import PlotHookAgent

        assert hasattr(PlotHookAgent, "generate_session_prep")

    def test_agent_has_generate_handout(self):
        """PlotHookAgent has generate_handout method."""
        from monitor_agents.plot_hooks import PlotHookAgent

        assert hasattr(PlotHookAgent, "generate_handout")


# =============================================================================
# PlotHook Schema
# =============================================================================


class TestPlotHookSchema:
    def test_plot_hook_importable(self):
        """PlotHook schema is importable."""
        from monitor_agents.plot_hooks import PlotHook

        assert PlotHook is not None

    def test_plot_hook_fields(self):
        """PlotHook has expected fields."""
        from monitor_agents.plot_hooks import PlotHook

        hook = PlotHook(
            title="The Missing Merchant",
            description="A merchant has vanished from the market district.",
            urgency="high",
            suggested_scene_type="investigation",
            connected_entities=["Merchant Guild"],
        )
        assert hook.title == "The Missing Merchant"
        assert hook.urgency == "high"
        assert hook.suggested_scene_type == "investigation"
        assert len(hook.connected_entities) == 1


# =============================================================================
# Contradiction Schema
# =============================================================================


class TestContradictionSchema:
    def test_contradiction_importable(self):
        """Contradiction schema is importable."""
        from monitor_agents.plot_hooks import Contradiction

        assert Contradiction is not None

    def test_contradiction_fields(self):
        """Contradiction has expected fields."""
        from monitor_agents.plot_hooks import Contradiction

        c = Contradiction(
            fact_a="The king is alive",
            fact_b="The king was assassinated",
            severity="critical",
            explanation="Direct contradiction about the king's status",
            suggestion="Investigate timeline of events",
        )
        assert c.severity == "critical"
        assert "king" in c.fact_a.lower()


# =============================================================================
# SessionPrep Schema
# =============================================================================


class TestSessionPrepSchema:
    def test_session_prep_importable(self):
        """SessionPrep schema is importable."""
        from monitor_agents.plot_hooks import SessionPrep

        assert SessionPrep is not None

    def test_session_prep_fields(self):
        """SessionPrep has expected fields."""
        from monitor_agents.plot_hooks import SessionPrep

        prep = SessionPrep(
            recap="Last session, the party discovered the hidden temple.",
            open_threads=["The cursed amulet", "The missing priest"],
            npc_reminders=["Father Thomas owes the party a favor"],
            world_state_changes=["The temple has been consecrated"],
        )
        assert len(prep.open_threads) == 2
        assert len(prep.npc_reminders) == 1
        assert "cursed amulet" in prep.open_threads[0]


# =============================================================================
# Handout Schema
# =============================================================================


class TestHandoutSchema:
    def test_handout_importable(self):
        """Handout schema is importable."""
        from monitor_agents.plot_hooks import Handout

        assert Handout is not None

    def test_handout_fields(self):
        """Handout has expected fields."""
        from monitor_agents.plot_hooks import Handout

        h = Handout(
            title="The Ancient Map",
            content="A weathered map showing the location of the lost mines.",
            handout_type="prop",
            related_entities=["Lost Mines"],
            tone="mysterious",
            spoiler_level="safe",
        )
        assert h.title == "The Ancient Map"
        assert h.handout_type == "prop"
        assert h.tone == "mysterious"
        assert h.spoiler_level == "safe"


# =============================================================================
# Oracle (CF-2: Probability Resolution)
# =============================================================================


class TestOracleAgentImport:
    def test_oracle_importable(self):
        """Oracle agent is importable."""
        from monitor_agents.oracle import Oracle

        assert Oracle is not None

    def test_oracle_is_base_agent(self):
        """Oracle inherits from BaseAgent."""
        from monitor_agents.base import BaseAgent
        from monitor_agents.oracle import Oracle

        assert issubclass(Oracle, BaseAgent)

    def test_oracle_has_resolve_question(self):
        """Oracle has resolve_question method."""
        from monitor_agents.oracle import Oracle

        assert hasattr(Oracle, "resolve_question")


class TestOracleLikelihoodEnum:
    def test_likelihood_importable(self):
        """Likelihood enum is importable."""
        from monitor_agents.oracle import Likelihood

        assert Likelihood is not None

    def test_likelihood_levels(self):
        """Likelihood has expected levels from certain to impossible."""
        from monitor_agents.oracle import Likelihood

        assert hasattr(Likelihood, "CERTAIN")
        assert hasattr(Likelihood, "IMPOSSIBLE")


class TestOracleOutcomeEnum:
    def test_outcome_importable(self):
        """OracleOutcome enum is importable."""
        from monitor_agents.oracle import OracleOutcome

        assert OracleOutcome is not None

    def test_outcome_values(self):
        """OracleOutcome has expected values."""
        from monitor_agents.oracle import OracleOutcome

        assert hasattr(OracleOutcome, "YES_AND")
        assert hasattr(OracleOutcome, "YES")
        assert hasattr(OracleOutcome, "YES_BUT")
        assert hasattr(OracleOutcome, "NO_BUT")
        assert hasattr(OracleOutcome, "NO")
        assert hasattr(OracleOutcome, "NO_AND")


# =============================================================================
# Simulacrum Agent (CF-3: World Simulation)
# =============================================================================


class TestSimulacrumAgentImport:
    def test_simulacrum_importable(self):
        """SimulacrumAgent is importable."""
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        assert SimulacrumAgent is not None

    def test_simulacrum_is_base_agent(self):
        """SimulacrumAgent inherits from BaseAgent."""
        from monitor_agents.base import BaseAgent
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        assert issubclass(SimulacrumAgent, BaseAgent)

    def test_simulacrum_has_world_tick(self):
        """SimulacrumAgent has run_world_tick method."""
        from monitor_agents.simulacrum.agent import SimulacrumAgent

        assert hasattr(SimulacrumAgent, "run_world_tick")


# =============================================================================
# GM Tools Router
# =============================================================================


class TestGMToolsRouter:
    def test_router_importable(self):
        """GM tools router module is importable."""
        from monitor_ui.routers.gm_tools import router

        assert router is not None

    def test_router_has_hooks_route(self):
        """GM tools router has hooks endpoint."""
        from monitor_ui.routers.gm_tools import router

        route_paths = [r.path for r in router.routes]
        assert any("hooks" in p for p in route_paths)

    def test_router_has_contradictions_route(self):
        """GM tools router has contradictions endpoint."""
        from monitor_ui.routers.gm_tools import router

        route_paths = [r.path for r in router.routes]
        assert any("contradictions" in p for p in route_paths)

    def test_router_has_session_prep_route(self):
        """GM tools router has session-prep endpoint."""
        from monitor_ui.routers.gm_tools import router

        route_paths = [r.path for r in router.routes]
        assert any("session" in p for p in route_paths)

    def test_router_has_handouts_route(self):
        """GM tools router has handouts endpoint."""
        from monitor_ui.routers.gm_tools import router

        route_paths = [r.path for r in router.routes]
        assert any("handout" in p for p in route_paths)


# =============================================================================
# GM Tools Request Schemas
# =============================================================================


class TestSuggestHooksRequestSchema:
    def test_request_importable(self):
        """SuggestHooksRequest schema is importable."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        assert SuggestHooksRequest is not None

    def test_request_fields(self):
        """SuggestHooksRequest has expected fields."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        req = SuggestHooksRequest(universe_id=uuid4(), story_id=uuid4(), max_hooks=5)
        assert req.max_hooks == 5


class TestDetectContradictionsRequestSchema:
    def test_request_importable(self):
        """DetectContradictionsRequest schema is importable."""
        from monitor_ui.routers.gm_tools import DetectContradictionsRequest

        assert DetectContradictionsRequest is not None


class TestSessionPrepRequestSchema:
    def test_request_importable(self):
        """SessionPrepRequest schema is importable."""
        from monitor_ui.routers.gm_tools import SessionPrepRequest

        assert SessionPrepRequest is not None


class TestGenerateHandoutRequestSchema:
    def test_request_importable(self):
        """GenerateHandoutRequest schema is importable."""
        from monitor_ui.routers.gm_tools import GenerateHandoutRequest

        assert GenerateHandoutRequest is not None

    def test_request_fields(self):
        """GenerateHandoutRequest has expected fields."""
        from monitor_ui.routers.gm_tools import GenerateHandoutRequest

        req = GenerateHandoutRequest(
            universe_id=uuid4(),
            handout_type="letter",
            tone="mysterious",
            spoiler_level="low",
        )
        assert req.handout_type == "letter"
        assert req.tone == "mysterious"
        assert req.spoiler_level == "low"


# =============================================================================
# BaseAgent Contract (CF-1: Co-pilot must be stateless)
# =============================================================================


class TestBaseAgentContract:
    def test_base_agent_is_stateless(self):
        """BaseAgent constructor stores agent_type and agent_id."""
        from monitor_agents.base import BaseAgent

        # BaseAgent is abstract but can be subclassed for testing
        class TestAgent(BaseAgent):
            async def run(self, **kwargs: object) -> None:
                pass

        agent = TestAgent(agent_type="TestAgent", agent_id="test-1")
        assert agent.agent_type == "TestAgent"
        assert agent.agent_id == "test-1"

    def test_base_agent_has_call_llm(self):
        """BaseAgent has call_llm_structured method."""
        from monitor_agents.base import BaseAgent

        assert hasattr(BaseAgent, "call_llm_structured")

    def test_base_agent_has_call_tool(self):
        """BaseAgent has call_tool method."""
        from monitor_agents.base import BaseAgent

        assert hasattr(BaseAgent, "call_tool")
