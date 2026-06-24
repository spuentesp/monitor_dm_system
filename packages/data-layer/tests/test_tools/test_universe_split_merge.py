"""Real-Neo4j integration tests for universe split & merge (M-39 / M-40).

Each test provisions an isolated multiverse, builds a small canon graph, runs
the split/merge tool, and asserts the resulting universe. Gated by
``RUN_INTEGRATION=1``.
"""

from __future__ import annotations

from uuid import UUID

import pytest

pytestmark = pytest.mark.integration


def _make_entity(universe_id: UUID, name: str, etype="character"):
    from monitor_data.schemas.base import Authority, CanonLevel, EntityType
    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.tools.neo4j_tools import neo4j_create_entity

    return neo4j_create_entity(
        EntityCreate(
            universe_id=universe_id,
            name=name,
            entity_type=EntityType(etype),
            is_archetype=False,
            description=f"{name} desc",
            properties={},
            authority=Authority.GM,
            canon_level=CanonLevel.CANON,
            confidence=1.0,
        )
    )


def _relate(a: UUID, b: UUID, rel_type="MEMBER_OF"):
    from monitor_data.schemas.relationships import (
        RelationshipCategory,
        RelationshipCreate,
        RelationshipType,
    )
    from monitor_data.tools.neo4j_tools import neo4j_create_relationship

    neo4j_create_relationship(
        RelationshipCreate(
            from_entity_id=a,
            to_entity_id=b,
            rel_type=RelationshipType(rel_type),
            category=RelationshipCategory.MEMBERSHIP,
        )
    )


def _count_entities(universe_id: str) -> int:
    from monitor_data.schemas.entities import EntityFilter
    from monitor_data.tools.neo4j_tools import neo4j_list_entities

    res = neo4j_list_entities(EntityFilter(universe_id=UUID(universe_id), limit=100))
    return len(res.entities)


@pytest.fixture()
def multiverse():
    """An isolated multiverse, cascade-deleted on teardown."""
    from monitor_data.schemas.universe import MultiverseCreate
    from monitor_data.tools.neo4j_tools import (
        neo4j_create_multiverse,
        neo4j_delete_multiverse,
        neo4j_ensure_omniverse,
    )

    omni = neo4j_ensure_omniverse()
    mv = neo4j_create_multiverse(
        MultiverseCreate(
            omniverse_id=UUID(omni["omniverse_id"]),
            name="Split/Merge Test MV",
            system_name="generic",
            description="ephemeral",
            is_template=False,
            source_document_id=None,
            parent_multiverse_id=None,
        )
    )
    yield mv.id
    try:
        neo4j_delete_multiverse(mv.id)
    except Exception:  # noqa: BLE001
        pass


def _new_universe(multiverse_id: UUID, name: str) -> UUID:
    from monitor_data.schemas.universe import UniverseCreate
    from monitor_data.tools.neo4j_tools import neo4j_create_universe

    u = neo4j_create_universe(
        UniverseCreate(multiverse_id=multiverse_id, name=name, description="x")
    )
    return u.id


def test_split_universe_clones_subset_and_induced_edges(multiverse):
    from monitor_data.tools.neo4j_tools import neo4j_split_universe

    uni = _new_universe(multiverse, "Source")
    a = _make_entity(uni, "Aldric")
    b = _make_entity(uni, "Iron Brotherhood", "faction")
    _make_entity(uni, "Caldera", "location")  # C — excluded from the split
    _relate(a.id, b.id)  # A -MEMBER_OF-> B (induced; both in subset)

    result = neo4j_split_universe(
        source_universe_id=uni,
        name="Splinter",
        entity_ids=[a.id, b.id],
    )

    assert result["entities_cloned"] == 2
    assert result["relationships_cloned"] == 1
    new_uid = result["new_universe_id"]
    assert _count_entities(new_uid) == 2  # C did not come along
    # source is untouched (still 3)
    assert _count_entities(str(uni)) == 3


def test_split_rejects_empty_selection(multiverse):
    from monitor_data.tools.neo4j_tools import neo4j_split_universe

    uni = _new_universe(multiverse, "Source2")
    with pytest.raises(ValueError):
        neo4j_split_universe(source_universe_id=uni, name="x", entity_ids=[])


def test_merge_universes_dedupes_by_name(multiverse):
    from monitor_data.tools.neo4j_tools import neo4j_merge_universes

    u1 = _new_universe(multiverse, "Left")
    _make_entity(u1, "Aldric")
    b1 = _make_entity(u1, "Shared Guild", "faction")

    u2 = _new_universe(multiverse, "Right")
    _make_entity(u2, "Shared Guild", "faction")  # same name → dedupes
    c2 = _make_entity(u2, "Caldera", "location")
    _relate(c2.id, _make_entity(u2, "Region", "location").id, "LOCATED_IN")

    result = neo4j_merge_universes(
        source_universe_ids=[u1, u2],
        name="Unified",
        dedupe_by_name=True,
    )

    # A, Shared Guild (deduped), Caldera, Region = 4 unique; 1 duplicate collapsed
    assert result["entities_cloned"] == 4
    assert result["duplicates_merged"] == 1
    assert result["sources_merged"] == 2
    assert _count_entities(result["new_universe_id"]) == 4
    # silence unused-var lint on b1 (kept for graph realism)
    assert b1 is not None


def test_merge_requires_two_sources(multiverse):
    from monitor_data.tools.neo4j_tools import neo4j_merge_universes

    uni = _new_universe(multiverse, "Solo")
    with pytest.raises(ValueError):
        neo4j_merge_universes(source_universe_ids=[uni], name="x")
