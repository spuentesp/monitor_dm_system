"""CF-15 — the knowledge inspector routes.

The GM opens a character and sees everything the system attributes to
them, with its provenance — and can challenge the attributions they doubt.
The challenge is staged as a CF-8 proposal; it never writes canon.

Use Cases: CF-15 (G09)
"""

from __future__ import annotations

from datetime import UTC, datetime
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


def _memory(stack: HermeticStack, entity_id, universe_id, **over) -> dict[str, Any]:
    doc = {
        "memory_id": str(uuid4()),
        "universe_id": str(universe_id),
        "entity_id": str(entity_id),
        "text": "The council met at dusk without Mira.",
        "scene_id": str(uuid4()),
        "importance": 0.4,
        "certainty": 1.0,
        "emotional_valence": 0.0,
        "witnesses": [str(entity_id)],
        "linked_fact_id": None,
        "created_at": datetime.now(UTC),
    }
    doc.update(over)
    stack.collection("character_memories").insert_one(doc)
    return doc


class TestKnowledgeAuditRoute:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_the_audit_lists_what_the_character_knows(
        self, hermetic: HermeticStack
    ) -> None:
        universe_id = uuid4()
        entity_id = uuid4()
        _memory(hermetic, entity_id, universe_id)

        resp = client.get(
            f"/api/gm/knowledge/{entity_id}",
            params={"universe_id": str(universe_id)},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["entity_id"] == str(entity_id)
        assert body["memory_count"] == 1
        assert body["items"][0]["statement"] == "The council met at dusk without Mira."
        assert body["items"][0]["source"] == "memory"

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_doubtful_attribution_is_marked(self, hermetic: HermeticStack) -> None:
        universe_id = uuid4()
        entity_id = uuid4()
        _memory(hermetic, entity_id, universe_id, certainty=0.2, importance=0.9)

        resp = client.get(
            f"/api/gm/knowledge/{entity_id}",
            params={"universe_id": str(universe_id)},
        )

        body = resp.json()
        assert body["suspicious_count"] == 1
        assert body["items"][0]["suspicious"] is True
        assert body["items"][0]["suspicion_reason"]

    @pytest.mark.usefixtures("local_auth_mode")
    def test_an_unknown_character_has_an_empty_audit(self, hermetic: HermeticStack) -> None:
        resp = client.get(
            f"/api/gm/knowledge/{uuid4()}",
            params={"universe_id": str(uuid4())},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == []
        assert resp.json()["memory_count"] == 0


class TestKnowledgeChallengeRoute:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_challenge_stages_a_proposal(self, hermetic: HermeticStack) -> None:
        universe_id = uuid4()
        entity_id = uuid4()
        story_id = uuid4()
        scene_id = uuid4()
        _memory(hermetic, entity_id, universe_id)
        hermetic.seed(
            "scenes",
            [
                {
                    "scene_id": str(scene_id),
                    "story_id": str(story_id),
                    "universe_id": str(universe_id),
                    "title": "The council",
                    "purpose": "Attend the council.",
                    "status": "active",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            ],
        )

        resp = client.post(
            f"/api/gm/knowledge/{entity_id}/challenge",
            json={
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "scene_id": str(scene_id),
                "item_id": "memory-1",
                "item_kind": "memory",
                "statement": "Mira was not at the council.",
                "reason": "She was at the docks that night.",
                "action": "retract",
            },
        )

        assert resp.status_code == 200, resp.text
        proposal_id = resp.json()["proposal_id"]
        assert proposal_id

        staged = hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})
        assert staged is not None
        assert staged["status"] == "pending"
        assert staged["content"]["knowledge_correction"]["action"] == "retract"
        assert staged["content"]["knowledge_correction"]["reason"].startswith("She was at")

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_challenge_without_a_scope_is_refused(self, hermetic: HermeticStack) -> None:
        resp = client.post(
            f"/api/gm/knowledge/{uuid4()}/challenge",
            json={
                "universe_id": str(uuid4()),
                "item_id": "memory-1",
                "item_kind": "memory",
                "statement": "Mira was not there.",
                "reason": "She was elsewhere.",
            },
        )

        assert resp.status_code == 422
        assert hermetic.collection("proposed_changes").count_documents({}) == 0
