"""
MONITOR Universe Commands — Universe management for World Design mode.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2)
NEVER IMPORTS: monitor_data (Layer 1)

Usage:
    $ monitor universe list
    $ monitor universe list-multiverses
    $ monitor universe create --name "My World" --description "A fantasy world"
    $ monitor universe show <universe-id>
"""

from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="Manage universes and multiverses (World Design mode)")
console = Console()


@app.command("list")
def list_universes() -> None:
    """List all available universes from the canonical Neo4j store."""
    asyncio.run(_run_list_universes())


@app.command("list-multiverses")
def list_multiverses() -> None:
    """List all available multiverses."""
    asyncio.run(_run_list_multiverses())


@app.command("create")
def create_universe(
    name: str = typer.Option(..., "--name", "-n", help="Universe name"),
    description: str = typer.Option("", "--description", "-d", help="Universe description"),
    multiverse_id: Optional[str] = typer.Option(
        None, "--multiverse", "-m", help="Parent Multiverse UUID"
    ),
) -> None:
    """Create a new universe."""
    asyncio.run(_run_create_universe(name, description, multiverse_id))


@app.command("show")
def show_universe(
    universe_id: str = typer.Argument(..., help="Universe UUID"),
) -> None:
    """Show details of a specific universe."""
    asyncio.run(_run_show_universe(universe_id))


async def _run_list_universes() -> None:
    """List all available universes."""
    try:
        from monitor_agents.canonkeeper import CanonKeeper

        ck = CanonKeeper()
        universes = await ck.list_universes()

        if not universes:
            console.print("[yellow]No universes found in canon.[/yellow]")
            console.print('[dim]Create one with: monitor universe create --name "My World"[/dim]')
            return

        # Create a rich table
        table = Table(title="Available Universes")
        table.add_column("ID", style="cyan", no_wrap=False)
        table.add_column("Name", style="green")
        table.add_column("Description", style="dim")
        table.add_column("Genre", style="magenta")

        for universe in universes:
            table.add_row(
                universe.get("id", "N/A"),
                universe.get("name", "N/A"),
                (universe.get("description", "") or "")[:50] or "No description",
                universe.get("genre", "N/A") or "N/A",
            )

        console.print(table)
        console.print(f"\n[bold]Total:[/bold] {len(universes)} universe(s)")

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to list universes: {exc}")


async def _run_list_multiverses() -> None:
    """List all available multiverses."""
    try:
        from monitor_agents.canonkeeper import CanonKeeper

        ck = CanonKeeper()
        multiverses = await ck.list_multiverses()

        if not multiverses:
            console.print("[yellow]No multiverses found in canon.[/yellow]")
            return

        # Create a rich table
        table = Table(title="Available Multiverses")
        table.add_column("ID", style="cyan", no_wrap=False)
        table.add_column("Name", style="green")
        table.add_column("System", style="yellow")
        table.add_column("Description", style="dim")

        for mv in multiverses:
            table.add_row(
                mv.get("id", "N/A"),
                mv.get("name", "N/A"),
                mv.get("system_name", "N/A"),
                (mv.get("description", "") or "")[:50] or "No description",
            )

        console.print(table)
        console.print(f"\n[bold]Total:[/bold] {len(multiverses)} multiverse(s)")

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to list multiverses: {exc}")


async def _run_create_universe(
    name: str, description: str, multiverse_id_str: Optional[str] = None
) -> None:
    """Create a new universe."""
    try:
        from monitor_agents.canonkeeper import CanonKeeper

        ck = CanonKeeper()

        # 1. Resolve Multiverse
        multiverse_id: Optional[UUID] = None
        if multiverse_id_str:
            multiverse_id = UUID(multiverse_id_str)
        else:
            # Try to find an existing multiverse or create a default one
            mvs = await ck.list_multiverses()
            if mvs:
                multiverse_id = UUID(mvs[0]["id"])
                console.print(f"[dim]Using existing multiverse: {mvs[0]['name']}[/dim]")
            else:
                # Need to ensure Omniverse and create a Multiverse first
                console.print("[yellow]No multiverse found. Creating default...[/yellow]")
                # Use neo4j_ensure_omniverse tool via CanonKeeper
                omni_res = await ck.call_tool("neo4j_ensure_omniverse", {})
                omniverse_id = UUID(omni_res["omniverse_id"])

                # Create a default multiverse
                mv_params = {
                    "omniverse_id": str(omniverse_id),
                    "name": "Default Multiverse",
                    "system_name": "Generic",
                    "description": "Default container for universes",
                }
                mv_res = await ck.call_tool("neo4j_create_multiverse", {"params": mv_params})
                multiverse_id = UUID(mv_res["id"])
                console.print(f"[green]Created default multiverse: {multiverse_id}[/green]")

        # 2. Create the Universe
        universe_params = {
            "multiverse_id": str(multiverse_id),
            "name": name,
            "description": description,
            "genre": "fantasy",  # default
            "authority": "system",
            "canon_level": "canon",
        }
        universe = await ck.create_universe(universe_params)

        if "error" in universe:
            console.print(f"[red]Error:[/red] Failed to create universe: {universe['error']}")
            raise typer.Exit(code=1)

        console.print(
            Panel(
                f"[bold]Universe Created[/bold]\n"
                f"ID: [cyan]{universe.get('id')}[/cyan]\n"
                f"Name: [green]{universe.get('name')}[/green]\n"
                f"Multiverse: [yellow]{multiverse_id}[/yellow]",
                title="Success",
                border_style="green",
            )
        )

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to create universe: {exc}")
        raise typer.Exit(code=1)


async def _run_show_universe(universe_id_str: str) -> None:
    """Show details of a specific universe."""
    try:
        from monitor_agents.canonkeeper import CanonKeeper

        ck = CanonKeeper()
        universe_id = UUID(universe_id_str)
        universe = await ck.get_universe(universe_id)

        if not universe:
            console.print(f"[red]Error:[/red] Universe '{universe_id}' not found in canon.")
            raise typer.Exit(code=1)

        # Display universe details
        console.print(
            Panel(
                f"[bold]ID:[/bold] [cyan]{universe.get('id', 'N/A')}[/cyan]\n"
                f"[bold]Name:[/bold] [green]{universe.get('name', 'N/A')}[/green]\n"
                f"[bold]Description:[/bold] [dim]{universe.get('description', 'No description')}[/dim]\n"
                f"[bold]Genre:[/bold] {universe.get('genre', 'N/A')}\n"
                f"[bold]Multiverse ID:[/bold] {universe.get('multiverse_id', 'N/A')}\n"
                f"[bold]Created At:[/bold] {universe.get('created_at', 'Unknown')}",
                title="Universe Details",
                border_style="blue",
            )
        )

    except ValueError:
        console.print(f"[red]Error:[/red] Invalid UUID format: {universe_id_str}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to show universe: {exc}")
        raise typer.Exit(code=1)
