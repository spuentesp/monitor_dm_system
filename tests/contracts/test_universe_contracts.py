"""
Contract tests for Universe/Multiverse/Omniverse schemas.

Covers:
- OmniverseCreate / Update / Response
- MultiverseCreate / Update / Response / Filter
- UniverseCreate / Update / Response
- KnowledgeTreeType enum
- AltWorldType enum

Use Cases: Phase 2 World Seeding (DL-1)
"""

from __future__ import annotations

from datetime import datetime
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
    UniverseResponse,
    UniverseUpdate,
)

# =============================================================================
# Omniverse
# =============================================================================


class TestOmniverseCreate:
    def test_minimal(self):
        o = OmniverseCreate(name="Main Omniverse")
        assert o.description == ""  # default

    def test_with_description(self):
        o = OmniverseCreate(
            name="Main Omniverse",
            description="The root of all worlds",
        )
        assert o.description == "The root of all worlds"

    def test_empty_name_fails(self):
        with pytest.raises(Exception):
            OmniverseCreate(name="")


class TestOmniverseUpdate:
    def test_empty(self):
        u = OmniverseUpdate()
        assert u.name is None
        assert u.description is None

    def test_partial(self):
        u = OmniverseUpdate(name="New name")
        assert u.name == "New name"


class TestOmniverseResponse:
    def test_minimal(self):
        r = OmniverseResponse(
            id=uuid4(),
            name="x",
            description="",
            created_at=datetime.utcnow(),
        )
        assert r.id is not None


# =============================================================================
# Multiverse
# =============================================================================


class TestMultiverseCreate:
    def test_minimal(self):
        m = MultiverseCreate(
            omniverse_id=uuid4(),
            name="Forgotten Realms",
            system_name="D&D 5e",
            description="The classic setting",
        )
        assert m.is_template is False  # default
        assert m.knowledge_tree_type == KnowledgeTreeType.DYNAMIC  # default
        assert m.parent_multiverse_id is None
        assert m.source_document_id is None

    def test_template(self):
        m = MultiverseCreate(
            omniverse_id=uuid4(),
            name="Wildemount",
            system_name="D&D 5e",
            description="Critical Role setting",
            is_template=True,
            source_document_id=uuid4(),
        )
        assert m.is_template is True
        assert m.source_document_id is not None

    def test_forked(self):
        m = MultiverseCreate(
            omniverse_id=uuid4(),
            name="Alt Wildemount",
            system_name="D&D 5e",
            description="An alternate version",
            parent_multiverse_id=uuid4(),
            knowledge_tree_type=KnowledgeTreeType.STATIC,
        )
        assert m.parent_multiverse_id is not None
        assert m.knowledge_tree_type == KnowledgeTreeType.STATIC

    def test_empty_name_fails(self):
        with pytest.raises(Exception):
            MultiverseCreate(
                omniverse_id=uuid4(),
                name="",
                system_name="x",
                description="x",
            )


class TestMultiverseUpdate:
    def test_empty(self):
        u = MultiverseUpdate()
        assert u.name is None

    def test_partial(self):
        u = MultiverseUpdate(
            name="New name",
            is_template=True,
        )
        assert u.is_template is True


class TestMultiverseResponse:
    def test_minimal(self):
        r = MultiverseResponse(
            id=uuid4(),
            omniverse_id=uuid4(),
            name="x",
            system_name="D&D 5e",
            description="x",
            created_at=datetime.utcnow(),
        )
        assert r.is_template is False  # default


class TestMultiverseFilter:
    def test_defaults(self):
        f = MultiverseFilter()
        assert f.limit == 30
        assert f.offset == 0

    def test_with_filters(self):
        f = MultiverseFilter(
            omniverse_id=uuid4(),
            is_template=True,
            knowledge_tree_type=KnowledgeTreeType.STATIC,
        )
        assert f.is_template is True

    def test_limit_bounds(self):
        with pytest.raises(Exception):
            MultiverseFilter(limit=0)
        with pytest.raises(Exception):
            MultiverseFilter(limit=2000)


# =============================================================================
# Universe
# =============================================================================


class TestUniverseCreate:
    def test_minimal(self):
        u = UniverseCreate(
            multiverse_id=uuid4(),
            name="Mortal Realms",
            description="Test",
        )
        assert u.alt_world_type == AltWorldType.MAIN  # default
        assert u.is_template is False  # default
        assert u.authority == Authority.SYSTEM  # default
        assert u.canon_level == CanonLevel.CANON  # default
        assert u.confidence == 1.0  # default

    def test_with_genre(self):
        u = UniverseCreate(
            multiverse_id=uuid4(),
            name="Forgotten Realms",
            description="Classic setting",
            genre="fantasy",
            tone="heroic",
            tech_level="medieval",
        )
        assert u.genre == "fantasy"
        assert u.tone == "heroic"

    def test_alt_world(self):
        u = UniverseCreate(
            multiverse_id=uuid4(),
            name="Dark Realms",
            description="Evil version",
            alt_world_type=AltWorldType.SIMULATION,
            parent_universe_id=uuid4(),
        )
        assert u.alt_world_type == AltWorldType.SIMULATION
        assert u.parent_universe_id is not None

    def test_with_game_system(self):
        u = UniverseCreate(
            multiverse_id=uuid4(),
            name="x",
            description="x",
            default_game_system_id=uuid4(),
            default_system_name="D&D 5e",
        )
        assert u.default_game_system_id is not None

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            UniverseCreate(
                multiverse_id=uuid4(),
                name="x",
                description="x",
                confidence=1.5,
            )

    def test_empty_name_fails(self):
        with pytest.raises(Exception):
            UniverseCreate(
                multiverse_id=uuid4(),
                name="",
                description="x",
            )


class TestUniverseUpdate:
    def test_empty(self):
        u = UniverseUpdate()
        assert u.name is None

    def test_partial(self):
        u = UniverseUpdate(
            name="New",
            genre="horror",
            tech_level="modern",
        )
        assert u.genre == "horror"


class TestUniverseResponse:
    def test_minimal(self):
        r = UniverseResponse(
            id=uuid4(),
            multiverse_id=uuid4(),
            name="x",
            description="x",
            created_at=datetime.utcnow(),
        )
        assert r.alt_world_type == AltWorldType.MAIN  # default
        assert r.canon_level == CanonLevel.CANON  # default
        assert r.source_ids == []  # default

    def test_full(self):
        r = UniverseResponse(
            id=uuid4(),
            multiverse_id=uuid4(),
            name="x",
            description="x",
            genre="fantasy",
            tone="dark",
            parent_universe_id=uuid4(),
            alt_world_type=AltWorldType.WHAT_IF,
            is_template=True,
            default_game_system_id=uuid4(),
            canon_level=CanonLevel.CANON,
            confidence=0.9,
            authority=Authority.GM,
            source_ids=[uuid4()],
            created_at=datetime.utcnow(),
        )
        assert r.is_template is True
        assert len(r.source_ids) == 1
