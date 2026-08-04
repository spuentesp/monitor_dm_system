"""Risu/SillyTavern-style lorebook output directives.

Imported cards increasingly rely on self-managing lorebooks: the model emits
``@@activate <entry name>`` / ``@@deactivate <entry name>`` lines in its reply,
and the runtime toggles the matching lorebook entries instead of showing the
directive to the player.

This module parses those directives out of narrator output and applies them
(``is_active`` flips) against the entries of the conversation's lorebook
characters. Everything here is best-effort: a directive failure must never
break a turn.

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
) -> int:
    """Apply parsed directives via MCP lorebook tools. Returns applied count.

    Entries are matched by ``comment`` (the ST "name" field), case-insensitive,
    across all given characters. Unknown names are skipped silently — models
    hallucinate directive targets often enough that this must not be loud.
    """
    applied = 0
    for directive in directives:
        target = directive.entry_name.casefold()
        if not target:
            continue
        try:
            matched_id: str | None = None
            for cid in character_ids:
                entries = await agent.call_tool("mongodb_get_lorebook_entries", {"character_id": cid})
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

            await agent.call_tool(
                "mongodb_update_lorebook_entry",
                {
                    "entry_id": matched_id,
                    "updates": {"is_active": directive.verb == "activate"},
                },
            )
            applied += 1
            logger.info(
                "lorebook_directive_applied",
                verb=directive.verb,
                entry_name=directive.entry_name,
            )
        except Exception:
            logger.warning(
                "lorebook_directive_failed",
                verb=directive.verb,
                entry_name=directive.entry_name,
                exc_info=True,
            )
    return applied
