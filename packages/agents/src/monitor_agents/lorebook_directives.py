"""Risu/SillyTavern-style lorebook output directives.

Imported cards increasingly rely on self-managing lorebooks: the model emits
``@@activate <entry name>`` / ``@@deactivate <entry name>`` lines in its reply,
and the runtime toggles the matching lorebook entries instead of showing the
directive to the player.

This module parses those directives out of narrator output and turns them into
per-conversation overrides of the entries' active flag. Nothing is written to
the lorebook, so one conversation can't change another's. Everything here is
best-effort: a directive failure must never break a turn.

LAYER: 2 (agents)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()

# A directive is a line whose first non-space token is @@activate or
# @@deactivate (case-insensitive), followed by the entry's comment/name.
# The trailing newline is consumed so stripping leaves no empty line behind.
_DIRECTIVE_PATTERN = re.compile(
    r"^[ \t]*@@(?P<verb>activate|deactivate)[^\S\n]+(?P<name>[^\n]+)\r?\n?",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class LorebookDirective:
    """One parsed output directive."""

    verb: str  # "activate" | "deactivate" (lowercased)
    entry_name: str


def parse_output_directives(text: str) -> tuple[str, list[LorebookDirective]]:
    """Split narrator output into (player-visible text, directives).

    Directive lines are removed from the visible text; surrounding blank
    lines collapse so the prose doesn't show scars.
    """
    if not text or "@@" not in text:
        return text, []

    directives = [
        LorebookDirective(verb=m.group("verb").lower(), entry_name=m.group("name").strip())
        for m in _DIRECTIVE_PATTERN.finditer(text)
    ]
    if not directives:
        return text, []

    cleaned = _DIRECTIVE_PATTERN.sub("", text)
    # Collapse the blank runs left behind by stripped lines.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, directives


async def apply_lorebook_directives(
    agent: Any,
    character_ids: list[str],
    directives: list[LorebookDirective],
    overrides: dict[str, bool],
) -> dict[str, bool]:
    """Return the conversation's entry overrides with these directives applied.

    Entries are matched by ``comment`` (the ST "name" field), case-insensitive,
    across all given characters, inactive entries included. Unknown names are
    skipped silently — models hallucinate directive targets often enough that
    this must not be loud.
    """
    updated = dict(overrides)
    for directive in directives:
        target = directive.entry_name.casefold()
        if not target:
            continue
        try:
            matched_id: str | None = None
            for cid in character_ids:
                entries = await agent.call_tool(
                    "mongodb_get_lorebook_entries", {"character_id": cid, "include_inactive": True}
                )
                for entry in entries or []:
                    comment = str(entry.get("comment") or "").strip()
                    if comment and comment.casefold() == target:
                        matched_id = str(entry.get("id"))
                        break
                if matched_id:
                    break
            if not matched_id:
                logger.info(
                    "lorebook_directive_unmatched",
                    verb=directive.verb,
                    entry_name=directive.entry_name,
                )
                continue

            updated[matched_id] = directive.verb == "activate"
            logger.info(
                "lorebook_directive_applied",
                verb=directive.verb,
                entry_name=directive.entry_name,
            )
        except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in apply_lorebook_directives)
            logger.warning(
                "lorebook_directive_failed",
                verb=directive.verb,
                entry_name=directive.entry_name,
                exc_info=True,
            )
    return updated
