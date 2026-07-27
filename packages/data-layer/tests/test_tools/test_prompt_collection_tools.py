"""Tests for PromptCollection CRUD operations in MongoDB tools."""

from uuid import uuid4

import pytest

from monitor_data.schemas.prompt_collections import (
    PromptCollectionCreate,
    PromptCollectionFilter,
    PromptCollectionUpdate,
    PromptEntry,
)

# =============================================================================
# FAKE MONGODB IMPLEMENTATION
# =============================================================================


class _FakeCursor:
    def __init__(self, results):
        self.results = list(results)

    def sort(self, key, direction):
        self.results = sorted(self.results, key=lambda x: x.get(key, ""), reverse=direction == -1)
        return self

    def skip(self, offset):
        return _FakeCursor(self.results[offset:])

    def limit(self, limit):
        return _FakeCursor(self.results[:limit])

    def __iter__(self):
        return iter(self.results)


class _FakeCollection:
    def __init__(self):
        self.rows: list[dict] = []

    def _matches(self, doc, query):
        for key, value in query.items():
            if key == "tags":
                if value not in doc.get("tags", []):
                    return False
            elif doc.get(key) != value:
                return False
        return True

    def find_one(self, query):
        for doc in self.rows:
            if self._matches(doc, query):
                return doc
        return None

    def insert_one(self, doc):
        self.rows.append(doc)

    def update_one(self, query, update):
        for doc in self.rows:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()

    def delete_one(self, query):
        for i, doc in enumerate(self.rows):
            if self._matches(doc, query):
                del self.rows[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    def count_documents(self, query):
        return sum(1 for d in self.rows if self._matches(d, query))

    def find(self, query):
        return _FakeCursor([d for d in self.rows if self._matches(d, query)])


class _FakeMongoClient:
    def __init__(self):
        self.collection = _FakeCollection()
        self.versions = _FakeCollection()

    def __getitem__(self, name):
        if name == "prompt_collections":
            return self.collection
        if name == "prompt_collection_versions":
            return self.versions
        raise AssertionError(f"unexpected collection {name}")

    def get_collection(self, name):
        return self[name]


@pytest.fixture
def fake_mongo(monkeypatch):
    client = _FakeMongoClient()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.prompt_collections.get_mongodb_client",
        lambda: client,
    )
    return client


# =============================================================================
# TESTS
# =============================================================================


def _sample_create(**overrides):
    params = {
        "name": "V5 Session Zero",
        "category": "session_zero",
        "system_id": uuid4(),
        "entries": [
            PromptEntry(order=0, category="name", question_text="What are you called?"),
            PromptEntry(order=1, category="origin", question_text="Where do you come from?", is_final=True),
        ],
    }
    params.update(overrides)
    return PromptCollectionCreate(**params)


def test_create_and_get_roundtrip(fake_mongo):
    from monitor_data.tools.mongodb_tools.prompt_collections import (
        mongodb_create_prompt_collection,
        mongodb_get_prompt_collection,
    )

    created = mongodb_create_prompt_collection(_sample_create())
    assert created.name == "V5 Session Zero"
    assert len(created.entries) == 2
    assert created.entries[0].question_text == "What are you called?"
    assert created.entries[1].is_final is True

    fetched = mongodb_get_prompt_collection(created.collection_id)
    assert fetched is not None
    assert fetched.collection_id == created.collection_id
    assert fetched.entries[0].category == "name"


def test_get_missing_returns_none(fake_mongo):
    from monitor_data.tools.mongodb_tools.prompt_collections import mongodb_get_prompt_collection

    assert mongodb_get_prompt_collection(uuid4()) is None


def test_update_replaces_entries(fake_mongo):
    from monitor_data.tools.mongodb_tools.prompt_collections import (
        mongodb_create_prompt_collection,
        mongodb_update_prompt_collection,
    )

    created = mongodb_create_prompt_collection(_sample_create())
    updated = mongodb_update_prompt_collection(
        created.collection_id,
        PromptCollectionUpdate(
            name="V5 Session Zero (v2)",
            entries=[PromptEntry(order=0, category="fear", question_text="What terrifies you?")],
        ),
    )
    assert updated.name == "V5 Session Zero (v2)"
    assert len(updated.entries) == 1
    assert updated.entries[0].category == "fear"


def test_update_missing_raises(fake_mongo):
    from monitor_data.tools.mongodb_tools.prompt_collections import mongodb_update_prompt_collection

    with pytest.raises(ValueError):
        mongodb_update_prompt_collection(uuid4(), PromptCollectionUpdate(name="x"))


def test_delete(fake_mongo):
    from monitor_data.tools.mongodb_tools.prompt_collections import (
        mongodb_create_prompt_collection,
        mongodb_delete_prompt_collection,
        mongodb_get_prompt_collection,
    )

    created = mongodb_create_prompt_collection(_sample_create())
    assert mongodb_delete_prompt_collection(created.collection_id) is True
    assert mongodb_get_prompt_collection(created.collection_id) is None
    assert mongodb_delete_prompt_collection(created.collection_id) is False


def test_list_filters_by_category_and_system(fake_mongo):
    from monitor_data.tools.mongodb_tools.prompt_collections import (
        mongodb_create_prompt_collection,
        mongodb_list_prompt_collections,
    )

    sys_a = uuid4()
    mongodb_create_prompt_collection(_sample_create(system_id=sys_a))
    mongodb_create_prompt_collection(_sample_create(name="Other", system_id=uuid4()))
    mongodb_create_prompt_collection(
        _sample_create(name="CharGen", category="character_creation", system_id=sys_a)
    )

    by_category = mongodb_list_prompt_collections(PromptCollectionFilter(category="session_zero"))
    assert by_category.total == 2

    by_system = mongodb_list_prompt_collections(
        PromptCollectionFilter(category="session_zero", system_id=sys_a)
    )
    assert by_system.total == 1
    assert by_system.collections[0].system_id == sys_a


def test_list_filters_by_tag_and_builtin(fake_mongo):
    from monitor_data.tools.mongodb_tools.prompt_collections import (
        mongodb_create_prompt_collection,
        mongodb_list_prompt_collections,
    )

    mongodb_create_prompt_collection(_sample_create(tags=["gothic"], is_builtin=True))
    mongodb_create_prompt_collection(_sample_create(name="Authored", tags=["scifi"]))

    tagged = mongodb_list_prompt_collections(PromptCollectionFilter(tag="scifi"))
    assert tagged.total == 1
    assert tagged.collections[0].name == "Authored"

    no_builtin = mongodb_list_prompt_collections(PromptCollectionFilter(include_builtin=False))
    assert no_builtin.total == 1
    assert no_builtin.collections[0].is_builtin is False


# =============================================================================
# VERSIONING
# =============================================================================


def test_publish_auto_increments_version(fake_mongo):
    from monitor_data.schemas.prompt_collections import PromptCollectionPublish
    from monitor_data.tools.mongodb_tools.prompt_collections import (
        mongodb_create_prompt_collection,
        mongodb_get_prompt_collection,
        mongodb_list_prompt_collection_versions,
        mongodb_publish_prompt_collection,
    )

    created = mongodb_create_prompt_collection(_sample_create())
    v1 = mongodb_publish_prompt_collection(created.collection_id, PromptCollectionPublish(note="first cut"))
    v2 = mongodb_publish_prompt_collection(created.collection_id, PromptCollectionPublish())

    assert v1.version == "v1"
    assert v1.note == "first cut"
    assert v2.version == "v2"

    # Live collection's freeform label reflects the latest publish.
    assert mongodb_get_prompt_collection(created.collection_id).version == "v2"

    listing = mongodb_list_prompt_collection_versions(created.collection_id)
    assert listing.total == 2


def test_publish_missing_collection_raises(fake_mongo):
    from monitor_data.schemas.prompt_collections import PromptCollectionPublish
    from monitor_data.tools.mongodb_tools.prompt_collections import mongodb_publish_prompt_collection

    with pytest.raises(ValueError):
        mongodb_publish_prompt_collection(uuid4(), PromptCollectionPublish())


def test_restore_reverts_live_content(fake_mongo):
    from monitor_data.schemas.prompt_collections import PromptCollectionPublish, PromptCollectionUpdate
    from monitor_data.tools.mongodb_tools.prompt_collections import (
        mongodb_create_prompt_collection,
        mongodb_get_prompt_collection,
        mongodb_publish_prompt_collection,
        mongodb_restore_prompt_collection_version,
        mongodb_update_prompt_collection,
    )

    created = mongodb_create_prompt_collection(_sample_create())  # 2 entries
    snapshot = mongodb_publish_prompt_collection(created.collection_id, PromptCollectionPublish())

    # Mutate the live collection away from the snapshot.
    mongodb_update_prompt_collection(
        created.collection_id,
        PromptCollectionUpdate(name="Rewritten", entries=[PromptEntry(order=0, question_text="only one")]),
    )
    assert mongodb_get_prompt_collection(created.collection_id).name == "Rewritten"

    restored = mongodb_restore_prompt_collection_version(snapshot.version_id)
    assert restored.name == "V5 Session Zero"
    assert len(restored.entries) == 2


def test_restore_missing_version_raises(fake_mongo):
    from monitor_data.tools.mongodb_tools.prompt_collections import mongodb_restore_prompt_collection_version

    with pytest.raises(ValueError):
        mongodb_restore_prompt_collection_version(uuid4())
