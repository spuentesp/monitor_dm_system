"""Tests for the character → canon promotion route."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)


def _fake_listener(events=None, lore=None, threads=None) -> MagicMock:
    listener = MagicMock()
    extraction = MagicMock()
    extraction.events = events or []
    extraction.new_lore = lore or []
    extraction.active_threads = threads or []
    listener.forward = MagicMock(return_value=extraction)
    return listener


def _conv_doc(conversation_id: str = "conv-1", turns=None) -> dict:
    return {
        "conversation_id": conversation_id,
        "status": "active",
        "lorebook_character_ids": ["char-1"],
        "turns": (
            turns
            if turns is not None
            else [
                {"turn_index": 0, "speaker_role": "player", "entity_name": "Kael", "text": "Hello."},
                {"turn_index": 1, "speaker_role": "npc", "entity_name": "Maeve", "text": "Well met."},
            ]
        ),
    }


def _character_doc() -> dict:
    return {
        "id": "char-1",
        "name": "Maeve",
        "description": "A wary ranger.",
        "personality": "Cautious.",
        "is_ooc_persona": False,
    }


def test_promote_emits_proposals_for_each_kind():
    """Events, lore, and threads each become a ProposedChange; counts match."""
    fake_event = MagicMock(
        statement="Kael drew the silvered blade.",
        involved_entities=["Kael", "Maeve"],
        consequence="Maeve took a step back.",
        is_lore=False,
    )
    listener = _fake_listener(
        events=[fake_event],
        lore=["A new ward has been raised."],
        threads=["The silvered blade hungers."],
    )

    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = _conv_doc()

    with (
        patch("monitor_ui.routers.character_storage.get_character", return_value=_character_doc()),
        patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
        patch("monitor_agents.ingestion.session_ingest.SessionListenerModule", return_value=listener),
    ):
        resp = client.post(
            "/api/entities/characters/char-1/promote",
            json={"context": "A friendly chat"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["character_id"] == "char-1"
    assert body["conversation_id"] == "conv-1"
    assert body["events_proposed"] == 1
    assert body["lore_proposed"] == 1
    assert body["threads_proposed"] == 1
    assert len(body["proposal_ids"]) == 3
    assert body["skipped"] == []

    inserts = mongo.get_collection.return_value.insert_one.call_args_list
    assert len(inserts) == 3
    docs = [c.args[0] for c in inserts]
    assert docs[0]["content"]["statement"] == "Kael drew the silvered blade."
    assert docs[0]["content"]["involved_entities"] == ["Kael", "Maeve"]
    assert docs[0]["proposer"] == "character_promotion:char-1"
    assert docs[0]["change_type"] == "fact"
    assert docs[0]["status"] == "pending"
    assert docs[0]["authority"] == "system"
    assert docs[1]["content"]["statement"] == "A new ward has been raised."
    assert docs[2]["content"]["description"] == "The silvered blade hungers."


def test_promote_skips_empty_statements():
    """Listener outputs without a statement are reported in `skipped` and don't error."""
    fake_event = MagicMock(statement="   ", involved_entities=[], consequence=None, is_lore=False)
    listener = _fake_listener(events=[fake_event], lore=["", "Real lore."], threads=["A real thread."])

    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = _conv_doc()

    with (
        patch("monitor_ui.routers.character_storage.get_character", return_value=_character_doc()),
        patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
        patch("monitor_agents.ingestion.session_ingest.SessionListenerModule", return_value=listener),
    ):
        resp = client.post("/api/entities/characters/char-1/promote", json={})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["events_proposed"] == 0
    assert body["lore_proposed"] == 1
    assert body["threads_proposed"] == 1
    assert any("empty" in s for s in body["skipped"])
    assert mongo.get_collection.return_value.insert_one.call_count == 2


def test_promote_returns_404_when_character_missing():
    with (
        patch("monitor_ui.routers.character_storage.get_character", return_value=None),
    ):
        resp = client.post("/api/entities/characters/missing/promote", json={})
    assert resp.status_code == 404


def test_promote_returns_404_when_conversation_id_given_but_missing():
    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = None

    with (
        patch("monitor_ui.routers.character_storage.get_character", return_value=_character_doc()),
        patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
    ):
        resp = client.post(
            "/api/entities/characters/char-1/promote",
            json={"conversation_id": "ghost"},
        )
    assert resp.status_code == 404


def test_promote_returns_409_when_no_active_conversation():
    mongo = MagicMock()
    # Both find_one calls (with conversation_id and the active-listing) return None.
    mongo.get_collection.return_value.find_one.return_value = None

    with (
        patch("monitor_ui.routers.character_storage.get_character", return_value=_character_doc()),
        patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
    ):
        resp = client.post("/api/entities/characters/char-1/promote", json={})
    assert resp.status_code == 409


def test_promote_returns_422_for_empty_transcript():
    conv = _conv_doc(turns=[])
    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = conv

    with (
        patch("monitor_ui.routers.character_storage.get_character", return_value=_character_doc()),
        patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
        patch("monitor_agents.ingestion.session_ingest.SessionListenerModule", return_value=_fake_listener()),
    ):
        resp = client.post("/api/entities/characters/char-1/promote", json={})
    assert resp.status_code == 422


def test_promote_uses_supplied_conversation_id():
    listener = _fake_listener(events=[])
    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = _conv_doc(conversation_id="conv-explicit")

    with (
        patch("monitor_ui.routers.character_storage.get_character", return_value=_character_doc()),
        patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
        patch("monitor_agents.ingestion.session_ingest.SessionListenerModule", return_value=listener),
    ):
        resp = client.post(
            "/api/entities/characters/char-1/promote",
            json={"conversation_id": "conv-explicit"},
        )

    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == "conv-explicit"
    # The lookup was by conversation_id, not the active-character search.
    args, _ = mongo.get_collection.return_value.find_one.call_args
    assert args[0] == {"conversation_id": "conv-explicit"}


def test_promote_proposal_creation_failure_lands_in_skipped():
    """If insert_one raises, the route keeps going and reports the failure."""
    fake_event = MagicMock(statement="Something happened.", involved_entities=[], consequence=None, is_lore=False)
    listener = _fake_listener(events=[fake_event])

    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = _conv_doc()
    mongo.get_collection.return_value.insert_one.side_effect = RuntimeError("mongo down")

    with (
        patch("monitor_ui.routers.character_storage.get_character", return_value=_character_doc()),
        patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
        patch("monitor_agents.ingestion.session_ingest.SessionListenerModule", return_value=listener),
    ):
        resp = client.post("/api/entities/characters/char-1/promote", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["events_proposed"] == 0
    assert body["proposal_ids"] == []
    assert any("mongo down" in s for s in body["skipped"])
