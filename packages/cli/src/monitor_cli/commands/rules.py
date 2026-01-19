"""
CLI commands for managing Game Systems (DL-20).
"""

import asyncio
import json
import os
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from monitor_agents.resolver import Resolver

app = typer.Typer(help="Manage game systems (rules, mechanics, stats)")
console = Console()


def _get_agent():
    return Resolver()


def _run_async(coro):
    return asyncio.run(coro)


@app.command("import")
def import_system(
    file_path: str = typer.Argument(..., help="Path to JSON system definition file"),
):
    """Import a game system definition from a JSON file."""
    if not os.path.exists(file_path):
        console.print(f"[red]File not found: {file_path}[/red]")
        return
        
    try:
        with open(file_path, "r") as f:
            system_data = json.load(f)
            
        agent = _get_agent()
        
        # Calling mongodb_create_game_system which expects 'params: GameSystemCreate'
        args = {
            "params": system_data
        }
        
        console.print(f"Importing system: {system_data.get('name')}...")
        result_json = _run_async(agent.call_tool("mongodb_create_game_system", args))
        
        if result_json:
            console.print("[green]System imported successfully![/green]")
            console.print_json(result_json)
        else:
             console.print("[red]No response from tool[/red]")

    except json.JSONDecodeError:
        console.print(f"[red]Invalid JSON file: {file_path}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@app.command("list")
def list_systems():
    """List all available game systems."""
    agent = _get_agent()
    
    args = {
        "params": {
            "limit": 20
        }
    }
    
    try:
        result_json = _run_async(agent.call_tool("mongodb_list_game_systems", args))
        if not result_json:
             console.print("[red]No response[/red]")
             return

        data = json.loads(result_json)
        systems = data.get("systems", [])
        
        if not systems:
            console.print("No game systems found.")
            return

        table = Table(title="Game Systems")
        table.add_column("System ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="magenta")
        table.add_column("Version", style="green")
        table.add_column("Mechanic", style="blue")

        for sys in systems:
            table.add_row(
                sys["id"],
                sys["name"],
                sys.get("version", ""),
                sys.get("core_mechanic", {}).get("type", "")
            )
            
        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
