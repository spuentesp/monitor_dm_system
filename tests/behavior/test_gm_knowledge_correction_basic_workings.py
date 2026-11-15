"""
Basic workings — character-knowledge corrections (G08/G09, CF-5/CF-8/CF-15).

The rule verified here, end to end on the hermetic stack: a challenged
attribution can be retracted or corrected, and the correction lands in
every store the character's knowledge is read from — MongoDB, Qdrant, fact
visibility, and the pending-proposal queue. It lands completely or not at
all: an accept cut off mid-write is finished by the auto-reconciler rather
than left half-applied, and a changed attribution is refused instead of
applied over.

Use Cases: CF-5, CF-8, CF-15
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from monitor_agents.knowledge_audit import KnowledgeAuditAgent
from monitor_agents.cast import fact_visible_to
from monitor_data.db import redis as redis_module
from monitor_data.schemas.base import ProposalType
from monitor_data.schemas.knowledge_audit import (
    KnowledgeAudit,
    KnowledgeAuditFilter,
    KnowledgeChallenge,
    KnowledgeItem,
)
from monitor_data.schemas.proposed_changes import ProposedChangeCreate
from monitor_data.tools.mongodb_tools.knowledge_audit import mongodb_list_knowledge_audit
from monitor_data.tools.mongodb_tools.proposals import mongodb_create_proposed_change
from monitor_ui.auth import LOCAL_USER_ID, Principal
from tests.behavior._hermetic_stack import HermeticStack


class _Preferences:
    """The owner-settings surface accept_proposal reads (local mode)."""

    async def pref_get(self, user_id: Any, key: str) -> dict[str, Any]:
        return {}


class _NoCache:
    def delete_prefix(self, prefix: str) -> int:
        return 0


@pytest.fixture
def principal() -> Principal:
    return Principal(LOCAL_USER_ID, True, "local")


@pytest.fixture(autouse=True)
def _quiet_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(redis_module, "get_redis_client", lambda: _NoCache())


@pytest.fixture
def character_id() -> str:
    return str(uuid4())


@pytest.fixture
def universe_id() -> str:
    return str(uuid4())


@pytest.fixture
def scene_id(hermetic: HermeticStack) -> str:
    scene = str(uuid4())
    now = datetime.now(UTC)
    hermetic.seed(
        "scenes",
        [{"scene_id": scene, "story_id": str(uuid4()), "universe_id": str(uuid4()),
          "title": "The sealed door", "status": "active", "created_at": now, "updated_at": now}],
    )
    return scene


def _memory(hermetic: HermeticStack, memory_id: str, character_id: str, universe_id: str, text: str) -> None:
    now = datetime.now(UTC)
    hermetic.collection("character_memories").insert_one({
        "memory_id": memory_id, "entity_id": character_id, "universe_id": universe_id,
        "text": text, "importance": 0.5, "certainty": 1.0,
        "emotional_valence": 0.0, "metadata": {}, "created_at": now,
        "last_accessed": now, "access_count": 0,
    })


def _stage(
    scene_id: str,
    character_id: str,
    universe_id: str,
    correction: dict[str, Any],
    *,
    statement: str = "The door opened",
) -> str:
    """A staged CF-8 correction proposal, as KnowledgeAuditAgent writes it."""
    content: dict[str, Any] = {
        "statement": statement,
        "participants": [character_id],
        "knowledge_correction": correction,
        "universe_id": universe_id,
    }
    created = mongodb_create_proposed_change(
        ProposedChangeCreate(
            scene_id=UUID(scene_id),
            change_type=ProposalType.FACT,
            content=content,
            confidence=1.0,
            authority="gm",
            proposer="KnowledgeAuditAgent",
            source=f"knowledge_challenge:{character_id}",
            proposal_type=f"knowledge_{correction['action']}",
        )
    )
    return str(created.proposal_id)


def _audit(character_id: str, universe_id: str) -> KnowledgeAudit:
    """The audit as a consumer reads it (facts come from the graph)."""
    from monitor_data.tools.neo4j_tools import facts as facts_module

    original = getattr(facts_module, "neo4j_list_facts", None)
    facts_module.neo4j_list_facts = lambda filters=None: []
    try:
        return mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=UUID(character_id), universe_id=UUID(universe_id))
        )
    finally:
        facts_module.neo4j_list_facts = original


class TestChallengeStaging:
    @pytest.mark.asyncio
    async def test_a_challenge_records_the_original_statement_and_stages_the_proposal(
        self, hermetic: HermeticStack, character_id: str, universe_id: str, scene_id: str
    ) -> None:
        memory_id = str(uuid4())
        hermetic.override(
            "mongodb_list_knowledge_audit",
            KnowledgeAudit(
                entity_id=UUID(character_id),
                universe_id=UUID(universe_id),
                items=[KnowledgeItem(id=memory_id, kind="memory", statement="The door opened", source="memory")],
                memory_count=1,
            ).model_dump(mode="json"),
        )
        proposal_id = await KnowledgeAuditAgent().challenge(
            UUID(character_id),
            UUID(universe_id),
            KnowledgeChallenge(
                item_id=memory_id, kind="memory", statement="The door opened",
                reason="The GM doubts this attribution.", action="retract",
            ),
            scene_id=UUID(scene_id),
        )
        proposal = hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})
        assert proposal["status"] == "pending"
        correction = proposal["content"]["knowledge_correction"]
        assert correction["action"] == "retract"
        assert correction["item_id"] == memory_id
        assert correction["original_statement"] == "The door opened"


class TestMemoryRetraction:
    @pytest.mark.asyncio
    async def test_a_retracted_memory_disappears_from_mongo_and_the_vector_store(
        self,
        hermetic: HermeticStack,
        principal: Principal,
        character_id: str,
        universe_id: str,
        scene_id: str,
    ) -> None:
        from monitor_ui.routers.canon_review import accept_proposal

        memory_id = str(uuid4())
        _memory(hermetic, memory_id, character_id, universe_id, "The door opened")
        hermetic.override("neo4j_get_entity", {"id": character_id, "universe_id": universe_id})
        hermetic.override("qdrant_delete", {"success": True})
        proposal_id = _stage(
            scene_id, character_id, universe_id,
            {"action": "retract", "item_kind": "memory", "item_id": memory_id,
             "original_statement": "The door opened"},
        )

        accepted = await accept_proposal(proposal_id, "Approve", None, principal, _Preferences())
        assert accepted.status.value == "accepted"

        assert hermetic.collection("character_memories").find_one({"memory_id": memory_id}) is None
        assert hermetic.called("qdrant_delete")
        assert all(str(item.id) != memory_id for item in _audit(character_id, universe_id).items)
        proposal = hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})
        assert proposal["knowledge_correction_applied"] is True


class TestMemoryCorrection:
    @pytest.mark.asyncio
    async def test_a_corrected_memory_reads_back_with_the_new_text(
        self,
        hermetic: HermeticStack,
        principal: Principal,
        character_id: str,
        universe_id: str,
        scene_id: str,
    ) -> None:
        from monitor_ui.routers.canon_review import accept_proposal

        memory_id = str(uuid4())
        _memory(hermetic, memory_id, character_id, universe_id, "The door opened")
        hermetic.override("neo4j_get_entity", {"id": character_id, "universe_id": universe_id})
        embeddings: dict[str, str] = {}

        def _embed(params: dict[str, Any]) -> dict[str, bool]:
            embeddings[params["memory_id"]] = params["text"]
            return {"success": True}

        hermetic.override("qdrant_embed_memory", _embed)
        proposal_id = _stage(
            scene_id, character_id, universe_id,
            {"action": "correct", "item_kind": "memory", "item_id": memory_id,
             "original_statement": "The door opened"},
            statement="The door stayed shut",
        )

        accepted = await accept_proposal(proposal_id, "Approve", None, principal, _Preferences())
        assert accepted.status.value == "accepted"

        assert hermetic.collection("character_memories").find_one({"memory_id": memory_id})["text"] == (
            "The door stayed shut"
        )
        assert embeddings[memory_id] == "The door stayed shut"
        statements = [item.statement for item in _audit(character_id, universe_id).items]
        assert "The door stayed shut" in statements


class TestFactRetraction:
    @pytest.mark.asyncio
    async def test_a_retracted_fact_is_hidden_from_the_character_only(
        self,
        hermetic: HermeticStack,
        principal: Principal,
        character_id: str,
        universe_id: str,
        scene_id: str,
    ) -> None:
        from monitor_ui.routers.canon_review import accept_proposal

        fact_id = str(uuid4())
        hermetic.override("neo4j_get_entity", {"id": character_id, "universe_id": universe_id})
        hermetic.override("neo4j_get_fact", {
            "id": fact_id, "universe_id": universe_id,
            "statement": "The door opened", "properties": {},
        })
        hermetic.override("neo4j_update_fact", {"success": True})
        proposal_id = _stage(
            scene_id, character_id, universe_id,
            {"action": "retract", "item_kind": "fact", "item_id": fact_id,
             "original_statement": "The door opened"},
        )

        accepted = await accept_proposal(proposal_id, "Approve", None, principal, _Preferences())
        assert accepted.status.value == "accepted"

        updates = hermetic.calls_to("neo4j_update_fact")[0]["params"]
        excluded = {str(value) for value in updates["properties"]["knowledge_excluded"]}
        assert character_id in excluded
        assert not fact_visible_to({**updates, "statement": "The door opened"}, character_id)
        assert fact_visible_to({**updates, "statement": "The door opened"}, str(uuid4()))


class TestProposalRetraction:
    @pytest.mark.asyncio
    async def test_a_retracted_pending_proposal_leaves_the_characters_knowledge(
        self,
        hermetic: HermeticStack,
        principal: Principal,
        character_id: str,
        universe_id: str,
        scene_id: str,
    ) -> None:
        from monitor_ui.routers.canon_review import accept_proposal

        target = mongodb_create_proposed_change(
            ProposedChangeCreate(
                scene_id=UUID(scene_id),
                change_type=ProposalType.FACT,
                content={"statement": "The ledger vanished", "participants": [character_id],
                         "universe_id": universe_id, "properties": {}},
                authority="gm",
                proposer="CaptureInsightAgent",
            )
        )
        target_id = str(target.proposal_id)
        hermetic.override("neo4j_get_entity", {"id": character_id, "universe_id": universe_id})
        proposal_id = _stage(
            scene_id, character_id, universe_id,
            {"action": "retract", "item_kind": "proposal", "item_id": target_id,
             "original_statement": "The ledger vanished"},
        )

        accepted = await accept_proposal(proposal_id, "Approve", None, principal, _Preferences())
        assert accepted.status.value == "accepted"

        target = hermetic.collection("proposed_changes").find_one({"proposal_id": target_id})
        excluded = {str(value) for value in target["content"]["properties"]["knowledge_excluded"]}
        assert character_id in excluded
        assert target["status"] == "pending"
        assert all(str(item.id) != target_id for item in _audit(character_id, universe_id).items)


class TestInterruption:
    @pytest.mark.asyncio
    async def test_an_accept_cut_off_mid_write_is_finished_by_the_auto_reconciler(
        self,
        hermetic: HermeticStack,
        principal: Principal,
        monkeypatch: pytest.MonkeyPatch,
        character_id: str,
        universe_id: str,
        scene_id: str,
    ) -> None:
        from monitor_ui.correction_reconcile import CorrectionReconciler
        from monitor_ui.routers import canon_review

        memory_id = str(uuid4())
        _memory(hermetic, memory_id, character_id, universe_id, "The door opened")
        hermetic.override("neo4j_get_entity", {"id": character_id, "universe_id": universe_id})
        hermetic.override("qdrant_delete", {"success": True})
        proposal_id = _stage(
            scene_id, character_id, universe_id,
            {"action": "retract", "item_kind": "memory", "item_id": memory_id,
             "original_statement": "The door opened"},
        )

        original_update = canon_review.mongodb_update_proposed_change
        attempts = 0

        def fail_once(*args: Any, **kwargs: Any) -> Any:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ValueError("simulated crash before the verdict write")
            return original_update(*args, **kwargs)

        monkeypatch.setattr(canon_review, "mongodb_update_proposed_change", fail_once)
        with pytest.raises(HTTPException):
            await canon_review.accept_proposal(proposal_id, "Approve", None, principal, _Preferences())

        interrupted = hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})
        assert interrupted["status"] == "pending"
        assert "knowledge_retraction_checkpoint" in interrupted
        assert hermetic.collection("character_memories").find_one({"memory_id": memory_id}) is None

        result = await CorrectionReconciler().tick()
        assert result == {"reconciled": [proposal_id], "stalled": []}
        proposal = hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})
        assert proposal["status"] == "accepted"
        assert proposal["knowledge_correction_applied"] is True
        assert await CorrectionReconciler().tick() == {"reconciled": [], "stalled": []}


class TestStaleAttribution:
    @pytest.mark.asyncio
    async def test_a_changed_attribution_is_refused_not_applied_over(
        self,
        hermetic: HermeticStack,
        principal: Principal,
        character_id: str,
        universe_id: str,
        scene_id: str,
    ) -> None:
        from monitor_ui.routers.canon_review import accept_proposal

        memory_id = str(uuid4())
        _memory(hermetic, memory_id, character_id, universe_id, "The door opened")
        hermetic.override("neo4j_get_entity", {"id": character_id, "universe_id": universe_id})
        proposal_id = _stage(
            scene_id, character_id, universe_id,
            {"action": "retract", "item_kind": "memory", "item_id": memory_id,
             "original_statement": "The door opened"},
        )
        hermetic.collection("character_memories").update_one(
            {"memory_id": memory_id}, {"$set": {"text": "Someone rewrote the memory"}},
        )

        with pytest.raises(HTTPException):
            await accept_proposal(proposal_id, "Approve", None, principal, _Preferences())

        assert hermetic.collection("character_memories").find_one({"memory_id": memory_id})["text"] == (
            "Someone rewrote the memory"
        )
        assert "knowledge_retraction_checkpoint" not in (
            hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})
        )
