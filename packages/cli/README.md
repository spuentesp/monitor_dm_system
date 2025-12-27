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
| `monitor play` | `commands/play.py` | Start/continue story sessions |
| `monitor ingest` | `commands/ingest.py` | Upload and process documents |
| `monitor query` | `commands/query.py` | Query canonical facts |
| `monitor manage` | `commands/manage.py` | Entity and universe management |

---

## Folder Structure

```
src/monitor_cli/
├── __init__.py           # Package root
├── main.py               # Typer app entry point
│
├── commands/             # CLI commands
│   ├── play.py           # `monitor play`
│   ├── ingest.py         # `monitor ingest`
│   ├── query.py          # `monitor query`
│   └── manage.py         # `monitor manage`
│
├── repl/                 # Interactive REPL
│   ├── session.py        # REPL session management
│   └── handlers.py       # Input handlers
│
└── ui/                   # Terminal UI components
    ├── output.py         # Rich output formatting
    ├── prompts.py        # User prompts
    └── tables.py         # Table displays
```

---

## Dependency Rules

```python
# ✅ ALLOWED imports in this package:
from monitor_agents import Orchestrator
from monitor_agents import ContextAssembly
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

# ✅ CORRECT - CLI using agents
from monitor_agents import ContextAssembly
context = ContextAssembly()
entities = await context.get_entities(...)  # Proper flow
```

---

## Key Files to Implement

1. `main.py` - Typer app with command registration
2. `commands/play.py` - Interactive story sessions
3. `repl/session.py` - REPL loop management
4. `ui/output.py` - Rich formatting utilities

---

## Running

```bash
# Install for development
pip install -e ".[dev]"

# Run CLI
monitor --help
monitor play --story "My Campaign"
monitor query "What is Gandalf's status?"

# Run tests
pytest
```

---

## Example Usage

```bash
# Start a new story
$ monitor play
? Select mode: Start new story
? Select universe: Middle-earth
? Story title: The Quest Begins
Starting story...

# Query canon
$ monitor query "Who is allied with Frodo?"
Allies of Frodo Baggins:
  - Samwise Gamgee (companion)
  - Gandalf the Grey (mentor)
  - Aragorn (protector)

# Ingest a document
$ monitor ingest ./dnd_phb.pdf --universe "Forgotten Realms"
Processing document...
Extracted 1,247 snippets
Created 89 entity proposals
```
