"""Reuse layers for finished Analyzer batches: saved batches, then disk cache (I-17, I-8).

Every test fakes the MongoDB book-record boundary or the filesystem; no real
model and no repository files are involved.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import dspy
import pytest
from monitor_data.schemas.book_graph import BookRecordType
from monitor_agents.analyzer import Analyzer
from monitor_agents.analyzer import _settings
from monitor_agents.analyzer._store import (
    AnalyzerBatchStore,
    ResponseDiskCache,
    prediction_from_jsonable,
    prediction_to_jsonable,
    prompt_key,
)
from monitor_agents.analyzer.analyzer import BatchedExtractionModule


def _prediction(**fields):
    # BatchedExtractionSignature declares extraction_reasoning as an output
    # field, and the reuse layers reject payloads that omit a declared field.
    fields.setdefault("extraction_reasoning", "reasoned through the section")
    return dspy.Prediction(**fields)


def _result(value):
    return SimpleNamespace(value=value)


def _fake_records():
    """In-memory stand-in for the book_records collection."""
    store: dict[tuple[str, BookRecordType, str], dict] = {}

    def list_records(doc_id: str, record_type: BookRecordType):
        return [
            SimpleNamespace(key=key, data=data)
            for (doc, rtype, key), data in store.items()
            if doc == doc_id and rtype == record_type
        ]

    def upsert_records(doc_id: str, record_type: BookRecordType, records) -> int:
        for record in records:
            store[(doc_id, record_type, record.key)] = record.data
        return len(records)

    return store, list_records, upsert_records


def _prepared_analyzer(doc_id: str) -> Analyzer:
    analyzer = Analyzer()
    analyzer._batch_store = AnalyzerBatchStore(doc_id)
    analyzer._response_cache = ResponseDiskCache()
    return analyzer


# ---------------------------------------------------------------------------
# Saved batches (first layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_finished_batch_is_saved_and_the_next_run_reuses_it(monkeypatch):
    doc_id = str(uuid4())
    _, list_records, upsert_records = _fake_records()
    upsert_calls: list[tuple[str, BookRecordType, list]] = []
    monkeypatch.setattr(
        "monitor_agents.analyzer._store.mongodb_list_book_records",
        list_records,
    )

    def capturing_upsert(doc_id_arg, record_type, records):
        upsert_calls.append((doc_id_arg, record_type, list(records)))
        return upsert_records(doc_id_arg, record_type, records)

    monkeypatch.setattr(
        "monitor_agents.analyzer._store.mongodb_upsert_book_records",
        capturing_upsert,
    )

    module = BatchedExtractionModule()
    first_value = _prediction(axioms=[], entities=[], lore_facts=[], sections_covered=["s1"])
    runner = AsyncMock(return_value=_result(first_value))

    analyzer = _prepared_analyzer(doc_id)
    monkeypatch.setattr(analyzer._llm_runner, "run_blocking", runner)

    returned = await analyzer._call_module(
        module,
        stage="batched_extraction",
        sections_context="# Section: s1\ntext",
        source_name="Source",
        known_graph_context="",
        source_profile_context="",
    )
    runner.assert_awaited_once()
    assert returned.sections_covered == ["s1"]

    # Cross-component boundary: the real store callee is invoked with the
    # document id, the REPORT record type and a settings-scoped key.
    assert len(upsert_calls) == 1
    saved_doc, saved_type, saved_records = upsert_calls[0]
    assert saved_doc == doc_id
    assert saved_type is BookRecordType.REPORT
    assert saved_records[0].key.startswith(f"analyzer-batch:{_settings.settings_hash()}:")
    assert saved_records[0].data["payload"]["sections_covered"] == ["s1"]

    # Second run, fresh instance, same document: no model call.
    runner2 = AsyncMock()
    analyzer2 = _prepared_analyzer(doc_id)
    monkeypatch.setattr(analyzer2._llm_runner, "run_blocking", runner2)
    reused = await analyzer2._call_module(
        module,
        stage="batched_extraction",
        sections_context="# Section: s1\ntext",
        source_name="Source",
        known_graph_context="",
        source_profile_context="",
    )
    runner2.assert_not_awaited()
    assert reused.sections_covered == ["s1"]
    assert analyzer2._batch_store.reused == 1


@pytest.mark.asyncio
async def test_a_settings_change_invalidates_saved_batches(monkeypatch):
    doc_id = str(uuid4())
    _, list_records, upsert_records = _fake_records()
    monkeypatch.setattr("monitor_agents.analyzer._store.mongodb_list_book_records", list_records)
    monkeypatch.setattr("monitor_agents.analyzer._store.mongodb_upsert_book_records", upsert_records)

    module = BatchedExtractionModule()
    runner = AsyncMock(
        return_value=_result(_prediction(axioms=[], entities=[], lore_facts=[], sections_covered=["s1"]))
    )
    analyzer = _prepared_analyzer(doc_id)
    monkeypatch.setattr(analyzer._llm_runner, "run_blocking", runner)
    await analyzer._call_module(module, stage="batched_extraction", sections_context="s1", source_name="S")
    runner.assert_awaited_once()

    # Same prompt, different batching settings → different key → model runs again.
    monkeypatch.setenv("MONITOR_ANALYZER_BATCH_SECTIONS", "7")
    runner2 = AsyncMock(
        return_value=_result(_prediction(axioms=[], entities=[], lore_facts=[], sections_covered=["s1"]))
    )
    analyzer2 = _prepared_analyzer(doc_id)
    monkeypatch.setattr(analyzer2._llm_runner, "run_blocking", runner2)
    await analyzer2._call_module(module, stage="batched_extraction", sections_context="s1", source_name="S")
    runner2.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_dead_database_degrades_to_plain_model_calls(monkeypatch):
    doc_id = str(uuid4())

    def broken(*_args, **_kwargs):
        raise RuntimeError("mongo down")

    monkeypatch.setattr("monitor_agents.analyzer._store.mongodb_list_book_records", broken)
    monkeypatch.setattr("monitor_agents.analyzer._store.mongodb_upsert_book_records", broken)

    module = BatchedExtractionModule()
    runner = AsyncMock(
        return_value=_result(_prediction(axioms=[], entities=[], lore_facts=[], sections_covered=["s1"]))
    )
    analyzer = _prepared_analyzer(doc_id)
    monkeypatch.setattr(analyzer._llm_runner, "run_blocking", runner)

    returned = await analyzer._call_module(module, stage="batched_extraction", sections_context="s", source_name="S")
    assert returned.sections_covered == ["s1"]
    runner.assert_awaited_once()


def test_the_prompt_key_changes_with_model_prompt_and_settings(monkeypatch):
    base = dict(model="model-a", stage="batched_extraction", instructions="do the thing", kwargs={"x": "1"})
    key = prompt_key(**base)

    assert prompt_key(**{**base, "model": "model-b"}) != key
    assert prompt_key(**{**base, "instructions": "other"}) != key
    assert prompt_key(**{**base, "kwargs": {"x": "2"}}) != key
    monkeypatch.setenv("MONITOR_ANALYZER_BATCH_WORDS", "4321")
    assert prompt_key(**base) != key
    monkeypatch.delenv("MONITOR_ANALYZER_BATCH_WORDS")
    assert prompt_key(**base) == key


def test_saved_payloads_round_trip_through_the_signature():
    module = BatchedExtractionModule()
    payload = prediction_to_jsonable(_prediction(axioms=[], entities=[], lore_facts=[], sections_covered=["A", "B"]))
    restored = prediction_from_jsonable(payload, module._signature)

    assert restored.sections_covered == ["A", "B"]
    assert restored.axioms == []


# ---------------------------------------------------------------------------
# Disk cache (second layer)
# ---------------------------------------------------------------------------


def test_the_disk_cache_is_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("MONITOR_ANALYZER_LLM_CACHE", raising=False)
    monkeypatch.setenv("MONITOR_ANALYZER_LLM_CACHE_DIR", str(tmp_path))
    assert not ResponseDiskCache().enabled
    assert not ResponseDiskCache().enabled and not list(tmp_path.iterdir())


def test_the_disk_cache_round_trips_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("MONITOR_ANALYZER_LLM_CACHE", "1")
    monkeypatch.setenv("MONITOR_ANALYZER_LLM_CACHE_DIR", str(tmp_path))
    cache = ResponseDiskCache()
    assert cache.enabled

    cache.put("abc123", {"sections_covered": ["s"]})
    assert cache.get("abc123") == {"sections_covered": ["s"]}
    assert cache.get("missing") is None
    # Everything lives under the configured directory, outside the repository.
    files = [p for p in tmp_path.rglob("*.json")]
    assert files and all(str(f).startswith(str(tmp_path)) for f in files)


def test_the_disk_cache_refuses_a_directory_inside_a_git_checkout(monkeypatch, tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()

    cache = ResponseDiskCache(root=checkout, enabled=True)
    assert cache.enabled
    assert cache._path("somekey").parent.parent == _settings.DEFAULT_CACHE_DIR


@pytest.mark.asyncio
async def test_an_enabled_disk_cache_avoids_the_second_model_call(monkeypatch, tmp_path):
    monkeypatch.setenv("MONITOR_ANALYZER_LLM_CACHE", "1")
    monkeypatch.setenv("MONITOR_ANALYZER_LLM_CACHE_DIR", str(tmp_path))

    module = BatchedExtractionModule()
    runner = AsyncMock(
        return_value=_result(_prediction(axioms=[], entities=[], lore_facts=[], sections_covered=["s1"]))
    )
    analyzer = Analyzer()
    analyzer._batch_store = AnalyzerBatchStore(None)  # saved-batch layer off
    analyzer._response_cache = ResponseDiskCache()
    monkeypatch.setattr(analyzer._llm_runner, "run_blocking", runner)

    await analyzer._call_module(module, stage="batched_extraction", sections_context="s1", source_name="S")
    runner.assert_awaited_once()

    runner2 = AsyncMock()
    analyzer2 = Analyzer()
    analyzer2._batch_store = AnalyzerBatchStore(None)
    analyzer2._response_cache = ResponseDiskCache()
    monkeypatch.setattr(analyzer2._llm_runner, "run_blocking", runner2)
    reused = await analyzer2._call_module(module, stage="batched_extraction", sections_context="s1", source_name="S")
    runner2.assert_not_awaited()
    assert reused.sections_covered == ["s1"]
