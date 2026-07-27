"""
MONITOR Manage Commands — Entity management for World Design mode.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2)
NEVER IMPORTS: monitor_data (Layer 1)

Usage:
    $ monitor manage list --universe <uuid>
    $ monitor manage create --universe <uuid> --type NPC --name "Gandalf"
    $ monitor manage show <entity-id>
    $ monitor manage update <entity-id> --name "New Name"
    $ monitor manage delete <entity-id>
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from monitor_cli._helpers import get_resolver, parse_tool_result

app = typer.Typer(help="Manage entities (World Design mode)")
tables_app = typer.Typer(help="Manage random tables")
app.add_typer(tables_app, name="tables")

snapshots_app = typer.Typer(help="Manage world snapshots")
app.add_typer(snapshots_app, name="snapshots")

templates_app = typer.Typer(help="Manage entity templates")
app.add_typer(templates_app, name="templates")

console = Console()


@app.command("list")
def list_entities(
    universe_id: str = typer.Option(..., "--universe", "-u", help="Universe UUID"),
) -> None:
    """List all entities in a universe."""
    asyncio.run(_run_list_entities(universe_id))


@app.command("create")
def create_entity(
    universe_id: str = typer.Option(..., "--universe", "-u", help="Universe UUID"),
    entity_type: str = typer.Option(..., "--type", "-t", help="Entity type (NPC, LOCATION, ITEM, etc.)"),
    name: str = typer.Option(..., "--name", "-n", help="Entity name"),
    description: str = typer.Option("", "--description", "-d", help="Entity description"),
) -> None:
    """Create a new entity."""
    asyncio.run(_run_create_entity(universe_id, entity_type, name, description))


@app.command("show")
def show_entity(
    entity_id: str = typer.Argument(..., help="Entity UUID"),
) -> None:
    """Show details of a specific entity."""
    asyncio.run(_run_show_entity(entity_id))


@app.command("update")
def update_entity(
    entity_id: str = typer.Argument(..., help="Entity UUID"),
    name: str = typer.Option(None, "--name", "-n", help="New name"),
    description: str = typer.Option(None, "--description", "-d", help="New description"),
) -> None:
    """Update an entity."""
    asyncio.run(_run_update_entity(entity_id, name, description))


@app.command("delete")
def delete_entity(
    entity_id: str = typer.Argument(..., help="Entity UUID"),
) -> None:
    """Delete an entity."""
    asyncio.run(_run_delete_entity(entity_id))


@tables_app.command("list")
def list_tables(
    universe_id: str = typer.Option(None, "--universe", "-u", help="Universe UUID"),
    table_type: str = typer.Option(None, "--type", "-t", help="Table type"),
) -> None:
    """List all random tables."""
    asyncio.run(_run_list_tables(universe_id, table_type))


@tables_app.command("roll")
def roll_on_table(
    table_id: str = typer.Argument(..., help="Table UUID"),
) -> None:
    """Roll on a random table."""
    asyncio.run(_run_roll_on_table(table_id))


@snapshots_app.command("list")
def list_snapshots(
    universe_id: str = typer.Option(..., "--universe", "-u", help="Universe UUID"),
) -> None:
    """List all snapshots for a universe."""
    asyncio.run(_run_list_snapshots(universe_id))


@snapshots_app.command("create")
def create_snapshot(
    universe_id: str = typer.Option(..., "--universe", "-u", help="Universe UUID"),
    name: str = typer.Option(..., "--name", "-n", help="Snapshot name"),
    description: str = typer.Option("", "--description", "-d", help="Snapshot description"),
) -> None:
    """Create a new world snapshot."""
    asyncio.run(_run_create_snapshot(universe_id, name, description))


@templates_app.command("list")
def list_templates(
    universe_id: str = typer.Option(..., "--universe", "-u", help="Universe UUID"),
    entity_type: str = typer.Option(None, "--type", "-t", help="Entity type"),
) -> None:
    """List all entity templates in a universe."""
    asyncio.run(_run_list_templates(universe_id, entity_type))


@templates_app.command("create")
def create_template(
    universe_id: str = typer.Option(..., "--universe", "-u", help="Universe UUID"),
    name: str = typer.Option(..., "--name", "-n", help="Template name"),
    entity_type: str = typer.Option(..., "--type", "-t", help="Entity type (NPC, LOCATION, ITEM, etc.)"),
    description: str = typer.Option("", "--description", "-d", help="Template description"),
    detail_level: str = typer.Option(
        "stub", "--detail", help="Default detail level (stub, sketched, detailed, elaborated)"
    ),
    parent: str = typer.Option(None, "--parent", "-p", help="Parent template UUID for inheritance"),
) -> None:
    """Create a new entity template."""
    asyncio.run(_run_create_template(universe_id, name, entity_type, description, detail_level, parent))


@templates_app.command("show")
def show_template(
    template_id: str = typer.Argument(..., help="Template UUID"),
) -> None:
    """Show details of a specific entity template."""
    asyncio.run(_run_show_template(template_id))


@templates_app.command("delete")
def delete_template(
    template_id: str = typer.Argument(..., help="Template UUID"),
) -> None:
    """Delete an entity template."""
    asyncio.run(_run_delete_template(template_id))


@tables_app.command("create")
def create_table(
    universe_id: str = typer.Option(None, "--universe", "-u", help="Universe UUID (optional for global tables)"),
    name: str = typer.Option(..., "--name", "-n", help="Table name"),
    table_type: str = typer.Option(
        "custom",
        "--type",
        "-t",
        help="Table type (encounter, loot, name, trait, weather, rumor, npc, event, location, complication, custom)",
    ),
    dice_formula: str = typer.Option("1d20", "--dice", "-d", help="Dice formula (e.g., 1d20, 2d6, 1d100)"),
    entries: str = typer.Option(..., "--entries", "-e", help="Comma-separated table entries"),
) -> None:
    """Create a new random table."""
    asyncio.run(_run_create_table(universe_id, name, table_type, dice_formula, entries))


@tables_app.command("show")
def show_table(
    table_id: str = typer.Argument(..., help="Table UUID"),
) -> None:
    """Show details of a specific random table."""
    asyncio.run(_run_show_table(table_id))


async def _run_list_tables(universe_id: str | None, table_type: str | None) -> None:
    """List all random tables."""
    try:
        agent = get_resolver()

        params = {"filters": {"universe_id": universe_id, "table_type": table_type, "limit": 100}}

        raw_result = await agent.call_tool("mongodb_list_random_tables", params)
        result = parse_tool_result(raw_result)
        tables = result.get("tables", [])

        if not tables:
            console.print("[yellow]No random tables found.[/yellow]")
            return

        table = Table(title="Random Tables")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="blue")
        table.add_column("Dice", style="magenta")

        for t in tables:
            table.add_row(
                t.get("table_id", "N/A"),
                t.get("name", "N/A"),
                t.get("table_type", "N/A"),
                t.get("dice_formula", "N/A"),
            )

        console.print(table)
        console.print(f"\n[bold]Total:[/bold] {len(tables)} table(s)")

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to list tables: {exc}")


async def _run_roll_on_table(table_id: str) -> None:
    """Roll on a random table."""
    try:
        agent = get_resolver()

        result_raw = await agent.call_tool("mongodb_roll_on_table", {"table_id": table_id})
        result = parse_tool_result(result_raw)

        console.print(
            Panel(
                f"[bold]Table:[/bold] {result.get('table_name', 'Unknown')}\n"
                f"[bold]Roll:[/bold]  {result.get('roll')} [dim]({result.get('formula')})[/dim]\n"
                f"[bold]Result:[/bold] [green]{result.get('value')}[/green]",
                title="🎲 Dice Roll",
                border_style="magenta",
            )
        )

        # Show subtable results if any
        for sub in result.get("sub_results", []):
            console.print(f"  └─ [bold]Subtable:[/bold] {sub.get('table_name')} -> {sub.get('value')}")

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to roll on table: {exc}")


async def _run_list_snapshots(universe_id: str) -> None:
    """List all snapshots for a universe."""
    try:
        agent = get_resolver()

        params = {"filters": {"universe_id": universe_id}}
        raw_result = await agent.call_tool("mongodb_list_world_snapshots", params)
        result = parse_tool_result(raw_result)
        snapshots = result.get("snapshots", [])

        if not snapshots:
            console.print(f"[yellow]No snapshots found for universe {universe_id}.[/yellow]")
            return

        table = Table(title=f"Snapshots for Universe {universe_id}")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Created At", style="blue")
        table.add_column("Counts (E/F/R/A)", style="magenta")

        for s in snapshots:
            counts = (
                f"{s.get('entity_count')}/{s.get('fact_count')}/{s.get('relationship_count')}/{s.get('axiom_count')}"
            )
            table.add_row(
                s.get("snapshot_id", "N/A"),
                s.get("name", "N/A"),
                s.get("created_at", "N/A"),
                counts,
            )

        console.print(table)

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to list snapshots: {exc}")


async def _run_create_snapshot(universe_id: str, name: str, description: str) -> None:
    """Create a new world snapshot."""
    try:
        agent = get_resolver()

        params = {"params": {"universe_id": universe_id, "name": name, "description": description}}

        console.print(f"[dim]Capturing snapshot of universe {universe_id}...[/dim]")
        raw_result = await agent.call_tool("mongodb_create_world_snapshot", params)
        result = parse_tool_result(raw_result)

        console.print(
            Panel(
                f"[bold]Snapshot Created[/bold]\n"
                f"ID:   [cyan]{result.get('snapshot_id')}[/cyan]\n"
                f"Name: [green]{result.get('name')}[/green]\n"
                f"Stats: {result.get('entity_count')} entities, {result.get('fact_count')} facts",
                title="Success",
                border_style="green",
            )
        )

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to create snapshot: {exc}")


async def _run_list_templates(universe_id: str, entity_type: str | None) -> None:
    """List all entity templates in a universe."""
    try:
        agent = get_resolver()

        params = {"filters": {"universe_id": universe_id, "entity_type": entity_type}}

        raw_result = await agent.call_tool("mongodb_list_entity_templates", params)
        result = parse_tool_result(raw_result)
        templates = result.get("templates", [])

        if not templates:
            console.print(f"[yellow]No templates found in universe {universe_id}.[/yellow]")
            return

        table = Table(title=f"Templates in Universe {universe_id}")
        table.add_column("ID", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Name", style="blue")
        table.add_column("Usage", style="magenta")

        for t in templates:
            table.add_row(
                t.get("template_id", "N/A"),
                t.get("entity_type", "N/A"),
                t.get("name", "N/A"),
                str(t.get("usage_count", 0)),
            )

        console.print(table)

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to list templates: {exc}")


async def _run_list_entities(universe_id: str) -> None:
    """List all entities in a universe."""
    try:
        agent = get_resolver()

        params = {"filters": {"universe_id": universe_id}}
        raw_result = await agent.call_tool("neo4j_list_entities", params)
        result = parse_tool_result(raw_result)
        entities = result.get("entities", [])

        if not entities:
            console.print(f"[yellow]No entities found in universe {universe_id}.[/yellow]")
            console.print(
                '[dim]Create one with: monitor manage create --universe <uuid> --type NPC --name "Name"[/dim]'
            )
            return

        # Create a rich table
        table = Table(title=f"Entities in Universe {universe_id}")
        table.add_column("ID", style="cyan", no_wrap=False)
        table.add_column("Type", style="green")
        table.add_column("Name", style="blue")
        table.add_column("Description", style="dim")

        for entity in entities:
            table.add_row(
                entity.get("entity_id", "N/A"),
                entity.get("entity_type", "N/A"),
                entity.get("name", "N/A"),
                (entity.get("description", "") or "No description")[:50],
            )

        console.print(table)
        console.print(f"\n[bold]Total:[/bold] {len(entities)} entity(ies)")

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to list entities: {exc}")


async def _run_create_entity(universe_id: str, entity_type: str, name: str, description: str) -> None:
    """Create a new entity via agent layer."""
    try:
        agent = get_resolver()

        params = {
            "params": {
                "universe_id": universe_id,
                "entity_type": entity_type.upper(),
                "name": name,
                "description": description,
            }
        }

        raw_result = await agent.call_tool("neo4j_create_entity", params)
        result = parse_tool_result(raw_result)
        entity_id = result.get("entity_id", "N/A")

        console.print(
            Panel(
                f"[bold]Entity Created[/bold]\n"
                f"ID: [cyan]{entity_id}[/cyan]\n"
                f"Type: [green]{entity_type.upper()}[/green]\n"
                f"Name: [blue]{name}[/blue]\n"
                f"Description: [dim]{description or 'No description'}[/dim]",
                title="Success",
                border_style="green",
            )
        )
        console.print(f"\n[dim]Universe: {universe_id}[/dim]")

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to create entity: {exc}")
        raise typer.Exit(code=1)


async def _run_show_entity(entity_id: str) -> None:
    """Show details of a specific entity via agent layer."""
    try:
        agent = get_resolver()

        params = {"entity_id": entity_id}
        raw_result = await agent.call_tool("neo4j_get_entity", params)
        entity = parse_tool_result(raw_result).get("entity") or parse_tool_result(raw_result)

        if not entity:
            console.print(f"[red]Error:[/red] Entity '{entity_id}' not found.")
            raise typer.Exit(code=1)

        console.print(
            Panel(
                f"[bold]ID:[/bold] [cyan]{entity.get('entity_id', 'N/A')}[/cyan]\n"
                f"[bold]Type:[/bold] [green]{entity.get('entity_type', 'N/A')}[/green]\n"
                f"[bold]Name:[/bold] [blue]{entity.get('name', 'N/A')}[/blue]\n"
                f"[bold]Description:[/bold] [dim]{entity.get('description', 'No description')}[/dim]\n"
                f"[bold]Universe ID:[/bold] {entity.get('universe_id', 'Unknown')}",
                title="Entity Details",
                border_style="blue",
            )
        )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to show entity: {exc}")
        raise typer.Exit(code=1)


async def _run_update_entity(entity_id: str, name: str | None, description: str | None) -> None:
    """Update an entity via agent layer."""
    try:
        agent = get_resolver()

        if not name and not description:
            console.print("[yellow]Warning:[/yellow] No changes specified. Use --name or --description.")
            return

        update_fields = {}
        if name:
            update_fields["name"] = name
        if description is not None:
            update_fields["description"] = description

        params = {"entity_id": entity_id, "updates": update_fields}
        raw_result = await agent.call_tool("neo4j_update_entity", params)
        result = parse_tool_result(raw_result)

        if not result or result.get("error"):
            console.print(f"[red]Error:[/red] Entity '{entity_id}' not found.")
            raise typer.Exit(code=1)

        console.print(
            Panel(
                f"[bold]Entity Updated[/bold]\n"
                f"ID: [cyan]{entity_id}[/cyan]\n"
                f"Changes: [green]{', '.join(update_fields.keys())}[/green]",
                title="Success",
                border_style="green",
            )
        )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to update entity: {exc}")
        raise typer.Exit(code=1)


async def _run_delete_entity(entity_id: str) -> None:
    """Delete an entity via agent layer."""
    try:
        agent = get_resolver()

        params = {"entity_id": entity_id}
        raw_result = await agent.call_tool("neo4j_delete_entity", params)
        result = parse_tool_result(raw_result)

        if not result or result.get("deleted_count", 0) == 0:
            console.print(f"[red]Error:[/red] Entity '{entity_id}' not found.")
            raise typer.Exit(code=1)

        console.print(
            Panel(
                f"[bold]Entity Deleted[/bold]\nID: [cyan]{entity_id}[/cyan]",
                title="Success",
                border_style="green",
            )
        )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to delete entity: {exc}")
        raise typer.Exit(code=1)


# =============================================================================
# ENTITY TEMPLATE COMMANDS
# =============================================================================


async def _run_create_template(
    universe_id: str,
    name: str,
    entity_type: str,
    description: str,
    detail_level: str,
    parent: str | None,
) -> None:
    """Create a new entity template."""
    try:
        agent = get_resolver()

        params = {
            "params": {
                "universe_id": universe_id,
                "name": name,
                "entity_type": entity_type.upper(),
                "description": description,
                "default_detail_level": detail_level,
            }
        }
        if parent:
            params["params"]["parent_template_id"] = parent

        raw_result = await agent.call_tool("mongodb_create_entity_template", params)
        result = parse_tool_result(raw_result)

        console.print(
            Panel(
                f"[bold]Template Created[/bold]\n"
                f"ID:   [cyan]{result.get('template_id', 'N/A')}[/cyan]\n"
                f"Type: [green]{entity_type.upper()}[/green]\n"
                f"Name: [blue]{name}[/blue]\n"
                f"Detail Level: [magenta]{detail_level}[/magenta]",
                title="Success",
                border_style="green",
            )
        )

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to create template: {exc}")
        raise typer.Exit(code=1)


async def _run_show_template(template_id: str) -> None:
    """Show details of a specific entity template."""
    try:
        agent = get_resolver()

        params = {"template_id": template_id}
        raw_result = await agent.call_tool("mongodb_get_entity_template", params)
        result = parse_tool_result(raw_result)

        if not result:
            console.print(f"[red]Error:[/red] Template '{template_id}' not found.")
            raise typer.Exit(code=1)

        # Format variable properties
        var_props = result.get("variable_properties", [])
        var_lines = []
        for vp in var_props:
            gen_type = vp.get("generation_type", "fixed")
            path = vp.get("property_path", "?")
            var_lines.append(f"  {path} ({gen_type})")

        # Format naming pattern
        naming = result.get("naming_pattern", {})
        naming_str = naming.get("pattern", "LLM-generated") if isinstance(naming, dict) else "LLM-generated"

        console.print(
            Panel(
                f"[bold]ID:[/bold] [cyan]{result.get('template_id', 'N/A')}[/cyan]\n"
                f"[bold]Type:[/bold] [green]{result.get('entity_type', 'N/A')}[/green]\n"
                f"[bold]Name:[/bold] [blue]{result.get('name', 'N/A')}[/blue]\n"
                f"[bold]Description:[/bold] [dim]{result.get('description', 'No description')}[/dim]\n"
                f"[bold]Detail Level:[/bold] [magenta]{result.get('default_detail_level', 'stub')}[/magenta]\n"
                f"[bold]Usage Count:[/bold] {result.get('usage_count', 0)}\n"
                f"[bold]Naming:[/bold] {naming_str}\n"
                f"[bold]Variable Properties:[/bold]\n"
                + ("\n".join(var_lines) if var_lines else "  (none)")
                + f"\n[bold]Parent:[/bold] {result.get('parent_template_id', 'None')}",
                title="Template Details",
                border_style="blue",
            )
        )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to show template: {exc}")
        raise typer.Exit(code=1)


async def _run_delete_template(template_id: str) -> None:
    """Delete an entity template."""
    try:
        agent = get_resolver()

        params = {"template_id": template_id}
        raw_result = await agent.call_tool("mongodb_delete_entity_template", params)
        result = parse_tool_result(raw_result)

        if not result:
            console.print(f"[red]Error:[/red] Template '{template_id}' not found.")
            raise typer.Exit(code=1)

        console.print(
            Panel(
                f"[bold]Template Deleted[/bold]\nID: [cyan]{template_id}[/cyan]",
                title="Success",
                border_style="green",
            )
        )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to delete template: {exc}")
        raise typer.Exit(code=1)


# =============================================================================
# RANDOM TABLE COMMANDS (create, show)
# =============================================================================


async def _run_create_table(
    universe_id: str | None,
    name: str,
    table_type: str,
    dice_formula: str,
    entries: str,
) -> None:
    """Create a new random table."""
    try:
        agent = get_resolver()

        # Parse comma-separated entries into RandomTableEntry items
        entry_texts = [e.strip() for e in entries.split(",") if e.strip()]
        if not entry_texts:
            console.print("[red]Error:[/red] At least one entry is required.")
            raise typer.Exit(code=1)

        # Assign roll ranges based on dice formula
        table_entries = []
        for i, text in enumerate(entry_texts):
            table_entries.append(
                {
                    "min_roll": i + 1,
                    "max_roll": i + 1,
                    "value": text,
                }
            )

        params = {
            "params": {
                "name": name,
                "table_type": table_type,
                "dice_formula": dice_formula,
                "entries": table_entries,
            }
        }
        if universe_id:
            params["params"]["universe_id"] = universe_id

        raw_result = await agent.call_tool("mongodb_create_random_table", params)
        result = parse_tool_result(raw_result)

        console.print(
            Panel(
                f"[bold]Table Created[/bold]\n"
                f"ID:   [cyan]{result.get('table_id', 'N/A')}[/cyan]\n"
                f"Name: [blue]{name}[/blue]\n"
                f"Type: [green]{table_type}[/green]\n"
                f"Dice: [magenta]{dice_formula}[/magenta]\n"
                f"Entries: {len(entry_texts)}",
                title="Success",
                border_style="green",
            )
        )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to create table: {exc}")
        raise typer.Exit(code=1)


async def _run_show_table(table_id: str) -> None:
    """Show details of a specific random table."""
    try:
        agent = get_resolver()

        params = {"table_id": table_id}
        raw_result = await agent.call_tool("mongodb_get_random_table", params)
        result = parse_tool_result(raw_result)

        if not result:
            console.print(f"[red]Error:[/red] Table '{table_id}' not found.")
            raise typer.Exit(code=1)

        # Format entries as a table
        entries = result.get("entries", [])
        entry_table = Table(title="Table Entries")
        entry_table.add_column("Roll", style="cyan", width=8)
        entry_table.add_column("Value", style="green")

        for entry in entries:
            min_r = entry.get("min_roll", "?")
            max_r = entry.get("max_roll", "?")
            roll_str = f"{min_r}-{max_r}" if min_r != max_r else str(min_r)
            entry_table.add_row(roll_str, entry.get("value", ""))

        console.print(
            Panel(
                f"[bold]ID:[/bold] [cyan]{result.get('table_id', 'N/A')}[/cyan]\n"
                f"[bold]Name:[/bold] [blue]{result.get('name', 'N/A')}[/blue]\n"
                f"[bold]Type:[/bold] [green]{result.get('table_type', 'N/A')}[/green]\n"
                f"[bold]Dice:[/bold] [magenta]{result.get('dice_formula', 'N/A')}[/magenta]\n"
                f"[bold]Weighted:[/bold] {result.get('weighted', False)}\n"
                f"[bold]Description:[/bold] [dim]{result.get('description', 'No description')}[/dim]",
                title="Random Table Details",
                border_style="blue",
            )
        )
        console.print(entry_table)

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to show table: {exc}")
        raise typer.Exit(code=1)
