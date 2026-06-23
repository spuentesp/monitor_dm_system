# MONITOR CLI Layer (Layer 3 of 3)

> **This is the TOP layer. It depends ONLY on agents (Layer 2).**

---

## What This Package Does

- Provides command-line interface for users
- Implements interactive REPL for gameplay
- Formats output for terminal display
- Handles user input

---

## CLI Commands

| Command | File | Description |
|---------|------|-------------|
| `monitor state` | `commands/state.py` | View and modify working state during scenes |
| `monitor rules` | `commands/rules.py` | Import and list game system definitions |
| `monitor mechanics` | `commands/mechanics.py` | Resolve checks and other mechanical outcomes |
| `monitor ingest` | `commands/ingest.py` | Ingest files/URIs and apply knowledge packs |
| `monitor playtest` | `commands/playtest.py` | Run live autonomous-GM smoke and benchmark flows |
| `monitor version` | `main.py` | Print CLI version |

> The broader `play` / `manage` / `query` workflows are specified in `docs/USE_CASES.md`; `monitor_cli.main` is the source of truth for what is currently registered. Today, the primary interactive play surface is the web UI, while `monitor playtest` exercises the live backend from the CLI.

---

## Folder Structure

```text
src/monitor_cli/
├── __init__.py           # Package root
├── main.py               # Typer app entry point
│
├── commands/             # Current CLI command groups
│   ├── ingest.py         # `monitor ingest`
│   ├── mechanics.py      # `monitor mechanics`
│   ├── playtest.py       # `monitor playtest`
│   ├── rules.py          # `monitor rules`
│   └── state.py          # `monitor state`
│
├── repl/                 # Interactive REPL (currently stubbed)
│   └── __init__.py
│
└── ui/                   # Terminal UI components (currently stubbed)
    └── __init__.py
```

---

## Dependency Rules

```python
# ✅ ALLOWED imports in this package:
from monitor_agents import ContextAssembly
from monitor_agents.loops.scene_loop import SceneLoop
from typer import Typer
from rich.console import Console

# ❌ FORBIDDEN imports in this package:
from monitor_data import ...         # NEVER import Layer 1 directly!
from monitor_data.db import ...      # NEVER skip Layer 2!
from monitor_data.tools import ...   # NEVER skip Layer 2!
```

---

## Why No Direct Data-Layer Access?

The CLI should NEVER bypass agents to access databases because:

1. **Authority enforcement** happens in data-layer via agent context
2. **Business logic** lives in agents (canonization, rules, etc.)
3. **Testability** - clear boundaries enable mocking
4. **Separation of concerns** - CLI is just UI

```python
# ❌ WRONG - CLI accessing data-layer directly
from monitor_data.db import Neo4jClient
client = Neo4jClient()
entities = client.query_entities(...)  # Bypasses everything!

# ✅ CORRECT - CLI using agents / loops
from monitor_agents import ContextAssembly
context = ContextAssembly()
entities = await context.assemble(...)  # Proper flow
```

---

## Key Entry Points

1. `main.py` - Typer app with command registration
2. `commands/state.py` - Scene working-state operations
3. `commands/rules.py` - Game-system import and listing
4. `commands/mechanics.py` - Resolution helpers
5. `commands/ingest.py` - File/URI ingestion and pack application
6. `commands/playtest.py` - Live autonomous-GM smoke and benchmark runs

---

## Running

```bash
# Install for development
pip install -e ".[dev]"

# Inspect the CLI
monitor --help
monitor state list
monitor rules list
monitor mechanics check <entity-id> Strength --dc 15
monitor ingest file ./lore.pdf --universe <uuid>
monitor playtest live --api-url http://localhost:8000/api

# Run tests
pytest
```

---

## Example Usage

```bash
# List active working states
$ monitor state list --limit 10

# List available game systems
$ monitor rules list

# Resolve a check for a character
$ monitor mechanics check <entity-id> Stealth --dc 15

# Ingest a setting document
$ monitor ingest file ./middle-earth.pdf --universe <uuid> --title "Middle-earth Primer"
```
