"""
SillyTavern / Tavern character-card (chara_card_v2) interop.

Parse a card — raw JSON, or a PNG with the card embedded in a tEXt/zTXt chunk
(the ``chara`` keyword, base64-encoded JSON, as TavernAI/SillyTavern write it)
— into our ``CharacterCreate`` shape, and serialize one back out. This is the
bridge into the SillyTavern ecosystem: drop a card, play with it.

LAYER: 3 (UI backend)
"""

from __future__ import annotations

import base64
import binascii
import json
import struct
import zlib
from typing import Any

from .entities_schemas import CharacterCreate

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CARD_KEYWORDS = ("chara", "ccv3")


def _extract_card_from_png(data: bytes) -> dict[str, Any]:
    """Pull the embedded card JSON out of a PNG's tEXt/zTXt chunks."""
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError("Not a PNG file.")
    offset = len(_PNG_SIGNATURE)
    found: dict[str, str] = {}
    while offset + 8 <= len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        ctype = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        offset += 12 + length  # length + type + data + CRC
        if ctype == b"tEXt":
            key, _, val = body.partition(b"\x00")
            found[key.decode("latin-1", "ignore")] = val.decode("latin-1", "ignore")
        elif ctype == b"zTXt":
            key, _, rest = body.partition(b"\x00")
            # rest = 1-byte compression method + compressed text
            try:
                text = zlib.decompress(rest[1:]).decode("latin-1", "ignore")
                found[key.decode("latin-1", "ignore")] = text
            except Exception:
                pass
        elif ctype == b"IEND":
            break

    for kw in _CARD_KEYWORDS:
        if kw in found and found[kw].strip():
            try:
                raw = base64.b64decode(found[kw])
                return json.loads(raw.decode("utf-8", "ignore"))  # type: ignore
            except (binascii.Error, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"PNG '{kw}' chunk is not a valid card: {exc}") from exc
    raise ValueError("No character card found in this PNG (no 'chara'/'ccv3' chunk).")


def parse_character_card(raw: bytes, *, content_type: str = "", filename: str = "") -> CharacterCreate:
    """Parse a JSON or PNG character card into a CharacterCreate."""
    is_png = raw.startswith(_PNG_SIGNATURE) or content_type == "image/png" or filename.lower().endswith(".png")
    card: dict[str, Any]
    if is_png:
        card = _extract_card_from_png(raw)
    else:
        try:
            card = json.loads(raw.decode("utf-8", "ignore"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Card is not valid JSON: {exc}") from exc

    # v2/v3 nest everything under "data"; v1 cards are flat.
    data = card.get("data") if isinstance(card.get("data"), dict) else card
    if not isinstance(data, dict):
        raise ValueError("Card has no readable fields.")

    name = str(data.get("name") or data.get("char_name") or "").strip()
    if not name:
        raise ValueError("Card has no character name.")

    # gm_notes carries the AI-facing guidance ST keeps in several fields.
    notes_parts = [
        str(data.get("system_prompt") or "").strip(),
        str(data.get("scenario") or "").strip(),
        str(data.get("creator_notes") or "").strip(),
        str(data.get("mes_example") or "").strip(),
    ]
    gm_notes = "\n\n".join(p for p in notes_parts if p)[:8000]

    return CharacterCreate(
        name=name[:200],
        description=str(data.get("description") or data.get("char_persona") or "").strip(),
        personality=str(data.get("personality") or "").strip(),
        first_message=str(data.get("first_mes") or data.get("char_greeting") or "").strip(),
        gm_notes=gm_notes,
        avatar_url=None,
        is_ooc_persona=False,
    )


def build_character_card(character: dict[str, Any]) -> dict[str, Any]:
    """Serialize one of our characters into a chara_card_v2 object."""
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": character.get("name", ""),
            "description": character.get("description", ""),
            "personality": character.get("personality", ""),
            "scenario": "",
            "first_mes": character.get("first_message", ""),
            "mes_example": "",
            "creator_notes": character.get("gm_notes", ""),
            "system_prompt": "",
            "post_history_instructions": "",
            "tags": [],
            "creator": "MONITOR",
            "character_version": "1.0",
            "alternate_greetings": [],
        },
    }
