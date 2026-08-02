"""Tests for VisualIdentity MongoDB persistence tools (Task 2)."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

import monitor_data.tools.mongodb_tools.visual_identities as identity_tools
from monitor_data.db.mongodb import MongoDBClient
from monitor_data.middleware.auth import AUTHORITY_MATRIX
from monitor_data.schemas.visual_identity import (
    VisualIdentity,
    VisualIdentityCreate,
    VisualIdentityFilter,
    VisualIdentitySource,
    VisualIdentityStatus,
    VisualIdentityUpdate,
)
from monitor_data.tools.mongodb_tools.visual_identities import (
    VisualIdentityConflictError,
    VisualIdentityNotFoundError,
)


class _FakeCursor:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = list(rows)

    def sort(self, key: str, direction: int) -> _FakeCursor:
        self.rows.sort(
            key=lambda row: (row.get(key) is None, row.get(key)),
            reverse=direction == -1,
        )
        return self

    def skip(self, amount: int) -> _FakeCursor:
        self.rows = self.rows[amount:]
        return self

    def limit(self, amount: int) -> _FakeCursor:
        self.rows = self.rows[:amount]
        return self

    def __iter__(self):
        return iter(self.rows)


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        return all(doc.get(key) == expected for key, expected in query.items())

    def find_one(self, query: dict) -> dict | None:
        return next((doc for doc in self.docs if self._matches(doc, query)), None)

    def find(self, query: dict) -> _FakeCursor:
        return _FakeCursor([doc for doc in self.docs if self._matches(doc, query)])

    def insert_one(self, doc: dict) -> None:
        self.docs.append(doc)

    def update_one(self, query: dict, update: dict):
        doc = self.find_one(query)
        if doc is None:
            return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0})()
        for key, value in update.get("$set", {}).items():
            doc[key] = value
        return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()


class _FakeMongoClient:
    def __init__(self) -> None:
        self.identities = _FakeCollection()

    def get_collection(self, name: str) -> _FakeCollection:
        if name != "visual_identities":
            raise AssertionError(f"unexpected collection {name}")
        return self.identities

    def __getitem__(self, name: str) -> _FakeCollection:
        return self.get_collection(name)


@pytest.fixture
def fake_mongo(monkeypatch: pytest.MonkeyPatch) -> _FakeMongoClient:
    client = _FakeMongoClient()
    monkeypatch.setattr(identity_tools, "get_mongodb_client", lambda: client)
    return client


def _sample_identity(**overrides: object) -> VisualIdentityCreate:
    payload: dict[str, object] = {
        "character_id": "dinah-lance",
        "description": "A poised martial artist with an unmistakable stage presence.",
        "species_or_type": "human",
        "apparent_age": "early thirties",
        "build": "athletic",
        "hair": "shoulder-length blonde hair",
        "eyes": "blue",
        "skin_or_surface": "fair",
        "signature_attire": "black jacket and practical combat boots",
        "distinguishing_features": ["confident stance"],
        "palette": ["black", "gold"],
        "style_hint": "grounded comic-book realism",
        "source": VisualIdentitySource.MANUAL,
        "approved_reference_asset_ids": [uuid4()],
    }
    payload.update(overrides)
    return VisualIdentityCreate(**payload)


def test_create_and_get_card_identity_roundtrip_uses_string_uuids(
    fake_mongo: _FakeMongoClient,
) -> None:
    reference_id = uuid4()
    created = identity_tools.mongodb_upsert_visual_identity(
        _sample_identity(approved_reference_asset_ids=[reference_id])
    )

    assert created.version == 1
    assert created.status == VisualIdentityStatus.DRAFT
    assert isinstance(created.identity_id, UUID)
    raw = fake_mongo.identities.docs[0]
    assert raw["identity_id"] == str(created.identity_id)
    assert raw["approved_reference_asset_ids"] == [str(reference_id)]

    loaded = identity_tools.mongodb_get_visual_identity(
        character_id="dinah-lance",
        status="draft",
    )
    assert loaded is not None
    assert loaded.identity_id == created.identity_id
    assert loaded.description == created.description
    assert identity_tools.mongodb_get_visual_identity(character_id="dinah-lance") is None


def test_get_visual_identity_by_entity_universe_and_status(
    fake_mongo: _FakeMongoClient,
) -> None:
    entity_id = uuid4()
    universe_id = uuid4()
    created = identity_tools.mongodb_upsert_visual_identity(
        _sample_identity(
            character_id=None,
            entity_id=entity_id,
            universe_id=universe_id,
            source=VisualIdentitySource.CANON,
        )
    )
    approved = identity_tools.mongodb_upsert_visual_identity(
        VisualIdentityUpdate(
            identity_id=created.identity_id,
            expected_version=created.version,
            status=VisualIdentityStatus.APPROVED,
        )
    )

    loaded = identity_tools.mongodb_get_visual_identity(
        entity_id=entity_id,
        universe_id=universe_id,
    )
    assert loaded is not None
    assert loaded.identity_id == approved.identity_id
    assert loaded.version == 2
    assert loaded.status == VisualIdentityStatus.APPROVED


def test_update_creates_next_version_and_supersedes_previous(
    fake_mongo: _FakeMongoClient,
) -> None:
    original = identity_tools.mongodb_upsert_visual_identity(_sample_identity())

    updated = identity_tools.mongodb_upsert_visual_identity(
        VisualIdentityUpdate(
            identity_id=original.identity_id,
            expected_version=1,
            description="Updated after a canon costume reveal.",
            hair="chin-length blonde hair",
        )
    )

    assert updated.identity_id != original.identity_id
    assert updated.version == 2
    assert updated.character_id == original.character_id
    assert updated.description == "Updated after a canon costume reveal."
    assert updated.hair == "chin-length blonde hair"
    assert updated.status == VisualIdentityStatus.DRAFT
    assert len(fake_mongo.identities.docs) == 2
    old_doc = next(
        doc for doc in fake_mongo.identities.docs if doc["identity_id"] == str(original.identity_id)
    )
    assert old_doc["status"] == VisualIdentityStatus.SUPERSEDED.value


def test_stale_expected_version_raises_conflict_without_creating_version(
    fake_mongo: _FakeMongoClient,
) -> None:
    original = identity_tools.mongodb_upsert_visual_identity(_sample_identity())
    current = identity_tools.mongodb_upsert_visual_identity(
        VisualIdentityUpdate(
            identity_id=original.identity_id,
            expected_version=1,
            description="Version two",
        )
    )

    with pytest.raises(VisualIdentityConflictError, match="version conflict"):
        identity_tools.mongodb_upsert_visual_identity(
            VisualIdentityUpdate(
                identity_id=original.identity_id,
                expected_version=1,
                description="Stale writer",
            )
        )
    with pytest.raises(VisualIdentityConflictError, match="version conflict"):
        identity_tools.mongodb_upsert_visual_identity(
            VisualIdentityUpdate(
                identity_id=current.identity_id,
                expected_version=1,
                description="Wrong expected version",
            )
        )
    # Backward compatible: conflicts remain ValueErrors for existing callers.
    assert issubclass(VisualIdentityConflictError, ValueError)

    assert len(fake_mongo.identities.docs) == 2
    assert current.version == 2


def test_update_unknown_identity_raises_not_found_error(fake_mongo: _FakeMongoClient) -> None:
    with pytest.raises(VisualIdentityNotFoundError, match="not found"):
        identity_tools.mongodb_upsert_visual_identity(
            VisualIdentityUpdate(
                identity_id=uuid4(),
                expected_version=1,
                description="ghost",
            )
        )
    assert issubclass(VisualIdentityNotFoundError, ValueError)


def test_create_for_existing_anchor_versions_latest_identity(
    fake_mongo: _FakeMongoClient,
) -> None:
    original = identity_tools.mongodb_upsert_visual_identity(_sample_identity())

    replacement = identity_tools.mongodb_upsert_visual_identity(
        _sample_identity(description="A replacement extracted from newer canon facts.")
    )

    assert replacement.version == 2
    assert replacement.identity_id != original.identity_id
    assert replacement.description == "A replacement extracted from newer canon facts."
    old_doc = next(
        doc for doc in fake_mongo.identities.docs if doc["identity_id"] == str(original.identity_id)
    )
    assert old_doc["status"] == VisualIdentityStatus.SUPERSEDED.value


def test_update_requires_identity_and_expected_version(fake_mongo: _FakeMongoClient) -> None:
    with pytest.raises(ValueError, match="identity_id"):
        identity_tools.mongodb_upsert_visual_identity(
            VisualIdentityUpdate(expected_version=1, description="missing target")
        )
    with pytest.raises(ValueError, match="expected_version"):
        identity_tools.mongodb_upsert_visual_identity(
            VisualIdentityUpdate(identity_id=uuid4(), description="missing version")
        )


def test_get_visual_identity_requires_an_anchor(fake_mongo: _FakeMongoClient) -> None:
    with pytest.raises(ValueError, match="anchor"):
        identity_tools.mongodb_get_visual_identity(status="draft")


def _approve(identity: VisualIdentity) -> VisualIdentity:
    """Advance a draft identity to an approved next version."""
    return identity_tools.mongodb_upsert_visual_identity(
        VisualIdentityUpdate(
            identity_id=identity.identity_id,
            expected_version=identity.version,
            status=VisualIdentityStatus.APPROVED,
        )
    )


def test_card_default_only_matches_null_universe_anchor(fake_mongo: _FakeMongoClient) -> None:
    """Regression (Task 4 review): the plain character_id lookup omits null
    anchors (``include_nulls=False``), so an approved incarnation with a
    higher version shadows the card default.  ``card_default_only=True``
    must query the explicit null anchor (``include_nulls=True`` semantics).
    """
    universe_id = uuid4()
    card = _approve(identity_tools.mongodb_upsert_visual_identity(_sample_identity()))
    incarnation = identity_tools.mongodb_upsert_visual_identity(
        _sample_identity(universe_id=universe_id, description="Universe incarnation.")
    )
    incarnation = _approve(incarnation)
    # Bump the incarnation to a strictly higher version than the card default.
    incarnation = identity_tools.mongodb_upsert_visual_identity(
        VisualIdentityUpdate(
            identity_id=incarnation.identity_id,
            expected_version=incarnation.version,
            description="Revised universe incarnation.",
            status=VisualIdentityStatus.APPROVED,
        )
    )
    assert incarnation.version > card.version

    # Plain lookup (unchanged semantics): highest version across all anchors.
    leaked = identity_tools.mongodb_get_visual_identity(character_id="dinah-lance")
    assert leaked is not None
    assert leaked.identity_id == incarnation.identity_id
    assert leaked.universe_id == universe_id

    # Explicit card-default lookup: null universe_id/entity_id anchors only.
    loaded = identity_tools.mongodb_get_visual_identity(
        character_id="dinah-lance",
        card_default_only=True,
    )
    assert loaded is not None
    assert loaded.identity_id == card.identity_id
    assert loaded.universe_id is None
    assert loaded.entity_id is None


def test_card_default_only_requires_bare_character_id(fake_mongo: _FakeMongoClient) -> None:
    with pytest.raises(ValueError, match="card_default_only"):
        identity_tools.mongodb_get_visual_identity(card_default_only=True)
    with pytest.raises(ValueError, match="card_default_only"):
        identity_tools.mongodb_get_visual_identity(
            character_id="dinah-lance",
            universe_id=uuid4(),
            card_default_only=True,
        )


def test_list_visual_identities_filters_by_anchor_and_status(
    fake_mongo: _FakeMongoClient,
) -> None:
    mine = identity_tools.mongodb_upsert_visual_identity(_sample_identity())
    other_universe = uuid4()
    identity_tools.mongodb_upsert_visual_identity(
        _sample_identity(character_id="oliver-queen", universe_id=other_universe)
    )

    result = identity_tools.mongodb_list_visual_identities(
        VisualIdentityFilter(character_id="dinah-lance")
    )
    assert [identity.identity_id for identity in result] == [mine.identity_id]

    by_status = identity_tools.mongodb_list_visual_identities(
        VisualIdentityFilter(status=VisualIdentityStatus.DRAFT)
    )
    assert len(by_status) == 2

    empty = identity_tools.mongodb_list_visual_identities(
        VisualIdentityFilter(status=VisualIdentityStatus.APPROVED)
    )
    assert empty == []


def test_list_visual_identities_filters_entity_and_universe_and_paginates(
    fake_mongo: _FakeMongoClient,
) -> None:
    entity_id = uuid4()
    universe_id = uuid4()
    canonical = identity_tools.mongodb_upsert_visual_identity(
        _sample_identity(character_id=None, entity_id=entity_id, universe_id=universe_id)
    )
    for index in range(2):
        identity_tools.mongodb_upsert_visual_identity(
            _sample_identity(character_id=f"card-{index}")
        )

    by_entity = identity_tools.mongodb_list_visual_identities(
        VisualIdentityFilter(entity_id=entity_id, universe_id=universe_id)
    )
    assert [identity.identity_id for identity in by_entity] == [canonical.identity_id]

    page = identity_tools.mongodb_list_visual_identities(VisualIdentityFilter(limit=1, offset=1))
    assert len(page) == 1

    all_identities = identity_tools.mongodb_list_visual_identities(VisualIdentityFilter(limit=10))
    assert len(all_identities) == 3


def test_update_visual_identity_status_marks_draft_approved_with_decision_reference(
    fake_mongo: _FakeMongoClient,
) -> None:
    draft = identity_tools.mongodb_upsert_visual_identity(_sample_identity())
    proposal_id = uuid4()

    updated = identity_tools.mongodb_update_visual_identity_status(
        draft.identity_id,
        status=VisualIdentityStatus.APPROVED,
        decision_proposal_id=proposal_id,
    )

    assert updated.identity_id == draft.identity_id
    assert updated.version == 1  # in-place transition — no new version
    assert updated.status == VisualIdentityStatus.APPROVED
    assert updated.decision_proposal_id == proposal_id
    assert len(fake_mongo.identities.docs) == 1
    raw = fake_mongo.identities.docs[0]
    assert raw["status"] == VisualIdentityStatus.APPROVED.value
    assert raw["decision_proposal_id"] == str(proposal_id)


def test_update_visual_identity_status_rejection_keeps_draft_and_stores_reference(
    fake_mongo: _FakeMongoClient,
) -> None:
    draft = identity_tools.mongodb_upsert_visual_identity(_sample_identity())
    proposal_id = uuid4()

    updated = identity_tools.mongodb_update_visual_identity_status(
        draft.identity_id,
        status=VisualIdentityStatus.DRAFT,
        decision_proposal_id=proposal_id,
    )

    assert updated.status == VisualIdentityStatus.DRAFT
    assert updated.decision_proposal_id == proposal_id
    assert len(fake_mongo.identities.docs) == 1


def test_update_visual_identity_status_rejects_invalid_transition(
    fake_mongo: _FakeMongoClient,
) -> None:
    approved = _approve(identity_tools.mongodb_upsert_visual_identity(_sample_identity()))

    with pytest.raises(VisualIdentityConflictError, match="transition"):
        identity_tools.mongodb_update_visual_identity_status(
            approved.identity_id,
            status=VisualIdentityStatus.DRAFT,
        )


def test_update_visual_identity_status_unknown_identity_raises(
    fake_mongo: _FakeMongoClient,
) -> None:
    with pytest.raises(VisualIdentityNotFoundError, match="not found"):
        identity_tools.mongodb_update_visual_identity_status(
            uuid4(),
            status=VisualIdentityStatus.APPROVED,
        )


def test_update_visual_identity_status_accepts_plain_string_status(
    fake_mongo: _FakeMongoClient,
) -> None:
    """MCP callers only have JSON strings; the tool coerces them internally."""
    draft = identity_tools.mongodb_upsert_visual_identity(_sample_identity())
    proposal_id = uuid4()

    updated = identity_tools.mongodb_update_visual_identity_status(
        str(draft.identity_id),
        status="approved",
        decision_proposal_id=str(proposal_id),
    )

    assert updated.status == VisualIdentityStatus.APPROVED
    assert updated.decision_proposal_id == proposal_id
    raw = fake_mongo.identities.docs[0]
    assert raw["status"] == "approved"


def test_authority_matrix_keeps_identity_upsert_restricted() -> None:
    assert AUTHORITY_MATRIX["mongodb_upsert_visual_identity"] == ["ImageRouter"]
    assert AUTHORITY_MATRIX["mongodb_get_visual_identity"] == ["*"]
    assert AUTHORITY_MATRIX["mongodb_list_visual_identities"] == ["*"]
    assert AUTHORITY_MATRIX["mongodb_update_visual_identity_status"] == ["CanonKeeper"]
    assert "neo4j_upsert_visual_identity" not in AUTHORITY_MATRIX


def test_visual_identity_tools_are_exported_from_facade() -> None:
    import monitor_data.tools.mongodb_tools as facade

    for name in (
        "mongodb_upsert_visual_identity",
        "mongodb_get_visual_identity",
        "mongodb_list_visual_identities",
        "mongodb_update_visual_identity_status",
    ):
        assert name in facade.__all__
        assert callable(getattr(facade, name))


@pytest.mark.asyncio
async def test_create_indexes_provisions_visual_identity_indexes() -> None:
    client = MongoDBClient.__new__(MongoDBClient)
    columns: dict[str, MagicMock] = {}
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: columns.setdefault(name, MagicMock())
    client._db = db

    await client._create_indexes()

    calls = columns["visual_identities"].create_index.call_args_list
    keys = [call.args[0] for call in calls]
    assert [("identity_id", 1)] in keys
    unique = next(call for call in calls if call.args[0] == [("identity_id", 1)])
    assert unique.kwargs["unique"] is True
    assert [("entity_id", 1), ("universe_id", 1), ("status", 1)] in keys
    assert [("character_id", 1), ("universe_id", 1), ("status", 1)] in keys
