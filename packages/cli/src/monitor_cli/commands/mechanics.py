"""
CLI commands for resolving mechanics (DL-24).
"""

import asyncio
import typer
from rich.console import Console
from rich.panel import Panel

from monitor_agents.resolver import Resolver

app = typer.Typer(help="Resolve game mechanics (checks, saves, combat)")
console = Console()


def _get_agent():
    return Resolver()


def _run_async(coro):
    return asyncio.run(coro)


@app.command("check")
def check_stat(
    entity_id: str = typer.Argument(..., help="UUID of the entity"),
    stat: str = typer.Argument(..., help="Name of the stat (Strength, Stealth, etc.)"),
    dc: int = typer.Option(15, help="Difficulty Class"),
):
    """
    Perform a mechanic check (Attribute or Skill).
    """
    agent = _get_agent()
    
    console.print(f"[bold]Resolving {stat} check for {entity_id} vs DC {dc}...[/bold]")
    
    try:
        result = _run_async(agent.resolve_check(entity_id, stat, dc))
        
        if "error" in result:
             console.print(f"[red]Error: {result['error']}[/red]")
             return

        # Display result
        success_color = "green" if result["success"] else "red"
        success_text = "SUCCESS" if result["success"] else "FAILURE"
        
        panel_content = f"""
        [bold {success_color}]{success_text}[/bold {success_color}]
        
        System: {result['system']}
        Stat: {result['stat']} (Mod: {result['modifier']})
        Details: {result['details']}
        """
        
        console.print(Panel(panel_content, title="Resolution Result", border_style=success_color))

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
