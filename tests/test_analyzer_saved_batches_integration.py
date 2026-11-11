"""Saved Analyzer batches round-trip through the real book_records store (I-17, I-8).

Needs a reachable MongoDB (``RUN_INTEGRATION=1``); no model is called. The
point is the contract a rescan relies on: a batch saved by one run is found by
a later run over the same document and settings, and is invisible to a run
with different batching settings.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


def test_a_saved_batch_is_found_by_a_later_run_with_the_same_settings(monkeypatch):
    from monitor_agents.analyzer._store import AnalyzerBatchStore, prompt_key
    from monitor_data.tools.mongodb_tools.book_decomposition import mongodb_delete_book_records

    doc_id = str(uuid4())
    key = prompt_key(
        model="model-a",
        stage="batched_extraction",
        instructions="extract from the section",
        kwargs={"sections_context": "# Section: Chapter > One\ntext", "source_name": "Book"},
    )
    payload = {
        "extraction_reasoning": "reasoned through the section",
        "axioms": [],
        "entities": [],
        "lore_facts": [],
        "sections_covered": ["Chapter > One"],
    }
    try:
        first_run = AnalyzerBatchStore(doc_id)
        first_run.put(key, payload)

        # A later run over the same document and settings reuses it.
        second_run = AnalyzerBatchStore(doc_id)
        assert second_run.get(key) == payload
        assert second_run.reused == 1

        # A run with different batching settings must not see it.
        monkeypatch.setenv("MONITOR_ANALYZER_BATCH_SECTIONS", "7")
        changed_settings = AnalyzerBatchStore(doc_id)
        assert changed_settings.get(key) is None
    finally:
        mongodb_delete_book_records(doc_id)
