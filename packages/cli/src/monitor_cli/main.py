"""
MONITOR CLI Entry Point.

This module defines the main Typer application and registers all commands.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2), external libraries
NEVER IMPORTS: monitor_data (Layer 1) - that would skip Layer 2!

Commands (7 groups):
    $ monitor play      # P- use cases - Solo Play mode
    $ monitor manage    # M- use cases - World Design mode
    $ monitor query     # Q- use cases - Canon exploration
    $ monitor ingest    # I- use cases - Document upload
    $ monitor copilot   # CF- use cases - GM Assistant mode
    $ monitor story     # ST- use cases - Arc planning
    $ monitor rules     # RS- use cases - Game system definition
"""

import typer
from rich.console import Console
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import commands
# from monitor_cli.commands import play, manage, query, ingest, copilot, story, rules

app = typer.Typer(
    name="monitor",
    help="MONITOR - Auto-GM for tabletop RPGs",
    no_args_is_help=True,
)

console = Console()


# Register command groups (7 total)
# Register command groups (7 total)
# app.add_typer(play.app, name="play", help="Start or continue a story (Solo Play)")
# app.add_typer(manage.app, name="manage", help="Manage universes, entities, facts (World Design)")
# app.add_typer(query.app, name="query", help="Search and explore canon")
# app.add_typer(ingest.app, name="ingest", help="Upload and process documents")
# app.add_typer(copilot.app, name="copilot", help="GM assistant features (Assisted GM)")
# app.add_typer(story.app, name="story", help="Arc planning, factions, what-if scenarios")
# app.add_typer(rules.app, name="rules", help="Game system definition and management")

from monitor_cli.commands import state
app.add_typer(state.app, name="state", help="Manage character working state (HP, resources)")


@app.command()
def version() -> None:
    """Show version information."""
    from monitor_cli import __version__

    console.print(f"MONITOR CLI v{__version__}")


@app.callback()
def main_callback() -> None:
    """
    MONITOR - Multi-Ontology Narrative Intelligence Through Omniversal Representation.

    An Auto-GM system for tabletop RPGs.
    """
    pass


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
