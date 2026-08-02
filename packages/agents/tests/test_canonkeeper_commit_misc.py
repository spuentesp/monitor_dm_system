from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper


@pytest.mark.asyncio
async def test_commit_spatial_topology_missing_locations(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_call_tool = AsyncMock()
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)
    
    proposal = {"payload": {"from_location": "", "to_location": "B"}}
    await keeper._commit_spatial_topology(MagicMock(), "pid", proposal, [], MagicMock())
    
    mock_call_tool.assert_not_called()
    
@pytest.mark.asyncio
async def test_commit_spatial_topology_unresolved(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_resolve = AsyncMock(return_value=None)
    monkeypatch.setattr(keeper, "_resolve_name_to_uuid", mock_resolve)
    mock_call_tool = AsyncMock()
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)
    
    proposal = {"payload": {"from_location": "A", "to_location": "B"}}
    await keeper._commit_spatial_topology(MagicMock(), "pid", proposal, [], MagicMock())
    
    mock_call_tool.assert_not_called()

@pytest.mark.asyncio
async def test_commit_spatial_topology_success(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    uid_a = str(uuid4())
    uid_b = str(uuid4())
    
    async def mock_resolve(name, universe_id):
        if name == "A":
            return uid_a
        if name == "B":
            return uid_b
        return None
        
    monkeypatch.setattr(keeper, "_resolve_name_to_uuid", mock_resolve)
    
    mock_call_tool = AsyncMock(return_value="{}")
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)
    monkeypatch.setattr(keeper, "_check_tool_error", MagicMock())
    
    proposal = {"payload": {"from_location": "A", "to_location": "B", "description": "test"}}
    await keeper._commit_spatial_topology(MagicMock(), "pid", proposal, [], MagicMock())
    
    mock_call_tool.assert_called_once()
    args = mock_call_tool.call_args[0][1]["params"]
    assert args["from_entity_id"] == uid_a
    assert args["to_entity_id"] == uid_b
    assert args["properties"]["description"] == "test"

@pytest.mark.asyncio
async def test_commit_create_agenda(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()

    mock_call_tool = AsyncMock()
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)

    proposal = {"payload": {"title": "My Agenda"}}
    await keeper._commit_create_agenda(MagicMock(), "pid", proposal, [], MagicMock())

    mock_call_tool.assert_called_once()
    assert mock_call_tool.call_args[0][0] == "neo4j_create_agenda"


# ---------------------------------------------------------------------------
# set_visual_identity commit branch (Task 7)
# ---------------------------------------------------------------------------


def _visual_identity_proposal(entity_id, universe_id, identity_id, version=3):
    return {
        "proposal_id": str(uuid4()),
        "change_type": "entity",
        "content": {
            "entity_id": str(entity_id),
            "universe_id": str(universe_id),
            "operation": "set_visual_identity",
            "visual_identity": {
                "identity_id": str(identity_id),
                "entity_id": str(entity_id),
                "universe_id": str(universe_id),
                "version": version,
                "hair": "silver-white",
                "eyes": "ember",
            },
            "visual_identity_version": version,
        },
    }


@pytest.mark.asyncio
async def test_commit_entity_set_visual_identity_merges_properties_and_marks_approved(
    monkeypatch: pytest.MonkeyPatch,
):
    keeper = CanonKeeper()
    entity_id, universe_id, identity_id = uuid4(), uuid4(), uuid4()
    existing_entity = {
        "id": str(entity_id),
        "name": "Dinah Lance",
        "properties": {"age": "early thirties", "occupation": "singer"},
    }
    calls: list[tuple[str, dict]] = []

    async def fake_call_tool(name, params):
        calls.append((name, params))
        if name == "neo4j_get_entity":
            return json.dumps(existing_entity)
        return json.dumps({"id": str(entity_id)})

    monkeypatch.setattr(keeper, "call_tool", fake_call_tool)

    proposal = _visual_identity_proposal(entity_id, universe_id, identity_id)
    await keeper._commit_entity(MagicMock(), proposal["proposal_id"], proposal, [], MagicMock())

    names = [name for name, _ in calls]
    # Must not flow through the new-entity branch.
    assert "neo4j_create_entity" not in names
    assert names[0] == "neo4j_get_entity"
    assert calls[0][1] == {"entity_id": str(entity_id)}

    update = next(params for name, params in calls if name == "neo4j_update_entity")
    assert update["entity_id"] == str(entity_id)
    merged = update["params"]["properties"]
    # Unrelated properties are preserved; the compact identity is merged in.
    assert merged["age"] == "early thirties"
    assert merged["occupation"] == "singer"
    assert merged["visual_identity"] == proposal["content"]["visual_identity"]

    # Acceptance marks the matching identity version approved with provenance.
    status = next(params for name, params in calls if name == "mongodb_update_visual_identity_status")
    assert status["identity_id"] == str(identity_id)
    assert status["status"] == "approved"
    assert status["decision_proposal_id"] == proposal["proposal_id"]


@pytest.mark.asyncio
async def test_commit_entity_set_visual_identity_missing_entity_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    keeper = CanonKeeper()
    entity_id, universe_id, identity_id = uuid4(), uuid4(), uuid4()

    async def fake_call_tool(name, params):
        return "null" if name == "neo4j_get_entity" else "{}"

    monkeypatch.setattr(keeper, "call_tool", fake_call_tool)

    proposal = _visual_identity_proposal(entity_id, universe_id, identity_id)
    with pytest.raises(RuntimeError, match="set_visual_identity"):
        await keeper._commit_entity(MagicMock(), proposal["proposal_id"], proposal, [], MagicMock())


@pytest.mark.asyncio
async def test_commit_entity_set_visual_identity_stashes_neo4j_id_for_audit_and_backlink(
    monkeypatch: pytest.MonkeyPatch,
):
    """The commit branch must feed the audit/back-link path like other branches.

    Without the stash, ``_audit_commit`` silently skips the ChangeLog entry and
    the proposal doc never gets its ``neo4j_id`` back-link.
    """
    keeper = CanonKeeper()
    entity_id, universe_id, identity_id = uuid4(), uuid4(), uuid4()
    existing_entity = {
        "id": str(entity_id),
        "name": "Dinah Lance",
        "properties": {"age": "early thirties"},
    }

    async def fake_call_tool(name, params):
        if name == "neo4j_get_entity":
            return json.dumps(existing_entity)
        return json.dumps({"id": str(entity_id)})

    monkeypatch.setattr(keeper, "call_tool", fake_call_tool)

    proposal = _visual_identity_proposal(entity_id, universe_id, identity_id)
    proposals_coll = MagicMock()
    keeper._last_commit_neo4j_id = None
    await keeper._commit_entity(proposals_coll, proposal["proposal_id"], proposal, [], MagicMock())

    # Stash consumed by _audit_commit for the ChangeLog entry.
    assert keeper._last_commit_neo4j_id == str(entity_id)
    # Back-link written onto the proposal document.
    proposals_coll.update_one.assert_called_once_with(
        {"proposal_id": proposal["proposal_id"]},
        {"$set": {"neo4j_id": str(entity_id)}},
    )


@pytest.mark.asyncio
async def test_commit_entity_set_visual_identity_status_tool_error_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    """A failed status update must surface, not be silently ignored."""
    keeper = CanonKeeper()
    entity_id, universe_id, identity_id = uuid4(), uuid4(), uuid4()
    existing_entity = {
        "id": str(entity_id),
        "name": "Dinah Lance",
        "properties": {},
    }

    async def fake_call_tool(name, params):
        if name == "neo4j_get_entity":
            return json.dumps(existing_entity)
        if name == "neo4j_update_entity":
            return json.dumps({"id": str(entity_id)})
        return "Validation error: status: Expected VisualIdentityStatus, got str"

    monkeypatch.setattr(keeper, "call_tool", fake_call_tool)

    proposal = _visual_identity_proposal(entity_id, universe_id, identity_id)
    with pytest.raises(RuntimeError, match="mongodb_update_visual_identity_status"):
        await keeper._commit_entity(MagicMock(), proposal["proposal_id"], proposal, [], MagicMock())


@pytest.mark.asyncio
async def test_record_visual_identity_rejection_status_tool_error_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    """A failed decision-reference write on rejection must surface too."""
    from monitor_data.schemas.agent_responses import CanonKeeperDecision, CanonKeeperVerdict

    keeper = CanonKeeper()
    entity_id, universe_id, identity_id = uuid4(), uuid4(), uuid4()
    proposal = _visual_identity_proposal(entity_id, universe_id, identity_id)
    verdict = CanonKeeperVerdict(
        proposal_id=UUID(proposal["proposal_id"]),
        decision=CanonKeeperDecision.REJECTED,
        reasoning="Contradicts established canon appearance.",
        canon_node_type="entity",
        canon_properties={},
        decided_at=datetime.now(UTC),
    )
    mock_call_tool = AsyncMock(
        return_value="Validation error: status: Expected VisualIdentityStatus, got str"
    )
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)

    with pytest.raises(RuntimeError, match="mongodb_update_visual_identity_status"):
        await keeper._record_visual_identity_rejection(proposal, verdict)


@pytest.mark.asyncio
async def test_rejected_visual_identity_proposal_stays_draft_with_decision_reference(
    monkeypatch: pytest.MonkeyPatch,
):
    from monitor_data.schemas.agent_responses import CanonKeeperDecision, CanonKeeperVerdict

    keeper = CanonKeeper()
    entity_id, universe_id, identity_id = uuid4(), uuid4(), uuid4()
    proposal = _visual_identity_proposal(entity_id, universe_id, identity_id)
    verdict = CanonKeeperVerdict(
        proposal_id=UUID(proposal["proposal_id"]),
        decision=CanonKeeperDecision.REJECTED,
        reasoning="Contradicts established canon appearance.",
        canon_node_type="entity",
        canon_properties={},
        decided_at=datetime.now(UTC),
    )

    monkeypatch.setattr(keeper, "_evaluate_single", AsyncMock(return_value=verdict))
    monkeypatch.setattr(keeper, "_fetch_world_rules", AsyncMock(return_value=""))
    monkeypatch.setattr(keeper, "_fetch_protected_entities", AsyncMock(return_value=""))
    monkeypatch.setattr(keeper, "_record_verdict", AsyncMock())
    mock_call_tool = AsyncMock(return_value="{}")
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)

    await keeper.evaluate_proposals(uuid4(), [proposal])

    status_calls = [
        c for c in mock_call_tool.call_args_list if c[0][0] == "mongodb_update_visual_identity_status"
    ]
    assert len(status_calls) == 1
    params = status_calls[0][0][1]
    assert params["identity_id"] == str(identity_id)
    assert params["status"] == "draft"  # stays draft on rejection
    assert params["decision_proposal_id"] == proposal["proposal_id"]
