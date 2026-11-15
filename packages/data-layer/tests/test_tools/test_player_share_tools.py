"""Tests for player share + shared artifact MongoDB tools (CF-14 / G07).

Covers: token minting (unguessable), revocation, story scoping, artifact
publish toggles, and owner/universe predicates on writes. Hermetic: an
in-memory collection stands in for Mongo — no real database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

from monitor_data.schemas.player_share import (
    PlayerShareCreate,
    ShareArtifactType,
    ShareSpoilerLevel,
    SharedArtifactCreate,
)
from monitor_data.tools.mongodb_tools.player_share import (
    mongodb_create_player_share,
    mongodb_create_shared_artifact,
    mongodb_get_player_share_by_token,
    mongodb_get_player_share_for_story,
    mongodb_get_shared_artifact,
    mongodb_list_shared_artifacts,
    mongodb_revoke_player_share,
    mongodb_set_shared_artifact_published,
)


class _FakeCollection:
    """In-memory stand-in for a Mongo collection (insert/find/update)."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    @staticmethod
    def _match(doc: dict[str, Any], query: dict[str, Any]) -> bool:
        return all(doc.get(k) == v for k, v in query.items())

    def insert_one(self, doc: dict[str, Any]) -> None:
        self.docs.append(dict(doc))

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        return next((d for d in self.docs if self._match(d, query)), None)

    def find(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        return [dict(d) for d in self.docs if self._match(d, query)]

    def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> Any:
        for doc in self.docs:
            if self._match(doc, query):
                doc.update(update.get("$set", {}))
                return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()

    def update_many(self, query: dict[str, Any], update: dict[str, Any]) -> Any:
        hits = 0
        for doc in self.docs:
            if self._match(doc, query):
                doc.update(update.get("$set", {}))
                hits += 1
        return type("R", (), {"modified_count": hits})()


def _patch_collections(shares: _FakeCollection, artifacts: _FakeCollection):
    """Route the two tool collection helpers at the in-memory fakes."""
    client = type(
        "C",
        (),
        {"get_collection": staticmethod(lambda name: artifacts if "artifact" in name else shares)},
    )()
    return patch(
        "monitor_data.tools.mongodb_tools.player_share.get_mongodb_client",
        return_value=client,
    )


def _share_params(**overrides: Any) -> PlayerShareCreate:
    base: dict[str, Any] = {
        "story_id": uuid4(),
        "universe_id": uuid4(),
        "owner_id": "user-a",
    }
    base.update(overrides)
    return PlayerShareCreate(**base)


def _artifact_params(**overrides: Any) -> SharedArtifactCreate:
    base: dict[str, Any] = {
        "story_id": uuid4(),
        "universe_id": uuid4(),
        "owner_id": "user-a",
        "artifact_type": ShareArtifactType.RECAP,
        "title": "Session 3 recap",
        "content": "# Recap\n\nThe party opened the door.",
        "published": True,
    }
    base.update(overrides)
    return SharedArtifactCreate(**base)


# ---------------------------------------------------------------------------
# Share tokens
# ---------------------------------------------------------------------------


def test_create_share_roundtrip() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    with _patch_collections(shares, artifacts):
        created = mongodb_create_player_share(_share_params())
        loaded = mongodb_get_player_share_by_token(created.token)

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.story_id == created.story_id
    assert loaded.owner_id == "user-a"
    assert loaded.revoked is False
    assert loaded.expires_at is None


def test_token_is_unguessable_and_url_safe() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    with _patch_collections(shares, artifacts):
        tokens = {mongodb_create_player_share(_share_params()).token for _ in range(5)}

    # Unique, long, and free of characters that break a URL path segment.
    assert len(tokens) == 5
    for token in tokens:
        assert len(token) >= 40
        assert "/" not in token and "+" not in token


def test_get_for_story_returns_latest_active_only() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    story_id = uuid4()
    universe_id = uuid4()
    with _patch_collections(shares, artifacts):
        first = mongodb_create_player_share(_share_params(story_id=story_id, universe_id=universe_id))
        second = mongodb_create_player_share(_share_params(story_id=story_id, universe_id=universe_id))

        active = mongodb_get_player_share_for_story(story_id)
        assert active is not None
        assert active.token == second.token

        # Revoke kills every live token for the story (update_many).
        assert mongodb_revoke_player_share(story_id, owner_id="user-a", universe_id=second.universe_id) is True
        assert mongodb_get_player_share_for_story(story_id) is None
        # The revoked docs are still readable by token (agent rejects them).
        for token in (first.token, second.token):
            revoked = mongodb_get_player_share_by_token(token)
            assert revoked is not None and revoked.revoked is True


def test_revoke_is_owner_and_universe_predicated() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    with _patch_collections(shares, artifacts):
        share = mongodb_create_player_share(_share_params())
        # Wrong owner → no-op.
        assert mongodb_revoke_player_share(share.story_id, owner_id="user-b", universe_id=share.universe_id) is False
        # Wrong universe → no-op.
        assert mongodb_revoke_player_share(share.story_id, owner_id="user-a", universe_id=uuid4()) is False
        # Correct predicates → revoked.
        assert mongodb_revoke_player_share(share.story_id, owner_id="user-a", universe_id=share.universe_id) is True
        # Second revoke finds nothing live.
        assert mongodb_revoke_player_share(share.story_id, owner_id="user-a", universe_id=share.universe_id) is False


def test_expired_share_is_not_active_for_story() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    story_id = uuid4()
    past = datetime.now(UTC) - timedelta(hours=1)
    with _patch_collections(shares, artifacts):
        expired = mongodb_create_player_share(_share_params(story_id=story_id, expires_at=past))
        assert mongodb_get_player_share_for_story(story_id) is None
        # Still resolvable by token so the agent can raise a typed expiry error.
        loaded = mongodb_get_player_share_by_token(expired.token)
        assert loaded is not None
        assert loaded.expires_at is not None and loaded.expires_at < datetime.now(UTC)


def test_scoping_tokens_are_per_story() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    story_a, story_b = uuid4(), uuid4()
    with _patch_collections(shares, artifacts):
        share_a = mongodb_create_player_share(_share_params(story_id=story_a))
        mongodb_create_player_share(_share_params(story_id=story_b))

        active_b = mongodb_get_player_share_for_story(story_b)
        assert active_b is not None
        assert active_b.story_id == story_b
        # A's token never resolves to B's story.
        loaded = mongodb_get_player_share_by_token(share_a.token)
        assert loaded is not None and loaded.story_id == story_a


def test_get_by_unknown_token_returns_none() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    with _patch_collections(shares, artifacts):
        assert mongodb_get_player_share_by_token("nope") is None
        assert mongodb_get_player_share_by_token("") is None


# ---------------------------------------------------------------------------
# Shared artifacts
# ---------------------------------------------------------------------------


def test_artifact_create_and_get_roundtrip() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    with _patch_collections(shares, artifacts):
        created = mongodb_create_shared_artifact(_artifact_params())
        loaded = mongodb_get_shared_artifact(created.id)

    assert loaded is not None
    assert loaded.artifact_type == ShareArtifactType.RECAP
    assert loaded.published is True
    assert loaded.spoiler_level == ShareSpoilerLevel.PARTY
    assert loaded.scope_character_id is None
    assert loaded.source_fact_ids == []


def test_list_only_returns_requested_story_and_published() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    story_a, story_b = uuid4(), uuid4()
    with _patch_collections(shares, artifacts):
        mongodb_create_shared_artifact(_artifact_params(story_id=story_a, published=True, title="A pub"))
        mongodb_create_shared_artifact(_artifact_params(story_id=story_a, published=False, title="A draft"))
        mongodb_create_shared_artifact(_artifact_params(story_id=story_b, published=True, title="B pub"))

        story_a_all = mongodb_list_shared_artifacts(story_a)
        assert {a.title for a in story_a_all} == {"A pub", "A draft"}

        story_a_published = mongodb_list_shared_artifacts(story_a, published_only=True)
        assert [a.title for a in story_a_published] == ["A pub"]

        story_b_published = mongodb_list_shared_artifacts(story_b, published_only=True)
        assert [a.title for a in story_b_published] == ["B pub"]


def test_publish_toggle_roundtrip() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    with _patch_collections(shares, artifacts):
        created = mongodb_create_shared_artifact(_artifact_params(published=True))
        assert mongodb_set_shared_artifact_published(
            created.id, universe_id=created.universe_id, owner_id="user-a", published=False
        )
        loaded = mongodb_get_shared_artifact(created.id)
        assert loaded is not None and loaded.published is False

        assert mongodb_set_shared_artifact_published(
            created.id, universe_id=created.universe_id, owner_id="user-a", published=True
        )
        loaded = mongodb_get_shared_artifact(created.id)
        assert loaded is not None and loaded.published is True


def test_unpublish_is_owner_and_universe_predicated() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    with _patch_collections(shares, artifacts):
        created = mongodb_create_shared_artifact(_artifact_params(published=True))
        # Foreign universe → miss (behaves like a nonexistent ID).
        assert (
            mongodb_set_shared_artifact_published(created.id, universe_id=uuid4(), owner_id="user-a", published=False)
            is False
        )
        # Foreign owner → miss.
        assert (
            mongodb_set_shared_artifact_published(
                created.id, universe_id=created.universe_id, owner_id="user-b", published=False
            )
            is False
        )
        # Untouched.
        loaded = mongodb_get_shared_artifact(created.id)
        assert loaded is not None and loaded.published is True


def test_character_scoped_artifact_fields_survive_roundtrip() -> None:
    shares, artifacts = _FakeCollection(), _FakeCollection()
    scope = uuid4()
    facts = [uuid4(), uuid4()]
    with _patch_collections(shares, artifacts):
        created = mongodb_create_shared_artifact(
            _artifact_params(
                artifact_type=ShareArtifactType.HANDOUT,
                spoiler_level=ShareSpoilerLevel.CHARACTER,
                scope_character_id=scope,
                source_fact_ids=facts,
            )
        )
        loaded = mongodb_get_shared_artifact(created.id)

    assert loaded is not None
    assert loaded.spoiler_level == ShareSpoilerLevel.CHARACTER
    assert loaded.scope_character_id == scope
    assert [UUID(str(f)) for f in loaded.source_fact_ids] == facts
