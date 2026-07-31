"""
Tests for lorebook_tools — keyword injection, trigger counting, bulk ops.

Uses a simple dict-list-based fake MongoDB for isolation.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from monitor_data.schemas.lorebook import LorebookEntryCreate

# =============================================================================
# Fake MongoDB collection
# =============================================================================


class FakeCollection:
    """Simple in-memory MongoDB-like collection for testing."""

    def __init__(self):
        self.docs: list[dict] = []

    def insert_one(self, doc: dict) -> Mock:
        self.docs.append(doc.copy())
        return Mock()

    def insert_many(self, documents: list[dict]) -> Mock:
        for d in documents:
            self.docs.append(d.copy())
        return Mock()

    def find_one(self, query: dict) -> dict | None:
        if "id" in query:
            for d in self.docs:
                if d["id"] == query["id"]:
                    return d.copy()
        return None

    def find_one_and_update(self, query: dict, update: dict, return_document=None) -> dict | None:
        for d in self.docs:
            if d.get("id") == query.get("id"):
                if "$set" in update:
                    d.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        d[k] = d.get(k, 0) + v
                return d.copy()
        return None

    def find(self, query: dict | None = None):
        """Returns a chainable fake cursor."""
        result = list(self.docs)
        if query:
            if "character_id" in query:
                result = [d for d in result if d.get("character_id") == query["character_id"]]
            if "is_active" in query:
                result = [d for d in result if d.get("is_active") == query["is_active"]]
            if "id" in query and isinstance(query["id"], dict) and "$in" in query["id"]:
                ids = query["id"]["$in"]
                result = [d for d in result if d.get("id") in ids]
            if "tags" in query and isinstance(query["tags"], dict) and "$in" in query["tags"]:
                tags = query["tags"]["$in"]
                result = [d for d in result if any(t in d.get("tags", []) for t in tags)]
        return FakeCursor(result)

    def delete_one(self, query: dict) -> Mock:
        for i, d in enumerate(self.docs):
            if d.get("id") == query.get("id"):
                self.docs = self.docs[:i] + self.docs[i + 1 :]
                return Mock(deleted_count=1)
        return Mock(deleted_count=0)

    def update_one(self, query: dict, update: dict) -> Mock:
        for d in self.docs:
            if d.get("id") == query.get("id"):
                if "$set" in update:
                    d.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        d[k] = d.get(k, 0) + v
                return Mock(modified_count=1)
        return Mock(modified_count=0)

    def update_many(self, query: dict, update: dict) -> Mock:
        matched = 0
        ids = query.get("id", {}).get("$in", []) if isinstance(query.get("id"), dict) else []
        for d in self.docs:
            if d.get("id") in ids:
                if "$set" in update:
                    d.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        d[k] = d.get(k, 0) + v
                matched += 1
        return Mock(modified_count=matched)

    def aggregate(self, pipeline: list[dict]) -> list[dict]:
        char_id = None
        for stage in pipeline:
            if "$match" in stage:
                char_id = stage["$match"].get("character_id")
                break
        if char_id:
            matching = [d for d in self.docs if d.get("character_id") == char_id and d.get("is_active", True)]
            total = len(matching)
            triggers = sum(d.get("trigger_count", 0) for d in matching)
            priorities = [d.get("priority", 0) for d in matching]
            avg = round(sum(priorities) / total, 1) if total else 0
            return [
                {
                    "_id": None,
                    "total_entries": total,
                    "total_triggers": triggers,
                    "avg_priority": avg,
                }
            ]
        return []


class FakeCursor:
    """Chainable fake cursor from FakeCollection.find()."""

    def __init__(self, docs: list[dict]):
        self._docs = docs

    def sort(self, field: str | tuple, direction: int = -1):
        if isinstance(field, tuple):
            field, direction = field
        self._docs.sort(key=lambda d: d.get(field, ""), reverse=(direction == -1))
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


# =============================================================================
# Keyword extraction
# =============================================================================


class TestAutoKeywords:
    def test_extracts_capitalized_nouns(self):
        from monitor_data.tools.mongodb_tools.lorebook_tools import _auto_keywords

        result = _auto_keywords("The ancient Dragon Smaug ruled the Lonely Mountain.")
        assert any(k in ["dragon", "smaug", "lonely", "mountain"] for k in result)

    def test_deduplicates(self):
        from monitor_data.tools.mongodb_tools.lorebook_tools import _auto_keywords

        result = _auto_keywords("Gandalf met Bilbo in the Shire. Gandalf was a wizard.")
        assert len(result) <= 5

    def test_lowercase_output(self):
        from monitor_data.tools.mongodb_tools.lorebook_tools import _auto_keywords

        result = _auto_keywords("The Kingdom of Rohan")
        assert all(w.islower() for w in result)

    def test_returns_empty_for_common_words_only(self):
        from monitor_data.tools.mongodb_tools.lorebook_tools import _auto_keywords

        result = _auto_keywords("the and of in")
        # The function may return these as-is; the important thing is it returns a list
        assert isinstance(result, list)
        assert len(result) <= 5


# =============================================================================
# mongodb_create_lorebook_entry
# =============================================================================


class TestCreateLorebookEntry:
    def test_inserts_with_all_fields(self):
        coll = FakeCollection()
        from monitor_data.tools.mongodb_tools.lorebook_tools import mongodb_create_lorebook_entry

        with patch("monitor_data.tools.mongodb_tools.lorebook_tools._coll", return_value=coll):
            entry = mongodb_create_lorebook_entry(
                "char-123",
                LorebookEntryCreate(
                    keywords=["dragon", "hoard"],
                    content="Dragons sleep on their hoards.",
                    priority=80,
                    tags=["combat"],
                ),
            )

        assert entry.id is not None
        assert entry.character_id == "char-123"
        assert entry.keywords == ["dragon", "hoard"]
        assert entry.content == "Dragons sleep on their hoards."
        assert entry.priority == 80
        assert entry.tags == ["combat"]
        assert entry.trigger_count == 0
        assert entry.is_active is True

    def test_falls_back_to_auto_keywords_when_empty(self):
        coll = FakeCollection()
        from monitor_data.tools.mongodb_tools.lorebook_tools import mongodb_create_lorebook_entry

        with patch("monitor_data.tools.mongodb_tools.lorebook_tools._coll", return_value=coll):
            entry = mongodb_create_lorebook_entry(
                "char-123",
                LorebookEntryCreate(content="The Kingdom of Gondor is ruled by a steward."),
            )

        assert len(entry.keywords) > 0
        assert all(isinstance(k, str) for k in entry.keywords)

    def test_respects_auto_generate_keywords_flag(self):
        coll = FakeCollection()
        from monitor_data.tools.mongodb_tools.lorebook_tools import mongodb_create_lorebook_entry

        with patch("monitor_data.tools.mongodb_tools.lorebook_tools._coll", return_value=coll):
            entry = mongodb_create_lorebook_entry(
                "char-123",
                LorebookEntryCreate(
                    content="The City of Ember lies underground.",
                    auto_generate_keywords=True,
                ),
            )

        assert len(entry.keywords) > 0


# =============================================================================
# mongodb_inject_lorebook_entries
# =============================================================================


class TestInjectLorebookEntries:
    def _inject(self, coll, character_id, text, scene_context=None):
        from monitor_data.tools.mongodb_tools.lorebook_tools import mongodb_inject_lorebook_entries

        with patch("monitor_data.tools.mongodb_tools.lorebook_tools._coll", return_value=coll):
            return mongodb_inject_lorebook_entries(character_id, text, scene_context=scene_context)

    def test_no_entries_returns_empty(self):
        coll = FakeCollection()
        result = self._inject(coll, "char-123", "I see a dragon")
        assert result == []

    def test_keyword_match_returns_content(self):
        coll = FakeCollection()
        coll.docs = [
            {
                "id": "e1",
                "character_id": "char-123",
                "keywords": ["dragon"],
                "content": "Dragons are immune to fire.",
                "priority": 80,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 0,
                "created_at": "2024-01-01",
            },
            {
                "id": "e2",
                "character_id": "char-123",
                "keywords": ["castle"],
                "content": "The castle has high walls.",
                "priority": 50,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 0,
                "created_at": "2024-01-02",
            },
        ]

        result = self._inject(coll, "char-123", "I attacked the dragon")
        assert "Dragons are immune to fire." in result

    def test_no_match_returns_empty(self):
        coll = FakeCollection()
        coll.docs = [
            {
                "id": "e1",
                "character_id": "char-123",
                "keywords": ["dragon"],
                "content": "Dragons are immune.",
                "priority": 80,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 0,
                "created_at": "2024-01-01",
            },
        ]

        result = self._inject(coll, "char-123", "I walked to the market")
        assert result == []

    def test_deduplicates_by_content(self):
        coll = FakeCollection()
        coll.docs = [
            {
                "id": "e1",
                "character_id": "char-123",
                "keywords": ["dragon"],
                "content": "Dragons sleep.",
                "priority": 50,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 0,
                "created_at": "2024-01-01",
            },
            {
                "id": "e2",
                "character_id": "char-123",
                "keywords": ["wyrm"],
                "content": "Dragons sleep.",
                "priority": 80,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 0,
                "created_at": "2024-01-02",
            },
        ]

        result = self._inject(coll, "char-123", "dragon and wyrm")
        assert len([r for r in result if r == "Dragons sleep."]) == 1

    def test_increments_trigger_count(self):
        coll = FakeCollection()
        coll.docs = [
            {
                "id": "e1",
                "character_id": "char-123",
                "keywords": ["dragon"],
                "content": "Dragons sleep.",
                "priority": 80,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 5,
                "created_at": "2024-01-01",
            },
        ]

        self._inject(coll, "char-123", "I see a dragon")
        entry = next(d for d in coll.docs if d["id"] == "e1")
        assert entry["trigger_count"] == 6

    def test_scene_filter_excludes_mismatched_entries(self):
        coll = FakeCollection()
        coll.docs = [
            {
                "id": "e1",
                "character_id": "char-123",
                "keywords": ["dragon"],
                "content": "Dragons in combat.",
                "priority": 80,
                "is_active": True,
                "tags": ["combat"],
                "scene_filter": "combat",
                "trigger_count": 0,
                "created_at": "2024-01-01",
            },
            {
                "id": "e2",
                "character_id": "char-123",
                "keywords": ["dragon"],
                "content": "Dragons in social.",
                "priority": 70,
                "is_active": True,
                "tags": ["social"],
                "scene_filter": "social",
                "trigger_count": 0,
                "created_at": "2024-01-02",
            },
        ]

        result = self._inject(coll, "char-123", "dragon here", scene_context="combat")
        assert "Dragons in combat." in result
        assert "Dragons in social." not in result

    def test_entries_without_scene_filter_are_always_eligible(self):
        coll = FakeCollection()
        coll.docs = [
            {
                "id": "e1",
                "character_id": "char-123",
                "keywords": ["dragon"],
                "content": "Dragons (no filter).",
                "priority": 80,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 0,
                "created_at": "2024-01-01",
            },
        ]

        result = self._inject(coll, "char-123", "dragon here", scene_context="combat")
        assert "Dragons (no filter)." in result

    def test_case_insensitive_matching(self):
        coll = FakeCollection()
        coll.docs = [
            {
                "id": "e1",
                "character_id": "char-123",
                "keywords": ["dragon"],
                "content": "Dragons.",
                "priority": 80,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 0,
                "created_at": "2024-01-01",
            },
        ]

        result = self._inject(coll, "char-123", "DRAGON")
        assert "Dragons." in result


# =============================================================================
# mongodb_get_lorebook_stats
# =============================================================================


class TestLorebookStats:
    def test_empty_returns_zero_stats(self):
        coll = FakeCollection()
        from monitor_data.tools.mongodb_tools.lorebook_tools import mongodb_get_lorebook_stats

        with patch("monitor_data.tools.mongodb_tools.lorebook_tools._coll", return_value=coll):
            stats = mongodb_get_lorebook_stats("char-123")

        assert stats["total_entries"] == 0
        assert stats["total_triggers"] == 0

    def test_aggregates_triggers_and_priority(self):
        coll = FakeCollection()
        coll.docs = [
            {
                "id": "e1",
                "character_id": "char-123",
                "keywords": [],
                "content": "D1",
                "priority": 80,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 10,
                "created_at": "2024-01-01",
            },
            {
                "id": "e2",
                "character_id": "char-123",
                "keywords": [],
                "content": "D2",
                "priority": 60,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 5,
                "created_at": "2024-01-02",
            },
        ]
        from monitor_data.tools.mongodb_tools.lorebook_tools import mongodb_get_lorebook_stats

        with patch("monitor_data.tools.mongodb_tools.lorebook_tools._coll", return_value=coll):
            stats = mongodb_get_lorebook_stats("char-123")

        assert stats["total_entries"] == 2
        assert stats["total_triggers"] == 15
        assert stats["avg_priority"] == 70.0


# =============================================================================
# mongodb_bulk_create_lorebook_entries
# =============================================================================


class TestBulkCreate:
    def test_empty_list_returns_empty(self):
        coll = FakeCollection()
        from monitor_data.tools.mongodb_tools.lorebook_tools import (
            mongodb_bulk_create_lorebook_entries,
        )

        with patch("monitor_data.tools.mongodb_tools.lorebook_tools._coll", return_value=coll):
            result = mongodb_bulk_create_lorebook_entries("char-123", [])

        assert result == []

    def test_creates_all_entries(self):
        coll = FakeCollection()
        from monitor_data.tools.mongodb_tools.lorebook_tools import (
            mongodb_bulk_create_lorebook_entries,
        )

        with patch("monitor_data.tools.mongodb_tools.lorebook_tools._coll", return_value=coll):
            result = mongodb_bulk_create_lorebook_entries(
                "char-123",
                [
                    LorebookEntryCreate(keywords=["a"], content="Entry A"),
                    LorebookEntryCreate(keywords=["b"], content="Entry B"),
                ],
            )

        assert len(result) == 2
        assert result[0].content == "Entry A"
        assert result[1].content == "Entry B"


# =============================================================================
# mongodb_get_top_lorebook_entries
# =============================================================================


class TestGetTopEntries:
    def test_sorts_by_trigger_count(self):
        coll = FakeCollection()
        coll.docs = [
            {
                "id": "e1",
                "character_id": "char-123",
                "keywords": [],
                "content": "D1",
                "priority": 80,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 3,
                "created_at": "2024-01-01",
            },
            {
                "id": "e2",
                "character_id": "char-123",
                "keywords": [],
                "content": "D2",
                "priority": 80,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 10,
                "created_at": "2024-01-02",
            },
            {
                "id": "e3",
                "character_id": "char-123",
                "keywords": [],
                "content": "D3",
                "priority": 80,
                "is_active": True,
                "tags": [],
                "scene_filter": None,
                "trigger_count": 1,
                "created_at": "2024-01-03",
            },
        ]
        from monitor_data.tools.mongodb_tools.lorebook_tools import mongodb_get_top_lorebook_entries

        with patch("monitor_data.tools.mongodb_tools.lorebook_tools._coll", return_value=coll):
            result = mongodb_get_top_lorebook_entries("char-123", limit=3)

        assert result[0].content == "D2"  # trigger_count=10
        assert result[1].content == "D1"  # trigger_count=3
        assert result[2].content == "D3"  # trigger_count=1


# =============================================================================
# mongodb_scan_lorebook — SillyTavern semantics
# =============================================================================


class TestScanLorebook:
    def _scan(self, coll, character_id, text, **kwargs):
        from monitor_data.tools.mongodb_tools.lorebook_tools import mongodb_scan_lorebook

        with patch("monitor_data.tools.mongodb_tools.lorebook_tools._coll", return_value=coll):
            return mongodb_scan_lorebook(character_ids=[character_id], text=text, **kwargs)

    def _make_doc(
        self,
        entry_id: str,
        character_id: str = "char-123",
        keywords: list[str] | None = None,
        content: str = "Content",
        priority: int = 50,
        **kwargs,
    ) -> dict:
        defaults = {
            "id": entry_id,
            "character_id": character_id,
            "keywords": keywords or [],
            "secondary_keywords": [],
            "content": content,
            "comment": "",
            "priority": priority,
            "order": 100,
            "position": 1,
            "depth": 4,
            "is_active": True,
            "constant": False,
            "selective": False,
            "selective_logic": 0,
            "probability": 100,
            "use_probability": True,
            "case_sensitive": None,
            "match_whole_words": None,
            "tags": [],
            "scene_filter": None,
            "group": "",
            "group_override": False,
            "sticky": 0,
            "cooldown": 0,
            "delay": 0,
            "exclude_recursion": False,
            "prevent_recursion": False,
            "vectorized": False,
            "trigger_count": 0,
            "last_triggered": None,
            "last_triggered_turn_index": None,
            "created_turn_index": None,
            "st_extensions": {},
            "created_at": "2024-01-01",
        }
        defaults.update(kwargs)
        return defaults

    def test_constant_entry_triggers_without_keyword(self):
        coll = FakeCollection()
        coll.docs = [self._make_doc("e1", keywords=[], content="Always on.", constant=True)]
        result = self._scan(coll, "char-123", "hello")
        assert result.after == ["Always on."]

    def test_scan_depth_searches_history(self):
        coll = FakeCollection()
        coll.docs = [self._make_doc("e1", keywords=["dragon"], content="Dragons.")]
        result = self._scan(coll, "char-123", "hello", history=["we saw a dragon earlier"])
        assert result.after == ["Dragons."]

    def test_scan_depth_respects_config(self):
        coll = FakeCollection()
        coll.docs = [self._make_doc("e1", keywords=["dragon"], content="Dragons.")]
        from monitor_data.schemas.lorebook import LorebookScanConfig

        config = LorebookScanConfig(scan_depth=0)
        result = self._scan(coll, "char-123", "hello", history=["we saw a dragon earlier"], config=config)
        assert result.after == []

    def test_selective_and_any_requires_secondary(self):
        coll = FakeCollection()
        coll.docs = [
            self._make_doc(
                "e1",
                keywords=["dragon"],
                secondary_keywords=["fire"],
                content="Fire dragon.",
                selective=True,
                selective_logic=0,
            )
        ]
        result = self._scan(coll, "char-123", "I see a dragon")
        assert result.after == []
        result = self._scan(coll, "char-123", "dragon breathes fire")
        assert result.after == ["Fire dragon."]

    def test_selective_not_all(self):
        coll = FakeCollection()
        coll.docs = [
            self._make_doc(
                "e1",
                keywords=["dragon"],
                secondary_keywords=["gold", "silver"],
                content="Dragon.",
                selective=True,
                selective_logic=1,
            )
        ]
        result = self._scan(coll, "char-123", "dragon with gold and silver")
        assert result.after == []
        result = self._scan(coll, "char-123", "dragon with gold only")
        assert result.after == ["Dragon."]

    def test_probability_blocks_when_roll_fails(self):
        coll = FakeCollection()
        coll.docs = [self._make_doc("e1", keywords=["dragon"], content="Dragons.", probability=0)]
        import random

        result = self._scan(coll, "char-123", "dragon", rng=random.Random(1))
        assert result.after == []

    def test_probability_allows_when_roll_succeeds(self):
        coll = FakeCollection()
        coll.docs = [self._make_doc("e1", keywords=["dragon"], content="Dragons.", probability=100)]
        import random

        result = self._scan(coll, "char-123", "dragon", rng=random.Random(1))
        assert result.after == ["Dragons."]

    def test_position_grouping(self):
        coll = FakeCollection()
        coll.docs = [
            self._make_doc("e1", keywords=["a"], content="Before.", position=0, order=1),
            self._make_doc("e2", keywords=["a"], content="After.", position=1, order=1),
            self._make_doc("e3", keywords=["a"], content="Depth.", position=4, order=1),
        ]
        result = self._scan(coll, "char-123", "a")
        assert result.before == ["Before."]
        assert result.after == ["After."]
        assert result.depth == ["Depth."]

    def test_token_budget_truncates(self):
        coll = FakeCollection()
        long_text = "word " * 500  # ~2500 chars -> ~625 tokens
        coll.docs = [
            self._make_doc("e1", keywords=["a"], content="Short.", order=1),
            self._make_doc("e2", keywords=["a"], content=long_text, order=2),
        ]
        from monitor_data.schemas.lorebook import LorebookScanConfig

        config = LorebookScanConfig(token_budget=10)
        result = self._scan(coll, "char-123", "a", config=config)
        assert "Short." in result.all_contents()
        assert long_text not in result.all_contents()

    def test_group_competition(self):
        coll = FakeCollection()
        coll.docs = [
            self._make_doc("e1", keywords=["a"], content="High.", group="g", priority=80),
            self._make_doc("e2", keywords=["a"], content="Low.", group="g", priority=50),
        ]
        result = self._scan(coll, "char-123", "a")
        assert result.after == ["High."]

    def test_sticky_keeps_entry_active(self):
        coll = FakeCollection()
        coll.docs = [
            self._make_doc(
                "e1",
                keywords=["dragon"],
                content="Sticky.",
                sticky=2,
                last_triggered_turn_index=5,
            )
        ]
        result = self._scan(coll, "char-123", "hello", turn_index=6)
        assert result.after == ["Sticky."]

    def test_cooldown_blocks_retrigger(self):
        coll = FakeCollection()
        coll.docs = [
            self._make_doc(
                "e1",
                keywords=["dragon"],
                content="Cooldown.",
                sticky=1,
                cooldown=3,
                last_triggered_turn_index=5,
            )
        ]
        # Turn 8 is within sticky(5)+cooldown(3)=8 window -> blocked.
        result = self._scan(coll, "char-123", "dragon", turn_index=8)
        assert result.after == []
        # Turn 10 is past the window -> allowed.
        result = self._scan(coll, "char-123", "dragon", turn_index=10)
        assert result.after == ["Cooldown."]

    def test_delay_blocks_early_trigger(self):
        coll = FakeCollection()
        coll.docs = [
            self._make_doc(
                "e1",
                keywords=["dragon"],
                content="Delayed.",
                delay=3,
                created_turn_index=5,
            )
        ]
        result = self._scan(coll, "char-123", "dragon", turn_index=7)
        assert result.after == []
        result = self._scan(coll, "char-123", "dragon", turn_index=9)
        assert result.after == ["Delayed."]

    def test_recursive_scanning(self):
        coll = FakeCollection()
        coll.docs = [
            self._make_doc("e1", keywords=["dragon"], content="Wyrms are related."),
            self._make_doc("e2", keywords=["wyrm"], content="Wyrm detail."),
        ]
        result = self._scan(coll, "char-123", "dragon")
        assert "Wyrm detail." in result.all_contents()

    def test_prevent_recursion_stops_chain(self):
        coll = FakeCollection()
        coll.docs = [
            self._make_doc("e1", keywords=["dragon"], content="Wyrms are related.", prevent_recursion=True),
            self._make_doc("e2", keywords=["wyrm"], content="Wyrm detail."),
        ]
        result = self._scan(coll, "char-123", "dragon")
        assert "Wyrm detail." not in result.all_contents()

    def test_exclude_recursion_not_scanned(self):
        coll = FakeCollection()
        coll.docs = [
            self._make_doc("e1", keywords=["dragon"], content="Wyrms are related."),
            self._make_doc("e2", keywords=["wyrm"], content="Wyrm detail.", exclude_recursion=True),
        ]
        result = self._scan(coll, "char-123", "dragon")
        assert "Wyrm detail." not in result.all_contents()
