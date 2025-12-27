"""
MONITOR CLI Entry Point.

This module defines the main Typer application and registers all commands.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2), external libraries
NEVER IMPORTS: monitor_data (Layer 1) - that would skip Layer 2!

Usage:
    $ monitor --help
    $ monitor play
    $ monitor ingest ./document.pdf
    $ monitor query "What happened to Gandalf?"
    $ monitor manage entities
"""

import typer
from rich.console import Console

# Import commands
# from monitor_cli.commands import play, ingest, query, manage

app = typer.Typer(
    name="monitor",
    help="MONITOR - Auto-GM for tabletop RPGs",
    no_args_is_help=True,
)

console = Console()


# Register command groups
# app.add_typer(play.app, name="play", help="Start or continue a story")
# app.add_typer(ingest.app, name="ingest", help="Upload and process documents")
# app.add_typer(query.app, name="query", help="Query canonical facts")
# app.add_typer(manage.app, name="manage", help="Manage entities and universes")


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
