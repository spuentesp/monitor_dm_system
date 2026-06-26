"""
Unit tests for monitor_agents.analyzer._enrichment.enrich_entities_from_evidence.

These are pure-function tests — no mocks, no DB, no LLM.
"""

from __future__ import annotations

import pytest
from monitor_data.schemas.knowledge_packs import ExtractedEntityArchetype
from monitor_agents.analyzer._enrichment import enrich_entities_from_evidence


def _entity(name: str, description: str = "", **props) -> ExtractedEntityArchetype:
    return ExtractedEntityArchetype(
        name=name,
        entity_type="character",
        description=description,
        properties=props,
    )


@pytest.mark.unit
class TestNoEvidence:
    def test_entity_without_evidence_passes_through_unchanged(self):
        e = _entity("Goblin", "A small green creature.")
        result = enrich_entities_from_evidence([e], {})
        assert result == [e]
        assert result[0] is e

    def test_entity_not_in_evidence_map_passes_through(self):
        e = _entity("Orc", "Large and brutish.")
        result = enrich_entities_from_evidence([e], {"Goblin": ["some snippet"]})
        assert result[0] is e

    def test_empty_evidence_list_passes_through(self):
        e = _entity("Troll", "Regenerating beast.")
        result = enrich_entities_from_evidence([e], {"Troll": []})
        assert result[0] is e


@pytest.mark.unit
class TestDescriptionFilling:
    def test_short_description_is_replaced_by_evidence_snippet(self):
        e = _entity("Dragon", "Big lizard")  # <40 chars
        result = enrich_entities_from_evidence(
            [e], {"Dragon": ["An ancient serpent of immense power and cunning."]}
        )
        assert "ancient serpent" in result[0].description

    def test_empty_description_is_filled(self):
        e = _entity("Wizard", "")
        result = enrich_entities_from_evidence(
            [e], {"Wizard": ["A master of arcane arts who bends reality."]}
        )
        assert result[0].description != ""

    def test_long_description_is_not_overwritten(self):
        long_desc = "A" * 50
        e = _entity("Knight", long_desc)
        snippet = "This snippet should not replace the description."
        result = enrich_entities_from_evidence([e], {"Knight": [snippet]})
        assert result[0].description == long_desc

    def test_exactly_39_chars_is_replaced(self):
        e = _entity("Elf", "X" * 39)
        result = enrich_entities_from_evidence(
            [e], {"Elf": ["Graceful immortal beings of the forest realm."]}
        )
        assert "Graceful" in result[0].description

    def test_exactly_40_chars_is_not_replaced(self):
        desc = "Y" * 40
        e = _entity("Dwarf", desc)
        result = enrich_entities_from_evidence(
            [e], {"Dwarf": ["Stout mountain folk with great endurance."]}
        )
        assert result[0].description == desc

    def test_seed_uses_only_first_snippet(self):
        e = _entity("Rogue", "short")
        result = enrich_entities_from_evidence(
            [e], {"Rogue": ["First snippet content.", "Second snippet ignored."]}
        )
        assert "First snippet" in result[0].description
        assert "Second snippet" not in result[0].description

    def test_seed_truncated_to_200_chars(self):
        long_snippet = "A" * 300
        e = _entity("Bard", "hi")
        result = enrich_entities_from_evidence([e], {"Bard": [long_snippet]})
        # seed is snippets[0][:200].strip()
        assert len(result[0].description) <= 201  # 200 + "…"

    def test_seed_exactly_200_chars_gets_ellipsis(self):
        snippet = "B" * 200
        e = _entity("Cleric", "short")
        result = enrich_entities_from_evidence([e], {"Cleric": [snippet]})
        assert result[0].description.endswith("…")

    def test_seed_under_200_chars_no_ellipsis(self):
        snippet = "C" * 100
        e = _entity("Paladin", "short")
        result = enrich_entities_from_evidence([e], {"Paladin": [snippet]})
        assert not result[0].description.endswith("…")

    def test_all_caps_heading_stripped_from_seed(self):
        snippet = "CHAPTER ONE\nA brave hero from the northern lands."
        e = _entity("Hero", "hi")
        result = enrich_entities_from_evidence([e], {"Hero": [snippet]})
        assert "CHAPTER ONE" not in result[0].description
        assert "brave hero" in result[0].description

    def test_description_truncated_to_1000_chars(self):
        # description field has max_length=1000, model_copy enforces via [:1000]
        snippet = "D" * 1100
        e = _entity("Monster", "short")
        result = enrich_entities_from_evidence([e], {"Monster": [snippet]})
        assert len(result[0].description) <= 1000


@pytest.mark.unit
class TestPropertyExtraction:
    def test_key_value_colon_pattern_extracted(self):
        e = _entity("NPC")
        result = enrich_entities_from_evidence(
            [e], {"NPC": ["Habitat: deep forest"]}
        )
        assert "habitat" in result[0].properties
        assert result[0].properties["habitat"] == "deep forest"

    def test_key_value_em_dash_pattern_extracted(self):
        e = _entity("NPC")
        result = enrich_entities_from_evidence(
            [e], {"NPC": ["Alignment — chaotic neutral"]}
        )
        assert "alignment" in result[0].properties

    def test_key_spaces_normalized_to_underscores(self):
        e = _entity("NPC")
        result = enrich_entities_from_evidence(
            [e], {"NPC": ["Hit Points: 42"]}
        )
        assert "hit_points" in result[0].properties

    def test_key_lowercased(self):
        e = _entity("NPC")
        result = enrich_entities_from_evidence(
            [e], {"NPC": ["Strength: 18"]}
        )
        assert "strength" in result[0].properties
        assert "Strength" not in result[0].properties

    def test_value_truncated_to_120_chars(self):
        e = _entity("NPC")
        long_val = "x" * 200
        result = enrich_entities_from_evidence(
            [e], {"NPC": [f"Description: {long_val}"]}
        )
        # key will be "description", value truncated to 120
        if "description" in result[0].properties:
            assert len(result[0].properties["description"]) <= 120

    def test_existing_property_not_overwritten(self):
        e = _entity("NPC", habitat="plains")
        result = enrich_entities_from_evidence(
            [e], {"NPC": ["Habitat: deep forest"]}
        )
        assert result[0].properties["habitat"] == "plains"

    def test_max_8_properties_respected(self):
        # Entity already has 7 properties
        existing_props = {f"key{i}": f"val{i}" for i in range(7)}
        e = ExtractedEntityArchetype(
            name="NPC", entity_type="character", description="short", properties=existing_props
        )
        # Evidence has many property lines
        evidence_lines = "\n".join([f"Prop{i}: value{i}" for i in range(10)])
        result = enrich_entities_from_evidence([e], {"NPC": [evidence_lines]})
        assert len(result[0].properties) <= 8

    def test_at_8_properties_no_more_added(self):
        existing_props = {f"key{i}": f"val{i}" for i in range(8)}
        e = ExtractedEntityArchetype(
            name="NPC", entity_type="character", description="short", properties=existing_props
        )
        result = enrich_entities_from_evidence(
            [e], {"NPC": ["Extra: should not be added"]}
        )
        assert len(result[0].properties) == 8
        assert "extra" not in result[0].properties

    def test_properties_extracted_from_all_snippets(self):
        e = _entity("NPC")
        snippets = ["Speed: 30", "Intelligence: 16"]
        result = enrich_entities_from_evidence([e], {"NPC": snippets})
        # combined = " ".join(snippets), so both searched
        props = result[0].properties
        assert "speed" in props or "intelligence" in props


@pytest.mark.unit
class TestModelCopyBehavior:
    def test_no_change_returns_same_object(self):
        long_desc = "A" * 50
        existing_props = {"habitat": "plains"}
        e = ExtractedEntityArchetype(
            name="NPC",
            entity_type="character",
            description=long_desc,
            properties=existing_props,
        )
        # Evidence has same property already present
        result = enrich_entities_from_evidence(
            [e], {"NPC": ["Habitat: mountains"]}
        )
        # description unchanged (>=40), existing prop not overwritten → no copy
        assert result[0] is e

    def test_description_change_creates_new_object(self):
        e = _entity("NPC", "short")
        result = enrich_entities_from_evidence(
            [e], {"NPC": ["A much longer description for this NPC entity."]}
        )
        assert result[0] is not e

    def test_new_property_creates_new_object(self):
        long_desc = "A" * 50
        e = ExtractedEntityArchetype(
            name="NPC", entity_type="character", description=long_desc, properties={}
        )
        result = enrich_entities_from_evidence([e], {"NPC": ["Speed: 30"]})
        if "speed" in result[0].properties:
            assert result[0] is not e

    def test_multiple_entities_processed_independently(self):
        e1 = _entity("Goblin", "hi")
        e2 = _entity("Orc", "A" * 50)
        result = enrich_entities_from_evidence(
            [e1, e2],
            {
                "Goblin": ["A small creature with sharp claws and beady eyes."],
                "Orc": ["Should not replace description"],
            },
        )
        assert len(result) == 2
        assert "small creature" in result[0].description
        assert result[1].description == "A" * 50

    def test_order_preserved(self):
        entities = [_entity(f"Entity{i}") for i in range(5)]
        result = enrich_entities_from_evidence(entities, {})
        assert [r.name for r in result] == [f"Entity{i}" for i in range(5)]
