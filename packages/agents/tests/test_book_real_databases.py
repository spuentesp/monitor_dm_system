"""Run book decomposition storage on real databases, when they're available (I-17).

Skipped unless MONITOR_TEST_MONGO_URI or MONITOR_TEST_NEO4J_URI is set. Uses unique IDs, and deletes
what it creates, so it's safe on a development database. Models are scripted, so it costs nothing.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import pytest
from monitor_agents.book_decomposition.extractor import ExtractorResult
from monitor_agents.book_decomposition.ledger import LogBusy
from monitor_agents.book_decomposition.pacing import RunGuard, RunStopped
from monitor_agents.book_decomposition.service import DecomposeStatus, decompose_book
from monitor_agents.book_decomposition.store import MongoExtractionLog
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookRecord,
    BookRecordType,
    ClaimCheck,
    ClaimVerdict,
    CoverageAudit,
    ExtractedAtom,
    SkipAudit,
    StackDecision,
    VerificationBatch,
    WindowExtraction,
)
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_data.tools.ingest_tools.book_tree import decompose_pdf
from monitor_data.tools.mongodb_tools import book_decomposition as storage
from monitor_data.tools.mongodb_tools import knowledge_packs
from monitor_data.tools.neo4j_tools import book_tree as neo4j_book_tree

MONGO_URI = os.environ.get("MONITOR_TEST_MONGO_URI")
NEO4J_URI = os.environ.get("MONITOR_TEST_NEO4J_URI")
needs_mongo = pytest.mark.skipif(not MONGO_URI, reason="MONITOR_TEST_MONGO_URI not set")
needs_neo4j = pytest.mark.skipif(not NEO4J_URI, reason="MONITOR_TEST_NEO4J_URI not set")


@pytest.fixture
def mongo():
    import pymongo

    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    database = client[f"book_test_{uuid.uuid4().hex}"]
    wrapper = SimpleNamespace(get_collection=lambda name: database[name])
    with (
        patch.object(storage, "get_mongodb_client", return_value=wrapper),
        patch.object(knowledge_packs, "get_mongodb_client", return_value=wrapper),
    ):
        yield database
    client.drop_database(database.name)
    client.close()


def _pdf(pages: int = 3) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 100), f"Rule number {i} says spending Momentum is allowed.")
    doc.set_toc([[1, f"Section {i}", i + 1] for i in range(pages)])
    return doc.tobytes()


class _Extractor:
    def __init__(self, stop_after: int | None = None, guard: RunGuard | None = None) -> None:
        self.stop_after, self.guard = stop_after, guard
        self.units: list[str] = []

    async def __call__(self, window):
        if self.stop_after is not None and len(self.units) >= self.stop_after:
            self.guard.stop("budget")
            raise RunStopped("budget")
        self.units.extend(u.node_id for u in window.units)
        atoms = [ExtractedAtom(kind=AtomKind.RULE, statement=u.text, cites=[u.label]) for u in window.units]
        return ExtractorResult(WindowExtraction(atoms=atoms), input_tokens=1, output_tokens=1)


class _Review:
    async def verify(self, prompt):
        labels = [b.split("]")[0].strip("[") for b in prompt.split("\n\n")]
        return VerificationBatch(checks=[ClaimCheck(label=x, verdict=ClaimVerdict.SUPPORTED) for x in labels])

    async def stack(self, prompt):
        return StackDecision()

    async def audit_skips(self, prompt):
        return SkipAudit()

    async def find_gaps(self, prompt):
        return CoverageAudit()


@needs_mongo
@pytest.mark.integration
def test_bulk_writes_replace_and_batch_on_real_mongodb(mongo):
    records = [BookRecord(key=str(i), data={"value": i}) for i in range(1203)]
    storage.mongodb_upsert_book_records("d", BookRecordType.NODE, records)
    storage.mongodb_upsert_book_records("d", BookRecordType.NODE, [BookRecord(key="0", data={"value": "new"})])
    found = storage.mongodb_list_book_records("d", BookRecordType.NODE)
    assert len(found) == 1203
    assert next(r for r in found if r.key == "0").data["value"] == "new"


@needs_mongo
@pytest.mark.integration
def test_leases_on_real_mongodb(mongo):
    start = datetime.now(UTC)
    assert storage.mongodb_acquire_book_lease("d", "a", 60, now=start)
    assert storage.mongodb_acquire_book_lease("d", "a", 60, now=start + timedelta(seconds=1))
    assert not storage.mongodb_acquire_book_lease("d", "b", 60, now=start + timedelta(seconds=2))
    assert storage.mongodb_acquire_book_lease("d", "b", 60, now=start + timedelta(seconds=120))
    storage.mongodb_release_book_lease("d", "a")
    assert not storage.mongodb_acquire_book_lease("d", "c", 60, now=start + timedelta(seconds=121))
    storage.mongodb_release_book_lease("d", "b")
    assert storage.mongodb_acquire_book_lease("d", "c", 60, now=start + timedelta(seconds=121))


@needs_mongo
@pytest.mark.integration
def test_two_workers_cannot_share_a_document_on_real_mongodb(mongo):
    with MongoExtractionLog("d").exclusive():
        with pytest.raises(LogBusy):
            with MongoExtractionLog("d").exclusive():
                pass


@needs_mongo
@pytest.mark.integration
async def test_a_paused_book_resumes_and_makes_one_pack_on_real_mongodb(mongo):
    doc, job = uuid.uuid4(), uuid.uuid4()

    async def run(extractor, guard):
        return await decompose_book(
            _pdf(5),
            doc_id=doc,
            job_id=job,
            title="Book",
            pack_type=KnowledgePackType.RULEBOOK,
            extractor=extractor,
            review_model=_Review(),
            guard=guard,
            run_key="m-1",
            accept_run=lambda key: key.startswith("m-"),
            concurrency=1,
        )

    guard = RunGuard()
    first = _Extractor(stop_after=1, guard=guard)
    assert (await run(first, guard)).status == DecomposeStatus.PAUSED
    second = _Extractor()
    done = await run(second, RunGuard())
    assert done.status == DecomposeStatus.COMPLETE
    assert set(first.units).isdisjoint(second.units)
    again = _Extractor()
    assert (await run(again, RunGuard())).pack_id == done.pack_id and again.units == []
    assert mongo["knowledge_packs"].count_documents({}) == 1
    pack = knowledge_packs.mongodb_get_knowledge_pack(done.pack_id)
    assert all(rule.evidence_refs for rule in pack.game_system_data.rules)


@pytest.fixture
def neo4j():
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(NEO4J_URI, auth=None)

    def run(query, parameters=None):
        with driver.session() as session:
            return [dict(row) for row in session.run(query, parameters or {})]

    client = SimpleNamespace(execute_write=run)
    with patch.object(neo4j_book_tree, "get_neo4j_client", return_value=client):
        yield run
    driver.close()


@needs_neo4j
@pytest.mark.integration
def test_book_structure_is_stored_repeatably_and_deleted_on_real_neo4j(neo4j):
    doc = f"test-{uuid.uuid4().hex}"
    source = uuid.uuid4()
    neo4j("CREATE (:Source {id: $id})", {"id": str(source)})
    try:
        tree = decompose_pdf(_pdf(), doc, "Book")
        count = len(tree.nodes)
        for _ in range(2):  # A second load must change nothing.
            assert neo4j_book_tree.neo4j_merge_book_tree(tree, source) == count
            nodes = neo4j("MATCH (n:BookNode {doc_id: $d}) RETURN count(n) AS c", {"d": doc})
            links = neo4j("MATCH (:BookNode {doc_id: $d})-[r:PART_OF]->() RETURN count(r) AS c", {"d": doc})
            described = neo4j("MATCH (:BookNode {doc_id: $d})-[r:DESCRIBES]->(:Source) RETURN count(r) AS c", {"d": doc})
            assert nodes[0]["c"] == count and links[0]["c"] == count - 1 and described[0]["c"] == 1
        neo4j_book_tree.neo4j_delete_book_tree(doc)
        assert neo4j("MATCH (n:BookNode {doc_id: $d}) RETURN count(n) AS c", {"d": doc})[0]["c"] == 0
        assert neo4j("MATCH (s:Source {id: $id}) RETURN count(s) AS c", {"id": str(source)})[0]["c"] == 1
    finally:
        neo4j("MATCH (n:BookNode {doc_id: $d}) DETACH DELETE n", {"d": doc})
        neo4j("MATCH (s:Source {id: $id}) DETACH DELETE s", {"id": str(source)})
