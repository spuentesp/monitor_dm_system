"""
CLI commands for managing Character Working State (DL-26).
"""

import asyncio
import json
from uuid import UUID
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from monitor_agents.resolver import Resolver

app = typer.Typer(help="Manage character working state (HP, resources, temp effects)")
console = Console()


def _get_agent():
    return Resolver()


def _run_async(coro):
    return asyncio.run(coro)


@app.command("list")
def list_states(
    scene_id: Optional[str] = typer.Option(None, help="Filter by Scene ID"),
    limit: int = 20,
):
    """List all active working states."""
    agent = _get_agent()
    
    args = {
        "params": {
            "scene_id": scene_id,
            "limit": limit
        }
    }
    
    # We call mongodb_list_working_states
    # Note: The tool arg is 'params', which is WorkingStateFilter.
    # We must match the schema structure expected by the tool harness.
    # The tool expects `params: WorkingStateFilter`.
    # When calling via `call_tool`, we pass a dict.
    
    try:
        result_json = _run_async(agent.call_tool("mongodb_list_working_states", args))
        if not result_json:
             console.print("[red]No response from tool[/red]")
             return

        data = json.loads(result_json)
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
            table.add_row(
                state["state_id"],
                state["entity_id"],
                str(hp),
                state["scene_id"]
            )
            
        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@app.command("get")
def get_state(entity_id: str, scene_id: str):
    """Get detailed state for an entity in a scene."""
    agent = _get_agent()
    
    args = {
        "entity_id": entity_id,
        "scene_id": scene_id
    }
    
    try:
        result_json = _run_async(agent.call_tool("mongodb_get_working_state", args))
        if not result_json:
             console.print("[red]No state found or error[/red]")
             return

        data = json.loads(result_json)
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
):
    """Add a stat modification (damage/heal/buff)."""
    agent = _get_agent()
    
    # The tool mongodb_add_modification takes 'params': AddStatModification
    args = {
        "params": {
            "state_id": state_id,
            "stat_or_resource": stat,
            "change": change,
            "source": source
        }
    }
    
    try:
        result_json = _run_async(agent.call_tool("mongodb_add_modification", args))
        console.print_json(result_json)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
