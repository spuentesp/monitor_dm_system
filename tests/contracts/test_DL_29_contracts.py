"""
Contract tests for Universe/Multiverse/Omniverse schemas.

LAYER: 1 (data-layer)
TESTS: Schema validation (unit), enum validation (unit)

pytest --test-run-type=unit tests/contracts/test_DL_29_contracts.py
"""

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.base import (
    AltWorldType,
    Authority,
    CanonLevel,
    KnowledgeTreeType,
)
from monitor_data.schemas.universe import (
    MultiverseCreate,
    MultiverseFilter,
    MultiverseResponse,
    MultiverseUpdate,
    OmniverseCreate,
    OmniverseResponse,
    OmniverseUpdate,
    UniverseCreate,
    UniverseFilter,
    UniverseResponse,
    UniverseUpdate,
)
from pydantic import ValidationError

# =============================================================================
# OMNIVERSE
# =============================================================================


class TestOmniverseCreate:
    def test_minimal(self):
        o = OmniverseCreate(name="Root", description="The root omniverse")
        assert o.name == "Root"
        assert o.description == "The root omniverse"

    def test_name_required(self):
        with pytest.raises(ValidationError):
            OmniverseCreate(description="test")  # type: ignore[arg-type]

    def test_name_min_length_1(self):
        with pytest.raises(ValidationError):
            OmniverseCreate(name="", description="")


class TestOmniverseUpdate:
    def test_empty(self):
        u = OmniverseUpdate()
        assert u.name is None

    def test_partial(self):
        u = OmniverseUpdate(name="New Root")
        assert u.name == "New Root"


class TestOmniverseResponse:
    def test_valid(self):
        now = datetime.now(UTC)
        r = OmniverseResponse(
            id=uuid4(), name="Root", description="desc", created_at=now
        )
        assert r.name == "Root"


# =============================================================================
# MULTIVERSE
# =============================================================================


class TestMultiverseCreate:
    def test_minimal(self):
        oid = uuid4()
        m = MultiverseCreate(
            omniverse_id=oid,
            name="Forgotten Realms",
            system_name="D&D 5e",
            description="A high fantasy multiverse",
        )
        assert m.name == "Forgotten Realms"
        assert m.system_name == "D&D 5e"
        assert m.is_template is False
        assert m.knowledge_tree_type == KnowledgeTreeType.DYNAMIC

    def test_as_template(self):
        m = MultiverseCreate(
            omniverse_id=uuid4(),
            name="FR Template",
            system_name="D&D 5e",
            description="Template blueprint",
            is_template=True,
            knowledge_tree_type=KnowledgeTreeType.TEMPLATE,
        )
        assert m.is_template is True
        assert m.knowledge_tree_type == KnowledgeTreeType.TEMPLATE

    def test_name_required(self):
        with pytest.raises(ValidationError):
            MultiverseCreate(
                omniverse_id=uuid4(), name="", system_name="", description=""
            )


class TestMultiverseUpdate:
    def test_empty(self):
        u = MultiverseUpdate()
        assert u.name is None


class TestMultiverseResponse:
    def test_valid(self):
        now = datetime.now(UTC)
        r = MultiverseResponse(
            id=uuid4(),
            omniverse_id=uuid4(),
            name="FR",
            system_name="D&D 5e",
            description="desc",
            created_at=now,
        )
        assert r.name == "FR"
        assert r.is_template is False


class TestMultiverseFilter:
    def test_defaults(self):
        f = MultiverseFilter()
        assert f.limit == 30
        assert f.offset == 0


# =============================================================================
# UNIVERSE
# =============================================================================


class TestUniverseCreate:
    def test_minimal(self):
        mid = uuid4()
        u = UniverseCreate(
            multiverse_id=mid, name="Toril", description="The world of Toril"
        )
        assert u.name == "Toril"
        assert u.alt_world_type == AltWorldType.MAIN
        assert u.is_template is False
        assert u.authority == Authority.SYSTEM
        assert u.canon_level == CanonLevel.CANON
        assert u.confidence == 1.0

    def test_with_metadata(self):
        u = UniverseCreate(
            multiverse_id=uuid4(),
            name="Dark Sun",
            description="A harsh desert world",
            genre="dark fantasy",
            tone="grim",
            tech_level="medieval",
        )
        assert u.genre == "dark fantasy"
        assert u.tone == "grim"

    def test_name_min_length_1(self):
        with pytest.raises(ValidationError):
            UniverseCreate(multiverse_id=uuid4(), name="", description="x")

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            UniverseCreate(
                multiverse_id=uuid4(), name="X", description="x", confidence=-0.1
            )
        with pytest.raises(ValidationError):
            UniverseCreate(
                multiverse_id=uuid4(), name="X", description="x", confidence=1.1
            )


class TestUniverseUpdate:
    def test_empty(self):
        u = UniverseUpdate()
        assert u.name is None

    def test_partial(self):
        u = UniverseUpdate(genre="sci-fi", tone="hopeful")
        assert u.genre == "sci-fi"


class TestUniverseResponse:
    def test_valid(self):
        now = datetime.now(UTC)
        r = UniverseResponse(
            id=uuid4(),
            multiverse_id=uuid4(),
            name="Toril",
            description="The world",
            created_at=now,
        )
        assert r.name == "Toril"
        assert r.alt_world_type == AltWorldType.MAIN
        assert r.source_ids == []


class TestUniverseFilter:
    def test_defaults(self):
        f = UniverseFilter()
        assert f.limit == 30
        assert f.offset == 0

    def test_limit_bounds(self):
        with pytest.raises(ValidationError):
            UniverseFilter(limit=0)
        with pytest.raises(ValidationError):
            UniverseFilter(limit=1001)


# =============================================================================
# ENUMS
# =============================================================================


class TestAltWorldTypeEnum:
    def test_values(self):
        assert AltWorldType.MAIN.value == "main"
        assert AltWorldType.FORK.value == "fork"
        assert AltWorldType.WHAT_IF.value == "what_if"
        assert AltWorldType.DREAM.value == "dream"
        assert AltWorldType.SIMULATION.value == "simulation"


class TestKnowledgeTreeTypeEnum:
    def test_values(self):
        assert KnowledgeTreeType.STATIC.value == "static"
        assert KnowledgeTreeType.DYNAMIC.value == "dynamic"
        assert KnowledgeTreeType.TEMPLATE.value == "template"
