"""
Basic workings — player-facing sharing (CF-14 / G07).

The share surface is the one GM feature that leaves the GM's own screens:
a recap or handout published to a story's share link is served to players
by a *token*, with no account. So its basic workings are worth pinning at
the behavior level: mint a link, publish to it, unpublish, revoke, and keep
a character-scoped handout away from a PC who has not earned it.

These tests run the shipped path — ShareAgent → the real ``mongodb_*``
tools → a mongomock store — over the hermetic stack. Only the Neo4j-backed
tools (facts, party roster) are stubbed.

Use Cases: CF-14 (G07)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from monitor_agents.player_share import ShareAccessError, ShareAgent, ShareTokenError
from monitor_data.schemas.player_share import ShareArtifactType, ShareSpoilerLevel
from tests.behavior._hermetic_stack import HermeticStack


@pytest.fixture
def story() -> tuple[UUID, UUID]:
    """A (universe, story) pair for the scenario."""
    return uuid4(), uuid4()


def _fact(fact_id: UUID, witnesses: list[str]) -> dict[str, Any]:
    return {"id": str(fact_id), "statement": "The gate opened.", "witnesses": witnesses}


def _stub_roster(hermetic: HermeticStack, characters: list[tuple[UUID, str]]) -> None:
    """Stub the Neo4j tools the share agent reads (facts, roster, entities)."""
    hermetic.override("neo4j_list_parties", [])
    hermetic.override("neo4j_get_entity", None)


class TestShareLinkLifecycle:
    """ensure_share → resolve_share → revoke."""

    async def test_link_is_minted_once_per_story(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        agent = ShareAgent()

        first = await agent.ensure_share(
            universe_id=universe_id, story_id=story_id, owner_id="gm-1"
        )
        second = await agent.ensure_share(
            universe_id=universe_id, story_id=story_id, owner_id="gm-1"
        )

        assert first.token == second.token
        assert len(hermetic.calls_to("mongodb_create_player_share")) == 1

    async def test_another_owner_gets_their_own_token(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        agent = ShareAgent()

        mine = await agent.ensure_share(universe_id=universe_id, story_id=story_id, owner_id="gm-1")
        theirs = await agent.ensure_share(
            universe_id=universe_id, story_id=story_id, owner_id="gm-2"
        )

        assert mine.token != theirs.token

    async def test_revoked_token_no_longer_resolves(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        agent = ShareAgent()
        share = await agent.ensure_share(
            universe_id=universe_id, story_id=story_id, owner_id="gm-1"
        )

        assert await agent.revoke(story_id=story_id, universe_id=universe_id, owner_id="gm-1")
        with pytest.raises(ShareTokenError):
            await agent.resolve_share(share.token)

    async def test_revoking_a_foreign_story_is_a_miss_not_a_crash(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        agent = ShareAgent()
        await agent.ensure_share(universe_id=universe_id, story_id=story_id, owner_id="gm-1")

        assert not await agent.revoke(
            story_id=story_id, universe_id=universe_id, owner_id="someone-else"
        )


class TestPublishAndPlayerView:
    """publish → player view → unpublish."""

    async def test_published_recap_reaches_the_player_view(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        _stub_roster(hermetic, [])
        agent = ShareAgent()

        share, artifact = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.RECAP,
            title="Session 4 recap",
            content="They opened the sealed door.",
        )

        view = await agent.build_player_view(story_id, share.token)
        assert [a.id for a in view.artifacts] == [artifact.id]
        assert view.artifacts[0].title == "Session 4 recap"

    async def test_unpublished_artifact_leaves_the_view(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        _stub_roster(hermetic, [])
        agent = ShareAgent()

        share, artifact = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.RECAP,
            title="Session 4 recap",
            content="They opened the sealed door.",
        )

        assert await agent.unpublish(
            artifact_id=artifact.id, universe_id=universe_id, owner_id="gm-1"
        )
        view = await agent.build_player_view(story_id, share.token)
        assert view.artifacts == []

    async def test_draft_artifact_is_unreachable(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        _stub_roster(hermetic, [])
        agent = ShareAgent()
        share, artifact = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.RECAP,
            title="Session 4 recap",
            content="Body",
        )
        await agent.unpublish(artifact_id=artifact.id, universe_id=universe_id, owner_id="gm-1")

        with pytest.raises(ShareAccessError):
            await agent.get_visible_artifact(story_id, share.token, artifact.id)

    async def test_token_for_another_story_is_refused(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        _stub_roster(hermetic, [])
        agent = ShareAgent()
        share, artifact = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.RECAP,
            title="Recap",
            content="Body",
        )

        with pytest.raises(ShareTokenError):
            await agent.build_player_view(uuid4(), share.token)


class TestSpoilerMatrix:
    """The spoiler matrix — who may see a character-scoped handout."""

    async def test_party_scoped_handout_is_visible_to_everyone(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        _stub_roster(hermetic, [])
        agent = ShareAgent()

        share, _ = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.HANDOUT,
            title="Town map",
            content="The harbour terraces.",
            spoiler_level=ShareSpoilerLevel.PARTY,
        )

        view = await agent.build_player_view(story_id, share.token, character_id=uuid4())
        assert len(view.artifacts) == 1

    async def test_character_scoped_handout_is_hidden_from_other_pcs(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        _stub_roster(hermetic, [])
        scoped = uuid4()
        other = uuid4()
        fact_id = uuid4()
        hermetic.override("neo4j_list_facts", [_fact(fact_id, [str(scoped)])])

        agent = ShareAgent()
        share, _ = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.HANDOUT,
            title="Mira's letter",
            content="A letter addressed to Mira.",
            spoiler_level=ShareSpoilerLevel.CHARACTER,
            scope_character_id=scoped,
            source_fact_ids=[fact_id],
        )

        # The PC it is scoped to sees it.
        scoped_view = await agent.build_player_view(story_id, share.token, character_id=scoped)
        assert len(scoped_view.artifacts) == 1

        # A PC who has not witnessed the source fact does not.
        other_view = await agent.build_player_view(story_id, share.token, character_id=other)
        assert other_view.artifacts == []

    async def test_witnessed_handout_is_visible_to_the_witnessing_pc(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        _stub_roster(hermetic, [])
        scoped = uuid4()
        witness = uuid4()
        fact_id = uuid4()
        hermetic.override("neo4j_list_facts", [_fact(fact_id, [str(witness)])])

        agent = ShareAgent()
        share, _ = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.HANDOUT,
            title="The sealed door",
            content="It opened.",
            spoiler_level=ShareSpoilerLevel.CHARACTER,
            scope_character_id=scoped,
            source_fact_ids=[fact_id],
        )

        witness_view = await agent.build_player_view(story_id, share.token, character_id=witness)
        assert len(witness_view.artifacts) == 1

    async def test_character_scoped_handout_without_a_viewer_is_hidden(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        _stub_roster(hermetic, [])
        scoped = uuid4()
        agent = ShareAgent()

        share, _ = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.HANDOUT,
            title="Mira's letter",
            content="A letter.",
            spoiler_level=ShareSpoilerLevel.CHARACTER,
            scope_character_id=scoped,
        )

        view = await agent.build_player_view(story_id, share.token)
        assert view.artifacts == []


class TestExport:
    """The markdown export players download."""

    async def test_export_carries_the_title_and_body(
        self, hermetic: HermeticStack, story: tuple[UUID, UUID]
    ) -> None:
        universe_id, story_id = story
        _stub_roster(hermetic, [])
        agent = ShareAgent()
        share, artifact = await agent.publish(
            universe_id=universe_id,
            story_id=story_id,
            owner_id="gm-1",
            artifact_type=ShareArtifactType.RECAP,
            title="Session 4 recap",
            content="They opened the sealed door.",
        )

        visible = await agent.get_visible_artifact(story_id, share.token, artifact.id)
        markdown = agent.export_markdown(visible)

        assert markdown.startswith("# Session 4 recap")
        assert "They opened the sealed door." in markdown
