"""Character-card macro substitution (``{{user}}`` / ``{{char}}``).

SillyTavern, RisuAI, and the chara_card ecosystem write card text with
placeholders that are resolved at *render* time, never at import time:

  - ``{{char}}`` — the character's name (also ``<CHAR>`` legacy alias).
  - ``{{user}}`` — the player's persona name (also ``<USER>`` legacy alias).

MONITOR stores card fields raw (so an export round-trip stays faithful) and
substitutes when a field is rendered into a prompt or shown as the opening
message. Substitution is case-insensitive, matching SillyTavern behavior.

LAYER: 1 (data-layer)
"""

from __future__ import annotations

import re

# {{user}}, {{ user }}, {{User}}, <USER> — permissive inner whitespace,
# case-insensitive, matching how the ecosystem actually writes these.
_USER_PATTERN = re.compile(r"\{\{\s*user\s*\}\}|<USER>", re.IGNORECASE)
_CHAR_PATTERN = re.compile(r"\{\{\s*char\s*\}\}|<CHAR>", re.IGNORECASE)

DEFAULT_USER_NAME = "User"


def substitute_card_macros(
    text: str,
    *,
    char_name: str,
    user_name: str | None = None,
) -> str:
    """Replace ``{{char}}``/``{{user}}`` placeholders in card text.

    Args:
        text: Raw card text (description, personality, greeting, ...).
        char_name: The character's display name.
        user_name: The player's persona name. Falls back to
            ``DEFAULT_USER_NAME`` ("User", the SillyTavern default) when no
            persona is bound.
    """
    if not text:
        return text
    resolved_user = (user_name or "").strip() or DEFAULT_USER_NAME
    out = _CHAR_PATTERN.sub(char_name, text)
    out = _USER_PATTERN.sub(resolved_user, out)
    return out
