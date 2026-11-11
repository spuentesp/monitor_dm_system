"""Decomposition-aware layer selection and batched section summaries (I-17 tasks 11-12).

The decomposition flag and the stored book tree are read through the real
callees (`book_decomposition_enabled`, `mongodb_list_book_records`); only the
model calls are faked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from monitor_data.schemas.book_graph import BookRecordType
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_agents.analyzer import Analyzer
from monitor_agents.analyzer._models import LLMExecutionSummary
from monitor_agents.analyzer.analyzer import SectionSummaryItem
from monitor_agents.utils.analyzer_support import SectionDigest


def _section(path: str = "Chapter > Bits", text: str = "Some game text.") -> SectionDigest:
    return SectionDigest(section_path=path, text=text, min_page=1, min_chunk_index=1)


def _empty_mindscape(**_kwargs):
    from monitor_data.schemas.knowledge_packs import SourceMindscapeArtifact

    return SourceMindscapeArtifact(
        source_name="X", summary="", themes=[], taxonomy_hints=[], system_name=None, confidence=0.0
    )


async def _run_full_analysis(monkeypatch, *, layers: list[str]) -> dict:
    """Run analyze_source with everything faked except the layer-selection logic."""
    analyzer = Analyzer()
    captured: dict = {}

    def _create_pack(*_args, **_kwargs):
        pid = uuid4()
        return SimpleNamespace(id=pid, pack_id=pid)

    monkeypatch.setattr("monitor_agents.analyzer._core.mongodb_create_knowledge_pack", _create_pack)
    monkeypatch.setattr("monitor_agents.analyzer._core.mongodb_update_knowledge_pack", lambda *_a, **_k: None)
    monkeypatch.setattr(analyzer, "_update_job", lambda *_a, **_k: None)
    monkeypatch.setattr(analyzer, "_retrieve_sections_by_category", AsyncMock(return_value=[_section()]))
    monkeypatch.setattr(analyzer, "_retrieve_reference_sections", AsyncMock(return_value=[]))
    monkeypatch.setattr(analyzer, "_classify_and_filter_sections", AsyncMock(side_effect=lambda s, _name: s))
    monkeypatch.setattr(analyzer, "_synthesize_source_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(analyzer, "synthesize_mindscape", AsyncMock(side_effect=_empty_mindscape))
    monkeypatch.setattr(analyzer, "_detect_game_system", AsyncMock(return_value=(True, "DiS")))

    async def _capture_batched(sections, source_name, include_axioms, include_entities, include_lore, **kwargs):
        captured["include_axioms"] = include_axioms
        captured["include_entities"] = include_entities
        captured["include_lore"] = include_lore
        return [], [], []

    monkeypatch.setattr(analyzer, "_batched_extract_all", _capture_batched)
    rules_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(analyzer, "_extract_game_rules", rules_mock)
    captured["game_rules_mock"] = rules_mock

    for name in (
        "_extract_random_tables",
        "_extract_agendas",
        "_extract_topologies",
        "_extract_tone_profiles",
        "_extract_character_profiles",
        "_extract_generation_templates",
        "_extract_plot_threads",
    ):
        monkeypatch.setattr(analyzer, name, AsyncMock(return_value=[]))
    for name in ("_extract_character_sheet", "_extract_creation_procedure", "_extract_npc_data"):
        monkeypatch.setattr(analyzer, name, AsyncMock(return_value={}))

    await analyzer.analyze_source(
        job_id=uuid4(),
        source_name="Death in Space",
        source_document_ids=[uuid4()],
        pack_name="DiS",
        pack_type=KnowledgePackType.RULEBOOK,
        analysis_layers=layers,
        auto_apply=False,
    )
    return captured


LAYERS = ["axioms", "entities", "lore", "game_system", "rules", "tone", "character_profiles", "plot_threads"]


@pytest.mark.asyncio
async def test_decomposition_on_skips_axioms_lore_and_rules(monkeypatch):
    # The real book_decomposition_enabled() reads this flag.
    monkeypatch.setenv("MONITOR_BOOK_DECOMPOSITION", "1")

    captured = await _run_full_analysis(monkeypatch, layers=LAYERS)

    assert captured["include_axioms"] is False
    assert captured["include_lore"] is False
    # Entities stay: relationship inference and the game system need them.
    assert captured["include_entities"] is True
    captured["game_rules_mock"].assert_not_called()


@pytest.mark.asyncio
async def test_decomposition_off_keeps_every_layer(monkeypatch):
    monkeypatch.delenv("MONITOR_BOOK_DECOMPOSITION", raising=False)

    captured = await _run_full_analysis(monkeypatch, layers=LAYERS)

    assert captured["include_axioms"] is True
    assert captured["include_lore"] is True
    assert captured["include_entities"] is True
    captured["game_rules_mock"].assert_awaited_once()


# ---------------------------------------------------------------------------
# Section summaries (task 12)
# ---------------------------------------------------------------------------


def _summary_fake(calls: list[str]):
    async def fake_call_module(module, **kwargs):
        stage = kwargs.get("stage")
        calls.append(str(stage))
        if stage == "section_summary":
            headings = [
                line.removeprefix("# Section: ").strip()
                for line in kwargs["sections_context"].splitlines()
                if line.startswith("# Section: ")
            ]
            return SimpleNamespace(
                summaries=[
                    SectionSummaryItem(heading_path=head, summary=f"summary of {head}", themes=[]) for head in headings
                ]
            )
        if stage == "mindscape_synthesis":
            return SimpleNamespace(global_summary="global", themes=[], taxonomy_hints=[], system_name=None)
        raise AssertionError(f"unexpected stage {stage}")

    return fake_call_module


def _prepare_mindscape(monkeypatch, analyzer: Analyzer) -> dict:
    captured: dict = {}
    analyzer._project_mindscape_to_qdrant = AsyncMock()
    monkeypatch.setattr(
        "monitor_agents.analyzer._core.persist_mindscape_artifacts",
        lambda **kwargs: captured.update(kwargs),
    )
    monkeypatch.setattr(
        "monitor_agents.analyzer._core.mongodb_list_book_records",
        lambda *_args, **_kwargs: [],
    )
    return captured


@pytest.mark.asyncio
async def test_section_summaries_run_ten_per_call(monkeypatch):
    analyzer = Analyzer()
    captured = _prepare_mindscape(monkeypatch, analyzer)
    calls: list[str] = []
    monkeypatch.setattr(analyzer, "_call_module", _summary_fake(calls))
    sections = [_section(path=f"Section {i}", text="text") for i in range(25)]

    await analyzer.synthesize_mindscape(sections=sections, source_name="Book", pack_id=uuid4())

    summary_calls = [stage for stage in calls if stage == "section_summary"]
    assert len(summary_calls) == 3  # 25 sections, 10 per call → 10 + 10 + 5
    assert calls.count("mindscape_synthesis") == 1
    assert len(captured["section_summaries"]) == 25
    assert all(item.summary.startswith("summary of ") for item in captured["section_summaries"])


@pytest.mark.asyncio
async def test_summary_batch_size_is_a_setting(monkeypatch):
    monkeypatch.setenv("MONITOR_ANALYZER_SUMMARY_BATCH", "5")
    analyzer = Analyzer()
    _prepare_mindscape(monkeypatch, analyzer)
    calls: list[str] = []
    monkeypatch.setattr(analyzer, "_call_module", _summary_fake(calls))
    sections = [_section(path=f"Section {i}", text="text") for i in range(12)]

    await analyzer.synthesize_mindscape(sections=sections, source_name="Book", pack_id=uuid4())

    assert calls.count("section_summary") == 3  # 12 sections, 5 per call → 5 + 5 + 2


@pytest.mark.asyncio
async def test_summaries_are_skipped_when_the_decomposition_tree_exists(monkeypatch):
    analyzer = Analyzer()
    doc_id = uuid4()
    analyzer._active_doc_ids = [doc_id]
    captured = _prepare_mindscape(monkeypatch, analyzer)
    list_calls: list[tuple[str, BookRecordType]] = []

    def fake_list(record_doc_id: str, record_type: BookRecordType):
        list_calls.append((record_doc_id, record_type))
        if record_type is BookRecordType.TREE_META:
            return [SimpleNamespace(key="meta", data={"doc_id": record_doc_id})]
        return []

    monkeypatch.setattr("monitor_agents.analyzer._core.mongodb_list_book_records", fake_list)

    async def no_model_calls(module, **kwargs):
        raise AssertionError(f"no model call expected, got stage={kwargs.get('stage')}")

    monkeypatch.setattr(analyzer, "_call_module", no_model_calls)
    sections = [
        SectionDigest(
            section_path=f"Section {i}",
            text="text",
            min_page=1,
            min_chunk_index=0,
            chunk_ids=[f"chunk-{i}"],
            chunk_records=[
                {
                    "chunk_id": f"chunk-{i}",
                    "chunk_index": 0,
                    "page": 1,
                    "text": "text worth a compact summary line",
                    "semantic_category": "general",
                }
            ],
        )
        for i in range(3)
    ]

    mindscape = await analyzer.synthesize_mindscape(sections=sections, source_name="Book", pack_id=uuid4())

    # Cross-component boundary: the real store reader is asked for this doc's tree.
    assert (str(doc_id), BookRecordType.TREE_META) in list_calls
    assert mindscape.confidence == 0.0
    # Free chunk summaries still persist; no fake section summaries are invented.
    assert captured["section_summaries"] == []
    assert len(captured["chunk_summaries"]) > 0


@pytest.mark.asyncio
async def test_a_summary_reply_that_drops_a_section_is_recorded_as_held(monkeypatch):
    analyzer = Analyzer()
    analyzer._active_execution_summary = LLMExecutionSummary()
    _prepare_mindscape(monkeypatch, analyzer)
    sections = [_section(path="Alpha", text="text"), _section(path="Beta", text="text")]
    seen: list[tuple[str, ...]] = []

    async def drops_beta(module, **kwargs):
        stage = kwargs.get("stage")
        if stage == "mindscape_synthesis":
            return SimpleNamespace(global_summary="g", themes=[], taxonomy_hints=[], system_name=None)
        headings = tuple(
            line.removeprefix("# Section: ").strip()
            for line in kwargs["sections_context"].splitlines()
            if line.startswith("# Section: ")
        )
        seen.append(headings)
        return SimpleNamespace(
            summaries=[
                SectionSummaryItem(heading_path=head, summary=f"s {head}") for head in headings if head != "Beta"
            ]
        )

    monkeypatch.setattr(analyzer, "_call_module", drops_beta)

    await analyzer.synthesize_mindscape(sections=sections, source_name="Book", pack_id=uuid4())

    # Full batch, then Beta alone (which also drops it) → held with a record.
    assert seen == [("Alpha", "Beta"), ("Beta",)]
    failed = analyzer._active_execution_summary.failed_sections
    assert [entry["section_path"] for entry in failed] == ["Beta"]
    assert failed[0]["stage"] == "section_summary"
    assert "did not cover" in failed[0]["reason"]


@pytest.mark.asyncio
async def test_summary_batch_one_keeps_the_single_section_call_shape(monkeypatch):
    monkeypatch.setenv("MONITOR_ANALYZER_SUMMARY_BATCH", "1")
    analyzer = Analyzer()
    captured = _prepare_mindscape(monkeypatch, analyzer)
    calls: list[tuple[str, dict]] = []

    async def fake_call_module(module, **kwargs):
        calls.append((str(kwargs.get("stage")), dict(kwargs)))
        if kwargs.get("stage") == "section_summary":
            return SimpleNamespace(summary="one section summary", themes=[])
        return SimpleNamespace(global_summary="g", themes=[], taxonomy_hints=[], system_name=None)

    monkeypatch.setattr(analyzer, "_call_module", fake_call_module)
    sections = [_section(path="Alpha", text="text"), _section(path="Beta", text="text")]

    await analyzer.synthesize_mindscape(sections=sections, source_name="Book", pack_id=uuid4())

    summary_calls = [kw for stage, kw in calls if stage == "section_summary"]
    assert len(summary_calls) == 2  # pre-phase shape: one call per section
    assert all("heading_path" in kw and "section_text" in kw for kw in summary_calls)
    assert all(item.summary for item in captured["section_summaries"])
