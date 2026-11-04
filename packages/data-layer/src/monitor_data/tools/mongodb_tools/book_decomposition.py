"""Storage for book decomposition progress (I-17).

Every record's `_id` comes from its document, type and key. A repeated write replaces the same
record, and a crash can't leave a partial one, so resuming is always safe.

These are internal pipeline storage, so they aren't exported from `mongodb_tools`. That keeps
them off the MCP surface, which registers everything that package exports.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.book_graph import BookRecord, BookRecordType
from pymongo import ReplaceOne
from pymongo.errors import DuplicateKeyError

RECORDS_COLLECTION = "book_records"
LEASES_COLLECTION = "book_leases"
_WRITE_BATCH = 500


def _record_id(doc_id: str, record_type: BookRecordType, key: str) -> str:
    return f"{doc_id}:{record_type.value}:{key}"


def mongodb_upsert_book_records(doc_id: str, record_type: BookRecordType, records: Sequence[BookRecord]) -> int:
    """Write records in batches, replacing any with the same key. Returns how many were sent."""
    collection = get_mongodb_client().get_collection(RECORDS_COLLECTION)
    now = datetime.now(UTC)
    for start in range(0, len(records), _WRITE_BATCH):
        operations = [
            ReplaceOne(
                {"_id": _record_id(doc_id, record_type, record.key)},
                {
                    "doc_id": doc_id,
                    "record_type": record_type.value,
                    "key": record.key,
                    "data": record.data,
                    "updated_at": now,
                },
                upsert=True,
            )
            for record in records[start : start + _WRITE_BATCH]
        ]
        collection.bulk_write(operations, ordered=False)
    return len(records)


def mongodb_list_book_records(doc_id: str, record_type: BookRecordType) -> list[BookRecord]:
    """Read every record of one type for a document."""
    collection = get_mongodb_client().get_collection(RECORDS_COLLECTION)
    cursor = collection.find({"doc_id": doc_id, "record_type": record_type.value})
    return [BookRecord(key=row["key"], data=row["data"]) for row in cursor]


def mongodb_delete_book_records(doc_id: str) -> int:
    """Delete everything stored for a document, including any lease. Returns records deleted."""
    client = get_mongodb_client()
    client.get_collection(LEASES_COLLECTION).delete_one({"_id": doc_id})
    return int(client.get_collection(RECORDS_COLLECTION).delete_many({"doc_id": doc_id}).deleted_count)


def mongodb_acquire_book_lease(doc_id: str, owner: str, ttl_seconds: float, now: datetime | None = None) -> bool:
    """Take or renew a document's lease. False means another live owner holds it.

    A lease expires by itself, so a crashed worker can't block a document forever.
    """
    current = now or datetime.now(UTC)
    expires_at = current + timedelta(seconds=ttl_seconds)
    collection = get_mongodb_client().get_collection(LEASES_COLLECTION)
    try:
        collection.find_one_and_update(
            {"_id": doc_id, "$or": [{"owner": owner}, {"expires_at": {"$lte": current}}]},
            {"$set": {"owner": owner, "expires_at": expires_at}},
            upsert=True,
        )
    except DuplicateKeyError:
        return False
    return True


def mongodb_release_book_lease(doc_id: str, owner: str) -> None:
    """Give up a lease, but only if this owner still holds it."""
    collection = get_mongodb_client().get_collection(LEASES_COLLECTION)
    collection.delete_one({"_id": doc_id, "owner": owner})
