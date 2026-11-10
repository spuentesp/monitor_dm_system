"""Tests for the Phase 7 Part B /gm routes — prep-to-table, lookups, session log.

Each test asserts the cross-component wiring: the real callee (agent method or
data-layer tool) is invoked with the expected arguments. The LLM and the
databases are mocked; the request/response contract is exercised end to end
through the FastAPI app.

Run:
    uv run pytest packages/ui/backend/tests/test_gm_table_routes.py -q -p no:cacheprovider
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from monitor_agents.gm_table import (
    PartyKnowledgeAnswer,
    PrepExtraction,
    PrepNpcItem,
    RulesAnswer,
    SessionLogExtraction,
    SessionLogStatement,
)
from monitor_data.schemas.base import ProposalType
from monitor_data.schemas.entities import EntityResponse
from monitor_data.schemas.gm_prep import (
    GmPrepBundleResponse,
    GmPrepNpc,
    GmPrepThread,
)
from monitor_data.schemas.stories import StoryLedgerEntry
from monitor_ui.main import app

pytestmark = pytest.mark.usefixtures("local_auth_mode")

client = TestClient(app)


def _entity_response(entity_id, name="Mira"):
    return EntityResponse(
        id=entity_id,
        created_at=datetime.now(UTC),
        universe_id=uuid4(),
        name=name,
        entity_type="character",
        is_archetype=False,
        description="A thief with a debt.",
        properties={},
        state_tags=["friendly"],
        canon_level="canon",
        confidence=1.0,
        authority="gm",
    )


def _ledger_entry(story_id):
    return StoryLedgerEntry(
        entry_id=uuid4(),
        sequence=2,
        story_id=story_id,
        scene_id=uuid4(),
        summary="The party returned to Ironwatch and took back the key.",
        state_changes=[],
        open_questions=["What waits below the chapel?"],
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Task 2 — prep to table
# ---------------------------------------------------------------------------


class TestPrepRoutes:
    def test_prep_extract_delegates_with_expected_args(self):
        universe_id = uuid4()
        extraction = PrepExtraction(
            npcs=[PrepNpcItem(name="Mira", want="the key back")],
            notes_summary="A return to Ironwatch.",
        )
        with patch("monitor_ui.routers.gm_tools.GmTableAgent") as mock_agent_cls:
            mock_agent_cls.return_value.extract_prep = AsyncMock(return_value=extraction)
            resp = client.post(
                "/api/gm/prep/extract",
                json={"universe_id": str(universe_id), "notes": "Mira wants the key back"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["npcs"][0]["name"] == "Mira"
        assert body["notes_summary"] == "A return to Ironwatch."
        mock_agent_cls.return_value.extract_prep.assert_awaited_once_with(
            universe_id=universe_id, notes="Mira wants the key back"
        )

    def test_prep_extract_rejects_empty_notes(self):
        resp = client.post(
            "/api/gm/prep/extract",
            json={"universe_id": str(uuid4()), "notes": ""},
        )
        assert resp.status_code == 422

    def test_prep_commit_writes_threads_stages_entities_and_saves_bundle(self):
        universe_id = uuid4()
        story_id = uuid4()
        thread_uuid = uuid4()
        proposal_ids = [uuid4(), uuid4()]
        bundle = GmPrepBundleResponse(
            universe_id=universe_id,
            story_id=story_id,
            npcs=[GmPrepNpc(name="Mira")],
            updated_at=datetime.now(UTC),
        )
        with (
            patch(
                "monitor_ui.routers.gm_tools.neo4j_create_plot_thread",
                return_value=SimpleNamespace(id=thread_uuid),
            ) as mock_thread,
            patch(
                "monitor_ui.routers.gm_tools.mongodb_create_proposed_change",
                side_effect=[SimpleNamespace(proposal_id=pid) for pid in proposal_ids],
            ) as mock_proposal,
            patch(
                "monitor_ui.routers.gm_tools.mongodb_upsert_gm_prep_bundle",
                return_value=bundle,
            ) as mock_bundle,
        ):
            resp = client.post(
                "/api/gm/prep/commit",
                json={
                    "universe_id": str(universe_id),
                    "story_id": str(story_id),
                    "npcs": [
                        {"name": "Mira", "want": "the key back"},
                        {"name": "The guild master", "existing_entity_id": str(uuid4())},
                    ],
                    "locations": [{"name": "The Sunken Chapel"}],
                    "threads": [{"title": "The sealed door", "description": "below"}],
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["committed_thread_ids"] == [str(thread_uuid)]
        assert body["staged_proposal_ids"] == [str(pid) for pid in proposal_ids]

        # Real callee 1: plot thread created with the reviewed thread's fields.
        plot_thread = mock_thread.call_args.args[0]
        assert str(plot_thread.story_id) == str(story_id)
        assert plot_thread.title == "The sealed door"
        assert plot_thread.gm_notes == "below"

        # Real callee 2: one ENTITY proposal per new NPC/location — the NPC
        # that already exists in canon is NOT staged again.
        assert mock_proposal.call_count == 2
        staged_names = set()
        for call in mock_proposal.call_args_list:
            create = call.args[0]
            assert create.change_type == ProposalType.ENTITY
            assert create.story_id == story_id
            staged_names.add(create.content["name"])
        assert staged_names == {"Mira", "The Sunken Chapel"}

        # Real callee 3: the bundle is saved with the committed thread id.
        upsert = mock_bundle.call_args.args[0]
        assert upsert.universe_id == universe_id
        assert upsert.story_id == story_id
        assert upsert.threads[0].thread_id == str(thread_uuid)

    def test_prep_get_reads_bundle_with_expected_args(self):
        universe_id = uuid4()
        bundle = GmPrepBundleResponse(
            universe_id=universe_id,
            story_id=None,
            threads=[GmPrepThread(title="The sealed door", thread_id="t-1")],
            updated_at=datetime.now(UTC),
        )
        with patch(
            "monitor_ui.routers.gm_tools.mongodb_get_gm_prep_bundle",
            return_value=bundle,
        ) as mock_get:
            resp = client.get(f"/api/gm/prep/{universe_id}")

        assert resp.status_code == 200
        assert resp.json()["found"] is True
        assert resp.json()["bundle"]["threads"][0]["title"] == "The sealed door"
        mock_get.assert_called_once_with(universe_id, None)

    def test_prep_get_absent_bundle_reports_not_found(self):
        universe_id = uuid4()
        story_id = uuid4()
        with patch(
            "monitor_ui.routers.gm_tools.mongodb_get_gm_prep_bundle",
            return_value=None,
        ) as mock_get:
            resp = client.get(f"/api/gm/prep/{universe_id}", params={"story_id": str(story_id)})

        assert resp.status_code == 200
        assert resp.json() == {"found": False, "bundle": None}
        mock_get.assert_called_once_with(universe_id, story_id)


# ---------------------------------------------------------------------------
# Task 3 — at-the-table lookups
# ---------------------------------------------------------------------------


class TestNpcLookup:
    def test_dossier_resolves_by_name_and_gathers_context(self):
        universe_id = uuid4()
        entity_id = uuid4()
        entity = _entity_response(entity_id)
        with (
            patch(
                "monitor_ui.routers.gm_tools.neo4j_search_entities",
                return_value=[{"id": str(entity_id), "name": "Mira"}],
            ) as mock_search,
            patch("monitor_ui.routers.gm_tools.neo4j_get_entity", return_value=entity) as mock_get,
            patch(
                "monitor_ui.routers.gm_tools.neo4j_list_agendas",
                return_value=[{"id": "a-1", "owner_id": str(entity_id), "title": "Get the key back"}],
            ) as mock_agendas,
            patch(
                "monitor_ui.routers.gm_tools.neo4j_list_relationships",
                return_value=SimpleNamespace(relationships=[]),
            ),
            patch(
                "monitor_ui.routers.gm_tools.neo4j_list_facts",
                return_value=[],
            ) as mock_facts,
        ):
            resp = client.post(
                "/api/gm/lookup/npc",
                json={"universe_id": str(universe_id), "name": "Mira"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is True
        assert body["entity"]["name"] == "Mira"
        assert body["agendas"] == [{"id": "a-1", "owner_id": str(entity_id), "title": "Get the key back"}]
        mock_search.assert_called_once_with(universe_id, "Mira")
        mock_get.assert_called_once_with(entity_id)
        mock_agendas.assert_called_once_with(universe_id, status=None)
        assert mock_facts.call_args.args[0].entity_id == entity_id
        assert mock_facts.call_args.args[0].universe_id == universe_id

    def test_unknown_name_reports_not_found(self):
        universe_id = uuid4()
        with patch("monitor_ui.routers.gm_tools.neo4j_search_entities", return_value=[]):
            resp = client.post(
                "/api/gm/lookup/npc",
                json={"universe_id": str(universe_id), "name": "Nobody"},
            )
        assert resp.status_code == 200
        assert resp.json()["found"] is False


class TestPartyKnowledgeLookup:
    def test_passes_party_member_ids_to_the_agent(self):
        universe_id = uuid4()
        party_id = uuid4()
        member_a, member_b = uuid4(), uuid4()
        with (
            patch(
                "monitor_ui.routers.gm_tools.neo4j_get_party",
                return_value=SimpleNamespace(
                    members=[
                        SimpleNamespace(entity_id=member_a),
                        SimpleNamespace(entity_id=member_b),
                    ]
                ),
            ) as mock_party,
            patch("monitor_ui.routers.gm_tools.GmTableAgent") as mock_agent_cls,
        ):
            mock_agent_cls.return_value.party_knowledge = AsyncMock(
                return_value=PartyKnowledgeAnswer(topic="the cult", summary="They know the name.")
            )
            resp = client.post(
                "/api/gm/lookup/party-knowledge",
                json={
                    "universe_id": str(universe_id),
                    "party_id": str(party_id),
                    "topic": "the cult",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["summary"] == "They know the name."
        mock_party.assert_called_once_with(party_id)
        mock_agent_cls.return_value.party_knowledge.assert_awaited_once_with(
            universe_id=universe_id,
            character_ids=[member_a, member_b],
            topic="the cult",
        )

    def test_requires_at_least_one_character(self):
        resp = client.post(
            "/api/gm/lookup/party-knowledge",
            json={"universe_id": str(uuid4()), "topic": "anything"},
        )
        assert resp.status_code == 422


class TestLastSessionLookup:
    def test_returns_ledger_entry_and_transcript_tail(self):
        universe_id = uuid4()
        story_id = uuid4()
        entry = _ledger_entry(story_id)
        with (
            patch(
                "monitor_ui.routers.gm_tools.mongodb_list_story_ledger_entries",
                return_value=[entry],
            ) as mock_ledger,
            patch(
                "monitor_ui.routers.gm_tools.db_load_sessions",
                return_value=[
                    {"id": "s-old", "story_id": str(story_id), "updated_at": "2026-11-01", "title": "Session 1"},
                    {"id": "s-new", "story_id": str(story_id), "updated_at": "2026-11-08", "title": "Session 2"},
                ],
            ),
            patch(
                "monitor_ui.routers.gm_tools.db_load_messages",
                return_value=[{"role": "gm", "content": "The gate opens.", "timestamp": "t1"}],
            ) as mock_messages,
        ):
            resp = client.post(
                "/api/gm/lookup/last-session",
                json={"universe_id": str(universe_id), "story_id": str(story_id)},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is True
        assert body["ledger_entry"]["summary"].startswith("The party returned")
        assert body["session_id"] == "s-new"
        assert body["transcript"] == [{"role": "gm", "content": "The gate opens.", "timestamp": "t1"}]
        mock_ledger.assert_called_once_with(story_id, limit=2)
        mock_messages.assert_called_once_with("s-new")

    def test_no_history_reports_not_found(self):
        universe_id = uuid4()
        story_id = uuid4()
        with (
            patch("monitor_ui.routers.gm_tools.mongodb_list_story_ledger_entries", return_value=[]),
            patch("monitor_ui.routers.gm_tools.db_load_sessions", return_value=[]),
        ):
            resp = client.post(
                "/api/gm/lookup/last-session",
                json={"universe_id": str(universe_id), "story_id": str(story_id)},
            )
        assert resp.status_code == 200
        assert resp.json()["found"] is False


class TestImproviseLookup:
    def test_name_suggestion_delegates_to_light_agent(self):
        universe_id = uuid4()
        with patch("monitor_ui.routers.gm_tools.light_table_agent") as mock_light:
            agent = mock_light.return_value
            agent.suggest_names = AsyncMock(return_value=SimpleNamespace(names=["Tovin"], rationale="fits"))
            resp = client.post(
                "/api/gm/lookup/improvise",
                json={"universe_id": str(universe_id), "kind": "name", "context": "a dock warden"},
            )

        assert resp.status_code == 200
        assert resp.json() == {"kind": "name", "suggestions": ["Tovin"], "rationale": "fits"}
        agent.suggest_names.assert_awaited_once_with(universe_id=universe_id, context="a dock warden", count=3)

    def test_complication_suggestion_delegates_to_light_agent(self):
        universe_id = uuid4()
        story_id = uuid4()
        with patch("monitor_ui.routers.gm_tools.light_table_agent") as mock_light:
            agent = mock_light.return_value
            agent.suggest_complications = AsyncMock(
                return_value=SimpleNamespace(complications=["The door opens."], rationale="presses")
            )
            resp = client.post(
                "/api/gm/lookup/improvise",
                json={
                    "universe_id": str(universe_id),
                    "story_id": str(story_id),
                    "kind": "complication",
                    "context": "the party stalls",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["suggestions"] == ["The door opens."]
        agent.suggest_complications.assert_awaited_once_with(
            universe_id=universe_id,
            context="the party stalls",
            count=3,
            story_id=story_id,
        )


class TestRulesLookup:
    def test_resolves_universe_binding_then_answers(self):
        universe_id = uuid4()
        system_id = uuid4()
        with (
            patch(
                "monitor_ui.routers.gm_tools.resolve_universe_system_binding",
                return_value={"system_id": str(system_id)},
            ) as mock_binding,
            patch("monitor_ui.routers.gm_tools.GmTableAgent") as mock_agent_cls,
        ):
            mock_agent_cls.return_value.answer_rules = AsyncMock(
                return_value=RulesAnswer(answer="Roll Might.", source="Grappling", covered=True)
            )
            resp = client.post(
                "/api/gm/lookup/rules",
                json={"universe_id": str(universe_id), "question": "How does grappling work?"},
            )

        assert resp.status_code == 200
        assert resp.json()["source"] == "Grappling"
        mock_binding.assert_called_once_with(str(universe_id))
        mock_agent_cls.return_value.answer_rules.assert_awaited_once_with(
            system_id=system_id, question="How does grappling work?"
        )

    def test_requires_a_system(self):
        with patch(
            "monitor_ui.routers.gm_tools.resolve_universe_system_binding",
            return_value={"system_id": None},
        ):
            resp = client.post(
                "/api/gm/lookup/rules",
                json={"universe_id": str(uuid4()), "question": "Anything?"},
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Task 4 — after the session
# ---------------------------------------------------------------------------


class TestSessionLogPropose:
    def test_stages_proposals_and_flags_contradictions(self):
        universe_id = uuid4()
        story_id = uuid4()
        batch_statements = [
            SessionLogStatement(statement="the key is now with Mira", participants=["Mira"]),
            SessionLogStatement(statement="the docks burned", locations=["Ironwatch"]),
        ]
        proposal_ids = [uuid4(), uuid4()]
        with (
            patch("monitor_ui.routers.gm_tools.GmTableAgent") as mock_agent_cls,
            patch("monitor_ui.routers.gm_tools.CanonKeeper") as mock_keeper_cls,
            patch(
                "monitor_ui.routers.gm_tools.mongodb_create_proposed_change",
                side_effect=[SimpleNamespace(proposal_id=pid) for pid in proposal_ids],
            ) as mock_proposal,
        ):
            mock_agent_cls.return_value.extract_session_log = AsyncMock(
                return_value=SessionLogExtraction(statements=batch_statements)
            )
            keeper = mock_keeper_cls.return_value
            keeper.check_live_entry = AsyncMock(
                side_effect=[
                    {"has_contradiction": True, "explanation": "Canon says the key is lost."},
                    {"has_contradiction": False, "explanation": ""},
                ]
            )
            keeper.implication_conflict_flags = AsyncMock(
                return_value=[
                    {
                        "statement": "the docks burned",
                        "explanation": "Canon implies the docks are under water.",
                        "severity": "high",
                    }
                ]
            )
            resp = client.post(
                "/api/gm/session-log/propose",
                json={
                    "universe_id": str(universe_id),
                    "story_id": str(story_id),
                    "log_text": "Mira took back the key. The docks burned.",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2

        # Real callee 1: extraction agent invoked with the pasted log.
        mock_agent_cls.return_value.extract_session_log.assert_awaited_once_with(
            universe_id=universe_id, log_text="Mira took back the key. The docks burned."
        )
        # Real callee 2: direct check per statement.
        assert keeper.check_live_entry.await_count == 2
        keeper.check_live_entry.assert_any_await(universe_id=universe_id, entry_text="the key is now with Mira")
        # Real callee 3: G-9 implication check over the whole batch.
        keeper.implication_conflict_flags.assert_awaited_once_with(
            universe_id, ["the key is now with Mira", "the docks burned"]
        )
        # Real callee 4: one pending proposal per statement, flagged when needed.
        assert mock_proposal.call_count == 2
        creates = [c.args[0] for c in mock_proposal.call_args_list]
        assert creates[0].content["statement"] == "the key is now with Mira"
        assert creates[0].needs_review is True
        assert "key is lost" in (creates[0].review_reason or "")
        assert creates[1].needs_review is True
        assert creates[1].review_source == "gm_session_log_flags"
        assert creates[0].source.startswith("session_log:")
        assert creates[0].change_type == ProposalType.FACT

        # Response carries the flags back to the GM.
        assert body["items"][0]["flags"][0]["kind"] == "direct"
        assert body["items"][1]["flags"][0]["kind"] == "implication"
        assert body["items"][0]["proposal_id"] == str(proposal_ids[0])
        assert body["proposal_errors"] == []

    def test_clean_statements_are_staged_unflagged(self):
        universe_id = uuid4()
        story_id = uuid4()
        with (
            patch("monitor_ui.routers.gm_tools.GmTableAgent") as mock_agent_cls,
            patch("monitor_ui.routers.gm_tools.CanonKeeper") as mock_keeper_cls,
            patch(
                "monitor_ui.routers.gm_tools.mongodb_create_proposed_change",
                return_value=SimpleNamespace(proposal_id=uuid4()),
            ) as mock_proposal,
        ):
            mock_agent_cls.return_value.extract_session_log = AsyncMock(
                return_value=SessionLogExtraction(statements=[SessionLogStatement(statement="the party camped")])
            )
            keeper = mock_keeper_cls.return_value
            keeper.check_live_entry = AsyncMock(return_value={"has_contradiction": False, "explanation": ""})
            keeper.implication_conflict_flags = AsyncMock(return_value=[])
            resp = client.post(
                "/api/gm/session-log/propose",
                json={
                    "universe_id": str(universe_id),
                    "story_id": str(story_id),
                    "log_text": "They camped.",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["items"][0]["flags"] == []
        create = mock_proposal.call_args.args[0]
        assert create.needs_review is False
        assert create.review_source is None

    def test_check_failure_writes_nothing(self):
        """A failed contradiction check must not leave half-staged proposals."""
        universe_id = uuid4()
        story_id = uuid4()
        with (
            patch("monitor_ui.routers.gm_tools.GmTableAgent") as mock_agent_cls,
            patch("monitor_ui.routers.gm_tools.CanonKeeper") as mock_keeper_cls,
            patch("monitor_ui.routers.gm_tools.mongodb_create_proposed_change") as mock_proposal,
        ):
            mock_agent_cls.return_value.extract_session_log = AsyncMock(
                return_value=SessionLogExtraction(statements=[SessionLogStatement(statement="the key is with Mira")])
            )
            mock_keeper_cls.return_value.check_live_entry = AsyncMock(side_effect=RuntimeError("canon store down"))
            resp = client.post(
                "/api/gm/session-log/propose",
                json={
                    "universe_id": str(universe_id),
                    "story_id": str(story_id),
                    "log_text": "Mira has the key.",
                },
            )

        assert resp.status_code == 500
        mock_proposal.assert_not_called()

    def test_requires_story_or_scene_context(self):
        """Proposals are story/scene-scoped — without either id, reject up front."""
        with patch("monitor_ui.routers.gm_tools.GmTableAgent") as mock_agent_cls:
            mock_agent_cls.return_value.extract_session_log = AsyncMock()
            resp = client.post(
                "/api/gm/session-log/propose",
                json={"universe_id": str(uuid4()), "log_text": "They camped."},
            )
        assert resp.status_code == 422
        mock_agent_cls.return_value.extract_session_log.assert_not_awaited()

    def test_rejects_empty_log(self):
        resp = client.post(
            "/api/gm/session-log/propose",
            json={"universe_id": str(uuid4()), "story_id": str(uuid4()), "log_text": ""},
        )
        assert resp.status_code == 422
