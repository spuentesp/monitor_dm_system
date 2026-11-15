"""Tests for ShareAgent — CF-14 player-facing sharing (G07).

Fake MCP clients only (no databases): every ``call_tool`` is a dict-keyed
async stub. The spoiler filter must reuse CF-6's witnessed-facts logic —
``monitor_agents.cast.filter_visible_facts`` — so these tests pin both the
behavior (party / character scoping, drafts unreachable) and the reuse
(no second visibility implementation in player_share).

Run:
    uv run pytest packages/agents/tests/test_player_share.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from monitor_agents import cast as cast_module
from monitor_agents import player_share as player_share_module
from monitor_agents.player_share import (
    ShareAccessError,
    ShareAgent,
    ShareTokenError,
)
from monitor_data.schemas.player_share import (
    PlayerShare,
    ShareArtifactType,
    SharedArtifact,
)

# ===========================================================================
# FIXTURES / FAKES
# ===========================================================================


def _make_agent(responses: dict[str, Any]) -> tuple[ShareAgent, list[tuple[str, dict]]]:
    """ShareAgent whose MCP calls resolve from ``responses`` (value or callable)."""
    agent = ShareAgent(agent_id="test-share-agent")
    calls: list[tuple[str, dict]] = []

    async def fake_call(name: str, arguments: dict[str, Any]) -> Any:
        calls.append((name, arguments))
        if name not in responses:
            raise KeyError(f"unexpected tool call: {name}")
        value = responses[name]
        return value(arguments) if callable(value) else value

    agent.call_tool = fake_call  # type: ignore[method-assign]
    return agent, calls


def _share(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": str(uuid4()),
        "story_id": str(uuid4()),
        "universe_id": str(uuid4()),
        "owner_id": "gm-1",
        "token": "tok-valid-abcdefghijklmnop",
        "revoked": False,
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": None,
    }
    base.update(over)
    return base


def _artifact(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": str(uuid4()),
        "story_id": str(uuid4()),
        "universe_id": str(uuid4()),
        "owner_id": "gm-1",
        "artifact_type": "recap",
        "title": "Session 4 recap",
        "content": "They opened the sealed door.",
        "spoiler_level": "party",
        "scope_character_id": None,
        "source_fact_ids": [],
        "session_id": None,
        "published": True,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    base.update(over)
    return base


def _fact(*, witnesses: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "statement": "The key is under the mat.",
        "witnesses": witnesses if witnesses is not None else [],
    }


@pytest.fixture
def story_id() -> UUID:
    return uuid4()


# ===========================================================================
# Anti-duplication: CF-6 witnessed-facts logic is shared, not copied
# ===========================================================================


def test_spoiler_filter_reuses_cf6_witnessed_facts_helper() -> None:
    assert player_share_module.filter_visible_facts is cast_module.filter_visible_facts


# ===========================================================================
# Token resolution
# ===========================================================================


class TestResolveShare:
    async def test_unknown_token_raises(self) -> None:
        agent, _ = _make_agent({"mongodb_get_player_share_by_token": None})
        with pytest.raises(ShareTokenError):
            await agent.resolve_share("nope")

    async def test_revoked_token_raises(self) -> None:
        agent, _ = _make_agent({"mongodb_get_player_share_by_token": _share(revoked=True)})
        with pytest.raises(ShareTokenError):
            await agent.resolve_share("tok")

    async def test_expired_token_raises(self) -> None:
        past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        agent, _ = _make_agent({"mongodb_get_player_share_by_token": _share(expires_at=past)})
        with pytest.raises(ShareTokenError):
            await agent.resolve_share("tok")

    async def test_valid_token_resolves(self) -> None:
        doc = _share()
        agent, _ = _make_agent({"mongodb_get_player_share_by_token": doc})
        share = await agent.resolve_share("tok")
        assert isinstance(share, PlayerShare)
        assert str(share.story_id) == doc["story_id"]


# ===========================================================================
# Player view — published-only + spoiler filtering
# ===========================================================================


class TestBuildPlayerView:
    async def test_lists_only_published_artifacts(self, story_id: UUID) -> None:
        published = _artifact(story_id=str(story_id), title="Published recap")
        draft = _artifact(story_id=str(story_id), title="Draft recap", published=False)
        share = _share(story_id=str(story_id))
        agent, calls = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                # The fake ignores published_only — the agent must still
                # refuse to surface the draft (defense in depth).
                "mongodb_list_shared_artifacts": [draft, published],
                "neo4j_list_parties": [],
            }
        )
        view = await agent.build_player_view(story_id, "tok")
        titles = [a.title for a in view.artifacts]
        assert titles == ["Published recap"]
        assert draft["id"] not in [str(a.id) for a in view.artifacts]
        list_call = next(a for n, a in calls if n == "mongodb_list_shared_artifacts")
        assert list_call["published_only"] is True

    async def test_token_from_other_story_is_rejected(self, story_id: UUID) -> None:
        foreign_story = str(uuid4())
        share = _share(story_id=foreign_story)
        agent, _ = _make_agent({"mongodb_get_player_share_by_token": share})
        with pytest.raises(ShareTokenError):
            await agent.build_player_view(story_id, "tok")

    async def test_party_artifact_visible_without_character(self, story_id: UUID) -> None:
        share = _share(story_id=str(story_id))
        party_artifact = _artifact(story_id=str(story_id), spoiler_level="party")
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_list_shared_artifacts": [party_artifact],
                "neo4j_list_parties": [],
            }
        )
        view = await agent.build_player_view(story_id, "tok")
        assert [str(a.id) for a in view.artifacts] == [party_artifact["id"]]

    async def test_character_scoped_hidden_without_selection(self, story_id: UUID) -> None:
        share = _share(story_id=str(story_id))
        scoped = _artifact(
            story_id=str(story_id),
            spoiler_level="character",
            scope_character_id=str(uuid4()),
        )
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_list_shared_artifacts": [scoped],
                "neo4j_list_parties": [],
            }
        )
        view = await agent.build_player_view(story_id, "tok")
        assert view.artifacts == []

    async def test_character_scoped_visible_to_scoped_character(self, story_id: UUID) -> None:
        alice = uuid4()
        share = _share(story_id=str(story_id))
        scoped = _artifact(
            story_id=str(story_id),
            spoiler_level="character",
            scope_character_id=str(alice),
            source_fact_ids=[str(uuid4())],
        )
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_list_shared_artifacts": [scoped],
                "neo4j_list_parties": [],
            }
        )
        view = await agent.build_player_view(story_id, "tok", character_id=alice)
        assert [str(a.id) for a in view.artifacts] == [scoped["id"]]

    async def test_character_scoped_hidden_from_unrelated_character(self, story_id: UUID) -> None:
        alice, bob = uuid4(), uuid4()
        fact = _fact(witnesses=[str(alice)])  # only Alice witnessed it
        share = _share(story_id=str(story_id))
        scoped = _artifact(
            story_id=str(story_id),
            universe_id=str(uuid4()),
            spoiler_level="character",
            scope_character_id=str(alice),
            source_fact_ids=[fact["id"]],
        )
        agent, calls = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_list_shared_artifacts": [scoped],
                "neo4j_list_parties": [],
                "neo4j_list_facts": [fact],
            }
        )
        view = await agent.build_player_view(story_id, "tok", character_id=bob)
        assert view.artifacts == []
        # Bob's view did consult the witnessed-facts query.
        assert any(name == "neo4j_list_facts" for name, _ in calls)

    async def test_character_scoped_visible_when_viewer_witnessed_all_facts(self, story_id: UUID) -> None:
        alice, bob = uuid4(), uuid4()
        fact_a = _fact(witnesses=[str(alice), str(bob)])
        fact_b = _fact(witnesses=[str(bob)])  # common-to-both? no: both must see all
        # Both facts witnessed by Bob → no new spoiler for him.
        fact_b["witnesses"] = [str(alice), str(bob)]
        share = _share(story_id=str(story_id))
        scoped = _artifact(
            story_id=str(story_id),
            universe_id=str(uuid4()),
            spoiler_level="character",
            scope_character_id=str(alice),
            source_fact_ids=[fact_a["id"], fact_b["id"]],
        )
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_list_shared_artifacts": [scoped],
                "neo4j_list_parties": [],
                "neo4j_list_facts": [fact_a, fact_b],
            }
        )
        view = await agent.build_player_view(story_id, "tok", character_id=bob)
        assert [str(a.id) for a in view.artifacts] == [scoped["id"]]

    async def test_partial_witness_blocks_other_character(self, story_id: UUID) -> None:
        alice, bob = uuid4(), uuid4()
        fact_a = _fact(witnesses=[str(alice), str(bob)])
        fact_b = _fact(witnesses=[str(alice)])  # Bob missed this one
        share = _share(story_id=str(story_id))
        scoped = _artifact(
            story_id=str(story_id),
            universe_id=str(uuid4()),
            spoiler_level="character",
            scope_character_id=str(alice),
            source_fact_ids=[fact_a["id"], fact_b["id"]],
        )
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_list_shared_artifacts": [scoped],
                "neo4j_list_parties": [],
                "neo4j_list_facts": [fact_a, fact_b],
            }
        )
        view = await agent.build_player_view(story_id, "tok", character_id=bob)
        assert view.artifacts == []

    async def test_common_knowledge_facts_expose_to_any_character(self, story_id: UUID) -> None:
        alice, bob = uuid4(), uuid4()
        fact = _fact(witnesses=[])  # no witnesses → common knowledge
        share = _share(story_id=str(story_id))
        scoped = _artifact(
            story_id=str(story_id),
            universe_id=str(uuid4()),
            spoiler_level="character",
            scope_character_id=str(alice),
            source_fact_ids=[fact["id"]],
        )
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_list_shared_artifacts": [scoped],
                "neo4j_list_parties": [],
                "neo4j_list_facts": [fact],
            }
        )
        view = await agent.build_player_view(story_id, "tok", character_id=bob)
        assert [str(a.id) for a in view.artifacts] == [scoped["id"]]

    async def test_missing_source_fact_is_conservative(self, story_id: UUID) -> None:
        alice, bob = uuid4(), uuid4()
        present = _fact(witnesses=[str(alice), str(bob)])
        gone_id = str(uuid4())  # referenced but no longer in Neo4j
        share = _share(story_id=str(story_id))
        scoped = _artifact(
            story_id=str(story_id),
            universe_id=str(uuid4()),
            spoiler_level="character",
            scope_character_id=str(alice),
            source_fact_ids=[present["id"], gone_id],
        )
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_list_shared_artifacts": [scoped],
                "neo4j_list_parties": [],
                "neo4j_list_facts": [present],
            }
        )
        view = await agent.build_player_view(story_id, "tok", character_id=bob)
        assert view.artifacts == []

    async def test_roster_failure_does_not_break_the_view(self, story_id: UUID) -> None:
        share = _share(story_id=str(story_id))
        party_artifact = _artifact(story_id=str(story_id))

        def boom(_args: dict[str, Any]) -> Any:
            raise RuntimeError("neo4j down")

        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_list_shared_artifacts": [party_artifact],
                "neo4j_list_parties": boom,
            }
        )
        view = await agent.build_player_view(story_id, "tok")
        assert len(view.artifacts) == 1
        assert view.characters == []

    async def test_roster_returns_party_member_names(self, story_id: UUID) -> None:
        member_id = uuid4()
        share = _share(story_id=str(story_id))
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_list_shared_artifacts": [],
                "neo4j_list_parties": [
                    {
                        "id": str(uuid4()),
                        "members": [{"entity_id": str(member_id)}],
                    }
                ],
                "neo4j_get_entity": {"name": "Mira"},
            }
        )
        view = await agent.build_player_view(story_id, "tok")
        assert [(str(c.id), c.name) for c in view.characters] == [(str(member_id), "Mira")]


# ===========================================================================
# Detail reads — drafts / foreign ids / wrong type are all 404-class
# ===========================================================================


class TestGetVisibleArtifact:
    async def test_returns_published_party_artifact(self, story_id: UUID) -> None:
        art = _artifact(story_id=str(story_id))
        share = _share(story_id=str(story_id))
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_get_shared_artifact": art,
            }
        )
        loaded = await agent.get_visible_artifact(story_id, "tok", UUID(art["id"]))
        assert str(loaded.id) == art["id"]

    async def test_draft_is_inaccessible(self, story_id: UUID) -> None:
        art = _artifact(story_id=str(story_id), published=False)
        share = _share(story_id=str(story_id))
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_get_shared_artifact": art,
            }
        )
        with pytest.raises(ShareAccessError):
            await agent.get_visible_artifact(story_id, "tok", UUID(art["id"]))

    async def test_foreign_story_artifact_is_inaccessible(self, story_id: UUID) -> None:
        art = _artifact(story_id=str(uuid4()))  # belongs to another story
        share = _share(story_id=str(story_id))
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_get_shared_artifact": art,
            }
        )
        with pytest.raises(ShareAccessError):
            await agent.get_visible_artifact(story_id, "tok", UUID(art["id"]))

    async def test_wrong_artifact_type_is_inaccessible(self, story_id: UUID) -> None:
        art = _artifact(story_id=str(story_id), artifact_type="handout")
        share = _share(story_id=str(story_id))
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_get_shared_artifact": art,
            }
        )
        with pytest.raises(ShareAccessError):
            await agent.get_visible_artifact(
                story_id,
                "tok",
                UUID(art["id"]),
                expected_type=ShareArtifactType.RECAP,
            )

    async def test_invisible_character_scoped_handout_is_inaccessible(self, story_id: UUID) -> None:
        alice, bob = uuid4(), uuid4()
        art = _artifact(
            story_id=str(story_id),
            universe_id=str(uuid4()),
            artifact_type="handout",
            spoiler_level="character",
            scope_character_id=str(alice),
            source_fact_ids=[str(uuid4())],
        )
        share = _share(story_id=str(story_id))
        agent, _ = _make_agent(
            {
                "mongodb_get_player_share_by_token": share,
                "mongodb_get_shared_artifact": art,
                "neo4j_list_facts": [_fact(witnesses=[str(alice)])],
            }
        )
        with pytest.raises(ShareAccessError):
            await agent.get_visible_artifact(
                story_id,
                "tok",
                UUID(art["id"]),
                character_id=bob,
                expected_type=ShareArtifactType.HANDOUT,
            )

    async def test_revoked_token_blocks_detail(self, story_id: UUID) -> None:
        art = _artifact(story_id=str(story_id))
        share = _share(story_id=str(story_id), revoked=True)
        agent, _ = _make_agent({"mongodb_get_player_share_by_token": share})
        with pytest.raises(ShareTokenError):
            await agent.get_visible_artifact(story_id, "tok", UUID(art["id"]))


# ===========================================================================
# Publish / unpublish / revoke
# ===========================================================================


class TestPublishFlow:
    async def test_publish_mints_link_when_none_exists(self, story_id: UUID) -> None:
        universe_id = uuid4()
        new_share = _share(story_id=str(story_id), universe_id=str(universe_id))
        created_artifact = _artifact(story_id=str(story_id), published=True)
        agent, calls = _make_agent(
            {
                "mongodb_get_player_share_for_story": None,
                "mongodb_create_player_share": new_share,
                "mongodb_create_shared_artifact": created_artifact,
            }
        )
        share, artifact = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.RECAP,
            title="Session 4 recap",
            content="They opened the sealed door.",
        )
        names = [n for n, _ in calls]
        assert "mongodb_create_player_share" in names
        assert "mongodb_create_shared_artifact" in names
        assert share.token == new_share["token"]
        assert artifact.published is True

        # The artifact create was stamped published=True.
        create_args = next(a for n, a in calls if n == "mongodb_create_shared_artifact")
        assert create_args["params"]["published"] is True
        assert create_args["params"]["story_id"] == str(story_id)

    async def test_publish_reuses_active_link(self, story_id: UUID) -> None:
        universe_id = uuid4()
        existing = _share(story_id=str(story_id), universe_id=str(universe_id))
        agent, calls = _make_agent(
            {
                "mongodb_get_player_share_for_story": existing,
                "mongodb_create_shared_artifact": _artifact(story_id=str(story_id), published=True),
            }
        )
        share, _ = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.HANDOUT,
            title="Letter",
            content="Come at dawn.",
        )
        names = [n for n, _ in calls]
        assert "mongodb_create_player_share" not in names
        assert share.token == existing["token"]

    async def test_publish_mints_new_link_for_foreign_owner(self, story_id: UUID) -> None:
        universe_id = uuid4()
        # Active link exists but belongs to another principal → do not reuse.
        existing = _share(story_id=str(story_id), universe_id=str(universe_id), owner_id="gm-2")
        fresh = _share(story_id=str(story_id), universe_id=str(universe_id))
        agent, calls = _make_agent(
            {
                "mongodb_get_player_share_for_story": existing,
                "mongodb_create_player_share": fresh,
                "mongodb_create_shared_artifact": _artifact(story_id=str(story_id), published=True),
            }
        )
        share, _ = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.RECAP,
            title="Recap",
            content="Body",
        )
        assert share.token == fresh["token"]
        assert any(n == "mongodb_create_player_share" for n, _ in calls)

    async def test_unpublish_passes_predicates(self) -> None:
        agent, calls = _make_agent({"mongodb_set_shared_artifact_published": True})
        artifact_id, universe_id = uuid4(), uuid4()
        ok = await agent.unpublish(artifact_id=artifact_id, universe_id=universe_id, owner_id="gm-1")
        assert ok is True
        name, args = calls[-1]
        assert name == "mongodb_set_shared_artifact_published"
        assert args == {
            "artifact_id": str(artifact_id),
            "universe_id": str(universe_id),
            "owner_id": "gm-1",
            "published": False,
        }

    async def test_unpublish_foreign_artifact_returns_false(self) -> None:
        agent, _ = _make_agent({"mongodb_set_shared_artifact_published": False})
        ok = await agent.unpublish(artifact_id=uuid4(), universe_id=uuid4(), owner_id="gm-1")
        assert ok is False

    async def test_revoke_passes_predicates(self, story_id: UUID) -> None:
        agent, calls = _make_agent({"mongodb_revoke_player_share": True})
        universe_id = uuid4()
        ok = await agent.revoke(story_id=story_id, universe_id=universe_id, owner_id="gm-1")
        assert ok is True
        name, args = calls[-1]
        assert name == "mongodb_revoke_player_share"
        assert args == {
            "story_id": str(story_id),
            "universe_id": str(universe_id),
            "owner_id": "gm-1",
        }


# ===========================================================================
# Markdown export
# ===========================================================================


class TestExportMarkdown:
    def test_contains_title_and_content(self) -> None:
        artifact = SharedArtifact.model_validate(
            _artifact(title="Session 4 recap", content="They opened the sealed door.")
        )
        md = ShareAgent().export_markdown(artifact)
        assert md.startswith("# Session 4 recap\n")
        assert "They opened the sealed door." in md
        assert md.endswith("\n")

    def test_character_scoped_gets_marker(self) -> None:
        artifact = SharedArtifact.model_validate(
            _artifact(
                artifact_type="handout",
                spoiler_level="character",
                scope_character_id=str(uuid4()),
                content="A letter for Alice.",
            )
        )
        md = ShareAgent().export_markdown(artifact)
        assert "Character-scoped handout" in md
        assert "A letter for Alice." in md
