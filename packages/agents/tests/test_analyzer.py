from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from monitor_data.schemas.agendas import ExtractedAgenda
from monitor_data.schemas.knowledge_packs import (
    EmbeddedSourceProfile,
    ExtractedCharacterProfile,
    ExtractedEntityArchetype,
    ExtractedGenerationTemplate,
    ExtractedRandomTable,
    ExtractedToneProfile,
    ExtractedTopology,
    KnowledgePackType,
)

from monitor_agents.analyzer import Analyzer
from monitor_agents.analyzer.analyzer import BatchedExtractionModule
from monitor_agents.utils.analyzer_support import (
    SectionDigest,
    build_source_profile_seed,
    dedupe_named_items,
    format_source_profile_context,
    heuristic_extract_character_sheet_sections,
    parse_source_profile,
)


def _patch_common_analyzer_dependencies(monkeypatch, analyzer):
    # Real KnowledgePackResponse exposes the primary key as `.id` (pack_id is
    # only a deser alias); the analyzer reads `pack.id` (T-082). Provide both
    # so the mock matches the field the code actually uses.
    def _fake_create_pack(*_args, **_kwargs):
        _pid = uuid4()
        return SimpleNamespace(id=_pid, pack_id=_pid)

    monkeypatch.setattr(
        "monitor_agents.analyzer._core.mongodb_create_knowledge_pack",
        _fake_create_pack,
    )
    monkeypatch.setattr(
        "monitor_agents.analyzer._core.mongodb_update_knowledge_pack",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(analyzer, "_update_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(analyzer, "_detect_game_system", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(
        analyzer,
        "_classify_and_filter_sections",
        AsyncMock(side_effect=lambda sections, source_name: sections),
    )
    monkeypatch.setattr(analyzer, "_batched_extract_all", AsyncMock(return_value=([], [], [])))
    monkeypatch.setattr(analyzer, "_extract_game_rules", AsyncMock(return_value=[]))


def test_heuristic_charsheet_extraction_recovers_death_in_space_abilities():
    parsed = heuristic_extract_character_sheet_sections(
        [
            SectionDigest(
                section_path="1.ABILITIES",
                text=(
                    "There are four abilities: BODY (BDY) Bodily strength and physical resistance, melee attacks "
                    "DEXTERITY (DEX) Reflexes, poise and speed "
                    "SAVVY (SVY) Perception, intuition, psychological resistance, piloting spacecraft "
                    "TECH (TEC) Understanding and operating technology, ranged attacks "
                    "GENERATING ABILITY VALUES For each ability, roll two d4."
                ),
                min_page=1,
                min_chunk_index=1,
            ),
            SectionDigest(
                section_path="#52 > COMBAT //",
                text=(
                    "ENEMIES IN COMBAT Stats-wise, an enemy has a defense rating (DR), hit points (HP), morale (ML)."
                ),
                min_page=52,
                min_chunk_index=1,
            ),
            SectionDigest(
                section_path="GENERAL RULES > 1D20 + RELEVANT ABILITY",
                text="When the outcome is uncertain, roll 1d20 + relevant ability and succeed on 12 or more.",
                min_page=36,
                min_chunk_index=1,
            ),
        ],
        "Death in Space Core Rules",
    )

    assert {item["name"] for item in parsed["attributes"]} >= {"Body", "Dexterity", "Savvy", "Tech"}
    assert {item["name"] for item in parsed["resources"]} >= {
        "Defense Rating",
        "Hit Points",
        "Morale",
    }
    assert parsed["core_mechanic"]["type"] == "d20"
    assert "1d20" in parsed["core_mechanic"]["formula"]


def test_dedupe_named_items_filters_placeholder_schema_names():
    items = dedupe_named_items(
        [
            {"name": "Attribute"},
            {"name": "Attributes"},
            {"name": "Body"},
            {"name": "Tech"},
        ]
    )

    assert [item["name"] for item in items] == ["Body", "Tech"]


def test_extracted_entity_archetype_truncates_overlong_description():
    entity = ExtractedEntityArchetype(
        name="Camarilla",
        entity_type="organization",
        description="x" * 1500,
    )

    assert len(entity.description) == 1000
    assert entity.description == "x" * 1000


def test_parse_source_profile_handles_json_payload_and_confidence_fields():
    profile = parse_source_profile(
        """
        {
          "source_kind": "rulebook",
          "world_kind": "gothic horror",
          "system_name": "Vampire: The Masquerade",
          "edition": "20th Anniversary Edition",
          "family": "Storyteller",
          "genre_tone": ["personal horror", "political intrigue"],
          "narrative_frame": ["tragic", "investigative"],
          "lore_domains": ["factions", "morality", "metaphysics"],
          "taxonomy_containers": ["Clan", "Discipline", "Sect"],
          "institution_model": ["sect allegiance", "clan lineage"],
          "relationship_patterns": ["member_of", "subtype_of", "opposes"],
          "term_lexicon": {"embrace": ["siring"], "kindred": ["vampires"]},
          "canon_signal_terms": ["tradition", "elder", "prince"],
          "coverage_summary": "Core vampire society, clans, sects, and disciplines are well covered.",
          "known_open_questions": ["How are blood sorcery rituals organized?"],
          "confidence_by_field": {"system_name": 0.98, "taxonomy_containers": 0.94, "world_kind": 0.91},
          "evidence_refs": [
            {"ref": "Table of Contents > Clans", "section_path": "Contents > Clans", "note": "Named category family"}
          ],
          "profile_version": "1.0",
          "prompt_version": "source-profile-v1",
          "model_used": "test-model"
        }
        """
    )

    assert isinstance(profile, EmbeddedSourceProfile)
    assert profile.system_name == "Vampire: The Masquerade"
    assert "Clan" in profile.taxonomy_containers
    assert profile.confidence_by_field["taxonomy_containers"] == pytest.approx(0.94)
    assert profile.evidence_refs[0].ref == "Table of Contents > Clans"


def test_build_source_profile_seed_uses_reference_sections_for_taxonomy_and_aliases():
    sections = [
        SectionDigest(
            section_path="Book One > Politics",
            text="Princes rule domains while elders shape sect politics.",
            min_page=10,
            min_chunk_index=1,
        )
    ]
    reference_sections = [
        SectionDigest(
            section_path="Contents > Clans > Brujah",
            text="Clans .... 42\nDisciplines .... 88",
            min_page=2,
            min_chunk_index=1,
        ),
        SectionDigest(
            section_path="Glossary",
            text="Kindred: also called Cainites.\nEmbrace: also known as the siring.",
            min_page=220,
            min_chunk_index=1,
        ),
    ]

    profile = build_source_profile_seed(
        "V20 Core",
        sections,
        reference_sections,
        source_kind="rulebook",
        detected_system_name="V20",
    )

    assert profile.system_name == "V20"
    assert "Clans" in profile.taxonomy_containers or "Clan" in profile.taxonomy_containers
    assert profile.term_lexicon["Kindred"] == ["Cainites"]
    assert profile.confidence_by_field["taxonomy_containers"] >= 0.8


def test_format_source_profile_context_only_keeps_high_confidence_fields():
    profile = EmbeddedSourceProfile(
        source_kind="rulebook",
        system_name="V20",
        lore_domains=["factions", "morality"],
        taxonomy_containers=["Clan", "Discipline"],
        canon_signal_terms=["prince", "tradition"],
        confidence_by_field={
            "system_name": 0.97,
            "taxonomy_containers": 0.91,
            "lore_domains": 0.6,
            "canon_signal_terms": 0.55,
        },
    )

    profile_context = format_source_profile_context(profile)

    assert "System: V20" in profile_context
    assert "Taxonomy containers: Clan, Discipline" in profile_context
    assert "Lore domains" not in profile_context
    assert "Canon signal terms" not in profile_context


def test_batched_extraction_module_raises_max_tokens_for_large_outputs(monkeypatch):
    captured = {}

    class _DummyContext:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "monitor_agents.analyzer.analyzer.dspy_context_for",
        lambda node_name, role, max_tokens=None: (
            captured.update({"node_name": node_name, "role": role, "max_tokens": max_tokens}) or _DummyContext()
        ),
    )

    module = BatchedExtractionModule()
    module._chain = lambda **kwargs: kwargs

    result = module.forward(
        sections_context="# Section: Combat\n\nLots of combat and lore text.",
        source_name="Death in Space Core Rules",
        known_graph_context="",
        source_profile_context="",
    )

    assert result["source_name"] == "Death in Space Core Rules"
    assert captured == {
        "node_name": "analyzer",
        "role": module._role,
        "max_tokens": 16384,
    }


@pytest.mark.asyncio
async def test_analyzer_persists_source_profile_data_when_synthesis_succeeds(monkeypatch):
    analyzer = Analyzer()
    captured_update = {}
    _patch_common_analyzer_dependencies(monkeypatch, analyzer)

    section = SectionDigest(
        section_path="Book One > Clans > Brujah",
        text="The Brujah are one of the great clans of Kindred society.",
        min_page=12,
        min_chunk_index=1,
    )

    monkeypatch.setattr(
        analyzer,
        "_retrieve_sections_by_category",
        AsyncMock(return_value=[section]),
    )
    monkeypatch.setattr(
        analyzer,
        "_retrieve_reference_sections",
        AsyncMock(return_value=[section]),
    )
    monkeypatch.setattr(
        analyzer,
        "_synthesize_source_profile",
        AsyncMock(
            return_value=EmbeddedSourceProfile(
                source_kind="rulebook",
                world_kind="gothic horror",
                system_name="V20",
                taxonomy_containers=["Clan", "Discipline"],
                lore_domains=["factions", "morality"],
                confidence_by_field={"system_name": 0.97, "taxonomy_containers": 0.93},
                coverage_summary="Clans and sect politics are clearly covered.",
                prompt_version="source-profile-v1",
            )
        ),
    )

    def _capture_update(pack_id, params):
        captured_update["pack_id"] = pack_id
        captured_update["params"] = params
        return None

    monkeypatch.setattr("monitor_agents.analyzer._core.mongodb_update_knowledge_pack", _capture_update)

    await analyzer.analyze_source(
        job_id=uuid4(),
        source_name="V20 Core Rulebook",
        source_document_ids=[uuid4()],
        pack_name="V20 Core",
        pack_type=KnowledgePackType.RULEBOOK,
        analysis_layers=["axioms", "entities", "lore"],
        auto_apply=False,
    )

    params = captured_update["params"]
    assert params.source_profile_data is not None
    assert params.source_profile_data.system_name == "V20"
    assert params.source_profile_data.taxonomy_containers == ["Clan", "Discipline"]


def test_materialize_container_entities_marks_container_roles():
    analyzer = Analyzer()
    entities = [
        ExtractedEntityArchetype(
            name="Brujah",
            entity_type="character",
            sub_type="clan",
            description="A rebellious vampire lineage.",
            parent_entity_name="Clan",
            confidence=0.9,
        )
    ]

    materialized, synthesized_count = analyzer._materialize_container_entities(entities, "V20")
    by_name = {entity.name: entity for entity in materialized}

    assert synthesized_count == 1
    assert by_name["Clan"].is_container is True
    assert {"container", "taxonomy_container"}.issubset(set(by_name["Clan"].entity_roles))
    assert "taxonomy_member" in by_name["Brujah"].entity_roles


@pytest.mark.asyncio
async def test_extract_game_subsystems_returns_all_outputs_for_game_system(monkeypatch):
    analyzer = Analyzer()
    monkeypatch.setattr(analyzer, "_update_job", lambda *_args, **_kwargs: None)

    section = SectionDigest(
        section_path="Chapter 2 > Combat",
        text="Roll initiative, then take one action on your turn.",
        min_page=10,
        min_chunk_index=1,
    )
    sections = SimpleNamespace(
        content_sections=[section],
        rule_sections=[section],
        charsheet_sections=[section],
        reference_sections=[],
        npc_sections=[section],
        table_sections=[section],
        tone_sections=[section],
        character_profile_sections=[section],
        generation_template_sections=[section],
        plot_thread_sections=[section],
    )

    random_table = ExtractedRandomTable(name="Combat Complications")
    agenda = ExtractedAgenda(title="Cult Escalation", description="The cult advances its ritual.")
    topology = ExtractedTopology(from_location="Hall", to_location="Crypt")
    tone_profile = ExtractedToneProfile(
        name="Pressure",
        description="Urgent, tactical danger.",
        instruction="Keep descriptions tense and immediate.",
    )
    character_profile = ExtractedCharacterProfile(name="Cultist")
    generation_template = ExtractedGenerationTemplate(
        name="Cultist Scout",
        archetype_name="Cultist",
    )

    monkeypatch.setattr(
        analyzer,
        "_extract_game_rules",
        AsyncMock(return_value=[{"name": "Initiative", "rule_type": "action"}]),
    )
    monkeypatch.setattr(
        analyzer,
        "_extract_random_tables",
        AsyncMock(return_value=[random_table]),
    )
    monkeypatch.setattr(analyzer, "_extract_agendas", AsyncMock(return_value=[agenda]))
    monkeypatch.setattr(analyzer, "_extract_topologies", AsyncMock(return_value=[topology]))
    monkeypatch.setattr(
        analyzer,
        "_extract_tone_profiles",
        AsyncMock(return_value=[tone_profile]),
    )
    monkeypatch.setattr(
        analyzer,
        "_extract_character_profiles",
        AsyncMock(return_value=[character_profile]),
    )
    monkeypatch.setattr(
        analyzer,
        "_extract_generation_templates",
        AsyncMock(return_value=[generation_template]),
    )
    monkeypatch.setattr(
        analyzer,
        "_extract_character_sheet",
        AsyncMock(return_value={"attributes": [], "skills": [], "resources": []}),
    )
    monkeypatch.setattr(
        analyzer,
        "_extract_creation_procedure",
        AsyncMock(return_value={"steps": []}),
    )
    monkeypatch.setattr(
        analyzer,
        "_extract_npc_data",
        AsyncMock(return_value={"stat_blocks": [], "creation_rules": None}),
    )
    monkeypatch.setattr(
        analyzer,
        "_extract_plot_threads",
        AsyncMock(return_value=[]),
    )

    result = await analyzer._extract_game_subsystems(
        job_id=uuid4(),
        source_name="Test Rulebook",
        sections=sections,
        is_game_system=True,
        detected_system_name="Test System",
        include_rules=True,
        source_profile_context="",
    )

    assert len(result) == 11
    (
        game_rules,
        charsheet,
        creation,
        npc_data,
        tables,
        agendas,
        topologies,
        tone_profiles,
        character_profiles,
        generation_templates,
        plot_threads,
    ) = result
    assert game_rules == [{"name": "Initiative", "rule_type": "action"}]
    assert charsheet == {"attributes": [], "skills": [], "resources": []}
    assert creation == {"steps": []}
    assert npc_data == {"stat_blocks": [], "creation_rules": None}
    assert tables == [random_table]
    assert agendas == [agenda]
    assert topologies == [topology]
    assert tone_profiles == [tone_profile]
    assert character_profiles == [character_profile]
    assert plot_threads == []
    assert generation_templates == [generation_template]


@pytest.mark.asyncio
async def test_extract_game_subsystems_keeps_adventure_extras_without_game_system(monkeypatch):
    analyzer = Analyzer()
    monkeypatch.setattr(analyzer, "_update_job", lambda *_args, **_kwargs: None)

    section = SectionDigest(
        section_path="Dungeon > Level 1",
        text="A patrol table, a faction clock, and a tunnel to the crypt appear here.",
        min_page=6,
        min_chunk_index=2,
    )
    sections = SimpleNamespace(
        content_sections=[section],
        rule_sections=[],
        charsheet_sections=[],
        reference_sections=[],
        npc_sections=[],
        table_sections=[section],
        tone_sections=[section],
        character_profile_sections=[section],
        generation_template_sections=[section],
        plot_thread_sections=[section],
    )

    random_table = ExtractedRandomTable(name="Dungeon Patrols")
    agenda = ExtractedAgenda(title="Alarm Clock", description="The guards raise the alarm.")
    topology = ExtractedTopology(from_location="Gatehouse", to_location="Crypt")
    tone_profile = ExtractedToneProfile(
        name="Dungeon Tension",
        description="Claustrophobic exploration pressure.",
        instruction="Emphasize constrained space and mounting risk.",
    )
    character_profile = ExtractedCharacterProfile(name="Dungeon Guard")

    monkeypatch.setattr(analyzer, "_extract_game_rules", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        analyzer,
        "_extract_random_tables",
        AsyncMock(return_value=[random_table]),
    )
    monkeypatch.setattr(analyzer, "_extract_agendas", AsyncMock(return_value=[agenda]))
    monkeypatch.setattr(analyzer, "_extract_topologies", AsyncMock(return_value=[topology]))
    monkeypatch.setattr(
        analyzer,
        "_extract_tone_profiles",
        AsyncMock(return_value=[tone_profile]),
    )
    monkeypatch.setattr(
        analyzer,
        "_extract_character_profiles",
        AsyncMock(return_value=[character_profile]),
    )
    monkeypatch.setattr(analyzer, "_extract_generation_templates", AsyncMock(return_value=[]))
    monkeypatch.setattr(analyzer, "_extract_character_sheet", AsyncMock(return_value={}))
    monkeypatch.setattr(analyzer, "_extract_creation_procedure", AsyncMock(return_value={}))
    monkeypatch.setattr(
        analyzer,
        "_extract_npc_data",
        AsyncMock(return_value={"stat_blocks": [], "creation_rules": None}),
    )
    monkeypatch.setattr(
        analyzer,
        "_extract_plot_threads",
        AsyncMock(return_value=[]),
    )

    result = await analyzer._extract_game_subsystems(
        job_id=uuid4(),
        source_name="Test Adventure",
        sections=sections,
        is_game_system=False,
        detected_system_name=None,
        include_rules=True,
        source_profile_context="",
    )

    (
        game_rules,
        charsheet,
        creation,
        npc_data,
        tables,
        agendas,
        topologies,
        tone_profiles,
        character_profiles,
        generation_templates,
        plot_threads,
    ) = result
    assert game_rules == []
    assert charsheet == {}
    assert creation == {}
    assert npc_data == {}
    assert tables == [random_table]
    assert agendas == [agenda]
    assert topologies == [topology]
    assert tone_profiles == [tone_profile]
    assert character_profiles == [character_profile]
    assert generation_templates == []
    assert plot_threads == []
    analyzer._extract_game_rules.assert_not_awaited()
    analyzer._extract_character_sheet.assert_not_awaited()
    analyzer._extract_creation_procedure.assert_not_awaited()
    analyzer._extract_npc_data.assert_not_awaited()
    analyzer._extract_generation_templates.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_mindscape_persists_real_chunk_and_section_artifacts(monkeypatch):
    analyzer = Analyzer()
    analyzer._project_mindscape_to_qdrant = AsyncMock()

    sections = [
        SectionDigest(
            section_path="Chapter 1 > Iron Ring",
            text="The Iron Ring is a decaying station full of scavengers and desperate crews.",
            min_page=4,
            min_chunk_index=0,
            chunk_ids=["chunk-1", "chunk-2"],
            semantic_category="factions",
            chunk_records=[
                {
                    "chunk_id": "chunk-1",
                    "chunk_index": 0,
                    "page": 4,
                    "text": "The Iron Ring is a decaying station where scavenger crews barter for survival.",
                    "semantic_category": "factions",
                },
                {
                    "chunk_id": "chunk-2",
                    "chunk_index": 1,
                    "page": 5,
                    "text": "Its corridors are ruled by desperate crews, black markets, and omens of the Void.",
                    "semantic_category": "factions",
                },
            ],
        )
    ]

    async def fake_call_module(_module, **kwargs):
        stage = kwargs.get("stage")
        if stage == "section_summary":
            return SimpleNamespace(summary="Summarizes the Iron Ring and its scavenger factions.", themes=["scarcity"])
        if stage == "mindscape_synthesis":
            return SimpleNamespace(
                global_summary="A bleak sci-fi sourcebook about survival among desperate scavengers.",
                themes=["resource scarcity", "cosmic dread"],
                taxonomy_hints=["Crew", "Void"],
                system_name="Death in Space",
            )
        raise AssertionError(f"Unexpected stage: {stage}")

    captured = {}

    def fake_persist(*, pack_id, chunk_summaries, section_summaries, mindscape, mongo_client=None):
        captured["pack_id"] = pack_id
        captured["chunk_summaries"] = chunk_summaries
        captured["section_summaries"] = section_summaries
        captured["mindscape"] = mindscape

    monkeypatch.setattr(analyzer, "_call_module", fake_call_module)
    monkeypatch.setattr("monitor_agents.analyzer._core.persist_mindscape_artifacts", fake_persist)

    mindscape = await analyzer.synthesize_mindscape(
        sections=sections,
        source_name="Death in Space Core Rules",
        pack_id=uuid4(),
    )

    assert mindscape.system_name == "Death in Space"
    assert len(captured["chunk_summaries"]) == 2
    assert captured["chunk_summaries"][0].chunk_id == "chunk-1"
    assert captured["section_summaries"][0].chunk_ids == ["chunk-1", "chunk-2"]
    analyzer._project_mindscape_to_qdrant.assert_awaited_once()


@pytest.mark.asyncio
async def test_project_mindscape_to_qdrant_updates_payloads_and_upserts_summary_vectors(
    monkeypatch,
):
    analyzer = Analyzer()

    fake_qdrant = MagicMock()
    fake_qdrant.set_payload = AsyncMock()
    fake_qdrant.upsert = AsyncMock()

    fake_client = MagicMock()
    fake_client.ensure_collection = AsyncMock()
    fake_client.get_client.return_value = fake_qdrant

    monkeypatch.setattr("monitor_agents.analyzer._mindscape_projection.get_qdrant_client", lambda: fake_client)
    # Embeddings route through the RetrievalService now — stub its embed_docs.
    fake_retriever = MagicMock()
    fake_retriever.embed_docs = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
    monkeypatch.setattr("monitor_data.retrieval.default_retrieval_service", lambda: fake_retriever)

    await analyzer._project_mindscape_to_qdrant(
        source_name="Death in Space Core Rules",
        chunk_summaries=[
            SimpleNamespace(
                chunk_id="chunk-1",
                chunk_index=0,
                summary="Scavenger crews barter for survival aboard the Iron Ring.",
                source_ref="Chapter 1 > Iron Ring (p. 4)",
                tags=["factions"],
                confidence=0.72,
            )
        ],
        section_summaries=[
            SimpleNamespace(
                section_key="chapter_1_iron_ring",
                heading_path=["Chapter 1", "Iron Ring"],
                chunk_ids=["chunk-1"],
                summary="Describes the station's scavenger economy and political pressure.",
                semantic_category="factions",
                confidence=0.8,
            )
        ],
        mindscape=SimpleNamespace(
            summary="Bleak sci-fi survival in a dying galaxy.",
            themes=["resource scarcity"],
            taxonomy_hints=["Crew", "Void"],
            system_name="Death in Space",
            confidence=0.85,
        ),
    )

    fake_qdrant.set_payload.assert_awaited_once()
    payload_patch = fake_qdrant.set_payload.await_args.kwargs["payload"]
    assert payload_patch["chunk_summary"].startswith("Scavenger crews")
    assert payload_patch["source_system_name"] == "Death in Space"

    fake_qdrant.upsert.assert_awaited_once()
    points = fake_qdrant.upsert.await_args.kwargs["points"]
    assert len(points) == 3
    assert {point.payload["artifact_type"] for point in points} == {
        "chunk_summary",
        "section_summary",
        "source_mindscape",
    }


def test_materialize_social_entities_adds_membership_and_multi_role_support():
    analyzer = Analyzer()
    entities = [
        ExtractedEntityArchetype(
            name="House Tremere",
            entity_type="organization",
            sub_type="clan",
            description="A blood-magic house that is both a lineage and a political order.",
            parent_entity_name="Clan",
            properties={"sect": "Camarilla"},
            confidence=0.88,
        )
    ]

    enriched_entities, inferred_relationships, synthesized_count = (
        analyzer._materialize_social_entities_and_relationships(
            entities,
            "V20",
        )
    )
    by_name = {entity.name: entity for entity in enriched_entities}

    assert synthesized_count == 1
    assert "Camarilla" in by_name
    assert {"organization", "taxonomy_member", "multi_role"}.issubset(set(by_name["House Tremere"].entity_roles))
    assert any(
        rel.from_entity == "House Tremere" and rel.rel_type == "member_of" and rel.to_entity == "Camarilla"
        for rel in inferred_relationships
    )


@pytest.mark.asyncio
async def test_analyzer_reads_ingested_chunks_from_snippets(monkeypatch):
    analyzer = Analyzer()
    searched_collections = []
    _patch_common_analyzer_dependencies(monkeypatch, analyzer)

    # Query embedding routes through the RetrievalService now.
    fake_retriever = MagicMock()
    fake_retriever.embed_query = AsyncMock(return_value=[0.1] * 1536)
    monkeypatch.setattr("monitor_data.retrieval.default_retrieval_service", lambda: fake_retriever)

    class FakeQdrant:
        async def search(self, *, collection_name, **_kwargs):
            searched_collections.append(collection_name)
            return [
                SimpleNamespace(
                    id=str(uuid4()),
                    payload={"text": "Roll 1d20 and add your stat."},
                    score=0.91,
                )
            ]

    class FakeClient:
        async def ensure_collection(self, _collection):
            return None

        def get_client(self):
            return FakeQdrant()

    def fake_get_qdrant_client():
        return FakeClient()

    monkeypatch.setattr("monitor_agents.analyzer._core.get_qdrant_client", fake_get_qdrant_client)

    await analyzer.analyze_source(
        job_id=uuid4(),
        source_name="Death In Space Core Rules",
        source_document_ids=[uuid4()],
        pack_name="Death in Space",
        pack_type=KnowledgePackType.RULEBOOK,
        analysis_layers=["axioms", "entities", "lore", "game_system", "rules"],
        auto_apply=False,
    )

    assert searched_collections
    assert set(searched_collections) == {"snippets"}


@pytest.mark.asyncio
async def test_analyzer_uses_http_search_fallback_when_search_method_is_missing(monkeypatch):
    analyzer = Analyzer()
    searched_collections = []
    _patch_common_analyzer_dependencies(monkeypatch, analyzer)

    # Query embedding routes through the RetrievalService now.
    fake_retriever = MagicMock()
    fake_retriever.embed_query = AsyncMock(return_value=[0.1] * 1536)
    monkeypatch.setattr("monitor_data.retrieval.default_retrieval_service", lambda: fake_retriever)

    class FakeSearchApi:
        async def search_points(self, *, collection_name, search_request):
            searched_collections.append(collection_name)
            assert search_request.limit > 0
            return SimpleNamespace(
                result=[
                    SimpleNamespace(
                        id=str(uuid4()),
                        payload={"text": "Roll 1d20 and add your stat."},
                        score=0.88,
                    )
                ]
            )

    class FakeQdrant:
        def __init__(self):
            self.http = SimpleNamespace(search_api=FakeSearchApi())

    class FakeClient:
        async def ensure_collection(self, _collection):
            return None

        def get_client(self):
            return FakeQdrant()

    def fake_get_qdrant_client():
        return FakeClient()

    monkeypatch.setattr("monitor_agents.analyzer._core.get_qdrant_client", fake_get_qdrant_client)

    await analyzer.analyze_source(
        job_id=uuid4(),
        source_name="Death In Space Core Rules",
        source_document_ids=[uuid4()],
        pack_name="Death in Space",
        pack_type=KnowledgePackType.RULEBOOK,
        analysis_layers=["axioms", "entities", "lore", "game_system", "rules"],
        auto_apply=False,
    )

    assert searched_collections
    assert set(searched_collections) == {"snippets"}
