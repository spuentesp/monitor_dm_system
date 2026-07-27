"""
End-to-end ingestion-pipeline regression test against a real PDF fixture.

INGESTION_PIPELINE_AUDIT.md Finding 6: nothing in the test suite ran the real
PDF-parsing + section-scoring + character-creation-assembly path together —
every existing Analyzer test mocks the LLM extraction calls, which is correct
for unit coverage but left the actual failure mode (real content producing an
empty/degenerate result) with zero coverage. That's why the VtM 20th
Anniversary ingestion sat broken from 2026-06-22 until the audit found it.

This test exercises:
  - real `extract_pdf_structure()` against a small, checked-in fixture PDF
    with genuine `fitz` bookmarks (tests/fixtures/ingestion/tiny_rulebook.pdf)
  - real `system_section_score()` / `prioritize_schema_sections()` ranking
  - real `Analyzer._extract_character_sheet` / `_extract_creation_procedure`
    assembly (heuristic pass + per-section + synthesis + dedup)
  - real `_build_character_creation` (Finding 2's semantic step_type check)
  - real `_detect_degenerate_extraction` (Finding 5)

Only the two DSPy calls (`_call_module` for character-sheet and
creation-procedure extraction) are mocked, at the same boundary the audit
specifies — everything else in the path is the genuine production code.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from monitor_data.schemas.game_systems import (
    AttributeDefinition,
    CoreMechanic,
    CoreMechanicType,
    CreationStep,
    CreationStepType,
    ResourceDefinition,
    SkillDefinition,
    SuccessType,
)
from monitor_data.tools.ingest_tools.pdf_processing import extract_pdf_structure

from monitor_agents.analyzer import Analyzer
from monitor_agents.analyzer._game_system_persistence import (
    _build_attributes,
    _build_character_creation,
    _build_core_mechanic,
    _detect_degenerate_extraction,
)
from monitor_agents.utils.analyzer_support import SectionDigest, system_section_score

FIXTURE_PDF = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ingestion" / "tiny_rulebook.pdf"


def _load_section_digests() -> list[SectionDigest]:
    """Real PDF parsing (`extract_pdf_structure`), bridged into `SectionDigest`.

    In production this bridge is the Indexer's chunk/embed pass into Qdrant
    followed by chunk-retrieval back into SectionDigests — standing that up
    would require live Qdrant + embeddings, which is exactly the network
    dependency Finding 6 wants this test to avoid. The bridge itself (turning
    a `SectionBlock` into a `SectionDigest`) is a trivial, lossless field
    mapping, not a thing under test.
    """
    pdf_bytes = FIXTURE_PDF.read_bytes()
    blocks = extract_pdf_structure(pdf_bytes)
    return [
        SectionDigest(
            section_path=" > ".join(block.heading_path),
            text=block.text,
            min_page=block.page_start,
            min_chunk_index=0,
        )
        for block in blocks
    ]


class TestFixturePdfExists:
    def test_fixture_present(self) -> None:
        assert FIXTURE_PDF.exists(), f"missing fixture: {FIXTURE_PDF}"

    def test_fixture_has_real_bookmarks_and_text(self) -> None:
        digests = _load_section_digests()
        paths = {d.section_path for d in digests}
        assert "Attributes" in paths
        assert "Character Creation Process" in paths
        assert "Abilities" in paths
        cc_section = next(d for d in digests if d.section_path == "Character Creation Process")
        assert "attribute" in cc_section.text.lower() or "Attribute" in cc_section.text

    def test_real_section_scoring_ranks_schema_sections_above_lore(self) -> None:
        """Mirrors the audit's own finding: 'Character Creation Process'
        and 'Attributes' should outrank a pure-lore introduction chapter."""
        digests = _load_section_digests()
        scores = {d.section_path: system_section_score(d) for d in digests}
        assert scores["Attributes"] > scores["Introduction"]
        assert scores["Character Creation Process"] > scores["Introduction"]


def _fake_charsheet_result() -> SimpleNamespace:
    """What CharacterSheetExtractionModule would plausibly return for the
    fixture's real 'Attributes'/'Abilities'/'Resolving Actions' text."""
    return SimpleNamespace(
        attributes=[
            AttributeDefinition(name="Might", abbreviation="MGT", min_value=1, max_value=5, default_value=2),
            AttributeDefinition(name="Cunning", abbreviation="CUN", min_value=1, max_value=5, default_value=2),
            AttributeDefinition(name="Grace", abbreviation="GRC", min_value=1, max_value=5, default_value=2),
        ],
        skills=[
            SkillDefinition(name="Athletics", linked_attribute="Might"),
            SkillDefinition(name="Lore", linked_attribute="Cunning"),
            SkillDefinition(name="Stealth", linked_attribute="Grace"),
        ],
        resources=[ResourceDefinition(name="Hit Points", abbreviation="HP")],
        conditions=[],
        scenery_rules=[],
        core_mechanic=CoreMechanic(
            type=CoreMechanicType.DICE_POOL,
            formula="Attribute + Ability dice pool, 5-6 succeed",
            success_type=SuccessType.COUNT_SUCCESSES,
        ),
        resolution_mechanics=[],
    )


def _fake_creation_procedure_result() -> SimpleNamespace:
    """What CreationProcedureExtractionModule would return for the fixture's
    real 'Character Creation Process' text — including one step whose
    step_type is deliberately mislabeled, the same way the real VtM seed
    doc's steps 4/5 were (Finding 2). The regression asserts it gets
    relabeled to CUSTOM by `_build_character_creation`, end to end."""
    return SimpleNamespace(
        steps=[
            CreationStep(
                step_number=1,
                step_type=CreationStepType.CHOOSE_NAME,
                title="Choose Name",
                instructions="Choose your character's Name.",
            ),
            CreationStep(
                step_number=2,
                step_type=CreationStepType.GENERATE_ATTRIBUTES,
                title="Assign Attribute Dots",
                instructions="Distribute 6 dots among Might, Cunning, and Grace.",
            ),
            CreationStep(
                step_number=3,
                step_type=CreationStepType.CHOOSE_SKILLS,
                title="Choose Abilities",
                instructions="Choose two starting Abilities and set each to rank 1.",
            ),
            # Deliberately mislabeled — content is about Backgrounds, not
            # Skills, the same shape of bug as the real VtM seed doc.
            CreationStep(
                step_number=4,
                step_type=CreationStepType.CHOOSE_SKILLS,
                title="Choose a Background",
                instructions="Choose a Background: Wanderer, Scholar, or Guardian.",
            ),
            CreationStep(
                step_number=5,
                step_type=CreationStepType.WRITE_BACKSTORY,
                title="Write Backstory",
                instructions="Write a one-paragraph Backstory for your character.",
            ),
        ],
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestFullIngestionPathAgainstFixture:
    """The single test Finding 6 says would have caught Findings 1-5 months
    earlier: real PDF parsing → real section scoring → real extraction
    assembly → real semantic validation → real degenerate-extraction check,
    with only the two DSPy LLM calls mocked at the boundary."""

    async def _run_extraction(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        digests = _load_section_digests()
        analyzer = Analyzer()

        async def fake_call_module(module: Any, *, stage: str | None = None, **kwargs: Any) -> Any:
            if stage == "character_sheet_extraction" or stage == "character_sheet_synthesis":
                return _fake_charsheet_result()
            if stage == "creation_procedure_extraction":
                return _fake_creation_procedure_result()
            raise AssertionError(f"Unexpected DSPy stage in a mocked-boundary test: {stage}")

        monkeypatch.setattr(analyzer, "_call_module", fake_call_module)

        charsheet_data = await analyzer._extract_character_sheet(digests, "Tiny Fixture System")
        creation_procedure_data = await analyzer._extract_creation_procedure(digests, "Tiny Fixture System")
        return {
            "charsheet_data": charsheet_data,
            "creation_procedure_data": creation_procedure_data,
        }

    async def test_attributes_non_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = await self._run_extraction(monkeypatch)
        attrs = _build_attributes(result["charsheet_data"])
        assert len(attrs) == 3
        assert {a.name for a in attrs} == {"Might", "Cunning", "Grace"}

    async def test_core_mechanic_is_not_bare_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = await self._run_extraction(monkeypatch)
        core_mechanic = _build_core_mechanic(result["charsheet_data"])
        # The mocked extraction returned a real dice_pool mechanic — the
        # bare d20/meet_or_beat placeholder defaults must NOT appear.
        assert core_mechanic.type == CoreMechanicType.DICE_POOL
        assert core_mechanic.success_type == SuccessType.COUNT_SUCCESSES

    async def test_character_creation_steps_non_empty_and_semantically_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = await self._run_extraction(monkeypatch)
        procedure = _build_character_creation(result["creation_procedure_data"])
        assert procedure is not None
        assert len(procedure.steps) == 5

        # Finding 2, exercised end-to-end: the deliberately mislabeled
        # "Choose a Background" step (typed choose_skills) must have been
        # relabeled to CUSTOM, not silently misrouted.
        bg_step = next(s for s in procedure.steps if s.title == "Choose a Background")
        assert bg_step.step_type == CreationStepType.CUSTOM

        # Every step whose type WASN'T relabeled must genuinely match its
        # own content — this is the semantic contract the fix establishes.
        from monitor_agents.analyzer._game_system_persistence import _step_type_matches_content

        for step in procedure.steps:
            if step.step_type == CreationStepType.CUSTOM:
                continue
            assert _step_type_matches_content(step.step_type, step.title, step.instructions), (
                f"step {step.title!r} declared as {step.step_type.value} but doesn't semantically match its own content"
            )

    async def test_not_flagged_degenerate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Finding 5, exercised end-to-end: a healthy extraction against
        real content must NOT trip the degenerate-extraction guard."""
        result = await self._run_extraction(monkeypatch)
        attrs = _build_attributes(result["charsheet_data"])
        from monitor_agents.analyzer._game_system_persistence import _build_resources, _build_skills

        skills = _build_skills(result["charsheet_data"])
        resources = _build_resources(result["charsheet_data"])
        procedure = _build_character_creation(result["creation_procedure_data"])

        reason = _detect_degenerate_extraction(result["charsheet_data"], attrs, skills, resources, procedure)
        assert reason is None
