---
description: Implement CLI command (Layer 3)
---

# Implement CLI Command

Step-by-step guide for implementing features in Layer 3 (cli).

## What Goes in CLI Layer

- User-facing CLI commands
- Interactive REPL logic
- Terminal UI formatting
- User input handling
- Output formatting with Rich library

## What Does NOT Go Here

- Agent logic (use agents package)
- Database access (agents handle that via data-layer)
- LLM calls (agents handle that)

## CLI Command Categories

| Command | Use Cases | Purpose |
|---------|-----------|---------|
| `monitor play` | P-1 to P-12 | Solo play mode - start/continue stories |
| `monitor manage` | M-1 to M-30 | World design - CRUD for entities |
| `monitor query` | Q-1 to Q-9 | Canon exploration - search and browse |
| `monitor ingest` | I-1 to I-6 | Knowledge import - documents, PDFs |
| `monitor copilot` | CF-1 to CF-5 | GM assistant mode |
| `monitor story` | ST-1 to ST-5 | Planning and meta-narrative |
| `monitor rules` | RS-1 to RS-4 | Game system definition |

## Steps

### 1. Identify Command Category

Based on your use case ID, determine which command file to edit:

- **P-*** → `packages/cli/src/monitor_cli/commands/play.py`
- **M-*** → `packages/cli/src/monitor_cli/commands/manage.py`
- **Q-*** → `packages/cli/src/monitor_cli/commands/query.py`
- **I-*** → `packages/cli/src/monitor_cli/commands/ingest.py`
- **CF-*** → `packages/cli/src/monitor_cli/commands/copilot.py`
- **ST-*** → `packages/cli/src/monitor_cli/commands/story.py`
- **RS-*** → `packages/cli/src/monitor_cli/commands/rules.py`

### 2. Review Use Case Documentation

Read `docs/USE_CASES.md` for your specific use case to understand:
- Expected inputs
- Expected outputs
- Error conditions
- User interactions

### 3. Implement Command Function

Location: `packages/cli/src/monitor_cli/commands/<category>.py`

Example:
```python
# packages/cli/src/monitor_cli/commands/query.py
import typer
from rich.console import Console
from rich.table import Table
from monitor_agents import ContextAssembly

console = Console()
app = typer.Typer()

@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, help="Max results")
):
    """
    Search canon for entities, facts, and events.
    
    Use case: Q-1 Semantic Search
    """
    # 1. Call agent (not data-layer directly!)
    context_agent = ContextAssembly()
    results = context_agent.semantic_search(query, limit=limit)
    
    # 2. Format output with Rich
    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return
    
    table = Table(title=f"Search Results: '{query}'")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    
    for result in results:
        table.add_row(
            result.type,
            result.name,
            result.description[:50] + "..."
        )
    
    console.print(table)
    console.print(f"\n[dim]Found {len(results)} results[/dim]")
```

### 4. Add Rich Terminal Formatting

Use Rich library for beautiful output:

**Tables**:
```python
from rich.table import Table

table = Table(title="Entities")
table.add_column("ID", style="cyan")
table.add_column("Name", style="green")
table.add_row("ent-1", "Gandalf")
console.print(table)
```

**Panels**:
```python
from rich.panel import Panel

console.print(Panel("Important message", title="Notice"))
```

**Progress**:
```python
from rich.progress import track

for item in track(items, description="Processing..."):
    process(item)
```

**Colors**:
```python
console.print("[bold green]Success![/bold green]")
console.print("[red]Error occurred[/red]")
console.print("[yellow]Warning[/yellow]")
```

### 5. Handle Errors Gracefully

```python
from typing import Optional
import sys

@app.command()
def create_entity(name: str):
    """Create a new entity."""
    try:
        agent = EntityManager()
        result = agent.create_entity(name)
        console.print(f"[green]✓[/green] Created entity: {result.name}")
    except ValueError as e:
        console.print(f"[red]✗ Validation error:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]✗ Unexpected error:[/red] {e}")
        sys.exit(1)
```

### 6. Register Command in Main App

Location: `packages/cli/src/monitor_cli/main.py`

```python
# packages/cli/src/monitor_cli/main.py
from typer import Typer
from .commands import play, manage, query  # Import your command module

app = Typer(name="monitor")

# Register command groups
app.add_typer(play.app, name="play", help="Solo play mode")
app.add_typer(manage.app, name="manage", help="World management")
app.add_typer(query.app, name="query", help="Search and explore canon")

if __name__ == "__main__":
    app()
```

### 7. Write Tests

Location: `packages/cli/tests/test_commands/`

Example:
```python
# packages/cli/tests/test_commands/test_query.py
import pytest
from typer.testing import CliRunner
from monitor_cli.main import app

runner = CliRunner()

@pytest.mark.unit
def test_search_command_success(mock_agent):
    """Test successful search command."""
    # Setup mock
    mock_agent.semantic_search.return_value = [
        {"type": "entity", "name": "Gandalf", "description": "Wizard"}
    ]
    
    # Execute
    result = runner.invoke(app, ["query", "search", "Gandalf"])
    
    # Verify
    assert result.exit_code == 0
    assert "Gandalf" in result.stdout
    assert "Wizard" in result.stdout

@pytest.mark.unit
def test_search_command_no_results(mock_agent):
    """Test search with no results."""
    mock_agent.semantic_search.return_value = []
    
    result = runner.invoke(app, ["query", "search", "NonexistentEntity"])
    
    assert result.exit_code == 0
    assert "No results found" in result.stdout
```

### 8. Update Help Text

Ensure commands have clear help text:

```python
@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (semantic)"),
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum results to return"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type: entity, fact, event")
):
    """
    Search the canon using semantic similarity.
    
    Examples:
        monitor query search "Gandalf's status"
        monitor query search "magic items" --limit 20
        monitor query search "battles" --type event
    """
    pass
```

## CLI Design Principles

### ✅ DO

- Call agents, not data-layer directly
- Use Rich library for output formatting
- Provide clear help text and examples
- Handle errors gracefully
- Show progress for long operations
- Confirm destructive actions

### ❌ DON'T

- Import from data-layer (skip-layer violation!)
- Make direct database calls
- Use plain `print()` (use Rich console)
- Exit without error message
- Show raw exception traces to users

## Common Patterns

**Interactive prompts**:
```python
import typer

def delete_entity(entity_id: str):
    """Delete an entity (requires confirmation)."""
    entity = agent.get_entity(entity_id)
    
    confirm = typer.confirm(f"Delete '{entity.name}'? This cannot be undone.")
    if not confirm:
        console.print("[yellow]Cancelled[/yellow]")
        return
    
    agent.delete_entity(entity_id)
    console.print(f"[green]✓[/green] Deleted {entity.name}")
```

**Pagination**:
```python
def list_entities(page: int = 1, per_page: int = 20):
    """List entities with pagination."""
    offset = (page - 1) * per_page
    results = agent.list_entities(offset=offset, limit=per_page)
    
    # Display results...
    console.print(f"\n[dim]Page {page} | Showing {len(results)} of {results.total}[/dim]")
```

**REPL mode**:
```python
# For interactive play mode
from prompt_toolkit import PromptSession

session = PromptSession()
while True:
    user_input = session.prompt("You: ")
    if user_input.lower() in ["quit", "exit"]:
        break
    
    response = narrator.generate_response(user_input)
    console.print(f"\n[bold cyan]GM:[/bold cyan] {response}\n")
```

## Before Committing

Run checks:
```bash
# Layer dependency check
python scripts/check_layer_dependencies.py

# Tests
cd packages/cli && pytest

# Linting
ruff check packages/cli
black --check packages/cli
mypy packages/cli
```

## Next Steps

After CLI implementation:
1. Test manually: `monitor <your-command>`
2. Run full test suite: `/run-tests`
3. Pre-commit checks: `/pre-commit-checks`
4. Update README with new command examples
