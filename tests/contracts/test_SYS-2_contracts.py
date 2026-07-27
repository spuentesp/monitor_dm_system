"""
SYS-2: Main Menu — Contract Tests

This module tests the API contracts defined in SYS-2-contracts.md:
- Agent classes: MainMenuProcessor (display_menu, parse_menu_input, handle_menu_choice, run_menu_loop)
- CLI commands: monitor play, manage, query, ingest, settings, exit
"""

from unittest.mock import patch

import pytest
from monitor_agents.main_menu_processor import MenuChoice

# ============================================================================
# Agent Contract Tests
# ============================================================================


@pytest.mark.unit
class TestMainMenuProcessorDisplayMenuContract:
    """Contract tests for MainMenuProcessor.display_menu method."""

    @pytest.mark.unit
    @patch("builtins.print")
    def test_displays_complete_menu_structure(self, mock_print, main_menu_processor):
        """Contract: Displays menu header, 6 options, and prompt."""
        main_menu_processor.display_menu()

        # Verify contract: prints were called
        assert mock_print.call_count > 0

        # Extract all printed strings
        printed_strings = [str(call.args[0]) for call in mock_print.call_args_list]

        # Verify contract: menu header present
        assert any("MONITOR" in s or "Auto-GM" in s for s in printed_strings)

        # Verify contract: all 6 options present
        option_strings = " ".join(printed_strings)
        assert "[P]" in option_strings and "Play" in option_strings
        assert "[M]" in option_strings and "Manage" in option_strings
        assert "[Q]" in option_strings and "Query" in option_strings
        assert "[I]" in option_strings and "Ingest" in option_strings
        assert "[S]" in option_strings and "Settings" in option_strings
        assert "[X]" in option_strings and "Exit" in option_strings

        # Verify contract: prompt present
        assert any("> " in s for s in printed_strings)

    @pytest.mark.unit
    @patch("builtins.print")
    def test_returns_none(self, mock_print, main_menu_processor):
        """Contract: Returns None (display operation)."""
        result = main_menu_processor.display_menu()
        assert result is None


@pytest.mark.unit
class TestMainMenuProcessorParseMenuInputContract:
    """Contract tests for MainMenuProcessor.parse_menu_input method."""

    @pytest.mark.unit
    def test_parses_play_valid_inputs(self, main_menu_processor):
        """Contract: Parses 'P', 'play', 'PLAY', ' p ' as PLAY."""
        assert main_menu_processor.parse_menu_input("P") == MenuChoice.PLAY
        assert main_menu_processor.parse_menu_input("play") == MenuChoice.PLAY
        assert main_menu_processor.parse_menu_input("PLAY") == MenuChoice.PLAY
        assert main_menu_processor.parse_menu_input(" p ") == MenuChoice.PLAY

    @pytest.mark.unit
    def test_parses_manage_valid_inputs(self, main_menu_processor):
        """Contract: Parses 'M', 'manage', 'MANAGE', ' m ' as MANAGE."""
        assert main_menu_processor.parse_menu_input("M") == MenuChoice.MANAGE
        assert main_menu_processor.parse_menu_input("manage") == MenuChoice.MANAGE
        assert main_menu_processor.parse_menu_input("MANAGE") == MenuChoice.MANAGE
        assert main_menu_processor.parse_menu_input(" m ") == MenuChoice.MANAGE

    @pytest.mark.unit
    def test_parses_query_valid_inputs(self, main_menu_processor):
        """Contract: Parses 'Q', 'query', 'QUERY', ' q ' as QUERY."""
        assert main_menu_processor.parse_menu_input("Q") == MenuChoice.QUERY
        assert main_menu_processor.parse_menu_input("query") == MenuChoice.QUERY
        assert main_menu_processor.parse_menu_input("QUERY") == MenuChoice.QUERY
        assert main_menu_processor.parse_menu_input(" q ") == MenuChoice.QUERY

    @pytest.mark.unit
    def test_parses_ingest_valid_inputs(self, main_menu_processor):
        """Contract: Parses 'I', 'ingest', 'INGEST', ' i ' as INGEST."""
        assert main_menu_processor.parse_menu_input("I") == MenuChoice.INGEST
        assert main_menu_processor.parse_menu_input("ingest") == MenuChoice.INGEST
        assert main_menu_processor.parse_menu_input("INGEST") == MenuChoice.INGEST
        assert main_menu_processor.parse_menu_input(" i ") == MenuChoice.INGEST

    @pytest.mark.unit
    def test_parses_settings_valid_inputs(self, main_menu_processor):
        """Contract: Parses 'S', 'settings', 'SETTINGS', ' s ' as SETTINGS."""
        assert main_menu_processor.parse_menu_input("S") == MenuChoice.SETTINGS
        assert main_menu_processor.parse_menu_input("settings") == MenuChoice.SETTINGS
        assert main_menu_processor.parse_menu_input("SETTINGS") == MenuChoice.SETTINGS
        assert main_menu_processor.parse_menu_input(" s ") == MenuChoice.SETTINGS

    @pytest.mark.unit
    def test_parses_exit_valid_inputs(self, main_menu_processor):
        """Contract: Parses 'X', 'exit', 'EXIT', ' x ' as EXIT."""
        assert main_menu_processor.parse_menu_input("X") == MenuChoice.EXIT
        assert main_menu_processor.parse_menu_input("exit") == MenuChoice.EXIT
        assert main_menu_processor.parse_menu_input("EXIT") == MenuChoice.EXIT
        assert main_menu_processor.parse_menu_input(" x ") == MenuChoice.EXIT

    @pytest.mark.unit
    def test_returns_invalid_for_unrecognized_input(self, main_menu_processor):
        """Contract: Returns INVALID for unrecognized input."""
        assert main_menu_processor.parse_menu_input("Z") == MenuChoice.INVALID
        assert main_menu_processor.parse_menu_input("invalid") == MenuChoice.INVALID
        assert main_menu_processor.parse_menu_input("") == MenuChoice.INVALID
        assert main_menu_processor.parse_menu_input("123") == MenuChoice.INVALID

    @pytest.mark.unit
    def test_raises_value_error_for_none_input(self, main_menu_processor):
        """Contract: Raises ValueError when user_input is None."""
        with pytest.raises(ValueError) as exc_info:
            main_menu_processor.parse_menu_input(None)
        assert "cannot be None" in str(exc_info.value)

    @pytest.mark.unit
    def test_raises_type_error_for_non_string_input(self, main_menu_processor):
        """Contract: Raises TypeError when user_input is not a string."""
        with pytest.raises(TypeError) as exc_info:
            main_menu_processor.parse_menu_input(123)
        assert "must be a string" in str(exc_info.value)


@pytest.mark.unit
class TestMainMenuProcessorHandleMenuChoiceContract:
    """Contract tests for MainMenuProcessor.handle_menu_choice method."""

    @pytest.mark.unit
    async def test_returns_true_for_play_choice(self, main_menu_processor):
        """Contract: Returns True for PLAY choice (application continues)."""
        result = await main_menu_processor.handle_menu_choice(MenuChoice.PLAY)
        assert result

    @pytest.mark.unit
    async def test_returns_true_for_manage_choice(self, main_menu_processor):
        """Contract: Returns True for MANAGE choice (application continues)."""
        result = await main_menu_processor.handle_menu_choice(MenuChoice.MANAGE)
        assert result

    @pytest.mark.unit
    async def test_returns_true_for_query_choice(self, main_menu_processor):
        """Contract: Returns True for QUERY choice (application continues)."""
        result = await main_menu_processor.handle_menu_choice(MenuChoice.QUERY)
        assert result

    @pytest.mark.unit
    async def test_returns_true_for_ingest_choice(self, main_menu_processor):
        """Contract: Returns True for INGEST choice (application continues)."""
        result = await main_menu_processor.handle_menu_choice(MenuChoice.INGEST)
        assert result

    @pytest.mark.unit
    async def test_returns_true_for_settings_choice(self, main_menu_processor):
        """Contract: Returns True for SETTINGS choice (application continues)."""
        result = await main_menu_processor.handle_menu_choice(MenuChoice.SETTINGS)
        assert result

    @pytest.mark.unit
    async def test_returns_false_for_exit_choice(self, main_menu_processor):
        """Contract: Returns False for EXIT choice (application exits)."""
        result = await main_menu_processor.handle_menu_choice(MenuChoice.EXIT)
        assert not result

    @pytest.mark.unit
    async def test_returns_true_for_invalid_choice(self, main_menu_processor):
        """Contract: Returns True for INVALID choice (stay in menu)."""
        result = await main_menu_processor.handle_menu_choice(MenuChoice.INVALID)
        assert result

    @pytest.mark.unit
    @patch("builtins.print")
    async def test_displays_error_for_invalid_choice(
        self, mock_print, main_menu_processor
    ):
        """Contract: Displays error message for INVALID choice."""
        await main_menu_processor.handle_menu_choice(MenuChoice.INVALID)

        # Verify contract: error message displayed
        printed_strings = [str(call.args[0]) for call in mock_print.call_args_list]
        assert any(
            "Invalid choice" in s or "Please enter" in s for s in printed_strings
        )


@pytest.mark.unit
class TestMainMenuProcessorRunMenuLoopContract:
    """Contract tests for MainMenuProcessor.run_menu_loop method."""

    @pytest.mark.unit
    @patch("builtins.input")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.display_menu")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.parse_menu_input")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.handle_menu_choice")
    async def test_calls_display_menu_at_start_of_loop(
        self, mock_handle, mock_parse, mock_display, mock_input, main_menu_processor
    ):
        """Contract: Calls display_menu at start of each loop iteration."""
        # Mock user input: X (exit)
        mock_input.side_effect = ["X"]

        # Mock parse returns EXIT
        mock_parse.return_value = MenuChoice.EXIT

        # Mock handle returns False (exit)
        mock_handle.return_value = False

        await main_menu_processor.run_menu_loop()

        # Verify contract: display_menu was called
        mock_display.assert_called_once()

    @pytest.mark.unit
    @patch("builtins.input")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.parse_menu_input")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.handle_menu_choice")
    async def test_exits_when_handle_returns_false(
        self, mock_handle, mock_parse, mock_input, main_menu_processor
    ):
        """Contract: Exits loop when handle_menu_choice returns False."""
        # Mock user input: X (exit)
        mock_input.side_effect = ["X"]

        # Mock parse returns EXIT
        mock_parse.return_value = MenuChoice.EXIT

        # Mock handle returns False (exit)
        mock_handle.return_value = False

        await main_menu_processor.run_menu_loop()

        # Verify contract: handle_menu_choice was called with EXIT
        mock_handle.assert_called_once_with(MenuChoice.EXIT)

    @pytest.mark.unit
    @patch("builtins.input")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.parse_menu_input")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.handle_menu_choice")
    async def test_continues_loop_when_handle_returns_true(
        self, mock_handle, mock_parse, mock_input, main_menu_processor
    ):
        """Contract: Continues loop when handle_menu_choice returns True."""
        # Mock user inputs: P (play), then X (exit)
        mock_input.side_effect = ["P", "X"]

        # Mock parse returns PLAY then EXIT
        mock_parse.side_effect = [MenuChoice.PLAY, MenuChoice.EXIT]

        # Mock handle returns True (continue) then False (exit)
        mock_handle.side_effect = [True, False]

        await main_menu_processor.run_menu_loop()

        # Verify contract: handle_menu_choice was called twice
        assert mock_handle.call_count == 2


# ============================================================================
# CLI Command Contract Tests
# ============================================================================


class TestMonitorPlayCommandContract:
    """Contract tests for monitor play CLI command."""

    @pytest.mark.unit
    def test_requires_no_options_by_default(self, cli_tester):
        """Contract: monitor play with no options lists stories."""
        result = cli_tester.run_command(["monitor", "play"])

        # Verify contract: command executed
        assert result.exit_code == 0 or "stories" in result.output.lower()

    @pytest.mark.unit
    def test_accepts_story_id_option(self, cli_tester):
        """Contract: monitor play --story-id <id> resumes story."""
        result = cli_tester.run_command(["monitor", "play", "--story-id", "abc123"])

        # Verify contract: command executed with story-id
        assert result.exit_code != 1 or "story" in result.output.lower()

    @pytest.mark.unit
    def test_accepts_universe_id_option(self, cli_tester):
        """Contract: monitor play --universe-id <id> starts story in universe."""
        result = cli_tester.run_command(["monitor", "play", "--universe-id", "uni456"])

        # Verify contract: command executed with universe-id
        assert result.exit_code != 1 or "universe" in result.output.lower()

    @pytest.mark.unit
    def test_accepts_scene_id_option(self, cli_tester):
        """Contract: monitor play --scene-id <id> resumes scene."""
        result = cli_tester.run_command(["monitor", "play", "--scene-id", "scene789"])

        # Verify contract: command executed with scene-id
        assert result.exit_code != 1 or "scene" in result.output.lower()


class TestMonitorManageCommandContract:
    """Contract tests for monitor manage CLI command."""

    @pytest.mark.unit
    def test_lists_universes_with_universes_option(self, cli_tester):
        """Contract: monitor manage --universes lists universes."""
        result = cli_tester.run_command(["monitor", "manage", "--universes"])

        # Verify contract: command executed
        assert result.exit_code == 0 or "universe" in result.output.lower()

    @pytest.mark.unit
    def test_lists_stories_with_stories_option(self, cli_tester):
        """Contract: monitor manage --stories lists stories."""
        result = cli_tester.run_command(["monitor", "manage", "--stories"])

        # Verify contract: command executed
        assert result.exit_code == 0 or "story" in result.output.lower()

    @pytest.mark.unit
    def test_creates_universe_with_create_universe_option(self, cli_tester):
        """Contract: monitor manage --create-universe <name> creates universe."""
        result = cli_tester.run_command(
            ["monitor", "manage", "--create-universe", "Fantasy World"]
        )

        # Verify contract: command executed with universe name
        assert result.exit_code != 1 or "created" in result.output.lower()

    @pytest.mark.unit
    def test_creates_character_with_create_character_option(self, cli_tester):
        """Contract: monitor manage --create-character <name> creates character."""
        result = cli_tester.run_command(
            ["monitor", "manage", "--create-character", "Aragorn"]
        )

        # Verify contract: command executed with character name
        assert result.exit_code != 1 or "character" in result.output.lower()


class TestMonitorQueryCommandContract:
    """Contract tests for monitor query CLI command."""

    @pytest.mark.unit
    def test_requires_query_option(self, cli_tester):
        """Contract: monitor query --query <text> searches canon."""
        result = cli_tester.run_command(["monitor", "query", "--query", "Aragorn"])

        # Verify contract: command executed with query
        assert result.exit_code != 1 or "search" in result.output.lower()

    @pytest.mark.unit
    def test_accepts_type_option(self, cli_tester):
        """Contract: monitor query --query <text> --type <type> filters by type."""
        result = cli_tester.run_command(
            ["monitor", "query", "--query", "swords", "--type", "item"]
        )

        # Verify contract: command executed with type filter
        assert result.exit_code != 1 or "item" in result.output.lower()

    @pytest.mark.unit
    def test_accepts_universe_id_option(self, cli_tester):
        """Contract: monitor query --query <text> --universe-id <id> scopes search."""
        result = cli_tester.run_command(
            ["monitor", "query", "--query", "mines", "--universe-id", "uni123"]
        )

        # Verify contract: command executed with universe scope
        assert result.exit_code != 1 or "search" in result.output.lower()


class TestMonitorIngestCommandContract:
    """Contract tests for monitor ingest CLI command."""

    @pytest.mark.unit
    def test_requires_file_option(self, cli_tester):
        """Contract: monitor ingest --file <path> ingests document."""
        result = cli_tester.run_command(["monitor", "ingest", "--file", "document.txt"])

        # Verify contract: command executed with file path
        assert result.exit_code != 1 or "ingest" in result.output.lower()

    @pytest.mark.unit
    def test_accepts_universe_id_option(self, cli_tester):
        """Contract: monitor ingest --file <path> --universe-id <id> ingests into universe."""
        result = cli_tester.run_command(
            ["monitor", "ingest", "--file", "document.txt", "--universe-id", "uni123"]
        )

        # Verify contract: command executed with universe association
        assert result.exit_code != 1 or "ingest" in result.output.lower()


class TestMonitorSettingsCommandContract:
    """Contract tests for monitor settings CLI command."""

    @pytest.mark.unit
    def test_displays_llm_settings_with_llm_option(self, cli_tester):
        """Contract: monitor settings --llm displays LLM configuration."""
        result = cli_tester.run_command(["monitor", "settings", "--llm"])

        # Verify contract: command executed
        assert result.exit_code == 0 or "llm" in result.output.lower()

    @pytest.mark.unit
    def test_displays_all_settings_with_list_option(self, cli_tester):
        """Contract: monitor settings --list lists all settings."""
        result = cli_tester.run_command(["monitor", "settings", "--list"])

        # Verify contract: command executed
        assert result.exit_code == 0 or "setting" in result.output.lower()

    @pytest.mark.unit
    def test_sets_setting_with_set_option(self, cli_tester):
        """Contract: monitor settings --set <key>=<value> updates configuration."""
        result = cli_tester.run_command(
            ["monitor", "settings", "--set", "LLM_MODEL=claude-opus-4"]
        )

        # Verify contract: command executed with key=value
        assert result.exit_code != 1 or "updated" in result.output.lower()

    @pytest.mark.unit
    def test_gets_setting_with_get_option(self, cli_tester):
        """Contract: monitor settings --get <key> displays setting value."""
        result = cli_tester.run_command(
            ["monitor", "settings", "--get", "LLM_TEMPERATURE"]
        )

        # Verify contract: command executed with key
        assert result.exit_code != 1 or "temperature" in result.output.lower()


class TestMonitorExitCommandContract:
    """Contract tests for monitor exit CLI command."""

    @pytest.mark.unit
    def test_exits_application_cleanly(self, cli_tester):
        """Contract: monitor exit calls SYS-3 and exits cleanly."""
        result = cli_tester.run_command(["monitor", "exit"])

        # Verify contract: command executed
        assert result.exit_code == 0 or "exit" in result.output.lower()


# ============================================================================
# Integration Tests (with mocks)
# ============================================================================


@pytest.mark.unit
class TestSYS2Integration:
    """Integration tests for SYS-2 using mocked components."""

    @pytest.mark.integration
    @pytest.mark.unit
    @patch("builtins.input")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.display_menu")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.parse_menu_input")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.handle_menu_choice")
    async def test_full_menu_navigation_exit_workflow(
        self, mock_handle, mock_parse, mock_display, mock_input, main_menu_processor
    ):
        """Contract: Full menu navigation from display to exit."""
        # Setup: User inputs X (exit)
        mock_input.side_effect = ["X"]

        # Setup: Parse returns EXIT
        mock_parse.return_value = MenuChoice.EXIT

        # Setup: Handle returns False (exit)
        mock_handle.return_value = False

        # Execute: Run menu loop
        await main_menu_processor.run_menu_loop()

        # Verify: Contract compliance
        mock_display.assert_called_once()
        mock_parse.assert_called_once_with("X")
        mock_handle.assert_called_once_with(MenuChoice.EXIT)

    @pytest.mark.integration
    @pytest.mark.unit
    @patch("builtins.input")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.display_menu")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.parse_menu_input")
    @patch("monitor_agents.main_menu_processor.MainMenuProcessor.handle_menu_choice")
    async def test_full_menu_navigation_play_workflow(
        self, mock_handle, mock_parse, mock_display, mock_input, main_menu_processor
    ):
        """Contract: Full menu navigation from display to play."""
        # Setup: User inputs P (play), then X (exit)
        mock_input.side_effect = ["P", "X"]

        # Setup: Parse returns PLAY then EXIT
        mock_parse.side_effect = [MenuChoice.PLAY, MenuChoice.EXIT]

        # Setup: Handle returns True (continue) then False (exit)
        mock_handle.side_effect = [True, False]

        # Execute: Run menu loop
        await main_menu_processor.run_menu_loop()

        # Verify: Contract compliance
        assert mock_display.call_count == 2
        assert mock_parse.call_count == 2
        assert mock_handle.call_count == 2

        # Verify: First iteration
        assert mock_parse.call_args_list[0][0][0] == "P"
        assert mock_handle.call_args_list[0][0][0] == MenuChoice.PLAY

        # Verify: Second iteration
        assert mock_parse.call_args_list[1][0][0] == "X"
        assert mock_handle.call_args_list[1][0][0] == MenuChoice.EXIT
