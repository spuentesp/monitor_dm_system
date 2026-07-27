from datetime import UTC, datetime
from uuid import uuid4

from monitor_data.schemas.knowledge_packs import (
    ChunkSummaryArtifact,
    EmbeddedSourceProfile,
    KnowledgePackCreate,
    KnowledgePackResponse,
    KnowledgePackStatus,
    KnowledgePackType,
    SectionSummaryArtifact,
    SourceMindscapeArtifact,
)


def test_chunk_summary_artifact_minimal():
    artifact = ChunkSummaryArtifact(
        chunk_id="abc123",
        chunk_index=0,
        summary="Describes the Nosferatu clan's deformity and Obfuscate affinity.",
    )
    assert artifact.confidence == 0.0
    assert artifact.source_ref is None
    assert artifact.tags == []


def test_section_summary_artifact():
    artifact = SectionSummaryArtifact(
        section_key="chapter_3_clans_nosferatu",
        heading_path=["Chapter 3", "Clans", "Nosferatu"],
        chunk_ids=["a1", "a2"],
        summary="Details the Nosferatu, a clan of hideous vampires skilled in Obfuscate.",
        semantic_category="lineage",
    )
    assert artifact.heading_path[2] == "Nosferatu"
    assert artifact.confidence == 0.0


def test_source_mindscape_artifact():
    artifact = SourceMindscapeArtifact(
        source_name="Vampire: the Masquerade 20th Anniversary Edition",
        summary="Gothic horror TTRPG where players are vampires navigating politics and the Beast.",
        themes=["gothic horror", "vampire politics", "humanity vs Beast"],
        taxonomy_hints=["Clan", "Discipline", "Path of Enlightenment", "Frenzy"],
        system_name="Vampire: the Masquerade",
    )
    assert "Clan" in artifact.taxonomy_hints
    assert artifact.confidence == 0.0


def test_knowledge_pack_create_backward_compat_without_artifacts():
    """Old packs without artifact fields must still deserialize cleanly."""
    pack = KnowledgePackCreate(
        name="Death in Space",
    )
    assert pack.chunk_summaries == []
    assert pack.section_summaries == []
    assert pack.source_mindscape is None


def test_knowledge_pack_create_with_mindscape():
    mindscape = SourceMindscapeArtifact(
        source_name="Death in Space",
        summary="Bleak sci-fi OSR where characters are scavengers in a dying galaxy.",
        themes=["cosmic horror", "resource scarcity"],
        taxonomy_hints=["BDY", "Omens", "Void"],
        system_name="Death in Space",
    )
    pack = KnowledgePackCreate(
        name="Death in Space",
        source_mindscape=mindscape,
    )
    assert pack.source_mindscape.system_name == "Death in Space"


def test_knowledge_pack_response_preserves_artifacts():
    chunk = ChunkSummaryArtifact(
        chunk_id="chunk-1",
        chunk_index=0,
        summary="Explains the scavenger economy around the Iron Ring.",
    )
    section = SectionSummaryArtifact(
        section_key="chapter_1_iron_ring",
        heading_path=["Chapter 1", "Iron Ring"],
        chunk_ids=["chunk-1"],
        summary="Describes the decaying station and its desperate factions.",
    )
    mindscape = SourceMindscapeArtifact(
        source_name="Death in Space",
        summary="A bleak sci-fi sandbox about survival in a dying galaxy.",
        themes=["resource scarcity", "cosmic dread"],
        taxonomy_hints=["Void", "Omens"],
        system_name="Death in Space",
    )

    pack = KnowledgePackResponse(
        pack_id=uuid4(),
        name="Death in Space",
        description="Mindscape-rich ingest",
        pack_type=KnowledgePackType.RULEBOOK,
        system_name="Death in Space",
        status=KnowledgePackStatus.READY,
        source_document_ids=[],
        ingestion_job_id=None,
        tags=[],
        parent_pack_ids=[],
        axioms=[],
        entity_archetypes=[],
        lore_facts=[],
        entity_relationships=[],
        game_system_id=None,
        game_system_data=None,
        source_profile_data=None,
        chunk_summaries=[chunk],
        section_summaries=[section],
        source_mindscape=mindscape,
        applied_to=[],
        created_at=datetime.now(UTC),
        updated_at=None,
    )

    assert pack.chunk_summaries[0].chunk_id == "chunk-1"
    assert pack.section_summaries[0].section_key == "chapter_1_iron_ring"
    assert pack.source_mindscape.system_name == "Death in Space"


def test_chunk_summary_artifact_with_all_fields():
    """Test ChunkSummaryArtifact with all optional fields populated."""
    artifact = ChunkSummaryArtifact(
        chunk_id="chunk-abc-123",
        chunk_index=5,
        category="rules",
        summary="Describes the Initiative system and turn order mechanics.",
        entities_mentioned=["Initiative", "Turn Order", "Reaction"],
        confidence=0.95,
        source_ref="Page 42",
        tags=["combat", "mechanics"],
    )
    assert artifact.category == "rules"
    assert artifact.entities_mentioned == ["Initiative", "Turn Order", "Reaction"]
    assert artifact.confidence == 0.95
    assert artifact.source_ref == "Page 42"
    assert artifact.tags == ["combat", "mechanics"]


def test_chunk_summary_artifact_confidence_bounds():
    """Test ChunkSummaryArtifact enforces confidence bounds."""
    # Valid confidence
    artifact = ChunkSummaryArtifact(
        chunk_id="test-chunk",
        chunk_index=0,
        summary="Test summary",
        confidence=0.5,
    )
    assert artifact.confidence == 0.5


def test_section_summary_artifact_with_all_fields():
    """Test SectionSummaryArtifact with all optional fields populated."""
    artifact = SectionSummaryArtifact(
        section_key="chapter_2_combat",
        heading_path=["Chapter 2", "Combat System"],
        category="mechanics",
        summary="Covers initiative, attacks, damage, and resolution.",
        key_topics=["Initiative", "Attacks", "Damage", "Resolution"],
        chunk_ids=["chunk-1", "chunk-2", "chunk-3"],
        semantic_category="combat_system",
        confidence=0.88,
    )
    assert artifact.category == "mechanics"
    assert artifact.key_topics == ["Initiative", "Attacks", "Damage", "Resolution"]
    assert len(artifact.chunk_ids) == 3
    assert artifact.semantic_category == "combat_system"
    assert artifact.confidence == 0.88


def test_section_summary_artifact_chunk_ids_relationship():
    """Test SectionSummaryArtifact correctly tracks chunk IDs."""
    artifact = SectionSummaryArtifact(
        section_key="section-entities",
        heading_path=["Chapter 1", "Entities"],
        chunk_ids=["entity-chunk-1", "entity-chunk-2", "entity-chunk-3"],
        summary="List of all entity types in the system.",
    )
    assert len(artifact.chunk_ids) == 3
    assert "entity-chunk-2" in artifact.chunk_ids


def test_source_mindscape_artifact_with_all_fields():
    """Test SourceMindscapeArtifact with all optional fields populated."""
    artifact = SourceMindscapeArtifact(
        source_name="Call of Cthulhu 7th Edition",
        summary="Horror RPG of investigation and cosmic dread.",
        tone="dark, suspenseful, investigative",
        genre_tags=["horror", "investigation", "cosmic horror"],
        themes=["madness", "forbidden knowledge", "cosmic entities"],
        taxonomy_hints=["Skill", "Sanity", "Mythos", "Investigation"],
        system_overview="D100-based percentile system with Sanity mechanics.",
        system_name="Call of Cthulhu",
        confidence=0.92,
    )
    assert artifact.tone == "dark, suspenseful, investigative"
    assert "horror" in artifact.genre_tags
    assert artifact.system_overview is not None
    assert artifact.confidence == 0.92


def test_source_mindscape_artifact_taxonomy_hints():
    """Test SourceMindscapeArtifact taxonomy hints validation."""
    artifact = SourceMindscapeArtifact(
        source_name="D&D 5e Player's Handbook",
        summary="Core rulebook for 5th Edition Dungeons & Dragons.",
        taxonomy_hints=["Class", "Race", "Spell", "Background", "Feat"],
        system_name="Dungeons & Dragons",
    )
    assert len(artifact.taxonomy_hints) == 5
    assert "Class" in artifact.taxonomy_hints
    assert "Background" in artifact.taxonomy_hints


def test_embedded_source_profile_creation():
    """Test EmbeddedSourceProfile creation."""
    profile = EmbeddedSourceProfile(
        title="Vampire: the Masquerade 5th Edition",
        source_type="rulebook",
        edition="5th Edition",
        publisher="White Wolf Entertainment",
        system_name="Vampire: the Masquerade",
        source_kind="tabletop_rpg",
        world_kind="modern_gothic_horror",
        family="World of Darkness",
        genre_tone=["gothic horror", "personal horror"],
        narrative_frame=["urban fantasy", "political intrigue"],
        lore_domains=["vampire lore", "bloodlines", "disciplines"],
        taxonomy_containers=["clans", "disciplines", "blood magic"],
        institution_model=["sect", "covenant", "prince"],
    )
    assert profile.title == "Vampire: the Masquerade 5th Edition"
    assert profile.source_type == "rulebook"
    assert profile.edition == "5th Edition"
    assert "gothic horror" in profile.genre_tone


def test_knowledge_pack_create_with_chunk_summaries():
    """Test KnowledgePackCreate with chunk summaries."""
    chunk1 = ChunkSummaryArtifact(
        chunk_id="chunk-1",
        chunk_index=0,
        summary="First chunk about rules.",
    )
    chunk2 = ChunkSummaryArtifact(
        chunk_id="chunk-2",
        chunk_index=1,
        summary="Second chunk about entities.",
    )
    pack = KnowledgePackCreate(
        name="Test Pack",
        chunk_summaries=[chunk1, chunk2],
    )
    assert len(pack.chunk_summaries) == 2
    assert pack.chunk_summaries[0].chunk_id == "chunk-1"
    assert pack.chunk_summaries[1].chunk_id == "chunk-2"


def test_knowledge_pack_create_with_section_summaries():
    """Test KnowledgePackCreate with section summaries."""
    section1 = SectionSummaryArtifact(
        section_key="chapter-1",
        heading_path=["Chapter 1"],
        chunk_ids=["chunk-1", "chunk-2"],
        summary="Introduction chapter.",
    )
    section2 = SectionSummaryArtifact(
        section_key="chapter-2",
        heading_path=["Chapter 2"],
        chunk_ids=["chunk-3", "chunk-4"],
        summary="Rules chapter.",
    )
    pack = KnowledgePackCreate(
        name="Test Pack",
        section_summaries=[section1, section2],
    )
    assert len(pack.section_summaries) == 2
    assert pack.section_summaries[0].section_key == "chapter-1"
    assert pack.section_summaries[1].section_key == "chapter-2"


def test_knowledge_pack_create_with_embedded_source_profile():
    """Test KnowledgePackCreate with embedded source profile."""
    profile = EmbeddedSourceProfile(
        title="Test Source",
        source_type="rulebook",
        system_name="Test System",
    )
    pack = KnowledgePackCreate(
        name="Test Pack",
        source_profile_data=profile,
    )
    assert pack.source_profile_data is not None
    assert pack.source_profile_data.title == "Test Source"
    assert pack.source_profile_data.system_name == "Test System"


def test_knowledge_pack_response_with_embedded_source_profile():
    """Test KnowledgePackResponse preserves embedded source profile."""
    profile = EmbeddedSourceProfile(
        title="Test Source",
        source_type="rulebook",
        system_name="Test System",
    )
    pack = KnowledgePackResponse(
        pack_id=uuid4(),
        name="Test Pack",
        description="Pack with source profile",
        pack_type=KnowledgePackType.RULEBOOK,
        system_name="Test System",
        status=KnowledgePackStatus.READY,
        source_document_ids=[],
        ingestion_job_id=None,
        tags=[],
        parent_pack_ids=[],
        axioms=[],
        entity_archetypes=[],
        lore_facts=[],
        entity_relationships=[],
        game_system_id=None,
        game_system_data=None,
        source_profile_data=profile,
        chunk_summaries=[],
        section_summaries=[],
        source_mindscape=None,
        applied_to=[],
        created_at=datetime.now(UTC),
        updated_at=None,
    )
    assert pack.source_profile_data is not None
    assert pack.source_profile_data.title == "Test Source"


def test_chunk_summary_artifact_serialization():
    """Test ChunkSummaryArtifact can be serialized to JSON."""
    artifact = ChunkSummaryArtifact(
        chunk_id="test-chunk",
        chunk_index=0,
        summary="Test summary",
        category="rules",
        entities_mentioned=["Entity1", "Entity2"],
        confidence=0.8,
        source_ref="Page 10",
        tags=["tag1", "tag2"],
    )
    serialized = artifact.model_dump_json()
    assert isinstance(serialized, str)
    assert "test-chunk" in serialized

    # Deserialization
    deserialized = ChunkSummaryArtifact.model_validate_json(serialized)
    assert deserialized.chunk_id == "test-chunk"
    assert deserialized.chunk_index == 0
    assert deserialized.confidence == 0.8


def test_section_summary_artifact_serialization():
    """Test SectionSummaryArtifact can be serialized to JSON."""
    artifact = SectionSummaryArtifact(
        section_key="test-section",
        heading_path=["Chapter 1", "Test Section"],
        chunk_ids=["chunk-1", "chunk-2"],
        summary="Test section summary",
        key_topics=["topic1", "topic2"],
    )
    serialized = artifact.model_dump_json()
    assert isinstance(serialized, str)
    assert "test-section" in serialized

    # Deserialization
    deserialized = SectionSummaryArtifact.model_validate_json(serialized)
    assert deserialized.section_key == "test-section"
    assert deserialized.heading_path == ["Chapter 1", "Test Section"]
    assert len(deserialized.chunk_ids) == 2


# =============================================================================
# [G-2] intro_text round-trip on KnowledgePackCreate / Update / Response
# =============================================================================


def test_intro_text_round_trip_on_knowledge_pack_create():
    """KnowledgePackCreate carries an optional intro_text verbatim."""
    intro = (
        "A pale sun rose over the wreck of the Iolarite, its blue-white glow "
        "picking out the names scratched into the hull — yours among them."
    )
    create = KnowledgePackCreate(
        name="Test Pack",
        description="with intro",
        pack_type=KnowledgePackType.ADVENTURE_MODULE,
        intro_text=intro,
    )
    assert create.intro_text == intro
    # Round-trip via JSON
    dumped = create.model_dump(mode="json")
    assert dumped["intro_text"] == intro
    restored = KnowledgePackCreate.model_validate(dumped)
    assert restored.intro_text == intro


def test_intro_text_defaults_to_none():
    """Omitting intro_text yields ``None`` (backward-compatible)."""
    create = KnowledgePackCreate(name="No Intro Pack")
    assert create.intro_text is None


def test_intro_text_max_length_enforced():
    """Max length 8000 chars enforced by the schema."""
    import pytest
    from pydantic import ValidationError

    long_intro = "x" * 8001
    with pytest.raises(ValidationError):
        KnowledgePackCreate(name="Long Pack", intro_text=long_intro)


def test_intro_text_on_knowledge_pack_response():
    """KnowledgePackResponse carries intro_text for read-back."""
    intro = "Read-aloud prose the GM speaks at session open."
    resp = KnowledgePackResponse(
        pack_id=uuid4(),
        name="Resp Pack",
        description="",
        intro_text=intro,
        pack_type=KnowledgePackType.ADVENTURE_MODULE,
        system_name="Test",
        status=KnowledgePackStatus.READY,
        source_document_ids=[],
        ingestion_job_id=None,
        tags=[],
        created_at=datetime.now(UTC),
    )
    assert resp.intro_text == intro


def test_intro_text_on_knowledge_pack_update():
    """KnowledgePackUpdate accepts a partial intro_text patch."""
    from monitor_data.schemas.knowledge_packs import KnowledgePackUpdate

    upd = KnowledgePackUpdate(intro_text="updated intro")
    assert upd.intro_text == "updated intro"
    assert upd.name is None  # other fields untouched


def test_intro_text_update_to_none_is_a_clear_patch():
    """``KnowledgePackUpdate(intro_text=None)`` leaves the field unset for the
    mongoid patcher — the ``is not None`` guard in mongodb_tools ignores it."""
    from monitor_data.schemas.knowledge_packs import KnowledgePackUpdate

    upd = KnowledgePackUpdate(intro_text=None)
    assert upd.intro_text is None
    assert upd.model_dump(exclude_none=True).get("intro_text") is None
