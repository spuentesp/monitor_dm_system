from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, UploadFile

from monitor_data.schemas.knowledge_packs import (
    ExtractedAgenda,
    ExtractedCharacterProfile,
    ExtractedEntityArchetype,
    ExtractedGenerationTemplate,
    ExtractedRandomTable,
    ExtractedToneProfile,
    ExtractedTopology,
    KnowledgePackStatus,
    KnowledgePackType,
)
from monitor_ui.routers import ingest


class _DummyLoop:
    def __init__(self):
        self.calls = 0

    def run_in_executor(self, executor, func):  # noqa: ANN001
        self.calls += 1
        return None


class _DummyCollection:
    def __init__(self, name, owner):  # noqa: ANN001
        self.name = name
        self.owner = owner

    def delete_many(self, query):  # noqa: ANN001
        self.owner.delete_calls.append((self.name, query))
        return None


class _DummyMongo:
    def __init__(self):
        self.delete_calls = []

    def get_collection(self, name):  # noqa: ANN001
        return _DummyCollection(name, self)


class _DummyMinio:
    async def download(self, _ref):  # noqa: ANN001
        return b"stored pdf bytes"


class _DummyPostgres:
    def __init__(self, rows=None):  # noqa: ANN001
        self.rows = rows or []
        self.calls = []

    async def llm_task_attempts_list(self, **filters):  # noqa: ANN003
        self.calls.append(filters)
        return list(self.rows)


def _reset_ingest_state():
    ingest._ingest_active_title = None
    ingest._ingest_active_job_id = None
    if hasattr(ingest, "_ingest_active_requests"):
        ingest._ingest_active_requests.clear()
    if hasattr(ingest, "_ingest_pending_requests"):
        ingest._ingest_pending_requests.clear()


@pytest.mark.asyncio
async def test_upload_source_claims_ingest_lock_before_background_thread_starts(
    monkeypatch,
):
    _reset_ingest_state()

    monkeypatch.setattr(ingest.asyncio, "get_running_loop", lambda: _DummyLoop())
    monkeypatch.setattr(
        ingest, "_create_setting", lambda name, system_name: (uuid4(), uuid4())
    )

    upload = UploadFile(filename="seventh_sea.pdf", file=BytesIO(b"test pdf bytes"))

    result = await ingest.upload_source(
        file=upload,
        scan_type="setting_supplement",
        analysis_layers=["axioms", "entities"],
        new_setting_name=None,
        new_setting_system=None,
        multiverse_id=None,
        title="Seventh Sea",
    )

    assert result["status"] == "processing"

    with pytest.raises(HTTPException) as exc:
        ingest._check_ingest_busy()

    assert exc.value.status_code == 409
    assert "Seventh Sea" in str(exc.value.detail)

    _reset_ingest_state()


@pytest.mark.asyncio
async def test_rescan_source_keeps_reserved_slot_without_unboundlocalerror(monkeypatch):
    _reset_ingest_state()

    source_id = str(uuid4())
    universe_id = uuid4()
    doc_id = uuid4()

    monkeypatch.setattr(ingest.asyncio, "get_running_loop", lambda: _DummyLoop())
    monkeypatch.setattr(
        ingest,
        "mongodb_list_ingestion_jobs",
        lambda _filters: SimpleNamespace(
            jobs=[
                SimpleNamespace(
                    doc_id=doc_id,
                    universe_id=universe_id,
                    source_title="Death in Space Core Rules",
                )
            ]
        ),
    )
    monkeypatch.setattr(
        ingest,
        "mongodb_get_document",
        lambda _doc_id: SimpleNamespace(
            doc_id=doc_id,
            universe_id=universe_id,
            title="Death in Space Core Rules",
            minio_ref="sources/death-in-space.pdf",
            filename="Death_in_Space_Core_Rules.pdf",
            file_type="pdf",
        ),
    )
    fake_mongo = _DummyMongo()
    monkeypatch.setattr(
        ingest, "neo4j_get_universe", lambda _uid: {"id": str(universe_id)}
    )
    monkeypatch.setattr(ingest, "get_minio_client", lambda: _DummyMinio())
    monkeypatch.setattr(ingest, "get_mongodb_client", lambda: fake_mongo)
    monkeypatch.setattr(ingest, "neo4j_delete_source", lambda _uid: None)

    result = await ingest.rescan_source(source_id=source_id)

    assert result["status"] == "processing"
    assert result["source_title"] == "Death in Space Core Rules"
    assert (
        "ingestion_jobs",
        {"source_id": str(UUID(source_id))},
    ) in fake_mongo.delete_calls
    assert all(name != "documents" for name, _query in fake_mongo.delete_calls)

    _reset_ingest_state()


@pytest.mark.asyncio
async def test_second_upload_is_queued_instead_of_rejected(monkeypatch):
    _reset_ingest_state()

    monkeypatch.setattr(ingest.asyncio, "get_running_loop", lambda: _DummyLoop())
    monkeypatch.setattr(
        ingest, "_create_setting", lambda name, system_name: (uuid4(), uuid4())
    )

    first = UploadFile(filename="first.pdf", file=BytesIO(b"first pdf bytes"))
    second = UploadFile(filename="second.pdf", file=BytesIO(b"second pdf bytes"))

    result1 = await ingest.upload_source(file=first, title="First Source")
    result2 = await ingest.upload_source(file=second, title="Second Source")

    assert result1["status"] == "processing"
    assert result2["status"] == "processing"
    assert result2["metadata"]["queue_position"] >= 1

    monkeypatch.setattr(
        ingest,
        "mongodb_list_ingestion_jobs",
        lambda _filters: SimpleNamespace(jobs=[]),
    )
    monkeypatch.setattr(ingest, "mongodb_list_documents", lambda: [])
    jobs = await ingest.list_jobs()
    titles = [job["source_title"] for job in jobs]

    assert "First Source" in titles
    assert "Second Source" in titles
    assert len([job for job in jobs if job["status"] in {"pending", "running"}]) >= 2

    _reset_ingest_state()


@pytest.mark.asyncio
async def test_upload_source_can_save_without_starting_ingest(monkeypatch):
    _reset_ingest_state()

    loop = _DummyLoop()
    source_id = uuid4()
    universe_id = uuid4()
    doc_id = uuid4()

    monkeypatch.setattr(ingest.asyncio, "get_running_loop", lambda: loop)
    monkeypatch.setattr(
        ingest, "_create_setting", lambda name, system_name: (uuid4(), universe_id)
    )

    async def _fake_save_uploaded_source_only(**_kwargs):
        return {
            "source_id": source_id,
            "doc_id": doc_id,
            "universe_id": universe_id,
        }

    monkeypatch.setattr(
        ingest, "_save_uploaded_source_only", _fake_save_uploaded_source_only
    )

    upload = UploadFile(filename="library_only.pdf", file=BytesIO(b"saved bytes"))

    result = await ingest.upload_source(
        file=upload,
        title="Library Only",
        ingest_now=False,
    )

    assert result["status"] == "saved"
    assert result["id"] == str(source_id)
    assert result["metadata"]["job_id"] is None
    assert result["metadata"]["ingest_requested"] is False
    assert loop.calls == 0

    _reset_ingest_state()


@pytest.mark.asyncio
async def test_list_jobs_surfaces_pending_placeholder_when_mutex_reserved(monkeypatch):
    _reset_ingest_state()
    ingest._reserve_ingest_slot("Vampire: The Masquerade")

    monkeypatch.setattr(
        ingest,
        "mongodb_list_ingestion_jobs",
        lambda _filters: SimpleNamespace(jobs=[]),
    )
    monkeypatch.setattr(ingest, "mongodb_list_documents", lambda: [])

    jobs = await ingest.list_jobs()

    assert len(jobs) == 1
    assert jobs[0]["status"] == "pending"
    assert jobs[0]["source_title"] == "Vampire: The Masquerade"
    assert jobs[0]["id"].startswith("pending:")

    _reset_ingest_state()


@pytest.mark.asyncio
async def test_list_jobs_surfaces_saved_source_without_job(monkeypatch):
    _reset_ingest_state()

    source_id = uuid4()
    universe_id = uuid4()
    uploaded_at = datetime.now(timezone.utc)

    monkeypatch.setattr(
        ingest,
        "mongodb_list_ingestion_jobs",
        lambda _filters: SimpleNamespace(jobs=[]),
    )
    monkeypatch.setattr(
        ingest,
        "mongodb_list_documents",
        lambda: [
            SimpleNamespace(
                source_id=source_id,
                universe_id=universe_id,
                title="Upload Only Source",
                filename="upload-only.pdf",
                file_type="pdf",
                file_size_bytes=123,
                extraction_status=SimpleNamespace(value="pending"),
                extraction_error=None,
                created_at=uploaded_at,
                extracted_at=None,
            )
        ],
    )

    jobs = await ingest.list_jobs()

    assert len(jobs) == 1
    assert jobs[0]["source_title"] == "Upload Only Source"
    assert jobs[0]["status"] == "saved"
    assert jobs[0]["current_stage"] == "saved"
    assert jobs[0]["id"].startswith("source:")


@pytest.mark.asyncio
async def test_list_job_attempts_returns_durable_audit_rows(monkeypatch):
    rows = [
        {
            "job_id": str(uuid4()),
            "stage": "rules",
            "batch_id": "batch-7",
            "status": "succeeded",
            "attempt_no": 1,
            "provider_id": "github-models-default",
            "model": "gpt-4.1-mini",
        }
    ]
    fake_postgres = _DummyPostgres(rows=rows)
    monkeypatch.setattr(ingest, "get_postgres_client", lambda: fake_postgres)

    job_id = str(uuid4())
    result = await ingest.list_job_attempts(job_id=job_id, stage="rules", limit=25)

    assert len(result) == 1
    assert result[0].stage == "rules"
    assert result[0].batch_id == "batch-7"
    assert result[0].status == "succeeded"
    assert result[0].provider_id == "github-models-default"
    assert fake_postgres.calls == [
        {
            "job_id": job_id,
            "stage": "rules",
            "batch_id": None,
            "provider_id": None,
            "limit": 25,
        }
    ]


@pytest.mark.asyncio
async def test_list_job_attempts_returns_empty_for_placeholder_ids():
    assert await ingest.list_job_attempts(job_id="pending:queued-job") == []


@pytest.mark.asyncio
async def test_cancel_job_marks_cancelled_state(monkeypatch):
    _reset_ingest_state()
    job_id = str(uuid4())

    class _CancelCollection:
        def __init__(self):
            self.query = None
            self.update = None

        def update_one(self, query, update):  # noqa: ANN001
            self.query = query
            self.update = update
            return SimpleNamespace(matched_count=1)

        def find_one(self, query):  # noqa: ANN001
            return {"job_id": job_id, "status": "running"}

    collection = _CancelCollection()
    monkeypatch.setattr(
        ingest,
        "get_mongodb_client",
        lambda: SimpleNamespace(get_collection=lambda _name: collection),
    )

    response = await ingest.cancel_job(job_id)

    assert collection.update["$set"]["status"] == "cancelled"
    assert response["status"] == "cancelled"


def test_pack_to_dict_preserves_entity_role_metadata():
    pack = SimpleNamespace(
        pack_id=uuid4(),
        name="Taxonomy Pack",
        description="Contains synthesized container entities.",
        pack_type=KnowledgePackType.CUSTOM,
        status=KnowledgePackStatus.READY,
        system_name="Test System",
        game_system_id=None,
        axiom_count=0,
        entity_count=1,
        lore_fact_count=0,
        axioms=[],
        entity_archetypes=[
            ExtractedEntityArchetype(
                name="Clan",
                entity_type="concept",
                sub_type="container",
                description="A grouping entity for vampire lineages.",
                properties={"container": True},
                entity_roles=["container", "taxonomy_container"],
                is_container=True,
                parent_entity_name=None,
                source_ref="test-source",
                confidence=0.95,
                tags=["schema_family"],
            )
        ],
        lore_facts=[],
        entity_relationships=[],
        created_at=datetime.now(timezone.utc),
        updated_at=None,
        applied_to=[],
        parent_pack_ids=[],
        source_document_ids=[],
    )

    payload = ingest._pack_to_dict(pack)
    entity_payload = payload["entity_archetypes"][0]

    assert entity_payload["sub_type"] == "container"
    assert entity_payload["entity_roles"] == ["container", "taxonomy_container"]
    assert entity_payload["is_container"] is True


def test_pack_to_dict_exposes_mindscape_artifacts():
    pack = SimpleNamespace(
        pack_id=uuid4(),
        name="Mindscape Pack",
        description="Contains semantic ingest artifacts.",
        pack_type=KnowledgePackType.CUSTOM,
        status=KnowledgePackStatus.READY,
        system_name="Death in Space",
        game_system_id=None,
        game_system_data=None,
        source_profile_data=None,
        chunk_summaries=[
            SimpleNamespace(
                model_dump=lambda mode="json": {
                    "chunk_id": "chunk-1",
                    "chunk_index": 0,
                    "summary": "Scavenger crews barter for air and salvage.",
                    "confidence": 0.8,
                    "tags": ["economy"],
                    "source_ref": "Chapter 1",
                }
            )
        ],
        section_summaries=[
            SimpleNamespace(
                model_dump=lambda mode="json": {
                    "section_key": "chapter_1",
                    "heading_path": ["Chapter 1"],
                    "chunk_ids": ["chunk-1"],
                    "summary": "Introduces the dying station economy.",
                    "confidence": 0.84,
                    "semantic_category": "lore_history",
                }
            )
        ],
        source_mindscape=SimpleNamespace(
            model_dump=lambda mode="json": {
                "source_name": "Death in Space",
                "summary": "Bleak survival horror in a decaying cosmos.",
                "themes": ["scarcity"],
                "taxonomy_hints": ["Void"],
                "system_name": "Death in Space",
                "confidence": 0.9,
            }
        ),
        axiom_count=0,
        entity_count=0,
        lore_fact_count=0,
        axioms=[],
        entity_archetypes=[],
        lore_facts=[],
        entity_relationships=[],
        created_at=datetime.now(timezone.utc),
        updated_at=None,
        applied_to=[],
        parent_pack_ids=[],
        source_document_ids=[],
    )

    payload = ingest._pack_to_dict(pack)

    assert payload["chunk_summaries"][0]["chunk_id"] == "chunk-1"
    assert payload["section_summaries"][0]["section_key"] == "chapter_1"
    assert payload["source_mindscape"]["system_name"] == "Death in Space"


def test_pack_to_dict_exposes_extended_ingestion_outputs():
    pack = SimpleNamespace(
        pack_id=uuid4(),
        name="Extended Pack",
        description="Contains P1 extraction outputs.",
        pack_type=KnowledgePackType.RULEBOOK,
        status=KnowledgePackStatus.READY,
        system_name="V20",
        game_system_id=None,
        game_system_data=None,
        source_profile_data=None,
        chunk_summaries=[],
        section_summaries=[],
        source_mindscape=None,
        axiom_count=0,
        entity_count=0,
        lore_fact_count=0,
        axioms=[],
        entity_archetypes=[],
        lore_facts=[],
        entity_relationships=[],
        random_tables=[ExtractedRandomTable(name="Street Encounters")],
        agendas=[ExtractedAgenda(title="Prince's Clock", description="The court tightens control.")],
        topologies=[ExtractedTopology(from_location="Elysium", to_location="Haven")],
        tone_profiles=[
            ExtractedToneProfile(
                name="Gothic Pressure",
                description="Dark social dread.",
                instruction="Keep narration tense and intimate.",
            )
        ],
        character_profiles=[ExtractedCharacterProfile(name="Camarilla Elder")],
        generation_templates=[
            ExtractedGenerationTemplate(name="Harpy Envoy", archetype_name="Harpy")
        ],
        created_at=datetime.now(timezone.utc),
        updated_at=None,
        applied_to=[],
        parent_pack_ids=[],
        source_document_ids=[],
    )

    payload = ingest._pack_to_dict(pack)

    assert payload["random_tables"][0]["name"] == "Street Encounters"
    assert payload["agendas"][0]["title"] == "Prince's Clock"
    assert payload["topologies"][0]["from_location"] == "Elysium"
    assert payload["tone_profiles"][0]["name"] == "Gothic Pressure"
    assert payload["character_profiles"][0]["name"] == "Camarilla Elder"
    assert payload["generation_templates"][0]["name"] == "Harpy Envoy"
    assert payload["random_table_count"] == 1
    assert payload["tone_profile_count"] == 1
    assert payload["generation_template_count"] == 1


def test_normalize_selected_layers_returns_default_for_none():
    result = ingest._normalize_selected_layers(None, KnowledgePackType.SETTING_SUPPLEMENT)
    assert result == ingest._default_processing_checklist(KnowledgePackType.SETTING_SUPPLEMENT)


def test_normalize_selected_layers_returns_provided_list():
    result = ingest._normalize_selected_layers(["entities", "facts"], KnowledgePackType.RULEBOOK)
    assert result == ["entities", "facts"]


def test_normalize_selected_layers_normalizes_layer_names():
    result = ingest._normalize_selected_layers(["Entities", "FACTS", "Rules"], KnowledgePackType.ADVENTURE_MODULE)
    assert result == ["entities", "facts", "rules"]


def test_normalize_bool_flag_returns_default_for_none():
    result = ingest._normalize_bool_flag(None, default=True)
    assert result is True

    result = ingest._normalize_bool_flag(None, default=False)
    assert result is False


def test_normalize_bool_flag_converts_strings_to_bool():
    assert ingest._normalize_bool_flag("true") is True
    assert ingest._normalize_bool_flag("True") is True
    assert ingest._normalize_bool_flag("TRUE") is True
    assert ingest._normalize_bool_flag("false") is False
    assert ingest._normalize_bool_flag("False") is False
    assert ingest._normalize_bool_flag("FALSE") is False
    assert ingest._normalize_bool_flag("") is False
    assert ingest._normalize_bool_flag("yes") is True
    assert ingest._normalize_bool_flag("no") is False
    assert ingest._normalize_bool_flag(True) is True
    assert ingest._normalize_bool_flag(False) is False
