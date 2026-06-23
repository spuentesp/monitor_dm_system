"""Tests for NPCProfile CRUD operations in MongoDB tools."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from monitor_data.schemas.npc_profiles import (
    NPCProfileCreate,
    NPCProfileUpdate,
    EmotionalTendency,
    CharacterPreference,
    BehavioralTrigger,
)


# =============================================================================
# FAKE MONGODB IMPLEMENTATION
# =============================================================================


class _FakeProfilesCollection:
    """Fake MongoDB collection for NPC profiles."""

    def __init__(self):
        self.profiles = {}

    def find_one(self, query):
        if "entity_id" in query:
            for profile in self.profiles.values():
                if profile["entity_id"] == query["entity_id"]:
                    return profile
        if "profile_id" in query:
            return self.profiles.get(query["profile_id"])
        return None

    def insert_one(self, doc):
        self.profiles[doc["profile_id"]] = doc

    def update_one(self, query, update):
        if "entity_id" in query:
            entity_id = query["entity_id"]
            for profile_id, profile in self.profiles.items():
                if profile["entity_id"] == entity_id:
                    for key, value in update.get("$set", {}).items():
                        self.profiles[profile_id][key] = value
                    return type("UpdateResult", (), {"matched_count": 1})()
        return type("UpdateResult", (), {"matched_count": 0})()


class _FakeNeo4jClient:
    """Fake Neo4j client for entity verification."""

    def __init__(self, entity_exists=True):
        self.entity_exists = entity_exists

    def execute_read(self, query, params):
        if self.entity_exists:
            return [{"id": params.get("entity_id", str(uuid4()))}]
        return []


class _FakeMongoClient:
    """Fake MongoDB client."""

    def __init__(self):
        self.profiles_db = _FakeProfilesCollection()

    def __getitem__(self, name):
        if name == "npc_profiles":
            return self.profiles_db
        return _FakeProfilesCollection()


# =============================================================================
# mongodb_create_npc_profile TESTS
# =============================================================================


def test_create_npc_profile_basic(monkeypatch):
    """Test creating an NPC profile with basic fields."""
    entity_id = uuid4()

    # Mock clients
    fake_neo4j = _FakeNeo4jClient(entity_exists=True)
    fake_mongo = _FakeMongoClient()

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: fake_neo4j,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_create_npc_profile

    result = mongodb_create_npc_profile(
        NPCProfileCreate(
            entity_id=entity_id,
            speech_style="measured and careful",
            current_emotional_state="guarded",
        )
    )

    assert result.entity_id == entity_id
    assert result.speech_style == "measured and careful"
    assert result.current_emotional_state == "guarded"
    assert result.profile_id is not None


def test_create_npc_profile_with_detailed_fields(monkeypatch):
    """Test creating an NPC profile with all detailed fields."""
    entity_id = uuid4()

    # Mock clients
    fake_neo4j = _FakeNeo4jClient(entity_exists=True)
    fake_mongo = _FakeMongoClient()

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: fake_neo4j,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_create_npc_profile

    result = mongodb_create_npc_profile(
        NPCProfileCreate(
            entity_id=entity_id,
            traits={"openness": 0.8, "conscientiousness": 0.3},
            values=["honor", "family"],
            fears=["betrayal", "death"],
            desires=["recognition", "peace"],
            speech_style="formal and verbose",
            catchphrases=["By my word", "Honor demands it"],
            mannerisms=["tugs ear when lying", "never makes eye contact"],
            emotional_tendencies=[
                EmotionalTendency(emotion="anger", baseline=0.3, volatility=0.7),
                EmotionalTendency(emotion="joy", baseline=0.5, volatility=0.3),
            ],
            preferences=[
                CharacterPreference(
                    category="food", item="hearty stew", valence=0.8, reason="comfort food"
                ),
                CharacterPreference(category="people", item="honest folk", valence=0.9),
            ],
            triggers=[
                BehavioralTrigger(
                    condition="asked about thieves guild", reaction="becomes evasive", intensity=0.7
                ),
            ],
            secrets=["secretly works for the enemy", "has a hidden family"],
            gm_notes="Complex antagonist with redeeming qualities",
            current_emotional_state="conflicted",
            relationship_states={str(uuid4()): {"sentiment": "trust", "score": 0.5}},
        )
    )

    assert result.entity_id == entity_id
    assert result.traits["openness"] == 0.8
    assert len(result.values) == 2
    assert len(result.emotional_tendencies) == 2
    assert len(result.preferences) == 2
    assert len(result.secrets) == 2
    assert result.gm_notes == "Complex antagonist with redeeming qualities"


def test_create_npc_profile_duplicate_raises_error(monkeypatch):
    """Test creating a duplicate NPC profile raises ValueError."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Mock clients
    fake_neo4j = _FakeNeo4jClient(entity_exists=True)
    fake_mongo = _FakeMongoClient()

    # Pre-populate with existing profile
    now = datetime.now(timezone.utc)
    fake_mongo.profiles_db.profiles[str(profile_id)] = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {"openness": 0.2},
        "values": ["loyalty"],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: fake_neo4j,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_create_npc_profile

    with pytest.raises(ValueError, match="already exists"):
        mongodb_create_npc_profile(
            NPCProfileCreate(
                entity_id=entity_id,
                speech_style="quiet",
            )
        )


def test_create_npc_profile_entity_not_found_raises_error(monkeypatch):
    """Test creating a profile for non-existent entity raises ValueError."""
    entity_id = uuid4()

    # Mock clients
    fake_neo4j = _FakeNeo4jClient(entity_exists=False)
    fake_mongo = _FakeMongoClient()

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: fake_neo4j,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_create_npc_profile

    with pytest.raises(ValueError, match="not found"):
        mongodb_create_npc_profile(
            NPCProfileCreate(
                entity_id=entity_id,
                speech_style="quiet",
            )
        )


# =============================================================================
# mongodb_get_npc_profile TESTS
# =============================================================================


def test_get_npc_profile_found(monkeypatch):
    """Test getting an existing NPC profile."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {"openness": 0.2},
        "values": ["loyalty"],
        "fears": ["betrayal"],
        "desires": ["belonging"],
        "speech_style": "quiet",
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": "guarded",
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_get_npc_profile

    result = mongodb_get_npc_profile(entity_id)

    assert result is not None
    assert result.profile_id == profile_id
    assert result.entity_id == entity_id
    assert result.current_emotional_state == "guarded"


def test_get_npc_profile_not_found_returns_none(monkeypatch):
    """Test getting a non-existent NPC profile returns None."""
    entity_id = uuid4()

    # Mock MongoDB client with empty collection
    fake_mongo = _FakeMongoClient()

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_get_npc_profile

    result = mongodb_get_npc_profile(entity_id)

    assert result is None


# =============================================================================
# mongodb_update_npc_profile TESTS
# =============================================================================


def test_update_npc_profile_basic(monkeypatch):
    """Test updating an NPC profile with basic fields."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {"openness": 0.2},
        "values": ["loyalty"],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": "guarded",
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            current_emotional_state="warmer",
            speech_style="more open",
        ),
    )

    assert result.current_emotional_state == "warmer"
    assert result.speech_style == "more open"
    assert result.values == ["loyalty"]  # Unchanged


def test_update_npc_profile_with_all_fields(monkeypatch):
    """Test updating an NPC profile with all fields."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {"openness": 0.2},
        "values": ["loyalty"],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            traits={"openness": 0.7, "conscientiousness": 0.5},
            values=["honor", "family", "freedom"],
            fears=["betrayal", "chaos"],
            desires=["recognition", "peace"],
            speech_style="formal and verbose",
            catchphrases=["By my word"],
            mannerisms=["tugs ear"],
            emotional_tendencies=[
                EmotionalTendency(emotion="anger", baseline=0.3, volatility=0.7),
            ],
            preferences=[
                CharacterPreference(category="food", item="hearty stew", valence=0.8),
            ],
            triggers=[
                BehavioralTrigger(
                    condition="asked about thieves guild", reaction="becomes evasive"
                ),
            ],
            secrets=["secret identity"],
            gm_notes="Updated notes",
            current_emotional_state="conflicted",
            relationship_states={str(uuid4()): {"sentiment": "trust"}},
        ),
    )

    assert result.traits["openness"] == 0.7
    assert len(result.values) == 3
    assert result.speech_style == "formal and verbose"
    assert len(result.secrets) == 1
    assert result.gm_notes == "Updated notes"


def test_update_npc_profile_upserts_when_not_exists(monkeypatch):
    """Test updating NPC profile creates it when it doesn't exist (upsert)."""
    entity_id = uuid4()

    # Mock MongoDB client with empty collection
    fake_mongo = _FakeMongoClient()

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            speech_style="terse military clipped",
            current_emotional_state="stern",
        ),
    )

    assert result.entity_id == entity_id
    assert result.speech_style == "terse military clipped"
    assert result.current_emotional_state == "stern"
    assert result.profile_id is not None


def test_update_npc_profile_with_add_preference(monkeypatch):
    """Test updating NPC profile with add_preference appends to list."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile with one preference
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [{"category": "food", "item": "bread", "valence": 0.5, "reason": "staple"}],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            add_preference=CharacterPreference(
                category="food",
                item="hearty stew",
                valence=0.9,
                reason="comfort food",
            ),
        ),
    )

    assert len(result.preferences) == 2
    assert result.preferences[0].item == "bread"
    assert result.preferences[1].item == "hearty stew"
    assert result.preferences[1].valence == 0.9


def test_update_npc_profile_with_add_trigger(monkeypatch):
    """Test updating NPC profile with add_trigger appends to list."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile with one trigger
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [
            {
                "condition": "mention of past",
                "reaction": "becomes sad",
                "intensity": 0.5,
                "is_hidden": True,
            }
        ],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            add_trigger=BehavioralTrigger(
                condition="asked about thieves guild",
                reaction="becomes evasive",
                intensity=0.8,
            ),
        ),
    )

    assert len(result.triggers) == 2
    assert result.triggers[0].condition == "mention of past"
    assert result.triggers[1].condition == "asked about thieves guild"
    assert result.triggers[1].intensity == 0.8


def test_update_npc_profile_with_add_secret(monkeypatch):
    """Test updating NPC profile with add_secret appends to list."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile with one secret
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": ["secretly works for the enemy"],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            add_secret="has a hidden family",
        ),
    )

    assert len(result.secrets) == 2
    assert result.secrets[0] == "secretly works for the enemy"
    assert result.secrets[1] == "has a hidden family"


def test_update_npc_profile_merges_relationship_states(monkeypatch):
    """Test updating NPC profile merges relationship states."""
    entity_id = uuid4()
    profile_id = uuid4()
    target_id_1 = uuid4()
    target_id_2 = uuid4()

    # Create existing profile with one relationship
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": "guarded",
        "relationship_states": {str(target_id_1): {"sentiment": "trust", "score": 0.3}},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            current_emotional_state="warmer",
            relationship_states={
                str(target_id_1): {"score": 0.5},  # Update existing
                str(target_id_2): {"sentiment": "trust", "score": 0.35},  # Add new
            },
        ),
    )

    assert result.current_emotional_state == "warmer"
    assert len(result.relationship_states) == 2
    assert result.relationship_states[str(target_id_1)]["score"] == 0.5
    assert result.relationship_states[str(target_id_1)]["sentiment"] == "trust"  # Merged


def test_update_npc_profile_replaces_catchphrases(monkeypatch):
    """Test updating NPC profile with catchphrases replaces (not appends) to list."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile with one catchphrase
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": ["By my word"],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            catchphrases=["Honor demands it", "For the king"],
        ),
    )

    assert len(result.catchphrases) == 2
    assert result.catchphrases == ["Honor demands it", "For the king"]


def test_update_npc_profile_replaces_mannerisms(monkeypatch):
    """Test updating NPC profile with mannerisms replaces (not appends) to list."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile with one mannerism
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": ["tugs ear when lying"],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            mannerisms=["never makes eye contact", "paces when thinking"],
        ),
    )

    assert len(result.mannerisms) == 2
    assert result.mannerisms == ["never makes eye contact", "paces when thinking"]


def test_update_npc_profile_replaces_emotional_tendencies(monkeypatch):
    """Test updating NPC profile with emotional_tendencies replaces (not appends) to list."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile with one emotional tendency
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [{"emotion": "anger", "baseline": 0.3, "volatility": 0.7}],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            emotional_tendencies=[
                EmotionalTendency(emotion="joy", baseline=0.5, volatility=0.3),
                EmotionalTendency(emotion="fear", baseline=0.2, volatility=0.6),
            ],
        ),
    )

    assert len(result.emotional_tendencies) == 2
    assert result.emotional_tendencies[0].emotion == "joy"
    assert result.emotional_tendencies[1].emotion == "fear"


def test_update_npc_profile_clears_secrets(monkeypatch):
    """Test updating NPC profile with empty secrets list clears secrets."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile with secrets
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": ["secret identity", "hidden family"],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            secrets=[],
        ),
    )

    assert len(result.secrets) == 0


def test_update_npc_profile_partial_relationship_states_adds_only_specified(monkeypatch):
    """Test updating NPC profile with partial relationship_states adds only specified relationships (existing ones unchanged)."""
    entity_id = uuid4()
    profile_id = uuid4()
    target_id_1 = uuid4()
    target_id_2 = uuid4()
    target_id_3 = uuid4()

    # Create existing profile with two relationships
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {
            str(target_id_1): {"sentiment": "trust", "score": 0.5},
            str(target_id_2): {"sentiment": "suspicion", "score": 0.2},
        },
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            relationship_states={
                str(target_id_2): {"score": 0.3},  # Update existing
                str(target_id_3): {"sentiment": "admiration", "score": 0.7},  # Add new
            },
        ),
    )

    # Should have 3 relationships (target_id_1 unchanged, target_id_2 updated, target_id_3 added)
    assert len(result.relationship_states) == 3
    assert result.relationship_states[str(target_id_1)]["score"] == 0.5  # Unchanged
    assert result.relationship_states[str(target_id_2)]["score"] == 0.3  # Updated
    assert (
        result.relationship_states[str(target_id_2)]["sentiment"] == "suspicion"
    )  # Merged (kept original)
    assert result.relationship_states[str(target_id_3)]["sentiment"] == "admiration"  # New added


def test_update_npc_profile_traits_only(monkeypatch):
    """Test updating NPC profile with only traits field."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {"openness": 0.2, "conscientiousness": 0.3},
        "values": ["loyalty"],
        "fears": ["betrayal"],
        "desires": ["peace"],
        "speech_style": "formal",
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": "Test notes",
        "current_emotional_state": "calm",
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            traits={"openness": 0.5, "extroversion": 0.8},
        ),
    )

    # Only traits should change
    assert result.traits == {"openness": 0.5, "extroversion": 0.8}
    assert result.values == ["loyalty"]  # Unchanged
    assert result.fears == ["betrayal"]  # Unchanged
    assert result.desires == ["peace"]  # Unchanged
    assert result.speech_style == "formal"  # Unchanged
    assert result.gm_notes == "Test notes"  # Unchanged
    assert result.current_emotional_state == "calm"  # Unchanged


def test_update_npc_profile_values_list(monkeypatch):
    """Test updating NPC profile values list."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {"openness": 0.2},
        "values": ["loyalty"],
        "fears": [],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            values=["honor", "courage", "wisdom"],
        ),
    )

    assert result.values == ["honor", "courage", "wisdom"]
    assert result.traits == {"openness": 0.2}  # Unchanged


def test_update_npc_profile_fears_list(monkeypatch):
    """Test updating NPC profile fears list."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {"openness": 0.2},
        "values": [],
        "fears": ["betrayal"],
        "desires": [],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            fears=["death", "chaos", "being alone"],
        ),
    )

    assert result.fears == ["death", "chaos", "being alone"]
    assert result.traits == {"openness": 0.2}  # Unchanged


def test_update_npc_profile_desires_list(monkeypatch):
    """Test updating NPC profile desires list."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {"openness": 0.2},
        "values": [],
        "fears": [],
        "desires": ["peace"],
        "speech_style": None,
        "catchphrases": [],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": [],
        "gm_notes": None,
        "current_emotional_state": None,
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            desires=["recognition", "power", "wealth"],
        ),
    )

    assert result.desires == ["recognition", "power", "wealth"]
    assert result.traits == {"openness": 0.2}  # Unchanged


def test_update_npc_profile_gm_notes_only(monkeypatch):
    """Test updating NPC profile with only gm_notes field."""
    entity_id = uuid4()
    profile_id = uuid4()

    # Create existing profile
    now = datetime.now(timezone.utc)
    existing_profile = {
        "profile_id": str(profile_id),
        "entity_id": str(entity_id),
        "traits": {"openness": 0.2},
        "values": ["loyalty"],
        "fears": ["betrayal"],
        "desires": ["peace"],
        "speech_style": "formal",
        "catchphrases": ["It is done."],
        "mannerisms": [],
        "emotional_tendencies": [],
        "preferences": [],
        "triggers": [],
        "secrets": ["Is actually a spy"],
        "gm_notes": "Initial notes",
        "current_emotional_state": "calm",
        "relationship_states": {},
        "created_at": now,
        "updated_at": now,
    }

    # Mock MongoDB client
    fake_mongo = _FakeMongoClient()
    fake_mongo.profiles_db.profiles[str(profile_id)] = existing_profile

    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_mongodb_client",
        lambda: fake_mongo,
    )
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.npc_profiles.get_neo4j_client",
        lambda: _FakeNeo4jClient(entity_exists=True),
    )

    # Import after monkeypatching
    from monitor_data.tools.mongodb_tools.npc_profiles import mongodb_update_npc_profile

    result = mongodb_update_npc_profile(
        entity_id,
        NPCProfileUpdate(
            gm_notes="Updated GM notes: This NPC plays a key role in the upcoming assassination plot.",
        ),
    )

    # Only gm_notes should change
    assert (
        result.gm_notes
        == "Updated GM notes: This NPC plays a key role in the upcoming assassination plot."
    )
    assert result.traits == {"openness": 0.2}  # Unchanged
    assert result.values == ["loyalty"]  # Unchanged
    assert result.fears == ["betrayal"]  # Unchanged
    assert result.desires == ["peace"]  # Unchanged
    assert result.speech_style == "formal"  # Unchanged
    assert result.catchphrases == ["It is done."]  # Unchanged
    assert result.secrets == ["Is actually a spy"]  # Unchanged
    assert result.current_emotional_state == "calm"  # Unchanged
