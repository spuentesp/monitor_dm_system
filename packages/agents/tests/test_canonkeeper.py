"""
Tests for CanonKeeper agent — private pipeline methods and commit routing.

Complements test_canonization_gate.py (which tests the high-level evaluate_proposals
integration flow).  Here we test individual private methods in isolation:
- _evaluate_single: 3-phase pipeline (policy gate → reasoning → verdict)
- _commit_to_neo4j: routing by change_type to the correct Neo4j tool
- _record_verdict: audit trail write shape
- finalize_story: story completion tool call
- Context fetch helpers: _fetch_world_rules, _fetch_protected_entities, _fetch_related_canon

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_canonkeeper.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper import CanonKeeper
from monitor_data.schemas.agent_responses import (
    CanonKeeperDecision,
    CanonKeeperVerdict,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _verdict(
    decision: CanonKeeperDecision = CanonKeeperDecision.ACCEPTED,
    canon_node_type: str = "Character",
    canon_properties: Dict[str, Any] | None = None,
    proposal_id: str | None = None,
) -> CanonKeeperVerdict:
    return CanonKeeperVerdict(
        proposal_id=proposal_id or str(uuid4()),
        decision=decision,
        reasoning="Test reasoning.",
        canon_node_type=canon_node_type,
        canon_properties=canon_properties or {},
        decided_at=datetime.now(timezone.utc),
    )


def _proposal(
    change_type: str = "entity",
    proposal_type: str = "",
    content: Dict[str, Any] | None = None,
    payload: Dict[str, Any] | None = None,
    entity_names: list[str] | None = None,
    universe_id: str = "",
) -> Dict[str, Any]:
    return {
        "proposal_id": str(uuid4()),
        "change_type": change_type,
        "proposal_type": proposal_type,
        "summary": "Test proposal",
        "content": content or {},
        "payload": payload or {"entity_type": "Character", "name": "Test NPC"},
        "entity_names": entity_names if entity_names is not None else ["Test NPC"],
        "universe_id": universe_id or str(uuid4()),
    }


def _patch_commit_mongo(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Return a fake proposed_changes collection for _commit_to_neo4j tests."""
    from monitor_data.db import mongodb as mongodb_module

    proposals_coll = MagicMock()
    mongo_client = MagicMock()
    mongo_client.get_collection.return_value = proposals_coll
    monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: mongo_client)
    return proposals_coll


# ===========================================================================
# finalize_story
# ===========================================================================


class TestFinalizeStory:
    @pytest.mark.asyncio
    async def test_calls_neo4j_update_story_status(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        story_id = uuid4()
        await ck.finalize_story(story_id=story_id)

        ck.call_tool.assert_called_once()
        tool_name, args = ck.call_tool.call_args[0]
        assert tool_name == "neo4j_update_story_status"
        assert args["story_id"] == str(story_id)
        assert args["status"] == "completed"
        assert "completed_at" in args

    @pytest.mark.asyncio
    async def test_finalize_sends_iso_timestamp(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        await ck.finalize_story(story_id=uuid4())

        args = ck.call_tool.call_args[0][1]
        # Should parse as ISO format without raising
        datetime.fromisoformat(args["completed_at"])


# ===========================================================================
# Contradiction Detection
# ===========================================================================


@pytest.mark.asyncio
async def test_canonkeeper_flags_contradiction():
    from monitor_agents.canonkeeper import CanonKeeper
    from monitor_data.schemas.agent_responses import CanonKeeperDecision
    from unittest.mock import patch, AsyncMock
    from uuid import uuid4

    ck = CanonKeeper()

    # Mock call_tool for fetchers inside _evaluate_single and _check_contradiction
    ck.call_tool = AsyncMock()
    ck.call_tool.side_effect = [
        '[{"statement": "The King is dead."}]',  # _fetch_canon_facts
        "[]",  # _fetch_canon_axioms
    ]

    # Mock PolicyCheckModule to pass
    with patch.object(ck, "_policy_check") as mock_policy:
        mock_policy.return_value.violation_found = "NO"

        # Mock DSPy module forward call inside _check_contradiction
        with patch(
            "monitor_agents.prompts.verification.ContradictionModule.forward"
        ) as mock_verify:
            mock_verify.return_value = {
                "has_contradiction": True,
                "explanation": "Character is dead.",
            }

            proposal = {
                "proposal_id": str(uuid4()),
                "universe_id": str(uuid4()),
                "summary": "The King walks into the tavern.",
                "content": {"statement": "The King walks into the tavern."},
            }

            verdict = await ck._evaluate_single(
                proposal=proposal, world_rules="- No violence", protected_entities="[]"
            )

            assert verdict.decision == CanonKeeperDecision.REJECTED
            assert "Character is dead" in verdict.reasoning


# ===========================================================================
# _record_verdict
# ===========================================================================


class TestRecordVerdict:
    @pytest.mark.asyncio
    async def test_calls_mongodb_record_verdict(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        scene_id = uuid4()
        v = _verdict(decision=CanonKeeperDecision.ACCEPTED)
        await ck._record_verdict(scene_id, v)

        ck.call_tool.assert_called_once()
        tool_name, args = ck.call_tool.call_args[0]
        assert tool_name == "mongodb_record_verdict"
        assert args["scene_id"] == str(scene_id)
        assert args["proposal_id"] == str(v.proposal_id)
        assert args["decision"] == CanonKeeperDecision.ACCEPTED.value

    @pytest.mark.asyncio
    async def test_record_verdict_rejected_decision(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict(decision=CanonKeeperDecision.REJECTED)
        await ck._record_verdict(uuid4(), v)

        args = ck.call_tool.call_args[0][1]
        assert args["decision"] == CanonKeeperDecision.REJECTED.value

    @pytest.mark.asyncio
    async def test_record_verdict_includes_reasoning(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict()
        v.reasoning = "Conflicts with established lore."
        await ck._record_verdict(uuid4(), v)

        args = ck.call_tool.call_args[0][1]
        assert args["reasoning"] == "Conflicts with established lore."


# ===========================================================================
# _fetch_world_rules
# ===========================================================================


class TestFetchWorldRules:
    @pytest.mark.asyncio
    async def test_returns_raw_when_tool_responds(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value="- No violence against children")

        result = await ck._fetch_world_rules(uuid4())

        assert result == "- No violence against children"

    @pytest.mark.asyncio
    async def test_returns_default_when_tool_returns_none(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value=None)

        result = await ck._fetch_world_rules(uuid4())

        assert "No explicit content restrictions" in result
        assert "internal consistency" in result

    @pytest.mark.asyncio
    async def test_returns_default_when_tool_returns_empty(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value="")

        result = await ck._fetch_world_rules(uuid4())

        assert "No explicit content restrictions" in result


# ===========================================================================
# _fetch_protected_entities
# ===========================================================================


class TestFetchProtectedEntities:
    @pytest.mark.asyncio
    async def test_returns_raw_json_from_tool(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value='["entity-1", "entity-2"]')

        result = await ck._fetch_protected_entities(uuid4())

        assert result == '["entity-1", "entity-2"]'

    @pytest.mark.asyncio
    async def test_returns_empty_list_json_on_none(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value=None)

        result = await ck._fetch_protected_entities(uuid4())

        assert result == "[]"


# ===========================================================================
# _fetch_related_canon
# ===========================================================================


class TestFetchRelatedCanon:
    @pytest.mark.asyncio
    async def test_returns_raw_when_entity_names_present(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value='{"name": "Lyra"}')

        proposal = _proposal(entity_names=["Lyra"])
        result = await ck._fetch_related_canon(proposal)

        assert result == '{"name": "Lyra"}'
        ck.call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_entity_names(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        proposal = _proposal(entity_names=[])
        result = await ck._fetch_related_canon(proposal)

        assert result == "{}"
        ck.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_dict_json_when_tool_returns_none(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value=None)

        proposal = _proposal(entity_names=["Unknown"])
        result = await ck._fetch_related_canon(proposal)

        assert result == "{}"

    @pytest.mark.asyncio
    async def test_reads_entity_names_from_payload_when_top_level_empty(self):
        """Falls back to payload.entity_names when top-level list is absent."""
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value="{}")

        proposal = {
            "proposal_id": str(uuid4()),
            "entity_names": [],
            "payload": {"entity_names": ["Drake"], "entity_type": "Character"},
            "universe_id": str(uuid4()),
        }
        await ck._fetch_related_canon(proposal)

        ck.call_tool.assert_called_once()
        call_args = ck.call_tool.call_args[0][1]
        assert "Drake" in call_args["names"]


# ===========================================================================
# _commit_to_neo4j — routing by type
# ===========================================================================


class TestCommitToNeo4j:
    @pytest.mark.asyncio
    async def test_entity_change_type_calls_neo4j_create_entity(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict(canon_node_type="Character", canon_properties={"age": 30})
        p = _proposal(change_type="entity", payload={"entity_type": "Character", "name": "Lyra"})
        await ck._commit_to_neo4j(v, p)

        tool_name = ck.call_tool.call_args[0][0]
        assert tool_name == "neo4j_create_entity"

    @pytest.mark.asyncio
    async def test_character_type_calls_neo4j_create_entity(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict(canon_node_type="character")
        p = _proposal(change_type="character", payload={"name": "Aldric"})
        await ck._commit_to_neo4j(v, p)

        tool_name = ck.call_tool.call_args[0][0]
        assert tool_name == "neo4j_create_entity"

    @pytest.mark.asyncio
    async def test_axiom_change_type_calls_neo4j_create_axiom(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict(canon_node_type="axiom")
        p = _proposal(
            change_type="axiom",
            payload={"statement": "Magic is forbidden in the North", "domain": "politics"},
        )
        await ck._commit_to_neo4j(v, p)

        tool_name = ck.call_tool.call_args[0][0]
        assert tool_name == "neo4j_create_axiom"

    @pytest.mark.asyncio
    async def test_world_truth_type_calls_neo4j_create_axiom(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict(canon_node_type="world_truth")
        p = _proposal(change_type="world_truth", payload={"statement": "Dragons are extinct"})
        await ck._commit_to_neo4j(v, p)

        tool_name = ck.call_tool.call_args[0][0]
        assert tool_name == "neo4j_create_axiom"

    @pytest.mark.asyncio
    async def test_fact_change_type_calls_neo4j_create_fact(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict(canon_node_type="fact")
        p = _proposal(change_type="fact", payload={"statement": "Aldric knows the guild"})
        await ck._commit_to_neo4j(v, p)

        tool_name = ck.call_tool.call_args[0][0]
        assert tool_name == "neo4j_create_fact"

    @pytest.mark.asyncio
    async def test_relationship_change_type_calls_neo4j_create_relationship(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        from_id = uuid4()
        to_id = uuid4()
        v = _verdict(canon_node_type="relationship")
        p = _proposal(
            change_type="relationship",
            content={
                "from_entity_id": str(from_id),
                "to_entity_id": str(to_id),
                "rel_type": "KNOWS",
                "properties": {"sentiment": "trust", "delta": 0.2},
            },
            payload={},
        )
        await ck._commit_to_neo4j(v, p)

        tool_name, args = ck.call_tool.call_args[0]
        assert tool_name == "neo4j_create_relationship"
        assert args["params"]["from_entity_id"] == str(from_id)
        assert args["params"]["to_entity_id"] == str(to_id)

    @pytest.mark.asyncio
    async def test_state_update_calls_neo4j_update_state_tags(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict(canon_node_type="state_update", canon_properties={"hp": 10})
        p = _proposal(change_type="state_update")
        await ck._commit_to_neo4j(v, p)

        tool_name = ck.call_tool.call_args[0][0]
        assert tool_name == "neo4j_update_state_tags"

    @pytest.mark.asyncio
    async def test_state_change_calls_neo4j_update_state_tags(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict(canon_node_type="state_change", canon_properties={})
        p = _proposal(
            change_type="state_change",
            payload={
                "entity_id": str(uuid4()),
                "add_tags": ["wounded", "revealed"],
                "remove_tags": [],
            },
        )
        await ck._commit_to_neo4j(v, p)

        tool_name, args = ck.call_tool.call_args[0]
        assert tool_name == "neo4j_update_state_tags"
        assert args["params"]["entity_id"] == p["payload"]["entity_id"]
        assert args["params"]["add_tags"] == ["wounded", "revealed"]

    @pytest.mark.asyncio
    async def test_proposal_type_takes_precedence_over_verdict_type(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        """proposal_type (from KnowledgePack) overrides verdict canon_node_type."""
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict(canon_node_type="unknown_type")
        p = _proposal(proposal_type="create_axiom", payload={"statement": "Elves are immortal"})
        await ck._commit_to_neo4j(v, p)

        tool_name = ck.call_tool.call_args[0][0]
        assert tool_name == "neo4j_create_axiom"

    @pytest.mark.asyncio
    async def test_create_entity_archetype_type_calls_neo4j_create_entity(self, monkeypatch):
        _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()

        v = _verdict(canon_node_type="entity")
        p = _proposal(proposal_type="create_entity_archetype", payload={"name": "Dragon"})
        await ck._commit_to_neo4j(v, p)

        tool_name = ck.call_tool.call_args[0][0]
        assert tool_name == "neo4j_create_entity"

    @pytest.mark.asyncio
    async def test_create_random_table_type_calls_mongodb_create_random_table(self, monkeypatch):
        proposals_coll = _patch_commit_mongo(monkeypatch)
        table_id = uuid4()
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value={"table_id": str(table_id)})

        v = _verdict(canon_node_type="mechanic")
        p = _proposal(
            proposal_type="create_random_table",
            payload={
                "name": "Dockside Rumors",
                "description": "Things overheard near the wharf.",
                "dice_formula": "1d6",
                "table_type": "rumors",
                "entries": [{"min_roll": 1, "max_roll": 6, "value": "The fog hides smugglers."}],
            },
        )
        await ck._commit_to_neo4j(v, p)

        tool_name, args = ck.call_tool.call_args[0]
        assert tool_name == "mongodb_create_random_table"
        assert args["params"]["table_type"] == "rumor"
        assert args["params"]["entries"][0]["value"] == "The fog hides smugglers."
        proposals_coll.update_one.assert_called_with(
            {"proposal_id": p["proposal_id"]},
            {
                "$set": {
                    "random_table_id": str(table_id),
                    "runtime_activation_status": "active",
                }
            },
        )

    @pytest.mark.asyncio
    async def test_create_tone_profile_type_calls_mongodb_create_tone_profile(self, monkeypatch):
        proposals_coll = _patch_commit_mongo(monkeypatch)
        profile_id = uuid4()
        pack_id = uuid4()
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value={"profile_id": str(profile_id)})

        v = _verdict(canon_node_type="fact")
        p = _proposal(
            proposal_type="create_tone_profile",
            payload={
                "name": "oppressive_gothic",
                "description": "Dread-soaked narration.",
                "instruction": "Keep pressure high and descriptions sensory.",
                "trigger_tags": ["gothic", "dread"],
                "category": "mood",
            },
        )
        p["source"] = f"knowledge_pack:{pack_id}"
        await ck._commit_to_neo4j(v, p)

        tool_name, args = ck.call_tool.call_args[0]
        assert tool_name == "mongodb_create_tone_profile"
        assert args["params"]["pack_id"] == str(pack_id)
        assert args["params"]["is_builtin"] is False
        proposals_coll.update_one.assert_called_with(
            {"proposal_id": p["proposal_id"]},
            {
                "$set": {
                    "tone_profile_id": str(profile_id),
                    "runtime_activation_status": "active",
                }
            },
        )

    @pytest.mark.asyncio
    async def test_create_character_profile_updates_matching_npc_profile(self, monkeypatch):
        proposals_coll = _patch_commit_mongo(monkeypatch)
        entity_id = uuid4()
        profile_id = uuid4()
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(
            side_effect=[
                {"entities": [{"id": str(entity_id), "name": "Aldric"}]},
                {"profile_id": str(profile_id), "entity_id": str(entity_id)},
            ]
        )

        v = _verdict(canon_node_type="fact")
        p = _proposal(
            proposal_type="create_character_profile",
            payload={
                "name": "Aldric",
                "traits": {"stoic": 0.8},
                "values": ["duty"],
                "fears": ["failure"],
                "desires": ["redemption"],
                "speech_style": "formal and clipped",
                "mannerisms": ["adjusts signet ring"],
            },
        )
        await ck._commit_to_neo4j(v, p)

        first_tool, first_args = ck.call_tool.await_args_list[0].args
        second_tool, second_args = ck.call_tool.await_args_list[1].args
        assert first_tool == "neo4j_list_entities"
        assert first_args["filters"]["name"] == "Aldric"
        assert second_tool == "mongodb_update_npc_profile"
        assert second_args["entity_id"] == str(entity_id)
        assert second_args["params"]["speech_style"] == "formal and clipped"
        proposals_coll.update_one.assert_any_call(
            {"proposal_id": p["proposal_id"]},
            {
                "$set": {
                    "npc_profile_id": str(profile_id),
                    "runtime_activation_status": "active",
                }
            },
        )
        proposals_coll.update_one.assert_any_call(
            {"proposal_id": p["proposal_id"]},
            {"$set": {"profile_entity_id": str(entity_id)}},
        )

    @pytest.mark.asyncio
    async def test_create_character_profile_marks_unresolved_when_entity_missing(self, monkeypatch):
        proposals_coll = _patch_commit_mongo(monkeypatch)
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value={"entities": []})

        v = _verdict(canon_node_type="fact")
        p = _proposal(
            proposal_type="create_character_profile",
            payload={"name": "Unknown Hermit", "values": ["silence"]},
        )
        await ck._commit_to_neo4j(v, p)

        ck.call_tool.assert_awaited_once()
        proposals_coll.update_one.assert_called_once()
        update_doc = proposals_coll.update_one.call_args.args[1]["$set"]
        assert update_doc["runtime_activation_status"] == "unresolved"
        assert "Unknown Hermit" in update_doc["runtime_activation_reason"]

    @pytest.mark.asyncio
    async def test_create_generation_template_type_calls_entity_template_tool(self, monkeypatch):
        proposals_coll = _patch_commit_mongo(monkeypatch)
        template_id = uuid4()
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value={"template_id": str(template_id)})

        v = _verdict(canon_node_type="mechanic")
        universe_id = str(uuid4())
        p = _proposal(
            proposal_type="create_generation_template",
            universe_id=universe_id,
            payload={
                "name": "Harpy Envoy",
                "archetype_name": "Harpy",
                "stat_block_name": "Harpy Scout",
                "profile_name": "Harpy Socialite",
                "random_table_refs": ["Harpy Names"],
                "tier_override": "elite",
            },
        )
        await ck._commit_to_neo4j(v, p)

        tool_name, args = ck.call_tool.call_args[0]
        assert tool_name == "mongodb_create_entity_template"
        assert args["params"]["universe_id"] == universe_id
        assert args["params"]["entity_type"] == "character"
        assert args["params"]["base_properties"]["archetype_name"] == "Harpy"
        assert args["params"]["variable_properties"][0]["generation_type"] == "llm"
        proposals_coll.update_one.assert_called_with(
            {"proposal_id": p["proposal_id"]},
            {
                "$set": {
                    "entity_template_id": str(template_id),
                    "runtime_activation_status": "active",
                }
            },
        )


# ===========================================================================
# _evaluate_single — policy gate short-circuit
# ===========================================================================


class TestEvaluateSingle:
    @pytest.mark.asyncio
    async def test_policy_violation_rejects_without_llm(self):
        """Policy gate hit → REJECTED immediately, no call_llm_structured."""
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value=None)
        ck.call_llm_structured = AsyncMock()

        fake_policy = MagicMock()
        fake_policy.violation_found = "YES"
        fake_policy.violation_detail = "Kills a protected entity"
        mock_policy_module = MagicMock(return_value=fake_policy)
        ck._policy_check = mock_policy_module

        ck._reasoning = MagicMock()
        ck._fetch_related_canon = AsyncMock(return_value="{}")

        proposal = _proposal()
        verdict = await ck._evaluate_single(
            proposal=proposal,
            world_rules="- No killing protected",
            protected_entities='["entity-1"]',
        )

        assert verdict.decision == CanonKeeperDecision.REJECTED
        assert "Policy violation" in verdict.reasoning
        ck.call_llm_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_policy_pass_reaches_llm_structured(self):
        """Policy gate passes → call_llm_structured is called for final verdict."""
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value="{}")
        ck._fetch_related_canon = AsyncMock(return_value="{}")

        fake_policy = MagicMock()
        fake_policy.violation_found = "NO"
        mock_policy_module = MagicMock(return_value=fake_policy)
        ck._policy_check = mock_policy_module

        fake_reasoning = MagicMock()
        fake_reasoning.reasoning = "Lyra is consistent with the world."
        mock_reasoning_module = MagicMock(return_value=fake_reasoning)
        ck._reasoning = mock_reasoning_module

        expected_verdict = _verdict(decision=CanonKeeperDecision.ACCEPTED)
        ck.call_llm_structured = AsyncMock(return_value=expected_verdict)

        proposal = _proposal()
        verdict = await ck._evaluate_single(
            proposal=proposal,
            world_rules="",
            protected_entities="[]",
        )

        assert verdict.decision == CanonKeeperDecision.ACCEPTED
        ck.call_llm_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_policy_violation_case_insensitive(self):
        """policy.violation_found matching is case-insensitive (YES/yes/Yes)."""
        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock(return_value=None)
        ck.call_llm_structured = AsyncMock()
        ck._fetch_related_canon = AsyncMock(return_value="{}")

        for yes_variant in ("yes", "Yes", "YES"):
            fake_policy = MagicMock()
            fake_policy.violation_found = yes_variant
            fake_policy.violation_detail = "violation"
            ck._policy_check = MagicMock(return_value=fake_policy)
            ck._reasoning = MagicMock()

            verdict = await ck._evaluate_single(
                proposal=_proposal(),
                world_rules="",
                protected_entities="[]",
            )
            assert verdict.decision == CanonKeeperDecision.REJECTED, f"Failed for {yes_variant!r}"


# ===========================================================================
# apply_pack_to_universe — mechanic node writes
# ===========================================================================


class TestApplyPackMechanicNodes:
    @pytest.mark.asyncio
    async def test_writes_mechanic_nodes_when_game_system_present(self):
        """When pack_doc has game_system_data, CanonKeeper must create Neo4j mechanic nodes."""
        from unittest.mock import patch, MagicMock

        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()
        ck._commit_to_neo4j = AsyncMock()

        pack_id = uuid4()
        multiverse_id = uuid4()

        # Build a fake MongoDB client with game_system_data on the pack
        mock_mongo = MagicMock()
        mock_proposals_coll = MagicMock()
        mock_proposals_coll.count_documents.return_value = 0
        mock_proposals_coll.find.return_value = []
        mock_packs_coll = MagicMock()
        mock_packs_coll.find_one.return_value = {
            "pack_id": str(pack_id),
            "source_document_ids": [],
            "game_system_data": {
                "name": "Vampire: the Masquerade",
                "tiered_abilities": [
                    {
                        "name": "Dominate",
                        "parent_category": "Discipline",
                        "tiers": [],
                        "max_tier": 5,
                    },
                ],
                "tracks": [
                    {
                        "name": "Blood Pool",
                        "min_value": 0,
                        "max_value": 10,
                        "default_value": 10,
                        "track_type": "resource",
                        "gain_conditions": [],
                        "loss_conditions": [],
                        "spend_conditions": [],
                        "recovery_rules": [],
                        "threshold_effects": [],
                    },
                ],
                "conditions": [
                    {
                        "name": "Frenzy",
                        "trigger": "Fail Humanity check",
                        "ends_when": "Willpower roll",
                        "stackable": False,
                    },
                ],
            },
        }

        def _fake_get_collection(name):
            return {
                "proposed_changes": mock_proposals_coll,
                "knowledge_packs": mock_packs_coll,
                "documents": MagicMock(find_one=MagicMock(return_value=None)),
            }[name]

        mock_mongo.get_collection = _fake_get_collection

        with (
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mock_mongo) as _,
            patch("monitor_data.tools.mongodb_tools.mongodb_apply_knowledge_pack") as mock_apply,
            patch("monitor_agents.canonkeeper.neo4j_create_ability_system") as mock_ab,
            patch("monitor_agents.canonkeeper.neo4j_create_track") as mock_tr,
            patch("monitor_agents.canonkeeper.neo4j_create_condition") as mock_cn,
        ):
            mock_apply.return_value = {"proposals_created": 1}
            await ck.apply_pack_to_universe(pack_id, multiverse_id, auto_accept=True)

        mock_ab.assert_called_once_with(
            name="Dominate",
            system_id="Vampire: the Masquerade",
            parent_category="Discipline",
        )
        mock_tr.assert_called_once_with(
            name="Blood Pool",
            system_id="Vampire: the Masquerade",
            track_type="resource",
        )
        mock_cn.assert_called_once_with(
            name="Frenzy",
            system_id="Vampire: the Masquerade",
        )

    @pytest.mark.asyncio
    async def test_skips_mechanic_nodes_when_no_game_system(self):
        """When pack_doc has no game_system_data, no mechanic nodes are written."""
        from unittest.mock import patch, MagicMock

        ck = CanonKeeper.__new__(CanonKeeper)
        ck.call_tool = AsyncMock()
        ck._commit_to_neo4j = AsyncMock()

        pack_id = uuid4()
        multiverse_id = uuid4()

        mock_mongo = MagicMock()
        mock_proposals_coll = MagicMock()
        mock_proposals_coll.count_documents.return_value = 0
        mock_proposals_coll.find.return_value = []
        mock_packs_coll = MagicMock()
        mock_packs_coll.find_one.return_value = {
            "pack_id": str(pack_id),
            "source_document_ids": [],
        }

        def _fake_get_collection(name):
            return {
                "proposed_changes": mock_proposals_coll,
                "knowledge_packs": mock_packs_coll,
                "documents": MagicMock(find_one=MagicMock(return_value=None)),
            }[name]

        mock_mongo.get_collection = _fake_get_collection

        with (
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mock_mongo),
            patch("monitor_data.tools.mongodb_tools.mongodb_apply_knowledge_pack") as mock_apply,
            patch("monitor_agents.canonkeeper.neo4j_create_ability_system") as mock_ab,
            patch("monitor_agents.canonkeeper.neo4j_create_track") as mock_tr,
            patch("monitor_agents.canonkeeper.neo4j_create_condition") as mock_cn,
        ):
            mock_apply.return_value = {"proposals_created": 0}
            await ck.apply_pack_to_universe(pack_id, multiverse_id, auto_accept=True)

        mock_ab.assert_not_called()
        mock_tr.assert_not_called()
        mock_cn.assert_not_called()
