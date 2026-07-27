"""
Shared pytest fixtures for MONITOR end-to-end tests.

These tests exercise the full stack:
  - Real Neo4j (testcontainers)
  - Real MongoDB (testcontainers)
  - Folder-based object storage (MinIO folder backend)
  - In-memory Qdrant
  - Mocked LLM calls (Anthropic / DSPy modules)

Environment gates
-----------------
All tests in this package are marked ``e2e``.  Set ``RUN_E2E=1`` to run them.
Set ``RUN_INTEGRATION=1`` additionally to run DB-backed tests.

The session-scoped ``e2e_databases`` fixture starts Neo4j + MongoDB containers
and patches the data-layer settings singleton so every tool call in the session
hits the real containers instead of localhost defaults.

Use-case coverage
-----------------
See individual test files for use-case codes (DL-, P-, M-, Q-, I-, RS-, CF-, ST-).
"""

from __future__ import annotations

import os
import textwrap
from datetime import datetime, timezone, UTC
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from monitor_data.schemas.agent_responses import (
    CanonKeeperDecision,
    CanonKeeperVerdict,
    NarratorResponse,
    ProposedChangeRef,
)
from testcontainers.mongodb import MongoDbContainer
from testcontainers.neo4j import Neo4jContainer

# =============================================================================
# SESSION SETUP — Minimum env vars so Settings doesn't complain at import
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def e2e_env_bootstrap():
    """Set minimum env vars before any module imports."""
    os.environ.setdefault("NEO4J_PASSWORD", "test_password")
    os.environ.setdefault("MINIO_SECRET_KEY", "test_secret")
    os.environ.setdefault("ANTHROPIC_API_KEY", "test_key_e2e")
    os.environ.setdefault("STORAGE_BACKEND", "folder")
    os.environ.setdefault("LOCAL_STORAGE_PATH", "/tmp/monitor_e2e_storage")


# =============================================================================
# REAL DATABASE CONTAINERS  (session-scoped — start once, shared across tests)
# =============================================================================


@pytest.fixture(scope="session")
def neo4j_container():
    """Start a real Neo4j 5 container. Reused across all e2e tests."""
    with Neo4jContainer("neo4j:5") as container:
        yield container


@pytest.fixture(scope="session")
def mongodb_container():
    """Start a real MongoDB 7 container. Reused across all e2e tests."""
    with MongoDbContainer("mongo:7") as container:
        yield container


@pytest.fixture(scope="session")
def e2e_databases(neo4j_container, mongodb_container):
    """
    Wire real containers into the data-layer settings singleton.

    This fixture:
    1. Configures settings.neo4j_uri / .neo4j_password / .mongodb_uri
    2. Resets client singletons so they reconnect against containers
    3. Yields so tests run with live DB connections
    4. Resets singletons again on teardown
    """
    from monitor_data import config as cfg

    # --- patch settings attributes directly ---
    neo4j_bolt = neo4j_container.get_connection_url()
    neo4j_pwd = getattr(neo4j_container, "password", None) or os.environ.get(
        "NEO4J_PASSWORD", "password"
    )
    mongo_uri = mongodb_container.get_connection_url()

    old_neo4j_uri = cfg.settings.neo4j_uri
    old_neo4j_pwd = cfg.settings.neo4j_password
    old_mongo_uri = cfg.settings.mongodb_uri

    cfg.settings.neo4j_uri = neo4j_bolt
    cfg.settings.neo4j_password = neo4j_pwd
    cfg.settings.mongodb_uri = mongo_uri

    # also update env so any fresh Settings() picks them up
    os.environ["NEO4J_URI"] = neo4j_bolt
    os.environ["NEO4J_PASSWORD"] = neo4j_pwd
    os.environ["MONGODB_URI"] = mongo_uri

    # Reset singletons so first call reconnects with new URIs
    from monitor_data.db.mongodb import reset_mongodb_client
    from monitor_data.db.neo4j import reset_neo4j_client

    reset_neo4j_client()
    reset_mongodb_client()

    yield {
        "neo4j_bolt": neo4j_bolt,
        "neo4j_password": neo4j_pwd,
        "mongodb_uri": mongo_uri,
    }

    # restore
    cfg.settings.neo4j_uri = old_neo4j_uri
    cfg.settings.neo4j_password = old_neo4j_pwd
    cfg.settings.mongodb_uri = old_mongo_uri
    reset_neo4j_client()
    reset_mongodb_client()


# =============================================================================
# FOLDER-BASED OBJECT STORAGE  (no S3 needed)
# =============================================================================


@pytest.fixture(scope="session")
def tmp_storage_dir(tmp_path_factory):
    """Persistent temp dir for the entire e2e test session."""
    return tmp_path_factory.mktemp("e2e_storage")


@pytest.fixture(scope="session")
def folder_minio(tmp_storage_dir, e2e_env_bootstrap):
    """MinIOClient in folder mode — no S3 containers needed."""
    from monitor_data.db.minio import MinIOClient

    client = MinIOClient(
        backend="folder",
        local_path=str(tmp_storage_dir),
        bucket="monitor",
        fallback_to_local=False,
    )
    return client


# =============================================================================
# IN-MEMORY QDRANT
# =============================================================================


@pytest.fixture(scope="session")
def qdrant_memory_client():
    """
    QdrantClient in :memory: mode — no server needed.

    Returns the raw qdrant_client.QdrantClient so tests can create
    collections and upsert vectors without a running Qdrant server.
    """
    from qdrant_client import QdrantClient

    client = QdrantClient(":memory:")

    # Newer qdrant-client builds removed `.search()` in favor of `.query_points()`.
    # The E2E suite still exercises the older compatibility shape.
    if not hasattr(client, "search"):

        def _search(*, collection_name: str, query_vector, limit: int = 10, **kwargs):
            response = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                with_payload=kwargs.get("with_payload", True),
                with_vectors=kwargs.get("with_vectors", False),
            )
            return response.points

        client.search = _search  # type: ignore[attr-defined]

    return client


# =============================================================================
# SYNTHETIC RPG BOOK  — "Realm of Shadows: Core Rulebook"
# =============================================================================

RPG_BOOK_TEXT = textwrap.dedent("""
    REALM OF SHADOWS — CORE RULEBOOK
    =================================

    CHAPTER 1: THE WORLD
    --------------------
    The Realm of Shadows is a dark fantasy world where light and darkness wage
    eternal war. Magic is woven into the very fabric of reality — every living
    being can feel its pull. The gods are real and walk among mortals in disguise.
    The dead do not rest unless properly buried with the rites of the Old Faith.

    AXIOMS OF THE REALM
    - Magic exists and flows from the Void between worlds.
    - The dead rise as shades within 3 days if unburied.
    - Sunlight weakens creatures of darkness by half their power.
    - The Old Faith commands the rites of burial and communion.
    - The Iron Throne has ruled the known lands for three centuries.

    CHAPTER 2: HISTORY
    ------------------
    THE SHADOW WAR (Year 0 — Year 12):
    The ancient Shadow War began when the Void Cult opened a rift between
    worlds. For twelve years, armies of darkness swept across the Realm.
    The war ended when High Paladin Ryven sealed the rift with his own life.

    THE GREAT SUNDERING (Year 312):
    The kingdom of Valdros was split by a catastrophic magical surge. The
    eastern half became the cursed Ashlands, uninhabitable for mortal kind.

    CHAPTER 3: FACTIONS
    -------------------
    THE IRON THRONE: The ruling monarchy of the western Realm. Known for
    its iron-fisted law and deep distrust of unchecked magic. Led by King Aldric.

    THE OLD FAITH: Ancient religion worshipping the twin gods of Light and Dark.
    Their priests can command the dead and heal the living. High Priestess Mara.

    THE VOID CULT: A secretive organization seeking to reopen the rift. Their
    leader is known only as the Hollow King. They operate from the Ashlands.

    CHAPTER 4: CHARACTERS & ARCHETYPES
    ------------------------------------
    FIGHTER: Masters of physical combat. Start with heavy armor, swords.
    Attributes: Strength (primary), Constitution (secondary).
    Special: Extra attack at level 5.

    MAGE: Wielders of arcane power. Fragile but devastating.
    Attributes: Intelligence (primary), Wisdom (secondary).
    Special: Spellcasting (Fire, Ice, Lightning, Arcane).

    ROGUE: Shadows and subterfuge. Strike fast, vanish.
    Attributes: Dexterity (primary), Charisma (secondary).
    Special: Sneak Attack, Evasion.

    CHAPTER 5: DICE MECHANICS
    -------------------------
    All resolution uses a D20 system:
    - Roll 1d20 + relevant modifier vs Difficulty Class (DC).
    - DC 10: Easy task. DC 15: Moderate. DC 20: Hard. DC 25: Epic.
    - Roll of 1 = Critical Failure. Roll of 20 = Critical Success.
    - Modifiers come from attributes: MOD = floor((ATTR - 10) / 2).
    - Proficiency bonus starts at +2 and increases at levels 5, 9, 13, 17.

    ATTRIBUTES: Strength, Dexterity, Constitution, Intelligence, Wisdom, Charisma.
    Start at 10 each. Character creation gives 27 points to distribute.

    SKILLS (linked attribute in parentheses):
    Athletics (Strength), Acrobatics (Dexterity), Stealth (Dexterity),
    Arcana (Intelligence), History (Intelligence), Perception (Wisdom),
    Insight (Wisdom), Persuasion (Charisma), Deception (Charisma).

    CHAPTER 6: LOCATIONS
    --------------------
    CASTLE IRONHOLD: The capital fortress of the Iron Throne. Sits atop a
    volcanic cliff. Home to King Aldric and his court. Impregnable walls.

    FOREST OF WHISPERS: Ancient woodland to the north. Home to elves and
    fae creatures. The trees speak at midnight in the Old Tongue.

    MARKET TOWN OF DUSK: The largest trade hub in the Realm. Crime-ridden
    but prosperous. The Void Cult has deep roots here.

    THE ASHLANDS: Cursed eastern wasteland from the Great Sundering. Void
    rifts dot the landscape. Only the Void Cult dares reside here.

    CHAPTER 7: SAMPLE ADVENTURE — THE HOLLOW CONSPIRACY
    ---------------------------------------------------
    The king's youngest son has gone missing. Rumours place him in the
    Ashlands. The Iron Throne offers a 1000 gold reward for his safe return.
    The Void Cult is involved. High Priestess Mara knows more than she admits.

    CHAPTER 8: COMBAT
    -----------------
    Initiative: Each participant rolls 1d20 + DEX modifier. Highest acts first.
    Attack: Roll 1d20 + STR/DEX modifier vs target's Armor Class (AC).
    AC = 10 + DEX modifier (light armor) or 12-18 (medium/heavy armor).
    Damage: Weapon die + modifier. Sword 1d8+STR. Dagger 1d4+DEX.
""").strip()

RPG_BOOK_BYTES = RPG_BOOK_TEXT.encode("utf-8")


@pytest.fixture(scope="session")
def rpg_book_text() -> str:
    """Synthetic RPG rulebook as plain text."""
    return RPG_BOOK_TEXT


@pytest.fixture(scope="session")
def rpg_book_bytes() -> bytes:
    """Synthetic RPG rulebook encoded as UTF-8 bytes."""
    return RPG_BOOK_BYTES


# =============================================================================
# WORLD SEED DATA  (shared fixture for all world/play tests)
# =============================================================================

WORLD_NAME = "Realm of Shadows"
SYSTEM_NAME = "Realm of Shadows D20"


@pytest.fixture(scope="session")
def seeded_world(e2e_databases):
    """
    Create a fully populated Realm of Shadows world in Neo4j.

    Returns a dict with all created IDs so downstream tests don't need
    to repeat the creation steps.

    Covers: DL-1 (Omniverse/Multiverse/Universe), DL-2 (Entities), DL-3 (Facts/Axioms/Events)
    """
    from datetime import datetime
    from datetime import timezone as _tz

    from monitor_data.schemas.base import (
        Authority,
        AxiomAuthority,
        CanonLevel,
        EntityType,
        KnowledgeTreeType,
    )
    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.schemas.facts import (
        AxiomCreate,
        EventCreate,
        FactCreate,
        FactType,
    )
    from monitor_data.schemas.universe import (
        MultiverseCreate,
        UniverseCreate,
    )
    from monitor_data.tools.neo4j_tools import (
        neo4j_create_axiom,
        neo4j_create_entity,
        neo4j_create_event,
        neo4j_create_fact,
        neo4j_create_multiverse,
        neo4j_create_universe,
        neo4j_ensure_omniverse,
    )

    # --- Omniverse (root) — returns dict with omniverse_id key
    omni_info = neo4j_ensure_omniverse()
    omniverse_id = UUID(omni_info["omniverse_id"])

    # --- Multiverse (game system container)
    multiverse = neo4j_create_multiverse(
        MultiverseCreate(
            omniverse_id=omniverse_id,
            name="Realm of Shadows Multiverse",
            system_name=SYSTEM_NAME,
            description="The dark fantasy world of Realm of Shadows.",
            knowledge_tree_type=KnowledgeTreeType.DYNAMIC,
        )
    )

    # --- Universe (the playable world)
    universe = neo4j_create_universe(
        UniverseCreate(
            multiverse_id=multiverse.id,
            name=WORLD_NAME,
            description="Primary timeline of the Realm of Shadows setting.",
            genre="dark_fantasy",
            tone="grim",
            tech_level="medieval",
        )
    )
    uid = universe.id

    # --- Axioms (ontological truths)
    axiom_magic = neo4j_create_axiom(
        AxiomCreate(
            universe_id=uid,
            statement="Magic exists and flows from the Void between worlds.",
            domain="magic",
            authority=AxiomAuthority.PHYSICS,
            canon_level=CanonLevel.CANON,
        )
    )
    axiom_dead = neo4j_create_axiom(
        AxiomCreate(
            universe_id=uid,
            statement="The dead rise as shades within 3 days if unburied.",
            domain="undead",
            authority=AxiomAuthority.PHYSICS,
            canon_level=CanonLevel.CANON,
        )
    )
    axiom_gods = neo4j_create_axiom(
        AxiomCreate(
            universe_id=uid,
            statement="The gods are real and walk among mortals in disguise.",
            domain="religion",
            authority=AxiomAuthority.METAPHYSICS,
            canon_level=CanonLevel.CANON,
        )
    )

    # --- Historical Events
    event_shadow_war = neo4j_create_event(
        EventCreate(
            universe_id=uid,
            title="The Shadow War",
            description="Twelve-year war against the Void Cult ended by High Paladin Ryven.",
            start_time=datetime(1, 1, 1, tzinfo=UTC),  # Year 0 fiction
            end_time=datetime(12, 1, 1, tzinfo=UTC),  # Year 12 fiction
            authority=Authority.SOURCE,
            canon_level=CanonLevel.CANON,
        )
    )
    event_sundering = neo4j_create_event(
        EventCreate(
            universe_id=uid,
            title="The Great Sundering",
            description="Catastrophic magical surge that split Valdros and created the Ashlands.",
            start_time=datetime(312, 1, 1, tzinfo=UTC),
            authority=Authority.SOURCE,
            canon_level=CanonLevel.CANON,
        )
    )

    # --- Entity Archetypes (character classes)
    arch_fighter = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="Fighter",
            entity_type=EntityType.CHARACTER,
            is_archetype=True,
            description="Master of physical combat. Heavy armor, swords.",
            properties={
                "primary_attr": "Strength",
                "secondary_attr": "Constitution",
                "special": "Extra attack at level 5",
            },
        )
    )
    arch_mage = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="Mage",
            entity_type=EntityType.CHARACTER,
            is_archetype=True,
            description="Wielder of arcane power. Fragile but devastating.",
            properties={
                "primary_attr": "Intelligence",
                "secondary_attr": "Wisdom",
                "special": "Spellcasting",
            },
        )
    )
    arch_rogue = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="Rogue",
            entity_type=EntityType.CHARACTER,
            is_archetype=True,
            description="Shadow and subterfuge specialist.",
            properties={
                "primary_attr": "Dexterity",
                "secondary_attr": "Charisma",
                "special": "Sneak Attack, Evasion",
            },
        )
    )

    # --- Faction Archetypes
    arch_iron_throne = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="Iron Throne",
            entity_type=EntityType.FACTION,
            is_archetype=True,
            description="Ruling monarchy of the western Realm.",
            properties={"alignment": "lawful neutral", "leader": "King Aldric"},
        )
    )
    arch_old_faith = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="Old Faith",
            entity_type=EntityType.FACTION,
            is_archetype=True,
            description="Ancient religion worshipping the twin gods of Light and Dark.",
            properties={"alignment": "neutral", "leader": "High Priestess Mara"},
        )
    )
    arch_void_cult = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="Void Cult",
            entity_type=EntityType.FACTION,
            is_archetype=True,
            description="Secretive organization seeking to reopen the Void rift.",
            properties={"alignment": "chaotic evil", "leader": "The Hollow King"},
        )
    )

    # --- Location Archetypes
    arch_castle = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="Castle Ironhold",
            entity_type=EntityType.LOCATION,
            is_archetype=True,
            description="Capital fortress of the Iron Throne. Sits atop a volcanic cliff.",
            properties={"region": "western_realm", "ruler": "King Aldric"},
        )
    )
    arch_forest = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="Forest of Whispers",
            entity_type=EntityType.LOCATION,
            is_archetype=True,
            description="Ancient woodland to the north. Home to elves and fae creatures.",
            properties={"region": "northern_realm", "inhabitants": "elves, fae"},
        )
    )

    # --- Specific NPC Instances
    npc_king = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="King Aldric",
            entity_type=EntityType.CHARACTER,
            is_archetype=False,
            description="Ruler of the Iron Throne. Stern and just.",
            archetype_id=arch_iron_throne.id,
            properties={
                "title": "King",
                "faction": "Iron Throne",
                "attributes": {
                    "Strength": 14,
                    "Dexterity": 10,
                    "Constitution": 16,
                    "Intelligence": 14,
                    "Wisdom": 16,
                    "Charisma": 18,
                },
            },
        )
    )
    npc_priestess = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="High Priestess Mara",
            entity_type=EntityType.CHARACTER,
            is_archetype=False,
            description="Senior priest of the Old Faith. Commands ancient rites.",
            archetype_id=arch_old_faith.id,
            properties={
                "title": "High Priestess",
                "faction": "Old Faith",
                "attributes": {
                    "Strength": 8,
                    "Dexterity": 12,
                    "Constitution": 12,
                    "Intelligence": 16,
                    "Wisdom": 20,
                    "Charisma": 14,
                },
            },
        )
    )

    # --- Player Character
    pc_hero = neo4j_create_entity(
        EntityCreate(
            universe_id=uid,
            name="Aldric the Bold",
            entity_type=EntityType.CHARACTER,
            is_archetype=False,
            description="A wandering fighter seeking the truth about the Void Cult.",
            archetype_id=arch_fighter.id,
            state_tags=["alive", "healthy", "armed"],
            properties={
                "class": "Fighter",
                "level": 3,
                "attributes": {
                    "Strength": 16,
                    "Dexterity": 12,
                    "Constitution": 14,
                    "Intelligence": 10,
                    "Wisdom": 10,
                    "Charisma": 10,
                },
                "inventory": ["longsword", "chainmail", "shield", "rations x5"],
                "hp": {"current": 28, "max": 28},
            },
        )
    )

    # --- World Facts
    fact_throne_rule = neo4j_create_fact(
        FactCreate(
            universe_id=uid,
            statement="The Iron Throne has ruled the known lands for three centuries.",
            fact_type=FactType.STATE,
            authority=Authority.SOURCE,
            canon_level=CanonLevel.CANON,
        )
    )
    fact_hollow_king = neo4j_create_fact(
        FactCreate(
            universe_id=uid,
            statement="The Hollow King seeks to reopen the Void rift.",
            fact_type=FactType.STATE,
            authority=Authority.SOURCE,
            canon_level=CanonLevel.CANON,
        )
    )

    return {
        "omniverse_id": omniverse_id,
        "multiverse_id": multiverse.id,
        "universe_id": uid,
        # axioms
        "axiom_magic_id": axiom_magic.id,
        "axiom_dead_id": axiom_dead.id,
        "axiom_gods_id": axiom_gods.id,
        # events
        "event_shadow_war_id": event_shadow_war.id,
        "event_sundering_id": event_sundering.id,
        # archetypes
        "arch_fighter_id": arch_fighter.id,
        "arch_mage_id": arch_mage.id,
        "arch_rogue_id": arch_rogue.id,
        "arch_iron_throne_id": arch_iron_throne.id,
        "arch_old_faith_id": arch_old_faith.id,
        "arch_void_cult_id": arch_void_cult.id,
        "arch_castle_id": arch_castle.id,
        "arch_forest_id": arch_forest.id,
        # instances
        "npc_king_id": npc_king.id,
        "npc_priestess_id": npc_priestess.id,
        "pc_hero_id": pc_hero.id,
        # facts
        "fact_throne_rule_id": fact_throne_rule.id,
        "fact_hollow_king_id": fact_hollow_king.id,
    }


# =============================================================================
# GAME SYSTEM FIXTURE
# =============================================================================


@pytest.fixture(scope="session")
def seeded_game_system(e2e_databases):
    """
    Create and return the Realm of Shadows D20 game system in MongoDB.

    Covers: RS-1..RS-4 (DL-20 game systems)
    """
    from monitor_data.schemas.game_systems import (
        AttributeDefinition,
        CoreMechanic,
        CoreMechanicType,
        GameRule,
        GameRuleType,
        GameSystemCreate,
        SkillDefinition,
        SuccessType,
    )
    from monitor_data.tools.mongodb_tools import mongodb_create_game_system

    params = GameSystemCreate(
        name=SYSTEM_NAME,
        version="1.0",
        description="D20-based system for the Realm of Shadows RPG.",
        core_mechanic=CoreMechanic(
            type=CoreMechanicType.D20,
            formula="1d20 + MOD vs DC",
            success_type=SuccessType.MEET_OR_BEAT,
            critical_success="Natural 20",
            critical_failure="Natural 1",
        ),
        attributes=[
            AttributeDefinition(
                name="Strength",
                abbreviation="STR",
                description="Physical power.",
                default_value=10,
                min_value=1,
                max_value=20,
                modifier_formula="floor((value - 10) / 2)",
            ),
            AttributeDefinition(
                name="Dexterity",
                abbreviation="DEX",
                description="Agility and reflexes.",
                default_value=10,
                min_value=1,
                max_value=20,
                modifier_formula="floor((value - 10) / 2)",
            ),
            AttributeDefinition(
                name="Constitution",
                abbreviation="CON",
                description="Endurance and health.",
                default_value=10,
                min_value=1,
                max_value=20,
                modifier_formula="floor((value - 10) / 2)",
            ),
            AttributeDefinition(
                name="Intelligence",
                abbreviation="INT",
                description="Reasoning and memory.",
                default_value=10,
                min_value=1,
                max_value=20,
                modifier_formula="floor((value - 10) / 2)",
            ),
            AttributeDefinition(
                name="Wisdom",
                abbreviation="WIS",
                description="Perception and intuition.",
                default_value=10,
                min_value=1,
                max_value=20,
                modifier_formula="floor((value - 10) / 2)",
            ),
            AttributeDefinition(
                name="Charisma",
                abbreviation="CHA",
                description="Social force of personality.",
                default_value=10,
                min_value=1,
                max_value=20,
                modifier_formula="floor((value - 10) / 2)",
            ),
        ],
        skills=[
            SkillDefinition(name="Athletics", linked_attribute="Strength"),
            SkillDefinition(name="Acrobatics", linked_attribute="Dexterity"),
            SkillDefinition(name="Stealth", linked_attribute="Dexterity"),
            SkillDefinition(name="Arcana", linked_attribute="Intelligence"),
            SkillDefinition(name="History", linked_attribute="Intelligence"),
            SkillDefinition(name="Perception", linked_attribute="Wisdom"),
            SkillDefinition(name="Insight", linked_attribute="Wisdom"),
            SkillDefinition(name="Persuasion", linked_attribute="Charisma"),
            SkillDefinition(name="Deception", linked_attribute="Charisma"),
        ],
        rules=[
            GameRule(
                name="Initiative",
                rule_type=GameRuleType.COMBAT,
                description="Roll 1d20 + DEX modifier. Highest acts first.",
            ),
            GameRule(
                name="Attack Roll",
                rule_type=GameRuleType.COMBAT,
                description="Roll 1d20 + STR/DEX modifier vs target AC.",
                formula="1d20 + STR_MOD vs AC",
            ),
            GameRule(
                name="Armor Class",
                rule_type=GameRuleType.CORE,
                description="AC = 10 + DEX modifier (light). Medium: 12+. Heavy: 18.",
                formula="10 + floor((DEX - 10) / 2)",
            ),
            GameRule(
                name="Proficiency Bonus",
                rule_type=GameRuleType.CORE,
                description="Starts at +2. Increases at levels 5, 9, 13, 17.",
            ),
        ],
        # [G-8] Provenance gate — this e2e fixture builds the system
        # directly (no ingestion path), so use the hand_authored path.
        hand_authored=True,
    )

    game_system = mongodb_create_game_system(params)
    return game_system


# =============================================================================
# STORY / SCENE FIXTURES  (function-scoped — fresh per test)
# =============================================================================


@pytest.fixture
def e2e_story(seeded_world, e2e_databases):
    """Create a fresh Story node for an e2e test turn."""
    from monitor_data.schemas.base import StoryStatus, StoryType
    from monitor_data.schemas.stories import StoryCreate
    from monitor_data.tools.neo4j_tools import neo4j_create_story

    story = neo4j_create_story(
        StoryCreate(
            universe_id=seeded_world["universe_id"],
            title="The Hollow Conspiracy",
            story_type=StoryType.CAMPAIGN,
            theme="conspiracy, darkness, duty",
            premise="The king's son is missing. The Void Cult is involved.",
            status=StoryStatus.ACTIVE,
            pc_ids=[seeded_world["pc_hero_id"]],
        )
    )
    return story


@pytest.fixture
def e2e_scene(e2e_story, seeded_world, e2e_databases):
    """Create a fresh Scene document for an e2e test turn."""
    from monitor_data.schemas.scenes import SceneCreate
    from monitor_data.tools.mongodb_tools import mongodb_create_scene

    scene = mongodb_create_scene(
        SceneCreate(
            story_id=e2e_story.id,
            universe_id=e2e_story.universe_id,
            title="The Market of Dusk — First Contact",
            purpose="The hero arrives at the Market Town of Dusk and follows the first lead.",
            narrative_order=1,
            participating_entities=[seeded_world["pc_hero_id"]],
        )
    )
    return scene


# =============================================================================
# LLM MOCK HELPERS
# =============================================================================


def make_narrator_response(narrative: str | None = None) -> NarratorResponse:
    """Build a canned NarratorResponse for LLM mocking."""
    proposal_id = uuid4()
    return NarratorResponse(
        narrative_text=(
            narrative
            or "The cobblestone streets of Dusk bustle with merchants and grey-cloaked figures. "
            "A hooded stranger catches your eye and nods towards a shadowed alley. "
            "The stench of fish and unwashed bodies mixes with the faint smell of brimstone."
        ),
        proposals=[
            ProposedChangeRef(
                proposal_id=proposal_id,
                change_type="entity",
                summary="A mysterious stranger appears in the Market of Dusk.",
                content={
                    "entity_type": "Character",
                    "name": "Hooded Stranger",
                    "properties": {"alignment": "unknown", "faction": "Void Cult"},
                },
            )
        ],
        mood="tense",
    )


def make_canonkeeper_verdict(
    proposal_id: str | UUID,
    decision: CanonKeeperDecision = CanonKeeperDecision.ACCEPTED,
) -> CanonKeeperVerdict:
    """Build a canned CanonKeeperVerdict for LLM mocking."""
    return CanonKeeperVerdict(
        proposal_id=UUID(str(proposal_id)),
        decision=decision,
        reasoning="No canon contradictions found. The stranger is a new entity consistent with lore.",
        canon_node_type="EntityInstance",
        canon_properties={
            "name": "Hooded Stranger",
            "entity_type": "Character",
            "properties": {"faction": "Void Cult"},
        },
        decided_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_narrator_llm():
    """
    Patch BaseAgent.call_llm_structured to return a canned NarratorResponse.
    """
    with patch(
        "monitor_agents.base.BaseAgent.call_llm_structured",
        new_callable=AsyncMock,
        return_value=make_narrator_response(),
    ) as m:
        yield m


@pytest.fixture
def mock_canonkeeper_llm():
    """
    Patch CanonKeeper's LLM and DSPy modules to accept all proposals.
    """
    policy_ok = MagicMock()
    policy_ok.violation_found = "NO"
    policy_ok.violation_detail = "none"

    reasoning_ok = MagicMock()
    reasoning_ok.reasoning = "No contradiction detected. ACCEPT."

    with (
        patch(
            "monitor_agents.canonkeeper.canonkeeper.PolicyCheckModule.__call__",
            return_value=policy_ok,
        ),
        patch(
            "monitor_agents.canonkeeper.canonkeeper.CanonKeeperReasoningModule.__call__",
            return_value=reasoning_ok,
        ),
        patch(
            "monitor_agents.base.BaseAgent.call_llm_structured",
            new_callable=AsyncMock,
        ) as verdict_mock,
    ):
        # Each call to call_llm_structured returns a fresh verdict accepting the call
        verdict_mock.side_effect = lambda schema, messages, **kw: (
            make_canonkeeper_verdict(
                uuid4()
            )
        )
        yield verdict_mock


@pytest.fixture
def mock_dspy_narrator():
    """Patch DSPy NarratorModule to return a canned prose prediction."""
    prediction = MagicMock()
    prediction.narrative_text = (
        "The cobblestone streets of Dusk bustle with merchants and grey-cloaked figures. "
        "A hooded stranger nods towards a shadowed alley."
    )
    # One proposed change so the canonization checkpoint has work to do
    # (finalize short-circuits when pending_proposals is empty).
    prediction.proposed_changes = (
        '[{"change_type": "fact_added", "payload": '
        '{"statement": "A hooded stranger frequents the Dusk alleys."}, '
        '"reason": "Introduced during narration."}]'
    )
    with patch(
        "monitor_agents.narrator.narrator.NarratorModule.__call__",
        return_value=prediction,
    ):
        yield


@pytest.fixture
def mock_context_assembly():
    """
    Patch ContextAssembly.assemble() to return an empty but valid context.
    Prevents tests from hitting real Qdrant or missing data.
    """
    from monitor_agents.context_assembly.agent import ContextAssembly

    empty_context: dict[str, Any] = {"entities": [], "memories": [], "turns": []}

    with (
        patch.object(
            ContextAssembly,
            "assemble",
            new_callable=AsyncMock,
            return_value=empty_context,
        ),
        patch.object(
            ContextAssembly,
            "retrieve_turn_context",
            new_callable=AsyncMock,
            return_value={"memories": []},
        ),
    ):
        yield


@pytest.fixture
def mock_resolver():
    """Patch Resolver.resolve_turn() to return a deterministic outcome."""
    from monitor_agents.resolver import Resolver

    resolution = {
        "success_level": "success",
        "roll_total": 16,
        "roll_breakdown": "1d20+3 = 13+3 = 16",
        "effects": [],
        "proposals": [],
    }

    with patch.object(
        Resolver,
        "resolve_turn",
        new_callable=AsyncMock,
        return_value=resolution,
    ):
        yield


@pytest.fixture
def mock_narrator_persist_turn():
    """Patch Narrator._persist_turn to avoid MongoDB turn write during testing."""
    from monitor_agents.narrator.agent import Narrator

    with patch.object(
        Narrator,
        "_persist_turn",
        new_callable=AsyncMock,
        return_value=str(uuid4()),
    ):
        yield
