"""Contract tests for the EntityTemplate schemas.

Verifies that entity_templates Pydantic models:
- instantiate with valid data,
- enforce required fields,
- enforce numeric / length constraints,
- reject invalid enum values where applicable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from monitor_data.schemas.base import DetailLevel, EntityType
from monitor_data.schemas.entity_templates import (
    DefaultPersonality,
    EntityTemplateCreate,
    EntityTemplateFilter,
    EntityTemplateListResponse,
    EntityTemplateResponse,
    EntityTemplateUpdate,
    GenerationType,
    InstantiateEntityRequest,
    NamingPattern,
    NamingType,
    StatGeneration,
    VariableProperty,
)
from pydantic import ValidationError


pytestmark = pytest.mark.unit


# =============================================================================
# VariableProperty
# =============================================================================


class TestVariableProperty:
    def test_minimal(self):
        prop = VariableProperty(
            property_path="stats.STR", generation_type=GenerationType.FIXED
        )
        assert prop.property_path == "stats.STR"
        assert prop.generation_type == GenerationType.FIXED
        assert prop.options == []
        assert prop.range_min is None
        assert prop.range_max is None
        assert prop.pattern is None
        assert prop.table_id is None
        assert prop.llm_hint is None

    def test_with_range(self):
        prop = VariableProperty(
            property_path="stats.DEX",
            generation_type=GenerationType.RANGE,
            range_min=8,
            range_max=18,
        )
        assert prop.range_min == 8
        assert prop.range_max == 18

    def test_with_pattern(self):
        prop = VariableProperty(
            property_path="name",
            generation_type=GenerationType.PATTERN,
            pattern="{adjective} {noun}",
        )
        assert prop.pattern == "{adjective} {noun}"

    def test_with_options(self):
        prop = VariableProperty(
            property_path="faction",
            generation_type=GenerationType.CHOICE,
            options=["red", "blue", "green"],
        )
        assert prop.options == ["red", "blue", "green"]

    def test_with_table(self):
        prop = VariableProperty(
            property_path="trait",
            generation_type=GenerationType.TABLE,
            table_id=uuid4(),
        )
        assert prop.table_id is not None

    def test_with_llm_hint(self):
        prop = VariableProperty(
            property_path="description",
            generation_type=GenerationType.LLM,
            llm_hint="a terse merchant",
        )
        assert prop.llm_hint == "a terse merchant"

    def test_path_too_long(self):
        with pytest.raises(ValidationError):
            VariableProperty(
                property_path="x" * 201, generation_type=GenerationType.FIXED
            )

    def test_pattern_too_long(self):
        with pytest.raises(ValidationError):
            VariableProperty(
                property_path="x",
                generation_type=GenerationType.PATTERN,
                pattern="y" * 501,
            )

    def test_llm_hint_too_long(self):
        with pytest.raises(ValidationError):
            VariableProperty(
                property_path="x",
                generation_type=GenerationType.LLM,
                llm_hint="y" * 501,
            )

    def test_invalid_generation_type(self):
        with pytest.raises(ValidationError):
            VariableProperty(property_path="x", generation_type="bogus")  # type: ignore[arg-type]

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            VariableProperty()  # type: ignore[call-arg]


# =============================================================================
# NamingPattern
# =============================================================================


class TestNamingPattern:
    def test_default(self):
        p = NamingPattern()
        assert p.type == NamingType.LLM
        assert p.pattern is None
        assert p.adjectives == []
        assert p.nouns == []
        assert p.name_list == []

    def test_with_lists(self):
        p = NamingPattern(
            type=NamingType.LIST,
            name_list=["Alice", "Bob", "Charlie"],
        )
        assert p.type == NamingType.LIST
        assert p.name_list == ["Alice", "Bob", "Charlie"]

    def test_pattern_length(self):
        with pytest.raises(ValidationError):
            NamingPattern(pattern="x" * 201)


# =============================================================================
# StatGeneration
# =============================================================================


class TestStatGeneration:
    def test_default(self):
        s = StatGeneration()
        assert s.method == "fixed"
        assert s.formulas == {}
        assert s.constraints == {}
        assert s.game_system_id is None

    def test_with_formulas(self):
        s = StatGeneration(
            method="roll",
            formulas={"HP": "2d8+CON"},
            constraints={"STR": {"min": 8, "max": 18}},
        )
        assert s.method == "roll"
        assert s.formulas["HP"] == "2d8+CON"

    def test_method_too_long(self):
        with pytest.raises(ValidationError):
            StatGeneration(method="x" * 51)

    def test_with_game_system(self):
        s = StatGeneration(game_system_id=uuid4())
        assert s.game_system_id is not None


# =============================================================================
# DefaultPersonality
# =============================================================================


class TestDefaultPersonality:
    def test_minimal(self):
        p = DefaultPersonality()
        assert p.trait_pool == []
        assert p.fear_pool == []
        assert p.desire_pool == []
        assert p.speech_styles == []
        assert p.default_disposition is None

    def test_full(self):
        p = DefaultPersonality(
            trait_pool=["gruff", "loyal"],
            fear_pool=["dragons"],
            desire_pool=["peace"],
            speech_styles=["sarcastic"],
            default_disposition="neutral",
        )
        assert "gruff" in p.trait_pool
        assert p.default_disposition == "neutral"

    def test_disposition_too_long(self):
        with pytest.raises(ValidationError):
            DefaultPersonality(default_disposition="x" * 51)


# =============================================================================
# EntityTemplateCreate
# =============================================================================


class TestEntityTemplateCreate:
    def test_minimal(self):
        t = EntityTemplateCreate(
            universe_id=uuid4(), name="City Guard", entity_type=EntityType.CHARACTER
        )
        assert t.name == "City Guard"
        assert t.entity_type == EntityType.CHARACTER
        assert t.base_properties == {}
        assert t.variable_properties == []
        assert t.default_state_tags == []
        assert t.default_detail_level == DetailLevel.STUB
        assert t.parent_template_id is None

    def test_full(self):
        t = EntityTemplateCreate(
            universe_id=uuid4(),
            name="Soldier",
            description="A trained soldier",
            entity_type=EntityType.CHARACTER,
            base_properties={"role": "soldier"},
            variable_properties=[
                VariableProperty(
                    property_path="stats.STR",
                    generation_type=GenerationType.RANGE,
                    range_min=12,
                    range_max=18,
                )
            ],
            naming_pattern=NamingPattern(type=NamingType.NUMBERED),
            stat_generation=StatGeneration(method="roll"),
            default_state_tags=["healthy", "armed"],
            default_detail_level=DetailLevel.SKETCHED,
            default_personality=DefaultPersonality(trait_pool=["loyal"]),
            parent_template_id=uuid4(),
        )
        assert t.parent_template_id is not None
        assert t.default_detail_level == DetailLevel.SKETCHED

    def test_name_required(self):
        with pytest.raises(ValidationError):
            EntityTemplateCreate(universe_id=uuid4(), entity_type=EntityType.CHARACTER)  # type: ignore[call-arg]

    def test_universe_id_required(self):
        with pytest.raises(ValidationError):
            EntityTemplateCreate(name="x", entity_type=EntityType.CHARACTER)  # type: ignore[call-arg]

    def test_entity_type_required(self):
        with pytest.raises(ValidationError):
            EntityTemplateCreate(universe_id=uuid4(), name="x")  # type: ignore[call-arg]

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            EntityTemplateCreate(
                universe_id=uuid4(), name="", entity_type=EntityType.CHARACTER
            )

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            EntityTemplateCreate(
                universe_id=uuid4(),
                name="x" * 201,
                entity_type=EntityType.CHARACTER,
            )

    def test_description_too_long(self):
        with pytest.raises(ValidationError):
            EntityTemplateCreate(
                universe_id=uuid4(),
                name="x",
                entity_type=EntityType.CHARACTER,
                description="y" * 2001,
            )

    def test_invalid_entity_type(self):
        with pytest.raises(ValidationError):
            EntityTemplateCreate(
                universe_id=uuid4(), name="x", entity_type="bogus"  # type: ignore[arg-type]
            )


# =============================================================================
# EntityTemplateUpdate
# =============================================================================


class TestEntityTemplateUpdate:
    def test_empty_update(self):
        u = EntityTemplateUpdate()
        assert u.name is None
        assert u.description is None
        assert u.base_properties is None

    def test_partial_update(self):
        u = EntityTemplateUpdate(name="New Name", default_detail_level=DetailLevel.DETAILED)
        assert u.name == "New Name"
        assert u.default_detail_level == DetailLevel.DETAILED

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            EntityTemplateUpdate(name="")


# =============================================================================
# EntityTemplateResponse
# =============================================================================


class TestEntityTemplateResponse:
    def _kwargs(self, **overrides):
        base = {
            "template_id": uuid4(),
            "universe_id": uuid4(),
            "name": "City Guard",
            "description": "",
            "entity_type": EntityType.CHARACTER,
            "base_properties": {},
            "variable_properties": [],
            "naming_pattern": NamingPattern(),
            "stat_generation": StatGeneration(),
            "default_state_tags": [],
            "default_detail_level": DetailLevel.STUB,
            "created_at": datetime.now(timezone.utc),
        }
        base.update(overrides)
        return base

    def test_minimal(self):
        r = EntityTemplateResponse(**self._kwargs())
        assert r.name == "City Guard"
        assert r.usage_count == 0
        assert r.updated_at is None
        assert r.parent_template_id is None

    def test_with_parent(self):
        r = EntityTemplateResponse(**self._kwargs(parent_template_id=uuid4()))
        assert r.parent_template_id is not None


# =============================================================================
# EntityTemplateFilter
# =============================================================================


class TestEntityTemplateFilter:
    def test_defaults(self):
        f = EntityTemplateFilter()
        assert f.universe_id is None
        assert f.entity_type is None
        assert f.parent_template_id is None
        assert f.limit == 50
        assert f.offset == 0

    def test_with_values(self):
        f = EntityTemplateFilter(
            universe_id=uuid4(),
            entity_type=EntityType.FACTION,
            limit=100,
        )
        assert f.entity_type == EntityType.FACTION
        assert f.limit == 100

    def test_limit_min(self):
        with pytest.raises(ValidationError):
            EntityTemplateFilter(limit=0)

    def test_limit_max(self):
        with pytest.raises(ValidationError):
            EntityTemplateFilter(limit=201)

    def test_offset_min(self):
        with pytest.raises(ValidationError):
            EntityTemplateFilter(offset=-1)


# =============================================================================
# EntityTemplateListResponse
# =============================================================================


class TestEntityTemplateListResponse:
    def test_empty(self):
        r = EntityTemplateListResponse(templates=[], total=0, limit=50, offset=0)
        assert r.templates == []
        assert r.total == 0

    def test_with_template(self):
        template = EntityTemplateResponse(
            template_id=uuid4(),
            universe_id=uuid4(),
            name="x",
            description="",
            entity_type=EntityType.CHARACTER,
            base_properties={},
            variable_properties=[],
            naming_pattern=NamingPattern(),
            stat_generation=StatGeneration(),
            default_state_tags=[],
            default_detail_level=DetailLevel.STUB,
            created_at=datetime.now(timezone.utc),
        )
        r = EntityTemplateListResponse(templates=[template], total=1, limit=50, offset=0)
        assert len(r.templates) == 1
        assert r.total == 1


# =============================================================================
# InstantiateEntityRequest
# =============================================================================


class TestInstantiateEntityRequest:
    def test_minimal(self):
        r = InstantiateEntityRequest(template_id=uuid4())
        assert r.template_id is not None
        assert r.scene_id is None
        assert r.story_id is None
        assert r.provide_context is None
        assert r.override_name is None
        assert r.override_properties is None

    def test_full(self):
        r = InstantiateEntityRequest(
            template_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            provide_context="a nervous innkeeper",
            override_name="Bartholomew",
            override_properties={"role": "innkeeper"},
        )
        assert r.override_name == "Bartholomew"
        assert r.override_properties == {"role": "innkeeper"}

    def test_context_too_long(self):
        with pytest.raises(ValidationError):
            InstantiateEntityRequest(
                template_id=uuid4(), provide_context="x" * 1001
            )

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            InstantiateEntityRequest(template_id=uuid4(), override_name="x" * 201)

    def test_template_id_required(self):
        with pytest.raises(ValidationError):
            InstantiateEntityRequest()  # type: ignore[call-arg]
