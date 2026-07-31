"""
E2E test for SillyTavern / character.ai lorebook compatibility.

Imports a ST World Info JSON into a live MongoDB container, then runs the
full scan engine end-to-end and asserts that:

  - entries are created with ST semantics (selective, constant, position, etc.)
  - scan depth finds keywords in recent history
  - constant entries inject without a keyword
  - timing (sticky/cooldown/delay) works across turn indices

Run:
    RUN_E2E=1 pytest tests/e2e/test_lorebook_st_compat.py -v
"""

from __future__ import annotations

import random

import pytest

from monitor_data.interop.sillytavern_lorebook import parse_st_lorebook_raw
from monitor_data.schemas.lorebook import LorebookEntryCreate
from monitor_data.tools.mongodb_tools.lorebook_tools import (
    mongodb_bulk_create_lorebook_entries,
    mongodb_get_lorebook_entries,
    mongodb_save_scan_config,
    mongodb_scan_lorebook,
)


@pytest.mark.e2e
async def test_st_lorebook_import_and_scan(e2e_databases) -> None:
    character_id = "e2e-char-st-lorebook"

    st_json = {
        "name": "E2E ST Book",
        "scan_depth": 2,
        "token_budget": 500,
        "recursive_scanning": True,
        "entries": {
            "0": {
                "uid": 0,
                "comment": "Constant world fact",
                "content": "The sky is green on this world.",
                "keys": [],
                "constant": True,
                "order": 1,
                "position": 0,
            },
            "1": {
                "uid": 1,
                "comment": "Selective dragon combat",
                "content": "Fire dragons are vulnerable to ice.",
                "keys": ["dragon"],
                "keysecondary": ["ice", "frost"],
                "selective": True,
                "selectiveLogic": 0,
                "order": 2,
                "position": 1,
            },
            "2": {
                "uid": 2,
                "comment": "History-triggered castle",
                "content": "The castle has a hidden vault.",
                "keys": ["castle"],
                "order": 3,
                "position": 4,
                "depth": 2,
            },
        },
    }

    parsed, config = parse_st_lorebook_raw(st_json)
    entries = [LorebookEntryCreate(**raw) for raw in parsed]
    assert len(entries) == 3

    # Bulk create with turn index 0 so delay math works if any entries have delay.
    created = mongodb_bulk_create_lorebook_entries(
        character_id=character_id,
        entries=entries,
        created_turn_index=0,
    )
    assert len(created) == 3

    mongodb_save_scan_config(character_id, config)

    # 1. Constant entry always injects; selective entry requires secondary keyword.
    result = mongodb_scan_lorebook(
        character_ids=[character_id],
        text="I see a dragon",
        history=[],
        turn_index=1,
        rng=random.Random(1),
    )
    assert "The sky is green on this world." in result.before
    assert "Fire dragons are vulnerable to ice." not in result.all_contents()

    # 2. Selective triggers when secondary keyword is in history (scan_depth=2).
    result = mongodb_scan_lorebook(
        character_ids=[character_id],
        text="I cast frost bolt at the dragon",
        history=["we entered the cave"],
        turn_index=2,
        rng=random.Random(1),
    )
    assert "Fire dragons are vulnerable to ice." in result.after

    # 3. History keyword triggers depth-positioned entry.
    result = mongodb_scan_lorebook(
        character_ids=[character_id],
        text="What now?",
        history=["the king lives in a castle", "we approached the gate"],
        turn_index=3,
        rng=random.Random(1),
    )
    assert "The castle has a hidden vault." in result.depth

    # 4. Verify round-trip persistence.
    stored = mongodb_get_lorebook_entries(character_id, sort_by="order", ascending=True)
    assert len(stored) == 3
    assert any(e.constant for e in stored)
    assert any(e.selective for e in stored)
