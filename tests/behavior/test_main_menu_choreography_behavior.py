"""Behavior tests for MainMenuProcessor (Phase 4 - CLI Menu).

Exercises pure parsing and routing — no I/O.

Covers:
- parse_menu_input (letter, word, number, invalid)
- handle_menu_choice (routing decisions)
- display_menu output format
- MenuChoice enum values
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytestmark = pytest.mark.unit


def _make_processor() -> Any:
    from monitor_agents.main_menu_processor import MainMenuProcessor

    return MainMenuProcessor()


# =============================================================================
# MenuChoice enum
# =============================================================================


class TestMenuChoice:
    def test_values(self):
        from monitor_agents.main_menu_processor import MenuChoice

        assert MenuChoice.PLAY.value == "play"
        assert MenuChoice.MANAGE.value == "manage"
        assert MenuChoice.QUERY.value == "query"
        assert MenuChoice.INGEST.value == "ingest"
        assert MenuChoice.SETTINGS.value == "settings"
        assert MenuChoice.EXIT.value == "exit"
        assert MenuChoice.INVALID.value == "invalid"

    def test_inherits_str(self):
        from monitor_agents.main_menu_processor import MenuChoice

        assert MenuChoice.PLAY == "play"
        assert f"{MenuChoice.EXIT}" == "exit"


# =============================================================================
# parse_menu_input
# =============================================================================


class TestParseMenuInput:
    def test_letter_p(self):
        proc = _make_processor()
        assert proc.parse_menu_input("p") == MenuChoiceValue("play")

    def test_letter_m(self):
        proc = _make_processor()
        assert proc.parse_menu_input("M") == MenuChoiceValue("manage")

    def test_full_word_play(self):
        proc = _make_processor()
        assert proc.parse_menu_input("play") == MenuChoiceValue("play")

    def test_full_word_settings(self):
        proc = _make_processor()
        assert proc.parse_menu_input("settings") == MenuChoiceValue("settings")

    def test_with_whitespace(self):
        proc = _make_processor()
        assert proc.parse_menu_input("  play  ") == MenuChoiceValue("play")

    def test_uppercase_word(self):
        proc = _make_processor()
        assert proc.parse_menu_input("EXIT") == MenuChoiceValue("exit")

    def test_number_1_play(self):
        proc = _make_processor()
        assert proc.parse_menu_input("1") == MenuChoiceValue("play")

    def test_number_4_ingest(self):
        proc = _make_processor()
        assert proc.parse_menu_input("4") == MenuChoiceValue("ingest")

    def test_invalid_returns_invalid(self):
        proc = _make_processor()
        assert proc.parse_menu_input("zzz") == MenuChoiceValue("invalid")

    def test_empty_string_returns_invalid(self):
        proc = _make_processor()
        assert proc.parse_menu_input("") == MenuChoiceValue("invalid")

    def test_number_6_returns_invalid(self):
        # 6 is not in the number_map
        proc = _make_processor()
        assert proc.parse_menu_input("6") == MenuChoiceValue("invalid")

    def test_none_raises(self):
        proc = _make_processor()
        with pytest.raises(ValueError):
            proc.parse_menu_input(None)  # type: ignore

    def test_int_raises_typeerror(self):
        proc = _make_processor()
        with pytest.raises(TypeError):
            proc.parse_menu_input(42)  # type: ignore


def MenuChoiceValue(value: str):
    from monitor_agents.main_menu_processor import MenuChoice

    return MenuChoice(value)


# =============================================================================
# handle_menu_choice
# =============================================================================


class TestHandleMenuChoice:
    def test_exit_returns_false(self):
        proc = _make_processor()
        result = asyncio.run(proc.handle_menu_choice(MenuChoiceValue("exit")))
        assert result is False

    def test_invalid_continues(self):
        proc = _make_processor()
        result = asyncio.run(proc.handle_menu_choice(MenuChoiceValue("invalid")))
        assert result is True

    def test_play_continues(self):
        proc = _make_processor()
        result = asyncio.run(proc.handle_menu_choice(MenuChoiceValue("play")))
        assert result is True

    def test_manage_continues(self):
        proc = _make_processor()
        result = asyncio.run(proc.handle_menu_choice(MenuChoiceValue("manage")))
        assert result is True

    def test_all_valid_choices_continue(self):
        proc = _make_processor()
        for value in ["play", "manage", "query", "ingest", "settings"]:
            result = asyncio.run(proc.handle_menu_choice(MenuChoiceValue(value)))
            assert result is True


# =============================================================================
# display_menu
# =============================================================================


class TestDisplayMenu:
    def test_prints_all_items(self, capsys):
        proc = _make_processor()
        proc.display_menu()
        out = capsys.readouterr().out
        assert "Play" in out
        assert "Manage" in out
        assert "Query" in out
        assert "Ingest" in out
        assert "Settings" in out
        assert "Exit" in out
        assert "[P]" in out
        assert "[X]" in out

    def test_menu_items_count(self):
        proc = _make_processor()
        assert len(proc.MENU_ITEMS) == 6


# =============================================================================
# run_menu_loop
# =============================================================================


class TestRunMenuLoop:
    def test_eof_returns_exit(self, monkeypatch, capsys):
        import builtins

        proc = _make_processor()

        def fake_input(_prompt):
            raise EOFError

        monkeypatch.setattr(builtins, "input", fake_input)
        result = asyncio.run(proc.run_menu_loop())
        assert result["action"] == "exit"

    def test_keyboard_interrupt_returns_exit(self, monkeypatch, capsys):
        import builtins

        proc = _make_processor()

        def fake_input(_prompt):
            raise KeyboardInterrupt

        monkeypatch.setattr(builtins, "input", fake_input)
        result = asyncio.run(proc.run_menu_loop())
        assert result["action"] == "exit"

    def test_exit_input_returns_exit(self, monkeypatch, capsys):
        import builtins

        proc = _make_processor()
        inputs = iter(["x"])

        def fake_input(_prompt):
            return next(inputs)

        monkeypatch.setattr(builtins, "input", fake_input)
        result = asyncio.run(proc.run_menu_loop())
        assert result["action"] == "exit"
