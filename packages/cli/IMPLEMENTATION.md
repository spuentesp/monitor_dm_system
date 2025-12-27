# CLI Layer Implementation

> Machine-optimized task list for implementing Layer 3.

---

## Prerequisites

```
REQUIRES: Layer 2 (agents) complete
READS: docs/USE_CASES.md
OUTPUTS: CLI application with commands + REPL
```

---

## Phase 1: Project Setup

### T1.1: Initialize Package

```bash
cd packages/cli
uv init --name monitor-cli
```

**Files to create:**
```
src/monitor_cli/
├── __init__.py
├── main.py
├── config.py
├── commands/
│   ├── __init__.py
│   ├── play.py           # P- use cases (Solo Play mode)
│   ├── manage.py         # M- use cases (World Design mode)
│   ├── query.py          # Q- use cases
│   ├── ingest.py         # I- use cases
│   ├── copilot.py        # CF- use cases (GM Assistant mode)
│   ├── story.py          # ST- use cases (Planning)
│   └── rules.py          # RS- use cases (Game Systems)
├── repl/
│   ├── __init__.py
│   ├── session.py
│   └── handlers.py
└── ui/
    ├── __init__.py
    ├── output.py
    ├── prompts.py
    └── tables.py
```

### T1.2: Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "monitor-agents",  # Layer 2
    "typer>=0.9",
    "rich>=13.7",
    "prompt-toolkit>=3.0",
]

[project.scripts]
monitor = "monitor_cli.main:main"
```

---

## Phase 2: Main Entry Point

### T2.1: Typer App

**File:** `src/monitor_cli/main.py`

```python
import typer
from rich.console import Console

app = typer.Typer(
    name="monitor",
    help="MONITOR - Auto-GM for tabletop RPGs",
    no_args_is_help=True,
)

console = Console()

@app.callback()
def main_callback():
    """MONITOR CLI."""
    pass

@app.command()
def version():
    """Show version."""
    from monitor_cli import __version__
    console.print(f"MONITOR v{__version__}")

def main():
    app()
```

### T2.2: Command Registration

```python
# main.py
from monitor_cli.commands import play, manage, query, ingest, copilot, story, rules

# 7 command groups
app.add_typer(play.app, name="play", help="Start or continue a story (Solo Play)")
app.add_typer(manage.app, name="manage", help="Manage universes, entities, facts (World Design)")
app.add_typer(query.app, name="query", help="Search and explore canon")
app.add_typer(ingest.app, name="ingest", help="Upload and process documents")
app.add_typer(copilot.app, name="copilot", help="GM assistant features (Assisted GM)")
app.add_typer(story.app, name="story", help="Arc planning, factions, what-if scenarios")
app.add_typer(rules.app, name="rules", help="Game system definition and management")
```

---

## Phase 3: Play Commands

### T3.1: Play Command Group

**File:** `src/monitor_cli/commands/play.py`

**Use Cases:** SYS-2, P-1, P-12, P-2, P-3, P-8

```python
app = typer.Typer(help="Start or continue a story")
```

### T3.2: Commands

| Command | Use Case | Description |
|---------|----------|-------------|
| `monitor play` | SYS-2 | Interactive main menu |
| `monitor play new` | P-1 | Start new story |
| `monitor play continue [STORY_ID]` | P-12 | Continue story |
| `monitor play quick` | P-1 | Quick one-shot |

### T3.3: Implementation

```python
@app.callback(invoke_without_command=True)
def play_menu(ctx: typer.Context):
    """Interactive play menu."""
    if ctx.invoked_subcommand is None:
        # SYS-2: Main menu navigation
        from monitor_cli.repl import start_play_menu
        start_play_menu()

@app.command()
def new(
    universe: str = typer.Option(None, help="Universe ID or name"),
    title: str = typer.Option(None, help="Story title"),
):
    """Start a new story (P-1)."""
    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()

    # 1. Select/create universe (M-4 if needed)
    if not universe:
        universe = prompt_universe_selection()

    # 2. Get story params
    if not title:
        title = prompt("Story title")

    story_type = prompt_choice("Type", ["campaign", "arc", "one-shot"])
    theme = prompt("Theme (optional)", default="")
    premise = prompt("Premise (optional)", default="")

    # 3. Create story
    story_id = orchestrator.start_new_story(
        universe_id=universe,
        title=title,
        story_type=story_type,
        theme=theme,
        premise=premise,
    )

    # 4. Enter REPL
    from monitor_cli.repl import REPLSession
    session = REPLSession(orchestrator, story_id)
    session.run()

@app.command()
def continue_(
    story_id: str = typer.Argument(None, help="Story ID"),
):
    """Continue an existing story (P-12)."""
    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()

    # 1. Select story if not provided
    if not story_id:
        story_id = prompt_story_selection(status="active")

    # 2. Load and display recap
    orchestrator.continue_story(story_id)

    # 3. Enter REPL
    from monitor_cli.repl import REPLSession
    session = REPLSession(orchestrator, story_id)
    session.run()
```

---

## Phase 4: Manage Commands

### T4.1: Manage Command Group

**File:** `src/monitor_cli/commands/manage.py`

**Use Cases:** M-1 to M-29

```python
app = typer.Typer(help="Manage universes, stories, characters")
```

### T4.2: Universe Commands

| Command | Use Case | Description |
|---------|----------|-------------|
| `monitor manage universes` | M-5 | List universes |
| `monitor manage universes create` | M-4 | Create universe |
| `monitor manage universes show ID` | M-6 | View universe |
| `monitor manage universes edit ID` | M-7 | Edit universe |
| `monitor manage universes delete ID` | M-8 | Delete universe |

```python
universes_app = typer.Typer(help="Manage universes")
app.add_typer(universes_app, name="universes")

@universes_app.callback(invoke_without_command=True)
def list_universes(ctx: typer.Context):
    """List all universes (M-5)."""
    if ctx.invoked_subcommand is None:
        from monitor_agents import Orchestrator
        orchestrator = Orchestrator()
        universes = orchestrator.call_tool("neo4j_list_universes", {})
        display_universe_table(universes)

@universes_app.command()
def create():
    """Create a new universe (M-4)."""
    name = prompt("Universe name")
    genre = prompt_choice("Genre", ["fantasy", "sci-fi", "horror", "modern", "other"])
    tone = prompt_choice("Tone", ["serious", "humorous", "dark", "epic"])
    tech_level = prompt_choice("Tech level", ["medieval", "renaissance", "modern", "futuristic"])
    description = prompt("Description (optional)", default="")

    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()
    result = orchestrator.call_tool("neo4j_create_universe", {
        "name": name,
        "genre": genre,
        "tone": tone,
        "tech_level": tech_level,
        "description": description,
    })
    console.print(f"Created universe: {result['universe_id']}")

@universes_app.command()
def show(universe_id: str):
    """View universe details (M-6)."""
    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()
    universe = orchestrator.call_tool("neo4j_get_universe", {"id": universe_id})
    display_universe_details(universe)
```

### T4.3: Story Commands

| Command | Use Case | Description |
|---------|----------|-------------|
| `monitor manage stories` | M-9 | List stories |
| `monitor manage stories show ID` | M-10 | View story |
| `monitor manage stories edit ID` | M-11 | Edit story |
| `monitor manage stories archive ID` | M-11 | Archive story |
| `monitor manage stories delete ID` | M-11 | Delete story |

### T4.4: Character Commands

| Command | Use Case | Description |
|---------|----------|-------------|
| `monitor manage characters` | Q-3 | List characters |
| `monitor manage characters create-pc` | M-13 | Create PC |
| `monitor manage characters create-npc` | M-13 | Create NPC |
| `monitor manage characters show ID` | M-16 | View character |
| `monitor manage characters edit ID` | M-19 | Edit character |

```python
characters_app = typer.Typer(help="Manage characters")
app.add_typer(characters_app, name="characters")

@characters_app.callback(invoke_without_command=True)
def list_characters(
    ctx: typer.Context,
    universe: str = typer.Option(None, help="Filter by universe"),
    role: str = typer.Option(None, help="Filter by role (PC/NPC)"),
):
    """List characters (Q-3)."""
    if ctx.invoked_subcommand is None:
        from monitor_agents import Orchestrator
        orchestrator = Orchestrator()
        characters = orchestrator.call_tool("neo4j_list_entities", {
            "entity_type": "character",
            "universe_id": universe,
        })
        display_character_table(characters)

@characters_app.command()
def create_pc():
    """Create player character (M-13)."""
    # 1. Select universe
    universe_id = prompt_universe_selection()

    # 2. Basic info
    name = prompt("Character name")
    description = prompt("Description")

    # 3. Select archetype (optional)
    archetypes = get_archetypes(universe_id, "character")
    archetype_id = prompt_optional_choice("Archetype", archetypes)

    # 4. Character sheet
    console.print("Character Sheet Setup:")
    stats = prompt_stats()
    resources = prompt_resources()

    # 5. Create
    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()

    entity_id = orchestrator.call_tool("neo4j_create_entity_concreta", {
        "universe_id": universe_id,
        "name": name,
        "entity_type": "character",
        "description": description,
        "properties": {"role": "PC"},
        "derives_from": archetype_id,
    })

    orchestrator.call_tool("mongodb_create_character_sheet", {
        "entity_id": entity_id,
        "stats": stats,
        "resources": resources,
    })

    console.print(f"Created PC: {name} ({entity_id})")
```

---

## Phase 5: Ingest Commands

### T5.1: Ingest Command Group

**File:** `src/monitor_cli/commands/ingest.py`

**Use Cases:** I-1 to I-5

```python
app = typer.Typer(help="Upload and process documents")
```

### T5.2: Commands

| Command | Use Case | Description |
|---------|----------|-------------|
| `monitor ingest upload FILE` | I-1 | Upload document |
| `monitor ingest review` | I-4 | Review proposals |
| `monitor ingest sources` | I-5 | List sources |
| `monitor ingest reprocess ID` | I-2, I-3 | Reprocess document |

```python
@app.command()
def upload(
    file: Path = typer.Argument(..., help="File to upload"),
    universe: str = typer.Option(None, help="Target universe"),
    source_type: str = typer.Option("lore", help="Source type"),
):
    """Upload and process document (I-1)."""
    # 1. Validate file
    if not file.exists():
        raise typer.BadParameter(f"File not found: {file}")

    # 2. Select universe
    if not universe:
        universe = prompt_universe_selection()

    # 3. Upload
    from monitor_agents import Indexer
    indexer = Indexer()

    with Progress() as progress:
        task = progress.add_task("Uploading...", total=100)

        # Upload to MinIO
        doc_id = indexer.call_tool("minio_upload", {
            "bucket": "documents",
            "file_path": str(file),
        })
        progress.update(task, advance=30)

        # Create source + document records
        source_id = indexer.call_tool("neo4j_create_source", {
            "universe_id": universe,
            "doc_id": doc_id,
            "title": file.stem,
            "source_type": source_type,
        })
        progress.update(task, advance=20)

        # Process document
        indexer.process_document(doc_id)
        progress.update(task, advance=50)

    console.print(f"Uploaded: {file.name}")
    console.print(f"Source ID: {source_id}")
    console.print("Proposals created - run 'monitor ingest review' to review")

@app.command()
def review(
    source: str = typer.Option(None, help="Filter by source ID"),
):
    """Review pending proposals (I-3)."""
    from monitor_agents import CanonKeeper
    canonkeeper = CanonKeeper()

    proposals = canonkeeper.call_tool("mongodb_list_pending_proposals", {
        "source_id": source,
    })

    for proposal in proposals:
        display_proposal(proposal)
        action = prompt_choice("Action", ["accept", "edit", "reject", "skip"])

        if action == "accept":
            canonkeeper.call_tool("mongodb_update_proposal", {
                "proposal_id": proposal["proposal_id"],
                "status": "accepted",
            })
            canonkeeper.write_proposal(proposal)

        elif action == "edit":
            edited = prompt_edit_proposal(proposal)
            canonkeeper.call_tool("mongodb_update_proposal", {
                "proposal_id": proposal["proposal_id"],
                "content": edited,
                "status": "accepted",
            })
            canonkeeper.write_proposal(edited)

        elif action == "reject":
            rationale = prompt("Reason for rejection")
            canonkeeper.call_tool("mongodb_update_proposal", {
                "proposal_id": proposal["proposal_id"],
                "status": "rejected",
                "rationale": rationale,
            })
```

---

## Phase 6: Query Commands

### T6.1: Query Command Group

**File:** `src/monitor_cli/commands/query.py`

**Use Cases:** Q-1 to Q-8

```python
app = typer.Typer(help="Query canonical facts")
```

### T6.2: Commands

| Command | Use Case | Description |
|---------|----------|-------------|
| `monitor query search QUERY` | Q-1 | Semantic search |
| `monitor query ask ENTITY` | Q-2 | Ask about entity |
| `monitor query entities` | Q-3 | Browse entities |
| `monitor query facts` | Q-4 | Explore facts |
| `monitor query timeline` | Q-5 | View timeline |
| `monitor query graph ENTITY` | Q-6 | Relationship graph |
| `monitor query ask-free TEXT` | Q-7 | Natural language question |
| `monitor query compare` | Q-8 | Compare entities |

```python
@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    universe: str = typer.Option(None, help="Filter by universe"),
    limit: int = typer.Option(10, help="Max results"),
):
    """Semantic search across canon (Q-1)."""
    from monitor_agents import ContextAssembly
    context = ContextAssembly()

    results = context.semantic_search(query, universe_id=universe, limit=limit)
    display_search_results(results)

@app.command()
def entities(
    universe: str = typer.Option(None, help="Filter by universe"),
    type_: str = typer.Option(None, "--type", help="Filter by type"),
):
    """Browse entities (Q-3)."""
    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()

    entities = orchestrator.call_tool("neo4j_list_entities", {
        "universe_id": universe,
        "entity_type": type_,
    })
    display_entity_table(entities)

@app.command()
def timeline(
    story: str = typer.Option(None, help="Story ID"),
    universe: str = typer.Option(None, help="Universe ID"),
):
    """View event timeline (Q-5)."""
    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()

    events = orchestrator.call_tool("neo4j_list_events", {
        "story_id": story,
        "universe_id": universe,
    })
    display_timeline(events)

@app.command()
def facts(
    entity: str = typer.Option(None, help="Filter by entity"),
    universe: str = typer.Option(None, help="Filter by universe"),
):
    """Explore facts (Q-4)."""
    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()

    facts = orchestrator.call_tool("neo4j_list_facts", {
        "entity_id": entity,
        "universe_id": universe,
    })
    display_facts_table(facts)

@app.command()
def graph(
    entity_id: str = typer.Argument(..., help="Entity ID"),
    depth: int = typer.Option(2, help="Relationship depth"),
):
    """View relationship graph (Q-6)."""
    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()

    relationships = orchestrator.call_tool("neo4j_get_relationships", {
        "entity_id": entity_id,
        "depth": depth,
    })
    display_relationship_graph(relationships)
```

---

## Phase 7: Copilot Commands

### T7.1: Copilot Command Group

**File:** `src/monitor_cli/commands/copilot.py`

**Use Cases:** CF-1 to CF-5

```python
app = typer.Typer(help="GM assistant features (Assisted GM mode)")
```

### T7.2: Commands

| Command | Use Case | Description |
|---------|----------|-------------|
| `monitor copilot record` | CF-1 | Start recording a live session |
| `monitor copilot recap` | CF-2 | Generate session recap |
| `monitor copilot threads` | CF-3 | Detect unresolved threads |
| `monitor copilot suggest` | CF-4 | Suggest plot hooks |
| `monitor copilot validate` | CF-5 | Detect contradictions |

### T7.3: Implementation

```python
@app.command()
def record(
    story_id: str = typer.Option(None, help="Story ID"),
):
    """Start recording a live session (CF-1)."""
    from monitor_agents import Orchestrator

    orchestrator = Orchestrator()

    if not story_id:
        story_id = prompt_story_selection()

    orchestrator.start_recording_session(story_id)

    console.print("Recording started. Type events as they happen.")
    console.print("Commands: /pause, /note, /end")

    # Enter recording REPL
    from monitor_cli.repl import RecordingSession
    session = RecordingSession(orchestrator, story_id)
    session.run()

@app.command()
def recap(
    scene_id: str = typer.Option(None, help="Scene ID"),
    story_id: str = typer.Option(None, help="Story ID"),
    last: bool = typer.Option(False, help="Recap last session"),
):
    """Generate session recap (CF-2)."""
    from monitor_agents import Narrator

    narrator = Narrator()

    if last and story_id:
        scene_id = narrator.call_tool("mongodb_get_latest_scene", {"story_id": story_id})

    recap = narrator.generate_recap(scene_id=scene_id, story_id=story_id)
    display_recap(recap)

@app.command()
def threads(
    story_id: str = typer.Argument(..., help="Story ID"),
    critical: bool = typer.Option(False, help="Show critical only"),
):
    """Detect unresolved plot threads (CF-3)."""
    from monitor_agents import CanonKeeper

    canonkeeper = CanonKeeper()
    threads = canonkeeper.analyze_threads(story_id)

    if critical:
        threads = [t for t in threads if t["priority"] == "high"]

    display_threads(threads)

@app.command()
def suggest(
    story_id: str = typer.Argument(..., help="Story ID"),
    type_: str = typer.Option(None, "--type", help="Hook type"),
    involving: str = typer.Option(None, help="Entity ID to involve"),
):
    """Suggest plot hooks (CF-4)."""
    from monitor_agents import Narrator

    narrator = Narrator()
    hooks = narrator.generate_hooks(
        story_id=story_id,
        hook_type=type_,
        involving_entity=involving,
    )

    display_hooks(hooks)

@app.command()
def validate(
    universe_id: str = typer.Option(None, help="Universe ID"),
    story_id: str = typer.Option(None, help="Story ID"),
    scene_id: str = typer.Option(None, help="Scene ID"),
):
    """Detect contradictions in canon (CF-5)."""
    from monitor_agents import CanonKeeper

    canonkeeper = CanonKeeper()
    conflicts = canonkeeper.validate_consistency(
        universe_id=universe_id,
        story_id=story_id,
        scene_id=scene_id,
    )

    if not conflicts:
        console.print("[green]No contradictions found![/green]")
        return

    for conflict in conflicts:
        display_conflict(conflict)
        action = prompt_choice("Action", ["resolve", "skip", "mark_mystery"])

        if action == "resolve":
            resolution = prompt_choice("Resolution", conflict["suggested_resolutions"])
            canonkeeper.apply_resolution(conflict, resolution)
        elif action == "mark_mystery":
            canonkeeper.mark_as_mystery(conflict)
```

---

## Phase 8: Story Commands

### T8.1: Story Command Group

**File:** `src/monitor_cli/commands/story.py`

**Use Cases:** ST-1 to ST-5

```python
app = typer.Typer(help="Arc planning, faction modeling, what-if scenarios")
```

### T8.2: Commands

| Command | Use Case | Description |
|---------|----------|-------------|
| `monitor story plan` | ST-1 | Plan story arc |
| `monitor story factions` | ST-2 | Model faction goals |
| `monitor story whatif` | ST-3 | Simulate what-if scenarios |
| `monitor story mystery` | ST-4 | Design mystery structure |
| `monitor story balance` | ST-5 | Check player agency balance |

### T8.3: Implementation

```python
@app.command()
def plan(
    story_id: str = typer.Argument(..., help="Story ID"),
    template: str = typer.Option(None, help="Arc template"),
):
    """Plan story arc (ST-1)."""
    from monitor_agents import Narrator

    narrator = Narrator()

    if template:
        arc = narrator.generate_arc_from_template(story_id, template)
    else:
        # Interactive arc planning
        arc_params = prompt_arc_params()
        arc = narrator.generate_arc_structure(story_id, arc_params)

    display_arc(arc)

    if confirm("Save this arc?"):
        narrator.save_arc(story_id, arc)
        console.print("[green]Arc saved![/green]")

@app.command()
def factions(
    story_id: str = typer.Argument(..., help="Story ID"),
    add: str = typer.Option(None, help="Add faction by ID"),
    simulate: bool = typer.Option(False, help="Simulate faction turn"),
):
    """Model faction goals (ST-2)."""
    from monitor_agents import Narrator

    narrator = Narrator()

    if add:
        narrator.add_faction_to_story(story_id, add)
        console.print(f"Added faction {add} to story")
        return

    if simulate:
        results = narrator.simulate_faction_turn(story_id)
        display_faction_simulation(results)
        return

    # Show faction dynamics
    dynamics = narrator.analyze_faction_dynamics(story_id)
    display_faction_dynamics(dynamics)

@app.command()
def whatif(
    universe_id: str = typer.Option(None, help="Universe ID"),
    story_id: str = typer.Option(None, help="Story ID"),
    change: str = typer.Argument(..., help="Hypothetical change"),
    adopt: str = typer.Option(None, help="Adopt simulation by ID"),
):
    """Simulate what-if scenarios (ST-3)."""
    from monitor_agents import Narrator, CanonKeeper

    if adopt:
        canonkeeper = CanonKeeper()
        canonkeeper.adopt_simulation(adopt)
        console.print("[green]Simulation adopted as canon![/green]")
        return

    narrator = Narrator()
    simulation = narrator.simulate_consequences(
        universe_id=universe_id,
        story_id=story_id,
        change=change,
    )

    display_simulation(simulation)
    console.print(f"\nSimulation ID: {simulation['id']}")
    console.print("Use --adopt to make this canon")

@app.command()
def mystery(
    story_id: str = typer.Argument(..., help="Story ID"),
    validate_flag: bool = typer.Option(False, "--validate", help="Validate solvability"),
    status: bool = typer.Option(False, help="Show discovery status"),
):
    """Design mystery structure (ST-4)."""
    from monitor_agents import Narrator

    narrator = Narrator()

    if status:
        mystery_status = narrator.get_mystery_status(story_id)
        display_mystery_status(mystery_status)
        return

    if validate_flag:
        validation = narrator.validate_mystery_solvability(story_id)
        display_mystery_validation(validation)
        return

    # Interactive mystery design
    mystery_params = prompt_mystery_params()
    mystery = narrator.design_mystery(story_id, mystery_params)
    display_mystery_structure(mystery)

    if confirm("Save this mystery structure?"):
        narrator.save_mystery(story_id, mystery)

@app.command()
def balance(
    story_id: str = typer.Argument(..., help="Story ID"),
    apply: str = typer.Option(None, help="Apply suggestion by ID"),
):
    """Check player agency balance (ST-5)."""
    from monitor_agents import Narrator

    narrator = Narrator()

    if apply:
        narrator.apply_balance_suggestion(story_id, apply)
        console.print("[green]Suggestion applied![/green]")
        return

    assessment = narrator.assess_agency(story_id)
    display_agency_assessment(assessment)
```

---

## Phase 9: Rules Commands

### T9.1: Rules Command Group

**File:** `src/monitor_cli/commands/rules.py`

**Use Cases:** RS-1 to RS-4

```python
app = typer.Typer(help="Game system definition and management")
```

### T9.2: Commands

| Command | Use Case | Description |
|---------|----------|-------------|
| `monitor rules create` | RS-1 | Define game system |
| `monitor rules import` | RS-2 | Import game system |
| `monitor rules template` | RS-3 | Define character template |
| `monitor rules override` | RS-4 | Manage house rules |
| `monitor rules list` | - | List game systems |
| `monitor rules view ID` | - | View game system |

### T9.3: Implementation

```python
@app.callback(invoke_without_command=True)
def list_systems(ctx: typer.Context):
    """List all game systems."""
    if ctx.invoked_subcommand is None:
        from monitor_agents import Orchestrator

        orchestrator = Orchestrator()
        systems = orchestrator.call_tool("mongodb_list_game_systems", {})
        display_game_systems(systems)

@app.command()
def create(
    name: str = typer.Option(None, help="System name"),
    template: str = typer.Option(None, help="Start from template"),
):
    """Define a new game system (RS-1)."""
    from monitor_agents import Orchestrator

    orchestrator = Orchestrator()

    if template:
        base = orchestrator.call_tool("mongodb_get_builtin_template", {"template": template})
        console.print(f"Starting from template: {template}")
    else:
        base = {}

    # Interactive game system creation
    if not name:
        name = prompt("System name")

    system_params = prompt_game_system_params(base)
    system_params["name"] = name

    system_id = orchestrator.call_tool("mongodb_create_game_system", system_params)
    console.print(f"[green]Created game system: {name} ({system_id})[/green]")

@app.command("import")
def import_system(
    template: str = typer.Option(None, help="Built-in template"),
    file: Path = typer.Option(None, help="JSON file path"),
    url: str = typer.Option(None, help="URL to import from"),
):
    """Import a game system (RS-2)."""
    from monitor_agents import Indexer

    indexer = Indexer()

    if template:
        system = indexer.import_builtin_template(template)
    elif file:
        system = indexer.import_game_system_file(file)
    elif url:
        system = indexer.import_game_system_url(url)
    else:
        # Show available templates
        templates = ["dnd5e", "pf2e", "fate", "pbta", "bitd", "osr", "simple"]
        console.print("Available templates:", ", ".join(templates))
        template = prompt_choice("Select template", templates)
        system = indexer.import_builtin_template(template)

    display_game_system_preview(system)

    if confirm("Import this system?"):
        system_id = indexer.save_game_system(system)
        console.print(f"[green]Imported: {system['name']} ({system_id})[/green]")

@app.command()
def template(
    system_id: str = typer.Argument(..., help="Game system ID"),
    wizard: bool = typer.Option(False, help="Interactive setup"),
):
    """Define character template for a game system (RS-3)."""
    from monitor_agents import Orchestrator

    orchestrator = Orchestrator()

    if wizard:
        template_params = prompt_character_template_params(system_id)
    else:
        # Show current template
        template = orchestrator.call_tool("mongodb_get_character_template", {
            "system_id": system_id,
        })
        display_character_template(template)
        return

    orchestrator.call_tool("mongodb_update_character_template", {
        "system_id": system_id,
        "template": template_params,
    })
    console.print("[green]Character template updated![/green]")

@app.command()
def override(
    story_id: str = typer.Option(None, help="Story ID"),
    scene_id: str = typer.Option(None, help="Scene ID"),
    rule: str = typer.Argument(None, help="Rule override text"),
    list_flag: bool = typer.Option(False, "--list", help="List active overrides"),
    remove: str = typer.Option(None, help="Remove override by ID"),
    temp: bool = typer.Option(False, help="One-time override"),
):
    """Manage rule overrides / house rules (RS-4)."""
    from monitor_agents import Resolver

    resolver = Resolver()

    if list_flag:
        overrides = resolver.call_tool("mongodb_list_rule_overrides", {
            "story_id": story_id,
        })
        display_rule_overrides(overrides)
        return

    if remove:
        resolver.call_tool("mongodb_delete_rule_override", {"override_id": remove})
        console.print(f"[green]Removed override {remove}[/green]")
        return

    if rule:
        scope = "one_time" if temp else "scene" if scene_id else "story"
        override_id = resolver.call_tool("mongodb_create_rule_override", {
            "scope": scope,
            "scope_id": scene_id or story_id,
            "override": rule,
            "created_by": "GM",
        })
        console.print(f"[green]Created override: {override_id}[/green]")

@app.command()
def view(
    system_id: str = typer.Argument(..., help="Game system ID"),
):
    """View game system details."""
    from monitor_agents import Orchestrator

    orchestrator = Orchestrator()
    system = orchestrator.call_tool("mongodb_get_game_system", {"system_id": system_id})
    display_game_system_details(system)
```

---

## Phase 10: REPL Session

### T10.1: REPLSession Class

**File:** `src/monitor_cli/repl/session.py`

**Use Cases:** P-3, P-7

```python
class REPLSession:
    def __init__(self, orchestrator: Orchestrator, story_id: str):
        self.orchestrator = orchestrator
        self.story_id = story_id
        self.scene_id: str | None = None
        self.running = True

    def run(self):
        """Main REPL loop."""
        while self.running:
            try:
                user_input = self.get_input()
                self.handle_input(user_input)
            except KeyboardInterrupt:
                self.handle_interrupt()
            except Exception as e:
                self.handle_error(e)

    def get_input(self) -> str:
        """Get user input with prompt-toolkit."""
        from prompt_toolkit import prompt
        return prompt("> ")

    def handle_input(self, user_input: str):
        """Route input to appropriate handler."""
        if user_input.startswith("/"):
            self.handle_meta_command(user_input)
        else:
            self.handle_narrative_input(user_input)

    def handle_narrative_input(self, text: str):
        """Process narrative input through agents."""
        # Delegates to orchestrator's turn loop
        self.orchestrator.process_turn(self.scene_id, text)

    def handle_meta_command(self, cmd: str):
        """Process /commands."""
        from monitor_cli.repl.handlers import META_HANDLERS
        parts = cmd[1:].split()
        command = parts[0]
        args = parts[1:]

        if command in META_HANDLERS:
            META_HANDLERS[command](self, args)
        else:
            console.print(f"Unknown command: {command}")
```

### T10.2: Meta Command Handlers

**File:** `src/monitor_cli/repl/handlers.py`

```python
def handle_status(session: REPLSession, args: list):
    """Show current scene status."""
    context = session.orchestrator.context.get_scene_context(session.scene_id)
    display_scene_status(context)

def handle_roll(session: REPLSession, args: list):
    """Roll dice."""
    formula = args[0] if args else "1d20"
    result = session.orchestrator.resolver.roll_dice(formula)
    console.print(f"Roll {formula}: {result}")

def handle_end_scene(session: REPLSession, args: list):
    """End current scene."""
    if confirm("End this scene?"):
        session.orchestrator.end_scene(session.scene_id)
        session.scene_id = None

def handle_pause(session: REPLSession, args: list):
    """Save and exit."""
    session.running = False

def handle_undo(session: REPLSession, args: list):
    """Undo last turn."""
    session.orchestrator.call_tool("mongodb_undo_turn", {
        "scene_id": session.scene_id,
    })
    console.print("Last turn undone")

def handle_recap(session: REPLSession, args: list):
    """Show recent turns."""
    turns = session.orchestrator.call_tool("mongodb_get_turns", {
        "scene_id": session.scene_id,
        "limit": 10,
    })
    display_turns(turns)

def handle_entities(session: REPLSession, args: list):
    """List entities in scene."""
    context = session.orchestrator.context.get_scene_context(session.scene_id)
    display_entity_list(context.participants)

def handle_facts(session: REPLSession, args: list):
    """Show facts about entity."""
    entity_id = args[0] if args else None
    if entity_id:
        facts = session.orchestrator.call_tool("neo4j_list_facts", {
            "entity_id": entity_id,
        })
        display_facts_table(facts)

def handle_help(session: REPLSession, args: list):
    """Show help."""
    display_help()

META_HANDLERS = {
    "status": handle_status,
    "roll": handle_roll,
    "end": handle_end_scene,
    "pause": handle_pause,
    "undo": handle_undo,
    "recap": handle_recap,
    "entities": handle_entities,
    "facts": handle_facts,
    "help": handle_help,
}
```

---

## Phase 11: UI Components

### T11.1: Output Formatting

**File:** `src/monitor_cli/ui/output.py`

```python
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()

def print_narrative(text: str):
    """Print GM narrative."""
    console.print(Panel(Markdown(text), title="GM", border_style="blue"))

def print_npc_dialogue(npc_name: str, text: str):
    """Print NPC speech."""
    console.print(f"[bold]{npc_name}:[/bold] \"{text}\"")

def print_error(message: str):
    """Print error message."""
    console.print(f"[red]Error:[/red] {message}")

def print_success(message: str):
    """Print success message."""
    console.print(f"[green]{message}[/green]")

def print_roll(formula: str, result: int, success: bool | None = None):
    """Print dice roll result."""
    style = "green" if success else "red" if success is False else "white"
    console.print(f"[{style}]Roll {formula}: {result}[/{style}]")
```

### T11.2: User Prompts

**File:** `src/monitor_cli/ui/prompts.py`

```python
from rich.prompt import Prompt, Confirm
from rich.console import Console

console = Console()

def prompt(message: str, default: str = "") -> str:
    """Prompt for text input."""
    return Prompt.ask(message, default=default)

def prompt_choice(message: str, choices: list[str]) -> str:
    """Prompt for choice selection."""
    return Prompt.ask(message, choices=choices)

def prompt_optional_choice(message: str, choices: list[str]) -> str | None:
    """Prompt for optional choice."""
    choices_with_skip = choices + ["(skip)"]
    result = Prompt.ask(message, choices=choices_with_skip)
    return None if result == "(skip)" else result

def confirm(message: str) -> bool:
    """Prompt for confirmation."""
    return Confirm.ask(message)

def prompt_universe_selection() -> str:
    """Interactive universe selection."""
    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()
    universes = orchestrator.call_tool("neo4j_list_universes", {})

    if not universes:
        console.print("No universes found. Creating new...")
        # Trigger M-4
        return create_universe_flow()

    display_universe_table(universes)
    return prompt("Select universe (ID or number)")

def prompt_story_selection(status: str = None) -> str:
    """Interactive story selection."""
    from monitor_agents import Orchestrator
    orchestrator = Orchestrator()
    stories = orchestrator.call_tool("neo4j_list_stories", {"status": status})

    display_story_table(stories)
    return prompt("Select story (ID or number)")
```

### T11.3: Table Displays

**File:** `src/monitor_cli/ui/tables.py`

```python
from rich.table import Table
from rich.console import Console

console = Console()

def display_universe_table(universes: list[dict]):
    """Display universes as table."""
    table = Table(title="Universes")
    table.add_column("#", style="dim")
    table.add_column("Name")
    table.add_column("Genre")
    table.add_column("Stories")
    table.add_column("Entities")

    for i, u in enumerate(universes, 1):
        table.add_row(
            str(i),
            u["name"],
            u["genre"],
            str(u.get("story_count", 0)),
            str(u.get("entity_count", 0)),
        )

    console.print(table)

def display_story_table(stories: list[dict]):
    """Display stories as table."""
    table = Table(title="Stories")
    table.add_column("#", style="dim")
    table.add_column("Title")
    table.add_column("Universe")
    table.add_column("Status")
    table.add_column("Scenes")

    for i, s in enumerate(stories, 1):
        table.add_row(
            str(i),
            s["title"],
            s.get("universe_name", s.get("universe_id", "")),
            s["status"],
            str(s.get("scene_count", 0)),
        )

    console.print(table)

def display_character_table(characters: list[dict]):
    """Display characters as table."""
    table = Table(title="Characters")
    table.add_column("#", style="dim")
    table.add_column("Name")
    table.add_column("Role")
    table.add_column("Universe")
    table.add_column("Status")

    for i, c in enumerate(characters, 1):
        role = c.get("properties", {}).get("role", "NPC")
        status = ", ".join(c.get("state_tags", []))
        table.add_row(
            str(i),
            c["name"],
            role,
            c.get("universe_name", ""),
            status,
        )

    console.print(table)

def display_entity_table(entities: list[dict]):
    """Display generic entities as table."""
    table = Table(title="Entities")
    table.add_column("#", style="dim")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Universe")

    for i, e in enumerate(entities, 1):
        table.add_row(
            str(i),
            e["name"],
            e["entity_type"],
            e.get("universe_name", ""),
        )

    console.print(table)

def display_facts_table(facts: list[dict]):
    """Display facts as table."""
    table = Table(title="Facts")
    table.add_column("Statement")
    table.add_column("Authority")
    table.add_column("Confidence")
    table.add_column("Canon")

    for f in facts:
        table.add_row(
            f["statement"][:60] + "..." if len(f["statement"]) > 60 else f["statement"],
            f["authority"],
            f"{f['confidence']:.0%}",
            f["canon_level"],
        )

    console.print(table)

def display_search_results(results: list[dict]):
    """Display search results."""
    for r in results:
        console.print(Panel(
            f"{r['text']}\n\n[dim]Score: {r['score']:.2f} | Type: {r['type']}[/dim]",
            title=r.get("title", "Result"),
        ))

def display_timeline(events: list[dict]):
    """Display event timeline."""
    for e in events:
        console.print(f"[dim]{e.get('time_ref', '?')}[/dim] {e['title']}")
        console.print(f"  {e['description']}")

def display_scene_status(context):
    """Display current scene status."""
    console.print(Panel(
        f"Scene: {context.scene['title']}\n"
        f"Location: {context.location['name'] if context.location else 'Unknown'}\n"
        f"Participants: {', '.join(p['name'] for p in context.participants)}\n"
        f"Turns: {len(context.recent_turns)}\n"
        f"Pending Proposals: {len(context.pending_proposals)}",
        title="Scene Status",
    ))
```

---

## Phase 12: Configuration Commands

### T12.1: Settings Subcommands

Add to `main.py`:

```python
@app.command()
def settings():
    """Configure MONITOR settings (SYS-4 to SYS-8)."""
    from monitor_cli.ui.prompts import prompt_choice

    action = prompt_choice("Settings", [
        "llm",
        "databases",
        "preferences",
        "export",
        "import",
    ])

    match action:
        case "llm": configure_llm()
        case "databases": configure_databases()
        case "preferences": configure_preferences()
        case "export": export_data()
        case "import": import_data()
```

---

## Phase 13: Testing

### T13.1: Unit Tests

```
tests/
├── conftest.py
├── test_commands/
│   ├── test_play.py
│   ├── test_manage.py
│   ├── test_ingest.py
│   └── test_query.py
├── test_repl/
│   ├── test_session.py
│   └── test_handlers.py
└── test_ui/
    ├── test_output.py
    ├── test_prompts.py
    └── test_tables.py
```

### T13.2: Integration Tests

- Full CLI workflow tests
- REPL interaction tests
- Command chaining tests

---

## Completion Checklist

```
[ ] T1: Package setup
[ ] T2: Main entry point
[ ] T3: Play commands (P-1 to P-12)
[ ] T4: Manage commands (M-1 to M-30)
[ ] T5: Ingest commands (I-1 to I-5)
[ ] T6: Query commands (Q-1 to Q-8)
[ ] T7: Copilot commands (CF-1 to CF-5)
[ ] T8: Story commands (ST-1 to ST-5)
[ ] T9: Rules commands (RS-1 to RS-4)
[ ] T10: REPL session + handlers
[ ] T11: UI components (output, prompts, tables)
[ ] T12: Settings commands (SYS-*)
[ ] T13: Tests
```

---

## Dependencies

```
INTERNAL: monitor-agents (Layer 2)
EXTERNAL: typer, rich, prompt-toolkit
```

---

## Command Reference

### Core Commands (7 groups)

| Command Group | Use Cases | Mode |
|---------------|-----------|------|
| `monitor play` | P-1 to P-12 | Solo Play |
| `monitor manage` | M-1 to M-30 | World Design |
| `monitor query` | Q-1 to Q-8 | — |
| `monitor ingest` | I-1 to I-5 | — |
| `monitor copilot` | CF-1 to CF-5 | GM Assistant |
| `monitor story` | ST-1 to ST-5 | — |
| `monitor rules` | RS-1 to RS-4 | — |

### Detailed Command Reference

| Command | Use Case | Description |
|---------|----------|-------------|
| `monitor play` | SYS-2 | Interactive play menu |
| `monitor play new` | P-1 | Start new story |
| `monitor play continue` | P-12 | Continue story |
| `monitor manage universes` | M-5 | List universes |
| `monitor manage universes create` | M-4 | Create universe |
| `monitor manage stories` | M-9 | List stories |
| `monitor manage characters` | Q-3 | List characters |
| `monitor manage characters create-pc` | M-13 | Create PC |
| `monitor ingest upload FILE` | I-1 | Upload document |
| `monitor ingest review` | I-4 | Review proposals |
| `monitor query search QUERY` | Q-1 | Semantic search |
| `monitor query entities` | Q-3 | Browse entities |
| `monitor query facts` | Q-4 | Explore facts |
| `monitor query timeline` | Q-5 | View timeline |
| `monitor query graph ENTITY` | Q-6 | Relationship graph |
| `monitor copilot record` | CF-1 | Record live session |
| `monitor copilot recap` | CF-2 | Generate recap |
| `monitor copilot threads` | CF-3 | Detect unresolved threads |
| `monitor copilot suggest` | CF-4 | Suggest plot hooks |
| `monitor copilot validate` | CF-5 | Detect contradictions |
| `monitor story plan` | ST-1 | Plan story arc |
| `monitor story factions` | ST-2 | Model faction goals |
| `monitor story whatif` | ST-3 | Simulate what-if |
| `monitor story mystery` | ST-4 | Design mystery |
| `monitor story balance` | ST-5 | Check player agency |
| `monitor rules create` | RS-1 | Define game system |
| `monitor rules import` | RS-2 | Import game system |
| `monitor rules template` | RS-3 | Character template |
| `monitor rules override` | RS-4 | House rules |
| `monitor settings` | SYS-* | Configuration |
