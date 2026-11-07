"""Book decomposition storage: repeated writes are harmless, and leases expire (I-17)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import mongomock
import pytest
from monitor_data.schemas.book_graph import BookRecord, BookRecordType
from monitor_data.tools import mongodb_tools
from monitor_data.tools.mongodb_tools import book_decomposition as tools

START = datetime(2026, 11, 4, tzinfo=UTC)


class _Collection:
    """mongomock's bulk_write rejects this pymongo version's ReplaceOne, so apply them one by one."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def bulk_write(self, operations, ordered=True):
        for op in operations:
            self._inner.replace_one(op._filter, op._doc, upsert=op._upsert)


@pytest.fixture
def mongo():
    database = mongomock.MongoClient().db
    client = SimpleNamespace(get_collection=lambda name: _Collection(database[name]))
    with patch.object(tools, "get_mongodb_client", return_value=client):
        yield database


def _rec(key: str, value: int = 1) -> BookRecord:
    return BookRecord(key=key, data={"value": value})


@pytest.mark.unit
def test_records_round_trip_by_document_and_type(mongo):
    tools.mongodb_upsert_book_records("d1", BookRecordType.CHECK, [_rec("a"), _rec("b")])
    tools.mongodb_upsert_book_records("d1", BookRecordType.CLAIM, [_rec("a", 2)])
    tools.mongodb_upsert_book_records("d2", BookRecordType.CHECK, [_rec("z")])
    assert {r.key for r in tools.mongodb_list_book_records("d1", BookRecordType.CHECK)} == {"a", "b"}
    assert tools.mongodb_list_book_records("d1", BookRecordType.CLAIM)[0].data == {"value": 2}


@pytest.mark.unit
def test_repeated_write_replaces_instead_of_duplicating(mongo):
    for value in (1, 2):
        tools.mongodb_upsert_book_records("d", BookRecordType.CHECK, [_rec("a", value)])
    records = tools.mongodb_list_book_records("d", BookRecordType.CHECK)
    assert [r.data["value"] for r in records] == [2]


@pytest.mark.unit
def test_large_writes_are_batched_without_losing_records(mongo):
    records = [_rec(str(i)) for i in range(1203)]
    assert tools.mongodb_upsert_book_records("d", BookRecordType.NODE, records) == 1203
    assert len(tools.mongodb_list_book_records("d", BookRecordType.NODE)) == 1203


@pytest.mark.unit
def test_writing_nothing_is_allowed(mongo):
    assert tools.mongodb_upsert_book_records("d", BookRecordType.NODE, []) == 0


@pytest.mark.unit
def test_delete_removes_only_that_documents_data(mongo):
    tools.mongodb_upsert_book_records("d1", BookRecordType.CHECK, [_rec("a")])
    tools.mongodb_upsert_book_records("d2", BookRecordType.CHECK, [_rec("a")])
    tools.mongodb_acquire_book_lease("d1", "me", 60, now=START)
    assert tools.mongodb_delete_book_records("d1") == 1
    assert tools.mongodb_list_book_records("d2", BookRecordType.CHECK)
    assert tools.mongodb_acquire_book_lease("d1", "other", 60, now=START)


@pytest.mark.unit
def test_second_owner_is_refused_while_a_lease_is_live(mongo):
    assert tools.mongodb_acquire_book_lease("d", "a", 60, now=START)
    assert not tools.mongodb_acquire_book_lease("d", "b", 60, now=START + timedelta(seconds=59))


@pytest.mark.unit
def test_owner_can_renew_and_renewal_extends_the_lease(mongo):
    assert tools.mongodb_acquire_book_lease("d", "a", 60, now=START)
    assert tools.mongodb_acquire_book_lease("d", "a", 60, now=START + timedelta(seconds=50))
    assert not tools.mongodb_acquire_book_lease("d", "b", 60, now=START + timedelta(seconds=100))


@pytest.mark.unit
def test_expired_lease_can_be_taken_over(mongo):
    tools.mongodb_acquire_book_lease("d", "a", 60, now=START)
    assert tools.mongodb_acquire_book_lease("d", "b", 60, now=START + timedelta(seconds=61))


@pytest.mark.unit
def test_release_only_works_for_the_current_owner(mongo):
    tools.mongodb_acquire_book_lease("d", "a", 60, now=START)
    tools.mongodb_release_book_lease("d", "b")
    assert not tools.mongodb_acquire_book_lease("d", "b", 60, now=START)
    tools.mongodb_release_book_lease("d", "a")
    assert tools.mongodb_acquire_book_lease("d", "b", 60, now=START)


@pytest.mark.unit
def test_tools_are_not_on_the_mcp_surface():
    # server.py registers everything mongodb_tools exports, and this is internal storage.
    assert not hasattr(mongodb_tools, "mongodb_upsert_book_records")
