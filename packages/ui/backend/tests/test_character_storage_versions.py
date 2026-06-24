"""
Unit tests for character_storage versions[] helpers.

All MongoDB calls go through a mocked _coll() so the helpers can be exercised
without a live DB. We assert on update operators and the resulting state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from monitor_ui.routers import character_storage as cs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def coll_mock():
    coll = MagicMock()
    with patch.object(cs, "_coll", return_value=coll):
        yield coll


def _make_doc(**overrides):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    doc = {
        "id": "char-1",
        "name": "Maeve",
        "versions": [],
        "default_universe_id": None,
        "entity_id": None,
        "source_universe_id": None,
        "memory_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    doc.update(overrides)
    return doc


# ---------------------------------------------------------------------------
# create_character + update_character protected-key guard
# ---------------------------------------------------------------------------


class TestCreateAndUpdate:
    def test_create_initializes_versions_and_default(self):
        coll = MagicMock()
        with patch.object(cs, "_coll", return_value=coll):
            cs.create_character(
                {"name": "Maeve", "description": "wary", "source_universe_id": "uni-1"}
            )
        insert_doc = coll.insert_one.call_args[0][0]
        assert insert_doc["versions"] == []
        assert insert_doc["default_universe_id"] == "uni-1"
        assert insert_doc["source_universe_id"] == "uni-1"

    def test_update_refuses_versions_key(self):
        with pytest.raises(ValueError, match="reserved keys"):
            cs.update_character("char-1", {"versions": []})

    def test_update_allows_normal_fields(self):
        coll = MagicMock()
        coll.find_one_and_update.return_value = {"id": "char-1", "name": "Maeve"}
        with patch.object(cs, "_coll", return_value=coll):
            cs.update_character("char-1", {"name": "Maeve (renamed)"})
        coll.find_one_and_update.assert_called_once()


# ---------------------------------------------------------------------------
# add_version
# ---------------------------------------------------------------------------


class TestAddVersion:
    def test_first_version_promotes_defaults(self, coll_mock):
        doc = _make_doc()
        coll_mock.find_one.return_value = doc
        out = cs.add_version("char-1", "uni-A", "ent-A", "profile-A")
        assert out["universe_id"] == "uni-A"
        assert out["entity_id"] == "ent-A"
        # Default fields are aligned for legacy callers.
        update_op = coll_mock.update_one.call_args[0][1]
        assert update_op["$push"]["versions"]["universe_id"] == "uni-A"
        assert update_op["$set"]["default_universe_id"] == "uni-A"
        assert update_op["$set"]["entity_id"] == "ent-A"
        assert update_op["$set"]["source_universe_id"] == "uni-A"

    def test_second_version_in_same_universe_is_idempotent(self, coll_mock):
        doc = _make_doc(
            versions=[
                {
                    "version_id": "v1",
                    "universe_id": "uni-A",
                    "entity_id": "ent-A",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                }
            ]
        )
        coll_mock.find_one.return_value = doc
        out = cs.add_version("char-1", "uni-A", "ent-A2", "profile-A2")
        assert out["version_id"] == "v1"  # existing entry
        coll_mock.update_one.assert_not_called()  # no-op

    def test_second_version_in_new_universe_adds_entry(self, coll_mock):
        doc = _make_doc(
            versions=[
                {
                    "version_id": "v1",
                    "universe_id": "uni-A",
                    "entity_id": "ent-A",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                }
            ],
            default_universe_id="uni-A",
            entity_id="ent-A",
            source_universe_id="uni-A",
        )
        coll_mock.find_one.return_value = doc
        out = cs.add_version("char-1", "uni-B", "ent-B", "profile-B")
        assert out["universe_id"] == "uni-B"
        assert out["entity_id"] == "ent-B"
        update_op = coll_mock.update_one.call_args[0][1]
        assert update_op["$push"]["versions"]["universe_id"] == "uni-B"


# ---------------------------------------------------------------------------
# get_version / list_versions
# ---------------------------------------------------------------------------


class TestReadVersions:
    def test_get_version_returns_entry(self, coll_mock):
        coll_mock.find_one.return_value = _make_doc(
            versions=[
                {
                    "version_id": "v1",
                    "universe_id": "uni-A",
                    "entity_id": "ent-A",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                },
                {
                    "version_id": "v2",
                    "universe_id": "uni-B",
                    "entity_id": "ent-B",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                },
            ]
        )
        v = cs.get_version("char-1", "uni-A")
        assert v["version_id"] == "v1"
        assert cs.get_version("char-1", "missing") is None

    def test_list_versions_sorted_newest_first(self, coll_mock):
        coll_mock.find_one.return_value = _make_doc(
            versions=[
                {
                    "version_id": "old",
                    "universe_id": "uni-A",
                    "entity_id": "ent-A",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                },
                {
                    "version_id": "new",
                    "universe_id": "uni-B",
                    "entity_id": "ent-B",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                },
            ]
        )
        out = cs.list_versions("char-1")
        assert [v["version_id"] for v in out] == ["new", "old"]


# ---------------------------------------------------------------------------
# touch_version
# ---------------------------------------------------------------------------


class TestTouchVersion:
    def test_targets_specific_version(self, coll_mock):
        cs.touch_version("char-1", "uni-A")
        op = coll_mock.update_one.call_args[0]
        assert op[0]["versions.universe_id"] == "uni-A"
        set_fields = coll_mock.update_one.call_args[0][1]["$set"]
        assert "versions.$.last_chatted_at" in set_fields


# ---------------------------------------------------------------------------
# delete_version
# ---------------------------------------------------------------------------


class TestDeleteVersion:
    def test_pops_entry_and_promotes_default(self, coll_mock):
        doc = _make_doc(
            versions=[
                {
                    "version_id": "v1",
                    "universe_id": "uni-A",
                    "entity_id": "ent-A",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                },
                {
                    "version_id": "v2",
                    "universe_id": "uni-B",
                    "entity_id": "ent-B",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                },
            ],
            default_universe_id="uni-A",
            entity_id="ent-A",
            source_universe_id="uni-A",
        )
        coll_mock.find_one.return_value = doc
        popped = cs.delete_version("char-1", "uni-A")
        assert popped is not None and popped["universe_id"] == "uni-A"
        update = coll_mock.update_one.call_args[0][1]
        surviving_universes = [v["universe_id"] for v in update["$set"]["versions"]]
        assert surviving_universes == ["uni-B"]
        # Default promoted to the surviving entry.
        assert update["$set"]["default_universe_id"] == "uni-B"
        assert update["$set"]["entity_id"] == "ent-B"

    def test_delete_last_version_clears_defaults(self, coll_mock):
        doc = _make_doc(
            versions=[
                {
                    "version_id": "v1",
                    "universe_id": "uni-A",
                    "entity_id": "ent-A",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                }
            ],
            default_universe_id="uni-A",
            entity_id="ent-A",
            source_universe_id="uni-A",
        )
        coll_mock.find_one.return_value = doc
        cs.delete_version("char-1", "uni-A")
        update = coll_mock.update_one.call_args[0][1]
        assert update["$set"]["versions"] == []
        assert update["$set"]["default_universe_id"] is None
        assert update["$set"]["entity_id"] is None

    def test_delete_non_default_keeps_default(self, coll_mock):
        doc = _make_doc(
            versions=[
                {
                    "version_id": "v1",
                    "universe_id": "uni-A",
                    "entity_id": "ent-A",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                },
                {
                    "version_id": "v2",
                    "universe_id": "uni-B",
                    "entity_id": "ent-B",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                },
            ],
            default_universe_id="uni-A",
            entity_id="ent-A",
            source_universe_id="uni-A",
        )
        coll_mock.find_one.return_value = doc
        cs.delete_version("char-1", "uni-B")
        update = coll_mock.update_one.call_args[0][1]
        # Default stays on uni-A — no $set for default_universe_id at all.
        assert "default_universe_id" not in update["$set"]
        assert [v["universe_id"] for v in update["$set"]["versions"]] == ["uni-A"]

    def test_delete_missing_returns_none(self, coll_mock):
        coll_mock.find_one.return_value = _make_doc(versions=[])
        assert cs.delete_version("char-1", "uni-A") is None
        coll_mock.update_one.assert_not_called()


# ---------------------------------------------------------------------------
# set_default_universe
# ---------------------------------------------------------------------------


class TestSetDefaultUniverse:
    def test_promotes_to_existing_version(self, coll_mock):
        doc = _make_doc(
            versions=[
                {
                    "version_id": "v2",
                    "universe_id": "uni-B",
                    "entity_id": "ent-B",
                    "npc_profile_id": None,
                    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    "last_chatted_at": None,
                }
            ],
            default_universe_id="uni-A",
            entity_id="ent-A",
        )
        coll_mock.find_one.return_value = doc
        coll_mock.find_one_and_update.return_value = {
            **doc,
            "default_universe_id": "uni-B",
            "entity_id": "ent-B",
        }
        out = cs.set_default_universe("char-1", "uni-B")
        assert out is not None
        assert out["default_universe_id"] == "uni-B"
        assert out["entity_id"] == "ent-B"

    def test_rejects_unknown_universe(self, coll_mock):
        coll_mock.find_one.return_value = _make_doc(versions=[])
        with pytest.raises(ValueError, match="No version for universe"):
            cs.set_default_universe("char-1", "uni-Z")
