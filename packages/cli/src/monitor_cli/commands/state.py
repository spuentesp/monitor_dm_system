"""
CLI commands for managing Character Working State (DL-26).
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from monitor_cli._helpers import get_resolver, parse_tool_result, run_async

app = typer.Typer(help="Manage character working state (HP, resources, temp effects)")
console = Console()


@app.command("list")
def list_states(
    scene_id: Optional[str] = typer.Option(None, help="Filter by Scene ID"),
    limit: int = 20,
) -> None:
    """List all active working states."""
    agent = get_resolver()

    args = {"params": {"scene_id": scene_id, "limit": limit}}

    try:
        result_json = run_async(agent.call_tool("mongodb_list_working_states", args))
        data = parse_tool_result(result_json)
        if not data:
            console.print("[red]No response from tool[/red]")
            return

        states = data.get("states", [])

        if not states:
            console.print("No states found.")
            return

        table = Table(title="Character Working States")
        table.add_column("State ID", style="cyan")
        table.add_column("Entity ID", style="magenta")
        table.add_column("HP", style="green")
        table.add_column("Scene ID", style="blue")

        for state in states:
            hp = state.get("resources", {}).get("hp", {}).get("current", "?")
            table.add_row(state["state_id"], state["entity_id"], str(hp), state["scene_id"])

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@app.command("get")
def get_state(entity_id: str, scene_id: str) -> None:
    """Get detailed state for an entity in a scene."""
    agent = get_resolver()

    args = {"entity_id": entity_id, "scene_id": scene_id}

    try:
        result_json = run_async(agent.call_tool("mongodb_get_working_state", args))
        data = parse_tool_result(result_json)
        if not data:
            console.print("[red]No state found or error[/red]")
            return

        state = data.get("state")

        console.print_json(data=state)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@app.command("mod")
def add_modification(
    state_id: str,
    stat: str,
    change: int,
    source: str = "CLI",
) -> None:
    """Add a stat modification (damage/heal/buff)."""
    agent = get_resolver()

    # The tool mongodb_add_modification takes 'params': AddStatModification
    args = {
        "params": {
            "state_id": state_id,
            "stat_or_resource": stat,
            "change": change,
            "source": source,
        }
    }

    try:
        result_json = run_async(agent.call_tool("mongodb_add_modification", args))
        console.print_json(result_json)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
