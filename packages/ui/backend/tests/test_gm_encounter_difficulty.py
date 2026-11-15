"""CF-13 — the encounter difficulty route.

"Is this fight fair?" is the question the prep panel asks. The route
answers it with arithmetic and shows its working.

Use Cases: CF-13 (G06)
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from monitor_ui.main import app
from tests.behavior._hermetic_stack import HermeticStack

client = TestClient(app)

_local_auth = pytest.mark.usefixtures("local_auth_mode")


@pytest.fixture
def hermetic(monkeypatch: pytest.MonkeyPatch) -> Any:
    stack = HermeticStack()
    stack.install(monkeypatch)
    try:
        yield stack
    finally:
        stack.uninstall()


def _body(foes: list[dict[str, Any]], party: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "universe_id": str(uuid4()),
        "foes": foes,
        "party": party,
    }


class TestEncounterCheckRoute:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_fair_fight_is_trivial(self, hermetic: HermeticStack) -> None:
        resp = client.post(
            "/api/gm/encounter/check",
            json=_body(
                [{"name": "Goblin", "count": 1, "hit_points": 7}],
                [{"name": "Mira", "level": 3, "hit_points": 24}] * 4,
            ),
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["label"] == "trivial"
        assert body["basis"] == "generic"
        assert "level-3 party of 4" in body["rationale"]

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_lopsided_fight_is_deadly(self, hermetic: HermeticStack) -> None:
        resp = client.post(
            "/api/gm/encounter/check",
            json=_body(
                [{"name": "Goblin", "count": 12, "hit_points": 7}],
                [{"name": "Mira", "level": 3, "hit_points": 24}] * 2,
            ),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["label"] == "deadly"

    @pytest.mark.usefixtures("local_auth_mode")
    def test_the_response_shows_the_working(self, hermetic: HermeticStack) -> None:
        resp = client.post(
            "/api/gm/encounter/check",
            json=_body(
                [{"name": "Ogre", "hit_points": 59}],
                [{"name": "Mira", "level": 3, "hit_points": 24}] * 4,
            ),
        )

        body = resp.json()
        assert body["party_budget"] == 96.0
        assert body["threat"] == 59.0
        assert body["ratio"] == pytest.approx(0.615, abs=1e-3)
        assert body["details"]["foe_count"] == 1

    @pytest.mark.usefixtures("local_auth_mode")
    def test_an_encounter_without_a_party_is_unrated(self, hermetic: HermeticStack) -> None:
        resp = client.post(
            "/api/gm/encounter/check",
            json=_body(
                [{"name": "Goblin", "hit_points": 7}],
                [{"name": "Mira", "level": 3, "hit_points": 0}],
            ),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["label"] == "unrated"
