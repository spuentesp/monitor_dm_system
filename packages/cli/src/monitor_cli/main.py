# ruff: noqa: E402
"""
MONITOR CLI Entry Point.

This module defines the main Typer application and registers all commands.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2), external libraries
NEVER IMPORTS: monitor_data (Layer 1) - that would skip Layer 2!

Commands (registered below — this list must match reality):
    $ monitor play        # P- use cases - Solo Play mode
    $ monitor manage      # M- use cases - World Design mode
    $ monitor universe    # Universe administration
    $ monitor ingest      # I- use cases - Document upload
    $ monitor state       # Character state (HP, resources)
    $ monitor rules       # RS- use cases - Game system definition
    $ monitor mechanics   # Resolve mechanics (rolls, checks)
    $ monitor playtest    # Automated test sessions

The GM Assistant (CF- use cases) has no CLI surface by design — it lives in
the web UI at `/gm` (see docs/architecture/GM_ASSISTANT_MODE_PLAN.md). World
authoring lives in the web UI at `/forge` (docs/architecture/FORGE_MODE_PLAN.md).
"""

import typer
from dotenv import load_dotenv
from rich.console import Console

# Load environment variables
load_dotenv()

app = typer.Typer(
    name="monitor",
    help="MONITOR - Auto-GM for tabletop RPGs",
    no_args_is_help=True,
)

console = Console()


from monitor_cli.commands import (
    doctor,
    ingest,
    ingest_doctor,
    ingest_jobs,
    init,
    manage,
    mechanics,
    play,
    playtest,
    rules,
    state,
    universe,
)

# play_errors registers "errors" onto play.app's Typer instance directly
# (mounted as `monitor play errors`, not a separate top-level group) — the
# import alone is what triggers its @app.command("errors") registration.
from monitor_cli.commands import play_errors  # noqa: F401

app.add_typer(state.app, name="state", help="Manage character working state (HP, resources)")
app.add_typer(rules.app, name="rules", help="Manage game systems (D&D, Vampire, etc.)")
app.add_typer(mechanics.app, name="mechanics", help="Resolve game mechanics (checks, rolls)")
app.add_typer(
    doctor.app,
    name="doctor",
    help="System-wide health check + idempotent repair (try `monitor ingest-doctor` for ingest-only)",
)
app.add_typer(
    init.app,
    name="init",
    help="First-run wizard: pick a provider and bootstrap the database schema",
)
app.add_typer(ingest.app, name="ingest", help="Ingest documents into the world knowledge base")
app.add_typer(ingest_jobs.app, name="ingest-jobs", help="Inspect and manage in-flight ingestion jobs")
app.add_typer(
    ingest_doctor.app,
    name="ingest-doctor",
    help="Pre-launch operator diagnostic for the ingest pipeline",
)
app.add_typer(
    playtest.app,
    name="playtest",
    help="Run live system playtests and compare gameplay logs",
)
app.add_typer(play.app, name="play", help="Start or continue a story (Solo Play)")
app.add_typer(universe.app, name="universe", help="Manage universes (World Design mode)")
app.add_typer(manage.app, name="manage", help="Manage entities (NPCs, locations, objects, etc.)")


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
