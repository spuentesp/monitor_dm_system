# MONITOR Today: What Works, What's Missing, and What's Next

*Fourth and final part of the series (for now). The real state of the system in June 2026.*

---

This is the part where it would be easy to finish with a list of impressive features and a promise that everything is almost ready. I am not going to do that.

MONITOR is a functional project with technical debt, uncovered edge cases, and half-finished flows. It is also the most ambitious system I've ever built, and there are parts that work better than I ever expected. Both things are true at the same time.

---

## What Works Today

### The Web Interface

The main game mode is a web interface: chat with the GM, character management, scene state visualization. The backend runs on FastAPI, the frontend on Next.js.

It isn't pretty yet. But it is functional — you can create a universe, ingest documents, start a session, and play full turns with the system as a GM.

### The CLI Commands

Eight command groups available:

```bash
monitor play        # start or continue a story
monitor manage      # manage entities (NPCs, places, items)
monitor universe    # create and administer universes
monitor ingest      # ingest documents to the world knowledge base
monitor state       # character state (HP, resources)
monitor rules       # manage game systems
monitor mechanics   # resolve mechanics (rolls, checks)
monitor playtest    # run automated testing sessions
```

### The MCP Data Layer

Four families of active MCP tools: `neo4j_*`, `mongodb_*`, `qdrant_*`, `ingest_*`. Agents call them asynchronously to read and write data without tightly coupling to the database clients.

The enforcement of architectural layers is ruthless. If you open `packages/cli/src/monitor_cli/commands/play.py`, the header docstring makes it clear:
```python
"""
MONITOR Play — Solo Play interactive REPL.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2)
NEVER IMPORTS: monitor_data (Layer 1)
"""
```


### The Tests

Approximately 5,900 tests in the full suite. Unit and integration tests run without network or API keys — everything is mocked. E2E tests require the full stack running.

```bash
uv run pytest packages tests -q          # ~5900 tests, < 6 minutes
RUN_E2E=1 uv run pytest tests/e2e -q    # full stack e2e
```

### The LLM-as-Player Playtest

The most reliable indicator of system health: we run sessions where a second LLM acts as the player and see if the session holds up from start to finish.

The logs for those sessions are in `tests/e2e/logs/`. The most recent one was a 13-entry session, `player_mode: llm`, zero fallbacks, zero GM clarification questions. The narration is coherent. World state updates correctly. Dice roll when they should.

---

## What's Missing

What frustrates me most today isn't the architecture, it's the **latency**. When a player declares a complex action, the system has to build context, ask the GMAgent for a verdict, resolve the mechanics, and then generate the final prose. That's multiple calls to large models in series. Technically it works flawlessly, and the state remains immaculate. But from the moment you press 'Enter' until you read the response, it can take 10 seconds or more. At a real table, the GM replies instantly. That pause inevitably pulls you out of the fiction.

Some concrete points on current status:

**Co-Pilot mode is incomplete.** The architecture for the system to assist a human GM — taking session notes, detecting contradictions, suggesting hooks — is designed and partially implemented. But there is no polished user flow yet.

**The UI needs work.** Chat works. Character management works. World graph visualization is basic. Everything related to World Design — building a universe from scratch, managing ontology, reviewing proposed entities — mostly lives in the CLI.

**Document ingestion is fragile with complex PDFs.** Well-structured PDFs (single column, clean text) ingest nicely. Rulebooks with multiple columns, complex tables, or lots of text baked into images still cause problems.

**The CanonKeeper needs more evaluation policies.** Today it detects direct contradictions. It doesn't yet detect subtler inconsistencies — logical implications that clash, state changes that are impossible given history.

---

## What I Learned in the Process

The hardest part wasn't getting the LLMs to write good prose. It was getting them to stop writing.

At first, I wasted entire weeks trying to fix consistency problems by tweaking *system prompts*. "Don't invent NPCs." "Use only the rulebook." It doesn't work. The model is a stochastic engine designed to predict the next word, not a relational database.

If I were starting over, I wouldn't waste a single day on *prompt engineering* for state control. I would build the CanonKeeper barrier and the tool architecture from day one. Hard rules are resolved in Python. Prose and intent interpretation are delegated to the LLM. When I separated those two things — deterministic reasoning on one side, and stochastic generation on the other — the system actually started to work.

## What's Next

The immediate roadmap has two priorities:

**First, Co-Pilot mode.** This has the clearest use case for someone who already runs games — having an assistant that remembers everything that happened in the campaign, detects inconsistencies, and alerts you when the story is tangling up. It doesn't require the player to cede narrative control.

**Second, the World Design UI.** The data model for building worlds is solid. What's missing is an interface that makes the process accessible without writing CLI commands.

Long term, what I am most interested in exploring is the parallel universe model — the ability to take an existing world, diverge it at a specific historical point, and explore what would have happened if a key decision was different. The architecture already supports it. The user flow just doesn't exist yet.

---

## Closing

MONITOR is a project that started with a simple question: can I build a system that remembers a world and narrates it without making things up?

The answer, after several years and many layers of architecture, is: yes, conditionally. The system remembers. It doesn't invent (or when it tries, there is a barrier stopping it). And it can narrate with a quality that still surprises me sometimes when I read the test session logs.

There is a long way to go. But it is a living project, and that is enough for now.

Building MONITOR taught me that the best way to truly understand how generative AI works is not to ask it clever questions in a chat window. It is to try to couple it to a strict database and force it to respect the rules.

It is a massive personal project, and it will probably never be completely "finished". But every time I read the log of an automated session where the system perfectly applies an obscure *City of Mist* rule, without anyone having programmed that mechanic by hand... I know the technical effort was worth it.

*If you made it this far and are interested in following the development, the repository is public: [github.com/spuentesp/monitor_dm_system](https://github.com/spuentesp/monitor_dm_system)*
