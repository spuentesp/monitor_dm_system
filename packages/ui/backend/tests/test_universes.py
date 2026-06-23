from unittest.mock import patch

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)


def test_get_universe_state_endpoint():
    with patch("monitor_ui.routers.universes.neo4j_get_universe_state") as mock_state:
        mock_state.return_value = {
            "entities": [],
            "facts": [],
            "axioms": [],
            "relationships": [],
        }
        # Router is mounted at /api/universes and defines /universes/... paths,
        # so the public path doubles the segment (matches frontend api.ts).
        response = client.get(
            "/api/universes/universes/123e4567-e89b-12d3-a456-426614174000/state"
        )
        assert response.status_code == 200
        assert "entities" in response.json()
