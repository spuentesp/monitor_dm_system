"""Tests for the World Architect coverage endpoint (F2-1 wave 1)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi.testclient import TestClient
from monitor_data.schemas.coverage import CoverageSnapshot
from monitor_data.schemas.universe import UniverseResponse

from monitor_ui.main import app

client = TestClient(app)

_UNIVERSE_ID = UUID("123e4567-e89b-12d3-a456-426614174000")


def _universe() -> UniverseResponse:
    return UniverseResponse(
        id=_UNIVERSE_ID,
        name="Ashmar",
        description="A test world",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _coverage():
    from monitor_agents.utils.world_coverage import build_world_coverage

    return build_world_coverage(CoverageSnapshot(universe=_universe()))


def test_get_coverage_returns_structured_report():
    mock_compute = AsyncMock(return_value=_coverage())
    with (
        patch(
            "monitor_ui.routers.architect.neo4j_get_universe",
            return_value=_universe(),
        ),
        patch("monitor_agents.world_architect.agent.WorldArchitect") as mock_architect_cls,
    ):
        mock_architect_cls.return_value.compute_coverage = mock_compute
        response = client.get(f"/api/architect/{_UNIVERSE_ID}/coverage")

        assert response.status_code == 200
        body = response.json()
        assert body["universe_id"] == str(_UNIVERSE_ID)
        assert body["floor_met"] is False  # empty world: no axioms
        assert body["overall_status"] == "missing"
        for dimension in (
            "identity",
            "entity_taxonomy",
            "fact_taxonomy",
            "axioms",
            "relationships",
            "mechanics",
            "random_tables",
            "provenance",
        ):
            assert dimension in body
            assert body[dimension]["status"] in {"missing", "thin", "ok"}
            assert isinstance(body[dimension]["gaps"], list)
        assert body["axioms"]["total"] == 0

        # Default query flags: mechanics/tables not applicable.
        thresholds = mock_compute.await_args.kwargs["thresholds"]
        assert thresholds.require_mechanics is False
        assert thresholds.require_random_tables is False


def test_get_coverage_applicability_flags():
    mock_compute = AsyncMock(return_value=_coverage())
    with (
        patch(
            "monitor_ui.routers.architect.neo4j_get_universe",
            return_value=_universe(),
        ),
        patch("monitor_agents.world_architect.agent.WorldArchitect") as mock_architect_cls,
    ):
        mock_architect_cls.return_value.compute_coverage = mock_compute
        response = client.get(
            f"/api/architect/{_UNIVERSE_ID}/coverage?require_mechanics=true&require_random_tables=true"
        )
        assert response.status_code == 200
        thresholds = mock_compute.await_args.kwargs["thresholds"]
        assert thresholds.require_mechanics is True
        assert thresholds.require_random_tables is True


def test_get_coverage_unknown_universe_is_404():
    with patch(
        "monitor_ui.routers.architect.neo4j_get_universe",
        return_value=None,
    ):
        response = client.get(f"/api/architect/{_UNIVERSE_ID}/coverage")
        assert response.status_code == 404
