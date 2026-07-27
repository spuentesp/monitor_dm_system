"""
Contract tests for Relationship schemas.

Covers:
- RelationshipType enum (21 structural types)
- RelationshipCategory enum (8 categories)
- RelationshipSubcategory enum (fine-grained)
- Direction enum (outgoing, incoming, both)
- StateTag enum (vital, visibility, combat, mental)
- RelationshipCreate: create request
- RelationshipUpdate: partial update
- RelationshipResponse: response
- RelationshipFilter: list filter
- RelationshipListResponse: paginated list

Use Cases: DL-7 (Relationship graph)
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from monitor_data.schemas.relationships import (
    Direction,
    RelationshipCategory,
    RelationshipCreate,
    RelationshipFilter,
    RelationshipListResponse,
    RelationshipResponse,
    RelationshipSubcategory,
    RelationshipType,
    RelationshipUpdate,
    StateTag,
)

# =============================================================================
# Enums
# =============================================================================


class TestRelationshipTypeEnum:
    def test_social_types(self):
        assert RelationshipType.KNOWS.value == "KNOWS"
        assert RelationshipType.ALLIED_WITH.value == "ALLIED_WITH"
        assert RelationshipType.HOSTILE_TO.value == "HOSTILE_TO"

    def test_structural_types(self):
        assert RelationshipType.MEMBER_OF.value == "MEMBER_OF"
        assert RelationshipType.PART_OF.value == "PART_OF"
        assert RelationshipType.SUBGROUP_OF.value == "SUBGROUP_OF"

    def test_spatial_types(self):
        assert RelationshipType.LOCATED_IN.value == "LOCATED_IN"
        assert RelationshipType.CONTAINS.value == "CONTAINS"

    def test_taxonomic_types(self):
        assert RelationshipType.SUBTYPE_OF.value == "SUBTYPE_OF"
        assert RelationshipType.INSTANCE_OF.value == "INSTANCE_OF"
        assert RelationshipType.DERIVES_FROM.value == "DERIVES_FROM"

    def test_power_types(self):
        assert RelationshipType.LEADS.value == "LEADS"
        assert RelationshipType.CONTROLS.value == "CONTROLS"
        assert RelationshipType.CONTROLLED_BY.value == "CONTROLLED_BY"


class TestRelationshipCategoryEnum:
    def test_all_values(self):
        assert RelationshipCategory.SOCIAL.value == "social"
        assert RelationshipCategory.MEMBERSHIP.value == "membership"
        assert RelationshipCategory.OWNERSHIP.value == "ownership"
        assert RelationshipCategory.SPATIAL.value == "spatial"
        assert RelationshipCategory.TEMPORAL.value == "temporal"
        assert RelationshipCategory.TAXONOMIC.value == "taxonomic"
        assert RelationshipCategory.POWER.value == "power"
        assert RelationshipCategory.GENERIC.value == "generic"


class TestRelationshipSubcategoryEnum:
    def test_personal(self):
        assert RelationshipSubcategory.PERSONAL.value == "personal"

    def test_leadership(self):
        assert RelationshipSubcategory.LEADERSHIP.value == "leadership"

    def test_classification(self):
        assert RelationshipSubcategory.CLASSIFICATION.value == "classification"


class TestDirectionEnum:
    def test_all_values(self):
        assert Direction.OUTGOING.value == "outgoing"
        assert Direction.INCOMING.value == "incoming"
        assert Direction.BOTH.value == "both"


class TestStateTagEnum:
    def test_vital(self):
        assert StateTag.ALIVE.value == "alive"
        assert StateTag.DEAD.value == "dead"
        assert StateTag.WOUNDED.value == "wounded"

    def test_disposition(self):
        assert StateTag.HOSTILE.value == "hostile"
        assert StateTag.FRIENDLY.value == "friendly"
        assert StateTag.NEUTRAL.value == "neutral"

    def test_combat(self):
        assert StateTag.PRONE.value == "prone"
        assert StateTag.STUNNED.value == "stunned"

    def test_mental(self):
        assert StateTag.CHARMED.value == "charmed"
        assert StateTag.FRIGHTENED.value == "frightened"


# =============================================================================
# RelationshipCreate
# =============================================================================


class TestRelationshipCreate:
    def test_minimal(self):
        r = RelationshipCreate(
            from_entity_id=uuid4(),
            to_entity_id=uuid4(),
            rel_type=RelationshipType.KNOWS,
            category=RelationshipCategory.SOCIAL,
        )
        assert r.properties == {}
        assert r.tags == []

    def test_with_properties(self):
        r = RelationshipCreate(
            from_entity_id=uuid4(),
            to_entity_id=uuid4(),
            rel_type=RelationshipType.MEMBER_OF,
            category=RelationshipCategory.MEMBERSHIP,
            subcategory=RelationshipSubcategory.ORGANIZATIONAL,
            properties={"since": "2020", "rank": "captain"},
            tags=["military", "active"],
        )
        assert r.properties["rank"] == "captain"
        assert "military" in r.tags


# =============================================================================
# RelationshipUpdate
# =============================================================================


class TestRelationshipUpdate:
    def test_empty(self):
        u = RelationshipUpdate()
        assert u.category is None
        assert u.tags is None
        assert u.properties is None

    def test_partial(self):
        u = RelationshipUpdate(
            category=RelationshipCategory.SOCIAL,
            tags=["romantic"],
        )
        assert u.category == RelationshipCategory.SOCIAL
        assert u.tags == ["romantic"]


# =============================================================================
# RelationshipResponse
# =============================================================================


class TestRelationshipResponse:
    def test_minimal(self):
        r = RelationshipResponse(
            relationship_id="neo4j-rel-1",
            from_entity_id=uuid4(),
            to_entity_id=uuid4(),
            rel_type=RelationshipType.KNOWS,
            category=RelationshipCategory.SOCIAL,
            properties={},
        )
        assert r.relationship_id == "neo4j-rel-1"
        assert r.tags == []
        assert r.created_at is None  # default


# =============================================================================
# RelationshipFilter
# =============================================================================


class TestRelationshipFilter:
    def test_defaults(self):
        f = RelationshipFilter()
        assert f.direction == Direction.BOTH
        assert f.limit == 50
        assert f.offset == 0

    def test_with_filters(self):
        f = RelationshipFilter(
            entity_id=uuid4(),
            rel_type=RelationshipType.KNOWS,
            category=RelationshipCategory.SOCIAL,
            direction=Direction.OUTGOING,
            limit=10,
        )
        assert f.direction == Direction.OUTGOING
        assert f.limit == 10

    def test_limit_bounds(self):
        with pytest.raises(Exception):
            RelationshipFilter(limit=0)  # < 1
        with pytest.raises(Exception):
            RelationshipFilter(limit=2000)  # > 1000


# =============================================================================
# RelationshipListResponse
# =============================================================================


class TestRelationshipListResponse:
    def test_empty(self):
        r = RelationshipListResponse(
            relationships=[],
            total=0,
            limit=50,
            offset=0,
        )
        assert r.relationships == []
        assert r.total == 0
