"""
HTTP-shape tests for POST /entities/characters/import-card.

Drives the FastAPI endpoint with TestClient; the underlying parse_character_card
and create_character are mocked so this is hermetic (no live DB).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from monitor_ui.main import app


client = TestClient(app)


SAMPLE_V2_CARD = {
    "spec": "chara_card_v2",
    "data": {
        "name": "Sister Veil",
        "description": "A confessor.",
        "personality": "Soft-spoken.",
        "first_mes": "Sit.",
        "system_prompt": "Stay reserved.",
        "creator_notes": "Shelters a deserter.",
    },
}


@pytest.fixture
def fake_create():
    """Stub the underlying character_storage.create_character."""
    return patch(
        "monitor_ui.routers.entities._create_character_doc",
        return_value={
            "id": "char-1",
            "name": "Sister Veil",
            "description": "A confessor.",
            "avatar_url": None,
            "personality": "Soft-spoken.",
            "gm_notes": "Shelters a deserter.\n\nStay reserved.",
            "first_message": "Sit.",
            "is_ooc_persona": False,
            "entity_id": None,
            "memory_count": 0,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    )


def test_import_card_json_returns_201_with_character_detail(fake_create):
    """Happy path: a valid chara_card_v2 JSON file → 201 + CharacterDetail shape."""
    with fake_create:
        resp = client.post(
            "/api/entities/characters/import-card",
            files={"file": ("card.json", json.dumps(SAMPLE_V2_CARD).encode(), "application/json")},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Sister Veil"
    assert body["description"] == "A confessor."
    assert body["personality"] == "Soft-spoken."
    assert body["first_message"] == "Sit."
    # gm_notes combines creator_notes + system_prompt (parser concatenation).
    assert "Shelters a deserter." in body["gm_notes"]
    assert "Stay reserved." in body["gm_notes"]
    # entity_id is None for a freshly imported light card.
    assert body["entity_id"] is None
    assert body["memory_count"] == 0


def test_import_card_invalid_json_returns_422():
    """An unparseable card → 422 (parser's ValueError surfaces in the detail)."""
    bad = b"definitely not a card"
    resp = client.post(
        "/api/entities/characters/import-card",
        files={"file": ("card.json", bad, "application/json")},
    )
    assert resp.status_code == 422
    body = resp.json()
    # The endpoint puts the parser's message in `detail`.
    assert "detail" in body and body["detail"]
    assert isinstance(body["detail"], str)


def test_import_card_empty_file_returns_422():
    """Zero-byte upload → 422 (the endpoint's empty-file guard)."""
    resp = client.post(
        "/api/entities/characters/import-card",
        files={"file": ("card.json", b"", "application/json")},
    )
    assert resp.status_code == 422
    assert "Empty" in resp.json().get("detail", "")


def test_import_card_png_with_embedded_chara_parses(fake_create):
    """A PNG with a 'chara' tEXt chunk carrying base64 JSON is routed correctly."""
    import base64
    import struct
    import zlib

    body_json = json.dumps(SAMPLE_V2_CARD).encode("utf-8")
    encoded = base64.b64encode(body_json).decode("ascii")

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
        return length + ctype + data + crc

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    text_body = b"chara\x00" + encoded.encode("latin-1")
    png_bytes = sig + _chunk(b"IHDR", ihdr) + _chunk(b"tEXt", text_body) + _chunk(b"IEND", b"")

    with fake_create:
        resp = client.post(
            "/api/entities/characters/import-card",
            files={"file": ("card.png", png_bytes, "image/png")},
        )

    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "Sister Veil"