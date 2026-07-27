"""
GM Tools API — Contract Tests

Tests the input/output contracts for the GM Tools API endpoints
(plot hooks, contradiction detection, session prep).

Use Cases: CF-4 (Plot Hooks), CF-5 (Contradiction Detection), CF-7 (Session Prep)
"""

from uuid import uuid4

import pytest
from monitor_agents.plot_hooks import (
    Contradiction,
    Handout,
    PlotHook,
    SessionPrep,
)

# =============================================================================
# PlotHook — Schema Contract Tests
# =============================================================================


@pytest.mark.unit
class TestPlotHookContract:
    """Contract tests for PlotHook schema."""

    def test_plot_hook_minimal(self):
        """PlotHook with only required fields is valid."""
        hook = PlotHook(
            title="The Missing Heir",
            description="A noble family searches for their lost heir.",
        )
        assert hook.title == "The Missing Heir"
        assert hook.description == "A noble family searches for their lost heir."
        assert hook.urgency == "medium"  # default
        assert hook.connected_entities == []  # default

    def test_plot_hook_with_all_fields(self):
        """PlotHook with all fields populated is valid."""
        entity_id = uuid4()
        hook = PlotHook(
            thread_id=str(uuid4()),
            title="The Dragon's Hoard",
            description="A dragon has been spotted near the village.",
            urgency="high",
            suggested_scene_type="encounter",
            connected_entities=[str(entity_id)],
        )
        assert hook.urgency == "high"
        assert hook.suggested_scene_type == "encounter"
        assert len(hook.connected_entities) == 1

    def test_plot_hook_urgency_values(self):
        """PlotHook accepts all valid urgency levels."""
        for urgency in ("low", "medium", "high", "critical"):
            hook = PlotHook(
                title=f"Hook {urgency}",
                description=f"A {urgency} urgency hook.",
                urgency=urgency,
            )
            assert hook.urgency == urgency


@pytest.mark.unit
class TestContradictionContract:
    """Contract tests for Contradiction schema."""

    def test_contradiction_minimal(self):
        """Contradiction with required fields is valid."""
        c = Contradiction(
            fact_a="The king died in 1245",
            fact_b="The king attended the council of 1250",
            severity="high",
            explanation="The king cannot be dead and attend a council 5 years later.",
            suggestion="Change the death year or the council year.",
        )
        assert c.severity == "high"
        assert "1245" in c.fact_a

    def test_contradiction_severity_values(self):
        """Contradiction accepts all valid severity levels."""
        for severity in ("low", "medium", "high"):
            c = Contradiction(
                fact_a="Fact A",
                fact_b="Fact B",
                severity=severity,
                explanation="They contradict.",
                suggestion="Fix it.",
            )
            assert c.severity == severity


@pytest.mark.unit
class TestSessionPrepContract:
    """Contract tests for SessionPrep schema."""

    def test_session_prep_minimal(self):
        """SessionPrep with required fields is valid."""
        prep = SessionPrep(
            recap="The party arrived at the village.",
            open_threads=["The missing heir", "The dragon sighting"],
            hooks=[PlotHook(title="Hook 1", description="A hook")],
            npc_reminders=["Guard Theron", "Mayor Elara"],
            world_state_changes=["The village is now fortified."],
        )
        assert prep.recap == "The party arrived at the village."
        assert len(prep.open_threads) == 2
        assert len(prep.hooks) == 1
        assert len(prep.npc_reminders) == 2
        assert len(prep.world_state_changes) == 1

    def test_session_prep_with_empty_lists(self):
        """SessionPrep can have empty lists for optional fields."""
        prep = SessionPrep(
            recap="Starting fresh.",
            open_threads=[],
            hooks=[],
            npc_reminders=[],
            world_state_changes=[],
        )
        assert prep.open_threads == []
        assert prep.hooks == []


# =============================================================================
# GM Tools Router — Schema Contract Tests
# =============================================================================


@pytest.mark.unit
class TestGMToolsRequestSchemas:
    """Contract tests for GM Tools API request schemas."""

    def test_suggest_hooks_request(self):
        """SuggestHooksRequest validates correctly."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        uid = uuid4()
        req = SuggestHooksRequest(universe_id=uid)
        assert req.universe_id == uid
        assert req.story_id is None
        assert req.max_hooks == 5  # default

    def test_suggest_hooks_request_with_story(self):
        """SuggestHooksRequest can include story_id."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        uid = uuid4()
        sid = uuid4()
        req = SuggestHooksRequest(universe_id=uid, story_id=sid, max_hooks=10)
        assert req.story_id == sid
        assert req.max_hooks == 10

    def test_suggest_hooks_request_max_hooks_bounds(self):
        """SuggestHooksRequest max_hooks must be between 1 and 20."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        uid = uuid4()
        req = SuggestHooksRequest(universe_id=uid, max_hooks=1)
        assert req.max_hooks == 1
        req = SuggestHooksRequest(universe_id=uid, max_hooks=20)
        assert req.max_hooks == 20

    def test_suggest_hooks_request_max_hooks_too_low(self):
        """SuggestHooksRequest with max_hooks=0 raises validation error."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        with pytest.raises(Exception):
            SuggestHooksRequest(universe_id=uuid4(), max_hooks=0)

    def test_suggest_hooks_request_max_hooks_too_high(self):
        """SuggestHooksRequest with max_hooks=21 raises validation error."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        with pytest.raises(Exception):
            SuggestHooksRequest(universe_id=uuid4(), max_hooks=21)

    def test_detect_contradictions_request(self):
        """DetectContradictionsRequest validates correctly."""
        from monitor_ui.routers.gm_tools import DetectContradictionsRequest

        uid = uuid4()
        req = DetectContradictionsRequest(universe_id=uid)
        assert req.universe_id == uid
        assert req.focus_entity_id is None

    def test_detect_contradictions_request_with_focus(self):
        """DetectContradictionsRequest can include focus_entity_id."""
        from monitor_ui.routers.gm_tools import DetectContradictionsRequest

        uid = uuid4()
        eid = uuid4()
        req = DetectContradictionsRequest(universe_id=uid, focus_entity_id=eid)
        assert req.focus_entity_id == eid

    def test_session_prep_request(self):
        """SessionPrepRequest validates correctly."""
        from monitor_ui.routers.gm_tools import SessionPrepRequest

        uid = uuid4()
        sid = uuid4()
        req = SessionPrepRequest(universe_id=uid, story_id=sid)
        assert req.universe_id == uid
        assert req.story_id == sid
        assert req.session_number is None

    def test_session_prep_request_with_session_number(self):
        """SessionPrepRequest can include session_number."""
        from monitor_ui.routers.gm_tools import SessionPrepRequest

        uid = uuid4()
        sid = uuid4()
        req = SessionPrepRequest(universe_id=uid, story_id=sid, session_number=3)
        assert req.session_number == 3


@pytest.mark.unit
class TestGMToolsResponseSchemas:
    """Contract tests for GM Tools API response schemas."""

    def test_suggest_hooks_response(self):
        """SuggestHooksResponse contains hooks list."""
        from monitor_ui.routers.gm_tools import SuggestHooksResponse

        hooks = [PlotHook(title="Hook 1", description="Desc 1")]
        resp = SuggestHooksResponse(hooks=hooks)
        assert len(resp.hooks) == 1
        assert resp.hooks[0].title == "Hook 1"

    def test_suggest_hooks_response_empty(self):
        """SuggestHooksResponse can have empty hooks list."""
        from monitor_ui.routers.gm_tools import SuggestHooksResponse

        resp = SuggestHooksResponse(hooks=[])
        assert resp.hooks == []

    def test_detect_contradictions_response(self):
        """DetectContradictionsResponse contains contradictions list."""
        from monitor_ui.routers.gm_tools import DetectContradictionsResponse

        contradictions = [
            Contradiction(
                fact_a="A",
                fact_b="B",
                severity="high",
                explanation="They conflict.",
                suggestion="Fix it.",
            )
        ]
        resp = DetectContradictionsResponse(contradictions=contradictions)
        assert len(resp.contradictions) == 1

    def test_session_prep_response(self):
        """SessionPrepResponse contains prep data."""
        from monitor_ui.routers.gm_tools import SessionPrepResponse

        prep = SessionPrep(
            recap="Recap text",
            open_threads=["Thread 1"],
            hooks=[PlotHook(title="Hook", description="Desc")],
            npc_reminders=["NPC 1"],
            world_state_changes=["Change 1"],
        )
        resp = SessionPrepResponse(prep=prep)
        assert resp.prep.recap == "Recap text"
        assert len(resp.prep.hooks) == 1


# =============================================================================
# GM Tools Router — Endpoint Contract Tests
# =============================================================================


@pytest.mark.unit
class TestGMToolsRouterContract:
    """Contract tests verifying the GM Tools router endpoints exist."""

    def test_router_has_hooks_endpoint(self):
        """The gm_tools router has a POST /gm/hooks endpoint."""
        from monitor_ui.routers.gm_tools import router

        routes = [route.path for route in router.routes]
        assert "/gm/hooks" in routes

    def test_router_has_contradictions_endpoint(self):
        """The gm_tools router has a POST /gm/contradictions endpoint."""
        from monitor_ui.routers.gm_tools import router

        routes = [route.path for route in router.routes]
        assert "/gm/contradictions" in routes

    def test_router_has_session_prep_endpoint(self):
        """The gm_tools router has a POST /gm/session-prep endpoint."""
        from monitor_ui.routers.gm_tools import router

        routes = [route.path for route in router.routes]
        assert "/gm/session-prep" in routes

    def test_router_registered_in_main(self):
        """The gm_tools router is registered in the FastAPI app."""
        from monitor_ui.routers import gm_tools

        assert hasattr(gm_tools, "router")


# =============================================================================
# Handout — Schema Contract Tests (CF-6)
# =============================================================================


@pytest.mark.unit
class TestHandoutContract:
    """Contract tests for Handout schema."""

    def test_handout_minimal(self):
        """Handout with only required fields is valid."""

        handout = Handout(
            title="A Mysterious Letter",
            content="Dear friend, I write to you with urgent news...",
        )
        assert handout.title == "A Mysterious Letter"
        assert handout.content == "Dear friend, I write to you with urgent news..."
        assert handout.handout_type == "letter"  # default
        assert handout.tone == "mysterious"  # default
        assert handout.spoiler_level == "safe"  # default
        assert handout.related_entities == []  # default

    def test_handout_with_all_fields(self):
        """Handout with all fields populated is valid."""

        handout = Handout(
            title="The Prophecy of Ages",
            content="# The Prophecy\n\n*When the moon turns red...*",
            handout_type="prophecy",
            related_entities=["The Oracle", "King Aldric"],
            tone="ominous",
            spoiler_level="partial",
        )
        assert handout.handout_type == "prophecy"
        assert handout.tone == "ominous"
        assert handout.spoiler_level == "partial"
        assert len(handout.related_entities) == 2

    def test_handout_types(self):
        """Handout supports all defined handout types."""

        for h_type in [
            "letter",
            "map_note",
            "prophecy",
            "journal_entry",
            "notice",
            "rumor",
        ]:
            handout = Handout(
                title=f"Test {h_type}", content="Content", handout_type=h_type
            )
            assert handout.handout_type == h_type

    def test_handout_tones(self):
        """Handout supports various tone values."""

        for tone in ["mysterious", "urgent", "warm", "ominous", "neutral"]:
            handout = Handout(title="Test", content="Content", tone=tone)
            assert handout.tone == tone

    def test_handout_spoiler_levels(self):
        """Handout supports all spoiler levels."""

        for level in ["safe", "partial", "full"]:
            handout = Handout(title="Test", content="Content", spoiler_level=level)
            assert handout.spoiler_level == level


@pytest.mark.unit
class TestHandoutRequestContract:
    """Contract tests for GenerateHandoutRequest schema."""

    def test_handout_request_minimal(self):
        """GenerateHandoutRequest with only universe_id is valid."""
        from monitor_ui.routers.gm_tools import GenerateHandoutRequest

        uid = uuid4()
        req = GenerateHandoutRequest(universe_id=uid)
        assert req.universe_id == uid
        assert req.handout_type == "letter"  # default
        assert req.tone == "mysterious"  # default
        assert req.spoiler_level == "safe"  # default
        assert req.focus_entity_id is None

    def test_handout_request_with_all_fields(self):
        """GenerateHandoutRequest with all fields is valid."""
        from monitor_ui.routers.gm_tools import GenerateHandoutRequest

        uid = uuid4()
        eid = uuid4()
        req = GenerateHandoutRequest(
            universe_id=uid,
            handout_type="prophecy",
            focus_entity_id=eid,
            tone="ominous",
            spoiler_level="partial",
        )
        assert req.handout_type == "prophecy"
        assert req.focus_entity_id == eid
        assert req.tone == "ominous"
        assert req.spoiler_level == "partial"


@pytest.mark.unit
class TestHandoutResponseContract:
    """Contract tests for GenerateHandoutResponse schema."""

    def test_handout_response(self):
        """GenerateHandoutResponse contains a Handout."""
        from monitor_ui.routers.gm_tools import GenerateHandoutResponse

        handout = Handout(
            title="A Letter from Afar",
            content="The road ahead is long...",
            handout_type="letter",
            related_entities=["Merchant"],
            tone="mysterious",
            spoiler_level="safe",
        )
        resp = GenerateHandoutResponse(handout=handout)
        assert resp.handout.title == "A Letter from Afar"
        assert resp.handout.handout_type == "letter"


@pytest.mark.unit
class TestHandoutRouterContract:
    """Contract tests verifying the handout endpoint exists in the router."""

    def test_router_has_handouts_endpoint(self):
        """The gm_tools router has a POST /gm/handouts endpoint."""
        from monitor_ui.routers.gm_tools import router

        routes = [route.path for route in router.routes]
        assert "/gm/handouts" in routes

    def test_handout_endpoint_method(self):
        """The /gm/handouts endpoint uses POST method."""
        from monitor_ui.routers.gm_tools import router

        handout_routes = [
            r for r in router.routes if hasattr(r, "path") and r.path == "/gm/handouts"
        ]
        assert len(handout_routes) == 1
        assert "POST" in handout_routes[0].methods


@pytest.mark.unit
class TestPlotHookAgentHandoutMethod:
    """Contract tests for PlotHookAgent.generate_handout method."""

    def test_generate_handout_method_exists(self):
        """PlotHookAgent has a generate_handout method."""
        from monitor_agents.plot_hooks import PlotHookAgent

        agent = PlotHookAgent()
        assert hasattr(agent, "generate_handout")
        assert callable(agent.generate_handout)

    def test_generate_handout_is_async(self):
        """PlotHookAgent.generate_handout is an async method."""
        import inspect

        from monitor_agents.plot_hooks import PlotHookAgent

        agent = PlotHookAgent()
        assert inspect.iscoroutinefunction(agent.generate_handout)

    def test_generate_handout_signature(self):
        """PlotHookAgent.generate_handout has the expected parameters."""
        import inspect

        from monitor_agents.plot_hooks import PlotHookAgent

        sig = inspect.signature(PlotHookAgent.generate_handout)
        params = list(sig.parameters.keys())
        assert "universe_id" in params
        assert "handout_type" in params
        assert "tone" in params
        assert "spoiler_level" in params

    def test_template_handout_method_exists(self):
        """PlotHookAgent has a _template_handout fallback method."""
        from monitor_agents.plot_hooks import PlotHookAgent

        agent = PlotHookAgent()
        assert hasattr(agent, "_template_handout")
        assert callable(agent._template_handout)

    def test_template_handout_returns_handout(self):
        """_template_handout returns a Handout instance."""
        from monitor_agents.plot_hooks import PlotHookAgent

        agent = PlotHookAgent()
        result = agent._template_handout(
            handout_type="letter",
            tone="mysterious",
            spoiler_level="safe",
            entity_summaries=["- Aragorn (character)"],
            fact_list=["- [canon] The ring must be destroyed"],
        )
        assert isinstance(result, Handout)
        assert result.handout_type == "letter"
        assert result.tone == "mysterious"
        assert result.spoiler_level == "safe"
        assert "Aragorn" in result.related_entities[0]

    def test_template_handout_all_types(self):
        """_template_handout produces valid output for all handout types."""
        from monitor_agents.plot_hooks import PlotHookAgent

        agent = PlotHookAgent()
        for h_type in [
            "letter",
            "map_note",
            "prophecy",
            "journal_entry",
            "notice",
            "rumor",
        ]:
            result = agent._template_handout(
                handout_type=h_type,
                tone="neutral",
                spoiler_level="safe",
                entity_summaries=["- Gandalf (wizard)"],
                fact_list=["- [canon] The bridge is broken"],
            )
            assert isinstance(result, Handout)
            assert result.handout_type == h_type
