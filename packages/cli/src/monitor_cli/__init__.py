"""
================================================================================
MONITOR CLI Layer (Layer 3 of 3)
================================================================================

This is the TOP layer of the MONITOR stack. It provides:
- Command-line interface for users
- Interactive REPL for gameplay
- Commands for ingestion, query, management
- User-facing output formatting

ARCHITECTURE RULES:
==================
1. This package depends ONLY on monitor-agents (Layer 2)
2. This package does NOT import from monitor-data-layer (Layer 1) directly
3. Nothing depends on this package (it's the user-facing top)
4. All data access goes through agents, never direct DB calls

IMPORT HIERARCHY:
================
    cli (Layer 3)  ← YOU ARE HERE
         ↓ imports
    agents (Layer 2)
         ↓ imports
    data-layer (Layer 1)
         ↓ imports
    external libraries + databases

WHY NO DIRECT DATA-LAYER ACCESS:
================================
The CLI should never bypass agents to access databases directly because:
1. Authority enforcement happens in the data layer via agent context
2. Agents contain business logic (e.g., canonization policy)
3. Direct access would violate the layered architecture
4. Testing becomes harder without clear boundaries

COMMANDS:
========
    monitor play      - Start or continue a story (interactive REPL)
    monitor ingest    - Upload and process source documents
    monitor query     - Query canonical facts and entities
    monitor manage    - Entity, universe, and campaign management

EXAMPLE USAGE:
=============
    $ monitor play --story "My Campaign"
    $ monitor ingest ./dnd_phb.pdf --universe "Forgotten Realms"
    $ monitor query "What is Gandalf's current status?"
    $ monitor manage entities --universe "Middle-earth"

================================================================================
"""

__version__ = "0.1.0"
__layer__ = 3
__layer_name__ = "cli"

# Re-export key components (to be implemented)
# from monitor_cli.main import app
