"""
Contract tests for the GM Tools router (CF-4, CF-5, CF-7).

Tests the input/output contracts for plot hooks, contradiction detection,
and session prep endpoints.

Use Cases: CF-4 (Plot Hooks), CF-5 (Contradiction Detection), CF-7 (Session Prep)

pytest --test-run-type=unit tests/contracts/test_gm_tools_contracts.py
"""

from __future__ import annotations

import pytest
from uuid import uuid4

from pydantic import ValidationError


# =============================================================================
# Router import contract
# =============================================================================


class TestGMRouterImport:
    """GM Tools router should be importable and properly configured."""

    def test_gm_tools_router_importable(self):
        """gm_tools router module imports without errors."""
        try:
            from monitor_ui.routers.gm_tools import router
            assert router is not None
        except ImportError as exc:
            pytest.fail(f"Failed to import gm_tools router: {exc}")

    def test_has_hooks_endpoint(self):
        """Router should have POST /gm/hooks."""
        from monitor_ui.routers.gm_tools import router

        routes = {r.path: r.methods for r in router.routes}
        assert "/gm/hooks" in routes, f"Expected /gm/hooks route, got {routes}"
        assert "POST" in routes["/gm/hooks"]

    def test_has_contradictions_endpoint(self):
        """Router should have POST /gm/contradictions."""
        from monitor_ui.routers.gm_tools import router

        routes = {r.path: r.methods for r in router.routes}
        assert "/gm/contradictions" in routes, f"Expected /gm/contradictions route, got {routes}"
        assert "POST" in routes["/gm/contradictions"]

    def test_has_session_prep_endpoint(self):
        """Router should have POST /gm/session-prep."""
        from monitor_ui.routers.gm_tools import router

        routes = {r.path: r.methods for r in router.routes}
        assert "/gm/session-prep" in routes, f"Expected /gm/session-prep route, got {routes}"
        assert "POST" in routes["/gm/session-prep"]


# =============================================================================
# SuggestHooksRequest schema contract
# =============================================================================


class TestSuggestHooksRequestContract:
    """Contract tests for SuggestHooksRequest schema."""

    def test_valid_request(self):
        """SuggestHooksRequest with all fields is valid."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        req = SuggestHooksRequest(
            universe_id=uuid4(),
            story_id=uuid4(),
            max_hooks=5,
        )
        assert req.universe_id is not None
        assert req.story_id is not None
        assert req.max_hooks == 5

    def test_universe_id_required(self):
        """universe_id is required."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        with pytest.raises(ValidationError):
            SuggestHooksRequest()  # missing required universe_id

    def test_story_id_optional(self):
        """story_id is optional."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        req = SuggestHooksRequest(universe_id=uuid4())
        assert req.story_id is None

    def test_max_hooks_default(self):
        """max_hooks defaults to 5."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        req = SuggestHooksRequest(universe_id=uuid4())
        assert req.max_hooks == 5

    def test_max_hooks_min_constraint(self):
        """max_hooks must be >= 1."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        with pytest.raises(ValidationError):
            SuggestHooksRequest(universe_id=uuid4(), max_hooks=0)

    def test_max_hooks_max_constraint(self):
        """max_hooks must be <= 20."""
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        with pytest.raises(ValidationError):
            SuggestHooksRequest(universe_id=uuid4(), max_hooks=25)


# =============================================================================
# DetectContradictionsRequest schema contract
# =============================================================================


class TestDetectContradictionsRequestContract:
    """Contract tests for DetectContradictionsRequest schema."""

    def test_valid_request_minimal(self):
        """DetectContradictionsRequest with required fields is valid."""
        from monitor_ui.routers.gm_tools import DetectContradictionsRequest

        req = DetectContradictionsRequest(universe_id=uuid4())
        assert req.universe_id is not None
        assert req.focus_entity_id is None

    def test_valid_request_with_focus(self):
        """DetectContradictionsRequest with focus_entity_id is valid."""
        from monitor_ui.routers.gm_tools import DetectContradictionsRequest

        req = DetectContradictionsRequest(
            universe_id=uuid4(),
            focus_entity_id=uuid4(),
        )
        assert req.focus_entity_id is not None

    def test_universe_id_required(self):
        """universe_id is required."""
        from monitor_ui.routers.gm_tools import DetectContradictionsRequest

        with pytest.raises(ValidationError):
            DetectContradictionsRequest()  # missing required universe_id


# =============================================================================
# SessionPrepRequest schema contract
# =============================================================================


class TestSessionPrepRequestContract:
    """Contract tests for SessionPrepRequest schema."""

    def test_valid_request(self):
        """SessionPrepRequest with all fields is valid."""
        from monitor_ui.routers.gm_tools import SessionPrepRequest

        req = SessionPrepRequest(
            universe_id=uuid4(),
            story_id=uuid4(),
            session_number=3,
        )
        assert req.universe_id is not None
        assert req.story_id is not None
        assert req.session_number == 3

    def test_universe_id_required(self):
        """universe_id is required."""
        from monitor_ui.routers.gm_tools import SessionPrepRequest

        with pytest.raises(ValidationError):
            SessionPrepRequest()  # missing required fields

    def test_story_id_required(self):
        """story_id is required."""
        from monitor_ui.routers.gm_tools import SessionPrepRequest

        with pytest.raises(ValidationError):
            SessionPrepRequest(universe_id=uuid4())  # missing story_id

    def test_session_number_optional(self):
        """session_number is optional."""
        from monitor_ui.routers.gm_tools import SessionPrepRequest

        req = SessionPrepRequest(
            universe_id=uuid4(),
            story_id=uuid4(),
        )
        assert req.session_number is None


# =============================================================================
# Response schema contracts
# =============================================================================


class TestSuggestHooksResponseContract:
    """Contract tests for SuggestHooksResponse schema."""

    def test_response_has_hooks_list(self):
        """SuggestHooksResponse has a hooks list field."""
        from monitor_ui.routers.gm_tools import SuggestHooksResponse

        resp = SuggestHooksResponse(hooks=[])
        assert resp.hooks == []


class TestDetectContradictionsResponseContract:
    """Contract tests for DetectContradictionsResponse schema."""

    def test_response_has_contradictions_list(self):
        """DetectContradictionsResponse has a contradictions list field."""
        from monitor_ui.routers.gm_tools import DetectContradictionsResponse

        resp = DetectContradictionsResponse(contradictions=[])
        assert resp.contradictions == []


class TestSessionPrepResponseContract:
    """Contract tests for SessionPrepResponse schema."""

    def test_response_has_prep_field(self):
        """SessionPrepResponse has a prep field."""
        from monitor_ui.routers.gm_tools import SessionPrepResponse

        # Create a minimal SessionPrep (all lists, no strings)
        from monitor_agents.plot_hooks import SessionPrep

        prep = SessionPrep(
            recap="",
            open_threads=[],
            hooks=[],
            npc_reminders=[],
            world_state_changes=[],
        )
        resp = SessionPrepResponse(prep=prep)
        assert resp.prep is not None


# =============================================================================
# Endpoint parameter validation via TestClient
# =============================================================================


class TestGMEndpointParameterValidation:
    """Parameter validation for GM tool endpoints."""

    def test_hooks_invalid_universe_id(self):
        """Invalid universe_id returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/gm/hooks",
            json={"universe_id": "not-a-uuid", "max_hooks": 5},
        )
        assert response.status_code == 422

    def test_hooks_max_hooks_too_high(self):
        """max_hooks > 20 returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/gm/hooks",
            json={"universe_id": str(uuid4()), "max_hooks": 50},
        )
        assert response.status_code == 422

    def test_contradictions_invalid_universe_id(self):
        """Invalid universe_id returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/gm/contradictions",
            json={"universe_id": "invalid"},
        )
        assert response.status_code == 422

    def test_session_prep_invalid_universe_id(self):
        """Invalid universe_id returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/gm/session-prep",
            json={"universe_id": "invalid", "story_id": str(uuid4())},
        )
        assert response.status_code == 422

    def test_session_prep_invalid_story_id(self):
        """Invalid story_id returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/gm/session-prep",
            json={"universe_id": str(uuid4()), "story_id": "not-a-uuid"},
        )
        assert response.status_code == 422