"""
MainMenuProcessor — CLI main menu handler (SYS-2).

Provides menu display, input parsing, and menu loop for the MONITOR CLI.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libraries
CALLED BY: CLI (Layer 3)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MenuChoice(str, Enum):
    """Available main menu choices."""

    PLAY = "play"
    MANAGE = "manage"
    QUERY = "query"
    INGEST = "ingest"
    SETTINGS = "settings"
    EXIT = "exit"
    INVALID = "invalid"


class MainMenuProcessor:
    """
    Process the main menu for the MONITOR CLI.

    Displays menu options, parses user input, and routes to
    the appropriate action.
    """

    MENU_ITEMS: List[Dict[str, str]] = [
        {"key": "P", "label": "Play — Start or continue a story", "choice": MenuChoice.PLAY},
        {
            "key": "M",
            "label": "Manage — Manage universes, entities, facts",
            "choice": MenuChoice.MANAGE,
        },
        {
            "key": "Q",
            "label": "Query — Search and retrieve information",
            "choice": MenuChoice.QUERY,
        },
        {"key": "I", "label": "Ingest — Import and process content", "choice": MenuChoice.INGEST},
        {"key": "S", "label": "Settings — Configure preferences", "choice": MenuChoice.SETTINGS},
        {"key": "X", "label": "Exit — Quit MONITOR", "choice": MenuChoice.EXIT},
    ]

    def display_menu(self) -> None:
        """
        Display the main menu to the console.

        Prints the formatted menu with letter options and a prompt.
        """
        lines = ["\n=== MONITOR — Narrative AI ===\n"]
        for item in self.MENU_ITEMS:
            lines.append(f"  [{item['key']}] {item['label']}")
        lines.append("\n  > ")
        print("\n".join(lines))

    def parse_menu_input(self, user_input: str) -> MenuChoice:
        """
        Parse user input into a MenuChoice.

        Args:
            user_input: Raw user input string.

        Returns:
            MenuChoice matching the input, or INVALID for unrecognized input.

        Raises:
            ValueError: If user_input is None.
            TypeError: If user_input is not a string.
        """
        if user_input is None:
            raise ValueError("user_input cannot be None")
        if not isinstance(user_input, str):
            raise TypeError(f"user_input must be a string, got {type(user_input).__name__}")

        cleaned = user_input.strip().lower()

        # Direct letter/word mappings
        mapping = {
            "p": MenuChoice.PLAY,
            "play": MenuChoice.PLAY,
            "m": MenuChoice.MANAGE,
            "manage": MenuChoice.MANAGE,
            "q": MenuChoice.QUERY,
            "query": MenuChoice.QUERY,
            "i": MenuChoice.INGEST,
            "ingest": MenuChoice.INGEST,
            "s": MenuChoice.SETTINGS,
            "settings": MenuChoice.SETTINGS,
            "x": MenuChoice.EXIT,
            "exit": MenuChoice.EXIT,
        }

        if cleaned in mapping:
            return mapping[cleaned]

        # Number mappings
        number_map = {
            "1": MenuChoice.PLAY,
            "2": MenuChoice.MANAGE,
            "3": MenuChoice.QUERY,
            "4": MenuChoice.INGEST,
            "5": MenuChoice.SETTINGS,
        }
        if cleaned in number_map:
            return number_map[cleaned]

        return MenuChoice.INVALID

    async def handle_menu_choice(self, choice: MenuChoice) -> bool:
        """
        Handle a parsed menu choice.

        Args:
            choice: Parsed MenuChoice enum value.

        Returns:
            True if the application should continue, False if it should exit.
        """
        if choice == MenuChoice.EXIT:
            return False
        if choice == MenuChoice.INVALID:
            # Display error for invalid choice but continue
            print("Invalid choice. Please enter a valid option.")
            return True
        return True

    async def run_menu_loop(self) -> Dict[str, Any]:
        """
        Run the interactive menu loop.

        Displays the menu, reads input, and processes choices
        until the user quits.

        Returns:
            Final result dict with the last action taken.
        """
        while True:
            self.display_menu()
            try:
                user_input = input("> ")
            except (EOFError, KeyboardInterrupt):
                break

            choice = self.parse_menu_input(user_input)
            should_continue = await self.handle_menu_choice(choice)

            if not should_continue:
                break

        return {
            "action": "exit",
            "route": "",
            "description": "User exited the menu",
        }
