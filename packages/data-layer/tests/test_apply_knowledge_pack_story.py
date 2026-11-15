"""P3.2(b) — proposals materialised by a pack carry the capture story.

The story arrives two ways: explicitly on the apply request, or inherited
from the ingestion job when the pack came from a story-scoped ingest
(scratchpad notes). Story-scoped review groups by ``story_id``, so without
this stamp ingest proposals are invisible to the story-level lane.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from monitor_data.db.mongodb import MongoDBClient
from monitor_data.schemas.knowledge_packs import (
    ApplyKnowledgePackRequest,
    ExtractedAxiom,
    KnowledgePackCreate,
    KnowledgePackStatus,
    KnowledgePackType,
)
from monitor_data.tools.mongodb_tools.knowledge_packs import (
    mongodb_apply_knowledge_pack,
    mongodb_create_knowledge_pack,
)


@pytest.fixture
def stores(monkeypatch: pytest.MonkeyPatch):
    import mongomock
    from monitor_data.db import mongodb as mongodb_module
    from monitor_data.tools.mongodb_tools import knowledge_packs as packs_module

    client = mongomock.MongoClient()
    db = client["monitor"]
    for name in ("knowledge_packs", "proposed_changes", "ingestion_jobs"):
        db.create_collection(name)

    holder = MongoDBClient()
    holder._client = client
    holder._db = db
    holder._indexes_created = True

    monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: holder)
    monkeypatch.setattr(packs_module, "get_mongodb_client", lambda: holder)
    return holder


def _ready_pack(stores, *, job_id=None):
    return mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="session notes",
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
            status=KnowledgePackStatus.READY,
            ingestion_job_id=job_id,
            axioms=[ExtractedAxiom(statement="The moon is hollow")],
        )
    )


def _stamped_proposals(stores) -> list[dict]:
    return list(stores.get_collection("proposed_changes").find({}))


def test_apply_stamps_explicit_story(stores):
    story_id = uuid4()
    pack = _ready_pack(stores)
    mongodb_apply_knowledge_pack(
        pack.id,
        ApplyKnowledgePackRequest(multiverse_id=uuid4(), universe_id=uuid4(), story_id=story_id),
    )
    docs = _stamped_proposals(stores)
    assert docs
    assert all(d["story_id"] == str(story_id) for d in docs)


def test_apply_inherits_story_from_the_ingestion_job(stores):
    story_id, job_id = uuid4(), uuid4()
    stores.get_collection("ingestion_jobs").insert_one({"job_id": str(job_id), "story_id": str(story_id)})
    pack = _ready_pack(stores, job_id=job_id)
    mongodb_apply_knowledge_pack(
        pack.id,
        ApplyKnowledgePackRequest(multiverse_id=uuid4(), universe_id=uuid4()),
    )
    docs = _stamped_proposals(stores)
    assert docs
    assert all(d["story_id"] == str(story_id) for d in docs)


def test_apply_without_any_story_leaves_the_stamp_off(stores):
    pack = _ready_pack(stores)
    mongodb_apply_knowledge_pack(
        pack.id,
        ApplyKnowledgePackRequest(multiverse_id=uuid4(), universe_id=uuid4()),
    )
    docs = _stamped_proposals(stores)
    assert docs
    assert all("story_id" not in d for d in docs)
