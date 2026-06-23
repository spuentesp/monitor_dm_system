"""
E2E Test 02 — World & Multiverse Setup

Use cases covered
-----------------
DL-1   Manage Multiverse/Universes (Neo4j)
DL-2   Manage Archetypes & Instances (Neo4j)
DL-3   Manage Facts & Events (Neo4j)
M-1..M-12  World-building operations
Q-1..Q-5   Query operations

All tests depend on the ``seeded_world`` session fixture which pre-populates
the Realm of Shadows world in Neo4j.  Heavy DB tests are also marked
``integration`` so they only run with RUN_INTEGRATION=1.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pytest


# =============================================================================
# DL-1 / M-1, M-2: Omniverse / Multiverse / Universe hierarchy
# =============================================================================


@pytest.mark.e2e
@pytest.mark.integration
class TestUniverseHierarchy:
    """DL-1 — Verify the Omniverse → Multiverse → Universe tree."""

    def test_omniverse_exists(self, seeded_world: Dict[str, Any]) -> None:
        """M-1: Calling ensure_omniverse twice returns the same ID."""
        from monitor_data.tools.neo4j_tools import neo4j_ensure_omniverse

        info = neo4j_ensure_omniverse()
        assert "omniverse_id" in info
        from uuid import UUID

        assert UUID(info["omniverse_id"]) == seeded_world["omniverse_id"]
        assert info["created"] is False, "Second call must NOT create a new root"

    def test_multiverse_exists(self, seeded_world: Dict[str, Any]) -> None:
        """M-1: Multiverse is retrievable by ID."""
        from monitor_data.tools.neo4j_tools import neo4j_get_multiverse

        mv = neo4j_get_multiverse(seeded_world["multiverse_id"])
        assert mv is not None
        assert mv.id == seeded_world["multiverse_id"]
        assert "Realm" in mv.name

    def test_universe_exists(self, seeded_world: Dict[str, Any]) -> None:
        """M-2: Universe is retrievable with correct genre."""
        from monitor_data.tools.neo4j_tools import neo4j_get_universe

        universe = neo4j_get_universe(seeded_world["universe_id"])
        assert universe is not None
        assert universe.id == seeded_world["universe_id"]
        assert universe.name == "Realm of Shadows"
        assert universe.genre == "dark_fantasy"

    def test_list_universes_includes_seed(self, seeded_world: Dict[str, Any]) -> None:
        """M-2: Listing universes by multiverse returns the seeded one."""
        from monitor_data.schemas.universe import UniverseFilter
        from monitor_data.tools.neo4j_tools import neo4j_list_universes

        # neo4j_list_universes returns List[UniverseResponse]
        universes = neo4j_list_universes(
            UniverseFilter(multiverse_id=seeded_world["multiverse_id"])
        )
        universe_ids = [u.id for u in universes]
        assert seeded_world["universe_id"] in universe_ids

    def test_create_delete_alternate_universe(
        self, seeded_world: Dict[str, Any]
    ) -> None:
        """M-2: An alternate-history universe can be created and deleted."""
        from monitor_data.schemas.universe import UniverseCreate
        from monitor_data.tools.neo4j_tools import (
            neo4j_create_universe,
            neo4j_delete_universe,
            neo4j_get_universe,
        )

        alt = neo4j_create_universe(
            UniverseCreate(
                multiverse_id=seeded_world["multiverse_id"],
                name="Realm — Ashland Timeline",
                description="Alt-timeline where the Void Cult won.",
                genre="dark_fantasy",
            )
        )
        assert alt is not None
        assert alt.id != seeded_world["universe_id"]

        neo4j_delete_universe(alt.id)
        assert neo4j_get_universe(alt.id) is None

    def test_update_universe(self, seeded_world: Dict[str, Any]) -> None:
        """M-2: Universe description can be patched."""
        from monitor_data.schemas.universe import UniverseCreate, UniverseUpdate
        from monitor_data.tools.neo4j_tools import (
            neo4j_create_universe,
            neo4j_update_universe,
            neo4j_get_universe,
            neo4j_delete_universe,
        )

        scratch = neo4j_create_universe(
            UniverseCreate(
                multiverse_id=seeded_world["multiverse_id"],
                name="Update Test Universe",
                description="Will be updated.",
            )
        )
        neo4j_update_universe(
            scratch.id,
            UniverseUpdate(description="Description has been updated."),
        )
        updated = neo4j_get_universe(scratch.id)
        assert updated.description == "Description has been updated."
        neo4j_delete_universe(scratch.id)


# =============================================================================
# DL-2 / M-3, M-4: Entity Archetypes and Instances
# =============================================================================


@pytest.mark.e2e
@pytest.mark.integration
class TestEntities:
    """DL-2 — EntityArchetype templates and EntityInstance concrete entities."""

    def test_archetype_fighter_exists(self, seeded_world: Dict[str, Any]) -> None:
        """M-3: Fighter archetype is accessible by ID."""
        from monitor_data.tools.neo4j_tools import neo4j_get_entity

        fighter = neo4j_get_entity(seeded_world["arch_fighter_id"])
        assert fighter is not None
        assert fighter.name == "Fighter"
        assert fighter.is_archetype is True

    def test_archetype_faction_types(self, seeded_world: Dict[str, Any]) -> None:
        """M-3: All three faction archetypes are accessible."""
        from monitor_data.tools.neo4j_tools import neo4j_get_entity

        for key in ("arch_iron_throne_id", "arch_old_faith_id", "arch_void_cult_id"):
            entity = neo4j_get_entity(seeded_world[key])
            assert entity is not None
            assert entity.entity_type.value == "faction"

    def test_pc_hero_is_instance(self, seeded_world: Dict[str, Any]) -> None:
        """M-4: PC 'Aldric the Bold' is an EntityInstance with state tags."""
        from monitor_data.tools.neo4j_tools import neo4j_get_entity

        pc = neo4j_get_entity(seeded_world["pc_hero_id"])
        assert pc is not None
        assert pc.name == "Aldric the Bold"
        assert pc.is_archetype is False
        assert "alive" in pc.state_tags
        assert pc.archetype_id == seeded_world["arch_fighter_id"]

    def test_npc_king_has_attributes(self, seeded_world: Dict[str, Any]) -> None:
        """M-4: NPC has structured attributes in properties dict."""
        from monitor_data.tools.neo4j_tools import neo4j_get_entity

        king = neo4j_get_entity(seeded_world["npc_king_id"])
        assert king.properties.get("attributes", {}).get("Charisma") == 18

    # Q-1: Query entities by type ------------------------------------

    def test_list_entities_by_type_character(
        self, seeded_world: Dict[str, Any]
    ) -> None:
        """Q-1: List character entities returns Fighter, Mage, Rogue, NPCs, PC."""
        from monitor_data.schemas.base import EntityType
        from monitor_data.schemas.entities import EntityFilter
        from monitor_data.tools.neo4j_tools import neo4j_list_entities

        result = neo4j_list_entities(
            EntityFilter(
                universe_id=seeded_world["universe_id"],
                entity_type=EntityType.CHARACTER,
            )
        )
        # neo4j_list_entities returns EntityListResponse with .total and .entities
        assert result.total >= 5
        names = [e.name for e in result.entities]
        assert "Fighter" in names
        assert "Aldric the Bold" in names

    def test_list_entities_by_type_faction(self, seeded_world: Dict[str, Any]) -> None:
        """Q-1: List faction entities returns all 3 factions."""
        from monitor_data.schemas.base import EntityType
        from monitor_data.schemas.entities import EntityFilter
        from monitor_data.tools.neo4j_tools import neo4j_list_entities

        result = neo4j_list_entities(
            EntityFilter(
                universe_id=seeded_world["universe_id"],
                entity_type=EntityType.FACTION,
            )
        )
        assert result.total >= 3
        names = [e.name for e in result.entities]
        assert "Iron Throne" in names
        assert "Void Cult" in names

    def test_list_archetypes_only(self, seeded_world: Dict[str, Any]) -> None:
        """M-9: is_archetype=True filter returns only archetypes."""
        from monitor_data.schemas.entities import EntityFilter
        from monitor_data.tools.neo4j_tools import neo4j_list_entities

        result = neo4j_list_entities(
            EntityFilter(
                universe_id=seeded_world["universe_id"],
                is_archetype=True,
            )
        )
        for entity in result.entities:
            assert entity.is_archetype is True

    def test_list_instances_only(self, seeded_world: Dict[str, Any]) -> None:
        """M-9: is_archetype=False filter returns only instances."""
        from monitor_data.schemas.entities import EntityFilter
        from monitor_data.tools.neo4j_tools import neo4j_list_entities

        result = neo4j_list_entities(
            EntityFilter(
                universe_id=seeded_world["universe_id"],
                is_archetype=False,
            )
        )
        for entity in result.entities:
            assert entity.is_archetype is False

    def test_update_entity_description(self, seeded_world: Dict[str, Any]) -> None:
        """M-4: Entity description can be updated."""
        from monitor_data.schemas.entities import EntityUpdate
        from monitor_data.tools.neo4j_tools import neo4j_get_entity, neo4j_update_entity

        neo4j_update_entity(
            seeded_world["npc_priestess_id"],
            EntityUpdate(
                description="High Priestess Mara, keeper of ancient rites and secrets."
            ),
        )
        updated = neo4j_get_entity(seeded_world["npc_priestess_id"])
        assert "secrets" in updated.description

    def test_set_state_tags(self, seeded_world: Dict[str, Any]) -> None:
        """M-4: State tags on EntityInstance can be added."""
        from monitor_data.schemas.entities import StateTagsUpdate
        from monitor_data.tools.neo4j_tools import (
            neo4j_get_entity,
            neo4j_set_state_tags,
        )

        neo4j_set_state_tags(
            seeded_world["pc_hero_id"],
            StateTagsUpdate(add_tags=["in_dusk_market"], remove_tags=[]),
        )
        pc = neo4j_get_entity(seeded_world["pc_hero_id"])
        assert "in_dusk_market" in pc.state_tags

    def test_create_and_delete_temporary_entity(
        self, seeded_world: Dict[str, Any]
    ) -> None:
        """M-4: Entities can be created and deleted."""
        from monitor_data.schemas.base import CanonLevel, EntityType
        from monitor_data.schemas.entities import EntityCreate
        from monitor_data.tools.neo4j_tools import (
            neo4j_create_entity,
            neo4j_delete_entity,
            neo4j_get_entity,
        )

        temp = neo4j_create_entity(
            EntityCreate(
                universe_id=seeded_world["universe_id"],
                name="Temporary Guard",
                entity_type=EntityType.CHARACTER,
                is_archetype=False,
                description="Disposable test entity.",
                canon_level=CanonLevel.PROPOSED,
            )
        )
        assert temp is not None
        neo4j_delete_entity(temp.id)
        assert neo4j_get_entity(temp.id) is None


# =============================================================================
# DL-3 / M-5, M-6, M-7: Facts, Axioms, Events
# =============================================================================


@pytest.mark.e2e
@pytest.mark.integration
class TestFactsAxiomsEvents:
    """
    DL-3 — Verify lore facts, physics axioms, and timeline events.

    Note: All list functions here return plain List[T], not paginated objects.
    """

    # Axioms ------------------------------------------------------------------

    def test_axiom_magic_exists(self, seeded_world: Dict[str, Any]) -> None:
        """M-6: The magic axiom is retrievable by ID."""
        from monitor_data.tools.neo4j_tools import neo4j_get_axiom

        axiom = neo4j_get_axiom(seeded_world["axiom_magic_id"])
        assert axiom is not None
        assert "Void" in axiom.statement or "Magic" in axiom.statement
        assert axiom.domain == "magic"

    def test_axiom_undead_exists(self, seeded_world: Dict[str, Any]) -> None:
        """M-6: The undead axiom is retrievable."""
        from monitor_data.tools.neo4j_tools import neo4j_get_axiom

        axiom = neo4j_get_axiom(seeded_world["axiom_dead_id"])
        assert axiom.domain == "undead"

    def test_list_axioms_by_domain(self, seeded_world: Dict[str, Any]) -> None:
        """Q-3: Filtering axioms by domain=magic returns the magic axiom."""
        from monitor_data.schemas.facts import AxiomFilter
        from monitor_data.tools.neo4j_tools import neo4j_list_axioms

        # neo4j_list_axioms returns List[AxiomResponse]
        axioms = neo4j_list_axioms(
            AxiomFilter(
                universe_id=seeded_world["universe_id"],
                domain="magic",
            )
        )
        assert len(axioms) >= 1
        assert any("Void" in a.statement or "Magic" in a.statement for a in axioms)

    def test_list_all_axioms_for_universe(self, seeded_world: Dict[str, Any]) -> None:
        """M-10: Universe has at least 3 seeded axioms."""
        from monitor_data.schemas.facts import AxiomFilter
        from monitor_data.tools.neo4j_tools import neo4j_list_axioms

        axioms = neo4j_list_axioms(AxiomFilter(universe_id=seeded_world["universe_id"]))
        assert len(axioms) >= 3

    def test_create_new_axiom_during_play(self, seeded_world: Dict[str, Any]) -> None:
        """M-6: New axioms can be added mid-game."""
        from monitor_data.schemas.base import AxiomAuthority, CanonLevel
        from monitor_data.schemas.facts import AxiomCreate
        from monitor_data.tools.neo4j_tools import neo4j_create_axiom, neo4j_get_axiom

        axiom = neo4j_create_axiom(
            AxiomCreate(
                universe_id=seeded_world["universe_id"],
                statement="The Void Rift can only be sealed with a willing sacrifice.",
                domain="magic",
                authority=AxiomAuthority.METAPHYSICS,
                canon_level=CanonLevel.CANON,
            )
        )
        assert axiom is not None
        retrieved = neo4j_get_axiom(axiom.id)
        assert "Void Rift" in retrieved.statement

    # Facts -------------------------------------------------------------------

    def test_fact_iron_throne_exists(self, seeded_world: Dict[str, Any]) -> None:
        """M-5: The Iron Throne rule fact is retrievable by ID."""
        from monitor_data.tools.neo4j_tools import neo4j_get_fact

        fact = neo4j_get_fact(seeded_world["fact_throne_rule_id"])
        assert fact is not None
        assert "Iron Throne" in fact.statement

    def test_list_facts_for_universe(self, seeded_world: Dict[str, Any]) -> None:
        """M-11 / Q-2: Listing facts returns at least the 2 seeded facts."""
        from monitor_data.schemas.facts import FactFilter
        from monitor_data.tools.neo4j_tools import neo4j_list_facts

        # neo4j_list_facts returns List[FactResponse]
        facts = neo4j_list_facts(FactFilter(universe_id=seeded_world["universe_id"]))
        assert len(facts) >= 2
        statements = [f.statement for f in facts]
        assert any("Iron Throne" in s for s in statements)

    def test_create_new_fact(self, seeded_world: Dict[str, Any]) -> None:
        """M-5: New facts can be added during play (e.g. from session discovery)."""
        from monitor_data.schemas.base import Authority, CanonLevel
        from monitor_data.schemas.facts import FactCreate, FactType
        from monitor_data.tools.neo4j_tools import neo4j_create_fact, neo4j_get_fact

        fact = neo4j_create_fact(
            FactCreate(
                universe_id=seeded_world["universe_id"],
                statement="The king's son was last seen near the Market Town of Dusk.",
                fact_type=FactType.STATE,
                authority=Authority.GM,
                canon_level=CanonLevel.CANON,
            )
        )
        retrieved = neo4j_get_fact(fact.id)
        assert "Market Town" in retrieved.statement

    # Events ------------------------------------------------------------------

    def test_event_shadow_war_exists(self, seeded_world: Dict[str, Any]) -> None:
        """M-7: The Shadow War event is retrievable by ID."""
        from monitor_data.tools.neo4j_tools import neo4j_get_event

        event = neo4j_get_event(seeded_world["event_shadow_war_id"])
        assert event is not None
        assert "Shadow War" in event.title

    def test_event_sundering_exists(self, seeded_world: Dict[str, Any]) -> None:
        """M-7: The Great Sundering event is retrievable."""
        from monitor_data.tools.neo4j_tools import neo4j_get_event

        event = neo4j_get_event(seeded_world["event_sundering_id"])
        assert "Sundering" in event.title

    def test_list_events_for_universe(self, seeded_world: Dict[str, Any]) -> None:
        """M-12 / Q-4: Listing events returns both seeded events."""
        from monitor_data.schemas.facts import EventFilter
        from monitor_data.tools.neo4j_tools import neo4j_list_events

        # neo4j_list_events returns List[EventResponse]
        events = neo4j_list_events(EventFilter(universe_id=seeded_world["universe_id"]))
        assert len(events) >= 2
        titles = [e.title for e in events]
        assert "The Shadow War" in titles
        assert "The Great Sundering" in titles

    def test_create_new_historical_event(self, seeded_world: Dict[str, Any]) -> None:
        """M-7: New events can be added."""
        from monitor_data.schemas.base import Authority, CanonLevel
        from monitor_data.schemas.facts import EventCreate
        from monitor_data.tools.neo4j_tools import neo4j_create_event, neo4j_get_event

        event = neo4j_create_event(
            EventCreate(
                universe_id=seeded_world["universe_id"],
                title="The PC Arrives at Dusk",
                description="The hero enters the Market Town of Dusk for the first time.",
                start_time=datetime(450, 3, 15, tzinfo=timezone.utc),
                authority=Authority.GM,
                canon_level=CanonLevel.CANON,
            )
        )
        retrieved = neo4j_get_event(event.id)
        assert "Dusk" in retrieved.title


# =============================================================================
# DL-2 / M-8 / Q-5: Entity Relationships
# =============================================================================


@pytest.mark.e2e
@pytest.mark.integration
class TestEntityRelationships:
    """DL-2 / M-8 / Q-5 — Typed relationships between entities."""

    def test_create_allied_with_relationship(
        self, seeded_world: Dict[str, Any]
    ) -> None:
        """M-8: ALLIED_WITH relationship can be established."""
        from monitor_data.schemas.relationships import (
            RelationshipCategory,
            RelationshipCreate,
            RelationshipType,
        )
        from monitor_data.tools.neo4j_tools import neo4j_create_relationship

        rel = neo4j_create_relationship(
            RelationshipCreate(
                from_entity_id=seeded_world["pc_hero_id"],
                to_entity_id=seeded_world["npc_king_id"],
                rel_type=RelationshipType.ALLIED_WITH,
                category=RelationshipCategory.SOCIAL,
                properties={"since": "campaign_start", "notes": "Sworn fealty."},
            )
        )
        assert rel is not None
        assert rel.rel_type == RelationshipType.ALLIED_WITH

    def test_list_relationships_for_entity(self, seeded_world: Dict[str, Any]) -> None:
        """Q-5: Relationships can be queried for an entity."""
        from monitor_data.schemas.relationships import (
            RelationshipCategory,
            RelationshipCreate,
            RelationshipFilter,
            RelationshipType,
        )
        from monitor_data.tools.neo4j_tools import (
            neo4j_create_relationship,
            neo4j_list_relationships,
        )

        neo4j_create_relationship(
            RelationshipCreate(
                from_entity_id=seeded_world["pc_hero_id"],
                to_entity_id=seeded_world["npc_priestess_id"],
                rel_type=RelationshipType.KNOWS,
                category=RelationshipCategory.SOCIAL,
                properties={"context": "Met during the investigation."},
            )
        )

        result = neo4j_list_relationships(
            RelationshipFilter(entity_id=seeded_world["pc_hero_id"])
        )
        # Returns RelationshipListResponse with .total and .relationships
        assert result.total >= 1
        types = [r.rel_type for r in result.relationships]
        assert RelationshipType.KNOWS in types
