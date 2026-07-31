"""
Tests for SillyTavern / character.ai lorebook interop.
"""

from __future__ import annotations

import json

import pytest

from monitor_data.interop.sillytavern_lorebook import (
    build_character_book,
    build_st_lorebook,
    parse_character_book_from_card,
    parse_st_lorebook_entry,
    parse_st_lorebook_raw,
)
from monitor_data.schemas.lorebook import LorebookEntryCreate, LorebookScanConfig, SelectiveLogic


class TestParseStLorebookEntry:
    def test_maps_basic_fields(self):
        raw = {
            "uid": 5,
            "comment": "Dragon lore",
            "content": "Dragons are immune to fire.",
            "keys": ["dragon", "wyrm"],
            "keysecondary": ["fire", "flame"],
            "constant": True,
            "selective": True,
            "selectiveLogic": 3,
            "order": 50,
            "position": 4,
            "depth": 6,
            "probability": 75,
            "useProbability": True,
            "disable": False,
            "group": "monsters",
            "groupOverride": False,
            "sticky": 2,
            "cooldown": 3,
            "delay": 1,
            "excludeRecursion": True,
            "preventRecursion": False,
            "vectorized": True,
            "caseSensitive": True,
            "matchWholeWords": True,
        }
        parsed = parse_st_lorebook_entry(raw)
        assert parsed["comment"] == "Dragon lore"
        assert parsed["keywords"] == ["dragon", "wyrm"]
        assert parsed["secondary_keywords"] == ["fire", "flame"]
        assert parsed["constant"] is True
        assert parsed["selective"] is True
        assert parsed["selective_logic"] == SelectiveLogic.AND_ALL
        assert parsed["order"] == 50
        assert parsed["position"] == 4
        assert parsed["depth"] == 6
        assert parsed["probability"] == 75
        assert parsed["group"] == "monsters"
        assert parsed["sticky"] == 2
        assert parsed["case_sensitive"] is True
        assert parsed["match_whole_words"] is True
        assert parsed["is_active"] is True

    def test_disable_sets_is_active_false(self):
        parsed = parse_st_lorebook_entry({"content": "x", "disable": True})
        assert parsed["is_active"] is False

    def test_comma_separated_keywords(self):
        parsed = parse_st_lorebook_entry({"content": "x", "keys": "dragon, wyrm"})
        assert parsed["keywords"] == ["dragon", "wyrm"]

    def test_preserves_unknown_extensions(self):
        parsed = parse_st_lorebook_entry({"content": "x", "customField": 123})
        assert parsed["st_extensions"] == {"customField": 123}


class TestParseStLorebookRaw:
    def test_dict_entries_format(self):
        raw = {
            "name": "My Book",
            "scan_depth": 5,
            "entries": {
                "0": {"uid": 0, "content": "Dragons.", "keys": ["dragon"]},
                "1": {"uid": 1, "content": "Castles.", "keys": ["castle"]},
            },
        }
        entries, config = parse_st_lorebook_raw(json.dumps(raw))
        assert len(entries) == 2
        assert entries[0]["content"] == "Dragons."
        assert config.scan_depth == 5

    def test_array_entries_format(self):
        raw = {
            "entries": [
                {"uid": 0, "content": "Dragons.", "keys": ["dragon"]},
            ]
        }
        entries, config = parse_st_lorebook_raw(raw)
        assert len(entries) == 1

    def test_character_book_wrapper(self):
        raw = {
            "data": {
                "name": "Card",
                "character_book": {
                    "entries": {"0": {"uid": 0, "content": "Lore.", "keys": ["lore"]}},
                },
            }
        }
        entries, config = parse_st_lorebook_raw(raw)
        assert len(entries) == 1

    def test_invalid_structure_raises(self):
        with pytest.raises(ValueError):
            parse_st_lorebook_raw('{"foo": "bar"}')


class TestParseCharacterBookFromCard:
    def test_v2_card(self):
        card = {
            "spec": "chara_card_v2",
            "data": {
                "name": "Test",
                "character_book": {
                    "entries": {"0": {"uid": 0, "content": "Lore.", "keys": ["lore"]}},
                },
            },
        }
        result = parse_character_book_from_card(card)
        assert result is not None
        entries, config = result
        assert len(entries) == 1

    def test_v1_card_no_book_returns_none(self):
        card = {"name": "Test", "description": "No book."}
        assert parse_character_book_from_card(card) is None


class TestBuildStLorebook:
    def test_round_trip_preserves_fields(self):
        entry = LorebookEntryCreate(
            keywords=["dragon"],
            secondary_keywords=["fire"],
            content="Dragons.",
            comment="Lore",
            priority=80,
            order=50,
            position=4,
            depth=6,
            constant=True,
            selective=True,
            selective_logic=SelectiveLogic.AND_ALL,
            probability=75,
            group="monsters",
            sticky=2,
            cooldown=3,
            delay=1,
            case_sensitive=True,
            match_whole_words=True,
            st_extensions={"customField": 123},
        )
        book = build_st_lorebook([entry], name="Test Book")
        assert book["name"] == "Test Book"
        st_entry = book["entries"]["0"]
        assert st_entry["keys"] == ["dragon"]
        assert st_entry["keysecondary"] == ["fire"]
        assert st_entry["constant"] is True
        assert st_entry["selective"] is True
        assert st_entry["selectiveLogic"] == SelectiveLogic.AND_ALL
        assert st_entry["order"] == 50
        assert st_entry["position"] == 4
        assert st_entry["depth"] == 6
        assert st_entry["probability"] == 75
        assert st_entry["sticky"] == 2
        assert st_entry["customField"] == 123

    def test_character_book_shape(self):
        entry = LorebookEntryCreate(content="Lore.", keywords=["lore"])
        book = build_character_book([entry], name="Card Book")
        assert "entries" in book
        assert book["scan_depth"] == LorebookScanConfig().scan_depth
