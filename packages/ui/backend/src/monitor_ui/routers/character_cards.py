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
from typing import Any, cast

from monitor_data.interop.sillytavern_lorebook import (
    build_character_book,
    parse_character_book_from_card,
)
from monitor_data.schemas.lorebook import LorebookEntryCreate, LorebookScanConfig

from .entities_schemas import CharacterCreate

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_ZIP_SIGNATURE = b"PK\x03\x04"
_CARD_KEYWORDS = ("chara", "ccv3")
_EMBEDED_URI_PREFIX = "embeded://"  # sic — the misspelling is in the CharX spec


def extract_charx_card(data: bytes) -> dict[str, Any]:
    """Read ``card.json`` out of a CharX (RisuAI) zip archive."""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            card_name = next(
                (n for n in zf.namelist() if n == "card.json" or n.endswith("/card.json")),
                None,
            )
            if card_name is None:
                raise ValueError("CharX archive has no card.json.")
            return json.loads(zf.read(card_name).decode("utf-8", "ignore"))  # type: ignore
    except zipfile.BadZipFile as exc:
        raise ValueError(f"CharX file is not a valid zip archive: {exc}") from exc


def extract_charx_assets(data: bytes) -> dict[str, bytes]:
    """Return the asset files of a CharX archive as ``{zip_path: bytes}``."""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return {
                name: zf.read(name)
                for name in zf.namelist()
                if name.startswith("assets/") and not name.endswith("/")
            }
    except zipfile.BadZipFile:
        return {}


def resolve_charx_icon(card: dict[str, Any], assets: dict[str, bytes]) -> bytes | None:
    """Pick the icon asset bytes from a CharX archive.

    Resolution order: the ``data.assets`` entry of type ``icon`` (matched by
    its ``embeded://`` uri, then by ``name.ext`` against zip paths), then any
    asset under an ``icon/`` directory. Returns None when no icon is found.
    """
    if not assets:
        return None

    card_data = card.get("data") if isinstance(card.get("data"), dict) else card
    declared = card_data.get("assets") if isinstance(card_data, dict) else None
    if isinstance(declared, list):
        for entry in declared:
            if not isinstance(entry, dict) or entry.get("type") != "icon":
                continue
            uri = str(entry.get("uri") or "")
            if uri.startswith(_EMBEDED_URI_PREFIX):
                path = uri[len(_EMBEDED_URI_PREFIX):].lstrip("/")
                if path in assets:
                    return assets[path]
            name, ext = str(entry.get("name") or ""), str(entry.get("ext") or "")
            if name:
                suffix = f"{name}.{ext}" if ext else name
                for path, blob in assets.items():
                    if path.endswith(suffix):
                        return blob

    for path, blob in assets.items():
        if "/icon/" in path or path.startswith("assets/icon"):
            return blob
    return None


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


def _load_card_dict(raw: bytes, *, content_type: str = "", filename: str = "") -> dict[str, Any]:
    """Load the raw card bytes into a dict, handling PNG/CharX extraction."""
    is_charx = (
        raw.startswith(_ZIP_SIGNATURE)
        or filename.lower().endswith(".charx")
        or content_type == "application/zip"
    )
    if is_charx:
        return extract_charx_card(raw)

    is_png = raw.startswith(_PNG_SIGNATURE) or content_type == "image/png" or filename.lower().endswith(".png")
    if is_png:
        return _extract_card_from_png(raw)

    try:
        return cast(dict[str, Any], json.loads(raw.decode("utf-8", "ignore")))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Card is not valid JSON: {exc}") from exc


def is_charx_file(raw: bytes, *, content_type: str = "", filename: str = "") -> bool:
    """Public predicate so routers can decide whether to extract assets."""
    return (
        raw.startswith(_ZIP_SIGNATURE)
        or filename.lower().endswith(".charx")
        or content_type == "application/zip"
    )


def sniff_image_type(blob: bytes) -> tuple[str, str]:
    """Sniff (content_type, extension) from image magic bytes. Defaults to PNG."""
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if blob.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if blob.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", "gif"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp", "webp"
    return "image/png", "png"


def parse_character_card_with_book(
    raw: bytes,
    *,
    content_type: str = "",
    filename: str = "",
) -> tuple[CharacterCreate, list[LorebookEntryCreate], LorebookScanConfig]:
    """Parse a JSON/PNG character card into a CharacterCreate plus embedded lorebook."""
    card = _load_card_dict(raw, content_type=content_type, filename=filename)

    # v2/v3 nest everything under "data"; v1 cards are flat.
    data = card.get("data") if isinstance(card.get("data"), dict) else card
    if not isinstance(data, dict):
        raise ValueError("Card has no readable fields.")

    name = str(data.get("name") or data.get("char_name") or "").strip()
    if not name:
        raise ValueError("Card has no character name.")

    notes_parts = [
        str(data.get("system_prompt") or "").strip(),
        str(data.get("scenario") or "").strip(),
        str(data.get("creator_notes") or "").strip(),
        str(data.get("mes_example") or "").strip(),
    ]
    gm_notes = "\n\n".join(p for p in notes_parts if p)[:8000]

    character = CharacterCreate(
        name=name[:200],
        description=str(data.get("description") or data.get("char_persona") or "").strip(),
        personality=str(data.get("personality") or "").strip(),
        first_message=str(data.get("first_mes") or data.get("char_greeting") or "").strip(),
        gm_notes=gm_notes,
        avatar_url=None,
        is_ooc_persona=False,
    )

    book_data = parse_character_book_from_card(card)
    entries: list[LorebookEntryCreate] = []
    config = LorebookScanConfig()
    if book_data is not None:
        raw_entries, config = book_data
        for raw_entry in raw_entries:
            try:
                entries.append(LorebookEntryCreate(**raw_entry))
            except Exception:
                # Defensive: skip malformed entries rather than failing the whole card.
                continue

    return character, entries, config


def parse_character_card(raw: bytes, *, content_type: str = "", filename: str = "") -> CharacterCreate:
    """Parse a JSON or PNG character card into a CharacterCreate.

    Backward-compatible wrapper that ignores any embedded ``character_book``.
    Use ``parse_character_card_with_book`` to import lorebook entries too.
    """
    character, _, _ = parse_character_card_with_book(
        raw, content_type=content_type, filename=filename
    )
    return character


def build_character_card(
    character: dict[str, Any],
    *,
    lorebook_entries: list[dict[str, Any]] | None = None,
    scan_config: LorebookScanConfig | None = None,
) -> dict[str, Any]:
    """Serialize one of our characters into a chara_card_v2 object.

    Args:
        character: Serialized character dict from ``_serialise_character``.
        lorebook_entries: Optional lorebook entries to embed as ``character_book``.
        scan_config: Optional scan config to embed with the character book.
    """
    book: dict[str, Any] | None = None
    if lorebook_entries is not None:
        book = build_character_book(
            lorebook_entries,
            name=f"{character.get('name', '')} lorebook",
            description="",
            config=scan_config,
        )

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
            "character_book": book,
        },
    }
