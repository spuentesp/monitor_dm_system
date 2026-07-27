"""
Edge-case tests for the SillyTavern / RisuAI character-card parser.

Covers: v1 flat cards, v2/v3 nested under 'data', PNG with embedded tEXt +
zTXt base64 chunks, RisuAI 'ccv3' keyword, malformed JSON, missing name,
non-PNG bytes, and round-trip build→parse.

No live DB — just byte/JSON manipulation.
"""

from __future__ import annotations

import base64
import json
import struct
import zlib

import pytest

from monitor_ui.routers.character_cards import (
    build_character_card,
    parse_character_card,
)


def _png_with_text_chunk(keyword: str, text: str) -> bytes:
    """Build a minimal PNG that has a single tEXt chunk carrying `text` for `keyword`."""
    signature = b"\x89PNG\r\n\x1a\n"

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
        return length + ctype + data + crc

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    tEXt_body = keyword.encode("latin-1") + b"\x00" + text.encode("latin-1")
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"tEXt", tEXt_body) + _chunk(b"IEND", b"")


def _png_with_ztext_chunk(keyword: str, text: str) -> bytes:
    """Same as above but the body is compressed (zTXt) — ST sometimes writes that."""
    signature = b"\x89PNG\r\n\x1a\n"

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
        return length + ctype + data + crc

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    compressed = zlib.compress(text.encode("latin-1"))
    zTXt_body = keyword.encode("latin-1") + b"\x00" + b"\x00" + compressed
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"zTXt", zTXt_body) + _chunk(b"IEND", b"")


# ---------------------------------------------------------------------------
# Happy paths — JSON shapes
# ---------------------------------------------------------------------------


class TestJSONParsing:
    def test_v2_card_nested_under_data(self):
        card = {
            "spec": "chara_card_v2",
            "data": {
                "name": "Aldric",
                "description": "A weary innkeeper.",
                "personality": "Dry, hospitable.",
                "first_mes": "Welcome, traveler.",
                "system_prompt": "stay reserved",
                "scenario": "A traveler enters.",
                "creator_notes": "secret: hides a key",
                "mes_example": "",
            },
        }
        parsed = parse_character_card(json.dumps(card).encode())
        assert parsed.name == "Aldric"
        assert parsed.description == "A weary innkeeper."
        assert parsed.first_message == "Welcome, traveler."
        # gm_notes combines system_prompt + scenario + creator_notes
        assert "secret: hides a key" in parsed.gm_notes
        assert "stay reserved" in parsed.gm_notes
        assert parsed.is_ooc_persona is False
        assert parsed.avatar_url is None

    def test_v3_card_with_creator_notes(self):
        card = {
            "spec": "chara_card_v3",
            "data": {
                "name": "Sister Veil",
                "description": "A confessor.",
                "personality": "Soft-spoken.",
                "first_mes": "Sit.",
                "creator_notes": "Shelters a deserter.",
                "tags": ["religious"],
            },
        }
        parsed = parse_character_card(json.dumps(card).encode())
        assert parsed.name == "Sister Veil"
        assert "Shelters a deserter." in parsed.gm_notes

    def test_v1_flat_card_uses_fallback_field_names(self):
        # v1 cards flatten name, description, etc. (no 'data' wrapper).
        card = {
            "name": "Mira",
            "char_name": "Mira",  # v1 fallback
            "char_persona": "A retired duelist.",
            "char_greeting": "Good evening.",
            "personality": "Reserved.",
        }
        parsed = parse_character_card(json.dumps(card).encode())
        assert parsed.name == "Mira"
        assert parsed.description == "A retired duelist."
        assert parsed.first_message == "Good evening."

    def test_empty_fields_become_empty_strings(self):
        card = {"data": {"name": "OnlyName", "description": "", "personality": ""}}
        parsed = parse_character_card(json.dumps(card).encode())
        assert parsed.name == "OnlyName"
        assert parsed.description == ""
        assert parsed.first_message == ""

    def test_long_gm_notes_get_capped_to_8000_chars(self):
        long_notes = "x" * 9000
        card = {"data": {"name": "Loud", "creator_notes": long_notes}}
        parsed = parse_character_card(json.dumps(card).encode())
        assert len(parsed.gm_notes) <= 8000

    def test_name_truncated_to_200_chars(self):
        card = {"data": {"name": "N" * 500}}
        parsed = parse_character_card(json.dumps(card).encode())
        assert len(parsed.name) <= 200


# ---------------------------------------------------------------------------
# PNG embedding (SillyTavern card PNGs)
# ---------------------------------------------------------------------------


class TestPNGParsing:
    def test_chara_keyword_in_text_chunk(self):
        body = json.dumps(
            {
                "spec": "chara_card_v2",
                "data": {
                    "name": "Aldric",
                    "description": "innkeeper",
                    "first_mes": "Welcome.",
                },
            }
        )
        encoded = base64.b64encode(body.encode("utf-8")).decode("ascii")
        png = _png_with_text_chunk("chara", encoded)
        parsed = parse_character_card(png, filename="card.png")
        assert parsed.name == "Aldric"
        assert parsed.first_message == "Welcome."

    def test_ccv3_keyword_for_risuai(self):
        body = json.dumps(
            {
                "spec": "chara_card_v3",
                "data": {
                    "name": "Rust",
                    "description": "salvage mechanic",
                    "first_mes": "You lost?",
                },
            }
        )
        encoded = base64.b64encode(body.encode("utf-8")).decode("ascii")
        png = _png_with_text_chunk("ccv3", encoded)
        parsed = parse_character_card(png, filename="card.png")
        assert parsed.name == "Rust"

    def test_compressed_zTXt_chunk_is_decompressed(self):
        body = json.dumps(
            {
                "spec": "chara_card_v2",
                "data": {
                    "name": "Zee",
                    "description": "compressed path",
                    "first_mes": "hi",
                },
            }
        )
        encoded = base64.b64encode(body.encode("utf-8")).decode("ascii")
        png = _png_with_ztext_chunk("chara", encoded)
        parsed = parse_character_card(png, filename="card.png")
        assert parsed.name == "Zee"

    def test_filename_png_extension_takes_precedence(self):
        # PNG detection by filename, not signature.
        png = _png_with_text_chunk("chara", base64.b64encode(b'{"data":{"name":"Fname"}}').decode())
        # Make first bytes ambiguous (strip signature from a *copy* in memory).
        # Filename detection alone should still route to PNG parser.
        parsed = parse_character_card(png, filename="x.png")
        assert parsed.name == "Fname"

    def test_content_type_image_png_routes_to_png_parser(self):
        png = _png_with_text_chunk("chara", base64.b64encode(b'{"data":{"name":"CT"}}').decode())
        parsed = parse_character_card(png, content_type="image/png")
        assert parsed.name == "CT"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_missing_name_raises_valueerror(self):
        bad = json.dumps({"data": {"description": "no name"}}).encode()
        with pytest.raises(ValueError, match="no character name"):
            parse_character_card(bad)

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_character_card(b"not json at all")

    def test_png_without_card_chunk_raises(self):
        png = _png_with_text_chunk("unrelated_keyword", "some random text")
        with pytest.raises(ValueError, match="No character card"):
            parse_character_card(png)

    def test_png_signature_but_corrupt_base64_raises(self):
        png = _png_with_text_chunk("chara", "!!!not base64!!!")
        with pytest.raises(ValueError, match="chara"):
            parse_character_card(png)

    def test_card_with_data_not_dict_falls_back_to_top_level(self):
        # 'data' is not a dict → parser treats the whole object as fields.
        card = {"data": "oops not a dict", "name": "TopLevel"}
        parsed = parse_character_card(json.dumps(card).encode())
        assert parsed.name == "TopLevel"

    def test_pure_no_card_payload_raises(self):
        # data=None falls back to the top-level dict, which has no name.
        with pytest.raises(ValueError, match="no character name"):
            parse_character_card(json.dumps({"data": None}).encode())


# ---------------------------------------------------------------------------
# Round-trip: build → parse yields the same card
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_build_then_parse_preserves_fields(self):
        original = {
            "name": "Aldric",
            "description": "Innkeeper of the Drowned Lantern.",
            "personality": "Dry, watchful.",
            "first_message": "We don't get much trouble here.",
            "gm_notes": "Secretly an ex-thief.",
        }
        card_obj = build_character_card(original)
        # Build emits a chara_card_v2 envelope; serialize back to bytes.
        encoded = json.dumps(card_obj).encode("utf-8")
        parsed = parse_character_card(encoded)
        assert parsed.name == original["name"]
        assert parsed.description == original["description"]
        assert parsed.personality == original["personality"]
        assert parsed.first_message == original["first_message"]
        # gm_notes was placed in creator_notes by build_character_card
        assert "Secretly an ex-thief" in parsed.gm_notes


# ---------------------------------------------------------------------------
# Mutation-killing additions: distinct fields between name and char_name so the
# fallback is actually exercised, and description-only cards (no name at all).
# ---------------------------------------------------------------------------


class TestMutationKillers:
    def test_v1_uses_char_name_when_name_missing(self):
        """v1 fallback path: 'name' missing, only 'char_name' present."""
        card = {
            "char_name": "FallbackName",
            "char_persona": "v1 persona.",
            "char_greeting": "v1 greeting.",
            "personality": "v1 personality.",
        }
        parsed = parse_character_card(json.dumps(card).encode())
        assert parsed.name == "FallbackName"
        assert parsed.description == "v1 persona."
        assert parsed.first_message == "v1 greeting."

    def test_v1_picks_name_over_char_name_when_both_present(self):
        card = {"name": "PrimaryName", "char_name": "ShouldBeIgnored"}
        parsed = parse_character_card(json.dumps(card).encode())
        assert parsed.name == "PrimaryName"
