"""Contract tests for ontology CRUD endpoints (F2-2 phases 1 & 2).

Covers the Fact/Axiom/Event routers and relationship update/delete on
``routers/entities.py`` (M-12…M-25 family), with the underlying Neo4j tools
patched at their source module (the router imports them lazily per call),
mirroring the ``test_entities_crud.py`` style.
"""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from monitor_data.schemas.base import (
    Authority,
    AxiomAuthority,
    CanonLevel,
    KnowledgeScope,
    SimulationScope,
)
from monitor_data.schemas.facts import (
    AxiomResponse,
    EventResponse,
    FactResponse,
    FactType,
)
from monitor_data.schemas.relationships import (
    RelationshipCategory,
    RelationshipResponse,
    RelationshipType,
)

from monitor_ui.main import app

client = TestClient(app)

FACTS_TOOLS = "monitor_data.tools.neo4j_tools.facts"
REL_TOOLS = "monitor_data.tools.neo4j_tools.relationships"

BASE = "/api/entities/entities"


def _fact(**over) -> FactResponse:
    data = {
        "id": uuid4(),
        "universe_id": uuid4(),
        "statement": "The door is broken",
        "fact_type": FactType.STATE,
        "canon_level": CanonLevel.CANON,
        "knowledge_scope": KnowledgeScope.WORLD,
        "confidence": 1.0,
        "authority": Authority.GM,
        "created_at": datetime.now(UTC),
        "replaces": None,
        "properties": None,
    }
    data.update(over)
    return FactResponse(**data)


def _axiom(**over) -> AxiomResponse:
    data = {
        "id": uuid4(),
        "universe_id": uuid4(),
        "statement": "Magic exists",
        "domain": "magic",
        "magnitude": 8,
        "scope": SimulationScope.GLOBAL,
        "canon_level": CanonLevel.CANON,
        "confidence": 0.9,
        "authority": AxiomAuthority.METAPHYSICS,
        "source_ref": None,
        "properties": None,
        "created_at": datetime.now(UTC),
    }
    data.update(over)
    return AxiomResponse(**data)


def _event(**over) -> EventResponse:
    data = {
        "id": uuid4(),
        "universe_id": uuid4(),
        "title": "The bridge falls",
        "start_time": datetime.now(UTC),
        "canon_level": CanonLevel.CANON,
        "knowledge_scope": KnowledgeScope.WORLD,
        "confidence": 1.0,
        "authority": Authority.GM,
        "created_at": datetime.now(UTC),
    }
    data.update(over)
    return EventResponse(**data)


def _relationship(**over) -> RelationshipResponse:
    data = {
        "relationship_id": "42",
        "from_entity_id": uuid4(),
        "to_entity_id": uuid4(),
        "rel_type": RelationshipType.KNOWS,
        "category": RelationshipCategory.SOCIAL,
        "subcategory": None,
        "properties": {},
        "created_at": datetime.now(UTC),
    }
    data.update(over)
    return RelationshipResponse(**data)


# ── facts (M-12…M-15) ─────────────────────────────────────────────


def test_create_fact_returns_201():
    uni = uuid4()
    with patch(f"{FACTS_TOOLS}.neo4j_create_fact") as mock_create:
        mock_create.return_value = _fact(universe_id=uni)
        resp = client.post(
            f"{BASE}/{uni}/facts",
            json={"statement": "The door is broken", "fact_type": "state"},
        )
    assert resp.status_code == 201
    assert resp.json()["statement"] == "The door is broken"
    params = mock_create.call_args.args[0]
    # universe_id comes from the path; UI-authored facts default to GM canon
    assert params.universe_id == uni
    assert params.canon_level == CanonLevel.CANON
    assert params.authority == Authority.GM


def test_create_fact_validation_error():
    resp = client.post(f"{BASE}/{uuid4()}/facts", json={"statement": ""})
    assert resp.status_code == 422


def test_create_fact_unknown_universe_404():
    with patch(f"{FACTS_TOOLS}.neo4j_create_fact") as mock_create:
        mock_create.side_effect = ValueError(f"Universe {uuid4()} not found")
        resp = client.post(f"{BASE}/{uuid4()}/facts", json={"statement": "Something true"})
    assert resp.status_code == 404


def test_list_facts_passes_filters():
    uni = uuid4()
    entity = uuid4()
    with patch(f"{FACTS_TOOLS}.neo4j_list_facts") as mock_list:
        mock_list.return_value = [_fact(universe_id=uni)]
        resp = client.get(
            f"{BASE}/{uni}/facts",
            params={
                "fact_type": "state",
                "canon_level": "canon",
                "entity_id": str(entity),
                "min_magnitude": 3,
                "limit": 10,
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["facts"][0]["statement"] == "The door is broken"
    filters = mock_list.call_args.args[0]
    assert filters.universe_id == uni
    assert filters.fact_type == FactType.STATE
    assert filters.canon_level == CanonLevel.CANON
    assert filters.entity_id == entity
    assert filters.min_magnitude == 3
    assert filters.limit == 10


def test_list_facts_invalid_enum_422():
    resp = client.get(f"{BASE}/{uuid4()}/facts", params={"fact_type": "bogus"})
    assert resp.status_code == 422


def test_update_fact_success():
    fid = uuid4()
    with patch(f"{FACTS_TOOLS}.neo4j_update_fact") as mock_update:
        mock_update.return_value = _fact(id=fid, statement="Updated")
        resp = client.patch(f"{BASE}/facts/{fid}", json={"statement": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["statement"] == "Updated"


def test_update_fact_404():
    with patch(f"{FACTS_TOOLS}.neo4j_update_fact") as mock_update:
        mock_update.side_effect = ValueError("Fact %s not found" % uuid4())
        resp = client.patch(f"{BASE}/facts/{uuid4()}", json={"statement": "X"})
    assert resp.status_code == 404


def test_delete_fact_success():
    fid = uuid4()
    with patch(f"{FACTS_TOOLS}.neo4j_delete_fact") as mock_delete:
        mock_delete.return_value = {"fact_id": str(fid), "deleted": True}
        resp = client.delete(f"{BASE}/facts/{fid}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert mock_delete.call_args.kwargs["force"] is False


def test_delete_fact_canon_without_force_400():
    with patch(f"{FACTS_TOOLS}.neo4j_delete_fact") as mock_delete:
        mock_delete.side_effect = ValueError("Cannot delete canon fact x without force=True")
        resp = client.delete(f"{BASE}/facts/{uuid4()}")
    assert resp.status_code == 400


def test_delete_fact_force_passed_through():
    with patch(f"{FACTS_TOOLS}.neo4j_delete_fact") as mock_delete:
        mock_delete.return_value = {"deleted": True, "forced": True}
        resp = client.delete(f"{BASE}/facts/{uuid4()}", params={"force": "true"})
    assert resp.status_code == 200
    assert mock_delete.call_args.kwargs["force"] is True


# ── axioms (M-16…M-19) ────────────────────────────────────────────


def test_create_axiom_returns_201():
    uni = uuid4()
    with patch(f"{FACTS_TOOLS}.neo4j_create_axiom") as mock_create:
        mock_create.return_value = _axiom(universe_id=uni)
        resp = client.post(
            f"{BASE}/{uni}/axioms",
            json={"statement": "Magic exists", "domain": "magic"},
        )
    assert resp.status_code == 201
    assert resp.json()["domain"] == "magic"
    params = mock_create.call_args.args[0]
    assert params.universe_id == uni
    assert params.canon_level == CanonLevel.CANON


def test_create_axiom_validation_error():
    resp = client.post(f"{BASE}/{uuid4()}/axioms", json={"statement": "", "domain": "x"})
    assert resp.status_code == 422


def test_list_axioms_passes_filters():
    uni = uuid4()
    with patch(f"{FACTS_TOOLS}.neo4j_list_axioms") as mock_list:
        mock_list.return_value = [_axiom(universe_id=uni)]
        resp = client.get(f"{BASE}/{uni}/axioms", params={"domain": "magic", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["axioms"][0]["statement"] == "Magic exists"
    filters = mock_list.call_args.args[0]
    assert filters.universe_id == uni
    assert filters.domain == "magic"
    assert filters.limit == 5


def test_update_axiom_success():
    aid = uuid4()
    with patch(f"{FACTS_TOOLS}.neo4j_update_axiom") as mock_update:
        mock_update.return_value = _axiom(id=aid, statement="Magic is rare")
        resp = client.patch(f"{BASE}/axioms/{aid}", json={"statement": "Magic is rare"})
    assert resp.status_code == 200
    assert resp.json()["statement"] == "Magic is rare"


def test_update_axiom_404():
    with patch(f"{FACTS_TOOLS}.neo4j_update_axiom") as mock_update:
        mock_update.side_effect = ValueError("Axiom %s not found" % uuid4())
        resp = client.patch(f"{BASE}/axioms/{uuid4()}", json={"domain": "physics"})
    assert resp.status_code == 404


def test_delete_axiom_canon_without_force_400():
    with patch(f"{FACTS_TOOLS}.neo4j_delete_axiom") as mock_delete:
        mock_delete.side_effect = ValueError("Cannot delete canon axiom x without force=True")
        resp = client.delete(f"{BASE}/axioms/{uuid4()}")
    assert resp.status_code == 400


def test_delete_axiom_success():
    with patch(f"{FACTS_TOOLS}.neo4j_delete_axiom") as mock_delete:
        mock_delete.return_value = {"deleted": True}
        resp = client.delete(f"{BASE}/axioms/{uuid4()}")
    assert resp.status_code == 200


# ── events (M-20…M-23) ────────────────────────────────────────────


def test_create_event_returns_201():
    uni = uuid4()
    start = datetime.now(UTC).isoformat()
    with patch("monitor_data.tools.mongodb_tools.proposals.mongodb_create_proposed_change") as mock_create:
        from monitor_data.schemas.proposed_changes import ProposedChangeResponse, ProposalStatus
        mock_create.return_value = ProposedChangeResponse(
            id=str(uuid4()),
            proposal_id=str(uuid4()),
            change_type="event",
            content={"title": "The bridge falls", "start_time": start, "universe_id": str(uni), "operation": "create"},
            authority="gm",
            proposer="UI",
            status=ProposalStatus.PENDING,
            confidence=1.0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)
        )
        resp = client.post(
            f"{BASE}/{uni}/events",
            json={"title": "The bridge falls", "start_time": start},
        )
    assert resp.status_code == 201
    assert resp.json()["content"]["title"] == "The bridge falls"
    proposal = mock_create.call_args.args[0]
    assert proposal.content["universe_id"] == str(uni)
    assert proposal.authority == "gm"


def test_create_event_requires_start_time():
    resp = client.post(f"{BASE}/{uuid4()}/events", json={"title": "No time"})
    assert resp.status_code == 422


def test_list_events_passes_filters():
    uni = uuid4()
    scene = uuid4()
    with patch(f"{FACTS_TOOLS}.neo4j_list_events") as mock_list:
        mock_list.return_value = ([_event(universe_id=uni)], 1)
        resp = client.get(f"{BASE}/{uni}/events", params={"scene_id": str(scene), "limit": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "The bridge falls"
    filters = mock_list.call_args.args[0]
    assert filters.universe_id == uni
    assert filters.scene_id == scene


def test_update_event_success():
    eid = uuid4()
    with patch("monitor_data.tools.mongodb_tools.proposals.mongodb_create_proposed_change") as mock_update:
        from monitor_data.schemas.proposed_changes import ProposedChangeResponse, ProposalStatus
        mock_update.return_value = ProposedChangeResponse(
            id=str(uuid4()),
            proposal_id=str(uuid4()),
            change_type="event",
            content={"title": "Renamed", "event_id": str(eid), "operation": "update"},
            authority="gm",
            proposer="UI",
            status=ProposalStatus.PENDING,
            confidence=1.0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)
        )
        resp = client.patch(f"{BASE}/events/{eid}", json={"title": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["content"]["title"] == "Renamed"



def test_delete_event_success():
    with patch("monitor_data.tools.mongodb_tools.proposals.mongodb_create_proposed_change") as mock_delete:
        from monitor_data.schemas.proposed_changes import ProposedChangeResponse, ProposalStatus
        mock_delete.return_value = ProposedChangeResponse(
            id=str(uuid4()),
            proposal_id=str(uuid4()),
            change_type="event",
            content={"event_id": str(uuid4()), "operation": "delete"},
            authority="gm",
            proposer="UI",
            status=ProposalStatus.PENDING,
            confidence=1.0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC)
        )
        resp = client.delete(f"{BASE}/events/{uuid4()}")
    assert resp.status_code == 200


# ── relationship update/delete (M-24 / M-25) ──────────────────────


def test_update_relationship_success():
    with patch(f"{REL_TOOLS}.neo4j_update_relationship") as mock_update:
        mock_update.return_value = _relationship(tags=["grim"])
        resp = client.patch(
            f"{BASE}/relationships/42",
            json={"tags": ["grim"], "properties": {"since": "yesterday"}},
        )
    assert resp.status_code == 200
    assert resp.json()["relationship_id"] == "42"
    body = mock_update.call_args.args[1]
    assert body.tags == ["grim"]


def test_update_relationship_404():
    with patch(f"{REL_TOOLS}.neo4j_update_relationship") as mock_update:
        mock_update.side_effect = ValueError("Relationship 999 not found")
        resp = client.patch(f"{BASE}/relationships/999", json={"tags": ["x"]})
    assert resp.status_code == 404


def test_update_relationship_invalid_id_400():
    with patch(f"{REL_TOOLS}.neo4j_update_relationship") as mock_update:
        mock_update.side_effect = ValueError("Invalid relationship ID format: must be a numeric string")
        resp = client.patch(f"{BASE}/relationships/abc", json={"tags": ["x"]})
    assert resp.status_code == 400


def test_delete_relationship_success():
    with patch(f"{REL_TOOLS}.neo4j_delete_relationship") as mock_delete:
        mock_delete.return_value = {"deleted": True, "relationship_id": "42"}
        resp = client.delete(f"{BASE}/relationships/42")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_delete_relationship_404():
    with patch(f"{REL_TOOLS}.neo4j_delete_relationship") as mock_delete:
        mock_delete.side_effect = ValueError("Relationship 999 not found")
        resp = client.delete(f"{BASE}/relationships/999")
    assert resp.status_code == 404


# ── universe-scoped relationship list (F2-2 phase 6) ────────────

ENT_TOOLS = "monitor_data.tools.neo4j_tools.entities"


def _entity(entity_id, universe_id):
    from monitor_data.schemas.base import Authority, CanonLevel, EntityType
    from monitor_data.schemas.entities import EntityResponse

    return EntityResponse(
        id=entity_id,
        universe_id=universe_id,
        name="Entity",
        entity_type=EntityType.CHARACTER,
        is_archetype=False,
        description="",
        properties={},
        canon_level=CanonLevel.CANON,
        confidence=1.0,
        authority=Authority.GM,
        created_at=datetime.now(UTC),
    )


def test_list_universe_relationships_filters_to_universe():
    from monitor_data.schemas.entities import EntityListResponse
    from monitor_data.schemas.relationships import RelationshipListResponse

    uni = uuid4()
    a, b, outsider = uuid4(), uuid4(), uuid4()
    with (
        patch(f"{ENT_TOOLS}.neo4j_list_entities") as mock_entities,
        patch(f"{REL_TOOLS}.neo4j_list_relationships") as mock_rels,
    ):
        mock_entities.return_value = EntityListResponse(
            entities=[_entity(a, uni), _entity(b, uni)], total=2, limit=1000, offset=0
        )
        mock_rels.return_value = RelationshipListResponse(
            relationships=[
                _relationship(from_entity_id=a, to_entity_id=b),
                _relationship(relationship_id="7", from_entity_id=a, to_entity_id=outsider),
            ],
            total=2,
            limit=1000,
            offset=0,
        )
        resp = client.get(f"{BASE}/universes/{uni}/relationships")
    assert resp.status_code == 200
    body = resp.json()
    # the edge touching an entity outside the universe is dropped
    assert body["total"] == 1
    assert {r["relationship_id"] for r in body["relationships"]} == {"42"}


def test_list_universe_relationships_passes_enum_filters():
    from monitor_data.schemas.entities import EntityListResponse
    from monitor_data.schemas.relationships import RelationshipListResponse

    uni = uuid4()
    with (
        patch(f"{ENT_TOOLS}.neo4j_list_entities") as mock_entities,
        patch(f"{REL_TOOLS}.neo4j_list_relationships") as mock_rels,
    ):
        mock_entities.return_value = EntityListResponse(entities=[], total=0, limit=1000, offset=0)
        mock_rels.return_value = RelationshipListResponse(relationships=[], total=0, limit=1000, offset=0)
        resp = client.get(
            f"{BASE}/universes/{uni}/relationships",
            params={"rel_type": "KNOWS", "category": "social"},
        )
    assert resp.status_code == 200
    filters = mock_rels.call_args.args[0]
    assert filters.rel_type == RelationshipType.KNOWS
    assert filters.category == RelationshipCategory.SOCIAL


def test_list_universe_relationships_invalid_rel_type_422():
    resp = client.get(f"{BASE}/universes/{uuid4()}/relationships", params={"rel_type": "NOPE"})
    assert resp.status_code == 422


# ── NPC profile read/upsert (F2-2 phase 5) ──────────────────────

MONGO_TOOLS = "monitor_data.tools.mongodb_tools"


def _profile(entity_id, **over):
    from monitor_data.schemas.npc_profiles import NPCProfileResponse

    data = {
        "profile_id": uuid4(),
        "entity_id": entity_id,
        "universe_id": None,
        "traits": {},
        "values": ["honor"],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "relationship_states_by_universe": {},
        "current_emotional_state_by_universe": {},
        "created_at": datetime.now(UTC),
        "updated_at": None,
    }
    data.update(over)
    return NPCProfileResponse(**data)


def test_get_npc_profile_success():
    npc = uuid4()
    with patch(f"{MONGO_TOOLS}.mongodb_get_npc_profile") as mock_get:
        mock_get.return_value = _profile(npc)
        resp = client.get(f"/api/entities/npcs/{npc}/profile")
    assert resp.status_code == 200
    assert resp.json()["entity_id"] == str(npc)
    assert resp.json()["values"] == ["honor"]


def test_get_npc_profile_404():
    with patch(f"{MONGO_TOOLS}.mongodb_get_npc_profile") as mock_get:
        mock_get.return_value = None
        resp = client.get(f"/api/entities/npcs/{uuid4()}/profile")
    assert resp.status_code == 404


def test_upsert_npc_profile_passes_update_through():
    npc = uuid4()
    with patch(f"{MONGO_TOOLS}.mongodb_update_npc_profile") as mock_update:
        mock_update.return_value = _profile(npc, values=["freedom"])
        resp = client.put(
            f"/api/entities/npcs/{npc}/profile",
            json={
                "values": ["freedom"],
                "speech_style": "terse military clipped",
                "triggers": [
                    {
                        "condition": "asked about the war",
                        "reaction": "goes quiet",
                        "intensity": 0.8,
                        "is_hidden": True,
                    }
                ],
            },
        )
    assert resp.status_code == 200
    assert resp.json()["values"] == ["freedom"]
    assert mock_update.call_args.args[0] == npc
    update = mock_update.call_args.args[1]
    assert update.values == ["freedom"]
    assert update.triggers[0].condition == "asked about the war"


def test_upsert_npc_profile_invalid_submodel_422():
    resp = client.put(
        f"/api/entities/npcs/{uuid4()}/profile",
        json={"triggers": [{"condition": "x"}]},  # missing required reaction
    )
    assert resp.status_code == 422
