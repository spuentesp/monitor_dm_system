"""G08 — the CF-8 accept path refuses a contradiction silently.

A proposal that contradicts canon used to be accepted without a word. Now:
a proposal carrying a direct-contradiction flag needs an explicit override
reason, the override is audited, and an owner in hard-rejection mode gets a
flat refusal instead.

The canon check itself is stubbed here — it is measured by
``scripts/eval_canonkeeper_recall.py``, not by a route test.

Use Cases: CF-5, CF-8 (G08)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from monitor_data.schemas.base import ProposalType
from monitor_data.schemas.proposed_changes import ProposedChangeCreate
from monitor_ui.main import app
from tests.behavior._hermetic_stack import HermeticStack

client = TestClient(app)

_local_auth = pytest.mark.usefixtures("local_auth_mode")


@pytest.fixture
def hermetic(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The hermetic stack, installed for the duration of the test."""
    stack = HermeticStack()
    stack.install(monkeypatch)
    try:
        yield stack
    finally:
        stack.uninstall()


def _pending_proposal(
    hermetic: HermeticStack,
    *,
    statement: str = "Mira Vale opened the sealed door.",
    universe_id: UUID | None = None,
    scene_id: UUID | None = None,
    flags: list[dict[str, Any]] | None = None,
) -> str:
    """A pending proposal in the queue, optionally carrying review flags."""
    from monitor_data.tools.mongodb_tools.proposals import mongodb_create_proposed_change

    universe_id = universe_id or uuid4()
    scene_id = scene_id or uuid4()
    hermetic.seed(
        "scenes",
        [
            {
                "scene_id": str(scene_id),
                "story_id": str(uuid4()),
                "universe_id": str(universe_id),
                "title": "The sealed door",
                "purpose": "Advance the harbour investigation.",
                "status": "active",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ],
    )
    created = mongodb_create_proposed_change(
        ProposedChangeCreate(
            scene_id=scene_id,
            change_type=ProposalType.FACT,
            content={"statement": statement, "universe_id": str(universe_id)},
            authority="gm",
            proposer="Test",
            source="capture_entry:entry-1",
        )
    )
    if flags:
        from monitor_data.tools.mongodb_tools.proposals import (
            mongodb_flag_proposal_review,
        )

        mongodb_flag_proposal_review(
            created.proposal_id,
            needs_review=True,
            reason=flags[0].get("explanation", "Contradicts established canon."),
            source=flags[0].get("kind", "direct_contradiction"),
            flags=flags,
        )
    return str(created.proposal_id)


def _direct_flag() -> dict[str, Any]:
    return {
        "kind": "direct_contradiction",
        "severity": "high",
        "explanation": "Mira Vale is a courier for the Grey Line; this says otherwise.",
        "implications": "",
        "rule": "",
        "detected_at": datetime.now(UTC).isoformat(),
    }


def _stub_check(monkeypatch: pytest.MonkeyPatch, flags: list[dict[str, Any]]) -> list[Any]:
    """Make the canon check return the given findings."""
    from monitor_agents.canonkeeper.agent import CanonKeeper

    async def _flags(self: Any, universe_id: UUID, statements: list[str]) -> list[dict[str, Any]]:
        return [
            {
                "statement": statements[0] if statements else "",
                "explanation": flag.get("explanation", ""),
                "implications": "",
                "contradiction_type": "semantic_opposite",
                "severity": "high",
                "flag_kind": flag.get("kind", "direct_contradiction"),
            }
            for flag in flags
        ]

    monkeypatch.setattr(CanonKeeper, "direct_contradiction_flags", _flags)
    return flags


@pytest.mark.usefixtures("local_auth_mode")
def test_batch_accept_does_not_bypass_contradiction(hermetic: HermeticStack) -> None:
    proposal_id = _pending_proposal(hermetic, flags=[_direct_flag()])
    response = client.post("/api/canon-review/verdicts", json={
        "items": [{"proposal_id": proposal_id, "decision": "accepted", "reason": "Approve"}]
    })
    assert response.status_code == 200
    assert response.json()["results"] == []
    assert "override reason" in response.json()["errors"][0]["error"]
    assert hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})["status"] == "pending"


@pytest.mark.usefixtures("local_auth_mode")
def test_filtered_accept_does_not_bypass_contradiction(hermetic: HermeticStack) -> None:
    scene_id = uuid4()
    proposal_id = _pending_proposal(hermetic, scene_id=scene_id, flags=[_direct_flag()])
    body = {"scene_id": str(scene_id), "decision": "accepted", "reason": "Approve", "dry_run": True}
    preview = client.post("/api/canon-review/verdicts/by-filter", json=body)
    assert preview.status_code == 200, preview.text
    body.update(dry_run=False, preview_token=preview.json()["preview_token"])
    response = client.post("/api/canon-review/verdicts/by-filter", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["results"] == []
    assert "override reason" in response.json()["errors"][0]["error"]
    assert hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})["status"] == "pending"


@pytest.mark.usefixtures("local_auth_mode")
def test_accepted_fact_challenge_changes_character_visibility(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monitor_agents.canonkeeper.agent import CanonKeeper
    from monitor_agents.cast import fact_visible_to

    proposal_id = _pending_proposal(hermetic)
    character_id, other_id, universe_id, fact_id = (str(uuid4()) for _ in range(4))
    fact = {"id": fact_id, "universe_id": universe_id, "statement": "The gate opened", "properties": {}}

    async def call_tool(self, name, args):
        if name == "neo4j_get_entity":
            return {"id": character_id, "universe_id": universe_id}
        if name == "neo4j_get_fact":
            return fact
        if name == "neo4j_update_fact":
            fact.update(args["params"])
            return fact
        raise AssertionError(name)

    monkeypatch.setattr(CanonKeeper, "call_tool", call_tool)
    hermetic.collection("proposed_changes").update_one(
        {"proposal_id": proposal_id}, {"$set": {"content": {
            "universe_id": universe_id, "participants": [character_id], "statement": fact["statement"],
            "knowledge_correction": {"action": "retract", "item_kind": "fact", "item_id": fact_id},
        }}}
    )
    response = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 200, response.text
    assert hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})["knowledge_correction_applied"] is True
    assert not fact_visible_to(fact, character_id)
    assert fact_visible_to(fact, other_id)


@pytest.mark.usefixtures("local_auth_mode")
def test_stale_fact_challenge_does_not_change_new_canon(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monitor_agents.canonkeeper.agent import CanonKeeper

    proposal_id = _pending_proposal(hermetic)
    character_id, universe_id, fact_id = (str(uuid4()) for _ in range(3))
    fact = {"id": fact_id, "universe_id": universe_id, "statement": "The gate is sealed", "properties": {}}
    calls = []

    async def call_tool(self, name, args):
        calls.append(name)
        if name == "neo4j_get_entity":
            return {"id": character_id, "universe_id": universe_id}
        if name == "neo4j_get_fact":
            return fact
        raise AssertionError(name)

    monkeypatch.setattr(CanonKeeper, "call_tool", call_tool)
    hermetic.collection("proposed_changes").update_one({"proposal_id": proposal_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": "The gate opened",
        "knowledge_correction": {"action": "retract", "item_kind": "fact", "item_id": fact_id,
                                 "original_statement": "The gate opened"},
    }}})
    response = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 409
    assert "changed after" in response.json()["detail"]
    assert "neo4j_update_fact" not in calls
    assert hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})["status"] == "pending"


@pytest.mark.usefixtures("local_auth_mode")
def test_old_correction_without_original_text_must_be_restaged(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monitor_agents.canonkeeper.agent import CanonKeeper

    proposal_id = _pending_proposal(hermetic)
    character_id, universe_id, fact_id = (str(uuid4()) for _ in range(3))
    hermetic.collection("proposed_changes").update_one({"proposal_id": proposal_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": "New statement",
        "knowledge_correction": {"action": "correct", "item_kind": "fact", "item_id": fact_id},
    }}})
    async def call_tool(self, name, args):
        if name == "neo4j_get_entity":
            return {"id": character_id, "universe_id": universe_id}
        raise AssertionError(name)

    async def no_flags(proposal):
        return []

    monkeypatch.setattr(CanonKeeper, "call_tool", call_tool)
    monkeypatch.setattr("monitor_ui.routers.canon_review._resolve_review_flags", no_flags)
    response = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 409
    assert "restage" in response.json()["detail"]
    assert hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})["status"] == "pending"


@pytest.mark.usefixtures("local_auth_mode")
@pytest.mark.parametrize("malformed", [None, {}, "invalid"])
def test_malformed_correction_cannot_be_accepted_as_an_ordinary_fact(
    hermetic: HermeticStack, malformed: Any
) -> None:
    proposal_id = _pending_proposal(hermetic)
    hermetic.collection("proposed_changes").update_one(
        {"proposal_id": proposal_id}, {"$set": {"content.knowledge_correction": malformed}}
    )
    response = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 409
    assert hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})["status"] == "pending"


@pytest.mark.usefixtures("local_auth_mode")
def test_fact_challenge_uses_registered_mcp_tools(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monitor_agents.cast import fact_visible_to
    from monitor_data.tools.neo4j_tools import entities, facts

    proposal_id = _pending_proposal(hermetic)
    character_id, universe_id, fact_id = (str(uuid4()) for _ in range(3))
    now = datetime.now(UTC)
    entity = {"id": character_id, "universe_id": universe_id, "name": "Mira", "entity_type": "character",
              "is_archetype": False, "description": "", "canon_level": "canon", "confidence": 1.0,
              "authority": "gm", "created_at": now}
    fact = {"id": fact_id, "universe_id": universe_id, "statement": "The door opened", "fact_type": "state",
            "canon_level": "canon", "confidence": 1.0, "authority": "gm", "created_at": now}

    class Graph:
        def execute_read(self, query, params):
            if "MATCH (n:Fact" in query:
                return [{"id": fact_id}]
            if "MATCH (e:Entity" in query:
                return [{"e": entity, "archetype_id": None}]
            if "MATCH (f:Fact" in query:
                return [{"f": fact, "entity_ids": [], "source_ids": [], "scene_ids": []}]
            raise AssertionError(query)

        def execute_write(self, query, params):
            fact["properties"] = params["properties"]
            return []

    graph = Graph()
    monkeypatch.setattr(entities, "get_neo4j_client", lambda: graph)
    monkeypatch.setattr(facts, "get_neo4j_client", lambda: graph)
    hermetic.collection("proposed_changes").update_one({"proposal_id": proposal_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": fact["statement"],
        "knowledge_correction": {"action": "retract", "item_kind": "fact", "item_id": fact_id},
    }}})
    response = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 200, response.text
    stored = facts.neo4j_get_fact(UUID(fact_id))
    assert stored is not None
    assert not fact_visible_to(stored.model_dump(mode="json"), character_id)
    assert hermetic.called("neo4j_update_fact")


@pytest.mark.usefixtures("local_auth_mode")
def test_accepted_memory_challenge_removes_memory_and_vector(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal_id = _pending_proposal(hermetic)
    character_id, universe_id, memory_id = (str(uuid4()) for _ in range(3))
    now = datetime.now(UTC)
    hermetic.collection("character_memories").insert_one({
        "memory_id": memory_id, "entity_id": character_id, "universe_id": universe_id,
        "text": "The door opened", "importance": 0.5, "certainty": 1.0,
        "emotional_valence": 0.0, "metadata": {}, "created_at": now,
        "last_accessed": now, "access_count": 0,
    })
    vectors = {memory_id}

    hermetic.override("neo4j_get_entity", {"id": character_id, "universe_id": universe_id})
    def delete_vector(params):
        vectors.discard(params["id"])
        return {"success": True}
    hermetic.override("qdrant_delete", delete_vector)
    hermetic.collection("proposed_changes").update_one({"proposal_id": proposal_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": "The door opened",
        "knowledge_correction": {"action": "retract", "item_kind": "memory", "item_id": memory_id},
    }}})
    response = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 200, response.text
    assert hermetic.collection("character_memories").find_one({"memory_id": memory_id}) is None
    assert not vectors
    assert hermetic.called("mongodb_get_memory")
    assert hermetic.called("mongodb_delete_memory")


@pytest.mark.usefixtures("local_auth_mode")
def test_accepted_memory_correction_updates_text_and_embedding(hermetic: HermeticStack) -> None:
    proposal_id = _pending_proposal(hermetic)
    character_id, universe_id, memory_id = (str(uuid4()) for _ in range(3))
    now = datetime.now(UTC)
    hermetic.collection("character_memories").insert_one({
        "memory_id": memory_id, "entity_id": character_id, "universe_id": universe_id,
        "text": "The door opened", "importance": 0.5, "certainty": 1.0,
        "emotional_valence": 0.0, "metadata": {}, "created_at": now,
        "last_accessed": now, "access_count": 0,
    })
    hermetic.override("neo4j_get_entity", {"id": character_id, "universe_id": universe_id})
    embeddings = {}
    def embed(params):
        embeddings[params["memory_id"]] = params["text"]
        return {"success": True}
    hermetic.override("qdrant_embed_memory", embed)
    hermetic.collection("proposed_changes").update_one({"proposal_id": proposal_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": "The door stayed shut",
        "knowledge_correction": {"action": "correct", "item_kind": "memory", "item_id": memory_id,
                                 "original_statement": "The door opened"},
    }}})
    response = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 200, response.text
    assert hermetic.collection("character_memories").find_one({"memory_id": memory_id})["text"] == "The door stayed shut"
    assert embeddings[memory_id] == "The door stayed shut"
    assert hermetic.called("mongodb_update_memory")


@pytest.mark.usefixtures("local_auth_mode")
def test_memory_retraction_can_retry_after_verdict_write_fails(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monitor_ui.routers import canon_review

    proposal_id = _pending_proposal(hermetic)
    character_id, universe_id, memory_id = (str(uuid4()) for _ in range(3))
    now = datetime.now(UTC)
    hermetic.collection("character_memories").insert_one({
        "memory_id": memory_id, "entity_id": character_id, "universe_id": universe_id,
        "text": "The door opened", "importance": 0.5, "certainty": 1.0,
        "emotional_valence": 0.0, "metadata": {}, "created_at": now,
        "last_accessed": now, "access_count": 0,
    })
    hermetic.override("neo4j_get_entity", {"id": character_id, "universe_id": universe_id})
    hermetic.override("qdrant_delete", {"success": True})
    hermetic.collection("proposed_changes").update_one({"proposal_id": proposal_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": "The door opened",
        "knowledge_correction": {"action": "retract", "item_kind": "memory", "item_id": memory_id},
    }}})
    original_update = canon_review.mongodb_update_proposed_change
    attempts = 0
    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("simulated verdict write failure")
        return original_update(*args, **kwargs)
    monkeypatch.setattr(canon_review, "mongodb_update_proposed_change", fail_once)

    first = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert first.status_code == 409
    assert hermetic.collection("character_memories").find_one({"memory_id": memory_id}) is None
    assert hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})["status"] == "pending"
    reject = client.post(f"/api/canon-review/{proposal_id}/reject", params={"reason": "Changed mind"})
    assert reject.status_code == 409
    edit = client.post(f"/api/canon-review/{proposal_id}/edit", json={"content_patch": {"statement": "Changed"}})
    assert edit.status_code == 409
    second = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "accepted"


@pytest.mark.usefixtures("local_auth_mode")
def test_memory_checkpoint_rejects_a_concurrently_edited_proposal(hermetic: HermeticStack) -> None:
    from monitor_data.tools.mongodb_tools.proposals import prepare_knowledge_memory_change

    proposal_id = _pending_proposal(hermetic)
    character_id, universe_id, memory_id = (str(uuid4()) for _ in range(3))
    content = {"universe_id": universe_id, "participants": [character_id], "statement": "Old",
               "knowledge_correction": {"action": "retract", "item_kind": "memory", "item_id": memory_id}}
    proposals = hermetic.collection("proposed_changes")
    proposals.update_one({"proposal_id": proposal_id}, {"$set": {"content": {**content, "statement": "New"}}})
    with pytest.raises(ValueError, match="proposal changed"):
        prepare_knowledge_memory_change(UUID(proposal_id), content)
    assert "knowledge_retraction_checkpoint" not in proposals.find_one({"proposal_id": proposal_id})


@pytest.mark.usefixtures("local_auth_mode")
def test_memory_correction_can_retry_after_store_and_verdict_failures(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monitor_agents.canonkeeper.agent import CanonKeeper
    from monitor_ui.routers import canon_review

    proposal_id = _pending_proposal(hermetic)
    character_id, universe_id, memory_id = (str(uuid4()) for _ in range(3))
    now = datetime.now(UTC)
    memories = hermetic.collection("character_memories")
    memories.insert_one({
        "memory_id": memory_id, "entity_id": character_id, "universe_id": universe_id,
        "text": "The door opened", "importance": 0.5, "certainty": 1.0,
        "emotional_valence": 0.0, "metadata": {}, "created_at": now,
        "last_accessed": now, "access_count": 0,
    })
    hermetic.override("neo4j_get_entity", {"id": character_id, "universe_id": universe_id})
    hermetic.override("qdrant_embed_memory", {"success": True})
    hermetic.collection("proposed_changes").update_one({"proposal_id": proposal_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": "The door stayed shut",
        "knowledge_correction": {"action": "correct", "item_kind": "memory", "item_id": memory_id,
                                 "original_statement": "The door opened"},
    }}})
    original_call = CanonKeeper.call_tool
    original_update = canon_review.mongodb_update_proposed_change
    calls = {"memory": 0, "verdict": 0}

    async def fail_memory_once(self, name, arguments):
        if name == "mongodb_update_memory":
            calls["memory"] += 1
            if calls["memory"] == 1:
                raise RuntimeError("simulated memory write failure")
        return await original_call(self, name, arguments)

    def fail_verdict_once(*args, **kwargs):
        if args[1].status.value == "accepted":
            calls["verdict"] += 1
            if calls["verdict"] == 1:
                raise ValueError("simulated verdict write failure")
        return original_update(*args, **kwargs)

    monkeypatch.setattr(CanonKeeper, "call_tool", fail_memory_once)
    monkeypatch.setattr(canon_review, "mongodb_update_proposed_change", fail_verdict_once)
    url = f"/api/canon-review/{proposal_id}/accept"
    first = client.post(url, params={"reason": "Approve"})
    assert first.status_code == 503
    assert memories.find_one({"memory_id": memory_id})["text"] == "The door opened"
    assert client.post(f"/api/canon-review/{proposal_id}/reject", params={"reason": "Stop"}).status_code == 409
    second = client.post(url, params={"reason": "Approve"})
    assert second.status_code == 409
    assert memories.find_one({"memory_id": memory_id})["text"] == "The door stayed shut"
    third = client.post(url, params={"reason": "Approve"})
    assert third.status_code == 200, third.text
    assert third.json()["status"] == "accepted"


@pytest.mark.usefixtures("local_auth_mode")
def test_accepted_proposal_challenge_updates_target_attribution(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monitor_agents.canonkeeper.agent import CanonKeeper
    from monitor_agents.cast import fact_visible_to
    from monitor_data.tools.mongodb_tools.proposals import mongodb_edit_proposed_change, mongodb_get_proposed_change

    character_id, universe_id = str(uuid4()), str(uuid4())
    target_id = _pending_proposal(hermetic)
    correction_id = _pending_proposal(hermetic)
    hermetic.collection("proposed_changes").update_one({"proposal_id": target_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": "The door opened"
    }}})
    hermetic.collection("proposed_changes").update_one({"proposal_id": correction_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": "The door opened",
        "knowledge_correction": {"action": "retract", "item_kind": "proposal", "item_id": target_id},
    }}})

    async def call_tool(self, name, args):
        if name == "neo4j_get_entity":
            return {"id": character_id, "universe_id": universe_id}
        if name == "mongodb_get_proposed_change":
            return mongodb_get_proposed_change(UUID(args["proposal_id"])).model_dump(mode="json")
        if name == "mongodb_edit_proposed_change":
            return mongodb_edit_proposed_change(UUID(args["proposal_id"]), args["content_patch"], args["reason"]).model_dump(mode="json")
        raise AssertionError(name)

    monkeypatch.setattr(CanonKeeper, "call_tool", call_tool)
    response = client.post(f"/api/canon-review/{correction_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 200, response.text
    target = hermetic.collection("proposed_changes").find_one({"proposal_id": target_id})
    assert target["status"] == "pending"
    assert not fact_visible_to(target["content"], character_id)


@pytest.mark.usefixtures("local_auth_mode")
def test_failed_knowledge_correction_remains_pending(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monitor_agents.canonkeeper.agent import CanonKeeper

    proposal_id = _pending_proposal(hermetic)
    universe_id, character_id, memory_id = (str(uuid4()) for _ in range(3))
    hermetic.collection("character_memories").insert_one({
        "memory_id": memory_id, "entity_id": character_id, "universe_id": universe_id, "text": "A memory",
    })
    hermetic.collection("proposed_changes").update_one({"proposal_id": proposal_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": "A memory",
        "knowledge_correction": {"action": "retract", "item_kind": "memory", "item_id": memory_id},
    }}})

    async def call_tool(self, name, args):
        if name == "neo4j_get_entity":
            return {"id": character_id, "universe_id": universe_id}
        if name == "mongodb_get_memory":
            return {"memory_id": memory_id, "entity_id": character_id, "universe_id": universe_id, "text": "A memory"}
        if name == "qdrant_delete":
            raise RuntimeError("vector store unavailable")
        raise AssertionError(name)

    monkeypatch.setattr(CanonKeeper, "call_tool", call_tool)
    response = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 503
    assert hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})["status"] == "pending"


@pytest.mark.usefixtures("local_auth_mode")
def test_missing_character_does_not_lock_memory_challenge(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monitor_agents.canonkeeper.agent import CanonKeeper

    proposal_id = _pending_proposal(hermetic)
    universe_id, character_id, memory_id = (str(uuid4()) for _ in range(3))
    hermetic.collection("character_memories").insert_one({
        "memory_id": memory_id, "entity_id": character_id, "universe_id": universe_id,
    })
    hermetic.collection("proposed_changes").update_one({"proposal_id": proposal_id}, {"$set": {"content": {
        "universe_id": universe_id, "participants": [character_id], "statement": "A memory",
        "knowledge_correction": {"action": "retract", "item_kind": "memory", "item_id": memory_id},
    }}})

    async def call_tool(self, name, args):
        assert name == "neo4j_get_entity"
        return None

    monkeypatch.setattr(CanonKeeper, "call_tool", call_tool)
    response = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 409
    proposal = hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})
    assert "knowledge_retraction_checkpoint" not in proposal
    rejected = client.post(f"/api/canon-review/{proposal_id}/reject", params={"reason": "Missing character"})
    assert rejected.status_code == 200


@pytest.mark.usefixtures("local_auth_mode")
def test_advisory_flag_does_not_suppress_direct_check(
    hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_check(monkeypatch, [_direct_flag()])
    advisory = {**_direct_flag(), "kind": "implication_contradiction"}
    proposal_id = _pending_proposal(hermetic, flags=[advisory])
    response = client.post(f"/api/canon-review/{proposal_id}/accept", params={"reason": "Approve"})
    assert response.status_code == 409
    stored = hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})
    assert {flag["kind"] for flag in stored["review_flags"]} == {
        "implication_contradiction", "direct_contradiction"
    }


class TestSoftBlock:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_flagged_proposal_needs_an_override_reason(
        self, hermetic: HermeticStack
    ) -> None:
        proposal_id = _pending_proposal(hermetic, flags=[_direct_flag()])

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Looks fine to me."},
        )

        assert resp.status_code == 409
        assert "override reason" in resp.json()["detail"]

    @pytest.mark.usefixtures("local_auth_mode")
    def test_an_override_accepts_the_proposal(
        self, hermetic: HermeticStack
    ) -> None:
        proposal_id = _pending_proposal(hermetic, flags=[_direct_flag()])

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={
                "reason": "The fiction changed on purpose.",
                "override_reason": "Mira left the Grey Line last night — on purpose.",
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["decision_metadata"]["override_reason"] == (
            "Mira left the Grey Line last night — on purpose."
        )

    @pytest.mark.usefixtures("local_auth_mode")
    def test_the_override_is_audited(self, hermetic: HermeticStack) -> None:
        proposal_id = _pending_proposal(hermetic, flags=[_direct_flag()])

        client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={
                "reason": "On purpose.",
                "override_reason": "The fiction changed.",
            },
        )

        audit = list(hermetic.collection("canon_override_audit").find({}))
        assert len(audit) == 1
        assert audit[0]["proposal_id"] == proposal_id
        assert audit[0]["reason"] == "The fiction changed."
        assert audit[0]["flag_kinds"] == ["direct_contradiction"]

    @pytest.mark.usefixtures("local_auth_mode")
    def test_an_unflagged_proposal_is_accepted_as_before(
        self, hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_check(monkeypatch, [])
        proposal_id = _pending_proposal(hermetic)

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Confirmed at the table."},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "accepted"
        assert resp.json()["decision_metadata"]["override_reason"] is None
        assert hermetic.collection("canon_override_audit").count_documents({}) == 0

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_contradiction_found_now_stamps_the_proposal(
        self, hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The check runs at the decision point, so a late conflict is caught."""
        _stub_check(monkeypatch, [_direct_flag()])
        proposal_id = _pending_proposal(hermetic)

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Looks fine to me."},
        )

        assert resp.status_code == 409
        stored = hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})
        assert stored is not None
        assert stored["needs_review"] is True
        assert stored["review_flags"][0]["kind"] == "direct_contradiction"

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_failed_check_never_blocks_an_acceptance(
        self, hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from monitor_agents.canonkeeper.agent import CanonKeeper

        async def _boom(self: Any, universe_id: UUID, statements: list[str]) -> list[dict[str, Any]]:
            raise RuntimeError("the model is down")

        monkeypatch.setattr(CanonKeeper, "direct_contradiction_flags", _boom)
        proposal_id = _pending_proposal(hermetic)

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Confirmed at the table."},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "accepted"


class TestHardRejection:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_hard_mode_refuses_a_flagged_proposal(
        self, hermetic: HermeticStack, local_auth_mode: Any
    ) -> None:
        import monitor_ui.routers.canon_review as canon_review

        async def _hard(db: Any, principal: Any) -> dict[str, Any]:
            return {"hard_rejection": True}

        original = canon_review._owner_canon_settings
        canon_review._owner_canon_settings = _hard  # type: ignore[assignment]
        try:
            proposal_id = _pending_proposal(hermetic, flags=[_direct_flag()])

            resp = client.post(
                f"/api/canon-review/{proposal_id}/accept",
                params={
                    "reason": "On purpose.",
                    "override_reason": "The fiction changed.",
                },
            )
        finally:
            canon_review._owner_canon_settings = original  # type: ignore[assignment]

        assert resp.status_code == 409
        assert "hard rejection is on" in resp.json()["detail"]
        # The proposal is untouched.
        stored = hermetic.collection("proposed_changes").find_one(
            {"proposal_id": proposal_id}
        )
        assert stored is not None
        assert stored["status"] == "pending"

    @pytest.mark.usefixtures("local_auth_mode")
    def test_hard_mode_leaves_unflagged_proposals_alone(
        self, hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import monitor_ui.routers.canon_review as canon_review

        async def _hard(db: Any, principal: Any) -> dict[str, Any]:
            return {"hard_rejection": True}

        monkeypatch.setattr(canon_review, "_owner_canon_settings", _hard)
        _stub_check(monkeypatch, [])
        proposal_id = _pending_proposal(hermetic)

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Confirmed at the table."},
        )

        assert resp.status_code == 200, resp.text
