"""Tests for analyzer_support.py — hierarchy derivation, social inference, cycle detection.

Covers multiple game systems to verify the code is not VtM-biased:
  - Vampire: The Masquerade (clan → discipline → power)
  - D&D 5e (class → subclass → feature, spell → school)
  - Lancer (frame → license, mech_system)
  - Monster of the Week / PbtA (playbook → move)
  - Death in Space (ship → module, crew)
  - 7th Sea (dueling_school → maneuver, advantage)
"""

from __future__ import annotations

from monitor_data.schemas.knowledge_packs import (
    ExtractedEntityArchetype,
    SourceMindscapeArtifact,
)

from monitor_agents.utils.analyzer_support import (
    build_section_summary_inputs,
    derive_hierarchy_relationships,
    format_mindscape_context,
    infer_social_entity_identity,
    merge_entity_archetypes,
    persist_mindscape_artifacts,
)


def _ent(
    name: str,
    entity_type: str = "concept",
    sub_type: str = "none",
    parent: str | None = None,
    **kwargs,
) -> ExtractedEntityArchetype:
    return ExtractedEntityArchetype(
        name=name,
        entity_type=entity_type,
        sub_type=sub_type,
        description=kwargs.get("description", f"Test entity {name}"),
        confidence=0.9,
        source_ref="test",
        parent_entity_name=parent,
        **{k: v for k, v in kwargs.items() if k != "description"},
    )


# ── VtM hierarchy ──────────────────────────────────────────────────────────


class TestVtMHierarchy:
    def test_discipline_to_power_uses_subtype_and_part_of(self):
        entities = [
            _ent("Discipline", entity_type="concept"),
            _ent("Animalism", entity_type="concept", sub_type="discipline", parent="Discipline"),
            _ent(
                "Feral Whispers",
                entity_type="concept",
                sub_type="discipline_power",
                parent="Animalism",
            ),
            _ent("Beckoning", entity_type="concept", sub_type="discipline_power", parent="Animalism"),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Animalism", "subtype_of", "Discipline") in rel_map
        assert ("Feral Whispers", "part_of", "Animalism") in rel_map
        assert ("Beckoning", "part_of", "Animalism") in rel_map

    def test_clan_hierarchy(self):
        entities = [
            _ent("Clan", entity_type="concept"),
            _ent("Nosferatu", entity_type="character", sub_type="clan", parent="Clan"),
            _ent("Gangrel", entity_type="character", sub_type="clan", parent="Clan"),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Nosferatu", "subtype_of", "Clan") in rel_map
        assert ("Gangrel", "subtype_of", "Clan") in rel_map


# ── D&D 5e hierarchy ──────────────────────────────────────────────────────


class TestDnDHierarchy:
    def test_class_to_subclass_to_feature(self):
        entities = [
            _ent("Class", entity_type="concept"),
            _ent("Fighter", entity_type="character", sub_type="class", parent="Class"),
            _ent("Champion", entity_type="character", sub_type="subclass", parent="Fighter"),
            _ent(
                "Improved Critical",
                entity_type="concept",
                sub_type="class_feature",
                parent="Champion",
            ),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Fighter", "subtype_of", "Class") in rel_map
        assert ("Champion", "subtype_of", "Fighter") in rel_map
        assert ("Improved Critical", "part_of", "Champion") in rel_map

    def test_spell_school_hierarchy(self):
        entities = [
            _ent("Spell School", entity_type="concept"),
            _ent("Evocation", entity_type="concept", sub_type="spell_school", parent="Spell School"),
            _ent("Fireball", entity_type="concept", sub_type="spell", parent="Evocation"),
            _ent("Lightning Bolt", entity_type="concept", sub_type="spell", parent="Evocation"),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Evocation", "subtype_of", "Spell School") in rel_map
        assert ("Fireball", "part_of", "Evocation") in rel_map
        assert ("Lightning Bolt", "part_of", "Evocation") in rel_map

    def test_feat_variants(self):
        entities = [
            _ent("Feat", entity_type="concept"),
            _ent("Great Weapon Master", entity_type="concept", sub_type="feat", parent="Feat"),
            _ent(
                "GWM Cleave",
                entity_type="concept",
                sub_type="feat_variant",
                parent="Great Weapon Master",
            ),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Great Weapon Master", "subtype_of", "Feat") in rel_map
        assert ("GWM Cleave", "part_of", "Great Weapon Master") in rel_map


# ── Lancer hierarchy ──────────────────────────────────────────────────────


class TestLancerHierarchy:
    def test_frame_and_license(self):
        entities = [
            _ent("Frame", entity_type="object"),
            _ent("Everest", entity_type="object", sub_type="frame", parent="Frame"),
            _ent("Blackbeard", entity_type="object", sub_type="frame", parent="Frame"),
            _ent(
                "IPS-N Blackbeard License",
                entity_type="concept",
                sub_type="license",
                parent="Blackbeard",
            ),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Everest", "subtype_of", "Frame") in rel_map
        assert ("Blackbeard", "subtype_of", "Frame") in rel_map
        assert ("IPS-N Blackbeard License", "subtype_of", "Blackbeard") in rel_map

    def test_mech_systems_are_part_of(self):
        entities = [
            _ent("Blackbeard", entity_type="object", sub_type="frame"),
            _ent("Chain Axe", entity_type="object", sub_type="mech_weapon", parent="Blackbeard"),
            _ent(
                "Reinforced Grapple",
                entity_type="object",
                sub_type="mech_system",
                parent="Blackbeard",
            ),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Chain Axe", "part_of", "Blackbeard") in rel_map
        assert ("Reinforced Grapple", "part_of", "Blackbeard") in rel_map

    def test_talent_ranks_are_part_of(self):
        entities = [
            _ent("Talent", entity_type="concept"),
            _ent("Ace", entity_type="concept", sub_type="talent", parent="Talent"),
            _ent("Ace Rank 1", entity_type="concept", sub_type="talent_rank", parent="Ace"),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Ace", "subtype_of", "Talent") in rel_map
        assert ("Ace Rank 1", "part_of", "Ace") in rel_map


# ── Monster of the Week / PbtA hierarchy ──────────────────────────────────


class TestPbtAHierarchy:
    def test_playbook_and_moves(self):
        entities = [
            _ent("Playbook", entity_type="concept"),
            _ent("The Chosen", entity_type="character", sub_type="playbook", parent="Playbook"),
            _ent("The Spooky", entity_type="character", sub_type="playbook", parent="Playbook"),
            _ent(
                "Destiny's Plaything",
                entity_type="concept",
                sub_type="playbook_move",
                parent="The Chosen",
            ),
            _ent(
                "The Big Entrance",
                entity_type="concept",
                sub_type="playbook_move",
                parent="The Chosen",
            ),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("The Chosen", "subtype_of", "Playbook") in rel_map
        assert ("The Spooky", "subtype_of", "Playbook") in rel_map
        assert ("Destiny's Plaything", "part_of", "The Chosen") in rel_map
        assert ("The Big Entrance", "part_of", "The Chosen") in rel_map

    def test_basic_moves(self):
        entities = [
            _ent("Basic Move", entity_type="concept"),
            _ent(
                "Act Under Pressure",
                entity_type="concept",
                sub_type="basic_move",
                parent="Basic Move",
            ),
            _ent("Kick Some Ass", entity_type="concept", sub_type="basic_move", parent="Basic Move"),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Act Under Pressure", "part_of", "Basic Move") in rel_map
        assert ("Kick Some Ass", "part_of", "Basic Move") in rel_map


# ── Death in Space hierarchy ──────────────────────────────────────────────


class TestDeathInSpaceHierarchy:
    def test_ship_modules(self):
        entities = [
            _ent("Ship", entity_type="object"),
            _ent("Cargo Hauler", entity_type="object", sub_type="ship", parent="Ship"),
            _ent("Void Drive", entity_type="object", sub_type="ship_module", parent="Cargo Hauler"),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Cargo Hauler", "subtype_of", "Ship") in rel_map
        assert ("Void Drive", "part_of", "Cargo Hauler") in rel_map

    def test_void_abilities(self):
        entities = [
            _ent("Void Corruption", entity_type="concept"),
            _ent(
                "Gravity Pulse",
                entity_type="concept",
                sub_type="void_ability",
                parent="Void Corruption",
            ),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Gravity Pulse", "part_of", "Void Corruption") in rel_map


# ── 7th Sea hierarchy ────────────────────────────────────────────────────


class TestSeventhSeaHierarchy:
    def test_dueling_schools_and_maneuvers(self):
        entities = [
            _ent("Dueling School", entity_type="concept"),
            _ent(
                "Aldana Style",
                entity_type="concept",
                sub_type="dueling_school",
                parent="Dueling School",
            ),
            _ent("Rompere", entity_type="concept", sub_type="dueling_maneuver", parent="Aldana Style"),
            _ent("Feint", entity_type="concept", sub_type="maneuver", parent="Aldana Style"),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Aldana Style", "subtype_of", "Dueling School") in rel_map
        assert ("Rompere", "part_of", "Aldana Style") in rel_map
        assert ("Feint", "part_of", "Aldana Style") in rel_map

    def test_sorcery_effects(self):
        entities = [
            _ent("Sorcery", entity_type="concept"),
            _ent("Porté", entity_type="concept", sub_type="sorcery", parent="Sorcery"),
            _ent("Blooding", entity_type="concept", sub_type="sorcery_effect", parent="Porté"),
        ]
        rels = derive_hierarchy_relationships(entities)
        rel_map = {(r.from_entity, r.rel_type, r.to_entity) for r in rels}
        assert ("Porté", "subtype_of", "Sorcery") in rel_map
        assert ("Blooding", "part_of", "Porté") in rel_map


# ── Cycle detection (game-agnostic) ──────────────────────────────────────


class TestCycleDetection:
    def test_self_loop_cleared(self):
        entities = [_ent("Magic", parent="Magic")]
        rels = derive_hierarchy_relationships(entities)
        assert len(rels) == 0
        assert entities[0].parent_entity_name is None

    def test_two_node_cycle_broken(self):
        entities = [
            _ent("Pilot", parent="Character"),
            _ent("Character", parent="Pilot"),
        ]
        rels = derive_hierarchy_relationships(entities)
        # One direction should survive, the other broken
        assert len(rels) == 1

    def test_deep_cycle_broken(self):
        entities = [
            _ent("A", parent="B"),
            _ent("B", parent="C"),
            _ent("C", parent="A"),
        ]
        rels = derive_hierarchy_relationships(entities)
        # At least one link must be broken to resolve cycle
        assert len(rels) <= 2


# ── Social entity identity inference (game-agnostic) ──────────────────────


class TestInferSocialEntityIdentity:
    def test_faction_keyword(self):
        assert infer_social_entity_identity("The Rebels", "faction") == ("faction", "faction")

    def test_sect_keyword(self):
        assert infer_social_entity_identity("Dark Council", "sect") == ("faction", "sect")

    def test_guild_keyword(self):
        assert infer_social_entity_identity("Thieves", "guild") == ("organization", "guild")

    def test_corp_keyword(self):
        """Lancer: IPS-N, Harrison Armory should be inferred as organizations."""
        assert infer_social_entity_identity("IPS-N", "corp") == ("organization", "corp")
        assert infer_social_entity_identity("Harrison Armory", "corporation") == (
            "organization",
            "corporation",
        )

    def test_crew_keyword(self):
        """Death in Space: crew should be organization."""
        assert infer_social_entity_identity("Salvage Crew", "crew") == ("organization", "crew")

    def test_generic_member_of(self):
        assert infer_social_entity_identity("Some Group", "member_of") == (
            "organization",
            "institution",
        )

    def test_coalition_token_maps_to_faction(self):
        assert infer_social_entity_identity("The Coalition", "coalition")[0] == "faction"

    def test_no_hardcoded_game_names(self):
        """Verify no VtM-specific names leak through — detection should be keyword-based."""
        # These should be handled purely by generic keywords, not hardcoded names
        et1, _ = infer_social_entity_identity("Camarilla", "member_of")
        et2, _ = infer_social_entity_identity("Sabbat", "member_of")
        # Both end up as organization/institution since the relation_key is member_of
        # NOT faction — the old code had hardcoded "camarilla"/"sabbat" checks
        assert et1 == "organization"
        assert et2 == "organization"


# ── Merge is alias-aware and game-agnostic ────────────────────────────────


class TestMergeMultiSystem:
    def test_merge_keeps_parent(self):
        entities = [
            _ent("Fireball", sub_type="spell", parent="Evocation"),
            _ent("Fireball", sub_type="spell", description="Hurls a ball of fire"),
        ]
        merged = merge_entity_archetypes(entities)
        fb = next(e for e in merged if e.name == "Fireball")
        assert fb.parent_entity_name == "Evocation"

    def test_merge_deduplicates_across_batches(self):
        entities = [
            _ent("Everest", entity_type="object", sub_type="frame", parent="Frame"),
            _ent("Everest", entity_type="object", sub_type="frame", description="GMS standard mech"),
        ]
        merged = merge_entity_archetypes(entities)
        assert sum(1 for e in merged if e.name == "Everest") == 1


# ── Mindscape synthesis helpers ────────────────────────────────────────────


def test_build_section_summary_inputs_returns_list_of_dicts():
    sections = [
        {
            "heading_path": ["Chapter 3", "Clans", "Nosferatu"],
            "text": "The Nosferatu are hideous vampires who live in sewers.",
        },
        {
            "heading_path": ["Chapter 3", "Clans", "Tremere"],
            "text": "The Tremere are blood sorcerers.",
        },
    ]
    inputs = build_section_summary_inputs(sections)
    assert len(inputs) == 2
    assert "heading_path" in inputs[0]
    assert "section_text" in inputs[0]
    assert len(inputs[0]["section_text"]) <= 2000


def test_build_section_summary_inputs_empty():
    assert build_section_summary_inputs([]) == []


def test_build_section_summary_inputs_truncates_long_text():
    sections = [{"heading_path": ["Ch 1"], "text": "A" * 3000}]
    inputs = build_section_summary_inputs(sections)
    assert len(inputs[0]["section_text"]) <= 2000


def test_format_mindscape_context_contains_source_name():
    mindscape = SourceMindscapeArtifact(
        source_name="VtM20",
        summary="Gothic horror TTRPG about vampires.",
        themes=["gothic horror", "vampire politics"],
        taxonomy_hints=["Clan", "Discipline", "Frenzy"],
        system_name="Vampire: the Masquerade",
    )
    ctx = format_mindscape_context(mindscape)
    assert "VtM20" in ctx or "Vampire: the Masquerade" in ctx
    assert "Clan" in ctx


def test_format_mindscape_context_returns_string():
    mindscape = SourceMindscapeArtifact(
        source_name="Death in Space",
        summary="Bleak sci-fi OSR.",
        themes=[],
        taxonomy_hints=[],
    )
    ctx = format_mindscape_context(mindscape)
    assert isinstance(ctx, str)
    assert len(ctx) > 0


def test_persist_mindscape_artifacts_calls_update(monkeypatch):
    """persist_mindscape_artifacts must call the MongoDB update function once."""
    mindscape = SourceMindscapeArtifact(
        source_name="VtM20",
        summary="Gothic horror TTRPG.",
        themes=[],
        taxonomy_hints=[],
    )
    calls = []

    def fake_update(pack_id, update, **kwargs):
        calls.append({"pack_id": pack_id, "update": update})

    import monitor_agents.utils.analyzer_support._summaries as _summaries_mod

    monkeypatch.setattr(_summaries_mod, "_update_knowledge_pack_fn", fake_update)

    persist_mindscape_artifacts(
        pack_id="pack1",
        chunk_summaries=[],
        section_summaries=[],
        mindscape=mindscape,
        mongo_client=None,
    )
    assert len(calls) == 1
    assert calls[0]["pack_id"] == "pack1"
    assert calls[0]["update"].source_mindscape == mindscape
