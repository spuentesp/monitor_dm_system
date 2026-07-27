"""
Contract tests for Relationship schemas (DL-14 extension).

LAYER: 1 (data-layer)
TESTS: Schema validation (unit), enum validation (unit)

pytest --test-run-type=unit tests/contracts/test_DL_31_contracts.py
"""

from uuid import uuid4

from monitor_data.schemas.relationships import (
    RelationshipCategory,
    RelationshipCreate,
    RelationshipFilter,
    RelationshipListResponse,
    RelationshipResponse,
    RelationshipType,
    RelationshipUpdate,
)


class TestRelationshipTypeEnum:
    def test_values(self):
        assert RelationshipType.MEMBER_OF.value == "MEMBER_OF"
        assert RelationshipType.KNOWS.value == "KNOWS"
        assert RelationshipType.ALLIED_WITH.value == "ALLIED_WITH"
        assert RelationshipType.LOCATED_IN.value == "LOCATED_IN"


class TestRelationshipCategoryEnum:
    def test_values(self):
        assert RelationshipCategory.SOCIAL.value == "social"
        assert RelationshipCategory.MEMBERSHIP.value == "membership"
        assert RelationshipCategory.OWNERSHIP.value == "ownership"
        assert RelationshipCategory.SPATIAL.value == "spatial"
        assert RelationshipCategory.TEMPORAL.value == "temporal"
        assert RelationshipCategory.TAXONOMIC.value == "taxonomic"
        assert RelationshipCategory.POWER.value == "power"
        assert RelationshipCategory.GENERIC.value == "generic"


class TestRelationshipCreate:
    def test_minimal(self):
        eid1 = uuid4()
        eid2 = uuid4()
        r = RelationshipCreate(
            from_entity_id=eid1,
            to_entity_id=eid2,
            rel_type=RelationshipType.KNOWS,
            category=RelationshipCategory.SOCIAL,
        )
        assert r.from_entity_id == eid1
        assert r.to_entity_id == eid2
        assert r.rel_type == RelationshipType.KNOWS
        assert r.category == RelationshipCategory.SOCIAL


class TestRelationshipUpdate:
    def test_minimal(self):
        u = RelationshipUpdate(category=RelationshipCategory.OWNERSHIP)
        assert u.category == RelationshipCategory.OWNERSHIP


class TestRelationshipResponse:
    def test_minimal(self):
        r = RelationshipResponse(
            relationship_id="rel-1",
            from_entity_id=uuid4(),
            to_entity_id=uuid4(),
            rel_type=RelationshipType.KNOWS,
            category=RelationshipCategory.SOCIAL,
            properties={},
        )
        assert r.rel_type == RelationshipType.KNOWS
        assert r.relationship_id == "rel-1"


class TestRelationshipFilter:
    def test_defaults(self):
        f = RelationshipFilter()
        assert f.limit == 50
        assert f.offset == 0


class TestRelationshipListResponse:
    def test_valid(self):
        r = RelationshipListResponse(relationships=[], total=0, limit=50, offset=0)
        assert r.total == 0
